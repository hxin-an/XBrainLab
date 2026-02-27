"""Unit tests for :class:`~XBrainLab.backend.training.epoch_runner.EpochRunner`."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import torch
from torch.utils.data import DataLoader, TensorDataset

from XBrainLab.backend.training.epoch_runner import EpochRunner

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

        runner.run(model, loader, None, None, optimizer, criterion, record)

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

        runner.run(model, loader, None, None, optimizer, criterion, record)

        # Should have returned early — no record updates
        record.update_train.assert_not_called()
        record.step.assert_not_called()

    def test_validation_loader_triggers_eval(self):
        """Providing a val_loader should invoke Evaluator.test_model."""
        interrupt = threading.Event()
        runner = EpochRunner(interrupt=interrupt)

        model = _make_simple_model()
        train_loader = _make_loader()
        val_loader = _make_loader()
        optimizer = torch.optim.SGD(model.parameters(), lr=0.01)
        criterion = torch.nn.CrossEntropyLoss()
        record = MagicMock()
        record.get_epoch.return_value = 1

        with patch("XBrainLab.backend.training.epoch_runner.Evaluator") as mock_eval:
            mock_eval.compute_auc.return_value = 0.5
            mock_eval.test_model.return_value = {"loss": 0.1, "acc": 90.0}
            runner.run(
                model, train_loader, val_loader, None, optimizer, criterion, record
            )
            mock_eval.test_model.assert_called_once()
            record.update_eval.assert_called_once()

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

        with patch("XBrainLab.backend.training.epoch_runner.Evaluator") as mock_eval:
            mock_eval.compute_auc.return_value = 0.5
            runner.run(model, loader, None, None, optimizer, criterion, record)

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

        with patch("XBrainLab.backend.training.epoch_runner.Evaluator") as mock_eval:
            mock_eval.compute_auc.return_value = 0.5
            runner.run(model, loader, None, None, optimizer, criterion, record)

        record.export_checkpoint.assert_not_called()
