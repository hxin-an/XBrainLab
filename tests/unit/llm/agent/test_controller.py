"""Coverage tests for LLMController - targeting uncovered lines."""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import replace
from typing import Any, cast
from unittest.mock import MagicMock, call, patch

import pytest

from XBrainLab.backend.application import CommandName
from XBrainLab.backend.application.capabilities import (
    CapabilityPolicy,
    CommandCapability,
)
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.application.view_publication import (
    ApplicationViewPublication,
    InterpretationReviewIdentity,
)
from XBrainLab.llm.agent.assistant_activity import (
    AssistantAttentionKind,
    AssistantTurnActivityPhase,
)
from XBrainLab.llm.agent.confirmation import (
    AgentConfirmationRequest,
    AgentConfirmationResolution,
    AgentConfirmationResolutionStatus,
)
from XBrainLab.llm.agent.interaction import (
    AgentInteractionOutcome,
    AgentInteractionStatus,
)
from XBrainLab.llm.agent.pending_interaction import (
    PendingConfirmation,
    PendingInteractionCoordinator,
)
from XBrainLab.llm.agent.product_turn_policy import ProductTurnPolicy
from XBrainLab.llm.agent.request_admission import (
    UserRequestAdmission,
    UserRequestAdmissionAction,
)
from XBrainLab.llm.agent.response_presentation import (
    AssistantPanelNavigationRequest,
    AssistantPanelTarget,
    AssistantResponseKind,
    AssistantResponsePresentation,
)
from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
    AssistantRuntimeSnapshot,
)
from XBrainLab.llm.agent.tool_attempt_coordinator import (
    ResourcePreflightReceipt,
    ToolAttemptAction,
    ToolAttemptDecision,
    ToolAttemptFeedback,
    ToolAttemptRequest,
)
from XBrainLab.llm.agent.tool_execution_coordinator import ToolExecutionOutcome
from XBrainLab.llm.agent.turn import (
    AssistantDebugToolRequest,
    AssistantGenerationEvent,
    AssistantGenerationEventPhase,
    AssistantGenerationStopAcknowledgement,
    AssistantGenerationStopRequest,
    AssistantResponseContract,
    AssistantTurnCorrelation,
    AssistantTurnDeliveryPhase,
    AssistantTurnRequest,
    AssistantTurnScope,
    AssistantTurnTerminal,
)
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolution,
    WorkflowUiHandoffResolutionStatus,
)
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.runtime_selection import (
    AssistantRuntimeLaunchResolver,
    AssistantRuntimeLaunchSpec,
)
from XBrainLab.llm.tools.application_surface import (
    ToolAvailabilityContext,
    ToolCommandResult,
)
from XBrainLab.llm.tools.result_contract import (
    SAFE_UNEXPECTED_FAILURE_MESSAGE,
    ToolResult,
    UiRequest,
    UiRequestKind,
)
from XBrainLab.product_language import tool_action_label


def _runtime_launch_spec(model_id: str | None = None) -> AssistantRuntimeLaunchSpec:
    selected_model = model_id or LLMConfig.default_local_model_id()
    config = LLMConfig(model_name=selected_model)
    config.local_backend_ready = lambda candidate=None: (  # type: ignore[method-assign]
        candidate == selected_model
    )
    config.local_backend_status_message = (  # type: ignore[method-assign]
        lambda candidate=None: "Local runtime ready."
    )
    resolution = AssistantRuntimeLaunchResolver().resolve(config)
    assert resolution.launch_spec is not None
    return resolution.launch_spec


def _submit_user_turn(ctrl: Any, text: str) -> AssistantTurnCorrelation:
    """Enter controller behavior through the host-admitted turn contract."""
    if not ctrl.is_processing and not ctrl.pending_interactions.has_pending:
        ctrl._active_host_turn_id = None
        ctrl._active_host_turn_generation = None
    sequence = getattr(ctrl, "_test_host_turn_sequence", 0) + 1
    ctrl._test_host_turn_sequence = sequence
    correlation = AssistantTurnCorrelation(
        generation=sequence,
        turn_id=sequence,
    )
    ctrl.handle_user_turn(
        AssistantTurnRequest.single_action(correlation=correlation, text=text)
    )
    return correlation


def _set_guided_turn_scope(ctrl: Any) -> None:
    """Set the immutable scope used by focused controller-policy tests."""
    ctrl._active_turn_scope = AssistantTurnScope.GUIDED_WORKFLOW


def _tool_outcome(
    message: str,
    *,
    ok: bool = True,
    tool_name: str = "cmd",
    error_type: str | None = None,
) -> ToolExecutionOutcome:
    result = ToolCommandResult(
        ok=ok,
        tool_name=tool_name,
        message=message,
        error_type=error_type or ("none" if ok else "runtime"),
    )
    return ToolExecutionOutcome(ok, result)


def _resolve_ui_handoff(
    ctrl: Any,
    status: WorkflowUiHandoffResolutionStatus,
    *,
    request: WorkflowUiHandoffRequest | None = None,
    message: str = "",
) -> WorkflowUiHandoffResolution:
    active_request = request or ctrl.pending_interactions.workflow_handoff
    assert isinstance(active_request, WorkflowUiHandoffRequest)
    resolution = WorkflowUiHandoffResolution.for_request(
        active_request,
        status=status,
        message=message,
    )
    ctrl.on_workflow_ui_handoff_resolved(resolution)
    return resolution


def _pending_session(ctrl: Any) -> PendingInteractionCoordinator:
    session = ctrl.pending_interactions
    assert isinstance(session, PendingInteractionCoordinator)
    return session


def _begin_confirmation(
    ctrl: Any,
    decision: ToolAttemptDecision,
    request: AgentConfirmationRequest | None = None,
) -> PendingConfirmation:
    paired_request = request or ctrl._build_confirmation_request(decision)
    return _pending_session(ctrl).begin_confirmation(decision, paired_request)


def _assert_intent_boundary_result(
    result: object,
    *,
    tool_name: str,
    command_name: CommandName,
    blocked_reason: str,
    message: str,
) -> ToolCommandResult:
    assert isinstance(result, ToolCommandResult), result
    assert result.ok is False
    assert result.tool_name == tool_name
    assert result.command_name == command_name.value
    assert result.error_type == "precondition"
    assert result.recoverable is True
    assert result.blocked_reason == blocked_reason
    assert result.message == message
    return result


def _assert_confirmation_prompt(
    ctrl: Any,
    *,
    tool_name: str,
    params: dict[str, Any],
    description: str,
    destructive: bool = False,
) -> ToolAttemptDecision:
    pending_pair = _pending_session(ctrl).confirmation
    assert isinstance(pending_pair, PendingConfirmation)
    pending = pending_pair.decision
    request = pending_pair.request
    assert pending.action is ToolAttemptAction.CONFIRMATION_REQUIRED
    assert pending.command_name == tool_name
    assert pending.params == params
    assert request.command_name == tool_name
    assert request.action_label == tool_action_label(tool_name)
    assert request.description == description
    assert request.destructive is destructive
    assert request.parameter_rows == tuple(
        (str(key).replace("_", " ").capitalize(), str(value))
        for key, value in sorted(params.items())
    )
    ctrl.status_update.emit.assert_any_call(f"Waiting for confirmation: {tool_name}")
    ctrl.confirmation_requested.emit.assert_called_once_with(request)
    return pending


def _resolve_confirmation(ctrl: Any, *, approved: bool) -> AgentConfirmationRequest:
    """Resolve the exact pending request through the typed product contract."""
    pending_pair = _pending_session(ctrl).confirmation
    assert isinstance(pending_pair, PendingConfirmation)
    request = pending_pair.request
    ctrl.on_user_confirmation_resolved(
        AgentConfirmationResolution.for_request(
            request,
            status=(
                AgentConfirmationResolutionStatus.APPROVED
                if approved
                else AgentConfirmationResolutionStatus.CANCELLED
            ),
        )
    )
    return request


def _allow_prompt_tools(ctrl: Any) -> None:
    from XBrainLab.llm.agent.assembler import PromptToolPublication
    from XBrainLab.llm.tools.application_surface import (
        READ_ONLY_TOOLS,
        TOOL_TO_COMMAND,
        ToolAvailability,
        ToolAvailabilityContext,
    )

    _set_context_reader(
        ctrl,
        side_effect=lambda tool_name: ToolAvailabilityContext(
            availability=ToolAvailability(tool_name=tool_name, enabled=True),
            state={"pipeline_stage": "empty"},
            generation=1,
        ),
    )
    ctrl._active_tool_publication = PromptToolPublication(
        tool_names=frozenset(
            set(TOOL_TO_COMMAND)
            | set(READ_ONLY_TOOLS)
            | {
                "cmd",
                "first",
                "review_choice",
            }
        ),
        backend_generation=1,
    )


def _set_context_reader(
    ctrl: Any,
    *,
    return_value: Any | None = None,
    side_effect: Any | None = None,
) -> MagicMock:
    """Install an explicit context source at the extracted policy boundary."""
    source = MagicMock()
    source.get_context = MagicMock(
        return_value=return_value,
        side_effect=side_effect,
    )
    ctrl._tool_attempt_coordinator._context_source = source
    return source.get_context


def _evaluate_policy(
    ctrl: Any,
    tool_name: str,
    context: Any,
    *,
    params: dict[str, Any] | None = None,
    text: str | None = None,
) -> ToolAttemptDecision:
    _set_context_reader(ctrl, return_value=context)
    return ctrl._tool_attempt_coordinator.evaluate(
        ToolAttemptRequest(
            command_name=tool_name,
            params=params or {},
            confidence=0.9,
            publication=ctrl._active_tool_publication,
            latest_user_text=(
                ctrl._latest_user_request_text() if text is None else text
            ),
        )
    )


def _tool_context(availability: Any):
    from XBrainLab.llm.tools.application_surface import ToolAvailabilityContext

    return ToolAvailabilityContext(
        availability=availability,
        state={"pipeline_stage": "empty"},
        generation=1,
    )


def _enabled_tool_context(
    tool_name: str,
    *,
    generation: int = 1,
    destructive: bool = False,
):
    return _tool_context_with_generation(
        tool_name,
        generation,
        destructive=destructive,
    )


def _tool_context_with_generation(
    tool_name: str,
    generation: int,
    *,
    destructive: bool = False,
):
    from XBrainLab.llm.tools.application_surface import (
        ToolAvailability,
        ToolAvailabilityContext,
    )

    return ToolAvailabilityContext(
        availability=ToolAvailability(
            tool_name=tool_name,
            enabled=True,
            destructive=destructive,
        ),
        state={"pipeline_stage": "empty", "generation_marker": generation},
        generation=generation,
    )


def _pending_decision(
    tool_name: str,
    params: dict[str, Any],
    *,
    context: Any | None = None,
    confirmation_kind: str | None = None,
    resource_preflight_receipt: ResourcePreflightReceipt | None = None,
) -> ToolAttemptDecision:
    return ToolAttemptDecision(
        action=ToolAttemptAction.CONFIRMATION_REQUIRED,
        command_name=tool_name,
        params=params,
        context=context or _enabled_tool_context(tool_name),
        tool=MagicMock(description=tool_name),
        confirmation_kind=confirmation_kind,
        resource_preflight_receipt=resource_preflight_receipt,
    )


def _training_resource_preflight(
    *,
    batch_size: int = 32,
    receipt_suffix: str = "1",
) -> dict[str, Any]:
    return {
        "payload_type": "training_resource_preflight",
        "risk_level": "warning",
        "requires_confirmation": True,
        "message": "Training may use most available memory.",
        "model_name": "EEGNet",
        "training_batch_size": batch_size,
        "estimated_gpu_batch_working_set_bytes": 4_096,
        "available_vram_bytes": 8_192,
        "confirmation_token": f"training-receipt-{receipt_suffix}",
        "confirmation_command": "start_training",
        "configuration_fingerprint": f"configuration-{receipt_suffix}",
        "preflight_fingerprint": f"preflight-{receipt_suffix}",
        "scope_fingerprint": f"scope-{receipt_suffix}",
        "confirmation_ttl_seconds": 120.0,
    }


def _pending_training_resource_confirmation(
    ctrl: Any,
    *,
    params: dict[str, Any] | None = None,
    preflight: dict[str, Any] | None = None,
) -> ToolAttemptDecision:
    context = _enabled_tool_context("start_training", generation=91)
    initial = ToolAttemptDecision(
        action=ToolAttemptAction.EXECUTE,
        command_name="start_training",
        params=dict(params or {}),
        context=context,
    )
    resource_preflight = preflight or _training_resource_preflight()
    warning = ToolCommandResult.failure(
        "start_training",
        str(resource_preflight["message"]),
        command_name="train",
        error_type="confirmation_required",
        diagnostics={"resource_preflight": resource_preflight},
    )
    pending = ctrl._tool_attempt_coordinator.resource_confirmation(
        initial,
        warning,
    )
    assert isinstance(pending, ToolAttemptDecision)
    assert pending.action is ToolAttemptAction.CONFIRMATION_REQUIRED
    assert pending.command_name == "start_training"
    assert pending.params == dict(params or {})
    assert pending.context == context
    assert isinstance(pending.result, ToolCommandResult)
    assert pending.result.ok is False
    assert pending.result.tool_name == "start_training"
    assert pending.result.command_name == "train"
    assert pending.result.message == "Training may use most available memory."
    assert pending.result.error_type == "confirmation_required"
    assert pending.result.blocked_reason is None
    assert pending.result.state is None
    assert pending.result.capability is None
    assert pending.result.diagnostics == {"resource_preflight": resource_preflight}
    receipt = pending.resource_preflight_receipt
    assert isinstance(receipt, ResourcePreflightReceipt)
    assert receipt.command_name == "start_training"
    assert receipt.token == resource_preflight["confirmation_token"]
    assert receipt.candidate_id is None
    assert (
        receipt.configuration_fingerprint
        == resource_preflight["configuration_fingerprint"]
    )
    assert receipt.preflight_fingerprint == resource_preflight["preflight_fingerprint"]
    assert receipt.scope_fingerprint == resource_preflight["scope_fingerprint"]
    assert receipt.ttl_seconds == 120.0
    return pending


def _assert_training_resource_context(context: object) -> ToolAvailabilityContext:
    assert isinstance(context, ToolAvailabilityContext)
    assert context.availability.tool_name == "start_training"
    assert context.availability.enabled is True
    assert context.availability.command_name is None
    assert context.availability.reason_text == ""
    assert context.state == {"pipeline_stage": "empty", "generation_marker": 91}
    assert context.generation == 91
    assert context.policy_error is None
    return context


class _RAGLifecycleProbe:
    def __init__(self, *, accept: bool = True) -> None:
        self.accept = accept
        self.requests: list[tuple[int, str]] = []
        self._callback: Any | None = None

    def retrieve(
        self,
        turn_id: int,
        query: str,
        callback: Any,
        *,
        allowed_tool_names: frozenset[str] | None = None,
    ) -> bool:
        del allowed_tool_names
        if not self.accept:
            return False
        self.requests.append((turn_id, query))
        self._callback = callback
        return True

    def complete(self, *, features: str = "", error: str = "") -> None:
        assert self.requests
        assert self._callback is not None
        turn_id, query = self.requests[-1]
        self._callback(turn_id, query, features, error)

    def close(self) -> bool:
        return True


def _use_rag_probe(ctrl: Any, *, accept: bool = True) -> _RAGLifecycleProbe:
    lifecycle = _RAGLifecycleProbe(accept=accept)
    ctrl._rag_lifecycle = lifecycle
    ctrl.sig_rag_context_ready.emit.side_effect = ctrl._on_rag_context_ready
    return lifecycle


class _BlockingRAGRetriever:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.closed = False

    def initialize(self) -> None:
        return None

    def get_similar_examples(
        self,
        query: str,
        *,
        allowed_tool_names: frozenset[str] | None = None,
    ) -> str:
        del allowed_tool_names
        self.started.set()
        self.release.wait(timeout=2)
        return "RAG info"

    def close(self) -> None:
        self.closed = True
        self.release.set()


def _make_real_signal_controller(
    rag_retriever: Any,
    *,
    rag_lifecycle: Any | None = None,
) -> Any:
    from PyQt6.QtCore import QObject

    with (
        patch("XBrainLab.llm.agent.controller.ToolRegistry"),
        patch("XBrainLab.llm.agent.controller.ContextAssembler"),
        patch("XBrainLab.llm.agent.controller.VerificationLayer"),
        patch(
            "XBrainLab.llm.agent.controller.RAGRetriever",
            return_value=rag_retriever,
        ),
        patch("XBrainLab.llm.agent.controller.QThread"),
        patch("XBrainLab.llm.agent.controller.AgentWorker"),
        patch("XBrainLab.llm.agent.controller.AVAILABLE_TOOLS", []),
    ):
        from XBrainLab.llm.agent.controller import LLMController

        controller = LLMController(MagicMock(), rag_lifecycle=rag_lifecycle)
        assert isinstance(controller, QObject)
        return controller


@pytest.fixture
def _mock_qt():
    """Patch Qt imports so controller module loads without a running QApp."""
    with patch.dict(
        "sys.modules",
        {
            "PyQt6": MagicMock(),
            "PyQt6.QtCore": MagicMock(),
        },
    ):
        yield


@pytest.fixture
def ctrl():
    """Build an LLMController with all heavy deps mocked.

    Use the real QObject constructor while mocking heavyweight runtime
    collaborators. This keeps Qt's signal host valid and still exercises the
    product constructor.
    """
    with (
        patch("XBrainLab.llm.agent.controller.ToolRegistry"),
        patch("XBrainLab.llm.agent.controller.ContextAssembler"),
        patch("XBrainLab.llm.agent.controller.VerificationLayer"),
        patch("XBrainLab.llm.agent.controller.RAGRetriever"),
        patch("XBrainLab.llm.agent.controller.QThread"),
        patch("XBrainLab.llm.agent.controller.AgentWorker"),
        patch("XBrainLab.llm.agent.controller.AVAILABLE_TOOLS", []),
    ):
        from XBrainLab.llm.agent.controller import LLMController

        study = MagicMock()

        # Pre-set signal mocks on the class so __init__ can .connect() them
        signal_names = [
            "response_presentation_ready",
            "generation_event",
            "processing_finished",
            "turn_finished",
            "status_update",
            "error_occurred",
            "panel_navigation_requested",
            "sig_initialize",
            "sig_generate",
            "sig_reinit",
            "sig_cancel_generation",
            "sig_shutdown_worker",
            "sig_rag_context_ready",
            "application_command_completed",
            "application_command_started",
            "runtime_state_changed",
            "interaction_resolved",
            "confirmation_requested",
            "activity_changed",
            "workflow_ui_handoff_requested",
        ]
        c = LLMController(study)
        for name in signal_names:
            setattr(c, name, MagicMock())
        # Most controller unit tests isolate a later boundary. They use an
        # explicit publication mock so the new publication gate does not hide
        # the behavior under test; dedicated tests above exercise fail-closed
        # publication behavior with the real contract.
        c._active_tool_publication = MagicMock()
        c._active_tool_publication.permits.return_value = True
        c._request_admission.evaluate = MagicMock(
            return_value=UserRequestAdmission(
                UserRequestAdmissionAction.GENERATE,
            )
        )
        _set_context_reader(
            c,
            side_effect=lambda tool_name: _enabled_tool_context(tool_name),
        )
        c._active_host_turn_generation = 1
        c._active_host_turn_id = 1
        yield c


# --- _append_history ---
class TestAppendHistory:
    def test_appends_message(self, ctrl):
        ctrl._append_history("user", "hello")
        assert ctrl.history == [{"role": "user", "content": "hello"}]

    def test_sliding_window(self, ctrl):
        ctrl.MAX_HISTORY = 5
        ctrl._conversation.max_size = 5
        for i in range(10):
            ctrl._append_history("user", str(i))
        assert len(ctrl.history) == 5
        assert ctrl.history[0]["content"] == "5"


def test_blocked_request_is_presented_before_rag_or_model_generation(ctrl):
    ctrl._request_admission.evaluate = MagicMock(
        return_value=UserRequestAdmission(
            UserRequestAdmissionAction.BLOCKED,
            command=CommandName.TRAIN,
            message="Generate datasets before training.",
        )
    )
    rag = _use_rag_probe(ctrl)
    ctrl._generate_response = MagicMock()
    publication = MagicMock()

    with patch("XBrainLab.llm.agent.controller.get_application_service") as get_service:
        get_service.return_value.get_view_publication.return_value = publication
        _submit_user_turn(ctrl, "Train now.")

    ctrl._request_admission.evaluate.assert_called_once_with(
        "Train now.",
        publication,
        scope=AssistantTurnScope.SINGLE_ACTION,
        terminal_command=None,
    )
    assert rag.requests == []
    ctrl._generate_response.assert_not_called()
    presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
    assert presentation.kind is AssistantResponseKind.BLOCKED
    assert "Generate datasets before training" in presentation.text
    assert ctrl.is_processing is False


def test_generated_request_preserves_admitted_command_for_prompt_scope(ctrl):
    ctrl._request_admission.evaluate = MagicMock(
        return_value=UserRequestAdmission(
            UserRequestAdmissionAction.GENERATE,
            command=CommandName.SCAN_SOURCE,
        )
    )
    publication = MagicMock()

    with patch("XBrainLab.llm.agent.controller.get_application_service") as get_service:
        get_service.return_value.get_view_publication.return_value = publication
        handled = ctrl._handle_request_admission("Load /data/S04.edf")

    assert handled is False
    ctrl.assembler.set_turn_authorized_command.assert_called_once_with(
        CommandName.SCAN_SOURCE.value
    )


