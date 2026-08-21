from __future__ import annotations

import importlib
from pathlib import Path

import pytest
import torch

from XBrainLab.backend.model_base.legacy_braindecode import models as legacy_models

_LABRAM_EEGSYM_MODELS = (
    ("labram", "Labram", False),
    ("labram", "InterpolatedLaBraM", True),
    ("eegsym", "EEGSym", False),
)


def _model_case(
    class_name: str,
    upstream_class: type,
) -> tuple[dict[str, object], torch.Tensor]:
    generator = torch.Generator().manual_seed(419)
    if class_name in {"Labram", "InterpolatedLaBraM"}:
        kwargs: dict[str, object] = {
            "n_times": 200,
            "n_outputs": 3,
            "patch_size": 200,
            "embed_dim": 32,
            "conv_out_channels": 4,
            "num_layers": 1,
            "num_heads": 4,
            "mlp_ratio": 2.0,
            "drop_prob": 0.0,
            "attn_drop_prob": 0.0,
            "drop_path_prob": 0.0,
        }
        if class_name == "InterpolatedLaBraM":
            kwargs["chs_info"] = upstream_class._TARGET_CHS_INFO
            n_chans = len(upstream_class._TARGET_CHS_INFO)
        else:
            n_chans = 128
            kwargs["n_chans"] = n_chans
        return kwargs, torch.randn(2, n_chans, 200, generator=generator)
    if class_name == "EEGSym":
        names = ["C3", "C4", "F3", "F4", "CZ", "FZ"]
        return (
            {
                "chs_info": [{"ch_name": name} for name in names],
                "n_outputs": 3,
                "n_times": 256,
                "sfreq": 128.0,
                "filters_per_branch": 8,
                "scales_time": (64, 32, 16),
                "drop_prob": 0.0,
                "spatial_resnet_repetitions": 1,
                "left_right_chs": [("C3", "C4"), ("F3", "F4")],
                "middle_chs": ["CZ", "FZ"],
            },
            torch.randn(2, 6, 256, generator=generator),
        )
    raise AssertionError(f"Unknown model case: {class_name}")


@pytest.mark.parametrize(
    ("module_name", "class_name", "interpolated"), _LABRAM_EEGSYM_MODELS
)
def test_local_labram_eegsym_strictly_loads_upstream_state_and_matches_output(
    module_name: str,
    class_name: str,
    interpolated: bool,
) -> None:
    del interpolated
    upstream_class = getattr(
        importlib.import_module(f"braindecode.models.{module_name}"), class_name
    )
    legacy_class = getattr(legacy_models, class_name)
    kwargs, inputs = _model_case(class_name, upstream_class)

    torch.manual_seed(401)
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


@pytest.mark.parametrize("class_name", ("Labram", "EEGSym"))
def test_local_labram_eegsym_supports_finite_backward(class_name: str) -> None:
    upstream_class = getattr(
        importlib.import_module(
            "braindecode.models.labram"
            if class_name == "Labram"
            else "braindecode.models.eegsym"
        ),
        class_name,
    )
    kwargs, inputs = _model_case(class_name, upstream_class)
    model = getattr(legacy_models, class_name)(**kwargs).train()

    model(inputs).square().mean().backward()

    gradients = [
        parameter.grad for parameter in model.parameters() if parameter.requires_grad
    ]
    finite_gradients = [gradient for gradient in gradients if gradient is not None]
    assert finite_gradients
    assert all(torch.isfinite(gradient).all() for gradient in finite_gradients)


def test_local_labram_eegsym_has_no_remote_loader_surface() -> None:
    model_root = Path(legacy_models.__file__).parent
    for module_name in ("labram", "eegsym"):
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
