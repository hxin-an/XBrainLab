"""Detached dataset-splitting context and preview publication contracts."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Any

import mne
import numpy as np
import pytest

from XBrainLab.backend.application.dataset_split_preview import (
    DatasetSplitContextRequest,
    DatasetSplitPreviewPublisher,
    DatasetSplitPreviewRequest,
    DatasetSplitSpecification,
)
from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.dataset import Dataset, DatasetGenerator, Epochs
from XBrainLab.backend.load_data import Raw


class _EpochData:
    def __init__(self) -> None:
        self.label_map = {"left": 0, "right": 1}
        self.data = list(range(12))

    def get_subject_map(self) -> dict[str, list[int]]:
        return {"S01": list(range(6)), "S02": list(range(6, 12))}

    def get_session_map(self) -> dict[str, list[int]]:
        return {"session-1": list(range(12))}

    def get_data_length(self) -> int:
        return len(self.data)


class _EpochDataWithTrialGroups(_EpochData):
    def __init__(self, trial_groups: object) -> None:
        super().__init__()
        self._trial_groups = trial_groups

    def get_trial_group_list(self) -> object:
        return self._trial_groups


class _DatasetState:
    def __init__(self, epoch_data: Any | None) -> None:
        self.epoch_data = epoch_data
        self.read_count = 0

    def get_epoch_data(self) -> Any | None:
        self.read_count += 1
        return self.epoch_data


class _PreviewDataset:
    def __init__(self, name: str, train: int, val: int, test: int) -> None:
        self._row = ("O", name, train, val, test)

    def get_treeview_row_info(self) -> tuple[str, str, int, int, int]:
        return self._row


class _Generator:
    def __init__(self) -> None:
        self.datasets: list[_PreviewDataset] = []
        self.interrupted = False

    def generate(self) -> None:
        self.datasets.extend(
            [
                _PreviewDataset("Fold_0", 8, 2, 2),
                _PreviewDataset("Fold_1", 8, 2, 2),
            ]
        )

    def set_interrupt(self) -> None:
        self.interrupted = True


def _view(generation: int = 4, *, usable: bool = True) -> SimpleNamespace:
    return SimpleNamespace(generation=generation, usable=usable)


def _specification() -> DatasetSplitSpecification:
    return DatasetSplitSpecification.from_payload(
        {
            "train_type": "Full Data",
            "is_cross_validation": True,
            "val_splitters": [
                {
                    "split_type": "By Trial",
                    "split_unit": "Ratio",
                    "value": "0.2",
                    "is_option": True,
                }
            ],
            "test_splitters": [
                {
                    "split_type": "By Trial",
                    "split_unit": "K Fold",
                    "value": "2",
                    "is_option": True,
                }
            ],
        }
    )


def _real_epoch_data() -> Epochs:
    trial_count = 10
    info = mne.create_info(ch_names=["C3", "C4"], sfreq=20, ch_types="eeg")
    events = np.column_stack(
        (
            np.arange(trial_count, dtype=int) * 20,
            np.zeros(trial_count, dtype=int),
            np.tile([0, 1], trial_count // 2),
        )
    )
    mne_epochs = mne.EpochsArray(
        np.zeros((trial_count, 2, 8)),
        info,
        events=events,
        event_id={"left": 0, "right": 1},
        tmin=0,
        verbose=False,
    )
    raw = Raw("sub-01_ses-01_task-preview-epo.fif", mne_epochs)
    raw.set_subject_name("01")
    raw.set_session_name("01")
    return Epochs([raw])


def _assert_live_split_state_unchanged(
    epoch_data: Epochs,
    original_evidence: list[dict[str, Any]],
    *,
    sequence: int,
    dropped: int,
) -> None:
    assert epoch_data.trial_selection_evidence is original_evidence
    assert epoch_data.trial_selection_evidence == [
        {"source": "live", "details": {"selected": 3}}
    ]
    assert epoch_data.trial_selection_evidence_dropped == dropped
    assert sequence == Dataset.SEQ


class _BlockingDatasetGenerator(DatasetGenerator):
    def __init__(self, *args: Any, started: threading.Event, release: threading.Event):
        super().__init__(*args)
        self._started = started
        self._release = release

    def _populate_pending_datasets(self) -> None:
        self._started.set()
        if not self._release.wait(timeout=1.0):
            raise TimeoutError("Timed out waiting to continue the preview")
        if self.interrupted:
            raise KeyboardInterrupt
        super()._populate_pending_datasets()


def test_context_publication_contains_only_detached_split_choices() -> None:
    dataset = _DatasetState(_EpochData())
    publisher = DatasetSplitPreviewPublisher(
        dataset=dataset,
        generator_factory=lambda _config: _Generator(),
        get_publication=lambda: _view(),
    )

    publication = publisher.publish_context(
        DatasetSplitContextRequest(publication_generation=4)
    )

    assert publication.generation == 4
    assert publication.context.epoch_available is True
    assert publication.context.subject_count == 2
    assert publication.context.session_count == 1
    assert publication.context.label_count == 2
    assert publication.context.trial_count == 12
    assert [
        (item.value, item.label) for item in publication.context.subject_choices
    ] == [
        ("S01", "S01"),
        ("S02", "S02"),
    ]
    assert [
        (item.value, item.label) for item in publication.context.session_choices
    ] == [("session-1", "session-1")]
    assert not hasattr(publication.context, "epoch_data")


@pytest.mark.parametrize(
    ("trial_groups", "expected_count"),
    [
        (["trial-a", "trial-a", "trial-b"], 2),
        (np.asarray(["trial-a", "trial-a", "trial-b"]), 2),
        ([["unhashable"]], 12),
        ("scalar-trial", 12),
        (b"scalar-trial", 12),
        (np.asarray("scalar-trial"), 12),
    ],
)
def test_context_trial_group_count_accepts_array_like_groups_and_fails_safe(
    trial_groups: object,
    expected_count: int,
) -> None:
    publisher = DatasetSplitPreviewPublisher(
        dataset=_DatasetState(_EpochDataWithTrialGroups(trial_groups)),
        generator_factory=lambda _config: _Generator(),
        get_publication=lambda: _view(),
    )

    context = publisher.publish_context(
        DatasetSplitContextRequest(publication_generation=4)
    ).context

    assert context.trial_group_count == expected_count


def test_context_choices_keep_internal_keys_but_publish_real_display_names() -> None:
    epoch_data = _EpochData()
    epoch_data.get_subject_map = lambda: {7: "sub-A"}  # type: ignore[method-assign]
    epoch_data.get_session_map = lambda: {3: "session-blue"}  # type: ignore[method-assign]
    epoch_data.label_map = {2: "12 Hz"}
    publisher = DatasetSplitPreviewPublisher(
        dataset=_DatasetState(epoch_data),
        generator_factory=lambda _config: _Generator(),
        get_publication=lambda: _view(),
    )

    context = publisher.publish_context(
        DatasetSplitContextRequest(publication_generation=4)
    ).context

    assert [(choice.value, choice.label) for choice in context.subject_choices] == [
        (7, "sub-A")
    ]
    assert [(choice.value, choice.label) for choice in context.session_choices] == [
        (3, "session-blue")
    ]
    assert [(choice.value, choice.label) for choice in context.label_choices] == [
        (2, "12 Hz")
    ]


def test_context_publication_represents_missing_epochs_without_live_payload() -> None:
    publisher = DatasetSplitPreviewPublisher(
        dataset=_DatasetState(None),
        generator_factory=lambda _config: _Generator(),
        get_publication=lambda: _view(),
    )

    publication = publisher.publish_context(
        DatasetSplitContextRequest(publication_generation=4)
    )

    assert publication.context.epoch_available is False
    assert publication.context.trial_count == 0
    assert publication.context.subject_choices == ()
    assert publication.context.session_choices == ()


def test_real_preview_success_preserves_live_epoch_evidence_and_dataset_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    epoch_data = _real_epoch_data()
    original_evidence = [{"source": "live", "details": {"selected": 3}}]
    epoch_data.trial_selection_evidence = original_evidence
    epoch_data.trial_selection_evidence_dropped = 2
    monkeypatch.setattr(Dataset, "SEQ", 41)
    publisher = DatasetSplitPreviewPublisher(
        dataset=_DatasetState(epoch_data),
        generator_factory=lambda config: DatasetGenerator(epoch_data, config),
        get_publication=lambda: _view(),
    )

    publication = publisher.publish_preview(
        DatasetSplitPreviewRequest(
            request_id="real-preview-success",
            publication_generation=4,
            specification=_specification(),
        )
    )

    assert publication.rows
    _assert_live_split_state_unchanged(
        epoch_data,
        original_evidence,
        sequence=41,
        dropped=2,
    )


def test_real_preview_row_exposes_allocation_and_saliency_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The UI receives evidence derived from the real generated masks, not defaults."""
    epoch_data = _real_epoch_data()
    monkeypatch.setattr(Dataset, "SEQ", 42)
    publisher = DatasetSplitPreviewPublisher(
        dataset=_DatasetState(epoch_data),
        generator_factory=lambda config: DatasetGenerator(epoch_data, config),
        get_publication=lambda: _view(),
    )

    specification = DatasetSplitSpecification.from_payload(
        {
            "train_type": "Full Data",
            "is_cross_validation": True,
            "val_splitters": [
                {
                    "split_type": "By Trial",
                    "split_unit": "Ratio",
                    "value": "0.2",
                    "is_option": True,
                }
            ],
            "test_splitters": [
                {
                    "split_type": "By Trial",
                    "split_unit": "K Fold",
                    "value": "2",
                    "is_option": True,
                }
            ],
        }
    )
    publication = publisher.publish_preview(
        DatasetSplitPreviewRequest(
            request_id="real-preview-allocation-evidence",
            publication_generation=4,
            specification=specification,
        )
    )

    row = publication.rows[0]
    assert row.test_scope_group_count > 0
    assert row.test_selected_group_count > 0
    assert row.test_requested_unit == "K Fold"
    assert row.test_requested_value == "2"
    assert row.validation_scope_group_count > 0
    assert row.validation_selected_group_count > 0
    assert row.validation_requested_unit == "Ratio"
    assert row.validation_requested_value == "0.2"
    assert row.test_missing_class_names == ()
    assert row.validation_missing_class_names == ()
    assert row.saliency_source == "test"


