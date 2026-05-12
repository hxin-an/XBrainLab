from unittest.mock import MagicMock, patch

import pytest
import torch

from XBrainLab.backend.facade import BackendFacade

pytestmark = pytest.mark.facade_compatibility


def _make_headless_facade():
    study = MagicMock()
    controllers = {
        "dataset": MagicMock(),
        "preprocess": MagicMock(),
        "training": MagicMock(),
        "evaluation": MagicMock(),
        "visualization": MagicMock(),
    }
    study.get_controller.side_effect = lambda name: controllers[name]
    study.loaded_data_list = []
    study.preprocessed_data_list = []
    study.epoch_data = None
    study.datasets = []
    study.dataset_generator = None
    study.trainer = None
    study.model_holder = None
    study.training_option = None
    study.saliency_params = None
    study.pipeline_stage.value = "empty"

    controllers["dataset"].is_locked.return_value = False
    controllers["dataset"].get_event_info.return_value = {
        "total": 0,
        "unique_count": 0,
        "unique_labels": [],
    }
    controllers["dataset"].get_runtime_diagnostics.return_value = {}
    controllers["preprocess"].is_epoched.return_value = False
    controllers["preprocess"].get_channel_names.return_value = []
    controllers["preprocess"].get_runtime_diagnostics.return_value = {}
    controllers["training"].is_training.return_value = False
    controllers["training"].get_missing_requirements.return_value = []
    controllers["evaluation"].get_plans.return_value = []

    return BackendFacade(study=study), study, controllers


def test_backend_facade_constructs_with_mocked_headless_study():
    facade, study, controllers = _make_headless_facade()

    assert facade.study is study
    assert facade.dataset is controllers["dataset"]
    assert facade.training is controllers["training"]
    assert facade.evaluation is controllers["evaluation"]


def test_backend_facade_load_data_preserves_legacy_tuple_shape():
    facade, _study, _controllers = _make_headless_facade()
    facade.dataset.import_files = MagicMock(return_value=(1, []))

    result = facade.load_data(["test.edf"])

    assert result == (1, [])
    facade.dataset.import_files.assert_called_once_with(["test.edf"])


def test_backend_facade_apply_filter_delegates_to_command_service():
    facade, study, _controllers = _make_headless_facade()
    study.loaded_data_list = [MagicMock()]
    study.preprocessed_data_list = [MagicMock()]
    facade.preprocess.apply_filter = MagicMock()

    facade.apply_filter(1, 30)

    facade.preprocess.apply_filter.assert_called_once_with(1, 30, None)


def test_backend_facade_training_setup_delegates_through_application_service():
    facade, _study, _controllers = _make_headless_facade()

    with (
        patch(
            "XBrainLab.backend.application.training_service.ModelHolder"
        ) as MockServiceModelHolder,
        patch(
            "XBrainLab.backend.application.training_service.TrainingOption"
        ) as MockTrainingOption,
    ):
        facade.training.set_model_holder = MagicMock()
        facade.training.set_training_option = MagicMock()

        facade.set_model("EEGNet")
        facade.configure_training(
            10,
            32,
            0.001,
            optimizer="sgd",
            save_checkpoints_every=5,
        )

    assert MockServiceModelHolder.called
    facade.training.set_model_holder.assert_called()
    assert MockTrainingOption.called
    assert MockTrainingOption.call_args.kwargs["optim"] == torch.optim.SGD
    assert MockTrainingOption.call_args.kwargs["checkpoint_epoch"] == 5
    facade.training.set_training_option.assert_called()


def test_backend_facade_run_training_delegates_when_prerequisites_exist():
    facade, study, _controllers = _make_headless_facade()
    facade.training.start_training = MagicMock()
    study.loaded_data_list = [MagicMock()]
    study.preprocessed_data_list = [MagicMock()]
    study.datasets = [MagicMock()]
    study.model_holder = MagicMock()
    study.training_option = MagicMock()

    facade.run_training(confirmed=True)

    facade.training.start_training.assert_called_once()


def test_backend_facade_lifecycle_methods_preserve_legacy_force_update_calls():
    facade, study, _controllers = _make_headless_facade()
    facade.preprocess.notify = MagicMock()
    study.reset_preprocess = MagicMock()
    study.loaded_data_list = [MagicMock()]
    study.preprocessed_data_list = [MagicMock()]

    facade.reset_preprocess()

    study.reset_preprocess.assert_called_once_with(force_update=True)

    facade.training.clean_datasets = MagicMock()
    study.datasets = [MagicMock()]
    facade.clear_datasets()

    facade.training.clean_datasets.assert_called_once_with(force_update=True)

    facade.training.clear_history = MagicMock()
    study.trainer = MagicMock()
    facade.evaluation.get_plans = MagicMock(return_value=[MagicMock()])
    facade.clear_training_history()

    facade.training.clear_history.assert_called_once_with()
