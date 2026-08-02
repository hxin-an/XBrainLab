"""Integration coverage for asynchronous saliency view publication."""

from __future__ import annotations

from threading import Event, Thread
from time import monotonic
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest
import torch

from XBrainLab.backend.application import (
    ApplicationService,
    QueryStateCommand,
    ResetSessionCommand,
    SaliencyCommand,
    SaliencyPlanIdentity,
    SaliencyRenderRequest,
    SaliencyRunIdentity,
)
from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import (
    ModelHolder,
    Trainer,
    TrainingEvaluation,
    TrainingOption,
    TrainingPlanHolder,
)
from XBrainLab.backend.training.record.eval import EvalRecord
from XBrainLab.backend.training.record.train import TrainRecord
from XBrainLab.backend.training.training_plan import PreparedSaliencyUpdate
from XBrainLab.backend.training_manager import (
    PostTrainingSaliencyTarget,
    post_training_saliency_target,
)
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    PostTrainingSaliencyScheduleDisposition,
    PostTrainingSaliencyScheduleReason,
    PostTrainingSaliencyStatus,
    TrainingLifecycleEvent,
    TrainingOutcomeState,
    TrainingRunIdentity,
)
from XBrainLab.ui.application_capabilities import (
    release_application_shutdown_fence,
)

_THREAD_WATCHDOG_SECONDS = 3.0
_BASELINE_METHODS = ("Gradient", "Gradient * Input")


class _TrainerAliasRaisesStudy(Study):
    @property
    def trainer(self) -> Any:
        raise AssertionError("Study.trainer alias must not be read")


class _SaliencyEpochData:
    """Small deterministic epoch contract used by publication lifecycle tests."""

    def __init__(self) -> None:
        self.label_map = {0: "left"}
        self.event_id = {"left": 0}
        self.data = np.zeros((1, 2, 8), dtype=np.float32)
        self.tmin = 0.0
        self.sfreq = 128.0

    def get_model_args(self) -> dict[str, int | float]:
        return {
            "n_classes": 1,
            "channels": 2,
            "samples": 8,
            "sfreq": self.sfreq,
        }

    def get_channel_names(self) -> list[str]:
        return ["C3", "C4"]

    def get_montage_position(self) -> list[tuple[float, float, float]]:
        return [(-0.04, 0.0, 0.08), (0.04, 0.0, 0.08)]


def _training_option() -> TrainingOption:
    return TrainingOption(
        output_dir="./test-output",
        optim=torch.optim.Adam,
        optim_params={},
        use_cpu=True,
        gpu_idx=None,
        epoch=1,
        bs=1,
        lr=0.001,
        checkpoint_epoch=0,
        evaluation_option=TrainingEvaluation.LAST_EPOCH,
        repeat_num=1,
    )


def _eval_record(*, with_saliency: bool) -> EvalRecord:
    saliency = {0: np.ones((1, 2, 8), dtype=np.float32)} if with_saliency else {}
    return EvalRecord(
        label=np.array([0], dtype=int),
        output=np.array([[1.0]], dtype=np.float32),
        gradient=saliency,
        gradient_input=dict(saliency),
        smoothgrad={},
        smoothgrad_sq={},
        vargrad={},
        evaluation_split="test",
    )


def _bound_saliency_eval_record(
    holder: TrainingPlanHolder,
    record: TrainRecord,
) -> EvalRecord:
    eval_record = _eval_record(with_saliency=True)
    eval_record.bind_saliency_context(
        holder.dataset.get_epoch_data(),
        producer_identity=holder.build_saliency_producer_identity(
            record,
            evaluation_split=eval_record.evaluation_split,
        ),
    )
    return eval_record


def _completed_training_service(
    *,
    study: Study | None = None,
) -> tuple[
    ApplicationService,
    Trainer,
    TrainingPlanHolder,
    TrainRecord,
    EvalRecord,
]:
    target_study = study if study is not None else Study()
    option = _training_option()
    model_holder = ModelHolder(type("EEGNet", (), {}), {})
    initial_eval_record = _eval_record(with_saliency=False)
    epoch_data = _SaliencyEpochData()
    dataset = SimpleNamespace(
        get_name=lambda: "saliency-publication",
        get_epoch_data=lambda: epoch_data,
        train_mask=np.array([False]),
        val_mask=np.array([False]),
        test_mask=np.array([True]),
    )

    record = object.__new__(TrainRecord)
    record._state_tracker = None
    record.epoch = option.epoch
    record.option = cast(Any, option)
    record.eval_record = initial_eval_record
    record.model = torch.nn.Linear(1, 1, bias=False)
    record.repeat = 0
    record.seed = 7
    record.plan_id = "saliency-publication"

    holder = object.__new__(TrainingPlanHolder)
    holder.model_holder = cast(Any, model_holder)
    holder.dataset = cast(Any, dataset)
    holder.option = cast(Any, option)
    holder.plan_id = "saliency-publication"
    holder.saliency_params = {}
    holder.train_record_list = [record]
    holder._state_tracker = None
    holder._interrupt = Event()
    holder.error = None
    holder.status = "Done"

    trainer = Trainer([holder])
    trainer.current_idx = 1
    trainer.run(interact=False)
    outcome = trainer.get_terminal_outcome()
    assert outcome.state is TrainingOutcomeState.COMPLETED
    assert outcome.run is not None

    target_study.training_manager.set_model_holder(model_holder)
    target_study.training_manager.set_training_option(option)
    target_study.training_manager.trainer = trainer
    return (
        ApplicationService(target_study),
        trainer,
        holder,
        record,
        initial_eval_record,
    )


def _method_coverage(publication, method: str):
    runs = publication.state.visualization.saliency_coverage
    assert len(runs) == 1
    return next(item for item in runs[0].methods if item.method == method)


def _publish_renderable_saliency(
    service: ApplicationService,
    holder: TrainingPlanHolder,
    record: TrainRecord,
) -> tuple[EvalRecord, Any]:
    eval_record = _bound_saliency_eval_record(holder, record)
    record.set_eval_record(eval_record)
    service.get_state()
    publication = service.get_view_publication()
    assert publication.state.visualization.saliency_available is True
    return eval_record, publication


def _render_request(publication) -> SaliencyRenderRequest:
    return SaliencyRenderRequest(
        publication_generation=publication.generation,
        run=SaliencyRunIdentity(
            plan=SaliencyPlanIdentity(plan_index=0),
            run_index=0,
        ),
        method="Gradient",
    )


def _schedule_baseline(service: ApplicationService, trainer: Trainer):
    outcome = trainer.get_terminal_outcome()
    assert outcome.run is not None
    target = PostTrainingSaliencyTarget(
        run=outcome.run,
        finished_runs_before=0,
        finished_runs_after=1,
        append=True,
    )
    with post_training_saliency_target(target):
        scheduled = service.execute(
            SaliencyCommand(
                method="Gradient",
                params={
                    "profile": "recommended",
                    "methods": list(_BASELINE_METHODS),
                },
            )
        )
        pending = service.get_view_publication()
        assert scheduled.ok is True, scheduled.message
        assert pending.state.visualization.post_training_saliency.phase is (
            PostTrainingSaliencyPhase.PENDING
        )
    return pending


def _wait_for_manager_phase(service: ApplicationService, phase) -> bool:
    deadline = monotonic() + _THREAD_WATCHDOG_SECONDS
    manager = service.study.training_manager
    while monotonic() < deadline:
        if manager.get_post_training_saliency_status().phase is phase:
            return True
        Event().wait(0.01)
    return False


def _lock_available_from_another_thread(lock) -> bool:
    acquired: list[bool] = []
    completed = Event()

    def probe() -> None:
        owns_lock = lock.acquire(blocking=False)
        acquired.append(owns_lock)
        if owns_lock:
            lock.release()
        completed.set()

    thread = Thread(target=probe, daemon=True)
    thread.start()
    assert completed.wait(timeout=_THREAD_WATCHDOG_SECONDS)
    thread.join(timeout=_THREAD_WATCHDOG_SECONDS)
    assert not thread.is_alive()
    return acquired == [True]


