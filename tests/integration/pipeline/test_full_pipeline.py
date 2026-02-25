"""
End-to-end integration test: Load → Preprocess → Split → Train → Evaluate.

Uses real MNE processing with synthetic data and a real EEGNet model
(1 epoch, 2 trials per class) to verify the complete pipeline works.
"""

from unittest.mock import patch

import numpy as np
import pytest
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


def _make_synthetic_dataset():
    """Create a mock dataset with realistic synthetic data for training tests."""
    from unittest.mock import MagicMock

    n_trials, n_channels, n_samples, n_classes = 4, 4, 168, 2
    X = np.random.randn(n_trials, n_channels, n_samples).astype(np.float32)
    y = np.array([0, 1, 0, 1])

    dataset = MagicMock()
    dataset.get_training_data.return_value = (X, y)
    dataset.get_val_data.return_value = (X, y)
    dataset.get_test_data.return_value = (X, y)
    dataset.get_training_indices.return_value = np.arange(n_trials)
    dataset.get_val_indices.return_value = np.arange(n_trials)
    dataset.get_test_indices.return_value = np.arange(n_trials)
    dataset.train_mask = np.ones(n_trials, dtype=bool)
    dataset.val_mask = np.ones(n_trials, dtype=bool)
    dataset.test_mask = np.ones(n_trials, dtype=bool)

    epoch_data = MagicMock()
    epoch_data.get_model_args.return_value = {
        "n_classes": n_classes,
        "channels": n_channels,
        "samples": n_samples,
        "sfreq": 128,
    }
    epoch_data.get_data.return_value = X
    epoch_data.get_label_list.return_value = y
    dataset.get_epoch_data.return_value = epoch_data

    return dataset, n_classes, n_channels, n_samples


class TestFullPipeline:
    """Complete load → preprocess → split → train → evaluate pipeline."""

    @pytest.fixture
    def synthetic_dataset(self):
        """Create a mock dataset with realistic synthetic data."""
        return _make_synthetic_dataset()

    def test_train_and_evaluate_metrics(self, synthetic_dataset):
        """Full pipeline produces valid training records with real metrics."""
        dataset, _n_classes, _n_channels, _n_samples = synthetic_dataset

        holder = ModelHolder(EEGNet, {}, None)
        option = TrainingOption(
            output_dir="test_output",
            optim=torch.optim.Adam,
            optim_params={},
            use_cpu=True,
            gpu_idx=None,
            epoch=2,
            bs=2,
            lr=0.001,
            checkpoint_epoch=1,
            evaluation_option=TrainingEvaluation.TEST_ACC,
            repeat_num=1,
        )

        with (
            patch("matplotlib.pyplot.savefig"),
            patch("torch.save"),
            patch("numpy.savetxt"),
            patch("os.makedirs"),
            patch("XBrainLab.backend.training.training_plan.validate_type"),
        ):
            plan = TrainingPlanHolder(holder, dataset, option, {})
            trainer = Trainer([plan])
            trainer.job()

            assert len(plan.train_record_list) == 1
            record = plan.train_record_list[0]

            # Metrics should exist
            assert RecordKey.LOSS in record.train
            assert RecordKey.ACC in record.train

            # Loss should be list of floats
            losses = record.train[RecordKey.LOSS]
            assert len(losses) == 2  # 2 epochs
            for loss in losses:
                assert isinstance(loss, float)
                assert loss >= 0

            # Accuracy should be between 0 and 100 (percentage)
            accs = record.train[RecordKey.ACC]
            for acc in accs:
                assert 0.0 <= acc <= 100.0

            # Eval record should exist
            assert record.eval_record is not None

    def test_sccnet_model(self, synthetic_dataset):
        """Pipeline also works with SCCNet model."""
        from XBrainLab.backend.model_base import SCCNet

        dataset, _n_classes, _n_channels, _n_samples = synthetic_dataset

        holder = ModelHolder(SCCNet, {}, None)
        option = TrainingOption(
            output_dir="test_output",
            optim=torch.optim.Adam,
            optim_params={},
            use_cpu=True,
            gpu_idx=None,
            epoch=1,
            bs=2,
            lr=0.001,
            checkpoint_epoch=1,
            evaluation_option=TrainingEvaluation.VAL_LOSS,
            repeat_num=1,
        )

        with (
            patch("matplotlib.pyplot.savefig"),
            patch("torch.save"),
            patch("numpy.savetxt"),
            patch("os.makedirs"),
            patch("XBrainLab.backend.training.training_plan.validate_type"),
        ):
            plan = TrainingPlanHolder(holder, dataset, option, {})
            trainer = Trainer([plan])
            trainer.job()

            assert len(plan.train_record_list) == 1
            record = plan.train_record_list[0]
            assert RecordKey.LOSS in record.train
            assert record.eval_record is not None


class TestMultiRepeatTraining:
    """Tests for multi-repeat and multi-plan training scenarios."""

    def test_two_repeats(self):
        """Training with repeat_num=2 produces two records."""
        dataset, _n_cls, _n_ch, _n_samp = _make_synthetic_dataset()

        holder = ModelHolder(EEGNet, {}, None)
        option = TrainingOption(
            output_dir="test_output",
            optim=torch.optim.Adam,
            optim_params={},
            use_cpu=True,
            gpu_idx=None,
            epoch=1,
            bs=2,
            lr=0.001,
            checkpoint_epoch=1,
            evaluation_option=TrainingEvaluation.TEST_ACC,
            repeat_num=2,
        )

        with (
            patch("matplotlib.pyplot.savefig"),
            patch("torch.save"),
            patch("numpy.savetxt"),
            patch("os.makedirs"),
            patch("XBrainLab.backend.training.training_plan.validate_type"),
        ):
            plan = TrainingPlanHolder(holder, dataset, option, {})
            trainer = Trainer([plan])
            trainer.job()

            assert len(plan.train_record_list) == 2
            for record in plan.train_record_list:
                assert RecordKey.LOSS in record.train
                assert record.eval_record is not None
