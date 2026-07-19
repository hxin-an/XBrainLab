"""Coverage tests for AgentWorker and GenerationThread."""

from unittest.mock import MagicMock, patch

from XBrainLab.llm.agent.turn import (
    AssistantGenerationRequest,
    AssistantGenerationStopAcknowledgement,
    AssistantGenerationStopRequest,
    AssistantResponseContract,
)
from XBrainLab.llm.tools.result_contract import SAFE_UNEXPECTED_FAILURE_MESSAGE


def _request(
    text: str = "hi",
    *,
    generation_id: int = 1,
) -> AssistantGenerationRequest:
    request = AssistantGenerationRequest.from_messages(
        [{"role": "user", "content": text}],
        response_contract=AssistantResponseContract.STRUCTURED_ACTION,
    )
    return request.correlated(generation_id)


class TestGenerationThread:
    """Cover GenerationThread.__init__ and run()."""

    def test_init(self):
        from XBrainLab.llm.agent.worker import GenerationThread

        engine = MagicMock()
        request = _request()
        gt = GenerationThread(engine, request)
        assert gt.engine is engine
        assert gt.request is request

    def test_run_success(self):
        from XBrainLab.llm.agent.worker import GenerationThread

        engine = MagicMock()
        engine.generate_stream.return_value = iter(["chunk1", "chunk2"])
        request = _request()
        gt = GenerationThread(engine, request)
        gt.chunk_received = MagicMock()
        gt.finished_generation = MagicMock()
        gt.isInterruptionRequested = MagicMock(return_value=False)
        gt.run()
        engine.generate_stream.assert_called_once_with(
            request.to_model_messages(),
            profile=request.generation_profile,
        )
        assert gt.chunk_received.emit.call_count == 2
        gt.finished_generation.emit.assert_called_once()

    def test_run_error(self):
        from XBrainLab.llm.agent.worker import GenerationThread

        engine = MagicMock()
        engine.generate_stream.side_effect = RuntimeError("boom")
        gt = GenerationThread(engine, _request())
        gt.error_occurred = MagicMock()
        gt.run()
        gt.error_occurred.emit.assert_called_once()
        message = gt.error_occurred.emit.call_args.args[0]
        assert message == SAFE_UNEXPECTED_FAILURE_MESSAGE
        assert "boom" not in message


class TestAgentWorkerCleanup:
    """Cover _cleanup_generation_thread."""

    def test_cleanup_retains_ownership_while_thread_is_running(self):
        from XBrainLab.llm.agent.worker import AgentWorker

        worker = AgentWorker()
        mock_thread = MagicMock()
        mock_thread.isRunning.return_value = True
        worker.generation_thread = mock_thread
        stopped = worker._cleanup_generation_thread()
        mock_thread.requestInterruption.assert_called_once()
        assert stopped is False
        assert worker.generation_thread is mock_thread

    def test_finished_thread_releases_worker_ownership(self):
        from XBrainLab.llm.agent.worker import ACTIVE_GENERATION_THREADS, AgentWorker

        worker = AgentWorker()
        mock_thread = MagicMock()
        worker.generation_thread = mock_thread
        ACTIVE_GENERATION_THREADS.add(mock_thread)

        worker._release_generation_thread(mock_thread)

        assert worker.generation_thread is None
        assert mock_thread not in ACTIVE_GENERATION_THREADS

    def test_finished_thread_does_not_repeat_backend_cancellation(self):
        from XBrainLab.llm.agent.worker import AgentWorker

        worker = AgentWorker()
        worker.engine = MagicMock()
        worker.generation_stop_finished = MagicMock()
        mock_thread = MagicMock()
        worker.generation_thread = mock_thread
        worker._active_generation_id = 7
        worker._generation_thread_id = 7
        worker._cancel_pending = True
        worker._pending_stop_request = AssistantGenerationStopRequest(
            generation_id=7,
        )

        worker._release_generation_thread(mock_thread)

        worker.engine.cancel_generation.assert_not_called()
        worker.generation_stop_finished.emit.assert_called_once_with(
            AssistantGenerationStopAcknowledgement(
                generation_id=7,
                stopped=True,
            )
        )

    def test_cancel_waits_for_finished_acknowledgement(self):
        from XBrainLab.llm.agent.worker import AgentWorker

        worker = AgentWorker()
        worker.timeout_timer = MagicMock()
        worker.generation_stop_finished = MagicMock()
        mock_thread = MagicMock()
        mock_thread.isRunning.return_value = True
        mock_thread.wait.return_value = False
        worker.generation_thread = mock_thread
        worker._active_generation_id = 7
        worker._generation_thread_id = 7
        stop_request = AssistantGenerationStopRequest(generation_id=7)

        worker.cancel_generation(stop_request)

        worker.timeout_timer.stop.assert_called_once()
        worker.generation_stop_finished.emit.assert_called_once_with(
            AssistantGenerationStopAcknowledgement(
                generation_id=7,
                stopped=False,
            )
        )
        assert worker.generation_thread is mock_thread
        worker._release_generation_thread(mock_thread)
        assert worker.generation_stop_finished.emit.call_args_list[-1].args == (
            AssistantGenerationStopAcknowledgement(
                generation_id=7,
                stopped=True,
            ),
        )

    def test_shutdown_waits_for_generation_and_closes_engine(self):
        from XBrainLab.llm.agent.worker import AgentWorker

        worker = AgentWorker()
        engine = MagicMock()
        worker.engine = engine
        worker.timeout_timer = MagicMock()
        mock_thread = MagicMock()
        mock_thread.isRunning.return_value = True
        mock_thread.wait.return_value = True
        worker.generation_thread = mock_thread

        worker.shutdown(wait_ms=250)

        worker.timeout_timer.stop.assert_called_once()
        engine.cancel_generation.assert_called_once_with(wait_timeout=0.25)
        mock_thread.requestInterruption.assert_called_once()
        mock_thread.wait.assert_called_once_with(250)
        engine.close.assert_called_once()
        assert worker.engine is None
        assert worker.generation_thread is None


