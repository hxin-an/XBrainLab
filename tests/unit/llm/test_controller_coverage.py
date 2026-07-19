"""Coverage tests for LLMController — ReAct loop, tool execution, finalization."""

from unittest.mock import MagicMock

from XBrainLab.llm.agent.confirmation import (
    AgentConfirmationRequest,
    AgentConfirmationResolution,
    AgentConfirmationResolutionStatus,
)
from XBrainLab.llm.agent.pending_interaction import PendingInteractionCoordinator
from XBrainLab.llm.agent.turn import (
    AssistantGenerationEvent,
    AssistantGenerationEventPhase,
    AssistantGenerationRequest,
    AssistantResponseContract,
)
from XBrainLab.llm.tools.application_surface import ToolCommandResult
from XBrainLab.llm.tools.result_contract import ToolResult, UiRequest, UiRequestKind


def _blocked_context(tool_name: str, reason: str):
    from XBrainLab.llm.tools.application_surface import (
        ToolAvailability,
        ToolAvailabilityContext,
    )

    return ToolAvailabilityContext(
        availability=ToolAvailability(
            tool_name=tool_name,
            enabled=False,
            reasons=(reason,),
            command_name=tool_name,
        ),
        state={"pipeline_stage": "empty"},
        generation=1,
    )


def _allowed_context(tool_name: str):
    from XBrainLab.llm.tools.application_surface import (
        ToolAvailability,
        ToolAvailabilityContext,
    )

    return ToolAvailabilityContext(
        availability=ToolAvailability(
            tool_name=tool_name,
            enabled=True,
            command_name=tool_name,
        ),
        state={"pipeline_stage": "empty"},
        generation=1,
    )


def _make_ctrl():
    """Create a LLMController stub that bypasses __init__ but has required attrs."""
    from PyQt6.QtCore import QObject

    from XBrainLab.llm.agent.assembler import PromptToolPublication
    from XBrainLab.llm.agent.controller import LLMController
    from XBrainLab.llm.agent.response_presentation import AssistantResponseKind
    from XBrainLab.llm.agent.strict_envelope_recovery import (
        StrictEnvelopeRecoveryPolicy,
    )
    from XBrainLab.llm.agent.tool_attempt_coordinator import ToolAttemptCoordinator
    from XBrainLab.llm.agent.tool_execution_coordinator import (
        ToolExecutionCoordinator,
    )

    ctrl = LLMController.__new__(LLMController)
    # Call QObject.__init__ so that Qt internals are initialised (hasattr etc.)
    QObject.__init__(ctrl)
    # This white-box fixture bypasses the product constructor, so it must opt in
    # to the same shutdown invariant instead of relying on close() fallbacks.
    ctrl._initialize_shutdown_lifecycle()
    # Provide the _conversation attribute so that the history property works
    conv = MagicMock()
    conv.messages = []
    ctrl._conversation = conv
    ctrl.metrics = MagicMock()
    ctrl.metrics.current_turn = MagicMock()
    ctrl.status_update = MagicMock()
    ctrl.processing_finished = MagicMock()
    ctrl.turn_finished = MagicMock()
    ctrl._active_host_turn_id = 1
    ctrl._active_host_turn_generation = 1
    ctrl._active_tool_publication = PromptToolPublication.empty()
    ctrl.sig_generate = MagicMock()
    ctrl.assembler = MagicMock()
    ctrl.assembler.get_generation_request.return_value = (
        AssistantGenerationRequest.from_messages(
            [{"role": "user", "content": "retry"}],
            response_contract=AssistantResponseContract.STRUCTURED_ACTION,
        )
    )
    ctrl.assembler.latest_tool_publication = PromptToolPublication.empty()
    ctrl.generation_event = MagicMock()
    ctrl.response_presentation_ready = MagicMock()
    ctrl.panel_navigation_requested = MagicMock()
    ctrl.confirmation_requested = MagicMock()
    ctrl.activity_changed = MagicMock()
    ctrl.interaction_resolved = MagicMock()
    ctrl.error_occurred = MagicMock()
    ctrl.current_response = ""
    ctrl._generation_id = 0
    ctrl._active_generation_id = None
    ctrl._active_generation_dispatch_phase = None
    ctrl._generation_dispatch_in_progress = False
    ctrl._visible_response_sent = False
    ctrl._last_tool_summary = None
    ctrl._last_tool_summary_kind = AssistantResponseKind.MESSAGE
    ctrl._retry_count = 0
    ctrl._strict_envelope_recovery_policy = StrictEnvelopeRecoveryPolicy(
        max_recovery_attempts=3,
    )
    ctrl.is_processing = True
    ctrl._tool_failure_count = 0
    ctrl._max_tool_failures = 3
    ctrl._successful_tool_count = 0
    ctrl._execution_mode = ctrl.MODE_SINGLE
    ctrl._tool_execution_count = 0
    ctrl._max_tool_executions = 5
    ctrl._turn_cancelled = False
    ctrl._pending_interactions = PendingInteractionCoordinator()
    ctrl._rag_lifecycle = MagicMock()
    ctrl._loop_break_count = 0
    ctrl._max_loop_breaks = 2
    ctrl.registry = MagicMock()
    ctrl.study = MagicMock()
    ctrl.verifier = MagicMock()
    context_source = MagicMock()
    context_source.get_context.side_effect = lambda tool_name: _allowed_context(
        tool_name
    )
    ctrl._tool_attempt_coordinator = ToolAttemptCoordinator(
        registry=ctrl.registry,
        verifier=ctrl.verifier,
        context_source=context_source,
    )
    ctrl._tool_execution_coordinator = ToolExecutionCoordinator(
        ctrl,
        block_policy=ctrl._tool_attempt_coordinator,
    )
    return ctrl


