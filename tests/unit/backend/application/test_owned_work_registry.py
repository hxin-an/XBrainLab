from __future__ import annotations

import ast
import inspect
import textwrap
from threading import Event, Thread
from time import monotonic

import pytest

from XBrainLab.backend.application.commands import (
    ApplyInterpretationCommand,
    EvaluateCommand,
    LoadDataCommand,
    PreprocessCommand,
    PreprocessOperation,
    ReviewInterpretationCommand,
    SaliencyCommand,
    ScanSourceCommand,
    StopTrainingCommand,
    TrainCommand,
)
from XBrainLab.backend.application.data_interpretation_service import (
    DataInterpretationCommandService,
)
from XBrainLab.backend.application.owned_work import (
    OwnedOperationCancelledError,
    OwnedOperationClaimError,
    OwnedWorkKind,
    OwnedWorkPhase,
    OwnedWorkRegistry,
    owned_work_checkpoint,
    owned_work_commit_boundary,
)
from XBrainLab.backend.application.results import ChangedState, CommandResult, ErrorType
from XBrainLab.backend.application.service import ApplicationService
from XBrainLab.backend.services.dataset_state_service import DatasetStateService
from XBrainLab.backend.study import Study
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    PostTrainingSaliencyStatus,
    TrainingOutcomeState,
    TrainingRunIdentity,
    TrainingTerminalOutcome,
)

_THREAD_WATCHDOG_SECONDS = 5.0


def test_owned_work_registry_publishes_identity_progress_and_terminal_state() -> None:
    registry = OwnedWorkRegistry()

    operation = registry.begin(OwnedWorkKind.IMPORT_REVIEW, cancellable=True)
    running = registry.start(operation.operation_id)
    updated = registry.update(
        operation.operation_id,
        stage="Scanning BIDS recordings",
        completed=2,
        total=5,
    )
    completed = registry.complete(operation.operation_id)

    assert operation.operation_id
    assert running.phase is OwnedWorkPhase.RUNNING
    assert updated.stage == "Scanning BIDS recordings"
    assert updated.completed == 2
    assert updated.total == 5
    assert updated.indeterminate is False
    assert completed.phase is OwnedWorkPhase.COMPLETED
    assert registry.wait_for_idle(timeout=0.0)


def test_apply_is_the_exact_cancellable_import_materialization_operation() -> None:
    service = ApplicationService(Study())

    apply_operation = service.begin_owned_operation(
        ApplyInterpretationCommand(confirmed=True)
    )
    compatibility_load = service.begin_owned_operation(LoadDataCommand(paths=[]))

    assert apply_operation.kind is OwnedWorkKind.IMPORT_APPLY
    assert apply_operation.cancellable is True
    assert compatibility_load.kind is OwnedWorkKind.COMMAND
    assert compatibility_load.cancellable is False


