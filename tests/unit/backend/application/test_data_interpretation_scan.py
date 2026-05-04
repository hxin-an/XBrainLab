from pathlib import Path

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
