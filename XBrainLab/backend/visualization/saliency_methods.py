"""Compatibility re-export for canonical backend saliency method names."""

from XBrainLab.backend.saliency_methods import (
    all_saliency_methods,
    recommended_saliency_methods,
    supported_saliency_methods,
)

__all__ = [
    "all_saliency_methods",
    "recommended_saliency_methods",
    "supported_saliency_methods",
]
