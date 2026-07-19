from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

import mne
import numpy as np
import pytest

from XBrainLab.backend.application import (
    ApplicationService,
    ReviewInterpretationCommand,
)
from XBrainLab.backend.application import (
    data_interpretation_bids_resources as bids_resources,
)
from XBrainLab.backend.application import data_interpretation_service as service_module
from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.application.resource_guard import (
    ResourceChecker,
    ResourcePreflightResult,
)


def _write_bids_run(root: Path) -> tuple[Path, Path]:
    root.mkdir(parents=True)
    (root / "dataset_description.json").write_text(
        json.dumps({"Name": "events-sidecar-test", "BIDSVersion": "1.11.1"}),
        encoding="utf-8",
    )
    eeg_dir = root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    stem = "sub-01_task-mi_run-1"
    eeg_path = eeg_dir / f"{stem}_eeg.fif"
    events_path = eeg_dir / f"{stem}_events.tsv"
    info = mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg")
    raw = mne.io.RawArray(np.zeros((1, 200)), info, verbose="ERROR")
    raw.save(eeg_path, overwrite=True, verbose="ERROR")
    events_path.write_text(
        "onset\tduration\ttrial_type\tvalue\n0\t1\tleft\t1\n",
        encoding="utf-8",
    )
    return eeg_path.resolve(), events_path.resolve()


def _safe_preflight(paths: list[str]) -> ResourcePreflightResult:
    return ResourcePreflightResult(
        (),
        {
            "risk_level": "safe",
            "files": [
                {
                    "path": path,
                    "file_bytes": Path(path).stat().st_size,
                    "resource_kind": "scan_metadata",
                }
                for path in paths
            ],
        },
    )


def test_events_json_candidates_stop_at_dataset_root_and_keep_inheritance(
    tmp_path: Path,
) -> None:
    root = tmp_path / "container" / "bids"
    _eeg_path, events_path = _write_bids_run(root)
    local_sidecar = events_path.with_suffix(".json")
    subject_sidecar = root / "sub-01" / "task-mi_events.json"
    root_sidecar = root / "events.json"
    outside_task_sidecar = root.parent / "task-mi_events.json"
    outside_default_sidecar = root.parent / "events.json"

    candidates = set(bids_resources.bids_events_json_candidates(events_path))

    assert {local_sidecar, subject_sidecar, root_sidecar} <= candidates
    assert outside_task_sidecar not in candidates
    assert outside_default_sidecar not in candidates


@pytest.mark.parametrize("outside_name", ["task-mi_events.json", "events.json"])
def test_review_does_not_admit_or_read_events_json_outside_dataset_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outside_name: str,
) -> None:
    root = tmp_path / "container" / "bids"
    _eeg_path, events_path = _write_bids_run(root)
    legal_sidecars = {
        events_path.with_suffix(".json"),
        root / "sub-01" / "task-mi_events.json",
        root / "events.json",
    }
    for sidecar in legal_sidecars:
        sidecar.write_text(
            json.dumps({"trial_type": {"Description": str(sidecar.parent)}}),
            encoding="utf-8",
        )
    outside_sidecar = root.parent / outside_name
    outside_sidecar.write_text(
        json.dumps({"trial_type": {"Levels": {"left": "OUTSIDE DATASET"}}}),
        encoding="utf-8",
    )
    observed_sidecars = {*legal_sidecars, outside_sidecar}
    checked_scopes: list[list[str]] = []
    real_preflight = service_module.check_import_resource_preflight

    def _capture_preflight(paths: list[str]) -> ResourcePreflightResult:
        scope = list(paths)
        checked_scopes.append(scope)
        return real_preflight(scope)

    opened: Counter[Path] = Counter()
    real_path_open = Path.open

    def _observed_open(path: Path, *args, **kwargs):
        resolved = path.resolve()
        if resolved in observed_sidecars:
            opened[resolved] += 1
        return real_path_open(path, *args, **kwargs)

    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        _capture_preflight,
    )
    monkeypatch.setattr(
        ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 10**12,
                "total_bytes": 10**12,
                "used_bytes": 0,
            }
        ),
    )
    monkeypatch.setattr(Path, "open", _observed_open)

    result = ApplicationService().execute(
        ReviewInterpretationCommand(
            source_path=str(root),
            source_hint="bids",
        ),
    )

    assert result.failed is False
    assert checked_scopes
    admitted = {Path(path).resolve() for path in checked_scopes[0]}
    assert legal_sidecars <= admitted
    assert outside_sidecar not in admitted
    assert opened == Counter({path.resolve(): 2 for path in legal_sidecars})
    assert (
        "OUTSIDE DATASET" not in result.diagnostics["candidate"]["class_map"].values()
    )


