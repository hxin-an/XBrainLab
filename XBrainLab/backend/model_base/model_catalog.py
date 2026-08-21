"""Curated EEG model catalog shared by UI and command clients.

Braindecode is imported only when a selected model is instantiated. Keeping the
catalog metadata lightweight prevents the Dataset and Training panels from paying
the model-library import cost during application startup.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from types import ModuleType
from typing import Any

from XBrainLab.backend.model_base.braindecode_catalog import (
    BRAINCDECODE_CATALOG_ENTRIES,
    BRAINCDECODE_SOURCE_REVISION,
    BraindecodeCatalogEntry,
)
from XBrainLab.backend.model_catalog_contract import (
    BRAINDECODE_MODEL_IDS,
    DEFAULT_MODEL_ID,
    TRAINING_MODEL_NAMES,
)

ModelFactory = Callable[..., Any]
_BRAINCDECODE_MATPLOTLIB_STYLE_LOCK = RLock()


@dataclass(frozen=True, slots=True)
class ModelParameter:
    """One curated, user-editable model parameter."""

    key: str
    label: str
    default: Any
    tooltip: str


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """Stable product identity and construction contract for one EEG model."""

    model_id: str
    display_name: str
    source: str
    factory: ModelFactory
    parameters: tuple[ModelParameter, ...] = ()
    provider: str = "xbrainlab"
    source_revision: str = "xbrainlab"
    family: str = "Local"
    task: str = "classification"
    aliases: tuple[str, ...] = ()
    license_id: str = "XBrainLab"
    required_inputs: tuple[str, ...] = ()
    available: bool = True
    unavailable_reason: str = ""
    legacy_copy_allowed: bool = False
    legacy_unavailable_reason: str = ""

    def default_parameters(self) -> dict[str, Any]:
        return {parameter.key: parameter.default for parameter in self.parameters}


@dataclass(frozen=True, slots=True)
class BraindecodeProviderStatus:
    """Availability of the one pinned upstream Braindecode provider."""

    available: bool
    installed_version: str | None
    reason: str


def _parameter(key: str, label: str, default: Any, description: str) -> ModelParameter:
    return ModelParameter(key=key, label=label, default=default, tooltip=description)


_BRAINCDECODE_MODELS: tuple[tuple[str, str, tuple[ModelParameter, ...]], ...] = (
    (
        "EEGNet",
        "EEGNet",
        (
            _parameter("F1", "Temporal filters", 8, "Number of temporal filters."),
            _parameter(
                "D", "Depth multiplier", 2, "Spatial filters per temporal filter."
            ),
            _parameter(
                "F2",
                "Pointwise filters",
                None,
                "Pointwise filters; None derives F1 x D.",
            ),
            _parameter(
                "kernel_length",
                "Temporal kernel",
                64,
                "Temporal kernel length in samples.",
            ),
            _parameter("drop_prob", "Dropout", 0.25, "Dropout probability."),
        ),
    ),
    (
        "ShallowFBCSPNet",
        "ShallowFBCSPNet",
        (
            _parameter(
                "n_filters_time", "Temporal filters", 40, "Number of temporal filters."
            ),
            _parameter(
                "filter_time_length",
                "Temporal kernel",
                25,
                "Temporal kernel length in samples.",
            ),
            _parameter(
                "n_filters_spat", "Spatial filters", 40, "Number of spatial filters."
            ),
            _parameter(
                "pool_time_length", "Pooling window", 75, "Pooling window in samples."
            ),
            _parameter(
                "pool_time_stride", "Pooling stride", 15, "Pooling stride in samples."
            ),
            _parameter("drop_prob", "Dropout", 0.5, "Dropout probability."),
        ),
    ),
    (
        "Deep4Net",
        "Deep4Net",
        (
            _parameter(
                "n_filters_time", "Temporal filters", 25, "First temporal-filter count."
            ),
            _parameter(
                "filter_time_length",
                "Temporal kernel",
                10,
                "First temporal kernel in samples.",
            ),
            _parameter(
                "n_filters_spat", "Spatial filters", 25, "First spatial-filter count."
            ),
            _parameter("drop_prob", "Dropout", 0.5, "Dropout probability."),
        ),
    ),
    (
        "EEGConformer",
        "EEGConformer",
        (
            _parameter(
                "n_filters_time",
                "Temporal filters",
                40,
                "Convolutional temporal-filter count.",
            ),
            _parameter(
                "num_layers",
                "Transformer layers",
                6,
                "Number of transformer encoder layers.",
            ),
            _parameter(
                "num_heads", "Attention heads", 10, "Number of attention heads."
            ),
            _parameter(
                "drop_prob", "Dropout", 0.5, "Convolutional dropout probability."
            ),
            _parameter(
                "att_drop_prob",
                "Attention dropout",
                0.5,
                "Attention dropout probability.",
            ),
        ),
    ),
    (
        "ATCNet",
        "ATCNet",
        (
            _parameter(
                "conv_block_n_filters",
                "Convolution filters",
                16,
                "Convolution-block filter count.",
            ),
            _parameter(
                "n_windows",
                "Attention windows",
                5,
                "Number of temporal attention windows.",
            ),
            _parameter("num_heads", "Attention heads", 2, "Number of attention heads."),
            _parameter(
                "tcn_depth", "TCN depth", 2, "Temporal-convolution network depth."
            ),
            _parameter(
                "conv_block_dropout",
                "Convolution dropout",
                0.3,
                "Convolution-block dropout probability.",
            ),
            _parameter("tcn_drop_prob", "TCN dropout", 0.3, "TCN dropout probability."),
        ),
    ),
    (
        "EEGInceptionERP",
        "EEGInceptionERP",
        (
            _parameter(
                "n_filters", "Inception filters", 8, "Filters per inception branch."
            ),
            _parameter(
                "depth_multiplier",
                "Depth multiplier",
                2,
                "Depthwise convolution multiplier.",
            ),
            _parameter("drop_prob", "Dropout", 0.5, "Dropout probability."),
        ),
    ),
    (
        "SCCNet",
        "SCCNet",
        (
            _parameter(
                "n_spatial_filters",
                "Spatial filters",
                22,
                "First spatial-filter count.",
            ),
            _parameter(
                "n_spatial_filters_smooth",
                "Smoothed spatial filters",
                20,
                "Spatio-temporal filter count.",
            ),
            _parameter("drop_prob", "Dropout", 0.5, "Dropout probability."),
        ),
    ),
    (
        "EEGNeX",
        "EEGNeX",
        (
            _parameter(
                "filter_1", "First filters", 8, "First convolution filter count."
            ),
            _parameter(
                "filter_2", "Second filters", 32, "Second convolution filter count."
            ),
            _parameter(
                "depth_multiplier",
                "Depth multiplier",
                2,
                "Depthwise convolution multiplier.",
            ),
            _parameter("drop_prob", "Dropout", 0.5, "Dropout probability."),
        ),
    ),
    (
        "EEGITNet",
        "EEGITNet",
        (
            _parameter(
                "n_filters_time", "Temporal filters", 2, "Temporal filter count."
            ),
            _parameter(
                "kernel_length",
                "Temporal kernel",
                16,
                "Temporal kernel length in samples.",
            ),
            _parameter(
                "pool_kernel", "Pooling window", 4, "Pooling window in samples."
            ),
            _parameter(
                "tcn_in_channel",
                "TCN channels",
                14,
                "Input channels for the TCN block.",
            ),
            _parameter("drop_prob", "Dropout", 0.4, "Dropout probability."),
        ),
    ),
    (
        "CTNet",
        "CTNet",
        (
            _parameter("num_heads", "Attention heads", 4, "Number of attention heads."),
            _parameter(
                "embed_dim", "Embedding size", 40, "Transformer embedding dimension."
            ),
            _parameter(
                "num_layers", "Transformer layers", 6, "Number of transformer layers."
            ),
            _parameter(
                "kernel_size",
                "Temporal kernel",
                64,
                "Temporal kernel length in samples.",
            ),
            _parameter(
                "depth_multiplier",
                "Depth multiplier",
                2,
                "Depthwise convolution multiplier.",
            ),
            _parameter("cnn_drop_prob", "CNN dropout", 0.3, "CNN dropout probability."),
            _parameter(
                "final_drop_prob",
                "Final dropout",
                0.5,
                "Classifier dropout probability.",
            ),
        ),
    ),
)

_REQUIRED_LOCAL_ARGUMENTS = {"self", "n_classes", "channels", "samples", "sfreq"}
_LOCAL_DISPLAY_NAMES = {
    "EEGNet": "EEGNet (XBrainLab)",
    "ShallowConvNet": "ShallowConvNet (XBrainLab)",
    "SCCNet": "SCCNet (XBrainLab)",
}
_PARAMETER_LABELS = {
    "f1": "Temporal filters",
    "f2": "Pointwise filters",
    "d": "Depth multiplier",
    "pool_1": "First pooling size",
    "pool_2": "Second pooling size",
    "ns": "Spatial filters",
    "pool_len": "Pooling window",
    "pool_stride": "Pooling stride",
}


def default_model_id() -> str:
    """Return the product default architecture."""
    return DEFAULT_MODEL_ID


def model_command_names() -> tuple[str, ...]:
    """Return stable command values plus compatible legacy local names."""
    return TRAINING_MODEL_NAMES


def braindecode_provider_status() -> BraindecodeProviderStatus:
    """Run the provider import preflight and return a fail-closed status."""
    installation_status = _braindecode_installation_status()
    if not installation_status.available:
        return installation_status
    try:
        importlib.import_module("braindecode.models.eegnet")
    except Exception as exc:
        return BraindecodeProviderStatus(
            available=False,
            installed_version=installation_status.installed_version,
            reason=(
                "The pinned Braindecode provider could not be loaded "
                f"({type(exc).__name__})."
            ),
        )
    return installation_status


def _braindecode_installation_status() -> BraindecodeProviderStatus:
    """Inspect package identity without importing the heavyweight provider."""
    if importlib.util.find_spec("braindecode") is None:
        return BraindecodeProviderStatus(
            available=False,
            installed_version=None,
            reason=f"{BRAINCDECODE_SOURCE_REVISION} is not installed.",
        )
    try:
        installed_version = importlib.metadata.version("braindecode")
    except importlib.metadata.PackageNotFoundError:
        return BraindecodeProviderStatus(
            available=False,
            installed_version=None,
            reason=f"{BRAINCDECODE_SOURCE_REVISION} is not installed.",
        )
    expected_version = BRAINCDECODE_SOURCE_REVISION.partition("==")[2]
    if installed_version != expected_version:
        return BraindecodeProviderStatus(
            available=False,
            installed_version=installed_version,
            reason=(
                f"{BRAINCDECODE_SOURCE_REVISION} is required; "
                f"found braindecode=={installed_version}."
            ),
        )
    return BraindecodeProviderStatus(
        available=True,
        installed_version=installed_version,
        reason="",
    )


def discover_model_specs(
    local_model_module: ModuleType,
    *,
    include_braindecode: bool = True,
) -> tuple[ModelSpec, ...]:
    """Return curated external models followed by locally implemented models."""
    local_models = inspect.getmembers(local_model_module, inspect.isclass)
    known_local_models = any(name in _LOCAL_DISPLAY_NAMES for name, _ in local_models)
    specs: list[ModelSpec] = []
    if include_braindecode and known_local_models:
        specs.extend(_braindecode_specs())
    for class_name, model_class in local_models:
        specs.append(_local_model_spec(class_name, model_class))
    return tuple(specs)


def discover_braindecode_model_specs() -> tuple[ModelSpec, ...]:
    """Return the complete pinned upstream catalog, including unavailable entries."""
    return _braindecode_specs(BRAINCDECODE_CATALOG_ENTRIES)


def get_model_spec(model_name: str) -> ModelSpec:
    """Resolve a stable id, display label, or compatible legacy model name."""
    model_base = importlib.import_module("XBrainLab.backend.model_base")
    normalized = str(model_name).strip().casefold()
    specs = discover_model_specs(model_base)
    by_value = {
        value.casefold(): spec
        for spec in specs
        for value in (spec.model_id, spec.display_name, *spec.aliases)
    }
    for spec in specs:
        class_name = getattr(spec.factory, "__name__", "")
        if spec.source == "xbrainlab":
            # Preserve old recipes and agent calls: an unsuffixed local class name
            # keeps its historical meaning instead of silently changing architecture.
            by_value[class_name.casefold()] = spec
    for spec in specs:
        class_name = getattr(spec.factory, "__name__", "")
        if spec.source == "braindecode":
            by_value.setdefault(class_name.removeprefix("Braindecode").casefold(), spec)
    result = by_value.get(normalized)
    if result is None:
        raise ValueError(f"Unknown model architecture: {model_name}")
    return result


def _braindecode_specs(
    entries: tuple[BraindecodeCatalogEntry, ...] | None = None,
) -> tuple[ModelSpec, ...]:
    provider_status = braindecode_provider_status()
    selected_entries = entries
    if selected_entries is None:
        entries_by_id = {
            entry.model_id: entry for entry in BRAINCDECODE_CATALOG_ENTRIES
        }
        selected_entries = tuple(
            entries_by_id[model_id] for model_id in BRAINDECODE_MODEL_IDS
        )
    return tuple(
        _braindecode_model_spec(entry, provider_status) for entry in selected_entries
    )


def _braindecode_model_spec(
    entry: BraindecodeCatalogEntry,
    provider_status: BraindecodeProviderStatus,
) -> ModelSpec:
    curated_parameters = {
        class_name: parameters
        for class_name, _display_name, parameters in _BRAINCDECODE_MODELS
    }
    unavailable_reasons = tuple(
        reason
        for reason in (entry.unavailable_reason, provider_status.reason)
        if reason
    )
    return ModelSpec(
        model_id=entry.model_id,
        display_name=f"{entry.class_name} (Braindecode)",
        source="braindecode",
        factory=_braindecode_factory(entry.module_name, entry.class_name),
        parameters=curated_parameters.get(entry.class_name, ()),
        provider="braindecode",
        source_revision=BRAINCDECODE_SOURCE_REVISION,
        family=entry.family,
        task=entry.task,
        aliases=(entry.class_name,),
        license_id=entry.license_id,
        required_inputs=entry.required_inputs,
        available=not unavailable_reasons,
        unavailable_reason=" ".join(unavailable_reasons),
        legacy_copy_allowed=entry.legacy_copy_allowed,
        legacy_unavailable_reason=entry.legacy_unavailable_reason,
    )


def _braindecode_factory(module_name: str, class_name: str) -> ModelFactory:
    def build_model(**kwargs: Any) -> Any:
        # Braindecode imports visualization helpers that apply a global
        # Seaborn/Matplotlib theme. Model construction is a backend operation;
        # it must not silently change geometry and fonts in later product plots.
        matplotlib = importlib.import_module("matplotlib")
        with _BRAINCDECODE_MATPLOTLIB_STYLE_LOCK, matplotlib.rc_context():
            models = importlib.import_module(module_name)
            model_class = getattr(models, class_name)
            required = {
                "n_outputs": kwargs.pop("n_classes"),
                "n_chans": kwargs.pop("channels"),
                "n_times": kwargs.pop("samples"),
                "sfreq": kwargs.pop("sfreq"),
            }
            return model_class(**required, **kwargs)

    build_model.__name__ = f"Braindecode{class_name}"
    return build_model


def _local_model_spec(class_name: str, model_class: type) -> ModelSpec:
    parameters: list[ModelParameter] = []
    for name, parameter in inspect.signature(model_class.__init__).parameters.items():
        if name in _REQUIRED_LOCAL_ARGUMENTS:
            continue
        default = (
            None if parameter.default is inspect.Parameter.empty else parameter.default
        )
        label = _PARAMETER_LABELS.get(name, name)
        parameters.append(
            ModelParameter(
                key=name,
                label=label,
                default=default,
                tooltip=f"Model constructor parameter: {name}",
            ),
        )
    display_name = _LOCAL_DISPLAY_NAMES.get(class_name, class_name)
    return ModelSpec(
        model_id=f"xbrainlab.{class_name.casefold()}",
        display_name=display_name,
        source="xbrainlab",
        factory=model_class,
        parameters=tuple(parameters),
        provider="xbrainlab",
        source_revision="xbrainlab",
        family="Local",
        task="classification",
        aliases=(class_name,),
        license_id="XBrainLab",
        required_inputs=("n_classes", "channels", "samples", "sfreq"),
        legacy_copy_allowed=True,
    )