def test_missing_decision_opens_existing_ui_before_rag_or_model(ctrl):
    ctrl._request_admission.evaluate = MagicMock(
        return_value=UserRequestAdmission(
            UserRequestAdmissionAction.UI_HANDOFF,
            command=CommandName.CREATE_EPOCH,
            message="Review the required choices in XBrainLab.",
            decision_fields=("target_event", "epoch_window"),
            suggested_values=(("target_event", "769"),),
        )
    )
    rag = _use_rag_probe(ctrl)
    ctrl._generate_response = MagicMock()
    publication = MagicMock()

    with patch("XBrainLab.llm.agent.controller.get_application_service") as get_service:
        get_service.return_value.get_view_publication.return_value = publication
        _submit_user_turn(ctrl, "Create epochs now.")

    assert rag.requests == []
    ctrl._generate_response.assert_not_called()
    request = ctrl.workflow_ui_handoff_requested.emit.call_args.args[0]
    assert isinstance(request, WorkflowUiHandoffRequest)
    assert request.command is CommandName.CREATE_EPOCH
    assert request.decision_fields == ("target_event", "epoch_window")
    assert request.suggestions == {"target_event": "769"}
    assert ctrl.pending_interactions.workflow_handoff == request
    assert ctrl.is_processing is True


def test_import_review_handoff_binds_publication_and_candidate_identity(ctrl):
    ctrl._request_admission.evaluate = MagicMock(
        return_value=UserRequestAdmission(
            UserRequestAdmissionAction.UI_HANDOFF,
            command=CommandName.APPLY_INTERPRETATION,
            decision_fields=("import_review",),
        )
    )
    publication = MagicMock()
    publication.usable = True
    publication.generation = 52
    publication.state.interpretation.latest_scan_id = "scan-a"
    publication.state.interpretation.latest_candidate_id = "candidate-a"

    with patch("XBrainLab.llm.agent.controller.get_application_service") as get_service:
        get_service.return_value.get_view_publication.return_value = publication
        handled = ctrl._handle_request_admission("Review the import")

    assert handled is True
    request = ctrl.workflow_ui_handoff_requested.emit.call_args.args[0]
    assert isinstance(request, WorkflowUiHandoffRequest)
    assert request.interpretation_identity == InterpretationReviewIdentity(
        publication_generation=52,
        scan_id="scan-a",
        candidate_id="candidate-a",
    )


def test_read_only_state_query_executes_without_model_generated_json(ctrl):
    ctrl._request_admission.evaluate = MagicMock(
        return_value=UserRequestAdmission(
            UserRequestAdmissionAction.EXECUTE_READ_ONLY,
            command=CommandName.QUERY_STATE,
        )
    )
    ctrl._execute_tool_attempt = MagicMock()
    ctrl._generate_response = MagicMock()
    rag = _use_rag_probe(ctrl)
    publication = MagicMock()

    with patch("XBrainLab.llm.agent.controller.get_application_service") as get_service:
        get_service.return_value.get_view_publication.return_value = publication
        _submit_user_turn(ctrl, "What is ready now?")

    assert rag.requests == []
    ctrl._generate_response.assert_not_called()
    decision = ctrl._execute_tool_attempt.call_args.args[0]
    assert decision.action is ToolAttemptAction.EXECUTE
    assert decision.command_name == "query_state"
    assert decision.params == {"query": "state"}


def test_runtime_snapshot_is_typed_and_republished(ctrl):
    snapshot = AssistantRuntimeSnapshot(
        phase=AssistantRuntimePhase.READY,
        initialized=True,
        backend_mode="local",
        model_id="test-model",
        activation_id=17,
    )

    ctrl._on_runtime_snapshot_changed(snapshot)

    assert ctrl.runtime_snapshot() is snapshot
    ctrl.runtime_state_changed.emit.assert_called_once_with(snapshot)


def test_runtime_snapshot_rejects_untyped_payload_without_losing_truth(ctrl):
    previous = ctrl.runtime_snapshot()

    ctrl._on_runtime_snapshot_changed(object())

    assert ctrl.runtime_snapshot() is previous
    ctrl.runtime_state_changed.emit.assert_not_called()


# --- handle_user_input ---
class TestHandleUserInput:
    def test_ignores_empty(self, ctrl):
        with pytest.raises(ValueError, match="must not be empty"):
            AssistantTurnRequest.single_action(
                correlation=AssistantTurnCorrelation(generation=1, turn_id=1),
                text="   ",
            )
        assert not ctrl.is_processing

    def test_ignores_when_busy(self, ctrl):
        ctrl.is_processing = True
        ctrl._visible_response_sent = False
        correlation = _submit_user_turn(ctrl, "hi")
        assert len(ctrl.history) == 0
        ctrl.turn_finished.emit.assert_called_once_with(
            AssistantTurnTerminal(
                correlation=correlation,
                outcome="rejected_busy",
            )
        )
        ctrl.response_presentation_ready.emit.assert_not_called()
        assert ctrl._visible_response_sent is False

    def test_normal_flow(self, ctrl):
        lifecycle = _use_rag_probe(ctrl)
        ctrl._generate_response = MagicMock()
        _submit_user_turn(ctrl, "do something")
        assert ctrl.is_processing
        assert len(ctrl.history) == 1
        assert lifecycle.requests == [(ctrl._active_rag_turn_id, "do something")]
        ctrl._generate_response.assert_not_called()

        lifecycle.complete()

        ctrl._generate_response.assert_called_once()

    def test_rag_error_continues_generation_without_user_visible_exception(self, ctrl):
        lifecycle = _use_rag_probe(ctrl)
        ctrl._generate_response = MagicMock()
        _submit_user_turn(ctrl, "run analysis")
        lifecycle.complete(error="Qdrant connection refused")

        ctrl._generate_response.assert_called_once()
        ctrl.error_occurred.emit.assert_not_called()
        assert all(
            "Qdrant connection refused" not in call.args[0]
            for call in ctrl.assembler.add_context.call_args_list
        )
        assert ctrl.is_processing

    def test_keeps_intent_authorization_out_of_persistent_rag_context(self, ctrl):
        lifecycle = _use_rag_probe(ctrl)
        ctrl._generate_response = MagicMock()
        _submit_user_turn(ctrl, "Preview the interpretation.")
        lifecycle.complete(features="RAG info")
        added = [call.args[0] for call in ctrl.assembler.add_context.call_args_list]
        assert "RAG info" in added
        assert not any("Latest user intent inferred" in item for item in added)

    def test_rag_completion_rechecks_admission_and_discards_stale_examples(
        self,
        ctrl,
    ):
        lifecycle = _use_rag_probe(ctrl)
        ctrl._generate_response = MagicMock()
        ctrl._request_admission.evaluate = MagicMock(
            side_effect=[
                UserRequestAdmission(
                    UserRequestAdmissionAction.GENERATE,
                    command=CommandName.SCAN_SOURCE,
                ),
                UserRequestAdmission(
                    UserRequestAdmissionAction.GENERATE,
                    command=CommandName.PREVIEW_INTERPRETATION,
                ),
            ]
        )
        first_publication = MagicMock(generation=11)
        current_publication = MagicMock(generation=12)

        with patch(
            "XBrainLab.llm.agent.controller.get_application_service"
        ) as get_service:
            get_service.return_value.get_view_publication.side_effect = [
                first_publication,
                current_publication,
            ]
            _submit_user_turn(ctrl, "Continue the workflow.")
            lifecycle.complete(features="stale scan_source example")

        assert ctrl._request_admission.evaluate.call_args_list == [
            call(
                "Continue the workflow.",
                first_publication,
                scope=AssistantTurnScope.SINGLE_ACTION,
                terminal_command=None,
            ),
            call(
                "Continue the workflow.",
                current_publication,
                scope=AssistantTurnScope.SINGLE_ACTION,
                terminal_command=None,
            ),
        ]
        assert ctrl.assembler.set_turn_authorized_command.call_args_list == [
            call(CommandName.SCAN_SOURCE.value),
            call(CommandName.PREVIEW_INTERPRETATION.value),
        ]
        assert all(
            item.args[0] != "stale scan_source example"
            for item in ctrl.assembler.add_context.call_args_list
        )
        ctrl._generate_response.assert_called_once_with()

    def test_general_no_tool_question_is_answered_by_local_model(self, ctrl):
        lifecycle = _use_rag_probe(ctrl)
        ctrl._generate_response = MagicMock()

        _submit_user_turn(ctrl, "什麼是 epoch?")

        ctrl._generate_response.assert_not_called()
        lifecycle.complete()
        ctrl._generate_response.assert_called_once()
        assert ctrl.is_processing

    def test_state_dependent_training_explanation_uses_publication_shortcut(
        self,
        ctrl,
    ):
        ctrl._generate_response = MagicMock()
        state = ApplicationStateSnapshot.empty()
        publication = ApplicationViewPublication(
            generation=11,
            state=state,
            capabilities=CapabilityPolicy(
                {
                    CommandName.TRAIN.value: CommandCapability(
                        command_name=CommandName.TRAIN.value,
                        enabled=False,
                        reasons=["Generate datasets before training."],
                    )
                }
            ),
        )
        ctrl._product_turn_policy = ProductTurnPolicy(
            ctrl.study,
            publication_reader=lambda: publication,
        )

        _submit_user_turn(ctrl, "Why can't I train?")

        ctrl._generate_response.assert_not_called()
        presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
        assert (
            presentation.text
            == "Training is not ready yet: Generate datasets before training."
        )
        assert ctrl.history == [
            {"role": "user", "content": "Why can't I train?"},
            {"role": "assistant", "content": presentation.text},
        ]
        assert not ctrl.is_processing

    def test_clarification_shortcut_emits_typed_contextual_actions(self, ctrl):
        ctrl._generate_response = MagicMock()

        _submit_user_turn(ctrl, "幫我處理資料")

        ctrl._generate_response.assert_not_called()
        presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
        assert isinstance(presentation, AssistantResponsePresentation)
        assert presentation.kind is AssistantResponseKind.CLARIFICATION
        assert presentation.text == (
            "Tell me which step you want to do next: import data, preview labels "
            "and metadata, preprocess, create epochs, build a dataset, train, "
            "evaluate, or inspect saliency."
        )
        assert [action.label for action in presentation.actions] == [
            "Check workflow",
            "Open Dataset",
        ]
        assert presentation.actions[1].panel is AssistantPanelTarget.DATASET

    def test_blocked_training_attempt_offers_existing_training_panel(self, ctrl):
        ctrl._finalize_turn_after_tool = MagicMock()
        result = ToolCommandResult.failure(
            "start_training",
            "Training settings are incomplete.",
            error_type="precondition",
            recoverable=True,
        )

        ctrl._handle_tool_attempt_blocked("start_training", result)

        presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
        assert isinstance(presentation, AssistantResponsePresentation)
        assert presentation.kind is AssistantResponseKind.BLOCKED
        assert len(presentation.actions) == 1
        assert presentation.actions[0].panel is AssistantPanelTarget.TRAINING
        ctrl._finalize_turn_after_tool.assert_called_once_with()

    def test_training_explanation_fails_closed_when_state_cannot_be_read(
        self,
        ctrl,
        caplog,
    ):
        def unavailable() -> ApplicationViewPublication:
            raise RuntimeError("publication unavailable")

        ctrl._product_turn_policy = ProductTurnPolicy(
            ctrl.study,
            publication_reader=unavailable,
        )
        ctrl._generate_response = MagicMock()

        _submit_user_turn(ctrl, "Why can't I train?")

        ctrl._generate_response.assert_not_called()
        presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
        assert "could not verify" in presentation.text.lower()
        assert "no training action was started" in presentation.text.lower()
        assert "training can run only" not in presentation.text.lower()
        assert "publication unavailable" in caplog.text

    def test_new_user_turn_clears_previous_tool_loop_history(self, ctrl):
        lifecycle = _use_rag_probe(ctrl)
        ctrl._generate_response = MagicMock()
        ctrl._tool_attempt_coordinator.reset_turn = MagicMock()

        _submit_user_turn(ctrl, "show current state")

        ctrl._tool_attempt_coordinator.reset_turn.assert_called_once_with()
        ctrl._generate_response.assert_not_called()
        lifecycle.complete()
        ctrl._generate_response.assert_called_once()

    def test_stop_while_waiting_for_rag_ignores_stale_result(self, ctrl):
        lifecycle = _use_rag_probe(ctrl)
        ctrl._generate_response = MagicMock()

        _submit_user_turn(ctrl, "load data")
        ctrl.stop_generation()
        lifecycle.complete(features="stale RAG")

        ctrl._generate_response.assert_not_called()
        ctrl.assembler.add_context.assert_not_called()
        assert not ctrl.is_processing

    def test_close_while_waiting_for_rag_ignores_stale_result(self, ctrl):
        lifecycle = _use_rag_probe(ctrl)
        ctrl._generate_response = MagicMock()
        ctrl.worker_thread.isRunning.return_value = False

        _submit_user_turn(ctrl, "load data")
        ctrl.close()
        lifecycle.complete(features="stale RAG")

        ctrl._generate_response.assert_not_called()
        ctrl.assembler.add_context.assert_not_called()


def test_handle_user_input_does_not_block_qt_event_loop_during_rag(qtbot):
    from PyQt6.QtCore import QEventLoop, QTimer

    rag = _BlockingRAGRetriever()
    ctrl = _make_real_signal_controller(rag)
    ctrl._generate_response = MagicMock()

    _submit_user_turn(ctrl, "do something")

    assert rag.started.wait(timeout=2)
    assert not rag.release.is_set()
    assert ctrl._rag_lifecycle.is_retrieving
    assert ctrl._rag_lifecycle.retrieval_thread_daemon is True
    ctrl._generate_response.assert_not_called()

    processed = []
    loop = QEventLoop()
    QTimer.singleShot(0, lambda: processed.append(True))
    QTimer.singleShot(0, loop.quit)
    loop.exec()
    assert processed == [True]

    rag.release.set()
    qtbot.waitUntil(lambda: ctrl._generate_response.call_count == 1, timeout=2_000)
    ctrl._generate_response.assert_called_once()


# --- _on_chunk_received ---
class TestOnChunkReceived:
    def test_ignores_empty_stream_chunk(self, ctrl):
        ctrl.is_processing = True
        ctrl._active_generation_id = 1
        turn = ctrl.metrics.start_turn()

        ctrl._on_chunk_received(1, "")

        assert ctrl.current_response == ""
        ctrl.generation_event.emit.assert_not_called()
        assert turn.output_chars == 0

    def test_buffers_short_response(self, ctrl):
        ctrl.is_processing = True
        ctrl._active_generation_id = 1
        ctrl._on_chunk_received(1, "hi")
        assert ctrl.current_response == "hi"
        ctrl.generation_event.emit.assert_called_once_with(
            AssistantGenerationEvent(
                generation_id=1,
                phase=AssistantGenerationEventPhase.CHUNK,
                text="hi",
            )
        )

    def test_buffers_non_tool_until_generation_is_classified(self, ctrl):
        ctrl.is_processing = True
        ctrl._active_generation_id = 2
        ctrl.current_response = "a" * 10
        ctrl._on_chunk_received(2, " more text")
        ctrl.response_presentation_ready.emit.assert_not_called()
        ctrl.generation_event.emit.assert_called_once_with(
            AssistantGenerationEvent(
                generation_id=2,
                phase=AssistantGenerationEventPhase.CHUNK,
                text=" more text",
            )
        )

    def test_buffers_tool_json(self, ctrl):
        ctrl.is_processing = True
        ctrl._active_generation_id = 3
        ctrl.current_response = '{"tool": "x"'
        ctrl._on_chunk_received(3, "}")
        assert ctrl.current_response == '{"tool": "x"}'
        ctrl.generation_event.emit.assert_called_once_with(
            AssistantGenerationEvent(
                generation_id=3,
                phase=AssistantGenerationEventPhase.CHUNK,
                text="}",
            )
        )

    def test_prose_prefix_and_cross_chunk_tool_json_never_stream_raw_trace(self, ctrl):
        ctrl.is_processing = True
        ctrl._active_generation_id = 4
        ctrl._on_chunk_received(4, "Sure, I will do that.\n")
        ctrl._on_chunk_received(4, '{"tool_name":"query_')
        ctrl._on_chunk_received(4, 'state","parameters":{}}')

        ctrl.response_presentation_ready.emit.assert_not_called()
        events = [
            signal_call.args[0]
            for signal_call in ctrl.generation_event.emit.call_args_list
        ]
        assert events == [
            AssistantGenerationEvent(
                generation_id=4,
                phase=AssistantGenerationEventPhase.CHUNK,
                text="Sure, I will do that.\n",
            ),
            AssistantGenerationEvent(
                generation_id=4,
                phase=AssistantGenerationEventPhase.CHUNK,
                text='{"tool_name":"query_',
            ),
            AssistantGenerationEvent(
                generation_id=4,
                phase=AssistantGenerationEventPhase.CHUNK,
                text='state","parameters":{}}',
            ),
        ]

    def test_ignores_chunk_from_stale_generation(self, ctrl):
        ctrl.is_processing = True
        ctrl._active_generation_id = 6

        ctrl._on_chunk_received(5, "stale")

        assert ctrl.current_response == ""
        assert ctrl._active_generation_id == 6
        ctrl.generation_event.emit.assert_not_called()


# --- _on_generation_finished ---
class TestOnGenerationFinished:
    def test_no_command_finalizes(self, ctrl):
        ctrl.current_response = "Just a regular reply, nothing special"
        ctrl._active_response_contract = AssistantResponseContract.NATURAL_LANGUAGE
        ctrl.is_processing = True
        ctrl._active_generation_id = 10
        ctrl._on_generation_finished(10, [])
        assert not ctrl.is_processing
        ctrl.generation_event.emit.assert_called_once_with(
            AssistantGenerationEvent(
                generation_id=10,
                phase=AssistantGenerationEventPhase.FINISHED,
            )
        )
        presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
        assert isinstance(presentation, AssistantResponsePresentation)
        assert presentation.kind is AssistantResponseKind.MESSAGE
        assert presentation.text == "Just a regular reply, nothing special"

    def test_no_tool_text_is_published_as_opaque_typed_copy(self, ctrl):
        response_text = "Request: review the current EEG workflow."
        ctrl.current_response = response_text
        ctrl._active_response_contract = AssistantResponseContract.NATURAL_LANGUAGE
        ctrl.is_processing = True
        ctrl._active_generation_id = 11

        ctrl._on_generation_finished(11, [])

        presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
        assert presentation.text == response_text

    def test_structured_no_tool_decision_publishes_only_user_message(self, ctrl):
        ctrl.current_response = (
            '{"tool_name":"respond_to_user","parameters":{'
            '"decision":"blocked",'
            '"message":"Load EEG data before training."}}'
        )
        ctrl.is_processing = True
        ctrl._active_generation_id = 12

        ctrl._on_generation_finished(12, [])

        presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
        assert presentation.text == "Load EEG data before training."
        assert "decision" not in presentation.text
        assert not ctrl.is_processing

    @pytest.mark.parametrize(
        "response_text",
        (
            "Request: review the current EEG workflow.",
            "[{'note': 'Visible explanatory copy.'}]",
            '```json\n{"note": "Visible explanatory copy."}\n```',
        ),
    )
    def test_typed_copy_preserves_internal_looking_prefixes(
        self,
        ctrl,
        response_text,
    ):
        ctrl._publish_response(response_text)

        presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
        assert presentation.text == response_text
        ctrl.response_presentation_ready.emit.assert_called_once()

    def test_empty_response_emits_visible_error(self, ctrl):
        ctrl.current_response = "   "
        ctrl.is_processing = True
        ctrl._active_generation_id = 13
        ctrl._on_generation_finished(13, [])
        ctrl.error_occurred.emit.assert_called_once()
        assert "empty response" in ctrl.error_occurred.emit.call_args[0][0]
        ctrl.processing_finished.emit.assert_called()

    def test_broken_json_retries(self, ctrl):
        from XBrainLab.llm.agent.parser import CommandParser
        from XBrainLab.llm.agent.strict_envelope_recovery import (
            StrictEnvelopeRecoveryRequest,
        )

        ctrl.current_response = '```json\n{"broken'
        ctrl._retry_count = 0
        ctrl.is_processing = True
        ctrl._active_generation_id = 14
        ctrl._generate_response = MagicMock()
        envelope = CommandParser.parse_product(ctrl.current_response)
        expected = ctrl._strict_envelope_recovery_policy.decide(
            StrictEnvelopeRecoveryRequest(
                envelope=envelope,
                recovery_attempts_used=0,
            )
        )
        ctrl._on_generation_finished(14, [])
        ctrl._generate_response.assert_called_once()
        assert ctrl._retry_count == 1
        assert expected.message is not None
        ctrl.assembler.add_context.assert_called_once_with(expected.message.content)

    def test_prose_prefixed_broken_tool_marker_retries_without_streaming(self, ctrl):
        ctrl.current_response = 'Sure, I will check.\n{"tool_name":'
        ctrl._retry_count = 0
        ctrl.is_processing = True
        ctrl._active_generation_id = 15
        ctrl._generate_response = MagicMock()

        ctrl._on_generation_finished(15, [])

        ctrl.response_presentation_ready.emit.assert_not_called()
        ctrl._generate_response.assert_called_once()

    def test_retry_exhausted_broken_tool_marker_finishes_without_raw_trace(
        self,
        ctrl,
    ):
        ctrl.current_response = 'Sure, I will check.\n{"tool_name":'
        ctrl._retry_count = ctrl._strict_envelope_recovery_policy.max_recovery_attempts
        ctrl.is_processing = True
        ctrl._active_generation_id = 16

        ctrl._on_generation_finished(16, [])

        visible = ctrl.response_presentation_ready.emit.call_args.args[0].text
        assert "valid assistant action" in visible
        assert "tool_name" not in visible
        assert ctrl.is_processing is False

    def test_malformed_generations_stop_at_bounded_retry_limit_without_execution(
        self,
        ctrl,
    ):
        malformed = '```json\n{"tool_name":"query_state","parameters":{}}\n```'
        ctrl._generate_response = MagicMock()
        ctrl._process_tool_calls = MagicMock()
        ctrl.is_processing = True

        retry_limit = ctrl._strict_envelope_recovery_policy.max_recovery_attempts
        for attempt_index in range(retry_limit + 1):
            generation_id = 20 + attempt_index
            ctrl._active_generation_id = generation_id
            ctrl.current_response = malformed
            ctrl._on_generation_finished(generation_id, [])
            if attempt_index < retry_limit:
                assert ctrl.is_processing is True

        assert ctrl._generate_response.call_count == retry_limit
        assert ctrl.assembler.add_context.call_count == retry_limit
        ctrl._process_tool_calls.assert_not_called()

    def test_prose_prefixed_tool_response_is_rejected_without_execution(self, ctrl):
        ctrl.current_response = (
            "Sure, I will check that.\n"
            '{"tool_name":"query_state","parameters":{"query":"state"}}'
        )
        ctrl.is_processing = True
        ctrl._active_generation_id = 30
        ctrl._generate_response = MagicMock()
        ctrl._process_tool_calls = MagicMock()

        ctrl._on_generation_finished(30, [])

        ctrl.response_presentation_ready.emit.assert_not_called()
        ctrl._process_tool_calls.assert_not_called()
        ctrl._generate_response.assert_called_once()

    @pytest.mark.parametrize(
        "response",
        [
            '```json\n{"tool_name":"query_state","parameters":{}}\n```',
            "query_state\nBlocked reasons: None.",
            '{"tool_name":"query_state","parameters":',
            '{"command":"query_state","parameters":{}}',
            '[{"tool_name":"query_state","parameters":{}}]',
        ],
    )
    def test_non_contract_tool_output_never_reaches_execution(self, ctrl, response):
        ctrl.current_response = response
        ctrl.is_processing = True
        ctrl._active_generation_id = 31
        ctrl._generate_response = MagicMock()
        ctrl._process_tool_calls = MagicMock()

        ctrl._on_generation_finished(31, [])

        ctrl._process_tool_calls.assert_not_called()
        ctrl._generate_response.assert_called_once()

    def test_ignores_finish_from_stale_generation(self, ctrl):
        ctrl.current_response = "active response"
        ctrl.is_processing = True
        ctrl._active_generation_id = 41

        ctrl._on_generation_finished(40, [])

        assert ctrl.current_response == "active response"
        assert ctrl._active_generation_id == 41
        assert ctrl.is_processing is True
        ctrl.generation_event.emit.assert_not_called()
        ctrl.response_presentation_ready.emit.assert_not_called()


