import sys
from copy import deepcopy
from dataclasses import replace
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication

from XBrainLab.backend.application import (
    ApplicationStateSnapshot,
    ApplicationViewPublication,
    CapabilityPolicy,
    CommandCapability,
    CommandName,
    ErrorType,
)
from XBrainLab.backend.application.results import ChangedState, CommandResult
from XBrainLab.backend.training_state_contract import (
    TrainingOutcomeState,
    TrainingTerminalOutcome,
)
from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.application_capabilities import TRAINING_PROGRESS_UPDATED_EVENT
from XBrainLab.ui.panels.training.panel import TrainingPanel

app = QApplication.instance() or QApplication(sys.argv)


def _typed_training_ports(history_query=None):
    ports = Observable()
    ports.get_view_publication = MagicMock(
        return_value=ApplicationViewPublication(
            generation=1,
            revision=1,
            state=ApplicationStateSnapshot.empty(),
            capabilities=CapabilityPolicy(
                {
                    CommandName.TRAIN.value: CommandCapability(
                        command_name=CommandName.TRAIN.value,
                        enabled=False,
                        reasons=["Training is not ready."],
                    )
                }
            ),
            verified=True,
            stale=False,
        )
    )
    ports.query_training_history = history_query or MagicMock()
    ports.query_training_state = MagicMock(return_value=None)
    ports.execute = MagicMock(return_value=None)
    return ports


def _panel(ports):
    return TrainingPanel(
        query_port=ports,
        publication_port=ports,
        action_port=ports,
        transient_port=ports,
    )


def _history_row(*, status="Running", epochs=(0.7,), run_index=0):
    return {
        "identity": {"plan_index": 0, "run_index": run_index},
        "group_name": "Group 1",
        "run_name": str(run_index + 1),
        "model_name": "EEGNet",
        "status": status,
        "epoch": len(epochs),
        "max_epochs": len(epochs),
        "is_active": status == "Running",
        "is_current_run": status == "Running",
        "metrics": {
            "train": {"accuracy": list(epochs), "loss": [1 - value for value in epochs]}
        },
    }


def test_training_panel_acknowledges_unrelated_publication_without_redraw(qtbot):
    ports = _typed_training_ports()
    panel = _panel(ports)
    qtbot.addWidget(panel)
    initial = ports.get_view_publication()

    with patch.object(panel, "update_panel") as update_panel:
        assert panel._on_application_view_publication_changed(initial)
        qtbot.waitUntil(lambda: panel._last_application_revision == 1)
        assert update_panel.call_count == 1
        update_panel.reset_mock()

        unrelated = replace(
            initial,
            generation=2,
            revision=2,
            state=replace(
                initial.state,
                visualization=replace(
                    initial.state.visualization, saliency_configured=True
                ),
            ),
        )
        assert panel._on_application_view_publication_changed(unrelated)
        qtbot.waitUntil(lambda: panel._last_application_revision == 2)
        update_panel.assert_not_called()


def test_training_panel_reads_history_from_matching_publication(qtbot):
    query_history = MagicMock(side_effect=AssertionError("must not read mutable state"))
    ports = _typed_training_ports(query_history)
    panel = _panel(ports)
    qtbot.addWidget(panel)
    publication = replace(
        ports.get_view_publication(),
        training_history=(
            {
                "identity": {"plan_index": 0, "run_index": 0},
                "group_name": "Group 1",
                "run_name": "1",
                "model_name": "EEGNet",
                "status": "Completed",
                "epoch": 1,
                "max_epochs": 1,
                "is_active": False,
                "is_current_run": False,
                "metrics": {"train": {"accuracy": [0.75], "loss": [0.5]}},
            },
        ),
    )
    ports.get_view_publication.return_value = publication
    panel._application_view_publication = publication

    rows = panel._history_for_render()

    assert rows is not None
    assert rows[0]["status"] == "Completed"
    query_history.assert_not_called()


