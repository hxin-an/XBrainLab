#!/usr/bin/env python3
"""Capture the focused ChatPanel UI/UX review gate.

The gate renders real Qt widgets and includes one composed MainWindow/QDockWidget
walkthrough. It is deterministic UI evidence, not assistant-accuracy or native
display-scaling evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import sys
import time
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any, cast
from weakref import WeakKeyDictionary

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
while str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

from scripts.dev.active_checkout import assert_active_checkout_import

assert_active_checkout_import(ROOT)

from PIL import Image
from PyQt6.QtCore import (
    QEvent,
    QEventLoop,
    QObject,
    QPoint,
    QRect,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QApplication,
    QDockWidget,
    QLabel,
    QMainWindow,
    QToolButton,
    QWidget,
)

import XBrainLab
from scripts.dev.capture_chatpanel_local_walkthrough import (
    collect_visible_messages,
)
from scripts.dev.human_like_walkthrough import evidence as human_evidence
from XBrainLab.backend.controller.chat_controller import (
    ChatController,
    ChatMessagePresentationKind,
    ChatPanelTarget,
    ChatResponseAction,
    ChatResponseActionKind,
)
from XBrainLab.backend.study import Study
from XBrainLab.llm.agent.assistant_activity import (
    AssistantTurnActivity,
    AssistantTurnActivityPhase,
)
from XBrainLab.llm.agent.confirmation import AgentConfirmationRequest
from XBrainLab.llm.agent.response_presentation import (
    AssistantPanelTarget,
    AssistantResponseAction,
    AssistantResponseKind,
    AssistantResponsePresentation,
)
from XBrainLab.llm.agent.turn import AssistantTurnCorrelation, AssistantTurnTerminal
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.model_download_lifecycle import (
    ModelCacheCleanupReason,
    ModelStatusInspectionRequest,
    ModelStatusInspectionResult,
)
from XBrainLab.ui.chat.message_bubble import (
    MessageBubble,
    MessagePresentationKind,
)
from XBrainLab.ui.chat.panel import ChatPanel
from XBrainLab.ui.chat.presentation import (
    ChatTurnCancelability,
    ChatTurnPresentation,
    ChatTurnPresentationPhase,
)
from XBrainLab.ui.dialogs.model_settings_dialog import ModelSettingsDialog
from XBrainLab.ui.main_window import MainWindow
from XBrainLab.ui.panels.training.components import MetricTab
from XBrainLab.ui.styles.stylesheets import Stylesheets

DEFAULT_OUTPUT_DIR = ROOT / "build" / "dev-artifacts" / "chatpanel-ui-ux"
JSON_ARTIFACT = "walkthrough.json"
README_ARTIFACT = "README.md"
SCHEMA_VERSION = 9
GENERATOR = "scripts/dev/capture_chatpanel_ui_ux_walkthrough.py"
CLAIM_BOUNDARY = (
    "Linux/Qt offscreen rendering and geometry evidence, including a real "
    "MainWindow/QDockWidget composition. Real widget captures preserve the "
    "device pixel ratio observed by Qt; the separate 1.5x synthetic QPixmap "
    "probe remains explicitly labeled. Configured offscreen scaling does not "
    "demonstrate native display scaling. "
    "This gate does not prove Windows launcher acceptance, Windows native DPI, "
    "multi-monitor behavior, local-model correctness, long-session behavior, or "
    "full-product completion."
)

EXPECTED_SCREEN_FILES = (
    "desktop-conversation-states.png",
    "narrow-conversation-states.png",
    "narrow-message-content-boundaries.png",
    "desktop-runtime-loading.png",
    "narrow-runtime-unavailable.png",
    "narrow-history-restored-audit.png",
    "narrow-cancellable-progress.png",
    "narrow-stopping-progress.png",
    "narrow-command-progress.png",
    "narrow-error-action.png",
    "narrow-setting-change-confirmation.png",
    "narrow-setting-change-confirmation-max-content.png",
    "pixmap-scaled-narrow.png",
    "dpi-320-message-error-confirmation.png",
    "dpi-420-message-error-confirmation.png",
    "dpi-760-message-error-confirmation.png",
    "responsive-320-idle.png",
    "responsive-320-multiline-composer.png",
    "responsive-320-long-clarification-action-520.png",
    "responsive-320-long-clarification-action-650.png",
    "responsive-320-processing-stop.png",
    "responsive-320-runtime-unavailable.png",
    "responsive-760-idle.png",
    "responsive-760-long-clarification-action.png",
    "responsive-760-processing-stop.png",
    "responsive-760-runtime-unavailable.png",
    "responsive-1280-idle.png",
    "responsive-1280-long-clarification-action.png",
    "responsive-1280-processing-stop.png",
    "responsive-1280-runtime-unavailable.png",
    "main-window-dock-420-action-visible.png",
    "main-window-dock-420-action-click.png",
    "main-window-dock-420-stopping.png",
    "main-window-dock-420-command-running.png",
)
FIRST_PAINT_SCREEN_FILES = (
    "first-paint-320-standalone.png",
    "first-paint-320-real-dock.png",
)
METRIC_TAB_SCREEN_FILES = (
    "training-metric-pre-first-epoch.png",
    "training-metric-first-data.png",
)
ASSISTANT_SETTINGS_SCREEN_FILES = (
    "assistant-settings-collapsed.png",
    "assistant-settings-advanced.png",
)

EXPECTED_STATE_LABELS = {
    MessagePresentationKind.TOOL_RESULT.value: "Completed",
    MessagePresentationKind.ATTENTION.value: "Needs attention",
    MessagePresentationKind.CLARIFICATION.value: "Needs input",
    MessagePresentationKind.ERROR.value: "Error",
    MessagePresentationKind.CANCELLED.value: "Cancelled",
}

FINGERPRINT_RELATIVE_PATHS = (
    GENERATOR,
    "scripts/dev/active_checkout.py",
    "scripts/dev/human_like_walkthrough/evidence.py",
    "pyproject.toml",
    "poetry.lock",
    "XBrainLab/chat_contract.py",
    "XBrainLab/backend/controller/chat_controller.py",
    "XBrainLab/llm/agent/assistant_activity.py",
    "XBrainLab/llm/agent/confirmation.py",
    "XBrainLab/llm/agent/controller.py",
    "XBrainLab/llm/agent/execution_policy.py",
    "XBrainLab/llm/agent/response_presentation.py",
    "XBrainLab/llm/agent/runtime_state.py",
    "XBrainLab/llm/agent/turn.py",
    "XBrainLab/product_language.py",
    "XBrainLab/ui/chat/composer.py",
    "XBrainLab/ui/chat/action_card.py",
    "XBrainLab/ui/chat/message_bubble.py",
    "XBrainLab/ui/chat/panel.py",
    "XBrainLab/ui/chat/presentation.py",
    "XBrainLab/ui/chat/segmented_control.py",
    "XBrainLab/ui/chat/status_presenter.py",
    "XBrainLab/ui/chat/styles.py",
    "XBrainLab/ui/chat/suggestion_card.py",
    "XBrainLab/ui/chat/turn_state.py",
    "XBrainLab/ui/components/agent_manager.py",
    "XBrainLab/ui/components/agent_presentation_service.py",
    "XBrainLab/ui/components/assistant_command_dispatcher.py",
    "XBrainLab/ui/components/assistant_runtime_coordinator.py",
    "XBrainLab/ui/components/assistant_runtime_lifecycle.py",
    "XBrainLab/ui/components/assistant_status_projection.py",
    "XBrainLab/ui/dialogs/model_settings_dialog.py",
    "XBrainLab/ui/main_window.py",
    "XBrainLab/ui/panels/training/components.py",
    "XBrainLab/ui/product_language.py",
    "XBrainLab/ui/styles/stylesheets.py",
    "XBrainLab/ui/styles/theme.py",
)


@dataclass(frozen=True, slots=True)
class ScenarioSpec:
    """One deterministic ChatPanel state and its visible expectations."""

    name: str
    filename: str
    logical_width: int
    logical_height: int
    render_pixel_ratio: float
    prepare: Callable[[ChatPanel], None]
    required_kinds: tuple[str, ...] = ()
    expected_send_text: str = "Send"
    expected_send_enabled: bool = False
    expected_input_enabled: bool = True
    expected_action_labels: tuple[str, ...] = ()
    runtime_state_visible: bool = False
    expected_runtime_title: str = ""
    activity_visible: bool = False
    expected_activity_title: str = ""
    expected_cancelability: ChatTurnCancelability = ChatTurnCancelability.NONE
    confirmation_visible: bool = False
    expected_confirmation_title: str = ""
    expected_confirmation_values: tuple[str, ...] = ()
    expected_confirmation_actions: tuple[str, ...] = ()
    expected_composer_text: str = ""
    minimum_composer_height: int = 0
    review_state: str = ""
    scroll_to_bottom: bool = False


class _FirstPaintProbe(QObject):
    """Snapshot panel state from the first paint event, before layout settling."""

    def __init__(self, collect: Callable[[], dict[str, Any]]) -> None:
        super().__init__()
        self._collect = collect
        self.paint_event_count = 0
        self.evidence: dict[str, Any] | None = None

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() is QEvent.Type.Paint:
            self.paint_event_count += 1
            if self.evidence is None:
                self.evidence = self._collect()
                self.evidence["paint_event_index"] = self.paint_event_count
                self.evidence["observed_during_first_paint_event"] = True
        return super().eventFilter(watched, event)


class _TeardownProbeController(QObject):
    """Minimal QObject controller used only to exercise real transport teardown."""

    def __init__(self) -> None:
        super().__init__()
        self.worker_thread = QThread.currentThread()

    @pyqtSlot(object)
    def initialize(self, _payload: object) -> None:
        return None

    def handle_user_turn(self, _payload: object) -> bool:
        return True

    @pyqtSlot()
    def stop_generation(self) -> None:
        return None

    @pyqtSlot(object)
    def set_model(self, _payload: object) -> None:
        return None

    @pyqtSlot()
    def reset_conversation(self) -> None:
        return None

    @pyqtSlot(object)
    def on_user_confirmation_resolved(self, _payload: object) -> None:
        return None

    @pyqtSlot(object)
    def on_workflow_ui_handoff_resolved(self, _payload: object) -> None:
        return None

    @pyqtSlot(str, object)
    def execute_debug_tool(self, _name: str, _params: object) -> None:
        return None

    def close(self) -> bool:
        # Keep the owned command thread busy long enough to observe that the GUI
        # event loop remains responsive while asynchronous cleanup completes.
        QThread.msleep(80)
        return True


class _AssistantSettingsCaptureLifecycle(QObject):
    """Deterministic, side-effect-free model lifecycle for Settings evidence."""

    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(object)
    terminal = pyqtSignal(bool, str)
    cache_cleanup_finished = pyqtSignal(object)
    inspection_finished = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self.idle = True
        self.active_target = None
        self.inspection_requests: list[ModelStatusInspectionRequest] = []

    def request_model_inspection(
        self,
        request: ModelStatusInspectionRequest,
    ) -> bool:
        self.inspection_requests.append(request)
        return True

    def start_download(self, repo_id: str, cache_dir: str) -> bool:
        del repo_id, cache_dir
        return False

    def request_cancel(self) -> bool:
        return True

    def request_shutdown(self) -> bool:
        return True

    def request_cache_removal(
        self,
        repo_id: str,
        cache_dir: str,
        *,
        reason: ModelCacheCleanupReason,
    ) -> bool:
        del repo_id, cache_dir, reason
        return False

    def is_idle(self) -> bool:
        return True

    def publish_ready_inspection(self) -> None:
        if not self.inspection_requests:
            raise RuntimeError("Assistant Settings did not request model inspection.")
        request = self.inspection_requests[-1]
        self.inspection_finished.emit(
            ModelStatusInspectionResult(
                request=request,
                installed=True,
                runtime_ready=True,
                runtime_message="Local runtime ready.",
                estimated_download_bytes=3_100_000_000,
                current_cache_bytes=3_100_000_000,
                projected_cache_bytes=3_100_000_000,
                available_disk_bytes=100_000_000_000,
                preflight_ok=True,
                preflight_message="Ready",
                cleanup_candidates=(),
                resolved_config=None,
            )
        )


_CAPTURE_CONTROLLERS: WeakKeyDictionary[ChatPanel, ChatController] = WeakKeyDictionary()


def _controller(panel: ChatPanel) -> ChatController:
    existing = _CAPTURE_CONTROLLERS.get(panel)
    if existing is not None:
        return existing
    controller = ChatController()
    _CAPTURE_CONTROLLERS[panel] = controller
    panel.connect_controller(controller)
    return controller


def _add_response(
    panel: ChatPanel,
    text: str,
    kind: ChatMessagePresentationKind,
    *,
    actions: tuple[ChatResponseAction, ...] = (),
    presentation_id: str = "",
) -> None:
    _controller(panel).add_agent_message(
        text,
        presentation_kind=kind,
        actions=actions,
        presentation_id=presentation_id,
    )


def _prepare_desktop_conversation(panel: ChatPanel) -> None:
    panel.set_runtime_state("ready")
    controller = _controller(panel)
    controller.add_user_message(
        "Review the imported EEG data and continue only when the next step is safe."
    )
    _add_response(
        panel,
        "The data is ready for preprocessing. I will keep decisions in the "
        "existing XBrainLab dialogs.",
        ChatMessagePresentationKind.ASSISTANT,
    )
    _add_response(
        panel,
        "Preprocessing completed. The updated data is ready for epoch settings.",
        ChatMessagePresentationKind.TOOL_RESULT,
    )
    _add_response(
        panel,
        "Training cannot start yet because the dataset split still needs review.",
        ChatMessagePresentationKind.ATTENTION,
    )
    _add_response(
        panel,
        "Choose the event source in Data Import before continuing.",
        ChatMessagePresentationKind.CLARIFICATION,
    )
    _add_response(
        panel,
        "Session reset cancelled. Your current workflow is unchanged.",
        ChatMessagePresentationKind.CANCELLED,
    )


def _prepare_narrow_conversation(panel: ChatPanel) -> None:
    panel.set_runtime_state("ready")
    controller = _controller(panel)
    controller.add_user_message(
        "Check this very_long_unbroken_dataset_identifier_that_must_wrap_without_"
        "clipping before training."
    )
    _add_response(
        panel,
        "The dataset check completed. Labels and epochs are aligned.",
        ChatMessagePresentationKind.TOOL_RESULT,
    )
    _add_response(
        panel,
        "Training cannot start until the dataset split is reviewed.",
        ChatMessagePresentationKind.ATTENTION,
    )
    _add_response(
        panel,
        "Request cancelled. You can revise it or ask something else.",
        ChatMessagePresentationKind.CANCELLED,
    )


def _prepare_message_content_boundaries(panel: ChatPanel) -> None:
    panel.set_runtime_state("ready")
    controller = _controller(panel)
    controller.add_user_message(
        "請檢查 EEG workflow 與這個長路徑: "
        "/mnt/d/workspace_v2/projects/lab/xbrainlab/tests/fixtures/data/"
        "subject_01_session_02_recording_without_spaces.edf"
    )
    _add_response(
        panel,
        (
            "The path and URL remain inside the transcript.\n\n"
            "https://example.com/reference/"
            "a_very_long_resource_identifier_without_break_points\n\n"
            "```python\n"
            "資料\t欄位\t值\n"
            'selected_files = ["' + ("subject_session_task_run_" * 10) + '.edf"]\n'
            "```"
        ),
        ChatMessagePresentationKind.ASSISTANT,
    )


def _prepare_loading(panel: ChatPanel) -> None:
    panel.set_runtime_state("loading")


def _prepare_runtime_unavailable(panel: ChatPanel) -> None:
    panel.set_runtime_state(
        "failed",
        "The selected local model could not start. Review assistant settings and "
        "try again.",
    )


def _prepare_restored_audit(panel: ChatPanel) -> None:
    panel.set_runtime_state("ready")
    original = ChatController()
    original.add_user_message("Explain why training is unavailable.")
    original.add_agent_message(
        "Review the imported labels before training.",
        presentation_kind=ChatMessagePresentationKind.ERROR,
        presentation_id="restored-response",
        actions=(
            ChatResponseAction(
                action_id="open-dataset",
                label="Open Dataset",
                kind=ChatResponseActionKind.OPEN_PANEL,
                panel=ChatPanelTarget.DATASET,
            ),
        ),
    )
    restored = ChatController()
    restored.restore_history(original.get_history())
    panel.connect_controller(restored)


def _prepare_cancellable_progress(panel: ChatPanel) -> None:
    panel.set_runtime_state("ready")
    _controller(panel).add_user_message(
        "Check the selected EEG data before choosing the next step."
    )
    panel.set_turn_activity(
        ChatTurnPresentation(
            phase=ChatTurnPresentationPhase.WORKING,
            primary_status="Working on your request",
            step="Checking the current EEG workflow",
            cancelability=ChatTurnCancelability.CANCELLABLE,
            cancelability_text="You can stop before an XBrainLab action starts.",
        )
    )


def _prepare_stopping_progress(panel: ChatPanel) -> None:
    _prepare_cancellable_progress(panel)
    panel.set_turn_activity(ChatTurnPresentation.stopping())


def _prepare_command_progress(panel: ChatPanel) -> None:
    panel.set_runtime_state("ready")
    _controller(panel).add_user_message(
        "Prepare the selected EEG data for the next workflow step."
    )
    panel.set_turn_activity(
        ChatTurnPresentation.application_command("Prepare EEG data")
    )


def _prepare_error_action(panel: ChatPanel) -> None:
    panel.set_runtime_state("ready")
    controller = _controller(panel)
    controller.add_user_message("Continue the previous request.")
    _add_response(
        panel,
        "The assistant could not complete the request. Technical details were "
        "written to the application log.",
        ChatMessagePresentationKind.ERROR,
        presentation_id="error-response",
        actions=(
            ChatResponseAction(
                action_id="try-again",
                label="Try again",
                kind=ChatResponseActionKind.SEND_MESSAGE,
                prompt="Please retry my previous request.",
            ),
        ),
    )


def _prepare_setting_change_confirmation(panel: ChatPanel) -> None:
    panel.set_runtime_state("ready")
    _controller(panel).add_user_message(
        "Reduce the batch size if the current configuration is too large."
    )
    request = AgentConfirmationRequest.for_action(
        command_name="configure_training",
        params={"batch_size": 16},
        action_label="Apply change",
        description="The current configuration may exceed available VRAM.",
        destructive=False,
        publication_generation=1,
        request_id="walkthrough-batch-size-change",
    )
    panel.show_confirmation_request(
        request,
        current_values={"Batch size": "32"},
    )


def _prepare_max_setting_change_confirmation(panel: ChatPanel) -> None:
    panel.set_runtime_state("ready")
    _controller(panel).add_user_message(
        "Review every proposed training setting before applying the change."
    )
    request = AgentConfirmationRequest.for_action(
        command_name="configure_training",
        params={
            f"parameter_{index:02d}": f"{index}-" + ("W" * 190) for index in range(14)
        },
        action_label="Apply reviewed settings",
        description=(
            "Review every proposed setting before applying this configuration."
        ),
        destructive=False,
        publication_generation=1,
        request_id="walkthrough-max-setting-change",
    )
    panel.show_confirmation_request(request)


def _prepare_scaled_pixmap(panel: ChatPanel) -> None:
    panel.set_runtime_state("ready")
    controller = _controller(panel)
    controller.add_user_message(
        "Check the long EEG workflow description before continuing."
    )
    _add_response(
        panel,
        "The workflow check completed. Review the dataset split in XBrainLab.",
        ChatMessagePresentationKind.TOOL_RESULT,
    )
    _add_response(
        panel,
        "Training cannot start until the split is reviewed.",
        ChatMessagePresentationKind.ATTENTION,
    )
    _add_response(
        panel,
        "Session reset cancelled. Your current workflow is unchanged.",
        ChatMessagePresentationKind.CANCELLED,
    )


def _prepare_dpi_evidence(panel: ChatPanel) -> None:
    """Compose the same message, error, and confirmation state at each width."""
    panel.set_runtime_state("ready")
    controller = _controller(panel)
    controller.add_user_message("Review the proposed training setting.")
    _add_response(
        panel,
        "The current batch size may exceed available GPU memory.",
        ChatMessagePresentationKind.ERROR,
    )
    request = AgentConfirmationRequest.for_action(
        command_name="configure_training",
        params={"batch_size": 16},
        action_label="Apply change",
        description="Reduce the batch size before starting training.",
        destructive=False,
        publication_generation=1,
        request_id=f"dpi-batch-size-change-{panel.width()}",
    )
    panel.show_confirmation_request(
        request,
        current_values={"Batch size": "32"},
    )


_RESPONSIVE_ACTION_LABEL = "Review import decision"


def _prepare_responsive_idle(panel: ChatPanel) -> None:
    panel.set_runtime_state("ready")


_MULTILINE_COMPOSER_TEXT = (
    "Review the current EEG workflow.\n"
    "Explain the unresolved label mapping.\n"
    "Do not change settings yet."
)


def _prepare_responsive_multiline_composer(panel: ChatPanel) -> None:
    panel.set_runtime_state("ready")
    panel.input_field.setText(_MULTILINE_COMPOSER_TEXT)


def _prepare_responsive_long_clarification(panel: ChatPanel) -> None:
    panel.set_runtime_state("ready")
    controller = _controller(panel)
    controller.add_user_message(
        "Check the unresolved event source before importing this EEG recording."
    )
    repeated_context = "\n\n".join(
        (
            "Keep the imported data unchanged while this clarification is pending. "
            "Use the existing Data Import workflow for the final decision."
        )
        for _ in range(8)
    )
    _add_response(
        panel,
        (
            "The selected EEG source needs one decision before import can continue. "
            "Review "
            "subject_01_session_02_task_motor_run_000000000000000000000000000001 "
            "and confirm which event stream supplies labels.\n\n"
            f"{repeated_context}"
        ),
        ChatMessagePresentationKind.CLARIFICATION,
        presentation_id=f"responsive-long-clarification-{panel.width()}-{panel.height()}",
        actions=(
            ChatResponseAction(
                action_id=f"review-labels-{panel.width()}-{panel.height()}",
                label=_RESPONSIVE_ACTION_LABEL,
                kind=ChatResponseActionKind.SEND_MESSAGE,
                prompt="Review the unresolved label alignment.",
            ),
        ),
    )


def _prepare_responsive_processing(panel: ChatPanel) -> None:
    panel.set_runtime_state("ready")
    _controller(panel).add_user_message(
        "Check the current EEG workflow before taking the next action."
    )
    panel.set_turn_activity(
        ChatTurnPresentation(
            phase=ChatTurnPresentationPhase.WORKING,
            primary_status="Working on your request",
            step="Checking the current EEG workflow",
            cancelability=ChatTurnCancelability.CANCELLABLE,
            cancelability_text="You can stop before an XBrainLab action starts.",
        )
    )


def _prepare_responsive_runtime_unavailable(panel: ChatPanel) -> None:
    panel.set_runtime_state(
        "failed",
        "The selected local model could not start. Review assistant settings and "
        "try again.",
    )


SCENARIOS = (
    ScenarioSpec(
        "desktop_conversation_states",
        "desktop-conversation-states.png",
        460,
        900,
        1.0,
        _prepare_desktop_conversation,
        required_kinds=(
            "user",
            "assistant",
            "tool_result",
            "attention",
            "clarification",
            "cancelled",
        ),
    ),
    ScenarioSpec(
        "narrow_conversation_states",
        "narrow-conversation-states.png",
        320,
        760,
        1.0,
        _prepare_narrow_conversation,
        required_kinds=("user", "tool_result", "attention", "cancelled"),
    ),
    ScenarioSpec(
        "narrow_message_content_boundaries",
        "narrow-message-content-boundaries.png",
        320,
        760,
        1.0,
        _prepare_message_content_boundaries,
        required_kinds=("user", "assistant"),
        review_state="message_content_boundaries",
        scroll_to_bottom=True,
    ),
    ScenarioSpec(
        "desktop_runtime_loading",
        "desktop-runtime-loading.png",
        460,
        680,
        1.0,
        _prepare_loading,
        expected_send_enabled=False,
        expected_input_enabled=False,
        runtime_state_visible=True,
        expected_runtime_title="Loading local assistant",
    ),
    ScenarioSpec(
        "narrow_runtime_unavailable",
        "narrow-runtime-unavailable.png",
        320,
        680,
        1.0,
        _prepare_runtime_unavailable,
        expected_send_enabled=False,
        expected_input_enabled=False,
        expected_action_labels=("Retry local assistant", "Settings"),
        runtime_state_visible=True,
        expected_runtime_title="Assistant unavailable",
    ),
    ScenarioSpec(
        "narrow_history_restored_audit",
        "narrow-history-restored-audit.png",
        320,
        680,
        1.0,
        _prepare_restored_audit,
        required_kinds=("user", "error"),
    ),
    ScenarioSpec(
        "narrow_cancellable_progress",
        "narrow-cancellable-progress.png",
        320,
        680,
        1.0,
        _prepare_cancellable_progress,
        required_kinds=("user",),
        expected_send_text="Stop",
        expected_send_enabled=True,
        expected_input_enabled=False,
        activity_visible=True,
        expected_activity_title="Working on your request",
        expected_cancelability=ChatTurnCancelability.CANCELLABLE,
    ),
    ScenarioSpec(
        "narrow_stopping_progress",
        "narrow-stopping-progress.png",
        320,
        680,
        1.0,
        _prepare_stopping_progress,
        required_kinds=("user",),
        expected_send_text="Stopping",
        expected_send_enabled=False,
        expected_input_enabled=False,
        activity_visible=True,
        expected_activity_title="Stopping request",
        expected_cancelability=ChatTurnCancelability.STOPPING,
    ),
    ScenarioSpec(
        "narrow_command_progress",
        "narrow-command-progress.png",
        320,
        680,
        1.0,
        _prepare_command_progress,
        required_kinds=("user",),
        expected_send_text="Working",
        expected_send_enabled=False,
        expected_input_enabled=False,
        activity_visible=True,
        expected_activity_title="XBrainLab action in progress",
        expected_cancelability=ChatTurnCancelability.NOT_CANCELLABLE,
    ),
    ScenarioSpec(
        "narrow_error_action",
        "narrow-error-action.png",
        320,
        680,
        1.0,
        _prepare_error_action,
        required_kinds=("user", "error"),
        expected_action_labels=("Try again",),
    ),
    ScenarioSpec(
        "narrow_setting_change_confirmation",
        "narrow-setting-change-confirmation.png",
        320,
        680,
        1.0,
        _prepare_setting_change_confirmation,
        required_kinds=("user",),
        confirmation_visible=True,
        expected_confirmation_title="Suggested change",
        expected_confirmation_values=("Batch size", "32  ->  16"),
        expected_confirmation_actions=("Keep current value", "Apply change"),
    ),
    ScenarioSpec(
        "narrow_setting_change_confirmation_max_content",
        "narrow-setting-change-confirmation-max-content.png",
        320,
        680,
        1.0,
        _prepare_max_setting_change_confirmation,
        required_kinds=("user",),
        confirmation_visible=True,
        expected_confirmation_title="Suggested change",
        expected_confirmation_values=("Parameter 00", "Parameter 13"),
        expected_confirmation_actions=(
            "Keep current settings",
            "Apply changes",
        ),
        scroll_to_bottom=True,
    ),
    ScenarioSpec(
        "pixmap_scaled_narrow",
        "pixmap-scaled-narrow.png",
        320,
        760,
        1.5,
        _prepare_scaled_pixmap,
        required_kinds=("user", "tool_result", "attention", "cancelled"),
    ),
    ScenarioSpec(
        "dpi_320_message_error_confirmation",
        "dpi-320-message-error-confirmation.png",
        320,
        720,
        1.0,
        _prepare_dpi_evidence,
        required_kinds=("user", "error"),
        confirmation_visible=True,
        expected_confirmation_title="Suggested change",
        expected_confirmation_values=("Batch size", "32  ->  16"),
        expected_confirmation_actions=("Keep current value", "Apply change"),
        review_state="dpi_evidence",
    ),
    ScenarioSpec(
        "dpi_420_message_error_confirmation",
        "dpi-420-message-error-confirmation.png",
        420,
        720,
        1.0,
        _prepare_dpi_evidence,
        required_kinds=("user", "error"),
        confirmation_visible=True,
        expected_confirmation_title="Suggested change",
        expected_confirmation_values=("Batch size", "32  ->  16"),
        expected_confirmation_actions=("Keep current value", "Apply change"),
        review_state="dpi_evidence",
    ),
    ScenarioSpec(
        "dpi_760_message_error_confirmation",
        "dpi-760-message-error-confirmation.png",
        760,
        720,
        1.0,
        _prepare_dpi_evidence,
        required_kinds=("user", "error"),
        confirmation_visible=True,
        expected_confirmation_title="Suggested change",
        expected_confirmation_values=("Batch size", "32  ->  16"),
        expected_confirmation_actions=("Keep current value", "Apply change"),
        review_state="dpi_evidence",
    ),
    ScenarioSpec(
        "responsive_320_idle",
        "responsive-320-idle.png",
        320,
        650,
        1.0,
        _prepare_responsive_idle,
        review_state="idle",
    ),
    ScenarioSpec(
        "responsive_320_multiline_composer",
        "responsive-320-multiline-composer.png",
        320,
        650,
        1.0,
        _prepare_responsive_multiline_composer,
        expected_send_enabled=True,
        expected_composer_text=_MULTILINE_COMPOSER_TEXT,
        minimum_composer_height=68,
        review_state="multiline_composer",
    ),
    ScenarioSpec(
        "responsive_320_long_clarification_action_520",
        "responsive-320-long-clarification-action-520.png",
        320,
        520,
        1.0,
        _prepare_responsive_long_clarification,
        required_kinds=("user", "clarification"),
        expected_action_labels=(_RESPONSIVE_ACTION_LABEL,),
        review_state="long_clarification_action",
    ),
    ScenarioSpec(
        "responsive_320_long_clarification_action_650",
        "responsive-320-long-clarification-action-650.png",
        320,
        650,
        1.0,
        _prepare_responsive_long_clarification,
        required_kinds=("user", "clarification"),
        expected_action_labels=(_RESPONSIVE_ACTION_LABEL,),
        review_state="long_clarification_action",
    ),
    ScenarioSpec(
        "responsive_320_processing_stop",
        "responsive-320-processing-stop.png",
        320,
        650,
        1.0,
        _prepare_responsive_processing,
        required_kinds=("user",),
        expected_send_text="Stop",
        expected_send_enabled=True,
        expected_input_enabled=False,
        activity_visible=True,
        expected_activity_title="Working on your request",
        expected_cancelability=ChatTurnCancelability.CANCELLABLE,
        review_state="processing_stop",
    ),
    ScenarioSpec(
        "responsive_320_runtime_unavailable",
        "responsive-320-runtime-unavailable.png",
        320,
        650,
        1.0,
        _prepare_responsive_runtime_unavailable,
        expected_send_enabled=False,
        expected_input_enabled=False,
        expected_action_labels=("Retry local assistant", "Settings"),
        runtime_state_visible=True,
        expected_runtime_title="Assistant unavailable",
        review_state="runtime_unavailable",
    ),
    ScenarioSpec(
        "responsive_760_idle",
        "responsive-760-idle.png",
        760,
        650,
        1.0,
        _prepare_responsive_idle,
        review_state="idle",
    ),
    ScenarioSpec(
        "responsive_760_long_clarification_action",
        "responsive-760-long-clarification-action.png",
        760,
        650,
        1.0,
        _prepare_responsive_long_clarification,
        required_kinds=("user", "clarification"),
        expected_action_labels=(_RESPONSIVE_ACTION_LABEL,),
        review_state="long_clarification_action",
    ),
    ScenarioSpec(
        "responsive_760_processing_stop",
        "responsive-760-processing-stop.png",
        760,
        650,
        1.0,
        _prepare_responsive_processing,
        required_kinds=("user",),
        expected_send_text="Stop",
        expected_send_enabled=True,
        expected_input_enabled=False,
        activity_visible=True,
        expected_activity_title="Working on your request",
        expected_cancelability=ChatTurnCancelability.CANCELLABLE,
        review_state="processing_stop",
    ),
    ScenarioSpec(
        "responsive_760_runtime_unavailable",
        "responsive-760-runtime-unavailable.png",
        760,
        650,
        1.0,
        _prepare_responsive_runtime_unavailable,
        expected_send_enabled=False,
        expected_input_enabled=False,
        expected_action_labels=("Retry local assistant", "Settings"),
        runtime_state_visible=True,
        expected_runtime_title="Assistant unavailable",
        review_state="runtime_unavailable",
    ),
    ScenarioSpec(
        "responsive_1280_idle",
        "responsive-1280-idle.png",
        1280,
        650,
        1.0,
        _prepare_responsive_idle,
        review_state="idle",
    ),
    ScenarioSpec(
        "responsive_1280_long_clarification_action",
        "responsive-1280-long-clarification-action.png",
        1280,
        650,
        1.0,
        _prepare_responsive_long_clarification,
        required_kinds=("user", "clarification"),
        expected_action_labels=(_RESPONSIVE_ACTION_LABEL,),
        review_state="long_clarification_action",
    ),
    ScenarioSpec(
        "responsive_1280_processing_stop",
        "responsive-1280-processing-stop.png",
        1280,
        650,
        1.0,
        _prepare_responsive_processing,
        required_kinds=("user",),
        expected_send_text="Stop",
        expected_send_enabled=True,
        expected_input_enabled=False,
        activity_visible=True,
        expected_activity_title="Working on your request",
        expected_cancelability=ChatTurnCancelability.CANCELLABLE,
        review_state="processing_stop",
    ),
    ScenarioSpec(
        "responsive_1280_runtime_unavailable",
        "responsive-1280-runtime-unavailable.png",
        1280,
        650,
        1.0,
        _prepare_responsive_runtime_unavailable,
        expected_send_enabled=False,
        expected_input_enabled=False,
        expected_action_labels=("Retry local assistant", "Settings"),
        runtime_state_visible=True,
        expected_runtime_title="Assistant unavailable",
        review_state="runtime_unavailable",
    ),
)


def source_file_manifest() -> list[dict[str, str]]:
    """Return every source file represented by the artifact fingerprint."""
    manifest: list[dict[str, str]] = []
    for relative in FINGERPRINT_RELATIVE_PATHS:
        path = ROOT / relative
        manifest.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return manifest


def source_fingerprint(
    source_files: Iterable[Mapping[str, str]] | None = None,
) -> str:
    """Hash the ordered, explicit capture source manifest."""
    digest = hashlib.sha256()
    records = source_file_manifest() if source_files is None else source_files
    for record in records:
        digest.update(record["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(record["sha256"].encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def runtime_import_provenance() -> dict[str, Any]:
    """Prove the capture imported product code from the artifact source root."""
    capture_root = ROOT.resolve()
    package_root = Path(XBrainLab.__file__).resolve().parent.parent
    symbols = (
        ("ChatPanel", ChatPanel),
        ("MainWindow", MainWindow),
        ("ChatController", ChatController),
        ("AssistantResponsePresentation", AssistantResponsePresentation),
        ("ModelSettingsDialog", ModelSettingsDialog),
    )
    modules: list[dict[str, Any]] = []
    for symbol_name, symbol in symbols:
        source = inspect.getsourcefile(symbol)
        resolved = Path(source).resolve() if source else None
        modules.append(
            {
                "symbol": symbol_name,
                "path": str(resolved) if resolved is not None else "",
                "under_root": bool(
                    resolved is not None and resolved.is_relative_to(capture_root)
                ),
            }
        )
    return {
        "capture_root": str(capture_root),
        "package_root": str(package_root),
        "root_matches_capture": package_root == capture_root,
        "all_sources_under_root": all(record["under_root"] for record in modules),
        "modules": modules,
    }


def _settle_layout(app: QApplication, widget: QWidget) -> None:
    widget.updateGeometry()
    for _ in range(8):
        app.processEvents()


def _layout_bubbles(panel: ChatPanel) -> list[MessageBubble]:
    return [
        cast(MessageBubble, item.widget())
        for index in range(panel.chat_layout.count())
        if (item := panel.chat_layout.itemAt(index)) is not None
        and isinstance(item.widget(), MessageBubble)
        and cast(MessageBubble, item.widget()).isVisible()
    ]


def _button_evidence(panel: ChatPanel) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    outside: list[str] = []
    for index, button in enumerate(panel.findChildren(QAbstractButton)):
        if not button.isVisibleTo(panel):
            continue
        name = button.objectName() or f"{type(button).__name__}_{index}"
        origin = button.mapTo(panel, QPoint(0, 0))
        inside_scroll_content = panel.scroll_area.isAncestorOf(button)
        if inside_scroll_content:
            viewport = panel.scroll_area.viewport()
            if viewport is None:
                inside = False
            else:
                viewport_origin = button.mapTo(viewport, QPoint(0, 0))
                inside = (
                    viewport_origin.x() >= 0
                    and viewport_origin.x() + button.width() <= viewport.width()
                )
        else:
            inside = human_evidence._widget_inside(panel, button)
        text = " ".join(str(button.text() or "").split())
        text_rendered = human_evidence._button_renders_text(button)
        text_fits = human_evidence.button_visible_text_fits(button)
        records.append(
            {
                "name": name,
                "text": text,
                "text_rendered": text_rendered,
                "enabled": button.isEnabled(),
                "bounds": [origin.x(), origin.y(), button.width(), button.height()],
                "inside_panel": inside,
                "inside_scroll_content": inside_scroll_content,
                "text_fits": text_fits,
            }
        )
        if not inside:
            outside.append(name)
    return records, outside


def _widget_panel_geometry(
    panel: ChatPanel,
    widget: QWidget | None,
) -> dict[str, Any] | None:
    """Record all four widget edges in ChatPanel-relative coordinates."""
    if widget is None:
        return None
    origin = widget.mapTo(panel, QPoint(0, 0))
    left = origin.x()
    top = origin.y()
    right = left + widget.width()
    bottom = top + widget.height()
    sides = {
        "left": left >= 0,
        "top": top >= 0,
        "right": right <= panel.width(),
        "bottom": bottom <= panel.height(),
    }
    return {
        "visible": widget.isVisibleTo(panel),
        "bounds": [left, top, widget.width(), widget.height()],
        "edges": {
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
        },
        "panel_size": [panel.width(), panel.height()],
        "sides": sides,
        "inside_panel_on_all_sides": all(sides.values()),
    }


def _panel_relative_geometry(panel: ChatPanel) -> dict[str, Any]:
    """Collect the hard geometry gate for persistent assistant controls."""
    response_action = next(
        (
            button
            for button in panel.response_actions_widget.findChildren(QToolButton)
            if button.isVisibleTo(panel)
        ),
        None,
    )
    return {
        "composer": _widget_panel_geometry(panel, panel.input_field),
        "send": _widget_panel_geometry(panel, panel.send_btn),
        "response_action": _widget_panel_geometry(panel, response_action),
    }


def _geometry_inside(record: dict[str, Any] | None) -> bool:
    return bool(record and record.get("inside_panel_on_all_sides"))


def _dpi_content_widgets(
    panel: ChatPanel,
    spec: ScenarioSpec,
) -> dict[str, QWidget] | None:
    """Return the painted regions required by dedicated DPI evidence frames."""
    if spec.review_state != "dpi_evidence":
        return None
    bubbles = _layout_bubbles(panel)
    user_bubble = next(
        (bubble for bubble in bubbles if bubble.presentation_kind.value == "user"),
        None,
    )
    error_bubble = next(
        (bubble for bubble in bubbles if bubble.presentation_kind.value == "error"),
        None,
    )
    if user_bubble is None or error_bubble is None:
        raise RuntimeError(f"{spec.name}: required DPI message content is missing.")
    return {
        "message_content": user_bubble,
        "warning_or_error": error_bubble,
        "confirmation_card": panel.confirmation_card_widget,
    }


def _screen_evidence(panel: ChatPanel, spec: ScenarioSpec) -> dict[str, Any]:
    horizontal = panel.scroll_area.horizontalScrollBar()
    viewport = panel.scroll_area.viewport()
    vertical = panel.scroll_area.verticalScrollBar()
    if horizontal is None or viewport is None or vertical is None:
        raise RuntimeError("ChatPanel scroll-area geometry is unavailable.")
    bubbles = _layout_bubbles(panel)
    buttons, outside_buttons = _button_evidence(panel)
    message_kinds = [bubble.presentation_kind.value for bubble in bubbles]
    state_labels = {
        bubble.presentation_kind.value: str(bubble.kind_label.text())
        for bubble in bubbles
        if bubble.kind_label is not None and bubble.kind_label.isVisible()
    }
    clipped: list[str] = []
    bubble_bounds: list[dict[str, Any]] = []
    for index, bubble in enumerate(bubbles):
        frame = bubble.bubble_frame
        if frame is None:
            clipped.append(f"message_bubble_{index}")
            continue
        origin = frame.mapTo(viewport, QPoint(0, 0))
        inside = origin.x() >= -2 and origin.x() + frame.width() <= viewport.width() + 2
        bubble_bounds.append(
            {
                "index": index,
                "kind": bubble.presentation_kind.value,
                "x": origin.x(),
                "width": frame.width(),
                "inside_viewport_horizontally": inside,
            }
        )
        if not inside:
            clipped.append(f"message_bubble_{index}")

    response_actions = [
        str(button.property("assistantFullLabel") or button.text())
        for button in panel.response_actions_widget.findChildren(QToolButton)
        if button.isVisibleTo(panel.response_actions_widget)
    ]
    runtime_actions = [
        " ".join(str(button.property("assistantFullLabel") or button.text()).split())
        for button in (panel.retry_runtime_btn, panel.setup_btn)
        if button.isVisibleTo(panel.runtime_state_widget)
    ]
    visible_actions = response_actions + runtime_actions
    panel_geometry = _panel_relative_geometry(panel)
    placeholder = human_evidence.assistant_composer_placeholder_evidence(panel)
    text_overflow = human_evidence._assistant_text_overflow(panel)
    activity = {
        "visible": panel.turn_activity_widget.isVisibleTo(panel),
        "primary_status": panel.turn_activity_title.text(),
        "step": panel.turn_activity_step.text(),
        "cancelability": panel.turn_activity_widget.property("assistantCancelability"),
        "cancelability_text": panel.turn_activity_cancelability.text(),
    }
    confirmation_card = panel.confirmation_card_widget
    confirmation_values = "\n\n".join(
        "\n".join(
            part
            for part in (
                row.label.text(),
                (
                    f"{row.current_value.accessibleDescription()}  ->  "
                    f"{row.proposed_value.accessibleDescription()}"
                    if row.current_value.isVisible()
                    else row.proposed_value.accessibleDescription()
                ),
            )
            if part
        )
        for row in confirmation_card.proposal_rows
    )
    confirmation = {
        "visible": confirmation_card.isVisibleTo(panel),
        "title": confirmation_card.title_label.text(),
        "description": confirmation_card.description_label.text(),
        "values": confirmation_values,
        "reason": confirmation_card.reason_label.text(),
        "actions": (
            confirmation_card.secondary_button.text(),
            confirmation_card.primary_button.text(),
        ),
        "request_id": confirmation_card.request_id,
    }
    prose_scroll_maxima = [
        scrollbar.maximum()
        for bubble in bubbles
        for view in bubble.content_view.text_views
        if (scrollbar := view.horizontalScrollBar()) is not None
    ]
    code_scroll_maxima = [
        scrollbar.maximum()
        for bubble in bubbles
        for code_block in bubble.code_blocks
        if (scrollbar := code_block.horizontalScrollBar()) is not None
    ]
    checks = {
        "no_horizontal_scroll": horizontal.maximum() == 0,
        "prose_has_no_horizontal_scroll": not any(prose_scroll_maxima),
        "message_bubbles_inside_viewport": not clipped,
        "message_bubble_widths_are_bounded": all(
            record["width"] <= int(viewport.width() * 0.84) + 2
            for record in bubble_bounds
        ),
        "code_block_scrolls_inside_message": (
            spec.review_state != "message_content_boundaries"
            or any(value > 0 for value in code_scroll_maxima)
        ),
        "visible_buttons_inside_panel": not outside_buttons,
        "visible_button_text_fits": all(button["text_fits"] for button in buttons),
        "visible_text_fits": not text_overflow,
        "composer_placeholder_fits": placeholder["fits"],
        "composer_visible": panel.input_field.isVisibleTo(panel),
        "send_button_visible": panel.send_btn.isVisibleTo(panel),
        "composer_inside_panel_on_all_sides": _geometry_inside(
            panel_geometry["composer"]
        ),
        "send_inside_panel_on_all_sides": _geometry_inside(panel_geometry["send"]),
        "legacy_mode_selector_absent": not any(
            hasattr(panel, name)
            for name in ("mode_selector_widget", "ask_mode_btn", "workflow_mode_btn")
        ),
        "response_action_inside_panel_on_all_sides": (
            not response_actions or _geometry_inside(panel_geometry["response_action"])
        ),
        "expected_message_kinds_present": message_kinds == list(spec.required_kinds),
        "expected_actions_present": visible_actions
        == list(spec.expected_action_labels),
        "expected_send_state_present": panel.send_btn.text() == spec.expected_send_text,
        "send_accessible_name_present": panel.send_btn.accessibleName()
        in {
            "Send request",
            "Stop current request",
            "Waiting for your decision",
            "Assistant is working",
            "Stopping current request",
        },
        "send_visual_present": (
            panel.send_btn.toolButtonStyle()
            is not Qt.ToolButtonStyle.ToolButtonIconOnly
            or not panel.send_btn.icon().isNull()
        ),
        "expected_send_enabled_present": (
            panel.send_btn.isEnabled() is spec.expected_send_enabled
        ),
        "expected_input_state_present": (
            panel.input_field.isEnabled() is spec.expected_input_enabled
        ),
        "expected_composer_text_present": (
            not spec.expected_composer_text
            or panel.input_field.toPlainText() == spec.expected_composer_text
        ),
        "expected_composer_height_present": (
            not spec.minimum_composer_height
            or panel.input_field.height() >= spec.minimum_composer_height
        ),
        "expected_runtime_visibility_present": (
            panel.runtime_state_widget.isVisibleTo(panel) is spec.runtime_state_visible
        ),
        "expected_runtime_title_present": (
            not spec.expected_runtime_title
            or panel.runtime_state_title.text() == spec.expected_runtime_title
        ),
        "expected_activity_visibility_present": (
            activity["visible"] is spec.activity_visible
        ),
        "expected_activity_title_present": (
            not spec.expected_activity_title
            or activity["primary_status"] == spec.expected_activity_title
        ),
        "expected_cancelability_present": (
            not spec.activity_visible
            or activity["cancelability"] == spec.expected_cancelability.value
        ),
        "expected_confirmation_visibility_present": (
            confirmation["visible"] is spec.confirmation_visible
        ),
        "expected_confirmation_title_present": (
            not spec.expected_confirmation_title
            or confirmation["title"] == spec.expected_confirmation_title
        ),
        "expected_confirmation_values_present": all(
            value in confirmation["values"]
            for value in spec.expected_confirmation_values
        ),
        "expected_confirmation_actions_present": (
            not spec.expected_confirmation_actions
            or confirmation["actions"] == spec.expected_confirmation_actions
        ),
        "legacy_muted_status_hidden": panel.workflow_run_status_label.isHidden(),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "name": spec.name,
        "file": spec.filename,
        "logical_size": [panel.width(), panel.height()],
        "requested_render_pixel_ratio": spec.render_pixel_ratio,
        "native_display_scaling_observed": False,
        "viewport_width": viewport.width(),
        "horizontal_scroll_max": horizontal.maximum(),
        "vertical_scroll_max": vertical.maximum(),
        "message_kinds": message_kinds,
        "state_labels": state_labels,
        "visible_messages": [
            {"sender": message.sender, "text": message.text}
            for message in collect_visible_messages(panel)
        ],
        "bubble_bounds": bubble_bounds,
        "message_horizontal_scroll_maxima": code_scroll_maxima,
        "visible_buttons": buttons,
        "visible_actions": visible_actions,
        "visible_response_actions": response_actions,
        "send_text": panel.send_btn.text(),
        "send_enabled": panel.send_btn.isEnabled(),
        "input_enabled": panel.input_field.isEnabled(),
        "composer_text": panel.input_field.toPlainText(),
        "composer_height": panel.input_field.height(),
        "activity": activity,
        "confirmation": confirmation,
        "composer_placeholder": placeholder,
        "text_overflow": text_overflow,
        "outside_buttons": outside_buttons,
        "panel_relative_geometry": panel_geometry,
        "checks": checks,
        "failures": failures,
    }


def _capture_widget(
    widget: QWidget,
    output_path: Path,
    *,
    render_pixel_ratio: float,
    required_content_widgets: Mapping[str, QWidget] | None = None,
    text_content_regions: Collection[str] = (),
) -> dict[str, Any]:
    """Capture two content-ready frames while preserving Qt's observed DPR."""
    synthetic_capture = render_pixel_ratio != 1.0
    widget_device_pixel_ratio = float(widget.devicePixelRatioF())

    app = QApplication.instance()
    consecutive_ready = 0
    content: dict[str, Any] = {}
    render_attempts = 0
    capture_device_pixel_ratio = 0.0
    required_regions: dict[str, tuple[int, int, int, int]] = {}
    for _attempt in range(10):
        render_attempts += 1
        widget.ensurePolished()
        layout = widget.layout()
        if layout is not None:
            layout.activate()
        widget.updateGeometry()
        widget.repaint()
        if isinstance(app, QApplication):
            app.processEvents()

        if synthetic_capture:
            pixel_width = _physical_dimension(widget.width(), render_pixel_ratio)
            pixel_height = _physical_dimension(widget.height(), render_pixel_ratio)
            pixmap = QPixmap(pixel_width, pixel_height)
            pixmap.setDevicePixelRatio(render_pixel_ratio)
            pixmap.fill(QColor("#1e1e1e"))
            painter = QPainter(pixmap)
            widget.render(painter)
            painter.end()
        else:
            pixmap = widget.grab()
        if pixmap.isNull():
            raise RuntimeError(f"Could not grab {output_path}.")
        capture_device_pixel_ratio = float(pixmap.devicePixelRatio())
        required_regions = _scaled_child_regions(
            widget,
            required_content_widgets or {},
            pixel_width=pixmap.width(),
            pixel_height=pixmap.height(),
        )
        if not pixmap.save(str(output_path)):
            raise RuntimeError(f"Could not save {output_path}.")
        with Image.open(output_path) as rendered:
            normalized = rendered.convert("RGB")
            normalized.save(output_path, format="PNG")
        content = image_content_evidence(
            output_path,
            required_regions=required_regions,
            text_region_names=text_content_regions,
        )
        consecutive_ready = consecutive_ready + 1 if content["passed"] else 0
        if consecutive_ready >= 2:
            break
    else:
        failed_regions = [
            name
            for name, region in content.get("regions", {}).items()
            if not region.get("passed")
        ]
        detail = ", ".join(failed_regions) or "full frame"
        raise RuntimeError(
            f"Captured screenshot did not become content-ready ({detail}): "
            f"{output_path}. Regions: {content.get('regions', {})!r}"
        )

    with Image.open(output_path) as captured:
        pixel_size = list(captured.size)
    return {
        "pixel_size": pixel_size,
        "image_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "capture_method": ("synthetic_qpixmap" if synthetic_capture else "widget_grab"),
        "widget_device_pixel_ratio": widget_device_pixel_ratio,
        "capture_device_pixel_ratio": capture_device_pixel_ratio,
        "render_pixel_ratio": capture_device_pixel_ratio,
        "render_scale_evidence": (
            "synthetic_pixmap_device_ratio"
            if synthetic_capture
            else "observed_widget_device_pixel_ratio"
        ),
        "render_attempts": render_attempts,
        "png_color_mode": "RGB",
        "render_content": content,
    }


