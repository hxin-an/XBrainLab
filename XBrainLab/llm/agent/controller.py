"""Central LLM agent controller.

Orchestrates conversation management, the ReAct reasoning loop, tool
execution, and communication between the UI layer and the backend
worker thread.
"""

import json
import logging
from collections.abc import Callable
from contextlib import suppress
from enum import Enum
from typing import Any, cast

from PyQt6 import sip
from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal, pyqtSlot

from XBrainLab.backend.application import CommandName, get_application_service
from XBrainLab.backend.application.view_publication import (
    InterpretationReviewIdentity,
)
from XBrainLab.llm.action_contracts import (
    AGENT_ACTION_CONTRACTS,
    AgentExecutionKind,
)
from XBrainLab.llm.core.runtime_selection import AssistantRuntimeLaunchSpec
from XBrainLab.llm.tools import AVAILABLE_TOOLS
from XBrainLab.llm.tools.application_surface import (
    APPLICATION_COMMAND_TOOLS,
    ToolAvailability,
    ToolAvailabilityContext,
    ToolCommandResult,
)
from XBrainLab.llm.tools.result_contract import (
    UiRequest,
    UiRequestKind,
    redact_public_text,
    safe_unexpected_failure,
)
from XBrainLab.llm.tools.tool_registry import ToolRegistry
from XBrainLab.product_language import ASSISTANT_CANCELLED_MESSAGE, tool_action_label

from .assembler import ContextAssembler, PromptToolPublication
from .assistant_activity import (
    AssistantAttentionKind,
    AssistantDecisionOwner,
    AssistantTurnActivity,
    AssistantTurnActivityPhase,
)
from .confidence import estimate_confidence
from .confirmation import (
    AgentConfirmationRequest,
    AgentConfirmationResolution,
    AgentConfirmationResolutionStatus,
    AgentConfirmationRisk,
)
from .conversation import ConversationHistory
from .decision_contract import MODEL_RESPONSE_TOOL_NAME
from .interaction import AgentInteractionOutcome, AgentInteractionStatus
from .metrics import AgentMetricsTracker
from .parser import CommandParser, ToolEnvelopeParseResult, ToolEnvelopeStatus
from .pending_interaction import (
    PendingConfirmationDecision,
    PendingInteractionCoordinator,
    PendingWorkflowHandoffDecision,
)
from .rag_lifecycle import RAGLifecycleRetriever, RAGRetrieverLifecycle
from .rag_process_lifecycle import ProcessRAGRetrieverLifecycle
from .response_presentation import (
    AssistantPanelNavigationRequest,
    AssistantPanelTarget,
    AssistantResponseKind,
    AssistantResponsePresentation,
    interaction_outcome_kind,
    interaction_outcome_message,
    panel_target_for_command,
    user_facing_generation_error,
)
from .runtime_state import AssistantRuntimePhase, AssistantRuntimeSnapshot
from .strict_envelope_recovery import (
    DEFAULT_STRICT_ENVELOPE_RECOVERY_POLICY,
    StrictEnvelopeRecoveryAction,
    StrictEnvelopeRecoveryRequest,
)
from .tool_attempt_coordinator import (
    ApplicationToolContextSource,
    ToolAttemptAction,
    ToolAttemptCoordinator,
    ToolAttemptDecision,
    ToolAttemptFeedback,
    ToolAttemptRequest,
)
from .tool_call_normalizer import normalize_tool_call
from .tool_execution_coordinator import (
    ToolExecutionCoordinator,
    ToolExecutionOutcome,
)
from .tool_feedback import format_tool_output, summarize_tool_result
from .turn import (
    AssistantDebugToolRequest,
    AssistantGenerationDispatchAcknowledgement,
    AssistantGenerationDispatchPhase,
    AssistantGenerationEvent,
    AssistantGenerationEventPhase,
    AssistantGenerationStopAcknowledgement,
    AssistantGenerationStopRequest,
    AssistantResponseContract,
    AssistantTurnCorrelation,
    AssistantTurnDeliveryAcknowledgement,
    AssistantTurnDeliveryPhase,
    AssistantTurnRequest,
    AssistantTurnScope,
    AssistantTurnTerminal,
)
from .turn_orchestrator import (
    AssistantToolAttemptSession,
    AssistantTurnOrchestrator,
)
from .ui_handoff import (
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolution,
    WorkflowUiHandoffResolutionStatus,
    WorkflowUiHandoffSurfaceKind,
    workflow_ui_handoff_route_for,
)
from .verifier import VerificationLayer
from .worker import AgentWorker

_DIRECT_ACTION_PANEL_TARGETS = {
    "apply_bandpass_filter": AssistantPanelTarget.PREPROCESS,
    "apply_notch_filter": AssistantPanelTarget.PREPROCESS,
    "resample_data": AssistantPanelTarget.PREPROCESS,
    "set_reference": AssistantPanelTarget.PREPROCESS,
    "normalize_data": AssistantPanelTarget.PREPROCESS,
    "reset_preprocessing": AssistantPanelTarget.PREPROCESS,
    "start_training": AssistantPanelTarget.TRAINING,
    "stop_training": AssistantPanelTarget.TRAINING,
    "clear_training_history": AssistantPanelTarget.TRAINING,
}

logger = logging.getLogger(__name__)


WORKER_GENERATION_SHUTDOWN_WAIT_MS = 2000
WORKER_SHUTDOWN_RETRY_INTERVAL_MS = 100
WORKER_SHUTDOWN_TIMEOUT_MS = 5000
_QT_THREAD_TYPE = QThread

_BLOCKED_TOOL_ERROR_TYPES = frozenset(
    {
        "confirmation_required",
        "input",
        "intent_mismatch",
        "precondition",
        "stale_confirmation",
        "stale_publication",
        "tool_not_published",
    }
)


class _ControllerShutdownPhase(str, Enum):
    OPEN = "open"
    WORKER_STOPPING = "worker_stopping"
    THREAD_STOPPING = "thread_stopping"
    CLOSED = "closed"


class _BestEffortGenerationObservers:
    """Isolate diagnostic callbacks from the worker dispatch contract."""

    def __init__(self) -> None:
        self._callbacks: list[Callable[[object], None]] = []
        self._emitting = False

    def connect(self, callback: Callable[[object], None]) -> None:
        if not callable(callback):
            raise TypeError("Generation diagnostic observer must be callable.")
        self._callbacks.append(callback)

    def disconnect(self, callback: Callable[[object], None] | None = None) -> None:
        if callback is None:
            self._callbacks.clear()
            return
        self._callbacks = [
            registered for registered in self._callbacks if registered != callback
        ]

    def emit(self, payload: object) -> None:
        if self._emitting:
            logger.warning(
                "Ignored reentrant assistant generation diagnostic publication."
            )
            return
        self._emitting = True
        try:
            for callback in tuple(self._callbacks):
                self._notify(callback, payload)
        finally:
            self._emitting = False

    @staticmethod
    def _notify(callback: Callable[[object], None], payload: object) -> None:
        try:
            callback(payload)
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="assistant_controller",
                operation="publish_generation_diagnostic",
            )


class _ExpectedPublicationApplicationRuntime:
    """Immutable tool runtime binding execution to one reviewed publication."""

    def __init__(self, service: Any, generation: int) -> None:
        self._service = service
        self._generation = generation

    def get_view_publication(self) -> Any:
        return self._service.get_view_publication()

    def execute(self, command: Any) -> Any:
        return self._service.execute(
            command,
            expected_publication_generation=self._generation,
        )


