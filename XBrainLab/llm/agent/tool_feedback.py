"""Visible summaries and compact follow-up payloads for assistant tools."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from XBrainLab.llm.tools.application_surface import ToolCommandResult
from XBrainLab.llm.tools.result_contract import (
    UiRequest,
    UiRequestKind,
    public_safe_result_projection,
    redact_public_text,
)
from XBrainLab.product_language import tool_action_label, tool_availability_label

_INTERPRETATION_DECISION_SUMMARIES: dict[str, str] = {
    "safe": "Data interpretation is ready to apply.",
    "needs_confirmation": (
        "Review and confirm the data interpretation before applying it."
    ),
    "blocked": "Data interpretation needs changes before it can be applied.",
}


def _safe_feedback_text(value: str, *, limit: int) -> str:
    """Flatten control characters and bound untrusted runtime text."""
    value = _require_exact_feedback_text(value, field_name="Tool feedback text")
    flattened = "".join(
        " " if unicodedata.category(char).startswith("C") else char
        for char in redact_public_text(value)
    )
    flattened = re.sub(r"\s+", " ", flattened).strip()
    if len(flattened) <= limit:
        return flattened
    return flattened[: max(0, limit - 3)].rstrip() + "..."


def _require_exact_feedback_text(value: object, *, field_name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be an exact string.")
    return value


def _require_exact_optional_feedback_text(
    value: object,
    *,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    return _require_exact_feedback_text(value, field_name=field_name)


def summarize_tool_result(
    command_name: str,
    success: bool,
    result: ToolCommandResult | UiRequest,
) -> str:
    """Build a short visible tool summary for the chat transcript."""
    command_name = _require_exact_feedback_text(
        command_name,
        field_name="Tool summary command name",
    )
    if isinstance(result, UiRequest):
        if result.kind is UiRequestKind.CONFIRM_MONTAGE:
            return "Montage setup needs confirmation in the app."
        if result.kind is UiRequestKind.SWITCH_PANEL:
            return "I opened the requested workspace panel."
        return "The app needs input before this action can continue."

    projection = public_safe_result_projection(
        message=result.message,
        blocked_reason=result.blocked_reason,
        raw_result=result.raw_result,
        state=result.state,
        capability=result.capability,
        diagnostics=result.diagnostics,
    )
    message = projection.message
    result_tool_name = _require_exact_feedback_text(
        result.tool_name,
        field_name="Tool result name",
    )
    tool_name = result_tool_name or command_name
    label = tool_action_label(tool_name)
    text = message.strip()
    lower_text = text.lower()

    if not success:
        reason = (projection.blocked_reason or projection.message or "").strip()
        if result.error_type == "precondition":
            if tool_name == "start_training":
                return _training_precondition_summary(
                    projection.capability,
                    fallback_reason=reason,
                )
            subject = tool_availability_label(tool_name)
            return _precondition_summary(subject, reason)
        if result.error_type == "confirmation_required":
            return f"{label} needs confirmation in the app before it can continue."
        if result.error_type == "input":
            return (
                f"I need more information before {label.lower()} can continue: "
                f"{clean_reason(reason)}"
            )
        return (
            f"I could not complete {label.lower()}. Details were saved to "
            "diagnostics; check the app status bar or try again."
        )

    if not text or text in {"[]", "{}"}:
        return (
            "The action completed, but there is nothing to show yet. Ask what is "
            "ready or choose the next workflow step."
        )
    if "requires ui confirmation" in lower_text or "backendfacade legacy path" in (
        lower_text
    ):
        return f"{label} needs confirmation in the app before it can continue."
    # Project the typed diagnostics independently. Large state/raw-result payloads
    # must not consume the shared public-projection budget before the user-facing
    # decision payload is reached.
    structured_diagnostics = public_safe_result_projection(
        message="",
        diagnostics=result.diagnostics,
    ).diagnostics
    structured_summary = _structured_success_summary(
        result,
        diagnostics=structured_diagnostics or projection.diagnostics,
    )
    if structured_summary is not None:
        return structured_summary
    return text


def _training_precondition_summary(
    capability: dict[str, Any] | None,
    *,
    fallback_reason: str,
) -> str:
    """Show one backend-owned training requirement without hiding later setup."""
    reasons: list[str] = []
    if type(capability) is dict:
        raw_reasons = capability.get("reasons")
        if type(raw_reasons) is list:
            reasons = [
                _safe_feedback_text(item, limit=500)
                for item in raw_reasons
                if type(item) is str and item.strip()
            ]
    first_reason = reasons[0] if reasons else clean_reason(fallback_reason)
    normalized = first_reason.strip().casefold()
    if normalized == "training is already running.":
        return "Training is already running."
    if normalized == "load raw data before training.":
        return _precondition_summary(
            "Training",
            "Import EEG data.",
            action="start",
        )

    concise_reason = re.sub(
        r"\s+before training\.$",
        ".",
        clean_reason(first_reason),
        flags=re.IGNORECASE,
    )
    return _precondition_summary(
        "Training",
        concise_reason,
        action="start",
    )


def _precondition_summary(
    subject: str,
    requirement: str,
    *,
    action: str = "run",
) -> str:
    """Separate the blocked action from its first backend-owned requirement."""
    cleaned_requirement = clean_reason(requirement)
    if cleaned_requirement:
        cleaned_requirement = cleaned_requirement[0].upper() + cleaned_requirement[1:]
    return f"{subject} can't {action} yet.\n\n**Required first:** {cleaned_requirement}"


def _structured_success_summary(
    result: ToolCommandResult,
    *,
    diagnostics: dict[str, Any] | None = None,
) -> str | None:
    """Present known typed backend payloads without exposing internal tokens."""
    safe_diagnostics = diagnostics if diagnostics is not None else result.diagnostics
    payload_type = safe_diagnostics.get("payload_type")
    if payload_type != "validation_decision":
        return None

    decision_payload = safe_diagnostics.get("validation_decision")
    if not isinstance(decision_payload, dict):
        return "Data interpretation review is ready."
    decision = decision_payload.get("decision")
    if not isinstance(decision, str):
        return "Data interpretation review is ready."
    normalized_decision = decision.strip().lower()
    if normalized_decision in {"needs_confirmation", "blocked"}:
        action_summary = _interpretation_action_summary(
            decision_payload,
            blocked=normalized_decision == "blocked",
        )
        if action_summary is not None:
            return action_summary
    return _INTERPRETATION_DECISION_SUMMARIES.get(
        normalized_decision,
        "Data interpretation review is ready.",
    )


def _interpretation_action_summary(
    decision_payload: dict[str, Any],
    *,
    blocked: bool,
) -> str | None:
    raw_items = decision_payload.get("action_items")
    if not isinstance(raw_items, list):
        return None
    issues: list[str] = []
    accepted_severities = (
        {"blocked"}
        if blocked
        else {
            "blocked",
            "needs_confirmation",
        }
    )
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity") or "").strip().lower()
        issue = _safe_feedback_text(str(item.get("issue") or ""), limit=180)
        if severity not in accepted_severities or not issue or issue in issues:
            continue
        issues.append(issue)
    if not issues:
        return None
    visible = issues[:3]
    lines = [
        "Import review is blocked:" if blocked else "Import review needs your input:",
        *(f"- {issue}" for issue in visible),
    ]
    if len(issues) > len(visible):
        lines.append(f"- {len(issues) - len(visible)} more item(s)")
    lines.append("Use the open Import EEG Data window to review these choices.")
    return "\n".join(lines)


def clean_reason(reason: str) -> str:
    """Remove developer prefixes from a reason shown in chat."""
    cleaned = reason.strip()
    for prefix in ("Error:", "Tool execution failed:", "Tool failed:"):
        if cleaned.lower().startswith(prefix.lower()):
            cleaned = cleaned[len(prefix) :].strip()
    cleaned = cleaned.replace(
        "ApplicationService requires paths list cannot be empty.",
        "The workflow requires a file or folder path.",
    )
    cleaned = cleaned.replace("ApplicationService", "the workflow")
    cleaned = cleaned.replace("legacy facade path", "app confirmation path")
    cleaned = cleaned.replace(
        "paths list cannot be empty.",
        "a file or folder path is required.",
    )
    cleaned = cleaned.replace("directory is required", "a folder path is required")
    cleaned = cleaned.replace(
        "epoch, batch_size, and learning_rate are required.",
        "training epochs, batch size, and learning rate are required.",
    )
    cleaned = re.sub(
        r"\b([A-Za-z]+(?:_[A-Za-z0-9]+)+)\b",
        lambda match: match.group(1).replace("_", " "),
        cleaned,
    )
    return cleaned or "the workflow is missing required input."


def format_tool_output(
    command_name: str,
    success: bool,
    result: ToolCommandResult | UiRequest,
) -> str:
    """Serialize compact tool output for the next local-model turn."""
    command_name = _require_exact_feedback_text(
        command_name,
        field_name="Tool output command name",
    )
    if isinstance(result, ToolCommandResult):
        payload = compact_tool_payload(result)
    elif isinstance(result, UiRequest):
        projection = public_safe_result_projection(
            message="UI request",
            raw_result=result.params,
        )
        payload = {
            "ok": bool(success),
            "tool_name": command_name,
            "ui_request": result.kind.value,
            "params": projection.raw_result,
        }
    else:
        raise AssertionError("Unsupported normalized tool result")
    return json.dumps(payload, ensure_ascii=False, default=str)


def compact_tool_payload(result: ToolCommandResult) -> dict[str, Any]:
    """Return tool feedback compact enough for the next local-model turn."""
    tool_name = _require_exact_feedback_text(
        result.tool_name,
        field_name="Tool result name",
    )
    command_name = _require_exact_optional_feedback_text(
        result.command_name,
        field_name="Tool result command name",
    )
    projection = public_safe_result_projection(
        message=result.message,
        blocked_reason=result.blocked_reason,
        raw_result=result.raw_result,
        state=result.state,
        capability=result.capability,
        diagnostics=result.diagnostics,
    )
    payload: dict[str, Any] = {
        "ok": result.ok,
        "tool_name": tool_name,
        "command_name": command_name,
        "message": projection.message,
        "error_type": result.error_type,
        "recoverable": result.recoverable,
        "blocked_reason": projection.blocked_reason,
    }
    if projection.capability:
        payload["capability"] = {
            key: projection.capability.get(key)
            for key in (
                "command_name",
                "enabled",
                "reasons",
                "requires_confirmation",
                "decision_boundary",
                "continue_allowed_after_success",
            )
            if key in projection.capability
        }
    state_summary = compact_state_summary(projection.state)
    if state_summary:
        payload["state_summary"] = state_summary
    diagnostics = compact_tool_diagnostics(projection.diagnostics)
    if diagnostics:
        payload["diagnostics"] = diagnostics
    return payload


def compact_state_summary(state: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only workflow readiness fields needed for follow-up turns."""
    if not isinstance(state, dict):
        return {}

    def pick(section: str, keys: tuple[str, ...]) -> dict[str, Any]:
        value = state.get(section)
        if not isinstance(value, dict):
            return {}
        return {key: value.get(key) for key in keys if key in value}

    summary: dict[str, Any] = {}
    if "pipeline_stage" in state:
        summary["pipeline_stage"] = state.get("pipeline_stage")
    sections = {
        "raw": ("loaded", "count", "files", "formats", "event_total"),
        "preprocessed": ("available", "count", "is_epoched", "operations"),
        "epoch": ("available", "exists", "epoch_count", "event_names"),
        "dataset": ("available", "count", "names", "locked"),
        "training": (
            "has_model",
            "has_training_option",
            "has_trainer",
            "is_running",
            "missing_requirements",
        ),
        "interpretation": (
            "has_scan_result",
            "has_candidate",
            "has_preview",
            "has_validation_decision",
            "has_applied_interpretation",
            "has_recipe",
            "validation_decision",
            "pending_confirmation",
            "blocked_reasons",
            "summary",
        ),
    }
    for section, keys in sections.items():
        section_summary = pick(section, keys)
        if section_summary:
            summary[section] = section_summary
    last_error = state.get("last_error")
    if isinstance(last_error, dict):
        summary["last_error"] = {
            key: last_error.get(key)
            for key in ("error_type", "message", "recoverable")
            if key in last_error
        }
    return summary


def compact_tool_diagnostics(diagnostics: dict[str, Any]) -> dict[str, Any]:
    """Keep small diagnostics fields while dropping full raw/state payloads."""
    if not isinstance(diagnostics, dict):
        return {}
    return {
        key: diagnostics[key]
        for key in (
            "payload_type",
            "success_count",
            "errors",
            "label_carriers_pending",
            "recipe_updated",
            "tool_name",
            "command_name",
            "publication_generation",
            "view_verified",
            "view_stale",
            "view_refresh_error",
        )
        if key in diagnostics
    }
