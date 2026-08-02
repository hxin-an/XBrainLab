"""Post-training saliency automation contract tests."""

from __future__ import annotations

from threading import Event, get_ident
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from XBrainLab.backend.application.post_training_saliency import (
    PostTrainingSaliencyAutomation,
)
from XBrainLab.backend.training_manager import current_post_training_saliency_target
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    PostTrainingSaliencyScheduleReason,
    PostTrainingSaliencyStatus,
    TrainingLifecycleEvent,
    TrainingOutcomeState,
    TrainingRunIdentity,
    TrainingStateToken,
    TrainingTerminalOutcome,
)
from XBrainLab.backend.utils.observer import Observable


class _TrainingEvents(Observable):
    def __init__(self) -> None:
        super().__init__()
        self.outcome = TrainingTerminalOutcome(state=TrainingOutcomeState.UNKNOWN)

    def get_terminal_outcome(self) -> TrainingTerminalOutcome:
        return self.outcome


def _outcome(
    state: TrainingOutcomeState,
    *,
    trainer_id: str = "trainer-a",
    run_id: int = 1,
    detail: str | None = None,
) -> TrainingTerminalOutcome:
    return TrainingTerminalOutcome(
        state=state,
        run=TrainingRunIdentity(trainer_id=trainer_id, run_id=run_id),
        detail=detail,
    )


def _state(*, finished_runs: int, progress: str = "Pending") -> SimpleNamespace:
    return SimpleNamespace(
        evaluation=SimpleNamespace(finished_runs=finished_runs),
        training=SimpleNamespace(progress_message=progress),
    )


def _publish_terminal(
    training: _TrainingEvents,
    *,
    publication_generation: int = 1,
) -> None:
    training.notify(
        "training_terminal_published",
        TrainingLifecycleEvent(
            token=TrainingStateToken(
                generation=publication_generation,
                stable=True,
            ),
            outcome=training.outcome,
            publication_generation=publication_generation,
            publication_revision=publication_generation,
        ),
    )


def test_raw_training_stop_waits_for_acknowledged_terminal_publication() -> None:
    training = _TrainingEvents()
    current_state = _state(finished_runs=0)
    configured: list[dict[str, object]] = []
    automation = PostTrainingSaliencyAutomation(
        training=training,
        get_state=lambda: current_state,
        configure_saliency=configured.append,
    )

    automation.arm()
    assert training._observers.get("training_stopped", ()) == ()
    assert len(training._observers.get("training_terminal_published", ())) == 1
    current_state.evaluation.finished_runs = 1
    training.outcome = _outcome(TrainingOutcomeState.COMPLETED)

    training.notify("training_stopped")

    assert configured == []

    _publish_terminal(training)
    assert automation.wait_for_idle(timeout=2.0)
    assert len(configured) == 1


def test_completed_training_starts_recommended_saliency_without_ui_panel() -> None:
    training = _TrainingEvents()
    current_state = _state(finished_runs=2)
    configured: list[dict[str, object]] = []
    automation = PostTrainingSaliencyAutomation(
        training=training,
        get_state=lambda: current_state,
        configure_saliency=configured.append,
    )

    automation.arm()
    current_state.evaluation.finished_runs = 3
    training.outcome = _outcome(TrainingOutcomeState.COMPLETED)
    _publish_terminal(training)
    assert automation.wait_for_idle(timeout=2.0)

    assert configured == [
        {
            "profile": "recommended",
            "methods": ["Gradient", "Gradient * Input"],
        }
    ]


def test_cancel_unsubscribes_idempotently_and_rearm_subscribes_once() -> None:
    training = _TrainingEvents()
    current_state = _state(finished_runs=0)
    automation = PostTrainingSaliencyAutomation(
        training=training,
        get_state=lambda: current_state,
        configure_saliency=lambda _params: None,
    )

    automation.arm()
    assert len(training._observers.get("training_terminal_published", ())) == 1

    automation.cancel()
    automation.cancel()
    assert len(training._observers.get("training_terminal_published", ())) == 0

    automation.arm()
    automation.arm()
    assert len(training._observers.get("training_terminal_published", ())) == 1

    automation.cancel()


