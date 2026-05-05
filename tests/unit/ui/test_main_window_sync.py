from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QWidget

from XBrainLab.ui.main_window import MainWindow


@pytest.fixture
def mock_study():
    return MagicMock()


@pytest.fixture
def main_window(mock_study, qtbot):
    # Patch init_panels and init_agent to avoid creating real widgets
    with (
        patch("XBrainLab.ui.main_window.MainWindow.init_panels"),
        patch("XBrainLab.ui.main_window.MainWindow.init_agent"),
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


def test_update_info_panel_uses_info_service(main_window):
    """Shared refresh should update registered AggregateInfoPanel instances."""
    main_window.info_service = MagicMock()

    main_window.update_info_panel()

    main_window.info_service.notify_all.assert_called_once()


def test_update_info_panel_keeps_legacy_direct_panel_fallback(main_window):
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
