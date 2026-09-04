from __future__ import annotations

import json
import re
from dataclasses import replace
from types import SimpleNamespace
from typing import cast

import mne
import numpy as np
import pytest

import XBrainLab.backend.dataset.epochs as epochs_module
from XBrainLab.backend.dataset import (
    Dataset,
    DataSplittingConfig,
    Epochs,
    EpochWindowProvenance,
    TrainingType,
)
from XBrainLab.backend.dataset.split_audit import (
    audit_dataset_splits,
    build_split_artifact,
    split_indices,
    write_split_artifact,
)
from XBrainLab.backend.load_data import Raw


class _EpochData:
    subject = np.array([0, 0, 1, 1, 2, 2])
    session = np.array([0, 0, 0, 1, 0, 1])
    label = np.array([0, 1, 0, 1, 0, 1])
    trial_group = np.array([0, 0, 1, 2, 3, 4])

    def get_subject_list_by_mask(self, mask):
        return self.subject[mask]

    def get_session_list_by_mask(self, mask):
        return self.session[mask]

    def get_label_list_by_mask(self, mask):
        return self.label[mask]

    def get_trial_group_list(self):
        return self.trial_group


def _dataset(train, val, test, name="split_0") -> Dataset:
    train_mask = np.array(train, dtype=bool)
    val_mask = np.array(val, dtype=bool)
    test_mask = np.array(test, dtype=bool)
    return cast(
        Dataset,
        SimpleNamespace(
            train_mask=train_mask,
            val_mask=val_mask,
            test_mask=test_mask,
            is_selected=True,
            get_name=lambda: name,
            get_train_len=lambda: int(train_mask.sum()),
            get_val_len=lambda: int(val_mask.sum()),
            get_test_len=lambda: int(test_mask.sum()),
            get_epoch_data=lambda: _EpochData(),
        ),
    )


def _recording_epochs(filepath: str, event_samples: list[int]) -> Raw:
    sfreq = 100.0
    info = mne.create_info(["Cz"], sfreq=sfreq, ch_types="eeg")
    raw = mne.io.RawArray(np.zeros((1, 1_000)), info, verbose=False)
    event_values = (np.arange(len(event_samples), dtype=int) % 2) + 1
    events = np.column_stack(
        (
            np.asarray(event_samples),
            np.zeros(len(event_samples), dtype=int),
            event_values,
        ),
    )
    event_id = {
        f"class-{value}": int(value) for value in sorted(set(event_values.tolist()))
    }
    mne_epochs = mne.Epochs(
        raw,
        events,
        event_id=event_id,
        tmin=0.0,
        tmax=0.99,
        baseline=None,
        preload=True,
        verbose=False,
    )
    wrapped = Raw(filepath, mne_epochs)
    epochs_module.mark_xbrainlab_raw_event_source_epochs(wrapped)
    return wrapped


def _split_epoch_data(
    epoch_data: Epochs,
    *,
    train: list[int],
    validation: list[int],
    test: list[int],
) -> Dataset:
    config = DataSplittingConfig(TrainingType.FULL, False, [], [])
    dataset = Dataset(epoch_data, config)
    dataset.set_name("recording-windows")
    dataset.train_mask[train] = True
    dataset.val_mask[validation] = True
    dataset.test_mask[test] = True
    dataset.remaining_mask[:] = False
    return dataset


def _recording_window_dataset(
    event_samples: list[int],
    *,
    filepath: str = "recordings/source-a.fif",
    train: list[int] | None = None,
    validation: list[int] | None = None,
    test: list[int] | None = None,
) -> Dataset:
    epoch_data = Epochs(
        [_recording_epochs(filepath, event_samples)],
    )
    return _split_epoch_data(
        epoch_data,
        train=train or [0],
        validation=validation or [1],
        test=test or [2],
    )


def test_split_indices_are_json_ready():
    dataset = _dataset(
        [True, False, True],
        [False, True, False],
        [False, False, False],
    )

    assert split_indices(dataset) == {
        "train": [0, 2],
        "validation": [1],
        "test": [],
    }


