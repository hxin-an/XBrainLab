"""Coverage tests for AgentWorker & GenerationThread."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def worker():
    """Return an AgentWorker with mocked Qt signals."""
    from XBrainLab.llm.agent.worker import AgentWorker

    w = AgentWorker.__new__(AgentWorker)
    w.engine = None
    w.generation_thread = None
    w.finished = MagicMock()
    w.chunk_received = MagicMock()
    w.error = MagicMock()
    w.log = MagicMock()
    return w


class TestInitializeAgent:
    def test_noop_if_already_initialized(self, worker):
        worker.engine = MagicMock()
        worker.initialize_agent()
        worker.log.emit.assert_not_called()

    def test_loads_model(self, worker):
        with (
            patch("XBrainLab.llm.agent.worker.LLMConfig") as MockCfg,
            patch("XBrainLab.llm.agent.worker.LLMEngine") as MockEng,
        ):
            cfg = MockCfg.return_value
            cfg.model_name = "test-model"
            engine = MockEng.return_value
            worker.initialize_agent()
            engine.load_model.assert_called_once()
            assert worker.engine is engine

    def test_error_on_failure(self, worker):
        with (
            patch("XBrainLab.llm.agent.worker.LLMConfig"),
            patch(
                "XBrainLab.llm.agent.worker.LLMEngine",
                side_effect=RuntimeError("boom"),
            ),
        ):
            worker.initialize_agent()
            worker.error.emit.assert_called_once()


class TestGenerateFromMessages:
    def test_initializes_if_needed(self, worker):
        worker.initialize_agent = MagicMock()
        worker.generate_from_messages([{"role": "user", "content": "hi"}])
        worker.initialize_agent.assert_called_once()

    def test_starts_thread(self, worker):
        engine = MagicMock()
        engine.config = MagicMock()
        engine.config.timeout = 30
        engine.config.inference_mode = "local"
        worker.engine = engine

        with (
            patch("XBrainLab.llm.agent.worker.GenerationThread") as MockGT,
            patch("XBrainLab.llm.agent.worker.QTimer") as MockTimer,
            patch("XBrainLab.llm.agent.worker.LLMConfig") as MockCfg,
        ):
            MockCfg.load_from_file.return_value = None
            gt = MockGT.return_value
            timer = MockTimer.return_value
            msgs = [{"role": "user", "content": "test"}]
            worker.generate_from_messages(msgs)
            gt.start.assert_called_once()
            timer.start.assert_called_once_with(30000)

    def test_syncs_config_and_switches_backend(self, worker):
        engine = MagicMock()
        engine.config = MagicMock()
        engine.config.inference_mode = "local"
        engine.config.timeout = 60
        worker.engine = engine

        fresh = MagicMock()
        fresh.inference_mode = "gemini"

        with (
            patch("XBrainLab.llm.agent.worker.GenerationThread"),
            patch("XBrainLab.llm.agent.worker.QTimer"),
            patch("XBrainLab.llm.agent.worker.LLMConfig") as MockCfg,
        ):
            MockCfg.load_from_file.return_value = fresh
            msgs = [{"role": "user", "content": "test"}]
            worker.generate_from_messages(msgs)
            engine.switch_backend.assert_called_once_with("gemini")


class TestOnTimeout:
    def test_emits_error(self, worker):
        gt = MagicMock()
        gt.isRunning.return_value = True
        worker.generation_thread = gt
        worker._is_timed_out = False
        worker._on_timeout()
        assert worker._is_timed_out
        worker.error.emit.assert_called_once()
        worker.finished.emit.assert_called_once_with([])

    def test_already_stopped_noop(self, worker):
        gt = MagicMock()
        gt.isRunning.return_value = False
        worker.generation_thread = gt
        worker._is_timed_out = False
        worker._on_timeout()
        assert not worker._is_timed_out


class TestOnGenerationFinished:
    def test_normal(self, worker):
        worker._is_timed_out = False
        worker.timeout_timer = MagicMock()
        worker._on_generation_finished()
        worker.finished.emit.assert_called_once_with([])

    def test_ignored_after_timeout(self, worker):
        worker._is_timed_out = True
        worker._on_generation_finished()
        worker.finished.emit.assert_not_called()


class TestOnGenerationError:
    def test_normal(self, worker):
        worker._is_timed_out = False
        worker.timeout_timer = MagicMock()
        worker._on_generation_error("oops")
        worker.error.emit.assert_called_once_with("oops")

    def test_ignored_after_timeout(self, worker):
        worker._is_timed_out = True
        worker._on_generation_error("oops")
        worker.error.emit.assert_not_called()


class TestReinitializeAgent:
    def test_gemini_mode(self, worker):
        engine = MagicMock()
        engine.config = MagicMock()
        worker.engine = engine
        worker.reinitialize_agent("Gemini")
        engine.switch_backend.assert_called_once_with("gemini")
        engine.config.save_to_file.assert_called_once()

    def test_local_mode(self, worker):
        engine = MagicMock()
        engine.config = MagicMock()
        worker.engine = engine
        worker.reinitialize_agent("Local")
        engine.switch_backend.assert_called_once_with("local")

    def test_api_mode(self, worker):
        engine = MagicMock()
        engine.config = MagicMock()
        worker.engine = engine
        worker.reinitialize_agent("gpt-4o")
        engine.switch_backend.assert_called_once_with("api")
        assert engine.config.api_model_name == "gpt-4o"

    def test_no_engine_returns(self, worker):
        worker.engine = None
        worker.reinitialize_agent("Gemini")
        worker.error.emit.assert_not_called()

    def test_error_emits_signal(self, worker):
        engine = MagicMock()
        engine.config = MagicMock()
        engine.switch_backend.side_effect = RuntimeError("fail")
        worker.engine = engine
        worker.reinitialize_agent("Gemini")
        worker.error.emit.assert_called_once()
