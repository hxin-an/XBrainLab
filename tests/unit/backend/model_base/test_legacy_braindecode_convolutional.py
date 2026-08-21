from __future__ import annotations

import importlib

import pytest
import torch

from XBrainLab.backend.model_base.legacy_braindecode import models as legacy_models

_CONVOLUTIONAL_MODELS = (
    ("eeginception_mi", "EEGInceptionMI"),
    ("eegitnet", "EEGITNet"),
    ("eegtcnet", "EEGTCNet"),
    ("eegsimpleconv", "EEGSimpleConv"),
    ("sparcnet", "SPARCNet"),
    ("contrawr", "ContraWR"),
    ("tsinception", "TSception"),
    ("syncnet", "SyncNet"),
    ("sinc_shallow", "SincShallowNet"),
    ("sstdpn", "SSTDPN"),
)


def _model_kwargs(class_name: str) -> dict[str, object]:
    common: dict[str, object] = {
        "n_chans": 4,
        "n_outputs": 3,
        "n_times": 256,
    }
    if class_name == "EEGInceptionMI":
        return common | {"sfreq": 128.0, "n_convs": 2, "n_filters": 4}
    if class_name == "EEGITNet":
        return common | {
            "n_filters_time": 2,
            "kernel_length": 16,
            "pool_kernel": 4,
            "tcn_in_channel": 14,
            "tcn_kernel_size": 4,
            "tcn_padding": 3,
        }
    if class_name == "EEGTCNet":
        return common | {
            "filter_1": 4,
            "depth_multiplier": 1,
            "filters": 4,
            "depth": 1,
            "kern_length": 32,
            "kernel_size": 4,
        }
    if class_name == "EEGSimpleConv":
        return common | {
            "sfreq": 128.0,
            "feature_maps": 8,
            "n_convs": 1,
            "resampling_freq": 64,
            "kernel_size": 4,
        }
    if class_name == "SPARCNet":
        return common | {
            "block_layers": 2,
            "growth_rate": 4,
            "bottleneck_size": 4,
        }
    if class_name == "ContraWR":
        return common | {
            "sfreq": 128.0,
            "emb_size": 16,
            "res_channels": [4, 8],
            "steps": 8,
        }
    if class_name == "TSception":
        return common | {
            "sfreq": 128.0,
            "number_filter_temp": 3,
            "number_filter_spat": 2,
            "hidden_size": 8,
            "pool_size": 4,
        }
    if class_name == "SyncNet":
        return common | {"num_filters": 1, "filter_width": 20, "pool_size": 20}
    if class_name == "SincShallowNet":
        return common | {
            "sfreq": 128.0,
            "num_time_filters": 4,
            "time_filter_len": 17,
            "depth_multiplier": 1,
            "pool_size": 16,
            "pool_stride": 8,
        }
    if class_name == "SSTDPN":
        return common | {
            "sfreq": 128.0,
            "n_spectral_filters_temporal": 3,
            "n_fused_filters": 8,
            "temporal_conv_kernel_size": 15,
            "mvp_kernel_sizes": [2, 4],
            "spt_attn_global_context_kernel": 64,
        }
    raise AssertionError(f"Unknown model case: {class_name}")


@pytest.mark.parametrize(("module_name", "class_name"), _CONVOLUTIONAL_MODELS)
def test_local_convolutional_strictly_loads_upstream_state_and_matches_output(
    module_name: str,
    class_name: str,
) -> None:
    upstream_module = importlib.import_module(f"braindecode.models.{module_name}")
    upstream_class = getattr(upstream_module, class_name)
    legacy_class = getattr(legacy_models, class_name)
    kwargs = _model_kwargs(class_name)

    torch.manual_seed(101)
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

    inputs = torch.randn(2, 4, 256, generator=torch.Generator().manual_seed(103))
    with torch.inference_mode():
        expected = upstream(inputs)
        actual = legacy(inputs)

    torch.testing.assert_close(actual, expected, rtol=1e-6, atol=1e-7)


@pytest.mark.parametrize("class_name", ("EEGInceptionMI", "ContraWR", "SSTDPN"))
def test_local_convolutional_representatives_support_finite_backward(
    class_name: str,
) -> None:
    model_class = getattr(legacy_models, class_name)
    model = model_class(**_model_kwargs(class_name)).train()
    inputs = torch.randn(2, 4, 256, generator=torch.Generator().manual_seed(107))

    loss = model(inputs).square().mean()
    loss.backward()

    gradients = [
        parameter.grad for parameter in model.parameters() if parameter.requires_grad
    ]
    assert gradients
    finite_gradients = [gradient for gradient in gradients if gradient is not None]
    assert finite_gradients
    assert all(torch.isfinite(gradient).all() for gradient in finite_gradients)