def test_audit_dataset_splits_detects_overlap():
    dataset = _dataset(
        [True, True, False],
        [False, True, False],
        [False, False, True],
    )

    result = audit_dataset_splits([dataset])

    assert result.ok is False
    assert any("data leakage" in issue.message for issue in result.issues)
    assert result.issues[0].indices == [1]


def test_audit_dataset_splits_rejects_one_class_supervised_data() -> None:
    labels = np.zeros(6, dtype=int)
    epoch_data = SimpleNamespace(
        get_subject_list_by_mask=lambda mask: np.arange(6)[mask],
        get_session_list_by_mask=lambda mask: np.zeros(6, dtype=int)[mask],
        get_label_list_by_mask=lambda mask: labels[mask],
    )
    train_mask = np.array([True, True, False, False, False, False])
    val_mask = np.array([False, False, True, True, False, False])
    test_mask = np.array([False, False, False, False, True, True])
    dataset = cast(
        Dataset,
        SimpleNamespace(
            train_mask=train_mask,
            val_mask=val_mask,
            test_mask=test_mask,
            is_selected=True,
            get_name=lambda: "one-class",
            get_train_len=lambda: 2,
            get_val_len=lambda: 2,
            get_test_len=lambda: 2,
            get_epoch_data=lambda: epoch_data,
        ),
    )

    result = audit_dataset_splits([dataset])

    issue = next(
        issue
        for issue in result.issues
        if issue.details.get("kind") == "insufficient_usable_classes"
    )
    assert result.ok is False
    assert issue.severity == "error"
    assert issue.details["usable_class_labels"] == [0]
    assert "at least 2" in issue.message
    assert "usable trials" in issue.message


def test_trial_wise_audit_rejects_cross_split_overlapping_epoch_windows():
    dataset = _recording_window_dataset([100, 150, 400])

    result = audit_dataset_splits([dataset], protocol="trial-wise")

    assert result.ok is False
    issue = next(
        issue for issue in result.issues if "epoch windows overlap" in issue.message
    )
    assert issue.indices == [0, 1]


def test_overlap_diagnostics_and_artifact_do_not_publish_source_paths(tmp_path):
    source_path = tmp_path / "participant-007-private-source.fif"
    dataset = _recording_window_dataset(
        [100, 150, 400],
        filepath=str(source_path),
    )

    payload = build_split_artifact([dataset], protocol="trial-wise")
    serialized = json.dumps(payload, sort_keys=True)

    assert str(source_path) not in serialized
    assert source_path.name not in serialized
    issue = next(
        issue
        for issue in payload["audit"]["issues"]
        if issue["details"].get("kind") == "epoch_window_overlap"
    )
    source_id = issue["details"]["overlaps"][0]["source_recording_id"]
    assert re.fullmatch(r"path-sha256:[0-9a-f]{64}", source_id)
    evidence = payload["datasets"][0]["epoch_window_provenance"]
    assert evidence["records"][0]["source_recording_id"] == source_id
    assert evidence["source_summaries"][0]["source_recording_id"] == source_id


def test_artifact_drops_legacy_nonopaque_source_paths(tmp_path):
    source_path = tmp_path / "participant-legacy-private-source.fif"
    dataset = _recording_window_dataset([100, 250, 400])
    epoch_data = dataset.get_epoch_data()
    epoch_data.epoch_window_provenance = tuple(
        replace(item, source_recording_id=str(source_path))
        for item in epoch_data.get_epoch_window_provenance()
    )

    payload = build_split_artifact([dataset], protocol="trial-wise")
    serialized = json.dumps(payload, sort_keys=True)
    evidence = payload["datasets"][0]["epoch_window_provenance"]

    assert str(source_path) not in serialized
    assert source_path.name not in serialized
    assert evidence["record_count"] == 0
    assert evidence["missing_count"] == 3
    assert evidence["records"] == []
    warning = next(
        issue
        for issue in payload["audit"]["issues"]
        if issue["details"].get("kind") == "missing_epoch_window_provenance"
    )
    assert warning["details"]["missing_count"] == 3


