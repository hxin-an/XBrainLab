"""Normalize common local-model tool-call variants before verification."""

from typing import Any

from XBrainLab.llm.agent.intent import infer_user_intent

_TOOL_ALIASES: dict[str, str] = {
    "apply_preprocess": "apply_standard_preprocess",
    "preprocess": "apply_standard_preprocess",
    "standard_preprocess": "apply_standard_preprocess",
    "create_epoch": "epoch_data",
    "create_epochs": "epoch_data",
    "train": "start_training",
    "train_model": "start_training",
    "get_dataset_info": "query_state",
    "get_state": "query_state",
    "state_query": "query_state",
}


def normalize_tool_call(
    tool_name: str,
    params: dict[str, Any],
    *,
    latest_user_text: str = "",
) -> tuple[str, dict[str, Any]]:
    """Return a verifier-ready tool call without bypassing backend policy."""
    normalized_name = _TOOL_ALIASES.get(tool_name, tool_name)
    normalized_params = dict(params)
    normalized_name, normalized_params = _apply_latest_intent_override(
        normalized_name,
        normalized_params,
        latest_user_text,
    )

    if _should_promote_to_standard_preprocess(
        normalized_name,
        latest_user_text,
    ):
        normalized_name = "apply_standard_preprocess"

    if normalized_name == "apply_standard_preprocess":
        _rename_key(normalized_params, "low_freq", "l_freq")
        _rename_key(normalized_params, "high_freq", "h_freq")

    if normalized_name == "scan_source":
        _normalize_scan_args(normalized_params)

    if normalized_name == "preview_interpretation":
        _normalize_preview_args(normalized_params, latest_user_text)

    if normalized_name == "epoch_data":
        _normalize_epoch_args(normalized_params)

    if normalized_name == "generate_dataset":
        _normalize_dataset_args(normalized_params)

    if normalized_name == "save_interpretation_recipe":
        recipe_path = normalized_params.get("recipe_path")
        if recipe_path is not None and not isinstance(recipe_path, str):
            normalized_params.pop("recipe_path", None)

    if _should_promote_to_start_training(normalized_name, latest_user_text):
        normalized_name = "start_training"
        normalized_params = {}

    if normalized_name == "query_state":
        normalized_params.setdefault("query", "state")

    return normalized_name, normalized_params


def _should_promote_to_standard_preprocess(
    tool_name: str,
    latest_user_text: str,
) -> bool:
    if tool_name != "apply_bandpass_filter":
        return False
    text = latest_user_text.lower()
    return "preprocess" in text or "standard" in text


def _apply_latest_intent_override(
    tool_name: str,
    params: dict[str, Any],
    latest_user_text: str,
) -> tuple[str, dict[str, Any]]:
    intent = infer_user_intent(latest_user_text)
    if intent == "scan_source" and tool_name in {
        "preview_interpretation",
        "validate_interpretation",
        "apply_interpretation",
    }:
        return "scan_source", {}
    if intent == "preview_interpretation" and tool_name == "scan_source":
        return "preview_interpretation", {}
    if intent == "validate_interpretation" and tool_name in {
        "preview_interpretation",
        "reload_interpretation_recipe",
    }:
        return "validate_interpretation", {}
    if intent == "apply_interpretation" and tool_name == "validate_interpretation":
        return "apply_interpretation", dict(params)
    return tool_name, params


def _rename_key(params: dict[str, Any], old: str, new: str) -> None:
    if old in params and new not in params:
        params[new] = params.pop(old)


def _normalize_scan_args(params: dict[str, Any]) -> None:
    source_path = params.get("source_path")
    if (
        isinstance(source_path, str)
        and "bids" in source_path.lower()
        and "source_hint" not in params
    ):
        params["source_hint"] = "bids"


def _normalize_preview_args(params: dict[str, Any], latest_user_text: str) -> None:
    choices = params.get("choices")
    normalized_choices = dict(choices) if isinstance(choices, dict) else {}
    scan_id = params.get("scan_id")
    if (
        isinstance(scan_id, str)
        and "subject" in latest_user_text.lower()
        and scan_id.upper().startswith("S")
    ):
        normalized_choices.setdefault("subject", scan_id)
        params.pop("scan_id", None)
    if normalized_choices:
        params["choices"] = normalized_choices


def _normalize_epoch_args(params: dict[str, Any]) -> None:
    event_id = params.get("event_id")
    if isinstance(event_id, list):
        params["event_id"] = [str(item) for item in event_id]
    elif event_id is not None:
        params["event_id"] = [str(event_id)]


def _normalize_dataset_args(params: dict[str, Any]) -> None:
    split_strategy = params.get("split_strategy")
    if split_strategy in {"individual", "group"} and "training_mode" not in params:
        params["training_mode"] = split_strategy
        params["split_strategy"] = "trial"
    params.setdefault("split_strategy", "trial")
    params.setdefault("training_mode", "individual")
    params.setdefault("val_ratio", 0.2)


def _should_promote_to_start_training(
    tool_name: str,
    latest_user_text: str,
) -> bool:
    if tool_name != "configure_training":
        return False
    text = latest_user_text.lower()
    return "train" in text and not any(
        marker in text for marker in ("configure", "set option", "training option")
    )
