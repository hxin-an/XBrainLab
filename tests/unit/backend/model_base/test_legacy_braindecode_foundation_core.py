from __future__ import annotations

import importlib
from pathlib import Path

import pytest
import torch

from XBrainLab.backend.model_base.legacy_braindecode import models as legacy_models

_FOUNDATION_CORE_MODELS = (
    ("eegpt", "EEGPT", False),
    ("eegpt", "InterpolatedEEGPT", True),
    ("biot", "BIOT", False),
    ("biot", "InterpolatedBIOT", True),
    ("bendr", "BENDR", False),
    ("bendr", "InterpolatedBENDR", True),
)


def _base_kwargs(class_name: str) -> tuple[dict[str, object], int, int]:
    if class_name.endswith("EEGPT"):
        return (
            {
                "n_outputs": 3,
                "n_times": 256,
                "patch_size": 32,
                "patch_stride": 16,
                "embed_num": 2,
                "embed_dim": 32,
                "depth": 1,
                "num_heads": 4,
                "mlp_ratio": 2,
                "n_chans_target": 19,
            },
            19 if class_name.startswith("Interpolated") else 4,
            256,
        )
    if class_name.endswith("BIOT"):
        return (
            {
                "n_outputs": 3,
                "n_times": 256,
                "sfreq": 128.0,
                "embed_dim": 32,
                "num_heads": 4,
                "num_layers": 1,
                "hop_length": 32,
                "max_seq_len": 128,
                "drop_prob": 0.0,
                "att_drop_prob": 0.0,
                "att_layer_drop_prob": 0.0,
            },
            18 if class_name.startswith("Interpolated") else 4,
            256,
        )
    if class_name.endswith("BENDR"):
        return (
            {
                "n_outputs": 3,
                "n_times": 512,
                "encoder_h": 32,
                "contextualizer_hidden": 64,
                "drop_prob": 0.0,
                "layer_drop": 0.0,
                "transformer_layers": 1,
                "transformer_heads": 4,
                "position_encoder_length": 9,
                "enc_width": (3, 2, 2),
                "enc_downsample": (2, 2, 2),
            },
            20 if class_name.startswith("Interpolated") else 4,
            512,
        )
    raise AssertionError(f"Unknown model case: {class_name}")


@pytest.mark.parametrize(
    ("module_name", "class_name", "interpolated"), _FOUNDATION_CORE_MODELS
)
def test_local_foundation_core_strictly_loads_upstream_state_and_matches_output(
    module_name: str,
    class_name: str,
    interpolated: bool,
) -> None:
    upstream_module = importlib.import_module(f"braindecode.models.{module_name}")
    upstream_class = getattr(upstream_module, class_name)
    legacy_class = getattr(legacy_models, class_name)
    kwargs, n_chans, n_times = _base_kwargs(class_name)
    if interpolated:
        kwargs["chs_info"] = upstream_class._TARGET_CHS_INFO
        n_chans = len(upstream_class._TARGET_CHS_INFO)
    else:
        kwargs["n_chans"] = n_chans

    torch.manual_seed(211)
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

    inputs = torch.randn(
        2,
        n_chans,
        n_times,
        generator=torch.Generator().manual_seed(223),
    )
    with torch.inference_mode():
        expected = upstream(inputs)
        actual = legacy(inputs)

    torch.testing.assert_close(actual, expected, rtol=1e-6, atol=1e-7)


@pytest.mark.parametrize("class_name", ("EEGPT", "BIOT", "BENDR"))
def test_local_foundation_core_supports_finite_backward(class_name: str) -> None:
    model_class = getattr(legacy_models, class_name)
    kwargs, n_chans, n_times = _base_kwargs(class_name)
    kwargs["n_chans"] = n_chans
    model = model_class(**kwargs).train()
    inputs = torch.randn(
        2,
        n_chans,
        n_times,
        generator=torch.Generator().manual_seed(227),
    )

    loss = model(inputs).square().mean()
    loss.backward()

    gradients = [
        parameter.grad for parameter in model.parameters() if parameter.requires_grad
    ]
    assert gradients
    finite_gradients = [gradient for gradient in gradients if gradient is not None]
    assert finite_gradients
    assert all(torch.isfinite(gradient).all() for gradient in finite_gradients)


def test_local_foundation_core_has_no_remote_loader_surface() -> None:
    model_root = Path(legacy_models.__file__).parent
    for module_name in ("eegpt", "biot", "bendr"):
        source = (model_root / f"{module_name}.py").read_text(encoding="utf-8")
        for forbidden_surface in (
            "Hugging Face Hub",
            "_hub_mixin_config",
            "from_pretrained",
            "hf_hub_download",
            "huggingface_hub",
            "requests.get",
        ):
            assert forbidden_surface not in source