def test_saliency_worker_terminal_state_republishes_query_and_coverage(
    monkeypatch,
) -> None:
    service, trainer, holder, record, initial_eval_record = (
        _completed_training_service()
    )
    compute_started = Event()
    release_compute = Event()
    terminal_eval_record = _bound_saliency_eval_record(holder, record)

    def bounded_compute(plan, *, should_cancel):
        compute_started.set()
        assert release_compute.wait(timeout=_THREAD_WATCHDOG_SECONDS)
        assert should_cancel() is False
        return PreparedSaliencyUpdate(
            plan=plan,
            eval_records=((record, initial_eval_record, terminal_eval_record),),
        )

    monkeypatch.setattr(holder, "compute_saliency_update", bounded_compute)
    pending = _schedule_baseline(service, trainer)
    terminal_events: list[TrainingLifecycleEvent] = []
    service.training.subscribe(
        "training_analysis_published",
        terminal_events.append,
    )
    pending_status_generation = (
        pending.state.visualization.post_training_saliency.generation
    )
    assert _method_coverage(pending, "Gradient").complete is False

    assert compute_started.wait(timeout=_THREAD_WATCHDOG_SECONDS)
    release_compute.set()
    assert service.study.training_manager.wait_for_saliency_job(
        timeout=_THREAD_WATCHDOG_SECONDS
    )
    assert (
        service.study.training_manager.get_post_training_saliency_status().phase
        is PostTrainingSaliencyPhase.SUCCEEDED
    )

    query = service.execute(QueryStateCommand())
    terminal = service.get_view_publication()

    assert query.ok is True
    assert query.state == terminal.state
    assert query.diagnostics["publication_generation"] == terminal.generation
    assert terminal.generation > pending.generation
    assert terminal.state.visualization.post_training_saliency.phase is (
        PostTrainingSaliencyPhase.SUCCEEDED
    )
    assert (
        terminal.state.visualization.post_training_saliency.generation
        == pending_status_generation
    )
    assert _method_coverage(terminal, "Gradient").complete is True
    assert _method_coverage(terminal, "Gradient * Input").complete is True
    assert len(terminal_events) == 1
    assert terminal_events[0].publication_generation == terminal.generation


def test_scheduler_thread_start_failure_publishes_failed_view_and_events_once(
    monkeypatch,
) -> None:
    service, trainer, _holder, _record, _initial_eval_record = (
        _completed_training_service()
    )
    outcome = trainer.get_terminal_outcome()
    assert outcome.run is not None
    target = PostTrainingSaliencyTarget(
        run=outcome.run,
        finished_runs_before=0,
        finished_runs_after=1,
        append=True,
    )
    application_events: list[TrainingLifecycleEvent] = []
    saliency_events: list[str] = []

    class _ThreadStartFailure:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        def start(self) -> None:
            raise RuntimeError("thread start failed")

    service.training.subscribe(
        "training_analysis_published",
        application_events.append,
    )
    service.visualization.subscribe(
        "saliency_changed",
        lambda: saliency_events.append("saliency_changed"),
    )
    monkeypatch.setattr(
        "XBrainLab.backend.training_manager.Thread",
        _ThreadStartFailure,
    )

    with post_training_saliency_target(target):
        result = service.execute(
            SaliencyCommand(
                method="Gradient",
                params={
                    "profile": "recommended",
                    "methods": list(_BASELINE_METHODS),
                },
            )
        )

    publication = service.get_view_publication()
    status = publication.state.visualization.post_training_saliency

    assert result.failed is True
    assert status.phase is PostTrainingSaliencyPhase.FAILED
    assert status.error_code == PostTrainingSaliencyScheduleReason.THREAD_START_FAILED
    assert len(application_events) == 1
    assert application_events[0].publication_generation == publication.generation
    assert saliency_events == ["saliency_changed"]

    assert service.execute(QueryStateCommand()).state == publication.state
    assert len(application_events) == 1
    assert saliency_events == ["saliency_changed"]


@pytest.mark.parametrize("failure_point", ["construct", "start"])
def test_submission_thread_failure_publishes_failed_view_and_events_once(
    monkeypatch,
    failure_point: str,
) -> None:
    service, trainer, _holder, _record, _initial_eval_record = (
        _completed_training_service()
    )
    application_events: list[TrainingLifecycleEvent] = []
    saliency_events: list[str] = []

    class _SubmissionFailureThread:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs
            if failure_point == "construct":
                raise RuntimeError("thread construction failed")

        def start(self) -> None:
            if failure_point == "start":
                raise RuntimeError("thread start failed")

        def join(self, timeout=None) -> None:
            del timeout
            raise AssertionError("an unstarted submission must not be joined")

    service.training.subscribe(
        "training_analysis_published",
        application_events.append,
    )
    service.visualization.subscribe(
        "saliency_changed",
        lambda: saliency_events.append("saliency_changed"),
    )
    service.post_training_saliency.arm(append=False)
    trainer.run(interact=False)
    monkeypatch.setattr(
        "XBrainLab.backend.application.post_training_saliency.Thread",
        _SubmissionFailureThread,
    )

    service.training.notify("training_stopped")
    service.training.notify("training_stopped")

    assert service.wait_for_background_tasks(timeout=_THREAD_WATCHDOG_SECONDS)
    publication = service.get_view_publication()
    status = publication.state.visualization.post_training_saliency
    assert status.phase is PostTrainingSaliencyPhase.FAILED
    assert status.error_code == (
        PostTrainingSaliencyScheduleReason.THREAD_START_FAILED.value
    )
    assert status.run == trainer.get_terminal_outcome().run
    assert len(application_events) == 1
    assert application_events[0].publication_generation == publication.generation
    assert saliency_events == ["saliency_changed"]

    assert service.execute(QueryStateCommand()).state == publication.state
    assert len(application_events) == 1
    assert saliency_events == ["saliency_changed"]


def test_worker_terminal_notification_survives_get_state_prepublish_race(
    monkeypatch,
) -> None:
    def run_iteration(iteration: int) -> None:
        service, trainer, holder, record, initial_eval_record = (
            _completed_training_service()
        )
        compute_started = Event()
        release_compute = Event()
        manager_notify_entered = Event()
        release_manager_notify = Event()
        manager_notify_completed = Event()
        terminal_eval_record = _bound_saliency_eval_record(holder, record)

        def bounded_compute(plan, *, should_cancel):
            compute_started.set()
            assert release_compute.wait(timeout=_THREAD_WATCHDOG_SECONDS)
            assert should_cancel() is False
            return PreparedSaliencyUpdate(
                plan=plan,
                eval_records=((record, initial_eval_record, terminal_eval_record),),
            )

        monkeypatch.setattr(holder, "compute_saliency_update", bounded_compute)
        pending = _schedule_baseline(service, trainer)
        manager = service.study.training_manager
        original_notify = manager._saliency_lifecycle_events.notify

        def notify_after_barrier(event_name, status) -> None:
            if status.phase is PostTrainingSaliencyPhase.SUCCEEDED:
                manager_notify_entered.set()
                assert release_manager_notify.wait(timeout=_THREAD_WATCHDOG_SECONDS)
            original_notify(event_name, status)
            if status.phase is PostTrainingSaliencyPhase.SUCCEEDED:
                manager_notify_completed.set()

        monkeypatch.setattr(
            manager._saliency_lifecycle_events,
            "notify",
            notify_after_barrier,
        )
        application_events: list[TrainingLifecycleEvent] = []
        saliency_publications = []
        service.training.subscribe(
            "training_analysis_published",
            application_events.append,
        )
        service.visualization.subscribe(
            "saliency_changed",
            lambda: saliency_publications.append(service.get_view_publication()),
        )

        assert compute_started.wait(timeout=_THREAD_WATCHDOG_SECONDS), iteration
        release_compute.set()
        assert manager_notify_entered.wait(timeout=_THREAD_WATCHDOG_SECONDS), iteration

        try:
            terminal_state = service.get_state()
            prepublished = service.get_view_publication()
            manager_status = manager.get_post_training_saliency_status()
            assert manager_status.phase is PostTrainingSaliencyPhase.SUCCEEDED
            assert terminal_state.visualization.post_training_saliency == manager_status
            assert prepublished.state == terminal_state
            assert prepublished.generation > pending.generation
            assert application_events == []
            assert saliency_publications == []
        finally:
            release_manager_notify.set()

        assert manager_notify_completed.wait(timeout=_THREAD_WATCHDOG_SECONDS), (
            iteration
        )
        assert manager.wait_for_saliency_job(timeout=_THREAD_WATCHDOG_SECONDS), (
            iteration
        )
        final_publication = service.get_view_publication()

        assert final_publication == prepublished
        assert final_publication.state.visualization.post_training_saliency == (
            manager_status
        )
        assert len(application_events) == 1
        assert application_events[0].publication_generation == (
            final_publication.generation
        )
        assert len(saliency_publications) == 1
        assert saliency_publications[0] == final_publication

    for iteration in range(10):
        run_iteration(iteration)