def test_events_json_candidates_find_dataset_root_beyond_eight_ancestors(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    root.mkdir()
    (root / "dataset_description.json").write_text("{}", encoding="utf-8")
    deep_directory = root.joinpath(*(f"level-{index}" for index in range(10)))
    events_path = deep_directory / "sub-01_task-mi_events.tsv"

    candidates = bids_resources.bids_events_json_candidates(events_path)

    assert root / "task-mi_events.json" in candidates
    assert root / "events.json" in candidates


def test_non_bids_events_carrier_limits_sidecars_to_local_directory(
    tmp_path: Path,
) -> None:
    carrier_directory = tmp_path / "loose"
    carrier_directory.mkdir()
    events_path = carrier_directory / "sub-01_task-mi_events.tsv"
    local_sidecar = events_path.with_suffix(".json")
    inherited_sidecar = tmp_path / "task-mi_events.json"
    local_sidecar.write_text("{}", encoding="utf-8")
    inherited_sidecar.write_text("{}", encoding="utf-8")

    candidates = bids_resources.bids_events_json_candidates(events_path)
    resource_paths = {
        Path(path)
        for path in bids_resources.bids_events_json_resource_paths([str(events_path)])
    }

    assert local_sidecar in candidates
    assert all(candidate.parent == carrier_directory for candidate in candidates)
    assert resource_paths == {local_sidecar.resolve()}


def test_review_admits_and_verifies_each_materializable_events_json_twice(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "bids"
    _eeg_path, events_path = _write_bids_run(root)
    local_sidecar = events_path.with_suffix(".json")
    inherited_sidecar = root / "task-mi_events.json"
    local_sidecar.write_text(
        json.dumps({"trial_type": {"Description": "Movement class"}}),
        encoding="utf-8",
    )
    inherited_sidecar.write_text(
        json.dumps({"trial_type": {"Levels": {"left": "Left hand"}}}),
        encoding="utf-8",
    )
    sidecars = {local_sidecar.resolve(), inherited_sidecar.resolve()}
    checked_scopes: list[list[str]] = []
    real_preflight = service_module.check_import_resource_preflight

    def _capture_preflight(paths: list[str]) -> ResourcePreflightResult:
        scope = list(paths)
        checked_scopes.append(scope)
        return real_preflight(scope)

    opened: Counter[Path] = Counter()
    real_path_open = Path.open

    def _observed_open(path: Path, *args, **kwargs):
        resolved = path.resolve()
        if resolved in sidecars:
            opened[resolved] += 1
        return real_path_open(path, *args, **kwargs)

    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        _capture_preflight,
    )
    monkeypatch.setattr(
        ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 10**12,
                "total_bytes": 10**12,
                "used_bytes": 0,
            }
        ),
    )
    monkeypatch.setattr(Path, "open", _observed_open)

    result = ApplicationService().execute(
        ReviewInterpretationCommand(
            source_path=str(root),
            source_hint="bids",
        ),
    )

    assert result.failed is False
    assert checked_scopes
    admitted = {Path(path).resolve() for path in checked_scopes[0]}
    assert sidecars <= admitted
    assert opened == Counter(dict.fromkeys(sidecars, 2))
    candidate = result.diagnostics["candidate"]
    assert candidate["class_map"] == {}
    [plan] = candidate["label_carrier_plan"]
    assert plan["value_decisions"]["left"]["suggested_name"] == "Left hand"
    assert plan["value_decisions"]["left"]["decision"] == "unresolved"
    [run] = result.diagnostics["candidate"]["bids"]["event_validation"]["runs"]
    assert run["event_code_class_map"] == {}
    reader_diagnostics = result.diagnostics["resource_preflight"]["bids_events_json"]
    assert reader_diagnostics == {
        "read_limit_bytes": 1_048_576,
        "bytes_read": sum(path.stat().st_size for path in sidecars),
        "admitted_path_count": 2,
        "cached_path_count": 2,
    }


