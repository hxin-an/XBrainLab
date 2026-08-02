"""Product regressions for the Assistant dock toolbar."""

from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QMainWindow

from XBrainLab.ui.components.agent_manager import AgentManager

AGENT_MANAGER_SOURCE = (
    Path(__file__).resolve().parents[4]
    / "XBrainLab"
    / "ui"
    / "components"
    / "agent_manager.py"
)
FORBIDDEN_TOOLBAR_GLYPHS = (
    "+",
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


def test_assistant_toolbar_source_uses_platform_icons_not_text_glyphs() -> None:
    source = AGENT_MANAGER_SOURCE.read_text(encoding="utf-8")

    for glyph in FORBIDDEN_TOOLBAR_GLYPHS:
        assert f'QPushButton("{glyph}")' not in source
    assert "def _assistant_title_icon(" not in source
    assert "QPainter" not in source


def test_assistant_toolbar_icon_buttons_have_one_accessible_contract(
    assistant_manager,
) -> None:
    expected = (
        (
            assistant_manager.retry_title_btn,
            "Retry last request",
            "Retry the most recent Assistant request.",
        ),
        (
            assistant_manager.new_conv_title_btn,
            "New chat",
            "Clear the assistant conversation without changing the EEG workflow.",
        ),
        (
            assistant_manager.settings_btn,
            "Assistant options",
            "Open Assistant settings and dock options.",
        ),
        (
            assistant_manager.close_btn,
            "Hide assistant",
            "Hide the Assistant panel without ending the conversation.",
        ),
    )

    for button, accessible_name, accessible_description in expected:
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


def test_assistant_toolbar_narrow_layout_keeps_essential_actions_reachable(
    assistant_manager,
    qtbot,
) -> None:
    title_bar = assistant_manager.assistant_header
    title_bar.set_retry_available(True, enabled=True)
    title_bar.resize(320, 36)
    title_bar.show()
    title_bar.layout().setGeometry(title_bar.rect())
    title_bar.layout().activate()
    qtbot.wait(10)

    assert title_bar.status_indicator is None
    assert title_bar.status_badge is None
    assert title_bar.status_dot is None
    assert assistant_manager.retry_title_btn.isHidden()

    essential = (
        assistant_manager.new_conv_title_btn,
        assistant_manager.settings_btn,
        assistant_manager.close_btn,
    )
    assert all(not button.isHidden() for button in essential)
    assert all(title_bar.rect().contains(button.geometry()) for button in essential)
    assert all(
        not first.geometry().intersects(second.geometry())
        for first, second in combinations(essential, 2)
    )


def test_assistant_options_expose_only_implemented_or_disabled_actions(
    assistant_manager,
) -> None:
    actions = assistant_manager.settings_menu.actions()

    assert [(action.text(), action.isEnabled()) for action in actions] == [
        ("Assistant settings", True),
        ("Float assistant", True),
        ("New chat", False),
    ]
