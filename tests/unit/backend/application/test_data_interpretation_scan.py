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


def test_scan_source_path_summarizes_bids_eeg_layout_participants_and_channels(
    tmp_path: Path,
):
    (tmp_path / "dataset_description.json").write_text(
        '{"Name":"Motor imagery"}',
        encoding="utf-8",
    )
    (tmp_path / "participants.tsv").write_text(
        "participant_id\tsex\tage\nsub-01\tF\t21\nsub-02\tM\t24\n",
        encoding="utf-8",
    )
    eeg_1 = (
        tmp_path / "sub-01" / "ses-01" / "eeg" / "sub-01_ses-01_task-mi_run-1_eeg.fif"
    )
    eeg_2 = (
        tmp_path / "sub-02" / "ses-01" / "eeg" / "sub-02_ses-01_task-mi_run-1_eeg.fif"
    )
    eeg_1.parent.mkdir(parents=True)
    eeg_2.parent.mkdir(parents=True)
    eeg_1.write_bytes(b"not loaded during scan")
    eeg_2.write_bytes(b"not loaded during scan")
    events = eeg_1.with_name("sub-01_ses-01_task-mi_run-1_events.tsv")
    channels = eeg_1.with_name("sub-01_ses-01_task-mi_run-1_channels.tsv")
    events.write_text("onset\tduration\ttrial_type\tvalue\n", encoding="utf-8")
    channels.write_text(
        "name\ttype\tunits\tstatus\nC3\tEEG\tuV\tgood\nEOG\tEOG\tuV\tbad\n",
        encoding="utf-8",
    )

    scan = scan_source_path(
        scan_id="scan-1",
        source_path=str(tmp_path),
        source_hint="bids",
    )

    assert scan.source_kind == "bids"
    assert scan.bids["root"] == str(tmp_path.resolve())
    assert scan.bids["scan_location"] == str(tmp_path.resolve())
    assert scan.bids["datatypes"] == ["eeg"]
    assert scan.bids["eeg_file_count"] == 2
    assert scan.bids["participant_count"] == 2
    assert scan.bids["participants"][0]["participant_id"] == "sub-01"
    assert scan.bids["channels_files"] == [str(channels.resolve())]
    assert scan.bids["channel_status_summary"]["bad"] == 1
    assert scan.bids["layout"][0]["datatype"] == "eeg"
    assert scan.bids["layout"][0]["events_file"] == str(events.resolve())
    assert scan.bids["layout"][0]["channels_file"] == str(channels.resolve())
    assert scan.label_carriers == [str(events.resolve())]
    assert all("participants.tsv" not in item for item in scan.label_carriers)
    assert all("channels.tsv" not in item for item in scan.label_carriers)
    assert any(
        "channels.tsv marks 1 channel(s) as bad" in item for item in scan.warnings
    )


def test_scan_source_path_bids_scan_location_is_separate_from_root(
    tmp_path: Path,
) -> None:
    bids_root = tmp_path / "bids"
    source_scope = bids_root / "sub-01"
    eeg_file = source_scope / "eeg" / "sub-01_task-mi_run-1_eeg.fif"
    (bids_root / "dataset_description.json").parent.mkdir(parents=True)
    (bids_root / "dataset_description.json").write_text("{}", encoding="utf-8")
    eeg_file.parent.mkdir(parents=True)
    eeg_file.write_bytes(b"not loaded during scan")

    scan = scan_source_path(
        scan_id="scan-1",
        source_path=str(source_scope),
        source_hint="bids",
    )

    assert scan.source_path == str(source_scope.resolve())
    assert scan.bids["root"] == str(bids_root.resolve())
    assert scan.bids["scan_location"] == str(source_scope.resolve())
    assert scan.bids["selected_scope"]["eeg_files"] == [str(eeg_file.resolve())]


def test_scan_source_path_bids_root_summarizes_multiple_subject_sessions_runs(
    tmp_path: Path,
) -> None:
    (tmp_path / "dataset_description.json").write_text("{}", encoding="utf-8")
    eeg_files = [
        (
            tmp_path
            / "sub-01"
            / "ses-01"
            / "eeg"
            / "sub-01_ses-01_task-mi_run-1_eeg.fif"
        ),
        (
            tmp_path
            / "sub-01"
            / "ses-02"
            / "eeg"
            / "sub-01_ses-02_task-rest_run-2_eeg.fif"
        ),
        (
            tmp_path
            / "sub-02"
            / "ses-01"
            / "eeg"
            / "sub-02_ses-01_task-mi_run-1_eeg.fif"
        ),
    ]
    for eeg_file in eeg_files:
        eeg_file.parent.mkdir(parents=True, exist_ok=True)
        eeg_file.write_bytes(b"not loaded during scan")
        eeg_file.with_name(eeg_file.name.replace("_eeg.fif", "_events.tsv")).write_text(
            "onset\tduration\ttrial_type\tvalue\n",
            encoding="utf-8",
        )

    scan = scan_source_path(
        scan_id="scan-1",
        source_path=str(tmp_path),
        source_hint="bids",
    )

    assert scan.bids["subjects"] == ["01", "02"]
    assert scan.bids["sessions"] == ["01", "02"]
    assert scan.bids["tasks"] == ["mi", "rest"]
    assert scan.bids["runs"] == ["1", "2"]
    assert scan.bids["eeg_file_count"] == 3
    assert len(scan.bids["events_files"]) == 3
    assert len(scan.label_carriers) == 3


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


def test_scan_source_path_sub_prefixed_files_do_not_make_folder_bids(
    tmp_path: Path,
) -> None:
    eeg_file = tmp_path / "sub-01_task-mi_run-1_raw.fif"
    label_file = tmp_path / "labels.tsv"
    eeg_file.write_bytes(b"not loaded during scan")
    label_file.write_text("onset\ttrial_type\n0.1\tleft\n", encoding="utf-8")

    scan = scan_source_path(scan_id="scan-1", source_path=str(tmp_path))

    assert scan.source_kind == "folder"
    assert scan.label_carriers == [str(label_file.resolve())]


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


def test_scan_source_path_reports_unsupported_sidecars_with_eeg(tmp_path: Path):
    eeg_file = tmp_path / "subject.fif"
    pickle_file = tmp_path / "labels.pkl"
    log_file = tmp_path / "vendor.log"
    unknown_file = tmp_path / "session.sidecar"
    eeg_file.write_bytes(b"not loaded during scan")
    pickle_file.write_bytes(b"pickle")
    log_file.write_text("proprietary export", encoding="utf-8")
    unknown_file.write_text("unknown sidecar", encoding="utf-8")

    scan = scan_source_path(scan_id="scan-1", source_path=str(tmp_path))
    capabilities = {item["name"]: item for item in scan.format_capabilities}

    assert capabilities["labels.pkl"]["status"] == "blocked"
    assert capabilities["vendor.log"]["status"] == "limited"
    assert capabilities["session.sidecar"]["status"] == "limited"
    assert any("not interpreted by this wizard" in item for item in scan.warnings)
    assert scan.blocked_reasons == []
