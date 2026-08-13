from __future__ import annotations

import logging
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QWidget

from XBrainLab.backend.application import (
    APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
    ApplicationViewPublication,
    QueryStateCommand,
    get_application_service,
)
from XBrainLab.backend.application.results import ChangedState, CommandResult
from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.application_capabilities import (
    execute_application_command,
    execute_application_command_async,
)
from XBrainLab.ui.panels.dataset.panel import DatasetPanel
from XBrainLab.ui.panels.preprocess.panel import PreprocessPanel
from XBrainLab.ui.panels.training.panel import TrainingPanel


class _PublicationPort(Observable):
    def __init__(self) -> None:
        super().__init__()
        baseline = get_application_service(Study()).get_view_publication()
        self.publication = replace(
            baseline,
            generation=baseline.generation + 1,
            revision=baseline.revision + 1,
        )

    def get_view_publication(self) -> ApplicationViewPublication:
        return self.publication


def _training_controller() -> Observable:
    controller = Observable()
    cast(Any, controller).validate_ready = MagicMock(return_value=False)
    cast(Any, controller).has_datasets = MagicMock(return_value=False)
    cast(Any, controller).has_model = MagicMock(return_value=False)
    cast(Any, controller).has_training_option = MagicMock(return_value=False)
    cast(Any, controller).get_formatted_history = MagicMock(return_value=[])
    return controller


_PRIMARY_PANEL_KINDS = ("dataset", "preprocess", "training")


def _make_primary_panel(panel_kind: str, port: _PublicationPort) -> Any:
    if panel_kind == "dataset":
        return DatasetPanel(
            controller=Observable(),
            publication_port=port,
        )
    if panel_kind == "preprocess":
        return PreprocessPanel(
            controller=Observable(),
            dataset_controller=Observable(),
            publication_port=port,
        )
    if panel_kind == "training":
        return TrainingPanel(
            controller=_training_controller(),
            dataset_controller=Observable(),
            preprocess_controller=Observable(),
            publication_port=port,
        )
    raise AssertionError(f"Unknown primary panel kind: {panel_kind}")


def _publish_revision(port: _PublicationPort, revision: int) -> None:
    port.publication = replace(port.publication, revision=revision)
    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)


@pytest.mark.parametrize("panel_kind", _PRIMARY_PANEL_KINDS)
def test_primary_panel_commits_revision_only_after_render_succeeds(
    qtbot,
    panel_kind: str,
) -> None:
    port = _PublicationPort()
    panel = _make_primary_panel(panel_kind, port)
    qtbot.addWidget(panel)
    revision = port.publication.revision + 2
    rendered_ledger_during_render: list[int] = []
    panel.update_panel = lambda: rendered_ledger_during_render.append(
        panel._last_application_revision
    )

    _publish_revision(port, revision)

    assert panel._last_application_revision == 0
    assert rendered_ledger_during_render == []
    qtbot.waitUntil(lambda: rendered_ledger_during_render == [0])
    assert panel._last_application_revision == revision


@pytest.mark.parametrize("panel_kind", _PRIMARY_PANEL_KINDS)
def test_primary_panel_render_exception_retries_internally_before_committing_revision(
    qtbot,
    panel_kind: str,
) -> None:
    port = _PublicationPort()
    panel = _make_primary_panel(panel_kind, port)
    qtbot.addWidget(panel)
    revision = port.publication.revision + 2
    render_attempts: list[int] = []

    def render() -> None:
        render_attempts.append(revision)
        if len(render_attempts) == 1:
            raise RuntimeError("transient render failure")

    panel.update_panel = render

    _publish_revision(port, revision)
    qtbot.waitUntil(lambda: render_attempts == [revision, revision])

    assert panel._last_application_revision == revision
    assert panel._application_render_ledger.pending_publication is None


