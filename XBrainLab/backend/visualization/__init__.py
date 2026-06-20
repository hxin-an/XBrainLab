"""Visualization subpackage for EEG saliency and training metric plots."""

# ruff: noqa: I001 - saliency method names must be available before plot_type
# imports pull in the training stack.
from .saliency_methods import (
    all_saliency_methods,
    recommended_saliency_methods,
    supported_saliency_methods,
)
from .plot_type import PlotType, VisualizerType

__all__ = [
    "PlotType",
    "VisualizerType",
    "all_saliency_methods",
    "recommended_saliency_methods",
    "supported_saliency_methods",
]
