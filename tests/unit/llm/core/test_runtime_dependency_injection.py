"""Product runtime dependency injection preserves admission and lifecycle."""

from dataclasses import replace
from functools import partial
from unittest.mock import MagicMock

import pytest

from XBrainLab.llm.core.backends.local import LocalBackend
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine
from XBrainLab.llm.core.model_catalog import LOCAL_MODEL_SPECS


def _config():
    return LLMConfig(model_name="test/unsupported-model", device="cpu")


def _spec():
    return replace(LOCAL_MODEL_SPECS[0], repo_id="test/unsupported-model")


def test_default_backend_rejects_unsupported_model():
    with pytest.raises(RuntimeError):
        LocalBackend(_config()).load()


def test_engine_uses_explicit_backend_without_changing_default_catalog():
    backend = MagicMock()
    backend.unload.return_value = True
    factory = MagicMock(return_value=backend)
    engine = LLMEngine(_config(), backend_factory=factory)
    engine.load_model()
    assert engine.active_backend is backend
    factory.assert_called_once_with(engine.config)
    backend.load.assert_called_once()
    assert engine.close()
    backend.unload.assert_called_once()
    test_default_backend_rejects_unsupported_model()


def test_worker_frozen_settings_loader_never_reads_daily_settings(qtbot, monkeypatch):
    from XBrainLab.llm.agent.worker import AgentWorker

    def forbid_daily_read(*args, **kwargs):
        pytest.fail("Injected settings loader read daily settings")

    monkeypatch.setattr(LLMConfig, "load_from_file", forbid_daily_read)
    frozen = _config()
    frozen.max_new_tokens = 123
    worker = AgentWorker(generation_config_loader=lambda: frozen)
    worker.engine = MagicMock(config=_config())
    worker._reload_generation_settings()
    assert worker.engine.config.max_new_tokens == 123
    worker.engine = None
    worker.deleteLater()
    qtbot.wait(0)


class _FiniteBackend:
    """Replace only native model inference in the real process/engine path."""

    def __init__(self, config, *, spec):
        self.config = config
        self.spec = spec

    def load(self):
        assert self.config.model_name == self.spec.repo_id

    def generate_stream(self, messages, *, options):
        del messages
        yield self.spec.revision
        yield str(options.max_new_tokens)

    def unload(self):
        return True


def _test_engine(config, *, spec):
    return LLMEngine(
        config,
        backend_factory=partial(_FiniteBackend, spec=spec),
    )


def test_worker_injection_spawns_real_process_and_closes(qtbot):
    from XBrainLab.llm.agent.runtime_state import AssistantRuntimePhase
    from XBrainLab.llm.agent.worker import AgentWorker
    from XBrainLab.llm.core.generation import GenerationProfile
    from XBrainLab.llm.core.runtime_selection import (
        AssistantRuntimeBackend,
        AssistantRuntimeLaunchSpec,
        AssistantRuntimeSelectionOutcome,
        AssistantRuntimeSettingsSnapshot,
    )

    config = _config()
    spec = _spec()
    worker = AgentWorker(engine_factory=partial(_test_engine, spec=spec))
    launch = AssistantRuntimeLaunchSpec(
        backend=AssistantRuntimeBackend.LOCAL,
        requested_backend_id="local",
        requested_model_id=spec.repo_id,
        model_id=spec.repo_id,
        outcome=AssistantRuntimeSelectionOutcome.EXACT,
        selection_detail="Local runtime ready.",
        settings=AssistantRuntimeSettingsSnapshot.from_config(config),
    )
    snapshots = []
    worker.runtime_snapshot_changed.connect(snapshots.append)
    try:
        worker.initialize_agent(launch)
        qtbot.waitUntil(lambda: worker.runtime_load_thread is None, timeout=60_000)
        assert snapshots[-1].phase is AssistantRuntimePhase.READY
        assert worker.engine is not None
        assert worker.engine.pid is not None
        assert worker.engine.active_backend is worker.engine
        assert list(
            worker.engine.generate_stream(
                [{"role": "user", "content": "probe"}],
                profile=GenerationProfile.INFORMATIONAL_TEXT,
            )
        ) == [spec.revision, str(config.max_new_tokens)]
    finally:
        if worker.engine is not None:
            assert worker.engine.close(wait_timeout=2)
            assert worker.engine.is_alive is False
            assert worker.engine.active_backend is None
        worker.deleteLater()
        qtbot.wait(0)


def test_controller_factory_keeps_real_worker_thread_lifecycle(qtbot):
    from tests.qt_lifecycle import close_controller_and_wait
    from XBrainLab.backend.study import Study
    from XBrainLab.llm.agent.controller import LLMController
    from XBrainLab.llm.agent.worker import AgentWorker

    created = []

    def factory():
        worker = AgentWorker(generation_config_loader=lambda: None)
        created.append(worker)
        return worker

    controller = LLMController(Study(), worker_factory=factory)
    try:
        assert created == [controller.worker]
        assert controller.worker.thread() is controller.worker_thread
        assert controller.worker_thread.isRunning()
    finally:
        close_controller_and_wait(controller, qtbot)
