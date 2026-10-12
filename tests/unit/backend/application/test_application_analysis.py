"""Application boundary: analysis behavior."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from threading import Event, Lock, Thread, current_thread
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch

from tests.unit.backend.application.application_test_support import (
    THREAD_WATCHDOG_SECONDS,
    _off_class_weighting,
    _positive_epoch_data,
    _raw_mock,
    _RecoveryBlockingPlan,
    _valid_training_option,
)
from XBrainLab.backend.application import (
    ApplicationService,
    ApplyMontageCommand,
    ClearTrainingHistoryCommand,
    CommandName,
    CommandResult,
    ErrorType,
    EvaluateCommand,
    QueryStateCommand,
    SaliencyCommand,
    StopTrainingCommand,
    VisualizeCommand,
)
from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.evaluation_render import (
    EvaluationPlanIdentity,
    EvaluationSummaryIdentity,
)
from XBrainLab.backend.application.owned_work import (
    OwnedWorkPhase,
)
from XBrainLab.backend.application.resource_guard import (
    ResourceChecker,
)
from XBrainLab.backend.application.state import (
    ActiveTrainingSnapshot,
    ApplicationStateSnapshot,
    EvaluationStateSnapshot,
    TrainingStateSnapshot,
)
from XBrainLab.backend.study import Study
from XBrainLab.backend.training import (
    ModelHolder,
    Trainer,
    TrainingPlanHolder,
)
from XBrainLab.backend.training.evaluator import Evaluator
from XBrainLab.backend.training.record import (
    TrainRecord,
)
from XBrainLab.backend.training_manager import (
    PostTrainingSaliencyTarget,
    post_training_saliency_target,
)
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    PostTrainingSaliencyScheduleDisposition,
    PostTrainingSaliencyScheduleReason,
    TrainingOutcomeState,
    TrainingRunIdentity,
    TrainingTerminalOutcome,
)

TRAINING_ACTIVE_SALIENCY_REASON = (
    "Wait for training to finish before configuring saliency."
)


STALE_SALIENCY_MESSAGE = (
    "Training or evaluation state changed during saliency recomputation. "
    "No saliency changes were applied; retry after training is idle."
)


SALIENCY_OOM_MESSAGE = (
    "Not enough GPU memory to recompute saliency. Existing evaluation results "
    "were kept. Reduce the selected saliency methods or sample count, then retry."
)


def test_evaluate_command_returns_typed_service_backed_summary():
    service = ApplicationService(Study())
    run = MagicMock()
    run.is_finished.return_value = True
    run.get_name.return_value = "Repeat-0"
    eval_record = SimpleNamespace(evaluation_split="test")
    run.get_eval_record.return_value = eval_record
    run.get_available_evaluation_splits.return_value = ["test"]
    run.get_evaluation_record_for_split.side_effect = (
        lambda split: eval_record if split == "test" else None
    )
    run.class_weighting = _off_class_weighting()
    plan = MagicMock()
    plan.get_name.return_value = "Plan A"
    plan.get_plans.return_value = [run]
    trainer = Trainer([])
    trainer.get_training_plan_holders = MagicMock(return_value=[plan])
    service.study.training_manager.trainer = trainer
    service.training_runtime.training_plan_holders = MagicMock(return_value=(plan,))

    result = service.execute(EvaluateCommand())

    assert result.ok is True
    assert not hasattr(service, "evaluation")
    assert result.command_name == "evaluate"
    assert result.diagnostics["payload_type"] == "evaluation_summary"
    assert result.diagnostics["evaluation_publication_generation"] == (
        service.get_view_publication().generation
    )
    assert result.diagnostics["available"] is True
    assert result.diagnostics["plan_count"] == 1
    assert result.diagnostics["plans"] == [
        {
            "identity": {"plan_index": 0},
            "name": "Plan A",
            "run_count": 1,
            "finished_run_count": 1,
            "evaluation_splits": ["test"],
            "runs": [
                {
                    "identity": {"plan_index": 0, "run_index": 0},
                    "name": "Repeat-0",
                    "finished": True,
                    "evaluation_split": "test",
                    "evaluation_splits": ["test"],
                }
            ],
        }
    ]
    assert "plan_objects" not in result.diagnostics
    assert result.diagnostics["training_read_verified"] is True
    assert isinstance(result.diagnostics["training_read_generation"], int)
    assert result.state.last_error is None


def test_model_summary_shutdown_cancel_is_terminal_and_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study = Study()
    epoch_data = SimpleNamespace(
        get_model_args=lambda: {
            "n_classes": 2,
            "channels": 2,
            "samples": 16,
            "sfreq": 128,
        },
        get_data=lambda: SimpleNamespace(shape=(8, 2, 16)),
    )
    dataset = SimpleNamespace(get_epoch_data=lambda: epoch_data)
    model = SimpleNamespace(parameters=list)
    run = MagicMock()
    run.is_finished.return_value = True
    run.get_name.return_value = "Repeat-0"
    run.eval_record.evaluation_split = "test"
    run.class_weighting = _off_class_weighting()
    plan = MagicMock()
    plan.dataset = dataset
    plan.model_holder = SimpleNamespace(get_model=lambda _args: model)
    plan.get_name.return_value = "Plan A"
    plan.get_plans.return_value = [run]
    trainer = Trainer([])
    trainer.get_training_plan_holders = MagicMock(return_value=[plan])
    study.training_manager.trainer = trainer
    service = ApplicationService(study)
    service.training_runtime.training_plan_holders = MagicMock(return_value=(plan,))
    summary_started = Event()
    release_summary = Event()
    summary_calls = 0

    def blocked_summary(*_args: Any, **_kwargs: Any) -> str:
        nonlocal summary_calls
        summary_calls += 1
        if summary_calls == 1:
            summary_started.set()
            assert release_summary.wait(timeout=THREAD_WATCHDOG_SECONDS)
        return "Model summary"

    monkeypatch.setattr("torchinfo.summary", blocked_summary)
    command = EvaluateCommand(
        summary_identity=EvaluationSummaryIdentity(
            plan=EvaluationPlanIdentity(plan_index=0),
        )
    )
    operation = service.begin_owned_operation(command)
    before = service.get_view_publication()
    results: list[CommandResult] = []
    worker = Thread(
        target=lambda: results.append(
            service.execute(command, operation_id=operation.operation_id)
        ),
        name="model-summary-shutdown-cancel",
    )
    worker.start()
    assert summary_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    assert service.get_owned_operation(operation.operation_id).stage == (
        "Building detailed model summary"
    )

    command_lock_available = service._command_lock.acquire(False)
    if command_lock_available:
        service._command_lock.release()
    assert command_lock_available is True

    started_at = time.monotonic()
    stop_result = service.execute(StopTrainingCommand())
    stop_elapsed = time.monotonic() - started_at
    assert stop_elapsed < 0.1
    assert stop_result.ok

    started_at = time.monotonic()
    assert service.cancel_owned_operation(operation.operation_id) is True
    owned_cancel_elapsed = time.monotonic() - started_at
    assert owned_cancel_elapsed < 0.1

    started_at = time.monotonic()
    service.request_shutdown_fence()
    fence_elapsed = time.monotonic() - started_at
    release_summary.set()
    worker.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert fence_elapsed < 0.1
    assert not worker.is_alive()
    assert len(results) == 1
    cancelled = results[0]
    assert cancelled.error_type is ErrorType.CANCELLED
    assert cancelled.diagnostics["operation_cancelled"] is True
    assert "model_summary" not in cancelled.diagnostics
    assert service.get_view_publication() == before
    assert service.get_owned_operation(operation.operation_id).phase is (
        OwnedWorkPhase.CANCELLED
    )

    assert service.release_shutdown_fence()
    retry_operation = service.begin_owned_operation(command)
    retried = service.execute(command, operation_id=retry_operation.operation_id)

    assert retried.ok
    assert retried.diagnostics["model_summary"]["text"] == "Model summary"
    assert service.get_owned_operation(retry_operation.operation_id).phase is (
        OwnedWorkPhase.COMPLETED
    )
    assert summary_calls == 2


def test_model_summary_model_construction_does_not_hold_command_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    study = Study()
    epoch_data = SimpleNamespace(
        get_model_args=lambda: {
            "n_classes": 2,
            "channels": 2,
            "samples": 16,
            "sfreq": 128,
        },
        get_data=lambda: SimpleNamespace(shape=(8, 2, 16)),
    )
    dataset = SimpleNamespace(get_epoch_data=lambda: epoch_data)
    model = SimpleNamespace(parameters=list)
    constructor_started = Event()
    release_constructor = Event()

    def build_model(_args: dict[str, int]) -> Any:
        constructor_started.set()
        assert release_constructor.wait(timeout=THREAD_WATCHDOG_SECONDS)
        return model

    run = MagicMock()
    run.is_finished.return_value = True
    run.eval_record.evaluation_split = "test"
    run.class_weighting = _off_class_weighting()
    plan = MagicMock()
    plan.dataset = dataset
    plan.model_holder = SimpleNamespace(get_model=build_model)
    plan.get_name.return_value = "Plan A"
    plan.get_plans.return_value = [run]
    trainer = Trainer([])
    trainer.get_training_plan_holders = MagicMock(return_value=[plan])
    study.training_manager.trainer = trainer
    service = ApplicationService(study)
    service.training_runtime.training_plan_holders = MagicMock(return_value=(plan,))
    monkeypatch.setattr("torchinfo.summary", lambda *_args, **_kwargs: "Summary")
    command = EvaluateCommand(
        summary_identity=EvaluationSummaryIdentity(
            plan=EvaluationPlanIdentity(plan_index=0),
        )
    )
    operation = service.begin_owned_operation(command)
    results: list[CommandResult] = []
    worker = Thread(
        target=lambda: results.append(
            service.execute(command, operation_id=operation.operation_id)
        ),
        name="model-summary-construction-lock-boundary",
    )
    worker.start()
    try:
        assert constructor_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
        acquired = service._command_lock.acquire(False)
        if acquired:
            service._command_lock.release()
        assert acquired is True
    finally:
        release_constructor.set()
        worker.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not worker.is_alive()
    assert len(results) == 1
    assert results[0].ok
    assert results[0].diagnostics["model_summary"]["text"] == "Summary"


def test_evaluation_query_fails_when_training_generation_changes_mid_read() -> None:
    service = ApplicationService(Study())
    run = MagicMock()
    run.is_finished.return_value = True
    run.class_weighting = _off_class_weighting()
    plan = MagicMock()
    plan.get_name.return_value = "Plan A"
    plan.get_plans.return_value = [run]
    trainer = Trainer([])
    trainer.get_training_plan_holders = MagicMock(return_value=[plan])
    service.study.training_manager.trainer = trainer

    original_handle_evaluate = service.analysis.handle_evaluate

    def mutate_training_while_reading(command: Any) -> Any:
        summary = original_handle_evaluate(command)
        trainer.set_interrupt()
        trainer.clear_interrupt()
        return summary

    service._command_handlers[CommandName.EVALUATE] = MagicMock(
        side_effect=mutate_training_while_reading
    )

    result = service.execute(EvaluateCommand())

    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.recoverable is True
    assert result.diagnostics["training_state_changed"] is True


def test_evaluation_catalog_keeps_the_generation_read_under_command_lock() -> None:
    """A later mutation must not relabel an older Evaluation catalog."""
    service = ApplicationService(Study())
    run = MagicMock()
    run.is_finished.return_value = True
    run.get_name.return_value = "Repeat-0"
    run.eval_record.evaluation_split = "test"
    run.class_weighting = _off_class_weighting()
    plan = MagicMock()
    plan.get_name.return_value = "Old plan"
    plan.get_plans.return_value = [run]
    trainer = Trainer([])
    trainer.get_training_plan_holders = MagicMock(return_value=[plan])
    service.study.training_manager.trainer = trainer
    service.training_runtime.training_plan_holders = MagicMock(return_value=(plan,))

    command_lock_released = Event()
    allow_evaluate_to_return = Event()
    original_lock = service._command_lock
    lock_depths: dict[object, int] = {}

    class _ReleaseBarrierLock:
        def acquire(self, *args: Any, **kwargs: Any) -> bool:
            acquired = original_lock.acquire(*args, **kwargs)
            if acquired:
                thread = current_thread()
                lock_depths[thread] = lock_depths.get(thread, 0) + 1
            return acquired

        def release(self) -> None:
            thread = current_thread()
            depth = lock_depths.get(thread, 0)
            assert depth > 0
            if depth == 1:
                del lock_depths[thread]
            else:
                lock_depths[thread] = depth - 1
            original_lock.release()
            if (
                depth == 1
                and thread.name.startswith("ThreadPoolExecutor")
                and not command_lock_released.is_set()
            ):
                command_lock_released.set()
                assert allow_evaluate_to_return.wait(timeout=5)

        def __enter__(self) -> _ReleaseBarrierLock:
            self.acquire()
            return self

        def __exit__(self, *_args: Any) -> None:
            self.release()

    service._command_lock = _ReleaseBarrierLock()
    before_generation = service.get_view_publication().generation

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(service.execute, EvaluateCommand())
        assert command_lock_released.wait(timeout=5)
        clear_result = service.execute(ClearTrainingHistoryCommand(confirmed=True))
        after_generation = service.get_view_publication().generation
        allow_evaluate_to_return.set()
        evaluate_result = future.result(timeout=5)

    assert clear_result.ok is True
    assert after_generation > before_generation
    assert evaluate_result.ok is True
    assert evaluate_result.diagnostics["plans"][0]["name"] == "Old plan"
    catalog_generation = evaluate_result.diagnostics[
        "evaluation_publication_generation"
    ]
    assert before_generation <= catalog_generation < after_generation


def test_training_history_query_fails_when_generation_changes_mid_read() -> None:
    service = ApplicationService(Study())
    trainer = Trainer([])
    service.study.training_manager.trainer = trainer

    def mutate_training_while_reading() -> list[dict[str, Any]]:
        trainer.set_interrupt()
        trainer.clear_interrupt()
        return []

    service.training_state.get_formatted_history = mutate_training_while_reading

    result = service.execute(QueryStateCommand(query="training_history"))

    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.recoverable is True
    assert result.diagnostics["training_state_changed"] is True


def test_visualize_and_saliency_commands_return_typed_query_payloads():
    service = ApplicationService(Study())
    service.study.data_manager.epoch_data = MagicMock()
    service.study.training_manager.model_holder = ModelHolder(
        type("EEGNet", (), {}),
        {},
    )
    service.study.training_manager.set_training_option(_valid_training_option())

    visualize = service.execute(VisualizeCommand(view="summary"))
    saliency = service.execute(SaliencyCommand())

    assert visualize.ok is True
    assert visualize.command_name == "visualize"
    assert visualize.diagnostics["payload_type"] == "visualization_summary"
    assert visualize.diagnostics["visualization_publication_generation"] == (
        service.get_view_publication().generation
    )
    assert visualize.diagnostics["available"] is True
    assert "available_views" in visualize.diagnostics
    assert saliency.ok is True
    assert saliency.command_name == "saliency"
    assert saliency.diagnostics["payload_type"] == "saliency_summary"
    assert saliency.diagnostics["action"] == "query"
    assert saliency.diagnostics["saliency_configured"] is False


def test_visualize_query_fails_when_training_generation_changes_mid_read() -> None:
    service = ApplicationService(Study())
    service.study.data_manager.epoch_data = MagicMock()
    service.study.training_manager.model_holder = ModelHolder(
        type("EEGNet", (), {}),
        {},
    )
    service.study.training_manager.set_training_option(_valid_training_option())
    trainer = Trainer([])
    service.study.training_manager.trainer = trainer

    original_handle_visualize = service.analysis.handle_visualize

    def mutate_training_while_reading(command: Any) -> Any:
        summary = original_handle_visualize(command)
        trainer.set_interrupt()
        trainer.clear_interrupt()
        return summary

    service._command_handlers[CommandName.VISUALIZE] = MagicMock(
        side_effect=mutate_training_while_reading
    )

    result = service.execute(VisualizeCommand(view="summary"))

    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.recoverable is True
    assert result.diagnostics["training_state_changed"] is True


def test_saliency_command_can_configure_params():
    service = ApplicationService(Study())
    service.study.training_manager.model_holder = ModelHolder(
        type("EEGNet", (), {}),
        {},
    )
    service.study.training_manager.set_training_option(_valid_training_option())

    result = service.execute(SaliencyCommand(params={"method": "Gradient"}))

    assert result.ok is True
    assert result.changed_state.visualization_changed is True
    assert result.diagnostics["action"] == "configure"
    assert result.diagnostics["saliency_configured"] is True
    assert result.diagnostics["saliency_available"] is False
    params = result.diagnostics["params"]
    assert params["_methods"] == ["Gradient"]
    assert {"SmoothGrad", "SmoothGrad_Squared", "VarGrad"}.issubset(params)


def test_manual_saliency_configuration_retries_failed_batched_view_delivery() -> None:
    service = ApplicationService(Study())
    service.study.training_manager.model_holder = ModelHolder(
        type("EEGNet", (), {}),
        {},
    )
    service.study.training_manager.set_training_option(_valid_training_option())
    attempts = 0

    def fail_once() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient visualization observer failure")

    service.visualization.subscribe("saliency_changed", fail_once)

    result = service.execute(SaliencyCommand(params={"method": "Gradient"}))

    assert result.ok is True
    assert attempts == 2


def test_manual_saliency_configuration_reports_persistent_view_delivery_failure() -> (
    None
):
    service = ApplicationService(Study())
    service.study.training_manager.model_holder = ModelHolder(
        type("EEGNet", (), {}),
        {},
    )
    service.study.training_manager.set_training_option(_valid_training_option())
    attempts = 0

    def always_fail() -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("persistent visualization observer failure")

    service.visualization.subscribe("saliency_changed", always_fail)

    result = service.execute(SaliencyCommand(params={"method": "Gradient"}))

    assert result.ok is True
    assert attempts == 2
    assert result.diagnostics["view_notification_retry_attempted"] is True
    assert result.diagnostics["view_notification_delivered"] is False
    assert "rejected both delivery attempts" in result.diagnostics["view_refresh_error"]


def test_concurrent_manual_saliency_commands_own_their_observer_acknowledgements(
    monkeypatch,
) -> None:
    """A waiting command must not join or erase another command's view batch."""
    service = ApplicationService(Study())
    service.study.training_manager.model_holder = ModelHolder(
        type("EEGNet", (), {}),
        {},
    )
    service.study.training_manager.set_training_option(_valid_training_option())
    first_in_handler = Event()
    release_first = Event()
    second_batch_entered = Event()
    batch_entry_count = 0
    batch_entry_lock = Lock()
    original_batch = service.visualization.batch_notifications
    original_set = service.study.training_manager.set_saliency_params
    observer_attempts: dict[str, int] = {}
    results: dict[str, CommandResult] = {}
    failures: list[BaseException] = []

    @contextmanager
    def tracked_batch():
        nonlocal batch_entry_count
        with original_batch():
            with batch_entry_lock:
                batch_entry_count += 1
                entry = batch_entry_count
            if entry == 2:
                second_batch_entered.set()
            yield

    def controlled_set(params):
        if current_thread().name == "saliency-first":
            first_in_handler.set()
            assert release_first.wait(timeout=THREAD_WATCHDOG_SECONDS)
        return original_set(params)

    def fail_first_delivery_per_thread() -> None:
        thread_name = current_thread().name
        observer_attempts[thread_name] = observer_attempts.get(thread_name, 0) + 1
        if thread_name == "saliency-first" and observer_attempts[thread_name] == 1:
            raise RuntimeError("transient first-command observer failure")

    def execute_saliency(name: str) -> None:
        try:
            results[name] = service.execute(
                SaliencyCommand(params={"method": "Gradient"})
            )
        except BaseException as exc:  # pragma: no cover - asserted below
            failures.append(exc)

    monkeypatch.setattr(service.visualization, "batch_notifications", tracked_batch)
    monkeypatch.setattr(
        service.study.training_manager,
        "set_saliency_params",
        controlled_set,
    )
    service.visualization.subscribe("saliency_changed", fail_first_delivery_per_thread)
    first = Thread(
        target=execute_saliency,
        args=("first",),
        name="saliency-first",
    )
    second = Thread(
        target=execute_saliency,
        args=("second",),
        name="saliency-second",
    )

    first.start()
    assert first_in_handler.wait(timeout=THREAD_WATCHDOG_SECONDS)
    second.start()
    assert second_batch_entered.wait(timeout=THREAD_WATCHDOG_SECONDS)
    release_first.set()
    first.join(timeout=THREAD_WATCHDOG_SECONDS)
    second.join(timeout=THREAD_WATCHDOG_SECONDS)

    assert not first.is_alive()
    assert not second.is_alive()
    assert failures == []
    assert results["first"].ok is True
    assert results["second"].ok is True
    assert results["first"].diagnostics["view_notification_retry_attempted"] is True
    assert results["first"].diagnostics["view_notification_delivered"] is True
    assert "view_notification_retry_attempted" not in results["second"].diagnostics
    assert observer_attempts == {"saliency-first": 2, "saliency-second": 1}