class TestGenerationErrors:
    def test_active_generation_publishes_correlated_typed_error(self, ctrl):
        ctrl.is_processing = True
        ctrl._active_generation_id = 51

        ctrl._on_generation_error(51, "generation failed")

        ctrl.generation_event.emit.assert_called_once_with(
            AssistantGenerationEvent(
                generation_id=51,
                phase=AssistantGenerationEventPhase.ERROR,
                text="generation failed",
            )
        )
        assert ctrl._active_generation_id is None
        presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
        assert presentation.kind is AssistantResponseKind.ERROR
        assert "could not complete the request" in presentation.text
        assert "generation failed" not in presentation.text
        activity = ctrl.activity_changed.emit.call_args.args[0]
        assert activity.attention_kind is AssistantAttentionKind.ERROR

    def test_stale_generation_error_is_ignored(self, ctrl):
        ctrl.is_processing = True
        ctrl._active_generation_id = 53

        ctrl._on_generation_error(52, "stale failure")

        assert ctrl._active_generation_id == 53
        assert ctrl.is_processing is True
        ctrl.generation_event.emit.assert_not_called()
        ctrl.error_occurred.emit.assert_not_called()
        ctrl.response_presentation_ready.emit.assert_not_called()


class TestRuntimeErrors:
    def test_startup_error_uses_runtime_state_without_chat_copy(self, ctrl):
        ctrl.is_processing = False
        ctrl._active_generation_id = None

        ctrl._on_runtime_error("model load failed")

        ctrl.response_presentation_ready.emit.assert_not_called()
        ctrl.error_occurred.emit.assert_called_once_with("model load failed")
        assert ctrl.is_processing is False
        ctrl.processing_finished.emit.assert_called_once()

    def test_runtime_error_does_not_steal_active_generation(self, ctrl):
        ctrl.is_processing = True
        ctrl._active_generation_id = 54

        ctrl._on_runtime_error("uncorrelated failure")

        assert ctrl._active_generation_id == 54
        assert ctrl.is_processing is True
        ctrl.generation_event.emit.assert_not_called()
        ctrl.error_occurred.emit.assert_not_called()
        ctrl.processing_finished.emit.assert_not_called()


# --- _handle_loop_detected ---
class TestHandleLoopDetected:
    def test_increments_break_count(self, ctrl):
        ctrl._generate_response = MagicMock()
        ctrl._handle_loop_detected("test_tool")
        assert ctrl._loop_break_count == 1
        ctrl._generate_response.assert_called_once()

    def test_aborts_after_max(self, ctrl):
        ctrl._loop_break_count = 3
        ctrl._handle_loop_detected("test_tool")

        presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
        assert presentation.kind is AssistantResponseKind.BLOCKED
        assert "repeated the same action" in presentation.text
        assert [action.label for action in presentation.actions] == ["Check workflow"]
        assert not ctrl.is_processing
        ctrl.processing_finished.emit.assert_called_once()


# --- _execute_tool_no_loop ---
class TestExecuteToolNoLoop:
    def test_unknown_tool(self, ctrl):
        ctrl.registry.get_tool.return_value = None
        outcome = ctrl._execute_tool_no_loop("bogus", {})
        assert not outcome.success
        assert "unavailable" in outcome.result.message

    def test_success(self, ctrl):
        mock_tool = MagicMock()
        mock_tool.execute.return_value = ToolResult(True, "ok")
        ctrl.registry.get_tool.return_value = mock_tool
        _allow_prompt_tools(ctrl)
        outcome = ctrl._execute_tool_no_loop("list_files", {"path": "/tmp"})
        assert outcome.success
        assert outcome.result.message == "ok"

    def test_exception(self, ctrl):
        mock_tool = MagicMock()
        mock_tool.execute.side_effect = RuntimeError("fail")
        ctrl.registry.get_tool.return_value = mock_tool
        _allow_prompt_tools(ctrl)
        outcome = ctrl._execute_tool_no_loop("list_files", {"path": "/tmp"})
        assert not outcome.success
        assert outcome.result.raw_result is None
        assert outcome.result.error_code == "unexpected_tool_failure"
        assert outcome.result.diagnostics["incident_id"]


# --- _handle_tool_result_logic ---
class TestHandleToolResultLogic:
    def test_switch_panel(self, ctrl):
        result = ctrl._handle_tool_result_logic(
            UiRequest(
                UiRequestKind.SWITCH_PANEL,
                {"panel": "visualization", "view_mode": "3d_plot"},
            )
        )
        assert result
        request = ctrl.panel_navigation_requested.emit.call_args.args[0]
        assert request == AssistantPanelNavigationRequest(
            target=AssistantPanelTarget.VISUALIZATION,
            view_mode="3d_plot",
        )

    @pytest.mark.parametrize(
        "params",
        [
            {"panel": "dashboard"},
            {"panel": "training", "view_mode": "metrics"},
        ],
    )
    def test_switch_panel_rejects_unavailable_product_surface(self, ctrl, params):
        result = ctrl._handle_tool_result_logic(
            UiRequest(UiRequestKind.SWITCH_PANEL, params)
        )

        assert result is False
        ctrl.panel_navigation_requested.emit.assert_not_called()
        presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
        assert presentation.kind is AssistantResponseKind.BLOCKED
        assert "not available" in presentation.text

    def test_confirm_montage(self, ctrl):
        result = ctrl._handle_tool_result_logic(
            UiRequest(
                UiRequestKind.CONFIRM_MONTAGE,
                {
                    "montage_name": "standard_1020",
                    "warning": "Review channel identities.",
                },
            )
        )
        assert result
        request = ctrl.workflow_ui_handoff_requested.emit.call_args.args[0]
        assert request.command is CommandName.APPLY_MONTAGE
        assert request.suggestions == {
            "montage_name": "standard_1020",
            "warning": "Review channel identities.",
        }
        assert ctrl.pending_interactions.workflow_handoff is request
        ctrl.panel_navigation_requested.emit.assert_not_called()

    def test_failure_waits_for_host_retry_policy_before_becoming_visible(self, ctrl):
        result = ctrl._handle_tool_result_logic(
            ToolCommandResult.failure("test", "some error"),
            success=False,
        )
        assert not result
        ctrl.response_presentation_ready.emit.assert_not_called()

    def test_finalize_after_tool_emits_visible_summary(self, ctrl):
        ctrl._visible_response_sent = False
        ctrl._last_tool_summary = "Dataset summary is ready."
        ctrl._finalize_turn_after_tool()
        presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
        assert presentation.text == "Dataset summary is ready."
        ctrl.processing_finished.emit.assert_called()

    def test_finalize_after_failed_tool_uses_blocked_presentation(self, ctrl):
        ctrl._visible_response_sent = False
        ctrl._last_tool_summary = "The requested command could not run."
        ctrl._last_tool_summary_kind = AssistantResponseKind.BLOCKED

        ctrl._finalize_turn_after_tool()

        presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
        assert presentation.kind is AssistantResponseKind.BLOCKED


