"""Lifecycle contracts for automatic post-training saliency jobs."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from threading import Event, Lock
from threading import Thread as WorkerThread
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest
import torch

from XBrainLab.backend.exceptions import (
    SaliencyCancellationTimeoutError,
    StaleSaliencyUpdateError,
)
from XBrainLab.backend.training.training_plan import (
    PreparedSaliencyUpdate,
    SaliencyUpdatePlan,
)
from XBrainLab.backend.training_manager import (
    PostTrainingSaliencyTarget,
    TrainingManager,
    post_training_saliency_target,
)
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    PostTrainingSaliencyScheduleDisposition,
    PostTrainingSaliencyScheduleOutcome,
    PostTrainingSaliencyScheduleReason,
    PostTrainingSaliencyStatus,
    TrainingOutcomeState,
    TrainingRunIdentity,
    TrainingStateToken,
    TrainingTerminalOutcome,
)

_BASELINE_PARAMS = {
    "_profile": "recommended",
    "_methods": ["Gradient", "Gradient * Input"],
}


@dataclass
class _FinishedRecord:
    eval_record: object

    def is_finished(self) -> bool:
        return True


class _Holder:
    def __init__(self, compute) -> None:
        self.records = [_FinishedRecord(eval_record=object())]
        self.compute = compute
        self.generation = 7
        self.last_params: dict[str, Any] = {}

    def get_plans(self) -> list[_FinishedRecord]:
        return self.records

    def prepare_saliency_update_plan(self, _params, *, records):
        assert records
        return SaliencyUpdatePlan(
            holder=self,
            saliency_params=dict(_params),
            tracker_generation=self.generation,
            records=tuple((record, record.eval_record) for record in records),
        )

    def compute_saliency_update(self, plan, *, should_cancel):
        result = self.compute(plan, should_cancel)
        if isinstance(result, PreparedSaliencyUpdate):
            return result
        if isinstance(result, SimpleNamespace) and hasattr(result, "eval_records"):
            return result
        # Most lifecycle cases only need an opaque successful expensive-compute
        # sentinel. Keep the production seam typed: the fixture translates that
        # sentinel into one real PreparedSaliencyUpdate.
        return PreparedSaliencyUpdate(
            plan=plan,
            eval_records=tuple(
                (record, previous_eval_record, object())
                for record, previous_eval_record in plan.records
            ),
        )


class _Trainer:
    def __init__(self, holder: _Holder, run: TrainingRunIdentity) -> None:
        self.holder = holder
        self.outcome = TrainingTerminalOutcome(
            state=TrainingOutcomeState.COMPLETED,
            run=run,
        )
        self.run_calls: list[bool] = []
        self.generation = 7

    def get_terminal_outcome(self) -> TrainingTerminalOutcome:
        return self.outcome

    def get_state_snapshot_token(self) -> TrainingStateToken:
        return TrainingStateToken(generation=self.generation, stable=True)

    def get_state_snapshot_identity(self) -> str:
        run = self.outcome.run
        if run is None:
            raise AssertionError("completed test trainer must expose a run identity")
        return run.trainer_id

    def get_training_plan_holders(self) -> list[_Holder]:
        return [self.holder]

    def is_running(self) -> bool:
        return False

    def clean(self, *, force_update: bool) -> None:
        assert force_update is False

    def run(self, *, interact: bool) -> None:
        self.run_calls.append(interact)


def _target(run: TrainingRunIdentity) -> PostTrainingSaliencyTarget:
    return PostTrainingSaliencyTarget(
        run=run,
        finished_runs_before=0,
        finished_runs_after=1,
        append=True,
    )


def _manager_with_compute(compute) -> tuple[TrainingManager, TrainingRunIdentity]:
    run = TrainingRunIdentity(trainer_id="saliency-lifecycle", run_id=1)
    manager = TrainingManager()
    manager._saliency_job_lock = Lock()
    manager.trainer = cast(Any, _Trainer(_Holder(compute), run))
    return manager, run


def _publish_updates(
    _updates,
    *,
    manager_params,
    publish_manager_params,
) -> None:
    publish_manager_params(manager_params)


def test_post_training_saliency_is_idle_before_any_job() -> None:
    status = TrainingManager().get_post_training_saliency_status()

    assert status.phase is PostTrainingSaliencyPhase.IDLE
    assert status.generation == 0
    assert status.run is None
    assert status.methods == ()


def test_post_training_saliency_reports_pending_running_and_succeeded() -> None:
    compute_started = Event()
    release_compute = Event()

    def compute(_plan, _should_cancel):
        compute_started.set()
        assert release_compute.wait(timeout=2.0)
        return object()

    manager, run = _manager_with_compute(compute)
    with patch(
        "XBrainLab.backend.training.training_plan.publish_prepared_saliency_updates",
        side_effect=_publish_updates,
    ):
        with post_training_saliency_target(_target(run)):
            schedule = manager.set_saliency_params(_BASELINE_PARAMS)
            assert isinstance(schedule, PostTrainingSaliencyScheduleOutcome)
            assert schedule.disposition is (
                PostTrainingSaliencyScheduleDisposition.SCHEDULED
            )
            assert schedule.reason is PostTrainingSaliencyScheduleReason.SCHEDULED
            pending = manager.get_post_training_saliency_status()
            assert schedule.status == pending
            assert pending.phase is PostTrainingSaliencyPhase.PENDING
            assert pending.run == run
            assert pending.methods == ("Gradient", "Gradient * Input")

        assert compute_started.wait(timeout=2.0)
        running = manager.get_post_training_saliency_status()
        assert running.phase is PostTrainingSaliencyPhase.RUNNING
        assert running.generation == pending.generation

        release_compute.set()
        assert manager.wait_for_saliency_job(timeout=2.0)

    succeeded = manager.get_post_training_saliency_status()
    assert succeeded.phase is PostTrainingSaliencyPhase.SUCCEEDED
    assert succeeded.generation == pending.generation
    assert succeeded.error_code is None
    assert manager.saliency_params == _BASELINE_PARAMS


def test_post_training_saliency_schedule_outcome_is_published_on_target() -> None:
    manager, run = _manager_with_compute(lambda _plan, _should_cancel: object())
    target = _target(run)

    with post_training_saliency_target(target):
        schedule = manager.set_saliency_params(_BASELINE_PARAMS)
        assert target.schedule_outcome == schedule
        manager.cancel_saliency_job()

    assert manager.wait_for_saliency_job(timeout=2.0)


def test_post_training_saliency_reports_expected_class_coverage_unavailability_without_generic_failure() -> (
    None
):
    manager, run = _manager_with_compute(
        lambda _plan, _should_cancel: SimpleNamespace(eval_records=())
    )
    with patch(
        "XBrainLab.backend.training.training_plan.publish_prepared_saliency_updates"
    ) as publish:
        with post_training_saliency_target(_target(run)):
            schedule = manager.set_saliency_params(_BASELINE_PARAMS)
        assert schedule.disposition is PostTrainingSaliencyScheduleDisposition.SCHEDULED
        assert manager.wait_for_saliency_job(timeout=2.0)

    status = manager.get_post_training_saliency_status()
    assert status.phase is PostTrainingSaliencyPhase.FAILED
    assert status.error_code == "evaluation_unavailable"
    assert "unavailable" in (status.message or "")
    publish.assert_not_called()


def test_explicit_target_computes_only_selected_members_in_canonical_order() -> None:
    calls: list[tuple[int, int]] = []
    published: list[list[object]] = []
    holders: list[_Holder] = []

    def compute(plan, _should_cancel):
        holder_index = holders.index(plan.holder)
        record, _previous_eval_record = plan.records[0]
        calls.append((holder_index, plan.holder.records.index(record)))
        return object()

    holders.extend([_Holder(compute), _Holder(compute)])
    for holder in holders:
        holder.records.append(_FinishedRecord(eval_record=object()))
    run = TrainingRunIdentity(trainer_id="selected-saliency-members", run_id=1)
    trainer = _Trainer(holders[0], run)
    trainer.get_training_plan_holders = lambda: holders  # type: ignore[method-assign]
    manager = TrainingManager()
    manager._saliency_job_lock = Lock()
    manager.trainer = cast(Any, trainer)
    target = PostTrainingSaliencyTarget(
        run=run,
        finished_runs_before=0,
        finished_runs_after=4,
        append=False,
        explicit=True,
        selected_members=((0, 1), (1, 1)),
    )

    def publish(updates, *, manager_params, publish_manager_params):
        published.append(list(updates))
        publish_manager_params(manager_params)

    with patch(
        "XBrainLab.backend.training.training_plan.publish_prepared_saliency_updates",
        side_effect=publish,
    ):
        with post_training_saliency_target(target):
            schedule = manager.set_saliency_params(_BASELINE_PARAMS)
        assert manager.wait_for_saliency_job(timeout=2.0)

    assert isinstance(schedule, PostTrainingSaliencyScheduleOutcome)
    assert schedule.disposition is PostTrainingSaliencyScheduleDisposition.SCHEDULED
    assert manager.get_post_training_saliency_status().phase is (
        PostTrainingSaliencyPhase.SUCCEEDED
    )
    assert calls == [(0, 1), (1, 1)]
    assert len(published) == 1
    assert len(published[0]) == 2


def test_explicit_target_failure_never_partially_publishes_members() -> None:
    compute_count = 0
    holders: list[_Holder] = []

    def compute(_plan, _should_cancel):
        nonlocal compute_count
        compute_count += 1
        if compute_count == 2:
            raise RuntimeError("second selected fold failed")
        return object()

    holders.extend([_Holder(compute), _Holder(compute)])
    run = TrainingRunIdentity(trainer_id="atomic-saliency-members", run_id=1)
    trainer = _Trainer(holders[0], run)
    trainer.get_training_plan_holders = lambda: holders  # type: ignore[method-assign]
    manager = TrainingManager()
    manager._saliency_job_lock = Lock()
    manager.trainer = cast(Any, trainer)
    manager.saliency_params = {"_methods": ["Gradient"]}
    target = PostTrainingSaliencyTarget(
        run=run,
        finished_runs_before=0,
        finished_runs_after=2,
        append=False,
        explicit=True,
        selected_members=((0, 0), (1, 0)),
    )

    with patch(
        "XBrainLab.backend.training.training_plan.publish_prepared_saliency_updates"
    ) as publish:
        with post_training_saliency_target(target):
            schedule = manager.set_saliency_params(_BASELINE_PARAMS)
        assert manager.wait_for_saliency_job(timeout=2.0)

    assert isinstance(schedule, PostTrainingSaliencyScheduleOutcome)
    assert schedule.disposition is PostTrainingSaliencyScheduleDisposition.SCHEDULED
    assert manager.get_post_training_saliency_status().phase is (
        PostTrainingSaliencyPhase.FAILED
    )
    assert compute_count == 2
    publish.assert_not_called()
    assert manager.saliency_params == {"_methods": ["Gradient"]}


def test_explicit_selected_members_with_one_unprepared_record_fail_atomically() -> None:
    """A selected Fold Set cannot publish only the members with an eval split."""
    holders: list[_Holder] = []

    def compute(plan, _should_cancel):
        record, _previous_eval_record = plan.records[0]
        if plan.holder is holders[1]:
            # Simulate a real holder which cannot select a valid evaluation split.
            return PreparedSaliencyUpdate(plan=plan, eval_records=())
        return PreparedSaliencyUpdate(
            plan=plan,
            eval_records=((record, record.eval_record, object()),),
        )

    holders.extend([_Holder(compute), _Holder(compute)])
    run = TrainingRunIdentity(trainer_id="partial-selected-members", run_id=1)
    trainer = _Trainer(holders[0], run)
    trainer.get_training_plan_holders = lambda: holders  # type: ignore[method-assign]
    manager = TrainingManager()
    manager._saliency_job_lock = Lock()
    manager.trainer = cast(Any, trainer)
    manager.saliency_params = {"_methods": ["Gradient"]}
    original_eval_records = tuple(holder.records[0].eval_record for holder in holders)
    target = PostTrainingSaliencyTarget(
        run=run,
        finished_runs_before=0,
        finished_runs_after=2,
        append=False,
        explicit=True,
        selected_members=((0, 0), (1, 0)),
    )

    with patch(
        "XBrainLab.backend.training.training_plan.publish_prepared_saliency_updates"
    ) as publish:
        with post_training_saliency_target(target):
            schedule = manager.set_saliency_params(_BASELINE_PARAMS)
        assert manager.wait_for_saliency_job(timeout=2.0)

    assert schedule.disposition is PostTrainingSaliencyScheduleDisposition.SCHEDULED
    status = manager.get_post_training_saliency_status()
    assert status.phase is PostTrainingSaliencyPhase.FAILED
    assert status.error_code == "evaluation_unavailable"
    publish.assert_not_called()
    assert (
        tuple(holder.records[0].eval_record for holder in holders)
        == original_eval_records
    )
    assert manager.saliency_params == {"_methods": ["Gradient"]}


def test_explicit_selected_members_reject_wrong_record_with_same_count() -> None:
    """A count-matching update cannot substitute a different selected record."""
    holders: list[_Holder] = []

    def compute(plan, _should_cancel):
        record, previous_eval_record = plan.records[0]
        if plan.holder is holders[0]:
            wrong_record = holders[1].records[0]
            return PreparedSaliencyUpdate(
                plan=plan,
                eval_records=((wrong_record, wrong_record.eval_record, object()),),
            )
        return PreparedSaliencyUpdate(
            plan=plan,
            eval_records=((record, previous_eval_record, object()),),
        )

    holders.extend([_Holder(compute), _Holder(compute)])
    run = TrainingRunIdentity(trainer_id="wrong-selected-record", run_id=1)
    trainer = _Trainer(holders[0], run)
    trainer.get_training_plan_holders = lambda: holders  # type: ignore[method-assign]
    manager = TrainingManager()
    manager._saliency_job_lock = Lock()
    manager.trainer = cast(Any, trainer)
    target = PostTrainingSaliencyTarget(
        run=run,
        finished_runs_before=0,
        finished_runs_after=2,
        append=False,
        explicit=True,
        selected_members=((0, 0), (1, 0)),
    )

    with patch(
        "XBrainLab.backend.training.training_plan.publish_prepared_saliency_updates"
    ) as publish:
        with post_training_saliency_target(target):
            manager.set_saliency_params(_BASELINE_PARAMS)
        assert manager.wait_for_saliency_job(timeout=2.0)

    status = manager.get_post_training_saliency_status()
    assert status.phase is PostTrainingSaliencyPhase.FAILED
    assert status.error_code == "evaluation_unavailable"
    publish.assert_not_called()


def test_explicit_selected_members_cancel_then_retry_publishes_one_atomic_batch() -> (
    None
):
    """A cancelled Fold Set keeps prior artifacts and retries the same members."""
    first_member_started = Event()
    cancellation_poll = Event()
    calls: list[tuple[str, int, int]] = []
    published: list[list[object]] = []
    holders: list[_Holder] = []
    cancelled_attempt = True

    def compute(plan, should_cancel):
        holder_index = holders.index(plan.holder)
        record_index = plan.holder.records.index(plan.records[0][0])
        attempt = "cancelled" if cancelled_attempt else "retry"
        calls.append((attempt, holder_index, record_index))
        if cancelled_attempt:
            first_member_started.set()
            while not should_cancel():
                cancellation_poll.wait(timeout=0.01)
            raise StaleSaliencyUpdateError
        return object()

    holders.extend([_Holder(compute), _Holder(compute)])
    run = TrainingRunIdentity(trainer_id="retry-selected-members", run_id=1)
    trainer = _Trainer(holders[0], run)
    trainer.get_training_plan_holders = lambda: holders  # type: ignore[method-assign]
    manager = TrainingManager()
    manager._saliency_job_lock = Lock()
    manager.trainer = cast(Any, trainer)
    manager.saliency_params = {"_methods": ["Gradient"]}
    selected_members = ((0, 0), (1, 0))

    def target() -> PostTrainingSaliencyTarget:
        return PostTrainingSaliencyTarget(
            run=run,
            finished_runs_before=0,
            finished_runs_after=2,
            append=False,
            explicit=True,
            selected_members=selected_members,
        )

    def publish(updates, *, manager_params, publish_manager_params):
        published.append(list(updates))
        publish_manager_params(manager_params)

    with patch(
        "XBrainLab.backend.training.training_plan.publish_prepared_saliency_updates",
        side_effect=publish,
    ):
        with post_training_saliency_target(target()):
            first_schedule = manager.set_saliency_params(_BASELINE_PARAMS)
        assert first_member_started.wait(timeout=2.0)
        manager.cancel_saliency_job()
        assert manager.wait_for_saliency_job(timeout=2.0)

        assert isinstance(first_schedule, PostTrainingSaliencyScheduleOutcome)
        assert (
            first_schedule.disposition
            is PostTrainingSaliencyScheduleDisposition.SCHEDULED
        )
        assert manager.get_post_training_saliency_status().phase is (
            PostTrainingSaliencyPhase.CANCELLED
        )
        assert published == []
        assert manager.saliency_params == {"_methods": ["Gradient"]}

        cancelled_attempt = False
        with post_training_saliency_target(target()):
            retry_schedule = manager.set_saliency_params(_BASELINE_PARAMS)
        assert manager.wait_for_saliency_job(timeout=2.0)

    assert isinstance(retry_schedule, PostTrainingSaliencyScheduleOutcome)
    assert (
        retry_schedule.disposition is PostTrainingSaliencyScheduleDisposition.SCHEDULED
    )
    assert manager.get_post_training_saliency_status().phase is (
        PostTrainingSaliencyPhase.SUCCEEDED
    )
    assert calls == [("cancelled", 0, 0), ("retry", 0, 0), ("retry", 1, 0)]
    assert len(published) == 1
    assert len(published[0]) == 2
    assert manager.saliency_params == _BASELINE_PARAMS


@pytest.mark.parametrize(
    "members",
    [(), ((0, 0), (0, 0)), ((1, 0), (0, 0)), ((0, -1),)],
)
def test_explicit_target_rejects_invalid_selected_members(
    members: tuple[tuple[int, int], ...],
) -> None:
    run = TrainingRunIdentity(trainer_id="invalid-saliency-members", run_id=1)

    with pytest.raises((TypeError, ValueError)):
        PostTrainingSaliencyTarget(
            run=run,
            finished_runs_before=0,
            finished_runs_after=2,
            append=False,
            explicit=True,
            selected_members=members,
        )


@pytest.mark.parametrize(
    ("scenario", "disposition", "reason"),
    [
        (
            "trainer_unavailable",
            PostTrainingSaliencyScheduleDisposition.STALE,
            PostTrainingSaliencyScheduleReason.TRAINER_UNAVAILABLE,
        ),
        (
            "unsupported_profile",
            PostTrainingSaliencyScheduleDisposition.REJECTED,
            PostTrainingSaliencyScheduleReason.UNSUPPORTED_PROFILE,
        ),
        (
            "training_not_completed",
            PostTrainingSaliencyScheduleDisposition.STALE,
            PostTrainingSaliencyScheduleReason.TRAINING_NOT_COMPLETED,
        ),
        (
            "training_run_changed",
            PostTrainingSaliencyScheduleDisposition.STALE,
            PostTrainingSaliencyScheduleReason.TRAINING_RUN_CHANGED,
        ),
        (
            "training_state_unavailable",
            PostTrainingSaliencyScheduleDisposition.REJECTED,
            PostTrainingSaliencyScheduleReason.TRAINING_STATE_UNAVAILABLE,
        ),
        (
            "training_state_unstable",
            PostTrainingSaliencyScheduleDisposition.STALE,
            PostTrainingSaliencyScheduleReason.TRAINING_STATE_UNSTABLE,
        ),
        (
            "finished_run_count_changed",
            PostTrainingSaliencyScheduleDisposition.STALE,
            PostTrainingSaliencyScheduleReason.FINISHED_RUN_COUNT_CHANGED,
        ),
        (
            "no_new_finished_runs",
            PostTrainingSaliencyScheduleDisposition.REJECTED,
            PostTrainingSaliencyScheduleReason.NO_NEW_FINISHED_RUNS,
        ),
        (
            "no_finished_records",
            PostTrainingSaliencyScheduleDisposition.REJECTED,
            PostTrainingSaliencyScheduleReason.NO_FINISHED_RECORDS,
        ),
        (
            "plan_preparation_failed",
            PostTrainingSaliencyScheduleDisposition.REJECTED,
            PostTrainingSaliencyScheduleReason.PLAN_PREPARATION_FAILED,
        ),
        (
            "training_generation_changed",
            PostTrainingSaliencyScheduleDisposition.STALE,
            PostTrainingSaliencyScheduleReason.TRAINING_GENERATION_CHANGED,
        ),
        (
            "previous_job_not_cancelled",
            PostTrainingSaliencyScheduleDisposition.REJECTED,
            PostTrainingSaliencyScheduleReason.PREVIOUS_JOB_NOT_CANCELLED,
        ),
        (
            "trainer_replaced",
            PostTrainingSaliencyScheduleDisposition.STALE,
            PostTrainingSaliencyScheduleReason.TRAINER_REPLACED,
        ),
        (
            "thread_start_failed",
            PostTrainingSaliencyScheduleDisposition.REJECTED,
            PostTrainingSaliencyScheduleReason.THREAD_START_FAILED,
        ),
    ],
)
def test_scheduler_returns_typed_terminal_outcome_for_every_rejection(
    scenario: str,
    disposition: PostTrainingSaliencyScheduleDisposition,
    reason: PostTrainingSaliencyScheduleReason,
) -> None:
    manager, run = _manager_with_compute(lambda _plan, _should_cancel: object())
    trainer = cast(_Trainer, manager.trainer)
    target = _target(run)
    params = dict(_BASELINE_PARAMS)
    patches = []

    if scenario == "trainer_unavailable":
        manager.trainer = None
    elif scenario == "unsupported_profile":
        params = {"_profile": "advanced", "_methods": ["SmoothGrad"]}
    elif scenario == "training_not_completed":
        trainer.outcome = TrainingTerminalOutcome(
            state=TrainingOutcomeState.FAILED,
            run=run,
        )
    elif scenario == "training_run_changed":
        trainer.outcome = TrainingTerminalOutcome(
            state=TrainingOutcomeState.COMPLETED,
            run=TrainingRunIdentity(trainer_id=run.trainer_id, run_id=run.run_id + 1),
        )
    elif scenario == "training_state_unavailable":
        patches.append(
            patch.object(
                trainer,
                "get_state_snapshot_token",
                side_effect=RuntimeError("private token failure"),
            )
        )
    elif scenario == "training_state_unstable":
        patches.append(
            patch.object(
                trainer,
                "get_state_snapshot_token",
                return_value=TrainingStateToken(generation=7, stable=False),
            )
        )
    elif scenario == "finished_run_count_changed":
        target = PostTrainingSaliencyTarget(
            run=run,
            finished_runs_before=0,
            finished_runs_after=2,
            append=True,
        )
    elif scenario == "no_new_finished_runs":
        target = PostTrainingSaliencyTarget(
            run=run,
            finished_runs_before=1,
            finished_runs_after=1,
            append=True,
        )
    elif scenario == "no_finished_records":
        trainer.holder.records = []
        target = PostTrainingSaliencyTarget(
            run=run,
            finished_runs_before=0,
            finished_runs_after=0,
            append=False,
        )
    elif scenario == "plan_preparation_failed":
        patches.append(
            patch.object(
                trainer.holder,
                "prepare_saliency_update_plan",
                side_effect=RuntimeError("private plan failure"),
            )
        )
    elif scenario == "training_generation_changed":
        patches.append(
            patch.object(
                trainer.holder,
                "prepare_saliency_update_plan",
                return_value=SimpleNamespace(
                    holder=trainer.holder,
                    tracker_generation=8,
                ),
            )
        )
    elif scenario == "previous_job_not_cancelled":
        patches.append(
            patch.object(
                manager,
                "_cancel_post_training_saliency",
                side_effect=SaliencyCancellationTimeoutError,
            )
        )
    elif scenario == "trainer_replaced":
        replacement = _Trainer(trainer.holder, run)

        def replace_trainer(
            *,
            wait: bool,
            request_generation: int | None = None,
        ) -> bool:
            assert wait is True
            assert request_generation is not None
            manager.trainer = cast(Any, replacement)
            return True

        patches.append(
            patch.object(
                manager,
                "_cancel_post_training_saliency",
                side_effect=replace_trainer,
            )
        )
    elif scenario == "thread_start_failed":

        class _ThreadStartFailure:
            def __init__(self, *args, **kwargs) -> None:
                del args, kwargs

            def start(self) -> None:
                raise RuntimeError("thread start failed")

        patches.append(
            patch(
                "XBrainLab.backend.training_manager.Thread",
                _ThreadStartFailure,
            )
        )
    else:  # pragma: no cover - parametrization is exhaustive
        raise AssertionError(f"Unhandled scenario: {scenario}")

    with post_training_saliency_target(target), contextlib.ExitStack() as stack:
        for active_patch in patches:
            stack.enter_context(active_patch)
        schedule = manager.set_saliency_params(params)

    assert isinstance(schedule, PostTrainingSaliencyScheduleOutcome)
    assert schedule.disposition is disposition
    assert schedule.reason is reason
    assert target.schedule_outcome == schedule
    assert manager.wait_for_saliency_job(timeout=0.1)
    status = manager.get_post_training_saliency_status()
    assert status == schedule.status
    assert status.phase.terminal is True
    assert status.message == schedule.message
    if disposition is PostTrainingSaliencyScheduleDisposition.REJECTED:
        assert status.phase is PostTrainingSaliencyPhase.FAILED
        assert status.error_code == reason.value
    else:
        assert status.phase is PostTrainingSaliencyPhase.CANCELLED


def test_thread_start_failure_publishes_terminal_after_scheduler_lock_release() -> None:
    manager, run = _manager_with_compute(lambda _plan, _should_cancel: object())
    target = _target(run)
    terminal_events: list[PostTrainingSaliencyStatus] = []
    lock_states: list[bool] = []

    class _ThreadStartFailure:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        def start(self) -> None:
            raise RuntimeError("thread start failed")

    def observe_terminal(status: PostTrainingSaliencyStatus) -> None:
        acquired = manager._saliency_job_lock.acquire(blocking=False)
        lock_states.append(acquired)
        if acquired:
            manager._saliency_job_lock.release()
        terminal_events.append(status)

    manager.subscribe_post_training_saliency_terminal(observe_terminal)

    with (
        patch("XBrainLab.backend.training_manager.Thread", _ThreadStartFailure),
        manager.defer_post_training_saliency_terminal_notifications(),
    ):
        with post_training_saliency_target(target):
            schedule = manager.set_saliency_params(_BASELINE_PARAMS)
        assert terminal_events == []

    assert isinstance(schedule, PostTrainingSaliencyScheduleOutcome)
    assert schedule.reason is PostTrainingSaliencyScheduleReason.THREAD_START_FAILED
    assert schedule.status.phase is PostTrainingSaliencyPhase.FAILED
    assert terminal_events == [schedule.status]
    assert lock_states == [True]


@pytest.mark.parametrize("scenario", ["trainer_replaced", "thread_construction_failed"])
def test_scheduler_terminal_paths_do_not_reacquire_non_reentrant_job_lock(
    scenario: str,
) -> None:
    manager, run = _manager_with_compute(lambda _plan, _should_cancel: object())
    trainer = cast(_Trainer, manager.trainer)
    target = _target(run)
    schedules: list[PostTrainingSaliencyScheduleOutcome | None] = []
    errors: list[BaseException] = []

    if scenario == "trainer_replaced":
        replacement = _Trainer(trainer.holder, run)

        def replace_trainer(
            *,
            wait: bool,
            request_generation: int | None = None,
        ) -> bool:
            assert wait is True
            assert request_generation is not None
            manager.trainer = cast(Any, replacement)
            return True

        scheduler_patch = patch.object(
            manager,
            "_cancel_post_training_saliency",
            side_effect=replace_trainer,
        )
        expected_reason = PostTrainingSaliencyScheduleReason.TRAINER_REPLACED
    else:

        class _ThreadConstructionFailure:
            def __init__(self, *args, **kwargs) -> None:
                del args, kwargs
                raise RuntimeError("thread construction failed")

        scheduler_patch = patch(
            "XBrainLab.backend.training_manager.Thread",
            _ThreadConstructionFailure,
        )
        expected_reason = PostTrainingSaliencyScheduleReason.THREAD_START_FAILED

    def schedule() -> None:
        try:
            with post_training_saliency_target(target):
                schedules.append(manager.set_saliency_params(_BASELINE_PARAMS))
        except BaseException as exc:  # pragma: no cover - asserted in caller
            errors.append(exc)

    worker = WorkerThread(target=schedule, daemon=True)
    with scheduler_patch:
        worker.start()
        worker.join(timeout=1.0)

    assert not worker.is_alive(), f"{scenario} deadlocked on _saliency_job_lock"
    assert errors == []
    assert len(schedules) == 1
    outcome = schedules[0]
    assert isinstance(outcome, PostTrainingSaliencyScheduleOutcome)
    assert outcome.reason is expected_reason
    assert outcome.status.phase.terminal is True


def test_clean_trainer_retires_previous_saliency_success_generation() -> None:
    """A removed trainer must not leave its saliency status looking current."""
    manager, run = _manager_with_compute(lambda _plan, _should_cancel: object())
    with patch(
        "XBrainLab.backend.training.training_plan.publish_prepared_saliency_updates",
        side_effect=_publish_updates,
    ):
        with post_training_saliency_target(_target(run)):
            manager.set_saliency_params(_BASELINE_PARAMS)
        assert manager.wait_for_saliency_job(timeout=2.0)

    succeeded = manager.get_post_training_saliency_status()
    assert succeeded.phase is PostTrainingSaliencyPhase.SUCCEEDED

    manager.clean_trainer()

    retired = manager.get_post_training_saliency_status()
    assert retired.phase is PostTrainingSaliencyPhase.IDLE
    assert retired.generation > succeeded.generation
    assert retired.run is None
    assert manager.trainer is None


def test_delayed_target_cannot_recreate_owner_after_trainer_deletion() -> None:
    manager, run = _manager_with_compute(lambda _plan, _should_cancel: object())
    terminal_events: list[PostTrainingSaliencyStatus] = []
    manager.subscribe_post_training_saliency_terminal(terminal_events.append)
    with patch(
        "XBrainLab.backend.training.training_plan.publish_prepared_saliency_updates",
        side_effect=_publish_updates,
    ):
        with post_training_saliency_target(_target(run)):
            manager.set_saliency_params(_BASELINE_PARAMS)
        assert manager.wait_for_saliency_job(timeout=2.0)

    manager.clean_trainer()
    retired = manager.get_post_training_saliency_status()
    observed_events = list(terminal_events)

    for _ in range(10):
        delayed = _target(run)
        with post_training_saliency_target(delayed):
            stale = manager.set_saliency_params(_BASELINE_PARAMS)

        assert isinstance(stale, PostTrainingSaliencyScheduleOutcome)
        assert stale.disposition is PostTrainingSaliencyScheduleDisposition.STALE
        assert stale.reason is PostTrainingSaliencyScheduleReason.TRAINER_UNAVAILABLE
        assert delayed.schedule_outcome == stale
        assert manager.get_post_training_saliency_status() == retired
        assert terminal_events == observed_events

    assert retired.phase is PostTrainingSaliencyPhase.IDLE
    assert retired.run is None


def test_starting_new_training_retires_previous_saliency_success_generation() -> None:
    """A new run starts from idle even when the previous baseline succeeded."""
    manager, run = _manager_with_compute(lambda _plan, _should_cancel: object())
    with patch(
        "XBrainLab.backend.training.training_plan.publish_prepared_saliency_updates",
        side_effect=_publish_updates,
    ):
        with post_training_saliency_target(_target(run)):
            manager.set_saliency_params(_BASELINE_PARAMS)
        assert manager.wait_for_saliency_job(timeout=2.0)

    succeeded = manager.get_post_training_saliency_status()
    assert succeeded.phase is PostTrainingSaliencyPhase.SUCCEEDED
    trainer = cast(_Trainer, manager.trainer)

    manager.train(interact=True)

    fresh = manager.get_post_training_saliency_status()
    assert fresh.phase is PostTrainingSaliencyPhase.IDLE
    assert fresh.generation > succeeded.generation
    assert fresh.run is None
    assert trainer.run_calls == [True]


def test_post_training_saliency_general_failure_is_safe_and_terminal() -> None:
    raw_error = "private/path/subject-01 failed"

    def compute(_plan, _should_cancel):
        raise RuntimeError(raw_error)

    manager, run = _manager_with_compute(compute)
    with patch(
        "XBrainLab.backend.training.training_plan.publish_prepared_saliency_updates",
        side_effect=_publish_updates,
    ):
        with post_training_saliency_target(_target(run)):
            manager.set_saliency_params(_BASELINE_PARAMS)
        assert manager.wait_for_saliency_job(timeout=2.0)

    failed = manager.get_post_training_saliency_status()
    assert failed.phase is PostTrainingSaliencyPhase.FAILED
    assert failed.error_code == "computation_failed"
    assert failed.diagnostic_type == "RuntimeError"
    assert raw_error not in (failed.message or "")
    assert manager.saliency_params is None


def test_post_training_saliency_cuda_oom_releases_cache_and_fails_safely() -> None:
    raw_error = "CUDA out of memory: allocation 123456 at private kernel"

    def compute(_plan, _should_cancel):
        raise torch.cuda.OutOfMemoryError(raw_error)

    manager, run = _manager_with_compute(compute)
    with (
        patch(
            "XBrainLab.backend.training.training_plan."
            "publish_prepared_saliency_updates",
            side_effect=_publish_updates,
        ),
        patch("XBrainLab.backend.training_manager.release_cuda_cache") as release_cache,
    ):
        with post_training_saliency_target(_target(run)):
            manager.set_saliency_params(_BASELINE_PARAMS)
        assert manager.wait_for_saliency_job(timeout=2.0)

    failed = manager.get_post_training_saliency_status()
    assert failed.phase is PostTrainingSaliencyPhase.FAILED
    assert failed.error_code == "cuda_oom"
    assert failed.diagnostic_type == "OutOfMemoryError"
    assert raw_error not in (failed.message or "")
    release_cache.assert_called_once()
    assert manager.saliency_params is None


def test_post_training_saliency_cancel_is_terminal_and_never_publishes() -> None:
    compute_started = Event()
    release_compute = Event()
    published = Event()

    def compute(_plan, _should_cancel):
        compute_started.set()
        assert release_compute.wait(timeout=2.0)
        return object()

    def publish(*_args, **_kwargs) -> None:
        published.set()

    manager, run = _manager_with_compute(compute)
    with patch(
        "XBrainLab.backend.training.training_plan.publish_prepared_saliency_updates",
        side_effect=publish,
    ):
        with post_training_saliency_target(_target(run)):
            manager.set_saliency_params(_BASELINE_PARAMS)
        assert compute_started.wait(timeout=2.0)

        manager.cancel_saliency_job()
        cancelled = manager.get_post_training_saliency_status()
        assert cancelled.phase is PostTrainingSaliencyPhase.CANCELLED

        release_compute.set()
        assert manager.wait_for_saliency_job(timeout=2.0)

    assert manager.get_post_training_saliency_status() == cancelled
    assert not published.is_set()
    assert manager.saliency_params is None


def test_stale_request_cannot_cancel_or_replace_newer_running_generation() -> None:
    compute_started = Event()
    release_compute = Event()

    def compute(_plan, _should_cancel):
        compute_started.set()
        assert release_compute.wait(timeout=2.0)
        return object()

    manager, initial_run = _manager_with_compute(compute)
    newer_run = TrainingRunIdentity(
        trainer_id=initial_run.trainer_id,
        run_id=initial_run.run_id + 1,
    )
    trainer = cast(_Trainer, manager.trainer)
    trainer.outcome = TrainingTerminalOutcome(
        state=TrainingOutcomeState.COMPLETED,
        run=newer_run,
    )
    stale_run = TrainingRunIdentity(
        trainer_id=newer_run.trainer_id,
        run_id=newer_run.run_id - 1,
    )
    newer_target = _target(newer_run)

    with patch(
        "XBrainLab.backend.training.training_plan.publish_prepared_saliency_updates",
        side_effect=_publish_updates,
    ):
        with post_training_saliency_target(newer_target):
            newer_schedule = manager.set_saliency_params(_BASELINE_PARAMS)
        assert isinstance(newer_schedule, PostTrainingSaliencyScheduleOutcome)
        assert compute_started.wait(timeout=2.0)

        newer_status = manager.get_post_training_saliency_status()
        assert newer_status.phase is PostTrainingSaliencyPhase.RUNNING

        try:
            for _ in range(10):
                stale_target = _target(stale_run)
                with post_training_saliency_target(stale_target):
                    stale_schedule = manager.set_saliency_params(_BASELINE_PARAMS)

                assert isinstance(
                    stale_schedule,
                    PostTrainingSaliencyScheduleOutcome,
                )
                assert stale_schedule.disposition is (
                    PostTrainingSaliencyScheduleDisposition.STALE
                )
                assert stale_schedule.reason is (
                    PostTrainingSaliencyScheduleReason.TRAINING_RUN_CHANGED
                )
                assert stale_schedule.status.run == stale_run
                assert stale_target.schedule_outcome == stale_schedule
                assert manager.get_post_training_saliency_status() == newer_status
        finally:
            release_compute.set()

        assert manager.wait_for_saliency_job(timeout=2.0)

    completed = manager.get_post_training_saliency_status()
    assert completed.phase is PostTrainingSaliencyPhase.SUCCEEDED
    assert completed.generation == newer_status.generation
    assert completed.run == newer_run


@pytest.mark.parametrize(
    "terminal_phase",
    [
        PostTrainingSaliencyPhase.SUCCEEDED,
        PostTrainingSaliencyPhase.FAILED,
        PostTrainingSaliencyPhase.CANCELLED,
    ],
)
def test_stale_request_after_terminal_cleanup_cannot_rewrite_current_lifecycle(
    terminal_phase: PostTrainingSaliencyPhase,
) -> None:
    """Delayed work from an older training run is request-local after cleanup."""
    compute_started = Event()
    cancellation_published = Event()

    def compute(_plan, should_cancel):
        compute_started.set()
        if terminal_phase is PostTrainingSaliencyPhase.FAILED:
            raise RuntimeError("bounded terminal failure")
        if terminal_phase is PostTrainingSaliencyPhase.CANCELLED:
            assert cancellation_published.wait(timeout=2.0)
            assert should_cancel() is True
        return object()

    manager, stale_run = _manager_with_compute(compute)
    current_run = TrainingRunIdentity(
        trainer_id=stale_run.trainer_id,
        run_id=stale_run.run_id + 1,
    )
    trainer = cast(_Trainer, manager.trainer)
    trainer.outcome = TrainingTerminalOutcome(
        state=TrainingOutcomeState.COMPLETED,
        run=current_run,
    )
    terminal_events: list[PostTrainingSaliencyStatus] = []

    def observe_terminal(status: PostTrainingSaliencyStatus) -> None:
        terminal_events.append(status)
        if status.phase is PostTrainingSaliencyPhase.CANCELLED:
            cancellation_published.set()

    manager.subscribe_post_training_saliency_terminal(observe_terminal)

    with patch(
        "XBrainLab.backend.training.training_plan.publish_prepared_saliency_updates",
        side_effect=_publish_updates,
    ):
        with post_training_saliency_target(_target(current_run)):
            scheduled = manager.set_saliency_params(_BASELINE_PARAMS)
        assert isinstance(scheduled, PostTrainingSaliencyScheduleOutcome)
        assert compute_started.wait(timeout=2.0)
        if terminal_phase is PostTrainingSaliencyPhase.CANCELLED:
            manager.cancel_saliency_job()
        assert manager.wait_for_saliency_job(timeout=2.0)

    current = manager.get_post_training_saliency_status()
    assert current.phase is terminal_phase
    assert current.run == current_run
    assert terminal_events == [current]

    for _ in range(10):
        delayed = _target(stale_run)
        with post_training_saliency_target(delayed):
            stale = manager.set_saliency_params(_BASELINE_PARAMS)

        assert isinstance(stale, PostTrainingSaliencyScheduleOutcome)
        assert stale.disposition is PostTrainingSaliencyScheduleDisposition.STALE
        assert stale.reason is PostTrainingSaliencyScheduleReason.TRAINING_RUN_CHANGED
        assert stale.status.run == stale_run
        assert delayed.schedule_outcome == stale
        assert manager.get_post_training_saliency_status() == current
        assert terminal_events == [current]


def test_newer_training_run_supersedes_terminal_saliency_owner() -> None:
    compute_calls: list[TrainingRunIdentity] = []
    manager, first_run = _manager_with_compute(
        lambda _plan, _should_cancel: compute_calls.append(
            cast(TrainingRunIdentity, cast(_Trainer, manager.trainer).outcome.run)
        )
    )
    trainer = cast(_Trainer, manager.trainer)

    with patch(
        "XBrainLab.backend.training.training_plan.publish_prepared_saliency_updates",
        side_effect=_publish_updates,
    ):
        with post_training_saliency_target(_target(first_run)):
            first_schedule = manager.set_saliency_params(_BASELINE_PARAMS)
        assert manager.wait_for_saliency_job(timeout=2.0)
        first_status = manager.get_post_training_saliency_status()

        second_run = TrainingRunIdentity(
            trainer_id=first_run.trainer_id,
            run_id=first_run.run_id + 1,
        )
        trainer.outcome = TrainingTerminalOutcome(
            state=TrainingOutcomeState.COMPLETED,
            run=second_run,
        )
        trainer.generation += 1
        trainer.holder.generation = trainer.generation
        trainer.holder.records.append(_FinishedRecord(eval_record=object()))
        second_target = PostTrainingSaliencyTarget(
            run=second_run,
            finished_runs_before=1,
            finished_runs_after=2,
            append=True,
        )
        with post_training_saliency_target(second_target):
            second_schedule = manager.set_saliency_params(_BASELINE_PARAMS)
        assert manager.wait_for_saliency_job(timeout=2.0)

    second_status = manager.get_post_training_saliency_status()
    assert isinstance(first_schedule, PostTrainingSaliencyScheduleOutcome)
    assert isinstance(second_schedule, PostTrainingSaliencyScheduleOutcome)
    assert second_schedule.disposition is (
        PostTrainingSaliencyScheduleDisposition.SCHEDULED
    )
    assert first_status.phase is PostTrainingSaliencyPhase.SUCCEEDED
    assert second_status.phase is PostTrainingSaliencyPhase.SUCCEEDED
    assert second_status.run == second_run
    assert second_status.generation > first_status.generation
    assert compute_calls == [first_run, second_run]


def test_explicit_same_lineage_recompute_supersedes_terminal_owner() -> None:
    compute_calls: list[tuple[str, ...]] = []

    def compute(plan, _should_cancel):
        methods = tuple(plan.holder.last_params["_methods"])
        compute_calls.append(methods)
        return object()

    manager, run = _manager_with_compute(compute)
    trainer = cast(_Trainer, manager.trainer)
    original_prepare = trainer.holder.prepare_saliency_update_plan

    def remember_params(params, *, records):
        trainer.holder.last_params = params
        return original_prepare(params, records=records)

    trainer.holder.prepare_saliency_update_plan = remember_params  # type: ignore[method-assign]
    explicit_target = PostTrainingSaliencyTarget(
        run=run,
        finished_runs_before=0,
        finished_runs_after=1,
        append=False,
        explicit=True,
    )
    accumulated_params = {
        "_methods": ["Gradient", "VarGrad"],
        "VarGrad": {
            "nt_samples": 7,
            "nt_samples_batch_size": 2,
            "stdevs": 0.25,
        },
    }

    with patch(
        "XBrainLab.backend.training.training_plan.publish_prepared_saliency_updates",
        side_effect=_publish_updates,
    ):
        with post_training_saliency_target(_target(run)):
            first_schedule = manager.set_saliency_params(_BASELINE_PARAMS)
        assert manager.wait_for_saliency_job(timeout=2.0)
        first_status = manager.get_post_training_saliency_status()

        with post_training_saliency_target(explicit_target):
            second_schedule = manager.set_saliency_params(accumulated_params)
        assert manager.wait_for_saliency_job(timeout=2.0)

    second_status = manager.get_post_training_saliency_status()
    assert isinstance(first_schedule, PostTrainingSaliencyScheduleOutcome)
    assert isinstance(second_schedule, PostTrainingSaliencyScheduleOutcome)
    assert first_status.phase is PostTrainingSaliencyPhase.SUCCEEDED
    assert second_schedule.disposition is (
        PostTrainingSaliencyScheduleDisposition.SCHEDULED
    )
    assert second_status.phase is PostTrainingSaliencyPhase.SUCCEEDED
    assert second_status.generation > first_status.generation
    assert second_status.methods == ("Gradient", "VarGrad")
    assert compute_calls == [
        ("Gradient", "Gradient * Input"),
        ("Gradient", "VarGrad"),
    ]


def test_explicit_same_lineage_failure_preserves_previous_committed_params() -> None:
    compute_count = 0

    def compute(_plan, _should_cancel):
        nonlocal compute_count
        compute_count += 1
        if compute_count == 2:
            raise RuntimeError("advanced attribution failed")
        return object()

    manager, run = _manager_with_compute(compute)
    explicit_target = PostTrainingSaliencyTarget(
        run=run,
        finished_runs_before=0,
        finished_runs_after=1,
        append=False,
        explicit=True,
    )
    accumulated_params = {
        "_methods": ["Gradient", "VarGrad"],
        "VarGrad": {
            "nt_samples": 7,
            "nt_samples_batch_size": 2,
            "stdevs": 0.25,
        },
    }

    with patch(
        "XBrainLab.backend.training.training_plan.publish_prepared_saliency_updates",
        side_effect=_publish_updates,
    ):
        with post_training_saliency_target(_target(run)):
            manager.set_saliency_params(_BASELINE_PARAMS)
        assert manager.wait_for_saliency_job(timeout=2.0)
        assert manager.saliency_params == _BASELINE_PARAMS

        with post_training_saliency_target(explicit_target):
            schedule = manager.set_saliency_params(accumulated_params)
        assert manager.wait_for_saliency_job(timeout=2.0)

    assert isinstance(schedule, PostTrainingSaliencyScheduleOutcome)
    assert schedule.disposition is PostTrainingSaliencyScheduleDisposition.SCHEDULED
    assert manager.get_post_training_saliency_status().phase is (
        PostTrainingSaliencyPhase.FAILED
    )
    assert manager.saliency_params == _BASELINE_PARAMS


def test_explicit_same_lineage_recompute_does_not_supersede_active_owner() -> None:
    compute_started = Event()
    release_compute = Event()

    def compute(_plan, _should_cancel):
        compute_started.set()
        assert release_compute.wait(timeout=2.0)
        return object()

    manager, run = _manager_with_compute(compute)
    explicit_target = PostTrainingSaliencyTarget(
        run=run,
        finished_runs_before=0,
        finished_runs_after=1,
        append=False,
        explicit=True,
    )

    with patch(
        "XBrainLab.backend.training.training_plan.publish_prepared_saliency_updates",
        side_effect=_publish_updates,
    ):
        with post_training_saliency_target(_target(run)):
            first = manager.set_saliency_params(_BASELINE_PARAMS)
        assert compute_started.wait(timeout=2.0)

        with post_training_saliency_target(explicit_target):
            blocked = manager.set_saliency_params({"_methods": ["Gradient", "VarGrad"]})

        assert isinstance(blocked, PostTrainingSaliencyScheduleOutcome)
        assert blocked.disposition is PostTrainingSaliencyScheduleDisposition.STALE
        assert blocked.reason is PostTrainingSaliencyScheduleReason.REQUEST_SUPERSEDED
        assert manager.get_post_training_saliency_status().phase is (
            PostTrainingSaliencyPhase.RUNNING
        )
        release_compute.set()
        assert manager.wait_for_saliency_job(timeout=2.0)

    assert isinstance(first, PostTrainingSaliencyScheduleOutcome)
    assert manager.get_post_training_saliency_status().phase is (
        PostTrainingSaliencyPhase.SUCCEEDED
    )


def test_non_explicit_same_lineage_request_remains_blocked_after_terminal() -> None:
    manager, run = _manager_with_compute(lambda _plan, _should_cancel: object())
    duplicate_target = PostTrainingSaliencyTarget(
        run=run,
        finished_runs_before=0,
        finished_runs_after=1,
        append=False,
        explicit=False,
    )

    with patch(
        "XBrainLab.backend.training.training_plan.publish_prepared_saliency_updates",
        side_effect=_publish_updates,
    ):
        with post_training_saliency_target(_target(run)):
            manager.set_saliency_params(_BASELINE_PARAMS)
        assert manager.wait_for_saliency_job(timeout=2.0)

        with post_training_saliency_target(duplicate_target):
            blocked = manager.set_saliency_params(_BASELINE_PARAMS)

    assert isinstance(blocked, PostTrainingSaliencyScheduleOutcome)
    assert blocked.disposition is PostTrainingSaliencyScheduleDisposition.STALE
    assert blocked.reason is PostTrainingSaliencyScheduleReason.REQUEST_SUPERSEDED


def test_terminal_delivery_remains_monotonic_when_older_notify_is_delayed() -> None:
    """A checked old terminal event cannot overtake a newer run publication."""
    for iteration in range(10):
        manager, first_run = _manager_with_compute(
            lambda _plan, _should_cancel: object()
        )
        trainer = cast(_Trainer, manager.trainer)
        old_notify_entered = Event()
        release_old_notify = Event()
        old_notify_completed = Event()
        second_delivered = Event()
        terminal_events: list[PostTrainingSaliencyStatus] = []

        def observe_terminal(
            status: PostTrainingSaliencyStatus,
            *,
            events=terminal_events,
            old_run=first_run,
            delivered=second_delivered,
        ) -> None:
            events.append(status)
            if status.run != old_run:
                delivered.set()

        manager.subscribe_post_training_saliency_terminal(observe_terminal)
        original_notify = manager._saliency_lifecycle_events.notify

        def notify_after_barrier(
            event_name,
            status,
            *,
            old_run=first_run,
            entered=old_notify_entered,
            release=release_old_notify,
            notify=original_notify,
            completed=old_notify_completed,
        ) -> None:
            if status.run == old_run:
                entered.set()
                assert release.wait(timeout=2.0)
            notify(event_name, status)
            if status.run == old_run:
                completed.set()

        with (
            patch(
                "XBrainLab.backend.training.training_plan."
                "publish_prepared_saliency_updates",
                side_effect=_publish_updates,
            ),
            patch.object(
                manager._saliency_lifecycle_events,
                "notify",
                side_effect=notify_after_barrier,
            ),
        ):
            with post_training_saliency_target(_target(first_run)):
                first_schedule = manager.set_saliency_params(_BASELINE_PARAMS)
            assert isinstance(first_schedule, PostTrainingSaliencyScheduleOutcome)
            assert old_notify_entered.wait(timeout=2.0), iteration

            second_run = TrainingRunIdentity(
                trainer_id=first_run.trainer_id,
                run_id=first_run.run_id + 1,
            )
            trainer.outcome = TrainingTerminalOutcome(
                state=TrainingOutcomeState.COMPLETED,
                run=second_run,
            )
            trainer.generation += 1
            trainer.holder.generation = trainer.generation
            trainer.holder.records.append(_FinishedRecord(eval_record=object()))
            second_target = PostTrainingSaliencyTarget(
                run=second_run,
                finished_runs_before=1,
                finished_runs_after=2,
                append=True,
            )
            with post_training_saliency_target(second_target):
                second_schedule = manager.set_saliency_params(_BASELINE_PARAMS)
            assert isinstance(second_schedule, PostTrainingSaliencyScheduleOutcome)
            assert manager.wait_for_saliency_job(timeout=2.0), iteration

            current_before_release = manager.get_post_training_saliency_status()
            assert current_before_release.phase is PostTrainingSaliencyPhase.SUCCEEDED
            assert current_before_release.run == second_run
            release_old_notify.set()
            assert old_notify_completed.wait(timeout=2.0), iteration
            assert second_delivered.wait(timeout=2.0), iteration

        current_after_release = manager.get_post_training_saliency_status()
        assert current_after_release == current_before_release
        assert [status.generation for status in terminal_events] == sorted(
            status.generation for status in terminal_events
        )
        assert terminal_events[-1] == current_after_release


def test_terminal_delivery_is_idempotent_for_reentrant_subscriber() -> None:
    manager, run = _manager_with_compute(lambda _plan, _should_cancel: object())
    terminal_events: list[PostTrainingSaliencyStatus] = []

    def observe_terminal(status: PostTrainingSaliencyStatus) -> None:
        terminal_events.append(status)
        if len(terminal_events) == 1:
            manager._notify_post_training_saliency_terminal(status)

    manager.subscribe_post_training_saliency_terminal(observe_terminal)
    with patch(
        "XBrainLab.backend.training.training_plan.publish_prepared_saliency_updates",
        side_effect=_publish_updates,
    ):
        with post_training_saliency_target(_target(run)):
            schedule = manager.set_saliency_params(_BASELINE_PARAMS)
        assert isinstance(schedule, PostTrainingSaliencyScheduleOutcome)
        assert manager.wait_for_saliency_job(timeout=2.0)

    current = manager.get_post_training_saliency_status()
    assert current.phase is PostTrainingSaliencyPhase.SUCCEEDED
    assert terminal_events == [current]


def test_terminal_observer_failure_retains_ledger_until_scheduled_retry() -> None:
    manager, run = _manager_with_compute(lambda _plan, _should_cancel: object())
    status = PostTrainingSaliencyStatus.pending(
        generation=1,
        run=run,
        training_generation=7,
        methods=("Gradient",),
    ).transition(
        generation=1,
        phase=PostTrainingSaliencyPhase.FAILED,
        error_code="fault_injection",
        message="Injected terminal failure.",
        diagnostic_type=RuntimeError.__name__,
    )
    with manager._saliency_job_lock:
        manager._saliency_job_sequence = status.generation
        manager._post_training_saliency_status = status

    attempts: list[PostTrainingSaliencyStatus] = []
    callback_lock_states: list[bool] = []

    def fail_first_delivery(delivered: PostTrainingSaliencyStatus) -> None:
        acquired = manager._saliency_terminal_delivery_lock.acquire(blocking=False)
        callback_lock_states.append(acquired)
        if acquired:
            manager._saliency_terminal_delivery_lock.release()
        attempts.append(delivered)
        if len(attempts) == 1:
            raise RuntimeError("transient observer handoff failure")

    manager.subscribe_post_training_saliency_terminal(fail_first_delivery)
    with patch(
        "XBrainLab.backend.training_manager."
        "_POST_TRAINING_SALIENCY_TERMINAL_RETRY_SECONDS",
        60.0,
    ):
        manager._notify_post_training_saliency_terminal(status)

    with manager._saliency_terminal_delivery_lock:
        retry_timer = manager._saliency_terminal_retry_timer
        assert manager._saliency_terminal_delivered_generation == 0
        assert manager._saliency_terminal_pending == {status.generation: status}
    assert retry_timer is not None
    retry_timer.cancel()
    with manager._saliency_terminal_delivery_lock:
        manager._saliency_terminal_retry_timer = None

    manager.retry_post_training_saliency_terminal_delivery()

    assert attempts == [status, status]
    assert callback_lock_states == [True, True]
    assert manager._saliency_terminal_delivered_generation == status.generation
    assert manager._saliency_terminal_pending == {}
    assert manager.wait_for_saliency_terminal_delivery(timeout=0.1)


def test_terminal_retry_survives_timer_start_failure_without_external_trigger() -> None:
    manager, run = _manager_with_compute(lambda _plan, _should_cancel: object())
    status = PostTrainingSaliencyStatus.pending(
        generation=1,
        run=run,
        training_generation=7,
        methods=("Gradient",),
    ).transition(
        generation=1,
        phase=PostTrainingSaliencyPhase.FAILED,
        error_code="fault_injection",
        message="Injected terminal failure.",
        diagnostic_type=RuntimeError.__name__,
    )
    with manager._saliency_job_lock:
        manager._saliency_job_sequence = status.generation
        manager._post_training_saliency_status = status

    attempts: list[PostTrainingSaliencyStatus] = []
    delivered = Event()

    def fail_once(delivery: PostTrainingSaliencyStatus) -> None:
        attempts.append(delivery)
        if len(attempts) == 1:
            raise RuntimeError("transient observer failure")
        delivered.set()

    class _TimerStartFailure:
        daemon = False

        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        def start(self) -> None:
            raise RuntimeError("timer start failed")

    manager.subscribe_post_training_saliency_terminal(fail_once)
    with patch("XBrainLab.backend.training_manager.Timer", _TimerStartFailure):
        manager._notify_post_training_saliency_terminal(status)
        assert delivered.wait(timeout=2.0)

    assert attempts == [status, status]
    assert manager.wait_for_saliency_terminal_delivery(timeout=0.1)
    with manager._saliency_terminal_delivery_lock:
        assert manager._saliency_terminal_pending == {}
        assert manager._saliency_terminal_delivered_generation == status.generation
        assert manager._saliency_terminal_retry_timer is None


def test_terminal_retry_survives_timer_constructor_failure_without_external_trigger() -> (
    None
):
    manager, run = _manager_with_compute(lambda _plan, _should_cancel: object())
    status = PostTrainingSaliencyStatus.pending(
        generation=1,
        run=run,
        training_generation=7,
        methods=("Gradient",),
    ).transition(
        generation=1,
        phase=PostTrainingSaliencyPhase.FAILED,
        error_code="fault_injection",
        message="Injected terminal failure.",
        diagnostic_type=RuntimeError.__name__,
    )
    with manager._saliency_job_lock:
        manager._saliency_job_sequence = status.generation
        manager._post_training_saliency_status = status

    attempts: list[PostTrainingSaliencyStatus] = []
    delivered = Event()

    def fail_once(delivery: PostTrainingSaliencyStatus) -> None:
        attempts.append(delivery)
        if len(attempts) == 1:
            raise RuntimeError("transient observer failure")
        delivered.set()

    class _TimerConstructorFailure:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("timer constructor failed")

    manager.subscribe_post_training_saliency_terminal(fail_once)
    with patch(
        "XBrainLab.backend.training_manager.Timer",
        _TimerConstructorFailure,
    ):
        manager._notify_post_training_saliency_terminal(status)
        assert delivered.wait(timeout=2.0)

    assert attempts == [status, status]
    assert manager.wait_for_saliency_terminal_delivery(timeout=0.1)
    state = manager.get_post_training_saliency_terminal_delivery_state()
    assert state.pending_generations == ()
    assert state.delivered_generation == status.generation
    assert state.retry_unavailable is False


@pytest.mark.parametrize("timer_failure", ["construct", "start"])
@pytest.mark.parametrize("thread_failure", ["construct", "start"])
def test_terminal_retry_owner_constructor_matrix_fails_closed(
    timer_failure: str,
    thread_failure: str,
) -> None:
    manager, run = _manager_with_compute(lambda _plan, _should_cancel: object())
    status = PostTrainingSaliencyStatus.pending(
        generation=1,
        run=run,
        training_generation=7,
        methods=("Gradient",),
    ).transition(
        generation=1,
        phase=PostTrainingSaliencyPhase.FAILED,
        error_code="fault_injection",
        message="Injected terminal failure.",
        diagnostic_type=RuntimeError.__name__,
    )
    with manager._saliency_job_lock:
        manager._saliency_job_sequence = status.generation
        manager._post_training_saliency_status = status

    attempts: list[PostTrainingSaliencyStatus] = []

    def fail_once(delivery: PostTrainingSaliencyStatus) -> None:
        attempts.append(delivery)
        if len(attempts) == 1:
            raise RuntimeError("transient observer failure")

    class _TimerFailure:
        daemon = False

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            if timer_failure == "construct":
                raise RuntimeError("timer constructor failed")

        def start(self) -> None:
            raise RuntimeError("timer start failed")

    class _ThreadFailure:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            if thread_failure == "construct":
                raise RuntimeError("thread constructor failed")

        def start(self) -> None:
            raise RuntimeError("thread start failed")

    manager.subscribe_post_training_saliency_terminal(fail_once)
    with (
        patch("XBrainLab.backend.training_manager.Timer", _TimerFailure),
        patch("XBrainLab.backend.training_manager.Thread", _ThreadFailure),
    ):
        manager._notify_post_training_saliency_terminal(status)

        state = manager.get_post_training_saliency_terminal_delivery_state()
        assert state.pending_generations == (status.generation,)
        assert state.active_generation is None
        assert state.delivered_generation == 0
        assert state.retry_owner_active is False
        assert state.retry_unavailable is True
        assert manager.wait_for_saliency_terminal_delivery(timeout=0.01) is False

    manager.retry_post_training_saliency_terminal_delivery()

    assert attempts == [status, status]
    assert manager.wait_for_saliency_terminal_delivery(timeout=0.1)
    state = manager.get_post_training_saliency_terminal_delivery_state()
    assert state.pending_generations == ()
    assert state.delivered_generation == status.generation
    assert state.retry_unavailable is False


def test_discard_terminal_delivery_releases_pending_retry_ownership() -> None:
    manager, run = _manager_with_compute(lambda _plan, _should_cancel: object())
    status = PostTrainingSaliencyStatus.pending(
        generation=1,
        run=run,
        training_generation=7,
        methods=("Gradient",),
    ).transition(
        generation=1,
        phase=PostTrainingSaliencyPhase.FAILED,
        error_code="fault_injection",
        message="Injected terminal failure.",
        diagnostic_type=RuntimeError.__name__,
    )
    with manager._saliency_job_lock:
        manager._saliency_job_sequence = status.generation
        manager._post_training_saliency_status = status

    def reject_delivery(_status: PostTrainingSaliencyStatus) -> None:
        raise RuntimeError("terminal observer is unavailable")

    manager.subscribe_post_training_saliency_terminal(reject_delivery)
    manager._notify_post_training_saliency_terminal(status)

    pending = manager.get_post_training_saliency_terminal_delivery_state()
    assert pending.pending_generations == (status.generation,)
    assert pending.retry_owner_active is True

    manager.discard_post_training_saliency_terminal_delivery()

    discarded = manager.get_post_training_saliency_terminal_delivery_state()
    assert discarded.pending_generations == ()
    assert discarded.active_generation is None
    assert discarded.retry_owner_active is False
    assert discarded.retry_unavailable is False
    assert manager.wait_for_saliency_terminal_delivery(timeout=0.1)


def test_reset_during_post_training_saliency_cancels_before_retiring_status() -> None:
    compute_started = Event()
    cancel_ready = Event()
    cancel_events: list[Event] = []
    published = Event()

    def compute(_plan, should_cancel):
        compute_started.set()
        assert cancel_ready.wait(timeout=2.0)
        assert cancel_events[0].wait(timeout=2.0)
        assert should_cancel()
        return object()

    def publish(*_args, **_kwargs) -> None:
        published.set()

    manager, run = _manager_with_compute(compute)
    with patch(
        "XBrainLab.backend.training.training_plan.publish_prepared_saliency_updates",
        side_effect=publish,
    ):
        with post_training_saliency_target(_target(run)):
            manager.set_saliency_params(_BASELINE_PARAMS)
        assert compute_started.wait(timeout=2.0)

        cancel = manager._saliency_job_cancel
        assert cancel is not None
        cancel_events.append(cancel)
        cancel_ready.set()
        cleaner = WorkerThread(target=manager.clean_trainer, daemon=True)
        cleaner.start()
        assert cancel.wait(timeout=2.0)
        cleaner.join(timeout=2.0)
        assert not cleaner.is_alive()

    status = manager.get_post_training_saliency_status()
    assert status.phase is PostTrainingSaliencyPhase.IDLE
    assert status.run is None
    assert manager.trainer is None
    assert manager.wait_for_saliency_job(timeout=0.1)
    assert not published.is_set()
    assert manager.saliency_params is None


def test_cancel_during_plan_preparation_invalidates_request_and_waits_for_cleanup() -> (
    None
):
    prepare_started = Event()
    release_prepare = Event()
    compute_started = Event()
    schedule_outcomes: list[PostTrainingSaliencyScheduleOutcome | None] = []
    manager, run = _manager_with_compute(
        lambda _plan, _should_cancel: compute_started.set(),
    )
    trainer = cast(_Trainer, manager.trainer)
    original_prepare = trainer.holder.prepare_saliency_update_plan

    def prepare_after_barrier(_params, *, records):
        prepare_started.set()
        assert release_prepare.wait(timeout=2.0)
        return original_prepare(_params, records=records)

    trainer.holder.prepare_saliency_update_plan = prepare_after_barrier

    def schedule() -> None:
        with post_training_saliency_target(_target(run)):
            schedule_outcomes.append(manager.set_saliency_params(_BASELINE_PARAMS))

    scheduler = WorkerThread(target=schedule, daemon=True)
    scheduler.start()
    assert prepare_started.wait(timeout=1.0)

    manager.cancel_saliency_job()

    assert manager.wait_for_saliency_job(timeout=0.05) is False
    release_prepare.set()
    scheduler.join(timeout=2.0)

    assert not scheduler.is_alive()
    assert manager.wait_for_saliency_job(timeout=1.0)
    assert len(schedule_outcomes) == 1
    outcome = schedule_outcomes[0]
    assert isinstance(outcome, PostTrainingSaliencyScheduleOutcome)
    assert outcome.disposition is PostTrainingSaliencyScheduleDisposition.STALE
    assert outcome.reason is PostTrainingSaliencyScheduleReason.REQUEST_SUPERSEDED
    assert not compute_started.is_set()


def test_successful_request_handoff_keeps_wait_pending_until_worker_cleanup() -> None:
    compute_started = Event()
    release_compute = Event()
    handoff_complete = Event()
    release_scheduler = Event()
    schedule_outcomes: list[PostTrainingSaliencyScheduleOutcome | None] = []

    def compute(_plan, _should_cancel):
        compute_started.set()
        assert release_compute.wait(timeout=2.0)
        return object()

    manager, run = _manager_with_compute(compute)
    target = _target(run)
    original_start = manager._prepare_and_start_post_training_saliency

    def pause_after_worker_handoff(**kwargs):
        outcome = original_start(**kwargs)
        handoff_complete.set()
        assert release_scheduler.wait(timeout=2.0)
        return outcome

    manager._prepare_and_start_post_training_saliency = pause_after_worker_handoff  # type: ignore[method-assign]

    def schedule() -> None:
        with post_training_saliency_target(target):
            schedule_outcomes.append(manager.set_saliency_params(_BASELINE_PARAMS))

    scheduler = WorkerThread(target=schedule, daemon=True)
    with patch(
        "XBrainLab.backend.training.training_plan.publish_prepared_saliency_updates",
        side_effect=_publish_updates,
    ):
        scheduler.start()
        assert handoff_complete.wait(timeout=1.0)

        assert manager.wait_for_saliency_job(timeout=0.05) is False
        release_scheduler.set()
        scheduler.join(timeout=1.0)
        assert not scheduler.is_alive()
        assert target._command_completed.is_set()
        assert compute_started.wait(timeout=1.0)
        assert manager.wait_for_saliency_job(timeout=0.05) is False

        release_compute.set()
        assert manager.wait_for_saliency_job(timeout=1.0)
    assert len(schedule_outcomes) == 1
    outcome = schedule_outcomes[0]
    assert isinstance(outcome, PostTrainingSaliencyScheduleOutcome)
    assert outcome.disposition is PostTrainingSaliencyScheduleDisposition.SCHEDULED


def test_stale_terminal_transition_cannot_overwrite_new_generation() -> None:
    run = TrainingRunIdentity(trainer_id="saliency-lifecycle", run_id=2)
    old = PostTrainingSaliencyStatus.pending(
        generation=1,
        run=run,
        training_generation=10,
        methods=("Gradient", "Gradient * Input"),
    )
    current = PostTrainingSaliencyStatus.pending(
        generation=2,
        run=run,
        training_generation=11,
        methods=("Gradient", "Gradient * Input"),
    )

    stale_result = current.transition(
        generation=old.generation,
        phase=PostTrainingSaliencyPhase.SUCCEEDED,
    )

    assert stale_result is current
    assert stale_result.phase is PostTrainingSaliencyPhase.PENDING


def test_invalid_lifecycle_transition_fails_closed() -> None:
    run = TrainingRunIdentity(trainer_id="saliency-lifecycle", run_id=3)
    pending = PostTrainingSaliencyStatus.pending(
        generation=1,
        run=run,
        training_generation=10,
        methods=("Gradient", "Gradient * Input"),
    )

    with pytest.raises(ValueError, match="invalid post-training saliency transition"):
        pending.transition(
            generation=1,
            phase=PostTrainingSaliencyPhase.SUCCEEDED,
        )