@pytest.mark.parametrize(
    ("left_split", "right_split", "train", "validation", "test"),
    [
        ("train", "test", [0], [2], [1]),
        ("validation", "test", [2], [0], [1]),
    ],
)
def test_trial_wise_audit_checks_every_cross_split_epoch_window_pair(
    left_split,
    right_split,
    train,
    validation,
    test,
):
    dataset = _recording_window_dataset(
        [100, 150, 400],
        train=train,
        validation=validation,
        test=test,
    )

    result = audit_dataset_splits([dataset], protocol="trial-wise")

    issue = next(
        issue
        for issue in result.issues
        if issue.details.get("kind") == "epoch_window_overlap"
    )
    assert result.ok is False
    assert issue.indices == [0, 1]
    assert issue.details["left_split"] == left_split
    assert issue.details["right_split"] == right_split


def test_trial_wise_audit_accepts_non_overlapping_epoch_windows():
    dataset = _recording_window_dataset(
        [100, 250, 400, 550, 700, 850],
        train=[0, 1],
        validation=[2, 3],
        test=[4, 5],
    )

    result = audit_dataset_splits([dataset], protocol="trial-wise")

    assert result.ok is True
    assert not any(
        issue.details.get("kind") == "epoch_window_overlap" for issue in result.issues
    )


def test_trial_wise_audit_treats_adjacent_half_open_windows_as_disjoint():
    dataset = _recording_window_dataset(
        [100, 200, 400, 500, 700, 800],
        train=[0, 1],
        validation=[2, 3],
        test=[4, 5],
    )

    result = audit_dataset_splits([dataset], protocol="trial-wise")

    assert result.ok is True


def test_trial_wise_audit_ignores_overlaps_within_one_split():
    dataset = _recording_window_dataset(
        [100, 150, 400, 600],
        train=[0, 1],
        validation=[2],
        test=[3],
    )

    result = audit_dataset_splits([dataset], protocol="trial-wise")

    assert result.ok is True


def test_trial_wise_audit_does_not_match_sample_ranges_across_recordings():
    epoch_data = Epochs(
        [
            _recording_epochs("recordings/source-a.fif", [100, 300, 500, 700]),
            _recording_epochs("recordings/source-b.fif", [100, 300]),
        ],
    )
    dataset = _split_epoch_data(
        epoch_data,
        train=[0, 1],
        validation=[4, 5],
        test=[2, 3],
    )

    result = audit_dataset_splits([dataset], protocol="trial-wise")

    assert result.ok is True


def test_trial_wise_audit_matches_copied_paths_by_reviewed_content_identity():
    original = _recording_epochs(
        "recordings/source-a.fif",
        [100, 400],
    )
    copied = _recording_epochs(
        "copied/source-a-copy.fif",
        [100, 400],
    )
    reviewed_identity = {
        "algorithm": "sha256",
        "sha256": "c" * 64,
        "file_bytes": 4_096,
    }
    original.set_source_content_identity(reviewed_identity)
    copied.set_source_content_identity(reviewed_identity)
    epochs_module.mark_xbrainlab_raw_event_source_epochs(original)
    epochs_module.mark_xbrainlab_raw_event_source_epochs(copied)
    dataset = _split_epoch_data(
        Epochs([original, copied]),
        train=[0],
        validation=[2],
        test=[1, 3],
    )

    result = audit_dataset_splits([dataset], protocol="trial-wise")

    issue = next(
        item
        for item in result.issues
        if item.details.get("kind") == "epoch_window_overlap"
    )
    assert result.ok is False
    assert issue.indices == [0, 2]
    assert issue.details["overlaps"][0]["source_recording_id"] == (
        f"content-sha256:{'c' * 64}"
    )


