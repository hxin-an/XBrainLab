from pathlib import Path

from XBrainLab.backend.application.data_interpretation_candidate import (
    build_interpretation_candidate,
)
from XBrainLab.backend.application.data_interpretation_scan import (
    ScanResult,
    scan_source_path,
)


def test_scan_source_path_collects_bids_files_labels_and_metadata(tmp_path: Path):
    (tmp_path / "dataset_description.json").write_text("{}", encoding="utf-8")
    eeg_file = (
        tmp_path / "sub-01" / "ses-01" / "eeg" / "sub-01_ses-01_task-mi_run-1_raw.fif"
    )
    events_file = (
        tmp_path
        / "sub-01"
        / "ses-01"
        / "eeg"
        / "sub-01_ses-01_task-mi_run-1_events.tsv"
    )
    channels_file = (
        tmp_path
        / "sub-01"
        / "ses-01"
        / "eeg"
        / "sub-01_ses-01_task-mi_run-1_channels.tsv"
    )
    eeg_file.parent.mkdir(parents=True)
    (tmp_path / "participants.tsv").write_text(
        "participant_id\nsub-01\n",
        encoding="utf-8",
    )
    eeg_file.write_text("", encoding="utf-8")
    events_file.write_text("onset\tduration\ttrial_type\n", encoding="utf-8")
    channels_file.write_text("name\tstatus\nC3\tgood\n", encoding="utf-8")

    scan = scan_source_path(scan_id="scan-1", source_path=str(tmp_path))

    assert isinstance(scan, ScanResult)
    assert scan.source_kind == "bids"
    assert scan.eeg_files == [str(eeg_file)]
    assert scan.label_carriers == [str(events_file)]
    assert scan.metadata[0].subject.value == "01"
    assert scan.bids["is_bids"] is True
    assert scan.bids["events_files"] == [str(events_file)]
    assert scan.bids["channels_files"] == [str(channels_file)]
    assert scan.bids["participants_file"] == str(tmp_path / "participants.tsv")


def test_scan_regular_folder_with_sub_prefixed_file_is_not_bids(tmp_path: Path):
    eeg_file = tmp_path / "sub-01_task-mi_raw.fif"
    eeg_file.write_bytes(b"not loaded during scan")

    scan = scan_source_path(scan_id="scan-1", source_path=str(tmp_path))

    assert scan.source_kind == "folder"
    assert scan.bids["is_bids"] is False
    assert scan.eeg_files == [str(eeg_file.resolve())]
    assert not any(
        "BIDS-like source has no events.tsv" in item for item in scan.warnings
    )


def test_scan_regular_folder_skips_nested_bids_dataset(tmp_path: Path):
    first_gdf = tmp_path / "A01T.gdf"
    second_gdf = tmp_path / "A02T.gdf"
    nested_bids = tmp_path / "bids"
    nested_eeg = (
        nested_bids / "sub-01" / "ses-01" / "eeg" / "sub-01_ses-01_task-rest_eeg.vhdr"
    )
    nested_events = (
        nested_bids / "sub-01" / "ses-01" / "eeg" / "sub-01_ses-01_task-rest_events.tsv"
    )
    first_gdf.write_bytes(b"not loaded during scan")
    second_gdf.write_bytes(b"not loaded during scan")
    nested_eeg.parent.mkdir(parents=True)
    (nested_bids / "dataset_description.json").write_text("{}", encoding="utf-8")
    nested_eeg.write_text("", encoding="utf-8")
    nested_events.write_text("onset\tduration\ttrial_type\n", encoding="utf-8")

    scan = scan_source_path(
        scan_id="scan-1",
        source_path=str(tmp_path),
        source_hint="folder",
    )

    assert scan.source_kind == "folder"
    assert scan.eeg_files == [str(first_gdf.resolve()), str(second_gdf.resolve())]
    assert str(nested_eeg.resolve()) not in scan.eeg_files
    assert str(nested_events.resolve()) not in scan.label_carriers
    assert any("Nested BIDS folder was skipped" in warning for warning in scan.warnings)


def test_scan_source_path_blocks_stream_export_without_selectable_eeg(tmp_path: Path):
    xdf_file = tmp_path / "session.xdf"
    xdf_file.write_text("", encoding="utf-8")

    scan = scan_source_path(scan_id="scan-1", source_path=str(tmp_path))

    assert scan.eeg_files == []
    assert scan.source_kind == "folder"
    assert len(scan.blocked_reasons) == 1
    assert "XDF / LSL stream selection is not available" in scan.blocked_reasons[0]


def test_scan_source_path_respects_explicit_file_hint(tmp_path: Path):
    eeg_file = tmp_path / "subject.fif"
    eeg_file.write_text("", encoding="utf-8")

    scan = scan_source_path(
        scan_id="scan-1",
        source_path=str(eeg_file),
        source_hint="file",
    )

    assert scan.source_kind == "file"
    assert scan.source_path == str(eeg_file.resolve())
    assert scan.eeg_files == [str(eeg_file.resolve())]


