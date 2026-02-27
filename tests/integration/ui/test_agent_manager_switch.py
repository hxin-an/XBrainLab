from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QStackedWidget, QTabWidget, QWidget

from XBrainLab.ui.components.agent_manager import AgentManager


class MockMainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.stack = QStackedWidget()
        self.nav_btns = []
        # Create buttons
        for _ in range(5):
            btn = MagicMock()
            # btn needs setChecked
            self.nav_btns.append(btn)

        # Init main panels in stack (Indices 0-4)
        for i in range(5):
            panel = QWidget()
            if i == 4:  # Visualization Panel
                panel.tabs = QTabWidget()
                panel.tabs.addTab(QWidget(), "Map")
                panel.tabs.addTab(QWidget(), "Spectrogram")
                panel.tabs.addTab(QWidget(), "Topo")
                panel.tabs.addTab(QWidget(), "3D Plot")
            self.stack.addWidget(panel)

    def switch_page(self, index):
        """Mimic MainWindow.switch_page for testing."""
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_btns):
            btn.setChecked(i == index)

    def statusBar(self):
        return MagicMock()


@pytest.fixture
def mock_main_window(qtbot):
    """Mock entire MainWindow structure needed for AgentManager."""
    window = MockMainWindow()
    qtbot.addWidget(window)
    return window


def test_switch_panel_with_view_mode_logic(qtbot, mock_main_window):
    """
    Verify that AgentManager.switch_panel correctly:
    1. Switches the main stack to Visualization (index 4)
    2. Switches the Visualization tabs to 3D Plot (index 3)
    """
    study = MagicMock()
    # Mock ChatController to avoid dependencies
    with patch("XBrainLab.ui.components.agent_manager.ChatController"):
        manager = AgentManager(mock_main_window, study)

        # Action: Switch to 3D Plot
        params = {"panel": "visualization", "view_mode": "3d_plot"}
        manager.switch_panel(params)

        # Assert Main Stack Switch
        assert mock_main_window.stack.currentIndex() == 4

        # Assert Sub-Tab Switch
        vis_panel = mock_main_window.stack.widget(4)
        assert vis_panel.tabs.currentIndex() == 3  # 3D Plot is index 3
