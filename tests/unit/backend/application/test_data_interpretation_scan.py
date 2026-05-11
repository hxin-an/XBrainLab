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
        tmp_path / "sub-01" / "ses-01" / "eeg" / "sub-01_ses-01_task-mi_events.tsv"
    )
    eeg_file.parent.mkdir(parents=True)
    eeg_file.write_text("", encoding="utf-8")
    events_file.write_text("onset\tduration\ttrial_type\n", encoding="utf-8")

    scan = scan_source_path(scan_id="scan-1", source_path=str(tmp_path))

    assert isinstance(scan, ScanResult)
    assert scan.source_kind == "bids"
    assert scan.eeg_files == [str(eeg_file)]
    assert scan.label_carriers == [str(events_file)]
    assert scan.metadata[0].subject.value == "01"
    assert scan.bids["is_bids"] is True
    assert scan.bids["events_files"] == [str(events_file)]


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
