from __future__ import annotations

from dataclasses import replace
from threading import Event
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import QWidget

from XBrainLab.backend.application import (
    SaliencyCommand,
    SaliencyCrossFoldIdentity,
    VisualizeCommand,
)
from XBrainLab.backend.application.commands import Command
from XBrainLab.backend.application.results import ChangedState, CommandResult
from XBrainLab.backend.application.state import (
    ApplicationStateSnapshot,
    ErrorSnapshot,
    SaliencyClassCoverageSnapshot,
    SaliencyMethodCoverageSnapshot,
    SaliencyRunCoverageSnapshot,
    VisualizationStateSnapshot,
)
from XBrainLab.backend.application.view_publication import (
    APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
    ApplicationViewPublication,
    ApplicationViewStore,
)
from XBrainLab.backend.training_state_contract import TrainingReadBoundary
from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.async_command_runner import application_command_registry
from XBrainLab.ui.panels.visualization.panel import VisualizationPanel


def _publication(
    *,
    generation: int,
    revision: int,
    visualization_marker: int | None = None,
    progress_message: str | None = None,
    irrelevant_summary: str | None = None,
    last_error: ErrorSnapshot | None = None,
    visualization: VisualizationStateSnapshot | None = None,
) -> ApplicationViewPublication:
    initial = ApplicationViewStore(
        ApplicationStateSnapshot.empty(),
        TrainingReadBoundary.no_trainer(),
    ).read()
    marker = generation if visualization_marker is None else visualization_marker
    state = replace(
        initial.state,
        training=replace(
            initial.state.training,
            progress_message=progress_message,
        ),
        visualization=(
            visualization
            if visualization is not None
            else replace(initial.state.visualization, channel_count=marker)
        ),
        interpretation=replace(
            initial.state.interpretation,
            summary=irrelevant_summary,
        ),
        last_error=last_error,
    )
    return replace(
        initial,
        generation=generation,
        revision=revision,
        state=state,
    )


class _VisualizationApplicationPort(Observable):
    def __init__(self) -> None:
        super().__init__()
        self.publication = _publication(generation=4, revision=4)
        self.publication_after_visualize: ApplicationViewPublication | None = None
        self.notify_after_visualize = False
        self.visualization_diagnostics_by_generation: dict[int, dict[str, object]] = {}
        self.visualize_gate: Event | None = None
        self.visualize_entered: Event | None = None
        self.query_calls = 0
        self.unsubscribe_calls = 0

    def execute(
        self,
        command: Command,
        *,
        expected_publication_generation: int | None = None,
    ) -> CommandResult:
        assert expected_publication_generation is None or isinstance(
            expected_publication_generation,
            int,
        )
        self.query_calls += 1
        if isinstance(command, SaliencyCommand):
            diagnostics = {
                "payload_type": "saliency_summary",
                "params": {},
            }
        else:
            assert isinstance(command, VisualizeCommand)
            if self.visualize_gate is not None:
                if self.visualize_entered is not None:
                    self.visualize_entered.set()
                self.visualize_gate.wait(timeout=2)
            result_publication = self.publication
            diagnostics = {
                "payload_type": "visualization_summary",
                "available": True,
                "available_views": ["montage setup"],
                "plot_views_available": False,
                "visualization_publication_generation": result_publication.generation,
            }
            diagnostics.update(
                self.visualization_diagnostics_by_generation.get(
                    result_publication.generation,
                    {},
                )
            )
            if self.publication_after_visualize is not None:
                self.publication = self.publication_after_visualize
                self.publication_after_visualize = None
                if self.notify_after_visualize:
                    self.notify(
                        APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
                        self.publication,
                    )
        return CommandResult.success_result(
            command_name=command.name.value,
            message="Visualization summary ready.",
            state=(
                result_publication.state
                if isinstance(command, VisualizeCommand)
                else self.publication.state
            ),
            changed_state=ChangedState(),
            diagnostics=diagnostics,
        )

    def get_view_publication(self) -> ApplicationViewPublication:
        return self.publication

    def get_saliency_render(self, request):
        del request
        raise AssertionError("An empty run catalog must not request render data.")

    def unsubscribe(self, event_name, callback) -> None:
        self.unsubscribe_calls += 1
        super().unsubscribe(event_name, callback)


