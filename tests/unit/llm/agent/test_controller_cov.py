"""Coverage tests for LLMController - targeting uncovered lines."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.llm.agent.request_admission import (
    UserRequestAdmission,
    UserRequestAdmissionAction,
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
    AssistantTurnRequest,
)
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.runtime_selection import AssistantRuntimeLaunchResolver
from XBrainLab.llm.tools.application_surface import ToolCommandResult
from XBrainLab.llm.tools.result_contract import ToolResult, UiRequest, UiRequestKind


def _tool_outcome(
    message: str,
    *,
    ok: bool = True,
    tool_name: str = "cmd",
    state: dict[str, object] | None = None,
) -> ToolExecutionOutcome:
    return ToolExecutionOutcome(
        ok,
        ToolCommandResult(
            ok=ok,
            tool_name=tool_name,
            message=message,
            error_type="none" if ok else "runtime",
            state=state,
        ),
    )


def _submit_user_turn(ctrl, text: str) -> AssistantTurnCorrelation:
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


def _allow_prompt_tools(ctrl):
    from XBrainLab.llm.agent.assembler import PromptToolPublication
    from XBrainLab.llm.tools.application_surface import (
        READ_ONLY_TOOLS,
        TOOL_TO_COMMAND,
        ToolAvailability,
        ToolAvailabilityContext,
    )

    source = MagicMock()
    source.get_context.side_effect = lambda tool_name: ToolAvailabilityContext(
        availability=ToolAvailability(tool_name=tool_name, enabled=True),
        state={"pipeline_stage": "empty"},
        generation=1,
    )
    ctrl._tool_attempt_coordinator._context_source = source
    ctrl._active_tool_publication = PromptToolPublication(
        tool_names=frozenset(
            set(TOOL_TO_COMMAND) | set(READ_ONLY_TOOLS) | {"cmd", "first"}
        ),
        backend_generation=1,
    )


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
        from XBrainLab.llm.agent.tool_attempt_coordinator import (
            ToolAttemptCoordinator,
        )
        from XBrainLab.llm.agent.tool_execution_coordinator import (
            ToolExecutionCoordinator,
        )

        study = MagicMock()

        # Construct through PyQt's normal QObject path before replacing signals.
        # ``__new__``-only fixtures do not establish a valid typed turn/signal host.
        signal_names = [
            "response_presentation_ready",
            "generation_event",
            "processing_finished",
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
            "workflow_ui_handoff_requested",
            "activity_changed",
        ]
        c = LLMController(study)
        for name in signal_names:
            setattr(c, name, MagicMock())
        c._active_tool_publication = MagicMock()
        c._active_tool_publication.permits.return_value = True
        c._request_admission.evaluate = MagicMock(
            return_value=UserRequestAdmission(
                UserRequestAdmissionAction.GENERATE,
            )
        )
        assert isinstance(c._tool_attempt_coordinator, ToolAttemptCoordinator)
        assert isinstance(c._tool_execution_coordinator, ToolExecutionCoordinator)
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
        _submit_user_turn(ctrl, "hi")
        assert len(ctrl.history) == 0

    def test_normal_flow(self, ctrl):
        ctrl.sig_rag_context_ready.emit.side_effect = ctrl._on_rag_context_ready
        ctrl._rag_lifecycle.retrieve = MagicMock(
            side_effect=lambda turn_id, text, callback, *, allowed_tool_names: (
                callback(turn_id, text, "", ""),
                True,
            )[1]
        )
        ctrl._generate_response = MagicMock()
        _submit_user_turn(ctrl, "do something")
        assert ctrl.is_processing
        assert len(ctrl.history) == 1
        ctrl._generate_response.assert_called_once()

    def test_rag_error_continues_generation_without_user_visible_error(self, ctrl):
        ctrl.sig_rag_context_ready.emit.side_effect = ctrl._on_rag_context_ready
        ctrl._rag_lifecycle.retrieve = MagicMock(
            side_effect=lambda turn_id, text, callback, *, allowed_tool_names: (
                callback(turn_id, text, "", "Qdrant exploded"),
                True,
            )[1]
        )
        ctrl._generate_response = MagicMock()
        _submit_user_turn(ctrl, "run analysis")
        ctrl._generate_response.assert_called_once()
        ctrl.error_occurred.emit.assert_not_called()
        assert ctrl.is_processing


# --- _on_chunk_received ---
class TestOnChunkReceived:
    def test_buffers_short_response(self, ctrl):
        ctrl.is_processing = True
        ctrl._active_generation_id = 11
        ctrl._on_chunk_received(11, "hi")
        assert ctrl.current_response == "hi"
        ctrl.generation_event.emit.assert_called_once_with(
            AssistantGenerationEvent(
                generation_id=11,
                phase=AssistantGenerationEventPhase.CHUNK,
                text="hi",
            )
        )

    def test_buffers_non_tool_until_generation_is_classified(self, ctrl):
        ctrl.is_processing = True
        ctrl._active_generation_id = 12
        ctrl.current_response = "a" * 10
        ctrl._on_chunk_received(12, " more text")
        assert ctrl.current_response.endswith(" more text")

    def test_buffers_tool_json(self, ctrl):
        ctrl.is_processing = True
        ctrl._active_generation_id = 13
        ctrl.current_response = '{"tool": "x"'
        ctrl._on_chunk_received(13, "}")
        assert ctrl.current_response == '{"tool": "x"}'

    def test_ignores_chunk_from_stale_generation(self, ctrl):
        ctrl.is_processing = True
        ctrl._active_generation_id = 14
        ctrl._on_chunk_received(13, "stale")
        assert ctrl.current_response == ""
        assert ctrl._active_generation_id == 14
        ctrl.generation_event.emit.assert_not_called()


# --- _on_generation_finished ---
class TestOnGenerationFinished:
    def test_no_command_finalizes(self, ctrl):
        ctrl._active_host_turn_id = 1
        ctrl._active_host_turn_generation = 1
        ctrl.current_response = "Just a regular reply, nothing special"
        ctrl._active_response_contract = AssistantResponseContract.NATURAL_LANGUAGE
        ctrl.is_processing = True
        ctrl._active_generation_id = 21
        ctrl._on_generation_finished(21, [])
        assert not ctrl.is_processing
        ctrl.generation_event.emit.assert_called_once_with(
            AssistantGenerationEvent(
                generation_id=21,
                phase=AssistantGenerationEventPhase.FINISHED,
            )
        )

    def test_broken_json_retries(self, ctrl):
        ctrl.current_response = '```json\n{"broken'
        ctrl._retry_count = 0
        ctrl.is_processing = True
        ctrl._active_generation_id = 22
        ctrl._generate_response = MagicMock()
        ctrl._on_generation_finished(22, [])
        ctrl._generate_response.assert_called_once()
        assert ctrl._retry_count == 1

    def test_stale_finish_does_not_close_active_generation(self, ctrl):
        ctrl.current_response = "active"
        ctrl.is_processing = True
        ctrl._active_generation_id = 24

        ctrl._on_generation_finished(23, [])

        assert ctrl.current_response == "active"
        assert ctrl._active_generation_id == 24
        assert ctrl.is_processing is True
        ctrl.generation_event.emit.assert_not_called()


# --- _handle_loop_detected ---
class TestHandleLoopDetected:
    def test_increments_break_count(self, ctrl):
        ctrl._generate_response = MagicMock()
        ctrl._handle_loop_detected("test_tool")
        assert ctrl._loop_break_count == 1
        ctrl._generate_response.assert_called_once()

    def test_aborts_after_max(self, ctrl):
        ctrl._active_host_turn_id = 1
        ctrl._active_host_turn_generation = 1
        ctrl._loop_break_count = 3
        ctrl._handle_loop_detected("test_tool")
        assert not ctrl.is_processing
        ctrl.processing_finished.emit.assert_called()


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
        outcome = ctrl._execute_tool_no_loop("get_dataset_info", {"a": 1})
        assert outcome.success
        assert outcome.result.message == "ok"

    def test_exception(self, ctrl):
        mock_tool = MagicMock()
        mock_tool.execute.side_effect = RuntimeError("fail")
        ctrl.registry.get_tool.return_value = mock_tool
        _allow_prompt_tools(ctrl)
        outcome = ctrl._execute_tool_no_loop("get_dataset_info", {})
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
        ctrl.panel_navigation_requested.emit.assert_called()

    def test_confirm_montage(self, ctrl):
        result = ctrl._handle_tool_result_logic(
            UiRequest(
                UiRequestKind.CONFIRM_MONTAGE,
                {"montage_name": "standard_1020"},
            )
        )
        assert result

    def test_failure_waits_for_host_retry_policy(self, ctrl):
        result = ctrl._handle_tool_result_logic(
            ToolCommandResult.failure("test", "some error"),
            success=False,
        )
        assert not result
        ctrl.response_presentation_ready.emit.assert_not_called()


# --- _process_tool_calls ---
class TestProcessToolCalls:
    def test_success_finalizes(self, ctrl):
        _allow_prompt_tools(ctrl)
        ctrl._execute_tool_no_loop = MagicMock(return_value=_tool_outcome("ok"))
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        ctrl._finalize_turn_after_tool = MagicMock()
        ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
        ctrl.registry.get_tool.return_value.requires_confirmation = False

        ctrl._process_tool_calls([("cmd", {"a": 1})], '{"cmd": "cmd"}')
        ctrl._finalize_turn_after_tool.assert_called_once()

    def test_failure_retries(self, ctrl):
        from XBrainLab.llm.agent.turn import AssistantTurnScope

        _allow_prompt_tools(ctrl)
        ctrl._active_turn_scope = AssistantTurnScope.GUIDED_WORKFLOW
        ctrl._execute_tool_no_loop = MagicMock(
            return_value=_tool_outcome(
                "err",
                ok=False,
                state=ApplicationStateSnapshot.empty().to_dict(),
            )
        )
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        ctrl._generate_response = MagicMock()
        ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
        ctrl.registry.get_tool.return_value.requires_confirmation = False

        ctrl._process_tool_calls([("cmd", {})], "json")
        ctrl._generate_response.assert_called_once()

    def test_max_failures_stops(self, ctrl):
        _allow_prompt_tools(ctrl)
        ctrl._tool_failure_count = 2
        ctrl._execute_tool_no_loop = MagicMock(
            return_value=_tool_outcome(
                "err",
                ok=False,
                state={"state_reliable": True},
            )
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
        ctrl._generate_response.assert_not_called()


# --- close ---
class TestClose:
    def test_close_stops_thread(self, ctrl):
        ctrl.worker_thread.isRunning.return_value = True
        ctrl.close()
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


# --- stop_generation ---
class TestStopGeneration:
    def test_stops_when_processing(self, ctrl):
        ctrl._active_host_turn_id = 1
        ctrl._active_host_turn_generation = 1
        ctrl._active_generation_id = 1
        ctrl.is_processing = True
        ctrl.stop_generation()
        assert ctrl.is_processing
        ctrl.worker.cancel_generation.assert_called_once_with(
            AssistantGenerationStopRequest(generation_id=1)
        )

        ctrl._on_generation_stop_finished(
            AssistantGenerationStopAcknowledgement(
                generation_id=1,
                stopped=True,
            )
        )

        assert not ctrl.is_processing


# --- set_model ---
class TestSetModel:
    def test_emits_reinit(self, ctrl):
        config = LLMConfig()
        config.local_backend_ready = lambda candidate=None: True  # type: ignore[method-assign]
        config.local_backend_status_message = (  # type: ignore[method-assign]
            lambda candidate=None: "Local runtime ready."
        )
        spec = AssistantRuntimeLaunchResolver().resolve(config).launch_spec
        assert spec is not None

        ctrl.set_model(spec)

        ctrl.sig_reinit.emit.assert_called_once_with(spec)


# --- reset_conversation ---
class TestResetConversation:
    def test_clears_state(self, ctrl):
        ctrl.history = [{"role": "user", "content": "hi"}]
        ctrl._retry_count = 5
        ctrl.reset_conversation()
        assert ctrl.history == []
        assert ctrl._retry_count == 0
        ctrl.assembler.clear_context.assert_called()


# --- execute_debug_tool ---
class TestExecuteDebugTool:
    def test_records_and_executes(self, ctrl):
        request = AssistantDebugToolRequest.from_params(
            correlation=AssistantTurnCorrelation(generation=1, turn_id=1),
            tool_name="test",
            params={"k": "v"},
        )
        ctrl._execute_tool_no_loop = MagicMock(return_value=_tool_outcome("done"))
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        ctrl.execute_debug_tool(request)
        assert not ctrl.is_processing
        assert len(ctrl.history) == 2
        assert ctrl.response_presentation_ready.emit.call_count == 2