def _physical_dimension(logical_size: int, device_pixel_ratio: float) -> int:
    """Match Qt's positive rounding for backing-store dimensions."""
    return max(int(logical_size * device_pixel_ratio + 0.5), 1)


def _region_content_evidence(
    image: Image.Image,
    box: tuple[int, int, int, int],
    *,
    minimum_color_count: int = 8,
) -> dict[str, Any]:
    """Measure whether one required image region contains painted UI detail."""
    x, y, width, height = box
    left = max(0, x)
    top = max(0, y)
    right = min(image.width, x + max(0, width))
    bottom = min(image.height, y + max(0, height))
    if right <= left or bottom <= top:
        return {
            "passed": False,
            "box": [left, top, right, bottom],
            "pixel_count": 0,
            "color_count": 0,
            "minimum_color_count": minimum_color_count,
            "dominant_color_ratio": 1.0,
            "channel_range": 0,
        }
    crop = image.crop((left, top, right, bottom)).convert("RGB")
    pixel_count = crop.width * crop.height
    colors = crop.getcolors(maxcolors=pixel_count) or []
    color_count = len(colors)
    dominant = max((count for count, _color in colors), default=pixel_count)
    extrema = cast(tuple[tuple[int, int], ...], crop.getextrema())
    channel_range = max(high - low for low, high in extrema)
    dominant_ratio = dominant / max(pixel_count, 1)
    passed = bool(
        pixel_count >= 64
        and color_count >= minimum_color_count
        and channel_range >= 16
        and dominant_ratio < 0.995
    )
    return {
        "passed": passed,
        "box": [left, top, right, bottom],
        "pixel_count": pixel_count,
        "color_count": color_count,
        "minimum_color_count": minimum_color_count,
        "dominant_color_ratio": round(dominant_ratio, 6),
        "channel_range": channel_range,
    }


