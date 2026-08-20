"""Trainer/model integration smokes on a real MNE-backed Dataset.

These tests intentionally construct epochs and split masks directly. They prove
real model execution and metrics, not the user-facing import-to-visualization
command workflow.
"""

from types import SimpleNamespace
from unittest.mock import patch

import mne
import numpy as np
import pytest
import torch

from XBrainLab.backend.application.evaluation_render import (
    EvaluationPlanIdentity,
    EvaluationRunIdentity,
    EvaluationSummaryIdentity,
    build_evaluation_model_summary,
)
from XBrainLab.backend.dataset import Dataset, DataSplittingConfig, Epochs, TrainingType
from XBrainLab.backend.load_data import Raw
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
    """Create a real tiny Dataset with mutually exclusive split masks."""
    n_trials, n_channels, n_samples, n_classes = 12, 4, 168, 2
    rng = np.random.default_rng(0)
    X = rng.standard_normal((n_trials, n_channels, n_samples)).astype(np.float32)
    y = np.arange(n_trials, dtype=int) % n_classes
    events = np.column_stack(
        (np.arange(n_trials), np.zeros(n_trials, dtype=int), y),
    )
    info = mne.create_info(
        [f"EEG-{index}" for index in range(n_channels)],
        sfreq=128,
        ch_types="eeg",
    )
    mne_epochs = mne.EpochsArray(
        X,
        info,
        events=events,
        event_id={"class-0": 0, "class-1": 1},
        verbose=False,
    )
    epoch_data = Epochs([Raw("tiny-synthetic-epo.fif", mne_epochs)])
    config = DataSplittingConfig(TrainingType.FULL, False, [], [])
    dataset = Dataset(epoch_data, config)
    dataset.set_name("tiny-synthetic")
    dataset.train_mask[:8] = True
    dataset.val_mask[8:10] = True
    dataset.test_mask[10:] = True
    dataset.remaining_mask[:] = False

    split_indices = (
        set(dataset.get_training_indices()),
        set(dataset.get_val_indices()),
        set(dataset.get_test_indices()),
    )
    assert split_indices[0].isdisjoint(split_indices[1])
    assert split_indices[0].isdisjoint(split_indices[2])
    assert split_indices[1].isdisjoint(split_indices[2])
    assert set.union(*split_indices) == set(range(n_trials))
    assert np.all(
        np.count_nonzero(
            np.stack((dataset.train_mask, dataset.val_mask, dataset.test_mask)),
            axis=0,
        )
        == 1,
    )

    return dataset, n_classes, n_channels, n_samples


class TestTrainerModelIntegration:
    """Focused trainer/evaluation integration on real Dataset objects."""

    @pytest.fixture
    def synthetic_dataset(self):
        """Create a tiny real Dataset with deterministic synthetic samples."""
        return _make_synthetic_dataset()

    def test_train_and_evaluate_metrics(self, synthetic_dataset, tmp_path):
        """Real EEGNet execution produces finite training and evaluation records."""
        dataset, _n_classes, _n_channels, _n_samples = synthetic_dataset

        holder = ModelHolder(EEGNet, {}, None)
        option = TrainingOption(
            output_dir=str(tmp_path / "training-output"),
            optim=torch.optim.Adam,
            optim_params={},
            use_cpu=True,
            gpu_idx=None,
            epoch=2,
            bs=2,
            lr=0.001,
            checkpoint_epoch=1,
            evaluation_option=TrainingEvaluation.VAL_ACC,
            repeat_num=1,
        )

        with (
            patch("matplotlib.pyplot.savefig"),
            patch("torch.save"),
            patch("numpy.savetxt"),
            patch("os.makedirs"),
        ):
            plan = TrainingPlanHolder(holder, dataset, option, {})
            trainer = Trainer([plan])
            trainer.job()

            assert len(plan.train_record_list) == 1
            record = plan.train_record_list[0]

            # Metrics should exist
            assert RecordKey.LOSS in record.train
            assert RecordKey.ACC in record.train
            assert RecordKey.AUC in record.train

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

            aucs = record.train[RecordKey.AUC]
            assert len(aucs) == 2
            assert all(np.isfinite(auc) for auc in aucs)

            # Eval record should exist
            assert record.eval_record is not None

            plan_identity = EvaluationPlanIdentity(plan_index=0)
            summary = build_evaluation_model_summary(
                SimpleNamespace(training_plan_holders=lambda: (plan,)),
                EvaluationSummaryIdentity(
                    plan=plan_identity,
                    run=EvaluationRunIdentity(plan=plan_identity, run_index=0),
                ),
            )
            assert "=== Run: Repeat-0 ===" in summary
            assert "EEGNet" in summary
            assert "Total params" in summary

    def test_sccnet_model(self, synthetic_dataset, tmp_path):
        """Pipeline also works with SCCNet model."""
        from XBrainLab.backend.model_base import SCCNet

        dataset, _n_classes, _n_channels, _n_samples = synthetic_dataset

        holder = ModelHolder(SCCNet, {}, None)
        option = TrainingOption(
            output_dir=str(tmp_path / "training-output"),
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

    def test_two_repeats(self, tmp_path):
        """Training with repeat_num=2 produces two records."""
        dataset, _n_cls, _n_ch, _n_samp = _make_synthetic_dataset()

        holder = ModelHolder(EEGNet, {}, None)
        option = TrainingOption(
            output_dir=str(tmp_path / "training-output"),
            optim=torch.optim.Adam,
            optim_params={},
            use_cpu=True,
            gpu_idx=None,
            epoch=1,
            bs=2,
            lr=0.001,
            checkpoint_epoch=1,
            evaluation_option=TrainingEvaluation.VAL_ACC,
            repeat_num=2,
        )

        with (
            patch("matplotlib.pyplot.savefig"),
            patch("torch.save"),
            patch("numpy.savetxt"),
            patch("os.makedirs"),
        ):
            plan = TrainingPlanHolder(holder, dataset, option, {})
            trainer = Trainer([plan])
            trainer.job()

            assert len(plan.train_record_list) == 2
            for record in plan.train_record_list:
                assert RecordKey.LOSS in record.train
                assert record.eval_record is not None