def test_completed_training_scopes_saliency_to_the_verified_run() -> None:
    training = _TrainingEvents()
    current_state = _state(finished_runs=2)
    observed_targets = []

    def configure(_params: dict[str, object]) -> None:
        observed_targets.append(current_post_training_saliency_target())

    automation = PostTrainingSaliencyAutomation(
        training=training,
        get_state=lambda: current_state,
        configure_saliency=configure,
    )

    automation.arm(append=True)
    current_state.evaluation.finished_runs = 4
    training.outcome = _outcome(TrainingOutcomeState.COMPLETED, run_id=7)
    _publish_terminal(training)
    assert automation.wait_for_idle(timeout=2.0)

    assert len(observed_targets) == 1
    target = observed_targets[0]
    assert target is not None
    assert target.run == training.outcome.run
    assert target.finished_runs_before == 2
    assert target.finished_runs_after == 4
    assert target.append is True


def test_terminal_publication_observer_does_not_run_saliency_command_inline() -> None:
    training = _TrainingEvents()
    current_state = _state(finished_runs=0)
    configure_started = Event()
    release_configure = Event()
    callback_threads = []

    def configure(_params: dict[str, object]) -> None:
        callback_threads.append(get_ident())
        configure_started.set()
        assert release_configure.wait(timeout=2.0)

    automation = PostTrainingSaliencyAutomation(
        training=training,
        get_state=lambda: current_state,
        configure_saliency=configure,
    )
    notifying_thread = get_ident()

    automation.arm()
    current_state.evaluation.finished_runs = 1
    training.outcome = _outcome(TrainingOutcomeState.COMPLETED)
    _publish_terminal(training)

    assert configure_started.wait(timeout=2.0)
    assert callback_threads != [notifying_thread]
    release_configure.set()
    assert automation.wait_for_idle(timeout=2.0)


@pytest.mark.parametrize("failure_point", ["construct", "start"])
def test_submission_thread_failure_publishes_typed_terminal_status_once(
    failure_point: str,
) -> None:
    """Submission failure must terminate the captured run instead of going idle."""
    training = _TrainingEvents()
    current_state = _state(finished_runs=0)
    configured: list[dict[str, object]] = []
    terminal_statuses: list[PostTrainingSaliencyStatus] = []

    class SubmissionFailureThread:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs
            if failure_point == "construct":
                raise RuntimeError("thread construction failed")

        def start(self) -> None:
            if failure_point == "start":
                raise RuntimeError("thread start failed")

        def join(self, timeout=None) -> None:
            del timeout
            raise AssertionError("an unstarted job must not be joined")

    def publish_failure(target, error: BaseException) -> PostTrainingSaliencyStatus:
        status = PostTrainingSaliencyStatus(
            phase=PostTrainingSaliencyPhase.FAILED,
            generation=1,
            run=target.run,
            training_generation=1,
            methods=("Gradient", "Gradient * Input"),
            error_code=PostTrainingSaliencyScheduleReason.THREAD_START_FAILED.value,
            message="Automatic saliency could not start its background worker.",
            diagnostic_type=type(error).__name__,
        )
        terminal_statuses.append(status)
        return status

    automation = PostTrainingSaliencyAutomation(
        training=training,
        get_state=lambda: current_state,
        configure_saliency=configured.append,
        publish_submission_failure=publish_failure,
    )
    automation.arm()
    current_state.evaluation.finished_runs = 1
    training.outcome = _outcome(TrainingOutcomeState.COMPLETED)

    with patch(
        "XBrainLab.backend.application.post_training_saliency.Thread",
        SubmissionFailureThread,
    ):
        _publish_terminal(training)
        _publish_terminal(training)

    assert automation.wait_for_idle(timeout=0.01)
    assert configured == []
    assert len(terminal_statuses) == 1
    status = terminal_statuses[0]
    assert status.phase is PostTrainingSaliencyPhase.FAILED
    assert status.run == training.outcome.run
    assert status.error_code == (
        PostTrainingSaliencyScheduleReason.THREAD_START_FAILED.value
    )


def test_failed_saliency_command_result_publishes_submission_failure() -> None:
    training = _TrainingEvents()
    current_state = _state(finished_runs=0)
    failures: list[tuple[object, BaseException]] = []

    def configure(_params: dict[str, object]) -> SimpleNamespace:
        return SimpleNamespace(
            failed=True,
            message="XBrainLab is closing.",
        )

    def publish_failure(target, error: BaseException) -> None:
        failures.append((target, error))

    automation = PostTrainingSaliencyAutomation(
        training=training,
        get_state=lambda: current_state,
        configure_saliency=configure,
        publish_submission_failure=publish_failure,
    )
    automation.arm()
    current_state.evaluation.finished_runs = 1
    training.outcome = _outcome(TrainingOutcomeState.COMPLETED)

    _publish_terminal(training)
    assert automation.wait_for_idle(timeout=2.0)

    assert len(failures) == 1
    target, error = failures[0]
    assert target.run == training.outcome.run
    assert str(error) == "XBrainLab is closing."


