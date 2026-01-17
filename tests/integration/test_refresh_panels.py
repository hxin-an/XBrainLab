from unittest.mock import MagicMock

import pytest

from XBrainLab.ui.main_window import MainWindow


@pytest.fixture
def mock_study():
    study = MagicMock()
    # Mock necessary attributes for MainWindow init if any
    return study


def test_refresh_panels(qtbot, mock_study):
    """Test that refresh_panels calls update methods on all child panels."""
    # Setup
    window = MainWindow(mock_study)
    qtbot.addWidget(window)

    # Mock the panels
    window.dataset_panel = MagicMock()
    window.preprocess_panel = MagicMock()
    window.training_panel = MagicMock()
    window.evaluation_panel = MagicMock()
    window.visualization_panel = MagicMock()

    # Call refresh_panels
    window.refresh_panels()

    # Assert calls
    window.dataset_panel.update_panel.assert_called_once()
    window.preprocess_panel.update_panel.assert_called_once()
    window.training_panel.update_info.assert_called_once()
    window.evaluation_panel.update_info.assert_called_once()
    window.visualization_panel.update_info.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])
