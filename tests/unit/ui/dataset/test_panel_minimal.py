from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QWidget

from XBrainLab.ui.panels.dataset.panel import DatasetPanel


@pytest.fixture
def app(qapp):
    """Ensure QApplication exists."""
    return qapp


@pytest.fixture
def mock_main_window(qapp):
    """Mock main window with study controller."""
    # Must be a QWidget to satisfy PyQt inheritance
    mw = QWidget()
    mw.study = MagicMock()
    # Mock dataset controller
    mw.study.get_controller.return_value = MagicMock()
    return mw


def test_dataset_panel_init(app, mock_main_window):
    """Verify DatasetPanel initializes without error and has UI components."""
    panel = DatasetPanel(parent=mock_main_window)

    # Check key components exist
    assert panel.table is not None
    assert panel.sidebar is not None
    assert panel.sidebar.info_panel is not None
    assert panel.sidebar.import_btn is not None
    assert panel.sidebar.chan_select_btn is not None
    assert panel.sidebar.clear_btn is not None

    # Check Theme application (check if styleSheet is not empty)
    assert "background-color" in panel.sidebar.info_panel.styleSheet()
    assert "background-color" in panel.sidebar.chan_select_btn.styleSheet()


def test_dataset_panel_no_parent(app):
    """Verify DatasetPanel can init without parent (headless/test mode)."""
    # Should not crash even if controller is missing
    panel = DatasetPanel(parent=None)
    assert panel.table is not None
