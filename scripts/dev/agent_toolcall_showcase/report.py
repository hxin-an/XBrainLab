"""Redacted JSON and Markdown reporting for showcase diagnostics."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from XBrainLab.backend.utils.public_diagnostics import (
    REDACTED_SECRET_MARKER,
    public_diagnostic_value,
)
from XBrainLab.llm.tools.application_surface import (
    AssistantSettingConfirmation,
    AuthoritativeConfirmationParameter,
)
from XBrainLab.llm.tools.authorized_paths import AuthorizedPath

_SECRET_KEY_MARKERS = (
    "api_key",
    "authorization",
    "credential",
    "password",
    "private_key",
    "resource_preflight_token",
    "secret",
    "token",
)
_TRACEBACK_HEADER = "Traceback (most recent call last):"
_REDACTED_STACK_MARKER = "[REDACTED_STACK]"


def sanitize_payload(payload: Any) -> Any:
    """Return a recursively public-safe artifact payload."""
    return _redact_secret_fields(_sanitize_fields(payload))


def _object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _optional_object(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {str(key): item for key, item in value.items()}


def _objects(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [_object(item) for item in value if isinstance(item, dict)]


def _sanitize_fields(value: Any, *, field_name: str | None = None) -> Any:
    """Apply the central projector per field without truncating the case matrix."""
    if isinstance(value, AssistantSettingConfirmation):
        return {
            "kind": "approved_confirmation",
            "tool_name": value.tool_name,
            "publication_generation": value.publication_generation,
        }
    if isinstance(value, (AuthorizedPath, AuthoritativeConfirmationParameter)):
        return public_diagnostic_value(str(value), field_name=field_name)
    if isinstance(value, dict):
        return {
            str(key): _sanitize_fields(item, field_name=str(key))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize_fields(item, field_name=field_name) for item in value]
    if isinstance(value, str) and _TRACEBACK_HEADER in value:
        prefix = value.split(_TRACEBACK_HEADER, maxsplit=1)[0].strip()
        value = f"{prefix} {_REDACTED_STACK_MARKER}".strip()
    return public_diagnostic_value(value, field_name=field_name)


def _redact_secret_fields(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            normalized = key.casefold()
            sanitized[key] = (
                REDACTED_SECRET_MARKER
                if any(marker in normalized for marker in _SECRET_KEY_MARKERS)
                and item not in (None, "", False, 0)
                else _redact_secret_fields(item)
            )
        return sanitized
    if isinstance(value, list):
        return [_redact_secret_fields(item) for item in value]
    return value


def write_reports(
    payload: dict[str, Any],
    *,
    json_path: Path,
    markdown_path: Path,
) -> tuple[dict[str, Any], str]:
    """Atomically write both report formats and return their rendered content."""
    sanitized = sanitize_payload(payload)
    if not isinstance(sanitized, dict):
        raise TypeError("Showcase report did not sanitize to an object.")
    markdown = render_markdown(sanitized)
    _atomic_write(
        json_path,
        json.dumps(sanitized, indent=2, ensure_ascii=True) + "\n",
    )
    _atomic_write(markdown_path, markdown)
    return sanitized, markdown


def render_markdown(payload: dict[str, Any]) -> str:
    """Render a readable, case-by-case diagnostic with the summary first."""
    lines = _summary_markdown(payload)
    cases = _objects(payload.get("cases"))
    for case in cases:
        lines.extend(_case_markdown(case))

    lines.extend(["", "## Limitations", ""])
    limitations = payload.get("limitations")
    if isinstance(limitations, list):
        lines.extend(f"- {item}" for item in limitations)
    generated = payload.get("generated_data")
    if isinstance(generated, dict):
        lines.extend(
            [
                "",
                "## Generated Data",
                "",
                f"- Written: `{bool(generated.get('written'))}`",
                f"- Downloaded: `{bool(generated.get('downloaded'))}`",
                f"- Kind: `{generated.get('kind') or 'none'}`",
                f"- Size: `{generated.get('bytes', 0)} bytes`",
                f"- Path: `{generated.get('path') or 'none'}`",
            ]
        )
    return "\n".join(str(item) for item in lines).rstrip() + "\n"


def render_stdout(payload: dict[str, Any], *, include_details: bool) -> str:
    """Render concise default stdout or the complete case diagnostic."""
    if include_details:
        return render_markdown(payload)
    lines = _summary_header(payload)
    cases = _objects(payload.get("cases"))
    for case in cases:
        lines.extend(_case_stdout(case))
    return "\n".join(lines).rstrip() + "\n"


def _summary_markdown(payload: dict[str, Any]) -> list[str]:
    lines = _summary_header(payload)
    lines.extend(
        [
            "",
            "| Case | Area | Terminal | Tool | Duration | Result |",
            "| --- | --- | --- | --- | ---: | --- |",
        ]
    )
    cases = _objects(payload.get("cases"))
    for case in cases:
        terminal = _object(case.get("terminal"))
        lines.append(
            "| {case_id} | {area} | {terminal} | {tool} | {duration} | {result} |".format(
                case_id=_table(case.get("case_id")),
                area=_table(case.get("area")),
                terminal=_table(
                    f"{terminal.get('kind', 'missing')}:{terminal.get('status', 'missing')}"
                ),
                tool=_table(case.get("selected_tool") or "none"),
                duration=_duration(case.get("duration_ms")),
                result="PASS" if case.get("pass") is True else "FAIL",
            )
        )

    return lines


def _summary_header(payload: dict[str, Any]) -> list[str]:
    run = _object(payload.get("run"))
    summary = _object(payload.get("summary"))
    lines = [
        "# Agent Tool-Call Showcase",
        "",
        f"**Status:** `{str(summary.get('status', 'failed')).upper()}`  ",
        f"**Mode:** `{run.get('mode', 'unknown')}`  ",
        (
            f"**Cases:** {summary.get('passed', 0)}/{summary.get('total', 0)} "
            f"passed; {summary.get('missing_terminal_outcomes', 0)} missing terminal "
            "outcomes  "
        ),
        f"**Duration:** {_duration(run.get('duration_ms'))}",
        "",
        f"> {payload.get('disclaimer', '')}",
    ]
    return lines


def _case_stdout(case: dict[str, Any]) -> list[str]:
    verdict = "PASS" if case.get("pass") is True else "FAIL"
    return [
        "",
        (
            f"[{verdict}] {_inline(case.get('case_id') or 'unknown')} "
            f"({_duration(case.get('duration_ms'))})"
        ),
        (
            f"  intent={_compact(case.get('title') or case.get('area') or 'unknown')} "
            f"| prompt={_compact(case.get('prompt'))}"
        ),
        (
            f"  exposed={_inline(case.get('exposed_tool_schema_names') or [])} "
            f"| selected={_selected_call(case)} | via={_selection_route(case)}"
        ),
        (f"  outcome={_outcome(case)} | result={_result(case)}"),
    ]


def _case_markdown(case: dict[str, Any]) -> list[str]:
    state = _object(case.get("state_before"))
    verification = _object(case.get("verification"))
    command_result = _optional_object(case.get("command_result"))
    changed = case.get("changed_state")
    changed_true = (
        sorted(key for key, enabled in changed.items() if enabled is True)
        if isinstance(changed, dict)
        else []
    )
    capability = verification.get("capability")
    if not isinstance(capability, dict) and command_result is not None:
        capability = command_result.get("capability")
    if not isinstance(capability, dict):
        capability = {}
    terminal = _object(case.get("terminal"))
    selection = _object(case.get("selection"))
    confirmation = case.get("confirmation")
    handoff = case.get("handoff")
    retry = case.get("retry")
    result_summary = (
        {
            "ok": command_result.get("ok"),
            "command_name": command_result.get("command_name"),
            "error_type": command_result.get("error_type"),
            "recoverable": command_result.get("recoverable"),
            "message": command_result.get("message"),
        }
        if command_result is not None
        else None
    )
    failures = case.get("failures") if isinstance(case.get("failures"), list) else []
    lines = [
        "",
        f"## {case.get('case_id', 'unknown')} - {'PASS' if case.get('pass') else 'FAIL'}",
        "",
        f"- Prompt/case: `{_inline(case.get('prompt'))}`",
        f"- State: `{_inline(_compact_state(state))}`",
        (
            "- Capability: `"
            + _inline(
                {
                    "enabled": capability.get("enabled"),
                    "reasons": capability.get("reasons", []),
                    "requires_confirmation": capability.get(
                        "requires_confirmation",
                        capability.get("confirmation_required"),
                    ),
                    "retry_limit": capability.get("retry_limit"),
                }
            )
            + "`"
        ),
        (
            "- Exposed schemas: `"
            + _inline(case.get("exposed_tool_schema_names") or [])
            + "`"
        ),
        (
            "- Proposal: `"
            + _inline(
                {
                    "owner": selection.get("owner"),
                    "parse_status": selection.get("parse_status"),
                    "tool": case.get("selected_tool"),
                    "parameters": case.get("selected_parameters"),
                }
            )
            + "`"
        ),
        (
            "- Verification: `"
            + _inline(
                {
                    "status": verification.get("status"),
                    "action": verification.get("coordinator_action"),
                    "valid": verification.get("valid"),
                    "message": verification.get("message"),
                }
            )
            + "`"
        ),
        f"- Confirmation: `{_inline(confirmation)}`",
        f"- Handoff: `{_inline(handoff)}`",
        f"- Retry: `{_inline(_retry_detail(retry))}`",
        f"- CommandResult: `{_inline(result_summary)}`",
        f"- State delta: `{_inline(changed_true)}`",
        f"- Visible response: `{_inline(case.get('user_visible_presentation'))}`",
        (
            f"- Terminal: `{terminal.get('kind', 'missing')}:"
            f"{terminal.get('status', 'missing')}`"
        ),
        f"- Duration: `{_duration(case.get('duration_ms'))}`",
    ]
    if failures:
        lines.append(f"- Failures: `{_inline(failures)}`")
    return lines


def _selected_call(case: dict[str, Any]) -> str:
    tool_name = case.get("selected_tool")
    if not isinstance(tool_name, str) or not tool_name:
        return "none"
    parameters = case.get("selected_parameters")
    return (
        f"{_inline(tool_name)}({_inline(parameters if parameters is not None else {})})"
    )


def _selection_route(case: dict[str, Any]) -> str:
    selection = _object(case.get("selection"))
    owner = selection.get("owner")
    if isinstance(owner, str) and owner:
        return _inline(owner)
    if isinstance(case.get("retry"), dict):
        return "host_retry_fixture (not model-selected)"
    return "request_admission (not model-selected)"


def _outcome(case: dict[str, Any]) -> str:
    terminal = _object(case.get("terminal"))
    terminal_text = (
        f"{terminal.get('kind', 'missing')}:{terminal.get('status', 'missing')}"
    )
    if case.get("reused_from_resume") is True:
        return f"resumed (not executed this run) -> {terminal_text}"

    retry = case.get("retry")
    if isinstance(retry, dict):
        attempts = retry.get("attempts")
        attempt_states = (
            ["ok" if item.get("success") is True else "failed" for item in attempts]
            if isinstance(attempts, list)
            else []
        )
        return f"retry[{' -> '.join(attempt_states) or 'missing'}] -> {terminal_text}"

    confirmation = case.get("confirmation")
    if isinstance(confirmation, dict):
        resolution = confirmation.get("resolution", "missing")
        if terminal.get("kind") == "confirmation":
            return f"confirmation:{resolution} -> {terminal_text}"
        return f"confirmation:{resolution} -> executed:{terminal.get('status', 'missing')} -> {terminal_text}"

    handoff = case.get("handoff")
    if isinstance(handoff, dict):
        return f"handoff:{handoff.get('status', 'missing')} -> {terminal_text}"

    verification = _object(case.get("verification"))
    verification_status = str(verification.get("status", ""))
    coordinator_action = str(verification.get("coordinator_action", ""))
    if "blocked" in verification_status or "blocked" in coordinator_action:
        command_result = case.get("command_result")
        error_type = (
            command_result.get("error_type")
            if isinstance(command_result, dict)
            else None
        )
        reason = error_type or coordinator_action or verification_status or "unknown"
        return f"blocked:{_compact(reason)} -> {terminal_text}"

    if terminal.get("kind") == "command_result":
        return f"executed:{terminal.get('status', 'missing')} -> {terminal_text}"
    return terminal_text


def _result(case: dict[str, Any]) -> str:
    command_result = case.get("command_result")
    if isinstance(command_result, dict):
        status = "ok" if command_result.get("ok") is True else "failed"
        error_type = command_result.get("error_type")
        if isinstance(error_type, str) and error_type.casefold() == "none":
            error_type = None
        prefix = f"{status}:{_inline(error_type)}" if error_type else status
        message = command_result.get("message")
        return f"{prefix}: {_compact(message)}" if message else prefix
    presentation = case.get("user_visible_presentation")
    return _compact(presentation) if presentation else "none"


def _retry_detail(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    attempts = value.get("attempts")
    detail: dict[str, Any] = {
        "continued": value.get("continued"),
        "attempts": (
            ["ok" if item.get("success") is True else "failed" for item in attempts]
            if isinstance(attempts, list)
            else []
        ),
    }
    if value.get("decision") is not None:
        detail["decision"] = value["decision"]
    return detail


def _compact_state(state: dict[str, Any]) -> dict[str, Any]:
    raw = _object(state.get("raw"))
    preprocessed = _object(state.get("preprocessed"))
    epoch = _object(state.get("epoch"))
    dataset = _object(state.get("dataset"))
    training = _object(state.get("training"))
    return {
        "pipeline_stage": state.get("pipeline_stage"),
        "raw_loaded": raw.get("loaded"),
        "preprocessed": preprocessed.get("available"),
        "epochs": epoch.get("available"),
        "datasets": dataset.get("count"),
        "model": training.get("model_name"),
        "training_running": training.get("is_running"),
        "finished_runs": training.get("finished_run_count"),
        "state_reliable": state.get("state_reliable"),
    }


def _inline(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=True, sort_keys=True)
    return " ".join(text.replace("`", "'").split())


def _compact(value: Any, *, limit: int = 180) -> str:
    text = _inline(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _table(value: Any) -> str:
    return _inline(value).replace("|", "\\|")


def _duration(value: Any) -> str:
    try:
        milliseconds = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if milliseconds >= 1000:
        return f"{milliseconds / 1000:.2f}s"
    return f"{milliseconds:.1f}ms"


def _atomic_write(path: Path, content: str) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