class _SaliencyWidgetStub(QWidget):
    class_selected = pyqtSignal(object)


def _widget_factory(parent=None):
    widget = cast(Any, _SaliencyWidgetStub(parent))
    widget.show_error = MagicMock()
    widget.show_message = MagicMock()
    widget.set_saliency_coverage = MagicMock()
    widget.set_post_training_saliency_status = MagicMock()
    widget.update_plot = MagicMock()
    widget.select_class_key = MagicMock()
    widget.invalidate_render_publication = MagicMock()
    widget.begin_render_shutdown = MagicMock()
    widget.cancel_render_shutdown = MagicMock()
    widget.native_render_work_idle = MagicMock(return_value=True)
    widget.finalize_native_render_resources = MagicMock(return_value=True)
    widget.native_render_resources_finalized = MagicMock(return_value=True)
    return widget


class _SidebarStub(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.update_info = MagicMock()
        self.refresh_view_controls = MagicMock()


def _panel(
    qtbot,
    port: _VisualizationApplicationPort,
    *,
    parent: QWidget | None = None,
) -> VisualizationPanel:
    with (
        patch(
            "XBrainLab.ui.panels.visualization.panel.ControlSidebar",
            _SidebarStub,
        ),
        patch(
            "XBrainLab.ui.panels.visualization.panel.SaliencyMapWidget",
            side_effect=_widget_factory,
        ),
        patch(
            "XBrainLab.ui.panels.visualization.panel.SaliencySpectrogramWidget",
            side_effect=_widget_factory,
        ),
        patch(
            "XBrainLab.ui.panels.visualization.panel.SaliencyTopographicMapWidget",
            side_effect=_widget_factory,
        ),
        patch(
            "XBrainLab.ui.panels.visualization.panel.Saliency3DPlotWidget",
            side_effect=_widget_factory,
        ),
    ):
        panel = VisualizationPanel(
            parent=parent,
            query_port=port,
            publication_port=port,
            action_port=port,
        )
    qtbot.addWidget(panel)
    return panel


def _prime_panel(panel: VisualizationPanel, qtbot) -> None:
    panel.update_panel()
    qtbot.waitUntil(lambda: panel.last_application_query is not None)


def test_visualization_instantiates_without_controller_or_controller_lookup(
    qtbot,
) -> None:
    port = _VisualizationApplicationPort()
    parent = cast(Any, QWidget())
    parent.study = MagicMock()
    parent.study.get_controller.side_effect = AssertionError(
        "Visualization must not resolve a broad controller."
    )
    qtbot.addWidget(parent)

    panel = _panel(qtbot, port, parent=parent)
    _prime_panel(panel, qtbot)

    parent.study.get_controller.assert_not_called()
    assert panel.controller is None


def test_visualization_renders_once_for_one_new_application_revision(qtbot) -> None:
    port = _VisualizationApplicationPort()
    panel = _panel(qtbot, port)
    _prime_panel(panel, qtbot)
    renders: list[int] = []
    panel.update_panel = lambda: renders.append(port.publication.revision)
    port.publication = _publication(generation=5, revision=5)

    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)

    assert renders == []
    qtbot.waitUntil(lambda: renders == [5])
    assert renders == [5]