def test_apply_materialization_source_keeps_checkpoints_and_final_admission() -> None:
    dataset_tree = ast.parse(
        textwrap.dedent(inspect.getsource(DatasetStateService.import_files))
    )
    import_calls = [
        node for node in ast.walk(dataset_tree) if isinstance(node, ast.Call)
    ]
    load_call = next(
        node
        for node in import_calls
        if isinstance(node.func, ast.Attribute) and node.func.attr == "load"
    )
    materialize_call = next(
        node
        for node in import_calls
        if isinstance(node.func, ast.Attribute) and node.func.attr == "apply"
    )
    import_checkpoint_lines = [
        node.lineno
        for node in import_calls
        if isinstance(node.func, ast.Name) and node.func.id == "owned_work_checkpoint"
    ]

    assert any(line < load_call.lineno for line in import_checkpoint_lines)
    assert any(
        load_call.lineno < line < materialize_call.lineno
        for line in import_checkpoint_lines
    )
    assert any(line > materialize_call.lineno for line in import_checkpoint_lines)

    apply_tree = ast.parse(
        textwrap.dedent(
            inspect.getsource(
                DataInterpretationCommandService.handle_apply_interpretation
            )
        )
    )
    apply_calls = [node for node in ast.walk(apply_tree) if isinstance(node, ast.Call)]
    checkpoint_stages = {
        str(node.args[0].value)
        for node in apply_calls
        if isinstance(node.func, ast.Name)
        and node.func.id == "owned_work_checkpoint"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    }
    assert {
        "Loading reviewed EEG recordings",
        "Binding reviewed source identity",
        "Applying reviewed channel metadata",
        "Recording interpreted dataset state",
        "Applying reviewed recording metadata",
        "Applying reviewed label carriers",
        "Recording reviewed epoch hints",
    } <= checkpoint_stages
    commit_admission = next(
        node
        for node in apply_calls
        if isinstance(node.func, ast.Name)
        and node.func.id == "owned_work_commit_boundary"
    )
    label_verification = next(
        node
        for node in apply_calls
        if isinstance(node.func, ast.Attribute)
        and node.func.attr == "_ensure_label_apply_succeeded"
    )
    pipeline_commit = next(
        node
        for node in apply_calls
        if isinstance(node.func, ast.Attribute)
        and node.func.attr == "commit_pipeline_invalidation"
    )
    assert label_verification.lineno < commit_admission.lineno < pipeline_commit.lineno


@pytest.mark.parametrize(
    ("method_name", "first_publish_call"),
    [
        ("handle_scan_source", "_record_prepared_scan"),
        ("handle_review_interpretation", "_record_prepared_review"),
        ("handle_preview_interpretation", "_record_prepared_preview"),
        ("handle_validate_interpretation", "_record_prepared_validation"),
    ],
)
def test_cancellable_interpretation_mutators_close_cancel_before_publication(
    method_name: str,
    first_publish_call: str,
) -> None:
    method = getattr(DataInterpretationCommandService, method_name)
    tree = ast.parse(textwrap.dedent(inspect.getsource(method)))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    commit_lines = [
        node.lineno
        for node in calls
        if isinstance(node.func, ast.Name)
        and node.func.id == "owned_work_commit_boundary"
    ]
    publish_lines = [
        node.lineno
        for node in calls
        if isinstance(node.func, ast.Attribute) and node.func.attr == first_publish_call
    ]

    assert commit_lines
    assert publish_lines
    assert min(commit_lines) < min(publish_lines)


def test_cancellation_is_lock_independent_and_reaches_bound_operation() -> None:
    registry = OwnedWorkRegistry()
    operation = registry.begin(OwnedWorkKind.IMPORT_REVIEW, cancellable=True)
    command_lock_held = Event()
    release_command_lock = Event()
    cancelled = Event()

    def worker() -> None:
        with registry.bind(operation.operation_id):
            registry.start(operation.operation_id)
            command_lock_held.set()
            assert release_command_lock.wait(timeout=2.0)
            with pytest.raises(OwnedOperationCancelledError):
                owned_work_checkpoint("Reading events")
            cancelled.set()

    thread = Thread(target=worker)
    thread.start()
    assert command_lock_held.wait(timeout=1.0)

    assert registry.cancel(operation.operation_id) is True
    snapshot = registry.snapshot(operation.operation_id)
    assert snapshot.cancel_requested is True
    assert snapshot.phase is OwnedWorkPhase.CANCELLING

    release_command_lock.set()
    thread.join(timeout=2.0)
    assert not thread.is_alive()
    assert cancelled.is_set()


def test_non_cancellable_and_terminal_operations_reject_cancel() -> None:
    registry = OwnedWorkRegistry()
    fixed = registry.begin(OwnedWorkKind.TRAINING, cancellable=False)
    done = registry.begin(OwnedWorkKind.EVALUATION, cancellable=True)
    registry.complete(done.operation_id)

    assert registry.cancel(fixed.operation_id) is False
    assert registry.cancel(done.operation_id) is False


