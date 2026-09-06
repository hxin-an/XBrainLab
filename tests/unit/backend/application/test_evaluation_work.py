from __future__ import annotations

from threading import Event, Thread
from typing import Any, cast

import numpy as np
import pytest

from XBrainLab.backend.application.evaluation_render import (
    EvaluationPlanIdentity,
    EvaluationRenderData,
    EvaluationRenderPublication,
    EvaluationRenderRequest,
    EvaluationSummaryIdentity,
)
from XBrainLab.backend.application.evaluation_work import EvaluationWorkController
from XBrainLab.backend.application.owned_work import (
    OwnedOperationCancelledError,
    OwnedOperationClaimError,
    OwnedWorkKind,
    OwnedWorkPhase,
    OwnedWorkRegistry,
    current_owned_operation_id,
    owned_work_checkpoint,
)
from XBrainLab.backend.training_state_contract import (
    TrainingReadBoundary,
    TrainingStateToken,
)


def _request(generation: int = 3) -> EvaluationRenderRequest:
    return EvaluationRenderRequest(
        publication_generation=generation,
        selection=EvaluationPlanIdentity(plan_index=0),
        trainer_identity="evaluation-test",
        split_specification_fingerprint="split-specification-sha256",
        split_epoch_revision=5,
    )


def _publication(request: EvaluationRenderRequest) -> EvaluationRenderPublication:
    selection = cast(EvaluationPlanIdentity, request.selection)
    return EvaluationRenderPublication(
        request=request,
        generation=request.publication_generation,
        training_boundary=TrainingReadBoundary(
            trainer_identity="evaluation-test",
            token=TrainingStateToken(generation=7, stable=True),
        ),
        data=EvaluationRenderData(
            labels=np.array([0, 1]),
            outputs=np.array([[0.8, 0.2], [0.1, 0.9]]),
            metrics={},
            class_labels={0: "Left", 1: "Right"},
            summary_identity=EvaluationSummaryIdentity(plan=selection),
            evaluation_split=request.split,
        ),
        split_specification_fingerprint="split-specification-sha256",
        split_epoch_revision=5,
    )


def test_evaluation_work_uses_injected_registry_and_terminal_identity() -> None:
    registry = OwnedWorkRegistry()
    observed: dict[str, Any] = {}

    def render(request: EvaluationRenderRequest) -> EvaluationRenderPublication:
        operation_id = current_owned_operation_id()
        assert operation_id is not None
        observed["operation_id"] = operation_id
        observed["running"] = registry.snapshot(operation_id)
        owned_work_checkpoint("Pooling evaluation folds", completed=1, total=2)
        observed["progress"] = registry.snapshot(operation_id)
        return _publication(request)

    controller = EvaluationWorkController(registry=registry, render=render)
    scheduled = controller.begin(_request())

    publication = controller.run(scheduled.operation_id, _request())

    terminal = registry.snapshot(scheduled.operation_id)
    assert publication.request == _request()
    assert observed["operation_id"] == scheduled.operation_id
    assert observed["running"].phase is OwnedWorkPhase.RUNNING
    assert observed["progress"].stage == "Pooling evaluation folds"
    assert observed["progress"].completed == 1
    assert observed["progress"].total == 2
    assert scheduled.kind is OwnedWorkKind.EVALUATION
    assert terminal.phase is OwnedWorkPhase.COMPLETED
    assert terminal.operation_id == scheduled.operation_id


def test_evaluation_work_cancel_is_lock_independent_and_retryable() -> None:
    registry = OwnedWorkRegistry()
    started = Event()
    release = Event()
    failures: list[BaseException] = []

    def blocking_render(
        request: EvaluationRenderRequest,
    ) -> EvaluationRenderPublication:
        started.set()
        release.wait(timeout=1.0)
        owned_work_checkpoint("Pooling evaluation folds", completed=1, total=2)
        return _publication(request)

    controller = EvaluationWorkController(registry=registry, render=blocking_render)
    scheduled = controller.begin(_request())

    def run() -> None:
        try:
            controller.run(scheduled.operation_id, _request())
        except BaseException as exc:  # pragma: no branch - asserted below
            failures.append(exc)

    worker = Thread(target=run, name="test-evaluation-work")
    worker.start()
    assert started.wait(timeout=1.0)

    assert controller.cancel(scheduled.operation_id) is True
    assert registry.snapshot(scheduled.operation_id).phase is OwnedWorkPhase.CANCELLING
    release.set()
    worker.join(timeout=1.0)

    assert not worker.is_alive()
    assert len(failures) == 1
    assert isinstance(failures[0], OwnedOperationCancelledError)
    assert registry.snapshot(scheduled.operation_id).phase is OwnedWorkPhase.CANCELLED

    retry = controller.begin(_request(generation=4))
    controller = EvaluationWorkController(
        registry=registry,
        render=lambda request: _publication(request),
    )
    assert controller.run(retry.operation_id, _request(generation=4)).request == (
        _request(generation=4)
    )
    assert registry.snapshot(retry.operation_id).phase is OwnedWorkPhase.COMPLETED


def test_evaluation_work_keeps_indeterminate_stage_without_unowned_heartbeat_thread() -> (
    None
):
    registry = OwnedWorkRegistry()
    started = Event()
    release = Event()

    def blocking_render(
        request: EvaluationRenderRequest,
    ) -> EvaluationRenderPublication:
        owned_work_checkpoint("Copying evaluation predictions")
        started.set()
        release.wait(timeout=1.0)
        return _publication(request)

    controller = EvaluationWorkController(registry=registry, render=blocking_render)
    scheduled = controller.begin(_request())
    worker = Thread(
        target=controller.run,
        args=(scheduled.operation_id, _request()),
        name="test-evaluation-heartbeat",
    )
    worker.start()
    assert started.wait(timeout=1.0)
    running = registry.snapshot(scheduled.operation_id)

    release.set()
    worker.join(timeout=1.0)

    assert running.stage == "Copying evaluation predictions"
    assert running.indeterminate is True
    assert not worker.is_alive()
    assert registry.snapshot(scheduled.operation_id).phase is OwnedWorkPhase.COMPLETED


def test_evaluation_work_operation_id_is_single_claim() -> None:
    registry = OwnedWorkRegistry()
    controller = EvaluationWorkController(
        registry=registry,
        render=lambda request: _publication(request),
    )
    request = _request()
    scheduled = controller.begin(request)

    controller.run(scheduled.operation_id, request)

    with pytest.raises(OwnedOperationClaimError) as exc_info:
        controller.run(scheduled.operation_id, request)
    assert exc_info.value.reason == "terminal_replay"


def test_evaluation_work_rejects_an_operation_for_a_different_request() -> None:
    registry = OwnedWorkRegistry()
    controller = EvaluationWorkController(
        registry=registry,
        render=lambda request: _publication(request),
    )
    scheduled = controller.begin(_request(generation=3))

    with pytest.raises(OwnedOperationClaimError) as exc_info:
        controller.run(scheduled.operation_id, _request(generation=4))

    assert exc_info.value.reason == "command_mismatch"
    assert registry.snapshot(scheduled.operation_id).phase is OwnedWorkPhase.FAILED
