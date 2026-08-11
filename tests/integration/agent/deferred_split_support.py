"""Real deferred-split state builders shared by Assistant integration tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from XBrainLab.backend.application import (
    ApplicationService,
    ConfigureTrainingCommand,
    SaveDatasetSplitCommand,
    get_application_service,
)
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.dataset import (
    Dataset,
    DataSplittingConfig,
    Epochs,
    EpochWindowProvenance,
    TrainingType,
)
from XBrainLab.backend.study import Study


def build_saved_split_runtime(
    study: Study,
) -> tuple[ApplicationService, Epochs]:
    """Save split intent through the command spine without creating datasets."""
    service = get_application_service(study)
    raw = MagicMock()
    raw.get_filename.return_value = "assistant-split.fif"
    raw.get_filepath.return_value = "/test-data/assistant-split.fif"
    raw.get_subject_name.return_value = "S01"
    raw.get_session_name.return_value = "001"
    raw.is_raw.return_value = True
    raw.get_mne.return_value.ch_names = ["C3", "C4"]
    epoch = _epoch_data()
    study.data_manager.loaded_data_list = [raw]
    study.data_manager.preprocessed_data_list = [raw]
    study.data_manager.epoch_data = epoch

    saved = service.execute(
        SaveDatasetSplitCommand(
            test_ratio=0.2,
            val_ratio=0.2,
            split_strategy="trial",
            training_mode="individual",
        )
    )

    assert saved.ok is True
    assert saved.state.dataset.split_spec_saved is True
    assert saved.state.active_dataset.has_saved_split is True
    assert saved.state.dataset.available is False
    assert saved.state.dataset.split_materialized is False
    assert study.datasets == []
    return service, epoch


def build_training_ready_state() -> ApplicationStateSnapshot:
    """Return command-derived readiness with saved, unmaterialized split intent."""
    study = Study()
    service, _epoch = build_saved_split_runtime(study)
    configured = service.execute(
        ConfigureTrainingCommand(
            model_name="EEGNet",
            epoch=1,
            batch_size=2,
            learning_rate=0.001,
            device="cpu",
        )
    )
    assert configured.ok is True
    state = service.get_state()
    assert state.dataset.split_spec_saved is True
    assert state.dataset.split_materialized is False
    assert state.active_dataset.has_saved_split is True
    assert state.training.has_model is True
    assert state.training.has_training_option is True
    return state


def install_materialized_candidate(study: Study, epoch: Epochs) -> None:
    """Provide the candidate that Start Training may materialize and audit."""
    generator = MagicMock()
    generator.prepare_result.return_value = [_materialized_dataset(epoch)]
    study.get_datasets_generator = MagicMock(return_value=generator)


def _epoch_data() -> Epochs:
    labels = np.asarray([0, 1] * 6, dtype=int)
    epoch = Epochs([])
    epoch.data = np.zeros((len(labels), 2, 512), dtype=np.float32)
    epoch.event_id = {"Left": 0, "Right": 1}
    epoch.label_map = {0: "Left", 1: "Right"}
    epoch.label = labels
    epoch.subject = np.zeros(len(labels), dtype=int)
    epoch.session = np.zeros(len(labels), dtype=int)
    epoch.idx = np.arange(len(labels), dtype=int)
    epoch.trial_group = np.arange(len(labels), dtype=int)
    epoch.subject_map = {0: "S01"}
    epoch.session_map = {0: "001"}
    epoch.ch_names = ["C3", "C4"]
    epoch.sfreq = 128.0
    epoch.epoch_window_provenance = tuple(
        EpochWindowProvenance(
            source_recording_id=f"content-sha256:{index:064x}",
            event_sample=index * 512,
            window_start_sample=index * 512,
            window_end_sample_exclusive=(index + 1) * 512,
            source_sfreq=128.0,
            epoch_sfreq=128.0,
            tmin_seconds=0.0,
            tmax_seconds=511 / 128,
            source_coordinates_verified=True,
        )
        for index in range(len(labels))
    )
    return epoch


def _materialized_dataset(epoch: Epochs) -> Dataset:
    dataset = Dataset(
        epoch,
        DataSplittingConfig(
            train_type=TrainingType.IND,
            is_cross_validation=False,
            val_splitter_list=[],
            test_splitter_list=[],
        ),
    )
    dataset.name = "S01"
    dataset.train_mask[:6] = True
    dataset.val_mask[6:9] = True
    dataset.test_mask[9:] = True
    return dataset