def test_commit_boundary_rejects_prior_cancel_and_closes_cancel_admission() -> None:
    registry = OwnedWorkRegistry()
    cancelled = registry.begin(OwnedWorkKind.PREPROCESS, cancellable=True)
    registry.start(cancelled.operation_id)
    assert registry.cancel(cancelled.operation_id) is True

    with (
        pytest.raises(OwnedOperationCancelledError),
        registry.bind(cancelled.operation_id),
    ):
        owned_work_commit_boundary("Publishing preprocessed EEG data")

    admitted = registry.begin(OwnedWorkKind.PREPROCESS, cancellable=True)
    with registry.bind(admitted.operation_id):
        registry.start(admitted.operation_id)
        snapshot = owned_work_commit_boundary("Publishing preprocessed EEG data")

    assert snapshot is not None
    assert snapshot.cancellable is False
    assert registry.cancel(admitted.operation_id) is False


def test_complete_terminalizes_late_cancel_request_as_cancelled() -> None:
    registry = OwnedWorkRegistry()
    operation = registry.begin(OwnedWorkKind.EVALUATION, cancellable=True)
    registry.start(operation.operation_id)

    assert registry.cancel(operation.operation_id) is True
    terminal = registry.complete(operation.operation_id)

    assert terminal.phase is OwnedWorkPhase.CANCELLED
    assert terminal.cancel_requested is True
    assert registry.wait_for_idle(timeout=0.0)


