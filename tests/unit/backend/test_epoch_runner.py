"""Unit tests for :class:`~XBrainLab.backend.training.epoch_runner.EpochRunner`."""

from __future__ import annotations

import threading
from inspect import signature
from unittest.mock import MagicMock, patch

import torch
from torch.utils.data import DataLoader, TensorDataset

from XBrainLab.backend.training.epoch_runner import EpochRunner
from XBrainLab.backend.training.evaluator import Evaluator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_loader(n_samples: int = 8, n_features: int = 4, n_classes: int = 2):
    """Create a tiny DataLoader for testing."""
    X = torch.randn(n_samples, n_features)
    y = torch.randint(0, n_classes, (n_samples,))
    ds = TensorDataset(X, y)
    return DataLoader(ds, batch_size=4)


def _make_simple_model(n_features: int = 4, n_classes: int = 2):
    """Return a trivial linear model."""
    return torch.nn.Linear(n_features, n_classes)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEpochRunner:
    """Validates the extracted epoch runner."""

    def test_run_completes_without_error(self):
        """A basic training epoch should complete successfully."""
        interrupt = threading.Event()
        runner = EpochRunner(interrupt=interrupt)

        model = _make_simple_model()
        loader = _make_loader()
        optimizer = torch.optim.SGD(model.parameters(), lr=0.01)
        criterion = torch.nn.CrossEntropyLoss()
        record = MagicMock()
        record.get_epoch.return_value = 1

        runner.run(
            model,
            loader,
            None,
            optimizer,
            criterion,
            record,
            torch.nn.CrossEntropyLoss(),
        )

        record.update_train.assert_called_once()
        record.update_statistic.assert_called_once()
        record.step.assert_called_once()

    def test_interrupt_stops_training(self):
        """Setting the interrupt event should abort the batch loop."""
        interrupt = threading.Event()
        interrupt.set()  # pre-set → should bail out immediately
        runner = EpochRunner(interrupt=interrupt)

        model = _make_simple_model()
        loader = _make_loader()
        optimizer = torch.optim.SGD(model.parameters(), lr=0.01)
        criterion = torch.nn.CrossEntropyLoss()
        record = MagicMock()

        runner.run(
            model,
            loader,
            None,
            optimizer,
            criterion,
            record,
            torch.nn.CrossEntropyLoss(),
        )

        # Should have returned early — no record updates
        record.update_train.assert_not_called()
        record.step.assert_not_called()

    def test_validation_loader_triggers_eval(self):
        """Providing a val_loader should invoke Evaluator.evaluate_metrics."""
        interrupt = threading.Event()
        runner = EpochRunner(interrupt=interrupt)

        model = _make_simple_model()
        train_loader = _make_loader()
        val_loader = _make_loader()
        optimizer = torch.optim.SGD(model.parameters(), lr=0.01)
        criterion = torch.nn.CrossEntropyLoss()
        record = MagicMock()
        record.get_epoch.return_value = 1

        with (
            patch.object(Evaluator, "compute_auc", return_value=0.5),
            patch.object(
                Evaluator,
                "evaluate_metrics",
                return_value={"loss": 0.1, "accuracy": 90.0, "auc": 0.5},
            ) as test_model,
        ):
            validation_criterion = torch.nn.CrossEntropyLoss()
            runner.run(
                model,
                train_loader,
                val_loader,
                optimizer,
                criterion,
                record,
                validation_criterion,
            )
            test_model.assert_called_once()
            assert test_model.call_args.args[2] is validation_criterion
            record.update_validation.assert_called_once()

    def test_checkpoint_called_at_interval(self):
        """Checkpoint should be exported when epoch matches interval."""
        interrupt = threading.Event()
        runner = EpochRunner(interrupt=interrupt, checkpoint_epoch=2)

        model = _make_simple_model()
        loader = _make_loader()
        optimizer = torch.optim.SGD(model.parameters(), lr=0.01)
        criterion = torch.nn.CrossEntropyLoss()
        record = MagicMock()
        record.get_epoch.return_value = 2  # divisible by 2

        with patch.object(Evaluator, "compute_auc", return_value=0.5):
            runner.run(
                model,
                loader,
                None,
                optimizer,
                criterion,
                record,
                torch.nn.CrossEntropyLoss(),
            )

        record.export_checkpoint.assert_called_once()

    def test_no_checkpoint_when_disabled(self):
        """Checkpoint should not be called when checkpoint_epoch is 0."""
        interrupt = threading.Event()
        runner = EpochRunner(interrupt=interrupt, checkpoint_epoch=0)

        model = _make_simple_model()
        loader = _make_loader()
        optimizer = torch.optim.SGD(model.parameters(), lr=0.01)
        criterion = torch.nn.CrossEntropyLoss()
        record = MagicMock()
        record.get_epoch.return_value = 10

        with patch.object(Evaluator, "compute_auc", return_value=0.5):
            runner.run(
                model,
                loader,
                None,
                optimizer,
                criterion,
                record,
                torch.nn.CrossEntropyLoss(),
            )

        record.export_checkpoint.assert_not_called()

    def test_public_api_does_not_accept_test_loader(self):
        """Epoch-level checkpoint selection must never inspect the test split."""
        assert "test_loader" not in signature(EpochRunner.run).parameters
        assert (
            signature(EpochRunner.run).parameters["validation_criterion"].default
            is signature(EpochRunner.run).empty
        )

    def test_run_does_not_flush_cuda_allocator_after_each_epoch(self):
        """Allocator cache is retained between epochs and cleared at run boundaries."""
        interrupt = threading.Event()
        runner = EpochRunner(interrupt=interrupt)
        model = _make_simple_model()
        loader = _make_loader()
        optimizer = torch.optim.SGD(model.parameters(), lr=0.01)
        criterion = torch.nn.CrossEntropyLoss()
        record = MagicMock()
        record.get_epoch.return_value = 1

        with patch(
            "XBrainLab.backend.training.epoch_runner.torch.cuda.empty_cache"
        ) as empty_cache:
            runner.run(
                model,
                loader,
                None,
                optimizer,
                criterion,
                record,
                torch.nn.CrossEntropyLoss(),
            )

        empty_cache.assert_not_called()