def test_terminal_refresh_failure_retries_delivery_from_public_state_reads(
    monkeypatch,
) -> None:
    def run_iteration(iteration: int) -> None:
        service, trainer, holder, record, initial_eval_record = (
            _completed_training_service()
        )
        compute_started = Event()
        release_compute = Event()
        terminal_refresh_failed = Event()
        terminal_eval_record = _bound_saliency_eval_record(holder, record)

        def bounded_compute(plan, *, should_cancel):
            compute_started.set()
            assert release_compute.wait(timeout=_THREAD_WATCHDOG_SECONDS)
            assert should_cancel() is False
            return PreparedSaliencyUpdate(
                plan=plan,
                eval_records=((record, initial_eval_record, terminal_eval_record),),
            )

        monkeypatch.setattr(holder, "compute_saliency_update", bounded_compute)
        pending = _schedule_baseline(service, trainer)
        manager = service.study.training_manager
        original_build = service.state_snapshot.build

        def fail_first_terminal_refresh(*, last_error=None):
            status = manager.get_post_training_saliency_status()
            if status.phase.terminal and not terminal_refresh_failed.is_set():
                terminal_refresh_failed.set()
                raise RuntimeError("transient terminal snapshot failure")
            return original_build(last_error=last_error)

        monkeypatch.setattr(
            service.state_snapshot, "build", fail_first_terminal_refresh
        )
        application_events: list[TrainingLifecycleEvent] = []
        saliency_publications = []
        delivery_lock_states: list[tuple[bool, bool, bool]] = []

        def observe_delivery_locks() -> None:
            delivery_lock_states.append(
                (
                    _lock_available_from_another_thread(manager._saliency_job_lock),
                    _lock_available_from_another_thread(
                        service._command_admission_lock
                    ),
                    _lock_available_from_another_thread(service._command_lock),
                )
            )

        def observe_application(event: TrainingLifecycleEvent) -> None:
            observe_delivery_locks()
            application_events.append(event)

        def observe_saliency() -> None:
            observe_delivery_locks()
            saliency_publications.append(service.get_view_publication())

        service.training.subscribe(
            "training_analysis_published",
            observe_application,
        )
        service.visualization.subscribe(
            "saliency_changed",
            observe_saliency,
        )

        assert compute_started.wait(timeout=_THREAD_WATCHDOG_SECONDS), iteration
        release_compute.set()
        assert manager.wait_for_saliency_job(timeout=_THREAD_WATCHDOG_SECONDS), (
            iteration
        )
        assert terminal_refresh_failed.is_set(), iteration
        terminal_status = manager.get_post_training_saliency_status()

        assert terminal_status.phase is PostTrainingSaliencyPhase.SUCCEEDED
        assert application_events == []
        assert saliency_publications == []

        if iteration % 2 == 0:
            recovered_state = service.get_state()
            query = service.execute(QueryStateCommand())
        else:
            query = service.execute(QueryStateCommand())
            recovered_state = query.state
        recovered = service.get_view_publication()

        assert query.ok is True, (iteration, query.message)
        assert query.state == recovered_state == recovered.state
        assert query.diagnostics["publication_generation"] == recovered.generation
        assert recovered.usable is True
        assert recovered.generation > pending.generation
        assert recovered.state.visualization.post_training_saliency == terminal_status
        assert _method_coverage(recovered, "Gradient").complete is True
        assert _method_coverage(recovered, "Gradient * Input").complete is True
        assert len(application_events) == 1
        assert application_events[0].publication_generation == recovered.generation
        assert len(saliency_publications) == 1
        assert saliency_publications[0] == recovered
        assert delivery_lock_states == [(True, True, True), (True, True, True)]

        repeated_query = service.execute(QueryStateCommand())
        assert repeated_query.ok is True
        assert repeated_query.state == recovered.state
        assert service.get_view_publication() == recovered
        assert manager.get_post_training_saliency_status() == terminal_status
        assert len(application_events) == 1
        assert len(saliency_publications) == 1

    for iteration in range(10):
        run_iteration(iteration)


def test_terminal_queue_handoff_failure_retries_once_after_shutdown_fence(
    monkeypatch,
) -> None:
    service, trainer, holder, record, initial_eval_record = (
        _completed_training_service()
    )
    compute_started = Event()
    release_compute = Event()
    terminal_refresh_failed = Event()
    handoff_failed = Event()
    terminal_eval_record = _bound_saliency_eval_record(holder, record)

    def bounded_compute(plan, *, should_cancel):
        compute_started.set()
        assert release_compute.wait(timeout=_THREAD_WATCHDOG_SECONDS)
        assert should_cancel() is False
        return PreparedSaliencyUpdate(
            plan=plan,
            eval_records=((record, initial_eval_record, terminal_eval_record),),
        )

    monkeypatch.setattr(holder, "compute_saliency_update", bounded_compute)
    pending = _schedule_baseline(service, trainer)
    manager = service.study.training_manager
    original_build = service.state_snapshot.build

    def fail_first_terminal_refresh(*, last_error=None):
        status = manager.get_post_training_saliency_status()
        if status.phase.terminal and not terminal_refresh_failed.is_set():
            terminal_refresh_failed.set()
            raise RuntimeError("transient terminal snapshot failure")
        return original_build(last_error=last_error)

    monkeypatch.setattr(service.state_snapshot, "build", fail_first_terminal_refresh)
    application_events: list[TrainingLifecycleEvent] = []
    saliency_events: list[str] = []
    service.training.subscribe(
        "training_analysis_published",
        application_events.append,
    )
    service.visualization.subscribe(
        "saliency_changed",
        lambda: saliency_events.append("saliency_changed"),
    )

    assert compute_started.wait(timeout=_THREAD_WATCHDOG_SECONDS)
    release_compute.set()
    assert manager.wait_for_saliency_job(timeout=_THREAD_WATCHDOG_SECONDS)
    assert terminal_refresh_failed.is_set()
    terminal_status = manager.get_post_training_saliency_status()
    assert terminal_status.phase is PostTrainingSaliencyPhase.SUCCEEDED
    assert application_events == []
    assert saliency_events == []

    boundary = service._saliency_notification_boundary
    original_enqueue = boundary._enqueue_deliveries

    def fail_first_handoff(notifications):
        batch = tuple(notifications)
        if not handoff_failed.is_set():
            handoff_failed.set()
            raise RuntimeError("transient notification queue handoff failure")
        return original_enqueue(batch)

    monkeypatch.setattr(boundary, "_enqueue_deliveries", fail_first_handoff)

    with pytest.raises(
        RuntimeError,
        match="transient notification queue handoff failure",
    ):
        service.get_state()

    assert handoff_failed.is_set()
    failed_publication = service.get_view_publication()
    assert (
        failed_publication.state.visualization.post_training_saliency == terminal_status
    )
    assert application_events == []
    assert saliency_events == []
    assert service._pending_saliency_terminal() == terminal_status
    assert boundary._reservations == {}

    service.request_shutdown_fence()
    fenced = service.execute(QueryStateCommand())

    assert fenced.ok is True
    assert service._pending_saliency_terminal() == terminal_status
    assert application_events == []
    assert saliency_events == []

    service.release_shutdown_fence()
    recovered = service.execute(QueryStateCommand())
    publication = service.get_view_publication()

    assert recovered.ok is True
    assert recovered.state == publication.state
    assert publication.generation > pending.generation
    assert service._pending_saliency_terminal() is None
    assert boundary._reservations == {}
    assert len(application_events) == 1
    assert application_events[0].publication_generation == publication.generation
    assert saliency_events == ["saliency_changed"]

    assert service.get_state() == publication.state
    repeated = service.execute(QueryStateCommand())
    assert repeated.ok is True
    assert len(application_events) == 1
    assert saliency_events == ["saliency_changed"]


def test_terminal_queue_handoff_failure_retries_without_public_state_read(
    monkeypatch,
) -> None:
    service, trainer, _holder, _record, _initial_eval_record = (
        _completed_training_service()
    )
    manager = service.study.training_manager
    outcome = trainer.get_terminal_outcome()
    assert outcome.run is not None
    pending_status = PostTrainingSaliencyStatus.pending(
        generation=1,
        run=outcome.run,
        training_generation=trainer.get_state_snapshot_token().generation,
        methods=_BASELINE_METHODS,
    )
    terminal_status = pending_status.transition(
        generation=1,
        phase=PostTrainingSaliencyPhase.FAILED,
        error_code="fault_injection",
        message="Injected terminal failure.",
        diagnostic_type=RuntimeError.__name__,
    )
    with manager._saliency_job_lock:
        manager._saliency_job_sequence = terminal_status.generation
        manager._post_training_saliency_status = terminal_status

    application_events: list[TrainingLifecycleEvent] = []
    saliency_events: list[str] = []
    publication_delivered = Event()
    service.training.subscribe(
        "training_analysis_published",
        application_events.append,
    )
    service.visualization.subscribe(
        "saliency_changed",
        lambda: (
            saliency_events.append("saliency_changed"),
            publication_delivered.set(),
        ),
    )
    boundary = service._saliency_notification_boundary
    original_enqueue = boundary._enqueue_deliveries
    handoff_attempts = 0

    def fail_first_handoff(notifications):
        nonlocal handoff_attempts
        batch = tuple(notifications)
        handoff_attempts += 1
        if handoff_attempts == 1:
            raise RuntimeError("transient notification queue handoff failure")
        return original_enqueue(batch)

    monkeypatch.setattr(boundary, "_enqueue_deliveries", fail_first_handoff)

    manager._notify_post_training_saliency_terminal(terminal_status)

    assert publication_delivered.wait(timeout=_THREAD_WATCHDOG_SECONDS)
    publication = service.get_view_publication()
    assert publication.state.visualization.post_training_saliency == terminal_status
    assert service._pending_saliency_terminal() is None
    assert handoff_attempts == 2
    assert len(application_events) == 1
    assert application_events[0].publication_generation == publication.generation
    assert saliency_events == ["saliency_changed"]

    Event().wait(0.1)
    assert handoff_attempts == 2
    assert len(application_events) == 1
    assert saliency_events == ["saliency_changed"]