class LLMController(QObject):
    """Central controller for the LLM agent.

    Manages conversation history with a sliding window, drives the ReAct
    reasoning loop (parse → verify → execute → feedback), and bridges
    UI signals with the background ``AgentWorker``.

    Attributes:
        study: The application Study object providing experiment state.
        registry: Tool registry holding all registered tools.
        assembler: Context assembler for building system prompts.
        verifier: Verification layer for validating tool calls.
        rag_retriever: RAG retriever for augmenting prompts with examples.
        worker_thread: Background QThread running the AgentWorker.
        worker: AgentWorker performing LLM inference.
        history: List of message dicts representing conversation history.
        current_response: Accumulated text of the current LLM response.
        is_processing: Flag indicating whether a generation is in progress.

    """

    # Signals to UI
    response_presentation_ready = pyqtSignal(object)
    generation_event = pyqtSignal(object)
    processing_finished = pyqtSignal()  # ROBUST: New signal for UI to stop spinner
    turn_finished = pyqtSignal(object)
    status_update = pyqtSignal(str)  # status message
    error_occurred = pyqtSignal(str)  # error message
    panel_navigation_requested = pyqtSignal(object)
    application_command_completed = pyqtSignal(object)
    application_command_started = pyqtSignal()
    runtime_state_changed = pyqtSignal(object)
    interaction_resolved = pyqtSignal(object)
    confirmation_requested = pyqtSignal(object)
    workflow_ui_handoff_requested = pyqtSignal(object)
    activity_changed = pyqtSignal(object)
    shutdown_finished = pyqtSignal(bool, str)

    # Internal signals to Worker
    sig_initialize = pyqtSignal(object)
    sig_generate: _BestEffortGenerationObservers
    _sig_dispatch_generation = pyqtSignal(object)
    sig_reinit = pyqtSignal(object)
    sig_cancel_generation = pyqtSignal(object)
    sig_shutdown_worker = pyqtSignal()
    sig_rag_context_ready = pyqtSignal(int, str, str, str)

    MAX_HISTORY = 20

    def __init__(
        self,
        study,
        *,
        rag_lifecycle: (
            RAGRetrieverLifecycle | ProcessRAGRetrieverLifecycle | None
        ) = None,
    ) -> None:
        """Initializes the LLMController.

        Sets up the tool registry, context assembler, verification layer,
        RAG retriever, and background worker thread.

        Args:
            study: The application Study object providing experiment context.
            rag_lifecycle: Optional lifecycle owner injected by tests or hosts.

        """
        super().__init__()
        self.sig_generate = _BestEffortGenerationObservers()
        self.study = study
        self._turn_orchestrator = AssistantTurnOrchestrator()
        self._tool_attempt_session = AssistantToolAttemptSession()

        # Initialize Tool Registry & Assembler
        self.registry = ToolRegistry()
        for tool in AVAILABLE_TOOLS:
            self.registry.register(tool)

        self.assembler = ContextAssembler(self.registry, self.study)
        self.verifier = VerificationLayer(
            tool_schemas={
                tool.name: tool.parameters for tool in self.registry.get_all_tools()
            },
        )

        # The lifecycle is the sole owner of retriever work and cleanup.
        self._rag_lifecycle = (
            rag_lifecycle
            if rag_lifecycle is not None
            else ProcessRAGRetrieverLifecycle()
        )

        # Setup Worker in separate thread to avoid blocking UI during load/inference
        self.worker_thread = QThread()
        worker = AgentWorker()
        self.worker: AgentWorker | None = worker
        worker.moveToThread(self.worker_thread)
        self.worker_thread.finished.connect(worker.deleteLater)
        self.worker_thread.finished.connect(self._on_worker_thread_finished)

        self._conversation = ConversationHistory(max_size=self.MAX_HISTORY)

        # Connect worker signals
        worker.generation_chunk_received.connect(self._on_chunk_received)
        worker.generation_finished.connect(self._on_generation_finished)
        worker.generation_error.connect(self._on_generation_error)
        worker.generation_dispatch_acknowledged.connect(
            self._on_generation_dispatch_acknowledged
        )
        worker.error.connect(self._on_runtime_error)
        worker.log.connect(self.status_update)

        # Connect control signals
        self.sig_initialize.connect(worker.initialize_agent)
        self._sig_dispatch_generation.connect(worker.generate_from_messages)
        self.sig_reinit.connect(worker.reinitialize_agent)  # M3.4
        self.sig_cancel_generation.connect(worker.cancel_generation)
        # Worker affinity is the dedicated thread, so AutoConnection queues cleanup.
        self.sig_shutdown_worker.connect(worker.shutdown)
        worker.generation_stop_finished.connect(
            self._on_generation_stop_finished,
        )
        worker.runtime_snapshot_changed.connect(self._on_runtime_snapshot_changed)
        worker.shutdown_finished.connect(self._on_worker_shutdown_finished)
        self.sig_rag_context_ready.connect(self._on_rag_context_ready)

        # Start thread
        self.worker_thread.start()

        self.current_response = ""
        self._worker_runtime_snapshot = AssistantRuntimeSnapshot(
            phase=AssistantRuntimePhase.IDLE,
            initialized=False,
        )
        self.is_processing = False
        self._active_response_contract = AssistantResponseContract.STRUCTURED_ACTION

        # Metrics tracker
        self.metrics = AgentMetricsTracker()

        # Robustness State
        self._strict_envelope_recovery_policy = DEFAULT_STRICT_ENVELOPE_RECOVERY_POLICY

        # Tool Failure Loop Protection
        self._max_tool_failures = 3
        self._max_loop_breaks = 3

        # The model proposes commands; this deterministic policy boundary owns
        # publication, provenance, schema, capability, and confirmation.
        self._tool_attempt_coordinator = ToolAttemptCoordinator(
            registry=self.registry,
            verifier=self.verifier,
            context_source=ApplicationToolContextSource(self.study),
        )
        self._tool_execution_coordinator = ToolExecutionCoordinator(
            self,
            block_policy=self._tool_attempt_coordinator,
        )
        self._initialize_shutdown_lifecycle()

        self._max_tool_executions = 5

        self._pending_interactions = PendingInteractionCoordinator()

    def _initialize_shutdown_lifecycle(self) -> None:
        """Initialize the controller-owned, signal-driven shutdown state."""
        self._closing = False
        self._closed = False
        self._shutdown_phase = _ControllerShutdownPhase.OPEN
        self._shutdown_preamble_complete = False
        self._rag_shutdown_attempted = False
        self._rag_shutdown_clean = True
        self._shutdown_timeout_timer = QTimer(self)
        self._shutdown_timeout_timer.setSingleShot(True)
        self._shutdown_timeout_timer.timeout.connect(self._on_shutdown_timeout)
        self._shutdown_retry_timer = QTimer(self)
        self._shutdown_retry_timer.setSingleShot(True)
        self._shutdown_retry_timer.timeout.connect(self._request_worker_shutdown)

    @property
    def accepts_commands(self) -> bool:
        """Return whether this controller may accept new product commands."""
        return not self._closing and not self._closed

    @property
    def shutdown_in_progress(self) -> bool:
        """Return whether asynchronous worker ownership is still being released."""
        return self._closing and not self._closed

    @property
    def rag_retriever(self) -> RAGLifecycleRetriever:
        """Expose the lifecycle-owned retriever for diagnostics and compatibility."""
        retriever = self._rag_lifecycle.retriever
        if retriever is None:
            raise RuntimeError("Production RAG is owned by an isolated process.")
        return retriever

    @property
    def pending_interactions(self) -> PendingInteractionCoordinator:
        """Return the typed owner of pending confirmation and UI handoff state."""
        return self._pending_interactions

    def _publish_activity(
        self,
        phase: AssistantTurnActivityPhase,
        *,
        command_name: str = "",
        request_id: str = "",
        message: str = "",
        attention_kind: AssistantAttentionKind = AssistantAttentionKind.ATTENTION,
        decision_owner: AssistantDecisionOwner | None = None,
    ) -> None:
        """Publish transient assistant activity without duplicating workflow truth."""
        self.activity_changed.emit(
            AssistantTurnActivity(
                phase=phase,
                command_name=command_name,
                request_id=request_id,
                message=message,
                turn_id=self._turn_orchestrator.host_turn_id,
                generation=self._turn_orchestrator.host_turn_generation,
                attention_kind=attention_kind,
                decision_owner=decision_owner,
            )
        )

    def _publish_response(
        self,
        text: str,
        *,
        kind: AssistantResponseKind = AssistantResponseKind.MESSAGE,
        marks_current_turn: bool = True,
    ) -> None:
        """Publish one opaque, typed response to the product transcript.

        Model text is classified before this boundary. Once copy reaches this
        method the UI must render it verbatim instead of reclassifying prefixes
        such as ``Request:`` or JSON-looking prose.
        """
        presentation = AssistantResponsePresentation(
            text=text,
            correlation=self._require_active_turn_correlation(),
            kind=kind,
        )
        self.response_presentation_ready.emit(presentation)
        if marks_current_turn:
            self._tool_attempt_session.mark_response_visible()

    def _active_policy_mode(self) -> str:
        """Return immutable autonomy for the active turn."""
        active_scope = self._turn_orchestrator.scope
        if active_scope is not None:
            return active_scope.policy_mode
        return AssistantTurnScope.SINGLE_ACTION.policy_mode

    @staticmethod
    def _workflow_handoff_decision_owner(
        command_name: CommandName | str,
    ) -> AssistantDecisionOwner | None:
        """Identify the existing product surface that owns one UI handoff."""
        route = workflow_ui_handoff_route_for(command_name)
        return route.decision_owner if route is not None else None

    def initialize(self, launch_spec: AssistantRuntimeLaunchSpec):
        """Initializes the underlying worker engine and RAG retriever.

        Emits the initialization signal to the worker thread and starts
        RAG initialization through the owned lifecycle helper.
        """
        if self._reject_command_while_closing("initialize"):
            return
        if not isinstance(launch_spec, AssistantRuntimeLaunchSpec):
            raise TypeError("Assistant initialization requires a runtime launch spec.")
        self.sig_initialize.emit(launch_spec)

        self._rag_lifecycle.start()

    @property
    def history(self):
        """list: Backward-compatible accessor for conversation messages."""
        return self._conversation.messages

    @history.setter
    def history(self, value):
        self._conversation.messages = value

    def _append_history(self, role: str, content: str):
        """Appends a message to history and prunes to the sliding window.

        Args:
            role: Message role (``'user'``, ``'assistant'``, or ``'system'``).
            content: The message text.

        """
        self._conversation.append(role, content)

    @pyqtSlot(object)
    def handle_user_turn(
        self,
        payload: object,
    ) -> AssistantTurnDeliveryAcknowledgement:
        """Start one host-correlated request without replacing an active turn."""
        if not isinstance(payload, AssistantTurnRequest):
            raise TypeError("Assistant user turn must use AssistantTurnRequest.")
        try:
            if not self.accepts_commands:
                logger.warning(
                    "Rejected turn %s because controller shutdown has started",
                    redact_public_text(payload.turn_id),
                )
                self.turn_finished.emit(
                    AssistantTurnTerminal(
                        correlation=payload.correlation,
                        outcome="rejected_closing",
                    )
                )
                return AssistantTurnDeliveryAcknowledgement(
                    correlation=payload.correlation,
                    phase=AssistantTurnDeliveryPhase.REJECTED,
                    message="Assistant controller is closing.",
                )
            if (
                self._turn_orchestrator.has_active_host_turn
                or self.is_processing
                or self.pending_interactions.has_pending
            ):
                logger.warning(
                    "Rejected turn %s because controller turn %s is still active",
                    redact_public_text(payload.turn_id),
                    self._turn_orchestrator.host_turn_id,
                )
                self.turn_finished.emit(
                    AssistantTurnTerminal(
                        correlation=payload.correlation,
                        outcome="rejected_busy",
                    )
                )
                return AssistantTurnDeliveryAcknowledgement(
                    correlation=payload.correlation,
                    phase=AssistantTurnDeliveryPhase.REJECTED,
                    message="Assistant controller is busy.",
                )
            self._turn_orchestrator.bind_host_turn(payload)
            self.assembler.bind_turn_scope(payload.scope)
            self._handle_admitted_user_input(payload.text)
        except Exception as exc:
            failure = safe_unexpected_failure(
                logger,
                exc,
                boundary="assistant_turn_controller",
                operation="deliver_host_turn",
            )
            self._finish_turn_delivery_error(payload)
            return AssistantTurnDeliveryAcknowledgement(
                correlation=payload.correlation,
                phase=AssistantTurnDeliveryPhase.ERROR,
                message=failure.message,
            )
        return AssistantTurnDeliveryAcknowledgement(
            correlation=payload.correlation,
            phase=AssistantTurnDeliveryPhase.ACCEPTED,
        )

    def _finish_turn_delivery_error(
        self,
        request: AssistantTurnRequest | AssistantDebugToolRequest,
    ) -> None:
        """Release controller state before reporting a host setup failure."""
        if self._active_turn_correlation() != request.correlation:
            return
        self._rollback_failed_turn_setup()
        self._emit_processing_finished("delivery_error")

    def _rollback_failed_turn_setup(self) -> None:
        """Unwind every mutable side effect of a partially started turn.

        Host delivery and admitted-input setup share this boundary so a fault at
        any point cannot leave metrics, pending interaction, RAG, authorization,
        or generation state that rejects the next correlated request.
        """
        cleanup_steps = (
            ("metrics", self.metrics.finish_turn),
            ("pending interactions", self.pending_interactions.clear),
            ("RAG context", self.assembler.clear_context),
            ("recovery feedback", self.assembler.clear_recovery_feedback),
            ("turn authorization", self.assembler.clear_turn_authorization),
        )
        for label, cleanup in cleanup_steps:
            self._run_turn_setup_cleanup(label, cleanup)

        self._invalidate_pending_rag_turn()
        self.is_processing = False
        self.current_response = ""
        self._active_response_contract = AssistantResponseContract.STRUCTURED_ACTION
        self._turn_orchestrator.reset_failed_setup()
        self._tool_attempt_session.reset_for_user_turn()

    @staticmethod
    def _run_turn_setup_cleanup(
        label: str,
        cleanup: Callable[[], object],
    ) -> None:
        """Run one rollback action without skipping later cleanup actions."""
        try:
            cleanup()
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="assistant_controller",
                operation=f"turn_setup_rollback_{label}",
            )

    def _emit_processing_finished(self, outcome: str = "completed") -> None:
        """Publish UI completion and a correlated host terminal exactly once."""
        correlation = self._turn_orchestrator.finish_host_turn()
        self.processing_finished.emit()
        if correlation is not None:
            self.turn_finished.emit(
                AssistantTurnTerminal(correlation=correlation, outcome=outcome)
            )

    def _active_turn_correlation(self) -> AssistantTurnCorrelation | None:
        return self._turn_orchestrator.correlation

    def _require_active_turn_correlation(self) -> AssistantTurnCorrelation:
        correlation = self._active_turn_correlation()
        if correlation is None:
            raise RuntimeError("Assistant response has no active turn correlation.")
        return correlation

    def handle_user_input(self, text: str):
        """Reject input that bypasses the host's typed turn admission."""
        del text
        logger.error(
            "Rejected assistant input without an AssistantTurnRequest correlation."
        )

    def _handle_admitted_user_input(self, text: str) -> None:
        """Start input previously admitted through ``handle_user_turn``.

        Appends the user message to history, schedules RAG retrieval through
        the owned lifecycle, and returns without waiting for embeddings.  LLM
        generation starts only when the current-turn RAG result is delivered
        back to this controller through the Qt queued signal.

        Args:
            text: The user's input text.

        """
        if self._reject_command_while_closing("handle user input"):
            return
        if not text.strip():
            return
        self._require_active_turn_correlation()

        # RACE CONDITION FIX: Prevent re-entry if already generating or loading
        if self.is_processing or self.pending_interactions.has_pending:
            logger.warning("User input ignored - Agent is busy.")
            self._publish_response(
                "The assistant is still processing the previous request. "
                "Stop it or wait for the current response before sending again.",
                kind=AssistantResponseKind.BLOCKED,
                marks_current_turn=False,
            )
            return

        self.is_processing = True
        self.status_update.emit("Thinking...")
        self._publish_activity(AssistantTurnActivityPhase.PREPARING)

        # Start metrics for this turn
        turn = self.metrics.start_turn()
        turn.input_chars += len(text)

        try:
            # 1. Update History
            self._append_history("user", text)

            self._reset_user_turn_state()
            turn_id = self._begin_rag_turn()
            self.assembler.clear_context()

            # 2. Retrieve RAG Context (Examples) off the GUI thread.
            if not self._rag_lifecycle.retrieve(
                turn_id,
                text,
                self._publish_rag_context_ready,
                allowed_tool_names=self.assembler.rag_allowed_tool_names(text),
            ):
                self._on_rag_context_ready(turn_id, text, "", "")
        except Exception as exc:
            failure = safe_unexpected_failure(
                logger,
                exc,
                boundary="assistant_turn_controller",
                operation="handle_user_input",
            )
            self._rollback_failed_turn_setup()
            self.error_occurred.emit(failure.message)
            self._publish_response(
                "The assistant could not start this request. Try again or "
                "rephrase the workflow step.",
                kind=AssistantResponseKind.ERROR,
            )
            self._publish_activity(
                AssistantTurnActivityPhase.NEEDS_ATTENTION,
                message=failure.message,
                attention_kind=AssistantAttentionKind.ERROR,
            )
            self._emit_processing_finished("failed_to_start")

    def _reset_user_turn_state(self) -> None:
        """Reset counters that are scoped to one user-authored turn."""
        self._tool_attempt_session.reset_for_user_turn()
        self._turn_orchestrator.reset_for_user_turn()
        self.pending_interactions.clear_workflow_handoff()
        self.assembler.clear_recovery_feedback()
        self.assembler.clear_turn_authorization()

    def _workflow_ui_handoff_request(
        self,
        command_name: CommandName | str,
        *,
        tool_name: str = "",
        decision_fields: Any = (),
        suggested_values: Any = None,
        publication: Any | None = None,
    ) -> WorkflowUiHandoffRequest:
        """Build one handoff, binding import review to published domain identity."""
        command = (
            command_name
            if isinstance(command_name, CommandName)
            else CommandName(str(command_name).strip().lower())
        )
        identity = None
        if command is CommandName.APPLY_INTERPRETATION:
            current_publication = publication
            if current_publication is None:
                try:
                    current_publication = get_application_service(
                        self.study
                    ).get_view_publication()
                except Exception as exc:
                    safe_unexpected_failure(
                        logger,
                        exc,
                        boundary="assistant_controller",
                        operation="bind_data_import_review_identity",
                    )
            interpretation = getattr(
                getattr(current_publication, "state", None),
                "interpretation",
                None,
            )
            generation = getattr(current_publication, "generation", None)
            scan_id = getattr(interpretation, "latest_scan_id", None)
            candidate_id = getattr(interpretation, "latest_candidate_id", None)
            if (
                type(generation) is int
                and generation >= 0
                and isinstance(scan_id, str)
                and scan_id.strip()
                and isinstance(candidate_id, str)
                and candidate_id.strip()
                and bool(getattr(current_publication, "usable", False))
            ):
                identity = InterpretationReviewIdentity(
                    publication_generation=generation,
                    scan_id=scan_id,
                    candidate_id=candidate_id,
                )
        route = workflow_ui_handoff_route_for(command)
        if (
            route is not None
            and route.surface_kind is WorkflowUiHandoffSurfaceKind.ACTION
        ):
            return WorkflowUiHandoffRequest.for_action(
                command,
                tool_name=tool_name,
            )
        return WorkflowUiHandoffRequest.for_decision(
            command,
            tool_name=tool_name,
            decision_fields=decision_fields,
            suggested_values=suggested_values,
            interpretation_identity=identity,
        )

    def _begin_rag_turn(self) -> int:
        """Open a new RAG turn token before asynchronous retrieval starts."""
        return self._turn_orchestrator.begin_rag_turn()

    def _invalidate_pending_rag_turn(self) -> None:
        """Invalidate any queued RAG result for stop/reset/close boundaries."""
        active_turn_id = self._turn_orchestrator.active_rag_turn_id
        if active_turn_id is not None:
            cancel = getattr(self._rag_lifecycle, "cancel_retrieval", None)
            if callable(cancel):
                cancel(active_turn_id)
        self._turn_orchestrator.invalidate_rag_turn()

    def _publish_rag_context_ready(
        self,
        turn_id: int,
        text: str,
        features: str,
        error: str,
    ) -> None:
        """Publish background RAG completion to the controller owner thread."""
        self.sig_rag_context_ready.emit(turn_id, text, features, error)

    def _on_rag_context_ready(
        self,
        turn_id: int,
        text: str,
        features: str,
        error: str,
    ) -> None:
        """Start generation only for the still-current user turn."""
        if (
            turn_id != self._turn_orchestrator.active_rag_turn_id
            or not self._turn_orchestrator.waiting_for_rag
            or not self.is_processing
            or self._turn_orchestrator.cancelled
            or self._closing
            or self._closed
        ):
            return

        if not self._turn_orchestrator.accept_rag_result(turn_id):
            return
        if error:
            logger.warning(
                "Optional RAG retrieval failed; continuing without RAG context: %s",
                redact_public_text(error),
            )
            features = ""

        try:
            if features:
                self.assembler.add_context(features)
            self._generate_response()
        except Exception as continuation_error:
            self._finish_generation_request_failure(continuation_error)

    def _generate_response(self) -> bool:
        """Triggers LLM generation based on the current history.

        Builds the full message list via the assembler, resets the
        response accumulator, and emits signals to the worker thread.
        """
        if not self._turn_orchestrator.begin_generation_dispatch():
            logger.warning(
                "Ignored reentrant assistant generation dispatch for the active turn."
            )
            return False
        try:
            request = self.assembler.get_generation_request(self.history)
            request = request.correlated(self._turn_orchestrator.begin_generation())
            messages = request.to_model_messages()
            self._active_response_contract = request.response_contract
            publication = getattr(
                self.assembler,
                "latest_tool_publication",
                None,
            )
            self._turn_orchestrator.set_active_publication(
                publication
                if isinstance(publication, PromptToolPublication)
                else PromptToolPublication.empty()
            )
            self.current_response = ""
            # Hold the complete generation until it is classified as user text or
            # a tool proposal. This prevents prose-prefixed or cross-chunk JSON from
            # appearing briefly in the product transcript.
            self._tool_attempt_session.begin_generation()

            if self.metrics.current_turn:
                self.metrics.current_turn.llm_calls += 1
                self.metrics.current_turn.input_chars += sum(
                    len(message.get("content", "")) for message in messages
                )

            self.status_update.emit("Generating response...")
            self._publish_activity(AssistantTurnActivityPhase.THINKING)
            self._sig_dispatch_generation.emit(request)
            self.sig_generate.emit(request)
        except Exception as error:
            self._finish_generation_request_failure(error)
            return False
        finally:
            self._turn_orchestrator.finish_generation_dispatch()
        return True

    def _on_generation_dispatch_acknowledged(self, payload: object) -> None:
        """Commit ordered worker acceptance/start evidence for the active ID."""
        if not isinstance(payload, AssistantGenerationDispatchAcknowledgement):
            logger.error(
                "Ignored untyped assistant generation dispatch acknowledgement."
            )
            return
        if payload.generation_id != self._turn_orchestrator.active_generation_id:
            return
        if self._turn_orchestrator.cancelled:
            return
        if self._closing or self._closed:
            return
        if not self._turn_orchestrator.acknowledge_generation_dispatch(
            payload.generation_id,
            payload.phase,
        ):
            if payload.phase is AssistantGenerationDispatchPhase.STARTED:
                logger.error(
                    "Ignored assistant generation start without acceptance for %s.",
                    redact_public_text(payload.generation_id),
                )
            return
        if payload.phase is AssistantGenerationDispatchPhase.ACCEPTED:
            return
        if payload.phase is not AssistantGenerationDispatchPhase.STARTED:
            return
        self.generation_event.emit(
            AssistantGenerationEvent(
                generation_id=payload.generation_id,
                phase=AssistantGenerationEventPhase.STARTED,
            )
        )

    def _finish_generation_request_failure(self, error: Exception) -> None:
        """Terminate a turn when pre-generation continuation cannot dispatch."""
        failure = safe_unexpected_failure(
            logger,
            error,
            boundary="assistant_turn_controller",
            operation="dispatch_generation_continuation",
        )
        message = failure.message
        self._invalidate_pending_rag_turn()
        generation_id = self._turn_orchestrator.active_generation_id
        if generation_id is not None:
            self._arbitrate_generation_terminal(
                generation_id,
                AssistantGenerationEventPhase.ERROR,
                text=message,
            )
        self._finish_worker_error(
            message,
            outcome="generation_request_failed",
        )

    def _on_chunk_received(
        self,
        generation_id: int,
        chunk: str,
    ):
        """Accumulate a worker chunk until the response is classified.

        The full generation is buffered until completion so a model cannot leak
        a late or prose-prefixed tool JSON object into the product transcript.

        Args:
            chunk: A text fragment received from the LLM generation stream.

        """
        if generation_id != self._turn_orchestrator.active_generation_id:
            return
        if (
            not self.is_processing
            or self._turn_orchestrator.cancelled
            or self._closing
            or self._closed
        ):
            return
        if chunk == "":
            return

        self.generation_event.emit(
            AssistantGenerationEvent(
                generation_id=generation_id,
                phase=AssistantGenerationEventPhase.CHUNK,
                text=chunk,
            )
        )
        self.current_response += chunk

        # Track output chars
        if self.metrics.current_turn:
            self.metrics.current_turn.output_chars += len(chunk)

    def _on_generation_finished(
        self,
        generation_id: int,
        _messages: list[Any],
    ):
        """Handles completion of one LLM generation turn.

        Parses the accumulated response for tool commands, retries on
        broken JSON, or finalizes the turn if no commands are found.
        """
        if not self._arbitrate_generation_terminal(
            generation_id,
            AssistantGenerationEventPhase.FINISHED,
        ):
            return
        if not self.is_processing:
            return

        response_text = self.current_response.strip()

        if not response_text:
            self._handle_empty_response()
            return

        if (
            getattr(
                self,
                "_active_response_contract",
                AssistantResponseContract.STRUCTURED_ACTION,
            )
            is AssistantResponseContract.NATURAL_LANGUAGE
        ):
            self._tool_attempt_session.clear_format_retries()
            self._finalize_turn(response_text)
            return

        envelope = CommandParser.parse_product(response_text)
        if (
            envelope.status is not ToolEnvelopeStatus.FORMAT_ERROR
            and envelope.workflow_stage
            != self._turn_orchestrator.active_publication.workflow_stage
        ):
            envelope = ToolEnvelopeParseResult.format_error(
                "workflow_stage does not match the current backend publication."
            )

        # Invalid tool-shaped output is never treated as user-facing prose and
        # never reaches verification or execution.
        if self._handle_tool_envelope_failure(response_text, envelope):
            return

        if envelope.status is ToolEnvelopeStatus.VALID:
            self._tool_attempt_session.clear_format_retries()
            self._process_tool_calls(list(envelope.commands), response_text)
        else:
            self._finalize_turn(envelope.message or response_text)

    def _handle_empty_response(self):
        """Finish a turn with a visible fallback when the model returns nothing."""
        message = (
            "Assistant returned an empty response. The local model may still be "
            "loading, may have failed to generate text, or may have been stopped "
            "before producing output. Try again, or open settings to inspect the "
            "local runtime status."
        )
        logger.warning(redact_public_text(message))
        self.metrics.finish_turn()
        self.error_occurred.emit(message)
        self._publish_response(
            message,
            kind=AssistantResponseKind.ERROR,
        )
        self.status_update.emit("Empty response")
        self._publish_activity(
            AssistantTurnActivityPhase.NEEDS_ATTENTION,
            message=message,
            attention_kind=AssistantAttentionKind.ERROR,
        )
        self.is_processing = False
        self._emit_processing_finished("empty_response")

    def _handle_tool_envelope_failure(
        self,
        response_text: str,
        envelope: ToolEnvelopeParseResult,
    ) -> bool:
        """Retry a model response that violates the product tool envelope.

        Only a ``FORMAT_ERROR`` result enters this path. A normal user-facing
        answer remains ``NO_TOOL`` and a valid envelope proceeds to policy
        verification. The malformed response is never executed or shown.

        Args:
            response_text: The full accumulated LLM response.
            envelope: Typed strict-parser classification for the response.

        Returns:
            ``True`` if a retry was triggered (caller should return early),
            ``False`` otherwise.

        """
        decision = self._strict_envelope_recovery_policy.decide(
            StrictEnvelopeRecoveryRequest(
                envelope=envelope,
                recovery_attempts_used=self._tool_attempt_session.retry_count,
            )
        )
        if decision.action not in {
            StrictEnvelopeRecoveryAction.RETRY_FORMAT,
            StrictEnvelopeRecoveryAction.EXHAUSTED,
        }:
            return False

        if decision.action is StrictEnvelopeRecoveryAction.RETRY_FORMAT:
            logger.warning(
                "Rejected model tool envelope: %s",
                redact_public_text(envelope.error),
            )
            self._tool_attempt_session.record_format_retry(
                decision.recovery_attempts_after
            )
            if decision.message is None:
                raise RuntimeError("Format retry decision is missing recovery context")
            self.assembler.add_context(decision.message.content)
            self.status_update.emit("Invalid assistant action, retrying...")
            self._generate_response()
            return True

        logger.error("Max retries reached for JSON error.")
        message = (
            "The assistant could not produce a valid assistant action. Try again "
            "or describe one workflow step more specifically."
        )
        self._publish_response(message, kind=AssistantResponseKind.ERROR)
        self.metrics.finish_turn()
        self.status_update.emit("Invalid assistant action")
        self._publish_activity(
            AssistantTurnActivityPhase.NEEDS_ATTENTION,
            message=message,
            attention_kind=AssistantAttentionKind.ERROR,
        )
        self.is_processing = False
        self._emit_processing_finished("invalid_action")
        return True

    def _process_tool_calls(self, command_result: Any, response_text: str):
        """Verify and execute at most one model-proposed command."""
        command = self._select_tool_proposal(command_result)
        if command is None:
            self._finalize_turn_after_tool()
            return

        if self._reject_excluded_turn_command(command[0]):
            return
        decision = self._evaluate_tool_proposal(command, response_text)
        if self._present_tool_attempt_boundary(decision):
            return
        self._execute_tool_attempt(decision)

    def _select_tool_proposal(
        self,
        command_result: Any,
    ) -> tuple[str, dict[str, Any]] | None:
        """Normalize one model response and enforce the per-turn host limit."""
        parsed_commands = (
            command_result if isinstance(command_result, list) else [command_result]
        )
        latest_user_text = self._latest_user_request_text()
        normalized_commands = [
            normalize_tool_call(
                cmd,
                params,
                latest_user_text=latest_user_text,
                published_tool_names=(
                    self._turn_orchestrator.active_publication.tool_names
                ),
            )
            for cmd, params in parsed_commands
        ]
        selection = self._tool_attempt_coordinator.select_proposal(
            normalized_commands,
            mode=self._active_policy_mode(),
            execution_count=self._tool_attempt_session.execution_count,
            workflow_tool_cap=self._max_tool_executions,
            cancelled=self._turn_orchestrator.cancelled,
        )
        command = selection.command
        if command is None:
            if selection.reason != "no_command":
                logger.info(
                    "Host policy rejected tool proposal: %s",
                    redact_public_text(selection.reason),
                )
            return None
        if selection.discarded_count:
            logger.warning(
                "Discarded %d additional tool proposal(s); host policy allows "
                "one command per model response.",
                selection.discarded_count,
            )
        return cast(tuple[str, dict[str, Any]], command)

    def _evaluate_tool_proposal(
        self,
        command: tuple[str, dict[str, Any]],
        response_text: str,
    ) -> ToolAttemptDecision:
        """Evaluate one normalized proposal against one backend publication."""
        self._append_history("assistant", response_text)
        confidence = estimate_confidence(response_text, [command])
        logger.debug("Heuristic confidence: %.2f", confidence)

        cmd, params = command
        repeated = self._tool_attempt_session.record_tool_proposal(cmd, params)
        latest_user_text = self._latest_user_request_text()
        publication = self._turn_orchestrator.active_publication
        return self._tool_attempt_coordinator.evaluate(
            ToolAttemptRequest(
                command_name=cmd,
                params=params,
                confidence=confidence,
                publication=publication,
                latest_user_text=latest_user_text,
                repeated=repeated,
            )
        )

    def _present_tool_attempt_boundary(self, decision: ToolAttemptDecision) -> bool:
        """Present loop, block, validation, or confirmation boundaries."""
        cmd = decision.command_name
        if decision.action is ToolAttemptAction.LOOP:
            self._handle_loop_detected(cmd)
            return True
        if decision.action is ToolAttemptAction.RESPOND:
            self._finalize_turn(
                decision.message or "Please provide the required values."
            )
            return True
        if decision.action in {
            ToolAttemptAction.PUBLICATION_BLOCKED,
            ToolAttemptAction.PROVENANCE_BLOCKED,
            ToolAttemptAction.INTENT_BLOCKED,
            ToolAttemptAction.VERIFICATION_BLOCKED,
            ToolAttemptAction.CAPABILITY_BLOCKED,
            ToolAttemptAction.RESOURCE_CONFIRMATION_BLOCKED,
        }:
            result = cast(ToolCommandResult, decision.result)
            self._handle_tool_attempt_blocked(
                cmd,
                result,
                feedback=decision.feedback,
            )
            return True
        if decision.action is ToolAttemptAction.CONFIRMATION_REQUIRED:
            self._request_tool_confirmation(decision)
            return True
        return False

    def _request_tool_confirmation(
        self,
        decision: ToolAttemptDecision,
        context: ToolAvailabilityContext | None = None,
    ) -> None:
        """Pause one proposal at its backend or tool confirmation boundary."""
        cmd = decision.command_name
        request = self._build_confirmation_request(decision, context)
        self.pending_interactions.begin_confirmation(decision, request)
        self.status_update.emit(f"Waiting for confirmation: {cmd}")
        self._publish_activity(
            AssistantTurnActivityPhase.WAITING_FOR_DECISION,
            command_name=cmd,
            request_id=request.request_id,
            decision_owner=AssistantDecisionOwner.CONFIRMATION_CARD,
        )
        self.confirmation_requested.emit(request)

    def _build_confirmation_request(
        self,
        decision: ToolAttemptDecision,
        context: ToolAvailabilityContext | None = None,
    ) -> AgentConfirmationRequest:
        """Build the typed request paired with one confirmation decision."""
        cmd = decision.command_name
        # Keep the prompt-time generation on the request. Resolution re-reads a
        # fresh context and ApplicationService performs the final locked check.
        tool_context = context
        if tool_context is None and isinstance(
            decision.context,
            ToolAvailabilityContext,
        ):
            tool_context = decision.context
        label = tool_action_label(cmd)
        availability = tool_context.availability if tool_context is not None else None
        high_impact = decision.confirmation_kind == "setting_change"
        risk = AgentConfirmationRisk.from_policy(
            command_name=cmd,
            destructive=bool(availability and availability.destructive),
            high_impact=high_impact,
            long_running=bool(availability and availability.long_running),
            decision_boundary=(
                availability.decision_boundary if availability is not None else None
            ),
        )
        return AgentConfirmationRequest.for_action(
            command_name=cmd,
            params=decision.params,
            action_label=label,
            description=decision.message
            or (decision.tool.description if decision.tool else label),
            destructive=risk.destructive,
            publication_generation=(tool_context.generation if tool_context else None),
            confirmation_kind=decision.confirmation_kind,
            risk=risk,
        )

    def _execute_tool_attempt(
        self,
        decision: ToolAttemptDecision,
        *,
        after_confirmation: bool = False,
        request_id: str = "",
        execution_params: dict[str, Any] | None = None,
        execution_context: ToolAvailabilityContext | None = None,
        expected_publication_generation: int | None = None,
    ) -> None:
        """Execute a verified decision and apply its continuation policy."""
        cmd = decision.command_name
        if self._reject_excluded_turn_command(cmd):
            return
        params = decision.params if execution_params is None else execution_params
        tool_context = execution_context or cast(
            ToolAvailabilityContext,
            decision.context,
        )
        autonomy = (
            tool_context.availability if tool_context.availability.enabled else None
        )
        status_prefix = "Executing confirmed" if after_confirmation else "Executing"
        self.status_update.emit(f"{status_prefix}: {cmd}...")
        self._publish_activity(
            AssistantTurnActivityPhase.RUNNING_COMMAND,
            command_name=cmd,
            request_id=request_id,
        )
        companion_target = _DIRECT_ACTION_PANEL_TARGETS.get(cmd)
        if companion_target is not None:
            self.panel_navigation_requested.emit(
                AssistantPanelNavigationRequest(target=companion_target)
            )
        self._tool_attempt_session.begin_execution()
        if expected_publication_generation is None:
            outcome = self._execute_tool_no_loop(
                cmd,
                params,
                context=tool_context,
            )
        else:
            outcome = self._execute_tool_no_loop(
                cmd,
                params,
                context=tool_context,
                expected_publication_generation=expected_publication_generation,
            )
        presented = self._present_tool_execution_outcome(decision, outcome)
        if presented is None:
            return
        success, result, requested_ui = presented
        if requested_ui:
            is_panel_navigation = (
                isinstance(result, UiRequest)
                and result.kind is UiRequestKind.SWITCH_PANEL
            )
            if (
                not is_panel_navigation
                and self.pending_interactions.workflow_handoff is None
            ):
                self._finalize_turn_after_tool("failed")
            return
        if after_confirmation:
            if not success:
                self._tool_attempt_session.record_failure()
                self._finalize_turn_after_tool(
                    self._terminal_outcome_for_result(False, result)
                )
                return
            self._handle_tool_success(
                autonomy,
                command_name=cmd,
                after_confirmation=True,
            )
            return
        if not success:
            self._handle_tool_failure(autonomy, result)
            return
        self._handle_tool_success(autonomy, command_name=cmd)

    def _present_tool_execution_outcome(
        self,
        decision: ToolAttemptDecision,
        outcome: ToolExecutionOutcome,
    ) -> tuple[bool, ToolCommandResult | UiRequest, bool] | None:
        """Publish one result or pause it at the resource confirmation boundary."""
        cmd = decision.command_name
        success, result = outcome.success, outcome.result
        self._tool_attempt_session.record_summary(
            self._summarize_tool_result(cmd, success, result),
            self._tool_result_response_kind(success, result),
        )
        resource_boundary = self._tool_attempt_coordinator.resource_confirmation(
            decision,
            result,
        )
        if resource_boundary is not None:
            if resource_boundary.action is ToolAttemptAction.CONFIRMATION_REQUIRED:
                context = cast(ToolAvailabilityContext, resource_boundary.context)
                self._request_tool_confirmation(resource_boundary, context)
                self._append_history(
                    "user",
                    f"Tool Output: {self._format_tool_output(cmd, success, result)}",
                )
            else:
                blocked_result = cast(ToolCommandResult, resource_boundary.result)
                self._handle_tool_attempt_blocked(
                    cmd,
                    blocked_result,
                    feedback=resource_boundary.feedback,
                )
            return None
        requested_ui = self._handle_tool_result_logic(result, success)
        self._append_history(
            "user",
            f"Tool Output: {self._format_tool_output(cmd, success, result)}",
        )
        return success, result, requested_ui

    def _handle_tool_attempt_blocked(
        self,
        command_name: str,
        result: ToolCommandResult,
        *,
        feedback: ToolAttemptFeedback = ToolAttemptFeedback.SYSTEM_REJECTION,
    ) -> None:
        """Present one typed blocked or failed attempt and finish the turn."""
        user_message = self._summarize_tool_result(command_name, False, result)
        response_kind = self._tool_result_response_kind(False, result)
        blocked = response_kind is AssistantResponseKind.BLOCKED
        logger.warning(
            "Tool attempt %s: %s",
            "blocked" if blocked else "failed",
            redact_public_text(result.message),
        )
        self.status_update.emit(f"{'Blocked' if blocked else 'Error'}: {user_message}")
        self._publish_activity(
            AssistantTurnActivityPhase.NEEDS_ATTENTION,
            command_name=command_name,
            message=user_message,
            attention_kind=(
                AssistantAttentionKind.ATTENTION
                if blocked
                else AssistantAttentionKind.ERROR
            ),
        )
        self._publish_response(
            user_message,
            kind=response_kind,
        )
        history_message = (
            f"Tool Output: {self._format_tool_output(command_name, False, result)}"
            if feedback is ToolAttemptFeedback.TOOL_OUTPUT
            else f"System: Tool call REJECTED: {result.message}"
        )
        self._append_history("user", history_message)
        self._tool_attempt_session.record_summary(
            user_message,
            response_kind,
        )
        self._finalize_turn_after_tool("blocked" if blocked else "failed")

    @staticmethod
    def _panel_target_for_command(
        command_name: str,
    ) -> AssistantPanelTarget | None:
        """Map a blocked backend/tool action to one existing product surface."""
        return panel_target_for_command(command_name)

    @staticmethod
    def _tool_result_response_kind(
        success: bool,
        result: ToolCommandResult | UiRequest,
    ) -> AssistantResponseKind:
        """Distinguish a completed command from a still-pending UI request."""
        if not success:
            if (
                isinstance(result, ToolCommandResult)
                and result.error_type in _BLOCKED_TOOL_ERROR_TYPES
            ):
                return AssistantResponseKind.BLOCKED
            return AssistantResponseKind.ERROR
        if isinstance(result, ToolCommandResult):
            return AssistantResponseKind.TOOL_RESULT
        return AssistantResponseKind.MESSAGE

    def _handle_tool_failure(
        self,
        autonomy: ToolAvailability | None,
        result: ToolCommandResult | UiRequest,
    ) -> None:
        """Finish after one executed command failure without model continuation."""
        del autonomy
        self._tool_attempt_session.record_failure()
        self.assembler.clear_recovery_feedback()
        self._finalize_turn_after_tool(self._terminal_outcome_for_result(False, result))

    def _handle_tool_success(
        self,
        autonomy: ToolAvailability | None,
        *,
        command_name: str,
        after_confirmation: bool = False,
    ) -> None:
        """Finish after one trusted tool result; each user turn owns one action."""
        del autonomy, after_confirmation
        self.assembler.clear_recovery_feedback()
        self._tool_attempt_session.record_success()
        logger.info(
            "Assistant completed one action for this turn: %s",
            redact_public_text(command_name),
        )
        self._finalize_turn_after_tool()

    def _reject_excluded_turn_command(self, command_name: str) -> bool:
        """Fail closed before any command excluded by the user can run."""
        mapped_command = AGENT_ACTION_CONTRACTS.tool_to_command().get(command_name)
        if mapped_command is None:
            try:
                mapped_command = CommandName(command_name)
            except ValueError:
                return False
        excluded_commands = self._turn_orchestrator.excluded_commands
        if mapped_command not in excluded_commands:
            return False

        action_label = tool_action_label(command_name)
        message = (
            f"{action_label} was not run because your request explicitly excluded "
            "that workflow stage."
        )
        logger.warning(
            "Turn policy blocked excluded command: %s",
            redact_public_text(mapped_command.value),
        )
        self.status_update.emit(f"Blocked: {message}")
        self._publish_activity(
            AssistantTurnActivityPhase.NEEDS_ATTENTION,
            command_name=command_name,
            message=message,
        )
        self._publish_response(
            message,
            kind=AssistantResponseKind.BLOCKED,
        )
        self._append_history(
            "user",
            f"System: Action excluded by the user: {mapped_command.value}",
        )
        self._tool_attempt_session.record_summary(
            message,
            AssistantResponseKind.BLOCKED,
        )
        self._finalize_turn_after_tool("blocked")
        return True

    def _finalize_turn_after_tool(self, outcome: str = "completed"):
        """Finalizes the turn after tool execution.

        Stops generation and signals the UI that the agent is ready for
        new input.  Resets the successful-tool counter.
        """
        if self.pending_interactions.workflow_handoff is not None:
            logger.error("Refused to finalize while a workflow UI handoff is pending")
            self.status_update.emit("Waiting for XBrainLab settings to finish.")
            return
        terminal = self._tool_attempt_session.arbitrate_terminal_response(
            "Tool execution finished, but no assistant message was produced."
        )
        if terminal.text is not None:
            self._publish_response(
                terminal.text,
                kind=terminal.kind,
                marks_current_turn=False,
            )
        self._tool_attempt_session.commit_terminal_response(terminal)
        self.metrics.finish_turn()
        self.status_update.emit("Ready")
        self._publish_activity(AssistantTurnActivityPhase.IDLE)
        self.is_processing = False
        self._emit_processing_finished(outcome)

    def _terminal_outcome_for_result(
        self,
        success: bool,
        result: ToolCommandResult | UiRequest,
    ) -> str:
        """Map one trusted tool result to the diagnostic terminal contract."""
        if success:
            return "completed"
        if (
            self._tool_result_response_kind(False, result)
            is AssistantResponseKind.BLOCKED
        ):
            return "blocked"
        return "failed"

    @staticmethod
    def _terminal_outcome_for_interaction(outcome: AgentInteractionOutcome) -> str:
        """Project typed UI outcomes onto the walkthrough terminal vocabulary."""
        if outcome.status in {
            AgentInteractionStatus.CONFIRMED,
            AgentInteractionStatus.DEFERRED_TO_UI,
            AgentInteractionStatus.COMPLETED_IN_UI,
        }:
            return "completed"
        return outcome.status.value

    def on_user_confirmation_resolved(self, payload: object) -> None:
        """Resolve exactly one still-current assistant action confirmation."""
        if self._reject_command_while_closing("confirm action"):
            return
        resolution = self.pending_interactions.resolve_confirmation(payload)
        if resolution.decision is PendingConfirmationDecision.INVALID:
            logger.error(
                "Ignored untyped assistant confirmation: %s",
                redact_public_text(payload),
            )
            return
        typed_payload = resolution.resolution
        if typed_payload is None:
            logger.error("Confirmation coordinator returned no typed resolution")
            return
        if resolution.decision is PendingConfirmationDecision.NO_PENDING:
            logger.warning("Ignored confirmation resolution with no pending action")
            return
        if resolution.decision is PendingConfirmationDecision.DUPLICATE:
            logger.warning(
                "Ignored duplicate assistant confirmation for %s (%s)",
                typed_payload.command_name,
                typed_payload.request_id,
            )
            return
        if resolution.decision is PendingConfirmationDecision.STALE:
            logger.warning(
                "Ignored stale assistant confirmation for %s (%s)",
                typed_payload.command_name,
                typed_payload.request_id,
            )
            return
        pending_pair = resolution.pending
        interaction_outcome = resolution.outcome
        if pending_pair is None or interaction_outcome is None:
            logger.error("Confirmation session consumed no pending value")
            return
        pending = pending_pair.decision
        request = pending_pair.request
        cmd = pending.command_name

        if resolution.decision is PendingConfirmationDecision.CANCEL:
            logger.info("User cancelled assistant action: %s", cmd)
            self._turn_orchestrator.request_cancellation()
            self._tool_attempt_session.clear_summary()
            self._append_history(
                "user",
                f"System: User rejected '{cmd}'. Action was NOT executed.",
            )
            self.status_update.emit("Action cancelled by user.")
            self.interaction_resolved.emit(interaction_outcome)
            self._publish_response(
                interaction_outcome_message(interaction_outcome),
                kind=interaction_outcome_kind(interaction_outcome),
            )
            self._finalize_turn_after_tool("cancelled")
            return

        current_context = self._tool_attempt_coordinator.context_for(cmd)
        if current_context.generation != request.publication_generation:
            message = (
                "Workflow state changed while this confirmation was open. "
                "Review the action again before continuing."
            )
            self.interaction_resolved.emit(
                AgentInteractionOutcome(
                    status=AgentInteractionStatus.BLOCKED,
                    command_name=cmd,
                    request_id=request.request_id,
                    message=message,
                )
            )
            self._handle_tool_attempt_blocked(
                cmd,
                ToolCommandResult.failure(
                    cmd,
                    message,
                    error_type="stale_confirmation",
                    recoverable=True,
                    diagnostics={
                        "confirmed_generation": request.publication_generation,
                        "current_generation": current_context.generation,
                    },
                ),
            )
            return

        logger.info("User confirmed assistant action: %s", cmd)
        self.interaction_resolved.emit(interaction_outcome)
        try:
            confirmed_params = self._tool_attempt_coordinator.approved_params(pending)
        except ValueError as exc:
            self._handle_tool_attempt_blocked(
                cmd,
                ToolCommandResult.failure(
                    cmd,
                    redact_public_text(exc),
                    error_type="contract",
                    recoverable=False,
                ),
                feedback=ToolAttemptFeedback.TOOL_OUTPUT,
            )
            return
        self._execute_tool_attempt(
            pending,
            after_confirmation=True,
            request_id=request.request_id,
            execution_params=confirmed_params,
            execution_context=current_context,
            expected_publication_generation=request.publication_generation,
        )

    def on_workflow_ui_handoff_resolved(self, payload: object) -> None:
        """Consume one correlated result from an existing product UI surface."""
        if self._reject_command_while_closing("resolve product UI handoff"):
            return
        if not isinstance(payload, WorkflowUiHandoffResolution):
            logger.error(
                "Ignored untyped workflow UI handoff resolution: %s",
                redact_public_text(payload),
            )
        resolution = self.pending_interactions.resolve_workflow_handoff(payload)
        typed_payload = resolution.resolution
        if resolution.decision is PendingWorkflowHandoffDecision.INVALID:
            logger.warning("Ignored invalid workflow UI handoff transition")
            return
        if resolution.decision is PendingWorkflowHandoffDecision.NO_PENDING:
            logger.warning("Ignored workflow UI resolution with no pending request")
            return
        if typed_payload is None:
            logger.error("Workflow handoff coordinator returned no typed resolution")
            return
        if resolution.decision is PendingWorkflowHandoffDecision.DUPLICATE:
            logger.warning(
                "Ignored duplicate workflow UI resolution for %s (%s)",
                typed_payload.command_name,
                typed_payload.request_id,
            )
            return
        if resolution.decision is PendingWorkflowHandoffDecision.STALE:
            logger.warning(
                "Ignored stale workflow UI resolution for %s (%s)",
                typed_payload.command_name,
                typed_payload.request_id,
            )
            return
        request = resolution.request
        outcome = resolution.outcome
        if request is None or outcome is None:
            logger.error("Workflow handoff resolution retained no interaction value")
            return
        if resolution.decision is PendingWorkflowHandoffDecision.PROGRESS:
            self._record_ui_handoff_outcome(outcome, progress=True)
            self.interaction_resolved.emit(outcome)
            self._publish_activity(
                AssistantTurnActivityPhase.RUNNING_COMMAND,
                command_name=request.tool_name,
                request_id=request.request_id,
                message=typed_payload.message,
            )
            return
        self._record_ui_handoff_outcome(outcome, progress=False)
        self.interaction_resolved.emit(outcome)
        self._publish_response(
            interaction_outcome_message(outcome),
            kind=interaction_outcome_kind(outcome),
        )
        self._finalize_turn_after_tool(self._terminal_outcome_for_interaction(outcome))

    def _record_ui_handoff_outcome(
        self,
        outcome: AgentInteractionOutcome,
        *,
        progress: bool,
    ) -> None:
        """Record presentation state for one coordinator-owned UI outcome."""
        command_name = outcome.command_name
        status = outcome.status
        if progress:
            self._append_history(
                "user",
                (
                    f"System: '{command_name}' is still pending in the existing "
                    "XBrainLab settings. Do not treat navigation or command "
                    "scheduling as completion."
                ),
            )
            self.status_update.emit("XBrainLab settings command is running.")
            return

        if status is AgentInteractionStatus.DEFERRED_TO_UI:
            self._append_history(
                "user",
                (
                    f"System: The '{command_name}' product panel is open for "
                    "manual continuation. The requested workflow action was not "
                    "verified as completed."
                ),
            )
            self._tool_attempt_session.clear_summary()
            self.status_update.emit("Product panel open for manual completion.")
            return

        if status is AgentInteractionStatus.COMPLETED_IN_UI:
            self._append_history(
                "user",
                f"System: The user completed '{command_name}' in XBrainLab.",
            )
            self._tool_attempt_session.record_summary(
                "The requested settings were completed in XBrainLab. Read current "
                "workflow state before proposing another action.",
                AssistantResponseKind.MESSAGE,
            )
            self.status_update.emit("Existing settings completed.")
            return

        if status is AgentInteractionStatus.CANCELLED:
            self._turn_orchestrator.request_cancellation()
            self._tool_attempt_session.clear_summary()
            self._append_history(
                "user",
                (
                    f"System: The user cancelled '{command_name}' in XBrainLab. "
                    "No workflow action was executed."
                ),
            )
            self.status_update.emit("Existing settings cancelled.")
            return

        outcome_label = {
            AgentInteractionStatus.BLOCKED: "blocked by workflow state",
            AgentInteractionStatus.UNAVAILABLE: "unavailable",
            AgentInteractionStatus.FAILED: "unable to open",
        }[status]
        self._append_history(
            "user",
            f"System: XBrainLab settings for '{command_name}' were {outcome_label}.",
        )
        self._tool_attempt_session.record_summary(
            f"The existing settings surface was {outcome_label}. No workflow "
            "action was executed.",
            AssistantResponseKind.MESSAGE,
        )
        self.status_update.emit(
            {
                AgentInteractionStatus.BLOCKED: "Existing settings blocked.",
                AgentInteractionStatus.UNAVAILABLE: ("Existing settings unavailable."),
                AgentInteractionStatus.FAILED: (
                    "Existing settings could not be opened."
                ),
            }[status]
        )

    def _handle_loop_detected(self, cmd: str):
        """Handles detection of a repeated tool-call loop.

        Injects a system message into history informing the LLM of the
        loop and re-triggers generation to break the cycle.

        Args:
            cmd: The tool name that was called repeatedly.

        """
        if self._tool_attempt_session.record_loop_break(limit=self._max_loop_breaks):
            msg = (
                f"System: Persistent loop detected for '{cmd}'. "
                "Aborting to prevent infinite recursion."
            )
            self._append_history("user", msg)
            visible_message = (
                "The assistant stopped because it repeated the same action "
                "without making progress. Check the current workflow before "
                "trying a narrower request."
            )
            self._append_history("assistant", visible_message)
            self._publish_response(
                visible_message,
                kind=AssistantResponseKind.BLOCKED,
            )
            self.metrics.finish_turn()
            self.status_update.emit("Loop detected, aborting.")
            self._publish_activity(
                AssistantTurnActivityPhase.NEEDS_ATTENTION,
                command_name=cmd,
            )
            self.is_processing = False
            self._emit_processing_finished("loop_detected")
            return

        msg = (
            f"System: Loop detected. You have called '{cmd}' "
            "with these params multiple times. Stop."
        )
        self._append_history("user", msg)
        self.status_update.emit("Loop detected, interrupting...")
        self._generate_response()

    def _finalize_turn(self, response_text: str):
        """Finalizes the turn when no tool commands are present.

        Appends the assistant response to history and emits the
        ``processing_finished`` signal.

        Args:
            response_text: The assistant's final response text.

        """
        self._append_history("assistant", response_text)
        self._publish_response(response_text)
        self.metrics.finish_turn()
        self.status_update.emit("Ready")
        self._publish_activity(AssistantTurnActivityPhase.IDLE)
        self.is_processing = False
        self._emit_processing_finished()

    def _execute_tool_no_loop(
        self,
        command_name,
        params,
        *,
        context: ToolAvailabilityContext | None = None,
        expected_publication_generation: int | None = None,
    ) -> ToolExecutionOutcome:
        """Executes a single tool call without triggering generation.

        Performs an ApplicationService capability-policy check before
        execution to reject tool calls that are not allowed in the
        current backend state.

        Args:
            command_name: Name of the tool to execute.
            params: Dictionary of parameters to pass to the tool.

        Returns:
            A typed outcome containing success and the structured tool result.

        """
        tool_context = context or self._tool_attempt_coordinator.context_for(
            command_name
        )
        application_runtime = None
        bound_generation = expected_publication_generation
        generation_required = (
            command_name in APPLICATION_COMMAND_TOOLS
            and tool_context.availability.enabled
        )
        if bound_generation is None and generation_required:
            bound_generation = tool_context.generation
        if generation_required and bound_generation is None:
            tool_context = self._tool_attempt_coordinator.unavailable_context(
                command_name,
                "Backend publication generation is unavailable; execution is "
                "blocked until workflow state can be verified.",
            )
        elif bound_generation is not None:
            service = get_application_service(self.study)
            application_runtime = _ExpectedPublicationApplicationRuntime(
                service,
                bound_generation,
            )
        return self._tool_execution_coordinator.execute(
            command_name,
            params,
            context=tool_context,
            application_runtime=application_runtime,
        )

    def _latest_user_request_text(self) -> str:
        """Return the most recent human request, excluding tool/system feedback."""
        for message in reversed(self.history):
            if message.get("role") != "user":
                continue
            content = str(message.get("content", "")).strip()
            if not content:
                continue
            if content.startswith(("System:", "Tool Output:")):
                continue
            return content
        return ""

    def _handle_tool_result_logic(
        self,
        result: ToolCommandResult | UiRequest,
        success: bool = True,
    ) -> bool:
        """Process a typed tool result and emit requested GUI interactions.

        Args:
            result: The normalized tool result or UI request.
            success: Whether the tool execution was successful.

        Returns:
            ``True`` if the result triggered a UI interaction signal,
            ``False`` otherwise.

        """
        if isinstance(result, UiRequest):
            if result.kind is UiRequestKind.WORKFLOW_HANDOFF:
                tool_name = result.params.get("tool_name")
                command_name = result.params.get("command")
                decision_fields = result.params.get("decision_fields")
                public_tool_name = tool_name if type(tool_name) is str else ""
                contract = (
                    AGENT_ACTION_CONTRACTS.contract_for(public_tool_name)
                    if public_tool_name
                    else None
                )
                try:
                    command = CommandName(command_name)
                except (TypeError, ValueError):
                    command = None
                valid = bool(
                    contract is not None
                    and contract.execution_kind is AgentExecutionKind.UI_REQUEST
                    and contract.action is command
                    and type(decision_fields) is tuple
                    and decision_fields == contract.ui_decision_fields
                    and command is not None
                    and workflow_ui_handoff_route_for(command) is not None
                )
                if not valid:
                    self._publish_response(
                        "That XBrainLab settings surface is not available.",
                        kind=AssistantResponseKind.BLOCKED,
                    )
                    return False
                workflow_request = self._workflow_ui_handoff_request(
                    command,
                    tool_name=public_tool_name,
                    decision_fields=decision_fields,
                )
                self.pending_interactions.begin_workflow_handoff(workflow_request)
                route = (
                    workflow_ui_handoff_route_for(command)
                    if command is not None
                    else None
                )
                is_action = bool(
                    route is not None
                    and route.surface_kind is WorkflowUiHandoffSurfaceKind.ACTION
                )
                self._publish_activity(
                    (
                        AssistantTurnActivityPhase.RUNNING_COMMAND
                        if is_action
                        else AssistantTurnActivityPhase.WAITING_FOR_DECISION
                    ),
                    command_name=workflow_request.tool_name,
                    request_id=workflow_request.request_id,
                    decision_owner=(
                        None
                        if is_action
                        else self._workflow_handoff_decision_owner(command)
                    ),
                )
                self.workflow_ui_handoff_requested.emit(workflow_request)
                return True
            if result.kind is UiRequestKind.SWITCH_PANEL:
                try:
                    navigation_request = AssistantPanelNavigationRequest(
                        target=AssistantPanelTarget(
                            str(result.params.get("panel", "")).strip().lower()
                        ),
                        view_mode=result.params.get("view_mode"),
                        correlation=self._require_active_turn_correlation(),
                    )
                except (TypeError, ValueError):
                    self._publish_response(
                        "That XBrainLab view is not available. Choose Dataset, "
                        "Preprocess, Training, Evaluation, or Visualization.",
                        kind=AssistantResponseKind.BLOCKED,
                    )
                    return False
                self.panel_navigation_requested.emit(navigation_request)
                return True
            if result.kind is UiRequestKind.CONFIRM_MONTAGE:
                self.status_update.emit("Waiting for user to confirm montage...")
                workflow_request = WorkflowUiHandoffRequest.for_decision(
                    CommandName.APPLY_MONTAGE,
                    decision_fields=("channel_mapping",),
                    suggested_values={
                        "montage_name": result.params.get("montage_name"),
                        "warning": result.params.get("warning"),
                    },
                )
                self.pending_interactions.begin_workflow_handoff(workflow_request)
                self._publish_activity(
                    AssistantTurnActivityPhase.WAITING_FOR_DECISION,
                    command_name=workflow_request.command_name,
                    request_id=workflow_request.request_id,
                    decision_owner=self._workflow_handoff_decision_owner(
                        workflow_request.command
                    ),
                )
                self.workflow_ui_handoff_requested.emit(workflow_request)
                return True
            return False

        # Tool failures remain internal recovery evidence until the host retry
        # policy decides that the turn is terminal. Publishing here would show
        # a failure bubble before a corrected retry succeeds.
        return False

    @staticmethod
    def _summarize_tool_result(
        command_name: str,
        success: bool,
        result: ToolCommandResult | UiRequest,
    ) -> str:
        """Compatibility wrapper around the assistant feedback policy."""
        return summarize_tool_result(command_name, success, result)

    @staticmethod
    def _format_tool_output(
        command_name: str,
        success: bool,
        result: ToolCommandResult | UiRequest,
    ) -> str:
        """Compatibility wrapper around compact local-model feedback."""
        return format_tool_output(command_name, success, result)

    def _on_runtime_error(self, error_msg: object) -> None:
        """Handle model/runtime errors only when no generation owns work."""
        if self._turn_orchestrator.active_generation_id is not None:
            return
        self._finish_worker_error(str(error_msg or "Assistant runtime failed."))

    def _on_generation_error(
        self,
        generation_id: int,
        error_msg: str,
    ) -> None:
        """Handle a correlated generation error and reject stale terminals."""
        message = str(error_msg or "Assistant generation failed.")
        if not self._arbitrate_generation_terminal(
            generation_id,
            AssistantGenerationEventPhase.ERROR,
            text=message,
        ):
            return
        self._finish_worker_error(message)

    def _arbitrate_generation_terminal(
        self,
        generation_id: int,
        phase: AssistantGenerationEventPhase,
        *,
        text: str = "",
    ) -> bool:
        """Commit one correlated terminal with cancellation taking priority.

        A finish or error queued after a stop request does not consume the active
        generation. The stop acknowledgement can then commit ``CANCELLED`` and
        clear correlation, which also makes every later callback stale.
        """
        if not self._turn_orchestrator.accept_generation_terminal(
            generation_id,
            phase,
        ):
            return False
        self.generation_event.emit(
            AssistantGenerationEvent(
                generation_id=generation_id,
                phase=phase,
                text=text,
            )
        )
        return True

    def _finish_worker_error(
        self,
        message: str,
        *,
        outcome: str = "generation_error",
    ) -> None:
        """Publish one visible failure after correlation has been resolved.

        Finishes the current metrics turn and resets processing state.
        """
        was_processing = self.is_processing
        self.metrics.finish_turn()
        self.error_occurred.emit(message)
        if was_processing:
            self._publish_response(
                user_facing_generation_error(message),
                kind=AssistantResponseKind.ERROR,
            )
        self.status_update.emit("Error")
        self._publish_activity(
            AssistantTurnActivityPhase.NEEDS_ATTENTION,
            message=message,
            attention_kind=AssistantAttentionKind.ERROR,
        )
        self.is_processing = False
        self._emit_processing_finished(outcome)

    def close(self) -> bool:
        """Start signal-driven cleanup and report whether ownership is terminal."""
        if self._closed:
            if self._rag_shutdown_clean:
                return True
            self._rag_shutdown_clean = self._close_rag_lifecycle()
            self.shutdown_finished.emit(
                self._rag_shutdown_clean,
                (
                    ""
                    if self._rag_shutdown_clean
                    else self._rag_shutdown_failure_message()
                ),
            )
            return self._rag_shutdown_clean
        if self._shutdown_phase in {
            _ControllerShutdownPhase.WORKER_STOPPING,
            _ControllerShutdownPhase.THREAD_STOPPING,
        }:
            return False

        self._closing = True
        self._prepare_shutdown_once()
        worker = cast(Any, getattr(self, "worker", None))
        if worker is None:
            self._request_worker_thread_exit()
            return self._closed and self._rag_shutdown_clean

        if not isinstance(worker, QObject):
            return self._close_non_qobject_worker(worker)

        if sip.isdeleted(worker):
            self._request_worker_thread_exit()
            return self._closed and self._rag_shutdown_clean

        self._shutdown_phase = _ControllerShutdownPhase.WORKER_STOPPING
        if not self._shutdown_timeout_timer.isActive():
            self._shutdown_timeout_timer.start(WORKER_SHUTDOWN_TIMEOUT_MS)
        self._request_worker_shutdown()
        return self._closed

    def _prepare_shutdown_once(self) -> None:
        """Cancel controller-owned work exactly once before worker teardown."""
        if self._shutdown_preamble_complete:
            return
        self._shutdown_preamble_complete = True
        correlation = self._active_turn_correlation()
        self.is_processing = False
        self._turn_orchestrator.reset_for_shutdown()
        if correlation is not None:
            self._emit_processing_finished("shutdown_cancelled")
        self.pending_interactions.clear()
        self._invalidate_pending_rag_turn()
        if not self._rag_shutdown_attempted:
            self._rag_shutdown_attempted = True
            self._rag_shutdown_clean = self._close_rag_lifecycle()
            if not self._rag_shutdown_clean:
                logger.warning(
                    "Optional RAG retriever lifecycle did not stop cleanly; "
                    "controller shutdown will remain pending."
                )

    def _close_non_qobject_worker(self, worker: Any) -> bool:
        """Keep lightweight test doubles retryable without a Qt signal contract."""
        try:
            result = worker.shutdown(wait_ms=WORKER_GENERATION_SHUTDOWN_WAIT_MS)
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="assistant_controller_shutdown",
                operation="close_non_qobject_worker",
            )
            self._shutdown_phase = _ControllerShutdownPhase.OPEN
            return False
        if result is False:
            self._shutdown_phase = _ControllerShutdownPhase.OPEN
            return False
        self._request_worker_thread_exit()
        return self._closed and self._rag_shutdown_clean

    @pyqtSlot()
    def _request_worker_shutdown(self) -> None:
        """Queue one worker-owned cleanup attempt without entering a nested loop."""
        if self._shutdown_phase is not _ControllerShutdownPhase.WORKER_STOPPING:
            return
        worker = cast(Any, getattr(self, "worker", None))
        if worker is None or not isinstance(worker, QObject) or sip.isdeleted(worker):
            self._request_worker_thread_exit()
            return
        try:
            self.sig_shutdown_worker.emit()
        except (RuntimeError, TypeError):
            logger.debug("Agent worker shutdown signal could not be delivered")
            if not self._shutdown_retry_timer.isActive():
                self._shutdown_retry_timer.start(WORKER_SHUTDOWN_RETRY_INTERVAL_MS)

    @pyqtSlot(bool)
    def _on_worker_shutdown_finished(self, ok: bool) -> None:
        """Advance worker cleanup from its typed terminal acknowledgement."""
        if self._shutdown_phase is not _ControllerShutdownPhase.WORKER_STOPPING:
            return
        if ok:
            self._shutdown_retry_timer.stop()
            self._request_worker_thread_exit()
            return
        logger.warning("Agent worker cleanup is still pending; retrying asynchronously")
        if not self._shutdown_retry_timer.isActive():
            self._shutdown_retry_timer.start(WORKER_SHUTDOWN_RETRY_INTERVAL_MS)

    def _request_worker_thread_exit(self) -> None:
        """Request event-loop exit and wait only through ``QThread.finished``."""
        if self._closed:
            return
        self._shutdown_phase = _ControllerShutdownPhase.THREAD_STOPPING
        self._shutdown_retry_timer.stop()
        thread = cast(Any, getattr(self, "worker_thread", None))
        if not isinstance(thread, _QT_THREAD_TYPE):
            quit_thread = getattr(thread, "quit", None)
            if callable(quit_thread):
                quit_thread()
            self._finalize_shutdown()
            return
        if sip.isdeleted(thread) or not thread.isRunning():
            self._finalize_shutdown()
            return
        thread.quit()

    @pyqtSlot()
    def _on_worker_thread_finished(self) -> None:
        """Commit terminal ownership only after the native worker thread exits."""
        if self._shutdown_phase is not _ControllerShutdownPhase.THREAD_STOPPING:
            if self._shutdown_phase is _ControllerShutdownPhase.WORKER_STOPPING:
                logger.error(
                    "Assistant worker thread stopped before cleanup was confirmed"
                )
                self.shutdown_finished.emit(
                    False,
                    "Assistant worker stopped before cleanup completed.",
                )
            return
        self._finalize_shutdown()

    @pyqtSlot()
    def _on_shutdown_timeout(self) -> None:
        """Report slow cleanup while retaining ownership until worker success."""
        if self._closed:
            return
        logger.error(
            "Assistant worker cleanup exceeded %sms; cleanup remains pending",
            WORKER_SHUTDOWN_TIMEOUT_MS,
        )
        self._shutdown_timeout_timer.stop()
        worker = cast(Any, getattr(self, "worker", None))
        if isinstance(worker, QObject) and not sip.isdeleted(worker):
            self._disconnect_worker_callbacks(
                worker,
                preserve_shutdown_terminal=True,
            )
        if not self._shutdown_retry_timer.isActive():
            self._shutdown_retry_timer.start(WORKER_SHUTDOWN_RETRY_INTERVAL_MS)
        self.shutdown_finished.emit(
            False,
            "Assistant worker cleanup timed out; cleanup is still pending.",
        )

    def _disconnect_worker_callbacks(
        self,
        worker: QObject,
        *,
        preserve_shutdown_terminal: bool = False,
    ) -> None:
        """Fence late worker signals while preserving terminal cleanup evidence."""
        bindings = (
            ("generation_chunk_received", self._on_chunk_received),
            ("generation_finished", self._on_generation_finished),
            ("generation_error", self._on_generation_error),
            (
                "generation_dispatch_acknowledged",
                self._on_generation_dispatch_acknowledged,
            ),
            ("error", self._on_runtime_error),
            ("log", self.status_update),
            ("generation_stop_finished", self._on_generation_stop_finished),
            ("runtime_snapshot_changed", self._on_runtime_snapshot_changed),
            ("shutdown_finished", self._on_worker_shutdown_finished),
        )
        for signal_name, slot in bindings:
            if preserve_shutdown_terminal and signal_name == "shutdown_finished":
                continue
            signal = getattr(worker, signal_name, None)
            if signal is None:
                continue
            with suppress(RuntimeError, TypeError):
                signal.disconnect(slot)

    def _finalize_shutdown(self, detail: str = "") -> None:
        """Publish one terminal event without touching released Qt wrappers."""
        if self._closed:
            return
        self._shutdown_timeout_timer.stop()
        self._shutdown_retry_timer.stop()
        self.worker = None
        self._closed = True
        self._shutdown_phase = _ControllerShutdownPhase.CLOSED
        shutdown_ok = self._rag_shutdown_clean
        terminal_detail = (
            detail if shutdown_ok else self._rag_shutdown_failure_message()
        )
        self.shutdown_finished.emit(shutdown_ok, terminal_detail)

    @staticmethod
    def _rag_shutdown_failure_message() -> str:
        return "Assistant retrieval cleanup did not finish; cleanup is still pending."

    def _reject_command_while_closing(self, command: str) -> bool:
        """Reject new work once shutdown starts, while cleanup remains retryable."""
        if self.accepts_commands:
            return False
        logger.warning(
            "Assistant command '%s' rejected because controller is shutting down",
            command,
        )
        return True

    def _close_rag_lifecycle(self) -> bool:
        """Delegate optional retriever cleanup to its sole lifecycle owner."""
        try:
            return bool(self._rag_lifecycle.close())
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="assistant_controller_shutdown",
                operation="close_rag_lifecycle",
            )
            return False

    def runtime_snapshot(self) -> AssistantRuntimeSnapshot:
        """Return the latest worker-published runtime state."""
        return self._worker_runtime_snapshot

    def _on_runtime_snapshot_changed(self, snapshot: object) -> None:
        if not isinstance(snapshot, AssistantRuntimeSnapshot):
            logger.error(
                "Ignored untyped assistant runtime transition: %s",
                type(snapshot).__name__,
            )
            return
        validation_error = snapshot.validation_error()
        if validation_error:
            logger.error(
                "Ignored inconsistent assistant runtime transition: %s",
                redact_public_text(validation_error),
            )
            return
        self._worker_runtime_snapshot = snapshot
        self.runtime_state_changed.emit(snapshot)

    def stop_generation(self):
        """Request generation cancellation and wait for worker acknowledgement."""
        if self._reject_command_while_closing("stop generation"):
            return
        session = self.pending_interactions
        pending_handoff = session.workflow_handoff
        if pending_handoff is not None:
            self.on_workflow_ui_handoff_resolved(
                WorkflowUiHandoffResolution.for_request(
                    pending_handoff,
                    status=WorkflowUiHandoffResolutionStatus.CANCELLED,
                    message="The pending settings step was cancelled.",
                )
            )
            return
        pending_confirmation = session.confirmation
        if pending_confirmation is not None:
            self.on_user_confirmation_resolved(
                AgentConfirmationResolution.for_request(
                    pending_confirmation.request,
                    status=AgentConfirmationResolutionStatus.CANCELLED,
                )
            )
            return
        if self.is_processing:
            if self._turn_orchestrator.request_cancellation():
                self.status_update.emit("Stopping...")
                self._publish_activity(AssistantTurnActivityPhase.STOPPING)
                self.metrics.finish_turn()
            if self._turn_orchestrator.waiting_for_rag:
                self._invalidate_pending_rag_turn()
                self._complete_cancelled_turn()
                return
            generation_id = self._turn_orchestrator.begin_stopping_generation()
            if generation_id is None:
                self._complete_cancelled_turn()
                return
            request = AssistantGenerationStopRequest(generation_id=generation_id)
            worker = getattr(self, "worker", None)
            worker_object = (
                cast(QObject, worker) if isinstance(worker, QObject) else None
            )
            if (
                worker_object is not None
                and worker_object.thread() is not QThread.currentThread()
            ):
                self.sig_cancel_generation.emit(request)
            else:
                cancel_generation = getattr(worker, "cancel_generation", None)
                if callable(cancel_generation):
                    cancel_generation(request)
                else:
                    self._on_generation_stop_finished(
                        AssistantGenerationStopAcknowledgement(
                            generation_id=generation_id,
                            stopped=True,
                        )
                    )

    def _on_generation_stop_finished(self, payload: object) -> None:
        """Keep the UI in Stopping state until the worker owns no live thread."""
        if not isinstance(payload, AssistantGenerationStopAcknowledgement):
            logger.error("Ignored untyped assistant generation stop acknowledgement.")
            return
        if not self._turn_orchestrator.cancelled:
            return
        if not self._turn_orchestrator.accepts_stop_acknowledgement(
            payload.generation_id
        ):
            logger.warning(
                "Ignored stale generation stop acknowledgement for %s; "
                "active=%s stopping=%s",
                redact_public_text(payload.generation_id),
                self._turn_orchestrator.active_generation_id,
                self._turn_orchestrator.stopping_generation_id,
            )
            return
        if not payload.stopped:
            self.status_update.emit("Stopping...")
            return
        self._complete_cancelled_turn()

    def _complete_cancelled_turn(self) -> None:
        """Publish one durable cancellation result after work has stopped."""
        generation_id = self._turn_orchestrator.active_generation_id
        if not self._turn_orchestrator.accept_cancellation_terminal():
            return
        if generation_id is not None:
            self.generation_event.emit(
                AssistantGenerationEvent(
                    generation_id=generation_id,
                    phase=AssistantGenerationEventPhase.CANCELLED,
                )
            )
        message = ASSISTANT_CANCELLED_MESSAGE
        self.current_response = ""
        self._append_history("assistant", message)
        self._publish_response(message, kind=AssistantResponseKind.CANCELLED)
        self.is_processing = False
        self.status_update.emit("Stopped")
        self._publish_activity(AssistantTurnActivityPhase.IDLE)
        self._emit_processing_finished("cancelled")

    def set_model(self, launch_spec: AssistantRuntimeLaunchSpec):
        """Forward one pre-resolved model selection to the worker.

        Args:
            launch_spec: Exact immutable selection resolved by the lifecycle.

        """
        if self._reject_command_while_closing("set model"):
            return
        if not isinstance(launch_spec, AssistantRuntimeLaunchSpec):
            raise TypeError("Assistant model switch requires a runtime launch spec.")
        self.status_update.emit(
            f"Switching model to: {redact_public_text(launch_spec.model_id)}"
        )
        self.sig_reinit.emit(launch_spec)

    def reset_conversation(self):
        """Resets conversation history and all internal state counters."""
        if self._reject_command_while_closing("reset conversation"):
            return
        if (
            self._turn_orchestrator.has_active_host_turn
            or self.is_processing
            or self.pending_interactions.workflow_handoff is not None
        ):
            logger.warning("Conversation reset ignored while a turn is active")
            return
        self._invalidate_pending_rag_turn()
        self._conversation.clear()
        self.current_response = ""
        self._tool_attempt_session.reset_for_user_turn()
        self.pending_interactions.reset()
        self._turn_orchestrator.reset_conversation()

        # Reset metrics for new conversation
        self.metrics.reset()

        # Clear Assembler context as well
        self.assembler.clear_context()
        self.assembler.clear_turn_authorization()

        self.status_update.emit("Conversation reset.")
        self._publish_activity(AssistantTurnActivityPhase.IDLE)

    @pyqtSlot(object)
    def execute_debug_tool(
        self,
        payload: object,
    ) -> AssistantTurnDeliveryAcknowledgement:
        """Execute one host-correlated diagnostic tool request."""
        if not isinstance(payload, AssistantDebugToolRequest):
            raise TypeError("Assistant debug turns must use AssistantDebugToolRequest.")
        try:
            if not self.accepts_commands:
                self.turn_finished.emit(
                    AssistantTurnTerminal(
                        correlation=payload.correlation,
                        outcome="rejected_closing",
                    )
                )
                return AssistantTurnDeliveryAcknowledgement(
                    correlation=payload.correlation,
                    phase=AssistantTurnDeliveryPhase.REJECTED,
                    message="Assistant controller is closing.",
                )
            if (
                self._turn_orchestrator.has_active_host_turn
                or self.is_processing
                or self.pending_interactions.has_pending
            ):
                self.turn_finished.emit(
                    AssistantTurnTerminal(
                        correlation=payload.correlation,
                        outcome="rejected_busy",
                    )
                )
                return AssistantTurnDeliveryAcknowledgement(
                    correlation=payload.correlation,
                    phase=AssistantTurnDeliveryPhase.REJECTED,
                    message="Assistant controller is busy.",
                )
            self._turn_orchestrator.bind_correlation(payload.correlation)
            self._execute_admitted_debug_tool(
                payload.tool_name,
                payload.to_params(),
                confirmed=payload.confirmed,
                authorization_text=payload.authorization_text,
            )
        except Exception as exc:
            failure = safe_unexpected_failure(
                logger,
                exc,
                boundary="assistant_debug_controller",
                operation=payload.tool_name,
            )
            self._finish_turn_delivery_error(payload)
            return AssistantTurnDeliveryAcknowledgement(
                correlation=payload.correlation,
                phase=AssistantTurnDeliveryPhase.ERROR,
                message=failure.message,
            )
        return AssistantTurnDeliveryAcknowledgement(
            correlation=payload.correlation,
            phase=AssistantTurnDeliveryPhase.ACCEPTED,
        )

    def _execute_admitted_debug_tool(
        self,
        tool_name: str,
        params: dict[str, Any],
        *,
        confirmed: bool = False,
        authorization_text: str = "",
    ) -> None:
        """Execute a diagnostic tool after exact host-turn admission.

        Used by Debug Mode to invoke tools manually.  The call and its
        result are recorded in conversation history.

        Args:
            tool_name: Name of the tool to execute.
            params: Dictionary of parameters for the tool.

        """
        self._require_active_turn_correlation()
        self._reset_user_turn_state()
        reserved_response = tool_name == MODEL_RESPONSE_TOOL_NAME
        safe_tool_name = (
            tool_name
            if reserved_response
            or AGENT_ACTION_CONTRACTS.contract_for(tool_name) is not None
            else "unknown_debug_tool"
        )
        safe_tool_name = redact_public_text(safe_tool_name)
        logger.info(
            "Debug execution requested for %s (parameter count: %d)",
            safe_tool_name,
            len(params),
        )

        self.is_processing = True
        self._append_history("user", f"[DEBUG] Tool Call: {safe_tool_name}")
        if confirmed:
            logger.warning(
                "Ignored pre-confirmed diagnostic action; confirmation is UI-owned."
            )
        if reserved_response:
            self._execute_debug_response(params)
            return
        if AGENT_ACTION_CONTRACTS.contract_for(tool_name) is None:
            self._handle_tool_attempt_blocked(
                "unknown_debug_tool",
                ToolCommandResult.failure(
                    "unknown_debug_tool",
                    "The requested debug tool is unavailable.",
                    error_type="input",
                    recoverable=False,
                ),
            )
            return

        context = self._tool_attempt_coordinator.context_for(tool_name)
        state = context.state if isinstance(context.state, dict) else {}
        workflow_stage = str(state.get("pipeline_stage") or "unavailable")
        publication = PromptToolPublication(
            tool_names=frozenset({tool_name}),
            workflow_stage=workflow_stage,
            backend_generation=context.generation,
        )
        self._turn_orchestrator.set_active_publication(publication)
        repeated = self._tool_attempt_session.record_tool_proposal(tool_name, params)
        decision = self._tool_attempt_coordinator.evaluate(
            ToolAttemptRequest(
                command_name=tool_name,
                params=dict(params),
                confidence=1.0,
                publication=publication,
                latest_user_text=authorization_text,
                repeated=repeated,
                enforce_direct_parameter_origins=False,
            )
        )
        if self._present_tool_attempt_boundary(decision):
            return
        self._execute_tool_attempt(decision)

    def _execute_debug_response(self, params: dict[str, Any]) -> None:
        """Replay one reserved response through the normal strict presentation path."""
        self.assembler.build_system_prompt("")
        publication = self.assembler.latest_tool_publication
        self._turn_orchestrator.set_active_publication(publication)
        response_text = json.dumps(
            {
                "workflow_stage": publication.workflow_stage,
                "tool_name": MODEL_RESPONSE_TOOL_NAME,
                "parameters": dict(params),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        envelope = CommandParser.parse_product(response_text)
        if (
            envelope.status is not ToolEnvelopeStatus.NO_TOOL
            or envelope.workflow_stage != publication.workflow_stage
            or not envelope.message
        ):
            self._publish_response(
                "The requested diagnostic response is invalid.",
                kind=AssistantResponseKind.ERROR,
            )
            self.metrics.finish_turn()
            self.status_update.emit("Diagnostic response rejected")
            self._publish_activity(AssistantTurnActivityPhase.NEEDS_ATTENTION)
            self.is_processing = False
            self._emit_processing_finished("failed")
            return
        self._finalize_turn(envelope.message)

    def on_panel_navigation_resolved(
        self,
        request: object,
        *,
        success: bool,
    ) -> None:
        """Finish one panel request only after its exact UI callback returns."""
        if not isinstance(request, AssistantPanelNavigationRequest):
            logger.error("Ignored untyped assistant panel navigation result")
            return
        correlation = request.correlation
        if correlation is None or correlation != self._active_turn_correlation():
            logger.warning("Ignored stale assistant panel navigation result")
            return
        if request.view_mode:
            destination = request.view_mode.replace("_", " ").title()
            success_message = f"Opened {destination} in Visualization panel."
        else:
            destination = request.target.value.title()
            success_message = f"Opened {destination} panel."
        if success:
            self._publish_response(
                success_message,
                kind=AssistantResponseKind.TOOL_RESULT,
            )
            outcome = "completed"
        else:
            self._publish_response(
                f"The {destination} view could not be opened.",
                kind=AssistantResponseKind.ERROR,
            )
            outcome = "panel_navigation_failed"
        self.status_update.emit("Ready" if success else "Panel unavailable")
        self.is_processing = False
        self._emit_processing_finished(outcome)
