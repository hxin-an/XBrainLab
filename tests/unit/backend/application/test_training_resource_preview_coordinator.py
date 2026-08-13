from __future__ import annotations

import ast
import inspect
from pathlib import Path
from threading import Event
from time import monotonic

import pytest

from XBrainLab.backend.application import (
    training_resource_preview_coordinator as preview_coordinator_module,
)
from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.application.owned_work import (
    OwnedWorkKind,
    OwnedWorkPhase,
    OwnedWorkRegistry,
    owned_work_checkpoint,
)
from XBrainLab.backend.application.resource_guard import (
    RISK_SAFE,
    TrainingResourcePreviewContext,
    TrainingResourcePreviewRequest,
    TrainingResourcePreviewResult,
)
from XBrainLab.backend.application.training_resource_preview_coordinator import (
    TrainingResourcePreviewCoordinator,
)


def _request(
    *,
    request_generation: int,
    publication_generation: int = 7,
) -> TrainingResourcePreviewRequest:
    return TrainingResourcePreviewRequest(
        request_generation=request_generation,
        publication_generation=publication_generation,
        model_name="EEGNet",
        model_params={},
        device="cuda:0",
        batch_size=16,
        optimizer="Adam",
    )


def _context() -> TrainingResourcePreviewContext:
    return TrainingResourcePreviewContext(
        input_shape=(2, 64),
        sample_count=8,
        class_count=2,
        sampling_frequency=128.0,
    )


def _result(request: TrainingResourcePreviewRequest) -> TrainingResourcePreviewResult:
    return TrainingResourcePreviewResult(
        request_generation=request.request_generation,
        publication_generation=request.publication_generation,
        requested_batch_size=request.batch_size,
        suggested_batch_size=request.batch_size,
        estimated_vram_bytes=1024,
        available_vram_bytes=1024**3,
        risk_level=RISK_SAFE,
        vram_known=True,
    )


def test_coordinator_requires_one_injected_owned_work_registry() -> None:
    signature = inspect.signature(TrainingResourcePreviewCoordinator)
    assert signature.parameters["registry"].default is inspect.Parameter.empty

    source_path = Path(inspect.getsourcefile(TrainingResourcePreviewCoordinator) or "")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    standalone_registry_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "OwnedWorkRegistry"
    ]
    assert standalone_registry_calls == []


def test_close_cancels_active_and_pending_owned_preview_then_retry_succeeds() -> None:
    registry = OwnedWorkRegistry()
    first_started = Event()
    release_first = Event()
    estimate_calls: list[int] = []

    def estimate(request, _context):
        estimate_calls.append(request.request_generation)
        owned_work_checkpoint("Estimating training preview resources")
        if request.request_generation == 1:
            first_started.set()
            assert release_first.wait(timeout=2.0)
            owned_work_checkpoint("Verifying training preview resources")
        return _result(request)

    coordinator = TrainingResourcePreviewCoordinator(
        estimate=estimate,
        generation_is_current=lambda _generation: True,
        registry=registry,
    )
    active = coordinator.submit(_request(request_generation=1), _context())
    assert first_started.wait(timeout=2.0)
    pending = coordinator.submit(_request(request_generation=2), _context())

    assert active.operation_id != pending.operation_id
    assert registry.snapshot(active.operation_id).kind is (
        OwnedWorkKind.TRAINING_RESOURCE_PREVIEW
    )
    assert registry.snapshot(active.operation_id).phase is OwnedWorkPhase.RUNNING
    assert registry.snapshot(pending.operation_id).phase is OwnedWorkPhase.PENDING

    started_at = monotonic()
    coordinator.begin_close()
    cancel_elapsed = monotonic() - started_at

    assert cancel_elapsed < 0.1
    assert registry.snapshot(active.operation_id).phase is OwnedWorkPhase.CANCELLING
    assert registry.snapshot(pending.operation_id).phase is OwnedWorkPhase.CANCELLED
    with pytest.raises(PreconditionError, match="closing"):
        pending.result(timeout=0.1)

    release_first.set()
    with pytest.raises(PreconditionError, match="closing"):
        active.result(timeout=2.0)
    assert coordinator.close(timeout=2.0)
    assert registry.snapshot(active.operation_id).phase is OwnedWorkPhase.CANCELLED
    assert registry.wait_for_idle(timeout=0.0)
    assert coordinator.background_work_snapshot() == {
        "idle": True,
        "remaining_workers": 0,
        "alive_workers": 0,
        "active_jobs": 0,
        "pending_jobs": 0,
    }

    assert coordinator.cancel_close()
    retried = coordinator.submit(_request(request_generation=3), _context())
    assert retried.result(timeout=2.0).request_generation == 3
    assert registry.snapshot(retried.operation_id).phase is OwnedWorkPhase.COMPLETED
    assert coordinator.close(timeout=2.0)
    assert estimate_calls == [1, 3]


def test_worker_start_failure_terminalizes_owned_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = OwnedWorkRegistry()
    operation_ids: list[str] = []
    original_begin = registry.begin

    def capture_begin(*args, **kwargs):
        operation = original_begin(*args, **kwargs)
        operation_ids.append(operation.operation_id)
        return operation

    monkeypatch.setattr(registry, "begin", capture_begin)

    class FailingThread:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        @staticmethod
        def start() -> None:
            raise RuntimeError("thread unavailable")

        @staticmethod
        def is_alive() -> bool:
            return False

    monkeypatch.setattr(preview_coordinator_module, "Thread", FailingThread)
    coordinator = TrainingResourcePreviewCoordinator(
        estimate=lambda request, _context: _result(request),
        generation_is_current=lambda _generation: True,
        registry=registry,
    )

    with pytest.raises(RuntimeError, match="thread unavailable"):
        coordinator.submit(_request(request_generation=1), _context())

    assert len(operation_ids) == 1
    assert registry.snapshot(operation_ids[0]).phase is OwnedWorkPhase.FAILED
    assert registry.active_snapshots() == ()
    assert coordinator.background_work_snapshot() == {
        "idle": True,
        "remaining_workers": 0,
        "alive_workers": 0,
        "active_jobs": 0,
        "pending_jobs": 0,
    }