def test_saliency_schedule_rejection_is_a_failed_command_result() -> None:
    service = ApplicationService(Study())
    service.study.training_manager.model_holder = ModelHolder(
        type("EEGNet", (), {}),
        {},
    )
    service.study.training_manager.set_training_option(_valid_training_option())
    target = PostTrainingSaliencyTarget(
        run=TrainingRunIdentity(trainer_id="retired-trainer", run_id=1),
        finished_runs_after=1,
    )

    with post_training_saliency_target(target):
        result = service.execute(
            SaliencyCommand(
                method="Gradient",
                params={
                    "profile": "recommended",
                    "methods": ["Gradient", "Gradient * Input"],
                },
            )
        )

    schedule = target.schedule_outcome
    assert schedule is not None
    assert result.failed is True
    assert result.error_type is ErrorType.PRECONDITION
    assert result.recoverable is True
    assert schedule.disposition is PostTrainingSaliencyScheduleDisposition.STALE
    assert schedule.reason is PostTrainingSaliencyScheduleReason.TRAINER_UNAVAILABLE
    assert schedule.status.phase is PostTrainingSaliencyPhase.CANCELLED
    assert result.message == schedule.message == schedule.status.message
    assert result.diagnostics["post_training_saliency_schedule"] == (schedule.to_dict())
    assert (
        service.study.training_manager.get_post_training_saliency_status()
        == schedule.status
    )


