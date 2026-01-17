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
