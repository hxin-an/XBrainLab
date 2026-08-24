from __future__ import annotations

from dataclasses import replace
from typing import Any, cast
from unittest.mock import MagicMock, patch

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget

from XBrainLab.backend.application import SaliencyCommand, VisualizeCommand
from XBrainLab.backend.application.commands import Command
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
from XBrainLab.backend.training_state_contract import TrainingReadBoundary
from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.panels.visualization.panel import VisualizationPanel


def _publication(
    *,
    generation: int,
    revision: int,
    visualization_marker: int | None = None,
    progress_message: str | None = None,
    irrelevant_summary: str | None = None,
    last_error: ErrorSnapshot | None = None,
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
        visualization=replace(
            initial.state.visualization,
            channel_count=marker,
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
        self.query_calls = 0
        self.unsubscribe_calls = 0

    def execute(
        self,
        command: Command,
        *,
        expected_publication_generation: int | None = None,
    ) -> CommandResult:
        assert expected_publication_generation in {
            None,
            self.publication.generation,
        }
        self.query_calls += 1
        if isinstance(command, SaliencyCommand):
            diagnostics = {
                "payload_type": "saliency_summary",
                "params": {},
            }
        else:
            assert isinstance(command, VisualizeCommand)
            diagnostics = {
                "payload_type": "visualization_summary",
                "available": True,
                "available_views": ["montage setup"],
                "plot_views_available": False,
            }
        return CommandResult.success_result(
            command_name=command.name.value,
            message="Visualization summary ready.",
            state=self.publication.state,
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


def _prime_panel(panel: VisualizationPanel) -> None:
    panel.update_panel()


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
    _prime_panel(panel)

    parent.study.get_controller.assert_not_called()
    assert panel.controller is None


def test_visualization_renders_once_for_one_new_application_revision(qtbot) -> None:
    port = _VisualizationApplicationPort()
    panel = _panel(qtbot, port)
    _prime_panel(panel)
    renders: list[int] = []
    panel.update_panel = lambda: renders.append(port.publication.revision)
    port.publication = _publication(generation=5, revision=5)

    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)

    assert renders == []
    qtbot.waitUntil(lambda: renders == [5])
    assert renders == [5]


def test_visualization_ignores_duplicate_and_stale_application_revisions(qtbot) -> None:
    port = _VisualizationApplicationPort()
    panel = _panel(qtbot, port)
    _prime_panel(panel)
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
    _prime_panel(panel)
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
    _prime_panel(panel)
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
    _prime_panel(panel)
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
    _prime_panel(panel)
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
    _prime_panel(panel)
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
    _prime_panel(panel)
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
