from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any, cast
from unittest.mock import MagicMock

from PyQt6.QtWidgets import QWidget

from XBrainLab.backend.application import ApplicationError, EvaluateCommand
from XBrainLab.backend.application.commands import Command
from XBrainLab.backend.application.evaluation_render import (
    EvaluationPlanIdentity,
    EvaluationRenderPublication,
    EvaluationRenderRequest,
    EvaluationSummaryIdentity,
)
from XBrainLab.backend.application.results import ChangedState, CommandResult
from XBrainLab.backend.application.state import (
    ApplicationStateSnapshot,
    ErrorSnapshot,
)
from XBrainLab.backend.application.view_publication import (
    APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
    ApplicationViewPublication,
    ApplicationViewStore,
)
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    PostTrainingSaliencyStatus,
    TrainingOutcomeState,
    TrainingReadBoundary,
    TrainingRunIdentity,
    TrainingStateToken,
    TrainingTerminalOutcome,
)
from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.panels.evaluation.panel import (
    EvaluationPanel,
    _RetryEvaluationPublicationRenderError,
)


def _publication(
    *,
    generation: int,
    revision: int,
    evaluation_marker: int | None = None,
    last_error: ErrorSnapshot | None = None,
    progress_message: str | None = None,
    terminal_outcome: TrainingTerminalOutcome | None = None,
    is_running: bool = False,
    model_params: dict[str, object] | None = None,
    trainer_identity: str | None = None,
    training_boundary_generation: int = 0,
    post_training_saliency: PostTrainingSaliencyStatus | None = None,
) -> ApplicationViewPublication:
    initial = ApplicationViewStore(
        ApplicationStateSnapshot.empty(),
        TrainingReadBoundary.no_trainer(),
    ).read()
    marker = generation if evaluation_marker is None else evaluation_marker
    state = replace(
        initial.state,
        training=replace(
            initial.state.training,
            model_params=dict(model_params or {}),
            is_running=is_running,
            progress_message=progress_message,
            terminal_outcome=terminal_outcome
            if terminal_outcome is not None
            else initial.state.training.terminal_outcome,
        ),
        evaluation=replace(
            initial.state.evaluation,
            total_runs=marker,
        ),
        visualization=replace(
            initial.state.visualization,
            post_training_saliency=(
                post_training_saliency
                if post_training_saliency is not None
                else initial.state.visualization.post_training_saliency
            ),
        ),
        last_error=last_error,
    )
    return replace(
        initial,
        generation=generation,
        revision=revision,
        state=state,
        training_boundary=TrainingReadBoundary(
            trainer_identity=trainer_identity,
            token=TrainingStateToken(
                generation=training_boundary_generation,
                stable=True,
            ),
        ),
    )


class _EvaluationApplicationPort(Observable):
    def __init__(self) -> None:
        super().__init__()
        self.publication = _publication(generation=4, revision=4)
        self.available = True
        self.query_calls = 0
        self.unsubscribe_calls = 0

    def execute(
        self,
        command: Command,
        *,
        expected_publication_generation: int | None = None,
    ) -> CommandResult:
        assert command == EvaluateCommand()
        assert expected_publication_generation == self.publication.generation
        self.query_calls += 1
        return CommandResult.success_result(
            command_name="evaluate",
            message="Evaluation summary ready.",
            state={},
            changed_state=ChangedState(),
            diagnostics={
                "payload_type": "evaluation_summary",
                "available": self.available,
                "plans": (
                    [
                        {
                            "identity": {"plan_index": 0},
                            "name": "EEGNet",
                            "runs": [],
                        }
                    ]
                    if self.available
                    else []
                ),
                "evaluation_publication_generation": self.publication.generation,
            },
        )

    def get_view_publication(self) -> ApplicationViewPublication:
        return self.publication

    def get_evaluation_render(
        self,
        request: EvaluationRenderRequest,
    ) -> EvaluationRenderPublication:
        del request
        raise AssertionError("An empty run catalog must not request chart data.")

    def unsubscribe(self, event_name, callback) -> None:
        self.unsubscribe_calls += 1
        super().unsubscribe(event_name, callback)


