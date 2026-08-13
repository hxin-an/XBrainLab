from __future__ import annotations

from collections import Counter
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, cast

import pytest

from XBrainLab.backend.application import bids_dataset_index as index_module
from XBrainLab.backend.application.bids_dataset_index import (
    build_bids_dataset_index,
)
from XBrainLab.backend.application.bids_subject_catalog import (
    inspect_bids_subject_catalog,
)
from XBrainLab.backend.application.commands import ScanSourceCommand
from XBrainLab.backend.application.data_interpretation_scan import (
    _ScanBudget,
    discover_source_preflight_scope,
    scan_source_path,
)
from XBrainLab.backend.application.data_interpretation_service import (
    DataInterpretationCommandService,
)


def _write_bids_dataset(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    description = root / "dataset_description.json"
    description.write_text(
        '{"Name": "indexed", "BIDSVersion": "1.11.0"}',
        encoding="utf-8",
    )
    participants = root / "participants.tsv"
    participants.write_text(
        "participant_id\nsub-01\nsub-02\n",
        encoding="utf-8",
    )
    paths: dict[str, Path] = {
        "description": description,
        "participants": participants,
    }
    for subject, task in (("01", "p300"), ("02", "mi")):
        eeg_dir = root / f"sub-{subject}" / "ses-01" / "eeg"
        eeg_dir.mkdir(parents=True)
        stem = f"sub-{subject}_ses-01_task-{task}_run-1"
        eeg = eeg_dir / f"{stem}_eeg.edf"
        events = eeg_dir / f"{stem}_events.tsv"
        channels = eeg_dir / f"{stem}_channels.tsv"
        eeg_json = eeg_dir / f"{stem}_eeg.json"
        electrodes = eeg_dir / f"sub-{subject}_ses-01_electrodes.tsv"
        coordsystem = eeg_dir / f"sub-{subject}_ses-01_coordsystem.json"
        inherited_events_json = eeg_dir / f"task-{task}_events.json"
        eeg.write_bytes(b"header only")
        events.write_text(
            "onset\tduration\ttrial_type\n0\t1\tleft\n",
            encoding="utf-8",
        )
        channels.write_text("name\tstatus\nC3\tgood\n", encoding="utf-8")
        eeg_json.write_text('{"EEGReference": "average"}', encoding="utf-8")
        electrodes.write_text("name\tx\ty\tz\nC3\t0\t0\t1\n", encoding="utf-8")
        coordsystem.write_text(
            '{"EEGCoordinateSystem": "CapTrak"}',
            encoding="utf-8",
        )
        inherited_events_json.write_text(
            '{"trial_type": {"Description": "condition"}}',
            encoding="utf-8",
        )
        for kind, path in (
            ("eeg", eeg),
            ("events", events),
            ("channels", channels),
            ("eeg_json", eeg_json),
            ("electrodes", electrodes),
            ("coordsystem", coordsystem),
            ("events_json", inherited_events_json),
        ):
            paths[f"{subject}_{kind}"] = path
    return paths


def test_index_is_immutable_and_projects_catalog_and_subjects_without_rewalking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_root = tmp_path / "container" / "selected-bids"
    sibling_root = tmp_path / "container" / "sibling-bids"
    paths = _write_bids_dataset(selected_root)
    sibling_paths = _write_bids_dataset(sibling_root)
    directory_reads: Counter[str] = Counter()
    original_iterdir = Path.iterdir

    def _observed_iterdir(path: Path):
        directory_reads[str(path.resolve())] += 1
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", _observed_iterdir)
    index = build_bids_dataset_index(selected_root)

    assert index.root == str(selected_root.resolve())
    assert index.completeness.complete is True
    assert index.completeness.blocked_reasons == ()
    assert max(directory_reads.values()) == 1
    assert len(index.recordings) == 2
    with pytest.raises(FrozenInstanceError):
        index.root = str(sibling_root)  # type: ignore[misc]

    def _forbid_rewalk(_path: Path):
        pytest.fail("an immutable BIDS index projection re-walked the dataset")

    monkeypatch.setattr(Path, "iterdir", _forbid_rewalk)
    catalog = index.subject_catalog()
    projection = index.project(["sub-02"])

    assert [row["subject"] for row in catalog["subjects"]] == ["01", "02"]
    assert projection.selected_subjects == ("02",)
    assert projection.eeg_files == (str(paths["02_eeg"].resolve()),)
    assert projection.events_files == (str(paths["02_events"].resolve()),)
    assert projection.channels_files == (str(paths["02_channels"].resolve()),)
    assert projection.electrodes_files == (str(paths["02_electrodes"].resolve()),)
    assert projection.coordsystem_files == (str(paths["02_coordsystem"].resolve()),)
    assert str(paths["02_eeg_json"].resolve()) in projection.json_sidecar_files
    assert str(paths["02_events_json"].resolve()) in projection.json_sidecar_files
    assert projection.events_json_by_carrier[str(paths["02_events"].resolve())] == (
        str(paths["02_events_json"].resolve()),
    )
    assert str(paths["description"].resolve()) in projection.metadata_files
    assert str(paths["participants"].resolve()) in projection.metadata_files
    assert not any("sub-01" in path for path in projection.all_files)
    assert not any(
        str(path.resolve()) in projection.all_files for path in sibling_paths.values()
    )


def test_index_skips_substitution_outside_explicit_root(tmp_path: Path) -> None:
    selected_root = tmp_path / "selected"
    paths = _write_bids_dataset(selected_root)
    outside = tmp_path / "outside-events.json"
    outside.write_text('{"trial_type": {}}', encoding="utf-8")
    escaped = paths["02_events"].with_name("task-mi_events.json")
    escaped.unlink()
    escaped.symlink_to(outside)

    index = build_bids_dataset_index(selected_root)
    projection = index.project(["02"])

    assert str(outside.resolve()) not in projection.all_files
    assert str(outside.resolve()) not in projection.json_sidecar_files
    assert projection.events_json_by_carrier[str(paths["02_events"].resolve())] == ()
    assert any("symbolic link" in warning for warning in index.warnings)


def test_registry_never_assigns_parent_index_to_skipped_nested_bids_recording(
    tmp_path: Path,
) -> None:
    parent_root = tmp_path / "parent-bids"
    nested_root = parent_root / "sourcedata" / "nested-bids"
    parent_paths = _write_bids_dataset(parent_root)
    nested_paths = _write_bids_dataset(nested_root)

    parent_index = build_bids_dataset_index(parent_root)

    assert str(nested_root.resolve()) in parent_index.skipped_nested_bids_roots
    assert (
        index_module.current_bids_dataset_index_for_path(parent_paths["01_eeg"])
        is parent_index
    )
    assert (
        index_module.current_bids_dataset_index_for_path(nested_paths["01_eeg"]) is None
    )

    nested_index = build_bids_dataset_index(nested_root)

    assert (
        index_module.current_bids_dataset_index_for_path(nested_paths["01_eeg"])
        is nested_index
    )


def test_container_with_one_nested_bids_root_resolves_once_for_catalog_and_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = tmp_path / "selected-container"
    nested_root = container / "download" / "converted-bids"
    paths = _write_bids_dataset(nested_root)
    directory_reads: Counter[str] = Counter()
    original_iterdir = Path.iterdir

    def _observed_iterdir(path: Path):
        directory_reads[str(path.resolve())] += 1
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", _observed_iterdir)
    index = build_bids_dataset_index(container)

    assert index.root == str(nested_root.resolve())
    assert index.selection_root == str(container.resolve())
    assert index.nested_bids_candidates == (str(nested_root.resolve()),)
    assert index.matches_root(container) is True
    assert max(directory_reads.values()) == 1

    def _forbid_rewalk(_path: Path):
        pytest.fail("catalog/scan projection re-walked the selected container")

    monkeypatch.setattr(Path, "iterdir", _forbid_rewalk)
    catalog = inspect_bids_subject_catalog(container, bids_index=index)
    scope = discover_source_preflight_scope(
        source_path=str(container),
        source_hint="bids",
        selected_bids_subjects=["02"],
        bids_index=index,
    )

    assert catalog["root"] == str(nested_root.resolve())
    assert catalog["selection_root"] == str(container.resolve())
    assert scope.source_path == str(nested_root.resolve())
    assert scope.scan_root == str(nested_root.resolve())
    assert scope.eeg_files == [str(paths["02_eeg"].resolve())]


def test_exact_bids_root_is_preferred_over_nested_formal_root(tmp_path: Path) -> None:
    exact_paths = _write_bids_dataset(tmp_path)
    nested_root = tmp_path / "sourcedata" / "nested-bids"
    nested_paths = _write_bids_dataset(nested_root)

    index = build_bids_dataset_index(tmp_path)

    assert index.root == str(tmp_path.resolve())
    assert index.selection_root == str(tmp_path.resolve())
    assert index.nested_bids_candidates == ()
    assert str(exact_paths["01_eeg"].resolve()) in index.project().eeg_files
    assert str(nested_paths["01_eeg"].resolve()) not in index.project().all_files


def test_container_with_multiple_nested_bids_roots_fails_closed_with_candidates(
    tmp_path: Path,
) -> None:
    container = tmp_path / "selected-container"
    first = container / "first"
    second = container / "second"
    first_paths = _write_bids_dataset(first)
    second_paths = _write_bids_dataset(second)

    index = build_bids_dataset_index(container)

    assert index.looks_like_bids is False
    assert index.completeness.complete is False
    assert index.nested_bids_candidates == (
        str(first.resolve()),
        str(second.resolve()),
    )
    assert "Multiple nested BIDS roots" in index.root_validation_issue
    assert str(first.resolve()) in index.root_validation_issue
    assert str(second.resolve()) in index.root_validation_issue
    assert str(first_paths["01_eeg"].resolve()) not in index.project().all_files
    assert str(second_paths["01_eeg"].resolve()) not in index.project().all_files
    with pytest.raises(ValueError, match="Multiple nested BIDS roots"):
        inspect_bids_subject_catalog(container, bids_index=index)


def test_nested_root_resolution_invalidates_when_second_candidate_is_added(
    tmp_path: Path,
) -> None:
    container = tmp_path / "selected-container"
    first = container / "first"
    _write_bids_dataset(first)
    index = build_bids_dataset_index(container)

    assert index.is_current() is True

    second = container / "second"
    _write_bids_dataset(second)

    assert index.is_current() is False
    refreshed = build_bids_dataset_index(container)
    assert refreshed.looks_like_bids is False
    assert "Multiple nested BIDS roots" in refreshed.root_validation_issue


@pytest.mark.parametrize("mutation", ["add", "remove"])
def test_index_seal_rejects_directory_entry_mutation_after_enumeration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    paths = _write_bids_dataset(tmp_path)
    eeg_directory = paths["01_eeg"].parent
    added_sidecar = eeg_directory / "sub-01_task-p300_physio.json"
    removed_sidecar = paths["01_events"]
    original_capture = index_module._IndexedPathIdentity.capture.__func__
    mutation_count = 0

    def _capture_after_mutating_enumerated_directory(
        cls: type[Any],
        path: Path,
    ):
        nonlocal mutation_count
        if path == eeg_directory and mutation_count == 0:
            mutation_count += 1
            if mutation == "add":
                added_sidecar.write_text(
                    '{"SamplingFrequency": 10}',
                    encoding="utf-8",
                )
            else:
                removed_sidecar.unlink()
        return original_capture(cls, path)

    monkeypatch.setattr(
        index_module._IndexedPathIdentity,
        "capture",
        classmethod(_capture_after_mutating_enumerated_directory),
    )

    index = build_bids_dataset_index(tmp_path)

    assert mutation_count == 1
    if mutation == "add":
        assert str(added_sidecar.resolve()) not in index.indexed_files
    else:
        assert str(removed_sidecar.resolve()) in index.indexed_files
    assert index.completeness.complete is False
    assert any(
        "changed while the BIDS index was being built" in reason
        for reason in index.completeness.blocked_reasons
    )
    assert index.is_current() is False
    assert index_module.current_bids_dataset_index_for_path(paths["01_eeg"]) is None


def test_service_reuses_resolved_nested_index_between_catalog_and_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = tmp_path / "selected-container"
    nested_root = container / "download" / "converted-bids"
    paths = _write_bids_dataset(nested_root)
    build_count = 0
    original_build = index_module.build_bids_dataset_index

    def _counted_build(source_path: str | Path):
        nonlocal build_count
        build_count += 1
        return original_build(source_path)

    monkeypatch.setattr(index_module, "build_bids_dataset_index", _counted_build)
    service = DataInterpretationCommandService(
        cast(Any, object()),
        data_filename=lambda data: str(data),
        data_filepath=lambda data: str(data),
    )

    catalog = service.handle_scan_source(
        ScanSourceCommand(
            source_path=str(container),
            source_hint="bids",
            catalog_only=True,
        )
    )
    selected = service.handle_scan_source(
        ScanSourceCommand(
            source_path=str(container),
            source_hint="bids",
            selected_bids_subjects=["02"],
        )
    )

    assert isinstance(catalog, tuple)
    assert isinstance(selected, tuple)
    assert build_count == 1
    catalog_payload = catalog[1]["bids_subject_catalog"]
    selected_scan = selected[1]["scan_result"]
    assert catalog_payload["root"] == str(nested_root.resolve())
    assert catalog_payload["selection_root"] == str(container.resolve())
    assert selected_scan["source_path"] == str(nested_root.resolve())
    assert selected_scan["eeg_files"] == [str(paths["02_eeg"].resolve())]


def test_bounded_index_reports_incomplete_traversal_and_blocks_scan(
    tmp_path: Path,
) -> None:
    _write_bids_dataset(tmp_path)
    index = build_bids_dataset_index(
        tmp_path,
        _scan_budget=_ScanBudget(max_depth=2),
    )
    scope = discover_source_preflight_scope(
        source_path=str(tmp_path),
        source_hint="bids",
        bids_index=index,
    )
    scan = scan_source_path(
        scan_id="scan-bounded-index",
        source_path=str(tmp_path),
        source_hint="bids",
        preflight_scope=scope,
        materialize_metadata=False,
    )

    assert index.completeness.complete is False
    assert index.completeness.traversal_complete is False
    assert any(
        "bounded traversal limit" in item for item in index.completeness.blocked_reasons
    )
    assert scope.bids["index_completeness"] == index.completeness.to_dict()
    assert any("bounded traversal limit" in item for item in scan.blocked_reasons)


def test_projection_keeps_brainvision_and_eeglab_parser_dependencies(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bids"
    eeg_dir = root / "sub-01" / "eeg"
    eeg_dir.mkdir(parents=True)
    (root / "dataset_description.json").write_text(
        '{"Name": "dependencies", "BIDSVersion": "1.11.0"}',
        encoding="utf-8",
    )
    brainvision = eeg_dir / "sub-01_task-bv_eeg.vhdr"
    brainvision_data = eeg_dir / "sub-01_task-bv_eeg.eeg"
    brainvision_markers = eeg_dir / "sub-01_task-bv_eeg.vmrk"
    eeglab = eeg_dir / "sub-01_task-eeglab_eeg.set"
    eeglab_data = eeg_dir / "sub-01_task-eeglab_eeg.fdt"
    brainvision.write_text(
        "Brain Vision Data Exchange Header File Version 1.0\n"
        "[Common Infos]\n"
        f"DataFile={brainvision_data.name}\n"
        f"MarkerFile={brainvision_markers.name}\n",
        encoding="utf-8",
    )
    brainvision_data.write_bytes(b"signal")
    brainvision_markers.write_text(
        "Brain Vision Data Exchange Marker File, Version 1.0\n",
        encoding="utf-8",
    )
    eeglab.write_bytes(b"set header")
    eeglab_data.write_bytes(b"external data")

    projection = build_bids_dataset_index(root).project(["01"])

    assert projection.eeg_files == (str(brainvision.resolve()), str(eeglab.resolve()))
    assert {
        str(brainvision_data.resolve()),
        str(brainvision_markers.resolve()),
        str(eeglab_data.resolve()),
    } <= set(projection.all_files)


def test_projection_keeps_subject_and_session_inherited_eeg_sidecars(
    tmp_path: Path,
) -> None:
    paths = _write_bids_dataset(tmp_path)
    subject_events = tmp_path / "sub-02" / "task-mi_events.json"
    session_electrodes = tmp_path / "sub-02" / "ses-01" / "electrodes.tsv"
    session_coordsystem = tmp_path / "sub-02" / "ses-01" / "coordsystem.json"
    subject_events.write_text('{"trial_type": {}}', encoding="utf-8")
    session_electrodes.write_text("name\tx\ty\tz\nC3\t0\t0\t1\n", encoding="utf-8")
    session_coordsystem.write_text(
        '{"EEGCoordinateSystem": "CapTrak"}',
        encoding="utf-8",
    )

    projection = build_bids_dataset_index(tmp_path).project(["02"])

    assert str(subject_events.resolve()) in projection.json_sidecar_files
    assert str(session_electrodes.resolve()) in projection.electrodes_files
    assert str(session_coordsystem.resolve()) in projection.coordsystem_files
    assert projection.events_json_by_carrier[str(paths["02_events"].resolve())] == (
        str(paths["02_events_json"].resolve()),
        str(subject_events.resolve()),
    )


def test_service_reuses_current_index_and_invalidates_after_sidecar_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _write_bids_dataset(tmp_path)
    build_count = 0
    original_build = index_module.build_bids_dataset_index

    def _counted_build(source_path: str | Path):
        nonlocal build_count
        build_count += 1
        return original_build(source_path)

    monkeypatch.setattr(index_module, "build_bids_dataset_index", _counted_build)
    service = DataInterpretationCommandService(
        cast(Any, object()),
        data_filename=lambda data: str(data),
        data_filepath=lambda data: str(data),
    )

    catalog = service.handle_scan_source(
        ScanSourceCommand(
            source_path=str(tmp_path),
            source_hint="bids",
            catalog_only=True,
        )
    )
    selected = service.handle_scan_source(
        ScanSourceCommand(
            source_path=str(tmp_path),
            source_hint="bids",
            selected_bids_subjects=["02"],
        )
    )

    assert isinstance(catalog, tuple)
    assert isinstance(selected, tuple)
    assert build_count == 1
    selected_scan = selected[1]["scan_result"]
    assert selected_scan["eeg_files"] == [str(paths["02_eeg"].resolve())]
    assert selected_scan["bids"]["index_completeness"]["complete"] is True

    added_sidecar = paths["02_eeg"].with_name("sub-02_ses-01_task-mi_run-1_physio.json")
    added_sidecar.write_text('{"SamplingFrequency": 10}', encoding="utf-8")
    refreshed = service.handle_scan_source(
        ScanSourceCommand(
            source_path=str(tmp_path),
            source_hint="bids",
            selected_bids_subjects=["02"],
        )
    )

    assert isinstance(refreshed, tuple)
    assert build_count == 2
    assert (
        str(added_sidecar.resolve())
        in refreshed[1]["scan_result"]["bids"]["json_sidecar_files"]
    )


def test_catalog_and_scan_do_not_own_additional_bids_tree_walkers() -> None:
    root = Path(__file__).resolve().parents[4]
    application_root = root / "XBrainLab/backend/application"
    index_source = (application_root / "bids_dataset_index.py").read_text(
        encoding="utf-8"
    )
    catalog_source = (application_root / "bids_subject_catalog.py").read_text(
        encoding="utf-8"
    )
    scan_source = (application_root / "data_interpretation_scan.py").read_text(
        encoding="utf-8"
    )
    montage_source = (application_root / "bids_montage_preparation.py").read_text(
        encoding="utf-8"
    )
    candidate_source = (
        application_root / "data_interpretation_candidate.py"
    ).read_text(encoding="utf-8")
    eeglab_source = (application_root / "eeglab_set_preflight.py").read_text(
        encoding="utf-8"
    )

    for forbidden in ("os.scandir(", ".rglob(", ".glob(", ".iterdir("):
        assert forbidden not in catalog_source
        assert forbidden not in montage_source
        for bids_module in application_root.glob("bids_*.py"):
            assert forbidden not in bids_module.read_text(encoding="utf-8")
    assert "def _selected_bids_subject_files(" not in scan_source
    for dependency_source in (candidate_source, eeglab_source):
        assert "current_bids_dataset_index_for_path" in dependency_source
        assert "indexed_file_in_recording_directory" in dependency_source
        ownership_guard = "if bids_index is not None and bids_index.contains_recording("
        assert dependency_source.index(ownership_guard) < dependency_source.index(
            ".iterdir("
        )
    for dataset_id in (
        "BNCI2014_001",
        "PhysionetMI",
        "Lee2021Mobile_ERP",
        "BNCI2014_009",
        "Nakanishi2015",
        "Ofner2017",
        "Ma2020",
        "ErpCore2021_P3",
        "Wang2016",
        "Chen2017SingleFlicker",
        "Thielen2021",
        "Hinss2021",
        "MAMEM1",
        "GuttmannFlury2025_SSVEP",
        "Zhou2020",
    ):
        assert dataset_id not in "\n".join(
            (index_source, catalog_source, scan_source, montage_source)
        )