def image_content_evidence(
    path: Path,
    *,
    required_regions: Mapping[str, tuple[int, int, int, int]] | None = None,
    text_region_names: Collection[str] = (),
) -> dict[str, Any]:
    """Reject blank frames and blank required shell/transcript/action regions."""
    with Image.open(path) as source:
        image = source.convert("RGB")
    full_frame = _region_content_evidence(
        image,
        (0, 0, image.width, image.height),
        minimum_color_count=2 if text_region_names else 8,
    )
    regions = {
        name: _region_content_evidence(
            image,
            box,
            minimum_color_count=2 if name in text_region_names else 8,
        )
        for name, box in (required_regions or {}).items()
    }
    return {
        "passed": bool(
            full_frame["passed"]
            and all(region["passed"] for region in regions.values())
        ),
        "full_frame": full_frame,
        "regions": regions,
    }


def _capture_immediate_widget_frame(
    widget: QWidget,
    output_path: Path,
    *,
    required_content_widgets: Mapping[str, QWidget],
) -> dict[str, Any]:
    """Save the already-painted backing store without a settle/retry loop."""
    pixmap = widget.grab()
    if pixmap.isNull() or not pixmap.save(str(output_path)):
        raise RuntimeError(f"Could not save immediate frame {output_path}.")
    with Image.open(output_path) as rendered:
        normalized = rendered.convert("RGB")
        normalized.save(output_path, format="PNG")
        pixel_size = list(normalized.size)
    required_regions = _scaled_child_regions(
        widget,
        required_content_widgets,
        pixel_width=pixel_size[0],
        pixel_height=pixel_size[1],
    )
    return {
        "pixel_size": pixel_size,
        "image_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "capture_method": "widget_grab",
        "widget_device_pixel_ratio": float(widget.devicePixelRatioF()),
        "capture_device_pixel_ratio": float(pixmap.devicePixelRatio()),
        "render_pixel_ratio": float(pixmap.devicePixelRatio()),
        "render_scale_evidence": "observed_widget_device_pixel_ratio",
        "png_color_mode": "RGB",
        "render_attempts": 1,
        "render_content": image_content_evidence(
            output_path,
            required_regions=required_regions,
        ),
    }


