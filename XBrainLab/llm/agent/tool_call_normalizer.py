"""Normalize common local-model tool-call variants before verification."""

import re
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
    if _should_demote_to_bandpass_only(normalized_name, latest_user_text):
        normalized_name = "apply_bandpass_filter"
        normalized_params = {}

    if normalized_name == "apply_bandpass_filter":
        _fill_bandpass_args(normalized_params, latest_user_text)

    if normalized_name == "apply_standard_preprocess":
        _rename_key(normalized_params, "low_freq", "l_freq")
        _rename_key(normalized_params, "high_freq", "h_freq")
        _fill_standard_preprocess_filter_args(normalized_params, latest_user_text)

    if normalized_name == "scan_source":
        _normalize_scan_args(normalized_params, latest_user_text)

    if normalized_name == "preview_interpretation":
        _normalize_preview_args(normalized_params, latest_user_text)

    if normalized_name == "apply_interpretation":
        _normalize_apply_args(normalized_params, latest_user_text)

    if normalized_name == "epoch_data":
        _normalize_epoch_args(normalized_params, latest_user_text)

    if normalized_name == "generate_dataset":
        _normalize_dataset_args(normalized_params, latest_user_text)

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


def _should_demote_to_bandpass_only(tool_name: str, latest_user_text: str) -> bool:
    if tool_name != "apply_standard_preprocess":
        return False
    text = latest_user_text.lower()
    return "bandpass" in text and "preprocess" not in text and "standard" not in text


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
    if intent == "scan_source" and tool_name == "load_data":
        source_path = _extract_path(latest_user_text)
        return (
            "scan_source",
            {"source_path": source_path} if source_path else dict(params),
        )
    if intent == "preview_interpretation" and tool_name == "scan_source":
        return "preview_interpretation", {}
    if intent == "validate_interpretation" and tool_name in {
        "preview_interpretation",
        "reload_interpretation_recipe",
    }:
        return "validate_interpretation", {}
    if intent == "apply_interpretation" and tool_name == "validate_interpretation":
        return "apply_interpretation", dict(params)
    if intent == "reload_interpretation_recipe" and tool_name == "scan_source":
        recipe_path = _extract_path(latest_user_text)
        return (
            "reload_interpretation_recipe",
            {"recipe_path": recipe_path} if recipe_path else dict(params),
        )
    if intent == "configure_training" and tool_name == "configure_training":
        model_name = _extract_model_name(latest_user_text)
        if model_name:
            return "set_model", {"model_name": model_name}
    if intent == "create_epoch" and tool_name == "generate_dataset":
        return "epoch_data", _extract_epoch_args(latest_user_text)
    return tool_name, params


def _rename_key(params: dict[str, Any], old: str, new: str) -> None:
    if old in params and new not in params:
        params[new] = params.pop(old)


def _normalize_scan_args(params: dict[str, Any], latest_user_text: str) -> None:
    if "source_path" not in params:
        source_path = _extract_path(latest_user_text)
        if source_path:
            params["source_path"] = source_path
    source_path = params.get("source_path")
    if (
        isinstance(source_path, str)
        and "bids" in source_path.lower()
        and "source_hint" not in params
    ):
        params["source_hint"] = "bids"
    source_hint = params.get("source_hint")
    valid_hints = {
        None,
        "auto",
        "file",
        "folder",
        "bids",
        "device_export",
        "recipe",
    }
    if source_hint not in valid_hints:
        params.pop("source_hint", None)


def _normalize_preview_args(params: dict[str, Any], latest_user_text: str) -> None:
    choices = params.get("choices")
    normalized_choices = dict(choices) if isinstance(choices, dict) else {}
    for key, value in list(normalized_choices.items()):
        if isinstance(value, str):
            normalized_choices[key] = _clean_choice_value(key, value)
    for key in ("subject", "session", "task", "run", "event_role"):
        value = params.get(key)
        if isinstance(value, str):
            normalized_choices.setdefault(key, _clean_choice_value(key, value))
            params.pop(key, None)
    scan_id = params.get("scan_id")
    if (
        isinstance(scan_id, str)
        and "subject" in latest_user_text.lower()
        and scan_id.upper().startswith("S")
    ):
        normalized_choices.setdefault("subject", scan_id)
        params.pop("scan_id", None)
    for key in ("subject", "session", "task", "run"):
        value = _extract_named_value(latest_user_text, key)
        if value:
            normalized_choices.setdefault(key, value)
    event_role = _extract_event_role(latest_user_text)
    if event_role:
        normalized_choices.setdefault("event_role", event_role)
    if normalized_choices:
        params["choices"] = normalized_choices


