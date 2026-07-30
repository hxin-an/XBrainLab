"""AgentWorker regressions for owned-process escalation and recovery."""

from __future__ import annotations

import threading
import time
from typing import Any, cast
from unittest.mock import MagicMock, patch

from XBrainLab.llm.agent import worker as worker_module
from XBrainLab.llm.agent.runtime_state import AssistantRuntimePhase
from XBrainLab.llm.agent.turn import (
    AssistantGenerationRequest,
    AssistantGenerationStopAcknowledgement,
    AssistantGenerationStopRequest,
    AssistantResponseContract,
)
from XBrainLab.llm.agent.worker import AgentWorker
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.runtime_process import LocalRuntimeProcessOwner
from XBrainLab.llm.core.runtime_selection import (
    AssistantRuntimeBackend,
    AssistantRuntimeLaunchSpec,
    AssistantRuntimeSelectionOutcome,
    AssistantRuntimeSettingsSnapshot,
)


class _EscalatedOwner:
    uses_owned_process = True

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.restart_required = False
        self.load_released = True
        self.closed = False

    def load_model(self) -> None:
        return None

    def cancel_generation(self, wait_timeout: float = 0.25) -> bool:
        del wait_timeout
        self.restart_required = True
        return True

    def close(self, wait_timeout: float = 0.25) -> bool:
        del wait_timeout
        self.closed = True
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

    def load_model(self) -> None:
        self.load_started.set()
        self.load_release.wait(timeout=2.0)
        if self.closed:
            raise RuntimeError("owned process closed during load")

    def close(self, wait_timeout: float = 0.25) -> bool:
        del wait_timeout
        self.closed = True
        self.load_release.set()
        return True


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


def test_product_worker_defaults_to_owned_process_boundary() -> None:
    assert worker_module.LLMEngine is LocalRuntimeProcessOwner


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
        response_contract=AssistantResponseContract.NATURAL_LANGUAGE,
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
        "XBrainLab.llm.agent.worker.LLMEngine",
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
        "XBrainLab.llm.agent.worker.LLMEngine",
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
