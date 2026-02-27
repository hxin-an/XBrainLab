"""Coverage tests for LLMController - targeting uncovered lines."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


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

    Instead of ``__new__`` + manual attribute assignment, we pre-mock
    the Qt signals on the raw instance and then let ``__init__`` run
    (with ``QObject.__init__`` patched to a no-op).  This ensures all
    attributes are set through the real constructor so the fixture
    stays in sync with production code automatically.
    """
    from PyQt6.QtCore import QObject

    with (
        patch("XBrainLab.llm.agent.controller.ToolRegistry"),
        patch("XBrainLab.llm.agent.controller.ContextAssembler"),
        patch("XBrainLab.llm.agent.controller.VerificationLayer"),
        patch("XBrainLab.llm.agent.controller.RAGRetriever"),
        patch("XBrainLab.llm.agent.controller.QThread"),
        patch("XBrainLab.llm.agent.controller.AgentWorker"),
        patch("XBrainLab.llm.agent.controller.AVAILABLE_TOOLS", []),
        patch.object(QObject, "__init__", lambda self: None),
    ):
        from XBrainLab.llm.agent.controller import LLMController

        study = MagicMock()

        # Pre-set signal mocks on the class so __init__ can .connect() them
        signal_names = [
            "response_ready",
            "chunk_received",
            "generation_started",
            "processing_finished",
            "status_update",
            "error_occurred",
            "request_user_interaction",
            "remove_content",
            "sig_initialize",
            "sig_generate",
            "sig_reinit",
        ]
        c = LLMController.__new__(LLMController)
        for name in signal_names:
            setattr(c, name, MagicMock())
        LLMController.__init__(c, study)
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
        ctrl.handle_user_input("   ")
        assert not ctrl.is_processing

    def test_ignores_when_busy(self, ctrl):
        ctrl.is_processing = True
        ctrl.handle_user_input("hi")
        assert len(ctrl.history) == 0

    def test_normal_flow(self, ctrl):
        ctrl.rag_retriever.get_similar_examples.return_value = []
        ctrl._generate_response = MagicMock()
        ctrl.handle_user_input("do something")
        assert ctrl.is_processing
        assert len(ctrl.history) == 1
        ctrl._generate_response.assert_called_once()

    def test_exception_emits_error(self, ctrl):
        ctrl.rag_retriever.get_similar_examples.side_effect = RuntimeError("boom")
        ctrl.handle_user_input("hi")
        ctrl.error_occurred.emit.assert_called()
        assert not ctrl.is_processing


# --- _on_chunk_received ---
class TestOnChunkReceived:
    def test_buffers_short_response(self, ctrl):
        ctrl._on_chunk_received("hi")
        assert ctrl.current_response == "hi"

    def test_streams_non_tool(self, ctrl):
        ctrl.current_response = "a" * 10
        ctrl._emitted_len = 10
        ctrl._on_chunk_received(" more text")
        ctrl.chunk_received.emit.assert_called_once_with(" more text")

    def test_buffers_tool_json(self, ctrl):
        ctrl.current_response = '{"tool": "x"}'
        ctrl._emitted_len = 0
        ctrl._on_chunk_received("")
        assert ctrl._is_buffering


# --- _on_generation_finished ---
class TestOnGenerationFinished:
    def test_no_command_finalizes(self, ctrl):
        ctrl.current_response = "Just a regular reply, nothing special"
        ctrl._emitted_len = 0
        with patch("XBrainLab.llm.agent.controller.CommandParser") as MockParser:
            MockParser.parse.return_value = None
            ctrl._on_generation_finished()
        assert not ctrl.is_processing

    def test_broken_json_retries(self, ctrl):
        ctrl.current_response = '```json\n{"broken'
        ctrl._emitted_len = 0
        ctrl._retry_count = 0
        ctrl._generate_response = MagicMock()
        with patch("XBrainLab.llm.agent.controller.CommandParser") as MockParser:
            MockParser.parse.return_value = None
            ctrl._on_generation_finished()
        ctrl._generate_response.assert_called_once()
        assert ctrl._retry_count == 1


# --- _detect_loop ---
class TestDetectLoop:
    def test_no_loop(self, ctrl):
        assert not ctrl._detect_loop(("cmd", "{}"))

    def test_detects_loop(self, ctrl):
        sig = ("cmd", "{}")
        for _ in range(3):
            ctrl._recent_tool_calls.append(sig)
        assert ctrl._detect_loop(sig)


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
        assert not ctrl.is_processing
        ctrl.processing_finished.emit.assert_called()


