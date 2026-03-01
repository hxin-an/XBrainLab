"""Coverage tests for LLMController — ReAct loop, tool execution, finalization."""

from collections import deque
from unittest.mock import MagicMock, patch


def _make_ctrl():
    """Create a LLMController stub that bypasses __init__ but has required attrs."""
    from PyQt6.QtCore import QObject

    from XBrainLab.llm.agent.controller import LLMController

    ctrl = LLMController.__new__(LLMController)
    # Call QObject.__init__ so that Qt internals are initialised (hasattr etc.)
    QObject.__init__(ctrl)
    # Provide the _conversation attribute so that the history property works
    conv = MagicMock()
    conv.messages = []
    ctrl._conversation = conv
    ctrl.metrics = MagicMock()
    ctrl.metrics.current_turn = MagicMock()
    ctrl.status_update = MagicMock()
    ctrl.chunk_received = MagicMock()
    ctrl.processing_finished = MagicMock()
    ctrl.remove_content = MagicMock()
    ctrl.sig_generate = MagicMock()
    ctrl.assembler = MagicMock()
    ctrl.generation_started = MagicMock()
    ctrl.response_ready = MagicMock()
    ctrl.request_user_interaction = MagicMock()
    ctrl.error_occurred = MagicMock()
    ctrl.current_response = ""
    ctrl._emitted_len = 0
    ctrl._is_buffering = False
    ctrl._retry_count = 0
    ctrl._max_retries = 3
    ctrl.is_processing = True
    ctrl._tool_failure_count = 0
    ctrl._max_tool_failures = 3
    ctrl._successful_tool_count = 0
    ctrl._max_successful_calls = 5
    ctrl._recent_tool_calls = deque(maxlen=10)
    ctrl._pending_confirmation = None
    ctrl._loop_break_count = 0
    ctrl._max_loop_breaks = 2
    ctrl.registry = MagicMock()
    ctrl.study = MagicMock()
    ctrl.verifier = MagicMock()
    return ctrl


class TestControllerChunkBuffer:
    """Cover _on_chunk_received buffering."""

    def test_short_response_buffered(self):
        ctrl = _make_ctrl()
        ctrl._on_chunk_received("Hi")
        # Response < 10 chars, should buffer (not emit)
        ctrl.chunk_received.emit.assert_not_called()


class TestControllerBrokenJsonRetry:
    """Cover _handle_json_broken_retry."""

    def test_broken_json_triggers_retry(self):
        ctrl = _make_ctrl()
        broken = '```json\n{"command": "load_data"'
        result = ctrl._handle_json_broken_retry(broken, None)
        assert result is True
        assert ctrl._retry_count == 1

    def test_valid_command_no_retry(self):
        ctrl = _make_ctrl()
        result = ctrl._handle_json_broken_retry("response", [("cmd", {})])
        assert result is False


class TestControllerToolExecution:
    """Cover _execute_tool_no_loop and _process_tool_calls."""

    @patch("XBrainLab.llm.agent.controller.compute_pipeline_stage")
    @patch("XBrainLab.llm.agent.controller.STAGE_CONFIG")
    def test_execute_success(self, mock_config, mock_stage):
        from XBrainLab.llm.agent.controller import PipelineStage

        ctrl = _make_ctrl()
        mock_stage.return_value = PipelineStage.EMPTY
        mock_config.get.return_value = {"tools": ["load_data"]}
        mock_tool = MagicMock()
        mock_tool.execute.return_value = "Done"
        ctrl.registry.get_tool.return_value = mock_tool

        success, result = ctrl._execute_tool_no_loop("load_data", {})
        assert success is True
        assert result == "Done"

    @patch("XBrainLab.llm.agent.controller.compute_pipeline_stage")
    @patch("XBrainLab.llm.agent.controller.STAGE_CONFIG")
    def test_execute_gated(self, mock_config, mock_stage):
        from XBrainLab.llm.agent.controller import PipelineStage

        ctrl = _make_ctrl()
        mock_stage.return_value = PipelineStage.EMPTY
        mock_config.get.return_value = {"tools": ["other_tool"]}
        mock_tool = MagicMock()
        ctrl.registry.get_tool.return_value = mock_tool

        success, result = ctrl._execute_tool_no_loop("load_data", {})
        assert success is False
        assert "not available" in result

    def test_execute_unknown_tool(self):
        ctrl = _make_ctrl()
        ctrl.registry.get_tool.return_value = None

        success, result = ctrl._execute_tool_no_loop("nonexistent", {})
        assert success is False
        assert "Unknown tool" in result


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

    def test_non_string_result(self):
        ctrl = _make_ctrl()
        result = ctrl._handle_tool_result_logic(12345, True)
        assert result is False

    def test_request_switch_panel(self):
        ctrl = _make_ctrl()
        result = ctrl._handle_tool_result_logic(
            "Request: Switch UI to 'training'", True
        )
        assert result is True
        ctrl.request_user_interaction.emit.assert_called_once()


