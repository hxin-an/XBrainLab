"""Lightweight user-intent helpers for agent command boundaries."""

from __future__ import annotations

import re

from XBrainLab.backend.application import CommandName

INTENT_TO_COMMAND: dict[str, CommandName] = {
    "scan_source": CommandName.SCAN_SOURCE,
    "preview_interpretation": CommandName.PREVIEW_INTERPRETATION,
    "validate_interpretation": CommandName.VALIDATE_INTERPRETATION,
    "apply_interpretation": CommandName.APPLY_INTERPRETATION,
    "save_interpretation_recipe": CommandName.SAVE_INTERPRETATION_RECIPE,
    "reload_interpretation_recipe": CommandName.RELOAD_INTERPRETATION_RECIPE,
    "load_data": CommandName.LOAD_DATA,
    "preprocess": CommandName.PREPROCESS,
    "create_epoch": CommandName.CREATE_EPOCH,
    "generate_dataset": CommandName.GENERATE_DATASET,
    "configure_training": CommandName.CONFIGURE_TRAINING,
    "train": CommandName.TRAIN,
    "reset_session": CommandName.RESET_SESSION,
    "query_state": CommandName.QUERY_STATE,
    "visualize": CommandName.VISUALIZE,
    "saliency": CommandName.SALIENCY,
}


def infer_user_intent(text: str) -> str:
    """Infer the next workflow intent from user-visible text."""
    normalized = text.lower()
    has_it = re.search(r"\bit\b", normalized) is not None
    if "reset" in normalized or "clear the dataset" in normalized:
        return "reset_session"
    if (
        "workflow state" in normalized
        or "current workflow" in normalized
        or "what changed" in normalized
    ):
        return "query_state"
    if "validate" in normalized and (
        "interpret" in normalized or "candidate" in normalized or has_it
    ):
        return "validate_interpretation"
    if "check whether" in normalized and "interpretation" in normalized:
        return "validate_interpretation"
    if "reload recipe" in normalized or "reload the interpretation recipe" in (
        normalized
    ):
        return "reload_interpretation_recipe"
    if "save" in normalized and "recipe" in normalized:
        return "save_interpretation_recipe"
    if "apply" in normalized and ("interpret" in normalized or has_it):
        return "apply_interpretation"
    if "preview" in normalized and (
        "interpret" in normalized
        or "candidate" in normalized
        or "subject" in normalized
        or has_it
    ):
        return "preview_interpretation"
    if (
        "interpret data source" in normalized
        or "interpret my eeg dataset" in normalized
        or "scan a data source" in normalized
        or "scan data source" in normalized
        or "scan the bids dataset" in normalized
        or "scan the source" in normalized
    ):
        return "scan_source"
    if "saliency" in normalized:
        return "saliency"
    if "visualize" in normalized or "visualise" in normalized:
        return "visualize"
    if "preprocess" in normalized or "bandpass" in normalized or "filter" in normalized:
        return "preprocess"
    if "generate" in normalized and "dataset" in normalized:
        return "generate_dataset"
    if "create epoch" in normalized or "epochs from" in normalized:
        return "create_epoch"
    if "configure training" in normalized or "batch size" in normalized:
        return "configure_training"
    if "train" in normalized or "training" in normalized:
        return "train"
    if "eegnet" in normalized or ("model" in normalized and "use" in normalized):
        return "configure_training"
    if "load" in normalized:
        return "load_data"
    return "unknown"


def command_for_intent(intent: str) -> CommandName | None:
    """Return the backend command represented by an inferred intent."""
    return INTENT_TO_COMMAND.get(intent)


def path_label_for_intent(intent: str) -> str | None:
    """Return the user-facing path label implied by an intent."""
    if intent == "load_data":
        return "file path"
    if intent == "scan_source":
        return "source path"
    if intent == "reload_interpretation_recipe":
        return "recipe path"
    return None