# --- _execute_tool_no_loop ---
class TestExecuteToolNoLoop:
    def test_unknown_tool(self, ctrl):
        ctrl.registry.get_tool.return_value = None
        success, result = ctrl._execute_tool_no_loop("bogus", {})
        assert not success
        assert "Unknown" in result

    def test_success(self, ctrl):
        mock_tool = MagicMock()
        mock_tool.execute.return_value = "ok"
        ctrl.registry.get_tool.return_value = mock_tool
        with patch(
            "XBrainLab.llm.agent.controller.compute_pipeline_stage",
        ) as mock_stage:
            mock_stage.return_value = MagicMock(value="empty")
            with patch(
                "XBrainLab.llm.agent.controller.STAGE_CONFIG",
                {mock_stage.return_value: {"tools": ["test"]}},
            ):
                success, result = ctrl._execute_tool_no_loop("test", {"a": 1})
        assert success
        assert result == "ok"

    def test_exception(self, ctrl):
        mock_tool = MagicMock()
        mock_tool.execute.side_effect = RuntimeError("fail")
        ctrl.registry.get_tool.return_value = mock_tool
        with patch(
            "XBrainLab.llm.agent.controller.compute_pipeline_stage",
        ) as mock_stage:
            mock_stage.return_value = MagicMock(value="empty")
            with patch(
                "XBrainLab.llm.agent.controller.STAGE_CONFIG",
                {mock_stage.return_value: {"tools": ["test"]}},
            ):
                success, result = ctrl._execute_tool_no_loop("test", {})
        assert not success
        assert "fail" in result


# --- _handle_tool_result_logic ---
class TestHandleToolResultLogic:
    def test_switch_panel(self, ctrl):
        result = ctrl._handle_tool_result_logic(
            "Request: Switch UI to 'visualization' (View: 3d_plot)"
        )
        assert result
        ctrl.request_user_interaction.emit.assert_called()

    def test_confirm_montage(self, ctrl):
        result = ctrl._handle_tool_result_logic(
            "Request: confirm_montage 'standard_1020'"
        )
        assert result

    def test_failure_emits_error(self, ctrl):
        result = ctrl._handle_tool_result_logic("some error", success=False)
        assert not result
        ctrl.response_ready.emit.assert_called()


# --- _process_tool_calls ---
class TestProcessToolCalls:
    def test_success_finalizes(self, ctrl):
        ctrl._execute_tool_no_loop = MagicMock(return_value=(True, "ok"))
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        ctrl._finalize_turn_after_tool = MagicMock()
        ctrl._detect_loop = MagicMock(return_value=False)
        ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
        ctrl.registry.get_tool.return_value.requires_confirmation = False

        ctrl._process_tool_calls([("cmd", {"a": 1})], '{"cmd": "cmd"}')
        ctrl._finalize_turn_after_tool.assert_called_once()

    def test_failure_retries(self, ctrl):
        ctrl._execute_tool_no_loop = MagicMock(return_value=(False, "err"))
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        ctrl._generate_response = MagicMock()
        ctrl._detect_loop = MagicMock(return_value=False)
        ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
        ctrl.registry.get_tool.return_value.requires_confirmation = False

        ctrl._process_tool_calls([("cmd", {})], "json")
        ctrl._generate_response.assert_called_once()

    def test_max_failures_stops(self, ctrl):
        ctrl._tool_failure_count = 2
        ctrl._execute_tool_no_loop = MagicMock(return_value=(False, "err"))
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        ctrl._finalize_turn_after_tool = MagicMock()
        ctrl._detect_loop = MagicMock(return_value=False)
        ctrl.verifier.verify_tool_call.return_value = MagicMock(is_valid=True)
        ctrl.registry.get_tool.return_value.requires_confirmation = False

        ctrl._process_tool_calls([("cmd", {})], "json")
        ctrl._finalize_turn_after_tool.assert_called_once()

    def test_verification_rejected(self, ctrl):
        ctrl._detect_loop = MagicMock(return_value=False)
        ctrl.verifier.verify_tool_call.return_value = MagicMock(
            is_valid=False, error_message="bad call"
        )
        ctrl._generate_response = MagicMock()
        ctrl._process_tool_calls([("cmd", {})], "json")
        ctrl._generate_response.assert_called_once()


# --- close ---
class TestClose:
    def test_close_stops_thread(self, ctrl):
        ctrl.worker_thread.isRunning.return_value = True
        ctrl.close()
        ctrl.worker_thread.quit.assert_called_once()
        ctrl.worker_thread.wait.assert_called_once()

    def test_close_rag_error_ignored(self, ctrl):
        ctrl.rag_retriever.close.side_effect = RuntimeError("x")
        ctrl.worker_thread.isRunning.return_value = False
        ctrl.close()  # Should not raise


# --- stop_generation ---
class TestStopGeneration:
    def test_stops_when_processing(self, ctrl):
        ctrl.is_processing = True
        ctrl.worker.generation_thread = MagicMock()
        ctrl.worker.generation_thread.isRunning.return_value = True
        ctrl.stop_generation()
        assert not ctrl.is_processing
        ctrl.worker.generation_thread.requestInterruption.assert_called()


# --- set_model ---
class TestSetModel:
    def test_emits_reinit(self, ctrl):
        ctrl.set_model("Gemini")
        ctrl.sig_reinit.emit.assert_called_once_with("Gemini")


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
        ctrl._execute_tool_no_loop = MagicMock(return_value=(True, "done"))
        ctrl._handle_tool_result_logic = MagicMock(return_value=False)
        ctrl.execute_debug_tool("test", {"k": "v"})
        assert not ctrl.is_processing
        assert len(ctrl.history) == 2
        ctrl.response_ready.emit.assert_called()
