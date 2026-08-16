"""Validation and rendering for exact-Granite recovery evidence."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from scripts.dev.local_assistant_capture_runtime import (
    validate_strict_capture_evidence,
)
from XBrainLab.product_language import ASSISTANT_CANCELLED_MESSAGE

ARTIFACT_SCHEMA = "xbrainlab.chatpanel-local-recovery.v1"
JSON_ARTIFACT = "chatpanel-local-recovery-walkthrough.json"
MARKDOWN_ARTIFACT = "chatpanel-local-recovery-walkthrough.md"

BLOCKED_PROMPT = "Evaluate the current training results."
CANCELLATION_PROMPT = (
    "Explain in detail how EEG epoch windows, event timing, baselines, and data "
    "leakage safeguards relate. Do not run an XBrainLab action."
)
EXPECTED_PRECONDITION_COMMANDS = (
    "scan_source",
    "preview_interpretation",
    "validate_interpretation",
    "apply_interpretation",
    "preprocess",
    "create_epoch",
    "configure_dataset_split",
    "configure_training",
)
EXPECTED_RECOVERY_COMMANDS = ("train",)
REQUIRED_SCREENSHOTS = (
    "ready",
    "blocked_retry",
    "recovery_complete",
    "cancel_in_flight",
    "cancel_stopping",
    "cancelled_terminal",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

PRIOR_EVIDENCE_AUDIT: list[dict[str, str]] = [
    {
        "evidence": "strict exact-Granite guided boundary",
        "proves": (
            "Exact Granite proposes scan_source; deterministic host policy continues "
            "parameter-free preview/validate steps and preserves the typed wizard "
            "handoff boundary."
        ),
        "does_not_prove": (
            "A failed or blocked request can be retried successfully, or that an "
            "in-flight exact-model turn can be stopped."
        ),
    },
    {
        "evidence": "strict exact-Granite training readiness",
        "proves": (
            "Exact Granite configures training/readiness tools, exposes confirmation "
            "rejection, and shows a backend-owned blocked evaluation reason."
        ),
        "does_not_prove": (
            "Visible recovery of the same blocked request through Retry, or in-flight "
            "generation cancellation."
        ),
    },
    {
        "evidence": "strict exact-Granite training completion",
        "proves": (
            "Confirmation approval, bounded real training completion, evaluation, "
            "visualization, and saliency readiness through the product surface."
        ),
        "does_not_prove": "Error recovery or user cancellation of active generation.",
    },
    {
        "evidence": "secure offline RAG",
        "proves": (
            "Pinned offline embedding/index identity, scoped retrieval, request/tool "
            "filtering, and repeat initialization."
        ),
        "does_not_prove": (
            "End-to-end exact-Granite recovery behavior or ChatPanel cancellation."
        ),
    },
    {
        "evidence": "deterministic 202-turn product soak",
        "proves": (
            "Bounded pruning, external workflow-state refresh, clarification, history "
            "restore, UI responsiveness, and deterministic shutdown behavior."
        ),
        "does_not_prove": (
            "Long-session Granite quality or any exact-model recovery/cancel claim."
        ),
    },
]


def validate_recovery_evidence(
    payload: Mapping[str, object],
    *,
    strict: bool = True,
    artifact_root: Path | None = None,
) -> tuple[bool, str]:
    """Fail closed unless every recovery and cancellation observation is present."""
    if payload.get("schema") != ARTIFACT_SCHEMA:
        return False, "Recovery evidence schema is missing or unsupported."
    if strict and payload.get("status") != "passed":
        return False, "Only a passed recovery walkthrough can be strict evidence."

    audit = payload.get("prior_evidence_audit")
    if not isinstance(audit, list) or len(audit) != len(PRIOR_EVIDENCE_AUDIT):
        return False, "The prior evidence audit is incomplete."

    scenario = _mapping(payload.get("scenario"))
    ok, reason = _validate_precondition(_mapping(scenario.get("precondition")))
    if not ok:
        return False, reason
    ok, reason = _validate_blocked(_mapping(scenario.get("blocked")))
    if not ok:
        return False, reason
    ok, reason = _validate_host_recovery(_mapping(scenario.get("host_recovery")))
    if not ok:
        return False, reason
    ok, reason = _validate_retry(_mapping(scenario.get("retry")))
    if not ok:
        return False, reason
    ok, reason = _validate_cancellation(_mapping(scenario.get("cancellation")))
    if not ok:
        return False, reason

    screenshots = _mapping(payload.get("screenshots"))
    missing_screenshots = [
        name for name in REQUIRED_SCREENSHOTS if not screenshots.get(name)
    ]
    if missing_screenshots:
        return False, f"Required screenshots are missing: {missing_screenshots}."

    assistance = _mapping(payload.get("host_assistance"))
    actions = assistance.get("actions")
    if (
        assistance.get("classification") != "host-assisted"
        or assistance.get("used") is not True
        or not isinstance(actions, list)
        or len(actions) < 4
    ):
        return False, "Host-assisted setup and actions were not recorded explicitly."

    ui_state = _mapping(payload.get("ui_state"))
    if (
        ui_state.get("send_button_text") != "Send"
        or ui_state.get("input_enabled") is not True
        or ui_state.get("chat_processing") is not False
        or ui_state.get("controller_processing") is not False
        or ui_state.get("runtime_turn_in_flight") is not False
    ):
        return False, "ChatPanel did not return to a terminal idle state."

    if _mapping(payload.get("shutdown")).get("status") != "completed":
        return False, "Walkthrough did not reach bounded terminal shutdown."
    claim_boundary = str(payload.get("claim_boundary") or "").lower()
    for phrase in ("host-assisted", "not raw-model accuracy", "windows"):
        if phrase not in claim_boundary:
            return False, f"Claim boundary is missing: {phrase}."

    if strict:
        return validate_strict_capture_evidence(
            payload,
            artifact_root=artifact_root,
        )
    return True, ""


def _validate_blocked(blocked: Mapping[str, object]) -> tuple[bool, str]:
    resubmit = _mapping(blocked.get("resubmit_control"))
    text = str(blocked.get("assistant_text") or "").lower()
    if blocked.get("prompt") != BLOCKED_PROMPT:
        return False, "Blocked request does not match the bounded prompt."
    if blocked.get("presentation_kind") != "attention":
        return False, "Blocked command was not visible as a Needs attention result."
    if "review results" not in text or "training plan" not in text:
        return False, "Blocked command omitted the backend recovery guidance."
    if _has_successful_tool(blocked.get("new_tools")):
        return False, "Blocked command unexpectedly executed a tool."
    if blocked.get("terminal_outcome") != "completed":
        return False, "Blocked command did not reach one terminal acknowledgement."
    if (
        resubmit.get("visible") is not True
        or resubmit.get("enabled") is not True
        or resubmit.get("accessible_name") != "Assistant message"
    ):
        return False, "The visible composer was unavailable after the block."
    return True, ""


def _validate_precondition(precondition: Mapping[str, object]) -> tuple[bool, str]:
    commands = precondition.get("commands")
    if precondition.get("command_spine") != "ApplicationService.execute":
        return False, "Precondition did not use the real ApplicationService spine."
    if not isinstance(commands, list):
        return False, "ApplicationService precondition commands are missing."
    observed_names = [
        str(_mapping(command).get("command") or "") for command in commands
    ]
    if observed_names != list(EXPECTED_PRECONDITION_COMMANDS) or any(
        _mapping(command).get("ok") is not True for command in commands
    ):
        return False, "ApplicationService precondition sequence is incomplete."
    if (
        precondition.get("dataset_available") is not True
        or precondition.get("training_configured") is not True
    ):
        return False, "Training-configured dataset precondition was not reached."
    fixture = _mapping(precondition.get("fixture"))
    if (
        fixture.get("kind") != "synthetic_fif"
        or not _SHA256.fullmatch(str(fixture.get("sha256") or ""))
        or fixture.get("retained") is not False
        or "path" in fixture
    ):
        return False, "Precondition fixture identity is missing or exposes a path."
    return True, ""


def _validate_host_recovery(recovery: Mapping[str, object]) -> tuple[bool, str]:
    commands = recovery.get("commands")
    if recovery.get("command_spine") != "ApplicationService.execute":
        return False, "Recovery did not use the real ApplicationService command spine."
    if not isinstance(commands, list):
        return False, "ApplicationService recovery commands are missing."
    observed_names = [
        str(_mapping(command).get("command") or "") for command in commands
    ]
    if observed_names != list(EXPECTED_RECOVERY_COMMANDS) or any(
        _mapping(command).get("ok") is not True for command in commands
    ):
        return False, "ApplicationService recovery sequence is incomplete or failed."
    if (
        recovery.get("training_finished") is not True
        or recovery.get("evaluation_available") is not True
        or recovery.get("terminal_outcome") != "completed"
        or recovery.get("output_retained") is not False
    ):
        return False, "Training recovery did not reach evaluable terminal state."
    if (
        recovery.get("post_training_saliency_phase")
        not in {"succeeded", "failed", "cancelled"}
        or not _is_positive_int(recovery.get("publication_generation"))
        or not _is_positive_int(recovery.get("publication_revision"))
        or recovery.get("assistant_projection_revision")
        != recovery.get("publication_revision")
        or not _is_int_at_least(recovery.get("publication_stable_samples"), 3)
    ):
        return False, "Training recovery publication was not observably quiescent."
    return True, ""


def _validate_retry(retry: Mapping[str, object]) -> tuple[bool, str]:
    if (
        retry.get("prompt") != BLOCKED_PROMPT
        or retry.get("same_prompt") is not True
        or retry.get("invoked_via") != "ChatPanel composer"
    ):
        return False, "The composer did not recover the same blocked prompt."
    text_source = str(retry.get("assistant_text_source") or "product_runtime")
    if text_source != "product_runtime" or "granite output" in text_source.lower():
        return False, "Retry evidence contains fabricated host-named Granite output."
    proposals = retry.get("model_proposals")
    if not isinstance(proposals, list) or not any(
        _mapping(proposal).get("tool_name") == "evaluate" for proposal in proposals
    ):
        return False, "Exact-model Retry did not record an evaluate proposal."
    if not _is_positive_int(retry.get("model_calls")):
        return False, "Exact-model Retry did not record a model call."
    if not _successful_named_tool(retry.get("new_tools"), "evaluate"):
        return False, "Recovered Retry did not execute evaluate successfully."
    if (
        retry.get("terminal_outcome") != "completed"
        or retry.get("presentation_kind") != "assistant"
        or "evaluat" not in str(retry.get("assistant_text") or "").lower()
    ):
        return False, "Recovered Retry did not reach a visible successful terminal."
    return True, ""


def _validate_cancellation(cancellation: Mapping[str, object]) -> tuple[bool, str]:
    in_flight = _mapping(cancellation.get("in_flight"))
    correlation = _mapping(in_flight.get("correlation"))
    if cancellation.get("prompt") != CANCELLATION_PROMPT:
        return False, "Cancellation turn does not match the bounded prompt."
    if (
        in_flight.get("observed") is not True
        or in_flight.get("send_button_text") != "Stop"
        or in_flight.get("cancelability") != "cancellable"
        or in_flight.get("application_command_in_flight") is not False
        or not _is_positive_int(in_flight.get("model_calls"))
        or not _is_positive_int(correlation.get("generation"))
        or not _is_positive_int(correlation.get("turn_id"))
    ):
        return False, "A true cancellable in-flight model turn was not observed."
    if in_flight.get("generation_dispatch_phase") != "started":
        return False, "Cancellation did not observe a started generation dispatch."
    if (
        cancellation.get("stop_clicked") is not True
        or cancellation.get("stopping_observed") is not True
    ):
        return False, "Visible Stop and Stopping states were not both observed."
    if (
        cancellation.get("terminal_outcome") != "cancelled"
        or cancellation.get("presentation_kind") != "cancelled"
        or cancellation.get("assistant_text") != ASSISTANT_CANCELLED_MESSAGE
    ):
        return False, "Cancellation did not reach the typed cancelled terminal."
    if _has_successful_tool(cancellation.get("new_tools")):
        return False, "The cancelled turn executed an application tool."
    return True, ""


def relativize_screenshot_paths(
    payload: dict[str, Any],
    *,
    artifact_root: Path,
) -> None:
    """Replace local screenshot paths with artifact-relative names after sealing."""
    root = artifact_root.expanduser().resolve()
    screenshots = _mapping(payload.get("screenshots"))
    relative: dict[str, str] = {}
    for name, raw_path in screenshots.items():
        path = Path(str(raw_path or "")).expanduser()
        try:
            relative[str(name)] = path.resolve(strict=True).relative_to(root).as_posix()
        except (OSError, ValueError):
            relative[str(name)] = ""
    payload["screenshots"] = relative


def write_artifacts(output_dir: Path, payload: dict[str, Any]) -> None:
    """Write only evidence that satisfies the strict recovery contract."""
    root = output_dir.expanduser().resolve()
    if payload.get("status") == "passed":
        ok, reason = validate_recovery_evidence(
            payload,
            artifact_root=root,
        )
        if not ok:
            raise ValueError(f"Refusing to write invalid recovery evidence: {reason}")
    (root / JSON_ARTIFACT).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (root / MARKDOWN_ARTIFACT).write_text(
        render_markdown(payload),
        encoding="utf-8",
    )


def render_markdown(payload: Mapping[str, object]) -> str:
    """Render a concise human-reviewable recovery evidence summary."""
    runtime = _mapping(payload.get("runtime"))
    model = _mapping(runtime.get("model_identity"))
    source = _mapping(payload.get("source_identity"))
    scenario = _mapping(payload.get("scenario"))
    precondition = _mapping(scenario.get("precondition"))
    blocked = _mapping(scenario.get("blocked"))
    recovery = _mapping(scenario.get("host_recovery"))
    retry = _mapping(scenario.get("retry"))
    cancellation = _mapping(scenario.get("cancellation"))
    in_flight = _mapping(cancellation.get("in_flight"))
    shutdown = _mapping(payload.get("shutdown"))
    assistance = _mapping(payload.get("host_assistance"))

    lines = [
        "# ChatPanel Exact Granite Recovery Walkthrough",
        "",
        f"- status: `{payload.get('status', '')}`",
        f"- failure reason: {payload.get('failure_reason') or 'none'}",
        f"- requested model: `{runtime.get('requested_model_id', '')}`",
        f"- loaded model: `{runtime.get('loaded_model_id', '')}`",
        f"- loaded revision: `{model.get('loaded_revision', '')}`",
        f"- model snapshot digest: `{model.get('snapshot_manifest_sha256', '')}`",
        f"- source commit: `{source.get('commit_sha', '')}`",
        f"- source identity: `{source.get('identity_sha256', '')}`",
        f"- offline loading: `{_mapping(payload.get('hf_offline'))}`",
        f"- bounded terminal shutdown: `{shutdown.get('status', '')}`",
        f"- elapsed seconds: `{payload.get('elapsed_seconds', 0)}`",
        "",
        "## Existing Evidence Audit",
        "",
    ]
    audit = payload.get("prior_evidence_audit")
    for item in audit if isinstance(audit, list) else []:
        record = _mapping(item)
        lines.extend(
            [
                f"### {record.get('evidence', '')}",
                "",
                f"- proves: {record.get('proves', '')}",
                f"- does not prove: {record.get('does_not_prove', '')}",
                "",
            ]
        )

    lines.extend(
        [
            "## Blocked command and visible recovery",
            "",
            f"- host precondition spine: `{precondition.get('command_spine', '')}`",
            f"- host precondition commands: `{[_mapping(item).get('command') for item in precondition.get('commands', [])]}`",
            f"- prompt: {blocked.get('prompt', '')}",
            f"- presentation: `{blocked.get('presentation_kind', '')}`",
            f"- visible result: {blocked.get('assistant_text', '')}",
            f"- terminal: `{blocked.get('terminal_outcome', '')}`",
            f"- resubmit control: `{_mapping(blocked.get('resubmit_control'))}`",
            "",
            "## Same-prompt Recovery",
            "",
            f"- command spine: `{recovery.get('command_spine', '')}`",
            f"- host commands: `{[_mapping(item).get('command') for item in recovery.get('commands', [])]}`",
            f"- same prompt: `{retry.get('same_prompt')}`",
            f"- invoked via: `{retry.get('invoked_via', '')}`",
            f"- model proposals: `{retry.get('model_proposals', [])}`",
            f"- visible result: {retry.get('assistant_text', '')}",
            f"- terminal: `{retry.get('terminal_outcome', '')}`",
            "",
            "## Cancellable in-flight turn",
            "",
            f"- prompt: {cancellation.get('prompt', '')}",
            f"- visible in-flight state: `{in_flight}`",
            f"- Stop clicked: `{cancellation.get('stop_clicked')}`",
            f"- Stopping observed: `{cancellation.get('stopping_observed')}`",
            f"- visible terminal: {cancellation.get('assistant_text', '')}",
            f"- terminal outcome: `{cancellation.get('terminal_outcome', '')}`",
            "",
            "## Host Assistance",
            "",
        ]
    )
    for action in assistance.get("actions", []):
        lines.append(f"- {action}")

    lines.extend(["", "## Screenshots", ""])
    for name, path in _mapping(payload.get("screenshots")).items():
        lines.append(f"- {name}: `{path}`")
    lines.extend(
        [
            "",
            "## Claim Boundary",
            "",
            str(payload.get("claim_boundary") or ""),
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _successful_named_tool(value: object, name: str) -> bool:
    return any(
        _mapping(item).get("name") == name and _mapping(item).get("success") is True
        for item in _list(value)
    )


def _has_successful_tool(value: object) -> bool:
    return any(_mapping(item).get("success") is True for item in _list(value))


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_int_at_least(value: object, minimum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum
