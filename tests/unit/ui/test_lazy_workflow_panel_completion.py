"""Completion and lifecycle guards for lazy workflow-panel first open."""

from __future__ import annotations

from collections import defaultdict
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QCoreApplication, QThread
from PyQt6.QtWidgets import QWidget

from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolutionStatus,
)
from XBrainLab.ui.components.workflow_ui_handoff_host import WorkflowUiHandoffHost
from XBrainLab.ui.interaction_outcome import InteractionOutcome
from XBrainLab.ui.main_window import MainWindow
from XBrainLab.ui.panel_navigation import PanelPreparationFailure


def _current_thread() -> QThread:
    thread = QThread.currentThread()
    assert thread is not None
    return thread


@pytest.fixture
def lazy_window(qtbot) -> MainWindow:
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
            "XBrainLab.ui.main_window.get_compatibility_workflow_controllers_for_panel_bootstrap",
            return_value=controllers,
        ),
    ):
        window = MainWindow(MagicMock())
    qtbot.addWidget(window)
    return window


def test_prepare_failure_settles_callbacks_before_manual_retry(
    lazy_window: MainWindow,
    qtbot,
) -> None:
    ready_panels: list[QWidget] = []
    failures: list[PanelPreparationFailure] = []

    class RetryPanel(QWidget):
        def __init__(self, *_args: Any) -> None:
            super().__init__()

    with patch.object(lazy_window, "_request_panel_prepare"):
        assert (
            lazy_window.switch_page(
                1,
                on_ready=ready_panels.append,
                on_failed=failures.append,
            )
            is False
        )
        lazy_window._on_panel_prepare_error(
            1,
            (RuntimeError, RuntimeError("injected prepare failure"), ""),
        )
        qtbot.waitUntil(lambda: len(failures) == 1, timeout=1_000)

        assert ready_panels == []
        preprocess_panel = cast(Any, lazy_window).preprocess_panel
        assert "Select it again to retry" in preprocess_panel.detail.text()

        assert lazy_window.switch_page(1) is False
        lazy_window._on_panel_prepare_result(1, RetryPanel)
        qtbot.waitUntil(
            lambda: 1 in lazy_window._loaded_panel_indices,
            timeout=1_000,
        )

    assert ready_panels == []
    assert failures[0].panel_index == 1
    assert failures[0].panel_name == "Preprocess"


def test_failed_handoff_cannot_open_dialog_after_manual_panel_retry(
    lazy_window: MainWindow,
    qtbot,
) -> None:
    class RetryPanel(QWidget):
        def __init__(self, *_args: Any) -> None:
            super().__init__()
            self.sidebar = SimpleNamespace(
                open_epoching=MagicMock(
                    return_value=InteractionOutcome.completed(
                        "Epoch settings were applied."
                    )
                )
            )

    host = WorkflowUiHandoffHost(lazy_window)
    request = WorkflowUiHandoffRequest.for_decision("create_epoch")
    terminal: list[Any] = []

    with patch.object(lazy_window, "_request_panel_prepare"):
        initial = host.open(request, on_terminal=terminal.append)
        lazy_window._on_panel_prepare_error(
            1,
            (RuntimeError, RuntimeError("injected prepare failure"), ""),
        )

        assert initial.status is WorkflowUiHandoffResolutionStatus.COMMAND_PENDING
        assert len(terminal) == 1
        assert terminal[0].status is WorkflowUiHandoffResolutionStatus.FAILED
        assert terminal[0].matches(request)
        assert host.active_request is None

        assert lazy_window.switch_page(1) is False
        lazy_window._on_panel_prepare_result(1, RetryPanel)
        qtbot.waitUntil(
            lambda: 1 in lazy_window._loaded_panel_indices,
            timeout=1_000,
        )

    retry_panel = cast(Any, lazy_window).preprocess_panel
    retry_panel.sidebar.open_epoching.assert_not_called()


def test_rapid_switch_does_not_activate_or_construct_stale_panel(
    lazy_window: MainWindow,
    qtbot,
) -> None:
    application = QCoreApplication.instance()
    assert application is not None
    construction_threads: list[tuple[int, QThread]] = []
    preprocess_ready: list[QWidget] = []
    training_ready: list[QWidget] = []

    class PreprocessPanel(QWidget):
        def __init__(self, *_args: Any) -> None:
            super().__init__()
            construction_threads.append((1, _current_thread()))

    class TrainingPanel(QWidget):
        def __init__(self, *_args: Any) -> None:
            super().__init__()
            construction_threads.append((2, _current_thread()))

    with patch.object(lazy_window, "_request_panel_prepare"):
        assert lazy_window.switch_page(1, on_ready=preprocess_ready.append) is False
        assert lazy_window.switch_page(2, on_ready=training_ready.append) is False

        lazy_window._on_panel_prepare_result(1, PreprocessPanel)
        qtbot.wait(0)
        assert 1 not in lazy_window._loaded_panel_indices
        assert preprocess_ready == []
        assert lazy_window.stack.currentIndex() == 2

        lazy_window._on_panel_prepare_result(2, TrainingPanel)
        qtbot.waitUntil(lambda: len(training_ready) == 1, timeout=1_000)
        assert lazy_window.stack.currentIndex() == 2
        assert preprocess_ready == []

        assert lazy_window.switch_page(1) is False
        lazy_window._schedule_panel_materialization(1)
        qtbot.waitUntil(lambda: len(preprocess_ready) == 1, timeout=1_000)

    assert construction_threads == [
        (2, application.thread()),
        (1, application.thread()),
    ]
    assert training_ready == [cast(Any, lazy_window).training_panel]
    assert preprocess_ready == [cast(Any, lazy_window).preprocess_panel]