def test_nested_public_observer_failures_retry_each_event_to_one_success() -> None:
    service, trainer, _holder, _record, _initial_eval_record = (
        _completed_training_service()
    )
    manager = service.study.training_manager
    outcome = trainer.get_terminal_outcome()
    assert outcome.run is not None
    terminal_status = PostTrainingSaliencyStatus.pending(
        generation=1,
        run=outcome.run,
        training_generation=trainer.get_state_snapshot_token().generation,
        methods=_BASELINE_METHODS,
    ).transition(
        generation=1,
        phase=PostTrainingSaliencyPhase.FAILED,
        error_code="fault_injection",
        message="Injected terminal failure.",
        diagnostic_type=RuntimeError.__name__,
    )
    with manager._saliency_job_lock:
        manager._saliency_job_sequence = terminal_status.generation
        manager._post_training_saliency_status = terminal_status

    analysis_attempts = 0
    saliency_attempts = 0
    analysis_successes: list[int] = []
    saliency_successes: list[int] = []
    analysis_recovered = Event()
    delivered = Event()

    def fail_analysis_once(event: TrainingLifecycleEvent) -> None:
        nonlocal analysis_attempts
        analysis_attempts += 1
        if analysis_attempts == 1:
            raise RuntimeError("transient analysis observer failure")
        publication_generation = event.publication_generation
        assert publication_generation is not None
        analysis_successes.append(publication_generation)
        analysis_recovered.set()

    def fail_saliency_once() -> None:
        nonlocal saliency_attempts
        saliency_attempts += 1
        if saliency_attempts == 1:
            raise RuntimeError("transient visualization observer failure")
        publication = service.get_view_publication()
        saliency_successes.append(
            publication.state.visualization.post_training_saliency.generation
        )
        delivered.set()

    service.training.subscribe("training_analysis_published", fail_analysis_once)
    service.visualization.subscribe("saliency_changed", fail_saliency_once)

    with service.visualization.batch_notifications():
        manager._notify_post_training_saliency_terminal(terminal_status)
        assert analysis_recovered.wait(timeout=_THREAD_WATCHDOG_SECONDS)
        assert saliency_attempts == 0

    assert delivered.wait(timeout=_THREAD_WATCHDOG_SECONDS)
    assert manager.wait_for_saliency_terminal_delivery(timeout=_THREAD_WATCHDOG_SECONDS)
    publication = service.get_view_publication()
    assert publication.state.visualization.post_training_saliency == terminal_status
    assert analysis_attempts == 2
    assert saliency_attempts == 2
    assert analysis_successes == [publication.generation]
    assert saliency_successes == [terminal_status.generation]
    assert service._pending_saliency_terminal() is None

    Event().wait(0.1)
    assert analysis_attempts == 2
    assert saliency_attempts == 2


def test_newer_terminal_generation_supersedes_failed_old_public_delivery() -> None:
    service, trainer, _holder, _record, _initial_eval_record = (
        _completed_training_service()
    )
    manager = service.study.training_manager
    first_run = trainer.get_terminal_outcome().run
    assert first_run is not None
    training_generation = trainer.get_state_snapshot_token().generation

    def failed_status(
        generation: int,
        run: TrainingRunIdentity,
    ) -> PostTrainingSaliencyStatus:
        return PostTrainingSaliencyStatus.pending(
            generation=generation,
            run=run,
            training_generation=training_generation,
            methods=_BASELINE_METHODS,
        ).transition(
            generation=generation,
            phase=PostTrainingSaliencyPhase.FAILED,
            error_code="fault_injection",
            message=f"Injected terminal failure {generation}.",
            diagnostic_type=RuntimeError.__name__,
        )

    first = failed_status(1, first_run)
    second = failed_status(2, first_run)
    analysis_attempts: list[int] = []
    analysis_successes: list[int] = []
    saliency_generations: list[int] = []
    second_delivered = Event()

    def fail_old_analysis(event: TrainingLifecycleEvent) -> None:
        publication_generation = event.publication_generation
        assert publication_generation is not None
        analysis_attempts.append(publication_generation)
        if len(analysis_attempts) == 1:
            raise RuntimeError("old generation observer failure")
        analysis_successes.append(publication_generation)

    def observe_saliency() -> None:
        generation = service.get_view_publication().state.visualization.post_training_saliency.generation
        saliency_generations.append(generation)
        if generation == second.generation:
            second_delivered.set()

    service.training.subscribe("training_analysis_published", fail_old_analysis)
    service.visualization.subscribe("saliency_changed", observe_saliency)

    with manager._saliency_job_lock:
        manager._saliency_job_sequence = first.generation
        manager._post_training_saliency_status = first
    service._publish_post_training_saliency_terminal_state(first)
    with manager._saliency_job_lock:
        manager._saliency_job_sequence = second.generation
        manager._post_training_saliency_status = second
    service._publish_post_training_saliency_terminal_state(second)

    assert second_delivered.wait(timeout=_THREAD_WATCHDOG_SECONDS)
    assert service._saliency_notification_boundary.wait_for_idle(
        timeout=_THREAD_WATCHDOG_SECONDS
    )
    publication = service.get_view_publication()
    assert publication.state.visualization.post_training_saliency == second
    assert len(analysis_attempts) == 2
    assert analysis_successes == [publication.generation]
    assert saliency_generations == [second.generation]
    assert service._pending_saliency_terminal() is None


def test_shutdown_release_retries_real_ui_adapter_handoff_before_reopening(
    monkeypatch,
) -> None:
    service, trainer, _holder, _record, _initial_eval_record = (
        _completed_training_service()
    )
    manager = service.study.training_manager
    outcome = trainer.get_terminal_outcome()
    assert outcome.run is not None
    pending_status = PostTrainingSaliencyStatus.pending(
        generation=1,
        run=outcome.run,
        training_generation=trainer.get_state_snapshot_token().generation,
        methods=_BASELINE_METHODS,
    )
    terminal_status = pending_status.transition(
        generation=1,
        phase=PostTrainingSaliencyPhase.FAILED,
        error_code="fault_injection",
        message="Injected terminal failure.",
        diagnostic_type=RuntimeError.__name__,
    )
    with manager._saliency_job_lock:
        manager._saliency_job_sequence = terminal_status.generation
        manager._post_training_saliency_status = terminal_status

    application_events: list[TrainingLifecycleEvent] = []
    saliency_events: list[str] = []
    service.training.subscribe(
        "training_analysis_published",
        application_events.append,
    )
    service.visualization.subscribe(
        "saliency_changed",
        lambda: saliency_events.append("saliency_changed"),
    )
    service.request_shutdown_fence()
    service._publish_post_training_saliency_terminal_state(terminal_status)
    assert service._pending_saliency_terminal() == terminal_status

    boundary = service._saliency_notification_boundary
    original_enqueue = boundary._enqueue_deliveries
    handoff_attempts = 0

    def fail_first_handoff(notifications):
        nonlocal handoff_attempts
        batch = tuple(notifications)
        if not batch:
            return original_enqueue(batch)
        handoff_attempts += 1
        if handoff_attempts == 1:
            raise RuntimeError("transient shutdown-release handoff failure")
        return original_enqueue(batch)

    monkeypatch.setattr(boundary, "_enqueue_deliveries", fail_first_handoff)
    service.study._application_service = service
    ui_context = SimpleNamespace(study=service.study)

    assert release_application_shutdown_fence(ui_context) is False
    assert service.shutdown_lifecycle.is_shutdown_fenced is True
    assert service._pending_saliency_terminal() == terminal_status
    assert application_events == []
    assert saliency_events == []
    blocked = service.execute(ResetSessionCommand(confirmed=True))
    assert blocked.failed is True
    assert blocked.diagnostics["shutdown_fenced"] is True

    assert release_application_shutdown_fence(ui_context) is False
    publication = service.get_view_publication()
    assert service.shutdown_lifecycle.is_shutdown_fenced is True
    assert service._pending_saliency_terminal() is None
    assert publication.state.visualization.post_training_saliency == terminal_status
    assert handoff_attempts == 2
    assert len(application_events) == 1
    assert application_events[0].publication_generation == publication.generation
    assert saliency_events == ["saliency_changed"]

    manager._notify_post_training_saliency_terminal(terminal_status)

    assert release_application_shutdown_fence(ui_context) is True
    assert service.shutdown_lifecycle.is_shutdown_fenced is False
    assert handoff_attempts == 2
    assert len(application_events) == 1
    assert saliency_events == ["saliency_changed"]


