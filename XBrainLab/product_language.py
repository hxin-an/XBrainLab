"""Shared product labels for assistant tools across model and GUI surfaces."""

from __future__ import annotations

from XBrainLab.backend.application.pipeline_stage import workflow_command_label

TOOL_ACTION_LABELS: dict[str, str] = {
    "list_files": "File browser",
    "get_dataset_info": "Dataset summary",
    "query_state": "State query",
    "scan_source": "Scan data source",
    "preview_interpretation": "Preview data interpretation",
    "validate_interpretation": "Validate data interpretation",
    "apply_interpretation": "Apply data interpretation",
    "save_interpretation_recipe": "Save interpretation recipe",
    "reload_interpretation_recipe": "Reload interpretation recipe",
    "load_data": "Import data",
    "attach_labels": "Add labels to loaded data",
    "preprocess_data": "Preprocess data",
    "apply_standard_preprocess": "Preprocess data",
    "apply_bandpass_filter": "Apply bandpass filter",
    "apply_notch_filter": "Apply notch filter",
    "resample_data": "Resample data",
    "normalize_data": "Normalize data",
    "set_reference": "Set EEG reference",
    "select_channels": "Select channels",
    "set_montage": "Set montage",
    "create_epochs": "Create EEG epochs",
    "epoch_data": "Create EEG epochs",
    "configure_dataset_split": "Configure data splitting",
    "set_model": "Configure model",
    "configure_training": "Configure training",
    "start_training": "Start training",
    "stop_training": "Stop training",
    "evaluate": "Review results",
    "visualize": "Open visualizations",
    "saliency": "Configure saliency analysis",
    "new_session": "Start new session",
    "switch_panel": "Navigation",
}

TOOL_AVAILABILITY_LABELS: dict[str, str] = {
    "start_training": "Training",
    "stop_training": "Training",
}

ASSISTANT_CANCELLED_MESSAGE = (
    "Request cancelled. You can revise it or ask something else."
)


def tool_action_label(tool_name: str) -> str:
    """Return one stable label for an assistant tool or workflow command."""
    key = str(tool_name or "").strip()
    if not key:
        return "Assistant action"
    return TOOL_ACTION_LABELS.get(key, workflow_command_label(key))


def tool_availability_label(tool_name: str) -> str:
    """Return a grammatical subject for tool availability messages."""
    key = str(tool_name or "").strip()
    return TOOL_AVAILABILITY_LABELS.get(key, tool_action_label(key))
