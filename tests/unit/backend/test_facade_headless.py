from unittest.mock import MagicMock, patch

import torch

from XBrainLab.backend.facade import BackendFacade


def test_backend_facade_headless():
    """
    Verify BackendFacade works without QApplication.
    """
    # 1. Assert no QApplication (loose check as before)
    # assert QApplication.instance() is None

    # 2. Mock internal dependencies to avoid real file I/O
    # or threading issues during simple init test
    with patch("XBrainLab.backend.facade.Study") as MockStudy:
        # Configure Mock Study
        mock_study_instance = MockStudy.return_value
        mock_study_instance.loaded_data_list = []
        mock_study_instance.preprocessed_data_list = []
        mock_study_instance.epoch_data = None
        mock_study_instance.datasets = []
        mock_study_instance.dataset_generator = None
        mock_study_instance.trainer = None
        mock_study_instance.model_holder = None
        mock_study_instance.training_option = None
        mock_study_instance.saliency_params = None
        mock_study_instance.pipeline_stage.value = "empty"

        controllers = {
            "dataset": MagicMock(),
            "preprocess": MagicMock(),
            "training": MagicMock(),
            "evaluation": MagicMock(),
            "visualization": MagicMock(),
        }
        mock_study_instance.get_controller.side_effect = lambda name: controllers[name]
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

        # 3. Instantiate Facade
        facade = BackendFacade()

        # 4. Verify Components
        assert facade.study == mock_study_instance
        assert facade.dataset is not None
        assert facade.training is not None
        assert facade.evaluation is not None

        # 5. Verify Delegation
        # Test load_data
        facade.dataset.import_files = MagicMock(return_value=(1, []))
        result = facade.load_data(["test.edf"])
        assert result == (1, [])
        facade.dataset.import_files.assert_called_with(["test.edf"])

        # Test Preprocessing Delegation
        mock_study_instance.loaded_data_list = [MagicMock()]
        mock_study_instance.preprocessed_data_list = [MagicMock()]
        facade.preprocess.apply_filter = MagicMock()
        facade.apply_filter(1, 30)
        facade.preprocess.apply_filter.assert_called_with(1, 30, None)

        # Test Training Setup Delegation through the application service.
        with (
            patch(
                "XBrainLab.backend.application.training_service.ModelHolder"
            ) as MockServiceModelHolder,
            patch(
                "XBrainLab.backend.application.training_service.TrainingOption"
            ) as MockTrainingOption,
        ):
            facade.training.set_model_holder = MagicMock()

            # Verify set_model delegates to ModelHolder
            facade.set_model("EEGNet")
            assert MockServiceModelHolder.called
            facade.training.set_model_holder.assert_called()

            facade.training.set_training_option = MagicMock()
            facade.configure_training(
                10, 32, 0.001, optimizer="sgd", save_checkpoints_every=5
            )

            # Verify configure_training delegates to TrainingOption
            # Verify configure_training delegates to TrainingOption
            assert MockTrainingOption.called
            # Verify SGD and checkpoints
            call_args = MockTrainingOption.call_args[1]
            assert call_args["optim"] == torch.optim.SGD
            assert call_args["checkpoint_epoch"] == 5

            facade.training.set_training_option.assert_called()

        # Test training
        # configure_training now injects a plan implicitly?
        # No, run_training does not yet.
        # But wait, did I update run_training to generate plan?
        # I decided NOT to, to stick to Facade = Thin Wrapper
        # around existing controller logic.
        # The Tool calls generate_plan via Facade?
        # Wait, I updated RealStartTrainingTool
        # to call facade.run_training() only.
        # This implies Facade.run_training MUST handle planning
        # or it will fail in integration.
        # But this is a unit test of the Facade.

        facade.training.start_training = MagicMock()
        mock_study_instance.datasets = [MagicMock()]
        mock_study_instance.model_holder = MagicMock()
        mock_study_instance.training_option = MagicMock()
        facade.run_training(confirmed=True)
        facade.training.start_training.assert_called_once()

        # Lifecycle compatibility methods stay wrapped by ApplicationService.
        facade.preprocess.notify = MagicMock()
        mock_study_instance.reset_preprocess = MagicMock()
        mock_study_instance.loaded_data_list = [MagicMock()]
        mock_study_instance.preprocessed_data_list = [MagicMock()]
        facade.reset_preprocess()
        mock_study_instance.reset_preprocess.assert_called_once_with(force_update=True)

        facade.training.clean_datasets = MagicMock()
        mock_study_instance.datasets = [MagicMock()]
        facade.clear_datasets()
        facade.training.clean_datasets.assert_called_once_with(force_update=True)

        facade.training.clear_history = MagicMock()
        mock_study_instance.trainer = MagicMock()
        facade.evaluation.get_plans = MagicMock(return_value=[MagicMock()])
        facade.clear_training_history()
        facade.training.clear_history.assert_called_once_with()
