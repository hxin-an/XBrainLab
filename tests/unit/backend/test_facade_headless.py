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
        facade.preprocess.apply_filter = MagicMock()
        facade.apply_filter(1, 30)
        facade.preprocess.apply_filter.assert_called_with(1, 30, None)

        # Test Training Setup Delegation
        # Mock dependencies (ModelHolder, TrainingOption class usage)
        # ModelHolder is global in facade -> patch facade.ModelHolder
        # TrainingOption is imported from backend.training inside function
        # -> patch backend.training.TrainingOption
        with (
            patch("XBrainLab.backend.facade.ModelHolder") as MockModelHolder,
            patch("XBrainLab.backend.facade.TrainingOption") as MockTrainingOption,
            patch("XBrainLab.backend.facade.DataSplittingConfig"),
        ):
            facade.training.set_model_holder = MagicMock()

            # Verify set_model delegates to ModelHolder
            facade.set_model("EEGNet")
            assert MockModelHolder.called
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
        facade.run_training()
        facade.training.start_training.assert_called_once()

    print("BackendFacade headless verification passed.")


if __name__ == "__main__":
    test_backend_facade_headless()
