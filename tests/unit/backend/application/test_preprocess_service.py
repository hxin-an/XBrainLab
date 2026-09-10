"""Focused tests for preprocessing and epoch command handlers."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast

import mne
import numpy as np
import pytest

from XBrainLab.backend.application.commands import (
    CreateEpochCommand,
    PreprocessCommand,
    PreprocessOperation,
)
from XBrainLab.backend.application.errors import (
    ConfirmationRequiredError,
    PreconditionError,
)
from XBrainLab.backend.application.preprocess_service import (
    PreprocessCommandService,
)
from XBrainLab.backend.application.service import ApplicationService
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.study import Study


class _PreprocessController:
    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []
        self.data_list: list[Any] = []

    def get_preprocessed_data_list(self) -> list[Any]:
        return self.data_list

    def apply_epoching(
        self,
        baseline: tuple[float, float] | None,
        event_ids: dict[str, int] | list[str] | None,
        t_min: float,
        t_max: float,
        allow_boundary_drop: bool = False,
        **_options: Any,
    ) -> None:
        values: tuple[Any, ...] = (baseline, event_ids, t_min, t_max)
        if allow_boundary_drop:
            values += (True,)
        self.events.append(("epoch", values))


class _BidsEpochData:
    def __init__(self) -> None:
        self.hint = {
            "source": "BIDS events.tsv",
            "placement_method": "interval",
            "label_field": "trial_type",
            "time_field": "onset",
            "duration_field": "duration",
            "duration_stats": {"numeric_count": 2, "min": 0.25, "max": 12.0},
            "placement_event_count": 2,
            "unknown_duration_count": 0,
            "class_map": {"left": "left", "right": "right"},
        }

    def get_event_list(self):
        return (
            np.array([[0, 0, 1], [100, 0, 2]], dtype=np.int32),
            {"left": 1, "right": 2},
        )

    def get_runtime_detail(self, name: str):
        if name == "data_interpretation_epoch_hint":
            return self.hint
        return None

    def get_sfreq(self) -> float:
        return 100.0

    def get_mne(self):
        return SimpleNamespace(
            info={"sfreq": self.get_sfreq()},
            first_samp=0,
            last_samp=2_000,
        )


class _InternalEpochData:
    def __init__(self, event_names: list[str] | None = None) -> None:
        names = event_names or ["left", "right", "noise", "oddball", "standard"]
        self.event_id = {name: index + 1 for index, name in enumerate(names)}
        self.events = np.asarray(
            [
                [1_000 + index * 100, 0, code]
                for index, code in enumerate(self.event_id.values())
            ],
            dtype=np.int32,
        )
        self.hint = {
            "source": "Labels inside EEG files",
            "placement_method": "internal_events",
            "class_map": {name: name for name in names},
            "recommended_events": names,
        }

    def get_event_list(self):
        return self.events, self.event_id

    def get_runtime_detail(self, name: str):
        return self.hint if name == "data_interpretation_epoch_hint" else None

    def get_sfreq(self) -> float:
        return 250.0

    def get_nchan(self) -> int:
        return 22

    def get_filename(self) -> str:
        return "internal-events.gdf"

    def get_mne(self):
        return SimpleNamespace(info={"sfreq": 250.0}, first_samp=0, last_samp=10_000)


def _ready_internal_handoff(event_names: list[str]) -> dict[str, object]:
    return {
        "ready": True,
        "supervised_ready": True,
        "label_source": "internal_events",
        "placement_modes": ["internal_events"],
        "default_epoch_events": event_names,
        "selected_event_names": event_names,
    }


def _state_with_epoch_handoff(
    epoch_handoff: object,
    *,
    reliable: bool = True,
) -> ApplicationStateSnapshot:
    state = ApplicationStateSnapshot.empty()
    return replace(
        state,
        interpretation=replace(
            state.interpretation,
            epoch_handoff=cast(dict[str, Any], epoch_handoff),
        ),
        state_reliable=reliable,
        read_errors=[] if reliable else ["interpretation snapshot is stale"],
    )


def _service() -> tuple[
    PreprocessCommandService,
    _PreprocessController,
    SimpleNamespace,
]:
    preprocess = _PreprocessController()
    event_names = ["left", "right", "noise", "oddball", "standard"]
    preprocess.data_list = [_InternalEpochData(event_names)]
    dataset = SimpleNamespace()
    return (
        PreprocessCommandService(
            preprocess=preprocess,
            dataset=dataset,
            get_state=lambda: _state_with_epoch_handoff(
                _ready_internal_handoff(event_names)
            ),
        ),
        preprocess,
        dataset,
    )


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


def test_preprocess_service_creates_epoch() -> None:
    service, preprocess, _dataset = _service()

    assert (
        service.handle_create_epoch(
            CreateEpochCommand(
                baseline=(0.0, 0.2),
                event_ids={"left": 1},
                t_min=-0.5,
                t_max=1.5,
            ),
        )
        == "Created EEG epochs from -0.5s to 1.5s."
    )

    assert preprocess.events == [
        ("epoch", ((0.0, 0.2), {"left": 1}, -0.5, 1.5)),
    ]


@pytest.mark.parametrize(
    ("hint", "handoff", "expected_code"),
    [
        (
            {},
            {
                "ready": True,
                "supervised_ready": True,
                "default_epoch_events": ["left", "right"],
                "label_source": "bids_events",
                "placement_modes": ["interval"],
            },
            "hint_missing",
        ),
        (
            {
                "source": "Loaded label file",
                "placement_method": "interval",
                "duration_field": "duration",
                "duration_stats": {"numeric_count": 1, "min": 0.5, "max": 0.5},
                "class_map": {"left": "left", "right": "right"},
            },
            {
                "ready": True,
                "supervised_ready": True,
                "default_epoch_events": ["left", "right"],
                "label_source": "bids_events",
                "placement_modes": ["interval"],
            },
            "handoff_source_mismatch",
        ),
        (
            {
                "source": "Loaded label file",
                "placement_method": "interval",
                "duration_field": "duration",
                "duration_stats": {"numeric_count": 0, "min": None, "max": None},
                "class_map": {"left": "left", "right": "right"},
            },
            {
                "ready": True,
                "supervised_ready": True,
                "default_epoch_events": ["left", "right"],
                "label_source": "loaded_label_files",
                "placement_modes": ["interval"],
            },
            "duration_unavailable",
        ),
    ],
    ids=["hint-missing", "source-mismatch", "non-bids-duration-missing"],
)
def test_preprocess_service_rejects_semantically_unavailable_epoch_context(
    hint,
    handoff,
    expected_code,
):
    data = _BidsEpochData()
    data.hint = hint
    preprocess = _PreprocessController()
    preprocess.data_list = [data]
    service = PreprocessCommandService(
        preprocess=preprocess,
        dataset=SimpleNamespace(),
        get_state=lambda: _state_with_epoch_handoff(handoff),
    )

    with pytest.raises(PreconditionError) as exc_info:
        service.handle_create_epoch(
            CreateEpochCommand(
                t_min=-0.2,
                t_max=1.0,
                event_ids=["left", "right"],
            )
        )

    assert exc_info.value.diagnostics["epoch_context_error"] == expected_code
    assert preprocess.events == []


def test_preprocess_service_uses_data_import_epoch_defaults() -> None:
    preprocess = _PreprocessController()
    event_names = ["Left hand", "Right hand"]
    preprocess.data_list = [_InternalEpochData(event_names)]
    dataset = SimpleNamespace()
    service = PreprocessCommandService(
        preprocess=preprocess,
        dataset=dataset,
        get_state=lambda: _state_with_epoch_handoff(
            _ready_internal_handoff(event_names)
        ),
    )

    service.handle_create_epoch(CreateEpochCommand(t_min=-0.2, t_max=1.0))

    assert preprocess.events == [
        ("epoch", (None, ["Left hand", "Right hand"], -0.2, 1.0)),
    ]


def test_preprocess_service_uses_raw_event_defaults_for_internal_labels() -> None:
    preprocess = _PreprocessController()
    event_names = ["769", "770"]
    preprocess.data_list = [_InternalEpochData(event_names)]
    dataset = SimpleNamespace()
    handoff = _ready_internal_handoff(event_names)
    handoff["event_label_aliases"] = {
        "769": "Left hand",
        "770": "Right hand",
    }
    service = PreprocessCommandService(
        preprocess=preprocess,
        dataset=dataset,
        get_state=lambda: _state_with_epoch_handoff(handoff),
    )

    service.handle_create_epoch(CreateEpochCommand(t_min=-0.2, t_max=1.0))

    assert preprocess.events == [
        ("epoch", (None, ["769", "770"], -0.2, 1.0)),
    ]


def test_preprocess_service_accepts_display_aliases_for_internal_labels() -> None:
    preprocess = _PreprocessController()
    event_names = ["769", "770"]
    preprocess.data_list = [_InternalEpochData(event_names)]
    dataset = SimpleNamespace()
    handoff = _ready_internal_handoff(event_names)
    handoff["event_label_aliases"] = {
        "769": "Left hand",
        "770": "Right hand",
    }
    service = PreprocessCommandService(
        preprocess=preprocess,
        dataset=dataset,
        get_state=lambda: _state_with_epoch_handoff(handoff),
    )

    service.handle_create_epoch(
        CreateEpochCommand(
            t_min=-0.2,
            t_max=1.0,
            event_ids=["Left hand", "Right hand"],
        ),
    )

    assert preprocess.events == [
        ("epoch", (None, ["769", "770"], -0.2, 1.0)),
    ]


def test_preprocess_service_rejects_epoch_targets_outside_import_handoff() -> None:
    preprocess = _PreprocessController()
    event_names = ["Left hand", "Right hand", "Artifact"]
    preprocess.data_list = [_InternalEpochData(event_names)]
    dataset = SimpleNamespace()
    service = PreprocessCommandService(
        preprocess=preprocess,
        dataset=dataset,
        get_state=lambda: _state_with_epoch_handoff(
            _ready_internal_handoff(["Left hand", "Right hand"])
        ),
    )

    with pytest.raises(PreconditionError, match="not in the reviewed import labels"):
        service.handle_create_epoch(
            CreateEpochCommand(t_min=-0.2, t_max=1.0, event_ids=["Artifact"]),
        )


def test_preprocess_service_blocks_handoff_blockers_before_defaults() -> None:
    preprocess = _PreprocessController()
    preprocess.data_list = [_InternalEpochData(["Left hand", "Right hand"])]
    dataset = SimpleNamespace()
    service = PreprocessCommandService(
        preprocess=preprocess,
        dataset=dataset,
        get_state=lambda: _state_with_epoch_handoff(
            {
                "ready": False,
                "supervised_ready": False,
                "supervised_blockers": ["No class labels were reviewed."],
                "default_epoch_events": ["Left hand", "Right hand"],
                "label_source": "internal_events",
                "placement_modes": ["internal_events"],
            }
        ),
    )

    with pytest.raises(PreconditionError, match="No class labels"):
        service.handle_create_epoch(CreateEpochCommand(t_min=-0.2, t_max=1.0))

    assert preprocess.events == []


def test_preprocess_service_rejects_dict_epoch_targets_outside_import_handoff() -> None:
    preprocess = _PreprocessController()
    event_names = ["Left hand", "Right hand", "Artifact"]
    preprocess.data_list = [_InternalEpochData(event_names)]
    dataset = SimpleNamespace()
    service = PreprocessCommandService(
        preprocess=preprocess,
        dataset=dataset,
        get_state=lambda: _state_with_epoch_handoff(
            _ready_internal_handoff(["Left hand", "Right hand"])
        ),
    )

    with pytest.raises(PreconditionError, match="not in the reviewed import labels"):
        service.handle_create_epoch(
            CreateEpochCommand(
                t_min=-0.2,
                t_max=1.0,
                event_ids={"Artifact": 99},
            ),
        )

    assert preprocess.events == []


def test_preprocess_service_fails_closed_when_epoch_state_read_raises() -> None:
    preprocess = _PreprocessController()

    def raise_state_read() -> ApplicationStateSnapshot:
        raise RuntimeError("authoritative read failed")

    service = PreprocessCommandService(
        preprocess=preprocess,
        dataset=SimpleNamespace(),
        get_state=raise_state_read,
    )

    with pytest.raises(PreconditionError) as exc_info:
        service.handle_create_epoch(
            CreateEpochCommand(
                t_min=-0.2,
                t_max=1.0,
                event_ids=["left"],
            )
        )

    assert exc_info.value.diagnostics["epoch_handoff_error"] == "state_read_failed"
    assert preprocess.events == []


def test_preprocess_service_fails_closed_for_unreliable_epoch_state() -> None:
    preprocess = _PreprocessController()
    service = PreprocessCommandService(
        preprocess=preprocess,
        dataset=SimpleNamespace(),
        get_state=lambda: _state_with_epoch_handoff({}, reliable=False),
    )

    with pytest.raises(PreconditionError) as exc_info:
        service.handle_create_epoch(
            CreateEpochCommand(t_min=-0.2, t_max=1.0, event_ids=["left"])
        )

    assert exc_info.value.diagnostics["epoch_handoff_error"] == "state_unreliable"
    assert preprocess.events == []


@pytest.mark.parametrize(
    "invalid_state",
    [
        object(),
        _state_with_epoch_handoff(["not", "a", "mapping"]),
        _state_with_epoch_handoff({"default_epoch_events": "left"}),
        replace(
            _state_with_epoch_handoff({}),
            read_errors=cast(list[str], None),
        ),
    ],
    ids=[
        "invalid-state",
        "invalid-handoff-shape",
        "invalid-handoff-field",
        "invalid-read-errors",
    ],
)
def test_preprocess_service_fails_closed_for_invalid_epoch_handoff_payload(
    invalid_state: object,
) -> None:
    preprocess = _PreprocessController()
    service = PreprocessCommandService(
        preprocess=preprocess,
        dataset=SimpleNamespace(),
        get_state=lambda: cast(ApplicationStateSnapshot, invalid_state),
    )

    with pytest.raises(PreconditionError) as exc_info:
        service.handle_create_epoch(
            CreateEpochCommand(t_min=-0.2, t_max=1.0, event_ids=["left"])
        )

    assert exc_info.value.diagnostics["epoch_handoff_error"] in {
        "invalid_state",
        "invalid_handoff",
    }
    assert preprocess.events == []


def test_preprocess_service_accepts_explicit_ordinary_epoch_settings() -> None:
    preprocess = _PreprocessController()
    event_names = ["left", "right"]
    preprocess.data_list = [_InternalEpochData(event_names)]
    service = PreprocessCommandService(
        preprocess=preprocess,
        dataset=SimpleNamespace(),
        get_state=lambda: _state_with_epoch_handoff(
            _ready_internal_handoff(event_names)
        ),
    )

    service.handle_create_epoch(
        CreateEpochCommand(
            baseline=(-0.2, 0.0),
            event_ids={"left": 1, "right": 2},
            t_min=-0.2,
            t_max=0.8,
        )
    )

    assert preprocess.events == [
        ("epoch", ((-0.2, 0.0), {"left": 1, "right": 2}, -0.2, 0.8))
    ]


def test_preprocess_service_preserves_safety_boundaries() -> None:
    service, _preprocess, _dataset = _service()

    with pytest.raises(ConfirmationRequiredError, match="set_montage requires UI"):
        service.handle_preprocess(
            PreprocessCommand(
                operation=PreprocessOperation.SET_MONTAGE,
                montage_name="standard_1020",
            ),
        )
