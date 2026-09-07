import numpy as np
import pytest
import torch
from captum.attr import NoiseTunnel, Saliency
from torch.utils.data import DataLoader, TensorDataset

from XBrainLab.backend.model_base.EEGNet import EEGNet
from XBrainLab.backend.training.evaluator import Evaluator
from XBrainLab.backend.training.training_plan import to_holder


@pytest.mark.parametrize("shuffle", [True, False])
def test_to_holder(shuffle):
    device = "cpu"
    length = 3000
    X = np.arange(length).reshape(-1, 1)
    y = np.arange(length)

    bs = 128
    indices = np.arange(length)
    dataloader = to_holder(X, y, indices, device, bs, shuffle, seed=7)

    # Perform assertions
    assert isinstance(dataloader, DataLoader)
    assert dataloader.batch_size == bs

    sample_x, sample_y = next(iter(dataloader))
    assert sample_x.dtype == torch.float32
    assert sample_y.dtype == torch.int64
    sequence = torch.arange(bs, dtype=torch.float32).reshape(-1, 1)
    if shuffle:
        with pytest.raises(AssertionError):
            torch.testing.assert_close(sample_x, sequence)
    else:
        torch.testing.assert_close(sample_x, sequence)


def test_to_holder_empty():
    X = np.array([])
    y = np.array([])
    indices = np.array([])
    device = "cpu"
    bs = 128
    shuffle = True
    assert to_holder(X, y, indices, device, bs, shuffle, seed=7) is None


CLASS_NUM = 4
ERROR_NUM = 3
SAMPLE_NUM = CLASS_NUM
REPEAT = 5
TOTAL_NUM = SAMPLE_NUM * REPEAT
BS = 2


class FakeModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.fc = torch.nn.Linear(CLASS_NUM, CLASS_NUM)
        self.fc.weight.data = torch.diag(torch.ones(CLASS_NUM))
        self.fc.bias.data = torch.zeros_like(self.fc.bias.data)

    def forward(self, x):
        x = self.fc(x)
        x = x.squeeze(1)
        return x


@pytest.fixture
def full_y():
    return np.arange(SAMPLE_NUM).repeat(REPEAT)


@pytest.fixture
def y(full_y):
    y = full_y.copy()
    y[:ERROR_NUM] += 1
    y[:ERROR_NUM] %= CLASS_NUM
    return y


@pytest.fixture
def dataloader(full_y, y):
    """
    X = [[1, 0, 0, 0],
         [1, 0, 0, 0],
         [1, 0, 0, 0],
          ...
         [0, 0, 0, 1]]
    ground truth = [0, 0, 0, 0, 0, 1, ...]
    y = [1, 1, 1, 0, 0, 1, ...]
    """
    X = np.zeros((TOTAL_NUM, CLASS_NUM))
    for idx, gt in enumerate(full_y):
        X[idx, gt] = 1

    device = "cpu"
    shuffle = False
    indices = np.arange(TOTAL_NUM)
    return to_holder(X, y, indices, device, BS, shuffle, seed=7)


@pytest.fixture
def loss_avg():
    criterion = torch.nn.CrossEntropyLoss()
    error_loss = criterion(
        torch.Tensor([[0, 0, 0, 1]]), torch.Tensor([0]).long()
    ).item()
    correct_loss = criterion(
        torch.Tensor([[1, 0, 0, 0]]), torch.Tensor([0]).long()
    ).item()
    loss = np.ones(TOTAL_NUM) * correct_loss
    loss[:ERROR_NUM] = error_loss
    loss_avg = [loss[i : i + BS].mean() for i in range(0, TOTAL_NUM, BS)]
    loss_avg = np.array(loss_avg).mean()
    return loss_avg


def test_test_model(dataloader, loss_avg):
    model = FakeModel()
    criterion = torch.nn.CrossEntropyLoss()
    test_dict = Evaluator.evaluate_metrics(model, dataloader, criterion)

    assert test_dict.keys() == {"loss", "accuracy", "auc"}
    assert test_dict["accuracy"] == (TOTAL_NUM - ERROR_NUM) / (TOTAL_NUM) * 100
    assert np.isclose(test_dict["loss"], loss_avg)


def test_eval_model(dataloader, y, full_y):
    model = FakeModel()
    model.eval()

    saliency_params = {
        "SmoothGrad": {"nt_samples": 1, "stdevs": 0.1},
        "SmoothGrad_Squared": {"nt_samples": 1, "stdevs": 0.1},
        "VarGrad": {"nt_samples": 1, "stdevs": 0.1},
    }

    result = Evaluator.evaluate_with_saliency(model, dataloader, saliency_params)
    assert not model.training
    np.testing.assert_array_equal(result.label, y)
    np.testing.assert_array_equal(result.output.argmax(axis=-1), full_y)
    for store in (
        result.gradient,
        result.gradient_input,
        result.smoothgrad,
        result.smoothgrad_sq,
        result.vargrad,
    ):
        assert set(store) == set(range(CLASS_NUM))
        for label, values in store.items():
            assert values.shape == (np.count_nonzero(y == label), CLASS_NUM)
            assert np.isfinite(values).all()
    assert result.saliency_method_parameters == {
        "Gradient": {},
        "Gradient * Input": {},
        **{
            method: {**params, "nt_samples_batch_size": None}
            for method, params in saliency_params.items()
        },
    }
    assert set(result.saliency_noise_seeds) == set(saliency_params)
    assert len(set(result.saliency_noise_seeds.values())) == 1


