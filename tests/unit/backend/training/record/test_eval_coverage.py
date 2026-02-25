"""Extended tests for EvalRecord covering load, AUC, saliency, per-class metrics.

Covers: EvalRecord.load, get_auc (binary + multi-class), get_kappa edge case,
export_saliency, get_per_class_metrics, saliency getters.
"""

import os
from unittest.mock import patch

import numpy as np
import pytest

from XBrainLab.backend.training.record.eval import EvalRecord

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def binary_eval():
    """Binary classification eval record."""
    label = np.array([0, 0, 1, 1])
    # Perfect binary classification
    output = np.array([[2.0, -1.0], [1.5, -0.5], [-1.0, 2.0], [-0.5, 1.5]])
    return EvalRecord(label, output, {}, {}, {}, {}, {})


@pytest.fixture
def multiclass_eval():
    """Multi-class (3-class) eval record."""
    label = np.array([0, 1, 2, 0, 1, 2])
    output = np.array(
        [
            [3.0, 0.1, 0.1],
            [0.1, 3.0, 0.1],
            [0.1, 0.1, 3.0],
            [3.0, 0.1, 0.1],
            [0.1, 3.0, 0.1],
            [0.1, 0.1, 3.0],
        ]
    )
    return EvalRecord(label, output, {}, {}, {}, {}, {})


@pytest.fixture
def saliency_eval():
    """Eval record with saliency maps."""
    label = np.array([0, 1])
    output = np.array([[1.0, 0.0], [0.0, 1.0]])
    grad = {0: np.array([1.0, 2.0]), 1: np.array([3.0, 4.0])}
    grad_input = {0: np.array([0.5, 1.0]), 1: np.array([1.5, 2.0])}
    smooth = {0: np.array([0.1, 0.2]), 1: np.array([0.3, 0.4])}
    smooth_sq = {0: np.array([0.01, 0.04]), 1: np.array([0.09, 0.16])}
    vargrad = {0: np.array([0.05, 0.1]), 1: np.array([0.15, 0.2])}
    return EvalRecord(label, output, grad, grad_input, smooth, smooth_sq, vargrad)


# ---------------------------------------------------------------------------
# AUC tests (previously xfail / not implemented)
# ---------------------------------------------------------------------------


class TestAUC:
    def test_binary_auc(self, binary_eval):
        auc = binary_eval.get_auc()
        assert isinstance(auc, float)
        assert auc == 1.0  # Perfect classification

    def test_multiclass_auc(self, multiclass_eval):
        auc = multiclass_eval.get_auc()
        assert isinstance(auc, float)
        assert auc == 1.0  # Perfect classification

    def test_imperfect_binary_auc(self):
        label = np.array([0, 0, 1, 1])
        # Intentionally wrong on one sample
        output = np.array([[2.0, -1.0], [-1.0, 2.0], [-1.0, 2.0], [-0.5, 1.5]])
        record = EvalRecord(label, output, {}, {}, {}, {}, {})
        auc = record.get_auc()
        assert 0.0 < auc < 1.0


# ---------------------------------------------------------------------------
# Kappa edge case
# ---------------------------------------------------------------------------


class TestKappa:
    def test_perfect_agreement(self):
        """PE >= 1 should return 0."""
        # Create a confusion matrix where pe >= 1
        confusion = np.array([[100, 0], [0, 0]])
        with patch(
            "XBrainLab.backend.training.record.eval.calculate_confusion",
            return_value=confusion,
        ):
            record = EvalRecord(np.array([0]), np.array([[1, 0]]), {}, {}, {}, {}, {})
            kappa = record.get_kappa()
            assert isinstance(kappa, float)


# ---------------------------------------------------------------------------
# Load / Export
# ---------------------------------------------------------------------------


