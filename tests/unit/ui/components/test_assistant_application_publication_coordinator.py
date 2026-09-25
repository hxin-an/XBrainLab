from dataclasses import replace
from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QWidget

from XBrainLab.backend.application import ApplicationService
from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.state import (
    ActiveTrainingSnapshot,
    ApplicationStateSnapshot,
    TrainingStateSnapshot,
)
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.backend.study import Study
from XBrainLab.backend.training_state_contract import (
    TrainingOutcomeState,
    TrainingRunIdentity,
    TrainingTerminalOutcome,
)
from XBrainLab.llm.agent.turn import AssistantTurnCorrelation
from XBrainLab.llm.tools.result_contract import ToolCommandResult
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


@pytest.fixture
def delivery(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)
    observed = SimpleNamespace(idle=False, notices=[], revisions=[], render_ok=True)

    def render_status(projection):
        observed.revisions.append(projection.publication_revision)
        return observed.render_ok

    def render_terminal(notice):
        observed.notices.append(notice)
        return True

    coordinator = AssistantApplicationPublicationCoordinator(
        service=ApplicationService(Study()),
        render_status=render_status,
        render_terminal=render_terminal,
        is_idle=lambda: observed.idle,
        parent=parent,
    )
    yield coordinator, observed
    coordinator.close()


def test_publication_retry_coalesces_to_latest_and_enters_recovery_interval(
    delivery, qtbot
):
    coordinator, observed = delivery
    observed.render_ok = False
    assert not coordinator.deliver(_publication(8))
    assert not coordinator.deliver(_publication(9))
    qtbot.waitUntil(lambda: len(observed.revisions) == 5, timeout=1000)
    assert observed.revisions == [8, 9, 9, 9, 9]
    qtbot.wait(100)
    assert len(observed.revisions) == 5
    observed.render_ok = True
    qtbot.waitUntil(lambda: coordinator.projection is not None, timeout=2000)
    assert coordinator.projection.publication_revision == 9
    assert observed.revisions == [8, 9, 9, 9, 9, 9]


@pytest.mark.parametrize("ending", ["deliver", "clear", "close"])
def test_training_terminal_keeps_exact_assistant_run_until_rendered(
    delivery,
    qtbot,
    ending,
) -> None:
    coordinator, observed = delivery
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
    assert coordinator.deliver(publication)
    assert observed.notices == []
    assert not coordinator.flush_terminal()
    observed.idle = True
    if ending != "deliver":
        attempts = []

        def fail_render(notice):
            attempts.append(notice)
            return False

        coordinator._render_terminal = fail_render
        assert not coordinator.flush_terminal()
        assert len(attempts) == 1
        if ending == "clear":
            coordinator.clear_training()
        else:
            coordinator.close()
            assert not coordinator.begin_training_watch(result, correlation)
        qtbot.wait(600)
        assert len(attempts) == 1
        assert not coordinator.flush_terminal()
        return
    assert coordinator.flush_terminal()
    assert len(observed.notices) == 1
    notice = observed.notices[0]
    assert notice.outcome is TrainingOutcomeState.COMPLETED
    assert notice.correlation == correlation
    assert not coordinator.flush_terminal()
    assert len(observed.notices) == 1


@pytest.mark.parametrize(
    ("outcome", "published_run"),
    (
        (TrainingOutcomeState.FAILED, None),
        (
            TrainingOutcomeState.CANCELLED,
            TrainingRunIdentity(trainer_id="trainer-1", run_id=3),
        ),
    ),
    ids=("missing-identity", "stale-identity"),
)
def test_training_terminal_requires_the_watched_run_identity(
    delivery,
    outcome: TrainingOutcomeState,
    published_run: TrainingRunIdentity | None,
) -> None:
    coordinator, observed = delivery
    observed.idle = True
    watched_run = TrainingRunIdentity(trainer_id="trainer-1", run_id=2)
    running = replace(
        ApplicationStateSnapshot.empty(),
        pipeline_stage="training",
        training=TrainingStateSnapshot(
            has_trainer=True,
            is_running=True,
            terminal_outcome=TrainingTerminalOutcome(
                state=TrainingOutcomeState.RUNNING,
                run=watched_run,
            ),
        ),
        active_training=ActiveTrainingSnapshot(
            has_trainer=True,
            is_running=True,
        ),
    )
    terminal = replace(
        running,
        pipeline_stage="dataset_ready",
        training=replace(
            running.training,
            is_running=False,
            terminal_outcome=TrainingTerminalOutcome(
                state=outcome,
                run=published_run,
            ),
        ),
        active_training=replace(running.active_training, is_running=False),
    )
    result = ToolCommandResult(
        ok=True,
        tool_name="start_training",
        command_name="train",
        message="Training started.",
        state=running.to_dict(),
        diagnostics={"training_handoff_generation": 7},
    )

    assert coordinator.begin_training_watch(
        result,
        AssistantTurnCorrelation(generation=4, turn_id=12),
    )
    watch_before = coordinator._training_watch
    assert watch_before is not None
    publication = ApplicationViewPublication(
        generation=8,
        revision=80,
        state=terminal,
        capabilities=build_capability_policy(terminal),
    )

    assert coordinator.deliver(publication)
    assert observed.notices == []
    assert coordinator._training_watch == watch_before
    assert not coordinator.flush_terminal()


@pytest.mark.parametrize("generation", [None, True, 0, -1, "7"])
def test_training_watch_rejects_untyped_handoff_identity(generation, delivery) -> None:
    coordinator, _observed = delivery
    result = ToolCommandResult(
        ok=True,
        tool_name="start_training",
        command_name="train",
        message="Training started.",
        state={"training": {"finished_run_count": 0}},
        diagnostics={"training_handoff_generation": generation},
    )

    assert (
        coordinator.begin_training_watch(
            result,
            AssistantTurnCorrelation(generation=1, turn_id=1),
        )
        is False
    )
    assert coordinator._training_watch is None
