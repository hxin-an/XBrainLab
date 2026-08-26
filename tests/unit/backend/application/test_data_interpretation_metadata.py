from pathlib import Path

import pytest

from XBrainLab.backend.application.data_interpretation_metadata import (
    DATASET_DESCRIPTION_MAX_BYTES,
    FileMetadataResolution,
    MetadataFieldResolution,
    bids_summary,
    file_metadata_from_dict,
    metadata_for_file,
)


def test_metadata_for_bids_file_resolves_entities(tmp_path: Path):
    eeg_file = (
        tmp_path / "sub-01" / "ses-02" / "eeg" / "sub-01_ses-02_task-mi_run-3_raw.fif"
    )
    eeg_file.parent.mkdir(parents=True)
    eeg_file.write_text("", encoding="utf-8")

    metadata = metadata_for_file(eeg_file, tmp_path, "bids")

    assert isinstance(metadata, FileMetadataResolution)
    assert metadata.subject.value == "01"
    assert metadata.subject.source == "bids_entity"
    assert metadata.subject.decision == "safe"
    assert metadata.session.value == "02"
    assert metadata.task.value == "mi"
    assert metadata.run.value == "3"


def test_metadata_for_filename_rule_requires_confirmation(tmp_path: Path):
    eeg_file = tmp_path / "subject_07_session_A_task_left_run_2.fif"
    eeg_file.write_text("", encoding="utf-8")

    metadata = metadata_for_file(eeg_file, tmp_path, "file")

    assert metadata.subject.value == "07"
    assert metadata.subject.source == "filename_rule"
    assert metadata.subject.decision == "needs_confirmation"
    assert metadata.session.value == "A"
    assert metadata.run.value == "2"


def test_bids_summary_collects_entities_and_dataset_description(tmp_path: Path):
    (tmp_path / "dataset_description.json").write_text("{}", encoding="utf-8")
    (tmp_path / "participants.tsv").write_text(
        "\ufeffparticipant_id\tage\tsex\nsub-01\t29\tF\n",
        encoding="utf-8",
    )
    eeg_files = [
        str(
            tmp_path
            / "sub-01"
            / "ses-01"
            / "eeg"
            / "sub-01_ses-01_task-mi_run-1_raw.fif"
        ),
        str(
            tmp_path
            / "sub-02"
            / "ses-01"
            / "eeg"
            / "sub-02_ses-01_task-mi_run-2_raw.fif"
        ),
    ]
    label_carriers = [str(tmp_path / "sub-01" / "eeg" / "sub-01_task-mi_events.tsv")]

    summary = bids_summary(tmp_path, "bids", eeg_files, label_carriers)

    assert summary["is_bids"] is True
    assert summary["subjects"] == ["01", "02"]
    assert summary["sessions"] == ["01"]
    assert summary["tasks"] == ["mi"]
    assert summary["runs"] == ["1", "2"]
    assert summary["events_files"] == label_carriers
    assert summary["dataset_description"] == str(tmp_path / "dataset_description.json")
    assert summary["participants"] == [
        {"participant_id": "sub-01", "age": "29", "sex": "F"}
    ]


def test_bids_summary_bounds_dataset_description_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    description = tmp_path / "dataset_description.json"
    description.write_text("{}", encoding="utf-8")
    with description.open("ab") as handle:
        handle.truncate(DATASET_DESCRIPTION_MAX_BYTES + 1)
    original_read_text = Path.read_text

    def _guarded_read_text(path: Path, *args, **kwargs):
        if path == description:
            pytest.fail("dataset_description.json used unbounded read_text")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _guarded_read_text)

    summary = bids_summary(tmp_path, "bids", [], [])

    assert summary["dataset"] == {}


def test_bids_summary_rejects_metadata_symlinks_outside_scan_root(
    tmp_path: Path,
) -> None:
    selected_root = tmp_path / "selected"
    eeg_file = selected_root / "sub-01" / "eeg" / "sub-01_task-mi_eeg.fif"
    eeg_file.parent.mkdir(parents=True)
    eeg_file.write_bytes(b"header only")
    outside_root = tmp_path / "outside"
    outside_root.mkdir()
    outside_description = outside_root / "dataset_description.json"
    outside_participants = outside_root / "participants.tsv"
    outside_channels = outside_root / "sub-01_task-mi_channels.tsv"
    outside_description.write_text(
        '{"Name": "outside", "BIDSVersion": "1.11.1"}',
        encoding="utf-8",
    )
    outside_participants.write_text("participant_id\nsub-99\n", encoding="utf-8")
    outside_channels.write_text("name\tstatus\nC3\tbad\n", encoding="utf-8")
    (selected_root / "dataset_description.json").symlink_to(outside_description)
    (selected_root / "participants.tsv").symlink_to(outside_participants)
    (eeg_file.parent / "sub-01_task-mi_channels.tsv").symlink_to(outside_channels)

    summary = bids_summary(selected_root, "bids", [str(eeg_file)], [])

    assert summary["dataset_description"] is None
    assert summary["dataset"] == {}
    assert summary["participants_file"] is None
    assert summary["participants"] == []
    assert summary["channels_files"] == []
    assert summary["channel_status_summary"]["total"] == 0


def test_file_metadata_from_dict_round_trips_minimal_payload():
    payload = {
        "file": "sample.fif",
        "subject": {"field": "subject", "value": "S01"},
        "session": {"field": "session", "value": "baseline"},
    }

    metadata = file_metadata_from_dict(payload)

    assert metadata.file == "sample.fif"
    assert isinstance(metadata.subject, MetadataFieldResolution)
    assert metadata.subject.value == "S01"
    assert metadata.session.value == "baseline"
    assert metadata.task.value is None
    assert metadata.run.field == "run"