def _scaled_child_regions(
    root: QWidget,
    children: Mapping[str, QWidget],
    *,
    pixel_width: int,
    pixel_height: int,
) -> dict[str, tuple[int, int, int, int]]:
    """Map logical child geometry into a captured image's physical pixels."""
    scale_x = pixel_width / max(root.width(), 1)
    scale_y = pixel_height / max(root.height(), 1)
    regions: dict[str, tuple[int, int, int, int]] = {}
    for name, child in children.items():
        origin = child.mapTo(root, QPoint(0, 0))
        regions[name] = (
            round(origin.x() * scale_x),
            round(origin.y() * scale_y),
            max(round(child.width() * scale_x), 1),
            max(round(child.height() * scale_y), 1),
        )
    return regions


def _first_paint_panel_state(panel: ChatPanel, *, surface: str) -> dict[str, Any]:
    """Read the narrow idle contract while the first paint event is dispatched."""
    horizontal = panel.scroll_area.horizontalScrollBar()
    runtime_phase = str(getattr(getattr(panel, "_runtime_phase", None), "value", ""))
    geometry = _panel_relative_geometry(panel)
    manual_mode_selector_present = any(
        hasattr(panel, name)
        for name in ("mode_selector_widget", "ask_mode_btn", "workflow_mode_btn")
    )
    text_overflow = human_evidence._assistant_text_overflow(panel)
    checks = {
        "first_paint_event_is_first": True,
        "assistant_usable_width_at_least_320": panel.width() >= 320,
        "runtime_not_ready": runtime_phase == "idle",
        "manual_mode_selector_absent": not manual_mode_selector_present,
        "composer_visible": panel.input_field.isVisibleTo(panel),
        "composer_disabled": not panel.input_field.isEnabled(),
        "send_visible": panel.send_btn.isVisibleTo(panel),
        "send_disabled": not panel.send_btn.isEnabled(),
        "no_horizontal_scroll": bool(
            horizontal is not None and horizontal.maximum() == 0
        ),
        "visible_text_fits": not text_overflow,
        "composer_inside_panel": _geometry_inside(geometry["composer"]),
        "send_inside_panel": _geometry_inside(geometry["send"]),
    }
    return {
        "surface": surface,
        "assistant_usable_width": panel.width(),
        "assistant_height": panel.height(),
        "runtime_phase": runtime_phase,
        "manual_mode_selector_present": manual_mode_selector_present,
        "composer_enabled": panel.input_field.isEnabled(),
        "send_enabled": panel.send_btn.isEnabled(),
        "text_overflow": text_overflow,
        "panel_relative_geometry": geometry,
        "settle_layout_called_before_observation": False,
        "checks": checks,
    }


def _observe_first_paint(
    app: QApplication,
    panel: ChatPanel,
    capture_widget: QWidget,
    output_path: Path,
    *,
    surface: str,
    show: Callable[[], None],
    required_content_widgets: Mapping[str, QWidget],
) -> dict[str, Any]:
    """Observe one real first paint and then save its completed backing store."""
    probe = _FirstPaintProbe(
        lambda: _first_paint_panel_state(panel, surface=surface),
    )
    panel.installEventFilter(probe)
    show()
    process_event_turns = 0
    while probe.evidence is None and process_event_turns < 8:
        process_event_turns += 1
        app.processEvents()
    panel.removeEventFilter(probe)
    if probe.evidence is None:
        raise RuntimeError(f"{surface}: ChatPanel first paint was not observed.")

    evidence = dict(probe.evidence)
    evidence["process_event_turns_before_observation"] = process_event_turns
    evidence["paint_events_observed_before_capture"] = probe.paint_event_count
    capture = _capture_immediate_widget_frame(
        capture_widget,
        output_path,
        required_content_widgets=required_content_widgets,
    )
    evidence.update(capture)
    evidence["file"] = output_path.name
    checks = cast(dict[str, bool], evidence["checks"])
    # Native Qt backends may dispatch more than one invalidation paint in the
    # same event turn. The probe still samples the first one; requiring a
    # globally singular paint would make the evidence backend-dependent.
    checks["observation_captured_first_paint"] = evidence.get("paint_event_index") == 1
    checks["first_paint_render_content_ready"] = bool(
        capture["render_content"]["passed"]
    )
    evidence["passed"] = all(checks.values())
    return evidence


