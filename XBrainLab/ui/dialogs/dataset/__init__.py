"""Dataset dialog components for EEG data management.

Provides dialogs for channel selection, data splitting, event filtering,
label import/mapping, and metadata parsing.
"""

from .channel_selection_dialog import ChannelSelectionDialog
from .data_interpretation_preview_dialog import DataInterpretationPreviewDialog
from .data_splitting_dialog import DataSplittingDialog
from .event_filter_dialog import EventFilterDialog
from .import_label_dialog import ImportLabelDialog
from .label_mapping_dialog import LabelMappingDialog
from .smart_parser_dialog import SmartParserDialog

__all__ = [
    "ChannelSelectionDialog",
    "DataInterpretationPreviewDialog",
    "DataSplittingDialog",
    "EventFilterDialog",
    "ImportLabelDialog",
    "LabelMappingDialog",
    "SmartParserDialog",
]