def _panel(
    qtbot,
    port: _EvaluationApplicationPort,
    *,
    parent: QWidget | None = None,
) -> EvaluationPanel:
    panel = EvaluationPanel(
        parent=parent,
        query_port=port,
        publication_port=port,
        action_port=port,
    )
    qtbot.addWidget(panel)
    return panel


def test_evaluation_instantiates_without_controller_or_controller_lookup(qtbot) -> None:
    port = _EvaluationApplicationPort()
    parent = cast(Any, QWidget())
    parent.study = MagicMock()
    parent.study.get_controller.side_effect = AssertionError(
        "Evaluation must not resolve a broad controller."
    )
    qtbot.addWidget(parent)

    panel = _panel(qtbot, port, parent=parent)
    panel.update_panel()

    parent.study.get_controller.assert_not_called()
    assert panel.controller is None
    assert panel.model_combo.count() == 1


def test_evaluation_fails_closed_without_application_ports(qtbot) -> None:
    panel = EvaluationPanel()
    qtbot.addWidget(panel)

    panel.update_panel()

    assert panel._evaluation_summary is None
    assert panel._evaluation_error == (
        "Evaluation results are temporarily unavailable."
    )
    assert panel.model_combo.count() == 0


def test_evaluation_renders_once_for_one_new_application_revision(qtbot) -> None:
    port = _EvaluationApplicationPort()
    panel = _panel(qtbot, port)
    panel.update_panel()
    assert port.query_calls == 1

    renders: list[int] = []
    original_update = panel.update_panel

    def counted_update() -> None:
        renders.append(port.publication.revision)
        original_update()

    panel.update_panel = counted_update
    port.available = False
    port.publication = _publication(generation=5, revision=5)

    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)

    assert renders == []
    assert port.query_calls == 1
    qtbot.waitUntil(lambda: renders == [5])
    assert renders == [5]
    assert port.query_calls == 2
    assert panel.model_combo.count() == 0


def test_evaluation_ignores_duplicate_and_stale_application_revisions(qtbot) -> None:
    port = _EvaluationApplicationPort()
    panel = _panel(qtbot, port)
    panel.update_panel()

    renders: list[int] = []
    original_update = panel.update_panel

    def counted_update() -> None:
        renders.append(port.publication.revision)
        original_update()

    panel.update_panel = counted_update
    port.publication = _publication(generation=5, revision=5)
    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)
    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)
    stale = _publication(generation=4, revision=3)
    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, stale)

    assert renders == []
    qtbot.waitUntil(lambda: renders == [5])
    assert renders == [5]
    assert port.query_calls == 2


def test_evaluation_ignores_new_revision_when_only_last_error_changes(
    qtbot,
    monkeypatch,
) -> None:
    port = _EvaluationApplicationPort()
    panel = _panel(qtbot, port)
    panel.update_panel()

    renders: list[int] = []
    panel.update_panel = lambda: renders.append(port.publication.revision)
    port.publication = _publication(
        generation=5,
        revision=5,
        evaluation_marker=4,
        last_error=ErrorSnapshot(
            error_type="TrainingError",
            message="Private backend failure detail.",
        ),
    )

    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)
    qtbot.wait(25)

    assert renders == []
    assert panel._last_application_revision == 5
    assert panel._application_generation == 5

    requested_generations: list[int] = []

    def render_for_current_generation(_panel, request, **_kwargs):
        requested_generations.append(request.publication_generation)

    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.get_evaluation_render_publication",
        render_for_current_generation,
    )
    render = panel._render_for_selection(
        EvaluationPlanIdentity(plan_index=0),
        split="test",
    )

    assert render is None
    assert requested_generations == [5]


def test_evaluation_ignores_progress_only_application_revision(qtbot) -> None:
    port = _EvaluationApplicationPort()
    port.publication = _publication(
        generation=4,
        revision=4,
        evaluation_marker=4,
        is_running=True,
        progress_message="Epoch 11 of 40",
        trainer_identity="trainer-1",
        training_boundary_generation=2,
    )
    panel = _panel(qtbot, port)
    panel.update_panel()

    renders: list[int] = []
    panel.update_panel = lambda: renders.append(port.publication.revision)
    port.publication = _publication(
        generation=5,
        revision=5,
        evaluation_marker=4,
        is_running=True,
        progress_message="Epoch 12 of 40",
        trainer_identity="trainer-1",
        training_boundary_generation=4,
    )

    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)
    qtbot.wait(25)

    assert renders == []
    assert panel._last_application_revision == 5
    assert panel._application_generation == 5


