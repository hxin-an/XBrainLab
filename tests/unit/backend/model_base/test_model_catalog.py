from __future__ import annotations

import sys

import pytest
import torch

from XBrainLab.backend import model_base
from XBrainLab.backend.model_base.model_catalog import (
    default_model_id,
    discover_model_specs,
    get_model_spec,
)
from XBrainLab.backend.model_catalog_contract import BRAINDECODE_MODEL_IDS


def test_catalog_exposes_curated_braindecode_and_legacy_models() -> None:
    specs = discover_model_specs(model_base)

    assert [spec.model_id for spec in specs[:10]] == list(BRAINDECODE_MODEL_IDS)
    assert default_model_id() == "braindecode.eegnet"
    assert {spec.display_name for spec in specs} >= {
        "EEGNet (Braindecode)",
        "ShallowFBCSPNet (Braindecode)",
        "Deep4Net (Braindecode)",
        "EEGConformer (Braindecode)",
        "ATCNet (Braindecode)",
        "EEGInceptionERP (Braindecode)",
        "SCCNet (Braindecode)",
        "EEGNeX (Braindecode)",
        "EEGITNet (Braindecode)",
        "CTNet (Braindecode)",
        "EEGNet (XBrainLab)",
        "ShallowConvNet (XBrainLab)",
        "SCCNet (XBrainLab)",
    }


def test_catalog_import_does_not_eagerly_import_braindecode_models() -> None:
    assert "braindecode.models" not in sys.modules


@pytest.mark.parametrize("model_id", BRAINDECODE_MODEL_IDS)
def test_curated_braindecode_model_builds_for_standard_eeg_input(model_id: str) -> None:
    spec = get_model_spec(model_id)
    model = spec.factory(
        n_classes=4,
        channels=22,
        samples=301,
        sfreq=250.0,
        **spec.default_parameters(),
    )

    with torch.no_grad():
        output = model(torch.randn(2, 22, 301))

    assert tuple(output.shape) == (2, 4)


def test_required_dimensions_are_not_exposed_as_editable_parameters() -> None:
    spec = get_model_spec("braindecode.eegnet")

    assert {parameter.key for parameter in spec.parameters}.isdisjoint(
        {"n_outputs", "n_chans", "n_times", "sfreq"},
    )
    assert spec.default_parameters()["F1"] == 8
