import threading
import time
from types import SimpleNamespace
from typing import Any, ClassVar, cast
from unittest.mock import MagicMock, patch

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QObject, QRunnable, Qt, QThread, QThreadPool
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QDockWidget, QMessageBox, QWidget

from XBrainLab.backend.application import StopTrainingCommand
from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.application_publication_renderer import (
    ApplicationPublicationRenderLedger,
)
from XBrainLab.ui.async_command_runner import application_command_registry
from XBrainLab.ui.main_window import MainWindow
from XBrainLab.ui.status import show_status_message


@pytest.fixture
def mock_study():
    return MagicMock()


@pytest.fixture
def main_window(mock_study, qtbot):
    # Patch init_panels and init_agent to avoid creating real widgets
    with (
        patch("XBrainLab.ui.main_window.MainWindow.init_panels"),
        patch("XBrainLab.ui.main_window.MainWindow.init_agent"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
    ):
        window = MainWindow(mock_study)

        # Manually attach mock panels
        window.dataset_panel = MagicMock(spec=QWidget)
        window.dataset_panel.update_panel = MagicMock()

        window.preprocess_panel = MagicMock(spec=QWidget)
        window.preprocess_panel.update_panel = MagicMock()

        window.training_panel = MagicMock(spec=QWidget)
        window.training_panel.update_panel = MagicMock()

        window.evaluation_panel = MagicMock(spec=QWidget)
        window.evaluation_panel.update_panel = MagicMock()

        window.visualization_panel = MagicMock(spec=QWidget)
        window.visualization_panel.update_panel = MagicMock()

        qtbot.addWidget(window)
        return window


def test_switch_page_updates_dataset_panel(main_window):
    """Test switching to Dataset panel (Index 0) calls update_panel."""
    main_window.switch_page(0)
    main_window.dataset_panel.update_panel.assert_called_once()


def test_switch_page_updates_preprocess_panel(main_window):
    """Test switching to Preprocess panel (Index 1) calls update_panel."""
    main_window.switch_page(1)
    main_window.preprocess_panel.update_panel.assert_called_once()


def test_switch_page_updates_training_panel(main_window):
    """Test switching to Training panel (Index 2) calls update_panel."""
    main_window.switch_page(2)
    main_window.training_panel.update_panel.assert_called_once()


def test_switch_page_updates_evaluation_panel(main_window):
    """Test switching to Evaluation panel (Index 3) calls update_panel."""
    main_window.switch_page(3)
    main_window.evaluation_panel.update_panel.assert_called_once()


def test_switch_page_updates_visualization_panel(main_window):
    """Test switching to Visualization panel (Index 4) calls update_panel."""
    main_window.switch_page(4)
    main_window.visualization_panel.update_panel.assert_called_once()


def test_switch_page_checks_only_active_nav_button(main_window):
    """Switching pages should keep nav button checked state in sync."""
    main_window.switch_page(3)

    checked_states = [btn.isChecked() for btn in main_window.nav_btns]

    assert checked_states == [False, False, False, True, False]
    assert main_window.compact_nav_combo.currentIndex() == 3


def test_assistant_top_bar_action_reserves_full_label_width(main_window):
    """Dock pressure must not clip the Assistant entry-point label."""
    label_width = main_window.ai_btn.fontMetrics().horizontalAdvance(
        main_window.ai_btn.text()
    )

    assert main_window.ai_btn.minimumWidth() >= label_width + 24

    larger_font = main_window.ai_btn.font()
    larger_font.setPointSize(larger_font.pointSize() + 4)
    main_window.ai_btn.setFont(larger_font)
    main_window._update_navigation_layout()
    resized_label_width = main_window.ai_btn.fontMetrics().horizontalAdvance(
        main_window.ai_btn.text()
    )

    assert main_window.ai_btn.minimumWidth() >= resized_label_width + 24


def test_compact_top_bar_removes_gap_before_assistant_action(main_window):
    """Compact navigation must keep both controls in the visible central area."""
    main_window.top_bar.resize(main_window.COMPACT_NAV_BREAKPOINT - 1, 50)
    main_window._update_navigation_layout()

    assert main_window.compact_nav_combo.isHidden() is False
    assert main_window.top_bar_spacer.isHidden() is True

    main_window.top_bar.resize(main_window.COMPACT_NAV_BREAKPOINT + 1, 50)
    main_window._update_navigation_layout()

    assert main_window.compact_nav_combo.isHidden() is True
    assert main_window.top_bar_spacer.isHidden() is False


def test_top_bar_flexible_space_does_not_cover_the_full_width_header(main_window):
    """The expanding spacer must reveal, not repaint, the TopBar background."""
    stylesheet = main_window.top_bar_spacer.styleSheet().replace(" ", "")

    assert "background-color:transparent" in stylesheet


def test_switch_page_only_updates_target_panel(main_window):
    """Only the selected panel should be refreshed for a page switch."""
    panels = [
        main_window.dataset_panel,
        main_window.preprocess_panel,
        main_window.training_panel,
        main_window.evaluation_panel,
        main_window.visualization_panel,
    ]

    main_window.switch_page(2)

    main_window.training_panel.update_panel.assert_called_once()
    for panel in (p for p in panels if p is not main_window.training_panel):
        panel.update_panel.assert_not_called()


def test_switch_page_delegates_navigation_refresh(main_window):
    """Panel refresh scope should live in the refresh coordinator."""
    with patch("XBrainLab.ui.main_window.refresh_after_navigation") as refresh:
        main_window.switch_page(4)

    refresh.assert_called_once_with(main_window, 4)


def test_switch_page_preserves_revisioned_publication_status(main_window):
    """Navigation must not overwrite the status committed by a publication."""
    result = SimpleNamespace(
        failed=False,
        diagnostics={
            "state": {
                "pipeline_stage": "data_loaded",
                "active_training": {"is_running": False},
                "evaluation": {"finished_runs": 0},
                "active_dataset": {
                    "has_datasets": True,
                    "has_epoch_data": True,
                    "has_preprocessed_data": True,
                    "has_raw_data": True,
                },
            },
        },
    )
    publication_message = "Training failed · Adjust settings"
    main_window.statusBar().showMessage(publication_message)

    with (
        patch(
            "XBrainLab.ui.main_window.has_real_application_context",
            return_value=True,
        ),
        patch(
            "XBrainLab.ui.main_window.application_runtime_initialized",
            return_value=True,
        ),
        patch(
            "XBrainLab.ui.main_window.execute_application_command",
            return_value=result,
        ) as execute,
    ):
        main_window.switch_page(0)

    execute.assert_not_called()
    assert main_window.statusBar().currentMessage() == publication_message


def test_page_activation_restores_cached_publication_after_opening_status(
    main_window,
):
    from XBrainLab.backend.application.service import ApplicationService
    from XBrainLab.backend.study import Study

    service = ApplicationService(Study())
    publication = service.get_view_publication()
    main_window._last_rendered_application_publication = publication
    main_window._loaded_panel_indices.add(0)
    main_window.statusBar().showMessage("Opening Dataset...")

    try:
        with (
            patch(
                "XBrainLab.ui.main_window.has_real_application_context",
                return_value=True,
            ),
            patch("XBrainLab.ui.main_window.refresh_after_navigation"),
        ):
            main_window._finish_page_activation(0)

        assert main_window.statusBar().currentMessage() == (
            main_window._application_publication_status_message(publication)
        )
    finally:
        service.close()


def test_publication_status_waits_for_transient_action_feedback(
    main_window,
    qtbot,
):
    """Committed state must not immediately erase visible command feedback."""
    from XBrainLab.backend.application.service import ApplicationService
    from XBrainLab.backend.study import Study

    service = ApplicationService(Study())
    publication = service.get_view_publication()
    main_window._last_rendered_application_publication = publication
    transient_message = "EEG epochs created. Preprocessing is now locked."
    publication_message = main_window._application_publication_status_message(
        publication
    )

    try:
        assert show_status_message(
            main_window,
            transient_message,
            timeout_ms=120,
        )

        assert main_window._show_application_publication_status(publication)
        assert main_window.statusBar().currentMessage() == transient_message

        qtbot.waitUntil(
            lambda: main_window.statusBar().currentMessage() == publication_message,
            timeout=2_000,
        )
    finally:
        service.close()


def test_switch_page_does_not_present_stale_backend_state_as_current(main_window):
    """A retained publication is diagnostic evidence, not current workflow truth."""
    result = SimpleNamespace(
        failed=False,
        diagnostics={
            "view_stale": True,
            "view_verified": True,
            "publication_generation": 12,
            "state": {
                "active_training": {"is_running": False},
                "evaluation": {"finished_runs": 0},
                "active_dataset": {
                    "has_datasets": True,
                    "has_epoch_data": True,
                    "has_preprocessed_data": True,
                    "has_raw_data": True,
                },
            },
        },
    )

    with (
        patch(
            "XBrainLab.ui.main_window.application_runtime_initialized",
            return_value=True,
        ),
        patch(
            "XBrainLab.ui.main_window.execute_application_command",
            return_value=result,
        ),
    ):
        main_window.switch_page(0)

    assert (
        main_window.statusBar().currentMessage()
        == "Workflow status unavailable · Try again"
    )


def test_close_shutdown_requests_nonblocking_training_stop(main_window):
    result = SimpleNamespace(failed=False, diagnostics={"stopped": True})
    callbacks = {}

    def fake_async(_context, command, *, on_result, on_error, **_kwargs):
        callbacks["result"] = on_result
        callbacks["error"] = on_error
        callbacks["command"] = command
        return True

    with (
        patch(
            "XBrainLab.ui.main_window.has_real_application_context",
            return_value=True,
        ),
        patch(
            "XBrainLab.ui.main_window.application_runtime_initialized",
            return_value=True,
        ),
        patch(
            "XBrainLab.ui.main_window.execute_application_command_async",
            side_effect=fake_async,
        ),
        patch("XBrainLab.ui.main_window.QTimer.singleShot") as retry,
    ):
        main_window._closing_in_progress = True
        stopped = main_window._stop_training_for_close()
        assert stopped is False
        assert main_window._training_close_check_in_flight is True

        callbacks["result"](result)

    command = callbacks["command"]
    assert isinstance(command, StopTrainingCommand)
    assert command.wait_timeout == 0.0
    assert main_window._training_close_ready is True
    assert main_window._training_close_check_in_flight is False
    retry.assert_called_once()


def test_close_does_not_self_wait_inside_training_stop_callback(main_window):
    result = SimpleNamespace(failed=False, diagnostics={"stopped": True})
    callbacks = {}

    def fake_async(_context, _command, *, on_result, **_kwargs):
        callbacks["result"] = on_result
        return True

    with (
        patch(
            "XBrainLab.ui.main_window.has_real_application_context",
            return_value=True,
        ),
        patch(
            "XBrainLab.ui.main_window.application_runtime_initialized",
            return_value=True,
        ),
        patch(
            "XBrainLab.ui.main_window.execute_application_command_async",
            side_effect=fake_async,
        ),
        patch.object(main_window, "_schedule_close_retry") as retry,
    ):
        main_window._closing_in_progress = True
        assert main_window._stop_training_for_close() is False
        callbacks["result"](result)

    assert main_window._training_close_ready is True
    assert main_window._training_close_check_in_flight is False
    retry.assert_called_once_with()


def test_close_waits_when_training_thread_does_not_stop(main_window):
    main_window.agent_manager = MagicMock()
    event = QCloseEvent()

    with (
        patch.object(main_window, "_stop_training_for_close", return_value=False),
        patch("XBrainLab.ui.main_window.QTimer.singleShot") as retry,
    ):
        main_window.closeEvent(event)

    assert event.isAccepted() is False
    main_window.agent_manager.close.assert_not_called()
    retry.assert_not_called()
    assert "Training is still stopping" in main_window.statusBar().currentMessage()


@pytest.mark.parametrize(
    ("prewarm_worker", "panel_workers", "active_index"),
    [
        (object(), {}, None),
        (None, {1: (object(), object())}, 1),
        (None, {}, 2),
    ],
)
def test_close_waits_for_owned_ui_background_work(
    main_window,
    prewarm_worker,
    panel_workers,
    active_index,
):
    main_window._startup_prewarm_worker = prewarm_worker
    main_window._panel_prepare_workers = panel_workers
    main_window._panel_prepare_active_index = active_index
    event = QCloseEvent()

    with (
        patch.object(
            main_window, "_ensure_shutdown_fence_for_close", return_value=True
        ),
        patch.object(main_window, "_stop_training_for_close", return_value=True),
        patch.object(main_window, "_close_assistant_for_shutdown") as close_assistant,
        patch.object(main_window, "_schedule_close_retry") as retry,
    ):
        main_window.closeEvent(event)

    assert event.isAccepted() is False
    close_assistant.assert_not_called()
    retry.assert_called_once_with()
    assert "background interface work" in main_window.statusBar().currentMessage()


def test_owned_background_gate_includes_application_workers(main_window) -> None:
    main_window._startup_prewarm_worker = None
    main_window._panel_prepare_workers = {}
    main_window._panel_prepare_active_index = None

    with (
        patch.object(
            main_window,
            "_visualization_native_render_idle",
            return_value=True,
        ),
        patch(
            "XBrainLab.ui.main_window.application_background_tasks_idle",
            return_value=False,
            create=True,
        ) as application_idle,
    ):
        assert main_window._owned_ui_background_work_idle() is False

    application_idle.assert_called_once_with(main_window, timeout=0.0)


def test_close_finalizes_application_runtime_before_qt_close(main_window) -> None:
    event = QCloseEvent()
    call_order: list[str] = []

    with (
        patch.object(
            main_window, "_ensure_shutdown_fence_for_close", return_value=True
        ),
        patch.object(main_window, "_stop_training_for_close", return_value=True),
        patch.object(main_window, "_owned_ui_background_work_idle", return_value=True),
        patch.object(
            main_window,
            "_finalize_visualization_native_render_resources",
            return_value=True,
        ),
        patch.object(
            main_window,
            "_finalize_preprocess_native_plots_for_shutdown",
            side_effect=lambda: call_order.append("preprocess") or True,
        ),
        patch.object(main_window, "_close_assistant_for_shutdown", return_value=True),
        patch.object(
            main_window,
            "_finalize_application_publication_renderer_for_shutdown",
            side_effect=lambda: call_order.append("renderer") or True,
        ),
        patch(
            "XBrainLab.ui.main_window.close_application_runtime",
            side_effect=lambda _window: call_order.append("application") or True,
            create=True,
        ),
        patch.object(
            main_window.window_geometry,
            "persist_before_close",
            return_value=True,
        ),
        patch.object(
            main_window,
            "_delegate_close_event_if_alive",
            side_effect=lambda _event: call_order.append("qt-close") or True,
        ),
    ):
        main_window.closeEvent(event)

    assert call_order == [
        "preprocess",
        "renderer",
        "application",
        "qt-close",
    ]


def test_close_waits_for_active_visualization_native_render(main_window):
    visualization_panel = SimpleNamespace(
        begin_native_render_shutdown=MagicMock(),
        native_render_work_idle=MagicMock(return_value=False),
    )
    main_window.visualization_panel = visualization_panel
    event = QCloseEvent()

    with (
        patch.object(
            main_window, "_ensure_shutdown_fence_for_close", return_value=True
        ),
        patch.object(main_window, "_stop_training_for_close", return_value=True),
        patch.object(main_window, "_close_assistant_for_shutdown") as close_assistant,
        patch.object(main_window, "_schedule_close_retry") as retry,
    ):
        main_window.closeEvent(event)

    assert event.isAccepted() is False
    visualization_panel.begin_native_render_shutdown.assert_called_once_with()
    visualization_panel.native_render_work_idle.assert_called()
    close_assistant.assert_not_called()
    retry.assert_called_once_with()


def test_close_quiesces_preprocess_native_plots_before_window_teardown(main_window):
    preview = SimpleNamespace(prepare_for_shutdown=MagicMock())
    main_window.preprocess_panel = SimpleNamespace(preview_widget=preview)

    main_window._begin_close_attempt()
    preview.prepare_for_shutdown.assert_not_called()
    main_window._begin_desktop_render_shutdown()

    preview.prepare_for_shutdown.assert_called_once_with()


def test_close_finalizes_native_resources_after_workers_idle_before_accept(
    main_window,
):
    call_order: list[str] = []
    visualization_panel = SimpleNamespace(
        begin_native_render_shutdown=MagicMock(),
        native_render_work_idle=MagicMock(return_value=True),
        finalize_native_render_resources=MagicMock(
            side_effect=lambda: call_order.append("finalize") or True,
        ),
    )
    main_window.visualization_panel = visualization_panel
    event = QCloseEvent()

    with (
        patch.object(
            main_window,
            "_ensure_shutdown_fence_for_close",
            return_value=True,
        ),
        patch.object(main_window, "_stop_training_for_close", return_value=True),
        patch.object(
            main_window,
            "_close_assistant_for_shutdown",
            side_effect=lambda: call_order.append("assistant") or True,
        ),
        patch.object(
            main_window.window_geometry,
            "persist_before_close",
            return_value=True,
        ),
        patch.object(
            main_window,
            "_delegate_close_event_if_alive",
            side_effect=lambda _event: call_order.append("accept") or True,
        ),
    ):
        main_window.closeEvent(event)

    assert call_order == ["finalize", "assistant", "accept"]
    visualization_panel.finalize_native_render_resources.assert_called_once_with()


def test_unrelated_global_qthreadpool_work_does_not_block_app_owned_close(
    main_window,
    qtbot,
):
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    class _UnrelatedWork(QRunnable):
        def run(self) -> None:
            started.set()
            release.wait(timeout=3.0)
            finished.set()

    pool = QThreadPool.globalInstance()
    assert pool is not None
    work = _UnrelatedWork()
    pool.start(work)
    qtbot.waitUntil(started.is_set, timeout=1000)
    assert pool.activeThreadCount() >= 1

    visualization_panel = SimpleNamespace(
        begin_native_render_shutdown=MagicMock(),
        native_render_work_idle=MagicMock(return_value=True),
        finalize_native_render_resources=MagicMock(return_value=True),
    )
    main_window.visualization_panel = visualization_panel
    event = QCloseEvent()

    try:
        with (
            patch.object(
                main_window,
                "_ensure_shutdown_fence_for_close",
                return_value=True,
            ),
            patch.object(main_window, "_stop_training_for_close", return_value=True),
            patch.object(
                main_window,
                "_close_assistant_for_shutdown",
                return_value=True,
            ),
            patch.object(
                main_window.window_geometry,
                "persist_before_close",
                return_value=True,
            ),
            patch.object(
                main_window,
                "_delegate_close_event_if_alive",
                return_value=True,
            ) as delegate,
        ):
            main_window.closeEvent(event)

        visualization_panel.finalize_native_render_resources.assert_called_once_with()
        delegate.assert_called_once_with(event)
        assert pool.activeThreadCount() >= 1
    finally:
        release.set()
        qtbot.waitUntil(finished.is_set, timeout=1000)


def test_close_retries_when_native_resource_finalizer_is_not_terminal(main_window):
    visualization_panel = SimpleNamespace(
        begin_native_render_shutdown=MagicMock(),
        native_render_work_idle=MagicMock(return_value=True),
        finalize_native_render_resources=MagicMock(return_value=False),
    )
    main_window.visualization_panel = visualization_panel
    event = QCloseEvent()

    with (
        patch.object(
            main_window,
            "_ensure_shutdown_fence_for_close",
            return_value=True,
        ),
        patch.object(main_window, "_stop_training_for_close", return_value=True),
        patch.object(main_window, "_close_assistant_for_shutdown") as close_assistant,
        patch.object(main_window, "_delegate_close_event_if_alive") as accept_close,
        patch.object(main_window, "_schedule_close_retry") as retry,
    ):
        main_window.closeEvent(event)

    assert event.isAccepted() is False
    visualization_panel.finalize_native_render_resources.assert_called_once_with()
    close_assistant.assert_not_called()
    accept_close.assert_not_called()
    retry.assert_called_once_with()


def test_cancelled_close_resumes_visualization_rendering(main_window):
    preview = SimpleNamespace(resume_after_cancelled_shutdown=MagicMock())
    main_window.preprocess_panel = SimpleNamespace(preview_widget=preview)
    visualization_panel = SimpleNamespace(
        cancel_native_render_shutdown=MagicMock(),
    )
    main_window.visualization_panel = visualization_panel
    main_window._closing_in_progress = True

    main_window._restore_close_interaction()

    visualization_panel.cancel_native_render_shutdown.assert_called_once_with()
    preview.resume_after_cancelled_shutdown.assert_called_once_with()
    assert main_window._closing_in_progress is False


def test_force_close_still_waits_for_owned_ui_background_work(main_window):
    main_window._force_shutdown_requested = True
    main_window._startup_prewarm_worker = object()
    event = QCloseEvent()

    with (
        patch.object(main_window, "_close_assistant_for_shutdown") as close_assistant,
        patch.object(main_window, "_delegate_close_event_if_alive") as delegate,
        patch.object(main_window, "_schedule_close_retry") as retry,
    ):
        main_window.closeEvent(event)

    assert event.isAccepted() is False
    close_assistant.assert_not_called()
    delegate.assert_not_called()
    retry.assert_called_once_with()


def test_cancelled_close_preserves_pending_panel_request(main_window):
    callback = MagicMock()
    main_window._panel_prepare_queue[:] = [2]
    main_window._panel_ready_callbacks[2] = [callback]

    main_window._begin_close_attempt()
    main_window._restore_close_interaction()

    assert main_window._panel_prepare_queue == [2]
    assert main_window._panel_ready_callbacks == {2: [callback]}


def test_close_disables_all_ui_before_training_check(main_window):
    call_order = []
    main_window.agent_manager = MagicMock()
    main_window.agent_manager.close.side_effect = (
        lambda: call_order.append("assistant") or True
    )
    dock = QDockWidget("Assistant", main_window)
    dock.setWidget(QWidget())
    main_window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    with patch.object(
        main_window,
        "_stop_training_for_close",
        side_effect=lambda: call_order.append("training") or False,
    ):
        event = QCloseEvent()
        main_window.closeEvent(event)

    assert event.isAccepted() is False
    assert call_order == ["training"]
    assert main_window.centralWidget().isEnabled() is False
    assert dock.isEnabled() is False


def test_close_coalesces_repeated_training_shutdown_retries(main_window):
    with patch("XBrainLab.ui.main_window.QTimer.singleShot") as retry:
        main_window._schedule_close_retry()
        main_window._schedule_close_retry()

    retry.assert_called_once()


def test_close_retry_from_worker_is_armed_on_the_gui_thread(main_window, qtbot):
    timer_threads = []

    def record_timer(_delay, _callback):
        timer_threads.append(QThread.currentThread())

    with patch(
        "XBrainLab.ui.main_window.QTimer.singleShot",
        side_effect=record_timer,
    ):
        worker = threading.Thread(target=main_window._schedule_close_retry)
        worker.start()
        worker.join(timeout=1.0)

        assert worker.is_alive() is False
        qtbot.waitUntil(lambda: bool(timer_threads), timeout=1_000)

    assert timer_threads == [main_window.thread()]


def test_runtime_wrapper_panel_blocks_desktop_revision_until_ledger_commits(
    main_window,
):
    from XBrainLab.backend.application.runtime import get_application_service
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.application_capabilities import application_ui_runtime

    study = Study()
    runtime = application_ui_runtime(SimpleNamespace(study=study))
    assert runtime is not None
    service = get_application_service(study)
    publication = service.get_view_publication()
    panel = QWidget(main_window)
    panel._publication_port = runtime
    panel._application_render_ledger = ApplicationPublicationRenderLedger(
        panel_name="Runtime wrapper fixture",
        render_publication=lambda _publication: None,
        commit_publication=lambda _publication: None,
        parent=panel,
    )
    main_window.visualization_panel = panel
    main_window._loaded_panel_indices.add(4)
    main_window._application_publication_renderer = SimpleNamespace(
        service=service,
    )
    main_window.info_service = MagicMock()
    main_window.info_service.render_publication.return_value = True

    try:
        assert panel._publication_port is not service
        assert main_window._render_application_view_publication(publication) is False

        assert panel._application_render_ledger.record_rendered(publication) is True
        assert main_window._render_application_view_publication(publication) is True
    finally:
        service.close()


def test_materialized_panel_without_revision_ledger_blocks_desktop_revision(
    main_window,
):
    panel = QWidget(main_window)
    panel._publication_port = Observable()
    main_window.visualization_panel = panel
    main_window._loaded_panel_indices.add(4)
    main_window._application_publication_renderer = SimpleNamespace(service=object())

    assert main_window._panel_rendered_application_revision(4, 8) is False


def test_close_allows_failed_stop_when_training_liveness_is_reliable(main_window):
    result = SimpleNamespace(
        failed=True,
        message="No active trainer.",
        state=SimpleNamespace(
            training_liveness_reliable=True,
            active_training=SimpleNamespace(is_running=False),
        ),
    )

    assert main_window._training_stop_result_allows_close(result) is True


def test_close_blocks_when_training_liveness_is_unreliable(main_window):
    result = SimpleNamespace(
        failed=True,
        message="Training state unavailable.",
        state=SimpleNamespace(
            training_liveness_reliable=False,
            active_training=SimpleNamespace(is_running=False),
        ),
    )

    assert main_window._training_stop_result_allows_close(result) is False


def test_close_ignores_unrelated_snapshot_errors_for_training_liveness(main_window):
    result = SimpleNamespace(
        failed=True,
        message="No active trainer.",
        state=SimpleNamespace(
            state_reliable=False,
            training_liveness_reliable=True,
            active_training=SimpleNamespace(is_running=False),
        ),
    )

    assert main_window._training_stop_result_allows_close(result) is True


def test_training_close_ready_is_not_reused_outside_active_close_attempt(main_window):
    main_window._training_close_ready = True
    main_window._closing_in_progress = False

    with (
        patch(
            "XBrainLab.ui.main_window.has_real_application_context",
            return_value=True,
        ),
        patch(
            "XBrainLab.ui.main_window.application_runtime_initialized",
            return_value=True,
        ),
        patch(
            "XBrainLab.ui.main_window.execute_application_command_async",
            return_value=True,
        ) as execute,
    ):
        assert main_window._stop_training_for_close() is False

    execute.assert_called_once()
    assert main_window._training_close_ready is False


def test_failed_close_check_restores_window_interaction(main_window):
    main_window.agent_manager = MagicMock()
    main_window.agent_manager.close.return_value = True
    callbacks = {}
    main_window._shutdown_fence_active = True
    dock = QDockWidget("Assistant", main_window)
    dock.setWidget(QWidget())
    main_window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def fake_async(_context, _command, *, on_result, on_error, **_kwargs):
        callbacks["error"] = on_error
        return True

    with (
        patch(
            "XBrainLab.ui.main_window.has_real_application_context",
            return_value=True,
        ),
        patch(
            "XBrainLab.ui.main_window.application_runtime_initialized",
            return_value=True,
        ),
        patch(
            "XBrainLab.ui.main_window.execute_application_command_async",
            side_effect=fake_async,
        ),
        patch(
            "XBrainLab.ui.main_window.release_application_shutdown_fence",
            return_value=True,
        ),
    ):
        event = QCloseEvent()
        main_window.closeEvent(event)
        assert event.isAccepted() is False
        assert main_window.centralWidget().isEnabled() is False
        assert dock.isEnabled() is False

        callbacks["error"]((RuntimeError, RuntimeError("state failed"), ""))

    assert main_window._closing_in_progress is False
    assert main_window._shutdown_fence_active is False
    assert main_window.centralWidget().isEnabled() is True
    assert dock.isEnabled() is True
    main_window.agent_manager.close.assert_not_called()


def test_shutdown_fence_release_retries_before_restoring_interaction(main_window):
    main_window._closing_in_progress = True
    main_window._shutdown_fence_active = True
    main_window._set_close_interaction_enabled(False)
    callbacks = []

    with (
        patch(
            "XBrainLab.ui.main_window.has_real_application_context",
            return_value=True,
        ),
        patch(
            "XBrainLab.ui.main_window.release_application_shutdown_fence",
            side_effect=[False, True],
        ) as release,
        patch(
            "XBrainLab.ui.main_window.QTimer.singleShot",
            side_effect=lambda _delay, callback: callbacks.append(callback),
        ),
    ):
        main_window._cancel_close_attempt()
        assert main_window._closing_in_progress is True
        assert main_window.centralWidget().isEnabled() is False
        assert len(callbacks) == 1

        callbacks[0]()

    assert release.call_count == 2
    assert main_window._closing_in_progress is False
    assert main_window._shutdown_fence_active is False
    assert main_window.centralWidget().isEnabled() is True


def test_shutdown_fence_release_failure_enters_visible_shutdown_only_state(
    main_window,
):
    main_window._closing_in_progress = True
    main_window._shutdown_fence_active = True
    main_window._set_close_interaction_enabled(False)
    callbacks = []

    with (
        patch(
            "XBrainLab.ui.main_window.has_real_application_context",
            return_value=True,
        ),
        patch(
            "XBrainLab.ui.main_window.release_application_shutdown_fence",
            return_value=False,
        ),
        patch(
            "XBrainLab.ui.main_window.SHUTDOWN_FENCE_RELEASE_MAX_ATTEMPTS",
            1,
        ),
        patch(
            "XBrainLab.ui.main_window.QTimer.singleShot",
            side_effect=lambda _delay, callback: callbacks.append(callback),
        ),
        patch(
            "XBrainLab.ui.main_window.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Close,
        ),
        patch.object(main_window, "close") as close,
    ):
        main_window._cancel_close_attempt()
        assert len(callbacks) == 1
        callbacks[0]()
        assert len(callbacks) == 2
        callbacks[1]()

    assert main_window._closing_in_progress is True
    assert main_window._shutdown_fence_active is True
    assert main_window._shutdown_only_mode is True
    assert main_window._force_shutdown_requested is True
    assert main_window.centralWidget().isEnabled() is False
    close.assert_called_once_with()
    assert (
        "could not resume normal operation" in main_window.statusBar().currentMessage()
    )


def test_force_shutdown_bypasses_failed_state_verification(main_window):
    main_window._force_shutdown_requested = True
    main_window.agent_manager = MagicMock()
    event = QCloseEvent()

    with patch.object(main_window, "_stop_training_for_close") as stop:
        main_window.closeEvent(event)

    assert event.isAccepted() is True
    stop.assert_not_called()
    main_window.agent_manager.close.assert_called_once_with()


def test_failed_stop_result_retains_close_fence_until_snapshot_recovers(qtbot):
    from XBrainLab.backend.application import get_application_service
    from XBrainLab.backend.study import Study

    study = Study()
    with (
        patch("XBrainLab.ui.main_window.MainWindow.init_panels"),
        patch("XBrainLab.ui.main_window.MainWindow.init_agent"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
    ):
        window = MainWindow(study)
    qtbot.addWidget(window)
    dock = QDockWidget("Assistant", window)
    dock.setWidget(QWidget())
    window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    callbacks = {}

    def fake_async(_context, _command, *, on_result, on_error, **_kwargs):
        callbacks["result"] = on_result
        callbacks["error"] = on_error
        return True

    service = get_application_service(study)
    with patch(
        "XBrainLab.ui.main_window.execute_application_command_async",
        side_effect=fake_async,
    ):
        event = QCloseEvent()
        window.closeEvent(event)

    assert event.isAccepted() is False
    assert service.shutdown_lifecycle.is_shutdown_fenced is True
    original_build_state = service.state_snapshot.build
    service.state_snapshot.build = MagicMock(
        side_effect=RuntimeError("state backend unavailable"),
    )
    result = service.execute(StopTrainingCommand(wait_timeout=0.0))
    assert result.failed is True

    callbacks["result"](result)

    assert service.shutdown_lifecycle.is_shutdown_fenced is True
    assert window._closing_in_progress is True
    assert window._shutdown_fence_active is True
    assert window._shutdown_release_retry_pending is True
    central_widget = window.centralWidget()
    assert central_widget is not None
    assert central_widget.isEnabled() is False
    assert dock.isEnabled() is False

    service.state_snapshot.build = original_build_state
    qtbot.waitUntil(
        lambda: service.shutdown_lifecycle.is_shutdown_fenced is False, timeout=2000
    )

    assert window._closing_in_progress is False
    assert window._shutdown_fence_active is False
    assert window._shutdown_release_retry_pending is False
    assert central_widget.isEnabled() is True
    assert dock.isEnabled() is True


def test_close_does_not_wait_for_application_command_lock(qtbot):
    import threading
    import time

    from PyQt6.QtCore import QTimer

    from XBrainLab.backend.application import get_application_service
    from XBrainLab.backend.study import Study

    study = Study()
    with (
        patch("XBrainLab.ui.main_window.MainWindow.init_panels"),
        patch("XBrainLab.ui.main_window.MainWindow.init_agent"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
    ):
        window = MainWindow(study)
    qtbot.addWidget(window)
    service = get_application_service(study)
    lock_acquired = threading.Event()
    release_lock = threading.Event()

    def hold_command_lock() -> None:
        with service._command_lock:
            lock_acquired.set()
            release_lock.wait(timeout=2.0)

    lock_holder = threading.Thread(target=hold_command_lock)
    lock_holder.start()
    assert lock_acquired.wait(timeout=1.0)

    with patch.object(window, "_schedule_close_retry") as retry:
        event = QCloseEvent()
        started_at = time.monotonic()
        window.closeEvent(event)
        elapsed = time.monotonic() - started_at

        assert elapsed < 0.1
        assert event.isAccepted() is False
        assert window._shutdown_fence_active is True
        assert window._training_close_check_in_flight is True

        heartbeat: list[bool] = []
        QTimer.singleShot(0, lambda: heartbeat.append(True))
        qtbot.waitUntil(lambda: bool(heartbeat), timeout=1000)

        release_lock.set()
        qtbot.waitUntil(lambda: window._training_close_ready, timeout=1000)
        retry.assert_called_once()

    lock_holder.join(timeout=1.0)
    assert not lock_holder.is_alive()
    window._closing_in_progress = True
    window._shutdown_fence_active = True
    window._training_close_ready = True


def test_close_fences_headless_training_before_async_stop_dispatch(qtbot):
    from XBrainLab.backend.application import TrainCommand, get_application_service
    from XBrainLab.backend.study import Study

    study = Study()
    with (
        patch("XBrainLab.ui.main_window.MainWindow.init_panels"),
        patch("XBrainLab.ui.main_window.MainWindow.init_agent"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
    ):
        window = MainWindow(study)
    qtbot.addWidget(window)
    service = get_application_service(study)

    with patch(
        "XBrainLab.ui.main_window.execute_application_command_async",
        return_value=True,
    ):
        event = QCloseEvent()
        window.closeEvent(event)

    blocked = service.execute(TrainCommand(confirmed=True))

    assert event.isAccepted() is False
    assert window._shutdown_fence_active is True
    assert service.shutdown_lifecycle.is_shutdown_fenced is True
    assert blocked.failed is True
    assert "closing" in blocked.message

    service.release_shutdown_fence()
    window._training_close_check_in_flight = False
    window._closing_in_progress = True
    window._shutdown_fence_active = True
    window._training_close_ready = True


def test_close_before_runtime_initialization_does_not_construct_service(qtbot):
    from XBrainLab.backend.study import Study

    study = Study()
    with (
        patch("XBrainLab.ui.main_window.MainWindow.init_panels"),
        patch("XBrainLab.ui.main_window.MainWindow.init_agent"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
    ):
        window = MainWindow(study)
    qtbot.addWidget(window)
    window.show()

    assert getattr(study, "_application_service", None) is None
    assert window.close() is True
    qtbot.waitUntil(lambda: not window.isVisible(), timeout=1000)

    assert window._closing_in_progress is True
    assert window._training_close_ready is False
    assert window._training_close_check_in_flight is False
    assert window._shutdown_fence_active is False
    assert getattr(study, "_application_service", None) is None
    assert application_command_registry().active_count(window) == 0


def test_close_waits_when_assistant_thread_ownership_is_not_released(main_window):
    main_window.agent_manager = MagicMock()
    main_window.agent_manager.close.return_value = False
    main_window.agent_manager.assistant_runtime = None
    event = QCloseEvent()

    with (
        patch.object(main_window, "_stop_training_for_close", return_value=True),
        patch("XBrainLab.ui.main_window.QTimer.singleShot") as retry,
    ):
        main_window.closeEvent(event)

    assert event.isAccepted() is False
    retry.assert_called_once()
    assert "Assistant is still stopping" in main_window.statusBar().currentMessage()


def test_update_info_panel_uses_info_service(main_window):
    """Shared refresh should update registered AggregateInfoPanel instances."""
    main_window.info_service = MagicMock()

    main_window.update_info_panel()

    main_window.info_service.notify_all.assert_called_once()


def test_main_window_delegates_info_refresh_to_coordinator(mock_study, qtbot):
    """Product MainWindow should not double-subscribe aggregate info refresh."""
    with (
        patch("XBrainLab.ui.main_window.MainWindow.init_panels"),
        patch("XBrainLab.ui.main_window.MainWindow.init_agent"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
    ):
        window = MainWindow(mock_study)

    qtbot.addWidget(window)
    assert window.info_service.study is mock_study
    assert window.info_service._observes_controller_events is False


def test_init_panels_never_resolves_workflow_controllers(
    mock_study,
    qtbot,
):
    """Lazy product panels must materialize only through typed ports."""
    loaded_classes = []

    with (
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
        patch("XBrainLab.ui.main_window.InfoPanelService"),
        patch(
            "XBrainLab.ui.main_window._load_panel_class",
            side_effect=lambda _module, class_name: (
                loaded_classes.append(class_name) or (lambda *args, **kwargs: QWidget())
            ),
        ) as load_panel_class,
    ):
        window = MainWindow(mock_study)
        assert loaded_classes == []
        window.switch_page(0)
        ready_panels = []
        window.switch_page(2, on_ready=ready_panels.append)
        qtbot.waitUntil(lambda: len(ready_panels) == 1, timeout=1_000)

    qtbot.addWidget(window)
    mock_study.get_controller.assert_not_called()
    assert sorted(loaded_classes) == ["DatasetPanel", "TrainingPanel"]
    assert window.stack.count() == 5
    assert load_panel_class.call_count == 2


@pytest.mark.parametrize(
    ("panel_index", "panel_attr"),
    ((0, "dataset_panel"), (1, "preprocess_panel")),
)
def test_primary_panel_materializes_with_publication_port_only(
    mock_study,
    qtbot,
    panel_index,
    panel_attr,
):
    """Dataset and Preprocess product construction must not touch controllers."""
    runtime = object()
    constructor_calls = []

    class _PrimaryPanelProbe(QWidget):
        def __init__(self, *, parent, publication_port):
            constructor_calls.append((parent, publication_port))
            super().__init__(parent)

    mock_study.get_controller.side_effect = AssertionError(
        "product panel construction must not call Study.get_controller",
    )
    with (
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
        patch("XBrainLab.ui.main_window.InfoPanelService"),
        patch(
            "XBrainLab.ui.main_window.application_ui_runtime",
            return_value=runtime,
        ) as resolve_runtime,
    ):
        window = MainWindow(mock_study)
        panel = window._materialize_panel(
            panel_index,
            panel_class=_PrimaryPanelProbe,
        )

    qtbot.addWidget(window)
    assert panel is getattr(window, panel_attr)
    assert constructor_calls == [(window, runtime)]
    resolve_runtime.assert_called_once_with(window)
    mock_study.get_controller.assert_not_called()


def test_training_materializes_with_narrow_typed_ports_only(mock_study, qtbot):
    runtime = object()
    transient_port = object()
    constructor_calls = []

    class _TrainingPanelProbe(QWidget):
        def __init__(
            self,
            *,
            parent,
            query_port,
            publication_port,
            action_port,
            transient_port,
        ):
            constructor_calls.append(
                (
                    parent,
                    query_port,
                    publication_port,
                    action_port,
                    transient_port,
                )
            )
            super().__init__(parent)

    mock_study.get_controller.side_effect = AssertionError(
        "Training product construction must not call Study.get_controller",
    )
    with (
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
        patch("XBrainLab.ui.main_window.InfoPanelService"),
        patch(
            "XBrainLab.ui.main_window.application_ui_runtime",
            return_value=runtime,
        ) as resolve_runtime,
        patch(
            "XBrainLab.ui.main_window.training_transient_ui_port",
            return_value=transient_port,
        ) as resolve_transient,
    ):
        window = MainWindow(mock_study)
        panel = window._materialize_panel(2, panel_class=_TrainingPanelProbe)

    qtbot.addWidget(window)
    assert panel is cast(Any, window).training_panel
    assert constructor_calls == [
        (window, runtime, runtime, runtime, transient_port),
    ]
    resolve_runtime.assert_called_once_with(window)
    resolve_transient.assert_called_once_with(window)
    mock_study.get_controller.assert_not_called()


def test_evaluation_materializes_without_compatibility_controller_access(
    mock_study,
    qtbot,
):
    """Evaluation construction receives one runtime through its typed ports."""

    runtime = object()
    constructor_calls = []

    class _EvaluationPanelProbe(QWidget):
        def __init__(
            self,
            *,
            parent,
            query_port,
            publication_port,
            action_port,
        ):
            constructor_calls.append(
                (parent, query_port, publication_port, action_port)
            )
            super().__init__(parent)

    with (
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
        patch("XBrainLab.ui.main_window.InfoPanelService"),
        patch(
            "XBrainLab.ui.main_window.application_ui_runtime",
            return_value=runtime,
        ) as resolve_runtime,
    ):
        window = MainWindow(mock_study)
        panel = window._materialize_panel(3, panel_class=_EvaluationPanelProbe)

    qtbot.addWidget(window)
    assert panel is cast(Any, window).evaluation_panel
    assert constructor_calls == [(window, runtime, runtime, runtime)]
    resolve_runtime.assert_called_once_with(window)


def test_visualization_materializes_with_narrow_application_ports(
    mock_study,
    qtbot,
):
    """Visualization construction receives one runtime through its three ports."""

    runtime = object()
    constructor_calls = []

    class _VisualizationPanelProbe(QWidget):
        def __init__(
            self,
            *,
            parent,
            query_port,
            publication_port,
            action_port,
        ):
            constructor_calls.append(
                (parent, query_port, publication_port, action_port)
            )
            super().__init__(parent)

    with (
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
        patch("XBrainLab.ui.main_window.InfoPanelService"),
        patch(
            "XBrainLab.ui.main_window.application_ui_runtime",
            return_value=runtime,
        ) as resolve_runtime,
    ):
        window = MainWindow(mock_study)
        panel = window._materialize_panel(4, panel_class=_VisualizationPanelProbe)

    qtbot.addWidget(window)
    assert panel is cast(Any, window).visualization_panel
    assert constructor_calls == [(window, runtime, runtime, runtime)]
    resolve_runtime.assert_called_once_with(window)


def test_initial_panel_lazy_load_preserves_current_page(mock_study, qtbot):
    """Replacing the visible placeholder must not jump to the next panel."""
    controllers = SimpleNamespace(
        dataset=object(),
        preprocess=object(),
        training=object(),
        evaluation=object(),
        visualization=object(),
    )

    with (
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
        patch(
            "XBrainLab.ui.main_window.application_ui_runtime",
            return_value=controllers,
        ),
        patch(
            "XBrainLab.ui.main_window._load_panel_class",
            return_value=lambda *args, **kwargs: QWidget(),
        ),
    ):
        window = MainWindow(mock_study)
        assert window.stack.currentIndex() == 0
        window._load_initial_panel_if_alive()

    qtbot.addWidget(window)
    assert window.stack.currentIndex() == 0
    assert window.nav_btns[0].isChecked()


def test_default_startup_materializes_dataset_before_main_window_is_shown(
    mock_study,
    qtbot,
):
    """The splash phase should prepare Dataset before the main window appears."""
    controllers = SimpleNamespace(
        dataset=object(),
        preprocess=object(),
        training=object(),
        evaluation=object(),
        visualization=object(),
    )
    loaded_classes = []

    with (
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
        patch(
            "XBrainLab.ui.main_window.application_ui_runtime",
            return_value=controllers,
        ),
        patch(
            "XBrainLab.ui.main_window._load_panel_class",
            side_effect=lambda _module, class_name: (
                loaded_classes.append(class_name) or (lambda *args, **kwargs: QWidget())
            ),
        ),
    ):
        window = MainWindow(mock_study)

    qtbot.addWidget(window)

    assert loaded_classes == ["DatasetPanel"]
    assert window._loaded_panel_indices == {0}
    assert window.dataset_panel.__class__.__name__ != "_LazyPanelPlaceholder"
    assert window.stack.currentIndex() == 0
    assert window.nav_btns[0].isChecked()


def test_startup_prewarm_result_does_not_reload_dataset(mock_study, qtbot):
    """Background prewarm completion should not re-materialize Dataset."""
    controllers = SimpleNamespace(
        dataset=object(),
        preprocess=object(),
        training=object(),
        evaluation=object(),
        visualization=object(),
    )
    loaded_classes = []

    with (
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
        patch(
            "XBrainLab.ui.main_window.application_ui_runtime",
            return_value=controllers,
        ),
        patch(
            "XBrainLab.ui.main_window._load_panel_class",
            side_effect=lambda _module, class_name: (
                loaded_classes.append(class_name) or (lambda *args, **kwargs: QWidget())
            ),
        ),
    ):
        window = MainWindow(mock_study)

    qtbot.addWidget(window)
    window._on_startup_prewarm_result({"loaded": [], "failed": []})

    assert loaded_classes == ["DatasetPanel"]
    assert window._loaded_panel_indices == {0}


def test_startup_prewarm_start_failure_releases_worker_for_retry(
    mock_study,
    qtbot,
):
    """A thread-pool setup fault must not permanently disable prewarming."""

    class _FailingPool:
        def start(self, _worker):
            raise RuntimeError("injected prewarm start failure")

    class _AcceptingPool:
        def __init__(self):
            self.workers = []

        def start(self, worker):
            self.workers.append(worker)

    with (
        patch("XBrainLab.ui.main_window.MainWindow.init_panels"),
        patch("XBrainLab.ui.main_window.MainWindow.init_agent"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
    ):
        window = MainWindow(mock_study)
    qtbot.addWidget(window)

    with patch(
        "XBrainLab.ui.main_window.QThreadPool.globalInstance",
        return_value=_FailingPool(),
    ):
        window._start_startup_prewarm()

    assert window._startup_prewarm_worker is None

    accepting_pool = _AcceptingPool()
    with patch(
        "XBrainLab.ui.main_window.QThreadPool.globalInstance",
        return_value=accepting_pool,
    ):
        window._start_startup_prewarm()

    assert window._startup_prewarm_worker is not None
    assert accepting_pool.workers == [window._startup_prewarm_worker]


def test_startup_prewarm_does_not_start_during_shutdown(mock_study, qtbot):
    with (
        patch("XBrainLab.ui.main_window.MainWindow.init_panels"),
        patch("XBrainLab.ui.main_window.MainWindow.init_agent"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
    ):
        window = MainWindow(mock_study)
    qtbot.addWidget(window)
    window._closing_in_progress = True

    with (
        patch("XBrainLab.ui.main_window.Worker") as worker,
        patch("XBrainLab.ui.main_window._require_global_thread_pool") as thread_pool,
    ):
        window._start_startup_prewarm()

    worker.assert_not_called()
    thread_pool.assert_not_called()
    assert window._startup_prewarm_worker is None


def test_panel_prepare_start_failure_is_visible_and_retryable(mock_study, qtbot):
    """A failed worker start must release the panel slot for the next click."""
    controllers = SimpleNamespace(
        dataset=object(),
        preprocess=object(),
        training=object(),
        evaluation=object(),
        visualization=object(),
    )

    class _FailingPool:
        def start(self, _worker):
            raise RuntimeError("injected panel start failure")

    class _AcceptingPool:
        def __init__(self):
            self.workers = []

        def start(self, worker):
            self.workers.append(worker)

    with (
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
        patch(
            "XBrainLab.ui.main_window.application_ui_runtime",
            return_value=controllers,
        ),
    ):
        window = MainWindow(mock_study)
    qtbot.addWidget(window)

    with patch(
        "XBrainLab.ui.main_window.QThreadPool.globalInstance",
        return_value=_FailingPool(),
    ):
        window._request_panel_prepare(1)

    assert window._panel_prepare_workers == {}
    assert "Could not open Preprocess" in window.statusBar().currentMessage()

    accepting_pool = _AcceptingPool()
    with patch(
        "XBrainLab.ui.main_window.QThreadPool.globalInstance",
        return_value=accepting_pool,
    ):
        window._request_panel_prepare(1)

    assert 1 in window._panel_prepare_workers
    assert accepting_pool.workers == [window._panel_prepare_workers[1][0]]


@pytest.mark.parametrize("failure_kind", ["constructor", "type"])
def test_prepared_panel_materialization_failure_rolls_back_and_can_retry(
    mock_study,
    qtbot,
    failure_kind,
):
    """A bad prepared class must not poison the cache or replace its placeholder."""
    controllers = SimpleNamespace(
        dataset=object(),
        preprocess=object(),
        training=object(),
        evaluation=object(),
        visualization=object(),
    )
    wrong_type_objects: list[QObject] = []

    class _ConstructorFailure(QWidget):
        def __init__(self, *_args, **_kwargs):
            super().__init__()
            raise RuntimeError("injected constructor failure")

    def _wrong_type(*args, **kwargs):
        parent = kwargs.get("parent") or args[-1]
        wrong_type = QObject(parent)
        wrong_type_objects.append(wrong_type)
        return wrong_type

    class _AcceptingPool:
        def __init__(self):
            self.workers = []

        def start(self, worker):
            self.workers.append(worker)

    class _RetryPanel(QWidget):
        def __init__(self, *_args, **_kwargs):
            super().__init__()

    bad_prepared_class = (
        _ConstructorFailure if failure_kind == "constructor" else _wrong_type
    )
    with (
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
        patch(
            "XBrainLab.ui.main_window.application_ui_runtime",
            return_value=controllers,
        ),
    ):
        window = MainWindow(mock_study)
    qtbot.addWidget(window)
    window._show_page(1)

    window._on_panel_prepare_result(1, bad_prepared_class)
    qtbot.waitUntil(
        lambda: 1 not in window._panel_materialization_pending,
        timeout=1_000,
    )

    assert 1 not in window._prepared_panel_classes
    assert 1 not in window._loaded_panel_indices
    assert window.stack.count() == 5
    assert window.stack.widget(1) is window.preprocess_panel
    assert window.preprocess_panel.__class__.__name__ == "_LazyPanelPlaceholder"
    assert "Select it again to retry" in window.preprocess_panel.detail.text()
    if wrong_type_objects:
        assert sip.isdeleted(wrong_type_objects[0])

    accepting_pool = _AcceptingPool()
    with patch(
        "XBrainLab.ui.main_window.QThreadPool.globalInstance",
        return_value=accepting_pool,
    ):
        assert window.switch_page(1) is False

    assert 1 in window._panel_prepare_workers
    assert accepting_pool.workers == [window._panel_prepare_workers[1][0]]

    retry_delivery = window._panel_prepare_workers[1][1]
    window._on_panel_prepare_result(1, _RetryPanel)
    qtbot.waitUntil(lambda: 1 in window._loaded_panel_indices, timeout=1_000)
    retry_delivery.handle_finished()

    assert isinstance(window.preprocess_panel, _RetryPanel)
    assert window._prepared_panel_classes == {}
    assert window._panel_prepare_workers == {}


def test_materialize_panel_disposes_rejected_qobject_before_raising(
    mock_study,
    qtbot,
):
    """A newly constructed wrong-type QObject must not outlive the failed call."""
    controllers = SimpleNamespace(
        dataset=object(),
        preprocess=object(),
        training=object(),
        evaluation=object(),
        visualization=object(),
    )
    rejected_objects: list[QObject] = []

    def _wrong_type(*args, **kwargs):
        parent = kwargs.get("parent") or args[-1]
        rejected = QObject(parent)
        rejected_objects.append(rejected)
        return rejected

    with (
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
        patch(
            "XBrainLab.ui.main_window.application_ui_runtime",
            return_value=controllers,
        ),
    ):
        window = MainWindow(mock_study)
    qtbot.addWidget(window)

    with pytest.raises(TypeError, match="did not create a QWidget"):
        window._materialize_panel(1, panel_class=_wrong_type)

    assert len(rejected_objects) == 1
    assert sip.isdeleted(rejected_objects[0])


def test_main_window_background_worker_construction_failures_release_ownership(
    mock_study,
    qtbot,
):
    """Worker construction faults must leave both background paths retryable."""
    controllers = SimpleNamespace(
        dataset=object(),
        preprocess=object(),
        training=object(),
        evaluation=object(),
        visualization=object(),
    )
    with (
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
        patch(
            "XBrainLab.ui.main_window.application_ui_runtime",
            return_value=controllers,
        ),
    ):
        window = MainWindow(mock_study)
    qtbot.addWidget(window)

    with patch(
        "XBrainLab.ui.main_window.Worker",
        side_effect=RuntimeError("injected worker construction failure"),
    ):
        window._start_startup_prewarm()
        window._request_panel_prepare(1)

    assert window._startup_prewarm_worker is None
    assert window._panel_prepare_workers == {}
    assert "Could not open Preprocess" in window.statusBar().currentMessage()


@pytest.mark.parametrize("panel_index", [1, 2])
def test_navigation_button_returns_before_slow_panel_prepare_and_builds_on_gui_thread(
    mock_study,
    qtbot,
    panel_index,
):
    """A first click may show a placeholder, but it must never import on the GUI thread."""
    controllers = SimpleNamespace(
        dataset=object(),
        preprocess=object(),
        training=object(),
        evaluation=object(),
        visualization=object(),
    )
    construction_threads: list[QThread] = []
    load_calls: list[str] = []

    class _PreparedPanel(QWidget):
        def __init__(self, *_args, **_kwargs):
            super().__init__()
            application = QCoreApplication.instance()
            assert application is not None
            construction_threads.append(QThread.currentThread())

    def slow_panel_load(_module: str, class_name: str):
        load_calls.append(class_name)
        time.sleep(0.18)
        return _PreparedPanel

    with (
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
        patch(
            "XBrainLab.ui.main_window.application_ui_runtime",
            return_value=controllers,
        ),
        patch(
            "XBrainLab.ui.main_window._load_panel_class",
            side_effect=slow_panel_load,
        ),
    ):
        window = MainWindow(mock_study)
        qtbot.addWidget(window)

        started_at = time.perf_counter()
        window.nav_btns[panel_index].click()
        click_elapsed = time.perf_counter() - started_at

        assert click_elapsed < 0.05
        assert window.stack.currentIndex() == panel_index
        assert panel_index not in window._loaded_panel_indices

        # A second click while preparation is active must reuse the same job.
        window.nav_btns[panel_index].click()
        qtbot.waitUntil(
            lambda: panel_index in window._loaded_panel_indices,
            timeout=2_000,
        )

    application = QCoreApplication.instance()
    assert application is not None
    assert construction_threads == [application.thread()]
    assert len(load_calls) == 1


def test_public_switch_page_prepares_unloaded_panel_without_blocking_gui_thread(
    mock_study,
    qtbot,
):
    """Programmatic navigation must use the same async first-open path as a click."""
    controllers = SimpleNamespace(
        dataset=object(),
        preprocess=object(),
        training=object(),
        evaluation=object(),
        visualization=object(),
    )
    construction_threads: list[QThread] = []
    load_calls: list[str] = []

    class _PreparedPanel(QWidget):
        def __init__(self, *_args, **_kwargs):
            super().__init__()
            construction_threads.append(QThread.currentThread())

    def slow_panel_load(_module: str, class_name: str):
        load_calls.append(class_name)
        time.sleep(0.18)
        return _PreparedPanel

    with (
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
        patch(
            "XBrainLab.ui.main_window.application_ui_runtime",
            return_value=controllers,
        ),
        patch(
            "XBrainLab.ui.main_window._load_panel_class",
            side_effect=slow_panel_load,
        ),
    ):
        window = MainWindow(mock_study)
        qtbot.addWidget(window)

        ready_panels = []
        started_at = time.perf_counter()
        materialized = window.switch_page(2, on_ready=ready_panels.append)
        call_elapsed = time.perf_counter() - started_at

        assert materialized is False
        assert call_elapsed < 0.05
        assert window.stack.currentIndex() == 2
        assert construction_threads == []

        qtbot.waitUntil(
            lambda: len(ready_panels) == 1,
            timeout=2_000,
        )

    application = QCoreApplication.instance()
    assert application is not None
    assert ready_panels == [window.training_panel]
    assert construction_threads == [application.thread()]
    assert load_calls == ["TrainingPanel"]


def test_panel_prepare_result_is_dropped_after_window_deletion(mock_study, qtbot):
    controllers = SimpleNamespace(
        dataset=object(),
        preprocess=object(),
        training=object(),
        evaluation=object(),
        visualization=object(),
    )
    constructed: list[bool] = []

    class _PreparedPanel(QWidget):
        def __init__(self, *_args, **_kwargs):
            super().__init__()
            constructed.append(True)

    def slow_panel_load(_module: str, _class_name: str):
        time.sleep(0.15)
        return _PreparedPanel

    with (
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
        patch(
            "XBrainLab.ui.main_window.application_ui_runtime",
            return_value=controllers,
        ),
        patch(
            "XBrainLab.ui.main_window._load_panel_class",
            side_effect=slow_panel_load,
        ),
    ):
        window = MainWindow(mock_study)
        qtbot.addWidget(window)
        window.nav_btns[2].click()
        window.deleteLater()
        qtbot.waitUntil(lambda: sip.isdeleted(window), timeout=1_000)
        qtbot.wait(250)

    assert constructed == []


def test_navigation_does_not_prepare_panels_during_shutdown(mock_study, qtbot):
    with (
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
        patch("XBrainLab.ui.main_window._load_panel_class") as load_panel,
    ):
        window = MainWindow(mock_study)
        qtbot.addWidget(window)
        window._closing_in_progress = True
        window._request_page_from_navigation(2)

    load_panel.assert_not_called()
    assert window._panel_prepare_workers == {}


def test_agent_manager_is_lazy_until_ai_toggle(mock_study, qtbot):
    """The AI assistant stack should not import/init during MainWindow startup."""

    class _Signal:
        def connect(self, _callback):
            return None

    class _AgentManager:
        status_message_received = _Signal()

        def __init__(self, *args, **kwargs):
            self.chat_panel = None
            self.toggled = False
            self.closed = False

        def init_ui(self):
            return None

        def toggle(self):
            self.toggled = True

        def close(self):
            self.closed = True

    with (
        patch("XBrainLab.ui.main_window.MainWindow.init_panels"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
        patch(
            "XBrainLab.ui.main_window._load_agent_manager_class",
            return_value=_AgentManager,
        ) as load_agent_manager,
        patch.object(
            MainWindow,
            "_ensure_application_publication_renderer",
            return_value=SimpleNamespace(service=MagicMock()),
        ),
    ):
        window = MainWindow(mock_study)
        assert window.agent_manager is None
        load_agent_manager.assert_not_called()
        window.toggle_ai_dock()

    qtbot.addWidget(window)
    load_agent_manager.assert_called_once()
    assert window.agent_manager is not None
    assert window.agent_manager.toggled is True


def test_agent_manager_init_failure_rolls_back_and_second_click_opens_dock(
    mock_study,
    qtbot,
):
    """A failed first assistant construction must leave the button retryable."""

    class _Signal:
        def connect(self, _callback):
            return None

    class _AgentManager:
        status_message_received = _Signal()
        instances: ClassVar[list[Any]] = []

        def __init__(self, main_window, _study, *, application_service):
            self.main_window = main_window
            self.application_service = application_service
            self.chat_panel = None
            self.chat_dock = None
            self.closed = False
            self.fail_init = not self.instances
            self.instances.append(self)

        def init_ui(self):
            self.chat_dock = QDockWidget("Assistant", self.main_window)
            self.chat_dock.setWidget(QWidget())
            self.main_window.addDockWidget(
                Qt.DockWidgetArea.RightDockWidgetArea,
                self.chat_dock,
            )
            if self.fail_init:
                raise RuntimeError("simulated first construction failure")
            self.chat_dock.hide()

        def toggle(self):
            assert self.chat_dock is not None
            self.chat_dock.show()

        def close(self):
            self.closed = True
            assert self.chat_dock is not None
            self.chat_dock.close()
            return True

    with (
        patch("XBrainLab.ui.main_window.MainWindow.init_panels"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
        patch(
            "XBrainLab.ui.main_window._load_agent_manager_class",
            return_value=_AgentManager,
        ),
        patch.object(
            MainWindow,
            "_ensure_application_publication_renderer",
            return_value=SimpleNamespace(service=MagicMock()),
        ),
    ):
        window = MainWindow(mock_study)
        qtbot.addWidget(window)
        window.show()

        window.ai_btn.click()

        first_manager = _AgentManager.instances[0]
        assert window.agent_manager is None
        assert first_manager.closed is True
        assert first_manager.chat_dock.isVisible() is False
        assert window.ai_btn.isChecked() is False
        status_bar = window.statusBar()
        assert status_bar is not None
        assert "Try again" in status_bar.currentMessage()

        window.ai_btn.click()

    assert len(_AgentManager.instances) == 2
    second_manager = _AgentManager.instances[1]
    assert window.agent_manager is second_manager
    assert second_manager.chat_dock.isVisible() is True
    assert window.ai_btn.isChecked() is True


def test_update_info_panel_keeps_compatibility_direct_panel_fallback(main_window):
    """Older injected contexts without InfoPanelService can still update directly."""
    delattr(main_window, "info_service")
    main_window.info_panel = MagicMock()

    main_window.update_info_panel()

    main_window.info_panel.update_info.assert_called_once()


def test_switch_page_skips_panel_without_update_panel(mock_study, qtbot):
    """Panels without update_panel should not break navigation refresh."""
    with (
        patch("XBrainLab.ui.main_window.MainWindow.init_panels"),
        patch("XBrainLab.ui.main_window.MainWindow.init_agent"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_initial_panel_load"),
        patch("XBrainLab.ui.main_window.MainWindow._schedule_startup_prewarm"),
        patch("XBrainLab.ui.main_window.MainWindow.apply_vscode_theme"),
    ):
        window = MainWindow(mock_study)
        cast(Any, window).dataset_panel = QWidget()
        window.preprocess_panel = MagicMock(spec=QWidget)
        window.preprocess_panel.update_panel = MagicMock()
        window.training_panel = MagicMock(spec=QWidget)
        window.training_panel.update_panel = MagicMock()
        window.evaluation_panel = MagicMock(spec=QWidget)
        window.evaluation_panel.update_panel = MagicMock()
        window.visualization_panel = MagicMock(spec=QWidget)
        window.visualization_panel.update_panel = MagicMock()

        qtbot.addWidget(window)

        window.switch_page(0)

        assert window.nav_btns[0].isChecked()
