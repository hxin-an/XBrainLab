"""Focused tests for preprocessing and epoch command handlers."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest

from XBrainLab.backend.application.commands import (
    ApplyMontageCommand,
    CreateEpochCommand,
    PreprocessCommand,
    PreprocessOperation,
)
from XBrainLab.backend.application.epoch_context import build_epoching_context
from XBrainLab.backend.application.errors import (
    ConfirmationRequiredError,
    PreconditionError,
)
from XBrainLab.backend.application.preprocess_service import (
    PreprocessCommandService,
)
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.preprocessor.time_epoch import EpochBoundarySummary


class _PreprocessController:
    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []
        self.data_list: list[Any] = []

    def get_preprocessed_data_list(self) -> list[Any]:
        return self.data_list

    def apply_filter(
        self,
        low_freq: float | None,
        high_freq: float | None,
        notch_freqs: list[float] | None,
    ) -> None:
        self.events.append(("filter", (low_freq, high_freq, notch_freqs)))

    def apply_resample(self, rate: float) -> None:
        self.events.append(("resample", rate))

    def apply_normalization(self, method: str) -> None:
        self.events.append(("normalize", method))

    def apply_rereference(self, channels: str | list[str]) -> None:
        self.events.append(("rereference", channels))

    def apply_montage(
        self,
        channels: list[str],
        positions: list[tuple[float, float, float]],
    ) -> None:
        self.events.append(("montage", (channels, positions)))

    def apply_standard_pipeline(
        self,
        *,
        l_freq: float,
        h_freq: float,
        notch_freq: float | None = None,
        rate: float | None = None,
        ref_channels: str | list[str] | None = None,
        normalization: str | None = None,
    ) -> None:
        self.events.append(
            (
                "standard_pipeline",
                {
                    "l_freq": l_freq,
                    "h_freq": h_freq,
                    "notch_freq": notch_freq,
                    "rate": rate,
                    "ref_channels": ref_channels,
                    "normalization": normalization,
                },
            )
        )

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


class _DatasetController:
    def __init__(self) -> None:
        self.selected_channels: list[str] | None = None

    def apply_channel_selection(self, channels: list[str]) -> None:
        self.selected_channels = channels


class _NormalizationTarget:
    def __init__(self, *, raw: bool) -> None:
        self._raw = raw

    def is_raw(self) -> bool:
        return self._raw


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
    _DatasetController,
]:
    preprocess = _PreprocessController()
    event_names = ["left", "right", "noise", "oddball", "standard"]
    preprocess.data_list = [_InternalEpochData(event_names)]
    dataset = _DatasetController()
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


def _bids_epoch_confirmation_service(
    monkeypatch,
) -> tuple[
    PreprocessCommandService,
    _PreprocessController,
    _BidsEpochData,
    dict[str, Any],
]:
    data = _BidsEpochData()
    preprocess = _PreprocessController()
    preprocess.data_list = [data]
    handoff = {
        "ready": True,
        "supervised_ready": True,
        "default_epoch_events": ["left", "right"],
        "selected_event_names": ["left", "right"],
        "label_source": "bids_events",
        "placement_modes": ["interval"],
    }
    service = PreprocessCommandService(
        preprocess=preprocess,
        dataset=_DatasetController(),
        get_state=lambda: _state_with_epoch_handoff(handoff),
    )
    monkeypatch.setattr(
        "XBrainLab.backend.application.preprocess_service."
        "ResourceChecker.check_epoch_materialization_safe",
        lambda *_args, **_kwargs: SimpleNamespace(
            blocking=False,
            risk_level="safe",
        ),
    )
    return service, preprocess, data, handoff


def test_preprocess_service_applies_core_operations() -> None:
    service, preprocess, dataset = _service()

    assert (
        service.handle_preprocess(
            PreprocessCommand(
                operation=PreprocessOperation.BANDPASS,
                low_freq=1.0,
                high_freq=40.0,
                notch_freq=50.0,
            ),
        )
        == "Applied bandpass filter: 1.0-40.0 Hz."
    )
    assert (
        service.handle_preprocess(
            PreprocessCommand(
                operation=PreprocessOperation.REREFERENCE,
                method="average",
            ),
        )
        == "Applied reference: average."
    )
    assert (
        service.handle_preprocess(
            PreprocessCommand(
                operation=PreprocessOperation.SELECT_CHANNELS,
                channels=["C3", "C4"],
            ),
        )
        == "Selected 2 channel(s)."
    )

    assert preprocess.events == [
        ("filter", (1.0, 40.0, [50.0])),
        ("rereference", "average"),
    ]
    assert dataset.selected_channels == ["C3", "C4"]


def test_preprocess_service_maps_individual_operations_without_facade() -> None:
    service, preprocess, _dataset = _service()
    preprocess.data_list = [_NormalizationTarget(raw=True)]

    assert (
        service.handle_preprocess(
            PreprocessCommand(
                operation=PreprocessOperation.NOTCH,
                notch_freq=60.0,
            ),
        )
        == "Applied notch filter: 60.0 Hz."
    )
    assert (
        service.handle_preprocess(
            PreprocessCommand(
                operation=PreprocessOperation.RESAMPLE,
                rate=256,
            ),
        )
        == "Resampled data to 256 Hz."
    )
    normalize_message, normalize_diagnostics = service.handle_preprocess(
        PreprocessCommand(
            operation=PreprocessOperation.NORMALIZE,
            method="z-score",
        ),
    )
    assert normalize_message == (
        "Z-score normalization will be applied independently to each EEG epoch "
        "when epochs are created."
    )
    assert normalize_diagnostics == {
        "normalization_method": "z-score",
        "normalization_scope": "per_epoch_per_channel",
        "raw_requests_deferred": 1,
        "epoched_items_normalized": 0,
        "recording_statistics_used": False,
    }
    assert (
        service.handle_preprocess(
            PreprocessCommand(
                operation=PreprocessOperation.REREFERENCE,
                channels=["Cz"],
            ),
        )
        == "Applied reference: Cz."
    )

    assert preprocess.events == [
        ("filter", (None, None, [60.0])),
        ("resample", 256),
        ("normalize", "z-score"),
        ("rereference", ["Cz"]),
    ]


def test_preprocess_service_owns_confirmed_montage_mutation() -> None:
    service, preprocess, _dataset = _service()

    message, diagnostics = service.handle_apply_montage(
        ApplyMontageCommand(
            channels=["Cz"],
            positions=[(0.0, 0.0, 0.0)],
            montage_name="standard_1020",
        ),
    )

    assert preprocess.events == [
        ("montage", (["Cz"], [(0.0, 0.0, 0.0)])),
    ]
    assert message == "Applied montage 'standard_1020' to 1 channel(s)."
    assert diagnostics == {
        "channel_count": 1,
        "montage_name": "standard_1020",
    }


@pytest.mark.parametrize(
    ("command", "message"),
    [
        (
            ApplyMontageCommand(channels=[], positions=[]),
            "channels list cannot be empty",
        ),
        (
            ApplyMontageCommand(channels=["Cz"], positions=[]),
            "positions list cannot be empty",
        ),
        (
            ApplyMontageCommand(
                channels=["C3", "C4"],
                positions=[(0.0, 0.0, 0.0)],
            ),
            "channels and positions must have equal length",
        ),
    ],
)
def test_preprocess_service_validates_confirmed_montage(
    command: ApplyMontageCommand,
    message: str,
) -> None:
    service, preprocess, _dataset = _service()

    with pytest.raises(PreconditionError, match=message):
        service.handle_apply_montage(command)

    assert preprocess.events == []


def test_preprocess_service_applies_standard_preprocess_in_batch() -> None:
    service, preprocess, _dataset = _service()
    preprocess.data_list = [_NormalizationTarget(raw=True)]

    message, diagnostics = service.handle_preprocess(
        PreprocessCommand(
            operation=PreprocessOperation.STANDARD,
            notch_freq=60.0,
            rate=128,
            method="z score",
            channels=["average"],
        ),
    )
    assert message == (
        "Standard preprocessing applied. Z score normalization will be applied "
        "independently to each EEG epoch when epochs are created."
    )
    assert diagnostics["normalization_scope"] == "per_epoch_per_channel"
    assert diagnostics["raw_requests_deferred"] == 1
    assert diagnostics["recording_statistics_used"] is False

    assert preprocess.events == [
        (
            "standard_pipeline",
            {
                "l_freq": 4,
                "h_freq": 40,
                "notch_freq": 60.0,
                "rate": 128,
                "ref_channels": "average",
                "normalization": "z score",
            },
        ),
    ]


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


def test_preprocess_service_reports_small_reviewed_boundary_exclusion(
    monkeypatch,
) -> None:
    service, preprocess, _dataset = _service()
    monkeypatch.setattr(
        "XBrainLab.backend.application.preprocess_service.summarize_epoch_boundaries",
        lambda *_args, **_kwargs: EpochBoundarySummary(
            selected_event_count=2_245,
            excluded_event_count=2,
            affected_recording_count=2,
            recording_count=3,
        ),
    )

    result = service.handle_create_epoch(
        CreateEpochCommand(
            baseline=(-0.2, 0.0),
            event_ids=["noise", "oddball", "standard"],
            t_min=-0.2,
            t_max=0.5,
        )
    )

    assert isinstance(result, tuple)
    message, diagnostics = result
    assert "Excluded 2 boundary event(s)" in message
    assert diagnostics["epoch_boundary_check"] == {
        "selected_event_count": 2_245,
        "excluded_event_count": 2,
        "remaining_event_count": 2_243,
        "affected_recording_count": 2,
        "recording_count": 3,
        "excluded_ratio": pytest.approx(2 / 2_245),
    }
    assert preprocess.events == [
        (
            "epoch",
            (
                (-0.2, 0.0),
                ["noise", "oddball", "standard"],
                -0.2,
                0.5,
                True,
            ),
        )
    ]


def test_preprocess_service_blocks_large_boundary_exclusion(monkeypatch) -> None:
    service, preprocess, _dataset = _service()
    monkeypatch.setattr(
        "XBrainLab.backend.application.preprocess_service.summarize_epoch_boundaries",
        lambda *_args, **_kwargs: EpochBoundarySummary(
            selected_event_count=100,
            excluded_event_count=2,
            affected_recording_count=1,
            recording_count=1,
        ),
    )

    with pytest.raises(PreconditionError, match=r"exclude 2 of 100") as exc_info:
        service.handle_create_epoch(
            CreateEpochCommand(t_min=-0.2, t_max=0.5, event_ids=["oddball"])
        )

    assert exc_info.value.diagnostics["epoch_boundary_check"][
        "excluded_ratio"
    ] == pytest.approx(0.02)
    assert preprocess.events == []


def test_bids_duration_warning_requires_receipt_before_epoch_mutation(
    monkeypatch,
) -> None:
    service, preprocess, data, handoff = _bids_epoch_confirmation_service(monkeypatch)
    context = build_epoching_context([data], epoch_handoff=handoff)
    requirement = context["confirmation_requirement"]
    command = CreateEpochCommand(
        t_min=requirement["scope"]["t_min"],
        t_max=requirement["scope"]["t_max"],
        event_ids=requirement["scope"]["selected_events"],
    )

    with pytest.raises(ConfirmationRequiredError) as exc_info:
        service.handle_create_epoch(command)

    assert exc_info.value.diagnostics["confirmation_requirement"] == requirement
    assert preprocess.events == []

    accepted = replace(
        command,
        confirmation_receipt=requirement["receipt"],
    )
    assert (
        service.handle_create_epoch(accepted)
        == f"Created EEG epochs from {command.t_min}s to {command.t_max}s."
    )
    assert preprocess.events == [
        (
            "epoch",
            (
                None,
                ["left", "right"],
                command.t_min,
                command.t_max,
            ),
        )
    ]


@pytest.mark.parametrize("changed_field", ["t_min", "t_max", "event_ids", "context"])
def test_bids_epoch_receipt_is_invalidated_by_scope_or_context_change(
    monkeypatch,
    changed_field,
) -> None:
    service, preprocess, data, handoff = _bids_epoch_confirmation_service(monkeypatch)
    context = build_epoching_context([data], epoch_handoff=handoff)
    requirement = context["confirmation_requirement"]
    command = CreateEpochCommand(
        t_min=requirement["scope"]["t_min"],
        t_max=requirement["scope"]["t_max"],
        event_ids=requirement["scope"]["selected_events"],
        confirmation_receipt=requirement["receipt"],
    )
    if changed_field == "context":
        data.hint["duration_stats"] = {
            "numeric_count": 2,
            "min": 0.25,
            "max": 14.0,
        }
    elif changed_field == "event_ids":
        command = replace(command, event_ids=["left"])
    elif changed_field == "t_min":
        command = replace(command, t_min=-0.1)
    else:
        command = replace(command, t_max=10.0)

    with pytest.raises(ConfirmationRequiredError) as exc_info:
        service.handle_create_epoch(command)

    refreshed = exc_info.value.diagnostics["confirmation_requirement"]
    assert refreshed["receipt"] != requirement["receipt"]
    assert preprocess.events == []


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
        dataset=_DatasetController(),
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


def test_preprocess_service_blocks_epoch_ram_before_copy_or_materialization(
    monkeypatch,
) -> None:
    import numpy as np

    class CopySensitiveSource:
        def __init__(self) -> None:
            self.copy_attempts = 0
            self.events = np.array([[100, 0, 1]], dtype=int)

        def get_event_list(self):
            return self.events, {"left": 1}

        def get_nchan(self) -> int:
            return 64

        def get_sfreq(self) -> float:
            return 1_000.0

        def get_filename(self) -> str:
            return "copy-sensitive.fif"

        def get_runtime_detail(self, name: str):
            if name != "data_interpretation_epoch_hint":
                return None
            return {
                "source": "Labels inside EEG files",
                "placement_method": "internal_events",
                "class_map": {"left": "left", "right": "right"},
                "recommended_events": ["left", "right"],
            }

        def copy(self):
            self.copy_attempts += 1
            return self

    class MaterializingPreprocessController(_PreprocessController):
        def __init__(self, source: CopySensitiveSource) -> None:
            super().__init__()
            self.data_list = [source]
            self.materialization_attempts = 0

        def apply_epoching(self, *args: Any) -> None:
            self.data_list[0].copy()
            self.materialization_attempts += 1
            super().apply_epoching(*args)

    source = CopySensitiveSource()
    preprocess = MaterializingPreprocessController(source)
    service = PreprocessCommandService(
        preprocess=preprocess,
        dataset=_DatasetController(),
        get_state=lambda: _state_with_epoch_handoff(
            _ready_internal_handoff(["left", "right"])
        ),
    )
    monkeypatch.setattr(
        "XBrainLab.backend.application.resource_guard.available_ram_bytes",
        lambda: 1,
    )

    with pytest.raises(PreconditionError, match=r"too large.*RAM"):
        service.handle_create_epoch(
            CreateEpochCommand(t_min=-0.2, t_max=4.0, event_ids=["left"])
        )

    assert source.copy_attempts == 0
    assert preprocess.materialization_attempts == 0
    assert preprocess.events == []


def test_preprocess_service_uses_data_import_epoch_defaults() -> None:
    preprocess = _PreprocessController()
    event_names = ["Left hand", "Right hand"]
    preprocess.data_list = [_InternalEpochData(event_names)]
    dataset = _DatasetController()
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
    dataset = _DatasetController()
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
    dataset = _DatasetController()
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
    dataset = _DatasetController()
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
    dataset = _DatasetController()
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
    dataset = _DatasetController()
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
        dataset=_DatasetController(),
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
        dataset=_DatasetController(),
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
        dataset=_DatasetController(),
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
        dataset=_DatasetController(),
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

    with pytest.raises(PreconditionError, match="low_freq is required"):
        service.handle_preprocess(
            PreprocessCommand(operation=PreprocessOperation.BANDPASS, high_freq=40.0),
        )

    with pytest.raises(ConfirmationRequiredError, match="set_montage requires UI"):
        service.handle_preprocess(
            PreprocessCommand(
                operation=PreprocessOperation.SET_MONTAGE,
                montage_name="standard_1020",
            ),
        )
