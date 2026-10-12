"""Application boundary: reset behavior."""

from __future__ import annotations

import gc
import weakref
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import mne
import numpy as np
import pytest

from tests.unit.backend.application.application_test_support import (
    _raw_mock,
    _valid_model_holder,
    _valid_training_option,
)
from tests.unit.backend.application.preprocess_test_support import (
    _apply_reviewed_epoch_fixture,
    _write_reviewed_epoch_fixture,
)
from XBrainLab.backend.application import (
    ApplicationService,
    ClearDatasetsCommand,
    ClearTrainingHistoryCommand,
    CommandName,
    ErrorType,
    NewSessionCommand,
    PreprocessCommand,
    PreprocessOperation,
    ResetPreprocessCommand,
    ResetSessionCommand,
)
from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.state import (
    ActiveDatasetSnapshot,
    ActiveTrainingSnapshot,
    ApplicationStateSnapshot,
)
from XBrainLab.backend.exceptions import StaleTrainingPipelineMutationError
from XBrainLab.backend.load_data.raw import Raw
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import (
    Trainer,
)


def test_reset_preprocess_is_blocked_while_training_is_running() -> None:
    state = replace(
        ApplicationStateSnapshot.empty(),
        pipeline_stage="training",
        active_dataset=ActiveDatasetSnapshot(has_raw_data=True),
        active_training=ActiveTrainingSnapshot(
            has_trainer=True,
            is_running=True,
        ),
    )

    capability = build_capability_policy(state).get(CommandName.RESET_PREPROCESS)

    assert capability.available is False
    assert any("training" in reason.lower() for reason in capability.reasons)


def test_reset_preprocess_command_does_not_mutate_live_training_state() -> None:
    service = ApplicationService(Study())
    raw = _raw_mock()
    raw.get_preprocess_history.return_value = ["filter"]
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    trainer = Trainer([])
    trainer.is_running = MagicMock(return_value=True)
    service.study.training_manager.trainer = trainer
    service.study.reset_preprocess = MagicMock()
    service.training.clean_datasets = MagicMock()

    result = service.execute(ResetPreprocessCommand(confirmed=True))

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    service.study.reset_preprocess.assert_not_called()
    service.training.clean_datasets.assert_not_called()
    assert service.study.data_manager.loaded_data_list == [raw]
    assert service.study.data_manager.preprocessed_data_list == [raw]
    assert service.study.training_manager.trainer is trainer


def test_reset_preprocess_command_rolls_back_stale_training_commit() -> None:
    service = ApplicationService(Study())
    manager = service.study.data_manager
    raw = _raw_mock()
    raw.get_preprocess_history.return_value = ["filter"]
    backup = _raw_mock()
    preprocessed = _raw_mock()
    preprocessed.get_preprocess_history.return_value = ["filter"]
    epoch = MagicMock()
    dataset = MagicMock()
    generator = MagicMock()
    trainer = Trainer([])
    trainer.is_running = MagicMock(return_value=False)
    manager.loaded_data_list = [raw]
    manager.backup_loaded_data_list = [backup]
    manager.preprocessed_data_list = [preprocessed]
    manager.epoch_data = epoch
    manager.datasets = [dataset]
    manager.dataset_generator = generator
    manager.dataset_locked = True
    service.study.training_manager.trainer = trainer

    def reset_preprocess(*, force_update: bool) -> None:
        assert force_update is True
        manager.loaded_data_list = [backup]
        manager.backup_loaded_data_list = None
        manager.preprocessed_data_list = []
        manager.epoch_data = None
        manager.datasets = []
        manager.dataset_generator = None
        manager.dataset_locked = False

    service.study.reset_preprocess = MagicMock(side_effect=reset_preprocess)
    service.study.training_manager.retire_trainer_if_current = MagicMock(
        side_effect=StaleTrainingPipelineMutationError(),
    )

    result = service.execute(ResetPreprocessCommand(confirmed=True))

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert manager.loaded_data_list == [raw]
    assert manager.backup_loaded_data_list == [backup]
    assert manager.preprocessed_data_list == [preprocessed]
    assert manager.epoch_data is epoch
    assert manager.datasets == [dataset]
    assert manager.dataset_generator is generator
    assert manager.dataset_locked is True
    assert service.study.training_manager.trainer is trainer