def test_events_json_inheritance_stops_at_dataset_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = tmp_path / "container"
    root = container / "bids"
    _eeg_path, events_path = _write_bids_run(root)
    legal_sidecars = {
        events_path.with_suffix(".json"),
        events_path.parent / "task-mi_events.json",
        root / "sub-01" / "events.json",
        root / "events.json",
    }
    outside_sidecars = {
        container / "task-mi_events.json",
        container / "events.json",
    }
    for sidecar in legal_sidecars | outside_sidecars:
        sidecar.write_text("{}", encoding="utf-8")

    candidates = {
        candidate.resolve()
        for candidate in bids_resources.bids_events_json_candidates(events_path)
    }
    checked_scopes: list[list[str]] = []
    real_preflight = service_module.check_import_resource_preflight

    def _capture_preflight(paths: list[str]) -> ResourcePreflightResult:
        scope = list(paths)
        checked_scopes.append(scope)
        return real_preflight(scope)

    opened: Counter[Path] = Counter()
    real_path_open = Path.open

    def _observed_open(path: Path, *args, **kwargs):
        resolved = path.resolve()
        if resolved in legal_sidecars | outside_sidecars:
            opened[resolved] += 1
        return real_path_open(path, *args, **kwargs)

    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        _capture_preflight,
    )
    monkeypatch.setattr(
        ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 10**12,
                "total_bytes": 10**12,
                "used_bytes": 0,
            }
        ),
    )
    monkeypatch.setattr(Path, "open", _observed_open)

    result = ApplicationService().execute(
        ReviewInterpretationCommand(
            source_path=str(root),
            source_hint="bids",
        ),
    )

    assert result.failed is False
    assert checked_scopes
    admitted = {Path(path).resolve() for path in checked_scopes[0]}
    assert {
        "legal_candidates_preserved": legal_sidecars <= candidates,
        "outside_candidates_excluded": candidates.isdisjoint(outside_sidecars),
        "legal_sidecars_admitted": legal_sidecars <= admitted,
        "outside_sidecars_not_admitted": admitted.isdisjoint(outside_sidecars),
        "legal_sidecars_read_twice": all(opened[path] == 2 for path in legal_sidecars),
        "outside_sidecars_not_read": all(
            opened[path] == 0 for path in outside_sidecars
        ),
    } == {
        "legal_candidates_preserved": True,
        "outside_candidates_excluded": True,
        "legal_sidecars_admitted": True,
        "outside_sidecars_not_admitted": True,
        "legal_sidecars_read_twice": True,
        "outside_sidecars_not_read": True,
    }


def test_events_json_candidates_without_bids_root_stay_local(tmp_path: Path) -> None:
    carrier = tmp_path / "not-bids" / "sub-01" / "eeg" / "task-mi_events.tsv"
    carrier.parent.mkdir(parents=True)
    carrier.write_text("onset\tduration\n0\t1\n", encoding="utf-8")
    (tmp_path / "task-mi_events.json").write_text("{}", encoding="utf-8")
    (tmp_path / "events.json").write_text("{}", encoding="utf-8")

    candidates = bids_resources.bids_events_json_candidates(carrier)

    assert candidates
    assert {candidate.parent for candidate in candidates} == {carrier.parent}


def test_events_json_candidates_follow_dataset_marker_without_depth_limit(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    root.mkdir()
    (root / "dataset_description.json").write_text("{}", encoding="utf-8")
    carrier_directory = root.joinpath(*(f"level-{index}" for index in range(10)))
    carrier_directory.mkdir(parents=True)
    carrier = carrier_directory / "task-mi_events.tsv"
    carrier.write_text("onset\tduration\n0\t1\n", encoding="utf-8")

    candidates = {
        candidate.resolve()
        for candidate in bids_resources.bids_events_json_candidates(carrier)
    }

    assert (root / "task-mi_events.json").resolve() in candidates
    assert (root.parent / "task-mi_events.json").resolve() not in candidates


def test_oversized_events_json_fails_before_parse_or_state_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "bids"
    _eeg_path, events_path = _write_bids_run(root)
    sidecar = events_path.with_suffix(".json")
    sidecar.write_bytes(
        b'{"padding":"'
        + (b"x" * bids_resources.BIDS_EVENTS_JSON_READ_BUDGET_BYTES)
        + b'"}',
    )
    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        _safe_preflight,
    )

    result = ApplicationService().execute(
        ReviewInterpretationCommand(
            source_path=str(root),
            source_hint="bids",
        ),
    )

    assert result.failed is True
    diagnostics = result.diagnostics["bids_events_json"]
    assert diagnostics["code"] == "events_json_sidecar_too_large"
    assert diagnostics["path"] == str(sidecar.resolve())
    assert diagnostics["admitted_bytes"] == sidecar.stat().st_size
    assert diagnostics["read_limit_bytes"] == 1_048_576
    assert diagnostics["json_parsing_started"] is False
    assert diagnostics["state_preserved"] is True
    assert result.state.interpretation.has_scan_result is False
    assert result.state.interpretation.has_candidate is False