def test_evaluation_refreshes_when_model_parameters_change(qtbot) -> None:
    port = _EvaluationApplicationPort()
    panel = _panel(qtbot, port)
    panel.update_panel()

    renders: list[int] = []
    panel.update_panel = lambda: renders.append(port.publication.revision)
    port.publication = _publication(
        generation=5,
        revision=5,
        evaluation_marker=4,
        model_params={"dropout": 0.5},
    )

    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)

    qtbot.waitUntil(lambda: renders == [5])


def test_evaluation_refreshes_for_stable_catalog_generation_change(qtbot) -> None:
    port = _EvaluationApplicationPort()
    port.publication = _publication(
        generation=4,
        revision=4,
        evaluation_marker=4,
        trainer_identity="trainer-1",
        training_boundary_generation=2,
    )
    panel = _panel(qtbot, port)
    panel.update_panel()

    renders: list[int] = []
    panel.update_panel = lambda: renders.append(port.publication.revision)
    port.publication = _publication(
        generation=5,
        revision=5,
        evaluation_marker=4,
        trainer_identity="trainer-1",
        training_boundary_generation=4,
    )

    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)

    qtbot.waitUntil(lambda: renders == [5])


def test_evaluation_defers_catalog_refresh_while_saliency_mutates_record(qtbot) -> None:
    run = TrainingRunIdentity(trainer_id="trainer-1", run_id=1)
    running = PostTrainingSaliencyStatus.pending(
        generation=1,
        run=run,
        training_generation=2,
        methods=("Gradient",),
    ).transition(
        generation=1,
        phase=PostTrainingSaliencyPhase.RUNNING,
    )
    port = _EvaluationApplicationPort()
    port.publication = _publication(
        generation=4,
        revision=4,
        evaluation_marker=4,
        trainer_identity=run.trainer_id,
        training_boundary_generation=2,
        post_training_saliency=running,
    )
    panel = _panel(qtbot, port)
    panel.update_panel()

    renders: list[int] = []
    panel.update_panel = lambda: renders.append(port.publication.revision)
    port.publication = _publication(
        generation=5,
        revision=5,
        evaluation_marker=4,
        trainer_identity=run.trainer_id,
        training_boundary_generation=4,
        post_training_saliency=running,
    )
    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)
    qtbot.wait(25)

    assert renders == []
    assert panel._last_application_revision == 5

    succeeded = running.transition(
        generation=1,
        phase=PostTrainingSaliencyPhase.SUCCEEDED,
    )
    port.publication = _publication(
        generation=6,
        revision=6,
        evaluation_marker=4,
        trainer_identity=run.trainer_id,
        training_boundary_generation=5,
        post_training_saliency=succeeded,
    )
    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)

    qtbot.waitUntil(lambda: renders == [6])


def test_evaluation_refreshes_when_trainer_identity_changes(qtbot) -> None:
    port = _EvaluationApplicationPort()
    port.publication = _publication(
        generation=4,
        revision=4,
        evaluation_marker=4,
        trainer_identity="trainer-1",
        training_boundary_generation=2,
    )
    panel = _panel(qtbot, port)
    panel.update_panel()

    renders: list[int] = []
    panel.update_panel = lambda: renders.append(port.publication.revision)
    port.publication = _publication(
        generation=5,
        revision=5,
        evaluation_marker=4,
        trainer_identity="trainer-2",
        training_boundary_generation=2,
    )

    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)

    qtbot.waitUntil(lambda: renders == [5])


def test_evaluation_coalesces_multiple_semantic_revisions_to_the_latest(qtbot) -> None:
    port = _EvaluationApplicationPort()
    panel = _panel(qtbot, port)
    panel.update_panel()

    renders: list[int] = []
    original_update = panel.update_panel

    def counted_update() -> None:
        renders.append(port.publication.revision)
        original_update()

    panel.update_panel = counted_update
    port.publication = _publication(generation=5, revision=5)
    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)
    port.publication = _publication(generation=6, revision=6)
    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)

    assert renders == []
    qtbot.waitUntil(lambda: renders == [6])
    assert port.query_calls == 2
    assert panel._last_application_revision == 6
    assert panel._application_generation == 6


