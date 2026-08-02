"""Assistant and GUI-with-Agent walkthrough contract validation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from scripts.dev.human_like_walkthrough.contract import (
    ASSISTANT_CONFIRMED_TERMINAL_MESSAGE,
    ASSISTANT_NARROW_DOCK_WIDTH,
    ASSISTANT_REQUIRED_FULL_WINDOW_SCREENSHOTS,
    ASSISTANT_REQUIRED_PHASES,
    ASSISTANT_REQUIRED_SCREENSHOTS,
    ASSISTANT_STANDARD_DOCK_WIDTH,
    ASSISTANT_STOPPED_MESSAGE,
    build_artifact_contract,
)
from XBrainLab.llm.core.model_catalog import PRIMARY_LOCAL_MODEL_ID

ASSISTANT_REVIEW_KEYS = (
    "assistant_processing_contract_review",
    "assistant_runtime_contract_review",
    "assistant_dock_contract_review",
    "assistant_full_window_contract_review",
    "assistant_notice_contract_review",
    "assistant_signal_path_review",
    "assistant_error_contract_review",
    "assistant_claim_contract_review",
    "assistant_interaction_contract_review",
    "assistant_settings_recovery_review",
)


def build_assistant_contract_reviews(
    phases: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build every assistant-specific review from one phase collection."""
    return {
        "assistant_stage_copy_review": build_assistant_stage_copy_review(phases),
        "assistant_processing_contract_review": (
            build_assistant_processing_contract_review(phases)
        ),
        "assistant_runtime_contract_review": build_assistant_runtime_contract_review(
            phases
        ),
        "assistant_dock_contract_review": build_assistant_dock_contract_review(phases),
        "assistant_full_window_contract_review": (
            build_assistant_full_window_contract_review(phases)
        ),
        "assistant_notice_contract_review": build_assistant_notice_contract_review(
            phases
        ),
        "assistant_signal_path_review": build_assistant_signal_path_review(phases),
        "assistant_error_contract_review": build_assistant_error_contract_review(
            phases
        ),
        "assistant_claim_contract_review": build_assistant_claim_contract_review(
            phases
        ),
        "assistant_interaction_contract_review": (
            build_assistant_interaction_contract_review(phases)
        ),
        "assistant_settings_recovery_review": (
            build_assistant_settings_recovery_review(phases)
        ),
    }


def assistant_contract_findings(
    reviews: dict[str, dict[str, Any]],
) -> list[str]:
    """Flatten findings from the required assistant behavior contracts."""
    findings: list[str] = []
    for key in ASSISTANT_REVIEW_KEYS:
        findings.extend(str(item) for item in reviews[key].get("findings", []))
    return findings


def required_assistant_screenshot_failures(
    screenshots: dict[str, str],
) -> list[str]:
    """Return missing screenshot-key failures for required assistant states."""
    return [
        f"{key.replace('_', ' ')} screenshot key is missing"
        for key in ASSISTANT_REQUIRED_SCREENSHOTS
        if key not in screenshots
    ]


def validate_assistant_payload(
    payload: dict[str, Any],
    *,
    forbidden_visible_text: Callable[[list[str]], list[str]],
) -> tuple[bool, str]:
    """Validate assistant contract identity, phases, screenshots, and evidence."""
    expected_contract = build_artifact_contract()
    contract = payload.get("artifact_contract", {})
    if not isinstance(contract, dict):
        return False, "walkthrough artifact contract is missing"
    if contract.get("version") != expected_contract["version"]:
        return False, "walkthrough JSON uses a stale evidence contract version"
    if contract.get("source_fingerprint") != expected_contract["source_fingerprint"]:
        return False, "walkthrough JSON is stale for the current assistant sources"
    capture_source = payload.get("capture_source", {})
    if not isinstance(capture_source, dict) or not capture_source:
        return False, "walkthrough capture source stability evidence is missing"
    expected_fingerprint = expected_contract["source_fingerprint"]
    if (
        capture_source.get("stable") is not True
        or capture_source.get("fingerprint_at_start") != expected_fingerprint
        or capture_source.get("fingerprint_at_completion") != expected_fingerprint
    ):
        return False, "walkthrough capture source changed or was not observed"
    if (
        contract.get("assistant_driver") != "agent_manager_qt_signals"
        or contract.get("assistant_capture_target") != "full_dock"
        or contract.get("assistant_state_capture_target")
        != "full_dock_and_full_main_window"
        or contract.get("assistant_full_window_phases")
        != list(ASSISTANT_REQUIRED_FULL_WINDOW_SCREENSHOTS)
        or contract.get("assistant_full_window_screenshots")
        != dict(ASSISTANT_REQUIRED_FULL_WINDOW_SCREENSHOTS)
        or contract.get("assistant_handoff_capture_target") != "full_main_window"
    ):
        return False, "walkthrough assistant evidence bypasses the product contract"

    phase_rows = payload.get("phases", [])
    assistant_phases = tuple(
        str(phase.get("phase") or "")
        for phase in phase_rows
        if str(phase.get("phase") or "").startswith("assistant_")
    )
    if assistant_phases != ASSISTANT_REQUIRED_PHASES:
        return False, "assistant phase sequence does not match the canonical order"
    screenshot_failures = required_assistant_screenshot_failures(
        payload.get("screenshots", {})
    )
    if screenshot_failures:
        return False, screenshot_failures[0]

    visible_internal: list[str] = []
    for phase in phase_rows:
        visible_internal.extend(forbidden_visible_text(phase.get("visible_text", [])))
    transcript_text = [
        str(item.get("text") or "")
        for item in payload.get("user_facing_message_transcript", [])
        if isinstance(item, dict)
    ]
    visible_internal.extend(forbidden_visible_text(transcript_text))
    if visible_internal:
        return False, f"assistant artifact exposes internal text: {visible_internal}"

    reviews = build_assistant_contract_reviews(phase_rows)
    findings = assistant_contract_findings(reviews)
    if findings:
        return False, "; ".join(findings)
    chat_review = build_chat_geometry_review(phase_rows)
    if not chat_review["passed"]:
        return False, "; ".join(
            str(finding) for finding in chat_review.get("findings", [])
        )
    return True, ""