def _normalize_apply_args(params: dict[str, Any], latest_user_text: str) -> None:
    text = latest_user_text.lower()
    if any(marker in text for marker in ("i confirm", "yes, apply", "yes apply")):
        params["confirmed"] = True


def _normalize_epoch_args(params: dict[str, Any], latest_user_text: str) -> None:
    event_id = params.get("event_id")
    if isinstance(event_id, list):
        params["event_id"] = [str(item) for item in event_id]
    elif event_id is not None:
        params["event_id"] = [str(event_id)]
    extracted = _extract_epoch_args(latest_user_text)
    if "event_id" in extracted:
        params["event_id"] = extracted["event_id"]
    if "t_min" in extracted and "t_max" in extracted:
        params["t_min"] = extracted["t_min"]
        params["t_max"] = extracted["t_max"]
    elif "event_id" in params:
        params["t_min"] = -0.1
        params["t_max"] = 1.0


def _extract_epoch_args(text: str) -> dict[str, Any]:
    args: dict[str, Any] = {}
    event = re.search(r"\bevent\s+([A-Za-z0-9_-]+)", text, flags=re.IGNORECASE)
    if event:
        args["event_id"] = [event.group(1)]
    window = re.search(
        r"from\s+(-?\d+(?:\.\d+)?)\s+to\s+(-?\d+(?:\.\d+)?)",
        text,
        flags=re.IGNORECASE,
    )
    if window:
        args["t_min"] = float(window.group(1))
        args["t_max"] = float(window.group(2))
    return args


def _fill_bandpass_args(params: dict[str, Any], latest_user_text: str) -> None:
    bandpass = _extract_bandpass_args(latest_user_text)
    if "low_freq" in bandpass:
        params["low_freq"] = bandpass["low_freq"]
    if "high_freq" in bandpass:
        params["high_freq"] = bandpass["high_freq"]


def _fill_standard_preprocess_filter_args(
    params: dict[str, Any],
    latest_user_text: str,
) -> None:
    bandpass = _extract_bandpass_args(latest_user_text)
    if "low_freq" in bandpass and "l_freq" not in params:
        params["l_freq"] = bandpass["low_freq"]
    if "high_freq" in bandpass and "h_freq" not in params:
        params["h_freq"] = bandpass["high_freq"]


def _extract_bandpass_args(text: str) -> dict[str, float]:
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*hz",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return {}
    return {
        "low_freq": float(match.group(1)),
        "high_freq": float(match.group(2)),
    }


def _normalize_dataset_args(params: dict[str, Any], latest_user_text: str) -> None:
    text = latest_user_text.lower()
    split_strategy = params.get("split_strategy")
    if split_strategy in {"individual", "group"} and "training_mode" not in params:
        params["training_mode"] = split_strategy
        params["split_strategy"] = "trial"
    if "group" in text:
        params["training_mode"] = "group"
    elif "individual" in text:
        params["training_mode"] = "individual"
    if split_strategy in {"individual", "group"}:
        params["split_strategy"] = "trial"
    if "subject" in text and "split" in text:
        params["split_strategy"] = "subject"
    elif "session" in text and "split" in text:
        params["split_strategy"] = "session"
    elif "trial" in text and "split" in text:
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


def _extract_path(text: str) -> str | None:
    match = re.search(r"(?<![A-Za-z0-9_.-])/[^\s,;]+", text)
    if not match:
        return None
    return match.group(0).rstrip(".")


def _extract_named_value(text: str, key: str) -> str | None:
    match = re.search(
        rf"\b{re.escape(key)}\s+([A-Za-z0-9_-]+)",
        text,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else None


def _clean_choice_value(key: str, value: str) -> str:
    prefix = f"{key} "
    return value[len(prefix) :] if value.lower().startswith(prefix) else value


def _extract_event_role(text: str) -> str | None:
    match = re.search(
        r"\bevent\s+role\s+([A-Za-z0-9_-]+)",
        text,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else None


def _extract_model_name(text: str) -> str | None:
    match = re.search(
        r"\buse\s+([A-Za-z0-9_-]+)\s+as\s+the\s+model",
        text,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else None