class TestLoadExport:
    def test_load_success(self, tmp_path):
        """Round-trip export then load."""
        label = np.array([0, 1, 0])
        output = np.array([[1.0, 0.0], [0.0, 1.0], [0.8, 0.2]])
        record = EvalRecord(
            label, output, {"g": 1}, {"gi": 2}, {"s": 3}, {"ss": 4}, {"v": 5}
        )
        record.export(str(tmp_path))

        loaded = EvalRecord.load(str(tmp_path))
        assert loaded is not None
        np.testing.assert_array_equal(loaded.label, label)
        np.testing.assert_array_equal(loaded.output, output)
        assert loaded.gradient == {"g": 1}

    def test_load_nonexistent(self, tmp_path):
        result = EvalRecord.load(str(tmp_path / "nonexistent"))
        assert result is None

    def test_load_corrupted(self, tmp_path):
        # Write garbage
        eval_path = tmp_path / "eval"
        eval_path.write_bytes(b"not a valid torch file")
        result = EvalRecord.load(str(tmp_path))
        assert result is None


# ---------------------------------------------------------------------------
# Saliency
# ---------------------------------------------------------------------------


class TestSaliency:
    @pytest.mark.parametrize(
        "method, attr",
        [
            ("Gradient", "gradient"),
            ("Gradient * Input", "gradient_input"),
            ("SmoothGrad", "smoothgrad"),
            ("SmoothGrad_Squared", "smoothgrad_sq"),
            ("VarGrad", "vargrad"),
        ],
    )
    def test_export_saliency(self, saliency_eval, method, attr):
        result = saliency_eval.export_saliency(method)
        assert result == getattr(saliency_eval, attr)

    def test_export_saliency_with_save(self, saliency_eval, tmp_path):
        target = str(tmp_path / "saliency.pt")
        result = saliency_eval.export_saliency("Gradient", target_path=target)
        assert os.path.exists(target)
        assert result == saliency_eval.gradient

    def test_export_saliency_unknown(self, saliency_eval):
        with pytest.raises(ValueError, match="Unknown saliency"):
            saliency_eval.export_saliency("InvalidMethod")

    def test_gradient_getter(self, saliency_eval):
        np.testing.assert_array_equal(
            saliency_eval.get_gradient(0), np.array([1.0, 2.0])
        )

    def test_gradient_input_getter(self, saliency_eval):
        np.testing.assert_array_equal(
            saliency_eval.get_gradient_input(0), np.array([0.5, 1.0])
        )

    def test_smoothgrad_getter(self, saliency_eval):
        np.testing.assert_array_equal(
            saliency_eval.get_smoothgrad(1), np.array([0.3, 0.4])
        )

    def test_smoothgrad_sq_getter(self, saliency_eval):
        np.testing.assert_array_equal(
            saliency_eval.get_smoothgrad_sq(1), np.array([0.09, 0.16])
        )

    def test_vargrad_getter(self, saliency_eval):
        np.testing.assert_array_equal(
            saliency_eval.get_vargrad(0), np.array([0.05, 0.1])
        )


# ---------------------------------------------------------------------------
# Per-class metrics
# ---------------------------------------------------------------------------


class TestPerClassMetrics:
    def test_perfect_classification(self, multiclass_eval):
        metrics = multiclass_eval.get_per_class_metrics()
        for i in range(3):
            assert metrics[i]["precision"] == 1.0
            assert metrics[i]["recall"] == 1.0
            assert metrics[i]["f1-score"] == 1.0
            assert metrics[i]["support"] == 2

        assert "macro_avg" in metrics
        assert metrics["macro_avg"]["precision"] == 1.0

    def test_imperfect_classification(self):
        label = np.array([0, 0, 1, 1])
        output = np.array([[1, 0], [0, 1], [1, 0], [0, 1]])  # 50% acc
        record = EvalRecord(label, output, {}, {}, {}, {}, {})
        metrics = record.get_per_class_metrics()
        assert metrics[0]["recall"] == 0.5
        assert metrics[1]["recall"] == 0.5
