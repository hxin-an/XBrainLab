from pathlib import Path

from XBrainLab.backend.application.data_interpretation_metadata import (
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