def _saliency_recompute_service() -> tuple[
    ApplicationService,
    Trainer,
    TrainingPlanHolder,
    TrainRecord,
    object,
]:
    service = ApplicationService(Study())
    old_eval_record = object()
    option = _valid_training_option(batch_size=1)
    model_holder = ModelHolder(type("EEGNet", (), {}), {})
    epoch_data = _positive_epoch_data()
    sample_count = len(epoch_data.get_label_list())
    dataset = SimpleNamespace(
        get_name=lambda: "saliency-dataset",
        get_epoch_data=lambda: epoch_data,
        get_test_len=lambda: sample_count,
        get_val_len=lambda: 0,
        train_mask=np.ones(sample_count, dtype=bool),
        val_mask=np.zeros(sample_count, dtype=bool),
        test_mask=np.ones(sample_count, dtype=bool),
    )
    record = object.__new__(TrainRecord)
    record._state_tracker = None
    record.epoch = option.epoch
    record.option = cast(Any, option)
    record.eval_record = cast(Any, old_eval_record)
    record.model = torch.nn.Linear(1, 1, bias=False)
    record.repeat = 0
    record.seed = 7
    record.plan_id = "saliency-plan"
    record.model_identity = model_holder.catalog_identity
    record.class_weighting = _off_class_weighting()

    holder = object.__new__(TrainingPlanHolder)
    holder.model_holder = cast(Any, model_holder)
    holder.dataset = cast(Any, dataset)
    holder.option = cast(Any, option)
    holder.plan_id = "saliency-plan"
    holder.saliency_params = {"Gradient": {}}
    holder.train_record_list = [record]
    holder._state_tracker = None
    holder._interrupt = Event()
    holder.error = None
    holder.status = "Done"
    test_loader = object()
    holder.get_loader = MagicMock(return_value=(None, None, test_loader))
    holder.get_eval_pair = MagicMock(return_value=(object(), test_loader))

    trainer = Trainer([holder])
    service.study.training_manager.model_holder = model_holder
    service.study.training_manager.set_training_option(option)
    service.study.training_manager.trainer = trainer
    service.study.training_manager.saliency_params = holder.saliency_params
    return service, trainer, holder, record, old_eval_record


