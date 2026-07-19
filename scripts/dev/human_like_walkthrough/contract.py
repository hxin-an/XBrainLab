"""Stable assistant artifact contract and deterministic replay inputs."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from XBrainLab.product_language import ASSISTANT_CANCELLED_MESSAGE

ROOT = Path(__file__).resolve().parents[3]

ASSISTANT_EVIDENCE_CONTRACT_VERSION = 13
ASSISTANT_STANDARD_DOCK_WIDTH = 420
ASSISTANT_NARROW_DOCK_WIDTH = 320

ASSISTANT_NORMAL_REQUEST = "Hello."
ASSISTANT_PROCESSING_REQUEST = "Check the workflow."
ASSISTANT_CLARIFICATION_REQUEST = "List files."
ASSISTANT_BLOCKED_REQUEST = "Import another dataset now."
ASSISTANT_SUCCESS_REQUEST = "What is ready now?"
ASSISTANT_ERROR_REQUEST = "Show a runtime error."
ASSISTANT_RECOVERY_REQUEST = "Preview the selected data again."
ASSISTANT_CANCEL_CONFIRMATION_REQUEST = "Cancel the proposed session reset."
ASSISTANT_CONFIRM_CONFIRMATION_REQUEST = "Confirm the proposed session reset."
ASSISTANT_EXISTING_UI_REQUEST = "Continue evaluation in the existing app view."
ASSISTANT_HANDOFF_REQUEST_ID = "walkthrough-evaluate-001"
ASSISTANT_STOPPED_MESSAGE = ASSISTANT_CANCELLED_MESSAGE
ASSISTANT_PATH_CLARIFICATION_MESSAGE = (
    "I need a folder path before I can list files. Choose a folder in the app "
    "or paste the path here."
)
ASSISTANT_CONFIRMED_TERMINAL_MESSAGE = "New session started."
ASSISTANT_RAW_TRACEBACK = (
    "Traceback (most recent call last): File /tmp/walkthrough_agent.py, line 7, "
    "in run RuntimeError: deterministic runtime failure"
)

ASSISTANT_SCREENSHOT_NAMES: dict[str, str] = {
    "assistant_idle_setup": "11z-assistant-setup-required.png",
    "assistant_empty": "12-assistant-empty.png",
    "assistant_loading": "12a-assistant-loading.png",
    "assistant_failed": "12b-assistant-failed.png",
    "assistant_settings": "12b1-assistant-settings.png",
    "assistant_recovery_loading": "12b2-assistant-recovery-loading.png",
    "assistant_ready": "12c-assistant-ready.png",
    "assistant_normal": "13-assistant-normal.png",
    "assistant_processing": "13a-assistant-processing.png",
    "assistant_idle": "13b-assistant-idle.png",
    "assistant_clarification": "14-assistant-clarification.png",
    "assistant_blocked": "15-assistant-blocked.png",
    "assistant_success": "16-assistant-success.png",
    "assistant_error": "16a-assistant-error.png",
    "assistant_cancelled": "16b-assistant-cancelled.png",
    "assistant_confirmation_dialog": "16b1-assistant-confirmation-dialog.png",
    "assistant_confirmed": "16c-assistant-confirmed.png",
    "assistant_handoff": "16d-assistant-existing-ui-handoff.png",
    "assistant_narrow": "17-assistant-narrow.png",
    "assistant_idle_setup_full_window": (
        "11z1-assistant-setup-required-full-window.png"
    ),
    "assistant_loading_full_window": "12a1-assistant-loading-full-window.png",
    "assistant_failed_full_window": "12b1-assistant-failed-full-window.png",
    "assistant_ready_full_window": "12c1-assistant-ready-full-window.png",
    "assistant_blocked_full_window": "15a-assistant-blocked-full-window.png",
    "assistant_narrow_full_window": "17a-assistant-narrow-full-window.png",
}

ASSISTANT_REQUIRED_FULL_WINDOW_SCREENSHOTS: dict[str, str] = {
    "assistant_runtime_idle": "assistant_idle_setup_full_window",
    "assistant_runtime_loading": "assistant_loading_full_window",
    "assistant_runtime_failed": "assistant_failed_full_window",
    "assistant_runtime_ready": "assistant_ready_full_window",
    "assistant_blocked_command": "assistant_blocked_full_window",
    "assistant_narrow_panel": "assistant_narrow_full_window",
    "assistant_existing_ui_handoff": "assistant_handoff",
}

ASSISTANT_REQUIRED_PHASES = (
    "assistant_runtime_idle",
    "assistant_empty_state",
    "assistant_runtime_loading",
    "assistant_runtime_failed",
    "assistant_runtime_recovery_loading",
    "assistant_runtime_ready",
    "assistant_normal_message",
    "assistant_processing_state",
    "assistant_idle_after_stop",
    "assistant_missing_input_clarification",
    "assistant_blocked_command",
    "assistant_successful_tool_result",
    "assistant_sanitized_error",
    "assistant_confirmation_cancelled",
    "assistant_confirmation_confirmed",
    "assistant_existing_ui_handoff",
    "assistant_repeated_open_close",
    "assistant_narrow_panel",
)

ASSISTANT_REQUIRED_SCREENSHOTS = tuple(
    dict.fromkeys(
        (
            "assistant_idle_setup",
            "assistant_loading",
            "assistant_failed",
            "assistant_settings",
            "assistant_recovery_loading",
            "assistant_ready",
            "assistant_empty",
            "assistant_processing",
            "assistant_idle",
            "assistant_error",
            "assistant_cancelled",
            "assistant_confirmation_dialog",
            "assistant_confirmed",
            "assistant_handoff",
            "assistant_narrow",
            *ASSISTANT_REQUIRED_FULL_WINDOW_SCREENSHOTS.values(),
        )
    )
)

_ASSISTANT_HELPER_PATHS = (
    Path(__file__).resolve(),
    Path(__file__).with_name("driver.py"),
    Path(__file__).with_name("evidence.py"),
    Path(__file__).with_name("capture.py"),
    Path(__file__).with_name("validation.py"),
)

ASSISTANT_FINGERPRINT_PATHS = (
    ROOT / "scripts/dev/capture_human_like_product_walkthrough.py",
    *_ASSISTANT_HELPER_PATHS,
    ROOT / "XBrainLab/chat_contract.py",
    ROOT / "XBrainLab/backend/controller/chat_controller.py",
    ROOT / "XBrainLab/ui/chat/panel.py",
    ROOT / "XBrainLab/ui/chat/composer.py",
    ROOT / "XBrainLab/ui/chat/message_bubble.py",
    ROOT / "XBrainLab/ui/chat/presentation.py",
    ROOT / "XBrainLab/ui/chat/status_presenter.py",
    ROOT / "XBrainLab/ui/chat/styles.py",
    ROOT / "XBrainLab/ui/chat/turn_state.py",
    ROOT / "XBrainLab/ui/main_window.py",
    ROOT / "XBrainLab/ui/product_language.py",
    ROOT / "XBrainLab/product_language.py",
    ROOT / "XBrainLab/ui/components/agent_manager.py",
    ROOT / "XBrainLab/ui/components/agent_presentation_service.py",
    ROOT / "XBrainLab/ui/components/assistant_command_dispatcher.py",
    ROOT / "XBrainLab/ui/components/assistant_runtime_coordinator.py",
    ROOT / "XBrainLab/ui/components/assistant_runtime_lifecycle.py",
    ROOT / "XBrainLab/ui/components/assistant_status_projection.py",
    ROOT / "XBrainLab/ui/components/workflow_surface_router.py",
    ROOT / "XBrainLab/ui/components/workflow_ui_handoff_host.py",
    ROOT / "XBrainLab/ui/dialogs/model_settings_dialog.py",
    ROOT / "XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py",
    ROOT / "XBrainLab/ui/dialogs/training/model_selection_dialog.py",
    ROOT / "XBrainLab/ui/dialogs/visualization/saliency_setting_dialog.py",
    ROOT / "XBrainLab/ui/panels/training/components.py",
    ROOT / "XBrainLab/ui/panels/training/history_table.py",
    ROOT / "XBrainLab/ui/panels/evaluation/confusion_matrix.py",
    ROOT / "XBrainLab/ui/panels/evaluation/metrics_bar_chart.py",
    ROOT / "XBrainLab/ui/panels/evaluation/metrics_table.py",
    ROOT / "XBrainLab/ui/panels/evaluation/panel.py",
    ROOT / "XBrainLab/ui/panels/visualization/control_sidebar.py",
    ROOT / "XBrainLab/ui/panels/visualization/panel.py",
    ROOT / "XBrainLab/ui/panels/visualization/saliency_views/base_saliency_view.py",
    ROOT / "XBrainLab/ui/panels/visualization/saliency_views/plot_3d_view.py",
    ROOT / "XBrainLab/backend/visualization/base.py",
    ROOT / "XBrainLab/backend/visualization/saliency_3d_engine.py",
    ROOT / "XBrainLab/backend/visualization/saliency_map.py",
    ROOT / "XBrainLab/backend/visualization/saliency_spectrogram_map.py",
    ROOT / "XBrainLab/backend/visualization/saliency_topomap.py",
    ROOT / "XBrainLab/llm/agent/controller.py",
    ROOT / "XBrainLab/llm/agent/assistant_activity.py",
    ROOT / "XBrainLab/llm/agent/execution_policy.py",
    ROOT / "XBrainLab/llm/agent/response_presentation.py",
    ROOT / "XBrainLab/llm/agent/turn.py",
    ROOT / "XBrainLab/llm/agent/runtime_state.py",
    ROOT / "XBrainLab/llm/agent/tool_feedback.py",
    ROOT / "XBrainLab/llm/agent/ui_handoff.py",
)


def walkthrough_source_fingerprint() -> str:
    """Hash the capture contract and assistant sources used by the artifact."""
    digest = hashlib.sha256()
    for path in ASSISTANT_FINGERPRINT_PATHS:
        relative = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path.name
        digest.update(str(relative).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def build_artifact_contract() -> dict[str, Any]:
    """Return the contract that makes stale walkthrough JSON detectable."""
    return {
        "version": ASSISTANT_EVIDENCE_CONTRACT_VERSION,
        "source_fingerprint": walkthrough_source_fingerprint(),
        "assistant_driver": "agent_manager_qt_signals",
        "assistant_capture_target": "full_dock",
        "assistant_state_capture_target": "full_dock_and_full_main_window",
        "minimum_window_capture": {"width": 760, "height": 520},
        "assistant_full_window_phases": list(
            ASSISTANT_REQUIRED_FULL_WINDOW_SCREENSHOTS
        ),
        "assistant_full_window_screenshots": dict(
            ASSISTANT_REQUIRED_FULL_WINDOW_SCREENSHOTS
        ),
        "assistant_handoff_capture_target": "full_main_window",
    }