def validate_recorded_assistant_reviews(
    ui_quality_review: dict[str, Any],
) -> tuple[bool, str]:
    """Ensure the persisted UI review records every required assistant pass."""
    for review_name in ASSISTANT_REVIEW_KEYS:
        if not ui_quality_review.get(review_name, {}).get("passed"):
            return False, f"{review_name.replace('_', ' ')} did not pass"
    return True, ""


def build_assistant_processing_contract_review(
    phases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate processing controls, readable status, and idle restoration."""
    matches = [
        phase for phase in phases if phase.get("phase") == "assistant_processing_state"
    ]
    findings: list[str] = []
    if len(matches) != 1:
        findings.append(
            "assistant processing contract requires exactly one processing phase"
        )
    if not matches:
        return {
            "passed": False,
            "checked_phases": 0,
            "findings": findings,
            "evidence": {},
        }
    idle_matches = [
        phase for phase in phases if phase.get("phase") == "assistant_idle_after_stop"
    ]
    if len(idle_matches) != 1:
        findings.append(
            "assistant processing contract requires one idle-after-Stop phase"
        )

    phase = matches[0]
    notes = phase.get("notes", {})
    notes = notes if isinstance(notes, dict) else {}
    processing = notes.get("assistant_processing", {})
    processing = processing if isinstance(processing, dict) else {}
    restored = notes.get("restored_state", {})
    restored = restored if isinstance(restored, dict) else {}
    visible_text = {
        " ".join(str(item).split()) for item in phase.get("visible_text", [])
    }
    button_states = [
        item for item in phase.get("button_state", []) if isinstance(item, dict)
    ]

    if not bool(processing.get("controller_processing")) or not bool(
        processing.get("panel_processing")
    ):
        findings.append("assistant processing did not capture active request state")
    if processing.get("runtime_phase") != "ready":
        findings.append("assistant processing occurred before runtime was ready")
    if bool(processing.get("composer_input_enabled", True)):
        findings.append("assistant processing composer input is not disabled")

    if bool(processing.get("manual_mode_selector_present")):
        findings.append("assistant processing still exposes a manual mode selector")

    stop_button = processing.get("stop_button", {})
    stop_button = stop_button if isinstance(stop_button, dict) else {}
    visible_stop = next(
        (item for item in button_states if item.get("text") == "Stop"),
        None,
    )
    if (
        stop_button.get("text") != "Stop"
        or not bool(stop_button.get("visible"))
        or not bool(stop_button.get("enabled"))
        or int(stop_button.get("width", 0) or 0) <= 0
        or int(stop_button.get("height", 0) or 0) <= 0
        or visible_stop is None
        or "Stop" not in visible_text
    ):
        findings.append("assistant processing visible Stop button evidence is missing")

    turn_activity = processing.get("turn_activity", {})
    turn_activity = turn_activity if isinstance(turn_activity, dict) else {}
    primary_status = turn_activity.get("primary_status", {})
    primary_status = primary_status if isinstance(primary_status, dict) else {}
    step = turn_activity.get("step", {})
    step = step if isinstance(step, dict) else {}
    if (
        not bool(turn_activity.get("visible"))
        or turn_activity.get("phase") != "working"
        or turn_activity.get("cancelability") != "cancellable"
        or primary_status.get("text") != "Preparing your request"
        or not bool(primary_status.get("visible"))
        or step.get("text") != "Current step: Checking the current EEG workflow"
        or not bool(step.get("visible"))
        or "Preparing your request" not in visible_text
    ):
        findings.append("assistant processing typed turn activity is not visible")
    activity_overflows = (
        not bool(primary_status.get("fits_height"))
        or not bool(step.get("fits_height"))
        or int(primary_status.get("available_width", 0) or 0) <= 0
        or int(step.get("available_width", 0) or 0) <= 0
    )
    if activity_overflows:
        findings.append("assistant processing turn activity text overflows its bounds")

    stopping = notes.get("stopping_state", {})
    stopping = stopping if isinstance(stopping, dict) else {}
    stopping_activity = stopping.get("turn_activity", {})
    stopping_activity = stopping_activity if isinstance(stopping_activity, dict) else {}
    stopping_button = stopping.get("stop_button", {})
    stopping_button = stopping_button if isinstance(stopping_button, dict) else {}
    if (
        not bool(stopping.get("controller_processing"))
        or not bool(stopping.get("panel_processing"))
        or stopping_activity.get("phase") != "stopping"
        or stopping_activity.get("cancelability") != "stopping"
        or stopping_button.get("text") != "Stopping"
        or not bool(stopping_button.get("visible"))
        or bool(stopping_button.get("enabled"))
    ):
        findings.append("assistant Stop did not expose a valid Stopping state")

    idle_evidence = (
        (idle_matches[0].get("notes") or {}).get("assistant_idle", {})
        if idle_matches
        else {}
    )
    restored_ok = (
        not bool(restored.get("manual_mode_selector_present"))
        and not bool(restored.get("controller_processing", True))
        and not bool(restored.get("panel_processing", True))
        and bool(restored.get("composer_input_enabled"))
        and restored.get("send_button_text") == "Send"
        and not bool(restored.get("workflow_status_visible", True))
        and idle_evidence == restored
    )
    if not restored_ok:
        findings.append("assistant processing did not restore the idle state")

    cancelled_turn = (
        (idle_matches[0].get("notes") or {}).get("assistant_cancelled_turn", {})
        if idle_matches
        else {}
    )
    cancelled_turn = cancelled_turn if isinstance(cancelled_turn, dict) else {}
    terminal_messages = [
        " ".join(str(item).split())
        for item in cancelled_turn.get("terminal_messages", [])
    ]
    idle_visible_text = {
        " ".join(str(item).split())
        for item in (idle_matches[0].get("visible_text", []) if idle_matches else [])
    }
    if terminal_messages != [ASSISTANT_STOPPED_MESSAGE] or (
        ASSISTANT_STOPPED_MESSAGE not in idle_visible_text
    ):
        findings.append("assistant terminal cancellation result is missing")

    return {
        "passed": len(matches) == 1 and not findings,
        "checked_phases": len(matches),
        "findings": findings,
        "evidence": {
            "turn_activity": dict(turn_activity),
            "stopping_state": dict(stopping),
            "stop_button": dict(stop_button),
            "composer_input_enabled": processing.get("composer_input_enabled"),
            "restored_state": dict(restored),
            "idle_after_stop": dict(idle_evidence),
            "cancelled_turn": dict(cancelled_turn),
        },
    }


def build_assistant_runtime_contract_review(
    phases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate setup, loading, recovery, ready, and failed runtime semantics."""
    findings: list[str] = []
    evidence_by_phase: dict[str, dict[str, Any]] = {}
    expected = {
        "idle": "assistant_runtime_idle",
        "loading": "assistant_runtime_loading",
        "recovery": "assistant_runtime_recovery_loading",
        "ready": "assistant_runtime_ready",
        "failed": "assistant_runtime_failed",
    }
    for runtime_phase, phase_name in expected.items():
        matches = [phase for phase in phases if phase.get("phase") == phase_name]
        if len(matches) != 1:
            findings.append(
                f"assistant runtime contract requires one {runtime_phase} phase"
            )
            continue
        evidence = (matches[0].get("notes") or {}).get("assistant_runtime", {})
        evidence_by_phase[runtime_phase] = (
            evidence if isinstance(evidence, dict) else {}
        )

    for runtime_phase, evidence in evidence_by_phase.items():
        if bool(evidence.get("panel_processing")) and runtime_phase != "ready":
            findings.append(
                f"assistant processing is invalid during {runtime_phase} runtime state"
            )
        if runtime_phase != "ready" and evidence.get("send_button_text") == "Stop":
            label = (
                "setup-required"
                if runtime_phase in {"idle", "failed"}
                else runtime_phase
            )
            findings.append(f"assistant {label} state incorrectly presented Stop")

    for runtime_phase in ("idle", "loading", "recovery", "failed"):
        evidence = evidence_by_phase.get(runtime_phase, {})
        if not bool(evidence.get("inline_state_visible")):
            findings.append(
                f"assistant {runtime_phase} state has no visible inline runtime state"
            )
        if evidence.get("inline_state_location") != "content":
            findings.append(
                f"assistant {runtime_phase} runtime state is not in conversation content"
            )
        if not bool(evidence.get("composer_visible")):
            findings.append(f"assistant {runtime_phase} hides the disabled composer")

    for runtime_phase, title in (
        ("idle", "Assistant setup required"),
        ("failed", "Assistant unavailable"),
    ):
        evidence = evidence_by_phase.get(runtime_phase, {})
        if evidence.get("inline_state_title") != title:
            findings.append(
                f"assistant {runtime_phase} state uses incorrect recovery copy"
            )
        expected_setup_text = (
            "Settings" if runtime_phase == "failed" else "Open Assistant Settings"
        )
        if (
            not bool(evidence.get("setup_action_visible"))
            or not bool(evidence.get("setup_action_enabled"))
            or evidence.get("setup_action_text") != expected_setup_text
        ):
            findings.append(
                f"assistant {runtime_phase} state has an incorrect settings action"
            )
        retry_expected = runtime_phase == "failed"
        if (
            bool(evidence.get("retry_action_visible")) != retry_expected
            or bool(evidence.get("retry_action_enabled")) != retry_expected
            or (
                retry_expected
                and evidence.get("retry_action_text") != "Retry local assistant"
            )
        ):
            findings.append(
                f"assistant {runtime_phase} state has incorrect runtime retry action"
            )
        if bool(evidence.get("composer_input_enabled")) or bool(
            evidence.get("send_button_enabled")
        ):
            findings.append(
                f"assistant {runtime_phase} composer is enabled before recovery"
            )

    idle = evidence_by_phase.get("idle", {})
    if idle.get("phase") != "idle":
        findings.append("assistant runtime idle phase was not published")

    loading = evidence_by_phase.get("loading", {})
    if loading.get("phase") != "loading":
        findings.append("assistant runtime loading phase was not published")
    if bool(loading.get("composer_input_enabled")):
        findings.append("assistant composer remained enabled while loading")
    if bool(loading.get("send_button_enabled")):
        findings.append("assistant Send remained enabled while loading")
    if loading.get("send_button_text") != "Send":
        findings.append("assistant loading state incorrectly presented Stop")
    if loading.get("inline_state_title") != "Loading local assistant":
        findings.append("assistant loading state has no visible loading cue")
    if bool(loading.get("status_visible")):
        findings.append("assistant loading state duplicated runtime copy in the footer")
    if bool(loading.get("setup_action_visible")):
        findings.append("assistant loading state exposes a stale setup action")

    recovery = evidence_by_phase.get("recovery", {})
    if recovery.get("phase") != "loading":
        findings.append("assistant runtime recovery loading phase was not published")
    recovery_title = str(recovery.get("inline_state_title") or "")
    recovery_detail = str(recovery.get("inline_state_detail") or "")
    stale_recovery_text = f"{recovery_title} {recovery_detail}".lower()
    if "retry" not in recovery_title.lower():
        findings.append("assistant recovery does not clearly show retrying")
    if any(
        marker in stale_recovery_text for marker in ("unavailable", "setup required")
    ):
        findings.append(
            "assistant recovery leaves stale unavailable or setup copy visible"
        )
    if bool(recovery.get("setup_action_visible")):
        findings.append("assistant recovery leaves a stale setup action visible")
    if bool(recovery.get("status_visible")):
        findings.append("assistant recovery duplicated runtime copy in the footer")
    if bool(recovery.get("composer_input_enabled")) or bool(
        recovery.get("send_button_enabled")
    ):
        findings.append("assistant recovery enabled the composer before runtime ready")

    ready = evidence_by_phase.get("ready", {})
    if ready.get("phase") != "ready":
        findings.append("assistant runtime ready phase was not published")
    if not bool(ready.get("composer_input_enabled")):
        findings.append("assistant composer did not enable when runtime became ready")
    if bool(ready.get("send_button_enabled")) != bool(ready.get("composer_has_text")):
        findings.append(
            "assistant Send state does not match whether the ready composer has input"
        )
    if ready.get("send_button_text") != "Send":
        findings.append("assistant ready state did not present Send")
    if bool(ready.get("inline_state_visible")):
        findings.append("assistant ready state left stale runtime copy visible")
    if bool(ready.get("setup_action_visible")):
        findings.append("assistant ready state left Open Assistant Settings visible")

    failed = evidence_by_phase.get("failed", {})
    if failed.get("phase") != "failed":
        findings.append("assistant runtime failed phase was not published")
    if bool(failed.get("composer_input_enabled")):
        findings.append("assistant composer remained enabled after runtime failure")
    if bool(failed.get("send_button_enabled")):
        findings.append("assistant Send remained enabled after runtime failure")
    if failed.get("send_button_text") != "Send":
        findings.append("assistant failed state incorrectly presented Stop")
    return {
        "passed": not findings,
        "findings": findings,
        "evidence": evidence_by_phase,
    }


def build_assistant_signal_path_review(
    phases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Reject evidence that bypassed AgentManager or Qt signals."""
    findings: list[str] = []
    checked = 0
    for phase in phases:
        phase_name = str(phase.get("phase") or "")
        if not phase_name.startswith("assistant_"):
            continue
        checked += 1
        notes_value = phase.get("notes")
        notes = notes_value if isinstance(notes_value, dict) else {}
        path_value = notes.get("assistant_signal_path", {})
        path = path_value if isinstance(path_value, dict) else {}
        if (
            notes.get("evidence_scope") != "agent_manager_qt_signal_product_evidence"
            or not bool(path.get("manager_path"))
            or not bool(path.get("qt_signal_path"))
            or bool(path.get("direct_chat_controller_injection", True))
        ):
            findings.append(
                f"{phase_name} used direct or unverified chat injection instead of "
                "AgentManager Qt signals"
            )
    if checked == 0:
        findings.append("assistant signal-path review found no assistant phases")
    return {
        "passed": checked > 0 and not findings,
        "checked_phases": checked,
        "findings": findings,
    }


def build_assistant_notice_contract_review(
    phases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Require runtime failure notice ownership and clear terminal UI states."""
    findings: list[str] = []
    checked = 0
    notice_free_phases = {
        "assistant_runtime_recovery_loading",
        "assistant_runtime_ready",
        "assistant_idle_after_stop",
        "assistant_blocked_command",
        "assistant_successful_tool_result",
        "assistant_sanitized_error",
    }
    for phase in phases:
        phase_name = str(phase.get("phase") or "")
        if not phase_name.startswith("assistant_"):
            continue
        notice = (phase.get("notes") or {}).get("assistant_notice", {})
        if not isinstance(notice, dict):
            findings.append(f"{phase_name} is missing assistant notice evidence")
            continue
        checked += 1
        if bool(notice.get("duplicate_with_transcript")):
            findings.append(f"{phase_name} duplicates a transcript message in a notice")
        if phase_name == "assistant_runtime_failed":
            if not bool(notice.get("visible")):
                findings.append(
                    "assistant_runtime_failed is missing its runtime-owned notice"
                )
            elif notice.get("owner") != "runtime":
                findings.append(
                    "assistant_runtime_failed notice is not owned by the runtime"
                )
        elif phase_name in notice_free_phases and bool(notice.get("visible")):
            findings.append(f"{phase_name} leaves a stale notice visible")
    if checked == 0:
        findings.append("assistant notice review found no assistant phases")
    return {
        "passed": checked > 0 and not findings,
        "checked_phases": checked,
        "findings": findings,
    }


def build_assistant_dock_contract_review(
    phases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Require every assistant phase to show a complete, non-overflowing dock."""
    findings: list[str] = []
    evidence: dict[str, Any] = {"phases": {}}
    checked = 0
    for phase in phases:
        phase_name = str(phase.get("phase") or "")
        if not phase_name.startswith("assistant_"):
            continue
        checked += 1
        dock = (phase.get("notes") or {}).get("assistant_dock", {})
        dock = dock if isinstance(dock, dict) else {}
        evidence["phases"][phase_name] = dock
        if dock.get("capture_target") != "full_dock":
            findings.append(f"{phase_name} did not capture the full dock")
        width = _geometry_int(dock, "dock_width")
        if (
            phase_name == "assistant_narrow_panel"
            and width != ASSISTANT_NARROW_DOCK_WIDTH
        ):
            findings.append(f"{phase_name} is not a 320px narrow dock: {width}px")
        elif (
            phase_name != "assistant_narrow_panel"
            and width != ASSISTANT_STANDARD_DOCK_WIDTH
        ):
            findings.append(f"{phase_name} is not a 420px standard dock: {width}px")
        if not bool(dock.get("title_bar_visible")):
            findings.append(f"{phase_name} does not include the visible dock title bar")
        if dock.get("title_text") != "XBrainLab Assistant" or not bool(
            dock.get("title_text_fits")
        ):
            findings.append(f"{phase_name} dock title text does not fit")
        if not bool(dock.get("title_bar_inside_bounds")) or not bool(
            dock.get("panel_inside_bounds")
        ):
            findings.append(f"{phase_name} dock content overflows its outer bounds")
        if _geometry_int(dock, "horizontal_scrollbar_max") > 0:
            findings.append(f"{phase_name} exposes horizontal assistant scrolling")
        overflowing = list(dock.get("overflowing_widgets", []) or [])
        if overflowing:
            findings.append(
                f"{phase_name} has overflowing widgets: {', '.join(map(str, overflowing))}"
            )
        transcript_message_count = int(dock.get("transcript_message_count", 0) or 0)
        empty_state_visible = bool(dock.get("empty_state_visible"))
        if transcript_message_count > 0 and empty_state_visible:
            findings.append(
                f"{phase_name} shows the assistant empty state beside an active transcript"
            )
        if phase_name == "assistant_empty_state" and (
            not empty_state_visible or transcript_message_count != 0
        ):
            findings.append(
                "assistant_empty_state does not exclusively show the empty-state surface"
            )
        runtime = (phase.get("notes") or {}).get("assistant_runtime", {})
        runtime = runtime if isinstance(runtime, dict) else {}
        runtime_phase = str(runtime.get("phase") or "")
        runtime_geometry = dock.get("runtime_state", {})
        runtime_geometry = (
            runtime_geometry if isinstance(runtime_geometry, dict) else {}
        )
        if runtime_phase and runtime_phase != "ready":
            if (
                not bool(runtime_geometry.get("visible"))
                or not bool(runtime_geometry.get("inside_content"))
                or not bool(runtime_geometry.get("inside_bounds"))
            ):
                findings.append(
                    f"{phase_name} inline runtime state is outside conversation content"
                )
        if runtime_phase in {"idle", "failed"}:
            action = dock.get("setup_action", {})
            action = action if isinstance(action, dict) else {}
            expected_action_text = (
                "Settings" if runtime_phase == "failed" else "Open Assistant Settings"
            )
            if (
                action.get("text") != expected_action_text
                or not bool(action.get("visible"))
                or not bool(action.get("enabled"))
                or not bool(action.get("inside_runtime_actions"))
                or not bool(action.get("inside_bounds"))
                or not bool(action.get("fits_width"))
            ):
                findings.append(f"{phase_name} settings action does not fit its dock")
            retry = dock.get("retry_action", {})
            retry = retry if isinstance(retry, dict) else {}
            retry_expected = runtime_phase == "failed"
            if (
                bool(retry.get("visible")) != retry_expected
                or bool(retry.get("enabled")) != retry_expected
                or (
                    retry_expected
                    and (
                        retry.get("text") != "Retry local assistant"
                        or not bool(retry.get("inside_runtime_actions"))
                        or not bool(retry.get("inside_bounds"))
                        or not bool(retry.get("fits_width"))
                    )
                )
            ):
                findings.append(f"{phase_name} retry action does not fit its dock")
    if checked == 0:
        findings.append("assistant dock review found no assistant phases")
    by_name = evidence["phases"]
    evidence["standard"] = by_name.get("assistant_empty_state", {})
    evidence["narrow"] = by_name.get("assistant_narrow_panel", {})
    return {
        "passed": checked > 0 and not findings,
        "checked_phases": checked,
        "findings": findings,
        "evidence": evidence,
    }


def build_assistant_full_window_contract_review(
    phases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Require full-product-window evidence for every critical assistant state."""
    expected_status = {
        "assistant_runtime_idle": "unavailable",
        "assistant_runtime_loading": "loading",
        "assistant_runtime_failed": "failed",
        "assistant_runtime_ready": "ready",
        "assistant_blocked_command": "blocked",
        "assistant_narrow_panel": "ready",
        "assistant_existing_ui_handoff": "opened",
    }
    findings: list[str] = []
    evidence: dict[str, Any] = {}
    checked = 0
    for (
        phase_name,
        screenshot_key,
    ) in ASSISTANT_REQUIRED_FULL_WINDOW_SCREENSHOTS.items():
        matches = [phase for phase in phases if phase.get("phase") == phase_name]
        if len(matches) != 1:
            findings.append(f"{phase_name} requires one full-window assistant phase")
            continue
        checked += 1
        notes = matches[0].get("notes", {})
        notes = notes if isinstance(notes, dict) else {}
        state = notes.get("assistant_main_window", {})
        state = state if isinstance(state, dict) else {}
        evidence[phase_name] = state
        if (
            state.get("capture_target") != "full_main_window"
            or state.get("screenshot_key") != screenshot_key
            or not str(state.get("screenshot") or "")
        ):
            findings.append(
                f"{phase_name} is missing its full-window screenshot evidence"
            )
        if state.get("state") != phase_name:
            findings.append(f"{phase_name} records the wrong full-window state")
        if state.get("workflow_status") != expected_status[phase_name]:
            findings.append(
                f"{phase_name} records the wrong workflow status: "
                f"{state.get('workflow_status')!r}"
            )
        if (
            not bool(state.get("main_window_visible"))
            or int(state.get("window_width", 0) or 0) <= 0
            or int(state.get("window_height", 0) or 0) <= 0
            or not bool(state.get("dock_visible"))
            or bool(state.get("dock_floating"))
            or not bool(state.get("dock_inside_window"))
        ):
            findings.append(f"{phase_name} assistant dock is outside the main window")
        if state.get("title_text") != "XBrainLab Assistant" or not bool(
            state.get("title_text_fits")
        ):
            findings.append(f"{phase_name} full-window assistant title does not fit")
        if (
            not bool(state.get("composer_visible"))
            or not bool(state.get("composer_inside_window"))
            or not bool(state.get("composer_inside_dock"))
        ):
            findings.append(f"{phase_name} full-window composer is not readable")
        if (
            state.get("primary_action_text") not in {"Send", "Stop"}
            or not bool(state.get("primary_action_visible"))
            or not bool(state.get("primary_action_inside_window"))
            or not bool(state.get("primary_action_inside_dock"))
        ):
            findings.append(f"{phase_name} full-window primary action is not readable")
        if (
            not bool(state.get("main_content_visible"))
            or not bool(state.get("main_content_inside_window"))
            or (
                int(state.get("main_navigation_visible_count", 0) or 0) <= 0
                and not bool(state.get("compact_navigation_visible"))
            )
        ):
            findings.append(f"{phase_name} does not show the complete main product UI")
        nav_outside = [
            str(item) for item in state.get("main_navigation_outside_window", []) or []
        ]
        if nav_outside:
            findings.append(
                f"{phase_name} has navigation outside the full window: "
                f"{', '.join(nav_outside)}"
            )
        nav_overflow = [
            str(item) for item in state.get("main_navigation_text_overflow", []) or []
        ]
        if nav_overflow:
            findings.append(
                f"{phase_name} has clipped main navigation text: "
                f"{', '.join(nav_overflow)}"
            )
        if bool(state.get("compact_navigation_visible")) and (
            not bool(state.get("compact_navigation_inside_window"))
            or not bool(state.get("compact_navigation_text_fits"))
            or not str(state.get("compact_navigation_text") or "").strip()
        ):
            findings.append(
                f"{phase_name} has an unreadable compact navigation selector"
            )
        out_of_window = [
            str(item) for item in state.get("out_of_window_widgets", []) or []
        ]
        if out_of_window:
            findings.append(
                f"{phase_name} has widgets outside the full window: "
                f"{', '.join(out_of_window)}"
            )
        overlaps = [str(item) for item in state.get("overlapping_widgets", []) or []]
        if overlaps:
            findings.append(
                f"{phase_name} has overlapping full-window widgets: "
                f"{', '.join(overlaps)}"
            )
        if not bool(state.get("geometry_passed")):
            findings.append(f"{phase_name} full-window geometry did not pass")
        if phase_name == "assistant_narrow_panel":
            plot = state.get("evaluation_plot_readability", {})
            plot = plot if isinstance(plot, dict) else {}
            if not bool(plot.get("available")) or not bool(plot.get("fully_visible")):
                overlap = ", ".join(
                    str(item) for item in plot.get("overlapping_x_ticks", []) or []
                )
                clipped = ", ".join(
                    str(item) for item in plot.get("clipped_labels", []) or []
                )
                detail = overlap or clipped
                findings.append(
                    f"{phase_name} narrow Evaluation plot is unreadable"
                    + (f": {detail}" if detail else "")
                )
    return {
        "passed": checked == len(ASSISTANT_REQUIRED_FULL_WINDOW_SCREENSHOTS)
        and not findings,
        "checked_phases": checked,
        "findings": findings,
        "evidence": evidence,
    }


def build_assistant_error_contract_review(
    phases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Require a raw-error injection whose visible result is sanitized."""
    matches = [
        phase for phase in phases if phase.get("phase") == "assistant_sanitized_error"
    ]
    findings: list[str] = []
    if len(matches) != 1:
        findings.append("assistant error contract requires one sanitized-error phase")
        return {"passed": False, "findings": findings, "evidence": {}}
    evidence = (matches[0].get("notes") or {}).get("assistant_error", {})
    if not bool(evidence.get("raw_error_injected")):
        findings.append("assistant sanitized-error phase did not inject a raw error")
    if bool(evidence.get("raw_error_visible")):
        findings.append("assistant sanitized-error phase exposed a raw traceback")
    if not bool(evidence.get("sanitized_message_visible")):
        findings.append("assistant sanitized-error phase lacks an actionable message")
    return {"passed": not findings, "findings": findings, "evidence": evidence}


def build_assistant_claim_contract_review(
    phases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare visible assistant success claims with the recorded backend state."""
    matches = [
        phase
        for phase in phases
        if phase.get("phase") == "assistant_successful_tool_result"
    ]
    findings: list[str] = []
    if len(matches) != 1:
        findings.append("assistant claim contract requires one state-result phase")
        return {"passed": False, "findings": findings, "evidence": {}}

    phase = matches[0]
    notes_value = phase.get("notes")
    notes = notes_value if isinstance(notes_value, dict) else {}
    evidence = notes.get("assistant_claims", {})
    evidence = evidence if isinstance(evidence, dict) else {}
    command = evidence.get("command_result", {})
    command = command if isinstance(command, dict) else {}
    claims = [str(item) for item in evidence.get("claims", [])]
    response_text = str(evidence.get("response_text") or "")
    lowered = response_text.lower()
    success_markers = ("complete", "finished", "available", "ready", "success")

    if not bool(command.get("ok")):
        findings.append("assistant state query failed; success phase cannot pass")
        if claims or any(marker in lowered for marker in success_markers):
            findings.append("failed assistant command rendered success language")

    state = phase.get("workflow_state", {})
    state = state if isinstance(state, dict) else {}
    training = state.get("training", {})
    evaluation = state.get("evaluation", {})
    visualization = state.get("visualization", {})
    supported = {
        "training_complete": isinstance(training, dict)
        and int(training.get("finished_run_count", 0) or 0) > 0,
        "evaluation_available": isinstance(evaluation, dict)
        and bool(evaluation.get("available", False)),
        "visualization_available": isinstance(visualization, dict)
        and bool(
            visualization.get("available", False)
            or visualization.get("saliency_available", False)
            or visualization.get("montage_available", False)
        ),
    }
    for claim in claims:
        if claim not in supported:
            findings.append(f"assistant recorded unknown claim: {claim}")
        elif not supported[claim]:
            findings.append(
                f"assistant claim is not supported by backend state: {claim}"
            )

    copy_claims = {
        "training_complete": "training" in lowered
        and ("finished" in lowered or "complete" in lowered),
        "evaluation_available": "evaluation" in lowered
        and ("available" in lowered or "ready" in lowered),
        "visualization_available": "visualization" in lowered
        and ("available" in lowered or "ready" in lowered),
    }
    for claim, present in copy_claims.items():
        if present and claim not in claims:
            findings.append(f"assistant copy lacks structured claim evidence: {claim}")

    return {
        "passed": not findings,
        "findings": findings,
        "evidence": {
            "command_result": dict(command),
            "claims": claims,
            "supported": supported,
            "response_text": response_text,
        },
    }


def build_assistant_interaction_contract_review(
    phases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Require isolated confirmation and typed main-window handoff evidence."""
    expected = {
        "assistant_confirmation_cancelled": (
            "production_confirmation_card",
            "cancelled",
            0,
            2,
        ),
        "assistant_confirmation_confirmed": (
            "production_confirmation_card",
            "confirmed",
            1,
            2,
        ),
        "assistant_existing_ui_handoff": (
            "typed_workflow_ui_handoff",
            "opened_in_main_window",
            0,
            2,
        ),
    }
    findings: list[str] = []
    evidence: dict[str, Any] = {}
    checked = 0
    for phase_name, (
        request_kind,
        decision,
        execution_count,
        scenario_message_count,
    ) in expected.items():
        matches = [phase for phase in phases if phase.get("phase") == phase_name]
        if len(matches) != 1:
            findings.append(f"assistant interaction contract requires one {phase_name}")
            continue
        checked += 1
        interaction = (matches[0].get("notes") or {}).get("assistant_interaction", {})
        interaction = interaction if isinstance(interaction, dict) else {}
        evidence[phase_name] = interaction
        if interaction.get("request_kind") != request_kind:
            findings.append(f"{phase_name} did not use {request_kind} routing")
        if interaction.get("decision") != decision:
            findings.append(f"{phase_name} did not record {decision}")
        if request_kind == "production_confirmation_card" and (
            not bool(interaction.get("card_opened"))
            or interaction.get("card_title") != "High-risk confirmation"
            or not bool(interaction.get("request_correlated"))
            or not str(interaction.get("card_request_id") or "")
        ):
            findings.append(
                f"{phase_name} did not use one correlated inline confirmation card"
            )
        if request_kind == "production_confirmation_card" and not bool(
            interaction.get("destructive")
        ):
            findings.append(f"{phase_name} did not mark the reset as destructive")
        if request_kind == "production_confirmation_card":
            waiting = interaction.get("waiting_surface", {})
            waiting = waiting if isinstance(waiting, dict) else {}
            waiting_activity = waiting.get("turn_activity", {})
            waiting_activity = (
                waiting_activity if isinstance(waiting_activity, dict) else {}
            )
            waiting_button = waiting.get("stop_button", {})
            waiting_button = waiting_button if isinstance(waiting_button, dict) else {}
            cancelability = waiting_activity.get("cancelability_text", {})
            cancelability = cancelability if isinstance(cancelability, dict) else {}
            if (
                waiting.get("header_status") != "Local · Waiting"
                or waiting_activity.get("phase") != "waiting"
                or waiting_button.get("text") != "Waiting"
                or bool(waiting_button.get("enabled"))
                or bool(waiting.get("composer_input_enabled", True))
                or cancelability.get("text")
                != "Use the confirmation card to continue or cancel."
            ):
                findings.append(
                    f"{phase_name} presents a pending decision as active work"
                )
        if request_kind == "typed_workflow_ui_handoff":
            if (
                interaction.get("handoff_kind") != "decision_required"
                or interaction.get("command_name") != "evaluate"
                or not bool(interaction.get("typed_handoff_emitted"))
                or not bool(interaction.get("typed_resolution_accepted"))
            ):
                findings.append(
                    f"{phase_name} did not emit the typed Evaluation handoff"
                )
            request_id = str(interaction.get("request_id") or "")
            decision_fields = tuple(interaction.get("decision_fields", []) or [])
            resolution_fields = tuple(
                interaction.get("resolution_decision_fields", []) or []
            )
            if (
                not request_id
                or interaction.get("resolution_request_id") != request_id
                or interaction.get("resolution_command_name") != "evaluate"
                or interaction.get("resolution_status") != "deferred_to_ui"
                or decision_fields != ("evaluation_result",)
                or resolution_fields != decision_fields
                or not bool(interaction.get("request_resolution_correlated"))
            ):
                findings.append(
                    f"{phase_name} did not preserve typed request/resolution correlation"
                )
            handoff = interaction.get("main_window_handoff", {})
            handoff = handoff if isinstance(handoff, dict) else {}
            if (
                handoff.get("capture_target") != "full_main_window"
                or not bool(handoff.get("main_window_visible"))
                or handoff.get("active_panel") != "Evaluation"
                or int(handoff.get("active_index", -1))
                != int(handoff.get("evaluation_index", -2))
                or not bool(handoff.get("evaluation_nav_checked"))
                or not bool(handoff.get("active_page_visible"))
                or not bool(handoff.get("assistant_dock_visible"))
                or handoff.get("workflow_status") != "opened"
                or not bool(handoff.get("workflow_opened"))
            ):
                findings.append(
                    f"{phase_name} does not prove a full-window active Evaluation view"
                )
            plot = handoff.get("evaluation_plot_readability", {})
            plot = plot if isinstance(plot, dict) else {}
            if not bool(plot.get("available")) or not bool(plot.get("fully_visible")):
                clipped = ", ".join(
                    str(item) for item in plot.get("clipped_labels", [])
                )
                findings.append(
                    "assistant_existing_ui_handoff hard gate: Evaluation "
                    "confusion-matrix labels or responsive layout are unreadable"
                    + (f" ({clipped})" if clipped else "")
                )
            expected_copy = {
                "cancelled": (
                    "Evaluation review was cancelled. "
                    "Your current workflow is unchanged."
                ),
                "completed": "Evaluation review is ready in XBrainLab.",
                "failed": (
                    "XBrainLab could not open Evaluation. "
                    "Try again from the main window."
                ),
            }
            product_copy = interaction.get("product_copy", {})
            product_copy = product_copy if isinstance(product_copy, dict) else {}
            for outcome, expected_text in expected_copy.items():
                if product_copy.get(outcome) != expected_text:
                    findings.append(
                        "assistant_existing_ui_handoff has unpolished "
                        f"{outcome} product copy: {product_copy.get(outcome)!r}"
                    )
        terminal = [str(item) for item in interaction.get("terminal_messages", [])]
        if len(terminal) != 1:
            findings.append(f"{phase_name} must have one terminal message")
        if bool(interaction.get("duplicate_terminal_message")):
            findings.append(f"{phase_name} contains a duplicate terminal message")
        if (
            int(interaction.get("confirmed_execution_count", -1) or 0)
            != execution_count
        ):
            findings.append(
                f"{phase_name} recorded the wrong confirmed execution count"
            )
        if (
            int(interaction.get("scenario_start_message_count", -1)) != 0
            or int(interaction.get("scenario_message_count", -1))
            != scenario_message_count
            or not bool(interaction.get("scenario_isolated"))
        ):
            findings.append(f"{phase_name} is not an isolated assistant scenario")
        if phase_name == "assistant_confirmation_cancelled":
            cancel_text = " ".join(terminal)
            if cancel_text != (
                "Session reset cancelled. Your current workflow is unchanged."
            ):
                findings.append("cancelled confirmation lacks the session reset result")
            if any(
                marker in cancel_text
                for marker in ("background action completed", "success", "ready")
            ):
                findings.append(
                    "cancelled confirmation rendered later success language"
                )
        if phase_name == "assistant_confirmation_confirmed" and terminal != [
            ASSISTANT_CONFIRMED_TERMINAL_MESSAGE
        ]:
            findings.append("confirmed reset lacks one clear terminal result")
        if phase_name == "assistant_existing_ui_handoff" and terminal != [
            "Evaluation is open in the main window. Review results there."
        ]:
            findings.append("Evaluation handoff lacks main-window guidance")

    return {
        "passed": checked == len(expected) and not findings,
        "checked_phases": checked,
        "findings": findings,
        "evidence": evidence,
    }


def build_assistant_settings_recovery_review(
    phases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Require a real settings save between failed and ready runtime states."""
    ready = [
        phase for phase in phases if phase.get("phase") == "assistant_runtime_ready"
    ]
    findings: list[str] = []
    if len(ready) != 1:
        findings.append("assistant settings recovery requires one ready phase")
        return {"passed": False, "findings": findings, "evidence": {}}
    evidence = (ready[0].get("notes") or {}).get("assistant_settings_recovery", {})
    evidence = evidence if isinstance(evidence, dict) else {}
    for key, label in (
        ("open_settings_clicked", "Open Assistant Settings click"),
        ("dialog_opened", "real settings dialog open"),
        ("activate_clicked", "settings Activate click"),
        ("save_observed", "settings save"),
        ("isolated_config", "isolated settings config"),
        ("host_config_unchanged", "host config restoration"),
    ):
        if not bool(evidence.get(key)):
            findings.append(f"assistant recovery lacks {label} evidence")
    if evidence.get("dialog_title") != "Assistant Settings":
        findings.append("assistant recovery did not open the real settings dialog")
    if evidence.get("selected_model") != PRIMARY_LOCAL_MODEL_ID:
        findings.append(
            "assistant recovery did not capture the primary local model "
            f"{PRIMARY_LOCAL_MODEL_ID}"
        )
    if list(evidence.get("runtime_sequence", [])) != [
        "failed",
        "loading",
        "ready",
    ]:
        findings.append("assistant recovery did not observe failed -> loading -> ready")
    if not str(evidence.get("settings_screenshot") or ""):
        findings.append("assistant recovery is missing the settings dialog screenshot")
    return {"passed": not findings, "findings": findings, "evidence": evidence}


def build_assistant_stage_copy_review(
    phases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Require stage-aware headings plus workflow-grounded status copy."""
    rows: list[dict[str, Any]] = []
    for phase in phases:
        if phase.get("phase") != "assistant_empty_state":
            continue
        workflow_state = phase.get("workflow_state", {})
        if not isinstance(workflow_state, dict):
            continue
        evaluation = workflow_state.get("evaluation", {})
        training = workflow_state.get("training", {})
        raw = workflow_state.get("raw", {})
        expected_heading = None
        expected_intro = None
        if isinstance(evaluation, dict) and (
            int(evaluation.get("finished_runs", 0) or 0) > 0
            or bool(evaluation.get("metrics_available", False))
        ):
            expected_heading = "Explore your results"
            expected_intro = (
                "Ask me to explain metrics, review available analyses, or recommend "
                "what to inspect next."
            )
        elif isinstance(training, dict) and bool(training.get("is_running", False)):
            expected_heading = "Training is running"
            expected_intro = "Ask for progress or stop the current training run."
        elif isinstance(raw, dict) and not bool(raw.get("loaded", False)):
            expected_heading = "Start with your EEG data"
            expected_intro = (
                "Ask me to find EEG files, explain supported formats, or begin an "
                "import."
            )
        if expected_heading is None or expected_intro is None:
            continue
        visible_text = [str(item) for item in phase.get("visible_text", [])]
        rows.append(
            {
                "phase": phase.get("phase"),
                "expected_heading": expected_heading,
                "expected_intro": expected_intro,
                "matched": (
                    expected_heading in visible_text and expected_intro in visible_text
                ),
            }
        )
    findings = [row for row in rows if not row["matched"]]
    return {
        "passed": bool(rows) and not findings,
        "checked_states": len(rows),
        "findings": findings,
    }


def build_chat_geometry_review(phases: list[dict[str, Any]]) -> dict[str, Any]:
    """Check ChatPanel evidence for latest-message clipping near the composer."""
    rows: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for phase in phases:
        phase_name = str(phase.get("phase", ""))
        notes = phase.get("notes", {})
        if not isinstance(notes, dict):
            continue
        state = notes.get("chat_geometry")
        if not isinstance(state, dict):
            continue
        row = {
            "phase": phase_name,
            "visible_bubble_count": _geometry_int(state, "visible_bubble_count"),
            "latest_message_bottom_y": _geometry_int(
                state,
                "latest_message_bottom_y",
            ),
            "composer_top_y": _geometry_int(state, "composer_top_y"),
            "bottom_clearance_px": _geometry_int(state, "bottom_clearance_px"),
            "scrollbar_value": _geometry_int(state, "scrollbar_value"),
            "scrollbar_max": _geometry_int(state, "scrollbar_max"),
            "latest_message_clear_of_composer": bool(
                state.get("latest_message_clear_of_composer")
            ),
            "scrollbar_at_bottom": bool(state.get("scrollbar_at_bottom")),
        }
        rows.append(row)
        if not row["latest_message_clear_of_composer"]:
            findings.append(row)
    return {
        "passed": not findings,
        "checked_widgets": len(rows),
        "findings": findings,
        "boundary": (
            "Automated ChatPanel geometry checks whether the latest visible bubble "
            "is clear of the composer. Human review still checks typography and "
            "visual comfort."
        ),
    }


def _geometry_int(state: dict[str, Any], key: str) -> int:
    try:
        return int(state.get(key, 0))
    except (TypeError, ValueError):
        return 0