def test_real_preview_failure_preserves_live_epoch_evidence_and_dataset_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    epoch_data = _real_epoch_data()
    original_evidence = [{"source": "live", "details": {"selected": 3}}]
    epoch_data.trial_selection_evidence = original_evidence
    epoch_data.trial_selection_evidence_dropped = 5
    monkeypatch.setattr(Dataset, "SEQ", 73)
    publisher = DatasetSplitPreviewPublisher(
        dataset=_DatasetState(epoch_data),
        generator_factory=lambda config: DatasetGenerator(epoch_data, config),
        get_publication=lambda: _view(),
    )
    invalid_specification = DatasetSplitSpecification.from_payload(
        {
            "train_type": "Full Data",
            "is_cross_validation": False,
            "val_splitters": [],
            "test_splitters": [
                {
                    "split_type": "By Trial",
                    "split_unit": "Ratio",
                    "value": "invalid-ratio",
                    "is_option": True,
                }
            ],
        }
    )

    with pytest.raises(ValueError, match="invalid unit or amount"):
        publisher.publish_preview(
            DatasetSplitPreviewRequest(
                request_id="real-preview-failure",
                publication_generation=4,
                specification=invalid_specification,
            )
        )

    _assert_live_split_state_unchanged(
        epoch_data,
        original_evidence,
        sequence=73,
        dropped=5,
    )