# --- _process_tool_calls ---
class TestProcessToolCalls:
    def test_ask_executes_only_first_command_from_model_batch(self, ctrl):
        context = _enabled_tool_context("first", generation=11)
        context_reader = _set_context_reader(ctrl, return_value=context)
        ctrl._execute_tool_no_loop = MagicMock(return_value=_tool_outcome("ok"))
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        ctrl._finalize_turn_after_tool = MagicMock()
        ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
        ctrl.registry.get_tool.return_value.requires_confirmation = False

        ctrl._process_tool_calls(
            [("first", {}), ("second", {})],
            '{"tool_calls": ["first", "second"]}',
        )

        ctrl._execute_tool_no_loop.assert_called_once_with(
            "first",
            {},
            context=context,
        )
        context_reader.assert_called_once_with("first")

    def test_ui_request_stops_before_workflow_continuation(self, ctrl):
        _allow_prompt_tools(ctrl)
        _set_guided_turn_scope(ctrl)
        ctrl._execute_tool_no_loop = MagicMock(
            return_value=ToolExecutionOutcome(
                True,
                UiRequest(
                    UiRequestKind.CONFIRM_MONTAGE,
                    {"montage_name": "standard_1020"},
                ),
            )
        )
        ctrl._finalize_turn_after_tool = MagicMock()
        ctrl._handle_tool_success = MagicMock()
        ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
        ctrl.registry.get_tool.return_value.requires_confirmation = False

        ctrl._process_tool_calls(
            [("set_montage", {"montage_name": "standard_1020"})],
            '{"tool_name": "set_montage"}',
        )

        ctrl._finalize_turn_after_tool.assert_not_called()
        ctrl._handle_tool_success.assert_not_called()
        assert ctrl.pending_interactions.workflow_handoff is not None
        assert (
            ctrl.pending_interactions.workflow_handoff.command
            is CommandName.APPLY_MONTAGE
        )

    def test_workflow_executes_one_command_then_rereads_policy(self, ctrl):
        from XBrainLab.llm.agent.execution_policy import ExecutionSnapshot

        context = _enabled_tool_context("first", generation=12)
        context_reader = _set_context_reader(ctrl, return_value=context)
        _set_guided_turn_scope(ctrl)
        ctrl._execute_tool_no_loop = MagicMock(return_value=_tool_outcome("ok"))
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        ctrl._finalize_turn_after_tool = MagicMock()
        ctrl._generate_response = MagicMock()
        ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
        ctrl.registry.get_tool.return_value.requires_confirmation = False
        ctrl._refresh_execution_snapshot = MagicMock(
            return_value=ExecutionSnapshot(
                state_reliable=True,
                decision_needed=(),
                can_auto_continue=True,
                recommended_next_step="second",
            )
        )

        ctrl._process_tool_calls(
            [("first", {}), ("discarded", {})],
            '{"tool_calls": ["first", "discarded"]}',
        )

        ctrl._execute_tool_no_loop.assert_called_once_with(
            "first",
            {},
            context=context,
        )
        context_reader.assert_called_once_with("first")
        ctrl._refresh_execution_snapshot.assert_called_once()
        ctrl.assembler.set_turn_authorized_command.assert_called_with(
            "second",
            continuation=True,
        )
        ctrl._generate_response.assert_called_once()

    def test_recoverable_failure_is_published_to_next_model_generation(self, ctrl):
        from XBrainLab.llm.agent.tool_feedback import ToolRecoveryFeedback

        _allow_prompt_tools(ctrl)
        _set_guided_turn_scope(ctrl)
        failure = ToolCommandResult.failure(
            "cmd",
            "Temporary runtime failure",
            state=ApplicationStateSnapshot.empty().to_dict(),
            error_type="runtime",
            recoverable=True,
        )
        ctrl._execute_tool_no_loop = MagicMock(
            return_value=ToolExecutionOutcome(False, failure)
        )
        ctrl._generate_response = MagicMock()
        ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
        ctrl.registry.get_tool.return_value.requires_confirmation = False

        ctrl._process_tool_calls([("cmd", {})], '{"tool_name":"cmd"}')

        feedback = ctrl.assembler.set_recovery_feedback.call_args.args[0]
        assert isinstance(feedback, ToolRecoveryFeedback)
        assert feedback.tool_name == "cmd"
        assert feedback.message == "Temporary runtime failure"
        ctrl.response_presentation_ready.emit.assert_not_called()
        ctrl._generate_response.assert_called_once()

    def test_refresh_reads_state_capabilities_and_decision_context(self, ctrl):
        from types import SimpleNamespace

        service = MagicMock()
        state = ApplicationStateSnapshot.empty()
        next_capability = SimpleNamespace(
            requires_confirmation=False,
            confirmation_required=False,
            decision_boundary=None,
            long_running=False,
            destructive=False,
            continue_allowed_after_success=True,
            stop_after_success=False,
        )
        capabilities = MagicMock()
        capabilities.get.return_value = next_capability
        publication = ApplicationViewPublication(
            generation=9,
            state=state,
            capabilities=capabilities,
        )
        service.get_view_publication.return_value = publication
        context = SimpleNamespace(
            recommended_next_step="preview_interpretation",
            decision_needed=[],
            can_auto_continue=True,
        )

        with (
            patch(
                "XBrainLab.llm.agent.controller.get_application_service",
                return_value=service,
            ),
            patch(
                "XBrainLab.llm.agent.controller.build_workflow_decision_context",
                return_value=context,
            ) as build_context,
        ):
            snapshot = ctrl._refresh_execution_snapshot()

        service.get_view_publication.assert_called_once_with()
        service.get_state.assert_not_called()
        service.get_capabilities.assert_not_called()
        build_context.assert_called_once_with(
            ctrl.study,
            latest_user_text=ctrl._latest_user_request_text(),
            mode=ctrl._active_policy_mode(),
            publication=publication,
        )
        assert snapshot.state_reliable is True
        assert snapshot.can_auto_continue is True

    def test_refresh_failure_is_unreliable_and_fail_closed(self, ctrl):
        with patch(
            "XBrainLab.llm.agent.controller.get_application_service",
            side_effect=RuntimeError("state read failed"),
        ):
            snapshot = ctrl._refresh_execution_snapshot()

        assert snapshot.state_reliable is False
        assert snapshot.can_auto_continue is False
        assert snapshot.read_error == SAFE_UNEXPECTED_FAILURE_MESSAGE
        assert "state read failed" not in snapshot.read_error

    def test_nonrecoverable_tool_failure_never_enters_agent_retry_loop(self, ctrl):
        result = ToolCommandResult(
            ok=False,
            tool_name="configure_training",
            command_name="configure_training",
            message="Updated state could not be verified.",
            error_type="internal",
            recoverable=False,
            state={"state_reliable": False},
        )

        assert ctrl._should_wait_for_user_after_tool_failure(result) is True

    def test_refresh_rejects_untyped_read_diagnostics_without_state_contract(
        self,
        ctrl,
    ):
        from types import SimpleNamespace

        service = MagicMock()
        service.get_view_publication.return_value = ApplicationViewPublication(
            generation=10,
            state=cast(Any, SimpleNamespace(read_errors=[])),
            capabilities=MagicMock(),
        )
        context = SimpleNamespace(
            recommended_next_step=None,
            decision_needed=[],
            can_auto_continue=True,
        )
        with (
            patch(
                "XBrainLab.llm.agent.controller.get_application_service",
                return_value=service,
            ),
            patch(
                "XBrainLab.llm.agent.controller.build_workflow_decision_context",
                return_value=context,
            ),
        ):
            snapshot = ctrl._refresh_execution_snapshot()

        assert snapshot.state_reliable is False

    def test_refresh_typed_read_errors_make_state_unreliable(
        self,
        ctrl,
    ):
        from types import SimpleNamespace

        service = MagicMock()
        service.get_view_publication.return_value = ApplicationViewPublication(
            generation=11,
            state=ApplicationStateSnapshot.empty(
                read_errors=["training state read failed"]
            ),
            capabilities=MagicMock(),
        )
        service.get_capabilities.return_value = MagicMock()
        context = SimpleNamespace(
            recommended_next_step=None,
            decision_needed=[],
            can_auto_continue=True,
        )
        with (
            patch(
                "XBrainLab.llm.agent.controller.get_application_service",
                return_value=service,
            ),
            patch(
                "XBrainLab.llm.agent.controller.build_workflow_decision_context",
                return_value=context,
            ),
        ):
            snapshot = ctrl._refresh_execution_snapshot()

        assert snapshot.state_reliable is False

    def test_workflow_decision_needed_opens_existing_ui_boundary(self, ctrl):
        from XBrainLab.llm.agent.execution_policy import ExecutionSnapshot

        _set_guided_turn_scope(ctrl)
        ctrl._tool_execution_count = 1
        ctrl._refresh_execution_snapshot = MagicMock(
            return_value=ExecutionSnapshot(
                state_reliable=True,
                decision_needed=("epoch_window", "target_event"),
                can_auto_continue=False,
                recommended_next_step="create_epoch",
            )
        )
        ctrl._generate_response = MagicMock()
        ctrl._finalize_turn_after_tool = MagicMock()

        ctrl._handle_tool_success(None, command_name="query_state")

        ctrl.workflow_ui_handoff_requested.emit.assert_called_once()
        emitted_request = ctrl.workflow_ui_handoff_requested.emit.call_args.args[0]
        assert isinstance(emitted_request, WorkflowUiHandoffRequest)
        assert emitted_request.command is CommandName.CREATE_EPOCH
        assert emitted_request.decision_fields == ("epoch_window", "target_event")
        assert emitted_request.request_id
        ctrl.panel_navigation_requested.emit.assert_not_called()
        ctrl._generate_response.assert_not_called()
        assert ctrl.pending_interactions.workflow_handoff is emitted_request
        ctrl._finalize_turn_after_tool.assert_not_called()

    def test_workflow_decision_publishes_concrete_tool_summary_before_handoff(
        self,
        ctrl,
    ):
        from XBrainLab.llm.agent.execution_policy import ExecutionSnapshot

        summary = (
            "Import review needs your input:\n"
            "- Confirm subject metadata for recording.fif.\n"
            "- Confirm which events are class labels.\n"
            "Open Import Review to resolve these choices."
        )
        _set_guided_turn_scope(ctrl)
        ctrl._tool_execution_count = 1
        ctrl._last_tool_summary = summary
        ctrl._last_tool_summary_kind = AssistantResponseKind.TOOL_RESULT
        ctrl._visible_response_sent = False
        ctrl._refresh_execution_snapshot = MagicMock(
            return_value=ExecutionSnapshot(
                state_reliable=True,
                decision_needed=("metadata_review", "label_matching"),
                can_auto_continue=False,
                recommended_next_step="apply_interpretation",
            )
        )

        ctrl._handle_tool_success(None, command_name="validate_interpretation")

        presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
        assert presentation.text == summary
        assert presentation.kind is AssistantResponseKind.TOOL_RESULT
        ctrl.workflow_ui_handoff_requested.emit.assert_called_once()

    def test_import_review_continuation_binds_current_domain_identity(self, ctrl):
        from XBrainLab.llm.agent.execution_policy import ExecutionSnapshot

        _set_guided_turn_scope(ctrl)
        ctrl._tool_execution_count = 1
        publication = MagicMock()
        publication.usable = True
        publication.generation = 61
        publication.state.interpretation.latest_scan_id = "scan-current"
        publication.state.interpretation.latest_candidate_id = "candidate-current"
        ctrl._refresh_execution_snapshot = MagicMock(
            return_value=ExecutionSnapshot(
                state_reliable=True,
                decision_needed=("import_review",),
                can_auto_continue=False,
                recommended_next_step="apply_interpretation",
                publication=publication,
            )
        )

        with patch(
            "XBrainLab.llm.agent.controller.get_application_service"
        ) as get_service:
            ctrl._handle_tool_success(None, command_name="query_state")

        get_service.assert_not_called()
        request = ctrl.workflow_ui_handoff_requested.emit.call_args.args[0]
        assert isinstance(request, WorkflowUiHandoffRequest)
        assert request.interpretation_identity == InterpretationReviewIdentity(
            publication_generation=61,
            scan_id="scan-current",
            candidate_id="candidate-current",
        )

    def test_workflow_decision_without_command_fails_closed(self, ctrl):
        from XBrainLab.llm.agent.execution_policy import ExecutionSnapshot

        _set_guided_turn_scope(ctrl)
        ctrl._refresh_execution_snapshot = MagicMock(
            return_value=ExecutionSnapshot(
                state_reliable=True,
                decision_needed=("epoch_window",),
                can_auto_continue=False,
                recommended_next_step=None,
            )
        )
        ctrl._finalize_turn_after_tool = MagicMock()

        ctrl._handle_tool_success(None, command_name="query_state")

        ctrl.workflow_ui_handoff_requested.emit.assert_not_called()
        ctrl.status_update.emit.assert_any_call(
            "Workflow decision could not be opened."
        )
        ctrl._finalize_turn_after_tool.assert_called_once()

    def test_success_finalizes(self, ctrl):
        _allow_prompt_tools(ctrl)
        ctrl._execute_tool_no_loop = MagicMock(return_value=_tool_outcome("ok"))
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        ctrl._finalize_turn_after_tool = MagicMock()
        ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
        ctrl.registry.get_tool.return_value.requires_confirmation = False

        ctrl._process_tool_calls([("cmd", {"a": 1})], '{"cmd": "cmd"}')
        ctrl._finalize_turn_after_tool.assert_called_once()

    def test_failure_without_reliable_state_finishes_without_retry(self, ctrl):
        _allow_prompt_tools(ctrl)
        _set_guided_turn_scope(ctrl)
        ctrl._execute_tool_no_loop = MagicMock(
            return_value=_tool_outcome("err", ok=False)
        )
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        ctrl._generate_response = MagicMock()
        ctrl._finalize_turn_after_tool = MagicMock()
        ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
        ctrl.registry.get_tool.return_value.requires_confirmation = False

        ctrl._process_tool_calls([("cmd", {})], "json")

        ctrl._generate_response.assert_not_called()
        ctrl.assembler.set_recovery_feedback.assert_not_called()
        ctrl._finalize_turn_after_tool.assert_called_once()

    def test_nonrecoverable_unreliable_failure_finishes_turn_without_retry(
        self,
        ctrl,
    ):
        context = _enabled_tool_context("cmd", generation=13)
        context_reader = _set_context_reader(ctrl, return_value=context)
        failure = ToolCommandResult.failure(
            "cmd",
            "Updated state could not be verified.",
            command_name="train",
            state={"state_reliable": False},
            error_type="internal",
            recoverable=False,
        )
        ctrl._execute_tool_no_loop = MagicMock(
            return_value=ToolExecutionOutcome(False, failure)
        )
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        ctrl._generate_response = MagicMock()
        ctrl._finalize_turn_after_tool = MagicMock()
        ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
        ctrl.registry.get_tool.return_value.requires_confirmation = False
        ctrl._tool_failure_count = 0

        ctrl._process_tool_calls([("cmd", {})], "json")

        ctrl._execute_tool_no_loop.assert_called_once_with(
            "cmd",
            {},
            context=context,
        )
        context_reader.assert_called_once_with("cmd")
        ctrl._generate_response.assert_not_called()
        assert ctrl._tool_failure_count == 0
        ctrl._finalize_turn_after_tool.assert_called_once()

    def test_real_post_state_failure_finishes_turn_after_command_side_effect(
        self,
        ctrl,
    ):
        from XBrainLab.backend.application import get_application_service
        from XBrainLab.backend.study import Study
        from XBrainLab.llm.tools import application_surface

        study = Study()
        service = get_application_service(study)
        real_build = service.state_snapshot.build

        def fail_post_state(*, last_error=None):
            if study.model_holder is not None:
                raise RuntimeError("post-command snapshot unavailable")
            return real_build(last_error=last_error)

        service.state_snapshot.build = MagicMock(side_effect=fail_post_state)
        service.execute = MagicMock(wraps=service.execute)
        ctrl.study = study
        from XBrainLab.llm.agent.tool_attempt_coordinator import (
            ApplicationToolContextSource,
        )

        ctrl._tool_attempt_coordinator._context_source = ApplicationToolContextSource(
            study
        )
        ctrl.registry.get_tool.return_value = MagicMock(
            requires_confirmation=False,
        )
        ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
        ctrl._generate_response = MagicMock()
        ctrl.is_processing = True

        with patch(
            "XBrainLab.llm.agent.tool_execution_coordinator."
            "execute_application_tool_command",
            wraps=application_surface.execute_application_tool_command,
        ) as execute_surface:
            ctrl._process_tool_calls(
                [("set_model", {"model_name": "EEGNet"})],
                '{"tool_name":"set_model","parameters":{"model_name":"EEGNet"}}',
            )

        service.execute.assert_called_once()
        execute_surface.assert_called_once()
        assert service.state_snapshot.build.call_count >= 2
        assert study.model_holder is not None
        ctrl._generate_response.assert_not_called()
        ctrl.processing_finished.emit.assert_called_once_with()
        assert ctrl.is_processing is False
        result = ctrl.application_command_completed.emit.call_args.args[0]
        assert isinstance(result, ToolCommandResult)
        assert result.ok is False
        assert result.recoverable is False
        assert isinstance(result.state, dict)
        assert isinstance(result.raw_result, dict)
        assert result.state["state_reliable"] is False
        assert result.raw_result["changed_state"]["state_unknown"] is True

    def test_max_failures_stops(self, ctrl):
        _allow_prompt_tools(ctrl)
        ctrl._tool_failure_count = 2
        ctrl._execute_tool_no_loop = MagicMock(
            return_value=_tool_outcome("err", ok=False)
        )
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        ctrl._finalize_turn_after_tool = MagicMock()
        ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
        ctrl.registry.get_tool.return_value.requires_confirmation = False

        ctrl._process_tool_calls([("cmd", {})], "json")
        ctrl._finalize_turn_after_tool.assert_called_once()

    def test_verification_rejected(self, ctrl):
        ctrl.verifier.verify_tool_call.return_value = MagicMock(
            is_valid=False, error_message="bad call"
        )
        ctrl._generate_response = MagicMock()
        ctrl._handle_tool_attempt_blocked = MagicMock()
        ctrl._process_tool_calls([("cmd", {})], "json")
        ctrl._handle_tool_attempt_blocked.assert_called_once()
        command_name, result = ctrl._handle_tool_attempt_blocked.call_args.args
        assert command_name == "cmd"
        assert result.message == "bad call"
        assert result.error_type == "input"
        ctrl._generate_response.assert_not_called()

    def test_guided_turn_retries_one_unpublished_model_tool_before_presenting_error(
        self,
        ctrl,
    ):
        from XBrainLab.llm.agent.assembler import PromptToolPublication

        ctrl._active_turn_scope = AssistantTurnScope.GUIDED_WORKFLOW
        ctrl._active_tool_publication = PromptToolPublication(
            tool_names=frozenset({"validate_interpretation"}),
            backend_generation=3,
            recommended_command="validate_interpretation",
            authorized_command="validate_interpretation",
        )
        ctrl._generate_response = MagicMock()
        ctrl._handle_tool_attempt_blocked = MagicMock()
        result = ToolCommandResult.failure(
            "eegdatapreparationtool",
            "This assistant tool was not published for the current model turn.",
            error_type="tool_not_published",
            recoverable=True,
        )

        handled = ctrl._present_tool_attempt_boundary(
            ToolAttemptDecision(
                ToolAttemptAction.PUBLICATION_BLOCKED,
                "eegdatapreparationtool",
                {},
                result=result,
            )
        )

        assert handled is True
        assert ctrl._tool_failure_count == 1
        ctrl.assembler.set_recovery_feedback.assert_called_once()
        feedback = ctrl.assembler.set_recovery_feedback.call_args.args[0]
        assert feedback.guidance == (
            "The only permitted action is validate_interpretation. Return that "
            "exact tool name using its published JSON contract."
        )
        ctrl._generate_response.assert_called_once_with()
        ctrl._handle_tool_attempt_blocked.assert_not_called()

    @pytest.mark.parametrize(
        ("scope", "failure_count"),
        [
            (AssistantTurnScope.SINGLE_ACTION, 0),
            (AssistantTurnScope.GUIDED_WORKFLOW, 1),
        ],
    )
    def test_unpublished_model_tool_is_presented_after_repair_boundary(
        self,
        ctrl,
        scope,
        failure_count,
    ):
        from XBrainLab.llm.agent.assembler import PromptToolPublication

        ctrl._active_turn_scope = scope
        ctrl._tool_failure_count = failure_count
        ctrl._active_tool_publication = PromptToolPublication(
            tool_names=frozenset({"validate_interpretation"}),
            backend_generation=3,
            recommended_command="validate_interpretation",
            authorized_command="validate_interpretation",
        )
        ctrl._generate_response = MagicMock()
        ctrl._handle_tool_attempt_blocked = MagicMock()
        result = ToolCommandResult.failure(
            "eegdatapreparationtool",
            "This assistant tool was not published for the current model turn.",
            error_type="tool_not_published",
            recoverable=True,
        )

        handled = ctrl._present_tool_attempt_boundary(
            ToolAttemptDecision(
                ToolAttemptAction.PUBLICATION_BLOCKED,
                "eegdatapreparationtool",
                {},
                result=result,
            )
        )

        assert handled is True
        ctrl._generate_response.assert_not_called()
        ctrl._handle_tool_attempt_blocked.assert_called_once_with(
            "eegdatapreparationtool",
            result,
            feedback=ToolAttemptFeedback.SYSTEM_REJECTION,
        )

    def test_requested_intent_boundary_rejects_before_verification(self, ctrl):
        from XBrainLab.llm.tools.application_surface import (
            ToolAvailability,
            ToolAvailabilityContext,
        )

        ctrl.history = [{"role": "user", "content": "Train an EEGNet model."}]
        capability = CommandCapability(
            command_name=CommandName.TRAIN.value,
            enabled=False,
            reasons=["Generate datasets before training"],
        )
        policy = MagicMock()
        policy.get.return_value = capability
        _set_context_reader(
            ctrl,
            return_value=ToolAvailabilityContext(
                availability=ToolAvailability(tool_name="set_model", enabled=True),
                state={"pipeline_stage": "empty"},
                generation=4,
                capabilities=policy,
            ),
        )
        ctrl._finalize_turn_after_tool = MagicMock()

        ctrl._process_tool_calls(
            [("set_model", {"model_name": "EEGNet"})],
            '{"tool_name":"set_model","parameters":{"model_name":"EEGNet"}}',
        )

        ctrl.verifier.verify_tool_call.assert_not_called()
        ctrl.response_presentation_ready.emit.assert_called_once()
        presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
        assert isinstance(presentation, AssistantResponsePresentation)
        assert presentation.kind is AssistantResponseKind.BLOCKED
        ctrl._finalize_turn_after_tool.assert_called_once()

    def test_requested_intent_boundary_reads_application_policy(self, ctrl):
        from XBrainLab.llm.tools.application_surface import (
            ToolAvailability,
            ToolAvailabilityContext,
        )

        ctrl.history = [{"role": "user", "content": "Train an EEGNet model now."}]
        capability = CommandCapability(
            command_name=CommandName.TRAIN.value,
            enabled=False,
            reasons=["Generate datasets before training"],
        )
        policy = MagicMock()
        policy.get.return_value = capability

        state_snapshot = {
            "pipeline_stage": "empty",
            "training": {"missing_requirements": ["Data Splitting"]},
        }
        context = ToolAvailabilityContext(
            availability=ToolAvailability(tool_name="set_model", enabled=True),
            state=state_snapshot,
            generation=4,
            capabilities=policy,
        )

        result = _evaluate_policy(ctrl, "set_model", context).result

        result = _assert_intent_boundary_result(
            result,
            tool_name="set_model",
            command_name=CommandName.TRAIN,
            blocked_reason="Generate datasets before training",
            message=(
                "Requested workflow step 'train' is not available: "
                "Generate datasets before training"
            ),
        )
        assert result.capability == capability.to_dict()
        assert result.state == state_snapshot

    def test_requested_intent_boundary_rejects_enabled_substitute_tool(self, ctrl):
        from XBrainLab.llm.tools.application_surface import (
            ToolAvailability,
            ToolAvailabilityContext,
        )

        ctrl.history = [{"role": "user", "content": "Train an EEGNet model now."}]
        capability = CommandCapability(
            command_name=CommandName.TRAIN.value,
            enabled=True,
            reasons=[],
        )
        policy = MagicMock()
        policy.get.return_value = capability
        context = ToolAvailabilityContext(
            availability=ToolAvailability(tool_name="set_model", enabled=True),
            state={"pipeline_stage": "dataset_ready"},
            generation=8,
            capabilities=policy,
        )

        result = _evaluate_policy(ctrl, "set_model", context).result

        assert isinstance(result, ToolCommandResult)
        assert result.ok is False
        assert result.error_type == "intent_mismatch"
        assert result.command_name == CommandName.TRAIN.value
        assert "does not match" in result.message

    def test_unknown_intent_does_not_authorize_mutating_tool(self, ctrl):
        context = _enabled_tool_context("start_training", generation=10)
        ctrl.history = [{"role": "user", "content": "Maybe do something useful."}]

        result = _evaluate_policy(ctrl, "start_training", context).result

        assert isinstance(result, ToolCommandResult)
        assert result.error_type == "intent_mismatch"
        assert "does not authorize" in result.message

    def test_explicit_continue_only_allows_published_recommended_command(self, ctrl):
        from XBrainLab.llm.agent.assembler import PromptToolPublication

        ctrl.history = [{"role": "user", "content": "Continue"}]
        ctrl._active_tool_publication = PromptToolPublication(
            tool_names=frozenset({"apply_standard_preprocess", "set_model"}),
            backend_generation=3,
            recommended_command=CommandName.PREPROCESS.value,
        )

        allowed = _evaluate_policy(
            ctrl,
            "apply_standard_preprocess",
            _enabled_tool_context("apply_standard_preprocess", generation=3),
        ).result
        rejected = _evaluate_policy(
            ctrl,
            "set_model",
            _enabled_tool_context("set_model", generation=3),
        ).result

        assert allowed is None
        assert isinstance(rejected, ToolCommandResult)
        assert rejected.error_type == "intent_mismatch"

    def test_tool_not_published_for_active_generation_fails_closed(self, ctrl):
        from XBrainLab.llm.agent.assembler import PromptToolPublication

        ctrl._active_tool_publication = PromptToolPublication(
            tool_names=frozenset({"query_state"}),
            backend_generation=12,
        )

        result = _evaluate_policy(
            ctrl,
            "load_data",
            _enabled_tool_context("load_data", generation=12),
        ).result

        assert isinstance(result, ToolCommandResult)
        assert result.error_type == "tool_not_published"
        assert result.recoverable is True
        assert result.diagnostics["publication_generation"] == 12

    def test_unpublished_intent_tool_keeps_same_generation_backend_blocker(
        self,
        ctrl,
    ):
        from XBrainLab.llm.agent.assembler import PromptToolPublication

        ctrl._active_tool_publication = PromptToolPublication(
            tool_names=frozenset({"scan_source"}),
            backend_generation=13,
            blocked_reasons=(("train", "Generate datasets before training"),),
        )

        matching = _evaluate_policy(
            ctrl,
            "start_training",
            _enabled_tool_context("start_training", generation=13),
        ).result
        unrelated = _evaluate_policy(
            ctrl,
            "load_data",
            _enabled_tool_context("load_data", generation=13),
        ).result

        assert isinstance(matching, ToolCommandResult)
        assert matching.error_type == "precondition"
        assert matching.blocked_reason == "Generate datasets before training"
        assert isinstance(unrelated, ToolCommandResult)
        assert unrelated.error_type == "tool_not_published"

    def test_model_invented_path_is_rejected_by_turn_provenance(self, ctrl, tmp_path):
        from XBrainLab.llm.tools.application_surface import (
            ToolAvailability,
            ToolAvailabilityContext,
        )

        invented = tmp_path / "not-selected"
        invented.mkdir()
        ctrl.history = [{"role": "user", "content": "Show my EEG files"}]
        context = ToolAvailabilityContext(
            availability=ToolAvailability(tool_name="list_files", enabled=True),
            state={"interpretation": {}},
            generation=14,
        )

        result = _evaluate_policy(
            ctrl,
            "list_files",
            context,
            params={"directory": str(invented)},
        ).result

        assert isinstance(result, ToolCommandResult)
        assert result.error_type == "input"
        assert result.diagnostics["policy"] == "path_provenance"
        assert "Choose a file or folder" in result.message

    def test_requested_intent_boundary_rejects_visualization_ui_substitute(self, ctrl):
        from XBrainLab.llm.tools.application_surface import (
            ToolAvailability,
            ToolAvailabilityContext,
        )

        ctrl.history = [{"role": "user", "content": "Visualize the trained result."}]
        capability = CommandCapability(
            command_name=CommandName.VISUALIZE.value,
            enabled=True,
            reasons=[],
        )
        policy = MagicMock()
        policy.get.return_value = capability

        context = ToolAvailabilityContext(
            availability=ToolAvailability(tool_name="switch_panel", enabled=True),
            state=None,
            generation=5,
            capabilities=policy,
        )
        result = _evaluate_policy(ctrl, "switch_panel", context).result

        result = _assert_intent_boundary_result(
            result,
            tool_name="switch_panel",
            command_name=CommandName.VISUALIZE,
            blocked_reason=(
                "Use an ApplicationService readiness summary before opening "
                "visualization views."
            ),
            message=(
                "Requested workflow step 'visualize' needs a readiness summary: "
                "Use an ApplicationService readiness summary before opening "
                "visualization views."
            ),
        )
        assert result.capability == capability.to_dict()
        assert result.state is None

    def test_requested_intent_boundary_rejects_saliency_setup_substitute(self, ctrl):
        from XBrainLab.llm.tools.application_surface import (
            ToolAvailability,
            ToolAvailabilityContext,
        )

        ctrl.history = [{"role": "user", "content": "Show saliency readiness."}]
        capability = CommandCapability(
            command_name=CommandName.SALIENCY.value,
            enabled=True,
            reasons=[],
        )
        policy = MagicMock()
        policy.get.return_value = capability

        context = ToolAvailabilityContext(
            availability=ToolAvailability(tool_name="set_model", enabled=True),
            state=None,
            generation=6,
            capabilities=policy,
        )
        result = _evaluate_policy(ctrl, "set_model", context).result

        result = _assert_intent_boundary_result(
            result,
            tool_name="set_model",
            command_name=CommandName.SALIENCY,
            blocked_reason=(
                "Use an ApplicationService readiness summary before opening "
                "visualization views."
            ),
            message=(
                "Requested workflow step 'saliency' needs a readiness summary: "
                "Use an ApplicationService readiness summary before opening "
                "visualization views."
            ),
        )
        assert result.capability == capability.to_dict()
        assert result.state is None


# --- close ---
class TestClose:
    def test_constructor_injected_rag_lifecycle_is_the_only_cleanup_owner(self):
        retriever = MagicMock()
        lifecycle = MagicMock(retriever=retriever)
        lifecycle.close.return_value = True
        controller = _make_real_signal_controller(
            MagicMock(),
            rag_lifecycle=lifecycle,
        )
        controller.worker_thread.isRunning.return_value = False

        assert controller.close() is True

        lifecycle.close.assert_called_once_with()
        retriever.close.assert_not_called()

    def test_close_stops_thread(self, ctrl):
        worker = ctrl.worker
        ctrl.worker_thread.isRunning.return_value = True
        ctrl.close()
        worker.shutdown.assert_called_once()
        ctrl.worker_thread.quit.assert_called_once()
        ctrl.worker_thread.wait.assert_not_called()

    def test_close_rag_error_ignored(self, ctrl):
        worker = ctrl.worker
        ctrl.rag_retriever.close.side_effect = RuntimeError("x")
        ctrl.worker_thread.isRunning.return_value = False
        ctrl.close()

        ctrl.rag_retriever.close.assert_called_once()
        worker.shutdown.assert_called_once()
        ctrl.worker_thread.quit.assert_called_once()
        ctrl.worker_thread.wait.assert_not_called()

    def test_close_returns_true_when_only_optional_rag_is_stuck(self, ctrl):
        ctrl._rag_lifecycle.close = MagicMock(return_value=False)
        worker = ctrl.worker
        ctrl.worker.shutdown.return_value = True
        ctrl.worker_thread.isRunning.return_value = False

        assert ctrl.close() is True

        ctrl._rag_lifecycle.close.assert_called_once()
        worker.shutdown.assert_called_once()

    def test_close_returns_false_when_worker_shutdown_fails(self, ctrl):
        ctrl._rag_lifecycle.close = MagicMock(return_value=True)
        ctrl.worker.shutdown.return_value = False
        ctrl.worker_thread.isRunning.return_value = False

        assert ctrl.close() is False

        ctrl._rag_lifecycle.close.assert_called_once()
        ctrl.worker.shutdown.assert_called_once()
        ctrl.worker_thread.quit.assert_not_called()

    def test_failed_worker_shutdown_keeps_close_retryable_until_success(self, ctrl):
        ctrl._rag_lifecycle.close = MagicMock(return_value=True)
        worker = ctrl.worker
        worker.shutdown.side_effect = [False, True]
        ctrl.worker_thread.isRunning.return_value = False

        assert ctrl.close() is False
        assert ctrl._closed is False
        assert ctrl.worker is worker

        assert ctrl.close() is True
        assert ctrl._closed is True
        assert ctrl.worker is None
        assert worker.shutdown.call_count == 2

    def test_failed_close_rejects_new_commands_while_cleanup_is_retryable(self, ctrl):
        ctrl._rag_lifecycle.close = MagicMock(return_value=True)
        ctrl.worker.shutdown.side_effect = [False, True]
        ctrl.worker_thread.isRunning.return_value = False
        ctrl._product_turn_policy.evaluate = MagicMock(return_value=None)

        assert ctrl.close() is False
        assert ctrl.accepts_commands is False

        correlation = _submit_user_turn(ctrl, "after-close")

        ctrl._product_turn_policy.evaluate.assert_not_called()
        assert ctrl.is_processing is False
        ctrl.turn_finished.emit.assert_called_with(
            AssistantTurnTerminal(
                correlation=correlation,
                outcome="rejected_closing",
            )
        )
        assert ctrl.close() is True

    def test_close_never_waits_for_a_mock_thread_terminal(self, ctrl):
        ctrl._rag_lifecycle.close = MagicMock(return_value=True)
        worker = ctrl.worker
        worker.shutdown.return_value = True
        ctrl.worker_thread.isRunning.return_value = True

        assert ctrl.close() is True
        assert ctrl._closed is True
        assert ctrl.worker is None
        assert worker.shutdown.call_count == 1
        ctrl.worker_thread.quit.assert_called_once()
        ctrl.worker_thread.wait.assert_not_called()

    def test_successful_close_is_terminal_and_idempotent(self, ctrl):
        ctrl._rag_lifecycle.close = MagicMock(return_value=True)
        worker = ctrl.worker
        worker.shutdown.return_value = True
        ctrl.worker_thread.isRunning.return_value = False

        assert ctrl.close() is True
        assert ctrl.close() is True

        assert ctrl._closed is True
        assert worker.shutdown.call_count == 1

    def test_shutdown_supersedes_pending_stop_and_ignores_late_ack(self, ctrl):
        ctrl._rag_lifecycle.close = MagicMock(return_value=True)
        ctrl.worker.shutdown.return_value = True
        ctrl.worker_thread.isRunning.return_value = False
        ctrl.is_processing = True
        ctrl._active_host_turn_generation = 7
        ctrl._active_host_turn_id = 71
        ctrl._active_generation_id = 17

        ctrl.stop_generation()
        assert ctrl.close() is True

        ctrl._on_generation_stop_finished(
            AssistantGenerationStopAcknowledgement(
                generation_id=17,
                stopped=True,
            )
        )

        assert ctrl.is_processing is False
        assert ctrl._active_generation_id is None
        assert ctrl._stopping_generation_id is None
        ctrl.turn_finished.emit.assert_called_once_with(
            AssistantTurnTerminal(
                correlation=AssistantTurnCorrelation(
                    generation=7,
                    turn_id=71,
                ),
                outcome="shutdown_cancelled",
            )
        )
        ctrl.response_presentation_ready.emit.assert_not_called()


