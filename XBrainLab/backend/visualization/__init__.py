"""Visualization subpackage for EEG saliency and training metric plots."""

# ruff: noqa: I001 - supported_saliency_methods must be available before plot_type
# imports pull in the training stack.
from .saliency_methods import supported_saliency_methods
from .plot_type import PlotType, VisualizerType

__all__ = [
    "PlotType",
    "VisualizerType",
    "supported_saliency_methods",
]
