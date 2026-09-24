"""Tests for VRAMConflictChecker."""

from __future__ import annotations

import configparser
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PyQt6.QtCore import QPoint, Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QMainWindow,
    QStackedWidget,
    QTabWidget,
    QWidget,
)

from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
    AssistantRuntimeSnapshot,
)
from XBrainLab.ui.components.modal_presentation import ModalAlertDialog
from XBrainLab.ui.components.vram_checker import VRAMConflictChecker
from XBrainLab.ui.qt_settings import application_settings


@pytest.fixture()
def widget_main_window(qtbot):
    main_window = QMainWindow()
    stack = QStackedWidget(main_window)
    # The visible workspace order is intentionally fixed here rather than
    # derived from the implementation constants being consolidated.
    for _ in range(4):
        stack.addWidget(QWidget(stack))

    visualization_panel = QWidget(stack)
    tabs = QTabWidget(visualization_panel)
    for label in (
        "Saliency Map",
        "Spectrogram",
        "Topographic Map",
        "3D Plot",
    ):
        tabs.addTab(QWidget(tabs), label)
    stack.addWidget(visualization_panel)
    stack.setCurrentIndex(4)

    main_window.setCentralWidget(stack)
    main_window.stack = stack
    main_window.visualization_panel = visualization_panel
    visualization_panel.tabs = tabs
    qtbot.addWidget(main_window)
    main_window.show()
    return main_window


@pytest.fixture()
def local_runtime_snapshot():
    return AssistantRuntimeSnapshot(
        phase=AssistantRuntimePhase.READY,
        initialized=True,
        backend_mode="local",
    )


@pytest.fixture()
def widget_checker(widget_main_window, local_runtime_snapshot):
    return VRAMConflictChecker(widget_main_window, lambda: local_runtime_snapshot)


@pytest.fixture()
def acknowledge_warning(allow_real_modals):
    del allow_real_modals

    def run(action):
        dialogs = []

        def acknowledge():
            dialog = QApplication.activeModalWidget()
            dialogs.append(dialog)
            dialog.acknowledge_button.click()

        QTimer.singleShot(0, acknowledge)
        action()
        assert len(dialogs) == 1
        assert isinstance(dialogs[0], ModalAlertDialog)
        return dialogs[0]

    return run


def test_real_widgets_warn_for_initialized_local_mode_with_active_3d(
    widget_main_window,
    widget_checker,
    acknowledge_warning,
):
    widget_main_window.visualization_panel.tabs.setCurrentIndex(3)
    assert not widget_main_window.visualization_panel.isHidden()
    assert widget_main_window.stack.currentIndex() == 4

    dialog = acknowledge_warning(widget_checker.check)
    assert dialog.windowTitle() == "GPU Memory Usage"
    assert dialog.message_label.text() == (
        "Using the local Assistant with 3D Plot may increase GPU memory use."
        " If the app slows down, try using one at a time."
    )
    assert dialog.opt_out_checkbox.text() == "Don't show this again"


@pytest.mark.parametrize(
    ("tab_index", "panel_hidden", "stack_index", "initialized", "backend_mode"),
    [
        (0, False, 4, True, "local"),
        (3, True, 4, True, "local"),
        (3, False, 0, True, "local"),
        (3, False, 4, True, "remote"),
        (3, False, 4, False, "local"),
    ],
    ids=("other-tab", "hidden", "other-workspace", "nonlocal", "not-initialized"),
)
def test_real_widgets_skip_warning_outside_active_local_3d_conditions(
    widget_main_window,
    tab_index,
    panel_hidden,
    stack_index,
    initialized,
    backend_mode,
):
    widget_main_window.visualization_panel.tabs.setCurrentIndex(tab_index)
    widget_main_window.stack.setCurrentIndex(stack_index)
    if panel_hidden:
        widget_main_window.visualization_panel.hide()
    snapshot = AssistantRuntimeSnapshot(
        phase=AssistantRuntimePhase.READY
        if initialized
        else AssistantRuntimePhase.IDLE,
        initialized=initialized,
        backend_mode=backend_mode,
    )
    checker = VRAMConflictChecker(widget_main_window, lambda: snapshot)

    checker.check()

    assert widget_main_window.visualization_panel.isHidden() is (
        panel_hidden or stack_index != 4
    )
    assert widget_main_window.stack.currentIndex() == stack_index


