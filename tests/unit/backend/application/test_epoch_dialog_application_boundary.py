"""Epoch dialog reads must stay detached behind ApplicationService."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from XBrainLab.backend.application.commands import CommandName
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


def test_application_service_with_missing_runtime_hint_is_unavailable() -> None:
    study = Study()
    recording = _preprocessed_recording()
    study.data_manager.loaded_data_list = [recording]
    study.data_manager.preprocessed_data_list = [recording]
    service = ApplicationService(study)

    first = service.get_epoch_dialog_context()

    assert first.usable is False
    assert first.publication_generation == service.get_view_publication().generation
    assert first.epoch_setup is None
    assert first.epoch_handoff is None
    assert "needs review" in str(first.unavailable_reason)


def test_mixed_sampling_epoch_context_disables_create_epoch_capability() -> None:
    study = Study()
    first_recording = _preprocessed_recording()
    first_recording.get_sfreq.return_value = 100.0
    second_recording = _preprocessed_recording()
    second_recording.get_sfreq.return_value = 256.0
    second_recording.get_filename.return_value = "sub-02_task-mi_raw.fif"
    second_recording.get_filepath.return_value = "/tmp/sub-02_task-mi_raw.fif"
    for recording in (first_recording, second_recording):
        recording.get_data.side_effect = AssertionError(
            "readiness must not materialize signal data"
        )
    study.data_manager.loaded_data_list = [first_recording, second_recording]
    study.data_manager.preprocessed_data_list = [first_recording, second_recording]
    service = ApplicationService(study)

    capability = service.get_capabilities().get(CommandName.CREATE_EPOCH)
    dialog_context = service.get_epoch_dialog_context()

    assert capability.enabled is False
    assert capability.reasons == [
        "Selected EEG files use different sampling frequencies (100 Hz, 256 Hz). "
        "Resample them to one shared rate before creating epochs."
    ]
    assert dialog_context.usable is False
    assert dialog_context.capability == capability
    first_recording.get_data.assert_not_called()
    second_recording.get_data.assert_not_called()