def test_rapid_first_open_serializes_panel_prepare_workers(
    lazy_window: MainWindow,
    qtbot,
) -> None:
    class RecordingPool:
        def __init__(self) -> None:
            self.workers = []

        def start(self, worker) -> None:
            self.workers.append(worker)

    pool = RecordingPool()
    with patch(
        "XBrainLab.ui.main_window.QThreadPool.globalInstance",
        return_value=pool,
    ):
        assert lazy_window.switch_page(1) is False
        assert lazy_window.switch_page(0) is False

        assert len(pool.workers) == 1
        assert lazy_window._panel_prepare_active_index == 1
        assert lazy_window._panel_prepare_queue == [0]

        first_delivery = lazy_window._panel_prepare_workers[1][1]
        first_delivery.handle_finished()
        qtbot.waitUntil(lambda: len(pool.workers) == 2, timeout=1_000)

    assert lazy_window._panel_prepare_active_index == 0
    assert lazy_window._panel_prepare_queue == []
    assert list(lazy_window._panel_prepare_workers) == [0]


@pytest.mark.parametrize(
    ("panel_index", "panel_attr"),
    (
        (2, "training_panel"),
        (3, "evaluation_panel"),
        (4, "visualization_panel"),
    ),
)
def test_matplotlib_panel_prepare_and_construction_stay_on_gui_thread(
    lazy_window: MainWindow,
    qtbot,
    panel_index: int,
    panel_attr: str,
) -> None:
    application = QCoreApplication.instance()
    assert application is not None
    load_threads: list[QThread] = []
    construction_threads: list[QThread] = []
    ready_panels: list[QWidget] = []

    class MatplotlibPanel(QWidget):
        def __init__(self, *_args: Any) -> None:
            super().__init__()
            construction_threads.append(_current_thread())

    def _load_panel(_module: str, _class_name: str):
        load_threads.append(_current_thread())
        return MatplotlibPanel

    with (
        patch(
            "XBrainLab.ui.main_window._load_panel_class",
            side_effect=_load_panel,
        ),
        patch("XBrainLab.ui.main_window.QThreadPool.globalInstance") as thread_pool,
    ):
        assert (
            lazy_window.switch_page(panel_index, on_ready=ready_panels.append) is False
        )
        qtbot.waitUntil(lambda: len(ready_panels) == 1, timeout=1_000)

    assert load_threads == [application.thread()]
    assert construction_threads == [application.thread()]
    assert ready_panels == [getattr(lazy_window, panel_attr)]
    thread_pool.assert_not_called()


class _DeferredMainWindow:
    def __init__(self) -> None:
        self.callbacks: dict[int, list[Any]] = defaultdict(list)
        self.navigation_calls: list[int] = []
        self.status_bar = MagicMock()
        self.preprocess_panel = SimpleNamespace(
            sidebar=SimpleNamespace(
                open_epoching=MagicMock(
                    return_value=InteractionOutcome.completed("Epoch settings opened.")
                )
            )
        )
        self.training_panel = SimpleNamespace(
            sidebar=SimpleNamespace(
                split_data=MagicMock(
                    return_value=InteractionOutcome.completed(
                        "Dataset settings opened."
                    )
                )
            )
        )

    def switch_page(self, index: int, *, on_ready=None) -> bool:
        self.navigation_calls.append(index)
        if on_ready is not None:
            self.callbacks[index].append(on_ready)
        return False

    def statusBar(self):
        return self.status_bar


def test_handoff_first_open_completes_surface_through_public_ready_callback() -> None:
    window = _DeferredMainWindow()
    host = WorkflowUiHandoffHost(window)

    outcome = host.open(
        WorkflowUiHandoffRequest.for_decision(
            "create_epoch",
            decision_fields=("epoch_window",),
        )
    )

    assert outcome.status is WorkflowUiHandoffResolutionStatus.COMMAND_PENDING
    assert host.active_request is not None
    window.preprocess_panel.sidebar.open_epoching.assert_not_called()
    assert window.navigation_calls == [1]
    assert len(window.callbacks[1]) == 1

    window.callbacks[1][0](window.preprocess_panel)
    window.callbacks[1][0](window.preprocess_panel)

    window.preprocess_panel.sidebar.open_epoching.assert_called_once_with()
    assert host.active_request is None


def test_abandon_and_new_handoff_invalidate_stale_first_open_callback() -> None:
    window = _DeferredMainWindow()
    host = WorkflowUiHandoffHost(window)

    host.open(WorkflowUiHandoffRequest.for_decision("create_epoch"))
    stale_callback = window.callbacks[1][0]
    host.abandon_active()
    host.open(WorkflowUiHandoffRequest.for_decision("generate_dataset"))
    current_callback = window.callbacks[2][0]

    assert window.navigation_calls == [1, 2]
    stale_callback(window.preprocess_panel)
    stale_callback(window.preprocess_panel)
    window.preprocess_panel.sidebar.open_epoching.assert_not_called()

    host.abandon_active()
    current_callback(window.training_panel)
    window.training_panel.sidebar.split_data.assert_not_called()
