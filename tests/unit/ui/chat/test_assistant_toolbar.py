"""Product regressions for the Assistant dock toolbar."""

from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, QSize, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QMainWindow

from XBrainLab.ui.components.agent_manager import AgentManager

AGENT_MANAGER_SOURCE = (
    Path(__file__).resolve().parents[4]
    / "XBrainLab"
    / "ui"
    / "components"
    / "agent_manager.py"
)
FORBIDDEN_TOOLBAR_GLYPHS = (
    "\N{VERTICAL ELLIPSIS}",
    "\N{UP ARROWHEAD}",
    "^",
    "\N{MULTIPLICATION SIGN}",
    "\N{LEFTWARDS ARROW}",
    "\N{RIGHTWARDS ARROW}",
)


@pytest.fixture
def assistant_manager(qtbot) -> Any:
    main_window = cast(Any, QMainWindow())
    main_window.ai_btn = MagicMock()
    qtbot.addWidget(main_window)
    study = MagicMock()
    study.get_controller.return_value = MagicMock()
    manager = cast(Any, AgentManager(main_window, study))
    manager.init_ui()
    yield manager
    manager.close()


def test_assistant_toolbar_source_has_no_options_menu_or_painted_icons() -> None:
    source = AGENT_MANAGER_SOURCE.read_text(encoding="utf-8")

    for glyph in FORBIDDEN_TOOLBAR_GLYPHS:
        assert f'QPushButton("{glyph}")' not in source
    assert "QMenu" not in source
    assert "QAction" not in source
    assert "def _assistant_title_icon(" not in source
    assert "QPainter" not in source


def test_assistant_toolbar_direct_buttons_have_one_accessible_contract(
    assistant_manager,
) -> None:
    expected = (
        (
            assistant_manager.new_conv_title_btn,
            "New chat",
            "Clear the assistant conversation without changing the EEG workflow.",
        ),
        (
            assistant_manager.float_btn,
            "Float assistant",
            "Move the Assistant into a separate movable window.",
        ),
        (
            assistant_manager.settings_btn,
            "Assistant settings",
            "Open Assistant settings.",
        ),
        (
            assistant_manager.close_btn,
            "Hide assistant",
            "Hide the Assistant panel without ending the conversation.",
        ),
    )

    for index, (button, accessible_name, accessible_description) in enumerate(expected):
        if index == 0:
            assert button.text() == "+"
            assert button.icon().isNull()
        else:
            assert button.text() == ""
            assert not button.icon().isNull()
        assert button.size() == QSize(30, 30)
        assert button.iconSize() == QSize(16, 16)
        assert button.toolTip()
        assert button.accessibleName() == accessible_name
        assert button.accessibleDescription() == accessible_description
        assert button.focusPolicy() == Qt.FocusPolicy.StrongFocus

    assert assistant_manager.settings_btn.isCheckable() is False
    assert assistant_manager.settings_btn.isChecked() is False
    assert assistant_manager.settings_btn.isDown() is False
    assert "QPushButton:checked" not in assistant_manager.settings_btn.styleSheet()
    assert not hasattr(assistant_manager, "settings_menu")
    assert not hasattr(assistant_manager, "retry_title_btn")


def test_assistant_toolbar_narrow_layout_keeps_essential_actions_reachable(
    assistant_manager,
    qtbot,
) -> None:
    title_bar = assistant_manager.assistant_header
    title_bar.resize(320, 36)
    title_bar.show()
    title_bar.layout().setGeometry(title_bar.rect())
    title_bar.layout().activate()
    qtbot.wait(10)

    assert title_bar.status_indicator is None
    assert title_bar.status_badge is None
    assert title_bar.status_dot is None

    essential = (
        assistant_manager.new_conv_title_btn,
        assistant_manager.float_btn,
        assistant_manager.settings_btn,
        assistant_manager.close_btn,
    )
    assert all(not button.isHidden() for button in essential)
    assert all(title_bar.rect().contains(button.geometry()) for button in essential)
    assert all(
        not first.geometry().intersects(second.geometry())
        for first, second in combinations(essential, 2)
    )


def test_assistant_toolbar_buttons_trigger_their_own_actions(
    assistant_manager,
    qtbot,
) -> None:
    dock = assistant_manager.chat_dock
    assert dock is not None
    dock.show()
    qtbot.wait(10)

    assistant_manager.chat_controller.add_user_message("hello")
    assistant_manager.new_conv_title_btn.click()
    assert assistant_manager.chat_controller.messages == []

    with patch.object(assistant_manager, "open_settings_dialog") as open_settings:
        assistant_manager.settings_btn.click()
    open_settings.assert_called_once_with()

    assistant_manager.float_btn.click()
    assert dock.isFloating()
    assert assistant_manager.float_btn.toolTip() == "Dock assistant"
    assert assistant_manager.float_btn.accessibleName() == "Dock assistant"

    assistant_manager.float_btn.click()
    assert not dock.isFloating()
    assert assistant_manager.float_btn.toolTip() == "Float assistant"

    assistant_manager.close_btn.click()
    assert dock.isHidden()


def test_floating_assistant_title_drag_changes_window_geometry(
    assistant_manager,
    qtbot,
    monkeypatch,
) -> None:
    dock = assistant_manager.chat_dock
    title_bar = assistant_manager.assistant_header
    assert dock is not None
    dock.show()
    dock.setFloating(True)
    dock.move(100, 100)
    QApplication.processEvents()
    qtbot.wait(10)

    monkeypatch.setattr(
        title_bar,
        "_start_system_move",
        lambda: False,
        raising=False,
    )
    start = dock.pos()
    local = QPoint(12, 12)
    global_start = start + local
    delta = QPoint(60, 40)

    title_bar.mousePressEvent(
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(local),
            QPointF(global_start),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    title_bar.mouseMoveEvent(
        QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(local + delta),
            QPointF(global_start + delta),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    title_bar.mouseReleaseEvent(
        QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(local + delta),
            QPointF(global_start + delta),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )

    assert dock.pos() == start + delta