def _capture_standalone_first_paint(
    app: QApplication,
    output_dir: Path,
) -> dict[str, Any]:
    """Capture the initial 320px standalone panel before any settle helper."""
    panel = ChatPanel()
    panel.resize(320, 520)
    evidence = _observe_first_paint(
        app,
        panel,
        panel,
        output_dir / FIRST_PAINT_SCREEN_FILES[0],
        surface="standalone",
        show=panel.show,
        required_content_widgets={
            "runtime_state": panel.runtime_state_widget,
            "composer": panel.input_widget,
        },
    )
    panel.close()
    panel.deleteLater()
    app.processEvents()
    return evidence


def _capture_metric_tab_transition(
    app: QApplication,
    output_dir: Path,
) -> dict[str, Any]:
    """Capture the product empty state and the first observable epoch update."""
    tab = MetricTab("Accuracy")
    tab.setStyleSheet(Stylesheets.MAIN_WINDOW)
    tab.resize(520, 300)
    tab.show()
    _settle_layout(app, tab)

    before = human_evidence.training_metric_tab_evidence(tab)
    before_capture = _capture_widget(
        tab,
        output_dir / METRIC_TAB_SCREEN_FILES[0],
        render_pixel_ratio=1.0,
        required_content_widgets={"empty_state": tab.empty_state_label},
        text_content_regions=("empty_state",),
    )
    before.update(before_capture)
    before["file"] = METRIC_TAB_SCREEN_FILES[0]

    tab.update_plot(1, 72.0, 68.0)
    _settle_layout(app, tab)
    after = human_evidence.training_metric_tab_evidence(tab)
    canvas = tab.canvas
    if canvas is None:
        raise RuntimeError("MetricTab released its canvas before first-data capture.")
    after_capture = _capture_widget(
        tab,
        output_dir / METRIC_TAB_SCREEN_FILES[1],
        render_pixel_ratio=1.0,
        required_content_widgets={"metric_canvas": canvas},
    )
    after.update(after_capture)
    after["file"] = METRIC_TAB_SCREEN_FILES[1]

    checks = {
        "pre_first_epoch_empty_state_visible": before["empty_state_visible"] is True,
        "pre_first_epoch_canvas_hidden": before["canvas_visible"] is False,
        "pre_first_epoch_has_no_values": (
            before["epochs"] == []
            and before["train_values"] == []
            and before["validation_values"] == []
            and before["plotted_series"] == 0
        ),
        "empty_state_copy_names_first_epoch": (
            before["empty_state_text"]
            == "Training metrics will appear after the first training epoch."
        ),
        "first_data_empty_state_hidden": after["empty_state_visible"] is False,
        "first_data_canvas_visible": after["canvas_visible"] is True,
        "first_data_is_epoch_one": after["epochs"] == [1],
        "first_data_values_observed": (
            after["train_values"] == [72.0] and after["validation_values"] == [68.0]
        ),
        "first_data_series_observed": after["plotted_series"] == 2,
        "pre_first_epoch_rendered": bool(before_capture["render_content"]["passed"]),
        "first_data_rendered": bool(after_capture["render_content"]["passed"]),
    }
    transition = {
        "pre_first_epoch": before,
        "first_data": after,
        "transition_observed": all(checks.values()),
        "checks": checks,
        "passed": all(checks.values()),
    }
    tab.close()
    tab.deleteLater()
    app.processEvents()
    return transition


def _set_dock_panel_width(
    app: QApplication,
    window: QMainWindow,
    dock: QDockWidget,
    panel: ChatPanel,
    target_width: int,
) -> None:
    """Resize a real dock until its ChatPanel content width is exactly target."""
    for _ in range(8):
        current = panel.width()
        if current == target_width:
            break
        requested = max(dock.minimumWidth(), dock.width() + target_width - current)
        window.resizeDocks([dock], [requested], Qt.Orientation.Horizontal)
        _settle_layout(app, window)
    if panel.width() != target_width:
        raise RuntimeError(
            f"Could not establish {target_width}px ChatPanel width in QDockWidget; "
            f"observed {panel.width()}px."
        )


def _main_window_screen_record(
    app: QApplication,
    output_dir: Path,
    window: MainWindow,
    dock: QDockWidget,
    panel: ChatPanel,
    *,
    name: str,
    filename: str,
) -> dict[str, Any]:
    _settle_layout(app, window)
    dock_evidence = human_evidence.assistant_dock_evidence(dock, panel)
    placeholder = human_evidence.assistant_composer_placeholder_evidence(panel)
    panel_geometry = _panel_relative_geometry(panel)
    response_actions = [
        str(button.property("assistantFullLabel") or button.text())
        for button in panel.response_actions_widget.findChildren(QToolButton)
        if button.isVisibleTo(panel)
    ]
    summary_label = window.findChild(QLabel, "DataSummaryEmpty")
    summary_text_fit = _wrapped_label_text_fit(summary_label)
    checks = {
        "real_main_window_visible": window.isVisible(),
        "real_qdockwidget_visible": dock.isVisible(),
        "dock_is_not_floating": not dock.isFloating(),
        "assistant_uses_product_standard_width": (
            panel.width() == window.ASSISTANT_DOCK_STANDARD_WIDTH
        ),
        "assistant_panel_fills_dock_width": bool(
            dock_evidence.get("panel_fills_dock_width")
        ),
        "panel_inside_dock": bool(dock_evidence.get("panel_inside_bounds")),
        "no_horizontal_scroll": (
            int(dock_evidence.get("horizontal_scrollbar_max", -1)) == 0
        ),
        "visible_text_fits": not dock_evidence.get("overflowing_widgets"),
        "composer_placeholder_fits": placeholder["fits"],
        "composer_inside_panel_on_all_sides": _geometry_inside(
            panel_geometry["composer"]
        ),
        "send_inside_panel_on_all_sides": _geometry_inside(panel_geometry["send"]),
        "legacy_mode_selector_absent": not any(
            hasattr(panel, name)
            for name in ("mode_selector_widget", "ask_mode_btn", "workflow_mode_btn")
        ),
        "response_action_inside_panel_on_all_sides": (
            not response_actions or _geometry_inside(panel_geometry["response_action"])
        ),
        "visible_data_summary_empty_copy_fits": (
            summary_text_fit["fits"] if summary_text_fit["visible"] else True
        ),
    }
    evidence: dict[str, Any] = {
        "name": name,
        "file": filename,
        "logical_size": [window.width(), window.height()],
        "render_pixel_ratio": 1.0,
        "render_scale_evidence": "logical_widget_render",
        "native_display_scaling_observed": False,
        "message_kinds": [
            bubble.presentation_kind.value for bubble in _layout_bubbles(panel)
        ],
        "state_labels": {},
        "checks": checks,
        "failures": [key for key, passed in checks.items() if not passed],
        "dock": dock_evidence,
        "composer_placeholder": placeholder,
        "visible_response_actions": response_actions,
        "panel_relative_geometry": panel_geometry,
        "data_summary_empty_copy": summary_text_fit,
    }
    bubbles = _layout_bubbles(panel)
    if not bubbles:
        raise RuntimeError(f"{name}: assistant transcript has no rendered message.")
    required_content_widgets: dict[str, QWidget] = {
        # The stacked page may intentionally be a quiet loading/placeholder surface.
        # The real product-shell evidence is the rendered navigation bar.
        "main_shell": window.top_bar,
        "assistant_transcript": bubbles[-1],
        "assistant_primary_action": panel.send_btn,
    }
    if panel.turn_activity_widget.isVisibleTo(panel):
        required_content_widgets["assistant_activity"] = panel.turn_activity_widget
    capture = _capture_widget(
        window,
        output_dir / filename,
        render_pixel_ratio=1.0,
        required_content_widgets=required_content_widgets,
        text_content_regions=(
            ("assistant_activity",)
            if "assistant_activity" in required_content_widgets
            else ()
        ),
    )
    evidence.update(capture)
    checks["render_content_ready"] = capture["render_content"]["passed"]
    evidence["failures"] = [key for key, passed in checks.items() if not passed]
    return evidence


def _wrapped_label_text_fit(label: QLabel | None) -> dict[str, Any]:
    """Measure one visible wrapped label instead of trusting its widget bounds."""
    if label is None or not label.isVisibleTo(label.window()):
        return {"visible": False, "fits": True}
    content = label.contentsRect()
    flags = int(label.alignment())
    if label.wordWrap():
        flags |= int(Qt.TextFlag.TextWordWrap)
    measured = label.fontMetrics().boundingRect(
        QRect(0, 0, max(1, content.width()), 10_000),
        flags,
        label.text(),
    )
    return {
        "visible": True,
        "word_wrap": label.wordWrap(),
        "text": label.text(),
        "available_width": content.width(),
        "available_height": content.height(),
        "required_width": measured.width(),
        "required_height": measured.height(),
        "fits": bool(
            measured.width() <= content.width()
            and measured.height() <= content.height()
        ),
    }


def _capture_manager_teardown(manager: Any) -> dict[str, Any]:
    """Observe manager/runtime/dispatcher cleanup without blocking on QThread."""
    runtime = manager.assistant_runtime
    dispatcher = runtime.dispatcher
    controller = _TeardownProbeController()
    dispatcher.bind(controller)
    command_thread = dispatcher.command_thread
    if not isinstance(command_thread, QThread):
        raise RuntimeError("Assistant teardown probe did not create a QThread.")

    runtime_results: list[dict[str, Any]] = []
    dispatcher_results: list[dict[str, Any]] = []
    thread_finished_events: list[bool] = []
    runtime.cleanup_finished.connect(
        lambda ok, message: runtime_results.append(
            {"ok": bool(ok), "message": str(message or "")}
        )
    )
    dispatcher.cleanup_finished.connect(
        lambda ok, message: dispatcher_results.append(
            {"ok": bool(ok), "message": str(message or "")}
        )
    )
    command_thread.finished.connect(lambda: thread_finished_events.append(True))

    running_before_close = command_thread.isRunning()
    heartbeat_times: list[float] = []
    heartbeat = QTimer()
    heartbeat.setInterval(5)
    heartbeat.timeout.connect(lambda: heartbeat_times.append(time.perf_counter()))
    heartbeat.start()
    close_started = time.perf_counter()
    initial_close_result = bool(manager.close())
    initial_close_call_duration_ms = (time.perf_counter() - close_started) * 1000.0

    def terminal_observed() -> bool:
        return bool(
            runtime_results
            and dispatcher_results
            and thread_finished_events
            and not command_thread.isRunning()
        )

    timed_out = False
    if not terminal_observed():
        loop = QEventLoop()
        poll = QTimer()
        poll.setInterval(5)
        timeout = QTimer()
        timeout.setSingleShot(True)

        def poll_terminal() -> None:
            if terminal_observed():
                loop.quit()

        poll.timeout.connect(poll_terminal)
        timeout.timeout.connect(loop.quit)
        poll.start()
        timeout.start(5000)
        loop.exec()
        timed_out = not terminal_observed()
        poll.stop()
        timeout.stop()

    heartbeat.stop()
    final_close_result = bool(manager.close())
    heartbeat_gaps_ms = [
        (current - previous) * 1000.0 for previous, current in pairwise(heartbeat_times)
    ]
    max_heartbeat_gap_ms = max(heartbeat_gaps_ms, default=0.0)
    gui_responsive = bool(
        initial_close_call_duration_ms < 100.0
        and len(heartbeat_times) >= 2
        and max_heartbeat_gap_ms < 100.0
    )
    runtime_result = runtime_results[-1] if runtime_results else {}
    dispatcher_result = dispatcher_results[-1] if dispatcher_results else {}
    runtime_state = str(getattr(runtime.state, "value", runtime.state))
    dispatcher_state = str(getattr(dispatcher.state, "value", dispatcher.state))
    checks = {
        "manager_close_reached_terminal": final_close_result,
        "runtime_cleanup_finished_observed": bool(runtime_results),
        "runtime_cleanup_succeeded": runtime_result.get("ok") is True,
        "dispatcher_cleanup_finished_observed": bool(dispatcher_results),
        "dispatcher_cleanup_succeeded": dispatcher_result.get("ok") is True,
        "dedicated_qthread_created": command_thread.objectName()
        == "AssistantCommandThread",
        "dedicated_qthread_was_running": running_before_close,
        "dedicated_qthread_finished_signal_observed": bool(thread_finished_events),
        "dedicated_qthread_not_running_after_cleanup": not command_thread.isRunning(),
        "runtime_closed": runtime_state == "closed",
        "dispatcher_closed": dispatcher_state == "closed",
        "signal_observation_did_not_time_out": not timed_out,
        "manager_close_returned_within_budget": (
            initial_close_call_duration_ms < 100.0
        ),
        "gui_heartbeat_observed_during_cleanup": len(heartbeat_times) >= 2,
        "gui_heartbeat_gap_within_budget": max_heartbeat_gap_ms < 100.0,
        "gui_thread_responsive_during_cleanup": gui_responsive,
    }
    return {
        "manager_close_requested": True,
        "manager_close_initial_result": initial_close_result,
        "manager_close_final_result": final_close_result,
        "manager_close_finished": final_close_result,
        "runtime_cleanup_finished": {
            "observed": bool(runtime_results),
            **runtime_result,
        },
        "dispatcher_cleanup_finished": {
            "observed": bool(dispatcher_results),
            **dispatcher_result,
        },
        "dedicated_qthread": {
            "created": command_thread.objectName() == "AssistantCommandThread",
            "object_name": command_thread.objectName(),
            "running_before_close": running_before_close,
            "finished_signal_observed": bool(thread_finished_events),
            "running_after_cleanup": command_thread.isRunning(),
        },
        "runtime_state_after_cleanup": runtime_state,
        "dispatcher_state_after_cleanup": dispatcher_state,
        "initial_close_call_duration_ms": round(
            initial_close_call_duration_ms,
            3,
        ),
        "gui_heartbeat": {
            "interval_ms": 5,
            "count_during_cleanup": len(heartbeat_times),
            "max_gap_ms": round(max_heartbeat_gap_ms, 3),
            "responsive": gui_responsive,
        },
        "gui_thread_blocking_wait_used": not gui_responsive,
        "observation_method": ("qt_signals_event_loop_heartbeat_and_close_latency"),
        "timed_out": timed_out,
        "checks": checks,
        "passed": all(checks.values()),
    }


