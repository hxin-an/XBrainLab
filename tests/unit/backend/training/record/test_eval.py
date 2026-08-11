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


def _complete_saliency_context() -> SaliencyArtifactContext:
    producer_identity = SaliencyProducerIdentity.from_components(
        dataset={"name": "saliency-methods"},
        split={"name": "saliency-methods"},
        run={"name": "saliency-methods"},
        model={"name": "saliency-methods"},
    )
    return SaliencyArtifactContext(
        class_map=((0, "class 0"), (1, "class 1")),
        channel_names=("Cz",),
        sampling_frequency_hz=1.0,
        epoch_start_seconds=0.0,
        epoch_end_seconds=1.0,
        epoch_sample_count=2,
        montage_fingerprint=None,
        epoch_data_fingerprint=producer_identity.dataset_fingerprint,
        producer_identity=producer_identity,
    )


@pytest.fixture
def saliency_eval_record() -> EvalRecord:
    return EvalRecord(
        np.array([0, 1]),
        np.array([[1.0, 0.0], [0.0, 1.0]]),
        {0: np.array([1.0, 2.0]), 1: np.array([3.0, 4.0])},
        {0: np.array([0.5, 1.0]), 1: np.array([1.5, 2.0])},
        {0: np.array([0.1, 0.2]), 1: np.array([0.3, 0.4])},
        {0: np.array([0.01, 0.04]), 1: np.array([0.09, 0.16])},
        {0: np.array([0.05, 0.1]), 1: np.array([0.15, 0.2])},
        saliency_context=_complete_saliency_context(),
        saliency_method_parameters={
            "Gradient": {},
            "Gradient * Input": {},
            "SmoothGrad": {},
            "SmoothGrad_Squared": {},
            "VarGrad": {},
        },
        saliency_noise_seeds={
            "SmoothGrad": 1,
            "SmoothGrad_Squared": 1,
            "VarGrad": 1,
        },
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


@pytest.mark.parametrize(
    ("label", "output", "expected"),
    [
        (
            np.array([0, 1, 2, 0, 1, 2]),
            np.array(
                [
                    [3.0, 0.1, 0.1],
                    [0.1, 3.0, 0.1],
                    [0.1, 0.1, 3.0],
                    [3.0, 0.1, 0.1],
                    [0.1, 3.0, 0.1],
                    [0.1, 0.1, 3.0],
                ]
            ),
            1.0,
        ),
        (
            np.array([0, 0, 1, 1]),
            np.array([[2.0, -1.0], [-1.0, 2.0], [-1.0, 2.0], [-0.5, 1.5]]),
            0.625,
        ),
    ],
    ids=("perfect-multiclass", "imperfect-binary"),
)
def test_auc_uses_class_scores_for_binary_and_multiclass_rankings(
    label,
    output,
    expected,
):
    record = EvalRecord(label, output, {}, {}, {}, {}, {})

    assert np.isclose(record.get_auc(), expected)


def test_kappa_returns_zero_when_expected_agreement_is_one():
    confusion = np.array([[100, 0], [0, 0]])
    with patch(
        "XBrainLab.backend.training.record.eval.calculate_confusion",
        return_value=confusion,
    ):
        record = EvalRecord(np.array([0]), np.array([[1, 0]]), {}, {}, {}, {}, {})

        assert record.get_kappa() == 0.0


def test_export(tmp_path):
    gradient = {0: np.array([1.0], dtype=np.float32)}
    label = np.array([1, 2])
    output = np.array([1])
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

    eval_record.export(str(tmp_path))

    assert os.path.exists(tmp_path / "eval")
    assert os.path.exists(tmp_path / "eval.npz")
    loaded = EvalRecord.load(str(tmp_path))
    assert loaded is not None
    np.testing.assert_array_equal(loaded.label, label)
    np.testing.assert_array_equal(loaded.output, output)
    np.testing.assert_array_equal(loaded.gradient[0], gradient[0])
    assert loaded.evaluation_split == "test"
    assert loaded.saliency_context == _saliency_context()
    assert loaded.saliency_integrity_manifest is not None
    assert loaded.saliency_integrity_manifest["manifest_sha256"]


def test_export_supports_a_named_prediction_split_artifact(tmp_path) -> None:
    record = EvalRecord(
        np.array([0, 1]),
        np.array([[0.8, 0.2], [0.1, 0.9]]),
        {},
        {},
        {},
        {},
        {},
        evaluation_split="validation",
    )

    record.export(str(tmp_path), artifact_basename="eval-validation")
    loaded = EvalRecord.load(
        str(tmp_path),
        artifact_basename="eval-validation",
    )

    assert loaded is not None
    assert loaded.evaluation_split == "validation"
    assert (tmp_path / "eval-validation").exists()
    assert (tmp_path / "eval-validation.npz").exists()


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


def test_load_returns_none_when_evaluation_artifact_is_missing(tmp_path):
    assert EvalRecord.load(str(tmp_path / "missing")) is None


@pytest.mark.parametrize(
    ("method", "attribute"),
    [
        ("Gradient", "gradient"),
        ("Gradient * Input", "gradient_input"),
        ("SmoothGrad", "smoothgrad"),
        ("SmoothGrad_Squared", "smoothgrad_sq"),
        ("VarGrad", "vargrad"),
    ],
)
def test_export_saliency_selects_requested_method_and_identity(
    saliency_eval_record,
    method,
    attribute,
):
    artifact = saliency_eval_record.export_saliency(method)

    assert artifact["method"] == method
    assert artifact["saliency"] is getattr(saliency_eval_record, attribute)
    assert artifact["saliency_context"] == _complete_saliency_context().to_payload()
    assert artifact["saliency_method_parameters"] == {
        method: saliency_eval_record.saliency_method_parameters[method]
    }
    expected_seeds = (
        {method: 1} if method in saliency_eval_record.saliency_noise_seeds else {}
    )
    assert artifact["saliency_noise_seeds"] == expected_seeds
    assert artifact["saliency_integrity_manifest"]["manifest_sha256"]


def test_export_saliency_rejects_unknown_method(saliency_eval_record):
    with pytest.raises(ValueError, match=r"Unknown saliency method: InvalidMethod"):
        saliency_eval_record.export_saliency("InvalidMethod")


@pytest.mark.parametrize(
    ("getter_name", "class_index", "expected"),
    [
        ("get_gradient", 0, np.array([1.0, 2.0])),
        ("get_gradient_input", 0, np.array([0.5, 1.0])),
        ("get_smoothgrad", 1, np.array([0.3, 0.4])),
        ("get_smoothgrad_sq", 1, np.array([0.09, 0.16])),
        ("get_vargrad", 0, np.array([0.05, 0.1])),
    ],
)
def test_saliency_getters_return_requested_class_values(
    saliency_eval_record,
    getter_name,
    class_index,
    expected,
):
    values = getattr(saliency_eval_record, getter_name)(class_index)

    np.testing.assert_array_equal(values, expected)