def test_shutdown_release_waits_for_manager_terminal_ledger_commit(
    monkeypatch,
) -> None:
    service, trainer, _holder, _record, _initial_eval_record = (
        _completed_training_service()
    )
    manager = service.study.training_manager
    outcome = trainer.get_terminal_outcome()
    assert outcome.run is not None
    terminal_status = PostTrainingSaliencyStatus.pending(
        generation=1,
        run=outcome.run,
        training_generation=trainer.get_state_snapshot_token().generation,
        methods=_BASELINE_METHODS,
    ).transition(
        generation=1,
        phase=PostTrainingSaliencyPhase.FAILED,
        error_code="fault_injection",
        message="Injected terminal failure.",
        diagnostic_type=RuntimeError.__name__,
    )
    with manager._saliency_job_lock:
        manager._saliency_job_sequence = terminal_status.generation
        manager._post_training_saliency_status = terminal_status

    release_results: list[bool] = []
    race_ledgers = []
    original_notify = manager._saliency_lifecycle_events.notify

    def notify_then_try_release(event: str, status: PostTrainingSaliencyStatus):
        delivered = original_notify(event, status)
        assert service._saliency_notification_boundary.has_delivered_generation(
            status.generation
        )
        service.request_shutdown_fence()
        race_ledgers.append(
            manager.get_post_training_saliency_terminal_delivery_state()
        )
        release_results.append(service.release_shutdown_fence())
        return delivered

    monkeypatch.setattr(
        manager._saliency_lifecycle_events,
        "notify",
        notify_then_try_release,
    )

    manager._notify_post_training_saliency_terminal(terminal_status)

    assert release_results == [False]
    assert service.shutdown_lifecycle.is_shutdown_fenced is True
    assert len(race_ledgers) == 1
    assert race_ledgers[0].pending_generations == (terminal_status.generation,)
    assert race_ledgers[0].active_generation == terminal_status.generation
    assert race_ledgers[0].delivered_generation < terminal_status.generation

    committed = manager.get_post_training_saliency_terminal_delivery_state()
    assert committed.pending_generations == ()
    assert committed.active_generation is None
    assert committed.delivered_generation == terminal_status.generation
    assert service.release_shutdown_fence() is True
    assert service.shutdown_lifecycle.is_shutdown_fenced is False


def test_shutdown_release_retries_unowned_manager_terminal_after_primitive_failure(
    monkeypatch,
) -> None:
    service, trainer, _holder, _record, _initial_eval_record = (
        _completed_training_service()
    )
    manager = service.study.training_manager
    outcome = trainer.get_terminal_outcome()
    assert outcome.run is not None
    terminal_status = PostTrainingSaliencyStatus.pending(
        generation=1,
        run=outcome.run,
        training_generation=trainer.get_state_snapshot_token().generation,
        methods=_BASELINE_METHODS,
    ).transition(
        generation=1,
        phase=PostTrainingSaliencyPhase.FAILED,
        error_code="fault_injection",
        message="Injected terminal failure.",
        diagnostic_type=RuntimeError.__name__,
    )
    with manager._saliency_job_lock:
        manager._saliency_job_sequence = terminal_status.generation
        manager._post_training_saliency_status = terminal_status

    class _RetryPrimitiveConstructorFailure:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("retry primitive constructor failed")

    application_events: list[TrainingLifecycleEvent] = []
    saliency_events: list[str] = []
    service.training.subscribe(
        "training_analysis_published",
        application_events.append,
    )
    service.visualization.subscribe(
        "saliency_changed",
        lambda: saliency_events.append("saliency_changed"),
    )
    service.request_shutdown_fence()
    with monkeypatch.context() as retry_faults:
        retry_faults.setattr(
            "XBrainLab.backend.training_manager.Timer",
            _RetryPrimitiveConstructorFailure,
        )
        retry_faults.setattr(
            "XBrainLab.backend.training_manager.Thread",
            _RetryPrimitiveConstructorFailure,
        )
        manager._notify_post_training_saliency_terminal(terminal_status)

    failed_owner = manager.get_post_training_saliency_terminal_delivery_state()
    assert failed_owner.pending_generations == (terminal_status.generation,)
    assert failed_owner.active_generation is None
    assert failed_owner.retry_owner_active is False
    assert failed_owner.retry_unavailable is True
    assert service._pending_saliency_terminal() == terminal_status

    assert service.release_shutdown_fence() is True

    committed = manager.get_post_training_saliency_terminal_delivery_state()
    assert committed.pending_generations == ()
    assert committed.delivered_generation == terminal_status.generation
    assert committed.retry_unavailable is False
    assert service.shutdown_lifecycle.is_shutdown_fenced is False
    assert service._pending_saliency_terminal() is None
    assert len(application_events) == 1
    assert saliency_events == ["saliency_changed"]


def test_shutdown_release_stays_fenced_when_refresh_fails_before_pending_exists(
    monkeypatch,
) -> None:
    service, trainer, _holder, _record, _initial_eval_record = (
        _completed_training_service()
    )
    manager = service.study.training_manager
    outcome = trainer.get_terminal_outcome()
    assert outcome.run is not None
    pending_status = PostTrainingSaliencyStatus.pending(
        generation=1,
        run=outcome.run,
        training_generation=trainer.get_state_snapshot_token().generation,
        methods=_BASELINE_METHODS,
    )
    terminal_status = pending_status.transition(
        generation=1,
        phase=PostTrainingSaliencyPhase.FAILED,
        error_code="fault_injection",
        message="Injected terminal failure.",
        diagnostic_type=RuntimeError.__name__,
    )
    with manager._saliency_job_lock:
        manager._saliency_job_sequence = pending_status.generation
        manager._post_training_saliency_status = pending_status
    assert service.get_state().visualization.post_training_saliency == pending_status
    with manager._saliency_job_lock:
        manager._post_training_saliency_status = terminal_status

    application_events: list[TrainingLifecycleEvent] = []
    saliency_events: list[str] = []
    service.training.subscribe(
        "training_analysis_published",
        application_events.append,
    )
    service.visualization.subscribe(
        "saliency_changed",
        lambda: saliency_events.append("saliency_changed"),
    )
    original_build = service.state_snapshot.build
    refresh_attempts = 0

    def fail_first_refresh(*, last_error=None):
        nonlocal refresh_attempts
        refresh_attempts += 1
        if refresh_attempts == 1:
            raise RuntimeError("terminal refresh failed before pending handoff")
        return original_build(last_error=last_error)

    monkeypatch.setattr(service.state_snapshot, "build", fail_first_refresh)
    service.request_shutdown_fence()

    assert service.release_shutdown_fence() is False
    assert service.shutdown_lifecycle.is_shutdown_fenced is True
    assert service._pending_saliency_terminal() == terminal_status
    assert application_events == []
    assert saliency_events == []
    blocked = service.execute(ResetSessionCommand(confirmed=True))
    assert blocked.failed is True
    assert blocked.diagnostics["shutdown_fenced"] is True

    assert service.release_shutdown_fence() is False
    publication = service.get_view_publication()
    assert service.shutdown_lifecycle.is_shutdown_fenced is True
    assert publication.state.visualization.post_training_saliency == terminal_status
    assert len(application_events) == 1
    assert application_events[0].publication_generation == publication.generation
    assert saliency_events == ["saliency_changed"]
    assert service._pending_saliency_terminal() is None

    manager._notify_post_training_saliency_terminal(terminal_status)

    assert service.release_shutdown_fence() is True
    assert service.shutdown_lifecycle.is_shutdown_fenced is False


