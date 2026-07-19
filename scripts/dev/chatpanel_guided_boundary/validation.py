"""Fail-closed validation for real Guided Workflow boundary evidence."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    ROOT,
    inspect_screenshot_artifact,
    validate_source_identity,
)

DEFAULT_MODEL_ID = "microsoft/Phi-4-mini-instruct"
EXPECTED_AUTO_CHAIN = (
    "scan_source",
    "preview_interpretation",
    "validate_interpretation",
)
FIRST_PROMPT_TEMPLATE = (
    "Use the EEG recording at {source_path} to prepare the data for analysis. "
    "Continue through safe steps, and stop when the app needs my input."
)
EXPECTED_DECISION_FIELDS = ("metadata_review", "label_matching")
EXPECTED_WIZARD_STEPS = (
    "Choose EEG Data",
    "Load Labels",
    "Review Metadata",
    "Match Labels",
    "Review and Import",
)
EXPECTED_WIZARD_TARGET = "Review Metadata"
EXPECTED_WIZARD_CLASS = (
    "XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog."
    "DataInterpretationPreviewDialog"
)
_BOUNDARY_PHASES = [
    "created",
    "starting",
    "waiting_for_ready",
    "selecting_guided_mode",
    "running_auto_chain",
    "waiting_at_boundary",
    "workflow_handoff_open",
    "waiting_after_cancel",
]
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_ARTIFACT_ROOT = ROOT / "artifacts" / "ui" / "chatpanel-guided-boundary"
JSON_ARTIFACT = "chatpanel-local-guided-boundary-walkthrough.json"
MARKDOWN_ARTIFACT = "chatpanel-local-guided-boundary-walkthrough.md"
_CURRENT_SCREENSHOT_NAMES = {
    "ready": "chatpanel-guided-boundary-ready.png",
    "auto_chain_complete": "chatpanel-guided-auto-chain-complete.png",
    "workflow_dialog_open": "chatpanel-guided-workflow-dialog-open.png",
    "post_cancel": "chatpanel-guided-post-cancel.png",
}


def canonical_turn_calls(source_path: str, *, turn: str) -> list[dict[str, Any]]:
    """Return the exact model/host parameter contract for this walkthrough."""
    if turn == "first":
        return [
            {
                "tool_name": "scan_source",
                "parameters": {"source_path": str(Path(source_path).resolve())},
            },
            {"tool_name": "preview_interpretation", "parameters": {}},
            {"tool_name": "validate_interpretation", "parameters": {}},
        ]
    raise ValueError(f"Unsupported guided-boundary turn: {turn}")


def build_guided_prompts(source_path: Path) -> tuple[str]:
    """Return the one natural request exercised by the handoff proof."""
    absolute_path = Path(source_path).expanduser().resolve()
    return (FIRST_PROMPT_TEMPLATE.format(source_path=absolute_path),)


def validate_guided_boundary_payload(
    payload: Mapping[str, Any],
    *,
    require_shutdown: bool = True,
    refresh_source_identity: bool = True,
    current_source_identity: Mapping[str, Any] | None = None,
) -> tuple[bool, str]:
    """Validate one complete typed-handoff proof without partial evidence."""
    if refresh_source_identity and current_source_identity is not None:
        return False, "Test source identity override cannot bypass current-run refresh."
    if not refresh_source_identity and current_source_identity is None:
        return False, "Disabled source refresh requires an explicit current identity."

    status = payload.get("status")
    if status == "failed":
        return False, str(payload.get("failure_reason") or "Walkthrough failed.")
    if status != "passed":
        return False, "Guided walkthrough artifact status is not passed."
    if payload.get("schema_version") != 3:
        return False, "Guided walkthrough schema version is missing or unsupported."
    if payload.get("walkthrough") != "guided_workflow_ui_handoff_boundary":
        return False, "Artifact is not the Guided Workflow boundary walkthrough."
    if list(payload.get("expected_auto_chain") or []) != list(EXPECTED_AUTO_CHAIN):
        return False, "Artifact expected auto-chain does not match the chain contract."
    claim_boundary = str(payload.get("claim_boundary") or "")
    if "not human Windows desktop acceptance" not in claim_boundary:
        return False, "Artifact claim boundary does not exclude Windows acceptance."

    source_path = str(payload.get("source_path") or "")
    if not source_path:
        return False, "Guided walkthrough source path is missing."
    expected_prompts = list(build_guided_prompts(Path(source_path)))
    if list(payload.get("prompts") or []) != expected_prompts:
        return False, "Guided walkthrough prompts do not match the natural contract."
    prompt_text = " ".join(expected_prompts)
    leaked_names = [
        name
        for name in (*EXPECTED_AUTO_CHAIN, "apply_interpretation")
        if name in prompt_text
    ]
    if leaked_names:
        return False, f"Natural prompts exposed tool names: {leaked_names}."
    if _mapping(payload.get("confirmation")) or _mapping(payload.get("second_turn")):
        return False, "Legacy generic confirmation evidence is not allowed."

    ok, reason = _validate_source_identity(
        payload.get("source_identity"),
        refresh=refresh_source_identity,
        current_identity=current_source_identity,
    )
    if not ok:
        return ok, reason

    ok, reason = _validate_runtime(payload)
    if not ok:
        return ok, reason
    ok, reason = _validate_mode(payload.get("mode_selection"))
    if not ok:
        return ok, reason
    ok, reason = _validate_auto_chain(payload)
    if not ok:
        return ok, reason
    ok, reason = _validate_boundary(payload.get("boundary"))
    if not ok:
        return ok, reason
    ok, reason = _validate_action_item_summary(payload)
    if not ok:
        return ok, reason
    ok, reason = _validate_workflow_handoff(payload)
    if not ok:
        return ok, reason
    ok, reason = _validate_wizard(payload)
    if not ok:
        return ok, reason
    ok, reason = _validate_post_cancel(payload)
    if not ok:
        return ok, reason

    expected_phases = list(_BOUNDARY_PHASES)
    if require_shutdown:
        expected_phases.extend(["finalizing", "shutting_down", "completed"])
    if list(payload.get("phase_history") or []) != expected_phases:
        return False, "Guided walkthrough phase history skipped or repeated a boundary."

    if _visible_transcript_has_raw_tool_json(payload.get("visible_messages")):
        return False, "Visible transcript leaked raw tool JSON."
    if payload.get("transcript_clean") is not True:
        return (
            False,
            "Visible transcript exposed raw JSON, debug text, or runtime errors.",
        )
    ui = _mapping(payload.get("ui_state"))
    if (
        ui.get("send_button_text") != "Send"
        or not ui.get("send_button_enabled")
        or not ui.get("input_enabled")
        or ui.get("chat_processing")
        or ui.get("controller_processing")
        or ui.get("runtime_turn_in_flight")
    ):
        return False, "Assistant UI did not return to an idle, usable state."

    ok, reason = _validate_screenshot_artifacts(payload)
    if not ok:
        return ok, reason
    if (
        require_shutdown
        and _mapping(payload.get("shutdown")).get("status") != "completed"
    ):
        return False, "Guided walkthrough did not complete bounded clean shutdown."
    return True, ""


def validate_guided_boundary_artifact_root(
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
    *,
    canonical_root: Path | None = None,
    require_shutdown: bool = True,
    refresh_source_identity: bool = True,
    current_source_identity: Mapping[str, Any] | None = None,
) -> tuple[bool, str]:
    """Validate schema-3 evidence only from the one canonical current root."""
    root = artifact_root.expanduser().resolve()
    if any(part.startswith("current-run-") for part in root.parts):
        return False, "Legacy current-run-* evidence is not current evidence."
    expected_root = (
        canonical_root.expanduser().resolve()
        if canonical_root is not None
        else DEFAULT_ARTIFACT_ROOT.resolve()
    )
    if root != expected_root:
        return False, "Guided evidence is outside the canonical current root."

    json_path = root / JSON_ARTIFACT
    markdown_path = root / MARKDOWN_ARTIFACT
    if not json_path.is_file() or not markdown_path.is_file():
        return False, "Canonical Guided JSON/Markdown evidence is missing."
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"Canonical Guided JSON evidence is unreadable: {exc}."
    if not isinstance(payload, Mapping):
        return False, "Canonical Guided JSON root is not an object."
    try:
        generated_at = datetime.fromisoformat(
            str(payload.get("generated_at_utc") or "").replace("Z", "+00:00")
        )
    except ValueError:
        return (
            False,
            "Canonical Guided UTC publication timestamp is missing or invalid.",
        )
    if generated_at.tzinfo is None or generated_at.utcoffset() != timedelta(0):
        return False, "Canonical Guided publication timestamp is not UTC."

    source_identity = _mapping(payload.get("source_identity"))
    source_digest = str(source_identity.get("source_digest") or "")
    capture_source = _mapping(payload.get("capture_source"))
    started_digest = str(capture_source.get("source_digest_at_start") or "")
    completed_digest = str(capture_source.get("source_digest_at_completion") or "")
    if (
        capture_source.get("stable") is not True
        or not started_digest
        or started_digest != completed_digest
        or completed_digest != source_digest
    ):
        return False, "Canonical Guided capture source was not frozen."

    screenshots = _mapping(payload.get("screenshots"))
    for key, expected_name in _CURRENT_SCREENSHOT_NAMES.items():
        path = Path(str(screenshots.get(key) or "")).expanduser()
        if path.name != expected_name or path.resolve().parent != root:
            return False, f"Guided current screenshot is not canonical: {key}."
    markdown = markdown_path.read_text(encoding="utf-8")
    if str(payload.get("generated_at_utc")) not in markdown:
        return False, "Canonical Guided Markdown does not identify this publication."
    return validate_guided_boundary_payload(
        payload,
        require_shutdown=require_shutdown,
        refresh_source_identity=refresh_source_identity,
        current_source_identity=current_source_identity,
    )


def validate_auto_chain_boundary(
    *,
    source_path: str,
    initial_publication: Mapping[str, Any],
    command_observations: Sequence[Mapping[str, Any]],
    first_turn: Mapping[str, Any],
    boundary: Mapping[str, Any],
    require_completed_turn: bool = True,
) -> tuple[bool, str]:
    """Validate the autonomous safe chain before the UI handoff is accepted."""
    payload = {
        "source_path": source_path,
        "initial_publication": initial_publication,
        "command_observations": list(command_observations),
        "first_turn": first_turn,
        "boundary": boundary,
    }
    ok, reason = _validate_auto_chain(
        payload,
        require_completed_turn=require_completed_turn,
    )
    if not ok:
        return ok, reason
    return _validate_boundary(boundary)


def _validate_runtime(payload: Mapping[str, Any]) -> tuple[bool, str]:
    runtime = _mapping(payload.get("runtime"))
    offline = _mapping(payload.get("hf_offline"))
    if payload.get("model_id") != DEFAULT_MODEL_ID:
        return False, f"Guided proof requires exact model {DEFAULT_MODEL_ID}."
    if runtime.get("classification") != "gpu-ready":
        return False, "Guided proof requires a local GPU-ready runtime."
    if (
        runtime.get("requested_model_id") != DEFAULT_MODEL_ID
        or runtime.get("loaded_model_id") != DEFAULT_MODEL_ID
    ):
        return False, "Requested and loaded runtime models are not exact Phi-4."
    if runtime.get("phase") != "ready" or not runtime.get("initialized"):
        return False, "Exact Phi-4 runtime was not ready and initialized."
    if (
        runtime.get("selection_outcome") != "exact"
        or runtime.get("fallback_used") is not False
    ):
        return False, "Guided proof used a fallback model."
    if (
        offline.get("HF_HUB_OFFLINE") != "1"
        or offline.get("TRANSFORMERS_OFFLINE") != "1"
    ):
        return False, "Guided proof did not enforce offline Hugging Face runtime flags."
    return True, ""


def _validate_mode(value: object) -> tuple[bool, str]:
    mode = _mapping(value)
    if not mode.get("selected_by_click") or not mode.get("button_checked"):
        return False, "Guided Workflow was not selected through its real UI button."
    for owner in ("panel", "manager", "controller"):
        if mode.get(owner) != "multi":
            return False, f"Guided mode did not reach the {owner} owner."
    return True, ""


def _validate_auto_chain(
    payload: Mapping[str, Any],
    *,
    require_completed_turn: bool = True,
) -> tuple[bool, str]:
    initial = _mapping(payload.get("initial_publication"))
    if not _publication_usable(initial):
        return False, "Initial application publication was not usable."
    first_turn = _mapping(payload.get("first_turn"))
    tool_names = _successful_tool_names(first_turn.get("new_tools"))
    if tool_names != list(EXPECTED_AUTO_CHAIN):
        return False, "First turn did not execute exactly the safe auto-chain."
    proposal_names = _proposal_names(first_turn.get("tool_proposals"))
    if proposal_names != list(EXPECTED_AUTO_CHAIN):
        return False, "First turn model proposals did not match the exact auto-chain."
    ok, reason = _validate_turn_tool_attempts(
        first_turn,
        canonical_turn_calls(str(payload.get("source_path") or ""), turn="first"),
        actual_kind="execution",
    )
    if not ok:
        return ok, reason
    if require_completed_turn:
        metrics = _mapping(first_turn.get("metrics"))
        metric_names = _successful_tool_names(metrics.get("tool_executions"))
        if metrics.get("completed_turn_count") != 1 or metric_names != list(
            EXPECTED_AUTO_CHAIN
        ):
            return (
                False,
                "First turn metrics do not prove one exact Guided Workflow turn.",
            )
        if metrics.get("llm_calls") != len(EXPECTED_AUTO_CHAIN):
            return (
                False,
                "First turn used format recovery, retries, or extra model calls.",
            )

    observations = _sequence(payload.get("command_observations"))
    observed_names = [
        str(_mapping(item).get("command_name") or "") for item in observations
    ]
    if observed_names != list(EXPECTED_AUTO_CHAIN):
        return False, "Application results did not observe exactly the safe auto-chain."
    generations = [initial.get("generation")]
    for item in observations:
        observation = _mapping(item)
        if observation.get("success") is not True:
            return False, "A Guided Workflow auto-chain command did not succeed."
        publication = _mapping(observation.get("publication"))
        if not _publication_usable(publication):
            return (
                False,
                "An auto-chain publication was not usable, verified, and fresh.",
            )
        generations.append(publication.get("generation"))
    if not _strictly_increasing_integers(generations):
        return False, "Auto-chain publication generations did not strictly increase."

    boundary_publication = _mapping(
        _mapping(payload.get("boundary")).get("publication")
    )
    if boundary_publication.get("generation") != generations[-1]:
        return (
            False,
            "Boundary publication does not match the final auto-chain generation.",
        )
    return True, ""


def _validate_boundary(value: object) -> tuple[bool, str]:
    boundary = _mapping(value)
    publication = _mapping(boundary.get("publication"))
    if not _publication_usable(publication):
        return False, "Workflow handoff publication is not usable and current."
    state = _mapping(boundary.get("state"))
    raw = _mapping(state.get("raw"))
    interpretation = _mapping(state.get("interpretation"))
    if raw.get("loaded"):
        return False, "Raw EEG was loaded before the workflow handoff completed."
    if interpretation.get("has_applied_interpretation"):
        return False, "Interpretation was applied before the workflow handoff."
    if interpretation.get("validation_decision") != "needs_confirmation":
        return False, "Auto-chain did not stop at validation needs_confirmation."
    if not interpretation.get("pending_confirmation"):
        return False, "Validated interpretation did not publish pending confirmation."
    action_items = _blocking_action_items(interpretation)
    if not action_items:
        return False, "Validation published no concrete pending action items."
    target_steps = {str(item.get("target_step") or "") for item in action_items}
    if not {"Review Metadata", "Match Labels"}.issubset(target_steps):
        return False, "Validation action items do not cover metadata and label review."
    capability = _mapping(boundary.get("apply_capability"))
    if not capability.get("enabled"):
        return False, "Reviewed apply action was not enabled at the boundary."
    if not (
        capability.get("requires_confirmation")
        and capability.get("confirmation_required")
    ):
        return False, "Apply action did not retain its confirmation boundary."
    if capability.get("can_auto_execute"):
        return False, "Apply action could auto-execute across a decision boundary."
    return True, ""


def _validate_action_item_summary(payload: Mapping[str, Any]) -> tuple[bool, str]:
    boundary = _mapping(payload.get("boundary"))
    interpretation = _mapping(_mapping(boundary.get("state")).get("interpretation"))
    action_items = _blocking_action_items(interpretation)
    expected = _action_item_summary(
        action_items,
        blocked=interpretation.get("validation_decision") == "blocked",
    )
    assistant_messages = [
        str(_mapping(item).get("text") or "")
        for item in _sequence(payload.get("visible_messages"))
        if str(_mapping(item).get("sender") or "").casefold() == "assistant"
    ]
    if expected not in assistant_messages:
        return False, "Concrete validation action-item summary was not visible."
    first_turn = _mapping(payload.get("first_turn"))
    if expected not in [
        str(item) for item in _sequence(first_turn.get("assistant_messages"))
    ]:
        return False, "First turn did not retain the concrete action-item summary."
    prompts = list(payload.get("prompts") or [])
    user_messages = [
        str(_mapping(item).get("text") or "")
        for item in _sequence(payload.get("visible_messages"))
        if str(_mapping(item).get("sender") or "").casefold() == "user"
    ]
    if user_messages != prompts:
        return False, "Visible transcript contains an extra natural Continue prompt."
    return True, ""


def _validate_workflow_handoff(payload: Mapping[str, Any]) -> tuple[bool, str]:
    handoff = _mapping(payload.get("workflow_handoff"))
    if not handoff.get("observed") or not handoff.get("observed_while_dialog_visible"):
        return False, "Typed workflow UI handoff was not observed with the dialog."
    request = _mapping(handoff.get("request"))
    ok, reason = _validate_handoff_request(request)
    if not ok:
        return ok, reason
    for owner in ("controller_pending_request", "host_active_request"):
        if _mapping(handoff.get(owner)) != request:
            return False, f"Workflow handoff {owner} does not match the typed request."
    requests = [
        _mapping(item) for item in _sequence(payload.get("workflow_handoff_requests"))
    ]
    if requests != [request]:
        return False, "Expected exactly one matching typed workflow UI handoff signal."
    if _sequence(payload.get("confirmation_requests")):
        return False, "Generic confirmation was emitted for a workflow UI handoff."
    return True, ""


def _validate_handoff_request(request: Mapping[str, Any]) -> tuple[bool, str]:
    if request.get("kind") != "decision_required":
        return False, "Workflow handoff kind is not decision_required."
    if request.get("command") != "apply_interpretation":
        return False, "Workflow handoff command is not apply_interpretation."
    if not str(request.get("request_id") or ""):
        return False, "Workflow handoff has no typed request correlation id."
    if list(request.get("decision_fields") or []) != list(EXPECTED_DECISION_FIELDS):
        return False, "Workflow handoff decision fields are not exact."
    if list(request.get("suggested_values") or []) != []:
        return False, "Workflow handoff unexpectedly contains suggested values."
    return True, ""


def _validate_wizard(payload: Mapping[str, Any]) -> tuple[bool, str]:
    wizard = _mapping(payload.get("wizard"))
    if not wizard.get("dialog_opened") or not wizard.get("dialog_visible"):
        return False, "Real Data Import wizard dialog was not observed while visible."
    if wizard.get("dialog_class") != EXPECTED_WIZARD_CLASS:
        return (
            False,
            "Observed dialog was not the real DataInterpretationPreviewDialog.",
        )
    if (
        wizard.get("object_name") != "DataImportWizardDialog"
        or wizard.get("dialog_title") != "Import EEG Data"
    ):
        return False, "Observed Data Import wizard identity is incorrect."
    request = _mapping(_mapping(payload.get("workflow_handoff")).get("request"))
    if wizard.get("request_id") != request.get("request_id"):
        return False, "Wizard does not correlate to the typed workflow handoff."
    if list(wizard.get("decision_fields") or []) != list(EXPECTED_DECISION_FIELDS):
        return False, "Wizard decision fields differ from the typed handoff."
    if list(wizard.get("step_titles") or []) != list(EXPECTED_WIZARD_STEPS):
        return False, "Data Import wizard step contract is incomplete."
    if (
        wizard.get("current_step_index")
        != EXPECTED_WIZARD_STEPS.index(EXPECTED_WIZARD_TARGET)
        or wizard.get("current_step_title") != EXPECTED_WIZARD_TARGET
    ):
        return False, "Data Import wizard did not open at the exact target step."
    if wizard.get("cancel_button_text") != "Cancel" or not wizard.get("cancel_clicked"):
        return False, "Data Import wizard was not cancelled through its Cancel button."
    if not wizard.get("cancel_signal_observed") or wizard.get(
        "visible_after_cancel_click"
    ):
        return False, "Data Import wizard did not close after its Cancel action."
    if not wizard.get("screenshot"):
        return False, "Data Import wizard screenshot was not captured."
    interactions = _sequence(payload.get("interaction_events"))
    if len(interactions) != 1:
        return False, "Expected exactly one workflow handoff cancellation outcome."
    interaction = _mapping(interactions[0])
    if (
        interaction.get("request_id") != request.get("request_id")
        or interaction.get("command_name") != "apply_interpretation"
        or interaction.get("status") != "cancelled"
    ):
        return False, "Cancellation outcome does not match the workflow handoff."
    if len(_sequence(payload.get("turn_terminals"))) != 1:
        return False, "Guided walkthrough did not terminate exactly one host turn."
    return True, ""


def _validate_post_cancel(payload: Mapping[str, Any]) -> tuple[bool, str]:
    post_cancel = _mapping(payload.get("post_cancel"))
    boundary = _mapping(payload.get("boundary"))
    boundary_publication = _mapping(boundary.get("publication"))
    post_publication = _mapping(post_cancel.get("publication"))
    if not _publication_usable(post_publication):
        return False, "Post-cancel publication is not usable."
    if post_publication.get("generation") != boundary_publication.get("generation"):
        return False, "Publication generation changed after cancellation."
    if post_cancel.get("state") != boundary.get("state"):
        return (
            False,
            "Workflow state changed after cancellation; it must remain unchanged.",
        )
    if post_cancel.get("pending_workflow_handoff"):
        return False, "Workflow UI handoff remained pending after cancellation."
    if post_cancel.get("workflow_dialog_visible"):
        return False, "Data Import wizard remained visible after cancellation."
    if post_cancel.get("apply_completion_observed"):
        return False, "Apply completion was observed after cancellation."

    names = _successful_tool_names(payload.get("executed_tools"))
    if names != list(EXPECTED_AUTO_CHAIN):
        return (
            False,
            "Executed tools were not exactly the safe auto-chain after cancel.",
        )
    post_names = _successful_tool_names(post_cancel.get("executed_tools"))
    if post_names != list(EXPECTED_AUTO_CHAIN):
        return False, "Post-cancel tool state contains an extra or missing action."
    application_names = [
        str(_mapping(item).get("command_name") or "")
        for item in _sequence(payload.get("application_results"))
    ]
    if application_names != list(EXPECTED_AUTO_CHAIN):
        return False, "Application completion results included an extra mutation."
    state = _mapping(post_cancel.get("state"))
    raw = _mapping(state.get("raw"))
    interpretation = _mapping(state.get("interpretation"))
    if raw.get("loaded") or interpretation.get("has_applied_interpretation"):
        return False, "Dataset or interpretation mutated after wizard cancellation."
    return True, ""


def _blocking_action_items(
    interpretation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen_issues: set[str] = set()
    for value in _sequence(interpretation.get("action_items")):
        item = _mapping(value)
        severity = str(item.get("severity") or "").strip().lower()
        issue = " ".join(str(item.get("issue") or "").split())
        if (
            severity not in {"blocked", "needs_confirmation"}
            or not issue
            or issue in seen_issues
        ):
            continue
        normalized = dict(item)
        normalized["issue"] = issue
        items.append(normalized)
        seen_issues.add(issue)
    return items


def _action_item_summary(
    action_items: Sequence[Mapping[str, Any]],
    *,
    blocked: bool,
) -> str:
    visible = list(action_items[:3])
    lines = [
        "Import review is blocked:" if blocked else "Import review needs your input:",
        *(f"- {item['issue']}" for item in visible),
    ]
    if len(action_items) > len(visible):
        lines.append(f"- {len(action_items) - len(visible)} more item(s)")
    lines.append("Open Import Review to resolve these choices.")
    return "\n".join(lines)


def _publication_usable(publication: Mapping[str, Any]) -> bool:
    return bool(
        publication.get("available")
        and publication.get("usable")
        and publication.get("verified")
        and not publication.get("stale")
        and not publication.get("refresh_error")
        and isinstance(publication.get("generation"), int)
        and not isinstance(publication.get("generation"), bool)
    )


def _strictly_increasing_integers(values: Sequence[object]) -> bool:
    if not values or any(
        isinstance(value, bool) or not isinstance(value, int) for value in values
    ):
        return False
    integers = [value for value in values if isinstance(value, int)]
    return all(left < right for left, right in pairwise(integers))


def _successful_tool_names(value: object) -> list[str]:
    items = [_mapping(item) for item in _sequence(value)]
    if any(item.get("success") is not True for item in items):
        return []
    return [str(item.get("name") or "") for item in items]


def _proposal_names(value: object) -> list[str]:
    return [str(_mapping(item).get("tool_name") or "") for item in _sequence(value)]


def _validate_turn_tool_attempts(
    turn: Mapping[str, Any],
    expected_calls: Sequence[Mapping[str, Any]],
    *,
    actual_kind: str,
) -> tuple[bool, str]:
    proposals = [_mapping(item) for item in _sequence(turn.get("tool_proposals"))]
    attempts = [_mapping(item) for item in _sequence(turn.get("tool_attempts"))]
    if len(proposals) != len(expected_calls):
        return False, "Tool proposal count does not match the canonical contract."
    if len(attempts) != len(expected_calls):
        return False, "Tool attempt trace does not cover every canonical proposal."

    for index, expected_value in enumerate(expected_calls):
        expected = _canonical_call(expected_value)
        proposal = _canonical_call(proposals[index])
        attempt = attempts[index]
        raw = _canonical_call(attempt.get("raw"))
        canonical = _canonical_call(attempt.get("canonical"))
        normalized = _canonical_call(attempt.get("normalized"))
        actual_value = _mapping(attempt.get("actual"))
        actual = _canonical_call(actual_value)
        label = str(expected.get("tool_name") or f"proposal {index}")
        if proposal != expected or raw != expected:
            return False, f"{label} raw parameters are not the exact canonical values."
        if canonical != expected:
            return False, f"{label} recorded canonical parameters are inconsistent."
        if normalized != expected:
            return False, f"{label} normalized parameters differ from canonical values."
        if actual_value.get("kind") != actual_kind or actual != expected:
            return (
                False,
                f"{label} actual host parameters differ from normalized values.",
            )
    return True, ""


def _canonical_call(value: object) -> dict[str, Any]:
    call = _mapping(value)
    parameters = call.get("parameters")
    return {
        "tool_name": str(call.get("tool_name") or ""),
        "parameters": dict(parameters) if isinstance(parameters, Mapping) else {},
    }


def _validate_screenshot_artifacts(
    payload: Mapping[str, Any],
) -> tuple[bool, str]:
    screenshots = _mapping(payload.get("screenshots"))
    recorded = _mapping(payload.get("screenshot_artifacts"))
    for name in (
        "ready",
        "auto_chain_complete",
        "workflow_dialog_open",
        "post_cancel",
    ):
        path = str(screenshots.get(name) or "")
        metadata = _mapping(recorded.get(name))
        if not path or not metadata:
            return False, f"Required screenshot evidence is missing: {name}."
        observed = inspect_screenshot_artifact(path)
        if not observed.get("exists") or not observed.get("readable"):
            return False, f"Required screenshot is missing or unreadable: {name}."
        dimensions = observed.get("dimensions")
        if not (
            isinstance(dimensions, list)
            and len(dimensions) == 2
            and all(isinstance(item, int) and item > 0 for item in dimensions)
        ):
            return False, f"Required screenshot has invalid dimensions: {name}."
        for field in (
            "path",
            "exists",
            "readable",
            "byte_size",
            "sha256",
            "dimensions",
            "format",
        ):
            if metadata.get(field) != observed.get(field):
                return False, f"Screenshot metadata/hash mismatch: {name} ({field})."
        if not _HEX_SHA256.fullmatch(str(metadata.get("sha256") or "")):
            return False, f"Required screenshot hash is invalid: {name}."
    wizard_path = str(_mapping(payload.get("wizard")).get("screenshot") or "")
    if wizard_path != str(screenshots.get("workflow_dialog_open") or ""):
        return False, "Wizard screenshot path does not match screenshot evidence."
    return True, ""


def _validate_source_identity(
    value: object,
    *,
    refresh: bool,
    current_identity: Mapping[str, Any] | None,
) -> tuple[bool, str]:
    return validate_source_identity(
        value,
        expected_repo_root=ROOT,
        refresh=refresh,
        current_identity=current_identity,
        artifact_name="Guided walkthrough",
    )


def _visible_transcript_has_raw_tool_json(value: object) -> bool:
    for item in _sequence(value):
        message = _mapping(item)
        if str(message.get("sender") or "").casefold() != "assistant":
            continue
        text = str(message.get("text") or "")
        if re.search(r'"(?:tool_name|parameters)"\s*:', text):
            return True
        decoder = json.JSONDecoder()
        for match in re.finditer(r"[\[{]", text):
            try:
                decoded, _end = decoder.raw_decode(text[match.start() :])
            except json.JSONDecodeError:
                continue
            if _contains_tool_envelope(decoded):
                return True
    return False


def _contains_tool_envelope(value: object) -> bool:
    if isinstance(value, Mapping):
        keys = {str(key).casefold() for key in value}
        if "tool_name" in keys or ({"action", "parameters"} <= keys):
            return True
        return any(_contains_tool_envelope(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_tool_envelope(item) for item in value)
    return False


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: object) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []
