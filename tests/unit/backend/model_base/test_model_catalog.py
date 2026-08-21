from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace

import matplotlib
import pytest
import torch

from XBrainLab.backend import model_base
from XBrainLab.backend.model_base import model_catalog
from XBrainLab.backend.model_base.model_catalog import (
    BRAINCDECODE_SOURCE_REVISION,
    braindecode_provider_status,
    default_model_id,
    discover_braindecode_model_specs,
    discover_model_specs,
    get_model_spec,
)
from XBrainLab.backend.model_catalog_contract import BRAINDECODE_MODEL_IDS

_BASELINE_FORWARD_MODEL_IDS = (
    "braindecode.eegnet",
    "braindecode.shallowfbcspnet",
    "braindecode.deep4net",
    "braindecode.eegconformer",
    "braindecode.atcnet",
    "braindecode.eeginceptionerp",
    "braindecode.sccnet",
    "braindecode.eegnex",
    "braindecode.eegitnet",
    "braindecode.ctnet",
)


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
    assert all(
        spec.source_revision == BRAINCDECODE_SOURCE_REVISION for spec in specs[:10]
    )
    assert all(spec.provider == "braindecode" for spec in specs[:10])


def test_complete_braindecode_inventory_has_61_pinned_contracts() -> None:
    specs = discover_braindecode_model_specs()

    assert len(specs) == 61
    assert len({spec.model_id for spec in specs}) == 61
    assert all(spec.model_id.startswith("braindecode.") for spec in specs)
    assert all(spec.source_revision == BRAINCDECODE_SOURCE_REVISION for spec in specs)
    assert all(spec.provider == "braindecode" for spec in specs)


def test_complete_inventory_matches_upstream_constructor_contract() -> None:
    from braindecode.models.util import models_mandatory_parameters

    specs = discover_braindecode_model_specs()
    actual = [(spec.aliases[0], spec.required_inputs) for spec in specs]
    expected = [
        (class_name, tuple(required_inputs))
        for class_name, required_inputs, _example_kwargs in models_mandatory_parameters
    ]

    assert actual == expected


def test_unverified_source_is_not_eligible_for_legacy_copy() -> None:
    specs = {spec.model_id: spec for spec in discover_braindecode_model_specs()}

    eegnet = specs["braindecode.eegnet"]
    assert eegnet.license_id == "UNVERIFIED"
    assert eegnet.legacy_copy_allowed is False
    assert "provenance" in eegnet.legacy_unavailable_reason.casefold()


def test_catalog_surfaces_restricted_and_non_classification_models_as_unavailable() -> (
    None
):
    specs = {spec.model_id: spec for spec in discover_braindecode_model_specs()}

    restricted = specs["braindecode.eegminer"]
    assert restricted.available is False
    assert restricted.license_id == "CC-BY-NC-4.0"
    assert "license" in restricted.unavailable_reason.casefold()

    representation = specs["braindecode.signaljepa"]
    assert representation.available is False
    assert representation.task == "representation"
    assert "classification" in representation.unavailable_reason.casefold()


def test_braindecode_provider_status_requires_exact_pinned_version(monkeypatch) -> None:
    monkeypatch.setattr(
        model_catalog.importlib.util, "find_spec", lambda _name: object()
    )
    monkeypatch.setattr(
        model_catalog.importlib.metadata, "version", lambda _name: "1.6.2"
    )

    status = braindecode_provider_status()

    assert status.available is False
    assert status.installed_version == "1.6.2"
    assert BRAINCDECODE_SOURCE_REVISION in status.reason


def test_braindecode_provider_status_rejects_import_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        model_catalog.importlib.util, "find_spec", lambda _name: object()
    )
    monkeypatch.setattr(
        model_catalog.importlib.metadata, "version", lambda _name: "1.6.1"
    )

    def fail_import(_name: str):
        raise ImportError("missing transitive dependency")

    monkeypatch.setattr(model_catalog.importlib, "import_module", fail_import)

    status = braindecode_provider_status()

    assert status.available is False
    assert status.installed_version == "1.6.1"
    assert "ImportError" in status.reason


def test_broken_provider_disables_visible_upstream_projection(monkeypatch) -> None:
    monkeypatch.setattr(
        model_catalog.importlib.util, "find_spec", lambda _name: object()
    )
    monkeypatch.setattr(
        model_catalog.importlib.metadata, "version", lambda _name: "1.6.1"
    )

    def fail_import(_name: str):
        raise ImportError("missing transitive dependency")

    monkeypatch.setattr(model_catalog.importlib, "import_module", fail_import)

    specs = discover_braindecode_model_specs()

    assert specs
    assert all(spec.available is False for spec in specs)
    assert all(
        "provider could not be loaded" in spec.unavailable_reason for spec in specs
    )


def test_catalog_import_does_not_eagerly_import_braindecode_models() -> None:
    process = subprocess.run(  # noqa: S603 - current interpreter, fixed test code
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import XBrainLab.backend.model_base.model_catalog; "
                "assert 'braindecode.models' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert process.returncode == 0, process.stderr


def test_braindecode_factory_contains_third_party_matplotlib_style_changes(
    monkeypatch,
) -> None:
    spec = get_model_spec("braindecode.eegnet")
    original_import_module = model_catalog.importlib.import_module
    original_font_size = matplotlib.rcParams["font.size"]

    def import_module(name: str):
        if name == "braindecode.models.eegnet":
            matplotlib.rcParams["font.size"] = float(original_font_size) + 7.0
            return SimpleNamespace(EEGNet=lambda **kwargs: kwargs)
        return original_import_module(name)

    monkeypatch.setattr(model_catalog.importlib, "import_module", import_module)

    built = spec.factory(n_classes=2, channels=4, samples=128, sfreq=128.0)

    assert built["n_outputs"] == 2
    assert matplotlib.rcParams["font.size"] == original_font_size


@pytest.mark.parametrize("model_id", _BASELINE_FORWARD_MODEL_IDS)
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