def test_explicit_saliency_compute_runs_outside_shared_command_lock() -> None:
    service, trainer, _holder, _record, _old_eval_record = _saliency_recompute_service()
    run = TrainingRunIdentity(
        trainer_id=trainer.get_state_snapshot_identity(),
        run_id=1,
    )
    trainer._terminal_outcome = TrainingTerminalOutcome(
        state=TrainingOutcomeState.COMPLETED,
        run=run,
    )
    compute_started = Event()
    release_compute = Event()
    replacement = MagicMock()

    def evaluate(*_args, **_kwargs):
        compute_started.set()
        assert release_compute.wait(timeout=THREAD_WATCHDOG_SECONDS)
        return replacement

    with patch.object(Evaluator, "evaluate_with_saliency", side_effect=evaluate):
        result = service.execute(
            SaliencyCommand(
                method="Gradient",
                params={
                    "profile": "recommended",
                    "methods": ["Gradient", "Gradient * Input"],
                },
            )
        )

        assert result.ok is True
        assert result.diagnostics["action"] == "schedule"
        assert compute_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
        assert service._command_lock.acquire(blocking=False)
        service._command_lock.release()
        release_compute.set()
        assert service.wait_for_background_tasks(timeout=THREAD_WATCHDOG_SECONDS)

    assert service.training_runtime.saliency_status().phase is (
        PostTrainingSaliencyPhase.SUCCEEDED
    )