# --- stop_generation ---
class TestStopGeneration:
    def test_stops_when_processing(self, ctrl):
        ctrl.is_processing = True
        ctrl._active_generation_id = 1
        ctrl.stop_generation()
        assert ctrl.is_processing
        ctrl.worker.cancel_generation.assert_called_once_with(
            AssistantGenerationStopRequest(generation_id=1)
        )
        ctrl.processing_finished.emit.assert_not_called()

        ctrl._on_generation_stop_finished(
            AssistantGenerationStopAcknowledgement(
                generation_id=1,
                stopped=True,
            )
        )

        assert not ctrl.is_processing
        ctrl.processing_finished.emit.assert_called_once()

    def test_stop_generation_cancels_backend_generation(self, ctrl):
        ctrl.is_processing = True
        ctrl._active_generation_id = 2
        ctrl.stop_generation()

        ctrl.worker.cancel_generation.assert_called_once_with(
            AssistantGenerationStopRequest(generation_id=2)
        )

    def test_stop_generation_stays_stopping_after_failed_ack(self, ctrl):
        ctrl.is_processing = True
        ctrl._active_generation_id = 3
        ctrl.stop_generation()

        ctrl._on_generation_stop_finished(
            AssistantGenerationStopAcknowledgement(
                generation_id=3,
                stopped=False,
            )
        )

        assert ctrl.is_processing is True
        ctrl.processing_finished.emit.assert_not_called()
        ctrl.status_update.emit.assert_called_with("Stopping...")

    def test_reentrant_stop_reuses_exact_generation_and_finalizes_once(
        self,
        ctrl,
    ):
        ctrl.is_processing = True
        ctrl._active_generation_id = 4
        ctrl.metrics.finish_turn = MagicMock()
        request = AssistantGenerationStopRequest(generation_id=4)

        ctrl.stop_generation()
        ctrl.stop_generation()

        assert ctrl.worker.cancel_generation.call_args_list == [
            call(request),
            call(request),
        ]
        ctrl.metrics.finish_turn.assert_called_once_with()
        stopping_activities = [
            item.args[0]
            for item in ctrl.activity_changed.emit.call_args_list
            if item.args[0].phase is AssistantTurnActivityPhase.STOPPING
        ]
        assert len(stopping_activities) == 1

        acknowledgement = AssistantGenerationStopAcknowledgement(
            generation_id=4,
            stopped=True,
        )
        ctrl._on_generation_stop_finished(acknowledgement)
        ctrl._on_generation_stop_finished(acknowledgement)

        ctrl.processing_finished.emit.assert_called_once_with()
        ctrl.response_presentation_ready.emit.assert_called_once()

    def test_finish_before_stop_ack_publishes_only_one_cancelled_terminal(
        self,
        ctrl,
    ):
        ctrl.is_processing = True
        ctrl._active_host_turn_generation = 1
        ctrl._active_host_turn_id = 105
        ctrl._active_generation_id = 5
        ctrl.current_response = "completed output queued before stop acknowledgement"

        ctrl.stop_generation()
        stopping_activity = ctrl.activity_changed.emit.call_args.args[0]
        assert stopping_activity.phase is AssistantTurnActivityPhase.STOPPING
        assert stopping_activity.turn_id == 105
        ctrl._on_generation_finished(5, [])

        assert ctrl._active_generation_id == 5
        ctrl.generation_event.emit.assert_not_called()
        ctrl.response_presentation_ready.emit.assert_not_called()
        ctrl.processing_finished.emit.assert_not_called()
        ctrl.turn_finished.emit.assert_not_called()

        ctrl._on_generation_stop_finished(
            AssistantGenerationStopAcknowledgement(
                generation_id=5,
                stopped=True,
            )
        )
        ctrl._on_generation_finished(5, [])
        ctrl._on_generation_error(5, "late generation failure")
        ctrl._on_generation_stop_finished(
            AssistantGenerationStopAcknowledgement(
                generation_id=5,
                stopped=True,
            )
        )

        ctrl.generation_event.emit.assert_called_once_with(
            AssistantGenerationEvent(
                generation_id=5,
                phase=AssistantGenerationEventPhase.CANCELLED,
            )
        )
        ctrl.response_presentation_ready.emit.assert_called_once()
        presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
        assert presentation.kind is AssistantResponseKind.CANCELLED
        assert presentation.text == (
            "Request cancelled. You can revise it or ask something else."
        )
        assert ctrl.history == [{"role": "assistant", "content": presentation.text}]
        ctrl.error_occurred.emit.assert_not_called()
        ctrl.processing_finished.emit.assert_called_once_with()
        ctrl.turn_finished.emit.assert_called_once_with(
            AssistantTurnTerminal(
                correlation=AssistantTurnCorrelation(generation=1, turn_id=105),
                outcome="cancelled",
            )
        )

    def test_error_before_stop_ack_publishes_only_one_cancelled_terminal(
        self,
        ctrl,
    ):
        ctrl.is_processing = True
        ctrl._active_host_turn_generation = 1
        ctrl._active_host_turn_id = 106
        ctrl._active_generation_id = 6

        ctrl.stop_generation()
        ctrl._on_generation_error(6, "generation failed while stopping")

        assert ctrl._active_generation_id == 6
        ctrl.generation_event.emit.assert_not_called()
        ctrl.error_occurred.emit.assert_not_called()
        ctrl.response_presentation_ready.emit.assert_not_called()
        ctrl.processing_finished.emit.assert_not_called()
        ctrl.turn_finished.emit.assert_not_called()

        ctrl._on_generation_stop_finished(
            AssistantGenerationStopAcknowledgement(
                generation_id=6,
                stopped=True,
            )
        )
        ctrl._on_generation_error(6, "late generation failure")
        ctrl._on_generation_finished(6, [])
        ctrl._on_generation_stop_finished(
            AssistantGenerationStopAcknowledgement(
                generation_id=6,
                stopped=True,
            )
        )

        ctrl.generation_event.emit.assert_called_once_with(
            AssistantGenerationEvent(
                generation_id=6,
                phase=AssistantGenerationEventPhase.CANCELLED,
            )
        )
        ctrl.response_presentation_ready.emit.assert_called_once()
        presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
        assert presentation.kind is AssistantResponseKind.CANCELLED
        assert presentation.text == (
            "Request cancelled. You can revise it or ask something else."
        )
        assert ctrl.history == [{"role": "assistant", "content": presentation.text}]
        ctrl.error_occurred.emit.assert_not_called()
        ctrl.processing_finished.emit.assert_called_once_with()
        ctrl.turn_finished.emit.assert_called_once_with(
            AssistantTurnTerminal(
                correlation=AssistantTurnCorrelation(generation=1, turn_id=106),
                outcome="cancelled",
            )
        )

    def test_stop_ack_clears_generation_and_rejects_late_finish(
        self,
        ctrl,
    ):
        ctrl.is_processing = True
        ctrl._active_generation_id = 5
        ctrl.current_response = "partial buffered response"

        ctrl.stop_generation()
        ctrl._on_chunk_received(5, " late output")

        ctrl.response_presentation_ready.emit.assert_not_called()
        ctrl.generation_event.emit.assert_not_called()
        assert ctrl.current_response == "partial buffered response"

        ctrl._on_generation_stop_finished(
            AssistantGenerationStopAcknowledgement(
                generation_id=5,
                stopped=True,
            )
        )
        active_generation_after_ack = ctrl._active_generation_id
        ctrl._on_generation_finished(5, [])
        ctrl._on_generation_stop_finished(
            AssistantGenerationStopAcknowledgement(
                generation_id=5,
                stopped=True,
            )
        )

        generation_events = [
            signal_call.args[0]
            for signal_call in ctrl.generation_event.emit.call_args_list
        ]
        assert active_generation_after_ack is None
        assert generation_events == [
            AssistantGenerationEvent(
                generation_id=5,
                phase=AssistantGenerationEventPhase.CANCELLED,
            )
        ]
        ctrl.response_presentation_ready.emit.assert_called_once()
        presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
        assert presentation.kind is AssistantResponseKind.CANCELLED
        assert presentation.text == (
            "Request cancelled. You can revise it or ask something else."
        )
        assert ctrl.history[-1] == {
            "role": "assistant",
            "content": presentation.text,
        }
        assert ctrl.is_processing is False
        ctrl.processing_finished.emit.assert_called_once()

    def test_delayed_generation_a_stop_ack_cannot_cancel_stopping_generation_b(
        self,
        ctrl,
    ):
        ctrl.is_processing = True
        ctrl._active_host_turn_generation = 1
        ctrl._active_host_turn_id = 101
        ctrl._active_generation_id = 41

        ctrl.stop_generation()

        ctrl.worker.cancel_generation.assert_called_once_with(
            AssistantGenerationStopRequest(generation_id=41)
        )
        ctrl._on_generation_stop_finished(
            AssistantGenerationStopAcknowledgement(
                generation_id=41,
                stopped=True,
            )
        )
        assert ctrl.is_processing is False

        ctrl._reset_user_turn_state()
        ctrl.is_processing = True
        ctrl._active_host_turn_generation = 2
        ctrl._active_host_turn_id = 102
        ctrl._active_generation_id = 42
        ctrl.processing_finished.emit.reset_mock()
        ctrl.response_presentation_ready.emit.reset_mock()

        ctrl.stop_generation()
        ctrl._on_generation_stop_finished(
            AssistantGenerationStopAcknowledgement(
                generation_id=41,
                stopped=True,
            )
        )

        assert ctrl.is_processing is True
        assert ctrl._active_generation_id == 42
        assert ctrl._active_host_turn_id == 102
        ctrl.processing_finished.emit.assert_not_called()
        ctrl.response_presentation_ready.emit.assert_not_called()

        ctrl._on_generation_stop_finished(
            AssistantGenerationStopAcknowledgement(
                generation_id=42,
                stopped=True,
            )
        )

        assert ctrl.is_processing is False
        ctrl.processing_finished.emit.assert_called_once_with()

    def test_stopping_pending_rag_has_the_same_terminal_response(self, ctrl):
        ctrl.is_processing = True
        ctrl._waiting_for_rag = True
        ctrl._active_rag_turn_id = 1

        ctrl.stop_generation()

        ctrl.response_presentation_ready.emit.assert_called_once()
        presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
        assert presentation.text == (
            "Request cancelled. You can revise it or ask something else."
        )
        assert ctrl.is_processing is False
        ctrl.processing_finished.emit.assert_called_once()


# --- set_model ---
class TestSetModel:
    def test_emits_reinit(self, ctrl):
        spec = _runtime_launch_spec()

        ctrl.set_model(spec)

        ctrl.sig_reinit.emit.assert_called_once_with(spec)

    def test_preserves_approved_local_model_identifier(self, ctrl):
        spec = _runtime_launch_spec(LLMConfig.fallback_local_model_id())

        ctrl.set_model(spec)

        ctrl.sig_reinit.emit.assert_called_once_with(spec)

    def test_rejects_untyped_selection_instead_of_normalizing(self, ctrl):
        with pytest.raises(TypeError, match="launch spec"):
            ctrl.set_model("Gemini")

        ctrl.sig_reinit.emit.assert_not_called()


def test_initialize_forwards_the_exact_launch_spec(ctrl):
    spec = _runtime_launch_spec()

    ctrl.initialize(spec)

    ctrl.sig_initialize.emit.assert_called_once_with(spec)


# --- reset_conversation ---
class TestResetConversation:
    def test_clears_state(self, ctrl):
        ctrl.history = [{"role": "user", "content": "hi"}]
        ctrl._retry_count = 5
        ctrl._active_host_turn_generation = None
        ctrl._active_host_turn_id = None
        ctrl.reset_conversation()
        assert ctrl.history == []
        assert ctrl._retry_count == 0
        ctrl.assembler.clear_context.assert_called()


# --- execute_debug_tool ---
class TestExecuteDebugTool:
    def test_records_and_executes(self, ctrl):
        ctrl._active_host_turn_generation = None
        ctrl._active_host_turn_id = None
        request = AssistantDebugToolRequest.from_params(
            correlation=AssistantTurnCorrelation(generation=7, turn_id=9),
            tool_name="test",
            params={"k": "v"},
        )
        ctrl._execute_tool_no_loop = MagicMock(return_value=_tool_outcome("done"))
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        acknowledgement = ctrl.execute_debug_tool(request)
        assert not ctrl.is_processing
        assert len(ctrl.history) == 2
        assert ctrl.response_presentation_ready.emit.call_count == 2
        assert acknowledgement.correlation == request.correlation
        assert acknowledgement.phase is AssistantTurnDeliveryPhase.ACCEPTED

    def test_rejects_stale_debug_request_without_executing_it(self, ctrl):
        ctrl._active_host_turn_generation = 11
        ctrl._active_host_turn_id = 12
        request = AssistantDebugToolRequest.from_params(
            correlation=AssistantTurnCorrelation(generation=13, turn_id=14),
            tool_name="test",
            params={"payload": "stale"},
        )
        ctrl._execute_tool_no_loop = MagicMock()

        acknowledgement = ctrl.execute_debug_tool(request)

        assert acknowledgement.correlation == request.correlation
        assert acknowledgement.phase is AssistantTurnDeliveryPhase.REJECTED
        ctrl._execute_tool_no_loop.assert_not_called()

    def test_typed_debug_request_keeps_confirmation_outside_tool_params(self):
        request = AssistantDebugToolRequest.from_params(
            correlation=AssistantTurnCorrelation(generation=7, turn_id=9),
            tool_name="clear_dataset",
            params={},
            confirmed=True,
            authorization_text="The host approved clearing the current dataset.",
        )

        assert request.confirmed is True
        assert request.authorization_text == (
            "The host approved clearing the current dataset."
        )
        assert request.to_params() == {}

    def test_debug_params_cannot_smuggle_host_confirmation(self, ctrl):
        from XBrainLab.backend.application import get_application_service
        from XBrainLab.backend.study import Study
        from XBrainLab.llm.tools import get_all_tools
        from XBrainLab.llm.tools.tool_registry import ToolRegistry

        study = Study()
        service = get_application_service(study)
        registry = ToolRegistry()
        for tool in get_all_tools("real"):
            registry.register(tool)
        ctrl.study = study
        ctrl.registry = registry
        ctrl._active_host_turn_generation = None
        ctrl._active_host_turn_id = None
        request = AssistantDebugToolRequest.from_params(
            correlation=AssistantTurnCorrelation(generation=7, turn_id=9),
            tool_name="clear_dataset",
            params={"confirmed": True},
        )

        with patch.object(service, "execute", wraps=service.execute) as execute:
            acknowledgement = ctrl.execute_debug_tool(request)

        assert acknowledgement.phase is AssistantTurnDeliveryPhase.ACCEPTED
        execute.assert_not_called()
        assert '"error_type": "input"' in ctrl.history[-1]["content"]

    def test_unknown_debug_tool_redacts_status_and_conversation_history(self, ctrl):
        private_path = "/home/alice/private/subject-17"
        private_token = "token=hf_super_secret"  # noqa: S105
        tool_name = f"unknown_{private_path} {private_token}"
        ctrl._active_host_turn_generation = None
        ctrl._active_host_turn_id = None
        request = AssistantDebugToolRequest.from_params(
            correlation=AssistantTurnCorrelation(generation=7, turn_id=10),
            tool_name=tool_name,
            params={},
        )

        acknowledgement = ctrl.execute_debug_tool(request)

        assert acknowledgement.phase is AssistantTurnDeliveryPhase.ACCEPTED
        public_output = f"{ctrl.history!r}\n{ctrl.status_update.emit.call_args_list!r}"
        assert private_path not in public_output
        assert private_token not in public_output
        assert "hf_super_secret" not in public_output
        assert "unknown_debug_tool" in public_output
        assert "The requested debug tool is unavailable." in public_output

    def test_apply_interpretation_debug_params_cannot_smuggle_confirmation(
        self,
        ctrl,
    ):
        from XBrainLab.backend.application import get_application_service
        from XBrainLab.backend.study import Study
        from XBrainLab.llm.tools import get_all_tools
        from XBrainLab.llm.tools.tool_registry import ToolRegistry

        study = Study()
        service = get_application_service(study)
        registry = ToolRegistry()
        for tool in get_all_tools("real"):
            registry.register(tool)
        ctrl.study = study
        ctrl.registry = registry
        ctrl._active_host_turn_generation = None
        ctrl._active_host_turn_id = None
        request = AssistantDebugToolRequest.from_params(
            correlation=AssistantTurnCorrelation(generation=7, turn_id=10),
            tool_name="apply_interpretation",
            params={"candidate_id": "candidate-1", "confirmed": True},
        )

        with patch.object(service, "execute", wraps=service.execute) as execute:
            acknowledgement = ctrl.execute_debug_tool(request)

        assert acknowledgement.phase is AssistantTurnDeliveryPhase.ACCEPTED
        execute.assert_not_called()
        assert '"error_type": "input"' in ctrl.history[-1]["content"]
        assert "trusted debug transport" in ctrl.history[-1]["content"]

    def test_top_level_debug_confirmation_executes_real_admitted_command_once(
        self,
        ctrl,
    ):
        from XBrainLab.backend.application import get_application_service
        from XBrainLab.backend.study import Study
        from XBrainLab.llm.tools import get_all_tools
        from XBrainLab.llm.tools.tool_registry import ToolRegistry

        study = Study()
        service = get_application_service(study)
        registry = ToolRegistry()
        for tool in get_all_tools("real"):
            registry.register(tool)
        ctrl.study = study
        ctrl.registry = registry
        ctrl._active_host_turn_generation = None
        ctrl._active_host_turn_id = None
        request = AssistantDebugToolRequest.from_params(
            correlation=AssistantTurnCorrelation(generation=7, turn_id=9),
            tool_name="clear_dataset",
            params={},
            confirmed=True,
        )

        with patch.object(service, "execute", wraps=service.execute) as execute:
            acknowledgement = ctrl.execute_debug_tool(request)

        assert acknowledgement.phase is AssistantTurnDeliveryPhase.ACCEPTED
        execute.assert_called_once()
        assert '"ok": true' in ctrl.history[-1]["content"]

    def test_ui_debug_path_admission_fails_closed_without_authorization(
        self,
        ctrl,
        tmp_path,
        caplog,
    ):
        from XBrainLab.backend.study import Study
        from XBrainLab.llm.tools import get_all_tools
        from XBrainLab.llm.tools.tool_registry import ToolRegistry

        private_path = tmp_path / "private-subject-17"
        private_path.mkdir()
        (private_path / "events.tsv").write_text("fixture", encoding="utf-8")
        registry = ToolRegistry()
        for tool in get_all_tools("real"):
            registry.register(tool)
        ctrl.study = Study()
        ctrl.registry = registry
        ctrl._active_host_turn_generation = None
        ctrl._active_host_turn_id = None
        request = AssistantDebugToolRequest.from_params(
            correlation=AssistantTurnCorrelation(generation=7, turn_id=9),
            tool_name="list_files",
            params={"directory": str(private_path)},
        )

        with caplog.at_level(logging.INFO):
            acknowledgement = ctrl.execute_debug_tool(request)

        assert acknowledgement.phase is AssistantTurnDeliveryPhase.ACCEPTED
        assert '"error_type": "input"' in ctrl.history[-1]["content"]
        assert str(private_path) not in repr(ctrl.history)
        assert str(private_path) not in "\n".join(
            record.getMessage() for record in caplog.records
        )