@pytest.mark.parametrize("panel_kind", _PRIMARY_PANEL_KINDS)
def test_primary_panel_retry_exhaustion_enters_low_frequency_recovery(
    qtbot,
    panel_kind: str,
) -> None:
    port = _PublicationPort()
    panel = _make_primary_panel(panel_kind, port)
    qtbot.addWidget(panel)
    failed_revision = port.publication.revision + 2
    recovery_revision = failed_revision + 1
    render_attempts: list[int] = []

    def render() -> None:
        publication = panel._application_view_publication
        assert publication is not None
        render_attempts.append(publication.revision)
        if publication.revision == failed_revision:
            raise RuntimeError("persistent render failure")

    panel.update_panel = render

    _publish_revision(port, failed_revision)
    qtbot.waitUntil(
        lambda: render_attempts == [failed_revision, failed_revision, failed_revision]
    )
    qtbot.wait(100)

    assert render_attempts == [failed_revision, failed_revision, failed_revision]
    assert panel._last_application_revision == 0
    assert panel._application_render_ledger.pending_publication.revision == (
        failed_revision
    )
    assert panel._application_refresh_timer.isActive()

    _publish_revision(port, recovery_revision)
    qtbot.waitUntil(lambda: render_attempts[-1] == recovery_revision)

    assert panel._last_application_revision == recovery_revision
    assert panel._application_render_ledger.pending_publication is None


@pytest.mark.parametrize("panel_kind", _PRIMARY_PANEL_KINDS)
def test_primary_panel_newer_revision_rearms_during_retry_backoff(
    qtbot,
    panel_kind: str,
) -> None:
    port = _PublicationPort()
    panel = _make_primary_panel(panel_kind, port)
    qtbot.addWidget(panel)
    first_revision = port.publication.revision + 2
    newest_revision = first_revision + 1
    render_attempts: list[int] = []

    def render() -> None:
        publication = panel._application_view_publication
        assert publication is not None
        render_attempts.append(publication.revision)
        if publication.revision == first_revision:
            raise RuntimeError("retryable render failure")

    panel.update_panel = render

    _publish_revision(port, first_revision)
    qtbot.waitUntil(lambda: render_attempts == [first_revision])
    assert panel._application_refresh_timer.isActive()

    _publish_revision(port, newest_revision)
    qtbot.waitUntil(lambda: render_attempts[-1] == newest_revision)

    assert render_attempts == [first_revision, newest_revision]
    assert panel._last_application_revision == newest_revision


@pytest.mark.parametrize("panel_kind", _PRIMARY_PANEL_KINDS)
def test_primary_panel_coalesces_pending_revisions_to_newest(
    qtbot,
    panel_kind: str,
) -> None:
    port = _PublicationPort()
    panel = _make_primary_panel(panel_kind, port)
    qtbot.addWidget(panel)
    first_revision = port.publication.revision + 2
    newest_revision = first_revision + 1
    renders: list[int] = []
    panel.update_panel = lambda: renders.append(
        panel._application_view_publication.revision
    )

    _publish_revision(port, first_revision)
    _publish_revision(port, newest_revision)

    assert renders == []
    qtbot.waitUntil(lambda: renders == [newest_revision])
    assert panel._last_application_revision == newest_revision
    assert panel._application_render_ledger.pending_publication is None


@pytest.mark.parametrize("panel_kind", _PRIMARY_PANEL_KINDS)
def test_primary_panel_cleanup_cancels_pending_revision_without_render(
    qtbot,
    panel_kind: str,
) -> None:
    port = _PublicationPort()
    panel = _make_primary_panel(panel_kind, port)
    qtbot.addWidget(panel)
    revision = port.publication.revision + 2
    panel.update_panel = MagicMock()

    _publish_revision(port, revision)
    panel.cleanup()
    qtbot.wait(25)

    panel.update_panel.assert_not_called()
    assert panel._last_application_revision == 0
    assert panel._application_render_ledger.pending_publication is None


@pytest.mark.parametrize("panel_kind", _PRIMARY_PANEL_KINDS)
def test_primary_panel_does_not_redraw_successful_duplicate_or_stale_revision(
    qtbot,
    panel_kind: str,
) -> None:
    port = _PublicationPort()
    panel = _make_primary_panel(panel_kind, port)
    qtbot.addWidget(panel)
    revision = port.publication.revision + 3
    renders: list[int] = []
    panel.update_panel = lambda: renders.append(
        panel._application_view_publication.revision
    )

    _publish_revision(port, revision)
    qtbot.waitUntil(lambda: renders == [revision])

    _publish_revision(port, revision)
    _publish_revision(port, revision - 1)
    qtbot.wait(25)

    assert renders == [revision]
    assert panel._last_application_revision == revision