def test_events_json_growth_after_admission_fails_closed_before_parse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "bids"
    _eeg_path, events_path = _write_bids_run(root)
    sidecar = events_path.with_suffix(".json")
    sidecar.write_text(
        json.dumps({"trial_type": {"Levels": {"left": "Left hand"}}}),
        encoding="utf-8",
    )
    admitted_bytes = sidecar.stat().st_size

    def _admit_then_grow(paths: list[str]) -> ResourcePreflightResult:
        preflight = _safe_preflight(paths)
        with sidecar.open("ab") as handle:
            handle.write(b" ")
        return preflight

    monkeypatch.setattr(
        service_module,
        "check_import_resource_preflight",
        _admit_then_grow,
    )

    result = ApplicationService().execute(
        ReviewInterpretationCommand(
            source_path=str(root),
            source_hint="bids",
        ),
    )

    assert result.failed is True
    diagnostics = result.diagnostics["bids_events_json"]
    assert diagnostics["code"] == "events_json_sidecar_changed_after_admission"
    assert diagnostics["path"] == str(sidecar.resolve())
    assert diagnostics["admitted_bytes"] == admitted_bytes
    assert diagnostics["observed_bytes"] == admitted_bytes + 1
    assert diagnostics["bytes_read"] == 0
    assert diagnostics["json_parsing_started"] is False
    assert diagnostics["state_preserved"] is True
    assert result.state.interpretation.has_scan_result is False
    assert result.state.interpretation.has_candidate is False