def test_real_preview_cancel_preserves_live_epoch_evidence_and_dataset_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    epoch_data = _real_epoch_data()
    original_evidence = [{"source": "live", "details": {"selected": 3}}]
    epoch_data.trial_selection_evidence = original_evidence
    epoch_data.trial_selection_evidence_dropped = 7
    monkeypatch.setattr(Dataset, "SEQ", 109)
    started = threading.Event()
    release = threading.Event()
    publisher = DatasetSplitPreviewPublisher(
        dataset=_DatasetState(epoch_data),
        generator_factory=lambda config: _BlockingDatasetGenerator(
            epoch_data,
            config,
            started=started,
            release=release,
        ),
        get_publication=lambda: _view(),
    )
    errors: list[BaseException] = []

    def publish() -> None:
        try:
            publisher.publish_preview(
                DatasetSplitPreviewRequest(
                    request_id="real-preview-cancel",
                    publication_generation=4,
                    specification=_specification(),
                )
            )
        except BaseException as error:
            errors.append(error)

    worker = threading.Thread(target=publish)
    worker.start()
    assert started.wait(timeout=1.0)

    try:
        assert publisher.cancel_preview("real-preview-cancel") is True
    finally:
        release.set()
        worker.join(timeout=1.0)

    assert worker.is_alive() is False
    assert len(errors) == 1
    assert isinstance(errors[0], PreconditionError)
    assert "cancelled" in str(errors[0]).casefold()
    _assert_live_split_state_unchanged(
        epoch_data,
        original_evidence,
        sequence=109,
        dropped=7,
    )


def test_stale_context_request_fails_before_reading_epoch_data() -> None:
    dataset = _DatasetState(_EpochData())
    publisher = DatasetSplitPreviewPublisher(
        dataset=dataset,
        generator_factory=lambda _config: _Generator(),
        get_publication=lambda: _view(generation=5),
    )

    with pytest.raises(PreconditionError, match="changed"):
        publisher.publish_context(DatasetSplitContextRequest(publication_generation=4))

    assert dataset.read_count == 0


def test_generation_change_discards_preview_rows() -> None:
    publications = iter((_view(4), _view(5)))
    epoch_data = _real_epoch_data()
    publisher = DatasetSplitPreviewPublisher(
        dataset=_DatasetState(epoch_data),
        generator_factory=lambda config: DatasetGenerator(epoch_data, config),
        get_publication=lambda: next(publications),
    )

    with pytest.raises(PreconditionError, match="changed"):
        publisher.publish_preview(
            DatasetSplitPreviewRequest(
                request_id="preview-stale",
                publication_generation=4,
                specification=_specification(),
            )
        )


def test_duplicate_active_preview_request_id_is_rejected() -> None:
    started = threading.Event()
    release = threading.Event()
    epoch_data = _real_epoch_data()

    publisher = DatasetSplitPreviewPublisher(
        dataset=_DatasetState(epoch_data),
        generator_factory=lambda config: _BlockingDatasetGenerator(
            epoch_data,
            config,
            started=started,
            release=release,
        ),
        get_publication=lambda: _view(),
    )
    request = DatasetSplitPreviewRequest(
        request_id="preview-duplicate",
        publication_generation=4,
        specification=_specification(),
    )
    worker = threading.Thread(target=lambda: publisher.publish_preview(request))
    worker.start()
    assert started.wait(timeout=1.0)

    try:
        with pytest.raises(PreconditionError, match="already active"):
            publisher.publish_preview(request)
    finally:
        release.set()
        worker.join(timeout=1.0)
