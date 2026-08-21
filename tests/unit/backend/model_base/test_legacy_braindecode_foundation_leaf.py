from __future__ import annotations

import importlib
from pathlib import Path

import numpy as np
import pytest
import torch

from XBrainLab.backend.model_base.legacy_braindecode import models as legacy_models

_FOUNDATION_LEAF_MODELS = (
    ("cbramod", "CBraMod"),
    ("codebrain", "CodeBrain"),
    ("dgcnn", "DGCNN"),
    ("eegdino", "EEGDINO"),
)


def _model_case(class_name: str) -> tuple[dict[str, object], torch.Tensor]:
    generator = torch.Generator().manual_seed(311)
    if class_name == "CBraMod":
        return (
            {
                "n_outputs": 3,
                "n_chans": 4,
                "n_times": 200,
                "patch_size": 200,
                "dim_feedforward": 64,
                "n_layer": 1,
                "nhead": 4,
                "emb_dim": 32,
                "drop_prob": 0.0,
            },
            torch.randn(2, 4, 200, generator=generator),
        )
    if class_name == "CodeBrain":
        return (
            {
                "n_outputs": 3,
                "n_chans": 4,
                "n_times": 128,
                "patch_size": 32,
                "res_channels": 16,
                "skip_channels": 16,
                "out_channels": 16,
                "num_res_layers": 1,
                "drop_prob": 0.0,
                "s4_lmax": 32,
                "s4_d_state": 8,
                "conv_out_chans": 10,
                "conv_groups": 5,
                "proj_kernel_size": 9,
                "proj_padding": 4,
                "proj_refine_kernel": 3,
                "pos_kernel": (3, 3),
                "spectral_dropout": 0.0,
                "mlp_hidden_multiplier": 2,
                "swa_window_size": 1,
                "codebook_size_t": 16,
                "codebook_size_f": 16,
            },
            torch.randn(2, 4, 128, generator=generator),
        )
    if class_name == "DGCNN":
        chs_info = [
            {
                "ch_name": f"C{index}",
                "loc": np.r_[
                    np.array([np.cos(index), np.sin(index), index / 10]),
                    np.zeros(9),
                ],
            }
            for index in range(4)
        ]
        return (
            {
                "n_outputs": 3,
                "chs_info": chs_info,
                "n_times": 16,
                "n_filters": 8,
                "cheb_order": 2,
                "n_neighbors": 2,
                "mlp_dims": (16,),
                "drop_prob": 0.0,
            },
            torch.randn(2, 4, 16, generator=generator),
        )
    if class_name == "EEGDINO":
        return (
            {
                "n_outputs": 3,
                "n_chans": 4,
                "n_times": 128,
                "patch_size": 32,
                "n_layer": 1,
                "nhead": 4,
                "dim_feedforward": 64,
                "n_channel_embeddings": 4,
                "n_global_tokens": 1,
                "global_token_layer": 1,
                "drop_prob": 0.0,
            },
            torch.randn(2, 4, 128, generator=generator),
        )
    raise AssertionError(f"Unknown model case: {class_name}")


@pytest.mark.parametrize(("module_name", "class_name"), _FOUNDATION_LEAF_MODELS)
def test_local_foundation_leaf_strictly_loads_upstream_state_and_matches_output(
    module_name: str,
    class_name: str,
) -> None:
    upstream_class = getattr(
        importlib.import_module(f"braindecode.models.{module_name}"), class_name
    )
    legacy_class = getattr(legacy_models, class_name)
    kwargs, inputs = _model_case(class_name)

    torch.manual_seed(307)
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


@pytest.mark.parametrize("class_name", ("CBraMod", "CodeBrain", "DGCNN", "EEGDINO"))
def test_local_foundation_leaf_supports_finite_backward(class_name: str) -> None:
    kwargs, inputs = _model_case(class_name)
    model = getattr(legacy_models, class_name)(**kwargs).train()

    loss = model(inputs).square().mean()
    loss.backward()

    gradients = [
        parameter.grad for parameter in model.parameters() if parameter.requires_grad
    ]
    finite_gradients = [gradient for gradient in gradients if gradient is not None]
    assert finite_gradients
    assert all(torch.isfinite(gradient).all() for gradient in finite_gradients)


def test_local_foundation_leaf_has_no_remote_loader_surface() -> None:
    model_root = Path(legacy_models.__file__).parent
    for module_name, _ in _FOUNDATION_LEAF_MODELS:
        source = (model_root / f"{module_name}.py").read_text(encoding="utf-8")
        for forbidden_surface in (
            "Hugging Face Hub",
            "HuggingFace",
            "_hub_mixin_config",
            "from_pretrained",
            "hf_hub_download",
            "huggingface_hub",
            "requests.get",
        ):
            assert forbidden_surface not in source