def test_scan_source_path_for_single_eeg_file_does_not_select_siblings(
    tmp_path: Path,
) -> None:
    selected_eeg = tmp_path / "selected.fif"
    sibling_eeg = tmp_path / "sibling.fif"
    selected_eeg.write_bytes(b"not loaded during scan")
    sibling_eeg.write_bytes(b"not part of explicit file scan")

    scan = scan_source_path(scan_id="scan-1", source_path=str(selected_eeg))
    candidate = build_interpretation_candidate(
        candidate_id="candidate-1",
        scan=scan,
        choices={},
    )

    assert scan.source_kind == "file"
    assert scan.source_path == str(selected_eeg.resolve())
    assert scan.eeg_files == [str(selected_eeg.resolve())]
    assert str(sibling_eeg.resolve()) not in scan.eeg_files
    assert candidate.selected_eeg_files == [str(selected_eeg.resolve())]


def test_scan_source_path_for_single_eeg_file_detects_same_stem_label_carriers(
    tmp_path: Path,
) -> None:
    selected_eeg = tmp_path / "A01T.gdf"
    sibling_eeg = tmp_path / "A02T.gdf"
    matching_label = tmp_path / "A01T.mat"
    sibling_label = tmp_path / "A02T.mat"
    selected_eeg.write_bytes(b"not loaded during scan")
    sibling_eeg.write_bytes(b"not part of explicit file scan")
    matching_label.write_bytes(b"label")
    sibling_label.write_bytes(b"label")

    scan = scan_source_path(scan_id="scan-1", source_path=str(selected_eeg))

    assert scan.source_kind == "file"
    assert scan.eeg_files == [str(selected_eeg.resolve())]
    assert str(sibling_eeg.resolve()) not in scan.eeg_files
    assert scan.label_carriers == [str(matching_label.resolve())]
    assert str(sibling_label.resolve()) not in scan.label_carriers


def test_scan_source_path_for_single_eeg_file_detects_label_subfolder(
    tmp_path: Path,
) -> None:
    selected_eeg = tmp_path / "A01T.gdf"
    labels_dir = tmp_path / "label"
    labels_dir.mkdir()
    matching_label = labels_dir / "A01T.mat"
    sibling_label = labels_dir / "A02T.mat"
    selected_eeg.write_bytes(b"not loaded during scan")
    matching_label.write_bytes(b"label")
    sibling_label.write_bytes(b"label")

    scan = scan_source_path(scan_id="scan-1", source_path=str(selected_eeg))

    assert scan.source_kind == "file"
    assert scan.eeg_files == [str(selected_eeg.resolve())]
    assert scan.label_carriers == [str(matching_label.resolve())]
    assert str(sibling_label.resolve()) not in scan.label_carriers


def test_scan_source_path_merges_external_label_sources(tmp_path: Path):
    eeg_dir = tmp_path / "eeg"
    label_dir = tmp_path / "labels"
    eeg_dir.mkdir()
    label_dir.mkdir()
    eeg_file = eeg_dir / "sub-01_task-mi_raw.fif"
    nearby_events = eeg_dir / "sub-01_task-mi_events.tsv"
    external_events = label_dir / "sub-01_task-mi_labels.tsv"
    eeg_file.write_bytes(b"not loaded during scan")
    nearby_events.write_text("onset\ttrial_type\n0.0\tleft\n", encoding="utf-8")
    external_events.write_text("onset\ttrial_type\n0.0\tright\n", encoding="utf-8")

    scan = scan_source_path(
        scan_id="scan-1",
        source_path=str(eeg_dir),
        label_sources=[str(label_dir)],
    )

    assert scan.eeg_files == [str(eeg_file.resolve())]
    assert scan.label_sources == [str(label_dir.resolve())]
    assert scan.label_carriers == [
        str(nearby_events.resolve()),
        str(external_events.resolve()),
    ]
    assert scan.label_carrier_sources[str(nearby_events.resolve())] == "auto"
    assert scan.label_carrier_sources[str(external_events.resolve())] == (
        str(label_dir.resolve())
    )


def test_scan_source_path_skips_symbolic_links(tmp_path: Path):
    eeg_file = tmp_path / "A01T.gdf"
    eeg_file.write_bytes(b"not loaded during scan")
    link_path = tmp_path / "linked.gdf"
    try:
        link_path.symlink_to(eeg_file)
    except OSError:
        return

    scan = scan_source_path(scan_id="scan-1", source_path=str(tmp_path))

    assert scan.eeg_files == [str(eeg_file.resolve())]
    assert any("Skipped symbolic link" in warning for warning in scan.warnings)


def test_scan_source_path_warns_when_folder_depth_budget_is_reached(tmp_path: Path):
    current = tmp_path
    for index in range(10):
        current = current / f"level-{index}"
        current.mkdir()
    deep_eeg = current / "A01T.gdf"
    deep_eeg.write_bytes(b"not loaded during scan")

    scan = scan_source_path(scan_id="scan-1", source_path=str(tmp_path))

    assert str(deep_eeg.resolve()) not in scan.eeg_files
    assert any("deeper than" in warning for warning in scan.warnings)