def test_training_panel_queries_history_at_matching_generation(qtbot):
    ports = _typed_training_ports(
        MagicMock(
            return_value=CommandResult.success_result(
                "history",
                "history",
                {},
                changed_state=ChangedState(),
                diagnostics={"payload_type": "training_history", "rows": []},
            )
        )
    )
    panel = _panel(ports)
    qtbot.addWidget(panel)

    assert panel._history_for_render() == []
    ports.query_training_history.assert_called_once_with(
        expected_publication_generation=1
    )


def test_training_panel_progress_event_refreshes_without_controller(qtbot):
    ports = _typed_training_ports()
    panel = _panel(ports)
    qtbot.addWidget(panel)
    panel.update_loop = MagicMock()

    ports.notify(TRAINING_PROGRESS_UPDATED_EVENT)
    qtbot.waitUntil(lambda: panel.update_loop.called)

    panel.update_loop.assert_called_once_with(log_epochs=True)


def test_training_panel_renders_running_and_terminal_publication(qtbot):
    ports = _typed_training_ports()
    panel = _panel(ports)
    qtbot.addWidget(panel)
    initial = ports.get_view_publication()
    started = replace(
        initial,
        state=replace(
            initial.state, training=replace(initial.state.training, is_running=True)
        ),
    )
    panel._render_training_publication(started)
    assert panel.sidebar.btn_stop.isEnabled()

    completed = replace(
        started,
        state=replace(
            started.state,
            training=replace(
                started.state.training,
                is_running=False,
                terminal_outcome=TrainingTerminalOutcome(
                    TrainingOutcomeState.COMPLETED
                ),
            ),
        ),
    )
    panel._render_training_publication(completed)
    assert not panel.sidebar.btn_stop.isEnabled()


def test_training_panel_preserves_rendered_history_plots_and_logs_until_query_recovers(
    qtbot,
):
    ports = _typed_training_ports()
    panel = _panel(ports)
    qtbot.addWidget(panel)
    initial = ports.get_view_publication()
    row = _history_row(epochs=(0.7, 0.8))
    published = replace(initial, training_history=(deepcopy(row),))
    ports.get_view_publication.return_value = published
    panel._application_view_publication = published
    panel.update_loop(log_epochs=True)
    before_log = panel.log_text.toPlainText()
    assert panel.history_table.rowCount() == 1
    assert panel.tab_acc.train_vals == [0.7, 0.8]

    unavailable = replace(published, generation=2, revision=2, training_history=None)
    ports.get_view_publication.return_value = unavailable
    panel._application_view_publication = unavailable
    ports.query_training_history = MagicMock(
        return_value=CommandResult.failure_result(
            "history",
            "unavailable",
            None,
            ChangedState(),
            ErrorType.PRECONDITION,
            True,
        )
    )
    panel.update_loop(log_epochs=True)
    assert panel.history_table.rowCount() == 1
    assert panel.tab_acc.train_vals == [0.7, 0.8]
    assert panel.log_text.toPlainText() == before_log

    recovered_row = _history_row(status="Completed", epochs=(0.7, 0.8, 0.9))
    ports.query_training_history.return_value = CommandResult.success_result(
        "history",
        "history",
        {},
        ChangedState(),
        diagnostics={"payload_type": "training_history", "rows": [recovered_row]},
    )
    panel.update_loop(log_epochs=True)
    assert panel.history_table.item(0, 3).text() == "Completed"
    assert panel.tab_acc.train_vals == [0.7, 0.8, 0.9]


def test_training_panel_clears_render_only_for_a_verified_empty_history(qtbot):
    ports = _typed_training_ports()
    panel = _panel(ports)
    qtbot.addWidget(panel)
    publication = replace(
        ports.get_view_publication(), training_history=(deepcopy(_history_row()),)
    )
    ports.get_view_publication.return_value = publication
    panel._application_view_publication = publication
    panel.update_loop()
    assert panel.history_table.rowCount() == 1

    empty = replace(publication, generation=2, revision=2, training_history=())
    ports.get_view_publication.return_value = empty
    panel._application_view_publication = empty
    panel.update_loop()
    assert panel.history_table.rowCount() == 0
    assert panel.current_plotting_identity is None
    assert panel.tab_acc.train_vals == []


