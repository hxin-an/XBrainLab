"""Epoch dialog reads must stay detached behind ApplicationService."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from XBrainLab.backend.application.service import ApplicationService
from XBrainLab.backend.study import Study


def _preprocessed_recording() -> MagicMock:
    recording = MagicMock()
    recording.get_event_list.return_value = (
        np.asarray(
            [
                [0, 0, 1],
                [250, 0, 2],
                [500, 0, 1],
            ],
            dtype=int,
        ),
        {"Left hand": 1, "Right hand": 2},
    )
    recording.get_runtime_detail.return_value = {}
    recording.get_sfreq.return_value = 250.0
    recording.get_filepath.return_value = "/tmp/sub-01_task-mi_raw.fif"
    recording.get_filename.return_value = "sub-01_task-mi_raw.fif"
    recording.get_subject_name.return_value = "01"
    recording.get_session_name.return_value = "01"
    recording.get_nchan.return_value = 22
    recording.get_epochs_length.return_value = 0
    recording.get_preprocess_history.return_value = []
    recording.is_raw.return_value = True
    recording.is_labels_imported.return_value = True
    return recording


def test_application_service_publishes_detached_epoch_dialog_setup() -> None:
    study = Study()
    recording = _preprocessed_recording()
    study.data_manager.loaded_data_list = [recording]
    study.data_manager.preprocessed_data_list = [recording]
    service = ApplicationService(study)

    first = service.get_epoch_dialog_context()

    assert first.usable is True
    assert first.publication_generation == service.get_view_publication().generation
    assert first.epoch_setup is not None
    assert first.epoch_setup["available_events"] == [
        {"name": "Left hand", "count": 2},
        {"name": "Right hand", "count": 1},
    ]
    assert first.epoch_setup["sampling_frequencies_hz"] == [250.0]

    first.epoch_setup["available_events"][0]["name"] = "mutated in UI"
    second = service.get_epoch_dialog_context()

    assert second.epoch_setup is not None
    assert second.epoch_setup["available_events"][0]["name"] == "Left hand"