@pytest.mark.parametrize("bulk", [False, True])
def test_explicit_saliency_operation_cancel_is_immediate_and_terminal(bulk) -> None:
    service, trainer, _holder, record, old_eval_record = _saliency_recompute_service()
    run = TrainingRunIdentity(
        trainer_id=trainer.get_state_snapshot_identity(),
        run_id=1,
    )
    trainer._terminal_outcome = TrainingTerminalOutcome(
        state=TrainingOutcomeState.COMPLETED,
        run=run,
    )
    compute_started = Event()
    release_compute = Event()
    compute_finished = Event()
    cancel_returned = Event()
    cancel_results = []
    cancel_errors = []
    command = SaliencyCommand(
        method="Gradient",
        params={
            "profile": "recommended",
            "methods": ["Gradient", "Gradient * Input"],
        },
    )
    operation = service.begin_owned_operation(command)

    def evaluate(*_args, **_kwargs):
        compute_started.set()
        try:
            assert release_compute.wait(timeout=THREAD_WATCHDOG_SECONDS)
            return MagicMock()
        finally:
            compute_finished.set()

    def cancel():
        try:
            cancel_results.append(
                operation.operation_id in service.cancel_all_owned_operations()
                if bulk
                else service.cancel_owned_operation(operation.operation_id)
            )
        except BaseException as exc:
            cancel_errors.append(exc)
        finally:
            cancel_returned.set()

    with patch.object(Evaluator, "evaluate_with_saliency", side_effect=evaluate):
        cancel_thread = Thread(target=cancel)
        try:
            result = service.execute(command, operation_id=operation.operation_id)
            assert result.ok is True
            assert result.diagnostics["operation_phase"] == "running"
            assert compute_started.wait(timeout=THREAD_WATCHDOG_SECONDS)
            cancel_thread.start()
            assert cancel_returned.wait(timeout=THREAD_WATCHDOG_SECONDS)
            assert cancel_errors == []
            assert cancel_results == [True]
            assert not release_compute.is_set()
            assert not compute_finished.is_set()
            snapshot = service.get_owned_operation(operation.operation_id)
            assert snapshot.phase is OwnedWorkPhase.CANCELLING
            assert snapshot.cancel_requested is True
        finally:
            release_compute.set()
            if cancel_thread.ident is not None:
                cancel_thread.join(timeout=THREAD_WATCHDOG_SECONDS)
            assert not cancel_thread.is_alive()
            assert service.wait_for_background_tasks(timeout=THREAD_WATCHDOG_SECONDS)
            assert service.owned_work.wait_for_idle(timeout=THREAD_WATCHDOG_SECONDS)

    assert service.get_owned_operation(operation.operation_id).phase is (
        OwnedWorkPhase.CANCELLED
    )
    assert record.eval_record is old_eval_record