def _capture_main_window_dock_walkthrough(
    app: QApplication,
    output_dir: Path,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    dict[str, Any],
    dict[str, Any],
]:
    """Drive real dock actions and typed busy states in the composed product shell."""
    window = cast(MainWindow, MainWindow(Study()))
    window.setWindowState(Qt.WindowState.WindowNoState)
    # The product shrinks the dock to its supported 320px floor when the
    # workflow surface needs the remaining width. This establishes the real
    # narrow first-paint contract without pinning the ChatPanel itself.
    window.resize(
        MainWindow.ASSISTANT_DOCK_CENTRAL_MINIMUM_WIDTH
        + MainWindow.ASSISTANT_DOCK_MINIMUM_WIDTH,
        760,
    )
    window.show()
    _settle_layout(app, window)
    window.init_agent()
    manager = window.agent_manager
    if manager is None or manager.chat_dock is None or manager.chat_panel is None:
        raise RuntimeError("MainWindow did not create the real assistant dock.")
    dock = cast(QDockWidget, manager.chat_dock)
    panel = cast(ChatPanel, manager.chat_panel)
    first_paint = _observe_first_paint(
        app,
        panel,
        window,
        output_dir / FIRST_PAINT_SCREEN_FILES[1],
        surface="real_dock",
        show=dock.show,
        required_content_widgets={
            "assistant_runtime_state": panel.runtime_state_widget,
            "assistant_composer": panel.input_widget,
        },
    )
    assistant_entry_origin = window.ai_btn.mapTo(window, QPoint(0, 0))
    dock_origin = dock.mapTo(window, QPoint(0, 0))
    first_paint.update(
        {
            "real_main_window": isinstance(window, MainWindow),
            "real_qdockwidget": isinstance(dock, QDockWidget),
            "dock_visible": dock.isVisible(),
            "dock_floating": dock.isFloating(),
            "panel_is_dock_widget": dock.widget() is panel,
            "assistant_entry": {
                "label": window.ai_btn.text(),
                "width": window.ai_btn.width(),
                "minimum_width": window.ai_btn.minimumWidth(),
                "left": assistant_entry_origin.x(),
                "right": assistant_entry_origin.x() + window.ai_btn.width(),
                "dock_left": dock_origin.x(),
                "required_text_width": (
                    window.ai_btn.fontMetrics().horizontalAdvance(window.ai_btn.text())
                    + 24
                ),
            },
            "top_bar_layout": {
                "width": window.top_bar.width(),
                "compact_navigation_visible": (
                    window.compact_nav_combo.isVisibleTo(window)
                ),
                "compact_navigation_geometry": [
                    window.compact_nav_combo.x(),
                    window.compact_nav_combo.y(),
                    window.compact_nav_combo.width(),
                    window.compact_nav_combo.height(),
                ],
                "flexible_space_hidden": window.top_bar_spacer.isHidden(),
                "flexible_space_geometry": [
                    window.top_bar_spacer.x(),
                    window.top_bar_spacer.y(),
                    window.top_bar_spacer.width(),
                    window.top_bar_spacer.height(),
                ],
                "visible_navigation_buttons": sum(
                    button.isVisibleTo(window) for button in window.nav_btns
                ),
            },
        }
    )
    first_paint_checks = cast(dict[str, bool], first_paint["checks"])
    first_paint_checks.update(
        {
            "real_main_window": first_paint["real_main_window"],
            "real_qdockwidget": first_paint["real_qdockwidget"],
            "dock_visible": first_paint["dock_visible"],
            "dock_not_floating": not first_paint["dock_floating"],
            "panel_owned_by_dock": first_paint["panel_is_dock_widget"],
            "assistant_entry_text_fits": (
                first_paint["assistant_entry"]["width"]
                >= first_paint["assistant_entry"]["required_text_width"]
            ),
            "assistant_entry_inside_visible_central_area": (
                first_paint["assistant_entry"]["left"] >= 0
                and first_paint["assistant_entry"]["right"]
                <= first_paint["assistant_entry"]["dock_left"]
            ),
        }
    )
    first_paint["passed"] = all(first_paint_checks.values())
    panel.set_runtime_state("ready")
    # Return to the normal product shell. MainWindow owns the 420px standard
    # dock width and the child panel remains responsive to that live geometry.
    window.resize(1180, 760)
    _settle_layout(app, window)
    _set_dock_panel_width(
        app,
        window,
        dock,
        panel,
        MainWindow.ASSISTANT_DOCK_STANDARD_WIDTH,
    )

    restored_presentation_id = "restored-open-dataset"
    source_history = ChatController()
    source_history.add_user_message("Show me where to review EEG data.")
    source_history.add_agent_message(
        "I can help review EEG files before they are loaded.",
        presentation_kind=ChatMessagePresentationKind.ASSISTANT,
        presentation_id=restored_presentation_id,
        actions=(
            ChatResponseAction(
                action_id="open-restored-dataset",
                label="Open Dataset",
                kind=ChatResponseActionKind.OPEN_PANEL,
                panel=ChatPanelTarget.DATASET,
            ),
        ),
    )
    active_identity_events: list[object] = []
    selected_identity_events: list[str] = []
    panel.active_response_presentation_changed.connect(active_identity_events.append)
    panel.response_action_requested.connect(
        lambda selection: selected_identity_events.append(selection.presentation_id)
    )
    restored_count = manager.chat_controller.restore_history(
        source_history.get_history()
    )
    window._ensure_panel_loaded(1)
    window._activate_page(1)
    _settle_layout(app, window)
    restored_records = manager.chat_controller.get_typed_history()
    restored_action_buttons = [
        button
        for button in panel.response_actions_widget.findChildren(QToolButton)
        if button.isVisibleTo(panel)
    ]
    restored_actions_inert = bool(
        restored_count == 2
        and restored_records
        and all(not record.has_active_actions for record in restored_records)
        and not restored_action_buttons
    )

    live_submission = manager._assistant_turn_state.begin_submission()
    live_correlation = AssistantTurnCorrelation(
        generation=live_submission.generation,
        turn_id=700,
    )
    if not manager._assistant_turn_state.accept_admission(
        live_submission,
        live_correlation,
    ):
        raise RuntimeError("Could not admit the live response-action capture turn.")
    presentation_id = "live-open-dataset"
    manager._handle_response_presentation(
        AssistantResponsePresentation(
            correlation=live_correlation,
            presentation_id=presentation_id,
            text="Open Dataset to review the current EEG workspace.",
            kind=AssistantResponseKind.CLARIFICATION,
            actions=(
                AssistantResponseAction.open_panel(
                    "Open Dataset",
                    AssistantPanelTarget.DATASET,
                ),
            ),
        )
    )
    _settle_layout(app, window)
    action = next(
        (
            button
            for button in panel.response_actions_widget.findChildren(QToolButton)
            if button.isVisibleTo(panel) and button.accessibleName() == "Open Dataset"
        ),
        None,
    )
    if action is None:
        raise RuntimeError("Real response action was not visible in the dock.")
    bubbles = _layout_bubbles(panel)
    if not bubbles:
        raise RuntimeError("Restored response did not render in the real dock.")
    pre_click_screen = _main_window_screen_record(
        app,
        output_dir,
        window,
        dock,
        panel,
        name="main_window_dock_420_action_visible",
        filename="main-window-dock-420-action-visible.png",
    )
    before_index = window.stack.currentIndex()
    before_widget = window.stack.currentWidget()
    before_widget_type = (
        type(before_widget).__name__ if before_widget is not None else ""
    )
    cast(Any, QTest.mouseClick)(action, Qt.MouseButton.LeftButton)
    _settle_layout(app, window)
    after_index = window.stack.currentIndex()
    after_widget = window.stack.currentWidget()
    after_widget_type = type(after_widget).__name__ if after_widget is not None else ""
    action_clicked = before_index != after_index and after_index == 0
    manager._on_assistant_turn_finished(
        AssistantTurnTerminal(
            correlation=live_correlation,
            outcome="completed",
        )
    )
    screens = [
        pre_click_screen,
        _main_window_screen_record(
            app,
            output_dir,
            window,
            dock,
            panel,
            name="main_window_dock_420_action_click",
            filename="main-window-dock-420-action-click.png",
        ),
    ]

    stopping_turn_id = 701
    stopping_submission = manager._assistant_turn_state.begin_submission()
    stopping_correlation = AssistantTurnCorrelation(
        generation=stopping_submission.generation,
        turn_id=stopping_turn_id,
    )
    if not manager._assistant_turn_state.accept_admission(
        stopping_submission,
        stopping_correlation,
    ):
        raise RuntimeError("Could not admit the stopping capture turn.")
    manager.on_assistant_activity_changed(
        AssistantTurnActivity(
            AssistantTurnActivityPhase.THINKING,
            turn_id=stopping_turn_id,
            generation=stopping_correlation.generation,
        )
    )
    _settle_layout(app, window)
    cancellable_state = {
        "button_text": panel.send_btn.text(),
        "button_enabled": panel.send_btn.isEnabled(),
        "cancelability": panel.turn_activity_widget.property("assistantCancelability"),
    }
    stop_clicks: list[bool] = []
    panel.stop_generation.connect(lambda: stop_clicks.append(True))
    cast(Any, QTest.mouseClick)(panel.send_btn, Qt.MouseButton.LeftButton)
    manager.on_assistant_activity_changed(
        AssistantTurnActivity(
            AssistantTurnActivityPhase.STOPPING,
            turn_id=stopping_turn_id,
            generation=stopping_correlation.generation,
        )
    )
    _settle_layout(app, window)
    stopping_state = {
        "button_text": panel.send_btn.text(),
        "button_enabled": panel.send_btn.isEnabled(),
        "cancelability": panel.turn_activity_widget.property("assistantCancelability"),
        "real_stop_click_emitted": stop_clicks == [True],
    }
    screens.append(
        _main_window_screen_record(
            app,
            output_dir,
            window,
            dock,
            panel,
            name="main_window_dock_420_stopping",
            filename="main-window-dock-420-stopping.png",
        )
    )

    late_event_states: list[tuple[str, bool]] = []
    for phase in (
        AssistantTurnActivityPhase.THINKING,
        AssistantTurnActivityPhase.RUNNING_COMMAND,
    ):
        manager.on_assistant_activity_changed(
            AssistantTurnActivity(
                phase,
                command_name=(
                    "scan_source"
                    if phase is AssistantTurnActivityPhase.RUNNING_COMMAND
                    else ""
                ),
                turn_id=stopping_turn_id,
                generation=stopping_correlation.generation,
            )
        )
        late_event_states.append((panel.send_btn.text(), panel.send_btn.isEnabled()))
    stopping_state["late_activity_latched"] = all(
        text == "Stopping" and not enabled for text, enabled in late_event_states
    )
    manager._on_assistant_turn_finished(
        AssistantTurnTerminal(
            correlation=stopping_correlation,
            outcome="cancelled",
        )
    )
    command_submission = manager._assistant_turn_state.begin_submission()
    command_correlation = AssistantTurnCorrelation(
        generation=command_submission.generation,
        turn_id=702,
    )
    if not manager._assistant_turn_state.accept_admission(
        command_submission,
        command_correlation,
    ):
        raise RuntimeError("Could not admit the command capture turn.")
    manager.on_assistant_activity_changed(
        AssistantTurnActivity(
            AssistantTurnActivityPhase.RUNNING_COMMAND,
            command_name="scan_source",
            turn_id=command_correlation.turn_id,
            generation=command_correlation.generation,
        )
    )
    _settle_layout(app, window)
    command_state = {
        "button_text": panel.send_btn.text(),
        "button_enabled": panel.send_btn.isEnabled(),
        "cancelability": panel.turn_activity_widget.property("assistantCancelability"),
        "primary_status": panel.turn_activity_title.text(),
        "step": panel.turn_activity_step.text(),
    }
    screens.append(
        _main_window_screen_record(
            app,
            output_dir,
            window,
            dock,
            panel,
            name="main_window_dock_420_command_running",
            filename="main-window-dock-420-command-running.png",
        )
    )

    _set_dock_panel_width(
        app,
        window,
        dock,
        panel,
        MainWindow.ASSISTANT_DOCK_STANDARD_WIDTH,
    )
    assistant_viewport = panel.scroll_area.viewport()
    if assistant_viewport is None:
        raise RuntimeError("Real assistant dock viewport is unavailable.")
    walkthrough = {
        "real_main_window": isinstance(window, MainWindow),
        "real_qdockwidget": isinstance(dock, QDockWidget),
        "assistant_usable_width": panel.width(),
        "assistant_viewport_width": assistant_viewport.width(),
        "action_click": {
            "label": "Open Dataset",
            "history_source": "live_correlated_response",
            "restored_record_count": restored_count,
            "restored_actions_inert": restored_actions_inert,
            "presentation_identity_from_ui": bool(
                presentation_id in active_identity_events
                and selected_identity_events == [presentation_id]
            ),
            "pre_click_render_content": pre_click_screen["render_content"],
            "clicked": action_clicked,
            "before_panel_index": before_index,
            "after_panel_index": after_index,
            "before_panel_widget_type": before_widget_type,
            "after_panel_widget_type": after_widget_type,
            "before_panel_materialized": bool(
                before_widget is not None
                and before_widget_type != "_LazyPanelPlaceholder"
            ),
            "after_panel_materialized": bool(
                after_widget is not None
                and after_widget_type != "_LazyPanelPlaceholder"
            ),
            "before_placeholder_visible": bool(
                before_widget is not None
                and before_widget_type == "_LazyPanelPlaceholder"
                and before_widget.isVisibleTo(window)
            ),
            "after_placeholder_visible": bool(
                after_widget is not None
                and after_widget_type == "_LazyPanelPlaceholder"
                and after_widget.isVisibleTo(window)
            ),
            "workflow_panel_opened": after_index == 0,
            "actions_consumed": panel.response_actions_widget.isHidden(),
        },
        "states": {
            "cancellable": cancellable_state,
            "stopping": stopping_state,
            "application_command": command_state,
        },
    }
    teardown = _capture_manager_teardown(manager)
    window.hide()
    window.deleteLater()
    app.processEvents()
    return walkthrough, screens, first_paint, teardown


def _machine_checks_passed(value: object) -> bool:
    return bool(
        isinstance(value, dict)
        and value
        and all(passed is True for passed in value.values())
    )


def _first_paint_contract_failures(payload: dict[str, Any]) -> list[str]:
    contract = payload.get("first_paint_320_contract")
    if not isinstance(contract, dict):
        return ["320px first-paint contract is missing"]
    failures: list[str] = []
    if contract.get("target_width") != 320 or contract.get("passed") is not True:
        failures.append("320px first-paint contract did not pass")
    for surface, expected_file in zip(
        ("standalone", "real_dock"),
        FIRST_PAINT_SCREEN_FILES,
        strict=True,
    ):
        evidence = contract.get(surface)
        label = f"{surface.replace('_', ' ')} first-paint"
        if not isinstance(evidence, dict):
            failures.append(f"{label} evidence is missing")
            continue
        required = bool(
            evidence.get("file") == expected_file
            and evidence.get("observed_during_first_paint_event") is True
            and evidence.get("paint_event_index") == 1
            and evidence.get("settle_layout_called_before_observation") is False
            and int(evidence.get("assistant_usable_width") or 0) >= 320
            and evidence.get("runtime_phase") == "idle"
            and evidence.get("manual_mode_selector_present") is False
            and evidence.get("composer_enabled") is False
            and evidence.get("send_enabled") is False
            and evidence.get("passed") is True
            and _machine_checks_passed(evidence.get("checks"))
            and isinstance(evidence.get("render_content"), dict)
            and evidence["render_content"].get("passed") is True
        )
        if surface == "real_dock":
            required = bool(
                required
                and evidence.get("real_main_window") is True
                and evidence.get("real_qdockwidget") is True
                and evidence.get("dock_visible") is True
                and evidence.get("dock_floating") is False
                and evidence.get("panel_is_dock_widget") is True
            )
        if not required:
            checks = evidence.get("checks")
            failed_checks = (
                [name for name, passed in checks.items() if passed is not True]
                if isinstance(checks, dict)
                else ["checks_missing"]
            )
            failures.append(
                f"{label} contract failed "
                f"(width={evidence.get('assistant_usable_width')}, "
                f"paint_events={evidence.get('paint_events_observed_before_capture')}, "
                f"failed_checks={failed_checks})"
            )
    return failures