def test_close_discards_retryable_terminal_after_queue_handoff_failure(
    monkeypatch,
) -> None:
    service, trainer, _holder, _record, _initial_eval_record = (
        _completed_training_service()
    )
    manager = service.study.training_manager
    outcome = trainer.get_terminal_outcome()
    assert outcome.run is not None
    generation = 1
    pending_status = PostTrainingSaliencyStatus.pending(
        generation=generation,
        run=outcome.run,
        training_generation=trainer.get_state_snapshot_token().generation,
        methods=_BASELINE_METHODS,
    )
    running_status = pending_status.transition(
        generation=generation,
        phase=PostTrainingSaliencyPhase.RUNNING,
        message="Automatic saliency is running.",
    )
    terminal_status = running_status.transition(
        generation=generation,
        phase=PostTrainingSaliencyPhase.SUCCEEDED,
        message="Automatic saliency finished.",
    )

    def set_manager_status(status: PostTrainingSaliencyStatus) -> None:
        with manager._saliency_job_lock:
            manager._saliency_job_sequence = status.generation
            manager._post_training_saliency_status = status

    set_manager_status(pending_status)
    assert service.get_state().visualization.post_training_saliency == pending_status
    set_manager_status(terminal_status)

    application_events: list[TrainingLifecycleEvent] = []
    saliency_events: list[str] = []
    service.training.subscribe(
        "training_analysis_published",
        application_events.append,
    )
    service.visualization.subscribe(
        "saliency_changed",
        lambda: saliency_events.append("saliency_changed"),
    )
    boundary = service._saliency_notification_boundary

    def fail_handoff(_notifications) -> None:
        raise RuntimeError("terminal queue unavailable during close")

    monkeypatch.setattr(boundary, "_enqueue_deliveries", fail_handoff)
    with pytest.raises(
        RuntimeError,
        match="terminal queue unavailable during close",
    ):
        service._publish_post_training_saliency_terminal_state(terminal_status)

    assert service._pending_saliency_terminal() == terminal_status
    assert boundary._reservations == {}

    service.close()
    service.close()

    assert service._pending_saliency_terminal() is None
    assert application_events == []
    assert saliency_events == []
    assert boundary._reservations == {}


def test_close_discards_committed_terminal_after_public_observer_failure() -> None:
    service, trainer, _holder, _record, _initial_eval_record = (
        _completed_training_service()
    )
    manager = service.study.training_manager
    outcome = trainer.get_terminal_outcome()
    assert outcome.run is not None
    terminal_status = PostTrainingSaliencyStatus.pending(
        generation=1,
        run=outcome.run,
        training_generation=trainer.get_state_snapshot_token().generation,
        methods=_BASELINE_METHODS,
    ).transition(
        generation=1,
        phase=PostTrainingSaliencyPhase.FAILED,
        error_code="fault_injection",
        message="Injected terminal failure.",
        diagnostic_type=RuntimeError.__name__,
    )
    with manager._saliency_job_lock:
        manager._saliency_job_sequence = terminal_status.generation
        manager._post_training_saliency_status = terminal_status

    analysis_attempted = Event()
    saliency_events: list[str] = []

    def fail_analysis(_event: TrainingLifecycleEvent) -> None:
        analysis_attempted.set()
        raise RuntimeError("terminal observer remains unavailable")

    service.training.subscribe("training_analysis_published", fail_analysis)
    service.visualization.subscribe(
        "saliency_changed",
        lambda: saliency_events.append("saliency_changed"),
    )

    service._publish_post_training_saliency_terminal_state(terminal_status)

    assert analysis_attempted.is_set()
    assert service._pending_saliency_terminal() == terminal_status
    service.close()
    service.close()

    assert service._pending_saliency_terminal() is None
    assert service._saliency_notification_boundary.wait_for_idle(timeout=0.1)
    assert saliency_events == []


def test_saliency_worker_failure_republishes_terminal_application_view(
    monkeypatch,
) -> None:
    service, trainer, holder, _record, _initial_eval_record = (
        _completed_training_service()
    )
    compute_started = Event()

    def failed_compute(_plan, *, should_cancel):
        compute_started.set()
        assert should_cancel() is False
        raise RuntimeError("bounded saliency failure")

    monkeypatch.setattr(holder, "compute_saliency_update", failed_compute)
    pending = _schedule_baseline(service, trainer)
    terminal_events: list[TrainingLifecycleEvent] = []
    service.training.subscribe(
        "training_analysis_published",
        terminal_events.append,
    )

    assert compute_started.wait(timeout=_THREAD_WATCHDOG_SECONDS)
    assert service.study.training_manager.wait_for_saliency_job(
        timeout=_THREAD_WATCHDOG_SECONDS
    )

    publication = service.get_view_publication()
    query = service.execute(QueryStateCommand())
    status = publication.state.visualization.post_training_saliency
    assert query.state == publication.state
    assert publication.generation > pending.generation
    assert status.phase is PostTrainingSaliencyPhase.FAILED
    assert status.generation == (
        pending.state.visualization.post_training_saliency.generation
    )
    assert status.error_code == "computation_failed"
    assert _method_coverage(publication, "Gradient").complete is False
    assert len(terminal_events) == 1
    assert terminal_events[0].publication_generation == publication.generation


def test_stale_automatic_command_preserves_current_application_publication(
    monkeypatch,
) -> None:
    service, trainer, holder, record, initial_eval_record = (
        _completed_training_service()
    )
    terminal_eval_record = _bound_saliency_eval_record(holder, record)

    def complete_compute(plan, *, should_cancel):
        assert should_cancel() is False
        return PreparedSaliencyUpdate(
            plan=plan,
            eval_records=((record, initial_eval_record, terminal_eval_record),),
        )

    monkeypatch.setattr(holder, "compute_saliency_update", complete_compute)
    _schedule_baseline(service, trainer)
    assert service.study.training_manager.wait_for_saliency_job(
        timeout=_THREAD_WATCHDOG_SECONDS
    )
    current = service.get_view_publication()
    current_status = current.state.visualization.post_training_saliency
    assert current_status.phase is PostTrainingSaliencyPhase.SUCCEEDED
    observed_events: list[str] = []
    service.training.subscribe(
        "training_analysis_published",
        lambda _event: observed_events.append("training_analysis_published"),
    )
    service.visualization.subscribe(
        "saliency_changed",
        lambda: observed_events.append("saliency_changed"),
    )
    delayed = PostTrainingSaliencyTarget(
        run=TrainingRunIdentity(trainer_id="retired-trainer", run_id=1),
        finished_runs_before=0,
        finished_runs_after=1,
        append=True,
    )

    with post_training_saliency_target(delayed):
        result = service.execute(
            SaliencyCommand(
                method="Gradient",
                params={
                    "profile": "recommended",
                    "methods": list(_BASELINE_METHODS),
                },
            )
        )

    stale = delayed.schedule_outcome
    assert stale is not None
    assert stale.disposition is PostTrainingSaliencyScheduleDisposition.STALE
    assert stale.reason is PostTrainingSaliencyScheduleReason.TRAINING_RUN_CHANGED
    assert result.failed is True
    assert service.study.training_manager.get_post_training_saliency_status() == (
        current_status
    )
    restored = service.get_view_publication()
    assert restored.generation == current.generation
    assert restored.revision > current.revision
    assert restored.state == current.state
    assert restored.capabilities == current.capabilities
    assert restored.training_boundary == current.training_boundary
    assert restored.usable is True
    assert observed_events == []


def test_explicit_saliency_cancellation_republishes_current_application_view(
    monkeypatch,
) -> None:
    service, trainer, holder, record, initial_eval_record = (
        _completed_training_service()
    )
    compute_started = Event()
    cancellation_seen = Event()

    def cancellable_compute(plan, *, should_cancel):
        compute_started.set()
        while not should_cancel():
            cancellation_seen.wait(0.01)
        cancellation_seen.set()
        return PreparedSaliencyUpdate(
            plan=plan,
            eval_records=((record, initial_eval_record, initial_eval_record),),
        )

    monkeypatch.setattr(holder, "compute_saliency_update", cancellable_compute)
    pending = _schedule_baseline(service, trainer)
    pending_status = pending.state.visualization.post_training_saliency
    terminal_events: list[TrainingLifecycleEvent] = []
    service.training.subscribe(
        "training_analysis_published",
        terminal_events.append,
    )
    assert compute_started.wait(timeout=_THREAD_WATCHDOG_SECONDS)

    service.study.training_manager.cancel_saliency_job()

    publication = service.get_view_publication()
    query = service.execute(QueryStateCommand())
    status = publication.state.visualization.post_training_saliency
    assert query.state == publication.state
    assert publication.generation > pending.generation
    assert status.phase is PostTrainingSaliencyPhase.CANCELLED
    assert status.generation == pending_status.generation
    assert _method_coverage(publication, "Gradient").complete is False
    assert len(terminal_events) == 1
    assert terminal_events[0].publication_generation == publication.generation
    assert cancellation_seen.wait(timeout=_THREAD_WATCHDOG_SECONDS)
    assert service.study.training_manager.wait_for_saliency_job(
        timeout=_THREAD_WATCHDOG_SECONDS
    )
    assert service.get_view_publication() == publication


