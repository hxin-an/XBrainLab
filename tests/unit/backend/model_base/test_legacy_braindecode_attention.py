from __future__ import annotations

# pyright: reportArgumentType=false
import importlib
from pathlib import Path

import pytest
import torch

from XBrainLab.backend.model_base.legacy_braindecode import models as legacy_models

_ATTENTION_MODELS = (
    ("atcnet", "ATCNet"),
    ("attentionbasenet", "AttentionBaseNet"),
    ("ctnet", "CTNet"),
    ("eegconformer", "EEGConformer"),
    ("medformer", "MEDFormer"),
    ("msvtnet", "MSVTNet"),
    ("mvpformer", "MVPFormer"),
    ("patchedtransformer", "PBT"),
    ("steegformer", "STEEGFormer"),
    ("tcformer", "TCFormer"),
)


def _model_kwargs(class_name: str) -> dict[str, object]:
    common: dict[str, object] = {
        "n_chans": 4,
        "n_outputs": 3,
        "n_times": 256,
    }
    if class_name == "ATCNet":
        return common | {
            "sfreq": 128.0,
            "conv_block_n_filters": 4,
            "conv_block_kernel_length_1": 32,
            "conv_block_kernel_length_2": 8,
            "conv_block_pool_size_1": 4,
            "conv_block_pool_size_2": 4,
            "n_windows": 3,
            "head_dim": 4,
            "num_heads": 2,
            "tcn_depth": 1,
            "tcn_kernel_size": 3,
        }
    if class_name == "AttentionBaseNet":
        return common | {
            "sfreq": 128.0,
            "n_temporal_filters": 4,
            "temp_filter_length_inp": 15,
            "spatial_expansion": 1,
            "pool_length_inp": 16,
            "pool_stride_inp": 4,
            "ch_dim": 8,
            "temp_filter_length": 7,
            "pool_length": 4,
            "pool_stride": 4,
            "attention_mode": "se",
            "reduction_rate": 2,
        }
    if class_name == "CTNet":
        return common | {
            "sfreq": 128.0,
            "embed_dim": 8,
            "num_layers": 1,
            "num_heads": 2,
            "n_filters_time": 4,
            "kernel_size": 32,
            "depth_multiplier": 2,
            "pool_size_1": 4,
            "pool_size_2": 4,
        }
    if class_name == "EEGConformer":
        return common | {
            "n_filters_time": 8,
            "filter_time_length": 15,
            "pool_time_length": 32,
            "pool_time_stride": 8,
            "num_layers": 1,
            "num_heads": 2,
            "final_fc_length": "auto",
        }
    if class_name == "MEDFormer":
        return common | {
            "patch_len_list": [8, 16],
            "embed_dim": 16,
            "num_heads": 2,
            "num_layers": 1,
            "dim_feedforward": 32,
            "output_attention": False,
        }
    if class_name == "MSVTNet":
        return common | {
            "n_filters_list": (2, 2),
            "conv1_kernels_size": (15, 31),
            "conv2_kernel_size": 7,
            "depth_multiplier": 1,
            "pool1_size": 4,
            "pool2_size": 4,
            "num_heads": 2,
            "num_layers": 1,
        }
    if class_name == "MVPFormer":
        return common | {
            "segment_len": 64,
            "d_model": 32,
            "n_layers": 1,
            "n_heads": 4,
            "n_head_kv": 2,
            "d_inner": 64,
            "local_window": 2,
            "max_segments": 8,
            "max_channels": 8,
        }
    if class_name == "PBT":
        return common | {
            "d_input": 32,
            "embed_dim": 32,
            "num_layers": 1,
            "num_heads": 4,
        }
    if class_name == "STEEGFormer":
        return common | {
            "patch_size": 16,
            "embed_dim": 32,
            "depth": 1,
            "num_heads": 4,
            "mlp_ratio": 2,
            "n_chans_pos": 16,
        }
    if class_name == "TCFormer":
        return common | {
            "n_filters_time": 4,
            "temp_kernel_lengths": (8, 16),
            "depth_multiplier": 1,
            "pool_length_1": 4,
            "pool_length_2": 4,
            "temp_kernel_length_2": 8,
            "group_dim": 4,
            "se_reduction": 2,
            "n_transformer_layers": 1,
            "q_heads": 2,
            "kv_heads": 1,
            "mlp_ratio": 2,
            "drop_path_max": 0.0,
            "tcn_depth": 1,
            "tcn_kernel_length": 3,
        }
    raise AssertionError(f"Unknown model case: {class_name}")


@pytest.mark.parametrize(("module_name", "class_name"), _ATTENTION_MODELS)
def test_local_attention_strictly_loads_upstream_state_and_matches_output(
    module_name: str,
    class_name: str,
) -> None:
    upstream_module = importlib.import_module(f"braindecode.models.{module_name}")
    upstream_class = getattr(upstream_module, class_name)
    legacy_class = getattr(legacy_models, class_name)
    kwargs = _model_kwargs(class_name)

    torch.manual_seed(151)
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

    inputs = torch.randn(2, 4, 256, generator=torch.Generator().manual_seed(157))
    with torch.inference_mode():
        expected = upstream(inputs)
        actual = legacy(inputs)

    torch.testing.assert_close(actual, expected, rtol=1e-6, atol=1e-7)


@pytest.mark.parametrize("class_name", ("AttentionBaseNet", "MVPFormer", "TCFormer"))
def test_local_attention_representatives_support_finite_backward(
    class_name: str,
) -> None:
    model_class = getattr(legacy_models, class_name)
    model = model_class(**_model_kwargs(class_name)).train()
    inputs = torch.randn(2, 4, 256, generator=torch.Generator().manual_seed(163))

    loss = model(inputs).square().mean()
    loss.backward()

    gradients = [
        parameter.grad for parameter in model.parameters() if parameter.requires_grad
    ]
    assert gradients
    finite_gradients = [gradient for gradient in gradients if gradient is not None]
    assert finite_gradients
    assert all(torch.isfinite(gradient).all() for gradient in finite_gradients)


def test_local_steegformer_never_downloads_channel_metadata() -> None:
    source_path = Path(legacy_models.__file__).parent / "steegformer.py"
    source = source_path.read_text(encoding="utf-8")

    assert "huggingface_hub" not in source
    assert "hf_hub_download" not in source

    with pytest.raises(ValueError, match="chan_pos_idx"):
        legacy_models.STEEGFormer(
            **_model_kwargs("STEEGFormer"),
            chs_info=[{"ch_name": name} for name in ("C3", "C4", "Cz", "Fz")],
        )
