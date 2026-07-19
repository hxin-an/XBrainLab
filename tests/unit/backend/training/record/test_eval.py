import os
from unittest.mock import patch

import numpy as np
import pytest

from XBrainLab.backend.training.record.eval import (
    EvalRecord,
    SaliencyArtifactContext,
    SaliencyProducerIdentity,
    calculate_confusion,
)


def _saliency_context() -> SaliencyArtifactContext:
    producer_identity = SaliencyProducerIdentity.from_components(
        dataset={"name": "test"},
        split={"name": "test"},
        run={"name": "test"},
        model={"name": "test"},
    )
    return SaliencyArtifactContext(
        class_map=(("123", "test"),),
        channel_names=("Cz",),
        sampling_frequency_hz=1.0,
        epoch_start_seconds=0.0,
        epoch_end_seconds=0.0,
        epoch_sample_count=1,
        montage_fingerprint=None,
        epoch_data_fingerprint=producer_identity.dataset_fingerprint,
        producer_identity=producer_identity,
    )


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


@pytest.mark.parametrize(
    "label, output, expected",
    [
        ([], [], None),
        ([0, 0], [[0.9, 0.1], [0.8, 0.2]], None),
        ([0, 1], [[0.9, 0.1, 0.0], [0.2, 0.8, 0.0]], None),
        ([0, 1], [[0.9, 0.1], [0.2, 0.8]], 1.0),
    ],
)
def test_auc(label, output, expected):
    result = EvalRecord(label, output, {}, {}, {}, {}, {}).get_auc()
    if expected is None:
        assert result is None
    else:
        assert np.isclose(result, expected)


def test_export():
    with patch("torch.save") as torch_mock:
        gradient = {0: np.array([1.0], dtype=np.float32)}
        label = [1, 2]
        output = [1]
        eval_record = EvalRecord(
            label,
            output,
            gradient,
            {},
            {},
            {},
            {},
            evaluation_split="test",
            saliency_context=_saliency_context(),
        )
        eval_record.export("target_path")
        torch_mock.assert_called_once()
        payload, path = torch_mock.call_args.args
        assert path == os.path.join("target_path", "eval")
        assert payload["artifact_schema_version"] == 4
        assert payload["label"] == label
        assert payload["output"] == output
        assert payload["gradient"] == gradient
        assert payload["evaluation_split"] == "test"
        assert payload["saliency_context"] == _saliency_context().to_payload()
        assert payload["saliency_integrity_manifest"]["manifest_sha256"]


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