def test_evaluation_model_summary_request_uses_latest_semantic_no_op_generation(
    qtbot,
    monkeypatch,
) -> None:
    port = _EvaluationApplicationPort()
    panel = _panel(qtbot, port)
    panel.update_panel()
    port.publication = _publication(
        generation=5,
        revision=5,
        evaluation_marker=4,
        last_error=ErrorSnapshot(error_type="TrainingError", message="Private detail"),
    )
    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)

    expected_generations: list[int | None] = []

    def capture_async(*_args, expected_publication_generation=None, **_kwargs):
        expected_generations.append(expected_publication_generation)
        return True

    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.execute_application_command_async",
        capture_async,
    )
    started = panel._refresh_application_query_async(
        summary_identity=EvaluationSummaryIdentity(
            plan=EvaluationPlanIdentity(plan_index=0),
        ),
    )

    assert started is True
    assert expected_generations == [5]


def test_evaluation_refreshes_for_terminal_outcome_change(qtbot) -> None:
    port = _EvaluationApplicationPort()
    panel = _panel(qtbot, port)
    panel.update_panel()

    renders: list[int] = []
    panel.update_panel = lambda: renders.append(port.publication.revision)
    port.publication = _publication(
        generation=5,
        revision=5,
        evaluation_marker=4,
        terminal_outcome=TrainingTerminalOutcome(
            state=TrainingOutcomeState.FAILED,
            detail="Safe terminal detail.",
        ),
    )

    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)

    qtbot.waitUntil(lambda: renders == [5])
    assert panel._last_application_revision == 5


def test_evaluation_keeps_transient_progress_out_of_render_refresh(qtbot) -> None:
    port = _EvaluationApplicationPort()
    panel = _panel(qtbot, port)
    panel.update_panel = MagicMock()

    port.notify("training_updated")

    panel.update_panel.assert_not_called()


def test_evaluation_close_unsubscribes_publication_safely(qtbot) -> None:
    port = _EvaluationApplicationPort()
    panel = _panel(qtbot, port)
    panel.update_panel = MagicMock()

    panel.close()
    panel.cleanup()
    port.publication = _publication(generation=5, revision=5)
    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)

    assert port.unsubscribe_calls == 1
    panel.update_panel.assert_not_called()


def test_evaluation_cleanup_cancels_queued_publication_refresh(qtbot) -> None:
    port = _EvaluationApplicationPort()
    panel = _panel(qtbot, port)
    panel.update_panel()
    panel.update_panel = MagicMock()
    panel.matrix_widget.cleanup = MagicMock()
    panel.bar_chart.cleanup = MagicMock()
    port.publication = _publication(generation=5, revision=5)

    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)
    assert panel._application_refresh_timer.isActive()
    panel.cleanup()
    qtbot.wait(25)

    assert not panel._application_refresh_timer.isActive()
    panel.update_panel.assert_not_called()
    panel.matrix_widget.cleanup.assert_called_once_with()
    panel.bar_chart.cleanup.assert_called_once_with()


def test_evaluation_render_exception_retries_internally_and_commits_on_success(
    qtbot,
) -> None:
    port = _EvaluationApplicationPort()
    panel = _panel(qtbot, port)
    panel.update_panel()
    port.publication = _publication(generation=5, revision=5)
    render_attempts: list[int] = []

    def render() -> None:
        render_attempts.append(port.publication.revision)
        if len(render_attempts) == 1:
            raise RuntimeError("transient Evaluation render failure")

    panel.update_panel = render

    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)
    qtbot.waitUntil(lambda: render_attempts == [5, 5])

    assert panel._last_application_revision == 5
    assert panel._application_render_ledger.pending_publication is None