def test_saliency_configuration_is_blocked_while_training_but_query_remains_usable():
    study = Study()
    service = ApplicationService(study)
    plan = _RecoveryBlockingPlan()
    trainer = Trainer([cast(TrainingPlanHolder, plan)])
    study.training_manager.trainer = trainer
    trainer.run(interact=True)
    assert plan.started.wait(timeout=THREAD_WATCHDOG_SECONDS)
    service.get_state()

    try:
        policy = service.get_capabilities().get(CommandName.SALIENCY)
        configured = service.execute(SaliencyCommand(method="Gradient"))
        queried = service.execute(SaliencyCommand())
    finally:
        trainer.stop(wait_timeout=THREAD_WATCHDOG_SECONDS)

    assert policy.available is False
    assert policy.reasons == [TRAINING_ACTIVE_SALIENCY_REASON]
    assert configured.failed is True
    assert configured.error_type == ErrorType.PRECONDITION
    assert configured.recoverable is True
    assert configured.message == TRAINING_ACTIVE_SALIENCY_REASON
    assert study.training_manager.saliency_params is None
    assert queried.ok is True
    assert queried.diagnostics["action"] == "query"
    assert queried.diagnostics["configure_available"] is False
    assert queried.diagnostics["configure_reasons"] == [TRAINING_ACTIVE_SALIENCY_REASON]


@pytest.mark.parametrize(
    "tracked_change",
    [True, False],
    ids=["tracked-generation-and-identity", "identity-only"],
)
def test_saliency_stale_prepare_returns_retryable_precondition_without_commit(
    tracked_change: bool,
):
    service, trainer, holder, record, old_eval_record = _saliency_recompute_service()
    manager = service.study.training_manager
    old_manager_params = manager.saliency_params
    old_holder_params = holder.saliency_params
    newer_eval_record = object()
    prepared_eval_record = object()
    generation_after_race: list[int] = []
    generation_before = trainer.get_state_generation()

    def mutate_after_prepare_started(*_args, **_kwargs):
        if tracked_change:
            record.set_eval_record(cast(Any, newer_eval_record))
        else:
            record.eval_record = cast(Any, newer_eval_record)
        generation_after_race.append(trainer.get_state_generation())
        return prepared_eval_record

    with patch.object(
        Evaluator,
        "evaluate_with_saliency",
        side_effect=mutate_after_prepare_started,
    ):
        result = service.execute(SaliencyCommand(method="Gradient"))

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert result.recoverable is True
    assert result.message == STALE_SALIENCY_MESSAGE
    assert result.diagnostics["retryable"] is True
    assert result.diagnostics["stale_saliency_update"] is True
    assert result.diagnostics["state_preserved"] is True
    assert result.changed_state.error_changed is True
    assert result.changed_state.evaluation_changed is False
    assert result.changed_state.visualization_changed is False
    assert manager.saliency_params is old_manager_params
    assert holder.saliency_params is old_holder_params
    assert record.eval_record is newer_eval_record
    assert record.eval_record is not old_eval_record
    assert record.eval_record is not prepared_eval_record
    assert trainer.get_state_generation() == generation_after_race[0]
    assert generation_after_race[0] == generation_before + (2 if tracked_change else 0)


def test_saliency_compute_error_without_state_change_remains_internal() -> None:
    service, trainer, holder, record, old_eval_record = _saliency_recompute_service()
    manager = service.study.training_manager
    old_manager_params = manager.saliency_params
    old_holder_params = holder.saliency_params
    generation_before = trainer.get_state_generation()

    with patch.object(
        Evaluator,
        "evaluate_with_saliency",
        side_effect=RuntimeError("saliency kernel failed"),
    ):
        result = service.execute(SaliencyCommand(method="Gradient"))

    assert result.failed is True
    assert result.error_type == ErrorType.INTERNAL
    assert result.recoverable is False
    assert result.message == "saliency kernel failed"
    assert result.diagnostics["exception_type"] == "RuntimeError"
    assert "stale_saliency_update" not in result.diagnostics
    assert manager.saliency_params is old_manager_params
    assert holder.saliency_params is old_holder_params
    assert record.eval_record is old_eval_record
    assert trainer.get_state_generation() == generation_before


def test_saliency_identity_change_without_compute_target_does_not_commit() -> None:
    service, trainer, holder, record, old_eval_record = _saliency_recompute_service()
    manager = service.study.training_manager
    old_manager_params = manager.saliency_params
    old_holder_params = holder.saliency_params
    newer_eval_record = object()
    generation_before = trainer.get_state_generation()

    def invalidate_record_before_target(*_args, **_kwargs):
        record.eval_record = cast(Any, newer_eval_record)
        return None, None

    holder.get_eval_pair = MagicMock(side_effect=invalidate_record_before_target)

    result = service.execute(SaliencyCommand(method="Gradient"))

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert result.recoverable is True
    assert result.message == STALE_SALIENCY_MESSAGE
    assert result.diagnostics["stale_saliency_update"] is True
    assert result.diagnostics["state_preserved"] is True
    assert manager.saliency_params is old_manager_params
    assert holder.saliency_params is old_holder_params
    assert record.eval_record is newer_eval_record
    assert record.eval_record is not old_eval_record
    assert trainer.get_state_generation() == generation_before


