"""AgentWorker regressions for owned-process escalation and recovery."""

from __future__ import annotations

import threading
import time
from dataclasses import replace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from XBrainLab.llm.agent import worker as worker_module
from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
    AssistantRuntimeSnapshot,
)
from XBrainLab.llm.agent.turn import (
    AssistantGenerationRequest,
    AssistantGenerationStopAcknowledgement,
    AssistantGenerationStopRequest,
)
from XBrainLab.llm.agent.worker import AgentWorker
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.runtime_selection import (
    AssistantRuntimeBackend,
    AssistantRuntimeLaunchSpec,
    AssistantRuntimeSelectionOutcome,
    AssistantRuntimeSettingsSnapshot,
)
from XBrainLab.ui.components.assistant_runtime_coordinator import (
    AssistantRuntimeCoordinator,
)
from XBrainLab.ui.components.assistant_runtime_lifecycle import (
    AssistantRuntimeActivationRequest,
    AssistantRuntimeLifecycle,
)


class _EscalatedOwner:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.restart_required = False
        self.load_released = True
        self.closed = False
        self.active_backend: object | None = object()

    def load_model(self) -> None:
        return None

    def cancel_generation(self, wait_timeout: float = 0.25) -> bool:
        del wait_timeout
        self.restart_required = True
        return True

    def close(self, wait_timeout: float = 0.25) -> bool:
        del wait_timeout
        self.closed = True
        self.active_backend = None
        return True


class _ReadyOwner(_EscalatedOwner):
    def cancel_generation(self, wait_timeout: float = 0.25) -> bool:
        del wait_timeout
        return True


class _BlockingLoadOwner(_ReadyOwner):
    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)
        self.load_started = threading.Event()
        self.load_release = threading.Event()
        self.active_backend = None

    def load_model(self) -> None:
        self.load_started.set()
        self.load_release.wait(timeout=2.0)
        if self.closed:
            raise RuntimeError("owned process closed during load")
        self.active_backend = object()

    def close(self, wait_timeout: float = 0.25) -> bool:
        del wait_timeout
        self.closed = True
        self.load_release.set()
        return True


def test_model_replacement_load_allows_queued_shutdown(qtbot, monkeypatch):
    class _Control(QObject):
        switch = pyqtSignal(object)
        shutdown = pyqtSignal()

    worker = AgentWorker()
    worker_thread = QThread()
    worker.moveToThread(worker_thread)
    worker_thread.finished.connect(worker.deleteLater)
    control = _Control()
    control.switch.connect(worker.reinitialize_agent)
    control.shutdown.connect(worker.shutdown)
    results = []
    worker.shutdown_finished.connect(results.append)
    initial_spec = _launch_spec()
    old_owner = _ReadyOwner(initial_spec.build_config())
    worker.engine = cast(Any, old_owner)
    worker._runtime_launch_spec = initial_spec
    replacement = _BlockingLoadOwner(initial_spec.build_config())
    old_owner.active_backend = object()

    monkeypatch.setattr(
        worker_module, "LocalRuntimeProcessOwner", lambda _config: replacement
    )
    monkeypatch.setattr(LLMConfig, "save_to_file", lambda _self: True)
    worker_thread.start()
    try:
        control.switch.emit(initial_spec)
        qtbot.waitUntil(replacement.load_started.is_set, timeout=1_000)
        assert old_owner.closed
        control.shutdown.emit()
        qtbot.waitUntil(lambda: replacement.closed, timeout=1_000)
        qtbot.waitUntil(lambda: worker.runtime_load_thread is None, timeout=1_000)
        control.shutdown.emit()
        qtbot.waitUntil(lambda: bool(results) and results[-1], timeout=1_000)
    finally:
        replacement.load_release.set()
        worker_thread.quit()
        assert worker_thread.wait(2_000)