def test_training_panel_preserves_manual_history_selection_across_publication_updates(
    qtbot,
):
    ports = _typed_training_ports()
    panel = _panel(ports)
    qtbot.addWidget(panel)
    initial = ports.get_view_publication()
    old = {
        "identity": {"plan_index": 0, "run_index": 0},
        "group_name": "Group 1",
        "run_name": "1",
        "model_name": "EEGNet",
        "status": "Completed",
        "epoch": 2,
        "max_epochs": 2,
        "is_active": False,
        "is_current_run": False,
        "metrics": {"train": {"accuracy": [0.7, 0.8], "loss": [0.6, 0.5]}},
    }
    active = {
        "identity": {"plan_index": 0, "run_index": 1},
        "group_name": "Group 1",
        "run_name": "2",
        "model_name": "EEGNet",
        "status": "Running",
        "epoch": 1,
        "max_epochs": 3,
        "is_active": True,
        "is_current_run": True,
        "metrics": {"train": {"accuracy": [0.75], "loss": [0.55]}},
    }
    publication = replace(initial, training_history=(old, active))
    ports.get_view_publication.return_value = publication
    panel._application_view_publication = publication
    panel.update_loop()
    assert panel.current_plotting_identity == (0, 1)
    panel.on_history_selection_changed({"plan_index": 0, "run_index": 0})
    assert panel.current_plotting_identity == (0, 0)

    active["metrics"]["train"]["accuracy"].append(0.81)
    refreshed = replace(
        publication, generation=2, revision=2, training_history=(old, active)
    )
    ports.get_view_publication.return_value = refreshed
    panel._application_view_publication = refreshed
    panel.update_loop(log_epochs=True)
    assert panel.current_plotting_identity == (0, 0)
    assert panel.tab_acc.train_vals == [0.7, 0.8]


def test_training_panel_close_releases_metric_canvases(qtbot):
    ports = _typed_training_ports()
    panel = _panel(ports)
    qtbot.addWidget(panel)
    panel.show()
    canvases = [panel.tab_acc.canvas, panel.tab_loss.canvas]
    for canvas in canvases:
        canvas._draw_pending = True

    panel.close()
    qtbot.wait(0)

    assert panel.tab_acc.canvas is None
    assert panel.tab_loss.canvas is None
    assert all(canvas._draw_pending is False for canvas in canvases)


def test_training_panel_delayed_transient_tick_keeps_terminal_render_idempotent(qtbot):
    ports = _typed_training_ports()
    panel = _panel(ports)
    qtbot.addWidget(panel)
    initial = ports.get_view_publication()
    completed_row = _history_row(status="Completed", epochs=(0.7,))
    terminal = replace(
        initial,
        generation=2,
        revision=2,
        state=replace(
            initial.state,
            training=replace(
                initial.state.training,
                is_running=False,
                terminal_outcome=TrainingTerminalOutcome(
                    TrainingOutcomeState.COMPLETED
                ),
            ),
        ),
        training_history=(deepcopy(completed_row),),
    )
    ports.get_view_publication.return_value = terminal
    panel._application_view_publication = terminal
    panel._render_training_publication(terminal)
    panel.update_loop(log_epochs=True)
    before_log = panel.log_text.toPlainText()
    before_identity = panel.current_plotting_identity

    ports.notify(TRAINING_PROGRESS_UPDATED_EVENT)
    qtbot.waitUntil(lambda: panel.log_text.toPlainText() == before_log)
    assert panel.current_plotting_identity == before_identity
    assert panel.sidebar.btn_stop.isEnabled() is False