def test_trial_wise_audit_blocks_when_epoch_window_provenance_is_missing():
    dataset = _dataset(
        [True, True, False, False, False, False],
        [False, False, True, True, False, False],
        [False, False, False, False, True, True],
    )

    result = audit_dataset_splits([dataset], protocol="trial-wise")

    issue = next(
        issue
        for issue in result.issues
        if issue.details.get("kind") == "missing_epoch_window_provenance"
    )
    assert result.ok is False
    assert issue.severity == "error"
    assert issue.indices == [0, 1, 2, 3, 4, 5]
    assert issue.details["missing_count"] == 6
    assert issue.details["protocol"] == "trial-wise"


def test_trial_wise_audit_blocks_unverified_epoch_array_coordinates():
    info = mne.create_info(["Cz"], sfreq=100.0, ch_types="eeg")
    events = np.column_stack(
        (
            np.asarray([100, 150, 400, 450, 700, 750]),
            np.zeros(6, dtype=int),
            np.asarray([1, 2, 1, 2, 1, 2]),
        ),
    )
    mne_epochs = mne.EpochsArray(
        np.zeros((6, 1, 100)),
        info,
        events=events,
        event_id={"class-1": 1, "class-2": 2},
        verbose=False,
    )
    dataset = _split_epoch_data(
        Epochs([Raw("recordings/legacy-array.fif", mne_epochs)]),
        train=[0, 1],
        validation=[2, 3],
        test=[4, 5],
    )

    result = audit_dataset_splits([dataset], protocol="trial-wise")

    issue = next(
        issue
        for issue in result.issues
        if issue.details.get("kind") == "missing_epoch_window_provenance"
    )
    assert result.ok is False
    assert issue.severity == "error"
    assert issue.details["missing_count"] == 0
    assert issue.details["unverified_count"] == 6
    assert issue.details["unavailable_count"] == 6
    evidence = build_split_artifact([dataset])["datasets"][0]["epoch_window_provenance"]
    assert evidence["status"] == "unverified"
    assert evidence["record_count"] == 6
    assert evidence["verified_count"] == 0
    assert evidence["unverified_count"] == 6


def test_subject_wise_audit_keeps_unknown_coordinates_non_blocking() -> None:
    dataset = _dataset(
        [True, True, False, False, False, False],
        [False, False, True, True, False, False],
        [False, False, False, False, True, True],
    )

    result = audit_dataset_splits([dataset], protocol="subject-wise")

    issue = next(
        issue
        for issue in result.issues
        if issue.details.get("kind") == "missing_epoch_window_provenance"
    )
    assert result.ok is True
    assert issue.severity == "warning"
    assert issue.details["protocol"] == "subject-wise"


def test_split_artifact_contains_compact_epoch_window_evidence():
    dataset = _recording_window_dataset([100, 250, 400])

    payload = build_split_artifact([dataset], protocol="trial-wise")

    evidence = payload["datasets"][0]["epoch_window_provenance"]
    assert evidence["status"] == "complete"
    assert evidence["interval_semantics"] == "half-open [start, end) samples"
    assert evidence["available_count"] == 3
    assert evidence["missing_count"] == 0
    assert evidence["records"][0]["epoch_index"] == 0
    assert evidence["records"][0]["event_sample"] == 100
    assert evidence["records"][0]["window_start_sample"] == 100
    assert evidence["records"][0]["window_end_sample_exclusive"] == 200
    assert "data" not in evidence
    assert "data" not in evidence["records"][0]