def test_failed_replacement_reports_unloaded_to_runtime_coordinator(qtbot, monkeypatch):
    class _FailedOwner(_ReadyOwner):
        def load_model(self):
            raise RuntimeError("replacement load failed")

    worker = AgentWorker()
    coordinator = AssistantRuntimeCoordinator(lambda _snapshot: None)
    worker.runtime_snapshot_changed.connect(coordinator.accept_worker_snapshot)
    initial_spec = _launch_spec()
    old_owner = _ReadyOwner(initial_spec.build_config())
    worker.engine = cast(Any, old_owner)
    worker._runtime_launch_spec = initial_spec
    coordinator.accept_worker_snapshot(
        AssistantRuntimeSnapshot(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id=initial_spec.model_id,
        )
    )
    target = AssistantRuntimeActivationRequest.from_launch_spec(
        replace(
            initial_spec,
            model_id="ibm-granite/granite-3.3-2b-instruct",
            requested_model_id="ibm-granite/granite-3.3-2b-instruct",
        ),
        activation_id=2,
    )
    failed = _FailedOwner(target.build_config())
    old_owner.active_backend = object()

    monkeypatch.setattr(
        worker_module, "LocalRuntimeProcessOwner", lambda _config: failed
    )
    monkeypatch.setattr(LLMConfig, "save_to_file", lambda _self: True)
    coordinator.begin_loading(target, activation_id=2)

    worker.reinitialize_agent(target)
    qtbot.waitUntil(lambda: worker.runtime_load_thread is None, timeout=1_000)

    assert old_owner.closed
    assert failed.closed
    assert worker.engine is None
    assert coordinator.current.phase is AssistantRuntimePhase.FAILED
    assert coordinator.current.initialized is False
    assert coordinator.restore_active_runtime() is False
    assert not coordinator.owns_local_runtime
    worker.deleteLater()


def test_replacement_save_failure_keeps_session_runtime_and_reports_warning(
    qtbot, monkeypatch
):
    worker = AgentWorker()
    spec = _launch_spec()
    old_owner = _ReadyOwner(spec.build_config())
    worker.engine = cast(Any, old_owner)
    worker._runtime_launch_spec = spec
    replacement = _ReadyOwner(spec.build_config())
    monkeypatch.setattr(
        worker_module, "LocalRuntimeProcessOwner", lambda _config: replacement
    )
    monkeypatch.setattr(LLMConfig, "save_to_file", lambda _self: False)
    errors = []
    snapshots = []
    worker.error.connect(errors.append)
    worker.runtime_snapshot_changed.connect(snapshots.append)

    worker.reinitialize_agent(spec)
    qtbot.waitUntil(lambda: worker.runtime_load_thread is None, timeout=1_000)

    assert errors == [
        "Model switched for this session, but the setting could not be saved."
    ]
    assert worker.engine is replacement
    assert snapshots[-1].phase is AssistantRuntimePhase.READY
    worker.shutdown()
    worker.deleteLater()


def test_repeated_initialization_does_not_announce_allocated_owner_as_ready(
    qtbot, monkeypatch
):
    worker = AgentWorker()
    spec = AssistantRuntimeActivationRequest.from_launch_spec(
        _launch_spec(), activation_id=1
    )
    owner = _BlockingLoadOwner(spec.build_config())
    monkeypatch.setattr(
        worker_module, "LocalRuntimeProcessOwner", lambda _config: owner
    )
    snapshots = []
    worker.runtime_snapshot_changed.connect(snapshots.append)
    try:
        worker.initialize_agent(spec)
        assert owner.load_started.wait(1.0)
        worker.initialize_agent(spec)
        assert all(
            snapshot.phase is AssistantRuntimePhase.LOADING for snapshot in snapshots
        )
        assert not any(snapshot.initialized for snapshot in snapshots)
    finally:
        owner.load_release.set()
        qtbot.waitUntil(lambda: worker.runtime_load_thread is None, timeout=1_000)
        worker.shutdown()
        worker.deleteLater()