def test_reset_cancellation_retires_worker_generation_without_stale_republish(
    monkeypatch,
) -> None:
    service, trainer, holder, record, initial_eval_record = (
        _completed_training_service()
    )
    compute_started = Event()
    cancellation_seen = Event()
    terminal_eval_record = _bound_saliency_eval_record(holder, record)

    def cancellable_compute(plan, *, should_cancel):
        compute_started.set()
        while not should_cancel():
            cancellation_seen.wait(0.01)
        cancellation_seen.set()
        return PreparedSaliencyUpdate(
            plan=plan,
            eval_records=((record, initial_eval_record, terminal_eval_record),),
        )

    monkeypatch.setattr(holder, "compute_saliency_update", cancellable_compute)
    pending = _schedule_baseline(service, trainer)
    pending_status_generation = (
        pending.state.visualization.post_training_saliency.generation
    )
    assert compute_started.wait(timeout=_THREAD_WATCHDOG_SECONDS)

    reset = service.execute(ResetSessionCommand(confirmed=True))

    assert reset.ok is True, reset.message
    assert cancellation_seen.wait(timeout=_THREAD_WATCHDOG_SECONDS)
    assert service.study.training_manager.wait_for_saliency_job(
        timeout=_THREAD_WATCHDOG_SECONDS
    )
    publication = service.get_view_publication()
    query = service.execute(QueryStateCommand())
    status = publication.state.visualization.post_training_saliency
    assert query.state == publication.state
    assert status.phase is PostTrainingSaliencyPhase.IDLE
    assert status.generation > pending_status_generation
    assert service.study.training_manager.trainer is None
    assert publication.state.visualization.saliency_coverage == []


def test_reset_does_not_deadlock_with_terminal_publication_callback(
    monkeypatch,
) -> None:
    service, trainer, holder, record, initial_eval_record = (
        _completed_training_service()
    )
    compute_started = Event()
    release_compute = Event()
    terminal_eval_record = _bound_saliency_eval_record(holder, record)

    def bounded_compute(plan, *, should_cancel):
        compute_started.set()
        assert release_compute.wait(timeout=_THREAD_WATCHDOG_SECONDS)
        return PreparedSaliencyUpdate(
            plan=plan,
            eval_records=((record, initial_eval_record, terminal_eval_record),),
        )

    monkeypatch.setattr(holder, "compute_saliency_update", bounded_compute)
    pending = _schedule_baseline(service, trainer)
    pending_status_generation = (
        pending.state.visualization.post_training_saliency.generation
    )
    assert compute_started.wait(timeout=_THREAD_WATCHDOG_SECONDS)

    with service._command_lock:
        release_compute.set()
        assert _wait_for_manager_phase(
            service,
            PostTrainingSaliencyPhase.SUCCEEDED,
        )
        reset = service.execute(ResetSessionCommand(confirmed=True))

    assert reset.ok is True, reset.message
    assert service.study.training_manager.wait_for_saliency_job(
        timeout=_THREAD_WATCHDOG_SECONDS
    )
    publication = service.get_view_publication()
    status = publication.state.visualization.post_training_saliency
    assert status.phase is PostTrainingSaliencyPhase.IDLE
    assert status.generation > pending_status_generation
    assert publication.state.visualization.saliency_coverage == []


def test_shutdown_fence_blocks_late_worker_terminal_publication(monkeypatch) -> None:
    service, trainer, holder, record, initial_eval_record = (
        _completed_training_service()
    )
    compute_started = Event()
    release_compute = Event()
    terminal_eval_record = _bound_saliency_eval_record(holder, record)

    def bounded_compute(plan, *, should_cancel):
        compute_started.set()
        assert release_compute.wait(timeout=_THREAD_WATCHDOG_SECONDS)
        return PreparedSaliencyUpdate(
            plan=plan,
            eval_records=((record, initial_eval_record, terminal_eval_record),),
        )

    monkeypatch.setattr(holder, "compute_saliency_update", bounded_compute)
    pending = _schedule_baseline(service, trainer)
    terminal_events: list[TrainingLifecycleEvent] = []
    service.training.subscribe(
        "training_analysis_published",
        terminal_events.append,
    )
    assert compute_started.wait(timeout=_THREAD_WATCHDOG_SECONDS)

    with service._command_lock:
        release_compute.set()
        assert _wait_for_manager_phase(
            service,
            PostTrainingSaliencyPhase.SUCCEEDED,
        )
        service.request_shutdown_fence()

    assert service.study.training_manager.wait_for_saliency_job(
        timeout=_THREAD_WATCHDOG_SECONDS
    )
    publication = service.get_view_publication()
    query = service.execute(QueryStateCommand())
    assert query.state == publication.state == pending.state
    assert publication.generation == pending.generation
    assert publication.state.visualization.post_training_saliency.phase is (
        PostTrainingSaliencyPhase.PENDING
    )
    assert terminal_events == []

    service.release_shutdown_fence()

    reopened = service.get_view_publication()
    reopened_query = service.execute(QueryStateCommand())
    assert reopened_query.state == reopened.state
    assert reopened.generation > pending.generation
    assert reopened.state.visualization.post_training_saliency.phase is (
        PostTrainingSaliencyPhase.SUCCEEDED
    )
    assert _method_coverage(reopened, "Gradient").complete is True
    assert _method_coverage(reopened, "Gradient * Input").complete is True
    assert len(terminal_events) == 1
    assert terminal_events[0].publication_generation == reopened.generation


def test_delayed_old_terminal_delivery_is_monotonic_and_cannot_revert_publication(
    monkeypatch,
) -> None:
    service, trainer, _holder, _record, _eval_record = _completed_training_service()
    manager = service.study.training_manager
    outcome = trainer.get_terminal_outcome()
    assert outcome.run is not None
    training_generation = trainer.get_state_snapshot_token().generation
    second_run = TrainingRunIdentity(
        trainer_id=outcome.run.trainer_id,
        run_id=outcome.run.run_id + 1,
    )

    def terminal_status(
        generation: int,
        run: TrainingRunIdentity,
    ) -> tuple[PostTrainingSaliencyStatus, PostTrainingSaliencyStatus]:
        pending = PostTrainingSaliencyStatus.pending(
            generation=generation,
            run=run,
            training_generation=training_generation,
            methods=_BASELINE_METHODS,
        )
        running = pending.transition(
            generation=generation,
            phase=PostTrainingSaliencyPhase.RUNNING,
            message="Automatic saliency is running.",
        )
        return pending, running.transition(
            generation=generation,
            phase=PostTrainingSaliencyPhase.SUCCEEDED,
            message="Automatic saliency finished.",
        )

    first_pending, first_terminal = terminal_status(1, outcome.run)
    second_pending, second_terminal = terminal_status(2, second_run)
    old_notify_entered = Event()
    release_old_notify = Event()
    old_notify_completed = Event()
    second_delivered = Event()
    manager_events: list[PostTrainingSaliencyStatus] = []
    application_events: list[TrainingLifecycleEvent] = []

    def observe_manager(status: PostTrainingSaliencyStatus) -> None:
        manager_events.append(status)
        if status == second_terminal:
            second_delivered.set()

    manager.subscribe_post_training_saliency_terminal(observe_manager)
    service.training.subscribe("training_analysis_published", application_events.append)
    original_notify = manager._saliency_lifecycle_events.notify

    def notify_after_barrier(event_name, status) -> None:
        if status == first_terminal:
            old_notify_entered.set()
            assert release_old_notify.wait(timeout=_THREAD_WATCHDOG_SECONDS)
        original_notify(event_name, status)
        if status == first_terminal:
            old_notify_completed.set()

    monkeypatch.setattr(
        manager._saliency_lifecycle_events,
        "notify",
        notify_after_barrier,
    )

    def set_manager_status(status: PostTrainingSaliencyStatus) -> None:
        with manager._saliency_job_lock:
            manager._saliency_job_sequence = status.generation
            manager._post_training_saliency_status = status

    set_manager_status(first_pending)
    assert service.get_state().visualization.post_training_saliency == first_pending
    set_manager_status(first_terminal)
    old_delivery = Thread(
        target=manager._notify_post_training_saliency_terminal,
        args=(first_terminal,),
        daemon=True,
    )
    old_delivery.start()
    assert old_notify_entered.wait(timeout=_THREAD_WATCHDOG_SECONDS)

    set_manager_status(second_pending)
    assert service.get_state().visualization.post_training_saliency == second_pending
    set_manager_status(second_terminal)
    manager._notify_post_training_saliency_terminal(second_terminal)
    release_old_notify.set()

    assert old_notify_completed.wait(timeout=_THREAD_WATCHDOG_SECONDS)
    assert second_delivered.wait(timeout=_THREAD_WATCHDOG_SECONDS)
    old_delivery.join(timeout=_THREAD_WATCHDOG_SECONDS)
    assert not old_delivery.is_alive()

    publication = service.get_view_publication()
    assert manager.get_post_training_saliency_status() == second_terminal
    assert publication.state.visualization.post_training_saliency == second_terminal
    assert [status.generation for status in manager_events] == sorted(
        status.generation for status in manager_events
    )
    assert manager_events[-1] == second_terminal
    assert len(application_events) == 1
    assert application_events[0].publication_generation == publication.generation