def test_two_clients_share_one_active_estimate() -> None:
    estimate_started = Event()
    release_estimate = Event()
    estimate_calls: list[int] = []

    def estimate(request, _context):
        estimate_calls.append(request.request_generation)
        estimate_started.set()
        assert release_estimate.wait(timeout=2.0)
        return _result(request)

    coordinator = TrainingResourcePreviewCoordinator(
        estimate=estimate,
        generation_is_current=lambda _generation: True,
        registry=OwnedWorkRegistry(),
    )
    try:
        request = _request(request_generation=1)
        first = coordinator.submit(request, _context())
        assert estimate_started.wait(timeout=2.0)
        second = coordinator.submit(request, _context())

        release_estimate.set()

        first_result = first.result(timeout=2.0)
        second_result = second.result(timeout=2.0)
        assert first_result == second_result
        assert first_result.receipt is not None
        assert first_result.request_generation == request.request_generation
        assert first_result.suggested_batch_size == request.batch_size
        assert estimate_calls == [1]
        assert coordinator.wait_for_idle(timeout=2.0)
    finally:
        release_estimate.set()
        assert coordinator.close(timeout=2.0)


def test_latest_pending_request_replaces_obsolete_pending_work() -> None:
    first_started = Event()
    release_first = Event()
    estimate_calls: list[int] = []

    def estimate(request, _context):
        estimate_calls.append(request.request_generation)
        if request.request_generation == 1:
            first_started.set()
            assert release_first.wait(timeout=2.0)
        return _result(request)

    coordinator = TrainingResourcePreviewCoordinator(
        estimate=estimate,
        generation_is_current=lambda _generation: True,
        registry=OwnedWorkRegistry(),
    )
    try:
        first = coordinator.submit(_request(request_generation=1), _context())
        assert first_started.wait(timeout=2.0)
        obsolete = coordinator.submit(_request(request_generation=2), _context())
        latest = coordinator.submit(_request(request_generation=3), _context())
        release_first.set()

        assert first.result(timeout=2.0).request_generation == 1
        with pytest.raises(PreconditionError, match="newer training resource preview"):
            obsolete.result(timeout=2.0)
        assert latest.result(timeout=2.0).request_generation == 3
        assert estimate_calls == [1, 3]
    finally:
        release_first.set()
        assert coordinator.close(timeout=2.0)


def test_generation_is_rechecked_after_estimation() -> None:
    estimate_started = Event()
    release_estimate = Event()
    current_generation = 7

    def estimate(request, _context):
        estimate_started.set()
        assert release_estimate.wait(timeout=2.0)
        return _result(request)

    coordinator = TrainingResourcePreviewCoordinator(
        estimate=estimate,
        generation_is_current=lambda generation: generation == current_generation,
        registry=OwnedWorkRegistry(),
    )
    try:
        ticket = coordinator.submit(_request(request_generation=1), _context())
        assert estimate_started.wait(timeout=2.0)
        current_generation = 8
        release_estimate.set()

        with pytest.raises(PreconditionError, match="Training context changed"):
            ticket.result(timeout=2.0)
    finally:
        release_estimate.set()
        assert coordinator.close(timeout=2.0)


def test_close_fences_new_work_and_joins_owned_non_daemon_worker() -> None:
    estimate_started = Event()
    release_estimate = Event()

    def estimate(request, _context):
        estimate_started.set()
        assert release_estimate.wait(timeout=2.0)
        return _result(request)

    coordinator = TrainingResourcePreviewCoordinator(
        estimate=estimate,
        generation_is_current=lambda _generation: True,
        registry=OwnedWorkRegistry(),
    )
    ticket = coordinator.submit(_request(request_generation=1), _context())
    assert estimate_started.wait(timeout=2.0)
    assert coordinator.background_work_snapshot() == {
        "idle": False,
        "remaining_workers": 1,
        "alive_workers": 1,
        "active_jobs": 1,
        "pending_jobs": 0,
    }
    assert ticket.done is False

    assert coordinator.close(timeout=0.0) is False
    with pytest.raises(PreconditionError, match="closing"):
        coordinator.submit(_request(request_generation=2), _context())

    release_estimate.set()

    with pytest.raises(PreconditionError, match="closing"):
        ticket.result(timeout=2.0)
    assert coordinator.close(timeout=2.0)
    assert ticket.done is True
    assert coordinator.background_work_snapshot() == {
        "idle": True,
        "remaining_workers": 0,
        "alive_workers": 0,
        "active_jobs": 0,
        "pending_jobs": 0,
    }
    worker = coordinator.worker_thread
    assert worker is None or not worker.is_alive()

    assert coordinator.cancel_close() is True
    retried = coordinator.submit(_request(request_generation=2), _context())
    assert retried.result(timeout=2.0).request_generation == 2
    assert coordinator.close(timeout=2.0)


def test_worker_exits_after_queue_becomes_idle() -> None:
    coordinator = TrainingResourcePreviewCoordinator(
        estimate=lambda request, _context: _result(request),
        generation_is_current=lambda _generation: True,
        registry=OwnedWorkRegistry(),
    )

    result = coordinator.submit(_request(request_generation=1), _context()).result(
        timeout=2.0
    )

    assert result.request_generation == 1
    assert coordinator.wait_for_idle(timeout=2.0)
    assert coordinator.worker_thread is None
