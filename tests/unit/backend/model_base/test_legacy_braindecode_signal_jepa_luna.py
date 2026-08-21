from __future__ import annotations

# pyright: reportArgumentType=false
import importlib
from pathlib import Path

import numpy as np
import pytest
import torch

from XBrainLab.backend.model_base.legacy_braindecode import models as legacy_models

_SIGNAL_JEPA_MODELS = (
    "SignalJEPA",
    "InterpolatedSignalJEPA",
    "SignalJEPA_Contextual",
    "SignalJEPA_PostLocal",
    "SignalJEPA_PreLocal",
)


def _channel_info() -> list[dict[str, object]]:
    return [
        {
            "ch_name": f"C{index}",
            "loc": np.r_[
                np.array([index / 10.0, (index + 1) / 10.0, (index + 2) / 10.0]),
                np.zeros(9),
            ],
        }
        for index in range(4)
    ]


def _signal_jepa_case(class_name: str) -> tuple[dict[str, object], torch.Tensor]:
    generator = torch.Generator().manual_seed(431)
    inputs = torch.randn(2, 4, 64, generator=generator)
    shared: dict[str, object] = {
        "n_chans": 4,
        "n_times": 64,
        "sfreq": 128.0,
        "feature_encoder__conv_layers_spec": ((8, 4, 2), (16, 4, 2)),
        "drop_prob": 0.0,
    }
    if class_name in {
        "SignalJEPA",
        "InterpolatedSignalJEPA",
        "SignalJEPA_Contextual",
    }:
        shared.update(
            {
                "chs_info": _channel_info(),
                "pos_encoder__spat_dim": 6,
                "pos_encoder__time_dim": 10,
                "pos_encoder__sfreq_features": 1.0,
                "transformer__d_model": 16,
                "transformer__num_encoder_layers": 1,
                "transformer__num_decoder_layers": 1,
                "transformer__nhead": 4,
                "channel_embedding": "scratch",
            }
        )
    if class_name not in {"SignalJEPA", "InterpolatedSignalJEPA"}:
        shared.update({"n_outputs": 3, "n_spat_filters": 2})
    return shared, inputs


def _luna_case() -> tuple[dict[str, object], torch.Tensor]:
    return (
        {
            "n_outputs": 3,
            "n_chans": 4,
            "n_times": 80,
            "sfreq": 128.0,
            "chs_info": _channel_info(),
            "patch_size": 40,
            "num_queries": 2,
            "embed_dim": 16,
            "depth": 1,
            "num_heads": 2,
            "mlp_ratio": 2.0,
            "drop_path": 0.0,
            "drop_prob_chan": 0.0,
            "attn_drop": 0.0,
        },
        torch.randn(2, 4, 80, generator=torch.Generator().manual_seed(433)),
    )


@pytest.mark.parametrize("class_name", _SIGNAL_JEPA_MODELS)
def test_local_signal_jepa_strictly_loads_upstream_state_and_matches_output(
    class_name: str,
) -> None:
    upstream_class = getattr(
        importlib.import_module("braindecode.models.signal_jepa"), class_name
    )
    legacy_class = getattr(legacy_models, class_name)
    kwargs, inputs = _signal_jepa_case(class_name)

    torch.manual_seed(421)
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

    with torch.inference_mode():
        expected = upstream(inputs)
        actual = legacy(inputs)
    torch.testing.assert_close(actual, expected, rtol=1e-6, atol=1e-7)


def test_local_luna_strictly_loads_upstream_state_and_matches_output() -> None:
    upstream_class = importlib.import_module("braindecode.models.luna").LUNA
    kwargs, inputs = _luna_case()

    torch.manual_seed(423)
    upstream = upstream_class(**kwargs).eval()
    legacy = legacy_models.LUNA(**kwargs).eval()

    upstream_state = upstream.state_dict()
    legacy_state = legacy.state_dict()
    assert list(legacy_state) == list(upstream_state)
    assert {
        key: (tuple(value.shape), value.dtype) for key, value in legacy_state.items()
    } == {
        key: (tuple(value.shape), value.dtype) for key, value in upstream_state.items()
    }
    legacy.load_state_dict(upstream_state, strict=True)

    with torch.inference_mode():
        expected = upstream(inputs)
        actual = legacy(inputs)
    torch.testing.assert_close(actual, expected, rtol=1e-6, atol=1e-7)


@pytest.mark.parametrize("class_name", ("SignalJEPA", "LUNA"))
def test_local_signal_jepa_luna_supports_finite_backward(class_name: str) -> None:
    kwargs, inputs = (
        _signal_jepa_case(class_name) if class_name == "SignalJEPA" else _luna_case()
    )
    model = getattr(legacy_models, class_name)(**kwargs).train()

    model(inputs).square().mean().backward()

    gradients = [
        parameter.grad for parameter in model.parameters() if parameter.requires_grad
    ]
    finite_gradients = [gradient for gradient in gradients if gradient is not None]
    assert finite_gradients
    assert all(torch.isfinite(gradient).all() for gradient in finite_gradients)


def test_local_signal_jepa_luna_has_no_remote_loader_surface() -> None:
    model_root = Path(legacy_models.__file__).parent
    for module_name in ("signal_jepa", "luna"):
        source = (model_root / f"{module_name}.py").read_text(encoding="utf-8")
        for forbidden_surface in (
            "Hugging Face Hub",
            "HuggingFace",
            "from_pretrained",
            "push_to_hub",
            "torch.hub",
            "load_state_dict_from_url",
            "hf_hub_download",
            "huggingface_hub",
            "requests.get",
        ):
            assert forbidden_surface not in source
