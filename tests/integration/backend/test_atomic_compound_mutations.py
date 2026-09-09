"""Command-spine regressions for all-or-nothing compound data mutations."""

from __future__ import annotations

from unittest.mock import patch

import mne
import numpy as np

from XBrainLab.backend.application import ApplicationService
from XBrainLab.backend.application.commands import (
    MetadataUpdate,
    PreprocessCommand,
    PreprocessOperation,
    UpdateMetadataCommand,
)
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.preprocessor.base import PreprocessBase
from XBrainLab.backend.study import Study


class _RecordingProcessor(PreprocessBase):
    def get_preprocess_desc(self, *_args, **_kwargs) -> str:
        return "filter"

    def _data_preprocess(self, preprocessed_data: Raw, *_args, **_kwargs) -> None:
        preprocessed_data.get_mne().apply_function(lambda samples: samples + 1)


class _FailingProcessor(PreprocessBase):
    def get_preprocess_desc(self, *_args, **_kwargs) -> str:
        return "resample"

    def _data_preprocess(self, preprocessed_data: Raw, *_args, **_kwargs) -> None:
        preprocessed_data.get_mne().apply_function(lambda samples: samples + 1)
        raise RuntimeError("resample failed")


class _FailingMetadataRaw(Raw):
    def set_session_name(self, session: str) -> None:
        if session == "bad-run":
            raise RuntimeError("metadata setter failed")
        super().set_session_name(session)


def _raw(filepath: str, *, failing_metadata: bool = False) -> Raw:
    info = mne.create_info(["C3", "C4"], sfreq=100.0, ch_types="eeg")
    mne_raw = mne.io.RawArray(
        np.zeros((2, 200), dtype=np.float64),
        info,
        verbose="ERROR",
    )
    raw_type = _FailingMetadataRaw if failing_metadata else Raw
    return raw_type(filepath, mne_raw)


def test_standard_pipeline_failure_is_atomic_through_application_service() -> None:
    study = Study()
    raw = _raw("/data/sub-01_raw.fif")
    study.set_loaded_data_list([raw], force_update=True)
    original_preprocessed = study.preprocessed_data_list
    original_samples = raw.get_mne().get_data().copy()
    notifications: list[str] = []
    preprocess = study.preprocess_state_service
    preprocess.subscribe(
        "preprocess_changed",
        lambda: notifications.append("changed"),
    )

    with (
        patch(
            "XBrainLab.backend.preprocessor.Filtering",
            _RecordingProcessor,
        ),
        patch(
            "XBrainLab.backend.preprocessor.Resample",
            _FailingProcessor,
        ),
    ):
        result = ApplicationService(study).execute(
            PreprocessCommand(
                operation=PreprocessOperation.STANDARD,
                low_freq=4,
                high_freq=40,
                rate=50,
            )
        )

    assert result.failed is True
    assert study.preprocessed_data_list is original_preprocessed
    assert raw.get_preprocess_history() == []
    assert np.array_equal(raw.get_mne().get_data(), original_samples)
    assert notifications == []


def test_metadata_batch_failure_is_atomic_through_application_service() -> None:
    study = Study()
    first = _raw("/data/sub-01_raw.fif")
    second = _raw("/data/sub-02_raw.fif", failing_metadata=True)
    first.set_subject_name("old-1")
    second.set_subject_name("old-2")
    second.set_session_name("run-2")
    study.set_loaded_data_list([first, second], force_update=True)
    original_loaded = study.loaded_data_list
    original_preprocessed = study.preprocessed_data_list

    result = ApplicationService(study).execute(
        UpdateMetadataCommand(
            updates=[
                MetadataUpdate(index=0, subject="new-1"),
                MetadataUpdate(index=1, subject="new-2", session="bad-run"),
            ]
        )
    )

    assert result.failed is True
    assert study.loaded_data_list is original_loaded
    assert study.preprocessed_data_list is original_preprocessed
    assert [row.get_subject_name() for row in study.loaded_data_list] == [
        "old-1",
        "old-2",
    ]
    assert second.get_session_name() == "run-2"
