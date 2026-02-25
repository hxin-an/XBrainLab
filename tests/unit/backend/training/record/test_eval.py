import os
from unittest.mock import patch

import numpy as np
import pytest

from XBrainLab.backend.training.record.eval import EvalRecord, calculate_confusion


@pytest.mark.parametrize(
    "output, label, expected",
    [
        (
            np.array([[0.1, 0.2, 0.7], [0.3, 0.4, 0.3], [0.5, 0.2, 0.3]]),
            np.array([2, 1, 0]),
            np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]]),
        ),
        (
            np.array([[0.1, 0.2, 0.7], [0.3, 0.4, 0.3], [0.5, 0.2, 0.3]]),
            np.array([0, 1, 2]),
            np.array([[0, 0, 1], [0, 1, 0], [1, 0, 0]]),
        ),
        (
            np.array(
                [[0.1, 0.2, 0.7], [0.1, 0.2, 0.7], [0.3, 0.4, 0.3], [0.5, 0.2, 0.3]]
            ),
            np.array([2, 2, 1, 0]),
            np.array([[1, 0, 0], [0, 1, 0], [0, 0, 2]]),
        ),
        (
            np.array(
                [[0.9, 0.2, 0.7], [0.1, 0.2, 0.7], [0.3, 0.4, 0.3], [0.5, 0.2, 0.3]]
            ),
            np.array([2, 2, 1, 0]),
            np.array([[1, 0, 0], [0, 1, 0], [1, 0, 1]]),
        ),
    ],
)
def test_calculate_confusion(output, label, expected):
    confusion = calculate_confusion(output, label)
    assert confusion.shape == (3, 3)
    assert (confusion == expected).all()


@pytest.mark.parametrize(
    "label, output, expected",
    [
        (
            np.array([0, 1, 2]),
            np.array([[0.1, 0.2, 0.7], [0.3, 0.4, 0.3], [0.5, 0.2, 0.3]]),
            1 / 3,
        ),
        (
            np.array([0, 1, 2]),
            np.array([[0.9, 0.2, 0.7], [0.3, 0.4, 0.3], [0.5, 0.2, 0.3]]),
            2 / 3,
        ),
        (
            np.array([0, 1, 0]),
            np.array([[0.9, 0.2, 0.7], [0.3, 0.4, 0.3], [0.5, 0.2, 0.3]]),
            3 / 3,
        ),
    ],
)
def test_acc(label, output, expected):
    gradient = {}
    eval_record = EvalRecord(label, output, gradient, {}, {}, {}, {})
    assert np.isclose(eval_record.get_acc(), expected)


@pytest.mark.parametrize(
    "value, expected",
    [
        (np.array([[25, 15], [5, 55]]), 0.5652173913043478),
        (np.array([[45, 15], [25, 15]]), 0.13043478260869554),
    ],
)
def test_kappa(value, expected):
    with patch(
        "XBrainLab.backend.training.record.eval.calculate_confusion", return_value=value
    ):
        assert np.isclose(EvalRecord([], [], {}, {}, {}, {}, {}).get_kappa(), expected)


@pytest.mark.xfail
@pytest.mark.parametrize(
    "label, output, expected",
    [
        (None, None, None),
    ],
)
def test_auc(label, output, expected):
    raise NotImplementedError


def test_export():
    with patch("torch.save") as torch_mock:
        gradient = {"123": "test"}
        label = [1, 2]
        output = [1]
        eval_record = EvalRecord(label, output, gradient, {}, {}, {}, {})
        eval_record.export("target_path")
        torch_mock.assert_called_once_with(
            {
                "label": label,
                "output": output,
                "gradient": gradient,
                "gradient_input": {},
                "smoothgrad": {},
                "smoothgrad_sq": {},
                "vargrad": {},
            },
            os.path.join("target_path", "eval"),
        )


def test_export_csv(tmp_path):
    csv_file = str(tmp_path / "output.csv")
    gradient = {"123": "test"}
    label = [1, 2]
    output = np.array([[0, 1], [1, 0]])
    eval_record = EvalRecord(label, output, gradient, {}, {}, {}, {})
    eval_record.export_csv(csv_file)
    assert os.path.exists(csv_file)

    with open(csv_file) as f:
        assert f.readline() == "0,1,ground_truth,predict\n"
        assert [float(i) for i in f.readline().split(",")] == [0, 1, 1, 1]
        assert [float(i) for i in f.readline().split(",")] == [1, 0, 2, 0]
