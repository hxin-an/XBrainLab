from __future__ import annotations

import importlib

import pytest
import torch

from XBrainLab.backend.model_base.legacy_braindecode import models as legacy_models

_SLEEP_TEMPORAL_MODELS = (
    ("tcn", "BDTCN"),
    ("deepsleepnet", "DeepSleepNet"),
    ("sleep_stager_blanco_2020", "SleepStagerBlanco2020"),
    ("sleep_stager_chambon_2018", "SleepStagerChambon2018"),
    ("attn_sleep", "AttnSleep"),
    ("tidnet", "TIDNet"),
    ("usleep", "USleep"),
)


def _model_case(class_name: str) -> tuple[dict[str, object], tuple[int, int, int]]:
    if class_name == "BDTCN":
        return (
            {"n_chans": 4, "n_outputs": 3, "n_blocks": 2, "n_filters": 8},
            (2, 4, 512),
        )
    if class_name == "DeepSleepNet":
        return (
            {
                "n_chans": 2,
                "n_outputs": 3,
                "n_times": 1000,
                "bilstm_hidden_size": 8,
                "bilstm_num_layers": 1,
                "small_n_filters_1": 4,
                "small_n_filters_2": 8,
                "large_n_filters_1": 4,
                "large_n_filters_2": 8,
            },
            (2, 2, 1000),
        )
    if class_name == "SleepStagerBlanco2020":
        return (
            {
                "n_chans": 4,
                "n_outputs": 3,
                "n_times": 3000,
                "sfreq": 100.0,
                "n_conv_chans": 4,
            },
            (2, 4, 3000),
        )
    if class_name == "SleepStagerChambon2018":
        return (
            {
                "n_chans": 4,
                "n_outputs": 3,
                "n_times": 3000,
                "sfreq": 100.0,
                "n_conv_chs": 4,
            },
            (2, 4, 3000),
        )
    if class_name == "AttnSleep":
        return (
            {
                "n_outputs": 3,
                "n_times": 3000,
                "sfreq": 100.0,
                "chs_info": [{"ch_name": "C1", "kind": "eeg"}],
                "n_tce": 1,
            },
            (2, 1, 3000),
        )
    if class_name == "TIDNet":
        return (
            {
                "n_chans": 4,
                "n_outputs": 3,
                "n_times": 512,
                "s_growth": 8,
                "t_filters": 8,
                "temp_layers": 1,
                "spat_layers": 1,
                "pooling": 8,
            },
            (2, 4, 512),
        )
    if class_name == "USleep":
        return (
            {
                "n_chans": 2,
                "n_outputs": 3,
                "n_times": 3000,
                "sfreq": 100.0,
                "depth": 5,
                "n_time_filters": 3,
                "complexity_factor": 0.5,
            },
            (2, 2, 3000),
        )
    raise AssertionError(f"Unknown model case: {class_name}")


@pytest.mark.parametrize(("module_name", "class_name"), _SLEEP_TEMPORAL_MODELS)
def test_local_sleep_temporal_strictly_loads_upstream_state_and_matches_output(
    module_name: str,
    class_name: str,
) -> None:
    upstream_module = importlib.import_module(f"braindecode.models.{module_name}")
    upstream_class = getattr(upstream_module, class_name)
    legacy_class = getattr(legacy_models, class_name)
    kwargs, input_shape = _model_case(class_name)

    torch.manual_seed(71)
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

    generator = torch.Generator().manual_seed(73)
    inputs = torch.randn(*input_shape, generator=generator)
    with torch.inference_mode():
        expected = upstream(inputs)
        actual = legacy(inputs)

    torch.testing.assert_close(actual, expected, rtol=1e-6, atol=1e-7)


@pytest.mark.parametrize("class_name", ("BDTCN", "DeepSleepNet"))
def test_local_sleep_temporal_representatives_support_finite_backward(
    class_name: str,
) -> None:
    model_class = getattr(legacy_models, class_name)
    kwargs, input_shape = _model_case(class_name)
    model = model_class(**kwargs).train()
    inputs = torch.randn(*input_shape, generator=torch.Generator().manual_seed(79))

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
