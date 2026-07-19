from __future__ import annotations

import inspect
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest
from PIL import Image, ImageDraw
from PyQt6.QtCore import QPoint, QRect, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

import scripts.dev.capture_human_like_product_walkthrough as walkthrough_module
from scripts.dev.capture_data_interpretation_replay import (
    pairing_rows,
    source_event_field_matches,
    tree_rows,
)
from scripts.dev.capture_human_like_product_walkthrough import (
    ASSISTANT_EVIDENCE_CONTRACT_VERSION,
    ASSISTANT_NORMAL_REQUEST,
    ASSISTANT_PROCESSING_REQUEST,
    DEFAULT_OUTPUT_DIR,
    NARROW_WINDOW_SIZE,
    REQUIRED_PHASES,
    SCREENSHOT_NAMES,
    WALKTHROUGH_EVENT_ROWS,
    _assert_assistant_dock_rendered,
    _assert_consecutive_complete_frames,
    _assert_main_navigation_rendered,
    _assert_region_has_no_unpainted_block,
    _assert_right_panels_rendered,
    _assert_step_navigation_rendered,
    _data_import_visual_evidence_failures,
    _grab_widget_to_path,
    _record_capture_source_stability,
    _required_command_payload,
    _run_walkthrough_steps,
    _use_native_window_capture,
    apply_review_choices,
    build_artifact_contract,
    build_assistant_dock_contract_review,
    build_assistant_notice_contract_review,
    build_assistant_processing_contract_review,
    build_assistant_runtime_contract_review,
    build_assistant_signal_path_review,
    build_assistant_stage_copy_review,
    build_chat_geometry_review,
    build_observable_evidence_summary,
    build_pass_fail_summary,
    build_resource_smoke_summary,
    build_ui_quality_review,
    build_workflow_contract_failures,
    capture_named,
    capture_widget,
    chat_panel_geometry,
    claim_boundary,
    dataset_page_geometry,
    drive_assistant_request,
    finalize_walkthrough_after_close,
    forbidden_visible_text,
    install_walkthrough_assistant,
    is_nearly_black,
    merge_ui_quality_into_pass_fail_summary,
    publish_artifact_run,
    render_eval_dashboard_html,
    render_markdown,
    run_chatpanel_walkthrough,
    settle_window_geometry_for_capture,
    validate_walkthrough_payload,
    visible_text_snapshot,
)
from scripts.dev.human_like_walkthrough.contract import (
    ASSISTANT_BLOCKED_REQUEST,
    ASSISTANT_CLARIFICATION_REQUEST,
    ASSISTANT_CONFIRM_CONFIRMATION_REQUEST,
    ASSISTANT_CONFIRMED_TERMINAL_MESSAGE,
    ASSISTANT_EXISTING_UI_REQUEST,
    ASSISTANT_FINGERPRINT_PATHS,
    ASSISTANT_HANDOFF_REQUEST_ID,
    ASSISTANT_PATH_CLARIFICATION_MESSAGE,
    ASSISTANT_REQUIRED_FULL_WINDOW_SCREENSHOTS,
    ASSISTANT_REQUIRED_SCREENSHOTS,
    ASSISTANT_STOPPED_MESSAGE,
)
from scripts.dev.human_like_walkthrough.driver import (
    WalkthroughAssistantController,
    build_state_backed_assistant_response,
)
from scripts.dev.human_like_walkthrough.evidence import (
    _overlapping_x_tick_labels,
    assistant_main_window_evidence,
    assistant_runtime_evidence,
)
from scripts.dev.human_like_walkthrough.validation import (
    build_assistant_claim_contract_review,
    build_assistant_full_window_contract_review,
    build_assistant_interaction_contract_review,
    build_assistant_settings_recovery_review,
)
from XBrainLab.backend.application.commands import CommandName
from XBrainLab.backend.study import Study
from XBrainLab.llm.agent.confirmation import (
    AgentConfirmationRequest,
    AgentConfirmationResolution,
    AgentConfirmationResolutionStatus,
)
from XBrainLab.llm.agent.interaction import (
    AgentInteractionOutcome,
    AgentInteractionStatus,
)
from XBrainLab.llm.agent.response_presentation import (
    AssistantResponseActionKind,
    AssistantResponsePresentation,
)
from XBrainLab.llm.agent.turn import (
    AssistantTurnCorrelation,
    AssistantTurnRequest,
)
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffKind,
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolution,
    WorkflowUiHandoffResolutionStatus,
)
from XBrainLab.ui.chat.message_bubble import MessageBubble
from XBrainLab.ui.components.agent_manager import AgentManager
from XBrainLab.ui.components.info_panel import AggregateInfoPanel
from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
)


def _admit_walkthrough_turn(
    controller: WalkthroughAssistantController,
    text: str,
) -> AssistantTurnRequest:
    request = AssistantTurnRequest(
        correlation=AssistantTurnCorrelation(generation=1, turn_id=1),
        text=text,
    )
    controller.handle_user_turn(request)
    return request


def test_confirmation_walkthrough_targets_custom_button_roles() -> None:
    source = Path("scripts/dev/human_like_walkthrough/capture.py").read_text(
        encoding="utf-8"
    )

    assert "buttonRole" in source
    assert "StandardButton.Yes" not in source
    assert "StandardButton.No" not in source


def test_confirmation_walkthrough_captures_dialog_before_choice() -> None:
    source = Path("scripts/dev/human_like_walkthrough/capture.py").read_text(
        encoding="utf-8"
    )

    capture_index = source.index('screenshots["assistant_confirmation_dialog"]')
    click_index = source.index("click_assistant_control(cast(QWidget, targets[0]))")
    assert capture_index < click_index


def test_rotated_x_tick_overlap_uses_anchor_spacing_not_axis_aligned_bounds() -> None:
    rows = [
        {
            "text": "Left hand",
            "x0": 100.0,
            "x1": 160.0,
            "anchor_x": 130.0,
            "rotation": 45.0,
        },
        {
            "text": "Right hand",
            "x0": 145.0,
            "x1": 215.0,
            "anchor_x": 180.0,
            "rotation": 45.0,
        },
    ]

    assert _overlapping_x_tick_labels(rows) == []

    rows[1]["anchor_x"] = 142.0
    assert _overlapping_x_tick_labels(rows) == ["Left hand / Right hand"]


def test_horizontal_x_ticks_require_visible_spacing() -> None:
    rows = [
        {
            "text": "Left hand",
            "x0": 100.0,
            "x1": 150.0,
            "anchor_x": 125.0,
            "rotation": 0.0,
        },
        {
            "text": "Right hand",
            "x0": 154.0,
            "x1": 214.0,
            "anchor_x": 184.0,
            "rotation": 0.0,
        },
    ]

    assert _overlapping_x_tick_labels(rows) == ["Left hand / Right hand"]