class TestControllerConfirmation:
    """Cover on_user_confirmed paths."""

    @patch("XBrainLab.llm.agent.controller.compute_pipeline_stage")
    @patch("XBrainLab.llm.agent.controller.STAGE_CONFIG")
    def test_approved_success(self, mock_config, mock_stage):
        from XBrainLab.llm.agent.controller import PipelineStage

        ctrl = _make_ctrl()
        ctrl._pending_confirmation = ("load_data", {"paths": ["/a"]}, [])
        ctrl._finalize_turn_after_tool = MagicMock()

        mock_stage.return_value = PipelineStage.EMPTY
        mock_config.get.return_value = {"tools": ["load_data"]}
        mock_tool = MagicMock()
        mock_tool.execute.return_value = "OK"
        ctrl.registry.get_tool.return_value = mock_tool

        ctrl.on_user_confirmed(True)
        ctrl._finalize_turn_after_tool.assert_called_once()

    @patch("XBrainLab.llm.agent.controller.compute_pipeline_stage")
    @patch("XBrainLab.llm.agent.controller.STAGE_CONFIG")
    def test_approved_failure_max_retries(self, mock_config, mock_stage):
        from XBrainLab.llm.agent.controller import PipelineStage

        ctrl = _make_ctrl()
        ctrl._pending_confirmation = ("load_data", {"paths": ["/a"]}, [])
        ctrl._finalize_turn_after_tool = MagicMock()
        ctrl._tool_failure_count = 2

        mock_stage.return_value = PipelineStage.EMPTY
        mock_config.get.return_value = {"tools": []}  # gated
        mock_tool = MagicMock()
        ctrl.registry.get_tool.return_value = mock_tool

        ctrl.on_user_confirmed(True)
        ctrl._finalize_turn_after_tool.assert_called_once()


class TestControllerClose:
    """Cover close() RAG cleanup."""

    def test_close_with_rag(self):
        ctrl = _make_ctrl()
        ctrl.rag_retriever = MagicMock()
        ctrl.worker_thread = MagicMock()
        ctrl.worker = MagicMock()
        ctrl.close()
        ctrl.rag_retriever.close.assert_called_once()

    def test_close_without_rag(self):
        ctrl = _make_ctrl()
        ctrl.worker_thread = MagicMock()
        ctrl.worker = MagicMock()
        # rag_retriever not set — hasattr returns False
        ctrl.close()


class TestControllerProcessToolCalls:
    """Cover _process_tool_calls — loop detection and params serialization."""

    @patch("XBrainLab.llm.agent.controller.compute_pipeline_stage")
    @patch("XBrainLab.llm.agent.controller.STAGE_CONFIG")
    @patch("XBrainLab.llm.agent.controller.estimate_confidence", return_value=0.9)
    def test_loop_detection(self, mock_conf, mock_config, mock_stage):
        from XBrainLab.llm.agent.controller import PipelineStage

        ctrl = _make_ctrl()
        sig = ("load_data", '{"paths": ["/a"]}')
        ctrl._recent_tool_calls.extend([sig, sig])
        ctrl._loop_break_count = 0

        mock_validation = MagicMock()
        mock_validation.is_valid = True
        mock_validation.requires_confirmation = False
        ctrl.verifier.verify_tool_call.return_value = mock_validation

        mock_stage.return_value = PipelineStage.EMPTY
        mock_config.get.return_value = {"tools": ["load_data"]}
        mock_tool = MagicMock()
        mock_tool.execute.return_value = "ok"
        ctrl.registry.get_tool.return_value = mock_tool

        ctrl._process_tool_calls([("load_data", {"paths": ["/a"]})], "response")