@pytest.mark.parametrize(
    "terminal", ["failed", "shutdown_failed", "shutdown_succeeded", "restart"]
)
@pytest.mark.parametrize("close_raises", [False, True])
def test_load_terminal_retains_owner_until_failed_close_can_be_retried(
    terminal, close_raises
):
    class _UnstoppedOwner(_ReadyOwner):
        def __init__(self, config):
            super().__init__(config)
            self.active_backend = None
            self.close_calls = 0
            self.allow_close = False

        def close(self, wait_timeout=0.25):
            self.close_calls += 1
            if close_raises and not self.allow_close:
                raise OSError("owned process join failed")
            return self.allow_close

    worker = AgentWorker()
    spec = AssistantRuntimeActivationRequest.from_launch_spec(
        _launch_spec(), activation_id=1
    )
    owner = _UnstoppedOwner(spec.build_config())
    worker.engine = cast(Any, owner)
    worker._runtime_launch_spec = spec
    load_thread = worker_module.RuntimeLoadThread(cast(Any, owner))
    worker.runtime_load_thread = load_thread
    snapshots = []
    worker.runtime_snapshot_changed.connect(snapshots.append)
    worker._shutdown_requested = terminal.startswith("shutdown")
    if terminal == "restart":
        worker._retire_restart_required_engine()
    elif terminal == "shutdown_succeeded":
        worker._on_runtime_load_succeeded(load_thread)
    else:
        worker._on_runtime_load_failed(load_thread, RuntimeError("load failed"))
    assert worker.engine is owner
    assert not any(snapshot.initialized for snapshot in snapshots)
    worker._release_runtime_load_thread(load_thread)
    if terminal == "failed":
        worker.initialize_agent(spec)
        assert snapshots[-1].phase is AssistantRuntimePhase.FAILED
        assert snapshots[-1].initialized is False
    assert worker.shutdown(wait_ms=0) is False
    assert worker.engine is owner
    failed_close_calls = owner.close_calls
    owner.allow_close = True
    assert worker.shutdown(wait_ms=0) is True
    assert owner.close_calls > failed_close_calls
    assert worker.engine is None
    worker.deleteLater()


def test_unready_retained_owner_blocks_model_deletion_until_cleanup_succeeds():
    class _UnstoppedOwner(_ReadyOwner):
        active_backend = None
        allow_close = False

        def close(self, wait_timeout=0.25):
            return self.allow_close

    worker = AgentWorker()
    lifecycle = AssistantRuntimeLifecycle(
        study=object(), controller_factory=lambda _study: worker
    )
    lifecycle._controller = worker
    worker.runtime_snapshot_changed.connect(lifecycle.accept_runtime_snapshot)
    spec = _launch_spec()
    owner = _UnstoppedOwner(spec.build_config())
    owner.active_backend = None
    worker.engine = cast(Any, owner)
    worker._runtime_launch_spec = spec
    load_thread = worker_module.RuntimeLoadThread(cast(Any, owner))
    worker.runtime_load_thread = load_thread

    worker._on_runtime_load_failed(load_thread, RuntimeError("load failed"))

    assert worker.engine is owner
    assert lifecycle.current.phase is AssistantRuntimePhase.FAILED
    assert lifecycle.current.initialized is False
    assert lifecycle.active_local_runtime_blocks_model_deletion() is True
    lifecycle.mark_unavailable("Runtime remains unavailable.")
    assert lifecycle.active_local_runtime_blocks_model_deletion() is True
    worker._release_runtime_load_thread(load_thread)
    assert worker.shutdown(wait_ms=0) is False
    assert lifecycle.active_local_runtime_blocks_model_deletion() is True

    owner.allow_close = True
    assert worker.shutdown(wait_ms=0) is True
    assert lifecycle.current.phase is AssistantRuntimePhase.IDLE
    assert lifecycle.current.initialized is False
    assert lifecycle.active_local_runtime_blocks_model_deletion() is False
    lifecycle.deleteLater()
    worker.deleteLater()


def _launch_spec() -> AssistantRuntimeLaunchSpec:
    config = LLMConfig()
    return AssistantRuntimeLaunchSpec(
        backend=AssistantRuntimeBackend.LOCAL,
        requested_backend_id="local",
        requested_model_id=config.model_name,
        model_id=config.model_name,
        outcome=AssistantRuntimeSelectionOutcome.EXACT,
        selection_detail="Local runtime ready.",
        settings=AssistantRuntimeSettingsSnapshot.from_config(config),
    )


def test_generation_is_not_started_before_owned_runtime_is_ready() -> None:
    worker = AgentWorker()
    generation_errors = []
    worker.generation_error.connect(
        lambda generation_id, message: generation_errors.append(
            (generation_id, message)
        )
    )
    owner = _ReadyOwner(_launch_spec().build_config())
    owner.active_backend = None
    worker.engine = cast(Any, owner)

    request = AssistantGenerationRequest.from_messages(
        [{"role": "user", "content": "Explain the current workflow."}],
    ).correlated(17)
    worker.generate_from_messages(request)

    assert generation_errors == [
        (
            17,
            "The local assistant is still loading. Please wait until it is ready.",
        )
    ]
    assert worker.generation_thread is None
    assert worker._active_generation_id is None