def test_saliency_identity_change_at_publish_boundary_does_not_commit() -> None:
    service, trainer, holder, record, old_eval_record = _saliency_recompute_service()
    manager = service.study.training_manager
    old_manager_params = manager.saliency_params
    old_holder_params = holder.saliency_params
    newer_eval_record = object()
    prepared_eval_record = MagicMock()
    generation_before = trainer.get_state_generation()

    class MutateIdentityOnEnter:
        def __enter__(self) -> bool:
            record.eval_record = cast(Any, newer_eval_record)
            return True

        def __exit__(self, *_args: object) -> None:
            return None

    with (
        patch.object(
            Evaluator,
            "evaluate_with_saliency",
            return_value=prepared_eval_record,
        ),
        patch.object(
            trainer._state_tracker,
            "mutation_if_current",
            return_value=MutateIdentityOnEnter(),
        ),
    ):
        result = service.execute(SaliencyCommand(method="Gradient"))

    assert result.failed is True
    assert result.error_type == ErrorType.PRECONDITION
    assert result.recoverable is True
    assert result.message == STALE_SALIENCY_MESSAGE
    assert result.diagnostics["stale_saliency_update"] is True
    assert result.diagnostics["state_preserved"] is True
    assert manager.saliency_params is old_manager_params
    assert holder.saliency_params is old_holder_params
    assert record.eval_record is newer_eval_record
    assert record.eval_record is not old_eval_record
    assert record.eval_record is not prepared_eval_record
    assert trainer.get_state_generation() == generation_before


def test_saliency_oom_returns_recoverable_visualization_error_and_releases_cache():
    service, trainer, holder, record, old_eval_record = _saliency_recompute_service()
    manager = service.study.training_manager
    old_manager_params = manager.saliency_params
    old_holder_params = holder.saliency_params
    generation_before = trainer.get_state_generation()
    oom = torch.cuda.OutOfMemoryError("CUDA out of memory in saliency")

    with (
        patch.object(Evaluator, "evaluate_with_saliency", side_effect=oom),
        patch("XBrainLab.backend.training_manager.release_cuda_cache") as release_cache,
    ):
        result = service.execute(SaliencyCommand(method="Gradient"))

    assert result.failed is True
    assert result.error_type == ErrorType.VISUALIZATION
    assert result.recoverable is True
    assert result.message == SALIENCY_OOM_MESSAGE
    assert result.diagnostics["retryable"] is True
    assert result.diagnostics["resource"] == "cuda_memory"
    assert result.diagnostics["operation"] == "saliency_recomputation"
    assert result.diagnostics["state_preserved"] is True
    assert result.changed_state.error_changed is True
    assert result.changed_state.evaluation_changed is False
    assert result.changed_state.visualization_changed is False
    release_cache.assert_called_once_with(torch)
    assert manager.saliency_params is old_manager_params
    assert holder.saliency_params is old_holder_params
    assert record.eval_record is old_eval_record
    assert trainer.get_state_generation() == generation_before


def test_oversized_saliency_is_rejected_before_evaluator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _trainer, holder, _record, _old_eval_record = _saliency_recompute_service()
    epoch_count = 64
    shape_only_data = SimpleNamespace(
        shape=(epoch_count, 128, 4096),
        nbytes=epoch_count * 128 * 4096 * 4,
    )
    shape_only_epoch = SimpleNamespace(get_data=lambda: shape_only_data)
    holder.dataset = cast(
        Any,
        SimpleNamespace(
            get_epoch_data=lambda: shape_only_epoch,
            get_test_len=lambda: epoch_count,
            get_val_len=lambda: 0,
            train_mask=np.zeros(epoch_count, dtype=bool),
            val_mask=np.zeros(epoch_count, dtype=bool),
            test_mask=np.ones(epoch_count, dtype=bool),
        ),
    )
    monkeypatch.setattr(
        ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 2 * 1024**3,
                "total_bytes": 4 * 1024**3,
                "used_bytes": 2 * 1024**3,
            }
        ),
    )

    with patch.object(
        Evaluator,
        "evaluate_with_saliency",
        side_effect=AssertionError("evaluator crossed saliency admission"),
    ) as evaluator:
        result = service.execute(
            SaliencyCommand(
                method="SmoothGrad",
                params={"nt_samples": 512},
            )
        )

    assert result.failed
    assert result.error_type == ErrorType.PRECONDITION
    assert result.recoverable
    assert "saliency" in result.message.lower()
    assert "ram" in result.message.lower()
    assert result.diagnostics["resource_preflight"]["risk_level"] == "blocking"
    evaluator.assert_not_called()


def test_reconfiguring_saliency_marks_visualization_changed() -> None:
    service = ApplicationService(Study())
    service.study.training_manager.model_holder = ModelHolder(
        type("EEGNet", (), {}),
        {},
    )
    service.study.training_manager.set_training_option(_valid_training_option())
    first = service.execute(
        SaliencyCommand(method="SmoothGrad", params={"nt_samples": 2}),
    )

    second = service.execute(
        SaliencyCommand(method="SmoothGrad", params={"nt_samples": 7}),
    )

    assert first.ok is True
    assert second.ok is True
    assert second.changed_state.visualization_changed is True
    assert second.state.visualization.saliency_params["SmoothGrad"]["nt_samples"] == 7


