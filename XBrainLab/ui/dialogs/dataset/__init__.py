# pyright: reportUnsupportedDunderAll=false
"""Dataset dialog components for EEG data management.

Dialog modules are intentionally lazy. Dataset panel startup imports this
package for compatibility in a few call sites, but the full Data Import wizard,
split dialogs, and label tools should load only when the user opens them.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORT_MODULES = {
    "ChannelSelectionDialog": ".channel_selection_dialog",
    "DataInterpretationPreviewDialog": ".data_interpretation_preview_dialog",
    "DataSplittingDialog": ".data_splitting_dialog",
    "EventFilterDialog": ".event_filter_dialog",
    "ImportLabelDialog": ".import_label_dialog",
    "LabelMappingDialog": ".label_mapping_dialog",
    "SmartParserDialog": ".smart_parser_dialog",
}

__all__ = [
    "ChannelSelectionDialog",
    "DataInterpretationPreviewDialog",
    "DataSplittingDialog",
    "EventFilterDialog",
    "ImportLabelDialog",
    "LabelMappingDialog",
    "SmartParserDialog",
]


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