def test_owned_read_result_is_suppressed_when_cancel_wins_before_completion(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    command = EvaluateCommand()
    operation = service.begin_owned_operation(command)
    handler_finished = Event()
    release_completion = Event()
    computed = CommandResult.success_result(
        command_name="evaluate",
        message="Evaluation ready.",
        state=service.get_state(),
        changed_state=ChangedState(),
    )

    def _execute_read(_command, **_kwargs):
        handler_finished.set()
        assert release_completion.wait(timeout=_THREAD_WATCHDOG_SECONDS)
        return computed

    monkeypatch.setattr(service, "_execute_command", _execute_read)
    results: list[CommandResult] = []
    worker = Thread(
        target=lambda: results.append(
            service.execute(command, operation_id=operation.operation_id)
        )
    )

    worker.start()
    assert handler_finished.wait(timeout=_THREAD_WATCHDOG_SECONDS)
    assert service.cancel_owned_operation(operation.operation_id) is True
    release_completion.set()
    worker.join(timeout=_THREAD_WATCHDOG_SECONDS)

    assert not worker.is_alive()
    assert len(results) == 1
    cancelled = results[0]
    assert cancelled.failed
    assert cancelled.error_type is ErrorType.CANCELLED
    assert cancelled.changed_state == ChangedState()
    assert cancelled.diagnostics["operation_cancelled"] is True
    assert cancelled.diagnostics["operation_phase"] == "cancelled"
    assert service.get_owned_operation(operation.operation_id).phase is (
        OwnedWorkPhase.CANCELLED
    )


def test_operation_start_is_a_single_claim_and_terminal_ids_cannot_replay() -> None:
    registry = OwnedWorkRegistry()
    operation = registry.begin(
        OwnedWorkKind.IMPORT_REVIEW,
        cancellable=True,
        command_identity="review_interpretation",
    )

    registry.claim_start(
        operation.operation_id,
        kind=OwnedWorkKind.IMPORT_REVIEW,
        command_identity="review_interpretation",
    )
    with pytest.raises(OwnedOperationClaimError) as duplicate:
        registry.claim_start(
            operation.operation_id,
            kind=OwnedWorkKind.IMPORT_REVIEW,
            command_identity="review_interpretation",
        )
    registry.complete(operation.operation_id)
    with pytest.raises(OwnedOperationClaimError) as terminal:
        registry.claim_start(
            operation.operation_id,
            kind=OwnedWorkKind.IMPORT_REVIEW,
            command_identity="review_interpretation",
        )

    assert duplicate.value.reason == "already_claimed"
    assert terminal.value.reason == "terminal_replay"


@pytest.mark.parametrize(
    ("kind", "command_identity", "expected_reason"),
    [
        (OwnedWorkKind.PREPROCESS, "review_interpretation", "kind_mismatch"),
        (OwnedWorkKind.IMPORT_REVIEW, "scan_source", "command_mismatch"),
    ],
)
def test_mismatched_operation_claim_fails_closed_and_terminalizes_receipt(
    kind: OwnedWorkKind,
    command_identity: str,
    expected_reason: str,
) -> None:
    registry = OwnedWorkRegistry()
    operation = registry.begin(
        OwnedWorkKind.IMPORT_REVIEW,
        cancellable=True,
        command_identity="review_interpretation",
    )

    with pytest.raises(OwnedOperationClaimError) as raised:
        registry.claim_start(
            operation.operation_id,
            kind=kind,
            command_identity=command_identity,
        )

    snapshot = registry.snapshot(operation.operation_id)
    assert raised.value.reason == expected_reason
    assert snapshot.phase is OwnedWorkPhase.FAILED
    assert registry.wait_for_idle(timeout=0.0)


def test_cancel_all_only_marks_active_cancellable_operations() -> None:
    registry = OwnedWorkRegistry()
    cancellable = registry.begin(OwnedWorkKind.IMPORT_APPLY, cancellable=True)
    fixed = registry.begin(OwnedWorkKind.TRAINING, cancellable=False)
    done = registry.begin(OwnedWorkKind.RENDER, cancellable=True)
    registry.complete(done.operation_id)

    assert registry.cancel_all() == (cancellable.operation_id,)
    assert registry.snapshot(cancellable.operation_id).cancel_requested is True
    assert registry.snapshot(fixed.operation_id).cancel_requested is False


def test_operation_failure_and_cancellation_are_distinct_terminal_phases() -> None:
    registry = OwnedWorkRegistry()
    failed = registry.begin(OwnedWorkKind.RENDER, cancellable=True)
    cancelled = registry.begin(OwnedWorkKind.SALIENCY, cancellable=True)

    failed_snapshot = registry.fail(failed.operation_id, message="render failed")
    cancelled_snapshot = registry.finish_cancelled(cancelled.operation_id)

    assert failed_snapshot.phase is OwnedWorkPhase.FAILED
    assert failed_snapshot.message == "render failed"
    assert cancelled_snapshot.phase is OwnedWorkPhase.CANCELLED
    assert registry.active_snapshots() == ()


def test_terminal_receipt_history_is_bounded_without_pruning_active_work() -> None:
    registry = OwnedWorkRegistry()
    active = registry.begin(OwnedWorkKind.TRAINING, cancellable=True)
    completed_ids = []
    for _ in range(300):
        operation = registry.begin(OwnedWorkKind.COMMAND, cancellable=False)
        completed_ids.append(operation.operation_id)
        registry.complete(operation.operation_id)

    with pytest.raises(KeyError):
        registry.snapshot(completed_ids[0])
    assert registry.snapshot(completed_ids[-1]).phase is OwnedWorkPhase.COMPLETED
    assert registry.snapshot(active.operation_id).phase is OwnedWorkPhase.PENDING


def test_application_operation_cancel_does_not_wait_for_command_lock() -> None:
    service = ApplicationService(Study())
    command = ReviewInterpretationCommand(source_path="/unused", source_hint="bids")
    operation = service.begin_owned_operation(command)
    results = []
    worker_started = Event()

    def execute() -> None:
        worker_started.set()
        results.append(service.execute(command, operation_id=operation.operation_id))

    with service._command_lock:
        worker = Thread(target=execute)
        worker.start()
        assert worker_started.wait(timeout=1.0)
        deadline = monotonic() + 1.0
        while (
            service.get_owned_operation(operation.operation_id).phase
            is OwnedWorkPhase.PENDING
            and monotonic() < deadline
        ):
            pass

        started_at = monotonic()
        assert service.cancel_owned_operation(operation.operation_id) is True
        elapsed = monotonic() - started_at

    worker.join(timeout=2.0)
    assert not worker.is_alive()
    assert elapsed < 0.1
    assert len(results) == 1
    assert results[0].failed is True
    assert results[0].error_type is ErrorType.CANCELLED
    assert results[0].diagnostics["operation_id"] == operation.operation_id
    assert (
        service.get_owned_operation(operation.operation_id).phase
        is OwnedWorkPhase.CANCELLED
    )


def test_application_background_idle_includes_owned_command_work() -> None:
    service = ApplicationService(Study())
    operation = service.begin_owned_operation(
        ReviewInterpretationCommand(source_path="/unused", source_hint="bids")
    )

    assert service.wait_for_background_tasks(timeout=0.0) is False

    service.owned_work.complete(operation.operation_id)
    assert service.wait_for_background_tasks(timeout=0.0) is True


def test_application_rejects_terminal_operation_id_replay_before_handler(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    command = ReviewInterpretationCommand(source_path="/unused", source_hint="bids")
    operation = service.begin_owned_operation(command)
    handler_calls: list[object] = []
    successful = CommandResult.success_result(
        command_name="review_interpretation",
        message="Review ready.",
        state=service.get_state(),
        changed_state=ChangedState(interpretation_changed=True),
    )

    def _execute_once(observed, **_kwargs):
        handler_calls.append(observed)
        return successful

    monkeypatch.setattr(service, "_execute_command", _execute_once)

    first = service.execute(command, operation_id=operation.operation_id)
    replay = service.execute(command, operation_id=operation.operation_id)

    assert first.ok
    assert replay.failed
    assert replay.error_type is ErrorType.PRECONDITION
    assert replay.diagnostics["operation_claim_reason"] == "terminal_replay"
    assert replay.diagnostics["state_preserved"] is True
    assert handler_calls == [command]


@pytest.mark.parametrize(
    ("wrong_command", "expected_reason"),
    [
        (
            PreprocessCommand(operation=PreprocessOperation.BANDPASS),
            "kind_mismatch",
        ),
        (ScanSourceCommand(source_path="/unused"), "command_mismatch"),
    ],
)
def test_application_rejects_mismatched_operation_before_handler(
    monkeypatch,
    wrong_command: object,
    expected_reason: str,
) -> None:
    service = ApplicationService(Study())
    scheduled = ReviewInterpretationCommand(
        source_path="/unused",
        source_hint="bids",
    )
    operation = service.begin_owned_operation(scheduled)

    def _unexpected_handler(*_args, **_kwargs):
        raise AssertionError("a mismatched operation reached its command handler")

    monkeypatch.setattr(service, "_execute_command", _unexpected_handler)

    result = service.execute(wrong_command, operation_id=operation.operation_id)

    assert result.failed
    assert result.error_type is ErrorType.PRECONDITION
    assert result.diagnostics["operation_claim_reason"] == expected_reason
    assert result.diagnostics["state_preserved"] is True
    assert service.get_owned_operation(operation.operation_id).phase is (
        OwnedWorkPhase.FAILED
    )
    assert service.wait_for_background_tasks(timeout=0.0)


def test_application_rejects_unknown_operation_id_as_structured_precondition(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    command = ReviewInterpretationCommand(source_path="/unused", source_hint="bids")

    def _unexpected_handler(*_args, **_kwargs):
        raise AssertionError("an unknown operation reached its command handler")

    monkeypatch.setattr(service, "_execute_command", _unexpected_handler)

    result = service.execute(command, operation_id="unknown-operation")

    assert result.failed
    assert result.error_type is ErrorType.PRECONDITION
    assert result.diagnostics["operation_claim_reason"] == "unknown_operation"
    assert result.diagnostics["state_preserved"] is True


def test_stop_training_control_does_not_wait_for_command_lock(monkeypatch) -> None:
    service = ApplicationService(Study())
    lock_held = Event()
    release_lock = Event()

    def hold_command_lock() -> None:
        with service._command_lock:
            lock_held.set()
            assert release_lock.wait(timeout=2.0)

    holder = Thread(target=hold_command_lock)
    holder.start()
    assert lock_held.wait(timeout=1.0)
    monkeypatch.setattr(
        service.training_runtime,
        "stop_training",
        lambda *, wait_timeout=None: False,
    )

    started_at = monotonic()
    result = service.execute(StopTrainingCommand(wait_timeout=0.0))
    elapsed = monotonic() - started_at
    release_lock.set()
    holder.join(timeout=2.0)

    assert result.ok
    assert result.diagnostics["control_path"] == "lock_independent"
    assert elapsed < 0.1


def test_shutdown_fence_cancels_active_owned_work() -> None:
    service = ApplicationService(Study())
    operation = service.begin_owned_operation(
        ReviewInterpretationCommand(source_path="/unused", source_hint="bids")
    )

    service.request_shutdown_fence()

    assert service.get_owned_operation(operation.operation_id).cancel_requested is True


def test_shutdown_fence_terminalizes_owned_saliency_without_delivery_ack(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    command = SaliencyCommand(method="Gradient", params={"profile": "recommended"})
    operation = service.begin_owned_operation(command)
    result = CommandResult.success_result(
        command_name="saliency",
        message="Saliency scheduled.",
        state=service.get_state(),
        changed_state=ChangedState(),
        diagnostics={
            "action": "schedule",
            "post_training_saliency_schedule": {
                "status": {"generation": 9},
            },
        },
    )
    job_finished = Event()
    delivery_wait_calls: list[float | None] = []
    status = PostTrainingSaliencyStatus(
        generation=9,
        phase=PostTrainingSaliencyPhase.CANCELLED,
        run=TrainingRunIdentity(trainer_id="trainer-1", run_id=1),
        training_generation=4,
        methods=("Gradient",),
    )
    monkeypatch.setattr(service, "_execute_command", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(
        service.training_runtime,
        "wait_for_saliency_job",
        lambda *, timeout=None: job_finished.wait(timeout=timeout),
    )
    monkeypatch.setattr(service.training_runtime, "saliency_status", lambda: status)
    monkeypatch.setattr(
        service.training_runtime,
        "wait_for_saliency_delivery",
        lambda *, timeout=None: delivery_wait_calls.append(timeout) or False,
    )
    monkeypatch.setattr(
        service.training_runtime,
        "cancel_saliency_job",
        lambda: job_finished.set(),
    )

    observed = service.execute(command, operation_id=operation.operation_id)
    assert observed.ok
    service.request_shutdown_fence()

    assert service.owned_work.wait_for_idle(timeout=1.0)
    assert service.get_owned_operation(operation.operation_id).phase is (
        OwnedWorkPhase.CANCELLED
    )
    assert delivery_wait_calls == []
    assert service.wait_for_background_tasks(timeout=0.0)


def test_interactive_training_operation_stays_active_until_exact_run_completes(
    monkeypatch,
) -> None:
    service = ApplicationService(Study())
    command = TrainCommand(confirmed=True, interactive=True)
    operation = service.begin_owned_operation(command)
    release_training = Event()
    run = TrainingRunIdentity(trainer_id="trainer-1", run_id=1)
    completed_outcome = TrainingTerminalOutcome(
        state=TrainingOutcomeState.COMPLETED,
        run=run,
    )
    result = CommandResult.success_result(
        command_name="train",
        message="Training started.",
        state=service.get_state(),
        changed_state=ChangedState(training_changed=True),
        diagnostics={
            "training_trainer_identity": "trainer-1",
            "training_handoff_generation": 4,
        },
    )
    monkeypatch.setattr(service, "_execute_command", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(
        service.training_runtime,
        "wait_for_training_completion",
        lambda **_kwargs: release_training.wait(timeout=2.0),
    )
    monkeypatch.setattr(
        service.training_runtime,
        "terminal_outcome",
        lambda: completed_outcome,
    )
    terminal_published = Event()
    release_monitor = Event()
    complete = service.owned_work.complete

    def block_after_complete(operation_id: str):
        completed = complete(operation_id)
        terminal_published.set()
        assert release_monitor.wait(timeout=_THREAD_WATCHDOG_SECONDS)
        return completed

    monkeypatch.setattr(service.owned_work, "complete", block_after_complete)

    observed = service.execute(command, operation_id=operation.operation_id)

    assert observed.ok
    assert (
        service.get_owned_operation(operation.operation_id).phase
        is OwnedWorkPhase.RUNNING
    )
    assert service.wait_for_background_tasks(timeout=0.0) is False
    release_training.set()
    assert terminal_published.wait(timeout=_THREAD_WATCHDOG_SECONDS)
    assert (
        service.get_owned_operation(operation.operation_id).phase
        is OwnedWorkPhase.COMPLETED
    )
    assert service.wait_for_background_tasks(timeout=0.0) is False
    with service._training_operation_lock:
        monitor = service._training_operation_threads[operation.operation_id]
    assert monitor.is_alive()
    release_monitor.set()
    assert service._wait_for_owned_operation_monitors(timeout=1.0)
    assert not monitor.is_alive()
    with service._training_operation_lock:
        assert operation.operation_id not in service._training_operation_threads


def test_owned_saliency_monitor_rejects_mismatched_terminal_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ApplicationService(Study())
    command = SaliencyCommand(method="Gradient", params={"profile": "recommended"})
    operation = service.begin_owned_operation(command)
    scheduled_generation = 9
    result = CommandResult.success_result(
        command_name="saliency",
        message="Saliency scheduled.",
        state=service.get_state(),
        changed_state=ChangedState(),
        diagnostics={
            "action": "schedule",
            "post_training_saliency_schedule": {
                "status": {"generation": scheduled_generation},
            },
        },
    )
    mismatched_status = PostTrainingSaliencyStatus(
        generation=scheduled_generation + 1,
        phase=PostTrainingSaliencyPhase.SUCCEEDED,
        run=TrainingRunIdentity(trainer_id="trainer-1", run_id=1),
        training_generation=4,
        methods=("Gradient",),
    )
    monkeypatch.setattr(service, "_execute_command", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(
        service.training_runtime,
        "wait_for_saliency_job",
        lambda *, timeout=None: True,
    )
    monkeypatch.setattr(
        service.training_runtime,
        "wait_for_saliency_delivery",
        lambda *, timeout=None: True,
    )
    monkeypatch.setattr(
        service.training_runtime,
        "saliency_status",
        lambda: mismatched_status,
    )
    terminal_published = Event()
    release_monitor = Event()
    fail = service.owned_work.fail

    def block_after_failure(operation_id: str, *, message: str):
        failed = fail(operation_id, message=message)
        terminal_published.set()
        assert release_monitor.wait(timeout=_THREAD_WATCHDOG_SECONDS)
        return failed

    monkeypatch.setattr(service.owned_work, "fail", block_after_failure)

    observed = service.execute(command, operation_id=operation.operation_id)

    assert observed.ok
    assert terminal_published.wait(timeout=_THREAD_WATCHDOG_SECONDS)
    terminal = service.get_owned_operation(operation.operation_id)
    assert terminal.phase is OwnedWorkPhase.FAILED
    assert "generation" in terminal.message.lower()
    assert service.wait_for_background_tasks(timeout=0.0) is False
    with service._training_operation_lock:
        monitor = service._training_operation_threads[operation.operation_id]
    assert monitor.is_alive()
    release_monitor.set()
    assert service._wait_for_owned_operation_monitors(timeout=1.0)
    assert not monitor.is_alive()
