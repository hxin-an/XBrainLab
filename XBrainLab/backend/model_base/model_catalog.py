"""Curated EEG model catalog shared by UI and command clients.

Braindecode is imported only when a selected model is instantiated. Keeping the
catalog metadata lightweight prevents the Dataset and Training panels from paying
the model-library import cost during application startup.
"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from types import ModuleType
from typing import Any

from XBrainLab.backend.model_catalog_contract import (
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

    def default_parameters(self) -> dict[str, Any]:
        return {parameter.key: parameter.default for parameter in self.parameters}


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


def get_model_spec(model_name: str) -> ModelSpec:
    """Resolve a stable id, display label, or compatible legacy model name."""
    model_base = importlib.import_module("XBrainLab.backend.model_base")
    normalized = str(model_name).strip().casefold()
    specs = discover_model_specs(model_base)
    by_value = {
        value.casefold(): spec
        for spec in specs
        for value in (spec.model_id, spec.display_name)
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


def _braindecode_specs() -> tuple[ModelSpec, ...]:
    return tuple(
        ModelSpec(
            model_id=f"braindecode.{class_name.casefold()}",
            display_name=f"{display_name} (Braindecode)",
            source="braindecode",
            factory=_braindecode_factory(class_name),
            parameters=parameters,
        )
        for class_name, display_name, parameters in _BRAINCDECODE_MODELS
    )


def _braindecode_factory(class_name: str) -> ModelFactory:
    def build_model(**kwargs: Any) -> Any:
        # Braindecode imports visualization helpers that apply a global
        # Seaborn/Matplotlib theme. Model construction is a backend operation;
        # it must not silently change geometry and fonts in later product plots.
        matplotlib = importlib.import_module("matplotlib")
        with _BRAINCDECODE_MATPLOTLIB_STYLE_LOCK, matplotlib.rc_context():
            models = importlib.import_module("braindecode.models")
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
    )
