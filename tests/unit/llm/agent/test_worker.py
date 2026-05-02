"""Coverage tests for AgentWorker & GenerationThread."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.llm.core.config import LLMConfig


@pytest.fixture
def worker():
    """Return an AgentWorker with mocked Qt signals.

    Patches ``QObject.__init__`` so the real ``AgentWorker.__init__``
    executes (setting ``engine`` and ``generation_thread``) without
    requiring a running ``QApplication``.
    """
    from PyQt6.QtCore import QObject

    from XBrainLab.llm.agent.worker import AgentWorker

    with patch.object(QObject, "__init__", lambda self: None):
        w = AgentWorker()
    # Signals need explicit mocking because QObject was not fully initialised
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
            patch("XBrainLab.llm.agent.worker.LLMConfig.load_from_file") as mock_load,
            patch("XBrainLab.llm.agent.worker.LLMEngine") as MockEng,
        ):
            cfg = LLMConfig()
            cfg.model_name = LLMConfig.default_local_model_id()
            cfg.inference_mode = "local"
            cfg.available_local_model_id = MagicMock(
                return_value=(cfg.model_name, "Local runtime ready.")
            )
            mock_load.return_value = cfg
            engine = MockEng.return_value
            worker.initialize_agent()
            engine.load_model.assert_called_once()
            assert worker.engine is engine

    def test_initialize_agent_uses_saved_config(self, worker):
        with (
            patch("XBrainLab.llm.agent.worker.LLMConfig.load_from_file") as mock_load,
            patch("XBrainLab.llm.agent.worker.LLMEngine") as MockEng,
        ):
            saved = LLMConfig()
            saved.inference_mode = "local"
            saved.model_name = LLMConfig.default_local_model_id()
            saved.available_local_model_id = MagicMock(
                return_value=(saved.model_name, "Local runtime ready.")
            )
            mock_load.return_value = saved
            worker.initialize_agent()
            MockEng.assert_called_once_with(saved)

    def test_initialize_agent_blocks_unready_local_runtime(self, worker):
        with (
            patch("XBrainLab.llm.agent.worker.LLMConfig.load_from_file") as mock_load,
            patch("XBrainLab.llm.agent.worker.LLMEngine") as MockEng,
        ):
            cfg = LLMConfig()
            cfg.inference_mode = "local"
            cfg.local_backend_ready = MagicMock(return_value=False)
            cfg.local_backend_status_message = MagicMock(
                return_value="Missing accelerate"
            )
            mock_load.return_value = cfg

            worker.initialize_agent()

            MockEng.assert_not_called()
            worker.error.emit.assert_called_once()

    def test_initialize_agent_logs_cpu_fallback_note(self, worker):
        with (
            patch("XBrainLab.llm.agent.worker.LLMConfig.load_from_file") as mock_load,
            patch("XBrainLab.llm.agent.worker.LLMEngine") as MockEng,
        ):
            cfg = LLMConfig()
            cfg.inference_mode = "local"
            cfg.model_name = "test-model"
            cfg.local_backend_ready = MagicMock(return_value=True)
            cfg.local_backend_status_message = MagicMock(
                return_value=(
                    "Local runtime ready. GPU execution is unavailable in this "
                    "environment, so startup will fall back to CPU and disable "
                    "4-bit loading."
                )
            )
            mock_load.return_value = cfg
            engine = MockEng.return_value

            worker.initialize_agent()

            assert (
                worker.log.emit.call_args_list[0]
                .args[0]
                .startswith("Local runtime ready. GPU execution is unavailable")
            )
            engine.load_model.assert_called_once()

    def test_initialize_agent_uses_ready_fallback_model(self, worker):
        with (
            patch("XBrainLab.llm.agent.worker.LLMConfig.load_from_file") as mock_load,
            patch("XBrainLab.llm.agent.worker.LLMEngine") as MockEng,
        ):
            cfg = LLMConfig()
            cfg.inference_mode = "local"
            primary = cfg.model_name
            fallback = cfg.fallback_local_model_id()
            cfg.local_backend_ready = MagicMock(
                side_effect=lambda model_id=None: (model_id or cfg.model_name)
                == fallback
            )
            cfg.local_backend_status_message = MagicMock(
                side_effect=lambda model_id=None: (
                    "Local runtime ready."
                    if (model_id or cfg.model_name) == fallback
                    else "Model cache not found."
                )
            )
            mock_load.return_value = cfg
            engine = MockEng.return_value

            worker.initialize_agent()

            assert primary != fallback
            assert cfg.model_name == fallback
            assert (
                worker.log.emit.call_args_list[0]
                .args[0]
                .endswith(f"Falling back to supported local model {fallback}.")
            )
            MockEng.assert_called_once_with(cfg)
            engine.load_model.assert_called_once()

    def test_error_on_failure(self, worker):
        with (
            patch(
                "XBrainLab.llm.agent.worker.LLMConfig.load_from_file", return_value=None
            ),
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
        fresh = LLMConfig()
        fresh.timeout = 30
        fresh.local_backend_ready = MagicMock(return_value=True)

        with (
            patch("XBrainLab.llm.agent.worker.GenerationThread") as MockGT,
            patch("XBrainLab.llm.agent.worker.QTimer") as MockTimer,
            patch(
                "XBrainLab.llm.agent.worker.LLMConfig.load_from_file",
                return_value=fresh,
            ),
        ):
            gt = MockGT.return_value
            timer = MockTimer.return_value
            msgs = [{"role": "user", "content": "test"}]
            worker.generate_from_messages(msgs)
            gt.start.assert_called_once()
            timer.start.assert_called_once_with(30000)

    def test_syncs_legacy_remote_config_without_remote_switch(self, worker):
        engine = MagicMock()
        engine.config = MagicMock()
        engine.config.inference_mode = "local"
        engine.config.active_mode = "local"
        engine.config.model_name = "microsoft/Phi-4-mini-instruct"
        engine.config.timeout = 60
        worker.engine = engine

        fresh = LLMConfig()
        fresh.inference_mode = "gemini"
        fresh.active_mode = "gemini"
        fresh.available_local_model_id = MagicMock(
            return_value=(fresh.model_name, "Local runtime ready.")
        )

        with (
            patch("XBrainLab.llm.agent.worker.GenerationThread"),
            patch("XBrainLab.llm.agent.worker.QTimer"),
            patch(
                "XBrainLab.llm.agent.worker.LLMConfig.load_from_file",
                return_value=fresh,
            ),
        ):
            msgs = [{"role": "user", "content": "test"}]
            worker.generate_from_messages(msgs)
            engine.switch_backend.assert_not_called()

    def test_reload_local_backend_when_model_id_changes_same_mode(self, worker):
        engine = MagicMock()
        engine.config = MagicMock()
        engine.config.inference_mode = "local"
        engine.config.active_mode = "local"
        engine.config.model_name = "microsoft/Phi-4-mini-instruct"
        engine.config.timeout = 60
        stale_backend = object()
        reloaded_backend = object()
        engine.active_backend = stale_backend
        worker.engine = engine

        fresh = LLMConfig()
        fresh.inference_mode = "local"
        fresh.active_mode = "local"
        fresh.model_name = "microsoft/Phi-3.5-mini-instruct"
        fresh.timeout = 60
        fresh.local_backend_ready = MagicMock(return_value=True)

        def reload_backend(mode):
            engine.active_backend = reloaded_backend

        with (
            patch("XBrainLab.llm.agent.worker.GenerationThread"),
            patch("XBrainLab.llm.agent.worker.QTimer"),
            patch(
                "XBrainLab.llm.agent.worker.LLMConfig.load_from_file",
                return_value=fresh,
            ),
        ):
            engine.switch_backend.side_effect = reload_backend

            worker.generate_from_messages([{"role": "user", "content": "test"}])

        engine.switch_backend.assert_called_once_with("local")
        assert engine.active_backend is reloaded_backend

    def test_legacy_remote_config_sync_switches_to_local_when_model_changes(
        self,
        worker,
    ):
        engine = MagicMock()
        engine.config = MagicMock()
        engine.config.inference_mode = "gemini"
        engine.config.active_mode = "gemini"
        engine.config.model_name = "microsoft/Phi-4-mini-instruct"
        engine.config.timeout = 60
        stale_backend = object()
        reloaded_backend = object()
        engine.active_backend = stale_backend
        worker.engine = engine

        fresh = LLMConfig()
        fresh.inference_mode = "gemini"
        fresh.active_mode = "gemini"
        fresh.model_name = "microsoft/Phi-3.5-mini-instruct"
        fresh.timeout = 60
        fresh.available_local_model_id = MagicMock(
            return_value=(fresh.model_name, "Local runtime ready.")
        )

        def reload_backend(mode):
            engine.active_backend = reloaded_backend

        with (
            patch("XBrainLab.llm.agent.worker.GenerationThread"),
            patch("XBrainLab.llm.agent.worker.QTimer"),
            patch(
                "XBrainLab.llm.agent.worker.LLMConfig.load_from_file",
                return_value=fresh,
            ),
        ):
            engine.switch_backend.side_effect = reload_backend

            worker.generate_from_messages([{"role": "user", "content": "test"}])

        engine.switch_backend.assert_called_once_with("local")
        assert engine.active_backend is reloaded_backend

    def test_fails_closed_when_config_sync_backend_switch_fails(self, worker):
        engine = MagicMock()
        engine.config = MagicMock()
        engine.config.inference_mode = "local"
        engine.config.active_mode = "local"
        engine.config.timeout = 60
        worker.engine = engine

        fresh = LLMConfig()
        fresh.inference_mode = "gemini"
        fresh.active_mode = "gemini"

        with (
            patch("XBrainLab.llm.agent.worker.GenerationThread") as MockGT,
            patch("XBrainLab.llm.agent.worker.QTimer"),
            patch(
                "XBrainLab.llm.agent.worker.LLMConfig.load_from_file",
                return_value=fresh,
            ),
        ):
            engine.switch_backend.side_effect = RuntimeError("boom")

            worker.generate_from_messages([{"role": "user", "content": "test"}])

        assert worker.engine.config is engine.config
        worker.error.emit.assert_called_once_with("Config Sync Failed: boom")
        worker.finished.emit.assert_called_once_with([])
        MockGT.assert_not_called()


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
    def test_legacy_remote_mode_is_rejected(self, worker):
        engine = MagicMock()
        engine.config = LLMConfig()
        engine.config.active_mode = "local"
        worker.engine = engine
        with patch.object(engine.config, "save_to_file") as mock_save:
            worker.reinitialize_agent("Gemini")
        engine.switch_backend.assert_not_called()
        mock_save.assert_not_called()
        worker.error.emit.assert_called_once()
        assert engine.config.active_mode == "local"
        assert engine.config.inference_mode == "local"

    def test_local_mode(self, worker):
        engine = MagicMock()
        engine.config = LLMConfig()
        engine.config.active_mode = "gemini"
        worker.engine = engine
        with patch.object(engine.config, "save_to_file") as mock_save:
            worker.reinitialize_agent("Local")
        engine.switch_backend.assert_called_once_with("local")
        mock_save.assert_called_once()
        assert engine.config.active_mode == "local"
        assert engine.config.inference_mode == "local"

    def test_unknown_non_catalog_model_is_rejected(self, worker):
        engine = MagicMock()
        engine.config = LLMConfig()
        worker.engine = engine
        with patch.object(engine.config, "save_to_file") as mock_save:
            worker.reinitialize_agent("gpt-4o")
        engine.switch_backend.assert_not_called()
        mock_save.assert_not_called()
        worker.error.emit.assert_called_once()
        assert engine.config.active_mode == "local"
        assert engine.config.inference_mode == "local"

    def test_no_engine_returns(self, worker):
        worker.engine = None
        worker.reinitialize_agent("Gemini")
        worker.error.emit.assert_not_called()

    def test_error_emits_signal(self, worker):
        engine = MagicMock()
        engine.config = MagicMock()
        engine.config.inference_mode = "local"
        engine.config.active_mode = "local"
        engine.switch_backend.side_effect = RuntimeError("fail")
        worker.engine = engine
        worker.reinitialize_agent("Local")
        worker.error.emit.assert_called_once()
        assert engine.config.inference_mode == "local"
        assert engine.config.active_mode == "local"