# --- HITL: on_user_confirmed ---
class TestOnUserConfirmed:
    def test_approved_executes_and_finalises(self, ctrl):
        """When user approves, the pending tool should execute."""
        context = _enabled_tool_context("clear_dataset", generation=31)
        context_reader = _set_context_reader(ctrl, return_value=context)
        _begin_confirmation(
            ctrl,
            _pending_decision("clear_dataset", {}, context=context),
        )
        ctrl._execute_tool_no_loop = MagicMock(
            return_value=_tool_outcome("Dataset cleared.")
        )
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        ctrl.metrics.finish_turn = MagicMock()

        _resolve_confirmation(ctrl, approved=True)

        ctrl._execute_tool_no_loop.assert_called_once_with(
            "clear_dataset",
            {"confirmed": True},
            context=context,
            expected_publication_generation=context.generation,
        )
        context_reader.assert_called_once_with("clear_dataset")
        assert ctrl.pending_interactions.confirmation_decision is None
        assert ctrl._tool_failure_count == 0

    def test_approved_data_interpretation_apply_adds_confirmed_param(self, ctrl):
        context = _enabled_tool_context("apply_interpretation", generation=32)
        context_reader = _set_context_reader(ctrl, return_value=context)
        _begin_confirmation(
            ctrl,
            _pending_decision(
                "apply_interpretation",
                {"candidate_id": "candidate-1"},
                context=context,
            ),
        )
        ctrl._execute_tool_no_loop = MagicMock(return_value=_tool_outcome("Applied."))
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        ctrl.metrics.finish_turn = MagicMock()

        _resolve_confirmation(ctrl, approved=True)

        ctrl._execute_tool_no_loop.assert_called_once_with(
            "apply_interpretation",
            {"candidate_id": "candidate-1", "confirmed": True},
            context=context,
            expected_publication_generation=context.generation,
        )
        context_reader.assert_called_once_with("apply_interpretation")

    def test_approved_resource_warning_replays_backend_receipt(self, ctrl):
        context = _enabled_tool_context("apply_interpretation", generation=32)
        _set_context_reader(ctrl, return_value=context)
        _begin_confirmation(
            ctrl,
            _pending_decision(
                "apply_interpretation",
                {"candidate_id": "candidate-1"},
                context=context,
                confirmation_kind="resource_preflight",
                resource_preflight_receipt=ResourcePreflightReceipt(
                    challenge_id="receipt-1",
                    command_name="apply_interpretation",
                    candidate_id="candidate-1",
                    scope_fingerprint="scope-1",
                    ttl_seconds=120.0,
                ),
            ),
        )
        ctrl._execute_tool_no_loop = MagicMock(
            return_value=_tool_outcome(
                "Interpretation applied.",
                tool_name="apply_interpretation",
            ),
        )
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)

        _resolve_confirmation(ctrl, approved=True)

        ctrl._execute_tool_no_loop.assert_called_once_with(
            "apply_interpretation",
            {
                "candidate_id": "candidate-1",
                "confirmed": True,
                "resource_preflight_confirmed": True,
                "resource_preflight_token": "receipt-1",
            },
            context=context,
            expected_publication_generation=context.generation,
        )

    @pytest.mark.parametrize(
        ("command_name", "params", "candidate_id", "token", "expected_params"),
        [
            (
                "preview_interpretation",
                {"choices": {"skip_labels": True}},
                "scan-1",
                "preview-receipt-1",
                {
                    "scan_id": "scan-1",
                    "choices": {"skip_labels": True},
                    "resource_preflight_confirmed": True,
                    "resource_preflight_token": "preview-receipt-1",
                },
            ),
            (
                "reload_interpretation_recipe",
                {"recipe_path": "/tmp/recipe.json"},
                "recipe-1",
                "reload-receipt-1",
                {
                    "recipe_path": "/tmp/recipe.json",
                    "resource_preflight_confirmed": True,
                    "resource_preflight_token": "reload-receipt-1",
                },
            ),
        ],
    )
    def test_human_approval_replays_data_interpretation_receipt(
        self,
        ctrl,
        command_name,
        params,
        candidate_id,
        token,
        expected_params,
    ):
        context = _enabled_tool_context(command_name, generation=32)
        _set_context_reader(ctrl, return_value=context)
        _begin_confirmation(
            ctrl,
            _pending_decision(
                command_name,
                params,
                context=context,
                confirmation_kind="resource_preflight",
                resource_preflight_receipt=ResourcePreflightReceipt(
                    challenge_id=token,
                    command_name=command_name,
                    candidate_id=candidate_id,
                    scope_fingerprint=f"{command_name}-scope-1",
                    ttl_seconds=120.0,
                    configuration_fingerprint=f"{command_name}-configuration-1",
                    preflight_fingerprint=f"{command_name}-preflight-1",
                ),
            ),
        )
        ctrl._execute_tool_no_loop = MagicMock(
            return_value=_tool_outcome(
                "Interpretation command completed.",
                tool_name=command_name,
            ),
        )
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)

        _resolve_confirmation(ctrl, approved=True)

        ctrl._execute_tool_no_loop.assert_called_once_with(
            command_name,
            expected_params,
            context=context,
            expected_publication_generation=context.generation,
        )

    def test_approved_training_resource_receipt_starts_exactly_once(self, ctrl):
        preflight = _training_resource_preflight()
        pending = _pending_training_resource_confirmation(
            ctrl,
            params={"append": True},
            preflight=preflight,
        )
        context = _assert_training_resource_context(pending.context)
        _set_context_reader(ctrl, return_value=context)
        _begin_confirmation(ctrl, pending)
        ctrl._execute_tool_no_loop = MagicMock(
            return_value=_tool_outcome(
                "Training started.",
                tool_name="start_training",
            )
        )
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        ctrl._handle_tool_success = MagicMock()

        _resolve_confirmation(ctrl, approved=True)

        ctrl._execute_tool_no_loop.assert_called_once_with(
            "start_training",
            {
                "append": True,
                "confirmed": True,
                "resource_preflight_confirmed": True,
                "resource_preflight_token": "training-receipt-1",
            },
            context=context,
            expected_publication_generation=context.generation,
        )
        ctrl._handle_tool_success.assert_called_once_with(
            context.availability,
            command_name="start_training",
            after_confirmation=True,
        )

    def test_changed_training_preflight_requests_fresh_confirmation(self, ctrl):
        pending = _pending_training_resource_confirmation(ctrl)
        context = _assert_training_resource_context(pending.context)
        _set_context_reader(ctrl, return_value=context)
        refreshed_preflight = _training_resource_preflight(
            batch_size=64,
            receipt_suffix="2",
        )
        refreshed_warning = ToolCommandResult.failure(
            "start_training",
            str(refreshed_preflight["message"]),
            command_name="train",
            error_type="confirmation_required",
            diagnostics={"resource_preflight": refreshed_preflight},
        )
        _begin_confirmation(ctrl, pending)
        ctrl._execute_tool_no_loop = MagicMock(
            return_value=ToolExecutionOutcome(False, refreshed_warning)
        )
        ctrl._handle_tool_result_logic = MagicMock()
        ctrl._handle_tool_success = MagicMock()

        _resolve_confirmation(ctrl, approved=True)

        ctrl._execute_tool_no_loop.assert_called_once_with(
            "start_training",
            {
                "confirmed": True,
                "resource_preflight_confirmed": True,
                "resource_preflight_token": "training-receipt-1",
            },
            context=context,
            expected_publication_generation=context.generation,
        )
        refreshed = ctrl.pending_interactions.confirmation_decision
        assert isinstance(refreshed, ToolAttemptDecision)
        assert refreshed.resource_preflight_receipt is not None
        assert (
            refreshed.resource_preflight_receipt.token == "training-receipt-2"  # noqa: S105 - opaque test receipt
        )
        ctrl._handle_tool_result_logic.assert_not_called()
        ctrl._handle_tool_success.assert_not_called()

    def test_rejected_training_resource_receipt_never_executes(self, ctrl):
        pending = _pending_training_resource_confirmation(ctrl)
        _begin_confirmation(ctrl, pending)
        ctrl._execute_tool_no_loop = MagicMock()

        _resolve_confirmation(ctrl, approved=False)

        ctrl._execute_tool_no_loop.assert_not_called()
        assert ctrl.pending_interactions.confirmation_decision is None

    def test_approved_action_pauses_for_backend_resource_confirmation_then_retries(
        self,
        ctrl,
    ):
        context = _enabled_tool_context("apply_interpretation", generation=33)
        _set_context_reader(ctrl, return_value=context)
        resource_warning = ToolCommandResult(
            ok=False,
            tool_name="apply_interpretation",
            command_name="apply_interpretation",
            message="Estimated RAM is near the available-memory limit.",
            error_type="confirmation_required",
            diagnostics={
                "resource_preflight": {
                    "risk_level": "warning",
                    "requires_confirmation": True,
                    "confirmation_token": "receipt-2",
                    "candidate_id": "candidate-2",
                    "scope_fingerprint": "scope-2",
                    "confirmation_ttl_seconds": 120.0,
                }
            },
        )
        _begin_confirmation(
            ctrl,
            _pending_decision(
                "apply_interpretation",
                {"candidate_id": "candidate-2"},
                context=context,
            ),
        )
        ctrl._execute_tool_no_loop = MagicMock(
            side_effect=[
                ToolExecutionOutcome(False, resource_warning),
                _tool_outcome(
                    "Interpretation applied.",
                    tool_name="apply_interpretation",
                ),
            ]
        )
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        ctrl._handle_tool_success = MagicMock()
        ctrl._finalize_turn_after_tool = MagicMock()

        _resolve_confirmation(ctrl, approved=True)

        pending = ctrl.pending_interactions.confirmation_decision
        assert isinstance(pending, ToolAttemptDecision)
        assert pending.confirmation_kind == "resource_preflight"
        assert pending.context is context
        assert pending.params == {"candidate_id": "candidate-2"}
        assert pending.resource_preflight_receipt is not None
        assert (
            pending.resource_preflight_receipt.token == "receipt-2"  # noqa: S105 - opaque test receipt
        )
        refreshed_request = ctrl.pending_interactions.confirmation_request
        assert isinstance(refreshed_request, AgentConfirmationRequest)
        assert refreshed_request.command_name == "apply_interpretation"
        assert refreshed_request.description == resource_warning.message
        ctrl.confirmation_requested.emit.assert_called_once_with(refreshed_request)
        ctrl._handle_tool_result_logic.assert_not_called()
        ctrl._handle_tool_success.assert_not_called()
        ctrl._finalize_turn_after_tool.assert_not_called()

        _resolve_confirmation(ctrl, approved=True)

        assert ctrl.pending_interactions.confirmation_decision is None
        assert ctrl._execute_tool_no_loop.call_args_list == [
            call(
                "apply_interpretation",
                {"candidate_id": "candidate-2", "confirmed": True},
                context=context,
                expected_publication_generation=context.generation,
            ),
            call(
                "apply_interpretation",
                {
                    "candidate_id": "candidate-2",
                    "confirmed": True,
                    "resource_preflight_confirmed": True,
                    "resource_preflight_token": "receipt-2",
                },
                context=context,
                expected_publication_generation=context.generation,
            ),
        ]
        ctrl._handle_tool_result_logic.assert_called_once()
        ctrl._handle_tool_success.assert_called_once_with(
            context.availability,
            command_name="apply_interpretation",
            after_confirmation=True,
        )

    def test_resource_warning_without_receipt_fails_closed_before_second_confirmation(
        self,
        ctrl,
    ):
        from XBrainLab.backend.application import (
            ConfigureTrainingCommand,
            get_application_service,
        )
        from XBrainLab.backend.study import Study
        from XBrainLab.llm.tools import application_surface
        from XBrainLab.llm.tools.application_surface import ToolAvailabilityContext

        study = Study()
        service = get_application_service(study)
        runtime_study = cast(Any, study)
        runtime_study.loaded_data_list = [object()]
        runtime_study.datasets = [object()]
        configured = service.execute(
            ConfigureTrainingCommand(
                model_name="EEGNet",
                epoch=1,
                batch_size=2,
                learning_rate=0.001,
                device="cpu",
            )
        )
        assert configured.ok is True
        ctrl.study = study
        prompt_context = application_surface.get_application_context(
            study,
            "start_training",
        )
        assert isinstance(prompt_context, ToolAvailabilityContext)
        assert prompt_context.availability.tool_name == "start_training"
        assert prompt_context.availability.command_name == CommandName.TRAIN.value
        assert prompt_context.state is not None
        assert prompt_context.availability.enabled is True
        assert service.get_view_publication().state.pipeline_stage == "dataset_ready"
        _begin_confirmation(
            ctrl,
            _pending_decision("start_training", {}, context=prompt_context),
        )
        _set_context_reader(ctrl, return_value=prompt_context)
        ctrl.registry.get_tool.return_value = MagicMock(
            description="Start training",
            requires_confirmation=True,
        )
        ctrl._generate_response = MagicMock()
        resource_warning = ToolCommandResult(
            ok=False,
            tool_name="start_training",
            command_name="train",
            message="Estimated VRAM needs confirmation.",
            error_type="confirmation_required",
            diagnostics={
                "resource_preflight": {
                    "risk_level": "warning",
                    "requires_confirmation": True,
                }
            },
        )
        execution_count = 0

        def execute_with_resource_warning(*args, **kwargs):
            nonlocal execution_count
            execution_count += 1
            return resource_warning

        with patch(
            "XBrainLab.llm.agent.tool_execution_coordinator."
            "execute_application_tool_command",
            side_effect=execute_with_resource_warning,
        ):
            _resolve_confirmation(ctrl, approved=True)

        assert execution_count == 1
        assert ctrl.pending_interactions.confirmation_decision is None
        ctrl.panel_navigation_requested.emit.assert_not_called()
        assert "command-bound receipt" in ctrl.history[-1]["content"]
        ctrl._generate_response.assert_not_called()

    def test_approved_command_discards_original_batch_remainder(self, ctrl):
        from XBrainLab.llm.agent.execution_policy import ExecutionSnapshot

        context = _enabled_tool_context("apply_interpretation", generation=33)
        context_reader = _set_context_reader(ctrl, return_value=context)
        _begin_confirmation(
            ctrl,
            _pending_decision(
                "apply_interpretation",
                {"candidate_id": "candidate-1"},
                context=context,
            ),
        )
        ctrl._execute_tool_no_loop = MagicMock(return_value=_tool_outcome("Applied."))
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        ctrl._process_tool_calls = MagicMock()
        ctrl._refresh_execution_snapshot = MagicMock(
            return_value=ExecutionSnapshot.safe_to_continue()
        )
        ctrl._finalize_turn_after_tool = MagicMock()

        _resolve_confirmation(ctrl, approved=True)

        ctrl._execute_tool_no_loop.assert_called_once_with(
            "apply_interpretation",
            {"candidate_id": "candidate-1", "confirmed": True},
            context=context,
            expected_publication_generation=context.generation,
        )
        ctrl._process_tool_calls.assert_not_called()
        context_reader.assert_called_once_with("apply_interpretation")
        ctrl._refresh_execution_snapshot.assert_called_once()
        ctrl._finalize_turn_after_tool.assert_called_once()

    def test_rejected_appends_rejection(self, ctrl):
        """When user rejects, no execution should happen."""
        _begin_confirmation(ctrl, _pending_decision("clear_dataset", {}))
        ctrl._execute_tool_no_loop = MagicMock()
        ctrl.metrics.finish_turn = MagicMock()

        request = _resolve_confirmation(ctrl, approved=False)

        ctrl._execute_tool_no_loop.assert_not_called()
        assert ctrl.pending_interactions.confirmation_decision is None
        assert any("rejected" in m["content"] for m in ctrl.history)

    def test_rejected_confirmation_emits_one_structured_terminal_outcome(self, ctrl):
        """Cancellation cannot reuse a stale tool summary or continue the turn."""
        _begin_confirmation(ctrl, _pending_decision("clear_dataset", {}))
        ctrl._last_tool_summary = "The assistant completed a background action."
        ctrl._execute_tool_no_loop = MagicMock()
        ctrl._generate_response = MagicMock()

        request = _resolve_confirmation(ctrl, approved=False)

        ctrl.interaction_resolved.emit.assert_called_once_with(
            AgentInteractionOutcome(
                status=AgentInteractionStatus.CANCELLED,
                command_name="clear_dataset",
                request_id=request.request_id,
            )
        )
        ctrl._execute_tool_no_loop.assert_not_called()
        ctrl._generate_response.assert_not_called()
        ctrl.processing_finished.emit.assert_called_once_with()
        presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
        assert isinstance(presentation, AssistantResponsePresentation)
        assert presentation.text == (
            "Dataset removal cancelled. Your current workspace is unchanged."
        )
        assert ctrl._turn_cancelled is True

    def test_confirmed_confirmation_emits_acceptance_and_executes_once(self, ctrl):
        """Approval is acknowledged once and executes exactly one pending command."""
        context = _enabled_tool_context("clear_dataset", generation=88)
        _set_context_reader(ctrl, return_value=context)
        _begin_confirmation(
            ctrl,
            _pending_decision("clear_dataset", {}, context=context),
        )
        ctrl._execute_tool_no_loop = MagicMock(
            return_value=_tool_outcome("Session cleared.", tool_name="clear_dataset")
        )
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        ctrl._handle_tool_success = MagicMock()

        request = _resolve_confirmation(ctrl, approved=True)

        ctrl.interaction_resolved.emit.assert_called_once_with(
            AgentInteractionOutcome(
                status=AgentInteractionStatus.CONFIRMED,
                command_name="clear_dataset",
                request_id=request.request_id,
            )
        )
        ctrl._execute_tool_no_loop.assert_called_once_with(
            "clear_dataset",
            {"confirmed": True},
            context=context,
            expected_publication_generation=context.generation,
        )
        ctrl._handle_tool_success.assert_called_once()

    def test_navigation_to_existing_ui_releases_turn_without_claiming_completion(
        self,
        ctrl,
    ):
        request = WorkflowUiHandoffRequest.for_decision(
            "evaluate",
            decision_fields=("result_view",),
        )
        ctrl.pending_interactions.begin_workflow_handoff(request)
        ctrl.is_processing = True

        _resolve_ui_handoff(
            ctrl,
            WorkflowUiHandoffResolutionStatus.DEFERRED_TO_UI,
            request=request,
        )

        assert ctrl.pending_interactions.workflow_handoff is None
        assert ctrl.is_processing is False
        assert not any("completed 'evaluate'" in m["content"] for m in ctrl.history)
        assert ctrl._last_tool_summary is None
        outcome = ctrl.interaction_resolved.emit.call_args.args[0]
        assert outcome.status is AgentInteractionStatus.DEFERRED_TO_UI
        presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
        assert presentation.text == (
            "Evaluation is open in the main window. Review results there."
        )
        assert "completed" not in presentation.text.lower()

        ctrl.handle_user_turn(
            AssistantTurnRequest.single_action(
                correlation=AssistantTurnCorrelation(generation=40, turn_id=40),
                text="hello",
            )
        )

        assert any(item["content"] == "hello" for item in ctrl.history)
        admitted = ctrl.turn_finished.emit.call_args.args[0]
        assert admitted.turn_id == 40
        assert admitted.outcome != "rejected_busy"

    def test_pending_epoch_handoff_rejects_new_turn_until_terminal_completion(
        self,
        ctrl,
    ):
        request = WorkflowUiHandoffRequest.for_decision(
            "create_epoch",
            decision_fields=("epoch_window",),
        )
        ctrl.pending_interactions.begin_workflow_handoff(request)
        ctrl.is_processing = True

        _resolve_ui_handoff(
            ctrl,
            WorkflowUiHandoffResolutionStatus.COMMAND_PENDING,
            request=request,
        )

        assert ctrl.pending_interactions.workflow_handoff is request
        assert ctrl.is_processing is True
        # The bounded session remains authoritative even if a stale UI
        # projection incorrectly clears the legacy processing flag.
        ctrl.is_processing = False
        ctrl.handle_user_turn(
            AssistantTurnRequest.single_action(
                correlation=AssistantTurnCorrelation(generation=41, turn_id=41),
                text="hello",
            )
        )
        assert not any(item["content"] == "hello" for item in ctrl.history)
        rejected = ctrl.turn_finished.emit.call_args.args[0]
        assert rejected.turn_id == 41
        assert rejected.outcome == "rejected_busy"

        _resolve_ui_handoff(
            ctrl,
            WorkflowUiHandoffResolutionStatus.COMPLETED,
            request=request,
        )

        assert ctrl.pending_interactions.workflow_handoff is None
        assert ctrl.is_processing is False
        ctrl.handle_user_turn(
            AssistantTurnRequest.single_action(
                correlation=AssistantTurnCorrelation(generation=42, turn_id=42),
                text="hello",
            )
        )
        assert any(item["content"] == "hello" for item in ctrl.history)
        admitted = ctrl.turn_finished.emit.call_args.args[0]
        assert admitted.turn_id == 42
        assert admitted.outcome != "rejected_busy"

    def test_completed_in_existing_ui_records_verified_completion(self, ctrl):
        ctrl.pending_interactions.begin_workflow_handoff(
            WorkflowUiHandoffRequest.for_decision(
                "create_epoch",
                decision_fields=("epoch_window",),
            )
        )
        ctrl._finalize_turn_after_tool = MagicMock()

        _resolve_ui_handoff(
            ctrl,
            WorkflowUiHandoffResolutionStatus.COMPLETED,
        )

        assert ctrl.pending_interactions.workflow_handoff is None
        assert any("completed 'create_epoch'" in m["content"] for m in ctrl.history)
        assert "completed" in ctrl._last_tool_summary.lower()
        ctrl.status_update.emit.assert_any_call("Existing settings completed.")
        ctrl._finalize_turn_after_tool.assert_called_once_with()

    def test_ui_handoff_clears_pending_before_resolution_and_idle(self, ctrl):
        request = WorkflowUiHandoffRequest.for_decision(
            "create_epoch",
            decision_fields=("epoch_window",),
        )
        ctrl.pending_interactions.begin_workflow_handoff(request)
        observed: list[str] = []

        def record_resolution(_outcome):
            assert ctrl.pending_interactions.workflow_handoff is None
            observed.append("resolution")

        def record_activity(activity):
            if activity.phase is AssistantTurnActivityPhase.IDLE:
                assert ctrl.pending_interactions.workflow_handoff is None
                observed.append("idle")

        ctrl.interaction_resolved.emit.side_effect = record_resolution
        ctrl.activity_changed.emit.side_effect = record_activity

        _resolve_ui_handoff(
            ctrl,
            WorkflowUiHandoffResolutionStatus.COMPLETED,
            request=request,
        )

        assert observed == ["resolution", "idle"]

    def test_cancelled_in_existing_ui_uses_rejection_semantics(self, ctrl):
        ctrl.pending_interactions.begin_workflow_handoff(
            WorkflowUiHandoffRequest.for_decision(
                "create_epoch",
                decision_fields=("epoch_window",),
            )
        )
        ctrl._finalize_turn_after_tool = MagicMock()

        _resolve_ui_handoff(
            ctrl,
            WorkflowUiHandoffResolutionStatus.CANCELLED,
        )

        assert ctrl.pending_interactions.workflow_handoff is None
        assert any("cancelled" in m["content"] for m in ctrl.history)
        ctrl._finalize_turn_after_tool.assert_called_once_with()

    def test_unavailable_existing_ui_does_not_claim_completion(self, ctrl):
        ctrl.pending_interactions.begin_workflow_handoff(
            WorkflowUiHandoffRequest.for_decision(
                "create_epoch",
                decision_fields=("epoch_window",),
            )
        )
        ctrl._finalize_turn_after_tool = MagicMock()

        _resolve_ui_handoff(
            ctrl,
            WorkflowUiHandoffResolutionStatus.UNAVAILABLE,
        )

        assert ctrl.pending_interactions.workflow_handoff is None
        assert any("unavailable" in m["content"] for m in ctrl.history)
        assert "No workflow action was executed" in ctrl._last_tool_summary
        ctrl.status_update.emit.assert_any_call("Existing settings unavailable.")
        ctrl._finalize_turn_after_tool.assert_called_once_with()

    def test_ui_handoff_failure_cannot_consume_training_resource_receipt(self, ctrl):
        pending = _pending_training_resource_confirmation(ctrl)
        _begin_confirmation(ctrl, pending)
        ctrl._finalize_turn_after_tool = MagicMock()

        resolution = WorkflowUiHandoffResolution.for_request(
            WorkflowUiHandoffRequest.for_decision("create_epoch"),
            status=WorkflowUiHandoffResolutionStatus.UNAVAILABLE,
        )
        ctrl.on_workflow_ui_handoff_resolved(resolution)

        assert ctrl.pending_interactions.confirmation_decision is pending
        ctrl._finalize_turn_after_tool.assert_not_called()

    def test_duplicate_workflow_handoff_resolution_finalizes_once(self, ctrl):
        ctrl.pending_interactions.begin_workflow_handoff(
            WorkflowUiHandoffRequest.for_decision(
                "create_epoch",
                decision_fields=("epoch_window",),
            )
        )
        ctrl._finalize_turn_after_tool = MagicMock()

        request = ctrl.pending_interactions.workflow_handoff
        _resolve_ui_handoff(
            ctrl,
            WorkflowUiHandoffResolutionStatus.COMPLETED,
            request=request,
        )
        _resolve_ui_handoff(
            ctrl,
            WorkflowUiHandoffResolutionStatus.COMPLETED,
            request=request,
        )

        assert ctrl.pending_interactions.workflow_handoff is None
        ctrl._finalize_turn_after_tool.assert_called_once_with()

    def test_reset_conversation_cannot_clear_pending_workflow_handoff(self, ctrl):
        request = WorkflowUiHandoffRequest.for_decision(
            "create_epoch",
            decision_fields=("epoch_window",),
        )
        ctrl.pending_interactions.begin_workflow_handoff(request)

        ctrl.reset_conversation()

        assert ctrl.pending_interactions.workflow_handoff is request

    def test_stop_cancels_pending_workflow_handoff_without_backend_execution(
        self,
        ctrl,
    ):
        ctrl.pending_interactions.begin_workflow_handoff(
            WorkflowUiHandoffRequest.for_decision(
                "create_epoch",
                decision_fields=("epoch_window",),
            )
        )
        ctrl.is_processing = True
        ctrl._execute_tool_no_loop = MagicMock()
        ctrl._finalize_turn_after_tool = MagicMock()

        ctrl.stop_generation()

        assert ctrl.pending_interactions.workflow_handoff is None
        ctrl._execute_tool_no_loop.assert_not_called()
        ctrl._finalize_turn_after_tool.assert_called_once_with()

    def test_stale_handoff_resolution_cannot_consume_current_request(self, ctrl):
        stale = WorkflowUiHandoffRequest.for_decision(
            "create_epoch",
            decision_fields=("epoch_window",),
        )
        current = WorkflowUiHandoffRequest.for_decision(
            "generate_dataset",
            decision_fields=("split_strategy",),
        )
        ctrl.pending_interactions.begin_workflow_handoff(current)
        ctrl._finalize_turn_after_tool = MagicMock()

        _resolve_ui_handoff(
            ctrl,
            WorkflowUiHandoffResolutionStatus.COMPLETED,
            request=stale,
        )

        assert ctrl.pending_interactions.workflow_handoff is current
        ctrl._finalize_turn_after_tool.assert_not_called()

    def test_malformed_handoff_callback_fails_current_request_without_sticking(
        self,
        ctrl,
    ):
        request = WorkflowUiHandoffRequest.for_decision("create_epoch")
        ctrl.pending_interactions.begin_workflow_handoff(request)
        ctrl.is_processing = True

        ctrl.on_workflow_ui_handoff_resolved({"status": "completed"})

        assert ctrl.pending_interactions.workflow_handoff is None
        assert ctrl.is_processing is False
        outcome = ctrl.interaction_resolved.emit.call_args.args[0]
        assert outcome.request_id == request.request_id
        assert outcome.status is AgentInteractionStatus.FAILED

    def test_montage_resolution_with_changed_suggestions_is_rejected(self, ctrl):
        current = WorkflowUiHandoffRequest.for_decision(
            CommandName.APPLY_MONTAGE,
            decision_fields=("channel_mapping",),
            suggested_values={
                "montage_name": "standard_1020",
                "warning": "Review channel identities.",
            },
        )
        ctrl.pending_interactions.begin_workflow_handoff(current)
        ctrl._finalize_turn_after_tool = MagicMock()
        mismatched = WorkflowUiHandoffResolution(
            request_id=current.request_id,
            command=current.command,
            status=WorkflowUiHandoffResolutionStatus.COMPLETED,
            decision_fields=current.decision_fields,
            suggested_values=(("montage_name", "standard_1005"),),
        )

        ctrl.on_workflow_ui_handoff_resolved(mismatched)

        assert ctrl.pending_interactions.workflow_handoff is current
        ctrl._finalize_turn_after_tool.assert_not_called()

    @pytest.mark.parametrize(
        ("resolution_status", "interaction_status"),
        [
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
    def test_handoff_failure_kinds_remain_distinct(
        self,
        ctrl,
        resolution_status,
        interaction_status,
    ):
        ctrl.pending_interactions.begin_workflow_handoff(
            WorkflowUiHandoffRequest.for_decision(
                "create_epoch",
                decision_fields=("epoch_window",),
            )
        )
        ctrl._finalize_turn_after_tool = MagicMock()

        _resolve_ui_handoff(
            ctrl,
            resolution_status,
            message="Specific product surface outcome.",
        )

        outcome = ctrl.interaction_resolved.emit.call_args.args[0]
        assert outcome.status is interaction_status
        assert outcome.message == "Specific product surface outcome."
        assert outcome.decision_fields == ("epoch_window",)

    def test_no_pending_is_noop(self, ctrl):
        """A typed resolution cannot execute when no action is pending."""
        ctrl.pending_interactions.clear()
        history_before = list(ctrl.history)
        ctrl._execute_tool_no_loop = MagicMock()
        request = AgentConfirmationRequest.for_action(
            command_name="clear_dataset",
            params={},
            action_label="Clear dataset",
            description="Clear dataset",
            destructive=True,
            publication_generation=1,
        )

        ctrl.on_user_confirmation_resolved(
            AgentConfirmationResolution.for_request(
                request,
                status=AgentConfirmationResolutionStatus.APPROVED,
            )
        )

        assert ctrl.history == history_before
        ctrl._execute_tool_no_loop.assert_not_called()

    def test_untyped_confirmation_cannot_approve_pending_action(self, ctrl):
        pending = _pending_decision(
            "clear_dataset",
            {},
            context=_enabled_tool_context("clear_dataset", generation=51),
        )
        request = AgentConfirmationRequest.for_action(
            command_name="clear_dataset",
            params={},
            action_label="Clear dataset",
            description="Clear dataset",
            destructive=True,
            publication_generation=51,
        )
        _begin_confirmation(ctrl, pending, request)
        ctrl._execute_tool_no_loop = MagicMock()

        ctrl.on_user_confirmation_resolved(True)

        assert ctrl.pending_interactions.confirmation_decision is pending
        assert isinstance(
            ctrl.pending_interactions.confirmation_request,
            AgentConfirmationRequest,
        )
        ctrl._execute_tool_no_loop.assert_not_called()

    def test_mismatched_confirmation_keeps_exact_pending_action(self, ctrl):
        context = _enabled_tool_context("clear_dataset", generation=52)
        pending = _pending_decision("clear_dataset", {}, context=context)
        active_request = AgentConfirmationRequest.for_action(
            command_name="clear_dataset",
            params={},
            action_label="Clear dataset",
            description="Clear dataset",
            destructive=True,
            publication_generation=52,
        )
        stale_request = AgentConfirmationRequest.for_action(
            command_name="clear_dataset",
            params={},
            action_label="Clear dataset",
            description="Clear dataset",
            destructive=True,
            publication_generation=52,
        )
        _begin_confirmation(ctrl, pending, active_request)
        ctrl._execute_tool_no_loop = MagicMock()

        ctrl.on_user_confirmation_resolved(
            AgentConfirmationResolution.for_request(
                stale_request,
                status=AgentConfirmationResolutionStatus.APPROVED,
            )
        )

        assert ctrl.pending_interactions.confirmation_decision is pending
        assert ctrl.pending_interactions.confirmation_request is active_request
        ctrl._execute_tool_no_loop.assert_not_called()

    def test_confirmation_is_rejected_when_publication_generation_changes(self, ctrl):
        context = _enabled_tool_context("clear_dataset", generation=53)
        pending = _pending_decision("clear_dataset", {}, context=context)
        request = AgentConfirmationRequest.for_action(
            command_name="clear_dataset",
            params={},
            action_label="Clear dataset",
            description="Clear dataset",
            destructive=True,
            publication_generation=53,
        )
        _begin_confirmation(ctrl, pending, request)
        _set_context_reader(
            ctrl,
            return_value=_enabled_tool_context("clear_dataset", generation=54),
        )
        ctrl._execute_tool_no_loop = MagicMock()
        ctrl._handle_tool_attempt_blocked = MagicMock()

        ctrl.on_user_confirmation_resolved(
            AgentConfirmationResolution.for_request(
                request,
                status=AgentConfirmationResolutionStatus.APPROVED,
            )
        )

        ctrl._execute_tool_no_loop.assert_not_called()
        ctrl._handle_tool_attempt_blocked.assert_called_once()
        blocked = ctrl._handle_tool_attempt_blocked.call_args.args[1]
        assert isinstance(blocked, ToolCommandResult)
        assert blocked.error_type == "stale_confirmation"
        assert blocked.diagnostics == {
            "confirmed_generation": 53,
            "current_generation": 54,
        }
        outcome = ctrl.interaction_resolved.emit.call_args.args[0]
        assert outcome.status is AgentInteractionStatus.BLOCKED
        assert outcome.request_id == request.request_id
        assert ctrl.pending_interactions.confirmation_decision is None
        assert ctrl.pending_interactions.confirmation_request is None

    def test_duplicate_confirmation_cannot_execute_twice(self, ctrl):
        context = _enabled_tool_context("clear_dataset", generation=55)
        _set_context_reader(ctrl, return_value=context)
        _begin_confirmation(
            ctrl,
            _pending_decision("clear_dataset", {}, context=context),
        )
        ctrl._execute_tool_no_loop = MagicMock(
            return_value=_tool_outcome("Dataset cleared.")
        )
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        ctrl._handle_tool_success = MagicMock()
        request = _resolve_confirmation(ctrl, approved=True)
        resolution = AgentConfirmationResolution.for_request(
            request,
            status=AgentConfirmationResolutionStatus.APPROVED,
        )

        ctrl.on_user_confirmation_resolved(resolution)

        ctrl._execute_tool_no_loop.assert_called_once()
        ctrl._handle_tool_success.assert_called_once()

    def test_approved_failure_stops_in_ask_mode(self, ctrl):
        """A confirmed Ask action cannot execute a second tool attempt."""
        context = _enabled_tool_context("start_training", generation=34)
        context_reader = _set_context_reader(ctrl, return_value=context)
        _begin_confirmation(
            ctrl,
            _pending_decision("start_training", {}, context=context),
        )
        ctrl._execute_tool_no_loop = MagicMock(
            return_value=_tool_outcome("error", ok=False)
        )
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        ctrl._generate_response = MagicMock()
        ctrl._finalize_turn_after_tool = MagicMock()
        ctrl._refresh_execution_snapshot = MagicMock()
        ctrl._tool_failure_count = 0

        _resolve_confirmation(ctrl, approved=True)

        ctrl._execute_tool_no_loop.assert_called_once_with(
            "start_training",
            {"confirmed": True},
            context=context,
            expected_publication_generation=context.generation,
        )
        assert ctrl._tool_failure_count == 1
        context_reader.assert_called_once_with("start_training")
        ctrl._generate_response.assert_not_called()
        ctrl._refresh_execution_snapshot.assert_called_once()
        ctrl._finalize_turn_after_tool.assert_called_once()

    def test_reset_conversation_clears_pending(self, ctrl):
        """reset_conversation should also clear any pending confirmation."""
        pending = _pending_decision("clear_dataset", {})
        request = AgentConfirmationRequest.for_action(
            command_name="clear_dataset",
            params={},
            action_label="Clear dataset",
            description="Clear dataset",
            destructive=True,
            publication_generation=1,
        )
        _begin_confirmation(ctrl, pending, request)
        ctrl._active_host_turn_generation = None
        ctrl._active_host_turn_id = None
        ctrl.reset_conversation()
        assert ctrl.pending_interactions.confirmation_decision is None
        assert ctrl.pending_interactions.confirmation_request is None


# --- HITL: _process_tool_calls confirmation gate ---
class TestProcessToolCallsConfirmation:
    def test_backend_resource_warning_without_receipt_stays_blocked(self, ctrl):
        context = _enabled_tool_context("load_data", generation=39)
        tool = MagicMock(description="Load EEG data")
        result = ToolCommandResult(
            ok=False,
            tool_name="load_data",
            command_name="load_data",
            message="Estimated RAM is near the available-memory limit.",
            error_type="confirmation_required",
            diagnostics={
                "resource_preflight": {
                    "risk_level": "warning",
                    "requires_confirmation": True,
                }
            },
        )
        ctrl._execute_tool_no_loop = MagicMock(
            return_value=ToolExecutionOutcome(False, result)
        )
        ctrl._handle_tool_result_logic = MagicMock()
        ctrl._handle_tool_attempt_blocked = MagicMock()
        decision = ToolAttemptDecision(
            ToolAttemptAction.EXECUTE,
            "load_data",
            {"paths": ["/data/eeg.fif"]},
            context=context,
            tool=tool,
        )

        ctrl._execute_tool_attempt(decision)

        assert ctrl.pending_interactions.confirmation_decision is None
        ctrl._handle_tool_result_logic.assert_not_called()
        ctrl.panel_navigation_requested.emit.assert_not_called()
        ctrl._handle_tool_attempt_blocked.assert_called_once()
        blocked = ctrl._handle_tool_attempt_blocked.call_args.args[1]
        assert isinstance(blocked, ToolCommandResult)
        assert blocked.error_type == "contract"
        assert "did not provide a complete command-bound receipt" in blocked.message
        assert (
            blocked.diagnostics["resource_confirmation_contract"] == "missing_receipt"
        )

    def test_non_auto_executable_policy_requires_confirmation(self, ctrl):
        from XBrainLab.llm.tools.application_surface import ToolAvailability

        _allow_prompt_tools(ctrl)
        tool = MagicMock(requires_confirmation=False, description="Review choice")
        ctrl.registry.get_tool.return_value = tool
        _set_context_reader(
            ctrl,
            return_value=_tool_context(
                ToolAvailability(
                    tool_name="review_choice",
                    enabled=True,
                    can_auto_execute=False,
                    decision_boundary="user_choice",
                )
            ),
        )
        ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
        ctrl._execute_tool_no_loop = MagicMock()

        ctrl._process_tool_calls([("review_choice", {})], "json")

        pending = ctrl.pending_interactions.confirmation_decision
        assert isinstance(pending, ToolAttemptDecision)
        assert pending.command_name == "review_choice"
        assert pending.params == {}
        ctrl._execute_tool_no_loop.assert_not_called()
        request = ctrl.pending_interactions.confirmation_request
        assert isinstance(request, AgentConfirmationRequest)
        assert request.command_name == "review_choice"
        assert request.description == "Review choice"
        ctrl.confirmation_requested.emit.assert_called_once_with(request)

    def test_confirmation_required_pauses_execution(self, ctrl):
        """Tool with requires_confirmation should emit signal and pause."""
        context = _enabled_tool_context(
            "clear_dataset",
            generation=40,
            destructive=True,
        )
        context_reader = _set_context_reader(ctrl, return_value=context)
        mock_tool = MagicMock()
        mock_tool.requires_confirmation = True
        mock_tool.description = "Clear data"
        ctrl.registry.get_tool.return_value = mock_tool

        with patch(
            "XBrainLab.llm.agent.controller.estimate_confidence",
            return_value=0.9,
        ):
            ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
            ctrl._process_tool_calls(
                [("clear_dataset", {})],
                '{"tool_name": "clear_dataset"}',
            )

        pending = _assert_confirmation_prompt(
            ctrl,
            tool_name="clear_dataset",
            params={},
            description="Clear data",
            destructive=True,
        )
        assert pending.context is context
        context_reader.assert_called_once_with("clear_dataset")

    def test_confirmed_execution_uses_fresh_context_for_same_publication(self, ctrl):
        """Approval re-reads context instead of reusing the pending snapshot."""
        prompt_context = _tool_context_with_generation("clear_dataset", 41)
        current_context = _tool_context_with_generation("clear_dataset", 41)
        context_reader = _set_context_reader(
            ctrl,
            side_effect=[prompt_context, current_context],
        )
        tool = MagicMock(requires_confirmation=True, description="Clear data")
        ctrl.registry.get_tool.return_value = tool
        ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
        ctrl._execute_tool_no_loop = MagicMock(
            return_value=_tool_outcome("Dataset cleared.")
        )
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        ctrl._handle_tool_success = MagicMock()

        ctrl._process_tool_calls([("clear_dataset", {})], "json")
        pending = ctrl.pending_interactions.confirmation_decision
        assert isinstance(pending, ToolAttemptDecision)
        assert pending.context is prompt_context
        _resolve_confirmation(ctrl, approved=True)

        assert context_reader.call_args_list == [
            call("clear_dataset"),
            call("clear_dataset"),
        ]
        execution_kwargs = ctrl._execute_tool_no_loop.call_args.kwargs
        assert execution_kwargs["context"] is current_context
        assert execution_kwargs["context"] is not prompt_context
        assert execution_kwargs["expected_publication_generation"] == 41

    def test_confirmed_attempt_uses_fresh_context_and_backend_rechecks_state(
        self,
        ctrl,
    ):
        from XBrainLab.backend.application import get_application_service
        from XBrainLab.backend.study import Study
        from XBrainLab.llm.tools import application_surface

        study = Study()
        service = get_application_service(study)
        ctrl.study = study
        publication_generation = service.get_view_publication().generation
        attempt_context = _tool_context_with_generation(
            "start_training",
            publication_generation,
        )
        current_context = _tool_context_with_generation(
            "start_training",
            publication_generation,
        )
        context_reader = _set_context_reader(
            ctrl,
            side_effect=[attempt_context, current_context],
        )
        tool = MagicMock(requires_confirmation=True, description="Start training")
        ctrl.registry.get_tool.return_value = tool
        ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
        ctrl._generate_response = MagicMock()

        with patch(
            "XBrainLab.llm.agent.tool_execution_coordinator."
            "execute_application_tool_command",
            wraps=application_surface.execute_application_tool_command,
        ) as execute_surface:
            ctrl._process_tool_calls([("start_training", {})], "json")
            pending = ctrl.pending_interactions.confirmation_decision
            assert isinstance(pending, ToolAttemptDecision)
            assert pending.context is attempt_context

            # The attempt context claims this command is enabled. The empty real
            # Study must still win at the ApplicationService admission boundary.
            _resolve_confirmation(ctrl, approved=True)

        assert context_reader.call_args_list == [
            call("start_training"),
            call("start_training"),
        ]
        execute_surface.assert_called_once()
        assert execute_surface.call_args.kwargs["availability"] is (
            current_context.availability
        )
        assert execute_surface.call_args.kwargs["state"] is current_context.state
        result = ctrl.application_command_completed.emit.call_args.args[0]
        assert isinstance(result, ToolCommandResult)
        assert result.ok is False
        assert result.error_type == "precondition"
        assert "Generate datasets before training." in result.message
        assert result.capability is not None
        assert result.capability["enabled"] is False
        ctrl._generate_response.assert_not_called()

    def test_capability_block_uses_one_attempt_context(self, ctrl):
        from XBrainLab.llm.tools.application_surface import (
            ToolAvailability,
            ToolAvailabilityContext,
        )

        state = {"pipeline_stage": "empty"}
        context = ToolAvailabilityContext(
            availability=ToolAvailability(
                tool_name="start_training",
                enabled=False,
                reasons=("Generate datasets before training.",),
                command_name="train",
            ),
            state=state,
            generation=43,
        )
        context_reader = _set_context_reader(ctrl, return_value=context)
        ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
        ctrl._handle_tool_attempt_blocked = MagicMock()
        ctrl._execute_tool_no_loop = MagicMock()

        ctrl._process_tool_calls([("start_training", {})], "json")

        context_reader.assert_called_once_with("start_training")
        ctrl._execute_tool_no_loop.assert_not_called()
        result = ctrl._handle_tool_attempt_blocked.call_args.args[1]
        assert result.state is state
        assert result.diagnostics["publication_generation"] == 43

    def test_backend_confirmation_boundary_pauses_execution(self, ctrl):
        """ApplicationService autonomy policy can require HITL dynamically."""
        from XBrainLab.llm.tools.application_surface import ToolAvailability

        _allow_prompt_tools(ctrl)
        mock_tool = MagicMock()
        mock_tool.requires_confirmation = False
        mock_tool.description = "Apply data interpretation"
        ctrl.registry.get_tool.return_value = mock_tool

        availability = ToolAvailability(
            tool_name="apply_interpretation",
            enabled=True,
            command_name="apply_interpretation",
            confirmation_required=True,
            requires_confirmation=True,
            decision_boundary="semantic_apply",
        )
        _set_context_reader(ctrl, return_value=_tool_context(availability))
        with patch(
            "XBrainLab.llm.agent.controller.estimate_confidence",
            return_value=0.9,
        ):
            ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
            ctrl._process_tool_calls(
                [("apply_interpretation", {})],
                '{"tool_name": "apply_interpretation"}',
            )

        _assert_confirmation_prompt(
            ctrl,
            tool_name="apply_interpretation",
            params={},
            description="Apply data interpretation",
        )

    def test_no_confirmation_executes_directly(self, ctrl):
        """Tool without requires_confirmation should execute normally."""
        ctrl.history = [
            {
                "role": "user",
                "content": "Use legacy load_data for /tmp/a.gdf",
            }
        ]
        context = _enabled_tool_context("load_data", generation=44)
        context_reader = _set_context_reader(ctrl, return_value=context)
        mock_tool = MagicMock()
        mock_tool.requires_confirmation = False
        ctrl.registry.get_tool.return_value = mock_tool

        with patch(
            "XBrainLab.llm.agent.controller.estimate_confidence",
            return_value=0.9,
        ):
            mock_tool.execute.return_value = ToolResult(True, "done")
            ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
            ctrl._execute_tool_no_loop = MagicMock(return_value=_tool_outcome("done"))
            ctrl._handle_tool_result_logic = MagicMock(return_value=False)
            ctrl.metrics.finish_turn = MagicMock()
            ctrl._process_tool_calls(
                [("load_data", {"paths": ["/tmp/a.gdf"]})],
                '{"tool_name": "load_data"}',
            )

        assert ctrl.pending_interactions.confirmation_decision is None
        ctrl._execute_tool_no_loop.assert_called_once_with(
            "load_data",
            {"paths": ["/tmp/a.gdf"]},
            context=context,
        )
        context_reader.assert_called_once_with("load_data")


# --- ApplicationService capability gate in _execute_tool_no_loop ---
class TestPipelineGate:
    def test_normal_mapped_mutation_rejects_concurrent_publication_change(
        self,
        ctrl,
    ):
        from XBrainLab.backend.application import get_application_service
        from XBrainLab.backend.study import Study
        from XBrainLab.llm.agent.tool_attempt_coordinator import (
            ApplicationToolContextSource,
        )

        study = Study()
        service = get_application_service(study)
        ctrl.study = study
        ctrl.registry.get_tool.return_value = MagicMock(requires_confirmation=False)
        context = ApplicationToolContextSource(study).get_context("set_model")
        assert isinstance(context, ToolAvailabilityContext)
        assert context.generation is not None
        assert context.availability.enabled is True

        publication_a = service.get_view_publication()
        assert context.generation == publication_a.generation
        publication_b_state = replace(
            publication_a.state,
            pipeline_stage="data_loaded",
        )
        service.state_snapshot.build = MagicMock(return_value=publication_b_state)
        handler = MagicMock(return_value="Training configuration updated.")
        service._command_handlers[CommandName.CONFIGURE_TRAINING] = handler
        started = threading.Event()
        outcomes: list[ToolExecutionOutcome] = []

        def _execute_reviewed_mutation() -> None:
            started.set()
            outcomes.append(
                ctrl._execute_tool_no_loop(
                    "set_model",
                    {"model_name": "EEGNet"},
                    context=context,
                )
            )

        with service._command_lock:
            thread = threading.Thread(
                target=_execute_reviewed_mutation,
                daemon=True,
            )
            thread.start()
            assert started.wait(timeout=1.0)
            service.get_state()
            publication_b = service.get_view_publication()
            assert publication_b.generation > publication_a.generation
            assert (
                publication_b.effective_capabilities.get(
                    CommandName.CONFIGURE_TRAINING
                ).enabled
                is True
            )

        thread.join(timeout=2.0)

        assert thread.is_alive() is False
        assert len(outcomes) == 1
        outcome = outcomes[0]
        assert outcome.success is False
        assert isinstance(outcome.result, ToolCommandResult)
        assert outcome.result.error_type == "precondition"
        assert outcome.result.diagnostics["stale_publication"] is True
        assert (
            outcome.result.diagnostics["expected_publication_generation"]
            == context.generation
        )
        assert (
            outcome.result.diagnostics["current_publication_generation"]
            == publication_b.generation
        )
        handler.assert_not_called()

    def test_normal_mapped_mutation_without_generation_fails_closed(self, ctrl):
        from XBrainLab.backend.application import get_application_service
        from XBrainLab.backend.study import Study
        from XBrainLab.llm.agent.tool_attempt_coordinator import (
            ApplicationToolContextSource,
        )

        study = Study()
        service = get_application_service(study)
        ctrl.study = study
        ctrl.registry.get_tool.return_value = MagicMock(requires_confirmation=False)
        published_context = ApplicationToolContextSource(study).get_context("set_model")
        assert isinstance(published_context, ToolAvailabilityContext)
        context_without_generation = replace(published_context, generation=None)
        handler = MagicMock(return_value="Training configuration updated.")
        service._command_handlers[CommandName.CONFIGURE_TRAINING] = handler

        outcome = ctrl._execute_tool_no_loop(
            "set_model",
            {"model_name": "EEGNet"},
            context=context_without_generation,
        )

        assert outcome.success is False
        assert isinstance(outcome.result, ToolCommandResult)
        assert outcome.result.error_type == "runtime"
        assert outcome.result.recoverable is True
        assert "publication generation is unavailable" in outcome.result.message
        assert outcome.result.diagnostics == {"publication_generation": None}
        handler.assert_not_called()

    def test_real_tool_context_reads_one_committed_publication_generation(
        self,
        ctrl,
    ):
        from XBrainLab.backend.application import get_application_service
        from XBrainLab.backend.study import Study

        study = Study()
        service = get_application_service(study)
        empty = service.get_view_publication().state
        loaded = replace(
            empty,
            pipeline_stage="data_loaded",
            raw=replace(
                empty.raw,
                loaded=True,
                count=1,
                files=["subject.gdf"],
            ),
            active_dataset=replace(
                empty.active_dataset,
                has_raw_data=True,
            ),
        )
        service.state_snapshot.build = MagicMock(return_value=loaded)
        service.get_state()
        published = service.get_view_publication()
        ctrl.study = study
        from XBrainLab.llm.agent.tool_attempt_coordinator import (
            ApplicationToolContextSource,
        )

        ctrl._tool_attempt_coordinator._context_source = ApplicationToolContextSource(
            study
        )

        decision = ctrl._refresh_execution_snapshot()
        loaded_context = ctrl._tool_attempt_coordinator.context_for(
            "apply_bandpass_filter"
        )

        assert service.state_snapshot.build.call_count == 1
        assert published.generation == 2
        assert decision.state_reliable is True
        assert decision.recommended_next_step == "preprocess"
        assert loaded_context.state["active_dataset"]["has_raw_data"] is True
        assert loaded_context.availability.enabled is True
        assert loaded_context.capabilities is not None
        assert loaded_context.generation == published.generation

    def test_blocked_tool_uses_one_publication_for_capability_and_state(self, ctrl):
        from XBrainLab.llm.tools.application_surface import (
            ToolAvailability,
            ToolAvailabilityContext,
        )

        availability = ToolAvailability(
            tool_name="start_training",
            enabled=False,
            reasons=("Load raw data before training.",),
            command_name="train",
        )
        state = {
            "pipeline_stage": "empty",
            "active_dataset": {"has_raw_data": False},
        }
        expected_context = ToolAvailabilityContext(
            availability=availability,
            state=state,
            generation=17,
        )
        context_reader = _set_context_reader(ctrl, return_value=expected_context)

        block = ctrl._tool_attempt_coordinator.context_for("start_training")
        result = ctrl._tool_attempt_coordinator.blocked_result(
            "start_training",
            block,
        )

        context_reader.assert_called_once_with("start_training")
        assert block is expected_context
        assert result.state == state
        assert result.capability == availability.to_dict()
        assert result.diagnostics["publication_generation"] == 17

    def test_unavailable_capability_policy_fails_closed(self, ctrl):
        from XBrainLab.llm.tools.application_surface import (
            CapabilityPolicyUnavailable,
            ToolAvailability,
            ToolAvailabilityContext,
        )

        _set_context_reader(
            ctrl,
            side_effect=CapabilityPolicyUnavailable("policy missing"),
        )
        result = ctrl._tool_attempt_coordinator.context_for("load_data")

        assert isinstance(result, ToolAvailabilityContext)
        assert isinstance(result.availability, ToolAvailability)
        assert result.availability.enabled is False
        assert result.availability.can_auto_execute is False
        assert "unavailable" in result.availability.reason_text.lower()

    def test_runtime_availability_has_no_stage_config_gate(self):
        import inspect

        from XBrainLab.llm.agent.tool_attempt_coordinator import ToolAttemptCoordinator

        source = inspect.getsource(ToolAttemptCoordinator.context_for)
        assert "STAGE_CONFIG" not in source
        assert "_check_prompt_tool_exposure" not in source

    def test_application_service_rejects_missing_preprocess_inputs(self, ctrl):
        """Execution still obeys ApplicationService after host policy approval."""
        from XBrainLab.backend.study import Study

        ctrl.study = Study()
        mock_tool = MagicMock()
        ctrl.registry.get_tool.return_value = mock_tool

        outcome = ctrl._execute_tool_no_loop(
            "apply_bandpass_filter",
            {"low_freq": 4.0, "high_freq": 40.0},
        )
        result = outcome.result

        assert not outcome.success
        assert result.ok is False
        assert result.command_name == "preprocess"
        assert result.message == "Load raw data before preprocessing."
        assert result.error_type == "precondition"
        assert result.capability is not None
        payload = result.to_payload()
        assert payload["ok"] is False
        assert payload["capability"]["command_name"] == "preprocess"

    def test_application_service_validates_tool_without_stage_execution_gate(
        self,
        ctrl,
    ):
        """Prompt exposure cannot replace ApplicationService command validation."""
        from XBrainLab.backend.study import Study

        ctrl.study = Study()
        mock_tool = MagicMock()
        mock_tool.execute.side_effect = AssertionError("legacy path should not run")
        ctrl.registry.get_tool.return_value = mock_tool

        outcome = ctrl._execute_tool_no_loop(
            "load_data",
            {"file_paths": ["/tmp/sample.gdf"]},
        )
        result = outcome.result

        assert not outcome.success
        assert result.ok is False
        assert result.command_name == "load_data"
        assert "Required inputs are missing" in result.message
        mock_tool.execute.assert_not_called()

    def test_allowed_mapped_tool_missing_params_does_not_use_legacy_tool(self, ctrl):
        """Real Study mapped tools must not bypass ApplicationService on bad args."""
        from XBrainLab.backend.study import Study

        ctrl.study = Study()
        raw = MagicMock()
        ctrl.study.data_manager.loaded_data_list = [raw]
        ctrl.study.data_manager.preprocessed_data_list = []
        mock_tool = MagicMock()
        mock_tool.execute.side_effect = AssertionError("legacy path should not run")
        ctrl.registry.get_tool.return_value = mock_tool

        outcome = ctrl._execute_tool_no_loop(
            "apply_bandpass_filter",
            {},
        )
        result = outcome.result

        assert not outcome.success
        assert result.ok is False
        assert result.command_name == "preprocess"
        assert result.error_type == "input"
        assert "Required inputs" in result.message
        mock_tool.execute.assert_not_called()

    def test_tool_output_history_uses_compact_state_summary(self, ctrl):
        result = ToolCommandResult(
            ok=True,
            tool_name="query_state",
            command_name="query_state",
            message="Application state snapshot ready.",
            state={
                "pipeline_stage": "empty",
                "raw": {
                    "loaded": False,
                    "count": 0,
                    "metadata": [{"large": "payload"}],
                    "diagnostics": {"verbose": "details"},
                },
                "training": {
                    "has_model": False,
                    "missing_requirements": ["Data Splitting"],
                },
            },
            diagnostics={
                "payload_type": "state_snapshot",
                "state": {"too": "big"},
                "publication_generation": 8,
                "view_verified": True,
                "view_stale": True,
                "view_refresh_error": "A command is still publishing state.",
            },
            raw_result={"status": "ok", "state": {"too": "big"}},
        )

        payload = json.loads(ctrl._format_tool_output("query_state", True, result))

        assert payload["message"] == "Application state snapshot ready."
        assert payload["state_summary"]["pipeline_stage"] == "empty"
        assert payload["state_summary"]["raw"] == {"loaded": False, "count": 0}
        assert payload["state_summary"]["training"]["missing_requirements"] == [
            "Data Splitting"
        ]
        assert payload["diagnostics"] == {
            "payload_type": "state_snapshot",
            "publication_generation": 8,
            "view_verified": True,
            "view_stale": True,
            "view_refresh_error": "A command is still publishing state.",
        }
        assert "raw_result" not in payload
        assert "state" not in payload

    def test_legacy_load_summary_uses_neutral_product_language(self):
        from XBrainLab.llm.agent.controller import LLMController

        result = ToolCommandResult.failure(
            "load_data",
            "Load raw data first.",
            command_name=CommandName.LOAD_DATA.value,
            error_type="precondition",
        )

        summary = LLMController._summarize_tool_result("load_data", False, result)

        assert "Import data is not available yet" in summary
        assert "Load EEG data" not in summary
        assert "load_data" not in summary

    def test_train_blocked_until_backend_ready(self, ctrl):
        """Train is blocked until dataset/model/training options exist."""
        from XBrainLab.backend.study import Study

        ctrl.study = Study()
        mock_tool = MagicMock()
        ctrl.registry.get_tool.return_value = mock_tool

        outcome = ctrl._execute_tool_no_loop("start_training", {})
        result = outcome.result

        assert not outcome.success
        assert result.ok is False
        assert result.command_name == "train"
        assert "Generate datasets before training" in result.message

    def test_mapped_tool_uses_application_command_result(self, ctrl):
        """Mapped agent tools can bypass legacy string results."""
        from XBrainLab.backend.study import Study

        ctrl.study = Study()
        mock_tool = MagicMock()
        mock_tool.execute.side_effect = AssertionError("legacy path should not run")
        ctrl.registry.get_tool.return_value = mock_tool

        outcome = ctrl._execute_tool_no_loop(
            "set_model",
            {"model_name": "EEGNet"},
        )
        result = outcome.result

        assert outcome.success is True
        assert result.ok is True
        assert result.command_name == "configure_training"
        assert result.raw_result["status"] == "ok"
        ctrl.application_command_started.emit.assert_called_once_with()
        ctrl.application_command_completed.emit.assert_called_once_with(result)
        mock_tool.execute.assert_not_called()

    def test_montage_ui_request_does_not_open_command_refresh_window(self, ctrl):
        from XBrainLab.backend.study import Study
        from XBrainLab.llm.tools.real.preprocess_real import RealSetMontageTool

        ctrl.study = Study()
        ctrl.registry.get_tool.return_value = RealSetMontageTool()
        _allow_prompt_tools(ctrl)

        outcome = ctrl._execute_tool_no_loop(
            "set_montage",
            {"montage_name": "standard_1020"},
        )

        assert outcome.success is True
        assert isinstance(outcome.result, UiRequest)
        assert outcome.result.kind is UiRequestKind.CONFIRM_MONTAGE
        ctrl.application_command_started.emit.assert_not_called()
        ctrl.application_command_completed.emit.assert_not_called()


# --- Immutable turn scope ---
class TestTurnScope:
    def test_idle_policy_is_single_action(self, ctrl):
        assert (
            ctrl._active_policy_mode() == AssistantTurnScope.SINGLE_ACTION.policy_mode
        )

    def test_guided_turn_stops_after_its_declared_endpoint(self, ctrl):
        from XBrainLab.backend.application import CommandName
        from XBrainLab.llm.agent.turn import AssistantTurnScope

        ctrl._active_turn_scope = AssistantTurnScope.GUIDED_WORKFLOW
        ctrl._active_turn_terminal_command = CommandName.CREATE_EPOCH.value
        ctrl._finalize_turn_after_tool = MagicMock()
        ctrl._generate_response = MagicMock()

        ctrl._handle_tool_success(None, command_name="epoch_data")

        ctrl._finalize_turn_after_tool.assert_called_once_with()
        ctrl._generate_response.assert_not_called()

    def test_guided_turn_cannot_continue_past_its_declared_endpoint(self, ctrl):
        from XBrainLab.backend.application import CommandName
        from XBrainLab.llm.agent.execution_policy import ExecutionSnapshot
        from XBrainLab.llm.agent.turn import AssistantTurnScope

        ctrl._active_turn_scope = AssistantTurnScope.GUIDED_WORKFLOW
        ctrl._active_turn_terminal_command = CommandName.CREATE_EPOCH.value
        ctrl._finalize_turn_after_tool = MagicMock()
        ctrl._generate_response = MagicMock()
        ctrl._refresh_execution_snapshot = MagicMock(
            return_value=ExecutionSnapshot(
                state_reliable=True,
                decision_needed=(),
                can_auto_continue=True,
                recommended_next_step=CommandName.GENERATE_DATASET.value,
            )
        )

        ctrl._handle_tool_success(None, command_name="preprocess")

        ctrl._finalize_turn_after_tool.assert_called_once_with()
        ctrl.assembler.set_turn_authorized_command.assert_not_called()
        ctrl._generate_response.assert_not_called()

    def test_single_mode_finalizes_on_success(self, ctrl):
        """In single mode, a successful tool call finalizes immediately."""
        _allow_prompt_tools(ctrl)
        ctrl._execute_tool_no_loop = MagicMock(return_value=_tool_outcome("ok"))
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        ctrl._finalize_turn_after_tool = MagicMock()
        ctrl._generate_response = MagicMock()
        ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
        ctrl.registry.get_tool.return_value.requires_confirmation = False

        ctrl._process_tool_calls([("cmd", {})], "json")
        ctrl._finalize_turn_after_tool.assert_called_once()
        ctrl._generate_response.assert_not_called()

    def test_multi_mode_uses_host_for_deterministic_import_continuation(self, ctrl):
        """A safe no-input import step does not depend on another model call."""
        from XBrainLab.llm.agent.execution_policy import ExecutionSnapshot

        _set_guided_turn_scope(ctrl)
        context = _enabled_tool_context("preview_interpretation", generation=7)
        _set_context_reader(ctrl, return_value=context)
        ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
        ctrl.registry.get_tool.return_value.requires_confirmation = False
        ctrl._execute_tool_attempt = MagicMock()
        ctrl._finalize_turn_after_tool = MagicMock()
        ctrl._generate_response = MagicMock()
        ctrl._refresh_execution_snapshot = MagicMock(
            return_value=ExecutionSnapshot(
                state_reliable=True,
                decision_needed=(),
                can_auto_continue=True,
                recommended_next_step="preview_interpretation",
            )
        )

        ctrl._handle_tool_success(None, command_name="scan_source")

        decision = ctrl._execute_tool_attempt.call_args.args[0]
        assert decision.action is ToolAttemptAction.EXECUTE
        assert decision.command_name == "preview_interpretation"
        assert decision.params == {}
        assert decision.context is context
        ctrl._generate_response.assert_not_called()
        ctrl._finalize_turn_after_tool.assert_not_called()

    def test_host_deterministic_continuation_respects_registry_confirmation(
        self,
        ctrl,
    ):
        context = _enabled_tool_context("preview_interpretation", generation=7)
        _set_context_reader(ctrl, return_value=context)
        ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
        ctrl.registry.get_tool.return_value.requires_confirmation = True
        ctrl._execute_tool_attempt = MagicMock()

        executed = ctrl._execute_host_deterministic_continuation(
            "preview_interpretation"
        )

        assert executed is False
        ctrl._execute_tool_attempt.assert_not_called()

    def test_host_deterministic_continuation_requires_schema_verification(
        self,
        ctrl,
    ):
        context = _enabled_tool_context("preview_interpretation", generation=7)
        _set_context_reader(ctrl, return_value=context)
        ctrl.verifier.verify_tool_call.return_value = MagicMock(
            is_valid=False,
            error_message="schema rejected",
        )
        ctrl.registry.get_tool.return_value.requires_confirmation = False
        ctrl._execute_tool_attempt = MagicMock()

        executed = ctrl._execute_host_deterministic_continuation(
            "preview_interpretation"
        )

        assert executed is False
        ctrl._execute_tool_attempt.assert_not_called()

    def test_multi_mode_uses_model_for_non_deterministic_continuation(self, ctrl):
        """A parameter-bearing workflow step still requires model generation."""
        from XBrainLab.llm.agent.execution_policy import ExecutionSnapshot

        _set_guided_turn_scope(ctrl)
        ctrl._execute_tool_attempt = MagicMock()
        ctrl._finalize_turn_after_tool = MagicMock()
        ctrl._generate_response = MagicMock()
        ctrl._refresh_execution_snapshot = MagicMock(
            return_value=ExecutionSnapshot(
                state_reliable=True,
                decision_needed=(),
                can_auto_continue=True,
                recommended_next_step="apply_standard_preprocess",
            )
        )

        ctrl._handle_tool_success(None, command_name="query_state")

        ctrl.assembler.set_turn_authorized_command.assert_called_once_with(
            "apply_standard_preprocess",
            continuation=True,
        )
        ctrl._generate_response.assert_called_once()
        ctrl._execute_tool_attempt.assert_not_called()
        ctrl._finalize_turn_after_tool.assert_not_called()

    def test_multi_mode_stops_at_cap(self, ctrl):
        """Multi mode stops after reaching the max successful tool count."""
        _allow_prompt_tools(ctrl)
        _set_guided_turn_scope(ctrl)
        ctrl._tool_execution_count = ctrl._max_tool_executions - 1
        ctrl._execute_tool_no_loop = MagicMock(return_value=_tool_outcome("ok"))
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        ctrl._finalize_turn_after_tool = MagicMock()
        ctrl._generate_response = MagicMock()
        ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
        ctrl.registry.get_tool.return_value.requires_confirmation = False

        ctrl._process_tool_calls([("cmd", {})], "json")
        ctrl._finalize_turn_after_tool.assert_called_once()
        ctrl._generate_response.assert_not_called()

    def test_handle_user_input_resets_counter(self, ctrl):
        """Starting a new user turn resets the successful tool counter."""
        ctrl._successful_tool_count = 3
        _use_rag_probe(ctrl)
        ctrl._generate_response = MagicMock()
        _submit_user_turn(ctrl, "hello")
        assert ctrl._successful_tool_count == 0
        ctrl._generate_response.assert_not_called()
