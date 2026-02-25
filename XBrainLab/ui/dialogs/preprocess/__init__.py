"""Preprocessing dialog components for EEG signal processing.

Provides dialogs for epoching, filtering, normalization, re-referencing,
and resampling operations.
"""

from .epoching_dialog import EpochingDialog
from .filtering_dialog import FilteringDialog
from .normalize_dialog import NormalizeDialog
from .rereference_dialog import RereferenceDialog
from .resampling_dialog import ResampleDialog

__all__ = [
    "EpochingDialog",
    "FilteringDialog",
    "NormalizeDialog",
    "RereferenceDialog",
    "ResampleDialog",
]
