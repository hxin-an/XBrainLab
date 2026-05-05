"""User-facing labels for backend workflow state and commands."""

from __future__ import annotations

from typing import Any

from XBrainLab.backend.application import CommandName

COMMAND_LABELS: dict[str, str] = {
    CommandName.SCAN_SOURCE.value: "Scan data source",
    CommandName.PREVIEW_INTERPRETATION.value: "Preview data interpretation",
    CommandName.VALIDATE_INTERPRETATION.value: "Validate data interpretation",
    CommandName.APPLY_INTERPRETATION.value: "Apply data interpretation",
    CommandName.SAVE_INTERPRETATION_RECIPE.value: "Save interpretation recipe",
    CommandName.RELOAD_INTERPRETATION_RECIPE.value: "Reload interpretation recipe",
    CommandName.LOAD_DATA.value: "Import data",
    CommandName.ATTACH_LABELS.value: "Add labels to loaded data",
    CommandName.PREPROCESS.value: "Preprocess data",
    CommandName.CREATE_EPOCH.value: "Create epochs",
    CommandName.GENERATE_DATASET.value: "Build training dataset",
    CommandName.CONFIGURE_TRAINING.value: "Configure training",
    CommandName.TRAIN.value: "Start training",
    CommandName.STOP_TRAINING.value: "Stop training",
    CommandName.EVALUATE.value: "Review results",
    CommandName.VISUALIZE.value: "Open visualizations",
    CommandName.SALIENCY.value: "Configure saliency analysis",
    CommandName.RESET_SESSION.value: "Reset session",
    CommandName.NEW_SESSION.value: "Start new session",
}

TOOL_ACTION_LABELS: dict[str, str] = {
    "start_training": "Start training",
    "stop_training": "Stop training",
    "clear_dataset": "Clear dataset",
    "scan_source": "Scan data source",
    "preview_interpretation": "Preview data interpretation",
    "validate_interpretation": "Validate data interpretation",
    "apply_interpretation": "Apply data interpretation",
    "save_interpretation_recipe": "Save interpretation recipe",
    "reload_interpretation_recipe": "Reload interpretation recipe",
    "load_data": "Import data",
    "attach_labels": "Add labels to loaded data",
    "preprocess_data": "Preprocess data",
    "create_epochs": "Create epochs",
    "generate_dataset": "Build training dataset",
    "configure_training": "Configure training",
    "reset_session": "Reset session",
    "new_session": "Start new session",
}


def command_label(command_name: str | CommandName) -> str:
    """Return a user-facing label for an application command."""
    key = command_name.value if isinstance(command_name, CommandName) else command_name
    return COMMAND_LABELS.get(key, key.replace("_", " ").title())


def command_labels(command_names: list[str] | tuple[str, ...]) -> list[str]:
    """Return user-facing labels for application command names."""
    return [command_label(name) for name in command_names]


def tool_action_label(tool_name: str) -> str:
    """Return a user-facing label for an assistant tool/action name."""
    key = str(tool_name or "").strip()
    if not key:
        return "Assistant action"
    return TOOL_ACTION_LABELS.get(key, command_label(key))


def workflow_stage_label(state: Any) -> str:
    """Derive a user-facing workflow stage from an ApplicationService snapshot."""
    training = getattr(state, "training", None)
    evaluation = getattr(state, "evaluation", None)
    active_dataset = getattr(state, "active_dataset", None)
    active_training = getattr(state, "active_training", None)

    if getattr(active_training, "is_running", False) or getattr(
        training,
        "is_running",
        False,
    ):
        return "Training running"
    if getattr(evaluation, "finished_runs", 0) > 0 or getattr(
        evaluation,
        "metrics_available",
        False,
    ):
        return "Results available"
    if getattr(active_dataset, "has_datasets", False):
        if getattr(training, "has_model", False) and getattr(
            training,
            "has_training_option",
            False,
        ):
            return "Ready to train"
        return "Dataset ready"
    if getattr(active_dataset, "has_epoch_data", False):
        return "Ready to build dataset"
    if getattr(active_dataset, "has_preprocessed_data", False):
        return "Ready for epoching"
    if getattr(active_dataset, "has_raw_data", False):
        return "Ready for preprocessing"

    raw_stage = str(getattr(state, "pipeline_stage", "") or "")
    return workflow_stage_text_label(raw_stage)


def workflow_stage_text_label(stage: str) -> str:
    """Translate a raw pipeline stage string into product language."""
    normalized = stage.strip().lower().replace(" ", "_")
    return {
        "empty": "No data loaded",
        "data_loaded": "Ready for preprocessing",
        "preprocessed": "Ready for epoching",
        "dataset_ready": "Dataset ready",
        "training": "Training running",
        "trained": "Results available",
        "status_unavailable": "Workflow status unavailable",
    }.get(normalized, stage.strip() or "No data loaded")
