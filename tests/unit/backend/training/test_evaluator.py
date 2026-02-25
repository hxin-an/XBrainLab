"""Unit tests for training/evaluator — AUC computation and model testing."""

import numpy as np
import pytest
import torch

from XBrainLab.backend.training.evaluator import Evaluator
from XBrainLab.backend.training.record.key import RecordKey


class TestComputeAuc:
    def test_binary_auc(self):
        y_true = np.array([0, 0, 1, 1])
        y_pred = np.array([[0.9, 0.1], [0.8, 0.2], [0.2, 0.8], [0.1, 0.9]])
        auc = Evaluator.compute_auc(y_true, y_pred)
        assert 0.9 <= auc <= 1.0

    def test_multiclass_auc(self):
        y_true = np.array([0, 1, 2, 0, 1, 2])
        y_pred = np.array(
            [
                [0.8, 0.1, 0.1],
                [0.1, 0.8, 0.1],
                [0.1, 0.1, 0.8],
                [0.7, 0.2, 0.1],
                [0.2, 0.7, 0.1],
                [0.1, 0.2, 0.7],
            ]
        )
        auc = Evaluator.compute_auc(y_true, y_pred)
        assert 0.0 <= auc <= 1.0

    def test_tensor_inputs(self):
        y_true = torch.tensor([0, 1, 0, 1])
        y_pred = torch.tensor([[0.9, 0.1], [0.2, 0.8], [0.7, 0.3], [0.1, 0.9]])
        auc = Evaluator.compute_auc(y_true, y_pred)
        assert 0.9 <= auc <= 1.0

    def test_none_inputs(self):
        assert Evaluator.compute_auc(None, None) == 0.0

    def test_returns_zero_on_failure(self):
        # Single class — roc_auc_score would fail; fallback must return 0.0
        y_true = np.array([0, 0, 0])
        y_pred = np.array([[0.9, 0.1], [0.8, 0.2], [0.7, 0.3]])
        auc = Evaluator.compute_auc(y_true, y_pred)
        assert auc == 0.0


class TestTestModel:
    @pytest.fixture
    def simple_model_and_loader(self):
        """Create a simple linear model and data loader for testing."""
        model = torch.nn.Linear(4, 2)
        model.eval()

        x = torch.randn(20, 4)
        y = torch.randint(0, 2, (20,))
        dataset = torch.utils.data.TensorDataset(x, y)
        loader = torch.utils.data.DataLoader(dataset, batch_size=10)

        return model, loader

    def test_returns_dict_with_keys(self, simple_model_and_loader):
        model, loader = simple_model_and_loader
        criterion = torch.nn.CrossEntropyLoss()
        result = Evaluator.test_model(model, loader, criterion)

        assert isinstance(result, dict)
        assert RecordKey.ACC in result
        assert RecordKey.AUC in result
        assert RecordKey.LOSS in result

    def test_accuracy_range(self, simple_model_and_loader):
        model, loader = simple_model_and_loader
        criterion = torch.nn.CrossEntropyLoss()
        result = Evaluator.test_model(model, loader, criterion)
        assert 0.0 <= result[RecordKey.ACC] <= 100.0

    def test_loss_nonnegative(self, simple_model_and_loader):
        model, loader = simple_model_and_loader
        criterion = torch.nn.CrossEntropyLoss()
        result = Evaluator.test_model(model, loader, criterion)
        assert result[RecordKey.LOSS] >= 0.0

    def test_empty_loader(self):
        model = torch.nn.Linear(4, 2)
        empty_dataset = torch.utils.data.TensorDataset(
            torch.empty(0, 4), torch.empty(0, dtype=torch.long)
        )
        loader = torch.utils.data.DataLoader(empty_dataset, batch_size=1)
        criterion = torch.nn.CrossEntropyLoss()
        result = Evaluator.test_model(model, loader, criterion)
        assert result[RecordKey.ACC] == 0
        assert result[RecordKey.AUC] == 0
        assert result[RecordKey.LOSS] == 0
