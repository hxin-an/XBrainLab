"""Visualization dialog components for EEG analysis results.

Provides dialogs for saliency map export, montage channel mapping,
and saliency method configuration.
"""

from .export_saliency_dialog import ExportSaliencyDialog
from .montage_picker_dialog import PickMontageDialog
from .saliency_setting_dialog import SaliencySettingDialog

__all__ = [
    "ExportSaliencyDialog",
    "PickMontageDialog",
    "SaliencySettingDialog",
]