def test_visualization_discards_a_summary_crossed_by_terminal_publication(
    qtbot,
) -> None:
    """Do not retain P1's Fold Set placeholder after P2 published saliency."""
    port = _VisualizationApplicationPort()
    panel = _panel(qtbot, port)
    port.publication_after_visualize = _publication(generation=5, revision=5)

    panel._refresh_application_query(view="Saliency Map")
    assert panel.last_application_query is None
    assert panel._application_summary_dirty is True
    qtbot.waitUntil(
        lambda: (
            panel._application_view_publication is not None
            and panel._application_view_publication.generation == 5
        )
    )
    accepted = panel._application_view_publication
    assert accepted is not None
    assert accepted.generation == 5

    # The next normal panel refresh reads P2, rather than offering P1's stale
    # cross-fold placeholder as an incomplete result that needs recomputation.
    panel._refresh_application_query(view="Saliency Map")
    qtbot.waitUntil(lambda: panel.last_application_query is not None)
    assert (
        panel.last_application_query.diagnostics["visualization_publication_generation"]
        == 5
    )


def test_visualization_summary_query_keeps_qt_and_selectors_responsive(qtbot) -> None:
    """A held summary query must not occupy the Qt event loop."""
    port = _VisualizationApplicationPort()
    port.visualize_gate = Event()
    port.visualize_entered = Event()
    panel = _panel(qtbot, port)
    ticks: list[bool] = []

    panel._refresh_application_query(view="Saliency Map")
    qtbot.waitUntil(port.visualize_entered.is_set, timeout=500)
    QTimer.singleShot(0, lambda: ticks.append(True))
    qtbot.waitUntil(lambda: bool(ticks), timeout=500)
    assert not port.visualize_gate.is_set()
    assert application_command_registry().active_count(panel) > 0
    assert panel.plan_combo.isEnabled()
    assert panel.run_combo.isEnabled()
    port.visualize_gate.set()
    qtbot.waitUntil(lambda: application_command_registry().active_count(panel) == 0)


def test_visualization_cleanup_ignores_a_late_summary_callback(qtbot) -> None:
    """Closing a panel fences its held summary-query callback."""
    port = _VisualizationApplicationPort()
    port.visualize_gate = Event()
    port.visualize_entered = Event()
    panel = _panel(qtbot, port)

    panel._refresh_application_query(view="Saliency Map")
    qtbot.waitUntil(port.visualize_entered.is_set, timeout=500)
    panel.cleanup()
    port.visualize_gate.set()
    qtbot.waitUntil(lambda: application_command_registry().active_count(panel) == 0)
    assert panel.last_application_query is None


@pytest.mark.parametrize("refresh_method", ("on_update", "update_panel"))
def test_visualization_summary_start_refusal_settles_once_publicly(
    qtbot,
    monkeypatch,
    refresh_method,
) -> None:
    port = _VisualizationApplicationPort()
    panel = _panel(qtbot, port)
    attempts = 0

    def refuse(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        return False

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command_async",
        refuse,
    )

    getattr(panel, refresh_method)()
    assert panel.last_application_query is not None
    assert panel.last_application_query.failed
    assert panel._application_summary_dirty is False
    current_widget = panel.tabs.currentWidget()
    assert current_widget is not None
    current_widget.show_message.assert_called()
    qtbot.wait(100)
    assert attempts == 1


@pytest.mark.parametrize("refresh_method", ("on_update", "update_panel"))
def test_visualization_summary_worker_error_settles_once_publicly(
    qtbot,
    monkeypatch,
    refresh_method,
) -> None:
    port = _VisualizationApplicationPort()
    panel = _panel(qtbot, port)
    attempts = 0

    def fail(_panel, _command, *, on_error, **_kwargs):
        nonlocal attempts
        attempts += 1
        QTimer.singleShot(
            0,
            lambda: on_error((RuntimeError, RuntimeError("held read failed"), "trace")),
        )
        return True

    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.panel.execute_application_command_async",
        fail,
    )
    getattr(panel, refresh_method)()
    qtbot.waitUntil(
        lambda: panel.last_application_query is not None
        and panel.last_application_query.failed
        and panel._application_summary_dirty is False,
    )
    current_widget = panel.tabs.currentWidget()
    assert current_widget is not None
    current_widget.show_message.assert_called()
    qtbot.wait(100)
    assert attempts == 1