def _approve_pending(ctrl, pending) -> None:
    request = AgentConfirmationRequest.for_action(
        command_name=pending.command_name,
        params=pending.params,
        action_label="Test action",
        description="Test action",
        destructive=False,
        publication_generation=pending.context.generation,
    )
    ctrl.pending_interactions.begin_confirmation(pending, request)
    ctrl.on_user_confirmation_resolved(
        AgentConfirmationResolution.for_request(
            request,
            status=AgentConfirmationResolutionStatus.APPROVED,
        )
    )


class TestControllerChunkBuffer:
    """Cover _on_chunk_received buffering."""

    def test_short_response_buffered(self):
        ctrl = _make_ctrl()
        ctrl._active_generation_id = 1
        ctrl._on_chunk_received(1, "Hi")
        assert ctrl.current_response == "Hi"
        ctrl.generation_event.emit.assert_called_once_with(
            AssistantGenerationEvent(
                generation_id=1,
                phase=AssistantGenerationEventPhase.CHUNK,
                text="Hi",
            )
        )


class TestControllerBrokenJsonRetry:
    """Cover strict product-envelope retry orchestration."""

    def test_broken_json_triggers_retry(self):
        ctrl = _make_ctrl()
        broken = '```json\n{"command": "load_data"'
        from XBrainLab.llm.agent.parser import CommandParser

        result = ctrl._handle_tool_envelope_failure(
            broken,
            CommandParser.parse_product(broken),
        )
        assert result is True
        assert ctrl._retry_count == 1
        ctrl.generation_event.emit.assert_not_called()
        request = ctrl.sig_generate.emit.call_args.args[0]
        assert request.generation_id == 1

    def test_plain_text_at_action_boundary_triggers_retry(self):
        ctrl = _make_ctrl()
        from XBrainLab.llm.agent.parser import CommandParser

        result = ctrl._handle_tool_envelope_failure(
            "response",
            CommandParser.parse_product("response"),
        )
        assert result is True
        assert ctrl._retry_count == 1
        ctrl.generation_event.emit.assert_not_called()


class TestControllerToolExecution:
    """Cover _execute_tool_no_loop and _process_tool_calls."""

    def test_execute_success(self):
        ctrl = _make_ctrl()
        mock_tool = MagicMock()
        mock_tool.execute.return_value = ToolResult(True, "Done")
        ctrl.registry.get_tool.return_value = mock_tool

        outcome = ctrl._execute_tool_no_loop(
            "list_files",
            {},
            context=_allowed_context("list_files"),
        )
        result = outcome.result
        assert outcome.success is True
        assert result.ok is True
        assert result.command_name == "list_files"
        assert result.message == "Done"

    def test_execute_gated(self):
        ctrl = _make_ctrl()
        mock_tool = MagicMock()
        ctrl.registry.get_tool.return_value = mock_tool

        outcome = ctrl._execute_tool_no_loop(
            "load_data",
            {},
            context=_blocked_context("load_data", "no raw data"),
        )
        result = outcome.result
        assert outcome.success is False
        assert result.ok is False
        assert result.command_name == "load_data"
        assert result.blocked_reason == "no raw data"

    def test_execute_unknown_tool(self):
        ctrl = _make_ctrl()
        ctrl.registry.get_tool.return_value = None

        outcome = ctrl._execute_tool_no_loop("nonexistent", {})
        assert outcome.success is False
        assert "unavailable" in outcome.result.message


class TestControllerFinalizeTurn:
    """Cover _finalize_turn."""

    def test_finalize_sets_ready(self):
        ctrl = _make_ctrl()
        ctrl._finalize_turn("Final response text")
        assert ctrl.is_processing is False
        ctrl.status_update.emit.assert_called_with("Ready")
        ctrl.processing_finished.emit.assert_called_once()


