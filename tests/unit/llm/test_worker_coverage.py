"""Coverage tests for AgentWorker and GenerationThread."""

from unittest.mock import MagicMock, patch

import pytest


class TestGenerationThread:
    """Cover GenerationThread.__init__ and run()."""

    @pytest.fixture(autouse=True)
    def _patch_qapp(self):
        with patch("XBrainLab.llm.agent.worker.QApplication"):
            yield

    def test_init(self):
        from XBrainLab.llm.agent.worker import GenerationThread

        engine = MagicMock()
        messages = [{"role": "user", "content": "hi"}]
        gt = GenerationThread(engine, messages)
        assert gt.engine is engine
        assert gt.messages is messages

    def test_run_success(self):
        from XBrainLab.llm.agent.worker import GenerationThread

        engine = MagicMock()
        engine.generate_stream.return_value = iter(["chunk1", "chunk2"])
        gt = GenerationThread(engine, [])
        gt.chunk_received = MagicMock()
        gt.finished_generation = MagicMock()
        gt.isInterruptionRequested = MagicMock(return_value=False)
        gt.run()
        assert gt.chunk_received.emit.call_count == 2
        gt.finished_generation.emit.assert_called_once()

    def test_run_error(self):
        from XBrainLab.llm.agent.worker import GenerationThread

        engine = MagicMock()
        engine.generate_stream.side_effect = RuntimeError("boom")
        gt = GenerationThread(engine, [])
        gt.error_occurred = MagicMock()
        gt.run()
        gt.error_occurred.emit.assert_called_once()
        assert "boom" in gt.error_occurred.emit.call_args[0][0]


class TestAgentWorkerCleanup:
    """Cover _cleanup_generation_thread."""

    @pytest.fixture(autouse=True)
    def _patch_qapp(self):
        with patch("XBrainLab.llm.agent.worker.QApplication"):
            yield

    def test_cleanup_disconnects_signals(self):
        from XBrainLab.llm.agent.worker import AgentWorker

        worker = AgentWorker()
        mock_thread = MagicMock()
        mock_thread.isRunning.return_value = True
        worker.generation_thread = mock_thread
        worker._cleanup_generation_thread()
        mock_thread.requestInterruption.assert_called_once()
        assert worker.generation_thread is None


class TestAgentWorkerGenerate:
    """Cover generate_from_messages paths."""

    @pytest.fixture(autouse=True)
    def _patch_qapp(self):
        with patch("XBrainLab.llm.agent.worker.QApplication") as mock_app:
            mock_app.instance.return_value = None
            yield

    def test_no_engine_emits_error(self):
        from XBrainLab.llm.agent.worker import AgentWorker

        worker = AgentWorker()
        worker.error = MagicMock()
        worker.finished = MagicMock()
        # Make initialize_agent a no-op (engine stays None)
        worker.initialize_agent = MagicMock()
        worker.generate_from_messages([{"role": "user", "content": "test"}])
        worker.error.emit.assert_called_once()
        assert "Failed to initialize" in worker.error.emit.call_args[0][0]

    @patch("XBrainLab.llm.agent.worker.LLMConfig")
    @patch("XBrainLab.llm.agent.worker.GenerationThread")
    def test_user_message_truncation(self, mock_gt_cls, mock_config):
        from XBrainLab.llm.agent.worker import AgentWorker

        worker = AgentWorker()
        worker.engine = MagicMock()
        worker.engine.config = MagicMock()
        worker.engine.config.inference_mode = "gemini"
        worker.engine.config.timeout = 60
        worker.log = MagicMock()
        worker.chunk_received = MagicMock()
        worker.finished = MagicMock()
        worker.error = MagicMock()

        mock_config.load_from_file.return_value = None

        mock_thread = MagicMock()
        mock_gt_cls.return_value = mock_thread

        long_msg = "x" * 100
        worker.generate_from_messages([{"role": "user", "content": long_msg}])
        # Verify log truncation happened (log_text should be 50+3 chars)
        worker.log.emit.assert_called()

    @patch("XBrainLab.llm.agent.worker.LLMConfig")
    @patch("XBrainLab.llm.agent.worker.GenerationThread")
    def test_config_reload_from_file(self, mock_gt_cls, mock_config):
        from XBrainLab.llm.agent.worker import AgentWorker

        worker = AgentWorker()
        worker.engine = MagicMock()
        worker.engine.config.inference_mode = "gemini"
        worker.engine.config.timeout = 60
        worker.log = MagicMock()
        worker.chunk_received = MagicMock()
        worker.finished = MagicMock()
        worker.error = MagicMock()

        fresh = MagicMock()
        fresh.inference_mode = "gemini"
        fresh.active_mode = "gemini"
        mock_config.load_from_file.return_value = fresh

        mock_gt_cls.return_value = MagicMock()

        worker.generate_from_messages([{"role": "user", "content": "hello"}])
        # Config should have been applied
        assert worker.engine.config is fresh


class TestAgentWorkerTimeout:
    """Cover _on_timeout."""

    @pytest.fixture(autouse=True)
    def _patch_qapp(self):
        with patch("XBrainLab.llm.agent.worker.QApplication"):
            yield

    def test_timeout_sets_flag_and_emits(self):
        from XBrainLab.llm.agent.worker import AgentWorker

        worker = AgentWorker()
        worker.error = MagicMock()
        worker.finished = MagicMock()
        mock_thread = MagicMock()
        mock_thread.isRunning.return_value = True
        worker.generation_thread = mock_thread
        worker._is_timed_out = False

        worker._on_timeout()

        assert worker._is_timed_out is True
        worker.error.emit.assert_called_once()
        assert "timed out" in worker.error.emit.call_args[0][0]


class TestAgentWorkerReinitialize:
    """Cover reinitialize_agent paths."""

    @pytest.fixture(autouse=True)
    def _patch_qapp(self):
        with patch("XBrainLab.llm.agent.worker.QApplication"):
            yield

    def test_no_engine_returns_early(self):
        from XBrainLab.llm.agent.worker import AgentWorker

        worker = AgentWorker()
        worker.log = MagicMock()
        worker.reinitialize_agent("gemini")
        # Should not crash, just log warning and return

    def test_gemini_model_switch(self):
        from XBrainLab.llm.agent.worker import AgentWorker

        worker = AgentWorker()
        worker.engine = MagicMock()
        worker.engine.config = MagicMock()
        worker.log = MagicMock()
        worker.error = MagicMock()

        worker.reinitialize_agent("gemini-2.0-flash")
        worker.engine.switch_backend.assert_called_with("gemini")
        assert worker.engine.config.gemini_model_name == "gemini-2.0-flash"

    def test_gemini_generic_switch(self):
        from XBrainLab.llm.agent.worker import AgentWorker

        worker = AgentWorker()
        worker.engine = MagicMock()
        worker.engine.config = MagicMock()
        worker.log = MagicMock()
        worker.error = MagicMock()

        # generic "gemini" should NOT set gemini_model_name
        worker.reinitialize_agent("gemini")
        worker.engine.switch_backend.assert_called_with("gemini")