def test_evaluation_stale_render_retries_without_error_log(
    qtbot,
    monkeypatch,
    caplog,
) -> None:
    port = _EvaluationApplicationPort()
    panel = _panel(qtbot, port)
    panel.update_panel()
    selection = EvaluationPlanIdentity(plan_index=0)
    panel._application_generation = port.publication.generation
    panel.run_combo.clear()
    panel.run_combo.addItem("Average", selection)
    panel.split_combo.clear()
    panel.split_combo.addItem("Test", "test")
    attempts = 0

    def stale_then_available(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ApplicationError(
                "Evaluation results changed while render data was being read.",
                diagnostics={
                    "evaluation_render_stale": True,
                    "retryable": True,
                },
            )

    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.get_evaluation_render_publication",
        stale_then_available,
    )
    caplog.set_level(logging.ERROR)

    assert panel._render_for_selection(selection, split="test") is None
    assert panel._evaluation_render_retry_timer.isActive()
    qtbot.waitUntil(lambda: attempts == 2)

    assert not [
        record
        for record in caplog.records
        if "Evaluation render publication failed" in record.getMessage()
    ]


def test_evaluation_publication_ledger_silently_retries_stale_render(
    qtbot,
    caplog,
) -> None:
    port = _EvaluationApplicationPort()
    panel = _panel(qtbot, port)
    panel.update_panel()
    caplog.set_level(logging.ERROR)
    panel.update_panel = MagicMock(
        side_effect=_RetryEvaluationPublicationRenderError("stale render")
    )
    port.publication = _publication(generation=5, revision=5)

    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)
    qtbot.waitUntil(lambda: panel.update_panel.call_count >= 2)
    panel.cleanup()

    assert not [
        record
        for record in caplog.records
        if "Evaluation application publication render failed" in record.getMessage()
    ]


def test_evaluation_cleanup_cancels_stale_render_retry(
    qtbot,
    monkeypatch,
) -> None:
    port = _EvaluationApplicationPort()
    panel = _panel(qtbot, port)
    panel.update_panel()
    selection = EvaluationPlanIdentity(plan_index=0)
    panel._application_generation = port.publication.generation
    panel.run_combo.clear()
    panel.run_combo.addItem("Average", selection)
    panel.split_combo.clear()
    panel.split_combo.addItem("Test", "test")
    attempts = 0

    def always_stale(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise ApplicationError(
            "Evaluation results changed while render data was being read.",
            diagnostics={
                "evaluation_render_stale": True,
                "retryable": True,
            },
        )

    monkeypatch.setattr(
        "XBrainLab.ui.panels.evaluation.panel.get_evaluation_render_publication",
        always_stale,
    )

    assert panel._render_for_selection(selection, split="test") is None
    assert panel._evaluation_render_retry_timer.isActive()
    panel.cleanup()
    qtbot.wait(100)

    assert attempts == 1
    assert not panel._evaluation_render_retry_timer.isActive()


def test_evaluation_exhausted_revision_recovers_from_newer_publication(qtbot) -> None:
    port = _EvaluationApplicationPort()
    panel = _panel(qtbot, port)
    panel.update_panel()
    render_attempts: list[int] = []

    def render() -> None:
        render_attempts.append(port.publication.revision)
        if port.publication.revision == 5:
            raise RuntimeError("persistent Evaluation render failure")

    panel.update_panel = render
    port.publication = _publication(generation=5, revision=5)
    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)
    qtbot.waitUntil(lambda: render_attempts == [5, 5, 5])
    qtbot.wait(100)

    assert render_attempts == [5, 5, 5]
    assert panel._last_application_revision == 4
    pending = panel._application_render_ledger.pending_publication
    assert pending is not None
    assert pending.revision == 5

    port.publication = _publication(generation=6, revision=6)
    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)
    qtbot.waitUntil(lambda: render_attempts[-1] == 6)

    assert panel._last_application_revision == 6


def test_evaluation_cleanup_cancels_scheduled_render_retry(qtbot) -> None:
    port = _EvaluationApplicationPort()
    panel = _panel(qtbot, port)
    panel.update_panel()
    attempts: list[int] = []

    def render() -> None:
        attempts.append(port.publication.revision)
        raise RuntimeError("retryable Evaluation render failure")

    panel.update_panel = render
    port.publication = _publication(generation=5, revision=5)
    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)
    qtbot.waitUntil(lambda: attempts == [5])
    assert panel._application_refresh_timer.isActive()

    panel.cleanup()
    qtbot.wait(100)

    assert attempts == [5]
    assert panel._application_render_ledger.pending_publication is None