def test_events_json_is_accounted_as_scan_metadata_by_ram_preflight(
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / "task-mi_events.json"
    sidecar.write_text(
        json.dumps({"trial_type": {"Levels": {"left": "Left hand"}}}),
        encoding="utf-8",
    )

    estimate = ResourceChecker.estimate_dataset_ram([str(sidecar)])

    assert estimate["scan_metadata_count"] == 1
    assert estimate["scan_metadata_file_bytes"] == sidecar.stat().st_size
    assert estimate["eeg_path_count"] == 0
    [details] = estimate["files"]
    assert details["resource_kind"] == "scan_metadata"


def test_admitted_events_json_disappearance_does_not_fall_back_silently(
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / "task-mi_events.json"
    sidecar.write_text(
        json.dumps({"trial_type": {"Levels": {"left": "Left hand"}}}),
        encoding="utf-8",
    )
    admitted_bytes = sidecar.stat().st_size
    reader = bids_resources.BidsEventsJsonReader.from_paths([str(sidecar)])
    sidecar.unlink()

    with pytest.raises(PreconditionError) as raised:
        reader.read_object(sidecar)

    diagnostics = raised.value.diagnostics["bids_events_json"]
    assert diagnostics["code"] == "events_json_sidecar_changed_after_admission"
    assert diagnostics["admitted_bytes"] == admitted_bytes
    assert diagnostics["observed_bytes"] is None
    assert diagnostics["json_parsing_started"] is False


def test_reader_rejects_same_size_atomic_replacement_after_admission(
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / "task-mi_events.json"
    sidecar.write_bytes(b'{"a":1}')
    reader = bids_resources.BidsEventsJsonReader.from_paths([str(sidecar)])
    replacement = tmp_path / "replacement.json"
    replacement.write_bytes(b'{"b":2}')
    assert replacement.stat().st_size == sidecar.stat().st_size
    replacement.replace(sidecar)

    with pytest.raises(PreconditionError) as raised:
        reader.read_object(sidecar)

    diagnostics = raised.value.diagnostics["bids_events_json"]
    assert diagnostics["code"] == "events_json_sidecar_changed_after_admission"
    assert diagnostics["admitted_bytes"] == len(b'{"a":1}')
    assert diagnostics["observed_bytes"] == len(b'{"b":2}')
    assert diagnostics["bytes_read"] == 0
    assert diagnostics["json_parsing_started"] is False


def test_reader_rejects_same_size_in_place_replacement_after_admission(
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / "task-mi_events.json"
    sidecar.write_bytes(b'{"a":1}')
    admitted_stat = sidecar.stat()
    reader = bids_resources.BidsEventsJsonReader.from_paths([str(sidecar)])

    with sidecar.open("r+b") as handle:
        handle.write(b'{"b":2}')
        handle.flush()
        os.fsync(handle.fileno())
    os.utime(
        sidecar,
        ns=(admitted_stat.st_atime_ns, admitted_stat.st_mtime_ns + 1_000_000_000),
    )
    assert sidecar.stat().st_size == admitted_stat.st_size

    with pytest.raises(PreconditionError) as raised:
        reader.read_object(sidecar)

    diagnostics = raised.value.diagnostics["bids_events_json"]
    assert diagnostics["code"] == "events_json_sidecar_changed_after_admission"
    assert diagnostics["admitted_bytes"] == len(b'{"a":1}')
    assert diagnostics["observed_bytes"] == len(b'{"b":2}')
    assert diagnostics["bytes_read"] == 0
    assert diagnostics["json_parsing_started"] is False


def test_reader_content_hash_rejects_change_even_when_stat_check_is_inconclusive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sidecar = tmp_path / "task-mi_events.json"
    sidecar.write_bytes(b'{"a":1}')
    reader = bids_resources.BidsEventsJsonReader.from_paths([str(sidecar)])
    monkeypatch.setattr(reader, "_assert_stable_identity", lambda **_kwargs: None)
    sidecar.write_bytes(b'{"b":2}')

    with pytest.raises(PreconditionError) as raised:
        reader.read_object(sidecar)

    diagnostics = raised.value.diagnostics["bids_events_json"]
    assert diagnostics["code"] == "events_json_sidecar_changed_after_admission"
    assert diagnostics["changed_identity_fields"] == ["content_sha256"]
    assert diagnostics["json_parsing_started"] is False


def test_reader_reads_unchanged_admitted_object_once_within_shared_budget(
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / "task-mi_events.json"
    encoded = b'{"trial_type":{"Description":"Movement class"}}'
    sidecar.write_bytes(encoded)
    reader = bids_resources.BidsEventsJsonReader.from_paths([str(sidecar)])

    first = reader.read_object(sidecar)
    second = reader.read_object(sidecar)

    assert first == {"trial_type": {"Description": "Movement class"}}
    assert second is first
    assert reader.diagnostics() == {
        "read_limit_bytes": bids_resources.BIDS_EVENTS_JSON_READ_BUDGET_BYTES,
        "bytes_read": len(encoded),
        "admitted_path_count": 1,
        "cached_path_count": 1,
    }


def test_reader_budget_and_dataset_root_inheritance_remain_bounded(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    root.mkdir()
    (root / "dataset_description.json").write_text("{}", encoding="utf-8")
    events_path = root / "sub-01" / "eeg" / "sub-01_task-mi_events.tsv"
    events_path.parent.mkdir(parents=True)
    events_path.write_text("onset\tduration\n0\t1\n", encoding="utf-8")
    root_sidecar = root / "task-mi_events.json"
    root_sidecar.write_bytes(
        b" " * (bids_resources.BIDS_EVENTS_JSON_READ_BUDGET_BYTES + 1)
    )

    candidates = bids_resources.bids_events_json_candidates(events_path)

    assert root_sidecar in candidates
    assert all(
        candidate == root or root in candidate.parents for candidate in candidates
    )
    with pytest.raises(PreconditionError) as raised:
        bids_resources.BidsEventsJsonReader.from_paths([str(root_sidecar)])
    diagnostics = raised.value.diagnostics["bids_events_json"]
    assert diagnostics["code"] == "events_json_sidecar_too_large"
    assert diagnostics["read_limit_bytes"] == 1_048_576
