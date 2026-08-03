#!/usr/bin/env python3
"""Run the larger local-only dataset gate used before teacher walkthroughs."""

from __future__ import annotations

import argparse
import contextlib
import csv
import gc
import hashlib
import io
import json
import sys
import warnings
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import mne

from scripts.dev.fetch_public_eeg_fixtures import (
    fixture_file_is_valid,
    fixture_groups_for_profile,
    fixture_profile_size_bytes,
)
from XBrainLab.backend.application import (
    ApplicationService,
    ApplyInterpretationCommand,
    CreateEpochCommand,
    PreviewInterpretationCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.logger import logger as xbrainlab_logger

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DIR = ROOT / "tests" / "fixtures" / "data" / "public"
ARTIFACT_DIR = ROOT / "build" / "dev-artifacts" / "teacher-data-preflight"
ARTIFACT_JSON = "teacher-dataset-preflight.json"
ARTIFACT_MARKDOWN = "teacher-dataset-preflight.md"
REQUIRED_CASE_IDS = frozenset(
    {
        "openneuro_p300_bids",
        "chbmit_raw_edf",
        "sleep_edfx_psg",
    }
)
TEACHER_FIXTURE_GROUP_NAMES = frozenset(
    {
        "openneuro-ds003061-p300",
        "chbmit-chb01",
        "sleep-edfx-st7011",
    }
)
TEACHER_FIXTURE_GROUP_COUNT = 10
TEACHER_FIXTURE_PROFILE_SIZE_BYTES = 277_106_963
_OPENNEURO_CLASS_VALUE_MAP = {
    "noise": "noise",
    "noise_with_reponse": "noise",
    "oddball": "oddball",
    "oddball_with_reponse": "oddball",
    "standard": "standard",
    "standard_with_reponse": "standard",
}


def _class_decision(class_name: str) -> dict[str, Any]:
    return {
        "role": "stimulus",
        "keep_event": True,
        "use_as_class": True,
        "class_name": class_name,
    }


def build_openneuro_p300_choices(dataset_root: Path) -> dict[str, Any]:
    """Return explicit reviewed choices for the three OpenNeuro P300 runs."""
    eeg_dir = dataset_root / "sub-001" / "eeg"
    eeg_files = sorted(eeg_dir.glob("*_eeg.set"))
    events_files = sorted(eeg_dir.glob("*_events.tsv"))
    if len(eeg_files) != 3 or len(events_files) != 3:
        raise ValueError(
            "OpenNeuro ds003061 preflight expects exactly three EEG runs and "
            "three run-specific events.tsv files."
        )

    value_decisions = {
        "standard": _class_decision("standard"),
        "standard_with_reponse": _class_decision("standard"),
        "oddball": _class_decision("oddball"),
        "oddball_with_reponse": _class_decision("oddball"),
        "noise": _class_decision("noise"),
        "noise_with_reponse": _class_decision("noise"),
        "response": {
            "role": "response",
            "keep_event": False,
            "use_as_class": False,
        },
        "ignore": {
            "role": "system",
            "keep_event": False,
            "use_as_class": False,
        },
    }
    label_choices: dict[str, dict[str, Any]] = {}
    for events_path in events_files:
        label_choices[str(events_path.resolve())] = {
            "label_field": "value",
            "anchor": "onset",
            "placement_method": "time_field",
            "time_model": "seconds",
            "value_decisions": value_decisions,
        }
    return {
        "selected_eeg_files": [str(path.resolve()) for path in eeg_files],
        "label_carrier_choices": label_choices,
    }


@contextlib.contextmanager
def _quiet_runtime() -> Any:
    previous_disabled = xbrainlab_logger.disabled
    xbrainlab_logger.disabled = True
    with (
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
        warnings.catch_warnings(),
        mne.use_log_level("ERROR"),
    ):
        warnings.simplefilter("ignore")
        try:
            yield
        finally:
            xbrainlab_logger.disabled = previous_disabled


def _stage(result: Any) -> dict[str, Any]:
    return {"ok": bool(result.ok), "message": str(result.message)}


def _failed(
    result: dict[str, Any],
    stage: str,
    message: str,
) -> dict[str, Any]:
    result["status"] = "failed"
    result["failed_stage"] = stage
    result["message"] = message
    return result


def _release_service(service: ApplicationService | None) -> None:
    if service is not None:
        for data in list(service.study.loaded_data_list):
            with contextlib.suppress(Exception):
                raw = data.get_mne()
                close = getattr(raw, "close", None)
                if callable(close):
                    close()
        with contextlib.suppress(Exception):
            service.close()
    gc.collect()


def _scan_payload(command_result: Any) -> dict[str, Any]:
    payload = command_result.diagnostics.get("scan_result", {})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _manifest_evidence(repo_root: Path) -> dict[str, Any]:
    groups = fixture_groups_for_profile("teacher-preflight")
    defined_groups = {str(group["name"]) for group in groups}
    missing_required_groups = sorted(TEACHER_FIXTURE_GROUP_NAMES - defined_groups)
    public_dir = repo_root / "tests" / "fixtures" / "data" / "public"
    invalid: list[str] = []
    verified_groups: list[str] = []
    for group in groups:
        group_valid = True
        for fixture_file in group["files"]:
            path = public_dir / fixture_file["filename"]
            if not fixture_file_is_valid(
                path,
                fixture_file["sha256"],
                fixture_file["size_bytes"],
            ):
                invalid.append(fixture_file["filename"])
                group_valid = False
        if group_valid:
            verified_groups.append(group["name"])
    return {
        "profile": "teacher-preflight",
        "size_bytes": fixture_profile_size_bytes(groups),
        "group_count": len(groups),
        "verified_group_count": len(verified_groups),
        "verified_groups": sorted(verified_groups),
        "invalid_files": sorted(invalid),
        "missing_required_groups": missing_required_groups,
        "expected_group_count": TEACHER_FIXTURE_GROUP_COUNT,
        "expected_size_bytes": TEACHER_FIXTURE_PROFILE_SIZE_BYTES,
        "all_files_verified": (
            not invalid
            and not missing_required_groups
            and len(groups) == TEACHER_FIXTURE_GROUP_COUNT
            and fixture_profile_size_bytes(groups) == TEACHER_FIXTURE_PROFILE_SIZE_BYTES
        ),
    }


def _base_result(
    *,
    case_id: str,
    dataset: str,
    format_name: str,
    evidence_tier: str,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "dataset": dataset,
        "format": format_name,
        "evidence_tier": evidence_tier,
        "status": "failed",
        "failed_stage": "fixture",
        "message": "Not run.",
        "stages": {},
        "observations": {},
    }


def _event_rows_digest(rows: list[tuple[int, str]]) -> str:
    encoded = json.dumps(
        sorted(rows),
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _review_openneuro_event_timing(
    data: Any,
    *,
    eeg_dir: Path,
) -> dict[str, Any]:
    eeg_name = Path(data.get_filepath()).name
    events_path = eeg_dir / eeg_name.replace("_eeg.set", "_events.tsv")
    raw = data.get_mne()
    expected_rows: list[tuple[int, str]] = []
    with events_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            class_name = _OPENNEURO_CLASS_VALUE_MAP.get(
                str(row.get("value") or "").strip()
            )
            if class_name is None:
                continue
            onset = float(str(row.get("onset") or "").strip())
            sample = int(raw.time_as_index([onset], use_rounding=True)[0])
            expected_rows.append((sample + int(raw.first_samp), class_name))
    events, event_id = data.get_event_list()
    labels_by_id = {int(value): str(name) for name, value in event_id.items()}
    observed_rows = [
        (int(event[0]), labels_by_id[int(event[2])])
        for event in events
        if int(event[2]) in labels_by_id
    ]
    expected_rows.sort()
    observed_rows.sort()
    return {
        "file": eeg_name,
        "events_file": events_path.name,
        "expected_count": len(expected_rows),
        "observed_count": len(observed_rows),
        "source_sample_label_digest": _event_rows_digest(expected_rows),
        "stored_sample_label_digest": _event_rows_digest(observed_rows),
        "sample_label_rows_match": observed_rows == expected_rows,
    }


def run_openneuro_p300_case(repo_root: Path = ROOT) -> dict[str, Any]:
    """Run three real BIDS/EEGLAB recordings through supervised import."""
    result = _base_result(
        case_id="openneuro_p300_bids",
        dataset="OpenNeuro ds003061 P300",
        format_name="BIDS EEG / EEGLAB SET + events.tsv",
        evidence_tier="supervised_import",
    )
    dataset_root = (
        repo_root / "tests" / "fixtures" / "data" / "public" / "openneuro-ds003061-p300"
    )
    eeg_dir = dataset_root / "sub-001" / "eeg"
    if not dataset_root.exists():
        result["status"] = "missing"
        result["message"] = f"Missing fixture: {dataset_root}"
        return result

    service: ApplicationService | None = None
    try:
        with _quiet_runtime():
            active_service = ApplicationService(Study())
            service = active_service
            scan = active_service.execute(
                ScanSourceCommand(
                    source_path=str(dataset_root),
                    source_hint="bids",
                )
            )
            result["stages"]["scan"] = _stage(scan)
            if not scan.ok:
                return _failed(result, "scan", scan.message)

            choices = build_openneuro_p300_choices(dataset_root)
            preview = active_service.execute(
                PreviewInterpretationCommand(choices=choices)
            )
            result["stages"]["preview"] = _stage(preview)
            if not preview.ok:
                return _failed(result, "preview", preview.message)

            validation = active_service.execute(ValidateInterpretationCommand())
            result["stages"]["validate"] = _stage(validation)
            if not validation.ok:
                return _failed(result, "validate", validation.message)
            validation_payload = validation.diagnostics.get(
                "validation_decision",
                {},
            )
            if validation_payload.get("decision") == "blocked":
                return _failed(
                    result,
                    "validate",
                    "Validation blocked apply: "
                    + "; ".join(validation_payload.get("blocked_reasons", [])),
                )

            applied = active_service.execute(ApplyInterpretationCommand(confirmed=True))
            result["stages"]["apply"] = _stage(applied)
            if not applied.ok:
                return _failed(result, "apply", applied.message)

            scan_payload = _scan_payload(scan)
            label_apply = applied.diagnostics.get("label_apply", {})
            placement = label_apply.get("bids_placement", [])
            handoff = applied.state.interpretation.epoch_handoff
            stored_events_by_run = []
            timing_checks = []
            for data in active_service.study.loaded_data_list:
                events, event_id = data.get_event_list()
                stored_events_by_run.append(
                    {
                        "file": Path(data.get_filepath()).name,
                        "count": len(events),
                        "labels": sorted(str(label) for label in event_id),
                    }
                )
                timing_checks.append(
                    _review_openneuro_event_timing(data, eeg_dir=eeg_dir)
                )
            epoch = active_service.execute(
                CreateEpochCommand(
                    t_min=-0.2,
                    t_max=0.5,
                    event_ids=["noise", "oddball", "standard"],
                )
            )
            result["stages"]["epoch_handoff"] = _stage(epoch)
            if not epoch.ok:
                return _failed(result, "epoch_handoff", epoch.message)
            observations = {
                "bids_detected": bool(
                    applied.state.interpretation.bids.get("is_bids", False)
                ),
                "eeg_file_count": len(scan_payload.get("eeg_files", [])),
                "label_carrier_count": len(scan_payload.get("label_carriers", [])),
                "raw_file_count": applied.state.raw.count,
                "validation_decision": validation_payload.get("decision"),
                "label_apply_status": label_apply.get("status"),
                "usable_events_by_run": [
                    int(item.get("usable_event_count", 0))
                    for item in placement
                    if isinstance(item, Mapping)
                ],
                "stored_events_by_run": stored_events_by_run,
                "event_timing_checks": timing_checks,
                "event_timing_all_match": all(
                    item["sample_label_rows_match"] for item in timing_checks
                ),
                "default_epoch_events": sorted(handoff.get("default_epoch_events", [])),
                "epoch_handoff_ready": bool(handoff.get("ready", False)),
                "supervised_ready": bool(handoff.get("supervised_ready", False)),
                "epoch_count": int(epoch.state.epoch.epoch_count),
                "epoch_event_ids": sorted(epoch.state.epoch.event_ids),
                "epoch_window_seconds": [-0.2, 0.5],
                "boundary_events_excluded": int(
                    epoch.diagnostics.get("epoch_boundary_check", {}).get(
                        "excluded_event_count",
                        0,
                    )
                ),
            }
            result["observations"] = observations
            expected = {
                "bids_detected": True,
                "eeg_file_count": 3,
                "label_carrier_count": 3,
                "raw_file_count": 3,
                "validation_decision": "safe",
                "label_apply_status": "applied",
                "usable_events_by_run": [747, 750, 748],
                "stored_events_by_run": [
                    {
                        "file": f"sub-001_task-P300_run-{run}_eeg.set",
                        "count": count,
                        "labels": ["noise", "oddball", "standard"],
                    }
                    for run, count in ((1, 747), (2, 750), (3, 748))
                ],
                "event_timing_all_match": True,
                "default_epoch_events": ["noise", "oddball", "standard"],
                "epoch_handoff_ready": True,
                "supervised_ready": True,
                "epoch_count": 2_243,
                "epoch_event_ids": ["noise", "oddball", "standard"],
                "epoch_window_seconds": [-0.2, 0.5],
                "boundary_events_excluded": 2,
            }
            mismatches = [
                f"{name}: expected {expected_value!r}, got {observations.get(name)!r}"
                for name, expected_value in expected.items()
                if observations.get(name) != expected_value
            ]
            if mismatches:
                return _failed(
                    result,
                    "evidence_assertion",
                    "; ".join(mismatches),
                )
            result["status"] = "passed"
            result["failed_stage"] = ""
            result["message"] = (
                "Three BIDS runs, three run-specific event carriers, and "
                "2,245 reviewed class events imported with exact source "
                "sample/label agreement. A -0.2 to 0.5 second epoch window "
                "created 2,243 epochs after reporting and excluding two "
                "recording-boundary events."
            )
            return result
    except Exception as exc:
        return _failed(
            result,
            "exception",
            f"{type(exc).__name__}: {exc}",
        )
    finally:
        _release_service(service)


def _find_capability(
    capabilities: list[dict[str, Any]],
    path: Path,
) -> dict[str, Any]:
    return next(
        (item for item in capabilities if item.get("path") == str(path.resolve())),
        {},
    )


def _run_raw_edf_case(
    *,
    repo_root: Path,
    case_id: str,
    dataset: str,
    fixture_root_name: str,
    eeg_name: str,
    context_name: str,
    context_format: str,
    context_status: str,
    expected_channels: int,
    expected_samples: int,
    expected_sfreq: float,
) -> dict[str, Any]:
    result = _base_result(
        case_id=case_id,
        dataset=dataset,
        format_name="EDF",
        evidence_tier="raw_import_only",
    )
    fixture_root = (
        repo_root / "tests" / "fixtures" / "data" / "public" / fixture_root_name
    )
    eeg_path = fixture_root / eeg_name
    context_path = fixture_root / context_name
    if not eeg_path.exists() or not context_path.exists():
        result["status"] = "missing"
        result["message"] = f"Missing fixture under {fixture_root}"
        return result

    folder_service: ApplicationService | None = None
    service: ApplicationService | None = None
    try:
        with _quiet_runtime():
            active_folder_service = ApplicationService(Study())
            folder_service = active_folder_service
            folder_scan = active_folder_service.execute(
                ScanSourceCommand(
                    source_path=str(fixture_root),
                    source_hint="folder",
                )
            )
            result["stages"]["folder_scan"] = _stage(folder_scan)
            if not folder_scan.ok:
                return _failed(result, "folder_scan", folder_scan.message)
            folder_payload = _scan_payload(folder_scan)
            capability = _find_capability(
                list(folder_payload.get("format_capabilities", [])),
                context_path,
            )
            folder_expectations = {
                "eeg_files": [str(eeg_path.resolve())],
                "label_carriers": [],
                "context_format": context_format,
                "context_role": "sidecar",
                "context_status": context_status,
            }
            folder_observed = {
                "eeg_files": folder_payload.get("eeg_files", []),
                "label_carriers": folder_payload.get("label_carriers", []),
                "context_format": capability.get("format"),
                "context_role": capability.get("role"),
                "context_status": capability.get("status"),
            }
            folder_mismatches = [
                (f"{name}: expected {expected!r}, got {folder_observed.get(name)!r}")
                for name, expected in folder_expectations.items()
                if folder_observed.get(name) != expected
            ]
            if folder_mismatches:
                return _failed(
                    result,
                    "folder_scan_assertion",
                    "; ".join(folder_mismatches),
                )

            active_service = ApplicationService(Study())
            service = active_service
            scan = active_service.execute(
                ScanSourceCommand(
                    source_path=str(eeg_path),
                    source_hint="file",
                )
            )
            result["stages"]["scan"] = _stage(scan)
            if not scan.ok:
                return _failed(result, "scan", scan.message)

            preview = active_service.execute(PreviewInterpretationCommand())
            result["stages"]["preview"] = _stage(preview)
            if not preview.ok:
                return _failed(result, "preview", preview.message)

            validation = active_service.execute(ValidateInterpretationCommand())
            result["stages"]["validate"] = _stage(validation)
            if not validation.ok:
                return _failed(result, "validate", validation.message)
            decision = validation.diagnostics.get(
                "validation_decision",
                {},
            ).get("decision")
            if decision == "blocked":
                return _failed(
                    result,
                    "validate",
                    "Raw import was unexpectedly blocked.",
                )

            applied = active_service.execute(ApplyInterpretationCommand(confirmed=True))
            result["stages"]["apply"] = _stage(applied)
            if not applied.ok:
                return _failed(result, "apply", applied.message)
            raw = active_service.study.loaded_data_list[0].get_mne()
            handoff = applied.state.interpretation.epoch_handoff
            observations = {
                **folder_observed,
                "validation_decision": decision,
                "raw_file_count": applied.state.raw.count,
                "channel_count": len(raw.ch_names),
                "sample_count": int(raw.n_times),
                "sampling_frequency_hz": float(raw.info["sfreq"]),
                "supervised_ready": bool(handoff.get("supervised_ready", False)),
            }
            result["observations"] = observations
            expected = {
                "raw_file_count": 1,
                "channel_count": expected_channels,
                "sample_count": expected_samples,
                "sampling_frequency_hz": expected_sfreq,
                "supervised_ready": False,
            }
            mismatches = [
                f"{name}: expected {expected_value!r}, got {observations.get(name)!r}"
                for name, expected_value in expected.items()
                if observations.get(name) != expected_value
            ]
            if mismatches:
                return _failed(
                    result,
                    "evidence_assertion",
                    "; ".join(mismatches),
                )
            result["status"] = "passed"
            result["failed_stage"] = ""
            result["message"] = (
                "The selected EDF recording imported as raw EEG; its companion "
                "annotation/report file remained an explicit unsupported sidecar."
            )
            return result
    except Exception as exc:
        return _failed(
            result,
            "exception",
            f"{type(exc).__name__}: {exc}",
        )
    finally:
        _release_service(folder_service)
        _release_service(service)


def run_chbmit_case(repo_root: Path = ROOT) -> dict[str, Any]:
    return _run_raw_edf_case(
        repo_root=repo_root,
        case_id="chbmit_raw_edf",
        dataset="CHB-MIT chb01",
        fixture_root_name="chbmit-chb01",
        eeg_name="chb01_03.edf",
        context_name="chb01_03.edf.seizures",
        context_format="Seizure annotation sidecar",
        context_status="unsupported",
        expected_channels=23,
        expected_samples=921_600,
        expected_sfreq=256.0,
    )


def run_sleep_edfx_case(repo_root: Path = ROOT) -> dict[str, Any]:
    result = _run_raw_edf_case(
        repo_root=repo_root,
        case_id="sleep_edfx_psg",
        dataset="Sleep-EDF Expanded ST7011",
        fixture_root_name="sleep-edfx-st7011",
        eeg_name="ST7011J0-PSG.edf",
        context_name="ST7011JP-Hypnogram.edf",
        context_format="EDF+ annotations",
        context_status="limited",
        expected_channels=5,
        expected_samples=3_590_000,
        expected_sfreq=100.0,
    )
    if result.get("status") != "passed":
        return result
    annotation_path = (
        repo_root
        / "tests"
        / "fixtures"
        / "data"
        / "public"
        / "sleep-edfx-st7011"
        / "ST7011JP-Hypnogram.edf"
    )
    try:
        with _quiet_runtime():
            annotations = mne.read_annotations(annotation_path)
    except Exception as exc:
        return _failed(
            result,
            "sidecar_evidence",
            f"{type(exc).__name__}: {exc}",
        )
    descriptions = sorted({str(item) for item in annotations.description})
    sidecar_evidence = {
        "annotation_count": len(annotations),
        "annotation_classes": descriptions,
        "all_durations_positive": bool(
            len(annotations) > 0 and all(value > 0 for value in annotations.duration)
        ),
        "onset_range_seconds": [
            float(min(annotations.onset)),
            float(max(annotations.onset)),
        ],
    }
    result["observations"]["sidecar_evidence"] = sidecar_evidence
    expected_classes = [
        "Sleep stage 1",
        "Sleep stage 2",
        "Sleep stage 3",
        "Sleep stage 4",
        "Sleep stage R",
        "Sleep stage W",
    ]
    if (
        sidecar_evidence["annotation_count"] != 231
        or sidecar_evidence["annotation_classes"] != expected_classes
        or sidecar_evidence["all_durations_positive"] is not True
    ):
        return _failed(
            result,
            "sidecar_evidence",
            f"Unexpected Sleep-EDF annotation evidence: {sidecar_evidence!r}",
        )
    result["message"] = (
        "The PSG recording imported as raw EEG. Its 231 reviewed hypnogram "
        "intervals remained a detected, unsupported sidecar and were not "
        "promoted to labels."
    )
    return result


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    results_by_id = {str(item.get("case_id")): item for item in results}
    passed_ids = sorted(
        case_id
        for case_id in REQUIRED_CASE_IDS
        if results_by_id.get(case_id, {}).get("status") == "passed"
    )
    failed_ids = sorted(
        case_id
        for case_id in REQUIRED_CASE_IDS
        if results_by_id.get(case_id, {}).get("status") == "failed"
    )
    missing_ids = sorted(
        case_id
        for case_id in REQUIRED_CASE_IDS
        if results_by_id.get(case_id, {}).get("status") == "missing"
    )
    absent_ids = sorted(REQUIRED_CASE_IDS - results_by_id.keys())
    return {
        "required_case_count": len(REQUIRED_CASE_IDS),
        "passed_required_case_count": len(passed_ids),
        "passed_case_ids": passed_ids,
        "failed_case_ids": failed_ids,
        "missing_case_ids": missing_ids,
        "absent_case_ids": absent_ids,
        "all_required_passed": (
            len(passed_ids) == len(REQUIRED_CASE_IDS)
            and not failed_ids
            and not missing_ids
            and not absent_ids
        ),
    }


def build_teacher_preflight_snapshot(
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    manifest = _manifest_evidence(repo_root)
    if manifest["all_files_verified"]:
        results = [
            run_openneuro_p300_case(repo_root),
            run_chbmit_case(repo_root),
            run_sleep_edfx_case(repo_root),
        ]
    else:
        manifest_message = "Teacher fixture manifest is incomplete or invalid."
        results = [
            _failed(
                _base_result(
                    case_id=case_id,
                    dataset=dataset,
                    format_name=format_name,
                    evidence_tier=evidence_tier,
                ),
                "manifest",
                manifest_message,
            )
            for case_id, dataset, format_name, evidence_tier in (
                (
                    "openneuro_p300_bids",
                    "OpenNeuro ds003061 P300",
                    "BIDS EEG / EEGLAB SET + events.tsv",
                    "supervised_import",
                ),
                (
                    "chbmit_raw_edf",
                    "CHB-MIT chb01",
                    "EDF",
                    "raw_import_only",
                ),
                (
                    "sleep_edfx_psg",
                    "Sleep-EDF Expanded ST7011",
                    "EDF",
                    "raw_import_only",
                ),
            )
        ]
    summary = summarize_results(results)
    summary["manifest_verified"] = manifest["all_files_verified"]
    summary["strict_ok"] = bool(
        summary["all_required_passed"] and manifest["all_files_verified"]
    )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "generator": "scripts/dev/report_teacher_dataset_preflight.py",
        "profile": "teacher-preflight",
        "manifest": manifest,
        "summary": summary,
        "results": results,
        "claim_boundary": {
            "supports": (
                "A larger teacher preflight across a real three-run OpenNeuro "
                "BIDS auditory dataset and independent CHB-MIT and Sleep-EDF raw "
                "recordings. The OpenNeuro case proves a reviewed three-condition "
                "auditory stimulus class-label import, exact source-to-runtime "
                "sample/label agreement, and a bounded epoch handoff; the two "
                "clinical/sleep cases prove raw import and that unsupported "
                "sidecars are not promoted to EEG or label carriers."
            ),
            "does_not_support": (
                "This does not claim automatic supervised use of CHB-MIT seizure "
                "sidecars or Sleep-EDF hypnograms. Those companion annotations "
                "remain explicit sidecar boundaries. It is not a full BIDS "
                "validator or exhaustive certification of every EEG dataset."
            ),
        },
    }


def render_markdown(snapshot: dict[str, Any]) -> str:
    summary = snapshot["summary"]
    lines = [
        "# Teacher Dataset Preflight",
        "",
        (
            f"- Required cases passed: "
            f"`{summary['passed_required_case_count']} / "
            f"{summary['required_case_count']}`"
        ),
        f"- Strict result: `{'PASS' if summary.get('strict_ok') is True else 'FAIL'}`",
        "",
        "| Dataset | Format | Evidence | Status | Result |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result in snapshot["results"]:
        message = str(result.get("message", "")).replace("|", "\\|")
        lines.append(
            "| {dataset} | {format} | {evidence} | {status} | {message} |".format(
                dataset=result.get("dataset", ""),
                format=result.get("format", ""),
                evidence=result.get("evidence_tier", ""),
                status=result.get("status", ""),
                message=message,
            )
        )
    lines.extend(
        [
            "",
            "## Claim Boundary",
            "",
            f"- Supports: {snapshot['claim_boundary']['supports']}",
            f"- Does not support: {snapshot['claim_boundary']['does_not_support']}",
            "",
        ]
    )
    return "\n".join(lines)


def write_artifacts(
    snapshot: dict[str, Any],
    output_dir: Path = ARTIFACT_DIR,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / ARTIFACT_JSON
    markdown_path = output_dir / ARTIFACT_MARKDOWN
    json_path.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(snapshot), encoding="utf-8")
    return json_path, markdown_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
    )
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--write-artifacts", action="store_true")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ARTIFACT_DIR,
    )
    args = parser.parse_args()

    snapshot = build_teacher_preflight_snapshot()
    if args.write_artifacts:
        json_path, markdown_path = write_artifacts(snapshot, args.output_dir)
        print(f"Wrote {json_path}", file=sys.stderr)
        print(f"Wrote {markdown_path}", file=sys.stderr)
    if args.format == "json":
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    else:
        print(render_markdown(snapshot))
    if args.strict and snapshot["summary"].get("strict_ok") is not True:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