def _teardown_contract_failures(payload: dict[str, Any]) -> list[str]:
    teardown = payload.get("teardown")
    if not isinstance(teardown, dict):
        return ["teardown contract is missing"]
    runtime = teardown.get("runtime_cleanup_finished")
    dispatcher = teardown.get("dispatcher_cleanup_finished")
    thread = teardown.get("dedicated_qthread")
    passed = bool(
        teardown.get("passed") is True
        and teardown.get("manager_close_requested") is True
        and teardown.get("manager_close_finished") is True
        and isinstance(runtime, dict)
        and runtime.get("observed") is True
        and runtime.get("ok") is True
        and isinstance(dispatcher, dict)
        and dispatcher.get("observed") is True
        and dispatcher.get("ok") is True
        and isinstance(thread, dict)
        and thread.get("created") is True
        and thread.get("object_name") == "AssistantCommandThread"
        and thread.get("running_before_close") is True
        and thread.get("finished_signal_observed") is True
        and thread.get("running_after_cleanup") is False
        and teardown.get("runtime_state_after_cleanup") == "closed"
        and teardown.get("dispatcher_state_after_cleanup") == "closed"
        and float(teardown.get("initial_close_call_duration_ms", 1000.0)) < 100.0
        and isinstance(teardown.get("gui_heartbeat"), dict)
        and teardown["gui_heartbeat"].get("count_during_cleanup", 0) >= 2
        and float(teardown["gui_heartbeat"].get("max_gap_ms", 1000.0)) < 100.0
        and teardown["gui_heartbeat"].get("responsive") is True
        and teardown.get("gui_thread_blocking_wait_used") is False
        and teardown.get("observation_method")
        == "qt_signals_event_loop_heartbeat_and_close_latency"
        and teardown.get("timed_out") is False
        and _machine_checks_passed(teardown.get("checks"))
    )
    return [] if passed else ["teardown contract did not reach terminal Qt cleanup"]


def _metric_tab_contract_failures(payload: dict[str, Any]) -> list[str]:
    transition = payload.get("metric_tab_transition")
    if not isinstance(transition, dict):
        return ["MetricTab transition evidence is missing"]
    before = transition.get("pre_first_epoch")
    after = transition.get("first_data")
    passed = bool(
        transition.get("passed") is True
        and transition.get("transition_observed") is True
        and _machine_checks_passed(transition.get("checks"))
        and isinstance(before, dict)
        and before.get("file") == METRIC_TAB_SCREEN_FILES[0]
        and before.get("empty_state_visible") is True
        and before.get("canvas_visible") is False
        and before.get("epochs") == []
        and before.get("train_values") == []
        and before.get("validation_values") == []
        and before.get("plotted_series") == 0
        and isinstance(before.get("render_content"), dict)
        and before["render_content"].get("passed") is True
        and isinstance(after, dict)
        and after.get("file") == METRIC_TAB_SCREEN_FILES[1]
        and after.get("empty_state_visible") is False
        and after.get("canvas_visible") is True
        and after.get("epochs") == [1]
        and after.get("train_values") == [72.0]
        and after.get("validation_values") == [68.0]
        and after.get("plotted_series") == 2
        and isinstance(after.get("render_content"), dict)
        and after["render_content"].get("passed") is True
    )
    return [] if passed else ["MetricTab empty-state to first-data contract failed"]


def _capture_assistant_settings(
    app: QApplication,
    output_dir: Path,
) -> dict[str, Any]:
    """Capture collapsed and advanced Settings from the real product dialog."""
    config = LLMConfig(device="cpu")
    config.inference_mode = "local"
    config.active_mode = "local"
    config.model_name = LLMConfig.default_local_model_id()
    config.local_model_enabled = True
    lifecycle = _AssistantSettingsCaptureLifecycle()
    dialog = ModelSettingsDialog(
        config=config,
        download_lifecycle=lifecycle,
    )
    dialog.show()
    _settle_layout(app, dialog)
    if not lifecycle.inspection_requests:
        dialog.check_local_model_status()
        _settle_layout(app, dialog)
    lifecycle.publish_ready_inspection()
    _settle_layout(app, dialog)

    def record(filename: str, *, advanced: bool) -> dict[str, Any]:
        body_viewport = dialog.settings_body_scroll.viewport()
        if body_viewport is None:
            raise RuntimeError("Assistant Settings scroll viewport is unavailable.")
        visible_segment_buttons = [
            button
            for control in (
                dialog.response_style_control,
                dialog.response_length_control,
            )
            for button in control.findChildren(QAbstractButton)
            if button.isVisibleTo(dialog)
        ]
        segment_text_fits = all(
            button.fontMetrics().horizontalAdvance(button.text()) + 20
            <= button.contentsRect().width() + 2
            for button in visible_segment_buttons
        )
        footer_inside = all(
            human_evidence._widget_inside(dialog, button)
            for button in (dialog.btn_cancel, dialog.btn_activate)
        )
        fields_inside_viewport = True
        if advanced:
            fields_inside_viewport = all(
                human_evidence._widget_inside(body_viewport, field)
                for field in (
                    dialog.temperature_spin,
                    dialog.top_p_spin,
                    dialog.max_tokens_spin,
                )
            )
        checks = {
            "dialog_title_complete": dialog.windowTitle() == "Assistant Settings",
            "heading_complete": dialog.heading_label.text() == "Assistant Settings",
            "model_status_ready": (
                dialog.local_status_label.text() == "Model: Installed"
                and dialog.local_runtime_label.text() == "Environment check: Ready"
            ),
            "primary_controls_selected": (
                dialog.response_style_control.selected_key() == "balanced"
                and dialog.response_length_control.selected_key() == "standard"
            ),
            "segment_text_fits": segment_text_fits,
            "horizontal_scroll_absent": (
                (horizontal_scroll := dialog.settings_body_scroll.horizontalScrollBar())
                is not None
                and horizontal_scroll.maximum() == 0
            ),
            "footer_inside_dialog": footer_inside,
            "buttons_text_only": (
                dialog.btn_activate.icon().isNull()
                and dialog.btn_cancel.icon().isNull()
            ),
            "save_is_primary_and_enabled": (
                dialog.btn_activate.objectName() == "AssistantPrimaryButton"
                and dialog.btn_activate.isEnabled()
            ),
            "advanced_visibility_matches": (
                dialog.advanced_content.isVisibleTo(dialog) is advanced
            ),
            "advanced_fields_inside_viewport": fields_inside_viewport,
            "spinbox_strips_absent": (
                not advanced
                or all(
                    field.buttonSymbols() is QAbstractSpinBox.ButtonSymbols.NoButtons
                    for field in (
                        dialog.temperature_spin,
                        dialog.top_p_spin,
                        dialog.max_tokens_spin,
                    )
                )
            ),
        }
        capture = _capture_widget(
            dialog,
            output_dir / filename,
            render_pixel_ratio=1.0,
            required_content_widgets={
                "footer": dialog.footer_widget,
                **(
                    {"advanced_fields": dialog.max_tokens_spin}
                    if advanced
                    else {
                        "heading": dialog.heading_label,
                        "model": dialog.local_model_combo,
                        "response_style": dialog.response_style_control,
                    }
                ),
            },
            text_content_regions=("heading",) if not advanced else (),
        )
        checks["render_content_ready"] = capture["render_content"]["passed"]
        return {
            "file": filename,
            "state": "advanced" if advanced else "collapsed",
            "logical_size": [dialog.width(), dialog.height()],
            "checks": checks,
            "failures": [name for name, passed in checks.items() if not passed],
            **capture,
        }

    collapsed = record(ASSISTANT_SETTINGS_SCREEN_FILES[0], advanced=False)
    dialog.advanced_toggle.setChecked(True)
    _settle_layout(app, dialog)
    vertical_scroll = dialog.settings_body_scroll.verticalScrollBar()
    if vertical_scroll is not None:
        vertical_scroll.setValue(vertical_scroll.maximum())
    _settle_layout(app, dialog)
    advanced = record(ASSISTANT_SETTINGS_SCREEN_FILES[1], advanced=True)
    screens = [collapsed, advanced]
    result = {
        "screens": screens,
        "passed": all(
            all(record["checks"].values()) and not record["failures"]
            for record in screens
        ),
    }
    dialog.close()
    dialog.deleteLater()
    app.processEvents()
    return result


def _assistant_settings_contract_failures(payload: dict[str, Any]) -> list[str]:
    settings = payload.get("assistant_settings")
    if not isinstance(settings, dict):
        return ["Assistant Settings presentation evidence is missing"]
    screens = settings.get("screens")
    if (
        not isinstance(screens, list)
        or tuple(screen.get("file") for screen in screens if isinstance(screen, dict))
        != ASSISTANT_SETTINGS_SCREEN_FILES
    ):
        return ["Assistant Settings screenshot set is incomplete or out of order"]
    failures: list[str] = []
    artifact_directory = Path(str(payload.get("artifact_directory") or ""))
    for record in screens:
        name = str(record.get("state") or record.get("file") or "settings")
        checks = record.get("checks")
        if not isinstance(checks, dict):
            failures.append(f"Assistant Settings {name}: checks are missing")
            continue
        failures.extend(
            f"Assistant Settings {name}: {check}"
            for check, passed in checks.items()
            if passed is not True
        )
        screenshot_path = artifact_directory / str(record.get("file") or "")
        if not screenshot_path.is_file():
            failures.append(f"Assistant Settings {name}: screenshot is missing")
            continue
        observed_hash = hashlib.sha256(screenshot_path.read_bytes()).hexdigest()
        if record.get("image_sha256") != observed_hash:
            failures.append(f"Assistant Settings {name}: screenshot hash is stale")
    if settings.get("passed") is not True:
        failures.append("Assistant Settings presentation contract failed")
    return failures


def validate_payload(payload: dict[str, Any]) -> list[str]:
    """Return every evidence contract failure."""
    failures: list[str] = []
    failures.extend(_first_paint_contract_failures(payload))
    failures.extend(_teardown_contract_failures(payload))
    failures.extend(_metric_tab_contract_failures(payload))
    failures.extend(_assistant_settings_contract_failures(payload))
    screens = payload.get("screens")
    if not isinstance(screens, list):
        return ["screens payload is missing"]
    artifact_directory = Path(str(payload.get("artifact_directory") or ""))
    if not artifact_directory.is_dir():
        failures.append("artifact directory is missing")
    if tuple(screen.get("file") for screen in screens) != EXPECTED_SCREEN_FILES:
        failures.append("required screenshot set is incomplete or out of order")
    try:
        observed_dpr = float(payload.get("observed_screen_device_pixel_ratio", 0.0))
    except (TypeError, ValueError):
        observed_dpr = 0.0
    observed_labels: dict[str, str] = {}
    for screen in screens:
        name = str(screen.get("name") or screen.get("file") or "unknown")
        checks = screen.get("checks")
        if not isinstance(checks, dict):
            failures.append(f"{name}: machine checks are missing")
            continue
        failures.extend(
            f"{name}: {check}" for check, passed in checks.items() if passed is not True
        )
        labels = screen.get("state_labels")
        if isinstance(labels, dict):
            observed_labels.update(
                {str(kind): str(label) for kind, label in labels.items()}
            )
        pixel_size = screen.get("pixel_size")
        logical_size = screen.get("logical_size")
        ratio = screen.get("render_pixel_ratio")
        requested_ratio = screen.get("requested_render_pixel_ratio", 1.0)
        capture_ratio = screen.get("capture_device_pixel_ratio")
        capture_method = screen.get("capture_method")
        if (
            not isinstance(pixel_size, list)
            or not isinstance(logical_size, list)
            or not isinstance(ratio, (float, int))
            or pixel_size
            != [_physical_dimension(int(value), float(ratio)) for value in logical_size]
        ):
            failures.append(f"{name}: rendered pixel size does not match render ratio")
        if (
            not isinstance(capture_ratio, (float, int))
            or abs(float(capture_ratio) - float(ratio or 0.0)) > 0.001
        ):
            failures.append(f"{name}: capture DPR metadata is inconsistent")
        if screen.get("native_display_scaling_observed") is not False:
            failures.append(f"{name}: native display scaling claim must remain false")
        if requested_ratio == 1.0:
            if capture_method != "widget_grab":
                failures.append(
                    f"{name}: real widget capture did not use widget.grab()"
                )
            if abs(float(capture_ratio or 0.0) - observed_dpr) > 0.02:
                failures.append(f"{name}: capture DPR does not match observed Qt DPR")
            if screen.get("render_scale_evidence") != (
                "observed_widget_device_pixel_ratio"
            ):
                failures.append(f"{name}: observed-DPR capture is mislabeled")
        elif (
            capture_method != "synthetic_qpixmap"
            or screen.get("render_scale_evidence") != "synthetic_pixmap_device_ratio"
            or abs(float(capture_ratio or 0.0) - float(requested_ratio or 0.0)) > 0.001
        ):
            failures.append(f"{name}: scaled pixmap evidence is mislabeled")
        render_content = screen.get("render_content")
        if not isinstance(render_content, dict) or not render_content.get("passed"):
            failures.append(f"{name}: rendered UI content is blank or incomplete")
        screenshot_path = artifact_directory / str(screen.get("file") or "")
        if not screenshot_path.is_file():
            failures.append(f"{name}: screenshot file is missing")
        else:
            observed_hash = hashlib.sha256(screenshot_path.read_bytes()).hexdigest()
            if screen.get("image_sha256") != observed_hash:
                failures.append(f"{name}: screenshot hash does not match the file")
    supplemental_records = (
        (
            "standalone first-paint",
            payload.get("first_paint_320_contract", {}).get("standalone", {}),
        ),
        (
            "real dock first-paint",
            payload.get("first_paint_320_contract", {}).get("real_dock", {}),
        ),
        (
            "metric pre-first-epoch",
            payload.get("metric_tab_transition", {}).get("pre_first_epoch", {}),
        ),
        (
            "metric first-data",
            payload.get("metric_tab_transition", {}).get("first_data", {}),
        ),
    )
    for label, record in supplemental_records:
        if not isinstance(record, dict):
            failures.append(f"{label}: screenshot record is missing")
            continue
        screenshot_path = artifact_directory / str(record.get("file") or "")
        if not screenshot_path.is_file():
            failures.append(f"{label}: screenshot file is missing")
            continue
        observed_hash = hashlib.sha256(screenshot_path.read_bytes()).hexdigest()
        if record.get("image_sha256") != observed_hash:
            failures.append(f"{label}: screenshot hash does not match the file")
    for kind, expected_label in EXPECTED_STATE_LABELS.items():
        if observed_labels.get(kind) != expected_label:
            failures.append(f"state label {kind!r} is missing or changed")
    labels = [observed_labels.get(kind, "") for kind in EXPECTED_STATE_LABELS]
    if len(set(labels)) != len(labels):
        failures.append("semantic state labels are not distinct")

    dock = payload.get("main_window_dock_walkthrough")
    if not isinstance(dock, dict):
        failures.append("real MainWindow/QDockWidget walkthrough is missing")
    else:
        if dock.get("assistant_usable_width") != (
            MainWindow.ASSISTANT_DOCK_STANDARD_WIDTH
        ):
            failures.append("real assistant dock does not use the standard width")
        if not dock.get("action_click", {}).get("clicked"):
            failures.append("real response action click was not observed")
        states = dock.get("states", {})
        expected_buttons = {
            "cancellable": ("Stop", True),
            "stopping": ("Stopping", False),
            "application_command": ("Working", False),
        }
        for state_name, (text, enabled) in expected_buttons.items():
            state = states.get(state_name, {})
            if (
                state.get("button_text") != text
                or state.get("button_enabled") is not enabled
            ):
                failures.append(f"real dock {state_name} button state is incorrect")
        if not states.get("stopping", {}).get("real_stop_click_emitted"):
            failures.append("real Stop click did not emit the cancellation request")
        if not states.get("stopping", {}).get("late_activity_latched"):
            failures.append("late stopped-turn activity escaped the Stopping latch")
        action_click = dock.get("action_click", {})
        if action_click.get("history_source") != "live_correlated_response":
            failures.append("real response action did not originate from a live turn")
        if action_click.get("restored_actions_inert") is not True:
            failures.append("restored response actions remained executable")
        if not action_click.get("presentation_identity_from_ui"):
            failures.append("live response identity was not authoritative in the UI")
        if not action_click.get("pre_click_render_content", {}).get("passed"):
            failures.append("live response action was not visibly painted before click")
        if action_click.get("before_panel_index") != 1:
            failures.append("response action did not start from Preprocess")
        if action_click.get("after_panel_index") != 0:
            failures.append("response action did not finish on Dataset")
        if action_click.get("before_panel_materialized") is not True:
            failures.append("Preprocess was not materialized before action capture")
        if action_click.get("after_panel_materialized") is not True:
            failures.append("Dataset was not materialized after action capture")
        if action_click.get("before_placeholder_visible") is not False:
            failures.append("Preprocess placeholder remained visible before action")
        if action_click.get("after_placeholder_visible") is not False:
            failures.append("Dataset placeholder remained visible after action")

    current_source_files = source_file_manifest()
    current_fingerprint = source_fingerprint(current_source_files)
    source_files = payload.get("source_files")
    if not isinstance(source_files, list) or [
        item.get("path") for item in source_files if isinstance(item, dict)
    ] != list(FINGERPRINT_RELATIVE_PATHS):
        failures.append("source fingerprint manifest is incomplete")
    elif source_files != current_source_files:
        failures.append("source manifest is stale for the current source")
    if payload.get("source_fingerprint") != current_fingerprint:
        failures.append("artifact is stale for the current source")
    capture_source = payload.get("capture_source")
    if not isinstance(capture_source, dict):
        failures.append("capture source fingerprint evidence is missing")
    elif (
        capture_source.get("stable") is not True
        or capture_source.get("fingerprint_at_start") != current_fingerprint
        or capture_source.get("fingerprint_at_completion") != current_fingerprint
    ):
        failures.append("source changed during capture or was not observed")
    provenance = payload.get("runtime_import_provenance")
    if not isinstance(provenance, dict):
        failures.append("runtime import provenance evidence is missing")
    elif (
        provenance.get("root_matches_capture") is not True
        or provenance.get("all_sources_under_root") is not True
    ):
        failures.append("runtime modules were imported from a different source root")
    if payload.get("native_display_scaling_observed") is not False:
        failures.append("artifact must not claim native display scaling")
    return failures