@pytest.mark.parametrize("panel_kind", _PRIMARY_PANEL_KINDS)
def test_primary_panel_cleanup_cancels_scheduled_render_retry(
    qtbot,
    panel_kind: str,
) -> None:
    port = _PublicationPort()
    panel = _make_primary_panel(panel_kind, port)
    qtbot.addWidget(panel)
    revision = port.publication.revision + 2
    render_attempts: list[int] = []

    def render() -> None:
        render_attempts.append(revision)
        raise RuntimeError("retryable render failure")

    panel.update_panel = render

    _publish_revision(port, revision)
    qtbot.waitUntil(lambda: render_attempts == [revision])
    assert panel._application_refresh_timer.isActive()

    panel.cleanup()
    qtbot.wait(100)

    assert render_attempts == [revision]
    assert not panel._application_refresh_timer.isActive()
    assert panel._application_render_ledger.pending_publication is None


def test_dataset_state_render_is_driven_only_by_application_publication(qtbot) -> None:
    controller = Observable()
    port = _PublicationPort()
    panel = DatasetPanel(controller=controller, publication_port=port)
    qtbot.addWidget(panel)
    renders: list[int] = []
    cast(Any, panel).update_panel = lambda: renders.append(port.publication.revision)

    controller.notify("data_changed")
    qtbot.wait(25)
    assert renders == []

    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)
    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)

    assert renders == []
    qtbot.waitUntil(lambda: renders == [port.publication.revision])


def test_dataset_query_failure_stays_pending_until_rows_can_be_rendered(
    qtbot,
) -> None:
    """A failed read-side query must not masquerade as an empty Dataset."""
    port = _PublicationPort()
    panel = DatasetPanel(controller=Observable(), publication_port=port)
    qtbot.addWidget(panel)
    panel.sidebar.update_sidebar = MagicMock()
    revision = port.publication.revision + 2
    query_result = MagicMock(failed=True, diagnostics={})

    with pytest.MonkeyPatch.context() as monkeypatch:
        execute = MagicMock(return_value=query_result)
        monkeypatch.setattr(
            "XBrainLab.ui.panels.dataset.panel.execute_application_command",
            execute,
        )

        _publish_revision(port, revision)
        qtbot.waitUntil(lambda: execute.call_count >= 1)

        assert panel._last_application_revision == 0
        assert panel._application_render_ledger.pending_publication is not None
        assert panel._application_render_ledger.pending_publication.revision == revision
        assert panel.data_surface.currentWidget() is panel.empty_state
        assert panel.empty_state_title.text() == "Dataset view unavailable"
        assert panel.empty_state_title.text() != "No EEG data loaded"

        query_result.failed = False
        query_result.diagnostics = {"raw_rows": []}
        qtbot.waitUntil(lambda: panel._last_application_revision == revision)

    assert panel._application_render_ledger.pending_publication is None
    assert panel.empty_state_title.text() == "No EEG data loaded"


@pytest.mark.parametrize(
    ("diagnostics", "message"),
    (
        (
            {"application_busy": True},
            "Application state is changing. Retry this query shortly.",
        ),
        (
            {"stale_publication": True},
            "Workflow state changed while this confirmed action was pending.",
        ),
    ),
)
def test_dataset_retryable_query_failure_preserves_visible_rows_without_error_log(
    qtbot,
    caplog,
    diagnostics,
    message,
) -> None:
    """A busy application read is normal publication backpressure, not data loss."""
    port = _PublicationPort()
    panel = DatasetPanel(controller=Observable(), publication_port=port)
    qtbot.addWidget(panel)
    panel.sidebar.update_sidebar = MagicMock()
    panel.table.setRowCount(1)
    panel.data_surface.setCurrentWidget(panel.table)
    revision = port.publication.revision + 2
    query_result = MagicMock(
        failed=True,
        recoverable=True,
        message=message,
        diagnostics=diagnostics,
    )

    caplog.set_level(logging.ERROR)
    with pytest.MonkeyPatch.context() as monkeypatch:
        execute = MagicMock(return_value=query_result)
        monkeypatch.setattr(
            "XBrainLab.ui.panels.dataset.panel.execute_application_command",
            execute,
        )

        _publish_revision(port, revision)
        qtbot.waitUntil(lambda: execute.call_count >= 1)

        assert panel._last_application_revision == 0
        assert panel._application_render_ledger.pending_publication is not None
        assert panel.data_surface.currentWidget() is panel.table
        assert panel.table.rowCount() == 1
        assert "Dataset data-list query failed" not in caplog.text
        assert "Dataset application publication render failed" not in caplog.text

        query_result.failed = False
        query_result.diagnostics = {"raw_rows": []}
        qtbot.waitUntil(lambda: panel._last_application_revision == revision)

    assert panel._application_render_ledger.pending_publication is None
    assert panel.empty_state_title.text() == "No EEG data loaded"