@pytest.mark.parametrize(
    "methods", [["Gradient"], ["Gradient * Input"], ["Gradient", "Gradient * Input"]]
)
def test_saliency_targets_each_sample_ground_truth_label(methods):
    inputs = torch.tensor([[1.0, 2.0, -3.0], [-2.0, 3.0, 1.0], [4.0, -1.0, 2.0]])
    labels = torch.tensor([0, 1, 1])
    model = _SignedLinearModel()
    loader = DataLoader(TensorDataset(inputs, labels), batch_size=2)
    record = Evaluator.evaluate_with_saliency(model, loader, {"_methods": methods})

    np.testing.assert_array_equal(record.label, labels.numpy())
    np.testing.assert_array_equal(record.output, model(inputs).numpy())
    expected_gradient = np.array(
        [[1.0, -2.0, 0.5], [-1.0, 2.0, -0.5], [-1.0, 2.0, -0.5]]
    )
    for method, store, expected in (
        ("Gradient", record.gradient, expected_gradient),
        ("Gradient * Input", record.gradient_input, expected_gradient * inputs.numpy()),
    ):
        if method in methods:
            for label in (0, 1):
                np.testing.assert_allclose(
                    store[label], expected[labels.numpy() == label]
                )
        else:
            assert store == {}
    assert record.smoothgrad == record.smoothgrad_sq == record.vargrad == {}
    assert record.saliency_method_parameters == {method: {} for method in methods}
    assert record.saliency_noise_seeds == {}


def test_eegnet_saliency_matches_captum_with_outer_no_grad():
    torch.manual_seed(20260907)
    inputs = torch.randn(5, 4, 128)
    labels = torch.tensor([0, 1, 2, 0, 1])
    model = EEGNet(3, 4, 128, 64.0, f1=2, f2=4, d=1).eval()
    expected = (
        Saliency(model)
        .attribute(
            inputs.clone().requires_grad_(True),
            target=labels.tolist(),
            abs=False,
        )
        .numpy()
    )
    with torch.no_grad():
        outputs = model(inputs).numpy()
        record = Evaluator.evaluate_with_saliency(
            model,
            DataLoader(TensorDataset(inputs, labels), batch_size=2),
            {"_methods": ["Gradient", "Gradient * Input"]},
        )
    np.testing.assert_allclose(record.output, outputs, rtol=1e-5, atol=1e-7)
    for label in range(3):
        mask = labels.numpy() == label
        np.testing.assert_allclose(
            record.gradient[label], expected[mask], rtol=1e-5, atol=1e-7
        )
        np.testing.assert_allclose(
            record.gradient_input[label],
            (expected * inputs.numpy())[mask],
            rtol=1e-5,
            atol=1e-7,
        )
    assert all(parameter.grad is None for parameter in model.parameters())


class _SignedLinearModel(torch.nn.Module):
    def forward(self, inputs):
        score = inputs[:, 0] - (2 * inputs[:, 1]) + (0.5 * inputs[:, 2])
        return torch.stack((score, -score), dim=1)


class _SignedQuadraticModel(torch.nn.Module):
    def forward(self, inputs):
        score = (inputs * inputs).sum(dim=1)
        return torch.stack((score, -score), dim=1)


def _single_sample_loader(inputs: torch.Tensor) -> DataLoader:
    generator = torch.Generator().manual_seed(99)
    return DataLoader(
        TensorDataset(inputs, torch.tensor([0])),
        batch_size=1,
        generator=generator,
    )


def test_noise_tunnel_saliency_preserves_signed_base_gradient():
    inputs = torch.tensor([[0.2, -0.3, 0.4]], dtype=torch.float32)
    record = Evaluator.evaluate_with_saliency(
        _SignedLinearModel(),
        _single_sample_loader(inputs),
        {
            "_methods": ["SmoothGrad", "SmoothGrad_Squared"],
            "SmoothGrad": {"nt_samples": 4, "stdevs": 0.2},
            "SmoothGrad_Squared": {"nt_samples": 4, "stdevs": 0.2},
        },
    )

    np.testing.assert_allclose(
        record.smoothgrad[0],
        np.array([[1.0, -2.0, 0.5]], dtype=np.float32),
    )
    np.testing.assert_allclose(
        record.smoothgrad_sq[0],
        np.array([[1.0, 4.0, 0.25]], dtype=np.float32),
    )


def test_vargrad_uses_variance_of_signed_gradients():
    inputs = torch.tensor([[0.0, 0.2, -0.1]], dtype=torch.float32)
    params = {"nt_samples": 64, "stdevs": 0.5}

    torch.manual_seed(1234)
    record = Evaluator.evaluate_with_saliency(
        _SignedQuadraticModel(),
        _single_sample_loader(inputs),
        {"_methods": ["VarGrad"], "VarGrad": params},
    )

    torch.manual_seed(1234)
    expected_signed = NoiseTunnel(Saliency(_SignedQuadraticModel())).attribute(
        inputs.clone().requires_grad_(True),
        target=[0],
        nt_type="vargrad",
        abs=False,
        **params,
    )
    torch.manual_seed(1234)
    absolute_gradient_variance = NoiseTunnel(
        Saliency(_SignedQuadraticModel())
    ).attribute(
        inputs.clone().requires_grad_(True),
        target=[0],
        nt_type="vargrad",
        **params,
    )

    np.testing.assert_allclose(record.vargrad[0], expected_signed.numpy())
    assert not np.allclose(record.vargrad[0], absolute_gradient_variance.numpy())