def test_split_artifact_caps_large_epoch_provenance_records():
    epoch_count = 5_000
    provenance = tuple(
        EpochWindowProvenance(
            source_recording_id=f"path-sha256:{'a' * 64}",
            event_sample=index * 100,
            window_start_sample=index * 100,
            window_end_sample_exclusive=(index + 1) * 100,
            source_sfreq=100.0,
            epoch_sfreq=100.0,
            tmin_seconds=0.0,
            tmax_seconds=0.99,
            source_coordinates_verified=True,
        )
        for index in range(epoch_count)
    )
    labels = np.arange(epoch_count) % 2
    epoch_data = SimpleNamespace(
        get_subject_list_by_mask=lambda mask: np.zeros(epoch_count, dtype=int)[mask],
        get_session_list_by_mask=lambda mask: np.zeros(epoch_count, dtype=int)[mask],
        get_label_list_by_mask=lambda mask: labels[mask],
        get_epoch_window_provenance=lambda: provenance,
        get_trial_group_list=lambda: np.arange(epoch_count),
        get_trial_selection_evidence=list,
    )
    train_mask = np.zeros(epoch_count, dtype=bool)
    val_mask = np.zeros(epoch_count, dtype=bool)
    test_mask = np.zeros(epoch_count, dtype=bool)
    train_mask[:3_000] = True
    val_mask[3_000:4_000] = True
    test_mask[4_000:] = True
    dataset = SimpleNamespace(
        train_mask=train_mask,
        val_mask=val_mask,
        test_mask=test_mask,
        is_selected=True,
        get_name=lambda: "large-split",
        get_train_len=lambda: int(train_mask.sum()),
        get_val_len=lambda: int(val_mask.sum()),
        get_test_len=lambda: int(test_mask.sum()),
        get_epoch_data=lambda: epoch_data,
    )

    evidence = build_split_artifact([cast(Dataset, dataset)])["datasets"][0][
        "epoch_window_provenance"
    ]

    assert evidence["record_count"] == epoch_count
    assert evidence["records_emitted"] <= 100
    assert len(evidence["records"]) == evidence["records_emitted"]
    assert evidence["records_truncated"] is True
    assert evidence["records_sha256"]


def test_audit_dataset_splits_blocks_missing_class_coverage():
    dataset = _dataset(
        [True, False, False, False, False, False],
        [False, True, False, True, False, False],
        [False, False, True, False, True, False],
    )

    result = audit_dataset_splits([dataset])

    assert result.ok is False
    messages = [issue.message for issue in result.issues]
    assert "train split is missing class label(s) 1." in messages


def test_audit_dataset_splits_detects_subject_wise_leakage():
    dataset = _dataset(
        [True, False, False, False, False, False],
        [False, True, False, False, False, False],
        [False, False, True, False, False, False],
    )

    result = audit_dataset_splits([dataset], protocol="subject-wise")

    assert result.ok is False
    assert any("subject groups overlap" in issue.message for issue in result.issues)


def test_audit_dataset_splits_detects_session_wise_leakage():
    dataset = _dataset(
        [True, False, False, False, False, False],
        [False, False, False, False, False, False],
        [False, True, False, False, False, False],
    )

    result = audit_dataset_splits([dataset], protocol="session-wise")

    assert result.ok is False
    assert any("session groups overlap" in issue.message for issue in result.issues)


def test_audit_dataset_splits_treats_same_named_session_as_global_across_subjects():
    dataset = _dataset(
        [True, False, False, False, False, False],
        [False, False, False, False, False, False],
        [False, False, True, False, False, False],
    )

    result = audit_dataset_splits([dataset], protocol="session-wise")

    assert any("session groups overlap" in issue.message for issue in result.issues)


def test_audit_applies_mixed_protocols_to_their_respective_partition_pairs():
    """Only the validation-trial versus train pair leaks in this fixture."""
    dataset = _dataset(
        [True, False, False, False, False, False],
        [False, True, False, False, False, False],
        [False, False, False, True, False, False],
    )

    result = audit_dataset_splits(
        [dataset],
        protocols={"test": "session-wise", "validation": "trial-wise"},
    )

    assert result.ok is False
    assert any(
        "trial groups overlap between train and validation" in issue.message
        for issue in result.issues
    )
    assert not any("session groups overlap" in issue.message for issue in result.issues)


