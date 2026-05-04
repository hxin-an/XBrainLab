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
    "evaluate": CommandName.EVALUATE,
    "reset_session": CommandName.RESET_SESSION,
    "query_state": CommandName.QUERY_STATE,
    "visualize": CommandName.VISUALIZE,
    "saliency": CommandName.SALIENCY,
}


def infer_user_intent(text: str) -> str:
    """Infer the next workflow intent from user-visible text."""
    normalized = text.lower()
    has_it = re.search(r"\bit\b", normalized) is not None
    if _is_explanatory_no_tool_request(normalized):
        return "no_tool"
    if _is_ambiguous_workflow_request(normalized):
        return "ask_clarification"
    if "reset" in normalized or "clear the dataset" in normalized:
        return "reset_session"
    if "重設" in normalized or "清空" in normalized:
        return "reset_session"
    if (
        "workflow state" in normalized
        or "current workflow" in normalized
        or "what changed" in normalized
        or "目前狀態" in normalized
        or "現在狀態" in normalized
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
    if "儲存" in normalized and "recipe" in normalized:
        return "save_interpretation_recipe"
    if "apply" in normalized and ("interpret" in normalized or has_it):
        return "apply_interpretation"
    if "preview" in normalized and (
        "interpret" in normalized
        or "candidate" in normalized
        or "subject" in normalized
        or "session" in normalized
        or "task" in normalized
        or "run" in normalized
        or "event role" in normalized
        or has_it
    ):
        return "preview_interpretation"
    if "預覽" in normalized and ("資料" in normalized or "標籤" in normalized):
        return "preview_interpretation"
    if "驗證" in normalized and ("資料" in normalized or "標籤" in normalized):
        return "validate_interpretation"
    if "套用" in normalized and ("資料" in normalized or "標籤" in normalized):
        return "apply_interpretation"
    if _is_chinese_data_interpretation_request(normalized):
        return "scan_source"
    if (
        "interpret data source" in normalized
        or "interpret my eeg dataset" in normalized
        or ("scan" in normalized and "bids" in normalized)
        or "scan bids" in normalized
        or "scan /" in normalized
        or "scan a data source" in normalized
        or "scan data source" in normalized
        or "scan the bids dataset" in normalized
        or "scan the source" in normalized
    ):
        return "scan_source"
    if "saliency" in normalized:
        return "saliency"
    if "顯著" in normalized or "可解釋" in normalized:
        return "saliency"
    if "evaluate" in normalized or "evaluation" in normalized:
        return "evaluate"
    if (
        "visualize" in normalized
        or "visualise" in normalized
        or "visualization" in normalized
        or "visualisation" in normalized
    ):
        return "visualize"
    if "preprocess" in normalized or "bandpass" in normalized or "filter" in normalized:
        return "preprocess"
    if "前處理" in normalized or "濾波" in normalized or "帶通" in normalized:
        return "preprocess"
    if "generate" in normalized and "dataset" in normalized:
        return "generate_dataset"
    if "create epoch" in normalized or "epochs from" in normalized:
        return "create_epoch"
    if "切 epoch" in normalized or "切epoch" in normalized or "切片段" in normalized:
        return "create_epoch"
    if "train it" in normalized or ("train" in normalized and "blocked" in normalized):
        return "train"
    if "configure training" in normalized or "batch size" in normalized:
        return "configure_training"
    if "train" in normalized or "training" in normalized:
        return "train"
    if "訓練" in normalized:
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


def _is_explanatory_no_tool_request(normalized: str) -> bool:
    explanatory_markers = (
        "why",
        "what is",
        "what are",
        "explain",
        "concept",
        "為什麼",
        "什麼是",
        "是什麼",
        "解釋",
        "概念",
    )
    if not any(marker in normalized for marker in explanatory_markers):
        return False
    return not any(
        marker in normalized
        for marker in (
            "workflow state",
            "current workflow",
            "目前狀態",
            "現在狀態",
        )
    )


def _is_ambiguous_workflow_request(normalized: str) -> bool:
    return any(
        marker in normalized
        for marker in (
            "help me process the data",
            "handle this data",
            "do the eeg workflow",
            "幫我處理資料",
            "幫我弄資料",
            "把資料處理一下",
        )
    )


def _is_chinese_data_interpretation_request(normalized: str) -> bool:
    if (
        "腦波" not in normalized
        and "eeg" not in normalized
        and "bci" not in normalized
        and "bids" not in normalized
    ):
        return False
    return any(
        marker in normalized
        for marker in (
            "讀",
            "載入",
            "匯入",
            "貼標籤",
            "標籤",
            "資料",
        )
    )
