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
        assert Evaluator.compute_auc(None, None) is None

    def test_returns_none_when_auc_is_undefined(self):
        # A single-class split cannot define ROC AUC and must not rank checkpoints.
        y_true = np.array([0, 0, 0])
        y_pred = np.array([[0.9, 0.1], [0.8, 0.2], [0.7, 0.3]])
        auc = Evaluator.compute_auc(y_true, y_pred)
        assert auc is None

    @pytest.mark.parametrize("invalid", [np.nan, np.inf])
    def test_rejects_nonfinite_predictions(self, invalid):
        y_true = np.array([0, 1, 0, 1])
        y_pred = np.array(
            [[0.9, 0.1], [0.2, 0.8], [0.7, 0.3], [0.1, invalid]],
        )

        with pytest.raises(
            ValueError,
            match="AUC prediction array contains NaN or infinite values",
        ):
            Evaluator.compute_auc(y_true, y_pred)


class TestEvaluateMetrics:
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
        result = Evaluator.evaluate_metrics(model, loader, criterion)

        assert isinstance(result, dict)
        assert RecordKey.ACC in result
        assert RecordKey.AUC in result
        assert RecordKey.LOSS in result

    def test_accuracy_range(self, simple_model_and_loader):
        model, loader = simple_model_and_loader
        criterion = torch.nn.CrossEntropyLoss()
        result = Evaluator.evaluate_metrics(model, loader, criterion)
        assert 0.0 <= result[RecordKey.ACC] <= 100.0

    def test_loss_nonnegative(self, simple_model_and_loader):
        model, loader = simple_model_and_loader
        criterion = torch.nn.CrossEntropyLoss()
        result = Evaluator.evaluate_metrics(model, loader, criterion)
        assert result[RecordKey.LOSS] >= 0.0

    def test_loss_is_weighted_by_sample_count_for_uneven_batches(self):
        logits = torch.tensor(
            [[4.0, 0.0], [3.0, 0.0], [0.0, 4.0]],
            dtype=torch.float32,
        )
        labels = torch.tensor([0, 0, 0], dtype=torch.long)
        loader = torch.utils.data.DataLoader(
            torch.utils.data.TensorDataset(logits, labels),
            batch_size=2,
            shuffle=False,
        )

        result = Evaluator.evaluate_metrics(
            torch.nn.Identity(),
            loader,
            torch.nn.CrossEntropyLoss(),
        )

        expected = torch.nn.functional.cross_entropy(logits, labels).item()
        assert result[RecordKey.LOSS] == pytest.approx(expected)

    def test_empty_loader(self):
        model = torch.nn.Linear(4, 2)
        empty_dataset = torch.utils.data.TensorDataset(
            torch.empty(0, 4), torch.empty(0, dtype=torch.long)
        )
        loader = torch.utils.data.DataLoader(empty_dataset, batch_size=1)
        criterion = torch.nn.CrossEntropyLoss()
        result = Evaluator.evaluate_metrics(model, loader, criterion)
        assert result[RecordKey.ACC] == 0
        assert result[RecordKey.AUC] is None
        assert result[RecordKey.LOSS] == 0

    def test_rejects_nonfinite_model_outputs(self):
        class NonFiniteModel(torch.nn.Module):
            def forward(self, inputs):
                return torch.full((len(inputs), 2), torch.nan)

        loader = torch.utils.data.DataLoader(
            torch.utils.data.TensorDataset(
                torch.ones((4, 3)),
                torch.tensor([0, 1, 0, 1]),
            ),
            batch_size=2,
        )

        with pytest.raises(
            ValueError,
            match="Evaluation model output contains NaN or infinite values",
        ):
            Evaluator.evaluate_metrics(
                NonFiniteModel(),
                loader,
                torch.nn.CrossEntropyLoss(),
            )


def test_evaluate_rejects_nonfinite_model_outputs():
    class NonFiniteModel(torch.nn.Module):
        def forward(self, inputs):
            return torch.full((len(inputs), 2), torch.inf)

    loader = torch.utils.data.DataLoader(
        torch.utils.data.TensorDataset(
            torch.ones((2, 3)),
            torch.tensor([0, 1]),
        ),
        batch_size=2,
    )

    with pytest.raises(
        ValueError,
        match="Evaluation model output contains NaN or infinite values",
    ):
        Evaluator.evaluate(NonFiniteModel(), loader, evaluation_split="test")
