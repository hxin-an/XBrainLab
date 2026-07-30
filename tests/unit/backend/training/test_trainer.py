import threading
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

import XBrainLab.backend.training.trainer as trainer_module
from XBrainLab.backend.training import Trainer, TrainingPlanHolder
from XBrainLab.backend.training.record import RecordKey, TrainRecord, TrainRecordKey
from XBrainLab.backend.training.state_tracker import TrainingStateTracker
from XBrainLab.backend.training_state_contract import (
    TrainingOutcomeState,
    TrainingStateToken,
    read_training_terminal_outcome,
)


class FakePlan:
    def __init__(self, i):
        self.i = i
        self._state_tracker = None

    def bind_state_tracker(self, tracker):
        self._state_tracker = tracker

    def get_name(self):
        return str(self.i)


class FakeTrainingPlanHolder(TrainingPlanHolder):
    def __init__(self, i):
        self.i = i
        self.train_record_list = [FakePlan("test")]
        self._interrupt = threading.Event()
        self.error = None

    def get_name(self):
        return "Fake" + str(self.i)


@pytest.fixture
def training_plan_holders():
    result = [FakeTrainingPlanHolder(i) for i in range(2)]
    return result


def test_trainer(training_plan_holders):
    trainer = Trainer(training_plan_holders)
    assert trainer.get_training_plan_holders() == training_plan_holders
    assert trainer.get_progress_text() == "Pending"
    holder = training_plan_holders[-1]

    with (
        patch.object(holder, "set_interrupt") as interrupt_mock,
        patch.object(holder, "clear_interrupt") as clear_interrupt_mock,
    ):

        def interrupt():
            assert trainer.get_progress_text() == "Interrupting"

        interrupt_mock.side_effect = interrupt

        trainer.set_interrupt()
        interrupt_mock.assert_called_once()
        assert trainer.interrupt
        assert trainer.get_progress_text() == "Interrupting"

        trainer.clear_interrupt()
        clear_interrupt_mock.assert_called_once()
        assert trainer.interrupt is False
        assert trainer.get_progress_text() == "Pending"


def test_trainer_custom_progress_text(training_plan_holders):
    trainer = Trainer(training_plan_holders)
    trainer.progress_text = "Custom"
    assert trainer.get_progress_text() == "Custom"


def test_trainer_initial_outcome_is_not_started(training_plan_holders) -> None:
    trainer = Trainer(training_plan_holders)

    outcome = trainer.get_terminal_outcome()

    assert outcome.state is TrainingOutcomeState.NOT_STARTED
    assert outcome.run is None
    assert outcome.is_quiescent is True
    assert outcome.is_terminal is False


def test_typed_outcome_reader_fails_closed_for_invalid_backend() -> None:
    invalid = type(
        "InvalidOutcomeBackend",
        (),
        {"get_terminal_outcome": lambda self: 1},
    )()

    missing = read_training_terminal_outcome(None)
    malformed = read_training_terminal_outcome(invalid)

    assert missing.state is TrainingOutcomeState.UNKNOWN
    assert malformed.state is TrainingOutcomeState.UNKNOWN
    assert missing.detail
    assert malformed.detail


def test_trainer_runtime_generation_tracks_state_transitions(training_plan_holders):
    trainer = Trainer(training_plan_holders)
    initial = trainer.get_state_generation()

    trainer.set_interrupt()
    interrupted = trainer.get_state_generation()
    trainer.clear_interrupt()

    assert interrupted > initial
    assert trainer.get_state_generation() > interrupted


def test_trainer_runtime_generation_tracks_nested_record_mutations():
    record = object.__new__(TrainRecord)
    record._state_tracker = None
    record.epoch = 0
    record.train = {key: [] for key in TrainRecordKey()}
    record.val = {key: [] for key in RecordKey()}
    record.eval_record = None

    holder = object.__new__(TrainingPlanHolder)
    holder.train_record_list = [record]
    holder._state_tracker = None
    holder._interrupt = threading.Event()
    holder.error = None
    holder.status = "Pending"

    trainer = Trainer([holder])
    initial = trainer.get_state_generation()

    record.update_train({RecordKey.LOSS: 1.0})
    after_metric = trainer.get_state_generation()
    record.step()
    after_epoch = trainer.get_state_generation()
    record.set_eval_record(cast(Any, object()))
    after_evaluation = trainer.get_state_generation()

    assert initial < after_metric < after_epoch < after_evaluation
    assert trainer.get_state_snapshot_token().stable is True