@pytest.mark.parametrize("refresh_method", ("on_update", "update_panel"))
def test_visualization_retries_cross_fold_summary_after_terminal_publication(
    qtbot,
    refresh_method,
) -> None:
    """A selected Fold Set automatically renders P2, never P1's placeholder."""
    members = [
        {"plan_index": 0, "run_index": 0},
        {"plan_index": 1, "run_index": 0},
    ]
    placeholder = {
        "identity": {"members": members},
        "display_name": "All Folds",
        "run_label": "Run 1 (Summary)",
        "methods": [],
        "classes": [],
    }
    renderable = {
        **placeholder,
        "methods": ["Gradient"],
        "classes": [
            {
                "class_index": 0,
                "display_name": "left",
                "event_code": 0,
                "store_key": 0,
            },
        ],
    }
    coverage = SaliencyMethodCoverageSnapshot(
        method="Gradient",
        available=True,
        complete=True,
        classes=[
            SaliencyClassCoverageSnapshot(
                class_index=0,
                display_name="left",
                event_code=0,
                store_key=0,
                available=True,
            ),
        ],
    )
    p2 = _publication(
        generation=5,
        revision=5,
        visualization=VisualizationStateSnapshot(
            saliency_available=True,
            saliency_coverage=[
                SaliencyRunCoverageSnapshot(
                    plan_index=index,
                    run_index=0,
                    model_name="EEGNet",
                    methods=[coverage],
                )
                for index in range(2)
            ],
        ),
    )
    port = _VisualizationApplicationPort()
    port.visualization_diagnostics_by_generation[4] = {
        "evaluation_cross_fold_choices": [placeholder],
        "saliency_cross_fold_choices": [],
        "available_views": ["Saliency Map"],
        "plot_views_available": True,
    }
    port.visualization_diagnostics_by_generation[5] = {
        "evaluation_cross_fold_choices": [placeholder],
        "saliency_cross_fold_choices": [renderable],
        "available_views": ["Saliency Map"],
        "plot_views_available": True,
    }
    panel = _panel(qtbot, port)
    panel.update_panel()
    qtbot.waitUntil(lambda: panel.run_combo.currentData() is not None)
    selected = panel.run_combo.currentData()
    assert isinstance(selected, SaliencyCrossFoldIdentity)

    port.publication_after_visualize = p2
    port.notify_after_visualize = True
    panel._application_summary_dirty = True
    requested = MagicMock()
    with patch.object(panel, "_request_saliency_render", requested):
        getattr(panel, refresh_method)()
        qtbot.waitUntil(
            lambda: (
                panel.last_application_query is not None
                and panel.last_application_query.diagnostics.get(
                    "visualization_publication_generation"
                )
                == 5
                and requested.called
            ),
            timeout=3000,
        )

    assert panel.run_combo.currentData() == selected
    task = requested.call_args.args[0]
    assert task.request.run == selected
    assert task.request.publication_generation == 5


def test_visualization_ignores_duplicate_and_stale_application_revisions(qtbot) -> None:
    port = _VisualizationApplicationPort()
    panel = _panel(qtbot, port)
    _prime_panel(panel, qtbot)
    renders: list[int] = []
    panel.update_panel = lambda: renders.append(port.publication.revision)
    port.publication = _publication(generation=5, revision=5)

    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)
    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)
    port.notify(
        APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
        _publication(generation=3, revision=3),
    )

    assert renders == []
    qtbot.waitUntil(lambda: renders == [5])
    assert renders == [5]