class _SidebarStub(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.info_panel = AggregateInfoPanel(None)


class _DatasetPanelStub(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.table = QTableWidget(1, 1, self)
        self.sidebar = _SidebarStub(self)


class _WindowStub:
    def __init__(self) -> None:
        self.dataset_panel = _DatasetPanelStub()


def _base_payload() -> dict:
    phases = [
        {
            "phase": phase,
            "screenshot": f"{phase}.png",
            "visible_text": ["Clean user-facing text"],
            "button_state": [{"text": "Send", "enabled": True}],
            "workflow_state": {},
            "notes": {},
        }
        for phase in REQUIRED_PHASES
    ]
    processing_phase = next(
        phase for phase in phases if phase["phase"] == "assistant_processing_state"
    )
    processing_phase.update(_valid_assistant_processing_phase())
    idle_phase = next(
        phase for phase in phases if phase["phase"] == "assistant_idle_after_stop"
    )
    idle_phase.update(_valid_assistant_idle_phase())
    runtime_phase = next(
        phase for phase in phases if phase["phase"] == "assistant_runtime_loading"
    )
    runtime_phase.update(_valid_assistant_runtime_phase())
    runtime_idle_phase = next(
        phase for phase in phases if phase["phase"] == "assistant_runtime_idle"
    )
    runtime_idle_phase.update(_valid_assistant_runtime_idle_phase())
    runtime_ready_phase = next(
        phase for phase in phases if phase["phase"] == "assistant_runtime_ready"
    )
    runtime_ready_phase.update(_valid_assistant_runtime_ready_phase())
    runtime_failed_phase = next(
        phase for phase in phases if phase["phase"] == "assistant_runtime_failed"
    )
    runtime_failed_phase.update(_valid_assistant_runtime_failed_phase())
    recovery_loading_phase = next(
        phase
        for phase in phases
        if phase["phase"] == "assistant_runtime_recovery_loading"
    )
    recovery_loading_phase.update(_valid_assistant_runtime_phase())
    recovery_loading_phase["phase"] = "assistant_runtime_recovery_loading"
    recovery_loading_phase["visible_text"] = [
        "Retrying local assistant",
        "Send",
    ]
    recovery_loading_phase["notes"]["assistant_runtime"].update(
        {
            "inline_state_title": "Retrying local assistant",
            "inline_state_detail": (
                "Applying Assistant Settings and retrying the local model."
            ),
            "composer_placeholder": "Retrying local assistant...",
        }
    )
    sanitized_error_phase = next(
        phase for phase in phases if phase["phase"] == "assistant_sanitized_error"
    )
    sanitized_error_phase.update(_valid_assistant_sanitized_error_phase())
    settings_evidence = {
        "open_settings_clicked": True,
        "dialog_opened": True,
        "dialog_title": "AI Assistant Settings",
        "activate_clicked": True,
        "save_observed": True,
        "isolated_config": True,
        "host_config_unchanged": True,
        "runtime_sequence": ["failed", "loading", "ready"],
        "settings_screenshot": "assistant-settings.png",
    }
    runtime_ready_phase["notes"]["assistant_settings_recovery"] = settings_evidence
    success_phase = next(
        phase
        for phase in phases
        if phase["phase"] == "assistant_successful_tool_result"
    )
    success_copy = (
        "Verified from the current workflow: training has finished; "
        "evaluation results are available."
    )
    success_phase["visible_text"] = [success_copy]
    success_phase["workflow_state"] = {
        "training": {"finished_run_count": 1},
        "evaluation": {"available": True},
        "visualization": {"available": False},
    }
    success_phase["notes"] = {
        "assistant_claims": {
            "command_result": {"ok": True, "command": "query_state"},
            "claims": ["training_complete", "evaluation_available"],
            "response_text": success_copy,
        }
    }
    for valid_interaction in _valid_assistant_interaction_phases():
        target = next(
            phase for phase in phases if phase["phase"] == valid_interaction["phase"]
        )
        target.update(valid_interaction)
    for phase in phases:
        if not str(phase["phase"]).startswith("assistant_"):
            continue
        phase.setdefault("notes", {}).update(_valid_assistant_common_notes())
        phase["notes"]["assistant_dock"] = _valid_assistant_dock_evidence(420)
    runtime_failed_phase["notes"]["assistant_notice"] = {
        "visible": True,
        "owner": "runtime",
        "text": "Assistant unavailable: The local model could not start.",
        "duplicate_with_transcript": False,
    }
    failed_dock = runtime_failed_phase["notes"]["assistant_dock"]
    failed_dock["setup_action"]["text"] = "Settings"
    failed_dock["retry_action"].update(
        {
            "text": "Retry local assistant",
            "visible": True,
            "enabled": True,
        }
    )
    empty_phase = next(
        phase for phase in phases if phase["phase"] == "assistant_empty_state"
    )
    empty_phase["notes"]["assistant_dock"] = _valid_assistant_dock_evidence(420)
    narrow_phase = next(
        phase for phase in phases if phase["phase"] == "assistant_narrow_panel"
    )
    narrow_phase["notes"]["assistant_dock"] = _valid_assistant_dock_evidence(320)
    for (
        phase_name,
        screenshot_key,
    ) in ASSISTANT_REQUIRED_FULL_WINDOW_SCREENSHOTS.items():
        phase = next(item for item in phases if item["phase"] == phase_name)
        phase["notes"]["assistant_main_window"] = _valid_assistant_main_window_evidence(
            phase_name, screenshot_key
        )
    narrow_phase["notes"]["assistant_main_window"]["evaluation_plot_readability"] = {
        "available": True,
        "fully_visible": True,
        "clipped_labels": [],
        "overlapping_x_ticks": [],
    }
    phases[0]["notes"] = {
        "ui_geometry": {
            "dataset_table": {
                "header_length": 640,
                "viewport_width": 640,
                "horizontal_scrollbar_max": 0,
                "headers": ["File", "Subject"],
                "rows": [],
            }
        }
    }
    return {
        "status": "passed",
        "failure_reason": "",
        "claim_boundary": (
            "Automated UI-observable PyQt replay; not human Windows desktop acceptance."
        ),
        "artifact_contract": build_artifact_contract(),
        "capture_source": {
            "fingerprint_at_start": build_artifact_contract()["source_fingerprint"],
            "fingerprint_at_completion": build_artifact_contract()[
                "source_fingerprint"
            ],
            "stable": True,
        },
        "source_path": "<walkthrough_source>",
        "recipe_path": "walkthrough-import.recipe.json",
        "phases": phases,
        "screenshots": {
            **{phase: f"{phase}.png" for phase in REQUIRED_PHASES},
            "assistant_processing": "assistant-processing.png",
            "assistant_idle": "assistant-idle.png",
            "assistant_idle_setup": "assistant-setup-required.png",
            "assistant_loading": "assistant-loading.png",
            "assistant_ready": "assistant-ready.png",
            "assistant_failed": "assistant-failed.png",
            "assistant_settings": "assistant-settings.png",
            "assistant_recovery_loading": "assistant-recovery-loading.png",
            "assistant_error": "assistant-error.png",
            "assistant_empty": "assistant-empty.png",
            "assistant_cancelled": "assistant-cancelled.png",
            "assistant_confirmation_dialog": SCREENSHOT_NAMES[
                "assistant_confirmation_dialog"
            ],
            "assistant_confirmed": "assistant-confirmed.png",
            "assistant_handoff": "assistant-handoff.png",
            "assistant_narrow": "assistant-narrow.png",
            **{
                screenshot_key: f"{screenshot_key}.png"
                for screenshot_key in ASSISTANT_REQUIRED_FULL_WINDOW_SCREENSHOTS.values()
            },
        },
        "observable_evidence": build_observable_evidence_summary(phases),
        "tool_transcript": [
            {"command": "query_state", "ok": True, "message": "Ready."}
        ],
        "user_facing_message_transcript": [
            {"role": "assistant", "text": "The dataset is ready."}
        ],
        "resource_notes": [
            {
                "label": "after_close",
                "python_threads": 1,
                "qt_active_threads": 0,
                "max_rss_kb": 123,
            }
        ],
        "pass_fail_summary": {
            "passed": True,
            "failed_checks": [],
            "required_phase_count": len(REQUIRED_PHASES),
            "observed_phase_count": len(REQUIRED_PHASES),
            "screenshot_count": len(REQUIRED_PHASES),
            "human_desktop_acceptance": "not performed",
        },
        "ui_quality_review": {
            "automated_checks_passed": True,
            "phase_snapshot_coverage": True,
            "forbidden_visible_text": [],
            "table_geometry_review": {
                "passed": True,
                "checked_widgets": 1,
                "findings": [],
                "rows": [],
            },
            "assistant_processing_contract_review": {
                "passed": True,
                "checked_phases": 1,
                "findings": [],
            },
            "assistant_runtime_contract_review": {
                "passed": True,
                "findings": [],
                "evidence": {
                    "idle": _valid_assistant_runtime_idle_phase()["notes"][
                        "assistant_runtime"
                    ],
                    "loading": _valid_assistant_runtime_phase()["notes"][
                        "assistant_runtime"
                    ],
                    "recovery": recovery_loading_phase["notes"]["assistant_runtime"],
                    "ready": _valid_assistant_runtime_ready_phase()["notes"][
                        "assistant_runtime"
                    ],
                    "failed": _valid_assistant_runtime_failed_phase()["notes"][
                        "assistant_runtime"
                    ],
                },
            },
            "assistant_dock_contract_review": {"passed": True, "findings": []},
            "assistant_full_window_contract_review": {
                "passed": True,
                "findings": [],
            },
            "assistant_notice_contract_review": {"passed": True, "findings": []},
            "assistant_signal_path_review": {"passed": True, "findings": []},
            "assistant_error_contract_review": {"passed": True, "findings": []},
            "assistant_claim_contract_review": {"passed": True, "findings": []},
            "assistant_interaction_contract_review": {
                "passed": True,
                "findings": [],
            },
            "assistant_settings_recovery_review": {
                "passed": True,
                "findings": [],
            },
            "human_design_review_boundary": "Automated replay only.",
        },
        "elapsed_seconds": 10.0,
    }


def _valid_assistant_processing_phase() -> dict[str, Any]:
    return {
        "phase": "assistant_processing_state",
        "screenshot": "assistant-processing.png",
        "visible_text": [
            "Guided workflow",
            "Preparing your request",
            "Current step: Checking the current EEG workflow",
            "Stop",
        ],
        "button_state": [
            {
                "text": "Guided workflow",
                "enabled": False,
                "checked": True,
            },
            {
                "text": "Stop",
                "enabled": True,
                "checked": None,
            },
        ],
        "workflow_state": {},
        "notes": {
            "assistant_processing": {
                "execution_mode": "multi",
                "runtime_phase": "ready",
                "controller_processing": True,
                "panel_processing": True,
                "composer_input_enabled": False,
                "workflow_mode": {
                    "text": "Guided workflow",
                    "visible": True,
                    "enabled": False,
                    "checked": True,
                },
                "stop_button": {
                    "text": "Stop",
                    "visible": True,
                    "enabled": True,
                    "width": 76,
                    "height": 36,
                },
                "workflow_status": {
                    "text": "Checking data",
                    "visible": True,
                    "text_width": 82,
                    "available_width": 180,
                    "text_height": 16,
                    "available_height": 24,
                    "fits_width": True,
                    "fits_height": True,
                },
                "turn_activity": {
                    "visible": True,
                    "phase": "working",
                    "cancelability": "cancellable",
                    "primary_status": {
                        "text": "Preparing your request",
                        "visible": True,
                        "available_width": 180,
                        "available_height": 24,
                        "required_height": 16,
                        "fits_height": True,
                    },
                    "step": {
                        "text": "Current step: Checking the current EEG workflow",
                        "visible": True,
                        "available_width": 180,
                        "available_height": 36,
                        "required_height": 32,
                        "fits_height": True,
                    },
                },
            },
            "stopping_state": {
                "controller_processing": True,
                "panel_processing": True,
                "stop_button": {
                    "text": "Stopping",
                    "visible": True,
                    "enabled": False,
                },
                "turn_activity": {
                    "phase": "stopping",
                    "cancelability": "stopping",
                },
            },
            "restored_state": {
                "execution_mode": "multi",
                "controller_processing": False,
                "panel_processing": False,
                "composer_input_enabled": True,
                "send_button_text": "Send",
                "workflow_status_visible": False,
                "one_step_checked": False,
                "workflow_checked": True,
            },
        },
    }


def _valid_assistant_idle_phase() -> dict[str, Any]:
    restored = deepcopy(_valid_assistant_processing_phase()["notes"]["restored_state"])
    return {
        "phase": "assistant_idle_after_stop",
        "screenshot": "assistant-idle.png",
        "visible_text": ["Guided workflow", "Send", ASSISTANT_STOPPED_MESSAGE],
        "button_state": [
            {
                "text": "Guided workflow",
                "enabled": True,
                "checked": True,
            },
            {"text": "Send", "enabled": True, "checked": None},
        ],
        "workflow_state": {},
        "notes": {
            "assistant_idle": restored,
            "assistant_cancelled_turn": {
                "terminal_messages": [ASSISTANT_STOPPED_MESSAGE],
            },
        },
    }


def _valid_assistant_runtime_phase() -> dict[str, Any]:
    return {
        "phase": "assistant_runtime_loading",
        "screenshot": "assistant-loading.png",
        "visible_text": ["Loading local assistant", "Send"],
        "button_state": [{"text": "Send", "enabled": False}],
        "workflow_state": {},
        "notes": {
            "assistant_runtime": {
                "phase": "loading",
                "panel_processing": False,
                "composer_input_enabled": False,
                "composer_visible": True,
                "send_button_enabled": False,
                "send_button_text": "Send",
                "composer_placeholder": "Loading assistant...",
                "status_visible": False,
                "status_text": "",
                "inline_state_visible": True,
                "inline_state_location": "content",
                "inline_state_title": "Loading local assistant",
                "inline_state_detail": "Preparing the selected local model.",
                "setup_action_visible": False,
                "setup_action_enabled": True,
                "setup_action_text": "Open Assistant Settings",
            }
        },
    }


def _valid_assistant_runtime_idle_phase() -> dict[str, Any]:
    return {
        "phase": "assistant_runtime_idle",
        "screenshot": "assistant-setup-required.png",
        "visible_text": [
            "Assistant setup required",
            "Open Assistant Settings",
            "Send",
        ],
        "button_state": [
            {"text": "Open Assistant Settings", "enabled": True},
            {"text": "Send", "enabled": False},
        ],
        "workflow_state": {},
        "notes": {
            "assistant_runtime": {
                "phase": "idle",
                "panel_processing": False,
                "composer_input_enabled": False,
                "composer_visible": True,
                "send_button_enabled": False,
                "send_button_text": "Send",
                "composer_placeholder": "Set up assistant",
                "status_visible": False,
                "status_text": "",
                "inline_state_visible": True,
                "inline_state_location": "content",
                "inline_state_title": "Assistant setup required",
                "inline_state_detail": (
                    "Choose a local model before using the assistant."
                ),
                "setup_action_visible": True,
                "setup_action_enabled": True,
                "setup_action_text": "Open Assistant Settings",
                "retry_action_visible": False,
                "retry_action_enabled": False,
                "retry_action_text": "Retry local assistant",
            }
        },
    }


def _valid_assistant_runtime_ready_phase() -> dict[str, Any]:
    return {
        "phase": "assistant_runtime_ready",
        "screenshot": "assistant-ready.png",
        "visible_text": ["Ask about EEG workflow", "Send"],
        "button_state": [{"text": "Send", "enabled": True}],
        "workflow_state": {},
        "notes": {
            "assistant_runtime": {
                "phase": "ready",
                "panel_processing": False,
                "composer_input_enabled": True,
                "composer_visible": True,
                "send_button_enabled": True,
                "send_button_text": "Send",
                "composer_placeholder": "Ask about EEG workflow",
                "status_visible": False,
                "status_text": "",
                "inline_state_visible": False,
                "inline_state_location": "content",
                "inline_state_title": "Loading local assistant",
                "inline_state_detail": "Preparing the selected local model.",
                "setup_action_visible": False,
                "setup_action_enabled": True,
                "setup_action_text": "Open Assistant Settings",
            }
        },
    }


def _valid_assistant_runtime_failed_phase() -> dict[str, Any]:
    return {
        "phase": "assistant_runtime_failed",
        "screenshot": "assistant-failed.png",
        "visible_text": [
            "Assistant unavailable: The local model could not start.",
            "Assistant unavailable",
            "Retry local assistant",
            "Settings",
            "Send",
        ],
        "button_state": [{"text": "Send", "enabled": False}],
        "workflow_state": {},
        "notes": {
            "assistant_runtime": {
                "phase": "failed",
                "panel_processing": False,
                "composer_input_enabled": False,
                "composer_visible": True,
                "send_button_enabled": False,
                "send_button_text": "Send",
                "composer_placeholder": "Assistant unavailable",
                "status_visible": False,
                "status_text": "",
                "inline_state_visible": True,
                "inline_state_location": "content",
                "inline_state_title": "Assistant unavailable",
                "inline_state_detail": (
                    "Assistant unavailable: The local model could not start."
                ),
                "setup_action_visible": True,
                "setup_action_enabled": True,
                "setup_action_text": "Settings",
                "retry_action_visible": True,
                "retry_action_enabled": True,
                "retry_action_text": "Retry local assistant",
            }
        },
    }


def _valid_assistant_sanitized_error_phase() -> dict[str, Any]:
    return {
        "phase": "assistant_sanitized_error",
        "screenshot": "assistant-error.png",
        "visible_text": [
            "Show a runtime error.",
            "Assistant could not complete the request: Try again.",
            "Send",
        ],
        "button_state": [{"text": "Send", "enabled": True}],
        "workflow_state": {},
        "notes": {
            "assistant_error": {
                "raw_error_injected": True,
                "raw_error_visible": False,
                "sanitized_message_visible": True,
            }
        },
    }


def _valid_assistant_common_notes() -> dict[str, Any]:
    return {
        "evidence_scope": "agent_manager_qt_signal_product_evidence",
        "assistant_signal_path": {
            "manager_path": True,
            "qt_signal_path": True,
            "direct_chat_controller_injection": False,
        },
        "assistant_notice": {
            "visible": False,
            "owner": None,
            "text": "",
            "duplicate_with_transcript": False,
        },
    }


def _valid_assistant_dock_evidence(width: int) -> dict[str, Any]:
    return {
        "capture_target": "full_dock",
        "dock_width": width,
        "dock_height": 720,
        "title_bar_visible": True,
        "title_text": "XBrainLab",
        "title_text_fits": True,
        "title_bar_inside_bounds": True,
        "panel_inside_bounds": True,
        "horizontal_scrollbar_max": 0,
        "overflowing_widgets": [],
        "runtime_state": {
            "visible": True,
            "inside_content": True,
            "inside_bounds": True,
        },
        "setup_action": {
            "text": "Open Assistant Settings",
            "visible": True,
            "enabled": True,
            "inside_runtime_actions": True,
            "inside_bounds": True,
            "fits_width": True,
        },
        "retry_action": {
            "text": "Retry local assistant",
            "visible": False,
            "enabled": False,
            "inside_runtime_actions": True,
            "inside_bounds": True,
            "fits_width": True,
        },
    }


def _valid_assistant_main_window_evidence(
    phase_name: str,
    screenshot_key: str,
) -> dict[str, Any]:
    workflow_status = {
        "assistant_runtime_idle": "unavailable",
        "assistant_runtime_loading": "loading",
        "assistant_runtime_failed": "failed",
        "assistant_runtime_ready": "ready",
        "assistant_blocked_command": "blocked",
        "assistant_narrow_panel": "ready",
        "assistant_existing_ui_handoff": "opened",
    }[phase_name]
    return {
        "capture_target": "full_main_window",
        "screenshot_key": screenshot_key,
        "screenshot": f"{screenshot_key}.png",
        "state": phase_name,
        "workflow_status": workflow_status,
        "main_window_visible": True,
        "window_width": 1280,
        "window_height": 800,
        "dock_visible": True,
        "dock_floating": False,
        "dock_inside_window": True,
        "title_text": "XBrainLab",
        "title_text_fits": True,
        "composer_visible": True,
        "composer_inside_window": True,
        "composer_inside_dock": True,
        "primary_action_text": "Send",
        "primary_action_visible": True,
        "primary_action_inside_window": True,
        "primary_action_inside_dock": True,
        "main_content_visible": True,
        "main_content_inside_window": True,
        "main_navigation_visible_count": 5,
        "main_navigation_outside_window": [],
        "main_navigation_text_overflow": [],
        "compact_navigation_visible": False,
        "compact_navigation_text": "",
        "compact_navigation_inside_window": True,
        "compact_navigation_text_fits": True,
        "out_of_window_widgets": [],
        "overlapping_widgets": [],
        "geometry_passed": True,
    }


def test_validate_walkthrough_payload_accepts_complete_artifact_without_files() -> None:
    ok, reason = validate_walkthrough_payload(_base_payload(), require_files=False)

    assert ok is True
    assert reason == ""


def test_assistant_runtime_contract_rejects_send_during_loading() -> None:
    phases = [
        _valid_assistant_runtime_phase(),
        _valid_assistant_runtime_ready_phase(),
        _valid_assistant_runtime_failed_phase(),
    ]
    phases[0]["notes"]["assistant_runtime"]["send_button_enabled"] = True

    review = build_assistant_runtime_contract_review(phases)

    assert review["passed"] is False
    assert "Send remained enabled" in "; ".join(review["findings"])


def test_assistant_runtime_contract_rejects_loading_without_visible_cue() -> None:
    phases = [
        _valid_assistant_runtime_phase(),
        _valid_assistant_runtime_ready_phase(),
        _valid_assistant_runtime_failed_phase(),
    ]
    evidence = phases[0]["notes"]["assistant_runtime"]
    evidence["composer_placeholder"] = ""
    evidence["status_visible"] = False
    evidence["status_text"] = ""
    evidence["inline_state_title"] = ""

    review = build_assistant_runtime_contract_review(phases)

    assert review["passed"] is False
    assert "loading cue" in "; ".join(review["findings"]).lower()


def test_assistant_runtime_contract_requires_loading_ready_and_failed() -> None:
    review = build_assistant_runtime_contract_review(
        [_valid_assistant_runtime_phase(), _valid_assistant_runtime_ready_phase()]
    )

    assert review["passed"] is False
    assert "failed" in "; ".join(review["findings"]).lower()


def test_assistant_runtime_contract_rejects_setup_required_with_stop() -> None:
    idle = {
        "phase": "assistant_runtime_idle",
        "notes": {
            "assistant_runtime": {
                "phase": "idle",
                "panel_processing": True,
                "composer_input_enabled": False,
                "send_button_enabled": True,
                "send_button_text": "Stop",
                "inline_state_visible": True,
                "inline_state_location": "content",
                "inline_state_title": "Assistant setup required",
                "setup_action_visible": True,
                "setup_action_enabled": True,
                "setup_action_text": "Open Assistant Settings",
            }
        },
    }
    phases = [
        idle,
        _valid_assistant_runtime_phase(),
        _valid_assistant_runtime_ready_phase(),
        _valid_assistant_runtime_failed_phase(),
    ]

    review = build_assistant_runtime_contract_review(phases)

    assert review["passed"] is False
    assert "setup-required" in "; ".join(review["findings"]).lower()


def test_assistant_runtime_contract_requires_recovery_action_in_idle_and_failed() -> (
    None
):
    failed = _valid_assistant_runtime_failed_phase()
    failed["notes"]["assistant_runtime"].update(
        {
            "inline_state_visible": True,
            "inline_state_location": "content",
            "inline_state_title": "Assistant unavailable",
            "setup_action_visible": False,
            "setup_action_enabled": True,
            "setup_action_text": "Open Assistant Settings",
            "panel_processing": False,
        }
    )

    review = build_assistant_runtime_contract_review(
        [
            _valid_assistant_runtime_phase(),
            _valid_assistant_runtime_ready_phase(),
            failed,
        ]
    )

    assert review["passed"] is False
    assert "incorrect settings action" in "; ".join(review["findings"])


def test_assistant_runtime_contract_rejects_processing_before_ready() -> None:
    failed = _valid_assistant_runtime_failed_phase()
    failed["notes"]["assistant_runtime"]["panel_processing"] = True

    review = build_assistant_runtime_contract_review(
        [
            _valid_assistant_runtime_phase(),
            _valid_assistant_runtime_ready_phase(),
            failed,
        ]
    )

    assert review["passed"] is False
    assert "processing" in "; ".join(review["findings"]).lower()


def test_assistant_runtime_contract_rejects_stale_failed_copy_during_recovery() -> None:
    recovery = _valid_assistant_runtime_phase()
    recovery["phase"] = "assistant_runtime_recovery_loading"
    recovery["notes"]["assistant_runtime"].update(
        {
            "inline_state_visible": True,
            "inline_state_location": "content",
            "inline_state_title": "Assistant unavailable",
            "inline_state_detail": "Assistant setup required",
            "setup_action_visible": True,
            "panel_processing": False,
        }
    )

    review = build_assistant_runtime_contract_review(
        [
            _valid_assistant_runtime_phase(),
            _valid_assistant_runtime_ready_phase(),
            _valid_assistant_runtime_failed_phase(),
            recovery,
        ]
    )

    assert review["passed"] is False
    assert "recovery" in "; ".join(review["findings"]).lower()


def test_assistant_runtime_contract_rejects_enabled_recovery_composer() -> None:
    recovery = _valid_assistant_runtime_phase()
    recovery["phase"] = "assistant_runtime_recovery_loading"
    recovery["notes"]["assistant_runtime"].update(
        {
            "composer_input_enabled": True,
            "inline_state_title": "Retrying local assistant",
            "inline_state_detail": "Retrying the local model.",
        }
    )

    review = build_assistant_runtime_contract_review(
        [
            _valid_assistant_runtime_idle_phase(),
            _valid_assistant_runtime_phase(),
            recovery,
            _valid_assistant_runtime_ready_phase(),
            _valid_assistant_runtime_failed_phase(),
        ]
    )

    assert review["passed"] is False
    assert "enabled the composer" in "; ".join(review["findings"])


def test_validate_walkthrough_payload_rejects_stale_source_fingerprint() -> None:
    payload = _base_payload()
    payload["artifact_contract"]["source_fingerprint"] = "stale-source"

    ok, reason = validate_walkthrough_payload(payload, require_files=False)

    assert ok is False
    assert "stale" in reason.lower()


def test_capture_source_stability_records_current_source() -> None:
    payload = {
        "status": "passed",
        "failure_reason": "",
        "pass_fail_summary": {"passed": True, "failed_checks": []},
    }

    result = _record_capture_source_stability(
        payload,
        started="current-source",
        completed="current-source",
    )

    assert result["status"] == "passed"
    assert result["capture_source"] == {
        "fingerprint_at_start": "current-source",
        "fingerprint_at_completion": "current-source",
        "stable": True,
    }


def test_capture_source_stability_rejects_source_drift() -> None:
    payload = {
        "status": "passed",
        "failure_reason": "",
        "pass_fail_summary": {"passed": True, "failed_checks": []},
    }

    result = _record_capture_source_stability(
        payload,
        started="before-source",
        completed="after-source",
    )

    assert result["status"] == "failed"
    assert result["capture_source"]["stable"] is False
    assert "discard this run" in result["failure_reason"]
    assert result["pass_fail_summary"]["passed"] is False


def test_validate_walkthrough_payload_rejects_missing_capture_source() -> None:
    payload = _base_payload()
    payload.pop("capture_source")

    ok, reason = validate_walkthrough_payload(payload, require_files=False)

    assert ok is False
    assert "source stability" in reason.lower()


def test_validate_walkthrough_payload_rejects_raw_transcript_even_if_recorded_passed() -> (
    None
):
    payload = _base_payload()
    payload["user_facing_message_transcript"].append(
        {"role": "assistant", "text": 'Tool Output: {"tool_name": "query_state"}'}
    )

    ok, reason = validate_walkthrough_payload(payload, require_files=False)

    assert ok is False
    assert "internal text" in reason.lower()


def test_assistant_notice_contract_rejects_duplicate_persistent_notice() -> None:
    payload = _base_payload()
    error_phase = next(
        phase
        for phase in payload["phases"]
        if phase["phase"] == "assistant_sanitized_error"
    )
    error_phase["notes"]["assistant_notice"] = {
        "visible": True,
        "text": "Assistant could not complete the request: Try again.",
        "duplicate_with_transcript": True,
    }

    review = build_assistant_notice_contract_review(payload["phases"])

    assert review["passed"] is False
    assert "duplicate" in "; ".join(review["findings"]).lower()


def test_assistant_notice_contract_tracks_runtime_failure_ownership() -> None:
    payload = _base_payload()
    failed_phase = next(
        phase
        for phase in payload["phases"]
        if phase["phase"] == "assistant_runtime_failed"
    )
    failed_phase["notes"]["assistant_notice"] = {
        "visible": True,
        "owner": "runtime",
        "text": "Assistant unavailable: The local model could not start.",
        "duplicate_with_transcript": False,
    }

    review = build_assistant_notice_contract_review(payload["phases"])

    assert review["passed"] is True

    recovery_phase = next(
        phase
        for phase in payload["phases"]
        if phase["phase"] == "assistant_runtime_recovery_loading"
    )
    recovery_phase["notes"]["assistant_notice"] = {
        "visible": True,
        "owner": "runtime",
        "text": "Assistant unavailable: The local model could not start.",
        "duplicate_with_transcript": False,
    }

    review = build_assistant_notice_contract_review(payload["phases"])

    assert review["passed"] is False
    assert "recovery" in "; ".join(review["findings"]).lower()


def test_inline_runtime_state_is_recorded_as_runtime_owned(qtbot) -> None:
    from unittest.mock import patch

    from scripts.dev.human_like_walkthrough.evidence import assistant_notice_evidence
    from XBrainLab.ui.chat.panel import ChatPanel

    with patch("XBrainLab.ui.chat.panel.ToolDebugMode", return_value=None):
        panel = ChatPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.set_runtime_state(
        "failed",
        "The local model could not start. Open assistant settings.",
    )

    evidence = assistant_notice_evidence(panel)

    assert evidence["visible"] is True
    assert evidence["source"] == "inline_runtime"
    assert evidence["owner"] == "runtime"


def test_assistant_error_evidence_accepts_actionable_case_insensitive_copy(
    qtbot,
) -> None:
    from unittest.mock import patch

    from scripts.dev.human_like_walkthrough.evidence import assistant_error_evidence
    from XBrainLab.backend.controller.chat_controller import ChatController
    from XBrainLab.ui.chat.panel import ChatPanel

    with patch("XBrainLab.ui.chat.panel.ToolDebugMode", return_value=None):
        panel = ChatPanel()
    qtbot.addWidget(panel)
    controller = ChatController()
    panel.connect_controller(controller)
    panel.show()
    controller.add_agent_message(
        "The assistant could not complete the request. Try again."
    )
    qtbot.wait(1)

    evidence = assistant_error_evidence(panel)

    assert evidence["raw_error_visible"] is False
    assert evidence["sanitized_message_visible"] is True


def test_assistant_dock_contract_requires_full_standard_and_320px_capture() -> None:
    payload = _base_payload()
    narrow_phase = next(
        phase
        for phase in payload["phases"]
        if phase["phase"] == "assistant_narrow_panel"
    )
    narrow_phase["notes"]["assistant_dock"]["capture_target"] = "panel"
    narrow_phase["notes"]["assistant_dock"]["overflowing_widgets"] = [
        "AssistantDockTitleBar/options"
    ]

    review = build_assistant_dock_contract_review(payload["phases"])

    assert review["passed"] is False
    findings = "; ".join(review["findings"]).lower()
    assert "full dock" in findings
    assert "overflow" in findings


def test_assistant_dock_contract_rejects_overflow_in_any_assistant_phase() -> None:
    payload = _base_payload()
    phase = next(
        phase
        for phase in payload["phases"]
        if phase["phase"] == "assistant_sanitized_error"
    )
    phase["notes"]["assistant_dock"]["overflowing_widgets"] = ["message_bubble_4"]

    review = build_assistant_dock_contract_review(payload["phases"])

    assert review["passed"] is False
    assert "assistant_sanitized_error" in "; ".join(review["findings"])


def test_assistant_signal_path_rejects_direct_chat_controller_injection() -> None:
    payload = _base_payload()
    phase = next(
        phase
        for phase in payload["phases"]
        if phase["phase"] == "assistant_normal_message"
    )
    phase["notes"]["assistant_signal_path"]["direct_chat_controller_injection"] = True

    review = build_assistant_signal_path_review(payload["phases"])

    assert review["passed"] is False
    assert "direct" in "; ".join(review["findings"]).lower()


def test_assistant_artifact_contract_names_manager_signal_evidence() -> None:
    contract = build_artifact_contract()

    assert contract["version"] == ASSISTANT_EVIDENCE_CONTRACT_VERSION
    assert contract["assistant_driver"] == "agent_manager_qt_signals"
    assert contract["assistant_capture_target"] == "full_dock"
    assert contract["assistant_state_capture_target"] == (
        "full_dock_and_full_main_window"
    )
    assert contract["assistant_handoff_capture_target"] == "full_main_window"
    assert contract["assistant_full_window_phases"] == list(
        ASSISTANT_REQUIRED_FULL_WINDOW_SCREENSHOTS
    )
    assert contract["assistant_full_window_screenshots"] == dict(
        ASSISTANT_REQUIRED_FULL_WINDOW_SCREENSHOTS
    )
    assert len(ASSISTANT_REQUIRED_SCREENSHOTS) == len(
        set(ASSISTANT_REQUIRED_SCREENSHOTS)
    )
    assert len(contract["source_fingerprint"]) == 64


def test_assistant_full_window_contract_accepts_required_product_states() -> None:
    payload = _base_payload()

    review = build_assistant_full_window_contract_review(payload["phases"])

    assert review["passed"] is True
    assert review["checked_phases"] == len(ASSISTANT_REQUIRED_FULL_WINDOW_SCREENSHOTS)
    assert set(review["evidence"]) == set(ASSISTANT_REQUIRED_FULL_WINDOW_SCREENSHOTS)


def test_assistant_main_window_evidence_measures_visible_product_geometry(
    qtbot,
) -> None:
    window = QMainWindow()
    window.resize(900, 700)
    central = QWidget(window)
    central_layout = QVBoxLayout(central)
    nav_button = QPushButton("Dataset", central)
    page = QWidget(central)
    central_layout.addWidget(nav_button)
    central_layout.addWidget(page, 1)
    window.setCentralWidget(central)
    window_state = cast(Any, window)
    window_state.nav_btns = [nav_button]
    window_state.stack = page
    dock = QDockWidget(window)
    title_bar = QWidget(dock)
    title_layout = QHBoxLayout(title_bar)
    title = QLabel("XBrainLab", title_bar)
    title.setObjectName("AssistantDockTitle")
    title_layout.addWidget(title)
    dock.setTitleBarWidget(title_bar)
    panel = QWidget(dock)
    panel_layout = QVBoxLayout(panel)
    panel_layout.addStretch(1)
    composer = QWidget(panel)
    composer_layout = QHBoxLayout(composer)
    input_field = QLineEdit(composer)
    send_button = QPushButton("Send", composer)
    composer_layout.addWidget(input_field)
    composer_layout.addWidget(send_button)
    panel_layout.addWidget(composer)
    panel_state = cast(Any, panel)
    panel_state.input_widget = composer
    panel_state.input_field = input_field
    panel_state.send_btn = send_button
    dock.setWidget(panel)
    window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    qtbot.addWidget(window)
    window.show()
    qtbot.wait(0)

    evidence = assistant_main_window_evidence(
        window,
        dock,
        panel_state,
        state="assistant_runtime_ready",
        workflow_status="ready",
    )

    assert evidence["geometry_passed"] is True
    assert evidence["title_text"] == "XBrainLab"
    assert evidence["title_text_fits"] is True
    assert evidence["composer_visible"] is True
    assert evidence["primary_action_text"] == "Send"
    assert evidence["main_content_visible"] is True
    assert evidence["main_navigation_visible_count"] == 1
    assert evidence["out_of_window_widgets"] == []
    assert evidence["overlapping_widgets"] == []


@pytest.mark.parametrize(
    ("phase_name", "field", "bad_value", "finding"),
    [
        ("assistant_runtime_loading", "title_text_fits", False, "title"),
        ("assistant_runtime_ready", "composer_visible", False, "composer"),
        ("assistant_runtime_failed", "primary_action_visible", False, "action"),
        (
            "assistant_blocked_command",
            "out_of_window_widgets",
            ["send_action"],
            "outside",
        ),
        (
            "assistant_narrow_panel",
            "overlapping_widgets",
            ["composer/send_action"],
            "overlap",
        ),
        (
            "assistant_narrow_panel",
            "main_navigation_text_overflow",
            ["Visualization"],
            "navigation text",
        ),
        (
            "assistant_existing_ui_handoff",
            "workflow_status",
            "pending",
            "workflow status",
        ),
    ],
)
def test_assistant_full_window_contract_rejects_unreadable_product_states(
    phase_name: str,
    field: str,
    bad_value: Any,
    finding: str,
) -> None:
    payload = _base_payload()
    phase = next(item for item in payload["phases"] if item["phase"] == phase_name)
    phase["notes"]["assistant_main_window"][field] = bad_value

    review = build_assistant_full_window_contract_review(payload["phases"])

    assert review["passed"] is False
    assert finding in "; ".join(review["findings"]).lower()


def test_assistant_full_window_contract_accepts_compact_navigation_selector() -> None:
    payload = _base_payload()
    phase = next(
        item for item in payload["phases"] if item["phase"] == "assistant_narrow_panel"
    )
    state = phase["notes"]["assistant_main_window"]
    state.update(
        {
            "main_navigation_visible_count": 0,
            "compact_navigation_visible": True,
            "compact_navigation_text": "Evaluation",
            "compact_navigation_inside_window": True,
            "compact_navigation_text_fits": True,
        }
    )

    review = build_assistant_full_window_contract_review(payload["phases"])

    assert review["passed"] is True


def test_assistant_full_window_contract_rejects_clipped_compact_navigation() -> None:
    payload = _base_payload()
    phase = next(
        item for item in payload["phases"] if item["phase"] == "assistant_narrow_panel"
    )
    state = phase["notes"]["assistant_main_window"]
    state.update(
        {
            "main_navigation_visible_count": 0,
            "compact_navigation_visible": True,
            "compact_navigation_text": "Evaluation",
            "compact_navigation_inside_window": True,
            "compact_navigation_text_fits": False,
        }
    )

    review = build_assistant_full_window_contract_review(payload["phases"])

    assert review["passed"] is False
    assert "compact navigation" in "; ".join(review["findings"])


def test_assistant_full_window_contract_rejects_narrow_plot_overlap() -> None:
    payload = _base_payload()
    phase = next(
        item for item in payload["phases"] if item["phase"] == "assistant_narrow_panel"
    )
    plot = phase["notes"]["assistant_main_window"]["evaluation_plot_readability"]
    plot.update(
        {
            "fully_visible": False,
            "overlapping_x_ticks": ["Left hand / Right hand"],
        }
    )

    review = build_assistant_full_window_contract_review(payload["phases"])

    assert review["passed"] is False
    findings = "; ".join(review["findings"])
    assert "narrow Evaluation plot" in findings
    assert "Left hand / Right hand" in findings


def test_validate_walkthrough_payload_rejects_missing_full_window_screenshot() -> None:
    payload = _base_payload()
    screenshot_key = ASSISTANT_REQUIRED_FULL_WINDOW_SCREENSHOTS[
        "assistant_runtime_loading"
    ]
    payload["screenshots"].pop(screenshot_key)

    ok, reason = validate_walkthrough_payload(payload, require_files=False)

    assert ok is False
    assert "full window" in reason.lower()


def test_assistant_source_fingerprint_covers_every_chat_presentation_source() -> None:
    relative_paths = {
        str(path.relative_to(Path(__file__).resolve().parents[3]))
        for path in ASSISTANT_FINGERPRINT_PATHS
    }

    assert "XBrainLab/ui/chat/composer.py" in relative_paths
    assert "XBrainLab/ui/chat/status_presenter.py" in relative_paths
    assert "XBrainLab/ui/components/workflow_ui_handoff_host.py" in relative_paths
    assert "XBrainLab/ui/components/assistant_status_projection.py" in relative_paths
    assert "XBrainLab/ui/components/assistant_runtime_coordinator.py" in relative_paths
    assert "XBrainLab/ui/panels/training/components.py" in relative_paths
    assert "XBrainLab/llm/agent/execution_policy.py" in relative_paths
    assert "XBrainLab/ui/panels/evaluation/panel.py" in relative_paths
    assert "XBrainLab/ui/panels/visualization/panel.py" in relative_paths
    assert (
        "XBrainLab/ui/panels/visualization/saliency_views/plot_3d_view.py"
        in relative_paths
    )
    assert "XBrainLab/backend/visualization/saliency_map.py" in relative_paths
    assert "XBrainLab/ui/dialogs/model_settings_dialog.py" in relative_paths
    assert (
        "XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py"
        in relative_paths
    )
    assert "XBrainLab/ui/dialogs/training/model_selection_dialog.py" in relative_paths
    assert (
        "XBrainLab/ui/dialogs/visualization/saliency_setting_dialog.py"
        in relative_paths
    )
    assert "XBrainLab/ui/panels/training/history_table.py" in relative_paths
    assert "XBrainLab/ui/panels/evaluation/confusion_matrix.py" in relative_paths
    assert "XBrainLab/ui/panels/evaluation/metrics_table.py" in relative_paths
    assert "XBrainLab/llm/agent/response_presentation.py" in relative_paths
    assert "XBrainLab/llm/agent/tool_feedback.py" in relative_paths


def test_assistant_source_fingerprint_covers_turn_history_and_action_contracts() -> (
    None
):
    root = Path(__file__).resolve().parents[3]
    relative_paths = {
        str(path.relative_to(root)) for path in ASSISTANT_FINGERPRINT_PATHS
    }
    required_contract_sources = {
        "XBrainLab/chat_contract.py",
        "XBrainLab/backend/controller/chat_controller.py",
        "XBrainLab/llm/agent/assistant_activity.py",
        "XBrainLab/llm/agent/response_presentation.py",
        "XBrainLab/llm/agent/turn.py",
        "XBrainLab/ui/chat/presentation.py",
        "XBrainLab/ui/chat/turn_state.py",
        "XBrainLab/ui/components/assistant_runtime_lifecycle.py",
    }

    assert required_contract_sources <= relative_paths


def test_narrow_walkthrough_uses_the_product_minimum_window_size() -> None:
    assert QSize(760, 520) == NARROW_WINDOW_SIZE


def test_state_backed_assistant_response_only_claims_observed_backend_truth() -> None:
    response = build_state_backed_assistant_response(
        SimpleNamespace(ok=True),
        {
            "training": {"finished_run_count": 1},
            "evaluation": {"available": True},
            "visualization": {"available": False},
        },
    )

    assert response.command_ok is True
    assert response.claims == ("training_complete", "evaluation_available")
    assert "training has finished" in response.text.lower()
    assert "evaluation results are available" in response.text.lower()
    assert "visualization" not in response.text.lower()


def test_failed_state_query_never_renders_success_language() -> None:
    response = build_state_backed_assistant_response(
        SimpleNamespace(ok=False),
        {
            "training": {"finished_run_count": 1},
            "evaluation": {"available": True},
            "visualization": {"available": True},
        },
    )

    assert response.command_ok is False
    assert response.claims == ()
    lowered = response.text.lower()
    for forbidden in ("complete", "finished", "available", "ready", "success"):
        assert forbidden not in lowered


def test_assistant_claim_review_compares_claims_with_recorded_backend_state() -> None:
    phase = {
        "phase": "assistant_successful_tool_result",
        "visible_text": [
            "Verified from the current workflow: training has finished; "
            "evaluation results are available."
        ],
        "workflow_state": {
            "training": {"finished_run_count": 1},
            "evaluation": {"available": True},
            "visualization": {"available": False},
        },
        "notes": {
            "assistant_claims": {
                "command_result": {"ok": True, "command": "query_state"},
                "claims": ["training_complete", "evaluation_available"],
                "response_text": (
                    "Verified from the current workflow: training has finished; "
                    "evaluation results are available."
                ),
            }
        },
    }

    assert build_assistant_claim_contract_review([phase])["passed"] is True

    phase["workflow_state"]["evaluation"]["available"] = False
    review = build_assistant_claim_contract_review([phase])

    assert review["passed"] is False
    assert "evaluation_available" in "; ".join(review["findings"])


def test_assistant_claim_review_rejects_failed_command_with_success_copy() -> None:
    phase = {
        "phase": "assistant_successful_tool_result",
        "visible_text": ["Training is complete. Evaluation is ready."],
        "workflow_state": {},
        "notes": {
            "assistant_claims": {
                "command_result": {"ok": False, "command": "query_state"},
                "claims": ["training_complete"],
                "response_text": "Training is complete. Evaluation is ready.",
            }
        },
    }

    review = build_assistant_claim_contract_review([phase])

    assert review["passed"] is False
    findings = "; ".join(review["findings"]).lower()
    assert "failed" in findings
    assert "success language" in findings


def _valid_assistant_interaction_phases() -> list[dict[str, Any]]:
    return [
        {
            "phase": "assistant_confirmation_cancelled",
            "visible_text": [
                "Session reset cancelled. Your current workflow is unchanged."
            ],
            "notes": {
                "assistant_interaction": {
                    "request_kind": "production_confirmation",
                    "decision": "cancelled",
                    "destructive": True,
                    "dialog_opened": True,
                    "dialog_title": "Confirm destructive action",
                    "terminal_messages": [
                        "Session reset cancelled. Your current workflow is unchanged."
                    ],
                    "confirmed_execution_count": 0,
                    "duplicate_terminal_message": False,
                    "scenario_start_message_count": 0,
                    "scenario_message_count": 2,
                    "scenario_isolated": True,
                }
            },
        },
        {
            "phase": "assistant_confirmation_confirmed",
            "visible_text": [ASSISTANT_CONFIRMED_TERMINAL_MESSAGE],
            "notes": {
                "assistant_interaction": {
                    "request_kind": "production_confirmation",
                    "decision": "confirmed",
                    "destructive": True,
                    "dialog_opened": True,
                    "dialog_title": "Confirm destructive action",
                    "terminal_messages": [ASSISTANT_CONFIRMED_TERMINAL_MESSAGE],
                    "confirmed_execution_count": 1,
                    "duplicate_terminal_message": False,
                    "scenario_start_message_count": 0,
                    "scenario_message_count": 2,
                    "scenario_isolated": True,
                }
            },
        },
        {
            "phase": "assistant_existing_ui_handoff",
            "visible_text": [
                "Evaluation is open in the main window. Review results there."
            ],
            "notes": {
                "assistant_interaction": {
                    "request_kind": "typed_workflow_ui_handoff",
                    "decision": "opened_in_main_window",
                    "handoff_kind": "decision_required",
                    "command_name": "evaluate",
                    "request_id": ASSISTANT_HANDOFF_REQUEST_ID,
                    "decision_fields": ["evaluation_result"],
                    "resolution_request_id": ASSISTANT_HANDOFF_REQUEST_ID,
                    "resolution_command_name": "evaluate",
                    "resolution_status": "deferred_to_ui",
                    "resolution_decision_fields": ["evaluation_result"],
                    "resolution_message": "The relevant XBrainLab panel is open.",
                    "request_resolution_correlated": True,
                    "terminal_messages": [
                        "Evaluation is open in the main window. Review results there."
                    ],
                    "confirmed_execution_count": 0,
                    "duplicate_terminal_message": False,
                    "typed_handoff_emitted": True,
                    "typed_resolution_accepted": True,
                    "scenario_start_message_count": 0,
                    "scenario_message_count": 2,
                    "scenario_isolated": True,
                    "main_window_handoff": {
                        "capture_target": "full_main_window",
                        "main_window_visible": True,
                        "active_panel": "Evaluation",
                        "active_index": 3,
                        "evaluation_index": 3,
                        "evaluation_nav_checked": True,
                        "active_page_visible": True,
                        "assistant_dock_visible": True,
                        "workflow_status": "opened",
                        "workflow_opened": True,
                        "evaluation_plot_readability": {
                            "available": True,
                            "fully_visible": True,
                            "responsive_layout_ok": True,
                            "layout_mode": "tabs",
                            "clipped_labels": [],
                            "overlapping_x_ticks": [],
                            "axes_outside_figure": [],
                            "y_tick_labels": [
                                {"text": "Left hand", "clipped": False},
                                {"text": "Right hand", "clipped": False},
                            ],
                        },
                    },
                    "product_copy": {
                        "cancelled": (
                            "Evaluation review was cancelled. "
                            "Your current workflow is unchanged."
                        ),
                        "completed": "Evaluation review is ready in XBrainLab.",
                        "failed": (
                            "XBrainLab could not open Evaluation. "
                            "Try again from the main window."
                        ),
                    },
                }
            },
        },
    ]


def test_assistant_interaction_review_requires_cancel_confirm_and_handoff() -> None:
    review = build_assistant_interaction_contract_review(
        _valid_assistant_interaction_phases()
    )

    assert review["passed"] is True
    assert review["checked_phases"] == 3


def test_assistant_interaction_review_rejects_duplicate_or_success_after_cancel() -> (
    None
):
    phases = _valid_assistant_interaction_phases()
    cancelled = phases[0]["notes"]["assistant_interaction"]
    cancelled["terminal_messages"].append(
        "The assistant completed a background action successfully."
    )
    cancelled["duplicate_terminal_message"] = True

    review = build_assistant_interaction_contract_review(phases)

    assert review["passed"] is False
    findings = "; ".join(review["findings"]).lower()
    assert "cancel" in findings
    assert "duplicate" in findings or "one terminal" in findings


def test_assistant_interaction_review_requires_active_full_window_handoff() -> None:
    phases = _valid_assistant_interaction_phases()
    handoff = phases[2]["notes"]["assistant_interaction"]
    handoff["main_window_handoff"]["active_panel"] = "Training"
    handoff["main_window_handoff"]["evaluation_nav_checked"] = False

    review = build_assistant_interaction_contract_review(phases)

    assert review["passed"] is False
    assert "full-window active Evaluation" in "; ".join(review["findings"])


def test_assistant_interaction_review_hard_fails_clipped_evaluation_labels() -> None:
    phases = _valid_assistant_interaction_phases()
    plot = phases[2]["notes"]["assistant_interaction"]["main_window_handoff"][
        "evaluation_plot_readability"
    ]
    plot["fully_visible"] = False
    plot["clipped_labels"] = ["Left hand", "Right hand"]

    review = build_assistant_interaction_contract_review(phases)

    assert review["passed"] is False
    findings = "; ".join(review["findings"])
    assert "hard gate" in findings
    assert "Left hand, Right hand" in findings


def test_assistant_interaction_review_requires_polished_handoff_outcome_copy() -> None:
    phases = _valid_assistant_interaction_phases()
    product_copy = phases[2]["notes"]["assistant_interaction"]["product_copy"]
    product_copy["cancelled"] = "Review results was cancelled."

    review = build_assistant_interaction_contract_review(phases)

    assert review["passed"] is False
    assert "unpolished cancelled product copy" in "; ".join(review["findings"])


def test_assistant_interaction_review_rejects_accumulated_scenarios() -> None:
    phases = _valid_assistant_interaction_phases()
    confirmed = phases[1]["notes"]["assistant_interaction"]
    confirmed["scenario_start_message_count"] = 4
    confirmed["scenario_message_count"] = 6
    confirmed["scenario_isolated"] = False

    review = build_assistant_interaction_contract_review(phases)

    assert review["passed"] is False
    assert "not an isolated assistant scenario" in "; ".join(review["findings"])


def test_settings_recovery_review_requires_real_dialog_save_and_runtime_sequence() -> (
    None
):
    phase = {
        "phase": "assistant_runtime_ready",
        "notes": {
            "assistant_settings_recovery": {
                "open_settings_clicked": True,
                "dialog_opened": True,
                "dialog_title": "AI Assistant Settings",
                "activate_clicked": True,
                "save_observed": True,
                "isolated_config": True,
                "host_config_unchanged": True,
                "runtime_sequence": ["failed", "loading", "ready"],
                "settings_screenshot": "assistant-settings.png",
            }
        },
    }

    assert build_assistant_settings_recovery_review([phase])["passed"] is True

    phase["notes"]["assistant_settings_recovery"]["save_observed"] = False
    review = build_assistant_settings_recovery_review([phase])

    assert review["passed"] is False
    assert "save" in "; ".join(review["findings"]).lower()


@pytest.mark.parametrize(
    ("phase_name", "width"),
    [
        ("assistant_empty_state", 419),
        ("assistant_narrow_panel", 321),
    ],
)
def test_assistant_dock_contract_enforces_420_and_320_widths(
    phase_name: str,
    width: int,
) -> None:
    payload = _base_payload()
    phase = next(item for item in payload["phases"] if item["phase"] == phase_name)
    phase["notes"]["assistant_dock"]["dock_width"] = width

    review = build_assistant_dock_contract_review(payload["phases"])

    assert review["passed"] is False
    assert str(width) in "; ".join(review["findings"])


def test_walkthrough_request_traverses_real_agent_manager_and_qt_signals(qtbot) -> None:
    window = QMainWindow()
    qtbot.addWidget(window)
    manager = AgentManager(window, Study())
    manager.init_ui()
    try:
        controller = install_walkthrough_assistant(manager)
        controller.publish_runtime("ready")
        app = QApplication.instance()
        assert isinstance(app, QApplication)

        drive_assistant_request(
            app,
            manager,
            ASSISTANT_NORMAL_REQUEST,
        )

        assert manager.chat_controller.messages == [
            {"role": "user", "content": ASSISTANT_NORMAL_REQUEST},
            {
                "role": "assistant",
                "content": (
                    "I can help interpret EEG data and prepare a training-ready "
                    "dataset."
                ),
            },
        ]
        assert f"request:{ASSISTANT_NORMAL_REQUEST}" in controller.events
        assert "response:ready" in controller.events
    finally:
        manager.close()


def test_runtime_semantics_traverse_agent_manager_qt_signals(qtbot) -> None:
    window = QMainWindow()
    qtbot.addWidget(window)
    manager = AgentManager(window, Study())
    manager.init_ui()
    try:
        controller = install_walkthrough_assistant(manager)
        panel = manager.chat_panel
        assert panel is not None
        app = QApplication.instance()
        assert isinstance(app, QApplication)
        window.show()
        assert manager.chat_dock is not None
        manager.chat_dock.show()
        app.processEvents()
        phases: list[dict[str, Any]] = []

        def record(phase_name: str) -> None:
            app.processEvents()
            phases.append(
                {
                    "phase": phase_name,
                    "notes": {
                        "assistant_runtime": assistant_runtime_evidence(panel),
                    },
                }
            )

        controller.publish_runtime("idle")
        record("assistant_runtime_idle")
        controller.publish_runtime("loading")
        record("assistant_runtime_loading")
        controller.publish_runtime_failure()
        record("assistant_runtime_failed")
        controller.publish_runtime("loading", activation_id=0)
        controller.publish_runtime("loading", activation_id=0)
        record("assistant_runtime_recovery_loading")
        controller.publish_runtime("ready", activation_id=0)
        record("assistant_runtime_ready")

        review = build_assistant_runtime_contract_review(phases)

        assert review["passed"] is True, review["findings"]
        recovery = review["evidence"]["recovery"]
        assert recovery["inline_state_title"] == "Retrying local assistant"
        assert recovery["setup_action_visible"] is False
        assert recovery["panel_processing"] is False
    finally:
        manager.close()


def test_walkthrough_processing_request_shows_workflow_feedback(qtbot) -> None:
    window = QMainWindow()
    qtbot.addWidget(window)
    manager = AgentManager(window, Study())
    manager.init_ui()
    try:
        controller = install_walkthrough_assistant(manager)
        controller.publish_runtime("ready")
        panel = manager.chat_panel
        assert panel is not None
        panel.workflow_mode_btn.click()
        app = QApplication.instance()
        assert isinstance(app, QApplication)

        drive_assistant_request(
            app,
            manager,
            ASSISTANT_PROCESSING_REQUEST,
            expect_processing=True,
        )

        assert not panel.turn_activity_widget.isHidden()
        assert panel.turn_activity_title.text() == "Preparing your request"
        assert panel.turn_activity_step.text() == (
            "Current step: Checking the current EEG workflow"
        )
        assert (
            panel.turn_activity_widget.property("assistantCancelability")
            == "cancellable"
        )
        assert panel.workflow_run_status_label.isHidden()
        assert panel.send_btn.text() == "Stop"
    finally:
        manager.close()


def test_capture_named_settles_layout_before_recording(qtbot, tmp_path) -> None:
    widget = QWidget()
    qtbot.addWidget(widget)
    widget.resize(420, 760)
    widget.show()
    calls: list[str] = []

    with (
        patch(
            "scripts.dev.capture_human_like_product_walkthrough."
            "settle_widget_for_capture",
            side_effect=lambda *_args, **_kwargs: calls.append("settle"),
        ),
        patch(
            "scripts.dev.capture_human_like_product_walkthrough.capture_widget",
            side_effect=lambda *_args, **_kwargs: calls.append("capture"),
        ),
    ):
        result = capture_named(widget, tmp_path, "assistant_failed")

    assert calls == ["settle", "capture"]
    assert result.endswith(SCREENSHOT_NAMES["assistant_failed"])


def test_capture_frame_readiness_rejects_large_local_unpainted_region(tmp_path) -> None:
    screenshot = tmp_path / "partial-main-window.png"
    image = Image.new("RGB", (760, 520), "#252a30")
    ImageDraw.Draw(image).rectangle((500, 30, 759, 500), fill="#000000")
    image.save(screenshot)

    with pytest.raises(RuntimeError, match="unpainted block"):
        _assert_region_has_no_unpainted_block(
            screenshot,
            (480, 0, 760, 520),
            surface_name="Workflow sidebar",
        )


def test_capture_frame_readiness_requires_stable_consecutive_frames(tmp_path) -> None:
    first = tmp_path / "frame-one.png"
    second = tmp_path / "frame-two.png"
    Image.new("RGB", (420, 650), "#27313a").save(first)
    changed = Image.new("RGB", (420, 650), "#27313a")
    ImageDraw.Draw(changed).rectangle((0, 300, 419, 649), fill="#000000")
    changed.save(second)

    with pytest.raises(RuntimeError, match="consecutive complete frames"):
        _assert_consecutive_complete_frames(first, second)


def test_capture_uses_qt_backing_store_instead_of_recursive_widget_render() -> None:
    source = inspect.getsource(capture_widget) + inspect.getsource(_grab_widget_to_path)

    assert "widget.render(" not in source
    assert "widget.grab()" in source


def test_docked_widget_capture_crops_composed_main_window_with_dpr(
    qtbot, tmp_path
) -> None:
    class BlackBackingStoreDock(QDockWidget):
        def grab(self, rectangle: QRect | None = None) -> QPixmap:
            del rectangle
            pixmap = QPixmap(self.size())
            pixmap.fill(QColor("#000000"))
            return pixmap

    class ComposedMainWindow(QMainWindow):
        dock: QDockWidget

        def grab(self, rectangle: QRect | None = None) -> QPixmap:
            del rectangle
            dpr = 2.0
            pixmap = QPixmap(
                round(self.width() * dpr),
                round(self.height() * dpr),
            )
            pixmap.fill(QColor("#101418"))
            dock_position = self.dock.mapTo(self, QPoint(0, 0))
            painter = QPainter(pixmap)
            painter.fillRect(
                QRect(
                    round(dock_position.x() * dpr),
                    round(dock_position.y() * dpr),
                    round(self.dock.width() * dpr),
                    round(self.dock.height() * dpr),
                ),
                QColor("#2ac780"),
            )
            painter.end()
            pixmap.setDevicePixelRatio(dpr)
            return pixmap

    window = ComposedMainWindow()
    qtbot.addWidget(window)
    window.resize(640, 420)
    window.setCentralWidget(QWidget(window))
    dock = BlackBackingStoreDock("Assistant", window)
    dock.setWidget(QWidget(dock))
    dock.setMinimumWidth(180)
    window.dock = dock
    window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    window.show()
    qtbot.wait(0)

    direct = dock.grab()
    assert direct.toImage().pixelColor(0, 0) == QColor("#000000")

    output_path = tmp_path / "composed-dock.png"
    _grab_widget_to_path(dock, output_path)

    with Image.open(output_path) as image:
        assert image.size == (dock.width() * 2, dock.height() * 2)
        center = image.convert("RGB").getpixel((image.width // 2, image.height // 2))
    assert center == QColor("#2ac780").getRgb()[:3]


def test_docked_widget_capture_falls_back_when_composed_grab_is_null(
    qtbot, tmp_path
) -> None:
    class NullComposedMainWindow(QMainWindow):
        def grab(self, rectangle: QRect | None = None) -> QPixmap:
            del rectangle
            return QPixmap()

    class FallbackDock(QDockWidget):
        def grab(self, rectangle: QRect | None = None) -> QPixmap:
            del rectangle
            pixmap = QPixmap(self.size())
            pixmap.fill(QColor("#d34dba"))
            return pixmap

    window = NullComposedMainWindow()
    qtbot.addWidget(window)
    window.resize(640, 420)
    window.setCentralWidget(QWidget(window))
    dock = FallbackDock("Assistant", window)
    dock.setWidget(QWidget(dock))
    dock.setMinimumWidth(180)
    window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    window.show()
    qtbot.wait(0)

    output_path = tmp_path / "fallback-dock.png"
    _grab_widget_to_path(dock, output_path)

    with Image.open(output_path) as image:
        assert image.size == (dock.width(), dock.height())
        center = image.convert("RGB").getpixel((image.width // 2, image.height // 2))
    assert center == QColor("#d34dba").getRgb()[:3]


def test_walkthrough_direct_user_input_fails_closed_without_turn_activity() -> None:
    controller = WalkthroughAssistantController()
    presentations: list[object] = []
    terminals: list[object] = []
    controller.response_presentation_ready.connect(presentations.append)
    controller.turn_finished.connect(terminals.append)

    with pytest.raises(RuntimeError, match="AssistantTurnRequest"):
        controller.handle_user_input(ASSISTANT_NORMAL_REQUEST)

    assert controller.events == []
    assert controller.is_processing is False
    assert controller._active_turn is None
    assert presentations == []
    assert terminals == []


def test_walkthrough_source_has_no_standalone_turn_admission_fallback() -> None:
    controller_source = inspect.getsource(WalkthroughAssistantController)
    admitted_source = inspect.getsource(WalkthroughAssistantController.handle_user_turn)
    direct_source = inspect.getsource(WalkthroughAssistantController.handle_user_input)

    assert "_standalone_turn_sequence" not in controller_source
    assert "AssistantTurnCorrelation(" not in direct_source
    assert "_handle_admitted_user_input(payload.text)" in admitted_source
    assert "raise RuntimeError" in direct_source


def test_walkthrough_confirmation_publishes_a_terminal_result() -> None:
    controller = WalkthroughAssistantController()
    presentations: list[object] = []
    controller.response_presentation_ready.connect(presentations.append)

    _admit_walkthrough_turn(controller, ASSISTANT_CONFIRM_CONFIRMATION_REQUEST)
    request = controller.last_confirmation_request
    assert isinstance(request, AgentConfirmationRequest)
    controller.on_user_confirmation_resolved(
        AgentConfirmationResolution.for_request(
            request,
            status=AgentConfirmationResolutionStatus.APPROVED,
        )
    )

    assert len(presentations) == 1
    presentation = presentations[0]
    assert isinstance(presentation, AssistantResponsePresentation)
    assert presentation.text == ASSISTANT_CONFIRMED_TERMINAL_MESSAGE
    assert controller.session_generation == 1


def test_walkthrough_stop_publishes_a_terminal_cancellation() -> None:
    controller = WalkthroughAssistantController()
    presentations: list[object] = []
    controller.response_presentation_ready.connect(presentations.append)

    _admit_walkthrough_turn(controller, ASSISTANT_PROCESSING_REQUEST)
    controller.stop_generation()

    assert presentations == []
    assert controller.is_processing is True
    controller.complete_stop()

    assert len(presentations) == 1
    presentation = presentations[0]
    assert isinstance(presentation, AssistantResponsePresentation)
    assert presentation.text == ASSISTANT_STOPPED_MESSAGE
    assert controller.is_processing is False


def test_walkthrough_clarification_copy_matches_its_available_actions() -> None:
    controller = WalkthroughAssistantController()
    presentations: list[object] = []
    controller.response_presentation_ready.connect(presentations.append)

    _admit_walkthrough_turn(controller, ASSISTANT_CLARIFICATION_REQUEST)

    assert len(presentations) == 1
    presentation = cast(AssistantResponsePresentation, presentations[0])
    assert presentation.text == ASSISTANT_PATH_CLARIFICATION_MESSAGE
    assert tuple(action.label for action in presentation.actions) == ("Open Dataset",)


def test_walkthrough_blocked_action_resolves_the_stated_session_blocker() -> None:
    controller = WalkthroughAssistantController()
    presentations: list[object] = []
    controller.response_presentation_ready.connect(presentations.append)

    _admit_walkthrough_turn(controller, ASSISTANT_BLOCKED_REQUEST)

    assert len(presentations) == 1
    presentation = cast(AssistantResponsePresentation, presentations[0])
    assert "Start a new session" in presentation.text
    assert len(presentation.actions) == 1
    action = presentation.actions[0]
    assert action.label == "Start new session"
    assert action.kind is AssistantResponseActionKind.SEND_MESSAGE
    assert action.prompt == ASSISTANT_CONFIRM_CONFIRMATION_REQUEST


def test_walkthrough_confirmation_marks_session_reset_as_destructive() -> None:
    controller = WalkthroughAssistantController()
    requests: list[object] = []
    controller.confirmation_requested.connect(requests.append)

    _admit_walkthrough_turn(controller, ASSISTANT_CONFIRM_CONFIRMATION_REQUEST)

    assert len(requests) == 1
    request = requests[0]
    assert isinstance(request, AgentConfirmationRequest)
    assert request.command_name == CommandName.NEW_SESSION.value
    assert request.parameter_rows == ()
    assert request.description == "Start a new session and clear the current one."
    assert request.destructive is True


def test_walkthrough_handoff_uses_typed_workflow_signal_only() -> None:
    controller = WalkthroughAssistantController()
    handoffs: list[object] = []
    panel_requests: list[object] = []
    controller.workflow_ui_handoff_requested.connect(handoffs.append)
    controller.panel_navigation_requested.connect(panel_requests.append)

    _admit_walkthrough_turn(controller, ASSISTANT_EXISTING_UI_REQUEST)

    assert len(handoffs) == 1
    handoff = cast(WorkflowUiHandoffRequest, handoffs[0])
    assert handoff.kind is WorkflowUiHandoffKind.DECISION_REQUIRED
    assert handoff.command is CommandName.EVALUATE
    assert handoff.decision_fields == ("evaluation_result",)
    assert handoff.request_id == ASSISTANT_HANDOFF_REQUEST_ID
    assert panel_requests == []


def test_walkthrough_handoff_only_accepts_correlated_typed_resolution() -> None:
    controller = WalkthroughAssistantController()
    outcomes: list[object] = []
    controller.interaction_resolved.connect(outcomes.append)
    _admit_walkthrough_turn(controller, ASSISTANT_EXISTING_UI_REQUEST)
    request = controller.last_workflow_handoff
    assert request is not None

    controller.on_workflow_ui_handoff_resolved(
        WorkflowUiHandoffResolution(
            request_id="stale-request",
            command=request.command,
            status=WorkflowUiHandoffResolutionStatus.DEFERRED_TO_UI,
            decision_fields=request.decision_fields,
        )
    )
    assert outcomes == []
    assert controller.is_processing is True

    resolution = WorkflowUiHandoffResolution.for_request(
        request,
        status=WorkflowUiHandoffResolutionStatus.DEFERRED_TO_UI,
        message="The relevant XBrainLab panel is open.",
    )
    controller.on_workflow_ui_handoff_resolved(resolution)

    assert len(outcomes) == 1
    outcome = cast(AgentInteractionOutcome, outcomes[0])
    assert outcome.status is AgentInteractionStatus.DEFERRED_TO_UI
    assert outcome.request_id == ASSISTANT_HANDOFF_REQUEST_ID
    assert outcome.decision_fields == ("evaluation_result",)
    assert controller.last_workflow_resolution == resolution
    assert controller.is_processing is False


@pytest.mark.parametrize(
    ("resolution_status", "interaction_status"),
    [
        (
            WorkflowUiHandoffResolutionStatus.DEFERRED_TO_UI,
            AgentInteractionStatus.DEFERRED_TO_UI,
        ),
        (
            WorkflowUiHandoffResolutionStatus.COMPLETED,
            AgentInteractionStatus.COMPLETED_IN_UI,
        ),
        (
            WorkflowUiHandoffResolutionStatus.CANCELLED,
            AgentInteractionStatus.CANCELLED,
        ),
        (
            WorkflowUiHandoffResolutionStatus.BLOCKED,
            AgentInteractionStatus.BLOCKED,
        ),
        (
            WorkflowUiHandoffResolutionStatus.UNAVAILABLE,
            AgentInteractionStatus.UNAVAILABLE,
        ),
        (
            WorkflowUiHandoffResolutionStatus.FAILED,
            AgentInteractionStatus.FAILED,
        ),
    ],
)
def test_walkthrough_handoff_preserves_every_typed_resolution_status(
    resolution_status: WorkflowUiHandoffResolutionStatus,
    interaction_status: AgentInteractionStatus,
) -> None:
    controller = WalkthroughAssistantController()
    outcomes: list[object] = []
    controller.interaction_resolved.connect(outcomes.append)
    _admit_walkthrough_turn(controller, ASSISTANT_EXISTING_UI_REQUEST)
    request = controller.last_workflow_handoff
    assert request is not None

    resolution = WorkflowUiHandoffResolution.for_request(
        request,
        status=resolution_status,
        message="Correlated product-surface result.",
    )
    controller.on_workflow_ui_handoff_resolved(resolution)

    assert len(outcomes) == 1
    outcome = cast(AgentInteractionOutcome, outcomes[0])
    assert outcome.status is interaction_status
    assert outcome.command_name == CommandName.EVALUATE.value
    assert outcome.request_id == ASSISTANT_HANDOFF_REQUEST_ID
    assert outcome.decision_fields == ("evaluation_result",)
    assert outcome.message == "Correlated product-surface result."


def test_walkthrough_handoff_does_not_restore_legacy_callback_surface() -> None:
    controller = WalkthroughAssistantController()

    for callback_name in (
        "on_user_deferred_to_ui",
        "on_user_completed_in_ui",
        "on_user_cancelled_in_ui",
        "on_existing_ui_unavailable",
    ):
        assert not hasattr(controller, callback_name)


def test_assistant_walkthrough_source_forbids_direct_ui_state_injection() -> None:
    source = inspect.getsource(run_chatpanel_walkthrough)

    for forbidden in (
        "chat_controller.add_user_message",
        "chat_controller.add_agent_message",
        "panel.set_runtime_state",
        "panel.set_processing_state",
        "chat_controller.set_processing",
    ):
        assert forbidden not in source


def test_entry_delegates_assistant_capture_to_cohesive_helper() -> None:
    source = inspect.getsource(run_chatpanel_walkthrough)

    assert "assistant_capture.run_assistant_walkthrough" in source
    assert len(source.splitlines()) <= 35


def test_single_recording_walkthrough_uses_individual_trial_split() -> None:
    source = inspect.getsource(_run_walkthrough_steps)

    assert len(WALKTHROUGH_EVENT_ROWS) == 10
    assert len(set(WALKTHROUGH_EVENT_ROWS)) == 10
    assert "t_max=0.51" in source
    assert 'model_name="SCCNet"' in source
    assert 'split_strategy="trial"' in source
    assert 'training_mode="individual"' in source
    assert 'training_mode="group"' not in source


@pytest.mark.parametrize(
    "reviewer",
    [
        build_assistant_processing_contract_review,
        build_assistant_runtime_contract_review,
        build_assistant_dock_contract_review,
        build_assistant_notice_contract_review,
        build_assistant_signal_path_review,
        build_assistant_stage_copy_review,
    ],
)
def test_assistant_reviewers_are_owned_by_walkthrough_helper(reviewer: Any) -> None:
    source_file = inspect.getsourcefile(reviewer)

    assert source_file is not None
    assert Path(source_file).parent.name == "human_like_walkthrough"


def test_data_import_visual_evidence_requires_distinct_expected_steps(tmp_path) -> None:
    expected = {
        "data_interpretation_scan_result": "Choose EEG Data",
        "data_interpretation_preview": "Review Metadata",
        "data_interpretation_confirm_metadata_labels": "Match Labels",
        "data_interpretation_review_and_import": "Review and Import",
    }
    phases = []
    for index, (phase, active_step) in enumerate(expected.items()):
        screenshot = tmp_path / f"step-{index}.png"
        screenshot.write_bytes(f"distinct-{index}".encode())
        phases.append(
            {
                "phase": phase,
                "screenshot": str(screenshot),
                "notes": {"active_step": active_step},
            }
        )

    assert _data_import_visual_evidence_failures(phases) == []


def test_data_import_visual_evidence_rejects_duplicate_or_wrong_step(tmp_path) -> None:
    preview = tmp_path / "preview.png"
    review = tmp_path / "review.png"
    preview.write_bytes(b"same-image")
    review.write_bytes(b"same-image")
    phases = [
        {
            "phase": "data_interpretation_scan_result",
            "screenshot": str(preview),
            "notes": {"active_step": "Choose EEG Data"},
        },
        {
            "phase": "data_interpretation_review_and_import",
            "screenshot": str(review),
            "notes": {"active_step": "Match Labels"},
        },
    ]

    failures = _data_import_visual_evidence_failures(phases)

    assert any("expected Review and Import" in failure for failure in failures)
    assert "Data Import walkthrough step screenshots are duplicated" in failures


def test_step_navigation_pixel_guard_rejects_unpainted_label(qtbot, tmp_path) -> None:
    widget = QWidget()
    qtbot.addWidget(widget)
    widget.resize(980, 110)
    full_titles = (
        "Choose EEG Data",
        "Load Labels",
        "Review Metadata",
        "Match Labels",
        "Review and Import",
    )
    labels: list[QLabel] = []
    for index, title in enumerate(full_titles, start=1):
        label = QLabel(f"{index}. {title}", widget)
        label.setGeometry(10 + (index - 1) * 190, 8, 180, 34)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        labels.append(label)
    cancel = QPushButton("Cancel", widget)
    cancel.setGeometry(10, 60, 90, 34)
    next_button = QPushButton("Next: Load Labels", widget)
    next_button.setObjectName("DataImportPrimaryButton")
    next_button.setGeometry(770, 60, 190, 34)
    apply_button = QPushButton("Confirm and Import", widget)
    apply_button.setObjectName("DataImportPrimaryButton")
    apply_button.setGeometry(770, 60, 190, 34)
    apply_button.hide()
    summary = QLabel("Found 1 EEG file and 1 label carrier.", widget)
    summary.setGeometry(300, 44, 300, 18)
    summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
    state = cast(Any, widget)
    state.step_labels = labels
    state.summary_label = summary
    state.cancel_button = cancel
    state.next_button = next_button
    state.apply_button = apply_button
    widget.show()
    qtbot.wait(20)

    empty = tmp_path / "empty.png"
    Image.new("RGB", (980, 110), "#1e1e1e").save(empty)
    with pytest.raises(RuntimeError, match="not fully rendered"):
        _assert_step_navigation_rendered(widget, empty)

    painted = tmp_path / "painted.png"
    image = Image.new("RGB", (980, 110), "#1e1e1e")
    ImageDraw.Draw(image).rectangle((10, 8, 189, 41), fill="#23303a")
    image.save(painted)
    with pytest.raises(RuntimeError, match="not fully rendered"):
        _assert_step_navigation_rendered(widget, painted)

    styled_blank = tmp_path / "styled-blank.png"
    image = Image.new("RGB", (980, 110), "#1e1e1e")
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (10, 8, 189, 41),
        fill="#23303a",
        outline="#5b7db1",
        width=1,
    )
    image.save(styled_blank)
    with pytest.raises(RuntimeError, match="not fully rendered"):
        _assert_step_navigation_rendered(widget, styled_blank)

    text_painted = tmp_path / "text-painted.png"
    assert widget.grab().save(str(text_painted))
    _assert_step_navigation_rendered(widget, text_painted)


@pytest.mark.parametrize("missing", ["step", "cancel", "primary"])
def test_step_navigation_contract_rejects_missing_expected_controls(
    qtbot,
    tmp_path,
    missing: str,
) -> None:
    widget = QWidget()
    qtbot.addWidget(widget)
    widget.resize(980, 110)
    labels = [
        QLabel(f"{index}. {title}", widget)
        for index, title in enumerate(
            (
                "Choose EEG Data",
                "Load Labels",
                "Review Metadata",
                "Match Labels",
                "Review and Import",
            ),
            start=1,
        )
    ]
    for index, label in enumerate(labels):
        label.setGeometry(10 + index * 190, 8, 180, 34)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    cancel = QPushButton("Cancel", widget)
    cancel.setGeometry(10, 60, 90, 34)
    primary = QPushButton("Next: Load Labels", widget)
    primary.setObjectName("DataImportPrimaryButton")
    primary.setGeometry(770, 60, 190, 34)
    hidden_apply = QPushButton("Confirm and Import", widget)
    hidden_apply.setObjectName("DataImportPrimaryButton")
    hidden_apply.hide()
    summary = QLabel("Found 1 EEG file and 1 label carrier.", widget)
    summary.setGeometry(300, 44, 300, 18)
    summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
    state = cast(Any, widget)
    state.step_labels = labels[:-1] if missing == "step" else labels
    state.summary_label = summary
    state.cancel_button = cancel
    state.next_button = primary
    state.apply_button = hidden_apply
    widget.show()
    qtbot.wait(20)
    if missing == "cancel":
        cancel.hide()
    elif missing == "primary":
        primary.hide()
    screenshot = tmp_path / f"missing-{missing}.png"
    assert widget.grab().save(str(screenshot))

    with pytest.raises(RuntimeError):
        _assert_step_navigation_rendered(widget, screenshot)


def test_import_review_rejects_missing_step_navigation_owner(qtbot, tmp_path) -> None:
    widget = QWidget()
    qtbot.addWidget(widget)
    widget.setObjectName("DataImportWizardDialog")
    widget.resize(400, 200)
    widget.show()
    screenshot = tmp_path / "missing-import-navigation.png"
    assert widget.grab().save(str(screenshot))

    with pytest.raises(RuntimeError, match="step navigation owner"):
        _assert_step_navigation_rendered(widget, screenshot)


def test_main_navigation_guard_uses_text_span_not_whole_button_area(
    qtbot, tmp_path
) -> None:
    widget = QWidget()
    qtbot.addWidget(widget)
    widget.resize(560, 70)
    buttons: list[QPushButton] = []
    for index, text in enumerate(
        ("Dataset", "Preprocess", "Training", "Evaluation", "Visualization")
    ):
        button = QPushButton(text, widget)
        button.setObjectName("NavButton")
        button.setGeometry(index * 105, 8, 105, 48)
        button.setStyleSheet(
            "background: #2d2d2d; color: #d0d0d0; border: none; font-weight: bold;"
        )
        buttons.append(button)
    cast(Any, widget).nav_btns = buttons
    widget.show()
    qtbot.wait(20)

    complete = tmp_path / "complete-navigation.png"
    assert widget.grab().save(str(complete))
    _assert_main_navigation_rendered(widget, complete)

    partial = tmp_path / "partial-navigation.png"
    image = Image.open(complete).convert("RGB")
    target = buttons[1]
    metrics = target.fontMetrics()
    expected_width = metrics.horizontalAdvance(target.text())
    expected_height = metrics.height()
    left = target.x() + (target.width() - expected_width) // 2 - 3
    top = target.y() + (target.height() - expected_height) // 2 - 3
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (left, top, left + expected_width + 6, top + expected_height + 6),
        fill="#2d2d2d",
    )
    draw.rectangle((left, top + 3, left + 5, top + expected_height), fill="#d0d0d0")
    image.save(partial)

    with pytest.raises(RuntimeError, match="text width painted"):
        _assert_main_navigation_rendered(widget, partial)


@pytest.mark.parametrize(
    "alignment",
    [
        Qt.AlignmentFlag.AlignLeft,
        Qt.AlignmentFlag.AlignHCenter,
        Qt.AlignmentFlag.AlignRight,
    ],
    ids=["left", "center", "right"],
)
def test_text_paint_guard_honors_label_alignment_and_contents_margins(
    qtbot,
    tmp_path,
    alignment: Qt.AlignmentFlag,
) -> None:
    root = QWidget()
    qtbot.addWidget(root)
    root.resize(620, 120)
    root.setStyleSheet("background: #202020;")
    label = QLabel("Interpretation summary is ready for review.", root)
    label.setGeometry(30, 30, 560, 44)
    label.setContentsMargins(32, 4, 24, 4)
    label.setAlignment(alignment | Qt.AlignmentFlag.AlignVCenter)
    label.setStyleSheet("color: #f2f2f2; background: #303030;")
    root.show()
    qtbot.wait(20)

    screenshot = tmp_path / f"aligned-{alignment.name}.png"
    assert root.grab().save(str(screenshot))

    walkthrough_module._assert_text_controls_rendered(
        root,
        screenshot,
        [label],
        surface_name="Aligned interpretation summary",
    )


def test_text_paint_guard_honors_word_wrap_and_rejects_real_label_clipping(
    qtbot,
    tmp_path,
) -> None:
    root = QWidget()
    qtbot.addWidget(root)
    root.resize(460, 230)
    root.setStyleSheet("background: #202020;")
    wrapped = QLabel(
        "Interpretation summary remains visible across wrapped evidence lines.",
        root,
    )
    wrapped.setGeometry(20, 20, 410, 100)
    wrapped.setContentsMargins(28, 8, 20, 8)
    wrapped.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
    wrapped.setWordWrap(True)
    wrapped.setStyleSheet("color: #f2f2f2; background: #303030;")
    clipped = QLabel("This interpretation summary is genuinely clipped.", root)
    clipped.setGeometry(20, 145, 140, 32)
    clipped.setContentsMargins(12, 2, 12, 2)
    clipped.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    clipped.setStyleSheet("color: #f2f2f2; background: #303030;")
    root.show()
    qtbot.wait(20)

    screenshot = tmp_path / "word-wrap-and-clipped.png"
    assert root.grab().save(str(screenshot))
    walkthrough_module._assert_text_controls_rendered(
        root,
        screenshot,
        [wrapped],
        surface_name="Wrapped interpretation summary",
    )

    with pytest.raises(RuntimeError, match=r"clipped|text width painted"):
        walkthrough_module._assert_text_controls_rendered(
            root,
            screenshot,
            [clipped],
            surface_name="Clipped interpretation summary",
        )


def test_main_window_rejects_missing_navigation_owner(qtbot, tmp_path) -> None:
    window = QMainWindow()
    qtbot.addWidget(window)
    window.resize(400, 200)
    window.show()
    screenshot = tmp_path / "missing-main-navigation.png"
    assert window.grab().save(str(screenshot))

    with pytest.raises(RuntimeError, match="missing navigation"):
        _assert_main_navigation_rendered(window, screenshot)


def test_workflow_sidebar_guard_requires_visible_painted_action(
    qtbot, tmp_path
) -> None:
    widget = QWidget()
    qtbot.addWidget(widget)
    widget.resize(420, 260)
    sidebar = QWidget(widget)
    sidebar.setObjectName("RightPanel")
    sidebar.setGeometry(150, 10, 250, 230)
    layout = QVBoxLayout(sidebar)
    action = QPushButton("Import file", sidebar)
    action.setStyleSheet(
        "background: #3a3a3a; color: #d8d8d8; border: none; "
        "padding-left: 12px; text-align: left;"
    )
    layout.addWidget(action)
    layout.addStretch()
    widget.show()
    qtbot.wait(20)

    complete = tmp_path / "sidebar-complete.png"
    assert widget.grab().save(str(complete))
    _assert_right_panels_rendered(widget, complete)

    blank = tmp_path / "sidebar-blank.png"
    Image.new("RGB", (420, 260), "#1e1e1e").save(blank)
    with pytest.raises(RuntimeError, match="does not match"):
        _assert_right_panels_rendered(widget, blank)

    action.hide()
    with pytest.raises(RuntimeError, match="no visible action"):
        _assert_right_panels_rendered(widget, complete)


def test_right_panel_guard_accepts_declared_read_only_information(
    qtbot,
    tmp_path,
) -> None:
    widget = QWidget()
    qtbot.addWidget(widget)
    widget.resize(420, 260)
    sidebar = QWidget(widget)
    sidebar.setObjectName("RightPanel")
    sidebar.setGeometry(150, 10, 250, 230)
    layout = QVBoxLayout(sidebar)
    layout.addWidget(QLabel("Aggregate Information", sidebar))
    layout.addWidget(QLabel("Total Files    3", sidebar))
    layout.addStretch()
    widget.show()
    qtbot.wait(20)

    screenshot = tmp_path / "read-only-right-panel.png"
    assert widget.grab().save(str(screenshot))

    _assert_right_panels_rendered(widget, screenshot)


def test_right_panel_guard_accepts_compact_main_window_layout(
    qtbot,
    tmp_path,
) -> None:
    window = QMainWindow()
    qtbot.addWidget(window)
    window.resize(760, 520)
    central = QWidget(window)
    window.setCentralWidget(central)
    compact_navigation = QComboBox(central)
    compact_navigation.addItems(["Dataset", "Evaluation"])
    compact_navigation.setGeometry(10, 10, 170, 32)
    window_state = cast(Any, window)
    window_state.nav_btns = [QPushButton("Dataset", central)]
    window_state.stack = object()
    window_state.compact_nav_combo = compact_navigation
    window.show()
    qtbot.wait(20)

    screenshot = tmp_path / "compact-main-window.png"
    assert window.grab().save(str(screenshot))

    _assert_right_panels_rendered(window, screenshot)


def test_assistant_loading_guard_requires_modes_and_send_to_be_painted(
    qtbot,
    tmp_path,
) -> None:
    root = QWidget()
    qtbot.addWidget(root)
    root.resize(420, 240)
    root_layout = QVBoxLayout(root)
    panel = QWidget(root)
    panel.setObjectName("AssistantPanel")
    panel_layout = QVBoxLayout(panel)
    control_panel = QWidget(panel)
    control_panel.setObjectName("ControlPanel")
    control_layout = QVBoxLayout(control_panel)
    mode_row = QHBoxLayout()
    ask_mode = QPushButton("One step", control_panel)
    workflow_mode = QPushButton("Guided workflow", control_panel)
    mode_row.addWidget(ask_mode)
    mode_row.addWidget(workflow_mode)
    control_layout.addLayout(mode_row)
    input_field = QLineEdit(control_panel)
    input_field.setPlaceholderText("Ask about the current workflow")
    control_layout.addWidget(input_field)
    send = QPushButton("Send", control_panel)
    control_layout.addWidget(send)
    empty_action = QPushButton("Scan data source", panel)
    empty_action.setAccessibleName("Scan data source")
    panel_layout.addWidget(empty_action)
    panel_layout.addStretch()
    panel_layout.addWidget(control_panel)
    root_layout.addWidget(panel)
    panel_state = cast(Any, panel)
    panel_state.ask_mode_btn = ask_mode
    panel_state.workflow_mode_btn = workflow_mode
    panel_state.input_field = input_field
    panel_state.send_btn = send
    panel_state.empty_state_action_button = empty_action
    panel_state.is_processing = False
    root.show()
    qtbot.wait(20)

    complete = tmp_path / "assistant-loading-controls.png"
    assert root.grab().save(str(complete))
    _assert_assistant_dock_rendered(root, complete)

    blank = tmp_path / "assistant-loading-controls-blank.png"
    Image.new("RGB", (420, 240), "#1e1e1e").save(blank)
    with pytest.raises(
        RuntimeError,
        match=r"foreground coverage|text width painted",
    ):
        _assert_assistant_dock_rendered(root, blank)

    workflow_mode.hide()
    with pytest.raises(RuntimeError, match="control is hidden"):
        _assert_assistant_dock_rendered(root, complete)

    workflow_mode.show()
    empty_action.setAccessibleName("stale action")
    with pytest.raises(RuntimeError, match="current action copy"):
        _assert_assistant_dock_rendered(root, complete)


def test_assistant_processing_guard_requires_stop_action(qtbot, tmp_path) -> None:
    root = QWidget()
    qtbot.addWidget(root)
    root.resize(420, 180)
    panel = QWidget(root)
    panel.setObjectName("AssistantPanel")
    panel.setGeometry(0, 0, 420, 180)
    ask_mode = QPushButton("One step", panel)
    ask_mode.setGeometry(10, 20, 180, 34)
    workflow_mode = QPushButton("Guided workflow", panel)
    workflow_mode.setGeometry(200, 20, 200, 34)
    send = QPushButton("Send", panel)
    send.setGeometry(310, 120, 90, 34)
    panel_state = cast(Any, panel)
    panel_state.ask_mode_btn = ask_mode
    panel_state.workflow_mode_btn = workflow_mode
    panel_state.send_btn = send
    panel_state.is_processing = True
    root.show()
    qtbot.wait(20)
    screenshot = tmp_path / "assistant-processing-stale-send.png"
    assert root.grab().save(str(screenshot))

    with pytest.raises(RuntimeError, match="expected Stop"):
        _assert_assistant_dock_rendered(root, screenshot)


def test_assistant_empty_capture_requires_current_action_button(
    qtbot,
    tmp_path,
) -> None:
    dock = QDockWidget()
    qtbot.addWidget(dock)
    panel = QWidget(dock)
    panel.setObjectName("AssistantPanel")
    layout = QVBoxLayout(panel)
    ask_mode = QPushButton("One step", panel)
    workflow_mode = QPushButton("Guided workflow", panel)
    send = QPushButton("Send", panel)
    for control in (ask_mode, workflow_mode, send):
        layout.addWidget(control)
    state = cast(Any, panel)
    state.ask_mode_btn = ask_mode
    state.workflow_mode_btn = workflow_mode
    state.send_btn = send
    state.is_processing = False
    dock.setWidget(panel)
    dock.resize(420, 240)
    dock.show()
    screenshot = tmp_path / SCREENSHOT_NAMES["assistant_empty"]
    assert dock.grab().save(str(screenshot))

    with pytest.raises(RuntimeError, match="visible action button"):
        _assert_assistant_dock_rendered(dock, screenshot)


def test_failed_artifact_run_does_not_mix_with_latest_success(tmp_path) -> None:
    latest = tmp_path / "walkthrough"
    latest.mkdir()
    (latest / "old.png").write_bytes(b"old-screenshot")
    (latest / "human-like-walkthrough.md").write_text("old report", encoding="utf-8")
    staging = tmp_path / ".walkthrough-staging-run-failed"
    staging.mkdir()
    new_image = staging / "new.png"
    new_image.write_bytes(b"new-screenshot")
    payload = {
        "status": "failed",
        "screenshots": {"new": str(new_image)},
        "phases": [],
        "pass_fail_summary": {"passed": False},
    }

    published = publish_artifact_run(
        staging_dir=staging,
        output_dir=latest,
        payload=payload,
        run_id="run-failed",
    )

    assert published == tmp_path / "walkthrough-runs" / "run-failed"
    assert (latest / "old.png").read_bytes() == b"old-screenshot"
    assert (latest / "human-like-walkthrough.md").read_text(encoding="utf-8") == (
        "old report"
    )
    assert (published / "new.png").read_bytes() == b"new-screenshot"
    assert not (published / "old.png").exists()
    assert payload["screenshots"]["new"] == str(published / "new.png")
    assert payload["artifact_run"]["screenshot_sha256"]["new"]


def test_required_command_payload_reads_process_local_result_payload() -> None:
    result = SimpleNamespace(
        success=True,
        command_name="scan_source",
        message="Scan ready.",
        error_type=SimpleNamespace(value="none"),
        diagnostics={"payload_type": "scan_result"},
        runtime={"scan_result": {"scan_id": "scan:1", "eeg_files": ["a.fif"]}},
    )

    payload = _required_command_payload(
        result,
        expected_payload_type="scan_result",
        required_fields=("scan_result",),
    )

    assert payload["scan_result"]["scan_id"] == "scan:1"


def test_required_command_payload_reports_contract_mismatch_without_key_error() -> None:
    result = SimpleNamespace(
        success=True,
        command_name="scan_source",
        message="Scan ready.",
        error_type=SimpleNamespace(value="none"),
        diagnostics={"payload_type": "state_snapshot"},
        runtime={},
    )

    with pytest.raises(
        RuntimeError,
        match=r"scan_source.*expected payload_type 'scan_result'.*state_snapshot",
    ):
        _required_command_payload(
            result,
            expected_payload_type="scan_result",
            required_fields=("scan_result",),
        )


def test_walkthrough_source_does_not_index_command_diagnostics_payloads() -> None:
    source = inspect.getsource(walkthrough_module)

    assert '.diagnostics["scan_result"]' not in source
    assert '.diagnostics["preview"]' not in source
    assert '.diagnostics["validation_decision"]' not in source
    assert '.diagnostics.get("validation_decision"' not in source


def test_main_returns_nonzero_when_walkthrough_artifact_fails(
    monkeypatch,
    tmp_path,
) -> None:
    class FakeApplication:
        def setStyle(self, _style: str) -> None:
            return None

    failed_payload = {
        "status": "failed",
        "failure_reason": "walkthrough failed",
        "screenshots": {},
        "phases": [],
        "pass_fail_summary": {"passed": False},
    }
    output_dir = tmp_path / "walkthrough-runs" / "current"
    monkeypatch.setattr(
        walkthrough_module, "QApplication", lambda _argv: FakeApplication()
    )
    monkeypatch.setattr(
        walkthrough_module,
        "capture_walkthrough",
        lambda _app, _staging: failed_payload,
    )
    monkeypatch.setattr(
        walkthrough_module,
        "publish_artifact_run",
        lambda **_kwargs: output_dir,
    )
    monkeypatch.setattr(
        walkthrough_module.sys,
        "argv",
        ["capture_human_like_product_walkthrough.py", "--output-dir", str(output_dir)],
    )

    assert walkthrough_module.main() == 1


def test_failed_markdown_surfaces_manifest_fingerprint_and_dirty_evidence() -> None:
    payload = {
        "status": "failed",
        "failure_reason": "scan contract failed",
        "claim_boundary": claim_boundary(),
        "artifact_run": {
            "run_id": "run-failed",
            "generated_at_utc": "2026-07-16T00:00:00+00:00",
            "git_revision": "abc123",
            "working_tree_dirty": True,
            "source_fingerprint": "source-sha256",
            "screenshot_sha256": {},
        },
        "phases": [],
        "screenshots": {},
        "pass_fail_summary": {"passed": False},
    }

    rendered = render_markdown(payload)

    assert "working tree dirty: `True`" in rendered
    assert "source fingerprint: `source-sha256`" in rendered


def test_default_artifact_entry_is_the_versioned_current_run() -> None:
    assert DEFAULT_OUTPUT_DIR.name == "current"
    assert DEFAULT_OUTPUT_DIR.parent.name == "human-like-walkthrough-runs"


def test_failed_current_artifact_run_is_saved_beside_current(tmp_path) -> None:
    latest = tmp_path / "human-like-walkthrough-runs" / "current"
    latest.mkdir(parents=True)
    (latest / "old.png").write_bytes(b"old-screenshot")
    staging = tmp_path / ".walkthrough-staging-run-failed"
    staging.mkdir()
    new_image = staging / "new.png"
    new_image.write_bytes(b"new-screenshot")
    payload = {
        "status": "failed",
        "screenshots": {"new": str(new_image)},
        "phases": [],
        "pass_fail_summary": {"passed": False},
    }

    published = publish_artifact_run(
        staging_dir=staging,
        output_dir=latest,
        payload=payload,
        run_id="run-failed",
    )

    assert published == latest.parent / "run-failed"
    assert (latest / "old.png").read_bytes() == b"old-screenshot"
    assert (published / "new.png").read_bytes() == b"new-screenshot"


def test_successful_artifact_run_replaces_latest_as_one_directory(tmp_path) -> None:
    latest = tmp_path / "walkthrough"
    latest.mkdir()
    (latest / "stale.png").write_bytes(b"stale")
    staging = tmp_path / ".walkthrough-staging-run-passed"
    staging.mkdir()
    current = staging / "current.png"
    current.write_bytes(b"current")
    payload = {
        "status": "passed",
        "screenshots": {"current": str(current)},
        "phases": [],
        "pass_fail_summary": {"passed": True},
    }

    published = publish_artifact_run(
        staging_dir=staging,
        output_dir=latest,
        payload=payload,
        run_id="run-passed",
    )

    assert published == latest
    assert (latest / "current.png").read_bytes() == b"current"
    assert not (latest / "stale.png").exists()
    assert payload["screenshots"]["current"] == str(latest / "current.png")
    assert payload["artifact_run"]["status"] == "passed"


def test_settle_window_geometry_reapplies_target_after_startup_timer(qtbot) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    widget = QWidget()
    qtbot.addWidget(widget)
    widget.resize(QSize(420, 360))
    widget.show()
    QTimer.singleShot(0, lambda: widget.resize(QSize(640, 480)))

    target = QSize(900, 760)
    settle_window_geometry_for_capture(
        app,
        widget,
        target,
        recovery_wait_ms=20,
    )

    assert widget.size() == target


def test_validate_walkthrough_payload_rejects_missing_human_boundary() -> None:
    payload = _base_payload()
    payload["claim_boundary"] = "Automated replay."

    ok, reason = validate_walkthrough_payload(payload, require_files=False)

    assert ok is False
    assert "human acceptance" in reason


def test_forbidden_visible_text_flags_raw_tool_syntax() -> None:
    offenders = forbidden_visible_text(
        [
            "The dataset is ready.",
            '{"tool_name": "scan_source"}',
            "Traceback:",
            "configure_training is blocked.",
            "legacy load_data fallback",
            "Recipe trace saved scan:scan-1",
            "Saved choices:metadata_overrides",
        ],
    )

    assert '{"tool_name": "scan_source"}' in offenders
    assert "Traceback:" in offenders
    assert "configure_training is blocked." in offenders
    assert "legacy load_data fallback" in offenders
    assert "Recipe trace saved scan:scan-1" in offenders
    assert "Saved choices:metadata_overrides" in offenders


def test_visible_text_snapshot_includes_chat_bubble_text(qtbot) -> None:
    widget = QWidget()
    qtbot.addWidget(widget)
    layout = QVBoxLayout(widget)
    bubble_text = QTextBrowser()
    bubble_text.setMarkdown(
        "Choose a file, folder, BIDS root, or saved recipe before I can scan it."
    )
    layout.addWidget(bubble_text)
    widget.show()

    texts = visible_text_snapshot(widget)

    assert (
        "Choose a file, folder, BIDS root, or saved recipe before I can scan it."
        in texts
    )


def test_build_pass_fail_summary_requires_all_phases() -> None:
    phases = [
        {
            "phase": REQUIRED_PHASES[0],
            "visible_text": [],
        }
    ]

    summary = build_pass_fail_summary(phases, screenshots={})

    assert summary["passed"] is False
    assert "missing phase" in "; ".join(summary["failed_checks"])


def test_workflow_contract_rejects_failed_happy_path_command() -> None:
    phases = [
        {
            "phase": "epoch_creation",
            "workflow_state": {
                "epoch": {"exists": False},
                "dataset": {"available": False},
            },
            "notes": {
                "epoch": {
                    "command": "create_epoch",
                    "ok": False,
                    "error_type": "precondition",
                },
                "dataset": {
                    "command": "generate_dataset",
                    "ok": False,
                    "error_type": "precondition",
                },
            },
        },
    ]

    failures = build_workflow_contract_failures(phases)

    assert "epoch_creation command create_epoch did not succeed" in failures
    assert "epoch_creation did not produce epochs" in failures


def test_workflow_contract_requires_reapply_after_recipe_reload() -> None:
    phases = [
        {
            "phase": "data_interpretation_reapply_recipe",
            "workflow_state": {},
            "notes": {
                "reapply": {"command": "apply_interpretation", "ok": False},
            },
        }
    ]

    failures = build_workflow_contract_failures(phases)

    assert (
        "data_interpretation_reapply_recipe command apply_interpretation did not succeed"
        in failures
    )


def test_workflow_contract_requires_observed_training_completion() -> None:
    phases = [
        {
            "phase": "training_readiness",
            "workflow_state": {"training": {"finished_run_count": 1}},
            "notes": {
                "training": {"command": "configure_training", "ok": True},
                "train": {"command": "train", "ok": True},
                "training_wait": {"completed": False},
            },
        }
    ]

    failures = build_workflow_contract_failures(phases)

    assert "training_readiness did not observe training completion" in failures


def test_walkthrough_claim_marks_deterministic_manager_signal_boundary() -> None:
    boundary = claim_boundary()

    assert "AgentManager and Qt signals" in boundary
    assert "not direct ChatController injection" in boundary
    assert "not local-model or tool-call correctness evidence" in boundary


def test_processing_phase_is_required_and_has_a_named_screenshot() -> None:
    assert "assistant_processing_state" in REQUIRED_PHASES
    assert SCREENSHOT_NAMES["assistant_processing"].endswith("assistant-processing.png")


def test_visualization_has_its_own_visible_walkthrough_phase() -> None:
    assert "visualization_readiness" in REQUIRED_PHASES
    assert SCREENSHOT_NAMES["visualization_readiness"].endswith(
        "visualization-readiness.png"
    )


def test_assistant_processing_contract_accepts_readable_loading_evidence() -> None:
    review = build_assistant_processing_contract_review(
        [_valid_assistant_processing_phase(), _valid_assistant_idle_phase()]
    )

    assert review["passed"] is True
    assert review["checked_phases"] == 1
    assert review["findings"] == []
    assert review["evidence"]["turn_activity"]["phase"] == "working"
    assert review["evidence"]["stopping_state"]["turn_activity"]["phase"] == (
        "stopping"
    )
    assert review["evidence"]["stop_button"]["text"] == "Stop"


@pytest.mark.parametrize(
    ("mutation", "expected_finding"),
    [
        ("composer_enabled", "composer input is not disabled"),
        (
            "workflow_unlocked",
            "Guided workflow selection evidence is missing",
        ),
        ("status_hidden", "typed turn activity is not visible"),
        ("status_overflow", "turn activity text overflows"),
        ("invalid_stopping", "valid Stopping state"),
        ("missing_stop_text", "visible Stop button evidence is missing"),
        ("not_restored", "did not restore the idle state"),
        ("missing_terminal", "terminal cancellation result is missing"),
    ],
)
def test_assistant_processing_contract_rejects_incomplete_loading_evidence(
    mutation: str,
    expected_finding: str,
) -> None:
    phase = deepcopy(_valid_assistant_processing_phase())
    idle_phase = _valid_assistant_idle_phase()
    processing = phase["notes"]["assistant_processing"]
    restored = phase["notes"]["restored_state"]
    if mutation == "composer_enabled":
        processing["composer_input_enabled"] = True
    elif mutation == "workflow_unlocked":
        processing["workflow_mode"]["enabled"] = True
    elif mutation == "status_hidden":
        processing["turn_activity"]["primary_status"]["visible"] = False
    elif mutation == "status_overflow":
        processing["turn_activity"]["primary_status"]["fits_height"] = False
    elif mutation == "invalid_stopping":
        phase["notes"]["stopping_state"]["turn_activity"]["phase"] = "idle"
    elif mutation == "missing_stop_text":
        phase["visible_text"].remove("Stop")
    elif mutation == "not_restored":
        restored["execution_mode"] = "single"
    elif mutation == "missing_terminal":
        idle_phase["notes"]["assistant_cancelled_turn"]["terminal_messages"] = []

    review = build_assistant_processing_contract_review([phase, idle_phase])

    assert review["passed"] is False
    assert any(expected_finding in finding for finding in review["findings"])


def test_validate_walkthrough_payload_rejects_missing_processing_screenshot_key() -> (
    None
):
    payload = _base_payload()
    payload["screenshots"].pop("assistant_processing")

    ok, reason = validate_walkthrough_payload(payload, require_files=False)

    assert ok is False
    assert "assistant processing screenshot" in reason


def test_validate_walkthrough_payload_rejects_stale_processing_pass_claim() -> None:
    payload = _base_payload()
    processing_phase = next(
        phase
        for phase in payload["phases"]
        if phase["phase"] == "assistant_processing_state"
    )
    processing_phase["notes"]["assistant_processing"]["composer_input_enabled"] = True
    assert payload["ui_quality_review"]["assistant_processing_contract_review"][
        "passed"
    ]

    ok, reason = validate_walkthrough_payload(payload, require_files=False)

    assert ok is False
    assert "composer input is not disabled" in reason


def test_nearly_black_guard_rejects_uniform_dark_ui_frame(tmp_path) -> None:
    blank = tmp_path / "blank-dark-frame.png"
    Image.new("RGB", (640, 480), "#2d2d2d").save(blank)

    assert is_nearly_black(blank) is True


def test_region_content_gate_rejects_ninety_nine_percent_blank_two_line_frame(
    tmp_path,
) -> None:
    path = tmp_path / "two-lines.png"
    image = Image.new("RGB", (640, 480), "#1e1e1e")
    draw = ImageDraw.Draw(image)
    draw.line((0, 160, 639, 160), fill="#f5f5f5", width=1)
    draw.line((0, 320, 639, 320), fill="#f5f5f5", width=1)
    image.save(path)

    with pytest.raises(RuntimeError, match="foreground coverage"):
        walkthrough_module._assert_region_foreground_content(
            path,
            (0, 0, 640, 480),
            surface_name="Assistant content",
        )


def test_assistant_stage_copy_review_rejects_results_with_import_heading() -> None:
    review = build_assistant_stage_copy_review(
        [
            {
                "phase": "assistant_empty_state",
                "visible_text": ["Start with your EEG data", "Results available"],
                "workflow_state": {
                    "raw": {"loaded": True},
                    "training": {"is_running": False},
                    "evaluation": {"finished_runs": 1, "metrics_available": True},
                },
            }
        ]
    )

    assert review["passed"] is False
    assert review["findings"][0]["expected_title"] == "Explore your results"


def test_assistant_stage_copy_review_accepts_stage_aware_results_heading() -> None:
    review = build_assistant_stage_copy_review(
        [
            {
                "phase": "assistant_empty_state",
                "visible_text": ["Explore your results", "Results available"],
                "workflow_state": {
                    "raw": {"loaded": True},
                    "training": {"is_running": False},
                    "evaluation": {"finished_runs": 1, "metrics_available": True},
                },
            }
        ]
    )

    assert review == {"passed": True, "checked_states": 1, "findings": []}


@pytest.mark.parametrize(
    "platform_name",
    ["offscreen", "minimal", "xcb", " OFFSCREEN "],
)
def test_virtual_qt_platform_uses_widget_backing_store(platform_name: str) -> None:
    assert not _use_native_window_capture(
        is_window=True,
        platform_name=platform_name,
        screen_available=True,
    )


def test_real_qt_window_platform_uses_native_capture() -> None:
    assert _use_native_window_capture(
        is_window=True,
        platform_name="windows",
        screen_available=True,
    )


def test_child_widget_or_missing_screen_uses_widget_capture() -> None:
    assert not _use_native_window_capture(
        is_window=False,
        platform_name="windows",
        screen_available=True,
    )
    assert not _use_native_window_capture(
        is_window=True,
        platform_name="windows",
        screen_available=False,
    )


def test_build_pass_fail_summary_flags_unsettled_threads() -> None:
    phases = [
        {
            "phase": phase,
            "visible_text": [],
            "button_state": [],
            "workflow_state": {},
            "screenshot": "",
        }
        for phase in REQUIRED_PHASES
    ]

    summary = build_pass_fail_summary(
        phases,
        screenshots={},
        resource_notes=[
            {
                "label": "start",
                "python_threads": 1,
                "qt_active_threads": 0,
                "max_rss_kb": 100,
                "current_rss_kb": 100,
            },
            {
                "label": "after_close",
                "python_threads": 4,
                "qt_active_threads": 2,
                "max_rss_kb": 900000,
                "current_rss_kb": 1_300_100,
            },
        ],
    )

    assert summary["passed"] is False
    failed = "; ".join(summary["failed_checks"])
    assert "Python threads did not settle" in failed
    assert "Qt thread pool still active" in failed
    assert "RSS smoke delta exceeded" in failed


def test_resource_smoke_records_max_rss_without_failing_high_water_only() -> None:
    summary = build_resource_smoke_summary(
        [
            {
                "label": "start",
                "python_threads": 1,
                "qt_active_threads": 0,
                "max_rss_kb": 100,
                "current_rss_kb": 100,
            },
            {
                "label": "after_close",
                "python_threads": 1,
                "qt_active_threads": 0,
                "max_rss_kb": 900000,
                "current_rss_kb": 200,
            },
        ],
    )

    assert summary["passed"] is True
    assert summary["rss_growth_kb"] == 100
    assert summary["max_rss_growth_kb"] == 899900


def test_walkthrough_resource_finalization_samples_after_qt_cleanup(qapp) -> None:
    payload = _base_payload()
    payload["resource_notes"] = [
        {
            "label": "start",
            "python_threads": 1,
            "qt_active_threads": 0,
            "max_rss_kb": 100,
            "current_rss_kb": 100,
        },
        {
            "label": "before_close",
            "python_threads": 1,
            "qt_active_threads": 0,
            "max_rss_kb": 150,
            "current_rss_kb": 150,
        },
    ]
    sampled = {
        "label": "after_close",
        "python_threads": 1,
        "qt_active_threads": 0,
        "max_rss_kb": 160,
        "current_rss_kb": 120,
    }

    with (
        patch.object(qapp, "sendPostedEvents") as send_posted,
        patch.object(qapp, "processEvents") as process_events,
        patch(
            "scripts.dev.capture_human_like_product_walkthrough.gc.collect"
        ) as collect,
        patch(
            "scripts.dev.capture_human_like_product_walkthrough.resource_snapshot",
            return_value=sampled,
        ),
    ):
        finalized = finalize_walkthrough_after_close(
            qapp,
            payload,
            started_at=0.0,
        )

    assert send_posted.call_count == 3
    assert process_events.call_count == 3
    assert collect.call_count == 3
    after_close = finalized["resource_notes"][-1]
    assert after_close["label"] == "after_close"
    assert after_close["measurement_boundary"] == (
        "after_walkthrough_return_and_qt_cleanup"
    )
    assert finalized["pass_fail_summary"]["resource_smoke"]["rss_growth_kb"] == 20


def test_walkthrough_finalization_preserves_the_root_capture_failure(qapp) -> None:
    payload = {
        "status": "failed",
        "failure_reason": "Screenshot is nearly black: 01-main-initial.png.",
        "claim_boundary": "Automated replay only.",
        "phases": [],
        "screenshots": {},
        "pass_fail_summary": {"passed": False, "failed_checks": []},
    }

    with patch(
        "scripts.dev.capture_human_like_product_walkthrough.resource_snapshot",
        return_value={
            "label": "after_close",
            "python_threads": 1,
            "qt_active_threads": 0,
            "max_rss_kb": 100,
            "current_rss_kb": 100,
        },
    ):
        finalized = finalize_walkthrough_after_close(
            qapp,
            payload,
            started_at=0.0,
        )

    assert finalized["failure_reason"] == payload["failure_reason"]
    assert (
        finalized["pass_fail_summary"]["failed_checks"][0] == payload["failure_reason"]
    )


def test_observable_evidence_summary_indexes_phase_snapshots() -> None:
    payload = _base_payload()

    evidence = payload["observable_evidence"]

    assert set(evidence["visible_text_snapshots"]) == set(REQUIRED_PHASES)
    assert evidence["button_states"][REQUIRED_PHASES[0]][0]["text"] == "Send"
    assert REQUIRED_PHASES[0] in evidence["backend_state_snapshots"]
    assert (
        evidence["assistant_processing_snapshots"]["assistant_processing_state"][
            "workflow_status"
        ]["text"]
        == "Checking data"
    )


def test_observable_evidence_summary_indexes_ui_geometry() -> None:
    phases = _base_payload()["phases"]
    phases[0]["notes"] = {
        "ui_geometry": {
            "dataset_table": {
                "header_length": 640,
                "viewport_width": 640,
                "horizontal_scrollbar_max": 0,
            }
        }
    }

    evidence = build_observable_evidence_summary(phases)

    assert (
        evidence["ui_geometry_snapshots"][REQUIRED_PHASES[0]]["dataset_table"][
            "viewport_width"
        ]
        == 640
    )


def test_observable_evidence_summary_indexes_chat_geometry() -> None:
    phases = _base_payload()["phases"]
    phases[0]["notes"] = {
        "chat_geometry": {
            "latest_message_bottom_y": 540,
            "composer_top_y": 560,
            "latest_message_clear_of_composer": True,
        }
    }

    evidence = build_observable_evidence_summary(phases)

    assert (
        evidence["chat_geometry_snapshots"][REQUIRED_PHASES[0]][
            "latest_message_bottom_y"
        ]
        == 540
    )


def test_validate_walkthrough_payload_requires_observable_evidence() -> None:
    payload = _base_payload()
    payload.pop("observable_evidence")

    ok, reason = validate_walkthrough_payload(payload, require_files=False)

    assert ok is False
    assert "observable evidence" in reason


def test_validate_walkthrough_payload_requires_ui_quality_pass() -> None:
    payload = _base_payload()
    payload["ui_quality_review"]["automated_checks_passed"] = False

    ok, reason = validate_walkthrough_payload(payload, require_files=False)

    assert ok is False
    assert "ui quality" in reason


def test_build_ui_quality_review_flags_forbidden_visible_text() -> None:
    phases = [
        {
            "phase": "assistant",
            "screenshot": "",
            "visible_text": ["Traceback: hidden"],
            "button_state": [],
            "workflow_state": {},
        }
    ]

    review = build_ui_quality_review(phases, screenshots={})

    assert review["automated_checks_passed"] is False
    assert review["forbidden_visible_text"][0]["phase"] == "assistant"


def test_build_ui_quality_review_does_not_treat_zero_phases_as_coverage() -> None:
    review = build_ui_quality_review([], screenshots={})

    assert review["phase_snapshot_coverage"] is False
    assert review["automated_checks_passed"] is False


def test_build_ui_quality_review_flags_overflowing_table_geometry() -> None:
    phases = [
        {
            "phase": "data_interpretation_preview",
            "screenshot": "",
            "visible_text": ["Interpretation Preview"],
            "button_state": [],
            "workflow_state": {},
            "notes": {
                "ui_geometry": {
                    "review_summary": {
                        "header_length": 1200,
                        "viewport_width": 900,
                        "horizontal_scrollbar_max": 40,
                        "headers": ["Item", "Status", "Details"],
                    }
                }
            },
        }
    ]

    review = build_ui_quality_review(phases, screenshots={})

    assert review["automated_checks_passed"] is False
    assert review["table_geometry_review"]["passed"] is False
    assert review["table_geometry_review"]["findings"][0]["phase"] == (
        "data_interpretation_preview"
    )


def test_build_ui_quality_review_flags_table_gap_to_sidebar() -> None:
    phases = [
        {
            "phase": "dataset_loaded",
            "screenshot": "",
            "visible_text": ["Dataset"],
            "button_state": [],
            "workflow_state": {},
            "notes": {
                "ui_geometry": {
                    "dataset_table": {
                        "header_length": 640,
                        "viewport_width": 640,
                        "horizontal_scrollbar_max": 0,
                        "right_gap_to_boundary": 220,
                        "headers": ["File", "Subject", "Events"],
                    }
                }
            },
        }
    ]

    review = build_ui_quality_review(phases, screenshots={})

    assert review["automated_checks_passed"] is False
    finding = review["table_geometry_review"]["findings"][0]
    assert finding["phase"] == "dataset_loaded"
    assert finding["right_gap_to_boundary"] == 220
    assert finding["fills_content_boundary"] is False


def test_build_ui_quality_review_flags_clipped_table_rows() -> None:
    phases = [
        {
            "phase": "data_interpretation_preview",
            "screenshot": "",
            "visible_text": ["Interpretation Preview"],
            "button_state": [],
            "workflow_state": {},
            "notes": {
                "ui_geometry": {
                    "review_summary": {
                        "header_length": 900,
                        "viewport_width": 900,
                        "horizontal_scrollbar_max": 0,
                        "vertical_scrollbar_max": 4,
                        "partial_visible_rows": [5],
                        "headers": ["Item", "Status", "Details"],
                    }
                }
            },
        }
    ]

    review = build_ui_quality_review(phases, screenshots={})

    assert review["automated_checks_passed"] is False
    finding = review["table_geometry_review"]["findings"][0]
    assert finding["phase"] == "data_interpretation_preview"
    assert finding["partial_visible_rows"] == [5]
    assert finding["shows_only_complete_rows"] is False


def test_build_chat_geometry_review_flags_bubble_composer_overlap() -> None:
    phases = [
        {
            "phase": "assistant_narrow_panel",
            "notes": {
                "chat_geometry": {
                    "visible_bubble_count": 8,
                    "latest_message_bottom_y": 644,
                    "composer_top_y": 591,
                    "bottom_clearance_px": -53,
                    "scrollbar_value": 0,
                    "scrollbar_max": 65,
                    "latest_message_clear_of_composer": False,
                    "scrollbar_at_bottom": False,
                }
            },
        }
    ]

    review = build_chat_geometry_review(phases)

    assert review["passed"] is False
    assert review["findings"][0]["phase"] == "assistant_narrow_panel"


def test_chat_panel_geometry_reports_latest_bubble_clearance(qtbot) -> None:
    widget = QWidget()
    qtbot.addWidget(widget)
    layout = QVBoxLayout(widget)
    bubble = MessageBubble("Assistant response ready.", is_user=False)
    layout.addWidget(bubble)
    composer = QWidget()
    composer.setObjectName("ControlPanel")
    layout.addWidget(composer)
    chat_widget = cast(Any, widget)
    chat_widget.scroll_area = type(
        "ScrollAreaStub",
        (),
        {"verticalScrollBar": lambda self: None},
    )()
    chat_widget.control_panel = composer
    widget.resize(320, 160)
    widget.show()
    bubble.adjust_width(300)
    qtbot.wait(0)

    geometry = chat_panel_geometry(chat_widget)

    assert geometry["visible_bubble_count"] == 1
    assert geometry["latest_message_clear_of_composer"] is True


def test_dataset_page_geometry_includes_aggregate_info_table(qtbot) -> None:
    window = _WindowStub()
    qtbot.addWidget(window.dataset_panel)
    qtbot.addWidget(window.dataset_panel.sidebar.info_panel)

    geometry = dataset_page_geometry(cast(Any, window))

    assert "dataset_table" in geometry
    assert "aggregate_info" in geometry
    assert len(geometry["aggregate_info"]["rows"]) == 13
    assert geometry["aggregate_info"]["partial_visible_rows"] == []


def test_merge_ui_quality_into_pass_fail_summary_blocks_passed_status() -> None:
    summary = {
        "passed": True,
        "failed_checks": [],
    }
    review = {
        "automated_checks_passed": False,
        "table_geometry_review": {"passed": False},
    }

    merged = merge_ui_quality_into_pass_fail_summary(summary, review)

    assert merged["passed"] is False
    assert "ui quality review did not pass" in merged["failed_checks"]


def test_render_markdown_keeps_claim_boundary_and_transcripts() -> None:
    rendered = render_markdown(_base_payload())

    assert "Human-Like Product Walkthrough" in rendered
    assert "not human Windows desktop acceptance" in rendered
    assert "Observable Evidence" in rendered
    assert "UI Quality Review" in rendered
    assert "The dataset is ready." in rendered
    assert "Remaining Human Verification" in rendered


def test_render_eval_dashboard_html_converts_markdown_tables() -> None:
    markdown = """# XBrainLab Tool-Call Eval Dashboard

## Model Comparison

| Runner | Model | Cases | Pass Rate |
| --- | --- | --- | --- |
| deterministic | deterministic | 121 | 100.00% |

## Metric Pass Rates

| Metric | deterministic |
| --- | --- |
| intent | 100.00% |
"""

    html = render_eval_dashboard_html(markdown)

    assert "<table>" in html
    assert "<th>Runner</th>" in html
    assert "<td>deterministic</td>" in html
    assert "| Runner |" not in html
    assert "background: #181818" in html


def test_render_eval_dashboard_html_surfaces_claim_boundary_first() -> None:
    markdown = """# XBrainLab Tool-Call Eval Dashboard

## Model Comparison

| Runner | Cases |
| --- | ---: |
| deterministic | 121 |

## Thesis Claim Boundary

- Supports this benchmark slice.
- Does not claim product completion.
"""

    html = render_eval_dashboard_html(markdown)

    assert 'class="claim-boundary"' in html
    assert "Does not claim product completion." in html
    assert html.index("Claim Boundary") < html.index("Model Comparison")


def test_apply_review_choices_uses_visible_file_pairing_controls(qtbot) -> None:
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": [
                "/tmp/source/sub-01_task-mi_run-1_raw.fif",
                "/tmp/source/sub-01_task-mi_run-2_raw.fif",
            ],
            "label_carriers": ["/tmp/source/events.tsv"],
        },
        preview={"event_roles": {"trial_type": "class label candidate"}},
        validation_decision={"decision": "needs_confirmation"},
    )
    qtbot.addWidget(dialog)

    role_item = None
    for index in range(dialog.event_tree.topLevelItemCount()):
        item = dialog.event_tree.topLevelItem(index)
        if item is not None and source_event_field_matches(item, "trial_type"):
            role_item = item
            break
    assert role_item is not None
    assert role_item.text(0) == "Trial type"
    role_selector = dialog.event_tree.itemWidget(role_item, 2)
    assert isinstance(role_selector, QComboBox)

    apply_review_choices(dialog)

    assert pairing_rows(dialog) == [
        ["sub-01_task-mi_run-1_raw.fif", "Choose label file", "Needs label"],
        ["sub-01_task-mi_run-2_raw.fif", "events.tsv", "Needs setup"],
    ]
    assert role_selector.currentData() == "class label candidate"
    assert ["Trial type", "event use", "Class label candidate"] in tree_rows(
        dialog.event_tree
    )


def test_apply_review_choices_resolves_walkthrough_event_values(qtbot) -> None:
    label_path = "/tmp/source/events.tsv"
    dialog = DataInterpretationPreviewDialog(
        parent=None,
        scan_result={
            "source_path": "/tmp/source",
            "eeg_files": ["/tmp/source/sub-01_task-mi_run-1_raw.fif"],
            "label_carriers": [label_path],
        },
        preview={
            "label_carrier_preview": [
                {
                    "path": label_path,
                    "name": "events.tsv",
                    "label_candidates": ["trial_type"],
                    "anchor_candidates": ["onset"],
                    "time_field_candidates": ["onset"],
                    "duration_candidates": ["duration"],
                    "selected_label_field": "trial_type",
                    "selected_anchor": "onset",
                    "selected_duration_field": "duration",
                    "placement_method": "interval",
                    "time_model": "seconds",
                    "granularity": "event",
                    "value_decisions": {
                        "left": {
                            "role": "unknown",
                            "keep_event": None,
                            "use_as_class": None,
                            "suggested_name": "left",
                            "decision": "unresolved",
                            "count": 5,
                        },
                        "right": {
                            "role": "unknown",
                            "keep_event": None,
                            "use_as_class": None,
                            "suggested_name": "right",
                            "decision": "unresolved",
                            "count": 5,
                        },
                    },
                }
            ],
        },
        validation_decision={"decision": "blocked"},
    )
    qtbot.addWidget(dialog)
    assert dialog.event_value_editor is not None
    assert dialog.event_value_editor.unresolved_values() == ["left", "right"]

    apply_review_choices(dialog)

    assert dialog.event_value_editor.unresolved_values() == []
    choices = dialog.get_result()["choices"]["label_carrier_choices"][label_path]
    decisions = choices["value_decisions"]
    assert set(decisions) == {"left", "right"}
    for raw_value in ("left", "right"):
        assert decisions[raw_value]["class_name"] == raw_value
        assert decisions[raw_value]["role"] == "stimulus"
        assert decisions[raw_value]["keep_event"] is True
        assert decisions[raw_value]["use_as_class"] is True
        assert decisions[raw_value]["provenance"] == "ui_event_value_editor"
