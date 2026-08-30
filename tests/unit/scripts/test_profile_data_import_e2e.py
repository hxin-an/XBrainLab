from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from scripts.dev import profile_data_import_e2e as profile

EVENT_DIGEST = "a" * 64
CONTENT_DIGEST = "b" * 64


def _correctness(workload_id: str) -> dict[str, Any]:
    value: dict[str, Any] = {
        "raw_file_count": 1 if workload_id == "bbci_gdf_file" else 3,
        "applied": True,
        "event_sample_label_digest": EVENT_DIGEST,
        "recipe_identity": {
            "applied_interpretation_id": "interpretation-6",
            "saved_recipe_id": None,
            "reviewed_content_identity_digest": CONTENT_DIGEST,
        },
    }
    if workload_id == "bbci_gdf_file":
        value["label_status"] = {
            "source_kind": "file",
            "mode": "embedded_events",
            "carrier_count": 0,
            "label_import_count": 0,
        }
    elif workload_id == "graz_gdf_mat_folder":
        value["label_status"] = {
            "source_kind": "folder",
            "mode": "external_carriers",
            "carrier_count": 3,
            "label_import_count": 1,
            "selected_fields": ["classlabel"] * 3,
        }
    else:
        value["label_status"] = {
            "source_kind": "bids",
            "mode": "external_carriers",
            "carrier_count": 3,
            "label_import_count": 1,
            "class_names": ["noise", "noise", "oddball", "standard"],
            "bids_detected": True,
        }
        value["dataset_metadata"] = {
            "channel_count": 79,
            "positioned_channel_count": 0,
            "electrode_layout_source": "",
        }
    return value


def _workload(workload_id: str) -> profile.ImportWorkload:
    raw_count = 1 if workload_id == "bbci_gdf_file" else 3
    return profile.ImportWorkload(
        workload_id,
        workload_id,
        "file",
        "fixture",
        raw_count,
        raw_count,
        "events",
        Path(f"{workload_id}.fixture"),
    )


def _passed(workload_id: str) -> dict[str, Any]:
    return {
        "status": "passed",
        "timeline": dict.fromkeys(profile.TIMING_FIELDS, 0.1),
        "events": [],
        "heartbeat": {"max_gap_seconds": 0.01},
        "process_resources": {},
        "fixture": {},
        "trace": {"available": True},
        "correctness": _correctness(workload_id),
    }


def _artifact(
    workload_id: str,
    source: dict[str, Any],
) -> dict[str, Any]:
    workload = _workload(workload_id)
    return profile.build_artifact(
        source_identity=source,
        environment=profile.environment_identity(
            measured_trace_modes={workload_id: "detailed"}
        ),
        workloads=[workload],
        workload_runs={workload_id: {"passes": [_passed(workload_id)]}},
    )


def test_redaction_removes_any_string_with_an_absolute_path() -> None:
    payload = {
        "posix": "Retry /home/Operator Name/EEG Data/a file.gdf",
        "windows": r"Retry C:\Users\Operator Name\EEG Data\a file.gdf",
        "nested": ["safe", {"path": "/private/a/secret.mat"}],
    }
    redacted = profile.redact_paths(payload)
    assert redacted == {
        "posix": "<redacted-path>",
        "windows": "<redacted-path>",
        "nested": ["safe", {"path": "<redacted-path>"}],
    }
    assert profile.contains_absolute_path(payload)
    assert not profile.contains_absolute_path(redacted)


def test_trace_uses_exact_apply_stages_and_restores_original_once() -> None:
    class Owner:
        def __init__(self) -> None:
            self.calls = 0

        def checkpoint(self, stage: str) -> str:
            self.calls += 1
            return stage

    tracer = profile.DevImportTracer()
    owner = Owner()
    tracer._patch(owner, "checkpoint", "checkpoint")
    assert (
        owner.checkpoint("Loading reviewed EEG recordings")
        == "Loading reviewed EEG recordings"
    )
    assert owner.calls == 1
    tracer.restore()
    assert owner.checkpoint("ordinary checkpoint") == "ordinary checkpoint"
    assert owner.calls == 2

    tracer.record("worker_start", at_seconds=1.0)
    tracer.record_checkpoint("Loading EEG recording 1 of 3", at_seconds=1.5)
    for offset, stage in enumerate(tracer._CHECKPOINT_PHASES, start=2):
        tracer.record_checkpoint(stage, at_seconds=float(offset))
    tracer.record_boundary("Committing interpreted dataset", at_seconds=20.0)
    summary = tracer.summary(started_at=1.0, ended_at=21.0)
    assert summary["available"] is True
    assert profile.DevImportTracer._REQUIRED_APPLY_PHASES.issubset(
        {event["phase"] for event in summary["events"]}
    )

    missing = profile.DevImportTracer()
    missing.record("worker_start", at_seconds=1.0)
    missing.record_checkpoint("Loading EEG recording", at_seconds=2.0)
    missing.record_boundary("Committing interpreted dataset", at_seconds=3.0)
    assert missing.summary(started_at=1.0, ended_at=4.0)["available"] is False