def test_forced_stop_fails_runtime_and_retry_constructs_new_owner(qtbot) -> None:
    worker = AgentWorker()
    snapshots = []
    stop_results = []
    worker.runtime_snapshot_changed.connect(snapshots.append)
    worker.generation_stop_finished.connect(stop_results.append)
    first_owner = _EscalatedOwner(_launch_spec().build_config())
    second_owner = _ReadyOwner(_launch_spec().build_config())

    running_thread = MagicMock()
    running_thread.isRunning.return_value = True
    running_thread.wait.return_value = True
    worker.engine = cast(Any, first_owner)
    worker.generation_thread = running_thread
    worker._active_generation_id = 41
    worker._generation_thread_id = 41

    with patch(
        "XBrainLab.llm.agent.worker.LocalRuntimeProcessOwner",
        side_effect=[second_owner],
    ):
        worker.cancel_generation(AssistantGenerationStopRequest(generation_id=41))

        assert stop_results == [
            AssistantGenerationStopAcknowledgement(
                generation_id=41,
                stopped=True,
            )
        ]
        assert worker.engine is None
        assert snapshots[-1].phase is AssistantRuntimePhase.FAILED
        assert snapshots[-1].initialized is False
        assert "retry" in snapshots[-1].error.lower()

        worker.initialize_agent(_launch_spec())
        qtbot.waitUntil(
            lambda: snapshots[-1].phase is AssistantRuntimePhase.READY,
            timeout=1_000,
        )

    assert worker.engine is second_owner
    assert first_owner.closed is True
    assert snapshots[-1].phase is AssistantRuntimePhase.READY


def test_shutdown_of_owned_process_is_terminal_even_after_forced_cancel() -> None:
    worker = AgentWorker()
    shutdown_results = []
    worker.shutdown_finished.connect(shutdown_results.append)
    owner = _EscalatedOwner(_launch_spec().build_config())
    running_thread = MagicMock()
    running_thread.isRunning.return_value = True
    running_thread.wait.return_value = True
    worker.engine = cast(Any, owner)
    worker.generation_thread = running_thread
    worker._active_generation_id = 73
    worker._generation_thread_id = 73

    assert worker.shutdown(wait_ms=100) is True

    assert shutdown_results == [True]
    assert owner.closed is True
    assert worker.engine is None


def test_timeout_escalation_is_correlated_and_requires_runtime_retry() -> None:
    worker = AgentWorker()
    snapshots = []
    generation_errors = []
    worker.runtime_snapshot_changed.connect(snapshots.append)
    worker.generation_error.connect(
        lambda generation_id, message: generation_errors.append(
            (generation_id, message)
        )
    )
    owner = _EscalatedOwner(_launch_spec().build_config())
    running_thread = MagicMock()
    running_thread.isRunning.return_value = True
    running_thread.wait.return_value = True
    worker.engine = cast(Any, owner)
    worker.generation_thread = running_thread
    worker._active_generation_id = 57
    worker._generation_thread_id = 57

    worker._on_timeout()

    assert generation_errors == [
        (57, "Error: Generation timed out (Local LLM is too slow).")
    ]
    assert worker.generation_thread is None
    assert worker.engine is None
    assert snapshots[-1].phase is AssistantRuntimePhase.FAILED
    assert snapshots[-1].initialized is False
    assert "retry" in snapshots[-1].error.lower()


def test_owned_process_load_does_not_block_bounded_worker_shutdown(qtbot) -> None:
    worker = AgentWorker()
    shutdown_results = []
    worker.shutdown_finished.connect(shutdown_results.append)
    owner = _BlockingLoadOwner(_launch_spec().build_config())

    with patch(
        "XBrainLab.llm.agent.worker.LocalRuntimeProcessOwner",
        return_value=owner,
    ):
        started = time.monotonic()
        worker.initialize_agent(_launch_spec())
        initialize_elapsed = time.monotonic() - started

    assert initialize_elapsed < 0.1
    assert owner.load_started.wait(timeout=1.0)

    started = time.monotonic()
    assert worker.shutdown(wait_ms=100) is False
    first_shutdown_elapsed = time.monotonic() - started

    assert first_shutdown_elapsed < 0.5
    assert shutdown_results == [False]
    assert owner.closed is True
    qtbot.waitUntil(lambda: worker.runtime_load_thread is None, timeout=1_000)

    assert worker.shutdown(wait_ms=100) is True
    assert shutdown_results == [False, True]
