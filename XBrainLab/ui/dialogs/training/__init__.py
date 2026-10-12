"""Training dialog components for model configuration.

Provides dialogs for model architecture selection,
optimizer configuration, and training parameter settings.
"""

from .model_selection_dialog import ModelSelectionDialog
from .optimizer_setting_dialog import OptimizerSettingDialog
from .training_setting_dialog import TrainingSettingDialog

__all__ = [
    "ModelSelectionDialog",
    "OptimizerSettingDialog",
    "TrainingSettingDialog",
]
