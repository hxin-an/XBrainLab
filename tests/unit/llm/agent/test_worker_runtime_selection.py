"""Worker contract tests for immutable Assistant runtime launch specs."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.llm.agent.runtime_state import AssistantRuntimePhase
from XBrainLab.llm.agent.turn import AssistantGenerationRequest
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.runtime_selection import (
    AssistantRuntimeLaunchResolver,
    AssistantRuntimeLaunchSpec,
    AssistantRuntimeSelectionOutcome,
)


class _OwnedProcessEngine:
    def __init__(self, config) -> None:
        self.config = config
        self.load_calls = 0
        self.closed = False
        self.active_backend = None

    def load_model(self) -> None:
        self.load_calls += 1
        self.active_backend = object()

    def close(self, *, wait_timeout: float = 5.0) -> bool:
        del wait_timeout
        self.closed = True
        self.active_backend = None
        return True


def _generation_request(text: str) -> AssistantGenerationRequest:
    request = AssistantGenerationRequest.from_messages(
        [{"role": "user", "content": text}],
    )
    return request.correlated(1)


@pytest.fixture
def worker():
    from PyQt6.QtCore import QObject

    from XBrainLab.llm.agent.worker import AgentWorker

    with patch.object(QObject, "__init__", lambda self: None):
        instance = AgentWorker()
    instance.error = MagicMock()
    instance.generation_finished = MagicMock()
    instance.generation_chunk_received = MagicMock()
    instance.generation_error = MagicMock()
    instance.generation_dispatch_acknowledged = MagicMock()
    instance.log = MagicMock()
    instance.runtime_snapshot_changed = MagicMock()
    yield instance

    generation_thread = instance.generation_thread
    if generation_thread is not None:
        instance._release_generation_thread(generation_thread)


@pytest.fixture
def owned_worker(qtbot):
    from XBrainLab.llm.agent.worker import AgentWorker

    instance = AgentWorker()
    yield instance
    if instance.runtime_load_thread is not None:
        qtbot.waitUntil(lambda: instance.runtime_load_thread is None, timeout=2_000)
    if instance.engine is not None:
        instance._close_engine(instance.engine)
        instance.engine = None
    instance.deleteLater()
    qtbot.wait(0)


def _launch_spec(
    monkeypatch: pytest.MonkeyPatch,
    model_id: str,
    *,
    requested_model_id: str | None = None,
) -> AssistantRuntimeLaunchSpec:
    requested = requested_model_id or model_id
    config = LLMConfig(model_name=requested)
    monkeypatch.setattr(
        config,
        "local_backend_ready",
        lambda candidate=None: candidate == model_id,
    )
    monkeypatch.setattr(
        config,
        "local_backend_status_message",
        lambda candidate=None: (
            "Local runtime ready."
            if candidate == model_id
            else f"Model cache not found for {candidate}."
        ),
    )
    monkeypatch.setattr(config, "local_backend_cpu_fallback_reason", lambda: None)
    resolution = AssistantRuntimeLaunchResolver().resolve(config)
    assert resolution.launch_spec is not None
    return resolution.launch_spec


def test_worker_initializes_only_from_the_exact_launch_spec(
    owned_worker,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_id = LLMConfig.default_local_model_id()
    spec = _launch_spec(monkeypatch, model_id)

    with (
        patch(
            "XBrainLab.llm.agent.worker.LLMConfig.load_from_file",
            side_effect=AssertionError("startup must not reread settings"),
        ),
        patch("XBrainLab.llm.agent.worker.LocalRuntimeProcessOwner") as engine_class,
    ):
        engine = _OwnedProcessEngine(spec.build_config())
        engine_class.return_value = engine
        snapshots = []
        owned_worker.runtime_snapshot_changed.connect(snapshots.append)
        owned_worker.initialize_agent(spec)
        qtbot.waitUntil(lambda: owned_worker.runtime_load_thread is None, timeout=2_000)

    launch_config = engine_class.call_args.args[0]
    assert launch_config.model_name == spec.model_id
    assert launch_config.inference_mode == spec.backend_mode
    assert engine.load_calls == 1
    assert owned_worker.engine is engine
    assert snapshots[0].phase is AssistantRuntimePhase.LOADING
    assert snapshots[-1].phase is AssistantRuntimePhase.READY
    assert snapshots[-1].model_id == spec.model_id
    assert snapshots[-1].requested_model_id == spec.requested_model_id
    assert snapshots[-1].selection_outcome is spec.outcome
    assert snapshots[-1].selection_detail == spec.selection_detail
    assert snapshots[-1].execution_device == spec.execution_device
    assert snapshots[-1].device_fallback_reason == spec.device_fallback_reason


def test_generation_settings_reload_cannot_reselect_the_active_model(
    worker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_model = LLMConfig.default_local_model_id()
    other_model = "microsoft/Phi-4-mini-instruct"
    spec = _launch_spec(monkeypatch, active_model)
    engine = MagicMock()
    engine.config = spec.build_config()
    engine.active_backend = object()
    worker.engine = engine
    worker._runtime_launch_spec = spec

    changed_settings = LLMConfig(model_name=other_model)
    changed_settings.temperature = 1.5
    changed_settings.timeout = 17
    original_timeout = engine.config.timeout
    with (
        patch(
            "XBrainLab.llm.agent.worker.LLMConfig.load_from_file",
            return_value=changed_settings,
        ),
        patch("XBrainLab.llm.agent.worker.GenerationThread") as thread_class,
        patch("XBrainLab.llm.agent.worker.QTimer"),
    ):
        worker.generate_from_messages(_generation_request("hello"))

    assert engine.config.model_name == active_model
    assert engine.config.temperature == 1.5
    assert engine.config.timeout == original_timeout
    engine.close.assert_not_called()
    thread_class.return_value.start.assert_called_once_with()


def test_worker_model_reselection_consumes_the_same_exact_spec_without_resolution(
    owned_worker,
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial_model = LLMConfig.default_local_model_id()
    reselected_model = LLMConfig.default_local_model_id()
    initial_spec = _launch_spec(monkeypatch, initial_model)
    target_spec = _launch_spec(monkeypatch, reselected_model)
    engine = _OwnedProcessEngine(initial_spec.build_config())
    replacement = _OwnedProcessEngine(target_spec.build_config())
    owned_worker.engine = engine
    owned_worker._runtime_launch_spec = initial_spec
    snapshots = []
    owned_worker.runtime_snapshot_changed.connect(snapshots.append)

    with (
        patch(
            "XBrainLab.llm.agent.worker.LLMConfig.load_from_file",
            side_effect=AssertionError("model switch must not reread settings"),
        ),
        patch.object(LLMConfig, "save_to_file", return_value=True),
        patch(
            "XBrainLab.llm.agent.worker.LocalRuntimeProcessOwner",
            return_value=replacement,
        ),
    ):
        owned_worker.reinitialize_agent(target_spec)
        qtbot.waitUntil(lambda: owned_worker.runtime_load_thread is None, timeout=2_000)

    assert engine.closed
    assert owned_worker.engine is replacement
    assert replacement.config.model_name == target_spec.model_id
    snapshot = snapshots[-1]
    assert snapshot.phase is AssistantRuntimePhase.READY
    assert snapshot.model_id == target_spec.model_id
    assert snapshot.selection_outcome is AssistantRuntimeSelectionOutcome.EXACT


def test_worker_rejects_untyped_model_switch_input_without_defaulting(worker) -> None:
    engine = MagicMock()
    engine.config = LLMConfig()
    worker.engine = engine

    worker.reinitialize_agent("unknown/model")

    engine.close.assert_not_called()
    worker.error.emit.assert_called_once()
    assert "launch spec" in worker.error.emit.call_args.args[0].lower()