class TestControllerToolResultLogic:
    """Cover _handle_tool_result_logic."""

    def test_structured_success_does_not_emit_failure_message(self):
        ctrl = _make_ctrl()
        result = ctrl._handle_tool_result_logic(
            ToolCommandResult(
                ok=True,
                tool_name="query_state",
                message="State ready.",
            ),
            True,
        )
        assert result is False

    def test_request_switch_panel(self):
        ctrl = _make_ctrl()
        result = ctrl._handle_tool_result_logic(
            UiRequest(UiRequestKind.SWITCH_PANEL, {"panel": "training"}),
            True,
        )
        assert result is True
        ctrl.panel_navigation_requested.emit.assert_called_once()


class TestControllerConfirmation:
    """Cover on_user_confirmed paths."""

    def test_approved_success(self):
        ctrl = _make_ctrl()
        from XBrainLab.llm.agent.tool_attempt_coordinator import (
            ToolAttemptAction,
            ToolAttemptDecision,
        )

        pending = ToolAttemptDecision(
            ToolAttemptAction.CONFIRMATION_REQUIRED,
            "load_data",
            {"paths": ["/a"]},
            context=_allowed_context("load_data"),
        )
        ctrl._finalize_turn_after_tool = MagicMock()
        mock_tool = MagicMock()
        mock_tool.execute.return_value = ToolResult(True, "OK")
        ctrl.registry.get_tool.return_value = mock_tool

        _approve_pending(ctrl, pending)
        ctrl._finalize_turn_after_tool.assert_called_once()

    def test_approved_failure_max_retries(self):
        ctrl = _make_ctrl()
        from XBrainLab.llm.agent.tool_attempt_coordinator import (
            ToolAttemptAction,
            ToolAttemptDecision,
        )

        pending = ToolAttemptDecision(
            ToolAttemptAction.CONFIRMATION_REQUIRED,
            "load_data",
            {"paths": ["/a"]},
            context=_blocked_context("load_data", "gated"),
        )
        ctrl._finalize_turn_after_tool = MagicMock()
        ctrl._tool_failure_count = 2

        mock_tool = MagicMock()
        ctrl.registry.get_tool.return_value = mock_tool

        _approve_pending(ctrl, pending)
        ctrl._finalize_turn_after_tool.assert_called_once()


class TestControllerClose:
    """Cover close() RAG cleanup."""

    def test_close_with_rag(self):
        ctrl = _make_ctrl()
        ctrl._rag_lifecycle = MagicMock()
        ctrl._rag_lifecycle.close.return_value = True
        ctrl.worker_thread = MagicMock()
        ctrl.worker = MagicMock()
        ctrl.close()
        ctrl._rag_lifecycle.close.assert_called_once()

    def test_close_without_rag(self):
        ctrl = _make_ctrl()
        ctrl.worker_thread = MagicMock()
        ctrl.worker = MagicMock()
        # rag_retriever not set — hasattr returns False
        ctrl.close()

    def test_non_qobject_worker_retry_and_idempotent_close(self):
        ctrl = _make_ctrl()
        terminals: list[tuple[bool, str]] = []
        ctrl.shutdown_finished.connect(
            lambda ok, message: terminals.append((ok, message))
        )
        ctrl._rag_lifecycle = MagicMock()
        ctrl._rag_lifecycle.close.return_value = True

        class _WorkerDouble:
            def __init__(self) -> None:
                self.calls = 0

            def shutdown(self, *, wait_ms: int) -> bool:
                assert wait_ms > 0
                self.calls += 1
                return self.calls >= 2

        class _ThreadDouble:
            def __init__(self) -> None:
                self.quit_calls = 0

            def quit(self) -> None:
                self.quit_calls += 1

        worker = _WorkerDouble()
        thread = _ThreadDouble()
        ctrl.worker = worker
        ctrl.worker_thread = thread

        assert ctrl.close() is False
        assert ctrl.shutdown_in_progress is True
        assert ctrl.close() is True
        assert ctrl.close() is True

        assert worker.calls == 2
        assert thread.quit_calls == 1
        ctrl._rag_lifecycle.close.assert_called_once_with()
        assert terminals == [(True, "")]


class TestControllerProcessToolCalls:
    """Cover controller presentation after a typed loop-policy decision."""

    def test_loop_decision_is_presented_without_execution(self):
        from XBrainLab.llm.agent.tool_attempt_coordinator import (
            ToolAttemptAction,
            ToolAttemptDecision,
        )

        ctrl = _make_ctrl()
        ctrl._evaluate_tool_proposal = MagicMock(
            return_value=ToolAttemptDecision(
                ToolAttemptAction.LOOP,
                "load_data",
                {"paths": ["/a"]},
            )
        )
        ctrl._handle_loop_detected = MagicMock()
        ctrl._execute_tool_attempt = MagicMock()

        ctrl._process_tool_calls([("load_data", {"paths": ["/a"]})], "response")

        ctrl._handle_loop_detected.assert_called_once_with("load_data")
        ctrl._execute_tool_attempt.assert_not_called()
