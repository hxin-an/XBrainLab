from dataclasses import replace

from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.state import (
    ActiveTrainingSnapshot,
    ApplicationStateSnapshot,
    TrainingStateSnapshot,
)
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.backend.training_state_contract import (
    TrainingOutcomeState,
    TrainingRunIdentity,
    TrainingTerminalOutcome,
)
from XBrainLab.llm.agent.turn import AssistantTurnCorrelation
from XBrainLab.llm.tools.application_surface import ToolCommandResult
from XBrainLab.ui.components.assistant_application_publication_coordinator import (
    AssistantApplicationPublicationCoordinator,
)


def _publication(revision: int) -> ApplicationViewPublication:
    state = ApplicationStateSnapshot.empty()
    return ApplicationViewPublication(
        generation=revision,
        revision=revision,
        state=state,
        capabilities=build_capability_policy(state),
    )


def test_publication_retry_coalesces_to_latest_and_enters_recovery_interval() -> None:
    coordinator = AssistantApplicationPublicationCoordinator(
        retry_interval_ms=25,
        max_fast_retries=3,
        recovery_interval_ms=500,
    )
    first = _publication(8)
    latest = _publication(9)

    first_schedule = coordinator.schedule_publication_retry(first)
    latest_schedule = coordinator.schedule_publication_retry(latest)

    assert first_schedule is not None and first_schedule.pending_changed is True
    assert latest_schedule is not None and latest_schedule.pending_changed is True
    assert coordinator.snapshot().pending_publication is latest
    for _ in range(3):
        assert coordinator.begin_publication_retry() is latest
        schedule = coordinator.schedule_publication_retry(latest)
        assert schedule is not None
    assert schedule.interval_ms == 500

    coordinator.complete_publication(9)

    state = coordinator.snapshot()
    assert state.pending_publication is None
    assert state.publication_retry_attempts == 0


def test_training_terminal_keeps_exact_assistant_run_until_rendered() -> None:
    coordinator = AssistantApplicationPublicationCoordinator()
    correlation = AssistantTurnCorrelation(generation=4, turn_id=12)
    run = TrainingRunIdentity(trainer_id="trainer-1", run_id=2)
    running = replace(
        ApplicationStateSnapshot.empty(),
        pipeline_stage="training",
        training=TrainingStateSnapshot(
            has_trainer=True,
            is_running=True,
            finished_run_count=0,
            terminal_outcome=TrainingTerminalOutcome(
                state=TrainingOutcomeState.RUNNING,
                run=run,
            ),
        ),
        active_training=ActiveTrainingSnapshot(
            has_trainer=True,
            is_running=True,
            finished_run_count=0,
        ),
    )
    completed = replace(
        running,
        pipeline_stage="trained",
        training=replace(
            running.training,
            is_running=False,
            finished_run_count=1,
            terminal_outcome=TrainingTerminalOutcome(
                state=TrainingOutcomeState.COMPLETED,
                run=run,
            ),
        ),
        active_training=replace(
            running.active_training,
            is_running=False,
            finished_run_count=1,
        ),
    )
    result = ToolCommandResult(
        ok=True,
        tool_name="start_training",
        command_name="train",
        message="Training started.",
        state=running.to_dict(),
        diagnostics={"training_handoff_generation": 7},
    )
    publication = ApplicationViewPublication(
        generation=8,
        revision=80,
        state=completed,
        capabilities=build_capability_policy(completed),
    )

    assert coordinator.begin_training_watch(result, correlation) is True
    notice = coordinator.observe_training_publication(publication)

    assert notice is not None
    assert notice.outcome is TrainingOutcomeState.COMPLETED
    assert notice.correlation == correlation
    assert coordinator.terminal_notice_if_idle(is_idle=False) is None
    assert coordinator.terminal_notice_if_idle(is_idle=True) is notice

    coordinator.complete_terminal_notice(notice)

    state = coordinator.snapshot()
    assert state.pending_training_terminal is None
    assert state.training_watch is None


def test_training_watch_rejects_untyped_handoff_identity() -> None:
    coordinator = AssistantApplicationPublicationCoordinator()
    result = ToolCommandResult(
        ok=True,
        tool_name="start_training",
        command_name="train",
        message="Training started.",
        state={"training": {"finished_run_count": 0}},
        diagnostics={},
    )

    assert (
        coordinator.begin_training_watch(
            result,
            AssistantTurnCorrelation(generation=1, turn_id=1),
        )
        is False
    )
    assert coordinator.snapshot().training_watch is None
