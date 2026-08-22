from __future__ import annotations

# pyright: reportArgumentType=false
import importlib
from pathlib import Path

import pytest
import torch
from torch import nn

from XBrainLab.backend.model_base.legacy_braindecode import models as legacy_models


class _OfflinePositionBank(nn.Module):
    """Replace the upstream download seam while comparing model math."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__()


def _model_case() -> tuple[dict[str, object], torch.Tensor, torch.Tensor]:
    generator = torch.Generator().manual_seed(443)
    return (
        {
            "n_outputs": 3,
            "n_chans": 4,
            "n_times": 64,
            "sfreq": 128.0,
            "embed_dim": 16,
            "depth": 1,
            "heads": 2,
            "head_dim": 8,
            "mlp_dim_ratio": 2.0,
            "use_geglu": True,
            "freqs": 2,
            "patch_size": 16,
            "patch_overlap": 0,
            "attention_pooling": True,
        },
        torch.randn(2, 4, 64, generator=generator),
        torch.rand(2, 4, 3, generator=generator),
    )


def test_local_reve_strictly_loads_upstream_state_and_matches_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upstream_module = importlib.import_module("braindecode.models.reve")
    monkeypatch.setattr(upstream_module, "RevePositionBank", _OfflinePositionBank)
    kwargs, inputs, positions = _model_case()

    torch.manual_seed(439)
    upstream = upstream_module.REVE(**kwargs).eval()
    legacy = legacy_models.REVE(**kwargs).eval()

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
        expected = upstream(inputs, pos=positions)
        actual = legacy(inputs, pos=positions)
    torch.testing.assert_close(actual, expected, rtol=1e-6, atol=1e-7)


def test_local_reve_supports_finite_backward() -> None:
    kwargs, inputs, positions = _model_case()
    model = legacy_models.REVE(**kwargs).train()

    model(inputs, pos=positions).square().mean().backward()

    gradients = [
        parameter.grad for parameter in model.parameters() if parameter.requires_grad
    ]
    finite_gradients = [gradient for gradient in gradients if gradient is not None]
    assert finite_gradients
    assert all(torch.isfinite(gradient).all() for gradient in finite_gradients)


def test_local_reve_channel_name_lookup_fails_closed_without_local_positions() -> None:
    kwargs, _, _ = _model_case()
    kwargs["chs_info"] = [{"ch_name": "C3"}, {"ch_name": "C4"}]
    kwargs["n_chans"] = 2

    with pytest.raises(RuntimeError, match="explicit channel positions"):
        legacy_models.REVE(**kwargs)


def test_local_reve_has_no_remote_or_cache_loader_surface() -> None:
    source = (Path(legacy_models.__file__).parent / "reve.py").read_text(
        encoding="utf-8"
    )
    for forbidden_surface in (
        "Hugging Face Hub",
        "HuggingFace",
        "from_pretrained",
        "push_to_hub",
        "requests",
        "os.makedirs",
        "json.load",
        "json.dump",
        "download",
        "FourierEmb",
    ):
        assert forbidden_surface not in source