def test_reapplying_montage_with_new_positions_marks_visualization_changed() -> None:
    class EpochWithMontage:
        def __init__(self) -> None:
            self.ch_names = ["C3", "Cz", "C4"]
            self.channel_position = [(-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)]

        def set_channels(
            self,
            channels: list[str],
            positions: list[tuple[float, float, float]],
        ) -> None:
            self.ch_names = list(channels)
            self.channel_position = list(positions)

        def get_channel_names(self) -> list[str]:
            return list(self.ch_names)

        def set_channel_positions(self, positions) -> None:
            self.channel_position = [positions.get(name) for name in self.ch_names]

    service = ApplicationService(Study())
    service.study.data_manager.epoch_data = EpochWithMontage()
    raw = _raw_mock()
    raw.get_mne.return_value.ch_names = ["C3", "Cz", "C4"]
    service.study.data_manager.loaded_data_list = [raw]
    first = service.execute(
        ApplyMontageCommand(
            channels=["C3", "Cz", "C4"],
            positions=[(-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)],
            montage_name="custom-a",
        ),
    )

    second = service.execute(
        ApplyMontageCommand(
            channels=["C3", "Cz", "C4"],
            positions=[(-0.9, 0.0, 0.0), (0.0, 1.1, 0.0), (0.9, 0.0, 0.0)],
            montage_name="custom-b",
        ),
    )

    assert first.ok is True
    assert second.ok is True
    assert second.changed_state.visualization_changed is True
    assert second.state.visualization.montage_channels == ["C3", "Cz", "C4"]
    assert second.state.visualization.montage_positions == [
        [-0.9, 0.0, 0.0],
        [0.0, 1.1, 0.0],
        [0.9, 0.0, 0.0],
    ]


def test_saliency_command_applies_exact_requested_params_to_authoritative_state():
    service = ApplicationService(Study())
    service.study.training_manager.model_holder = ModelHolder(
        type("EEGNet", (), {}),
        {},
    )
    service.study.training_manager.set_training_option(_valid_training_option())

    result = service.execute(
        SaliencyCommand(
            method="SmoothGrad",
            params={
                "nt_samples": 2,
                "nt_samples_batch_size": 1,
                "stdevs": 1.0,
            },
        ),
    )

    assert result.ok is True
    assert result.diagnostics["requested_method"] == "SmoothGrad"
    params = result.diagnostics["params"]
    assert params == result.state.visualization.saliency_params
    assert params["_methods"] == ["SmoothGrad"]
    assert params["SmoothGrad"] == {
        "nt_samples": 2,
        "nt_samples_batch_size": 1,
        "stdevs": 1.0,
    }
    assert params["SmoothGrad_Squared"] == {
        "nt_samples": 5,
        "nt_samples_batch_size": None,
        "stdevs": 1.0,
    }


@pytest.mark.parametrize(
    ("method", "params"),
    [
        ("IntegratedGradients", None),
        ("Gradient", {"nt_samples": 2}),
    ],
)
def test_saliency_command_returns_typed_validation_failure_for_unsupported_request(
    method: str,
    params: dict[str, object] | None,
) -> None:
    service = ApplicationService(Study())
    service.study.training_manager.model_holder = ModelHolder(
        type("EEGNet", (), {}),
        {},
    )
    service.study.training_manager.set_training_option(_valid_training_option())

    result = service.execute(SaliencyCommand(method=method, params=params))

    assert result.failed is True
    assert result.error_type == ErrorType.VALIDATION
    assert result.state.visualization.saliency_configured is False
    assert result.state.visualization.saliency_params == {}


def test_evaluate_and_clear_history_block_when_trainer_has_no_plan_history():
    service = ApplicationService(Study())
    trainer = Trainer([])
    service.study.training_manager.trainer = trainer

    policy = service.get_capabilities()
    evaluate = service.execute(EvaluateCommand())
    clear_history = service.execute(ClearTrainingHistoryCommand(confirmed=True))

    assert policy.get(CommandName.EVALUATE).available is False
    assert policy.get(CommandName.CLEAR_TRAINING_HISTORY).available is False
    assert evaluate.failed is True
    assert evaluate.error_type == ErrorType.PRECONDITION
    assert clear_history.failed is True
    assert clear_history.error_type == ErrorType.PRECONDITION


def test_evaluate_is_blocked_until_a_training_run_has_finished() -> None:
    state = replace(
        ApplicationStateSnapshot.empty(),
        pipeline_stage="dataset_ready",
        evaluation=EvaluationStateSnapshot(
            available=False,
            total_plans=1,
            total_runs=1,
            finished_runs=0,
        ),
        active_training=ActiveTrainingSnapshot(has_trainer=True),
    )

    capability = build_capability_policy(state).get(CommandName.EVALUATE)

    assert capability.available is False
    assert capability.reasons == [
        "Complete at least one training run before evaluating results."
    ]


def test_existing_finished_results_remain_evaluable_after_a_later_failure() -> None:
    state = replace(
        ApplicationStateSnapshot.empty(),
        pipeline_stage="trained",
        evaluation=EvaluationStateSnapshot(
            available=True,
            total_plans=2,
            total_runs=2,
            finished_runs=1,
            metrics_available=True,
        ),
        training=TrainingStateSnapshot(
            has_trainer=True,
            finished_run_count=1,
            terminal_outcome=TrainingTerminalOutcome(
                state=TrainingOutcomeState.FAILED,
                detail="later run failed",
            ),
        ),
        active_training=ActiveTrainingSnapshot(has_trainer=True),
    )

    capability = build_capability_policy(state).get(CommandName.EVALUATE)

    assert capability.available is True