def test_real_widgets_warn_when_switching_to_local_with_3d_visible(
    widget_main_window,
    acknowledge_warning,
):
    widget_main_window.visualization_panel.tabs.setCurrentIndex(3)
    remote_snapshot = AssistantRuntimeSnapshot(
        phase=AssistantRuntimePhase.READY,
        initialized=True,
        backend_mode="remote",
    )
    checker = VRAMConflictChecker(widget_main_window, lambda: remote_snapshot)

    acknowledge_warning(lambda: checker.check(switching_to_local=True))


def test_real_widgets_warn_when_switching_to_3d_with_local_mode(
    widget_main_window,
    widget_checker,
    acknowledge_warning,
):
    widget_main_window.visualization_panel.tabs.setCurrentIndex(0)

    widget_checker.on_viz_tab_changed(0)
    acknowledge_warning(lambda: widget_checker.on_viz_tab_changed(3))


def test_real_widgets_skip_warning_when_runtime_snapshot_is_unavailable(
    widget_main_window,
):
    widget_main_window.visualization_panel.tabs.setCurrentIndex(3)

    def unavailable_snapshot():
        raise RuntimeError("runtime not ready")

    checker = VRAMConflictChecker(widget_main_window, unavailable_snapshot)
    checker.check()


def test_real_widgets_skip_warning_for_lazy_visualization_placeholder(
    widget_main_window,
    local_runtime_snapshot,
):
    lazy_placeholder = QWidget(widget_main_window)
    widget_main_window.visualization_panel = lazy_placeholder
    checker = VRAMConflictChecker(widget_main_window, lambda: local_runtime_snapshot)

    checker.check()


@pytest.mark.parametrize(
    ("checked", "dismiss", "persisted"),
    [
        (True, "ok", True),
        (False, "ok", False),
        (True, "escape", False),
        (True, "close", False),
    ],
)
def test_checked_acknowledgement_persists_advisory_opt_out(
    widget_main_window,
    local_runtime_snapshot,
    allow_real_modals,
    checked,
    dismiss,
    persisted,
):
    del allow_real_modals
    observed = []

    def acknowledge():
        dialog = QApplication.activeModalWidget()
        checkbox = dialog.findChild(QCheckBox)
        observed.append(checkbox is not None)
        if checkbox is not None and checked:
            QTest.mouseClick(
                checkbox,
                Qt.MouseButton.LeftButton,
                pos=QPoint(8, checkbox.height() // 2),
            )
        if checkbox is not None:
            observed.append(checkbox.isChecked())
        if dismiss == "ok":
            dialog.acknowledge_button.click()
        elif dismiss == "escape":
            QTest.keyClick(dialog, Qt.Key.Key_Escape)
        else:
            dialog.close()

    QTimer.singleShot(0, acknowledge)
    checker = VRAMConflictChecker(widget_main_window, lambda: local_runtime_snapshot)
    checker.check(switching_to_3d=True)

    assert observed == [True, checked], "VRAM warning needs an operable opt-out"
    settings = application_settings()
    settings.sync()
    assert (
        settings.value("warnings/suppress_local_assistant_3d", False, type=bool)
        is persisted
    )
    if persisted:
        # Inspect disk, not only QSettings' shared in-process cache.
        stored = configparser.ConfigParser()
        stored.read(settings.fileName())
        assert stored.getboolean("warnings", "suppress_local_assistant_3d")
        # A fresh interpreter must see the same preference through the product
        # settings factory, without pytest's settings isolation or Qt cache.
        restored = subprocess.run(  # noqa: S603 - fixed code and current interpreter
            [
                sys.executable,
                "-c",
                "from XBrainLab.ui.qt_settings import application_settings; "
                "assert application_settings().value("
                "'warnings/suppress_local_assistant_3d', False, type=bool)",
            ],
            env={
                **os.environ,
                "XBRAINLAB_CONFIG_DIR": str(Path(settings.fileName()).parent.parent),
            },
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert restored.returncode == 0, restored.stderr

    # A new checker must restore the choice, for either entry direction.
    observed.clear()
    widget_main_window.visualization_panel.tabs.setCurrentIndex(3)
    fresh_checker = VRAMConflictChecker(
        widget_main_window, lambda: local_runtime_snapshot
    )
    for switching in ({"switching_to_local": True}, {"switching_to_3d": True}):
        if not persisted:
            QTimer.singleShot(0, acknowledge)
        fresh_checker.check(**switching)
    assert observed == ([] if persisted else [True, checked, True, checked])
