from __future__ import annotations

import importlib

import pytest
import torch

from XBrainLab.backend.model_base.legacy_braindecode import models as legacy_models

_FILTER_BANK_MODELS = (
    ("fbcnet", "FBCNet"),
    ("fbmsnet", "FBMSNet"),
    ("fblightconvnet", "FBLightConvNet"),
    ("ifnet", "IFNet"),
)

_FAST_FILTER = {
    "method": "iir",
    "iir_params": {"order": 2, "ftype": "butter", "output": "ba"},
}


def _model_case(class_name: str) -> tuple[dict[str, object], tuple[int, int, int]]:
    common: dict[str, object] = {
        "n_chans": 4,
        "n_outputs": 3,
        "n_times": 256,
        "sfreq": 128.0,
        "filter_parameters": _FAST_FILTER,
    }
    if class_name == "FBCNet":
        return (
            common
            | {
                "n_bands": 2,
                "n_filters_spat": 4,
                "stride_factor": 4,
            },
            (2, 4, 256),
        )
    if class_name == "FBMSNet":
        return (
            common
            | {
                "n_bands": 4,
                "n_filters_spat": 8,
                "dilatability": 2,
                "kernels_weights": (3, 5, 7, 9),
                "stride_factor": 4,
            },
            (2, 4, 256),
        )
    if class_name == "FBLightConvNet":
        return (
            common
            | {
                "n_bands": 2,
                "n_filters_spat": 8,
                "win_len": 64,
                "heads": 2,
            },
            (2, 4, 256),
        )
    if class_name == "IFNet":
        return (
            common
            | {
                "bands": [(4.0, 16.0), (16.0, 40.0)],
                "n_filters_spat": 8,
                "kernel_sizes": (7, 5),
                "stride_factor": 4,
            },
            (2, 4, 256),
        )
    raise AssertionError(f"Unknown model case: {class_name}")


@pytest.mark.parametrize(("module_name", "class_name"), _FILTER_BANK_MODELS)
def test_local_filter_bank_strictly_loads_upstream_state_and_matches_output(
    module_name: str,
    class_name: str,
) -> None:
    upstream_module = importlib.import_module(f"braindecode.models.{module_name}")
    upstream_class = getattr(upstream_module, class_name)
    legacy_class = getattr(legacy_models, class_name)
    kwargs, input_shape = _model_case(class_name)

    torch.manual_seed(83)
    upstream = upstream_class(**kwargs).eval()
    legacy = legacy_class(**kwargs).eval()

    upstream_state = upstream.state_dict()
    legacy_state = legacy.state_dict()
    assert list(legacy_state) == list(upstream_state)
    assert {
        key: (tuple(value.shape), value.dtype) for key, value in legacy_state.items()
    } == {
        key: (tuple(value.shape), value.dtype) for key, value in upstream_state.items()
    }
    legacy.load_state_dict(upstream_state, strict=True)

    generator = torch.Generator().manual_seed(89)
    inputs = torch.randn(*input_shape, generator=generator)
    with torch.inference_mode():
        expected = upstream(inputs)
        actual = legacy(inputs)

    torch.testing.assert_close(actual, expected, rtol=1e-6, atol=1e-7)


@pytest.mark.parametrize("class_name", ("FBCNet", "IFNet"))
def test_local_filter_bank_representatives_support_finite_backward(
    class_name: str,
) -> None:
    model_class = getattr(legacy_models, class_name)
    kwargs, input_shape = _model_case(class_name)
    model = model_class(**kwargs).train()
    inputs = torch.randn(*input_shape, generator=torch.Generator().manual_seed(97))

    loss = model(inputs).square().mean()
    loss.backward()

    gradients = [
        parameter.grad for parameter in model.parameters() if parameter.requires_grad
    ]
    assert gradients
    assert all(gradient is not None for gradient in gradients)
    assert all(
        torch.isfinite(gradient).all() for gradient in gradients if gradient is not None
    )
