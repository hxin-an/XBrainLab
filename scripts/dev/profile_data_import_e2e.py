#!/usr/bin/env python3
"""Record a redacted, product-equivalent Qt Data Import timing profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any, ClassVar

import psutil
from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
from PyQt6.QtWidgets import QFileDialog

from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_source_identity,
    validate_source_identity,
)
from scripts.dev.fetch_public_eeg_fixtures import resolve_public_fixture_dir
from tests.integration.ui.data_import_wizard_harness import (
    BbciWizardDriver,
    Heartbeat,
    P300BidsWizardDriver,
    SuggestedLabelWizardDriver,
    build_dataset_panel_for_runner,
)
from tests.integration.ui.modal_helpers import visible_modal_dialog
from XBrainLab.ui.async_command_runner import application_command_registry

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = ROOT / "build" / "dev-artifacts" / "import-e2e"
SCHEMA_VERSION = 1
REPO_ROOT_TOKEN = "<repo-root>"  # noqa: S105 - redaction marker, not a secret
REQUIRED_EVENTS = (
    "import_clicked",
    "chooser_accepted",
    "review_ready",
    "apply_clicked",
    "dataset_ready",
    "background_idle",
)
TIMED_STAGES = (
    "chooser_seconds",
    "review_seconds",
    "review_interaction_seconds",
    "apply_seconds",
    "background_idle_seconds",
)
TIMING_FIELDS = (*TIMED_STAGES, "stable_idle_seconds")
_ABSOLUTE_POSIX = re.compile(r"(?<![\w<])/(?:[^\s\\\"'<>]+/)*[^\s\\\"'<>]+")
_ABSOLUTE_WINDOWS = re.compile(
    r"(?<![\w])(?:[A-Za-z]:[\\/])(?:[^\s\\\"'<>]+[\\/])*[^\s\\\"'<>]+"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ImportWorkload:
    id: str
    title: str
    source_shape: str
    fixture_group: str
    expected_raw_count: int
    selected_run_count: int
    label_mode: str
    source_path: Path

    def artifact_scope(self) -> dict[str, Any]:
        return {
            key: value for key, value in vars(self).items() if key != "source_path"
        } | {"source_basename": self.source_path.name}


@dataclass(frozen=True)
class TimelineEvent:
    name: str
    at_seconds: float


class DevImportTracer:
    _CHECKPOINT_PHASES: ClassVar[dict[str, str]] = {
        "Loading reviewed EEG recordings": "apply_raw_load",
        "Binding reviewed source identity": "apply_source_identity",
        "Applying reviewed channel metadata": "apply_channels",
        "Applying reviewed recording metadata": "apply_metadata",
        "Applying reviewed label carriers": "apply_labels",
        "Verifying prepared import content": "apply_identity_verification",
        "Preparing interpretation candidate": "review_candidate",
        "Checking selected EEG data": "review_publish",
        "Preparing selected EEG data": "review_admission",
    }
    _REQUIRED_APPLY_PHASES: ClassVar[frozenset[str]] = frozenset(
        {
            "worker_start",
            "apply_raw_load",
            "apply_source_identity",
            "apply_channels",
            "apply_metadata",
            "apply_labels",
            "apply_identity_verification",
            "apply_commit",
        }
    )
    _NUMBERED_RAW_LOAD_STAGE: ClassVar[re.Pattern[str]] = re.compile(
        r"Loading EEG recording [1-9][0-9]* of [1-9][0-9]*"
    )

    def __init__(self) -> None:
        self.events: list[tuple[str, float]] = []
        self.available = True
        self.reason = ""
        self._patches: list[tuple[Any, str, Any, bool]] = []

    def record(self, phase: str, *, at_seconds: float | None = None) -> None:
        self.events.append(
            (phase, time.perf_counter() if at_seconds is None else at_seconds)
        )

    def record_checkpoint(self, stage: str, *, at_seconds: float | None = None) -> None:
        stage_text = str(stage)
        phase = self._CHECKPOINT_PHASES.get(stage_text)
        if phase is None and self._NUMBERED_RAW_LOAD_STAGE.fullmatch(stage_text):
            phase = "apply_raw_load"
        self.record(
            phase or "checkpoint",
            at_seconds=at_seconds,
        )

    def record_boundary(self, stage: str, *, at_seconds: float | None = None) -> None:
        self.record(
            "apply_commit"
            if str(stage) == "Committing interpreted dataset"
            else "commit_boundary",
            at_seconds=at_seconds,
        )

    def install(self, *, runtime: Any, panel: Any) -> None:
        if application_command_registry().active_count(panel):
            raise RuntimeError(
                "cannot install import tracer while a UI worker is active"
            )
        waiter = getattr(runtime, "wait_for_background_tasks", None)
        if callable(waiter) and not waiter(timeout=0.0):
            raise RuntimeError("cannot install import tracer before runtime is idle")
        service_getter = getattr(runtime, "_service", None)
        if not callable(service_getter):
            self.available = False
            self.reason = "runtime does not expose the dev service seam"
            return
        try:
            service = service_getter()
            self._patch(service, "begin_owned_operation", "operation_allocated")
            self._patch(service, "_execute_owned_operation", "worker_start")
            from XBrainLab.backend.application import data_interpretation_service
            from XBrainLab.backend.application import service as application_service
            from XBrainLab.backend.services import dataset_state_service

            for module in (
                application_service,
                data_interpretation_service,
                dataset_state_service,
            ):
                if hasattr(module, "owned_work_checkpoint"):
                    self._patch(module, "owned_work_checkpoint", "checkpoint")
                if hasattr(module, "owned_work_commit_boundary"):
                    self._patch(module, "owned_work_commit_boundary", "boundary")
        except Exception as exc:
            self.restore()
            self.available = False
            self.reason = f"dev trace seam unavailable: {type(exc).__name__}"

    def _patch(self, owner: Any, name: str, kind: str) -> None:
        original = getattr(owner, name)
        had_instance_value = name in getattr(owner, "__dict__", {})
        self._patches.append((owner, name, original, had_instance_value))

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            if kind == "operation_allocated":
                result = original(*args, **kwargs)
                self.record(kind)
                return result
            if kind == "worker_start":
                self.record(kind)
            elif kind == "checkpoint":
                self.record_checkpoint(str(args[0]))
            else:
                self.record_boundary(str(args[0]))
            return original(*args, **kwargs)

        setattr(owner, name, wrapped)

    def restore(self) -> None:
        while self._patches:
            owner, name, original, had_instance_value = self._patches.pop()
            if had_instance_value:
                setattr(owner, name, original)
            else:
                delattr(owner, name)

    def summary(self, *, started_at: float, ended_at: float) -> dict[str, Any]:
        if not self.available:
            return {"available": False, "reason": self.reason, "phase_durations": []}
        phases = {name for name, _ in self.events}
        missing_apply = sorted(self._REQUIRED_APPLY_PHASES - phases)
        if not self.events or missing_apply:
            return {
                "available": False,
                "reason": "required apply trace boundary was not observed: "
                + ", ".join(missing_apply),
                "events": [
                    {
                        "phase": phase,
                        "after_import_seconds": round(at - started_at, 6),
                    }
                    for phase, at in sorted(self.events, key=lambda item: item[1])
                ],
                "phase_durations": [],
            }
        events = sorted(self.events, key=lambda item: item[1])
        durations: dict[str, float] = {}
        for (phase, at), (_, next_at) in pairwise([*events, ("terminal", ended_at)]):
            durations[phase] = durations.get(phase, 0.0) + max(next_at - at, 0.0)
        return {
            "available": True,
            "events": [
                {
                    "phase": phase,
                    "after_import_seconds": round(at - started_at, 6),
                }
                for phase, at in events
            ],
            "phase_durations": [
                {"phase": phase, "seconds": round(seconds, 6)}
                for phase, seconds in durations.items()
                if seconds > 0
            ],
            "event_count": len(events),
            "started_after_import_seconds": round(events[0][1] - started_at, 6),
        }


class ProcessSampler:
    def __init__(self, interval_seconds: float = 0.02) -> None:
        self.interval_seconds = interval_seconds
        self._process = psutil.Process()
        self._samples: list[tuple[float, int, float, int, int]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._result: dict[str, float | int] | None = None

    def start(self) -> None:
        self._sample()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self._sample()

    def _sample(self) -> None:
        try:
            cpu = self._process.cpu_times()
            io = self._process.io_counters()
            row = (
                time.perf_counter(),
                self._process.memory_info().rss,
                float(cpu.user + cpu.system),
                int(io.read_bytes),
                int(io.write_bytes),
            )
        except (psutil.Error, OSError):
            return
        self._samples.append(row)

    def stop(self) -> dict[str, float | int]:
        if self._result is not None:
            return dict(self._result)
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(self.interval_seconds * 4, 0.1))
        self._sample()
        samples = list(self._samples)
        if len(samples) < 2:
            self._result = {
                "sample_count": len(samples),
                "sample_interval_seconds": self.interval_seconds,
            }
            return dict(self._result)
        first, last = samples[0], samples[-1]
        wall = max(last[0] - first[0], 1e-9)
        self._result = {
            "sample_count": len(samples),
            "sample_interval_seconds": self.interval_seconds,
            "cpu_seconds": round(max(last[2] - first[2], 0.0), 6),
            "mean_cpu_utilization": round(max(last[2] - first[2], 0.0) / wall, 6),
            "peak_rss_bytes": max(row[1] for row in samples),
            "rss_delta_bytes": last[1] - first[1],
            "read_bytes": max(last[3] - first[3], 0),
            "write_bytes": max(last[4] - first[4], 0),
        }
        return dict(self._result)


def default_workloads(repo_root: Path = ROOT) -> tuple[ImportWorkload, ...]:
    public_root = resolve_public_fixture_dir()
    return (
        ImportWorkload(
            "bbci_gdf_file",
            "BBCI Competition III single-file import",
            "file",
            "bbci-gdf",
            1,
            1,
            "embedded_events",
            public_root / "bbci-competition-iii-O3VR.gdf",
        ),
        ImportWorkload(
            "graz_gdf_mat_folder",
            "Graz A01T-A03T folder import with MAT labels",
            "folder",
            "graz-a01t-a03t-mat",
            3,
            3,
            "external_mat_event_order",
            repo_root / "tests" / "fixtures" / "data" / "A01T.gdf",
        ),
        ImportWorkload(
            "openneuro_p300_bids",
            "OpenNeuro ds003061 P300 subject 001",
            "bids",
            "openneuro-ds003061-p300",
            3,
            3,
            "bids_events_value_onset",
            public_root / "openneuro-ds003061-p300",
        ),
    )


def redact_paths(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): redact_paths(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_paths(item) for item in value]
    if not isinstance(value, str):
        return value
    if _ABSOLUTE_POSIX.search(value) or _ABSOLUTE_WINDOWS.search(value):
        return "<redacted-path>"
    return value


def contains_absolute_path(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(contains_absolute_path(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(contains_absolute_path(item) for item in value)
    return isinstance(value, str) and bool(
        _ABSOLUTE_POSIX.search(value) or _ABSOLUTE_WINDOWS.search(value)
    )


def summarize_timeline(events: Sequence[TimelineEvent]) -> dict[str, float]:
    by_name: dict[str, float] = {}
    previous = -math.inf
    for event in events:
        if event.at_seconds < previous:
            raise ValueError("timeline timestamps must be monotonic")
        previous = event.at_seconds
        if event.name in by_name:
            raise ValueError(f"timeline event was recorded twice: {event.name}")
        by_name[event.name] = event.at_seconds
    missing = [name for name in REQUIRED_EVENTS if name not in by_name]
    if missing:
        raise ValueError(f"timeline is missing required event(s): {', '.join(missing)}")
    start = by_name["import_clicked"]
    return {
        "chooser_seconds": round(by_name["chooser_accepted"] - start, 6),
        "review_seconds": round(
            by_name["review_ready"] - by_name["chooser_accepted"], 6
        ),
        "review_interaction_seconds": round(
            by_name["apply_clicked"] - by_name["review_ready"], 6
        ),
        "apply_seconds": round(by_name["dataset_ready"] - by_name["apply_clicked"], 6),
        "background_idle_seconds": round(
            by_name["background_idle"] - by_name["dataset_ready"], 6
        ),
        "stable_idle_seconds": round(by_name["background_idle"] - start, 6),
    }


def summarize_heartbeat(ticks: Sequence[float]) -> dict[str, float | int]:
    gaps = [max(current - prior, 0.0) for prior, current in pairwise(ticks)]
    if not gaps:
        return {
            "tick_count": len(ticks),
            "p95_gap_seconds": 0.0,
            "max_gap_seconds": 0.0,
        }
    ordered = sorted(gaps)
    index = min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)
    return {
        "tick_count": len(ticks),
        "p95_gap_seconds": round(ordered[index], 6),
        "max_gap_seconds": round(max(gaps), 6),
    }


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value))


def validate_workload_correctness(
    workload_id: str,
    value: object,
) -> str | None:
    expected_raw_count = {
        "bbci_gdf_file": 1,
        "graz_gdf_mat_folder": 3,
        "openneuro_p300_bids": 3,
    }.get(workload_id)
    if expected_raw_count is None:
        return "unknown workload"
    if not isinstance(value, Mapping):
        return "correctness is missing"
    if value.get("raw_file_count") != expected_raw_count:
        return "unexpected raw file count"
    if value.get("applied") is not True:
        return "interpretation was not applied"
    if not _is_sha256(value.get("event_sample_label_digest")):
        return "event digest is missing"
    recipe = value.get("recipe_identity")
    if not isinstance(recipe, Mapping) or not _is_sha256(
        recipe.get("reviewed_content_identity_digest")
    ):
        return "reviewed content identity is missing"
    if (
        not isinstance(recipe.get("applied_interpretation_id"), str)
        or not recipe["applied_interpretation_id"]
    ):
        return "applied interpretation identity is missing"
    if "saved_recipe_id" not in recipe:
        return "saved recipe identity is missing"
    labels = value.get("label_status")
    if not isinstance(labels, Mapping):
        return "label status is missing"
    expected_labels = {
        "bbci_gdf_file": ("file", "embedded_events", 0, 0),
        "graz_gdf_mat_folder": ("folder", "external_carriers", 3, 1),
        "openneuro_p300_bids": ("bids", "external_carriers", 3, 1),
    }[workload_id]
    if (
        labels.get("source_kind"),
        labels.get("mode"),
        labels.get("carrier_count"),
        labels.get("label_import_count"),
    ) != expected_labels:
        return "label mode or carrier result is unexpected"
    if workload_id == "graz_gdf_mat_folder":
        if labels.get("selected_fields") != ["classlabel"] * 3:
            return "MAT label field selection is unexpected"
        return None
    if workload_id == "openneuro_p300_bids":
        class_names = labels.get("class_names")
        if labels.get("bids_detected") is not True:
            return "BIDS detection is missing"
        if not isinstance(class_names, list) or set(class_names) != {
            "noise",
            "oddball",
            "standard",
        }:
            return "BIDS class names are unexpected"
        metadata = value.get("dataset_metadata")
        if not isinstance(metadata, Mapping):
            return "BIDS dataset metadata is missing"
        if metadata.get("channel_count") != 79:
            return "BIDS channel count is unexpected"
        if metadata.get("positioned_channel_count") != 0:
            return "BIDS unexpectedly positioned channels"
        if metadata.get("electrode_layout_source") != "":
            return "BIDS unexpectedly applied an electrode layout"
    return None


def _correctness_signature(item: Mapping[str, Any]) -> str | None:
    correctness = item.get("correctness")
    if not isinstance(correctness, Mapping):
        return None
    recipe = correctness.get("recipe_identity")
    digest = correctness.get("event_sample_label_digest")
    content = (
        recipe.get("reviewed_content_identity_digest")
        if isinstance(recipe, Mapping)
        else None
    )
    if (
        not isinstance(correctness.get("raw_file_count"), int)
        or correctness.get("applied") is not True
        or not _is_sha256(digest)
        or not _is_sha256(content)
        or not isinstance(recipe.get("applied_interpretation_id"), str)
        or not recipe["applied_interpretation_id"]
        or "saved_recipe_id" not in recipe
    ):
        return None
    return _identity_digest(
        {
            "raw_file_count": correctness["raw_file_count"],
            "applied": correctness["applied"],
            "event_sample_label_digest": digest,
            "recipe_identity": dict(recipe),
            "label_status": correctness.get("label_status"),
            "dataset_metadata": correctness.get("dataset_metadata"),
        }
    )


def aggregate_passes(
    passes: Sequence[Mapping[str, Any]],
    *,
    required_count: int,
    workload_id: str | None = None,
) -> dict[str, Any]:
    passed = [item for item in passes if item.get("status") == "passed"]
    complete = len(passes) == required_count and len(passed) == required_count
    failed = {
        "ok": False,
        "passed_pass_count": len(passed),
        "required_pass_count": required_count,
        "ranked_stages": [],
    }
    if not complete:
        return failed
    if any(
        not isinstance(item.get("timeline"), Mapping)
        or any(stage not in item["timeline"] for stage in TIMING_FIELDS)
        for item in passed
    ):
        return failed | {"reason": "a passed run is missing required timing fields"}
    signatures = {_correctness_signature(item) for item in passed}
    if None in signatures or len(signatures) != 1:
        return failed | {"reason": "measured passes disagree on correctness identity"}
    if workload_id is not None:
        for item in passed:
            correctness_error = validate_workload_correctness(
                workload_id,
                item.get("correctness"),
            )
            if correctness_error is not None:
                return failed | {"reason": correctness_error}
    medians = {
        stage: statistics.median(float(item["timeline"][stage]) for item in passed)
        for stage in TIMED_STAGES
    }
    ranked = [
        {
            "stage": stage,
            "median_seconds": round(value, 6),
            "share": round(value / max(sum(medians.values()), 1e-9), 6),
        }
        for stage, value in sorted(
            medians.items(), key=lambda item: item[1], reverse=True
        )
    ]
    return {
        "ok": True,
        "passed_pass_count": len(passed),
        "required_pass_count": required_count,
        "median_stable_idle_seconds": round(
            statistics.median(
                float(item["timeline"]["stable_idle_seconds"]) for item in passed
            ),
            6,
        ),
        "ranked_stages": ranked,
        "dominant_stage": ranked[0]["stage"]
        if ranked and ranked[0]["share"] >= 0.35
        else None,
    }


def build_artifact(
    *,
    source_identity: Mapping[str, Any],
    environment: Mapping[str, Any],
    workloads: Sequence[ImportWorkload],
    workload_runs: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    return redact_paths(
        {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(UTC).isoformat(),
            "generator": "scripts/dev/profile_data_import_e2e.py",
            "source_identity": dict(source_identity),
            "environment": dict(environment),
            "workloads": [workload.artifact_scope() for workload in workloads],
            "runs": dict(workload_runs),
            "claim_boundary": {
                "supports": "Measured Qt Dataset Import timing on the recorded platform.",
                "does_not_support": "A Windows result on another platform, loader optimization, or arbitrary dataset performance.",
            },
        }
    )


def _validate_recorded_source_identity(
    value: object,
    *,
    current_identity: Mapping[str, Any] | None,
    repo_root: Path,
) -> tuple[bool, str]:
    if not isinstance(value, Mapping):
        return False, "profile source identity has an invalid shape"
    if value.get("repo_root") != REPO_ROOT_TOKEN:
        return False, "profile source identity must redact its repository root"
    actual_root = repo_root.expanduser().resolve()
    recorded = dict(value)
    recorded["repo_root"] = str(actual_root)
    current = (
        dict(current_identity)
        if current_identity is not None
        else collect_source_identity(actual_root, refresh=True)
    )
    return validate_source_identity(
        recorded,
        expected_repo_root=actual_root,
        refresh=True,
        current_identity=current,
        artifact_name="Data Import E2E profile",
    )


def validate_artifact(
    payload: Mapping[str, Any],
    *,
    current_identity: Mapping[str, Any] | None = None,
    repo_root: Path = ROOT,
) -> tuple[bool, str]:
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("generator") != "scripts/dev/profile_data_import_e2e.py"
    ):
        return False, "unexpected schema"
    if contains_absolute_path(payload):
        return False, "artifact contains an absolute path fragment"
    required = {"source_identity", "environment", "workloads", "runs", "claim_boundary"}
    if not required.issubset(payload):
        return False, "missing required artifact field"
    workloads, runs = payload["workloads"], payload["runs"]
    if (
        not isinstance(workloads, list)
        or not workloads
        or not isinstance(runs, Mapping)
    ):
        return False, "workloads or runs has an invalid shape"
    source_ok, source_reason = _validate_recorded_source_identity(
        payload["source_identity"],
        current_identity=current_identity,
        repo_root=repo_root,
    )
    if not source_ok:
        return False, source_reason
    environment = payload["environment"]
    if not isinstance(environment, Mapping):
        return False, "environment has an invalid shape"
    trace_modes = environment.get("measured_trace_modes")
    if not isinstance(trace_modes, Mapping):
        return False, "environment is missing per-workload trace modes"
    workload_ids = [
        item.get("id") if isinstance(item, Mapping) else None for item in workloads
    ]
    if (
        any(not isinstance(identifier, str) for identifier in workload_ids)
        or len(set(workload_ids)) != len(workload_ids)
        or set(runs) != set(workload_ids)
        or set(trace_modes) != set(workload_ids)
        or not all(mode in {"coarse", "detailed"} for mode in trace_modes.values())
    ):
        return False, "environment trace modes do not match the workload matrix"
    distinct_modes = set(trace_modes.values())
    expected_trace_mode = (
        next(iter(distinct_modes)) if len(distinct_modes) == 1 else "mixed"
    )
    if environment.get("trace_mode") != expected_trace_mode:
        return False, "environment trace mode is inconsistent"
    fields = {
        "events",
        "heartbeat",
        "process_resources",
        "correctness",
        "fixture",
        "trace",
    }
    for workload in workloads:
        identifier = workload.get("id") if isinstance(workload, Mapping) else None
        run = runs.get(identifier)
        if (
            not isinstance(identifier, str)
            or not isinstance(run, Mapping)
            or not isinstance(run.get("passes"), list)
        ):
            return False, "workload is missing an id or pass list"
        for item in run["passes"]:
            if not isinstance(item, Mapping) or item.get("status") != "passed":
                continue
            trace, correctness = item.get("trace"), item.get("correctness")
            if (
                not isinstance(item.get("timeline"), Mapping)
                or not set(TIMING_FIELDS).issubset(item["timeline"])
                or not fields.issubset(item)
                or not isinstance(trace, Mapping)
                or not isinstance(trace.get("available"), bool)
                or _correctness_signature(item) is None
            ):
                return False, f"passed {identifier} run is incomplete"
            correctness_error = validate_workload_correctness(
                identifier,
                correctness,
            )
            if correctness_error is not None:
                return False, f"passed {identifier} run is invalid: {correctness_error}"
    return True, "ok"


def render_markdown(payload: Mapping[str, Any]) -> str:
    lines = ["# Data Import E2E Profile", ""]
    for workload in payload.get("workloads", []):
        if isinstance(workload, Mapping):
            run = payload.get("runs", {}).get(workload.get("id"), {})
            summary = run.get("summary", {}) if isinstance(run, Mapping) else {}
            lines += [
                f"## {workload.get('title', workload.get('id', 'workload'))}",
                f"Status `{summary.get('ok', False)}` · median stable idle `{summary.get('median_stable_idle_seconds', 'n/a')}` s · dominant `{summary.get('dominant_stage', 'n/a')}`",
                "",
            ]
    lines += [
        "## Claim boundary",
        str(payload.get("claim_boundary", {}).get("does_not_support", "")),
        "",
    ]
    return "\n".join(lines)


def write_artifacts(payload: Mapping[str, Any], output_dir: Path) -> tuple[Path, Path]:
    ok, reason = validate_artifact(payload)
    if not ok:
        raise ValueError(f"refusing to write invalid profile: {reason}")
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "import-e2e-profile.json"
    markdown_path = output_dir / "import-e2e-profile.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    return json_path, markdown_path


def source_identity(repo_root: Path = ROOT) -> dict[str, Any]:
    identity = collect_source_identity(repo_root, refresh=True)
    identity["repo_root"] = REPO_ROOT_TOKEN
    return identity


def environment_identity(
    *,
    measured_trace_modes: Mapping[str, str],
) -> dict[str, Any]:
    if not measured_trace_modes:
        raise ValueError("measured trace modes are required for every workload")
    modes = set(measured_trace_modes.values())
    return {
        "platform": sys.platform,
        "platform_release": platform.release(),
        "python": sys.version.split()[0],
        "qt": QT_VERSION_STR,
        "pyqt": PYQT_VERSION_STR,
        "trace_mode": next(iter(modes)) if len(modes) == 1 else "mixed",
        "measured_trace_modes": dict(measured_trace_modes),
    }


def fixture_inventory(workload: ImportWorkload) -> dict[str, int]:
    if workload.id == "graz_gdf_mat_folder":
        root = workload.source_path.parent
        files = [
            *(root / f"A0{index}T.gdf" for index in range(1, 4)),
            *(root / "label" / f"A0{index}T.mat" for index in range(1, 4)),
        ]
    elif workload.source_path.is_dir():
        files = [item for item in workload.source_path.rglob("*") if item.is_file()]
    else:
        files = [workload.source_path]
    existing = [item for item in files if item.is_file()]
    return {
        "file_count": len(existing),
        "total_bytes": sum(item.stat().st_size for item in existing),
    }


def event_sample_label_digest(study: Any) -> str:
    rows: list[tuple[int, str]] = []
    for data in study.loaded_data_list:
        events, event_id = data.get_event_list()
        labels = {int(value): str(name) for name, value in event_id.items()}
        rows.extend(
            (int(event[0]), labels[int(event[2])])
            for event in events
            if int(event[2]) in labels
        )
    encoded = json.dumps(sorted(rows), ensure_ascii=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _identity_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _materialize_graz_folder(
    workload: ImportWorkload,
) -> tempfile.TemporaryDirectory[str]:
    data_root = workload.source_path.parent
    label_root = data_root / "label"
    names = ("A01T", "A02T", "A03T")
    required = [
        *(data_root / f"{name}.gdf" for name in names),
        *(label_root / f"{name}.mat" for name in names),
    ]
    if not all(path.is_file() for path in required):
        missing = [path.name for path in required if not path.is_file()]
        raise FileNotFoundError(f"Graz folder fixtures are unavailable: {missing!r}")
    temporary = tempfile.TemporaryDirectory(prefix="xbrainlab-graz-folder-")
    root = Path(temporary.name)
    (root / "label").mkdir()
    for name in names:
        shutil.copy2(data_root / f"{name}.gdf", root / f"{name}.gdf")
        shutil.copy2(label_root / f"{name}.mat", root / "label" / f"{name}.mat")
    return temporary


def _base_correctness(state: Any, study: Any) -> dict[str, Any]:
    interpretation = state.interpretation
    label_plans = list(interpretation.label_carrier_plan)
    identity_rows = [
        data.get_source_content_identity() for data in study.loaded_data_list
    ]
    return {
        "raw_file_count": state.raw.count,
        "applied": interpretation.has_applied_interpretation,
        "event_sample_label_digest": event_sample_label_digest(study),
        "label_status": {
            "source_kind": str(interpretation.source_kind or ""),
            "mode": "external_carriers" if label_plans else "embedded_events",
            "carrier_count": len(label_plans),
            "label_import_count": interpretation.label_import_count,
        },
        "recipe_identity": {
            "applied_interpretation_id": interpretation.latest_interpretation_id,
            "saved_recipe_id": interpretation.latest_recipe_id,
            "reviewed_content_identity_digest": _identity_digest(identity_rows),
        },
    }


def collect_workload_correctness(
    state: Any,
    study: Any,
    workload: ImportWorkload,
) -> dict[str, Any] | str:
    details = _base_correctness(state, study)
    if workload.id == "graz_gdf_mat_folder":
        details["label_status"]["selected_fields"] = sorted(
            str(plan.get("selected_label_field") or "")
            for plan in state.interpretation.label_carrier_plan
        )
    elif workload.id == "openneuro_p300_bids":
        details["label_status"] |= {
            "class_names": sorted(state.interpretation.class_map.values()),
            "bids_detected": bool(state.interpretation.bids.get("is_bids")),
        }
        details["dataset_metadata"] = {
            "channel_count": len(state.raw.channels),
            "electrode_layout_source": str(state.electrode_layout.source or ""),
            "positioned_channel_count": state.electrode_layout.positioned_channel_count,
        }
    error = validate_workload_correctness(workload.id, details)
    if error is not None:
        return error
    return details


def _run_visible_import(
    app: Any,
    panel: Any,
    runtime: Any,
    driver: Any,
    heartbeat: Heartbeat,
    *,
    started: float,
    timeout_seconds: float,
) -> tuple[Any | None, list[TimelineEvent], str | None]:
    events = [TimelineEvent("import_clicked", started)]
    heartbeat.start()
    driver.start()
    panel.sidebar.import_btn.click()
    while time.perf_counter() < started + timeout_seconds:
        app.processEvents()
        for name, timestamp in (
            ("chooser_accepted", driver.chooser_accepted_at),
            ("review_ready", driver.wizard_ready_at),
            ("apply_clicked", driver.apply_clicked_at),
        ):
            if timestamp is not None and not any(item.name == name for item in events):
                events.append(TimelineEvent(name, timestamp))
        if driver.errors:
            return None, events, driver.errors[0]
        state = runtime.get_view_publication().state
        if state.interpretation.has_applied_interpretation:
            if not any(item.name == "dataset_ready" for item in events):
                events.append(TimelineEvent("dataset_ready", time.perf_counter()))
            if application_command_registry().active_count(panel) == 0:
                events.append(TimelineEvent("background_idle", time.perf_counter()))
                return state, events, None
        time.sleep(0.005)
    return None, events, "Qt import timed out."


def _run_profile_pass(
    *,
    workload: ImportWorkload,
    chooser_name: str,
    chooser_result: Any,
    driver: Any,
    timeout_seconds: float,
    correctness: Any,
    detailed_trace: bool = True,
) -> dict[str, Any]:
    app, host, panel, runtime = build_dataset_panel_for_runner()
    chooser = getattr(QFileDialog, chooser_name)
    started = time.perf_counter()
    heartbeat = Heartbeat()
    tracer = DevImportTracer()
    sampler = ProcessSampler()
    try:
        setattr(QFileDialog, chooser_name, staticmethod(chooser_result))
        if detailed_trace:
            tracer.install(runtime=runtime, panel=panel)
        else:
            tracer.available = False
            tracer.reason = "coarse trace mode requested"
        sampler.start()
        state, events, failure = _run_visible_import(
            app,
            panel,
            runtime,
            driver,
            heartbeat,
            started=started,
            timeout_seconds=timeout_seconds,
        )
        if failure is not None:
            return {"status": "failed", "message": failure}
        assert state is not None  # noqa: S101 - checked immediately above
        if application_command_registry().active_count(panel):
            return {"status": "failed", "message": "profile did not reach idle"}
        details = correctness(state, host.study)
        if isinstance(details, str):
            return {"status": "failed", "message": details}
        return {
            "status": "passed",
            "timeline": summarize_timeline(events),
            "events": [
                {"name": item.name, "at_seconds": round(item.at_seconds, 6)}
                for item in events
            ],
            "heartbeat": summarize_heartbeat(heartbeat.stop()),
            "process_resources": sampler.stop(),
            "fixture": fixture_inventory(workload),
            "trace": tracer.summary(
                started_at=started,
                ended_at=time.perf_counter(),
            ),
            "correctness": details,
        }
    finally:
        driver.stop()
        heartbeat.stop()
        sampler.stop()
        tracer.restore()
        setattr(QFileDialog, chooser_name, chooser)
        host.close()
        host.deleteLater()
        app.processEvents()


def run_bbci_qt_pass(
    workload: ImportWorkload,
    *,
    timeout_seconds: float = 90.0,
    detailed_trace: bool = True,
) -> dict[str, Any]:
    if not workload.source_path.is_file():
        return {"status": "failed", "message": "BBCI fixture is unavailable."}
    return _run_profile_pass(
        workload=workload,
        chooser_name="getOpenFileNames",
        chooser_result=lambda *_args, **_kwargs: ([str(workload.source_path)], ""),
        driver=BbciWizardDriver(visible_modal_dialog),
        timeout_seconds=timeout_seconds,
        detailed_trace=detailed_trace,
        correctness=lambda state, study: collect_workload_correctness(
            state,
            study,
            workload,
        ),
    )


def run_graz_folder_qt_pass(
    workload: ImportWorkload,
    *,
    timeout_seconds: float = 120.0,
    detailed_trace: bool = True,
) -> dict[str, Any]:
    try:
        temporary = _materialize_graz_folder(workload)
    except FileNotFoundError as exc:
        return {"status": "failed", "message": str(exc)}
    try:
        return _run_profile_pass(
            workload=workload,
            chooser_name="getExistingDirectory",
            chooser_result=lambda *_args, **_kwargs: temporary.name,
            driver=SuggestedLabelWizardDriver(
                visible_modal_dialog, source_kind="folder"
            ),
            timeout_seconds=timeout_seconds,
            detailed_trace=detailed_trace,
            correctness=lambda state, study: collect_workload_correctness(
                state,
                study,
                workload,
            ),
        )
    finally:
        temporary.cleanup()


def run_p300_qt_pass(
    workload: ImportWorkload,
    *,
    timeout_seconds: float = 300.0,
    detailed_trace: bool = True,
) -> dict[str, Any]:
    if not workload.source_path.is_dir():
        return {
            "status": "failed",
            "message": f"OpenNeuro P300 fixture is unavailable: {workload.source_path.name}",
        }

    return _run_profile_pass(
        workload=workload,
        chooser_name="getExistingDirectory",
        chooser_result=lambda *_args, **_kwargs: str(workload.source_path),
        driver=P300BidsWizardDriver(visible_modal_dialog),
        timeout_seconds=timeout_seconds,
        detailed_trace=detailed_trace,
        correctness=lambda state, study: collect_workload_correctness(
            state,
            study,
            workload,
        ),
    )


def run_workload_pass(
    workload: ImportWorkload, *, detailed_trace: bool
) -> dict[str, Any]:
    runners = {
        "bbci_gdf_file": run_bbci_qt_pass,
        "graz_gdf_mat_folder": run_graz_folder_qt_pass,
        "openneuro_p300_bids": run_p300_qt_pass,
    }
    return runners[workload.id](workload, detailed_trace=detailed_trace)


def _fresh_process_pass(
    workload: ImportWorkload, *, detailed_trace: bool
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="xbrainlab-import-profile-") as directory:
        result_path = Path(directory) / "result.json"
        command = [
            sys.executable,
            "-m",
            "scripts.dev.profile_data_import_e2e",
            "--worker-workload",
            workload.id,
            "--trace-mode",
            "detailed" if detailed_trace else "coarse",
            "--result-path",
            str(result_path),
        ]
        try:
            completed = subprocess.run(  # noqa: S603 - fixed local runner command
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=420,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"status": "failed", "message": "fresh-process profile timed out"}
        if not result_path.is_file():
            return {
                "status": "failed",
                "message": f"fresh-process profile exited {completed.returncode}",
            }
        try:
            return redact_paths(json.loads(result_path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return {"status": "failed", "message": "fresh-process result was invalid"}


def _median_field(
    passes: Sequence[Mapping[str, Any]], path: Sequence[str]
) -> float | None:
    values: list[float] = []
    for item in passes:
        current: Any = item
        for key in path:
            current = current.get(key) if isinstance(current, Mapping) else None
        if isinstance(current, (float, int)):
            values.append(float(current))
    return statistics.median(values) if values else None


def calibrate_trace_overhead(
    coarse: Sequence[Mapping[str, Any]], detailed: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    if not (
        len(coarse) == 2
        and len(detailed) == 2
        and all(item.get("status") == "passed" for item in (*coarse, *detailed))
        and all(
            isinstance(item.get("trace"), Mapping)
            and bool(item["trace"].get("available"))
            for item in detailed
        )
    ):
        return {"detailed_allowed": False, "reason": "calibration evidence incomplete"}
    coarse_time = _median_field(coarse, ("timeline", "stable_idle_seconds"))
    detailed_time = _median_field(detailed, ("timeline", "stable_idle_seconds"))
    coarse_gap = _median_field(coarse, ("heartbeat", "max_gap_seconds"))
    detailed_gap = _median_field(detailed, ("heartbeat", "max_gap_seconds"))
    if None in {coarse_time, detailed_time, coarse_gap, detailed_gap}:
        return {"detailed_allowed": False, "reason": "calibration pass failed"}
    delta = detailed_time - coarse_time
    gap_delta = detailed_gap - coarse_gap
    allowed = delta <= max(0.05, coarse_time * 0.05) and gap_delta <= 0.02
    return {
        "detailed_allowed": allowed,
        "coarse_median_seconds": round(coarse_time, 6),
        "detailed_median_seconds": round(detailed_time, 6),
        "delta_seconds": round(delta, 6),
        "heartbeat_delta_seconds": round(gap_delta, 6),
        "reason": "within budget" if allowed else "tracer overhead exceeds budget",
    }


def run_full_profile(
    output_dir: Path | None = None,
) -> tuple[dict[str, Any], tuple[Path, Path]]:
    workloads = default_workloads()
    runs: dict[str, dict[str, Any]] = {}
    for workload in workloads:
        diagnostic = _fresh_process_pass(workload, detailed_trace=True)
        warmup = _fresh_process_pass(workload, detailed_trace=False)
        coarse = [
            warmup,
            _fresh_process_pass(workload, detailed_trace=False),
        ]
        detailed = [
            diagnostic,
            _fresh_process_pass(workload, detailed_trace=True),
        ]
        calibration = calibrate_trace_overhead(coarse, detailed)
        detailed_trace = bool(calibration["detailed_allowed"])
        measured = [
            _fresh_process_pass(workload, detailed_trace=detailed_trace)
            for _ in range(3)
        ]
        runs[workload.id] = {
            "diagnostic": diagnostic,
            "warmup": warmup,
            "passes": measured,
            "summary": aggregate_passes(
                measured,
                required_count=3,
                workload_id=workload.id,
            ),
            "measured_trace_mode": "detailed" if detailed_trace else "coarse",
            "trace_calibration": {
                "coarse": coarse,
                "detailed": detailed,
                "summary": calibration,
            },
        }
    trace_modes = {
        workload.id: str(runs[workload.id]["measured_trace_mode"])
        for workload in workloads
    }
    identity = source_identity()
    payload = build_artifact(
        source_identity=identity,
        environment=environment_identity(measured_trace_modes=trace_modes),
        workloads=workloads,
        workload_runs=runs,
    )
    destination = output_dir or DEFAULT_OUTPUT_ROOT / identity["commit_sha"][:12]
    return payload, write_artifacts(payload, destination)


def _write_one_pass_artifact(
    workload: ImportWorkload,
    result: Mapping[str, Any],
    output_dir: Path,
) -> tuple[Path, Path]:
    trace_mode = (
        "detailed" if bool(result.get("trace", {}).get("available")) else "coarse"
    )
    payload = build_artifact(
        source_identity=source_identity(),
        environment=environment_identity(
            measured_trace_modes={workload.id: trace_mode}
        ),
        workloads=[workload],
        workload_runs={
            workload.id: {
                "summary": aggregate_passes(
                    [result],
                    required_count=1,
                    workload_id=workload.id,
                ),
                "passes": [result],
            }
        },
    )
    return write_artifacts(payload, output_dir)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--validate", type=Path, help="Validate an existing JSON artifact."
    )
    for name, help_text in (
        ("bbci", "Run one real Qt BBCI profile pass."),
        ("folder", "Run one real Qt Graz folder profile pass."),
        ("p300", "Run one real Qt OpenNeuro P300 profile pass."),
    ):
        parser.add_argument(f"--{name}-once", action="store_true", help=help_text)
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run fresh-process diagnostic, warmup and three measured passes.",
    )
    parser.add_argument(
        "--worker-workload", choices=[item.id for item in default_workloads()]
    )
    parser.add_argument(
        "--trace-mode", choices=("detailed", "coarse"), default="detailed"
    )
    parser.add_argument("--result-path", type=Path)
    args = parser.parse_args(argv)
    workloads = default_workloads()
    if args.validate:
        payload = json.loads(args.validate.read_text(encoding="utf-8"))
        ok, reason = validate_artifact(payload)
        print(reason)
        return 0 if ok else 1
    if args.worker_workload:
        if args.result_path is None:
            parser.error("--worker-workload requires --result-path")
        workload = next(item for item in workloads if item.id == args.worker_workload)
        result = run_workload_pass(
            workload,
            detailed_trace=args.trace_mode == "detailed",
        )
        args.result_path.write_text(
            json.dumps(redact_paths(result), sort_keys=True), encoding="utf-8"
        )
        return 0 if result.get("status") == "passed" else 1
    one_passes = (
        (args.bbci_once, 0, run_bbci_qt_pass),
        (args.folder_once, 1, run_graz_folder_qt_pass),
        (args.p300_once, 2, run_p300_qt_pass),
    )
    for enabled, index, runner in one_passes:
        if not enabled:
            continue
        workload = workloads[index]
        result = runner(workload)
        output_dir = args.output_dir or DEFAULT_OUTPUT_ROOT / "ad-hoc"
        paths = _write_one_pass_artifact(workload, result, output_dir)
        print("\n".join(str(path) for path in paths))
        return 0 if result.get("status") == "passed" else 1
    if args.full:
        payload, paths = run_full_profile(args.output_dir)
        print("\n".join(str(path) for path in paths))
        return int(
            not all(
                bool(run.get("summary", {}).get("ok"))
                for run in payload["runs"].values()
            )
        )
    parser.error(
        "choose one of --bbci-once, --folder-once, --p300-once, --full, or --validate"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
