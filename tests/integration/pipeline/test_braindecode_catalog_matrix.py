"""Product-catalog construction and gradient matrix for Braindecode 1.6.1."""

from __future__ import annotations

import gc
from typing import Any

import mne
import pytest
import torch

from XBrainLab.backend.model_base.model_catalog import (
    BraindecodeProviderStatus,
    discover_braindecode_model_specs,
    get_model_spec,
)

_HEALTHY_PROVIDER = BraindecodeProviderStatus(
    available=True,
    installed_version="1.6.1",
    reason="",
    checked=True,
)
_STANDARD_CHANNEL_NAMES = (
    "Fp1",
    "Fp2",
    "F7",
    "F3",
    "Fz",
    "F4",
    "F8",
    "T7",
    "C3",
    "Cz",
    "C4",
    "T8",
    "P7",
    "P3",
    "Pz",
    "P4",
    "P8",
    "O1",
    "Oz",
    "O2",
    "FC1",
    "FC2",
)
_STATIC_SELECTABLE_MODEL_IDS = tuple(
    spec.model_id
    for spec in discover_braindecode_model_specs(
        provider_status=_HEALTHY_PROVIDER,
    )
    if spec.available
)


def _standard_chs_info(channels: int, sfreq: float) -> list[dict[str, Any]]:
    names = list(_STANDARD_CHANNEL_NAMES[:channels])
    info = mne.create_info(names, sfreq=sfreq, ch_types="eeg")
    info.set_montage(mne.channels.make_standard_montage("standard_1020"))
    return [dict(channel) for channel in info["chs"]]


def _signal_context(model_id: str) -> dict[str, Any]:
    channels = 22
    samples = 256
    sfreq = 128.0
    chs_info: list[dict[str, Any]] | None = None

    if model_id == "braindecode.sleepstagerblanco2020":
        samples = 512
    elif model_id == "braindecode.attnsleep":
        channels = 1
        samples = 3_000
        sfreq = 100.0
    elif model_id == "braindecode.labram":
        from XBrainLab.backend.model_base.legacy_braindecode.models.labram import (
            LABRAM_CHANNEL_ORDER,
        )

        channels = len(LABRAM_CHANNEL_ORDER)
        samples = 400
        chs_info = [
            {"ch_name": name, "loc": [float("nan")] * 12}
            for name in LABRAM_CHANNEL_ORDER
        ]
    elif model_id == "braindecode.interpolatedlabram":
        samples = 400
    elif model_id == "braindecode.luna":
        samples = 280
    elif model_id == "braindecode.cbramod":
        samples = 400
    elif model_id == "braindecode.eegdino":
        channels = 19

    if chs_info is None:
        chs_info = _standard_chs_info(channels, sfreq)
    return {
        "n_classes": 4,
        "channels": channels,
        "samples": samples,
        "sfreq": sfreq,
        "chs_info": chs_info,
    }


def test_static_selectable_inventory_remains_complete() -> None:
    assert len(_STATIC_SELECTABLE_MODEL_IDS) == 54
    assert len(set(_STATIC_SELECTABLE_MODEL_IDS)) == 54


@pytest.mark.parametrize("model_id", _STATIC_SELECTABLE_MODEL_IDS)
def test_selectable_upstream_model_builds_and_supports_finite_gradient(
    model_id: str,
) -> None:
    context = _signal_context(model_id)
    spec = get_model_spec(
        model_id,
        provider_status=_HEALTHY_PROVIDER,
        signal_context=context,
    )
    assert spec.available, spec.unavailable_reason

    torch.manual_seed(1301)
    model = spec.factory(**context, **spec.default_parameters()).eval()
    inputs = torch.randn(
        1,
        context["channels"],
        context["samples"],
        generator=torch.Generator().manual_seed(1303),
    )
    output = model(inputs)

    assert isinstance(output, torch.Tensor)
    assert tuple(output.shape) == (1, 4)
    assert torch.isfinite(output).all()

    output.float().square().mean().backward()
    gradients = [
        parameter.grad
        for parameter in model.parameters()
        if parameter.requires_grad and parameter.grad is not None
    ]
    assert gradients
    assert all(torch.isfinite(gradient).all() for gradient in gradients)

    del output, inputs, model
    gc.collect()