def test_preprocess_state_render_is_driven_only_by_application_publication(
    qtbot,
) -> None:
    controller = Observable()
    dataset_controller = Observable()
    port = _PublicationPort()
    panel = PreprocessPanel(
        controller=controller,
        dataset_controller=dataset_controller,
        publication_port=port,
    )
    qtbot.addWidget(panel)
    renders: list[int] = []
    cast(Any, panel).update_panel = lambda: renders.append(port.publication.revision)

    controller.notify("preprocess_changed")
    dataset_controller.notify("data_changed")
    qtbot.wait(25)
    assert renders == []

    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)

    assert renders == []
    qtbot.waitUntil(lambda: renders == [port.publication.revision])


def test_training_state_render_uses_publication_while_progress_stays_transient(
    qtbot,
) -> None:
    port = _PublicationPort()
    transient_port = Observable()
    panel = TrainingPanel(
        query_port=MagicMock(),
        publication_port=port,
        action_port=MagicMock(),
        transient_port=transient_port,
    )
    qtbot.addWidget(panel)
    renders: list[int] = []
    progress_ticks: list[bool] = []
    cast(Any, panel).update_panel = lambda: renders.append(port.publication.revision)
    cast(Any, panel).update_loop = lambda **kwargs: progress_ticks.append(
        bool(kwargs.get("log_epochs"))
    )
    initial_revision = panel._last_application_revision
    initial_start_enabled = panel.sidebar.btn_start.isEnabled()
    initial_stop_enabled = panel.sidebar.btn_stop.isEnabled()

    transient_port.notify("training_updated")
    qtbot.waitUntil(lambda: progress_ticks == [True])
    assert renders == []
    assert panel._rendered_training_running is None
    assert panel._last_application_revision == initial_revision
    assert panel._application_render_ledger.pending_publication is None
    assert panel.sidebar.btn_start.isEnabled() is initial_start_enabled
    assert panel.sidebar.btn_stop.isEnabled() is initial_stop_enabled

    port.notify(APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT, port.publication)

    assert renders == []
    qtbot.waitUntil(lambda: renders == [port.publication.revision])


def test_sync_product_command_result_does_not_refresh_workflow_panels(qtbot) -> None:
    context = QWidget()
    qtbot.addWidget(context)
    updates = SimpleNamespace(dataset=0, preprocess=0, training=0, info=0)

    class _Panel:
        def __init__(self, name: str) -> None:
            self._name = name

        def mark_refresh_dirty(self) -> None:
            pass

        def update_panel(self) -> None:
            setattr(updates, self._name, getattr(updates, self._name) + 1)

    main_window = SimpleNamespace(
        study=Study(),
        stack=object(),
        dataset_panel=_Panel("dataset"),
        preprocess_panel=_Panel("preprocess"),
        training_panel=_Panel("training"),
        evaluation_panel=None,
        visualization_panel=None,
        update_info_panel=lambda: setattr(updates, "info", updates.info + 1),
    )
    cast(Any, context).main_window = main_window
    result = CommandResult.success_result(
        command_name="query_state",
        message="State changed.",
        state=None,
        changed_state=ChangedState(raw_changed=True),
    )
    runtime = MagicMock()
    runtime.execute.return_value = result

    observed = execute_application_command(
        context,
        QueryStateCommand(),
        runtime=runtime,
    )

    assert observed is result
    assert updates == SimpleNamespace(dataset=0, preprocess=0, training=0, info=0)


def test_async_application_command_disables_command_result_refresh(
    qtbot,
    monkeypatch,
) -> None:
    context = QWidget()
    qtbot.addWidget(context)
    captured_refresh: list[bool] = []

    class _Runner:
        def __init__(self, **kwargs: Any) -> None:
            captured_refresh.append(bool(kwargs["refresh"]))

        def start(self) -> bool:
            return True

    monkeypatch.setattr(
        "XBrainLab.ui.application_capabilities.QtApplicationCommandRunner",
        _Runner,
    )

    runtime = MagicMock()
    runtime.begin_owned_operation.return_value = SimpleNamespace(
        operation_id="test-query-state-operation"
    )
    started = execute_application_command_async(
        context,
        QueryStateCommand(),
        on_result=lambda _result: None,
        runtime=runtime,
        refresh=True,
    )

    assert started is True
    assert captured_refresh == [False]