@pytest.mark.parametrize("trigger", ["cancel", "reset", "configure", "shutdown"])
def test_synchronous_saliency_terminal_observers_run_after_all_outer_locks(
    monkeypatch,
    trigger: str,
) -> None:
    service, trainer, holder, _record, _initial_eval_record = (
        _completed_training_service()
    )
    compute_started = Event()
    cancelled_published = Event()
    cancel_event_ready = Event()
    cancel_events: list[Event] = []
    manager = service.study.training_manager

    def cancellable_compute(_plan, *, should_cancel):
        compute_started.set()
        assert cancel_event_ready.wait(timeout=_THREAD_WATCHDOG_SECONDS)
        assert cancel_events[0].wait(timeout=_THREAD_WATCHDOG_SECONDS)
        assert should_cancel() is True
        return object()

    monkeypatch.setattr(holder, "compute_saliency_update", cancellable_compute)
    pending = _schedule_baseline(service, trainer)
    cancel_event = manager._saliency_job_cancel
    assert cancel_event is not None
    cancel_events.append(cancel_event)
    cancel_event_ready.set()
    assert compute_started.wait(timeout=_THREAD_WATCHDOG_SECONDS)

    observed: list[tuple[str, PostTrainingSaliencyPhase, tuple[bool, bool, bool]]] = []

    def observe(event_name: str) -> None:
        publication = service.get_view_publication()
        observed.append(
            (
                event_name,
                publication.state.visualization.post_training_saliency.phase,
                (
                    _lock_available_from_another_thread(manager._saliency_job_lock),
                    _lock_available_from_another_thread(
                        service._command_admission_lock
                    ),
                    _lock_available_from_another_thread(service._command_lock),
                ),
            )
        )

    service.training.subscribe(
        "training_analysis_published",
        lambda _event: observe("training_analysis_published"),
    )
    service.visualization.subscribe(
        "saliency_changed",
        lambda: observe("saliency_changed"),
    )

    def observe_manager_terminal(status) -> None:
        observed.append(
            (
                "manager_terminal",
                status.phase,
                (
                    _lock_available_from_another_thread(manager._saliency_job_lock),
                    _lock_available_from_another_thread(
                        service._command_admission_lock
                    ),
                    _lock_available_from_another_thread(service._command_lock),
                ),
            )
        )
        if status.phase is PostTrainingSaliencyPhase.CANCELLED:
            cancelled_published.set()

    manager.subscribe_post_training_saliency_terminal(observe_manager_terminal)

    if trigger == "cancel":
        manager.cancel_saliency_job()
    elif trigger == "reset":
        result = service.execute(ResetSessionCommand(confirmed=True))
        assert result.ok is True, result.message
    elif trigger == "configure":
        original_set_saliency_params = manager.set_saliency_params

        def cancel_then_configure(params):
            manager.cancel_saliency_job()
            manager.saliency_params = dict(params)

        monkeypatch.setattr(manager, "set_saliency_params", cancel_then_configure)
        result = service.execute(
            SaliencyCommand(
                method="Gradient",
                params={"methods": list(_BASELINE_METHODS)},
            )
        )
        monkeypatch.setattr(
            manager,
            "set_saliency_params",
            original_set_saliency_params,
        )
        assert result.ok is True, result.message
    else:
        service.request_shutdown_fence()

    assert manager.wait_for_saliency_job(timeout=_THREAD_WATCHDOG_SECONDS)
    assert cancelled_published.is_set()
    if trigger == "shutdown":
        service.release_shutdown_fence()
    final_publication = service.get_view_publication()
    final_status = final_publication.state.visualization.post_training_saliency
    if trigger == "reset":
        assert final_status.phase is PostTrainingSaliencyPhase.IDLE
        assert final_status.generation > (
            pending.state.visualization.post_training_saliency.generation
        )
    else:
        assert final_status.phase is PostTrainingSaliencyPhase.CANCELLED

    assert sorted(item[0] for item in observed) == [
        "manager_terminal",
        "saliency_changed",
        "training_analysis_published",
    ]
    assert (
        next(phase for event, phase, _locks in observed if event == "manager_terminal")
        is PostTrainingSaliencyPhase.CANCELLED
    )
    assert all(lock_state == (True, True, True) for _, _, lock_state in observed)


def test_saliency_render_rejects_a_stale_publication_generation() -> None:
    service, _trainer, holder, record, _initial_eval_record = (
        _completed_training_service()
    )
    _first_record, first_publication = _publish_renderable_saliency(
        service,
        holder,
        record,
    )
    stale_request = _render_request(first_publication)

    replacement = _bound_saliency_eval_record(holder, record)
    replacement.gradient[0].fill(2.0)
    record.set_eval_record(replacement)
    service.get_state()
    current_publication = service.get_view_publication()

    assert current_publication.generation > first_publication.generation
    with pytest.raises(PreconditionError) as error:
        service.get_saliency_render(stale_request)

    assert error.value.diagnostics["retryable"] is True
    assert error.value.diagnostics["publication_generation_before"] == (
        first_publication.generation
    )
    assert error.value.diagnostics["publication_generation_after"] == (
        current_publication.generation
    )


def test_saliency_render_rejects_a_commit_that_crosses_the_copy_barrier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _trainer, holder, record, _initial_eval_record = (
        _completed_training_service()
    )
    _source_record, publication = _publish_renderable_saliency(
        service,
        holder,
        record,
    )
    request = _render_request(publication)
    replacement = _bound_saliency_eval_record(holder, record)
    replacement.gradient[0].fill(3.0)

    from XBrainLab.backend.application import saliency_render

    original_copy = saliency_render._copy_array_readonly
    commit_count = 0

    def commit_during_first_copy(value):
        nonlocal commit_count
        commit_count += 1
        if commit_count == 1:
            record.set_eval_record(replacement)
        return original_copy(value)

    monkeypatch.setattr(
        saliency_render,
        "_copy_array_readonly",
        commit_during_first_copy,
    )

    with pytest.raises(PreconditionError) as error:
        service.get_saliency_render(request)

    assert commit_count >= 1
    assert error.value.diagnostics["retryable"] is True
    assert error.value.diagnostics["training_state_changed"] is True


def test_saliency_render_arrays_are_readonly_and_detached() -> None:
    service, _trainer, holder, record, _initial_eval_record = (
        _completed_training_service()
    )
    source_record, publication = _publish_renderable_saliency(
        service,
        holder,
        record,
    )

    render = service.get_saliency_render(_render_request(publication))
    copied = render.data.saliency_by_class[0]

    assert copied.flags.writeable is False
    source_record.gradient[0].fill(9.0)
    assert np.all(copied == 1.0)
    with pytest.raises(ValueError):
        copied[0, 0, 0] = 4.0


def test_saliency_render_reads_training_history_from_runtime_not_study_alias() -> None:
    service, _trainer, holder, record, _initial_eval_record = (
        _completed_training_service(study=_TrainerAliasRaisesStudy())
    )
    _source_record, publication = _publish_renderable_saliency(
        service,
        holder,
        record,
    )

    render = service.get_saliency_render(_render_request(publication))

    assert np.all(render.data.saliency_by_class[0] == 1.0)


def test_saliency_render_accepts_a_safely_recovered_view_publication() -> None:
    service, _trainer, holder, record, _initial_eval_record = (
        _completed_training_service()
    )
    _eval_record, initial = _publish_renderable_saliency(service, holder, record)
    service._view_coordinator.mark_stale("transient visualization read failure")

    recovered = service.get_view_publication()
    render = service.get_saliency_render(_render_request(recovered))

    assert recovered.usable is True
    assert recovered.generation > initial.generation
    assert render.generation == recovered.generation
    assert render.training_generation == (
        service.state_snapshot.capture_training_read_boundary().token.generation
    )


def test_saliency_render_rejects_unverified_class_identity() -> None:
    service, _trainer, holder, record, _initial_eval_record = (
        _completed_training_service()
    )
    eval_record, publication = _publish_renderable_saliency(service, holder, record)
    cast(Any, eval_record).validate_saliency_context = None

    with pytest.raises(PreconditionError, match="identity context"):
        service.get_saliency_render(_render_request(publication))
