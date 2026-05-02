from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from XBrainLab.backend.dataset.split_audit import (
    audit_dataset_splits,
    build_split_artifact,
    split_indices,
    write_split_artifact,
)


class _EpochData:
    subject = np.array([0, 0, 1, 1, 2, 2])
    session = np.array([0, 0, 0, 1, 0, 1])
    label = np.array([0, 1, 0, 1, 0, 1])

    def get_subject_list_by_mask(self, mask):
        return self.subject[mask]

    def get_session_list_by_mask(self, mask):
        return self.session[mask]

    def get_label_list_by_mask(self, mask):
        return self.label[mask]


def _dataset(train, val, test, name="split_0"):
    train_mask = np.array(train, dtype=bool)
    val_mask = np.array(val, dtype=bool)
    test_mask = np.array(test, dtype=bool)
    return SimpleNamespace(
        train_mask=train_mask,
        val_mask=val_mask,
        test_mask=test_mask,
        is_selected=True,
        get_name=lambda: name,
        get_train_len=lambda: int(train_mask.sum()),
        get_val_len=lambda: int(val_mask.sum()),
        get_test_len=lambda: int(test_mask.sum()),
        get_epoch_data=lambda: _EpochData(),
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


def test_audit_dataset_splits_detects_subject_wise_leakage():
    dataset = _dataset(
        [True, False, False, False, False, False],
        [False, True, False, False, False, False],
        [False, False, True, False, False, False],
    )

    result = audit_dataset_splits([dataset], protocol="subject-wise")

    assert result.ok is False
    assert any("subject groups overlap" in issue.message for issue in result.issues)


def test_audit_dataset_splits_detects_session_wise_leakage_by_subject_session_pair():
    dataset = _dataset(
        [True, False, False, False, False, False],
        [False, False, False, False, False, False],
        [False, True, False, False, False, False],
    )

    result = audit_dataset_splits([dataset], protocol="session-wise")

    assert result.ok is False
    assert any("session groups overlap" in issue.message for issue in result.issues)


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