def capture_walkthrough(
    app: QApplication,
    output_dir: Path,
    *,
    scenarios: Iterable[ScenarioSpec] = SCENARIOS,
) -> dict[str, Any]:
    """Capture all focused and composed scenarios, then write validated evidence."""
    output_dir.mkdir(parents=True, exist_ok=True)
    source_files_at_start = source_file_manifest()
    fingerprint_at_start = source_fingerprint(source_files_at_start)
    app.setStyle("Fusion")
    standalone_first_paint = _capture_standalone_first_paint(app, output_dir)
    metric_tab_transition = _capture_metric_tab_transition(app, output_dir)
    screens: list[dict[str, Any]] = []
    for spec in scenarios:
        panel = ChatPanel()
        panel.resize(spec.logical_width, spec.logical_height)
        spec.prepare(panel)
        panel.show()
        _settle_layout(app, panel)
        if spec.scroll_to_bottom:
            scrollbar = panel.scroll_area.verticalScrollBar()
            if scrollbar is not None:
                scrollbar.setValue(scrollbar.maximum())
                app.processEvents()
        evidence = _screen_evidence(panel, spec)
        capture = _capture_widget(
            panel,
            output_dir / spec.filename,
            render_pixel_ratio=spec.render_pixel_ratio,
            required_content_widgets=_dpi_content_widgets(panel, spec),
        )
        evidence.update(capture)
        send_contrast = human_evidence.icon_only_control_contrast_evidence(
            panel,
            output_dir / spec.filename,
            panel.send_btn,
        )
        evidence["send_icon_contrast"] = send_contrast
        evidence["checks"]["send_visual_present"] = bool(
            evidence["checks"]["send_visual_present"] and send_contrast["passed"]
        )
        evidence["checks"]["render_content_ready"] = capture["render_content"]["passed"]
        evidence["failures"] = [
            name for name, passed in evidence["checks"].items() if not passed
        ]
        screens.append(evidence)
        panel.close()
        panel.deleteLater()
        app.processEvents()

    (
        dock_walkthrough,
        dock_screens,
        dock_first_paint,
        teardown,
    ) = _capture_main_window_dock_walkthrough(app, output_dir)
    screens.extend(dock_screens)
    assistant_settings = _capture_assistant_settings(app, output_dir)
    source_files_at_completion = source_file_manifest()
    fingerprint_at_completion = source_fingerprint(source_files_at_completion)
    first_paint_contract = {
        "target_width": 320,
        "observation_boundary": (
            "State and geometry sampled inside the first ChatPanel paint event; "
            "the backing store is saved immediately afterward without the settle helper."
        ),
        "standalone": standalone_first_paint,
        "real_dock": dock_first_paint,
        "passed": bool(
            standalone_first_paint.get("passed") and dock_first_paint.get("passed")
        ),
    }
    primary_screen = app.primaryScreen()
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "pending",
        "generated_at": datetime.now(UTC).isoformat(),
        "generator": GENERATOR,
        "artifact_directory": str(output_dir.resolve()),
        "replay_command": (
            'PYTHONPATH="$PWD" QT_QPA_PLATFORM=offscreen poetry run -- python '
            "scripts/dev/capture_chatpanel_ui_ux_walkthrough.py"
        ),
        "platform": QApplication.platformName(),
        "configured_qt_scale_factor": os.environ.get("QT_SCALE_FACTOR", "1"),
        "observed_screen_device_pixel_ratio": float(
            primary_screen.devicePixelRatio() if primary_screen is not None else 1.0
        ),
        "source_files": source_files_at_start,
        "source_fingerprint": fingerprint_at_start,
        "capture_source": {
            "fingerprint_at_start": fingerprint_at_start,
            "fingerprint_at_completion": fingerprint_at_completion,
            "stable": bool(
                fingerprint_at_start
                and fingerprint_at_start == fingerprint_at_completion
            ),
        },
        "runtime_import_provenance": runtime_import_provenance(),
        "render_scale_evidence": (
            "observed_widget_dpr_with_labeled_synthetic_pixmap_probe"
        ),
        "render_readiness": {
            "required_consecutive_content_frames": 2,
            "normalized_png_color_mode": "RGB",
            "real_widget_capture_method": "QWidget.grab",
            "full_frame_content_check": True,
            "main_window_required_regions": [
                "main_shell",
                "assistant_transcript",
                "assistant_primary_action",
                "assistant_activity_when_visible",
            ],
            "restored_action_inert_check": True,
            "live_action_pre_click_region_check": True,
        },
        "native_display_scaling_observed": False,
        "claim_boundary": CLAIM_BOUNDARY,
        "first_paint_320_contract": first_paint_contract,
        "main_window_dock_walkthrough": dock_walkthrough,
        "teardown": teardown,
        "metric_tab_transition": metric_tab_transition,
        "assistant_settings": assistant_settings,
        "screens": screens,
    }
    failures = validate_payload(payload)
    payload["status"] = "passed" if not failures else "failed"
    payload["failures"] = failures
    _write_artifacts(output_dir, payload)
    return payload


def render_readme(payload: dict[str, Any]) -> str:
    """Render reviewer-facing replay instructions and evidence boundaries."""
    lines = [
        "# ChatPanel UI/UX Walkthrough Gate",
        "",
        "This directory is generated from real Qt widgets. It includes focused "
        "ChatPanel states and a composed `MainWindow` / `QDockWidget` walkthrough. "
        "Visual acceptance remains a separate reviewer decision.",
        "",
        "## Replay",
        "",
        "```bash",
        str(payload["replay_command"]),
        "```",
        "",
        f"- machine gate: `{payload['status']}`",
        f"- source fingerprint: `{payload['source_fingerprint']}`",
        f"- source stable during capture: `{payload['capture_source']['stable']}`",
        "- source fingerprint at start / completion: "
        f"`{payload['capture_source']['fingerprint_at_start']}` / "
        f"`{payload['capture_source']['fingerprint_at_completion']}`",
        "- runtime imports under capture root: "
        f"`{payload['runtime_import_provenance']['all_sources_under_root']}`",
        f"- fingerprinted source files: `{len(payload['source_files'])}`",
        f"- Qt platform: `{payload['platform']}`",
        "- visual reviewer verdict: `not adjudicated by this script`",
        "- native display scaling observed: `false`",
        "",
        "## Screens",
        "",
        "| Screenshot | Logical / rendered pixel size | States | Checks |",
        "| --- | --- | --- | --- |",
    ]
    for screen in payload["screens"]:
        kinds = ", ".join(screen["message_kinds"]) or "runtime / activity state"
        checks = "PASS" if not screen["failures"] else ", ".join(screen["failures"])
        lines.append(
            f"| `{screen['file']}` | {screen['logical_size'][0]} x "
            f"{screen['logical_size'][1]} / {screen['pixel_size'][0]} x "
            f"{screen['pixel_size'][1]} | {kinds} | {checks} |"
        )
    lines.extend(
        [
            "",
            "## First Paint",
            "",
            "The standalone ChatPanel and the real MainWindow dock are both sampled "
            "inside their first 320 px ChatPanel paint event, before the layout-settle "
            "helper runs. The assistant activity state must already be visible while "
            "its composer and Send action remain disabled for the idle runtime.",
            "",
            f"- first-paint contract passed: "
            f"`{payload['first_paint_320_contract']['passed']}`",
            f"- standalone frame: "
            f"`{payload['first_paint_320_contract']['standalone']['file']}`",
            f"- real dock frame: "
            f"`{payload['first_paint_320_contract']['real_dock']['file']}`",
            "",
            "## Training Metric Transition",
            "",
            "A real `MetricTab` records the pre-first-epoch empty state, then applies "
            "epoch 1 through `update_plot()` and records the first train/validation "
            "series frame.",
            "",
            f"- transition passed: `{payload['metric_tab_transition']['passed']}`",
            f"- empty frame: "
            f"`{payload['metric_tab_transition']['pre_first_epoch']['file']}`",
            f"- first-data frame: "
            f"`{payload['metric_tab_transition']['first_data']['file']}`",
            "",
            "## Assistant Settings",
            "",
            "The real local-only Settings dialog is captured in collapsed and "
            "advanced states. The gate checks model/runtime status, selected presets, "
            "text-only footer actions, bounded controls, spinbox presentation, and "
            "horizontal-overflow absence without reading or downloading model files.",
            "",
            f"- settings contract passed: `{payload['assistant_settings']['passed']}`",
            f"- collapsed frame: "
            f"`{payload['assistant_settings']['screens'][0]['file']}`",
            f"- advanced frame: "
            f"`{payload['assistant_settings']['screens'][1]['file']}`",
            "",
            "## Teardown",
            "",
            "The composed walkthrough binds a dedicated `AssistantCommandThread`, "
            "requests `AgentManager.close()`, and observes dispatcher cleanup, runtime "
            "cleanup, QThread completion, GUI heartbeat continuity, and close-call "
            "latency through Qt signals and an event loop. It does not call "
            "`QThread.wait()` on the GUI thread.",
            "",
            f"- teardown passed: `{payload['teardown']['passed']}`",
            f"- manager close finished: "
            f"`{payload['teardown']['manager_close_finished']}`",
            f"- dedicated QThread finished: "
            f"`{payload['teardown']['dedicated_qthread']['finished_signal_observed']}`",
            f"- initial close-call latency: "
            f"`{payload['teardown']['initial_close_call_duration_ms']} ms`",
            f"- GUI heartbeat count / max gap: "
            f"`{payload['teardown']['gui_heartbeat']['count_during_cleanup']}` / "
            f"`{payload['teardown']['gui_heartbeat']['max_gap_ms']} ms`",
            "",
            "## Interaction Coverage",
            "",
            "The composed walkthrough uses the real `MainWindow`, `AgentManager`, "
            "`QDockWidget`, and `ChatPanel`. It establishes a 320 px ChatPanel width, "
            "proves a response action restored from serialized history is inert, then "
            "clicks a correlated live-turn action to open Dataset. It then clicks Stop "
            "while the typed state is cancellable, "
            "proves late activity for that turn remains latched at Stopping until the "
            "matching terminal event, and records a new-turn Application command state "
            "where Stop is unavailable.",
            "",
            "## Render Readiness",
            "",
            "Every saved frame must pass the pixel-content gate twice consecutively. "
            "Captured output is normalized to a standard RGB PNG before inspection. "
            "The composed MainWindow frames additionally require painted main-shell, "
            "assistant transcript, and primary-action regions; visible activity cards "
            "are checked separately. Restored actions must remain inert, and the live "
            "action is checked in its own painted region before the real click. Solid "
            "or shell-only captures fail the gate.",
            "",
            "## Render Scaling",
            "",
            "Real widget frames use `QWidget.grab()` and retain the device pixel ratio "
            "observed by Qt in their physical PNG dimensions. The dedicated 320 / "
            "420 / 760 frames include message content, an error, and a confirmation "
            "card. `pixmap-scaled-narrow.png` remains a separately labeled synthetic "
            "pixmap probe via `QPixmap.setDevicePixelRatio(1.5)`. Configured Linux "
            "offscreen scaling does not demonstrate Windows native DPI behavior, "
            "monitor transitions, or operating-system compositor behavior.",
            "",
            "## Claim Boundary",
            "",
            str(payload["claim_boundary"]),
            "",
        ]
    )
    return "\n".join(lines)


def _write_artifacts(output_dir: Path, payload: dict[str, Any]) -> None:
    (output_dir / JSON_ARTIFACT).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / README_ARTIFACT).write_text(
        render_readme(payload),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for PNG, JSON, and README artifacts.",
    )
    args = parser.parse_args()
    app = QApplication.instance() or QApplication(sys.argv)
    if not isinstance(app, QApplication):
        raise RuntimeError("A QApplication is required for ChatPanel capture.")
    payload = capture_walkthrough(app, args.output_dir)
    print(f"ChatPanel UI/UX gate: {payload['status']}")
    for failure in payload["failures"]:
        print(f"- {failure}", file=sys.stderr)
    print(f"Wrote {args.output_dir / JSON_ARTIFACT}")
    print(f"Wrote {args.output_dir / README_ARTIFACT}")
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