@pytest.mark.parametrize("command_type", [ResetSessionCommand, NewSessionCommand])
def test_session_clear_releases_real_channel_selection_backup(
    command_type: type[ResetSessionCommand] | type[NewSessionCommand],
    tmp_path: Path,
) -> None:
    study = Study()
    raw = Raw(
        "previous-session.fif",
        mne.io.RawArray(
            np.zeros((2, 500)),
            mne.create_info(["C3", "C4"], sfreq=100.0, ch_types="eeg"),
            verbose="ERROR",
        ),
    )
    study.set_loaded_data_list([raw], force_update=True)
    service = ApplicationService(study)
    selected = service.execute(
        PreprocessCommand(
            operation=PreprocessOperation.SELECT_CHANNELS,
            channels=["C3"],
        )
    )
    assert selected.ok
    backup = study.data_manager.backup_loaded_data_list
    assert backup is not None
    assert backup[0].get_mne().ch_names == ["C3", "C4"]
    backup_ref = weakref.ref(backup[0])
    samples_ref = weakref.ref(backup[0].get_mne()._data)
    assert samples_ref().nbytes == 8000
    del backup

    result = service.execute(command_type(confirmed=True))
    gc.collect()

    assert result.ok
    assert result.state.pipeline_stage == "empty"
    assert study.loaded_data_list == []
    assert study.preprocessed_data_list == []
    assert study.data_manager.backup_loaded_data_list is None
    assert backup_ref() is None
    assert samples_ref() is None

    replacement_path = tmp_path / "replacement_raw.fif"
    _write_reviewed_epoch_fixture(replacement_path, channel_names=("Pz",))
    _apply_reviewed_epoch_fixture(service, replacement_path)
    replacement = study.loaded_data_list[0]

    reset = service.execute(ResetPreprocessCommand(confirmed=True))

    assert reset.ok
    assert study.loaded_data_list == [replacement]
    assert study.preprocessed_data_list == [replacement]
    assert replacement.get_mne().ch_names == ["Pz"]
    assert Path(replacement.get_filepath()) == replacement_path