def test_nested_record_mutation_exception_restores_stable_token():
    record = object.__new__(TrainRecord)
    record._state_tracker = None
    record.epoch = 0
    record.train = {key: [] for key in TrainRecordKey()}

    holder = object.__new__(TrainingPlanHolder)
    holder.train_record_list = [record]
    holder._state_tracker = None

    trainer = Trainer([holder])

    with pytest.raises(KeyError):
        record.update_train({"not-a-metric": 1.0})

    assert trainer.get_state_snapshot_token().stable is True


def test_trainer_snapshot_identity_is_stable_and_unique() -> None:
    first = Trainer([])
    second = Trainer([])
    identity = first.get_state_snapshot_identity()

    first.add_training_plan_holders([])

    assert first.get_state_snapshot_identity() == identity
    assert second.get_state_snapshot_identity() != identity


def test_training_state_tracker_nested_exception_restores_stability():
    tracker = TrainingStateTracker()

    with pytest.raises(RuntimeError), tracker.mutation(), tracker.mutation():
        raise RuntimeError("nested mutation failed")

    token = tracker.token()
    assert token == TrainingStateToken(generation=2, stable=True)


def test_training_state_tracker_concurrent_overlap_stays_unstable():
    tracker = TrainingStateTracker()
    entered = [threading.Event(), threading.Event()]
    release = [threading.Event(), threading.Event()]

    def mutate(index: int) -> None:
        with tracker.mutation():
            entered[index].set()
            assert release[index].wait(timeout=2.0)

    threads = [threading.Thread(target=mutate, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    assert all(event.wait(timeout=2.0) for event in entered)
    assert tracker.token().stable is False

    release[0].set()
    threads[0].join(timeout=2.0)
    assert not threads[0].is_alive()
    assert tracker.token().stable is False

    release[1].set()
    threads[1].join(timeout=2.0)
    assert not threads[1].is_alive()
    token = tracker.token()
    assert token == TrainingStateToken(generation=2, stable=True)


@pytest.mark.parametrize("add_many", [False, True])
def test_added_training_plans_bind_epoch_and_eval_mutations_to_tracker(add_many):
    record = object.__new__(TrainRecord)
    record._state_tracker = None
    record.epoch = 0
    record.train = {key: [] for key in TrainRecordKey()}
    record.val = {key: [] for key in RecordKey()}
    record.eval_record = None

    holder = object.__new__(TrainingPlanHolder)
    holder.train_record_list = [record]
    holder._state_tracker = None

    trainer = Trainer([])
    initial = trainer.get_state_generation()
    if add_many:
        trainer.add_training_plan_holders([holder])
    else:
        trainer.add_plan(holder)
    after_add = trainer.get_state_generation()

    record.step()
    after_epoch = trainer.get_state_generation()
    record.set_eval_record(cast(Any, object()))
    after_evaluation = trainer.get_state_generation()

    assert initial < after_add < after_epoch < after_evaluation
    assert trainer.get_state_snapshot_token().stable is True


def test_trainer_owns_plan_collection_and_cannot_be_bypassed_by_list_alias():
    original: list[TrainingPlanHolder] = []
    trainer = Trainer(original)
    holder = object.__new__(TrainingPlanHolder)
    holder.train_record_list = []
    holder._state_tracker = None

    original.append(holder)

    assert trainer.get_training_plan_holders() == []
    assert holder._state_tracker is None

    trainer.add_plan(holder)

    assert trainer.get_training_plan_holders() == [holder]
    assert holder._state_tracker is not None


@pytest.mark.parametrize("interact", [True, False])
def test_trainer_run(training_plan_holders, interact):
    trainer = Trainer(training_plan_holders)

    with patch.object(trainer, "job") as job_mock:

        def job():
            if interact:
                assert trainer.is_running()
                assert threading.current_thread() is not threading.main_thread()
                call_count = job_mock.call_count
                trainer.run()
                assert job_mock.call_count == call_count
                with pytest.raises(RuntimeError):
                    trainer.clean()
                trainer.clean(force_update=True)
            else:
                assert threading.current_thread() is threading.main_thread()

        job_mock.side_effect = job
        trainer.run(interact=interact)
        job_mock.assert_called_once()
        thread = trainer.job_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        assert trainer.is_running() is False


def test_concurrent_run_callers_admit_exactly_one_background_worker(
    training_plan_holders,
):
    trainer = Trainer(training_plan_holders)
    native_thread = threading.Thread
    callers_ready = threading.Barrier(2)
    start_entered = threading.Event()
    allow_start = threading.Event()
    worker_entered = threading.Event()
    release_worker = threading.Event()
    worker_threads: list[threading.Thread] = []
    caller_errors: list[BaseException] = []

    def blocking_train() -> None:
        worker_entered.set()
        assert release_worker.wait(timeout=2.0)

    def create_worker(*args, **kwargs):
        class StartBlockedThread(native_thread):
            def start(self) -> None:
                start_entered.set()
                assert allow_start.wait(timeout=2.0)
                super().start()

        thread = StartBlockedThread(*args, **kwargs)
        worker_threads.append(thread)
        return thread

    def call_run() -> None:
        try:
            callers_ready.wait(timeout=2.0)
            trainer.run(interact=True)
        except BaseException as exc:
            caller_errors.append(exc)

    callers = [native_thread(target=call_run) for _ in range(2)]
    with (
        patch.object(training_plan_holders[0], "train", side_effect=blocking_train),
        patch.object(training_plan_holders[1], "train", side_effect=blocking_train),
        patch.object(
            trainer_module.threading,
            "Thread",
            side_effect=create_worker,
        ),
    ):
        for caller in callers:
            caller.start()
        assert start_entered.wait(timeout=2.0)
        allow_start.set()
        for caller in callers:
            caller.join(timeout=2.0)

        try:
            assert all(not caller.is_alive() for caller in callers)
            assert caller_errors == []
            assert worker_entered.wait(timeout=2.0)
            assert len(worker_threads) == 1
            active = trainer.get_terminal_outcome()
            assert active.state is TrainingOutcomeState.RUNNING
            assert active.run is not None
            assert active.run.run_id == 1
        finally:
            release_worker.set()
            for thread in worker_threads:
                thread.join(timeout=2.0)

    assert all(not thread.is_alive() for thread in worker_threads)
    completed = trainer.get_terminal_outcome()
    assert completed.state is TrainingOutcomeState.COMPLETED
    assert completed.run == active.run


def test_stop_before_background_thread_start_cancels_without_starting_worker(
    training_plan_holders,
) -> None:
    trainer = Trainer(training_plan_holders)
    native_thread = threading.Thread
    clear_entered = threading.Event()
    release_clear = threading.Event()
    worker_threads: list[threading.Thread] = []
    caller_errors: list[BaseException] = []

    def block_clear_interrupt() -> None:
        clear_entered.set()
        assert release_clear.wait(timeout=2.0)

    def create_worker(*args, **kwargs):
        thread = native_thread(*args, **kwargs)
        worker_threads.append(thread)
        return thread

    def call_run() -> None:
        try:
            trainer.run(interact=True)
        except BaseException as exc:
            caller_errors.append(exc)

    caller = native_thread(target=call_run)
    with (
        patch.object(
            training_plan_holders[0],
            "clear_interrupt",
            side_effect=block_clear_interrupt,
        ),
        patch.object(training_plan_holders[0], "train") as train,
        patch.object(
            trainer_module.threading,
            "Thread",
            side_effect=create_worker,
        ),
    ):
        caller.start()
        assert clear_entered.wait(timeout=2.0)
        assert trainer.is_running() is True

        assert trainer.stop(wait_timeout=0.1) is True
        release_clear.set()
        caller.join(timeout=2.0)

    assert not caller.is_alive()
    assert caller_errors == []
    assert len(worker_threads) == 1
    assert worker_threads[0].ident is None
    train.assert_not_called()
    assert trainer.is_running() is False
    outcome = trainer.get_terminal_outcome()
    assert outcome.state is TrainingOutcomeState.CANCELLED
    assert outcome.run is not None


def test_snapshot_token_is_not_mutated_by_observing_dead_worker() -> None:
    trainer = Trainer([])
    native_thread = threading.Thread
    target_returned = threading.Event()
    allow_thread_exit = threading.Event()
    worker_threads: list[threading.Thread] = []

    def create_delayed_exit_worker(*args, **kwargs):
        target = kwargs.pop("target")
        target_args = kwargs.pop("args", ())
        target_kwargs = kwargs.pop("kwargs", {})

        def delayed_exit_target() -> None:
            target(*target_args, **target_kwargs)
            target_returned.set()
            assert allow_thread_exit.wait(timeout=2.0)

        thread = native_thread(*args, target=delayed_exit_target, **kwargs)
        worker_threads.append(thread)
        return thread

    with patch.object(
        trainer_module.threading,
        "Thread",
        side_effect=create_delayed_exit_worker,
    ):
        trainer.run(interact=True)
        assert target_returned.wait(timeout=2.0)
        thread = trainer.job_thread
        assert thread is not None
        assert thread.is_alive()
        assert trainer.get_terminal_outcome().state is TrainingOutcomeState.COMPLETED
        alive_token = trainer.get_state_snapshot_token()
        assert alive_token.stable is True

        allow_thread_exit.set()
        thread.join(timeout=2.0)
        assert not thread.is_alive()
        dead_token = trainer.get_state_snapshot_token()

    assert dead_token.stable is True
    assert dead_token == alive_token
    assert trainer.get_state_snapshot_token() == dead_token
    assert trainer.is_running() is False


def test_trainer_job(training_plan_holders):
    trainer = Trainer(training_plan_holders)
    counter = 0

    def train():
        nonlocal counter
        assert trainer.get_progress_text() == "Now training: Fake" + str(counter)
        counter += 1

    # We need to patch 'train' on EACH holder instance.
    # Since training_plan_holders is a list of instances, we can patch them
    # individually.
    # But patch.object works on the object.

    patches = [
        patch.object(holder, "train", side_effect=train)
        for holder in training_plan_holders
    ]

    # Start all patches
    mocks = [p.start() for p in patches]

    try:
        trainer.job()
        for m in mocks:
            m.assert_called_once()
        assert trainer.get_progress_text() == "Pending"
        outcome = trainer.get_terminal_outcome()
        assert outcome.state is TrainingOutcomeState.COMPLETED
        assert outcome.run is not None
        assert trainer.is_running() is False
    finally:
        for p in patches:
            p.stop()


def test_trainer_preserves_plan_failure_and_stops_remaining_queue(
    training_plan_holders,
):
    trainer = Trainer(training_plan_holders)
    failed_holder, queued_holder = training_plan_holders

    def fail_training() -> None:
        failed_holder.error = "CUDA out of memory during training. Reduce batch size."
        trainer.set_interrupt()

    with (
        patch.object(failed_holder, "train", side_effect=fail_training) as failed,
        patch.object(queued_holder, "train") as queued,
    ):
        trainer.job()

    failed.assert_called_once()
    queued.assert_not_called()
    assert trainer.get_progress_text() == (
        "Error: CUDA out of memory during training. Reduce batch size."
    )
    assert trainer.get_current_index() == len(training_plan_holders)
    outcome = trainer.get_terminal_outcome()
    assert outcome.state is TrainingOutcomeState.FAILED
    assert outcome.detail == "CUDA out of memory during training. Reduce batch size."


def test_trainer_does_not_infer_failure_from_display_status(training_plan_holders):
    trainer = Trainer(training_plan_holders)
    holder = training_plan_holders[0]
    holder.status = "Failed: display-only stale text"

    with (
        patch.object(training_plan_holders[0], "train"),
        patch.object(training_plan_holders[1], "train"),
    ):
        trainer.run(interact=False)

    assert trainer.get_terminal_outcome().state is TrainingOutcomeState.COMPLETED


def test_trainer_interrupt(training_plan_holders):
    trainer = Trainer(training_plan_holders)
    holder = training_plan_holders[0]

    with patch.object(holder, "train") as train_mock:
        trainer.set_interrupt()
        trainer.job()
        train_mock.assert_not_called()

    assert trainer.get_terminal_outcome().state is TrainingOutcomeState.CANCELLED


def test_stop_request_is_not_terminal_until_background_thread_exits(
    training_plan_holders,
):
    trainer = Trainer(training_plan_holders)
    entered = threading.Event()
    release = threading.Event()

    def blocking_train() -> None:
        entered.set()
        assert release.wait(timeout=2.0)

    with patch.object(training_plan_holders[0], "train", side_effect=blocking_train):
        trainer.run(interact=True)
        assert entered.wait(timeout=2.0)

        try:
            stopped = trainer.stop(wait_timeout=0.01)

            assert stopped is False
            requested = trainer.get_terminal_outcome()
            assert requested.state is TrainingOutcomeState.STOP_REQUESTED
            assert requested.run is not None
            assert trainer.is_running() is True
        finally:
            release.set()
            thread = trainer.job_thread
            if thread is not None:
                thread.join(timeout=2.0)

    assert trainer.is_running() is False
    cancelled = trainer.get_terminal_outcome()
    assert cancelled.state is TrainingOutcomeState.CANCELLED
    assert cancelled.run == requested.run


def test_stop_retires_cancelled_queue_before_a_new_plan_runs(
    training_plan_holders,
):
    old_holder, new_holder = training_plan_holders
    trainer = Trainer([old_holder])
    entered = threading.Event()
    release = threading.Event()

    def interrupted_train() -> None:
        entered.set()
        assert release.wait(timeout=2.0)

    with patch.object(old_holder, "train", side_effect=interrupted_train) as old_train:
        trainer.run(interact=True)
        assert entered.wait(timeout=2.0)
        assert trainer.stop(wait_timeout=0.01) is False
        release.set()
        assert trainer.wait_for_completion(timeout=2.0) is True

    assert old_train.call_count == 1
    assert trainer.get_terminal_outcome().state is TrainingOutcomeState.CANCELLED
    assert trainer.get_current_index() == 1
    assert old_holder.get_training_status() == "Cancelled"

    trainer.add_plan(new_holder)
    with (
        patch.object(old_holder, "train") as old_retry,
        patch.object(new_holder, "train") as new_train,
    ):
        trainer.run(interact=False)

    old_retry.assert_not_called()
    new_train.assert_called_once()
    assert trainer.get_current_index() == 2
    assert trainer.get_terminal_outcome().state is TrainingOutcomeState.COMPLETED


def test_each_training_run_has_a_distinct_typed_identity(training_plan_holders):
    trainer = Trainer(training_plan_holders)
    for holder in training_plan_holders:
        holder.train = MagicMock()

    trainer.run(interact=False)
    first = trainer.get_terminal_outcome()
    added = FakeTrainingPlanHolder(3)
    added.train = MagicMock()
    trainer.add_plan(added)
    trainer.run(interact=False)
    second = trainer.get_terminal_outcome()

    assert first.state is TrainingOutcomeState.COMPLETED
    assert second.state is TrainingOutcomeState.COMPLETED
    assert first.run is not None
    assert second.run is not None
    assert first.run.trainer_id == second.run.trainer_id
    assert second.run.run_id == first.run.run_id + 1


def test_stop_after_terminal_completion_preserves_completed_truth(
    training_plan_holders,
):
    trainer = Trainer(training_plan_holders)
    for holder in training_plan_holders:
        holder.train = MagicMock()
    trainer.run(interact=False)
    completed = trainer.get_terminal_outcome()

    stopped = trainer.stop()

    assert stopped is True
    assert trainer.get_terminal_outcome() == completed
    assert trainer.get_progress_text() == "Pending"


def test_trainer_force_clean_joins_running_job(training_plan_holders):
    trainer = Trainer(training_plan_holders)
    thread = MagicMock()
    thread.is_alive.side_effect = [True, False]
    trainer.job_thread = thread

    trainer.clean(force_update=True)

    thread.join.assert_called_once()
    assert trainer.job_thread is None
    assert trainer.interrupt is True


def test_trainer_stop_sets_interrupt_and_waits(training_plan_holders):
    trainer = Trainer(training_plan_holders)
    thread = MagicMock()
    thread.is_alive.side_effect = [True, False, False]
    trainer.job_thread = thread

    stopped = trainer.stop(wait_timeout=0.5)

    assert stopped is True
    thread.join.assert_called_once_with(timeout=0.5)
    assert trainer.job_thread is None
    assert trainer.interrupt is True


def test_trainer_force_clean_raises_when_job_stays_running(training_plan_holders):
    trainer = Trainer(training_plan_holders)
    thread = MagicMock()
    thread.is_alive.return_value = True
    trainer.job_thread = thread

    with pytest.raises(RuntimeError, match="did not stop"):
        trainer.clean(force_update=True)

    assert trainer.job_thread is thread


@pytest.mark.parametrize(
    "plan_name, real_plan_name, error_stage",
    [
        ["Fake", "test", 1],
        ["Fake0", "test", 0],
        ["Fake1", "test", 0],
        ["Fake1", "tests", 2],
    ],
)
def test_trainer_get_plan(
    training_plan_holders, plan_name, real_plan_name, error_stage
):
    trainer = Trainer(training_plan_holders)
    if error_stage == 0:
        trainer.get_real_training_plan(plan_name, real_plan_name)
    else:
        error = ".*training plan.*" if error_stage == 1 else ".*real plan.*"
        with pytest.raises(ValueError, match=error):
            trainer.get_real_training_plan(plan_name, real_plan_name)