def test_visualization_ignores_irrelevant_application_revision(qtbot) -> None:
    port = _VisualizationApplicationPort()
    panel = _panel(qtbot, port)
    _prime_panel(panel, qtbot)
    panel.update_panel = MagicMock()
    port.publication = _publication(
        generation=5,
        revision=5,
        visualization_marker=4,
        irrelevant_summary="A Data Import-only change.",
        last_error=ErrorSnapshot(
            error_type="ImportError",
            message="A private import diagnostic.",
        ),
    )

    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)
    qtbot.wait(25)

    panel.update_panel.assert_not_called()
    assert panel._last_application_revision == 5


def test_visualization_ignores_progress_only_application_revision(qtbot) -> None:
    port = _VisualizationApplicationPort()
    panel = _panel(qtbot, port)
    _prime_panel(panel, qtbot)
    panel.update_panel = MagicMock()
    port.publication = _publication(
        generation=5,
        revision=5,
        visualization_marker=4,
        progress_message="Epoch 12 of 40",
    )

    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)
    qtbot.wait(25)

    panel.update_panel.assert_not_called()
    assert panel._last_application_revision == 5


def test_visualization_cleanup_cancels_queued_publication_refresh(qtbot) -> None:
    port = _VisualizationApplicationPort()
    panel = _panel(qtbot, port)
    _prime_panel(panel, qtbot)
    panel.update_panel = MagicMock()
    port.publication = _publication(generation=5, revision=5)

    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)
    assert panel._application_refresh_timer.isActive()
    panel.cleanup()
    panel.cleanup()
    qtbot.wait(25)

    assert not panel._application_refresh_timer.isActive()
    assert port.unsubscribe_calls == 1
    panel.update_panel.assert_not_called()


def test_visualization_render_exception_retries_internally_and_commits_on_success(
    qtbot,
) -> None:
    port = _VisualizationApplicationPort()
    panel = _panel(qtbot, port)
    _prime_panel(panel, qtbot)
    port.publication = _publication(generation=5, revision=5)
    attempts: list[int] = []

    def render() -> None:
        attempts.append(port.publication.revision)
        if len(attempts) == 1:
            raise RuntimeError("transient Visualization render failure")

    panel.update_panel = render

    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)
    qtbot.waitUntil(lambda: attempts == [5, 5])

    assert panel._last_application_revision == 5
    assert panel._application_render_ledger.pending_publication is None


def test_visualization_exhausted_revision_recovers_from_newer_publication(
    qtbot,
) -> None:
    port = _VisualizationApplicationPort()
    panel = _panel(qtbot, port)
    _prime_panel(panel, qtbot)
    attempts: list[int] = []

    def render() -> None:
        attempts.append(port.publication.revision)
        if port.publication.revision == 5:
            raise RuntimeError("persistent Visualization render failure")

    panel.update_panel = render
    port.publication = _publication(generation=5, revision=5)
    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)
    qtbot.waitUntil(lambda: attempts == [5, 5, 5])
    qtbot.wait(100)

    assert attempts == [5, 5, 5]
    assert panel._last_application_revision == 4
    pending = panel._application_render_ledger.pending_publication
    assert pending is not None
    assert pending.revision == 5

    port.publication = _publication(generation=6, revision=6)
    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)
    qtbot.waitUntil(lambda: attempts[-1] == 6)

    assert panel._last_application_revision == 6


def test_visualization_cleanup_cancels_scheduled_render_retry(qtbot) -> None:
    port = _VisualizationApplicationPort()
    panel = _panel(qtbot, port)
    _prime_panel(panel, qtbot)
    attempts: list[int] = []

    def render() -> None:
        attempts.append(port.publication.revision)
        raise RuntimeError("retryable Visualization render failure")

    panel.update_panel = render
    port.publication = _publication(generation=5, revision=5)
    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)
    qtbot.waitUntil(lambda: attempts == [5])
    assert panel._application_refresh_timer.isActive()

    panel.cleanup()
    qtbot.wait(100)

    assert attempts == [5]
    assert panel._application_render_ledger.pending_publication is None