class TestAgentWorkerGenerate:
    """Cover generate_from_messages paths."""

    def test_no_engine_emits_correlated_generation_error(self):
        from XBrainLab.llm.agent.worker import AgentWorker

        worker = AgentWorker()
        worker.error = MagicMock()
        worker.generation_error = MagicMock()
        # Make initialize_agent a no-op (engine stays None)
        worker.initialize_agent = MagicMock()
        worker.generate_from_messages(_request("test", generation_id=11))
        worker.error.emit.assert_not_called()
        worker.generation_error.emit.assert_called_once_with(
            11,
            "Failed to initialize LLM engine.",
        )

    @patch("XBrainLab.llm.agent.worker.LLMConfig")
    @patch("XBrainLab.llm.agent.worker.GenerationThread")
    def test_user_message_logs_size_without_prompt_content(
        self,
        mock_gt_cls,
        mock_config,
    ):
        from XBrainLab.llm.agent.worker import AgentWorker

        worker = AgentWorker()
        worker.engine = MagicMock()
        worker.engine.config = MagicMock()
        worker.engine.config.inference_mode = "local"
        worker.engine.config.timeout = 60
        worker.log = MagicMock()
        worker.error = MagicMock()

        mock_config.load_from_file.return_value = None

        mock_thread = MagicMock()
        mock_gt_cls.return_value = mock_thread

        long_msg = "SECRET_EEG_SUBJECT_42_" + "x" * 100
        with patch("XBrainLab.llm.agent.worker.logger") as mock_logger:
            worker.generate_from_messages(_request(long_msg))

        worker.log.emit.assert_called()
        mock_logger.info.assert_called_once_with(
            "Agent generation requested (message_chars=%s)",
            len(long_msg),
        )
        generation_thread = worker.generation_thread
        assert generation_thread is not None
        worker._release_generation_thread(generation_thread)


class TestAgentWorkerTimeout:
    """Cover _on_timeout."""

    def test_timeout_sets_flag_then_emits_after_thread_exit(self):
        from XBrainLab.llm.agent.worker import AgentWorker

        worker = AgentWorker()
        worker.error = MagicMock()
        worker.generation_finished = MagicMock()
        worker.generation_error = MagicMock()
        mock_thread = MagicMock()
        mock_thread.isRunning.return_value = True
        worker.generation_thread = mock_thread
        worker._active_generation_id = 12
        worker._is_timed_out = False

        worker._on_timeout()

        assert worker._is_timed_out is True
        worker.error.emit.assert_not_called()
        worker.generation_error.emit.assert_not_called()
        worker.generation_finished.emit.assert_not_called()
        assert worker.generation_thread is mock_thread

        worker._release_generation_thread(mock_thread)

        worker.error.emit.assert_not_called()
        worker.generation_error.emit.assert_called_once_with(
            12,
            "Error: Generation timed out (Local LLM is too slow).",
        )
        worker.generation_finished.emit.assert_not_called()