def test_failed_or_duplicate_training_stop_does_not_compute_saliency() -> None:
    training = _TrainingEvents()
    current_state = _state(finished_runs=1)
    configured: list[dict[str, object]] = []
    automation = PostTrainingSaliencyAutomation(
        training=training,
        get_state=lambda: current_state,
        configure_saliency=configured.append,
    )

    automation.arm()
    current_state.evaluation.finished_runs = 2
    current_state.training.progress_message = "Error: CUDA out of memory"
    training.outcome = _outcome(
        TrainingOutcomeState.FAILED,
        detail="CUDA out of memory",
    )
    _publish_terminal(training)
    _publish_terminal(training)

    assert configured == []


def test_training_without_new_finished_run_does_not_compute_saliency() -> None:
    training = _TrainingEvents()
    current_state = _state(finished_runs=1)
    configured: list[dict[str, object]] = []
    automation = PostTrainingSaliencyAutomation(
        training=training,
        get_state=lambda: current_state,
        configure_saliency=configured.append,
    )

    automation.arm()
    training.outcome = _outcome(TrainingOutcomeState.COMPLETED)
    _publish_terminal(training)

    assert configured == []


def test_replacement_training_computes_saliency_when_finished_count_is_equal() -> None:
    training = _TrainingEvents()
    current_state = _state(finished_runs=1)
    configured: list[dict[str, object]] = []
    automation = PostTrainingSaliencyAutomation(
        training=training,
        get_state=lambda: current_state,
        configure_saliency=configured.append,
    )

    automation.arm(append=False)
    # append=False replaces the old trainer. The new trainer can finish one run,
    # leaving the aggregate count unchanged even though this is a new result.
    training.outcome = _outcome(
        TrainingOutcomeState.COMPLETED,
        trainer_id="trainer-b",
    )
    _publish_terminal(training)
    assert automation.wait_for_idle(timeout=2.0)

    assert configured == [
        {
            "profile": "recommended",
            "methods": ["Gradient", "Gradient * Input"],
        }
    ]


@pytest.mark.parametrize(
    "terminal_state",
    [TrainingOutcomeState.CANCELLED, TrainingOutcomeState.STOP_REQUESTED],
)
def test_partial_cancelled_training_never_starts_saliency(
    terminal_state: TrainingOutcomeState,
) -> None:
    training = _TrainingEvents()
    current_state = _state(finished_runs=2)
    configured: list[dict[str, object]] = []
    automation = PostTrainingSaliencyAutomation(
        training=training,
        get_state=lambda: current_state,
        configure_saliency=configured.append,
    )

    automation.arm(append=True)
    current_state.evaluation.finished_runs = 3
    training.outcome = _outcome(terminal_state, run_id=2)
    _publish_terminal(training)

    assert configured == []


def test_duplicate_terminal_event_for_previous_run_does_not_consume_armed_run() -> None:
    training = _TrainingEvents()
    training.outcome = _outcome(TrainingOutcomeState.COMPLETED, run_id=1)
    current_state = _state(finished_runs=1)
    configured: list[dict[str, object]] = []
    automation = PostTrainingSaliencyAutomation(
        training=training,
        get_state=lambda: current_state,
        configure_saliency=configured.append,
    )

    automation.arm(append=True)
    _publish_terminal(training)
    current_state.evaluation.finished_runs = 2
    training.outcome = _outcome(TrainingOutcomeState.COMPLETED, run_id=2)
    _publish_terminal(training, publication_generation=2)
    assert automation.wait_for_idle(timeout=2.0)

    assert len(configured) == 1


def test_invalid_terminal_publication_does_not_consume_the_armed_run() -> None:
    training = _TrainingEvents()
    current_state = _state(finished_runs=0)
    configured: list[dict[str, object]] = []
    automation = PostTrainingSaliencyAutomation(
        training=training,
        get_state=lambda: current_state,
        configure_saliency=configured.append,
    )

    automation.arm()
    training.notify("training_terminal_published")
    current_state.evaluation.finished_runs = 1
    training.outcome = _outcome(TrainingOutcomeState.COMPLETED)
    _publish_terminal(training)
    assert automation.wait_for_idle(timeout=2.0)

    assert len(configured) == 1
