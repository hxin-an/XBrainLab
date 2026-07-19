"""Visible summaries and compact follow-up payloads for assistant tools."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
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


@dataclass(frozen=True)
class ToolRecoveryFeedback:
    """Small, instruction-isolated failure payload for one model retry."""

    tool_name: str
    command_name: str | None
    error_type: str | None
    message: str
    blocked_reason: str | None
    guidance: str

    def to_prompt_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": "xbrainlab.tool_recovery.v1",
            "tool_name": _safe_feedback_text(self.tool_name, limit=100),
            "command_name": (
                _safe_feedback_text(self.command_name, limit=100)
                if self.command_name
                else None
            ),
            "error_type": (
                _safe_feedback_text(self.error_type, limit=80)
                if self.error_type
                else None
            ),
            "message": _safe_feedback_text(self.message, limit=500),
            "blocked_reason": (
                _safe_feedback_text(self.blocked_reason, limit=500)
                if self.blocked_reason
                else None
            ),
            "recoverable": True,
            "guidance": _safe_feedback_text(self.guidance, limit=300),
        }
        return payload


def build_recovery_feedback(
    command_name: str,
    result: ToolCommandResult | UiRequest,
) -> ToolRecoveryFeedback | None:
    """Build retry context only for typed, recoverable command failures."""
    if not isinstance(result, ToolCommandResult) or result.ok or not result.recoverable:
        return None
    projection = public_safe_result_projection(
        message=result.message,
        blocked_reason=result.blocked_reason,
        raw_result=result.raw_result,
        state=result.state,
        capability=result.capability,
        diagnostics=result.diagnostics,
    )
    guidance_by_error = {
        "input": "Correct only the named input, or ask the user for that input.",
        "precondition": (
            "Do not substitute a different tool. Explain the blocker or wait for "
            "the required workflow state."
        ),
        "intent_mismatch": (
            "Select the tool that directly matches the latest user request."
        ),
        "tool_not_published": (
            "Use only a tool published in the current Available Tools block."
        ),
    }
    return ToolRecoveryFeedback(
        tool_name=result.tool_name or command_name,
        command_name=result.command_name,
        error_type=result.error_type,
        message=projection.message,
        blocked_reason=projection.blocked_reason,
        guidance=guidance_by_error.get(
            result.error_type or "",
            "Use the runtime error details to make one corrected proposal.",
        ),
    )


def _safe_feedback_text(value: str, *, limit: int) -> str:
    """Flatten control characters and bound untrusted runtime text."""
    flattened = "".join(
        " " if unicodedata.category(char).startswith("C") else char
        for char in redact_public_text(value)
    )
    flattened = re.sub(r"\s+", " ", flattened).strip()
    if len(flattened) <= limit:
        return flattened
    return flattened[: max(0, limit - 3)].rstrip() + "..."


def summarize_tool_result(
    command_name: str,
    success: bool,
    result: ToolCommandResult | UiRequest,
) -> str:
    """Build a short visible tool summary for the chat transcript."""
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
    tool_name = result.tool_name or command_name
    label = tool_action_label(tool_name)
    text = message.strip()
    lower_text = text.lower()

    if tool_name == "list_files":
        if not success and "directory is required" in lower_text:
            return (
                "I need a folder path before I can list files. Choose a folder "
                "in the app or paste the path here."
            )
        if not success and "does not exist" in lower_text:
            return (
                "I could not find that folder. Choose another folder or paste a "
                "valid path."
            )
        if not success and "system directories" in lower_text:
            return (
                "I cannot browse protected system folders. Choose a project or "
                "EEG data folder instead."
            )
        files = (
            [str(item) for item in projection.raw_result]
            if isinstance(projection.raw_result, list)
            else None
        )
        if success and files is not None:
            if not files:
                return (
                    "I did not find files in that folder. Choose another folder "
                    "or import EEG data to begin."
                )
            preview = ", ".join(files[:5])
            suffix = "" if len(files) <= 5 else f", and {len(files) - 5} more"
            return f"I found {len(files)} item(s): {preview}{suffix}."

    if not success:
        reason = (projection.blocked_reason or projection.message or "").strip()
        if result.error_type == "precondition":
            subject = tool_availability_label(tool_name)
            return f"{subject} is not available yet: {clean_reason(reason)}"
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
    structured_summary = _structured_success_summary(
        result,
        diagnostics=projection.diagnostics,
    )
    if structured_summary is not None:
        return structured_summary
    return text


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
    lines.append("Open Import Review to resolve these choices.")
    return "\n".join(lines)


def clean_reason(reason: str) -> str:
    """Remove developer prefixes from a reason shown in chat."""
    cleaned = reason.strip()
    for prefix in ("Error:", "Tool execution failed:", "Tool failed:"):
        if cleaned.lower().startswith(prefix.lower()):
            cleaned = cleaned[len(prefix) :].strip()
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
        "tool_name": result.tool_name,
        "command_name": result.command_name,
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
