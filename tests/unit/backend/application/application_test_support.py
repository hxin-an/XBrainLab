"""Application boundary: application test support behavior."""

from __future__ import annotations

from pathlib import Path
from threading import Event
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import torch

from tests.unit.backend.application.preprocess_test_support import (
    _minimal_raw,
)
from XBrainLab.backend.application import (
    ApplicationService,
    SaveDatasetSplitCommand,
)
from XBrainLab.backend.dataset import (
    Epochs,
    EpochWindowProvenance,
)
from XBrainLab.backend.load_data.raw import Raw
from XBrainLab.backend.training import (
    ModelHolder,
    Trainer,
    TrainingEvaluation,
    TrainingOption,
    TrainingPlanHolder,
)

THREAD_WATCHDOG_SECONDS = 5.0


def _off_class_weighting() -> dict[str, object]:
    """Return detached record metadata for lightweight TrainRecord test stubs."""
    return {
        "requested": {
            "mode": "off",
            "custom_class_weights": {},
            "class_map_fingerprint": None,
        },
        "resolved": {
            "class_names": [],
            "class_order": [],
            "class_counts": [],
            "weights": [],
        },
    }


def _class_value_decisions(
    class_names: dict[str, str],
) -> dict[str, dict[str, object]]:
    return {
        raw_value: {
            "role": "stimulus",
            "keep_event": True,
            "use_as_class": True,
            "class_name": class_name,
        }
        for raw_value, class_name in class_names.items()
    }


def _use_test_raw_factory(
    service: ApplicationService,
    loaded: Raw | dict[str, Raw] | None = None,
) -> MagicMock:
    """Install the real detached-import seam without mocking Study mutation."""

    def load(path: str) -> Raw:
        if isinstance(loaded, dict):
            selected = loaded.get(str(path)) or loaded.get(Path(path).name)
            if selected is not None:
                return selected
        elif loaded is not None:
            return loaded
        return _minimal_raw(Path(path))

    load_mock = MagicMock(side_effect=load)
    service.dataset._raw_factory_provider = lambda: SimpleNamespace(load=load_mock)
    return load_mock


def _valid_model_holder() -> ModelHolder:
    return ModelHolder(int, {})


def _valid_training_option(*, batch_size: int = 4) -> TrainingOption:
    return TrainingOption(
        output_dir="./test-output",
        optim=torch.optim.Adam,
        optim_params={},
        use_cpu=True,
        gpu_idx=None,
        epoch=1,
        bs=batch_size,
        lr=0.001,
        checkpoint_epoch=0,
        evaluation_option=TrainingEvaluation.LAST_EPOCH,
        repeat_num=1,
    )


def _publish_mock_training_identity(service: ApplicationService) -> None:
    """Keep mocked starts honest about the typed runtime identity contract."""
    trainer = Trainer([])
    trainer.run(interact=False)
    service.study.training_manager.trainer = trainer


def _positive_epoch_data() -> Epochs:
    labels = np.array([0, 1, 0, 1, 0, 1], dtype=int)
    event_names = ("Left hand", "Right hand")
    epoch_data = Epochs([])
    epoch_data.data = np.zeros((len(labels), 2, 16), dtype=np.float32)
    epoch_data.event_id = {
        name: identifier for identifier, name in enumerate(event_names)
    }
    epoch_data.label_map = {
        identifier: name for name, identifier in epoch_data.event_id.items()
    }
    epoch_data.label = labels
    epoch_data.subject = np.zeros(len(labels), dtype=int)
    epoch_data.session = np.zeros(len(labels), dtype=int)
    epoch_data.idx = np.arange(len(labels), dtype=int)
    epoch_data.trial_group = np.arange(len(labels), dtype=int)
    epoch_data.subject_map = {0: "S01"}
    epoch_data.session_map = {0: "001"}
    epoch_data.ch_names = ["C3", "C4"]
    epoch_data.sfreq = 128.0
    epoch_data.epoch_window_provenance = tuple(
        EpochWindowProvenance(
            source_recording_id=f"content-sha256:{'a' * 64}",
            event_sample=index * 32,
            window_start_sample=index * 32,
            window_end_sample_exclusive=index * 32 + 16,
            source_sfreq=128.0,
            epoch_sfreq=128.0,
            tmin_seconds=0.0,
            tmax_seconds=15 / 128,
            source_coordinates_verified=True,
        )
        for index in range(len(labels))
    )
    return epoch_data


def _prepare_saved_training_split(service: ApplicationService) -> dict[str, Any]:
    """Prepare one real, audited split through the deferred public contract."""
    service.study.data_manager.loaded_data_list = [
        _minimal_raw(Path("/tmp/application-service-training.fif"))
    ]
    service.study.data_manager.epoch_data = _positive_epoch_data()

    saved = service.execute(SaveDatasetSplitCommand(split_strategy="trial"))
    assert saved.ok is True
    assert saved.state.dataset.split_spec_saved is True
    assert saved.state.dataset.split_materialized is False

    candidate = service.dataset_generation.prepare_saved_split_candidate()
    prepared = service.dataset_generation.commit_prepared_split(candidate)
    state = service.get_state()
    assert prepared["materialized"] is True
    assert prepared["split_audit"]["ok"] is True
    assert state.dataset.split_spec_saved is True
    assert state.dataset.split_materialized is True
    return prepared


class _RecoveryBlockingPlan(TrainingPlanHolder):
    """Minimal real Trainer plan that exits only after StopTraining interrupts it."""

    def __init__(self) -> None:
        self.started = Event()
        self._interrupt = Event()
        self.tracker = None

    def bind_state_tracker(self, tracker) -> None:
        self.tracker = tracker

    def get_name(self) -> str:
        return "Blocking plan"

    def get_plans(self) -> list[Any]:
        return []

    def train(self) -> None:
        self.started.set()
        self._interrupt.wait(timeout=THREAD_WATCHDOG_SECONDS)

    def set_interrupt(self) -> None:
        self._interrupt.set()

    def clear_interrupt(self) -> None:
        self._interrupt.clear()


def _raw_mock():
    raw = MagicMock(spec=Raw)
    raw.get_filename.return_value = "sample.fif"
    raw.get_filepath.return_value = "/tmp/sample.fif"
    raw.get_subject_name.return_value = "S01"
    raw.get_session_name.return_value = "001"
    raw.get_nchan.return_value = 2
    raw.get_sfreq.return_value = 100.0
    raw.get_epoch_duration.return_value = 100
    raw.is_raw.return_value = True
    mne_raw = MagicMock()
    mne_raw.ch_names = ["C3", "C4"]
    mne_raw.annotations = []
    raw.get_mne.return_value = mne_raw
    return raw
