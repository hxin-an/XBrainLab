from unittest.mock import MagicMock, patch

import numpy as np
import torch

from XBrainLab.backend.model_base import EEGNet
from XBrainLab.backend.training import (
    ModelHolder,
    Trainer,
    TrainingEvaluation,
    TrainingOption,
    TrainingPlanHolder,
)
from XBrainLab.backend.training.record import RecordKey


def test_pipeline_integration():
    # 1. Setup Mock Data and Environment
    # We allow real GPU usage if available
    use_cuda = torch.cuda.is_available()
    use_cuda = torch.cuda.is_available()

    # 2. Create Dataset Generator (Mocking data loading)
    # We'll use synthetic data instead of loading from files
    # Reduce size for speed (Saliency calculation)
    # Even on GPU, we keep it small for unit test speed.
    n_trials = 4  # Slightly increased from minimal 2 to ensure batch norm works well
    n_channels = 4
    n_samples = 168  # Minimum for EEGNet
    n_classes = 2

    # Mock DatasetGenerator's internal data structures if possible,
    # or just mock the output of get_dataset

    # Mock the dataset object directly to avoid complex file I/O mocking.
    dataset_mock = MagicMock()

    # Mock get_training_data, get_val_data, get_test_data to return (X, y)
    # X needs to be numpy array, y needs to be numpy array
    mock_X = np.random.randn(n_trials, n_channels, n_samples)
    mock_y = np.random.randint(0, n_classes, n_trials)

    dataset_mock.get_training_data.return_value = (mock_X, mock_y)
    dataset_mock.get_val_data.return_value = (mock_X, mock_y)
    dataset_mock.get_test_data.return_value = (mock_X, mock_y)

    # Mock indices because SharedMemoryDataset uses them
    indices = np.arange(n_trials)
    dataset_mock.get_training_indices.return_value = indices
    dataset_mock.get_val_indices.return_value = indices
    dataset_mock.get_test_indices.return_value = indices

    # Mock masks
    dataset_mock.train_mask = np.ones(n_trials, dtype=bool)
    dataset_mock.val_mask = np.ones(n_trials, dtype=bool)
    dataset_mock.test_mask = np.ones(n_trials, dtype=bool)

    # 3. Setup Model Holder
    # Use a real model class but small parameters
    model_params = {
        "n_classes": n_classes,
        "channels": n_channels,
        "samples": n_samples,
        "sfreq": 128,
    }

    # Mock get_epoch_data().get_model_args() used in
    # TrainingPlanHolder.__init__ loop
    epoch_data_mock = MagicMock()
    epoch_data_mock.get_model_args.return_value = model_params
    epoch_data_mock.get_data.return_value = mock_X  # Needed for SharedMemoryDataset
    epoch_data_mock.get_label_list.return_value = (
        mock_y  # Needed for SharedMemoryDataset
    )
    dataset_mock.get_epoch_data.return_value = epoch_data_mock

    # We need to mock torch.load if ModelHolder tries to load weights,
    # but here we init from scratch.
    # ModelHolder expects a class, params map, and weight path (optional)
    # Pass empty dict for params map because get_model_args provides them
    holder = ModelHolder(EEGNet, {}, None)

    # 4. Setup Training Option
    option_args = {
        "output_dir": "test_output",
        "optim": torch.optim.Adam,
        "optim_params": {},  # lr is handled by 'lr' argument
        "use_cpu": not use_cuda,
        "gpu_idx": 0 if use_cuda else None,
        "epoch": 1,  # Short training
        "bs": 2,
        "lr": 0.001,
        "checkpoint_epoch": 1,
        "evaluation_option": "TrainingEvaluation.VAL_LOSS",
        "repeat_num": 1,
    }
    option_args["evaluation_option"] = TrainingEvaluation.TEST_ACC

    option = TrainingOption(**option_args)

    # 5. Setup Training Plan
    saliency_params = {
        "SmoothGrad": {"nt_samples": 1, "stdevs": 0.1},
        "SmoothGrad_Squared": {"nt_samples": 1, "stdevs": 0.1},
        "VarGrad": {"nt_samples": 1, "stdevs": 0.1},
    }

    # 6. Run Training via Trainer

    # Mock threading to run synchronously or just call job() directly
    # Trainer.run() starts a thread. Trainer.job() runs the logic.
    # Call job() directly to avoid threading complexity in test.

    # We need to patch 'plt.savefig' and 'torch.save' to avoid file writes
    # Also patch validate_type to skip type checking for mocks
    with (
        patch("matplotlib.pyplot.savefig"),
        patch("torch.save"),
        patch("numpy.savetxt"),
        patch("os.makedirs"),
        patch("XBrainLab.backend.training.training_plan.validate_type"),
    ):
        plan_holder = TrainingPlanHolder(holder, dataset_mock, option, saliency_params)
        trainer = Trainer([plan_holder])
        trainer.job()

        # 7. Verify Results
        # Check if training record exists
        assert len(plan_holder.train_record_list) == 1
        record = plan_holder.train_record_list[0]

        # Check if metrics are recorded
        # TrainRecord stores metrics in .train dictionary with keys from RecordKey
        # We need to import RecordKey or check string keys if they are strings
        assert RecordKey.LOSS in record.train
        assert RecordKey.ACC in record.train
        assert RecordKey.AUC in record.train

        # Check if evaluation record exists
        assert record.eval_record is not None

        # Check if model state dict is saved (mocked)
        # We can check if torch.save was called

        print("Pipeline integration test passed!")


if __name__ == "__main__":
    test_pipeline_integration()
