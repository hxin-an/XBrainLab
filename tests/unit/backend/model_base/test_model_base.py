import pytest
import torch

from XBrainLab.backend import model_base
from XBrainLab.backend.model_requirements import minimum_samples_for_model


@pytest.mark.parametrize("n_classes", [2, 3])
@pytest.mark.parametrize("channel", [1, 2, 22, 23])
@pytest.mark.parametrize("samples", [1000, 1001, 1024])
@pytest.mark.parametrize("sfreq", [128, 256, 501])
@pytest.mark.parametrize(
    "model_class_str",
    [
        m
        for m in dir(model_base)
        if not m.startswith("_") and isinstance(getattr(model_base, m), type)
    ],
)
def test_model_base(n_classes, channel, samples, sfreq, model_class_str):
    model_class = getattr(model_base, model_class_str)
    model = model_class(n_classes, channel, samples, sfreq)
    inputX = torch.randn(1, channel, samples)
    model(inputX)


@pytest.mark.parametrize(
    "model_class_str",
    [
        m
        for m in dir(model_base)
        if not m.startswith("_") and isinstance(getattr(model_base, m), type)
    ],
)
def test_supported_models_run_one_optimizer_step(model_class_str):
    model_class = getattr(model_base, model_class_str)
    model = model_class(n_classes=2, channels=4, samples=512, sfreq=128)
    model.train()
    optimizer = torch.optim.SGD(model.parameters(), lr=0.001)
    batch = torch.randn(2, 4, 512)
    target = torch.tensor([0, 1], dtype=torch.long)

    output = model(batch)
    loss = torch.nn.CrossEntropyLoss()(output, target)
    loss.backward()
    optimizer.step()

    assert output.shape == (2, 2)


@pytest.mark.parametrize(
    ("model_class_str", "params"),
    [
        ("EEGNet", {"pool_1": 4, "pool_2": 8}),
        ("EEGNet", {"pool_1": 4, "pool_2": 128}),
        ("SCCNet", {}),
        ("ShallowConvNet", {"pool_len": 75, "pool_stride": 15}),
    ],
)
def test_model_sample_requirement_matches_model_boundary(model_class_str, params):
    model_class = getattr(model_base, model_class_str)
    requirement = minimum_samples_for_model(
        model_class_str,
        sfreq=128,
        model_params=params,
    )
    assert requirement is not None

    constructor_kwargs = {
        "n_classes": 2,
        "channels": 4,
        "samples": requirement.min_samples,
        "sfreq": 128,
        **params,
    }
    model = model_class(**constructor_kwargs)
    output = model(torch.randn(2, 4, requirement.min_samples))

    assert output.shape == (2, 2)
    with pytest.raises(ValueError, match="Epoch duration is too short"):
        model_class(**{**constructor_kwargs, "samples": requirement.min_samples - 1})
