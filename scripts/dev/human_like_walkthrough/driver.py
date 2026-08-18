"""Deterministic AgentManager driver used by assistant walkthrough capture."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, cast
from unittest.mock import patch

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget

from scripts.dev.human_like_walkthrough.contract import (
    ASSISTANT_BLOCKED_REQUEST,
    ASSISTANT_CANCEL_CONFIRMATION_REQUEST,
    ASSISTANT_CLARIFICATION_REQUEST,
    ASSISTANT_CONFIRM_CONFIRMATION_REQUEST,
    ASSISTANT_CONFIRMED_TERMINAL_MESSAGE,
    ASSISTANT_ERROR_REQUEST,
    ASSISTANT_EXISTING_UI_REQUEST,
    ASSISTANT_HANDOFF_REQUEST_ID,
    ASSISTANT_NORMAL_REQUEST,
    ASSISTANT_PROCESSING_REQUEST,
    ASSISTANT_RAW_TRACEBACK,
    ASSISTANT_RECOVERY_REQUEST,
    ASSISTANT_STOPPED_MESSAGE,
    ASSISTANT_SUCCESS_REQUEST,
    ASSISTANT_WORKFLOW_CLARIFICATION_MESSAGE,
)
from XBrainLab.backend.application.commands import CommandName
from XBrainLab.llm.agent.assistant_activity import (
    AssistantDecisionOwner,
    AssistantTurnActivity,
    AssistantTurnActivityPhase,
)
from XBrainLab.llm.agent.confirmation import (
    AgentConfirmationRequest,
    AgentConfirmationResolution,
    AgentConfirmationResolutionStatus,
)
from XBrainLab.llm.agent.controller import (
    AgentInteractionOutcome,
    AgentInteractionStatus,
)
from XBrainLab.llm.agent.response_presentation import (
    AssistantResponseKind,
    AssistantResponsePresentation,
    interaction_outcome_kind,
    interaction_outcome_message,
    user_facing_generation_error,
)
from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
    AssistantRuntimeSnapshot,
)
from XBrainLab.llm.agent.turn import (
    AssistantGenerationEvent,
    AssistantGenerationEventPhase,
    AssistantTurnCorrelation,
    AssistantTurnRequest,
    AssistantTurnTerminal,
)
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolution,
    WorkflowUiHandoffResolutionStatus,
)
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.model_catalog import PRIMARY_LOCAL_MODEL_ID
from XBrainLab.llm.core.runtime_selection import (
    AssistantRuntimeBackend,
    AssistantRuntimeLaunchSpec,
    AssistantRuntimeSelectionOutcome,
    AssistantRuntimeSettingsSnapshot,
)


@dataclass(frozen=True)
class StateBackedAssistantResponse:
    """Assistant copy and claims derived from one backend state query."""

    text: str
    claims: tuple[str, ...]
    command_ok: bool


def build_state_backed_assistant_response(
    command_result: object,
    workflow_state: dict[str, Any],
) -> StateBackedAssistantResponse:
    """Build success copy only from a successful command and observed state."""
    if not bool(getattr(command_result, "ok", False)):
        return StateBackedAssistantResponse(
            text="I could not verify the current workflow state. Try again.",
            claims=(),
            command_ok=False,
        )

    claims: list[str] = []
    phrases: list[str] = []
    training = workflow_state.get("training", {})
    evaluation = workflow_state.get("evaluation", {})
    visualization = workflow_state.get("visualization", {})
    if (
        isinstance(training, dict)
        and int(training.get("finished_run_count", 0) or 0) > 0
    ):
        claims.append("training_complete")
        phrases.append("training has finished")
    if isinstance(evaluation, dict) and bool(evaluation.get("available", False)):
        claims.append("evaluation_available")
        phrases.append("evaluation results are available")
    if isinstance(visualization, dict) and bool(
        visualization.get("available", False)
        or visualization.get("saliency_available", False)
        or visualization.get("montage_available", False)
    ):
        claims.append("visualization_available")
        phrases.append("visualization data are available")

    if not phrases:
        return StateBackedAssistantResponse(
            text=(
                "I verified the current workflow state. No completed analysis result "
                "is available yet."
            ),
            claims=(),
            command_ok=True,
        )
    return StateBackedAssistantResponse(
        text="Verified from the current workflow: " + "; ".join(phrases) + ".",
        claims=tuple(claims),
        command_ok=True,
    )


class WalkthroughAssistantController(QObject):
    """Deterministic controller double using the production Qt signal surface."""

    response_presentation_ready = pyqtSignal(object)
    generation_event = pyqtSignal(object)
    processing_finished = pyqtSignal()
    turn_finished = pyqtSignal(object)
    status_update = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    panel_navigation_requested = pyqtSignal(object)
    workflow_ui_handoff_requested = pyqtSignal(object)
    application_command_completed = pyqtSignal(object)
    application_command_started = pyqtSignal()
    runtime_state_changed = pyqtSignal(object)
    interaction_resolved = pyqtSignal(object)
    confirmation_requested = pyqtSignal(object)
    activity_changed = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self.is_processing = False
        self._active_turn: AssistantTurnCorrelation | None = None
        self._generation_sequence = 0
        self._walkthrough_generation_id: int | None = None
        self._stop_pending = False
        self.events: list[str] = []
        self.confirmed_execution_count = 0
        self.session_generation = 0
        self.last_confirmation_request: AgentConfirmationRequest | None = None
        self.last_workflow_handoff: WorkflowUiHandoffRequest | None = None
        self.last_workflow_resolution: WorkflowUiHandoffResolution | None = None
        self._pending_workflow_handoff: WorkflowUiHandoffRequest | None = None
        self._pending_confirmation_request: AgentConfirmationRequest | None = None
        self._runtime_model_id = "walkthrough-local-model"
        self._active_launch_spec: object | None = None
        self._state_response = StateBackedAssistantResponse(
            text="I could not verify the current workflow state. Try again.",
            claims=(),
            command_ok=False,
        )
        self.responses: dict[str, tuple[str, str]] = {
            ASSISTANT_NORMAL_REQUEST: (
                "I can help interpret EEG data and prepare a training-ready dataset.",
                "ready",
            ),
            ASSISTANT_CLARIFICATION_REQUEST: (
                ASSISTANT_WORKFLOW_CLARIFICATION_MESSAGE,
                "clarification",
            ),
            ASSISTANT_BLOCKED_REQUEST: (
                "Start a new session before importing another dataset into this "
                "completed workflow.",
                "blocked",
            ),
            ASSISTANT_RECOVERY_REQUEST: (
                "I scanned the selected source and prepared the import preview.",
                "success",
            ),
        }

    def _publish_activity(
        self,
        phase: AssistantTurnActivityPhase,
        *,
        command_name: str = "",
        request_id: str = "",
        decision_owner: AssistantDecisionOwner | None = None,
    ) -> None:
        correlation = self._active_turn
        self.activity_changed.emit(
            AssistantTurnActivity(
                phase,
                command_name=command_name,
                request_id=request_id,
                decision_owner=decision_owner,
                turn_id=correlation.turn_id if correlation is not None else None,
                generation=(
                    correlation.generation if correlation is not None else None
                ),
            )
        )

    def _response_presentation(
        self,
        *,
        text: str,
        kind: AssistantResponseKind = AssistantResponseKind.MESSAGE,
    ) -> AssistantResponsePresentation:
        correlation = self._active_turn
        if correlation is None:
            raise RuntimeError("Walkthrough response has no active turn correlation.")
        return AssistantResponsePresentation(
            text=text,
            correlation=correlation,
            kind=kind,
        )

    def _begin_generation(self) -> None:
        self._generation_sequence += 1
        self._walkthrough_generation_id = self._generation_sequence
        self.generation_event.emit(
            AssistantGenerationEvent(
                generation_id=self._generation_sequence,
                phase=AssistantGenerationEventPhase.STARTED,
            )
        )

    def _finish_generation(
        self,
        phase: AssistantGenerationEventPhase = AssistantGenerationEventPhase.FINISHED,
        *,
        text: str = "",
    ) -> None:
        generation_id = self._walkthrough_generation_id
        if generation_id is None:
            return
        self.generation_event.emit(
            AssistantGenerationEvent(
                generation_id=generation_id,
                phase=phase,
                text=text,
            )
        )
        self._walkthrough_generation_id = None

    def initialize(self, _launch_spec: object | None = None) -> None:
        self._active_launch_spec = _launch_spec
        selected_model = str(getattr(_launch_spec, "model_id", "") or "").strip()
        if selected_model:
            self._runtime_model_id = selected_model
        self.events.append("initialize")
        self.publish_runtime("loading")

    def publish_runtime(
        self,
        phase: str,
        error: str = "",
        *,
        activation_id: int | None = None,
    ) -> None:
        self.events.append(f"runtime:{phase}")
        request_activation_id = max(
            0,
            int(getattr(self._active_launch_spec, "activation_id", 0) or 0),
        )
        self.runtime_state_changed.emit(
            AssistantRuntimeSnapshot(
                phase=AssistantRuntimePhase(phase),
                initialized=phase == AssistantRuntimePhase.READY.value,
                backend_mode="local",
                model_id=self._runtime_model_id,
                requested_model_id=str(
                    getattr(self._active_launch_spec, "requested_model_id", "") or ""
                ),
                selection_outcome=getattr(self._active_launch_spec, "outcome", None),
                selection_detail=str(
                    getattr(self._active_launch_spec, "selection_detail", "") or ""
                ),
                error=error,
                activation_id=(
                    request_activation_id
                    if activation_id is None
                    else max(0, int(activation_id))
                ),
            )
        )

    def publish_runtime_failure(self) -> None:
        self.publish_runtime("failed", "Model Load Error: deterministic failure")
        self.error_occurred.emit("Model Load Error: deterministic failure")
        self.events.append("error:runtime_failed")

    def configure_state_response(
        self,
        command_result: object,
        workflow_state: dict[str, Any],
    ) -> StateBackedAssistantResponse:
        """Bind the next state-summary response to current backend evidence."""
        self._state_response = build_state_backed_assistant_response(
            command_result,
            workflow_state,
        )
        return self._state_response

    def handle_user_turn(self, payload: object) -> None:
        """Accept the same correlated turn contract as the product controller."""
        if not isinstance(payload, AssistantTurnRequest):
            raise TypeError("Walkthrough turns require AssistantTurnRequest.")
        if self._active_turn is not None or self.is_processing:
            self.turn_finished.emit(
                AssistantTurnTerminal(
                    correlation=payload.correlation,
                    outcome="rejected_busy",
                )
            )
            return
        self._active_turn = payload.correlation
        self._handle_admitted_user_input(payload.text)

    def handle_user_input(self, _text: str) -> None:
        """Reject the legacy uncorrelated entry point in evidence harnesses."""
        raise RuntimeError(
            "Walkthrough user input requires AssistantTurnRequest via "
            "handle_user_turn()."
        )

    def _handle_admitted_user_input(self, text: str) -> None:
        """Process text only after the product-shaped admission contract succeeds."""
        if self._active_turn is None:
            raise RuntimeError("Walkthrough request has no admitted turn correlation.")
        request = str(text).strip()
        self.events.append(f"request:{request}")
        self.is_processing = True
        self._publish_activity(AssistantTurnActivityPhase.PREPARING)
        self._begin_generation()

        if request == ASSISTANT_PROCESSING_REQUEST:
            self.status_update.emit("Checking data")
            self.events.append("processing:pending")
            return
        if request == ASSISTANT_ERROR_REQUEST:
            self.error_occurred.emit(ASSISTANT_RAW_TRACEBACK)
            self.status_update.emit("Error")
            self._publish_activity(AssistantTurnActivityPhase.NEEDS_ATTENTION)
            self.response_presentation_ready.emit(
                self._response_presentation(
                    text=user_facing_generation_error(ASSISTANT_RAW_TRACEBACK),
                    kind=AssistantResponseKind.ERROR,
                )
            )
            self.events.append("error:traceback")
            self._finish_generation(
                AssistantGenerationEventPhase.ERROR,
                text=ASSISTANT_RAW_TRACEBACK,
            )
            self._finish()
            return
        if request in {
            ASSISTANT_CANCEL_CONFIRMATION_REQUEST,
            ASSISTANT_CONFIRM_CONFIRMATION_REQUEST,
        }:
            self.status_update.emit("Waiting for confirmation: new_session")
            confirmation = AgentConfirmationRequest.for_action(
                command_name=CommandName.NEW_SESSION.value,
                params={},
                action_label="Start new session",
                description="Start a new session and clear the current one.",
                destructive=True,
                publication_generation=1,
            )
            self.last_confirmation_request = confirmation
            self._pending_confirmation_request = confirmation
            self._publish_activity(
                AssistantTurnActivityPhase.WAITING_FOR_DECISION,
                command_name=confirmation.command_name,
                request_id=confirmation.request_id,
                decision_owner=AssistantDecisionOwner.CONFIRMATION_CARD,
            )
            self.confirmation_requested.emit(confirmation)
            self.events.append("interaction:confirmation_requested")
            self._finish_generation()
            return
        if request == ASSISTANT_EXISTING_UI_REQUEST:
            self.status_update.emit("Opening Evaluation")
            handoff = WorkflowUiHandoffRequest.for_decision(
                CommandName.EVALUATE,
                decision_fields=("evaluation_result",),
                request_id=ASSISTANT_HANDOFF_REQUEST_ID,
            )
            self.last_workflow_handoff = handoff
            self._pending_workflow_handoff = handoff
            self._publish_activity(
                AssistantTurnActivityPhase.WAITING_FOR_DECISION,
                command_name=handoff.command_name,
                request_id=handoff.request_id,
                decision_owner=AssistantDecisionOwner.PANEL_HANDOFF,
            )
            self.events.append("handoff:typed_requested:evaluate")
            self.workflow_ui_handoff_requested.emit(handoff)
            self.events.append("handoff:typed_emitted:evaluate")
            self._finish_generation()
            return
        if request == ASSISTANT_SUCCESS_REQUEST:
            outcome = "success" if self._state_response.command_ok else "failed"
            self.status_update.emit("Generating response...")
            self._publish_activity(AssistantTurnActivityPhase.THINKING)
            self.response_presentation_ready.emit(
                self._response_presentation(text=self._state_response.text)
            )
            self.events.append(f"response:{outcome}")
            self._finish()
            return

        message, outcome = self.responses.get(
            request,
            (
                "Tell me which EEG workflow step you want to continue.",
                "clarification",
            ),
        )
        if outcome == "blocked":
            self.status_update.emit("Blocked: user decision required")
            self._publish_activity(AssistantTurnActivityPhase.NEEDS_ATTENTION)
            self.response_presentation_ready.emit(
                self._response_presentation(
                    text=message,
                    kind=AssistantResponseKind.BLOCKED,
                )
            )
        elif outcome == "clarification":
            self.status_update.emit("Waiting for your choice")
            self.response_presentation_ready.emit(
                self._response_presentation(
                    text=message,
                    kind=AssistantResponseKind.CLARIFICATION,
                )
            )
        else:
            self.status_update.emit("Generating response...")
            self._publish_activity(AssistantTurnActivityPhase.THINKING)
            self.response_presentation_ready.emit(
                self._response_presentation(text=message)
            )
        self.events.append(f"response:{outcome}")
        self._finish()

    def stop_generation(self) -> None:
        if not self.is_processing or self._stop_pending:
            return
        self._stop_pending = True
        self.status_update.emit("Stopping...")
        self._publish_activity(AssistantTurnActivityPhase.STOPPING)
        self.events.append("processing:stop")

    def complete_stop(self) -> None:
        """Complete a previously accepted Stop after UI evidence is captured."""
        if not self._stop_pending or not self.is_processing:
            raise RuntimeError("Walkthrough Stop was not pending completion.")
        self.response_presentation_ready.emit(
            self._response_presentation(
                text=ASSISTANT_STOPPED_MESSAGE,
                kind=AssistantResponseKind.CANCELLED,
            )
        )
        self.events.append("response:cancelled")
        self._finish_generation(AssistantGenerationEventPhase.CANCELLED)
        self._finish()

    def _finish(self) -> None:
        self._finish_generation()
        correlation = self._active_turn
        self.is_processing = False
        self.status_update.emit("Ready")
        self._publish_activity(AssistantTurnActivityPhase.IDLE)
        self._active_turn = None
        self._stop_pending = False
        self.processing_finished.emit()
        if correlation is not None:
            self.turn_finished.emit(AssistantTurnTerminal(correlation=correlation))

    def set_model(self, model_request: object) -> None:
        self._active_launch_spec = model_request
        model_id = str(getattr(model_request, "model_id", model_request) or "")
        self.events.append(f"settings:model_selected:{model_id}")
        self._runtime_model_id = model_id
        self.publish_runtime("loading")

    def complete_model_switch(self) -> None:
        """Publish ready only after the settings-driven loading state is recorded."""
        self.publish_runtime("ready")

    def reset_conversation(self) -> None:
        self.events.append("conversation:reset")

    def on_user_confirmation_resolved(self, payload: object) -> None:
        if not isinstance(payload, AgentConfirmationResolution):
            self.events.append("confirmation:rejected:untyped")
            return
        request = self._pending_confirmation_request
        if request is None or not payload.matches(request):
            self.events.append("confirmation:rejected:stale")
            return
        self._pending_confirmation_request = None
        command_name = request.command_name
        self.events.append(f"confirmation:{payload.status.value}")
        if payload.status is AgentConfirmationResolutionStatus.APPROVED:
            self._publish_activity(
                AssistantTurnActivityPhase.RUNNING_COMMAND,
                command_name=command_name,
                request_id=request.request_id,
            )
            self.confirmed_execution_count += 1
            self.session_generation += 1
            self.interaction_resolved.emit(
                AgentInteractionOutcome(
                    status=AgentInteractionStatus.CONFIRMED,
                    command_name=command_name,
                    request_id=request.request_id,
                )
            )
            self.response_presentation_ready.emit(
                self._response_presentation(text=ASSISTANT_CONFIRMED_TERMINAL_MESSAGE)
            )
            self.events.append("response:confirmed:completed")
        else:
            outcome = AgentInteractionOutcome(
                status=AgentInteractionStatus.CANCELLED,
                command_name=command_name,
                request_id=request.request_id,
            )
            self.interaction_resolved.emit(outcome)
            self.response_presentation_ready.emit(
                self._response_presentation(
                    text=interaction_outcome_message(outcome),
                    kind=interaction_outcome_kind(outcome),
                )
            )
            self.events.append("response:cancelled")
        self._finish()

    def on_workflow_ui_handoff_resolved(self, payload: object) -> None:
        """Consume the same correlated typed resolution as the product controller."""
        if not isinstance(payload, WorkflowUiHandoffResolution):
            self.events.append("handoff:resolution_rejected:untyped")
            return
        request = self._pending_workflow_handoff
        if request is None:
            self.events.append("handoff:resolution_rejected:no_pending_request")
            return
        if (
            payload.request_id != request.request_id
            or payload.command is not request.command
            or payload.decision_fields != request.decision_fields
        ):
            self.events.append("handoff:resolution_rejected:mismatched")
            return

        self._pending_workflow_handoff = None
        self.last_workflow_resolution = payload
        interaction_status = {
            WorkflowUiHandoffResolutionStatus.DEFERRED_TO_UI: (
                AgentInteractionStatus.DEFERRED_TO_UI
            ),
            WorkflowUiHandoffResolutionStatus.COMPLETED: (
                AgentInteractionStatus.COMPLETED_IN_UI
            ),
            WorkflowUiHandoffResolutionStatus.CANCELLED: (
                AgentInteractionStatus.CANCELLED
            ),
            WorkflowUiHandoffResolutionStatus.BLOCKED: AgentInteractionStatus.BLOCKED,
            WorkflowUiHandoffResolutionStatus.UNAVAILABLE: (
                AgentInteractionStatus.UNAVAILABLE
            ),
            WorkflowUiHandoffResolutionStatus.FAILED: AgentInteractionStatus.FAILED,
        }[payload.status]
        outcome = AgentInteractionOutcome(
            status=interaction_status,
            command_name=request.command_name,
            request_id=request.request_id,
            decision_fields=request.decision_fields,
            message=payload.message,
        )
        self.interaction_resolved.emit(outcome)
        self.response_presentation_ready.emit(
            self._response_presentation(
                text=interaction_outcome_message(outcome),
                kind=interaction_outcome_kind(outcome),
            )
        )
        self.events.append(
            f"handoff:resolution_accepted:{payload.status.value}:{payload.request_id}"
        )
        self._finish()

    def execute_debug_tool(self, tool_name: str, _params: dict[Any, Any]) -> None:
        self.events.append(f"debug:{tool_name}")

    def close(self) -> bool:
        self.events.append("close")
        return True


def install_walkthrough_assistant(manager: Any) -> WalkthroughAssistantController:
    """Install a deterministic controller through the product runtime owner."""
    controller = WalkthroughAssistantController()
    config = LLMConfig(model_name=PRIMARY_LOCAL_MODEL_ID)
    launch_spec = AssistantRuntimeLaunchSpec(
        backend=AssistantRuntimeBackend.LOCAL,
        requested_backend_id=AssistantRuntimeBackend.LOCAL.value,
        requested_model_id=PRIMARY_LOCAL_MODEL_ID,
        model_id=PRIMARY_LOCAL_MODEL_ID,
        outcome=AssistantRuntimeSelectionOutcome.EXACT,
        selection_detail=f"Selected {PRIMARY_LOCAL_MODEL_ID}.",
        settings=AssistantRuntimeSettingsSnapshot.from_config(config),
    )
    with patch(
        "XBrainLab.ui.components.agent_manager.LLMController",
        return_value=controller,
    ):
        manager.assistant_runtime.start(launch_spec=launch_spec)
    if manager.agent_controller is not controller or not manager.agent_initialized:
        raise RuntimeError("Walkthrough assistant did not start through AgentManager.")
    return controller


def click_assistant_control(control: QWidget) -> None:
    """Click a Qt control through QTest despite incomplete PyQt overload typing."""
    cast(Any, QTest.mouseClick)(control, Qt.MouseButton.LeftButton)


def drive_assistant_request(
    app: QApplication,
    manager: Any,
    text: str,
    *,
    expect_processing: bool = False,
) -> None:
    """Send one request through ChatPanel, AgentManager, and the controller."""
    panel = manager.chat_panel
    if panel is None:
        raise RuntimeError("Assistant panel is unavailable.")
    previous_count = len(manager.chat_controller.messages)
    panel.input_field.setText(text)
    click_assistant_control(cast(QWidget, panel.send_btn))
    app.processEvents()
    if expect_processing:
        if not manager.chat_controller.is_processing or panel.send_btn.text() != "Stop":
            raise RuntimeError("Assistant did not enter the expected processing state.")
        return
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        app.processEvents()
        if (
            len(manager.chat_controller.messages) > previous_count
            and not manager.chat_controller.is_processing
        ):
            return
        time.sleep(0.005)
    raise RuntimeError(f"Assistant request did not finish through Qt signals: {text}")


def append_chat_transcript(
    target: list[dict[str, str]],
    messages: list[dict[str, Any]],
) -> None:
    """Record the transcript produced by ChatController without injecting it."""
    target.extend(
        {
            "role": str(message.get("role") or "assistant"),
            "text": str(message.get("content") or ""),
        }
        for message in messages
    )
