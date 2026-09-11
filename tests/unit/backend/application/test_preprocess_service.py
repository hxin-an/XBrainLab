"""Focused tests for preprocessing and epoch command handlers."""

from __future__ import annotations

from typing import cast

import mne
import numpy as np
import pytest

from XBrainLab.backend.application.commands import (
    PreprocessCommand,
    PreprocessOperation,
)
from XBrainLab.backend.application.errors import ConfirmationRequiredError
from XBrainLab.backend.application.service import ApplicationService
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.study import Study


def _real_preprocess_application() -> tuple[ApplicationService, Raw, np.ndarray]:
    study = Study()
    source_values = np.vstack(
        [
            np.sin(np.linspace(0.0, 20.0, 2_048))
            + 5.0 * np.sin(2 * np.pi * 50.0 * np.arange(2_048) / 256.0),
            np.cos(np.linspace(0.0, 20.0, 2_048)),
            np.sin(np.linspace(0.0, 40.0, 2_048)),
        ]
    )
    raw = Raw(
        "preprocess-characterization.fif",
        mne.io.RawArray(
            source_values.copy(),
            mne.create_info(["C3", "C4", "Cz"], sfreq=256.0, ch_types="eeg"),
            verbose="ERROR",
        ),
    )
    study.set_loaded_data_list([raw], force_update=True)
    return ApplicationService(study), raw, source_values


@pytest.mark.parametrize(
    ("command", "expected_message", "effect"),
    [
        (
            PreprocessCommand(
                operation=PreprocessOperation.BANDPASS, low_freq=1.0, high_freq=40.0
            ),
            "Applied bandpass filter: 1.0-40.0 Hz.",
            "filter",
        ),
        (
            PreprocessCommand(operation=PreprocessOperation.NOTCH, notch_freq=50.0),
            "Applied notch filter: 50.0 Hz.",
            "notch",
        ),
        (
            PreprocessCommand(operation=PreprocessOperation.RESAMPLE, rate=128.0),
            "Resampled data to 128.0 Hz.",
            "resample",
        ),
        (
            PreprocessCommand(
                operation=PreprocessOperation.NORMALIZE, method="z-score"
            ),
            "Z-score normalization will be applied independently to each EEG epoch when epochs are created.",
            "normalize",
        ),
        (
            PreprocessCommand(
                operation=PreprocessOperation.REREFERENCE, method="average"
            ),
            "Applied reference: average.",
            "average_reference",
        ),
        (
            PreprocessCommand(
                operation=PreprocessOperation.REREFERENCE, channels=["Cz"]
            ),
            "Applied reference: Cz.",
            "named_reference",
        ),
        (
            PreprocessCommand(
                operation=PreprocessOperation.CHANNEL_SELECTION, channels=["C3", "C4"]
            ),
            "Selected 2 channel(s).",
            "channel_selection",
        ),
        (
            PreprocessCommand(
                operation=PreprocessOperation.SELECT_CHANNELS, channels=["C3", "C4"]
            ),
            "Selected 2 channel(s).",
            "channel_selection",
        ),
        (
            PreprocessCommand(
                operation=PreprocessOperation.STANDARD,
                notch_freq=60.0,
                rate=128.0,
                channels=["average"],
                method="z score",
            ),
            "Standard preprocessing applied. Z score normalization will be applied independently to each EEG epoch when epochs are created.",
            "standard",
        ),
    ],
    ids=(
        "bandpass",
        "notch",
        "resample",
        "normalize",
        "average-reference",
        "named-reference",
        "channel-selection",
        "select-channels",
        "standard",
    ),
)
def test_application_preprocess_operations_use_prepared_command_path(
    command: PreprocessCommand,
    expected_message: str,
    effect: str,
) -> None:
    service, source, source_values = _real_preprocess_application()
    try:
        result = service.execute(command)

        assert result.ok, result.message
        assert result.message == expected_message
        np.testing.assert_array_equal(source.get_mne().get_data(), source_values)
        assert source.get_preprocess_history() == []
        if effect == "channel_selection":
            selected_loaded = service.study.loaded_data_list[0]
            assert selected_loaded is not source
            assert selected_loaded.get_mne().ch_names == ["C3", "C4"]
            np.testing.assert_array_equal(
                selected_loaded.get_mne().get_data(), source_values[:2]
            )
        else:
            assert service.study.loaded_data_list[0] is source
        prepared = service.study.preprocessed_data_list[0]
        assert prepared is not source
        if effect in {"filter", "notch"}:
            frequencies = np.fft.rfftfreq(source_values.shape[1], 1 / 256.0)
            index_50_hz = int(np.argmin(np.abs(frequencies - 50.0)))
            original_power = abs(np.fft.rfft(source_values[0])[index_50_hz]) ** 2
            processed_power = (
                abs(np.fft.rfft(prepared.get_mne().get_data()[0])[index_50_hz]) ** 2
            )
            assert processed_power < original_power * (
                0.1 if effect == "filter" else 0.5
            )
        elif effect == "resample":
            assert prepared.get_sfreq() == 128.0
        elif effect == "normalize":
            assert prepared.get_runtime_detail("normalization") == {
                "method": "z score",
                "scope": "per_epoch_per_channel",
                "status": "pending",
                "requested_on": "raw",
                "uses_recording_statistics": False,
            }
            assert {
                key: result.diagnostics[key]
                for key in (
                    "normalization_method",
                    "normalization_scope",
                    "raw_requests_deferred",
                    "epoched_items_normalized",
                    "recording_statistics_used",
                )
            } == {
                "normalization_method": "z-score",
                "normalization_scope": "per_epoch_per_channel",
                "raw_requests_deferred": 1,
                "epoched_items_normalized": 0,
                "recording_statistics_used": False,
            }
        elif effect == "average_reference":
            assert np.allclose(prepared.get_mne().get_data().sum(axis=0), 0.0)
        elif effect == "named_reference":
            assert np.allclose(prepared.get_mne().get_data()[2], 0.0)
        elif effect == "channel_selection":
            assert prepared.get_mne().ch_names == ["C3", "C4"]
        elif effect == "standard":
            assert prepared.get_sfreq() == 128.0
            assert prepared.get_filter_range() == (4.0, 40.0)
            assert np.allclose(prepared.get_mne().get_data().sum(axis=0), 0.0)
            assert prepared.get_runtime_detail("normalization") == {
                "method": "z score",
                "scope": "per_epoch_per_channel",
                "status": "pending",
                "requested_on": "raw",
                "uses_recording_statistics": False,
            }
            assert {
                key: result.diagnostics[key]
                for key in (
                    "normalization_method",
                    "normalization_scope",
                    "raw_requests_deferred",
                    "epoched_items_normalized",
                    "recording_statistics_used",
                )
            } == {
                "normalization_method": "z score",
                "normalization_scope": "per_epoch_per_channel",
                "raw_requests_deferred": 1,
                "epoched_items_normalized": 0,
                "recording_statistics_used": False,
            }
    finally:
        service.close()


