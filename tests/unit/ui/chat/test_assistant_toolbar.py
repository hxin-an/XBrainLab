"""Product regressions for the Assistant dock toolbar."""

from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QMainWindow

from XBrainLab.ui.chat.assistant_dock import AssistantDockView
from XBrainLab.ui.components.agent_manager import AgentManager

ASSISTANT_DOCK_SOURCE = (
    Path(__file__).resolve().parents[4]
    / "XBrainLab"
    / "ui"
    / "chat"
    / "assistant_dock.py"
)
FORBIDDEN_TOOLBAR_GLYPHS = (
    "\N{VERTICAL ELLIPSIS}",
    "\N{UP ARROWHEAD}",
    "^",
    "\N{MULTIPLICATION SIGN}",
    "\N{LEFTWARDS ARROW}",
    "\N{RIGHTWARDS ARROW}",
)


def _assistant_dock(manager: AgentManager) -> AssistantDockView:
    dock = manager.chat_dock
    assert isinstance(dock, AssistantDockView)
    return dock


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
    source = ASSISTANT_DOCK_SOURCE.read_text(encoding="utf-8")

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
            _assistant_dock(assistant_manager).new_conversation_button,
            "New chat",
            "Clear the assistant conversation without changing the EEG workflow.",
        ),
        (
            _assistant_dock(assistant_manager).settings_button,
            "Assistant settings",
            "Open Assistant settings.",
        ),
        (
            _assistant_dock(assistant_manager).close_button,
            "Hide assistant",
            "Hide the Assistant panel without ending the conversation.",
        ),
    )

    for index, (button, accessible_name, accessible_description) in enumerate(expected):
        assert button is not None
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

    settings_button = _assistant_dock(assistant_manager).settings_button
    assert settings_button is not None
    assert settings_button.isCheckable() is False
    assert settings_button.isChecked() is False
    assert settings_button.isDown() is False
    assert "QPushButton:checked" not in settings_button.styleSheet()
    assert not hasattr(assistant_manager, "settings_menu")
    assert not hasattr(assistant_manager, "retry_title_btn")


def test_assistant_toolbar_narrow_layout_keeps_essential_actions_reachable(
    assistant_manager,
    qtbot,
) -> None:
    title_bar = _assistant_dock(assistant_manager).title_bar
    assert title_bar is not None
    title_bar.resize(320, 36)
    title_bar.show()
    title_bar.layout().setGeometry(title_bar.rect())
    title_bar.layout().activate()
    qtbot.wait(10)

    assert title_bar.status_indicator is None
    assert title_bar.status_badge is None
    assert title_bar.status_dot is None

    essential = (
        _assistant_dock(assistant_manager).new_conversation_button,
        _assistant_dock(assistant_manager).settings_button,
        _assistant_dock(assistant_manager).close_button,
    )
    assert all(button is not None for button in essential)
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
    new_conversation_button = _assistant_dock(assistant_manager).new_conversation_button
    assert new_conversation_button is not None
    new_conversation_button.click()
    assert assistant_manager.chat_controller.messages == []

    with patch.object(assistant_manager, "open_settings_dialog") as open_settings:
        settings_button = _assistant_dock(assistant_manager).settings_button
        assert settings_button is not None
        settings_button.click()
    open_settings.assert_called_once_with()

    assert dock.isFloating() is False
    assert not hasattr(assistant_manager, "float_btn")

    close_button = _assistant_dock(assistant_manager).close_button
    assert close_button is not None
    close_button.click()
    assert dock.isHidden()