@pytest.mark.parametrize(
    "recovery_command",
    ["reset_session", "new_session"],
)
def test_recovery_command_executes_real_handler_after_initial_snapshot_failure(
    recovery_command: str,
) -> None:
    study = Study()
    service = ApplicationService(study)
    study.data_manager.loaded_data_list = [cast(Any, object())]
    study.data_manager.preprocessed_data_list = [cast(Any, object())]
    study.data_manager.epoch_data = cast(Any, object())
    study.data_manager.datasets = [cast(Any, object())]
    study.data_manager.dataset_generator = cast(Any, object())
    study.data_manager.dataset_locked = True
    # Deliberately corrupt private state to exercise recovery after a failed read.
    study.training_manager._model_holder = cast(Any, object())
    study.training_manager._training_option = cast(Any, object())
    study.training_manager.saliency_params = {"SmoothGrad": {"nt_samples": 5}}
    study.training_manager.trainer = Trainer([])
    command = (
        ResetSessionCommand(confirmed=True)
        if recovery_command == "reset_session"
        else NewSessionCommand(confirmed=True)
    )
    real_build = service.state_snapshot.build
    calls = 0

    def fail_once_then_build(*, last_error=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("snapshot unavailable")
        return real_build(last_error=last_error)

    service.state_snapshot.build = MagicMock(side_effect=fail_once_then_build)

    result = service.execute(command)

    assert result.ok is True
    assert result.command_name == command.name.value
    assert result.state.state_reliable is True
    assert service.state_snapshot.build.call_count == 2
    assert result.state.pipeline_stage == "empty"
    assert study.data_manager.loaded_data_list == []
    assert study.data_manager.preprocessed_data_list == []
    assert study.data_manager.epoch_data is None
    assert study.data_manager.datasets == []
    assert study.data_manager.dataset_generator is None
    assert study.data_manager.dataset_locked is False
    assert study.training_manager.model_holder is None
    assert study.training_manager.training_option is None
    assert study.training_manager.saliency_params is None
    assert study.training_manager.trainer is None


@pytest.mark.parametrize(
    "command_type",
    [ResetSessionCommand, NewSessionCommand],
    ids=["reset-session", "new-session"],
)
@pytest.mark.parametrize(
    "materialize_training_service",
    [False, True],
    ids=["lazy", "materialized"],
)
def test_session_reset_uses_one_training_configuration_owner_regardless_of_laziness(
    monkeypatch: pytest.MonkeyPatch,
    command_type: type[ResetSessionCommand] | type[NewSessionCommand],
    materialize_training_service: bool,
) -> None:
    study = Study()
    service = ApplicationService(study)
    manager = study.training_manager
    manager.set_model_holder(_valid_model_holder())
    manager.set_training_option(_valid_training_option())
    manager.saliency_params = {"SmoothGrad": {"nt_samples": 5}}
    if materialize_training_service:
        assert service.training_commands is not None

    reset_owner = service.training_configuration_reset
    original_clear = reset_owner.clear
    clear_count = 0

    def record_clear() -> None:
        nonlocal clear_count
        clear_count += 1
        original_clear()

    monkeypatch.setattr(reset_owner, "clear", record_clear)

    result = service.execute(command_type(confirmed=True))

    assert result.ok is True
    assert clear_count == 1
    assert manager.model_holder is None
    assert manager.training_option is None
    assert manager.saliency_params is None
    assert ("training_commands" in vars(service)) is (materialize_training_service)


def test_reset_preprocess_command_clears_downstream_training_plan():
    service = ApplicationService(Study())
    raw = _raw_mock()
    raw.get_preprocess_history.return_value = ["filter"]
    service.study.data_manager.loaded_data_list = [raw]
    service.study.data_manager.preprocessed_data_list = [raw]
    service.study.data_manager.epoch_data = MagicMock()
    service.study.data_manager.datasets = [MagicMock()]
    service.study.training_manager.trainer = Trainer([])
    service.study.reset_preprocess = MagicMock(
        side_effect=lambda force_update: (
            setattr(service.study.data_manager, "epoch_data", None),
            setattr(service.study.data_manager, "datasets", []),
            setattr(service.study.data_manager, "dataset_generator", None),
        )
    )

    unconfirmed = service.execute(ResetPreprocessCommand())
    assert unconfirmed.failed is True
    assert unconfirmed.error_type == ErrorType.CONFIRMATION_REQUIRED

    result = service.execute(ResetPreprocessCommand(confirmed=True))

    assert result.ok is True
    assert result.state.epoch.available is False
    assert result.state.dataset.available is False
    assert result.state.training.has_trainer is False
    assert result.diagnostics["trainer_cleared"] is True


def test_clear_datasets_and_training_history_commands_route_cleanup():
    service = ApplicationService(Study())
    service.study.data_manager.datasets = [MagicMock()]
    service.training.clean_datasets = MagicMock()

    clear_datasets = service.execute(ClearDatasetsCommand(confirmed=True))

    assert clear_datasets.ok is True
    service.training.clean_datasets.assert_called_once_with(force_update=True)

    trainer = Trainer([])
    plan = MagicMock()
    trainer.get_training_plan_holders = MagicMock(return_value=[plan])
    service.study.training_manager.trainer = trainer
    service.training.clear_history = MagicMock()

    clear_history = service.execute(ClearTrainingHistoryCommand(confirmed=True))

    assert clear_history.ok is True
    service.training.clear_history.assert_called_once_with()


def test_clear_datasets_reads_trainer_presence_from_runtime_not_study_alias():
    class _TrainerAliasRaisesStudy(Study):
        @property
        def trainer(self):
            raise AssertionError("Study.trainer alias must not be read")

    study = _TrainerAliasRaisesStudy()
    study.data_manager.datasets = [MagicMock()]
    study.training_manager.trainer = Trainer([])
    service = ApplicationService(study)

    result = service.execute(ClearDatasetsCommand(confirmed=True))

    assert result.ok is True
    assert result.diagnostics["trainer_cleared"] is True
    assert study.training_manager.trainer is None