@pytest.mark.parametrize(
    ("command", "expected_message"),
    [
        (
            PreprocessCommand(
                operation=PreprocessOperation.BANDPASS,
                high_freq=40.0,
            ),
            "low_freq is required.",
        ),
        (
            PreprocessCommand(operation=cast(PreprocessOperation, "unsupported")),
            "'unsupported' is not a valid PreprocessOperation",
        ),
    ],
    ids=("bandpass-missing-low-frequency", "unsupported-operation"),
)
def test_application_preprocess_rejects_invalid_commands_without_mutation(
    command: PreprocessCommand,
    expected_message: str,
) -> None:
    service, source, source_values = _real_preprocess_application()
    try:
        original_preprocessed = service.study.preprocessed_data_list

        result = service.execute(command)

        assert result.failed is True
        assert result.message == expected_message
        assert service.study.loaded_data_list[0] is source
        assert service.study.preprocessed_data_list is original_preprocessed
        np.testing.assert_array_equal(source.get_mne().get_data(), source_values)
        assert source.get_preprocess_history() == []
    finally:
        service.close()


def test_preprocess_service_preserves_safety_boundaries() -> None:
    service = ApplicationService(Study())
    try:
        with pytest.raises(ConfirmationRequiredError, match="set_montage requires UI"):
            service.preprocess_commands.handle_preprocess(
                PreprocessCommand(
                    operation=PreprocessOperation.SET_MONTAGE,
                    montage_name="standard_1020",
                ),
            )
    finally:
        service.close()