def test_mixed_session_test_and_trial_validation_blocks_unverified_coordinates():
    """Trial validation needs temporal provenance even when test is session-wise."""
    dataset = _dataset(
        [True, True, False, False, False, False],
        [False, False, True, True, False, False],
        [False, False, False, False, True, True],
    )

    result = audit_dataset_splits(
        [dataset],
        protocol="session-wise",
        protocols={"test": "session-wise", "validation": "trial-wise"},
    )

    issue = next(
        issue
        for issue in result.issues
        if issue.details.get("kind") == "missing_epoch_window_provenance"
    )
    assert result.ok is False
    assert issue.severity == "error"
    assert issue.details["protocol"] == "trial-wise"


def test_mixed_trial_validation_ignores_unavailable_test_only_coordinates():
    """A Session test partition is outside the Trial validation pair."""
    dataset = _recording_window_dataset(
        [100, 250, 400, 550, 700, 850],
        train=[0, 1],
        validation=[2, 3],
        test=[4, 5],
    )
    epoch_data = dataset.get_epoch_data()
    epoch_data.epoch_window_provenance = tuple(
        item if index < 4 else replace(item, source_coordinates_verified=False)
        for index, item in enumerate(epoch_data.get_epoch_window_provenance())
    )

    result = audit_dataset_splits(
        [dataset],
        protocol="session-wise",
        protocols={"test": "session-wise", "validation": "trial-wise"},
    )

    provenance_issues = [
        issue
        for issue in result.issues
        if issue.details.get("kind") == "missing_epoch_window_provenance"
    ]
    assert not any(issue.severity == "error" for issue in provenance_issues)
    assert provenance_issues[0].indices == [4, 5]
    assert provenance_issues[0].details["epoch_count"] == 2
    assert provenance_issues[0].details["available_count"] == 0


def test_epoch_window_audit_ignores_unavailable_epochs_outside_dataset_scope():
    """Individual datasets must not inherit provenance warnings from other rows."""
    dataset = _recording_window_dataset(
        [100, 250, 400, 550, 700, 850],
        train=[0],
        validation=[1],
        test=[2],
    )
    epoch_data = dataset.get_epoch_data()
    epoch_data.epoch_window_provenance = tuple(
        item if index < 3 else replace(item, source_coordinates_verified=False)
        for index, item in enumerate(epoch_data.get_epoch_window_provenance())
    )

    result = audit_dataset_splits([dataset], protocol="session-wise")

    assert not any(
        issue.details.get("kind") == "missing_epoch_window_provenance"
        for issue in result.issues
    )


def test_pair_scoped_trial_protocol_rejects_atomic_group_leakage():
    dataset = _dataset(
        [True, False, False, False, False, False],
        [False, False, False, False, False, False],
        [False, True, False, False, False, False],
    )

    result = audit_dataset_splits(
        [dataset],
        protocols={"test": "trial-wise", "validation": "trial-wise"},
    )

    assert result.ok is False
    assert any(
        "trial groups overlap between train and test" in issue.message
        for issue in result.issues
    )


def test_build_and_write_split_artifact(tmp_path):
    dataset = _dataset(
        [True, True, False, False, False, False],
        [False, False, True, True, False, False],
        [False, False, False, False, True, True],
    )
    artifact_path = tmp_path / "splits.json"

    payload = write_split_artifact(
        [dataset],
        artifact_path,
        seed=7,
        repeat=1,
        protocol="subject-wise",
        extra_config={"split_unit": "subject"},
    )

    assert artifact_path.exists()
    assert payload == build_split_artifact(
        [dataset],
        seed=7,
        repeat=1,
        protocol="subject-wise",
        extra_config={"split_unit": "subject"},
    )
    assert payload["schema_version"] == 1
    assert payload["audit"]["ok"] is True
    assert payload["datasets"][0]["indices"]["test"] == [4, 5]
    assert payload["datasets"][0]["groups"]["train"]["subjects"] == [0]