def test_timeline_heartbeat_and_aggregate_fail_closed() -> None:
    events = [
        profile.TimelineEvent(name, at)
        for name, at in (
            ("import_clicked", 1.0),
            ("chooser_accepted", 1.2),
            ("review_ready", 2.0),
            ("apply_clicked", 2.5),
            ("dataset_ready", 4.0),
            ("background_idle", 4.5),
        )
    ]
    timeline = profile.summarize_timeline(events)
    assert timeline["apply_seconds"] == pytest.approx(1.5)
    assert profile.summarize_heartbeat([0.0, 0.05, 0.4])[
        "max_gap_seconds"
    ] == pytest.approx(0.35)
    passed = _passed("bbci_gdf_file")
    passed["timeline"] = {**timeline, "apply_seconds": 3.0}
    aggregate = profile.aggregate_passes(
        [passed] * 3,
        required_count=3,
        workload_id="bbci_gdf_file",
    )
    assert aggregate["dominant_stage"] == "apply_seconds"
    assert profile.aggregate_passes([passed], required_count=3)["ok"] is False
    mismatched = deepcopy(passed)
    mismatched["correctness"]["recipe_identity"]["reviewed_content_identity_digest"] = (
        "c" * 64
    )
    assert (
        profile.aggregate_passes(
            [passed, passed, mismatched],
            required_count=3,
            workload_id="bbci_gdf_file",
        )["ok"]
        is False
    )


@pytest.mark.parametrize(
    ("workload_id", "path", "replacement"),
    [
        ("bbci_gdf_file", ("raw_file_count",), 2),
        ("bbci_gdf_file", ("applied",), False),
        ("bbci_gdf_file", ("event_sample_label_digest",), ""),
        ("bbci_gdf_file", ("recipe_identity", "applied_interpretation_id"), ""),
        ("bbci_gdf_file", ("recipe_identity", "reviewed_content_identity_digest"), ""),
        ("bbci_gdf_file", ("label_status", "mode"), "external_carriers"),
        ("bbci_gdf_file", ("label_status", "carrier_count"), 1),
        ("bbci_gdf_file", ("label_status", "label_import_count"), 1),
        ("graz_gdf_mat_folder", ("label_status", "source_kind"), "file"),
        ("graz_gdf_mat_folder", ("label_status", "carrier_count"), 2),
        ("graz_gdf_mat_folder", ("label_status", "label_import_count"), 0),
        (
            "graz_gdf_mat_folder",
            ("label_status", "selected_fields"),
            ["classlabel"] * 2,
        ),
        ("openneuro_p300_bids", ("label_status", "source_kind"), "folder"),
        ("openneuro_p300_bids", ("label_status", "carrier_count"), 2),
        ("openneuro_p300_bids", ("label_status", "label_import_count"), 0),
        ("openneuro_p300_bids", ("label_status", "class_names"), ["noise"]),
        ("openneuro_p300_bids", ("label_status", "bids_detected"), False),
        ("openneuro_p300_bids", ("dataset_metadata", "channel_count"), 78),
        ("openneuro_p300_bids", ("dataset_metadata", "positioned_channel_count"), 1),
        (
            "openneuro_p300_bids",
            ("dataset_metadata", "electrode_layout_source"),
            "BIDS",
        ),
    ],
)
def test_workload_correctness_rejects_each_contract_mutation(
    workload_id: str,
    path: tuple[str, ...],
    replacement: object,
) -> None:
    correctness = _correctness(workload_id)
    target: dict[str, Any] = correctness
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    assert profile.validate_workload_correctness(workload_id, correctness) is not None


def test_source_identity_keeps_full_fields_but_redacts_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = profile.collect_source_identity(profile.ROOT, refresh=True)
    monkeypatch.setattr(
        profile,
        "collect_source_identity",
        lambda *_args, **_kwargs: dict(current),
    )
    identity = profile.source_identity()
    assert set(identity) == set(current)
    assert identity["repo_root"] == profile.REPO_ROOT_TOKEN
    assert all(
        identity[field] == value
        for field, value in current.items()
        if field != "repo_root"
    )
    artifact = _artifact("bbci_gdf_file", identity)
    assert profile.validate_artifact(artifact, current_identity=current) == (True, "ok")
    assert profile.contains_absolute_path(artifact) is False
    stale = dict(current)
    stale["source_content_digest"] = "0" * 64
    assert profile.validate_artifact(artifact, current_identity=stale)[0] is False


def test_artifact_reuses_correctness_and_measurement_contract() -> None:
    current = profile.collect_source_identity(profile.ROOT, refresh=True)
    identity = {**current, "repo_root": profile.REPO_ROOT_TOKEN}
    artifact = _artifact("openneuro_p300_bids", identity)
    assert profile.validate_artifact(artifact, current_identity=current) == (True, "ok")
    missing_measurement = deepcopy(artifact)
    del missing_measurement["runs"]["openneuro_p300_bids"]["passes"][0]["trace"]
    assert (
        profile.validate_artifact(missing_measurement, current_identity=current)[0]
        is False
    )
    invalid_p300 = deepcopy(artifact)
    invalid_p300["runs"]["openneuro_p300_bids"]["passes"][0]["correctness"][
        "dataset_metadata"
    ]["channel_count"] = 78
    assert profile.validate_artifact(invalid_p300, current_identity=current)[0] is False


def test_calibration_requires_two_complete_detailed_passes() -> None:
    passed = {
        "status": "passed",
        "timeline": {"stable_idle_seconds": 1.0},
        "heartbeat": {"max_gap_seconds": 0.01},
        "trace": {"available": True},
    }
    calibrate = profile.calibrate_trace_overhead
    assert calibrate([passed] * 2, [passed] * 2)["detailed_allowed"] is True
    assert calibrate([passed], [passed] * 2)["detailed_allowed"] is False
    assert (
        calibrate([passed] * 2, [{**passed, "trace": {"available": False}}] * 2)[
            "detailed_allowed"
        ]
        is False
    )
