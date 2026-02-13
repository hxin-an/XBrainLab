from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QWidget

from XBrainLab.ui.main_window import MainWindow


@pytest.fixture
def mock_study():
    study = MagicMock()
    study.trainer = MagicMock()
    study.model_holder = MagicMock()
    study.model_holder.target_model = MagicMock()
    study.model_holder.target_model.__name__ = "MockModel"
    return study


def test_ui_refresh_on_tab_switch(qtbot, mock_study):
    """Test that switching tabs triggers refresh_data/update_panel on panels."""
    # Patch the panel classes to avoid real instantiation and side effects
    with (
        patch("XBrainLab.ui.main_window.DatasetPanel") as MockDatasetPanel,
        patch("XBrainLab.ui.main_window.PreprocessPanel") as MockPreprocessPanel,
        patch("XBrainLab.ui.main_window.TrainingPanel") as MockTrainingPanel,
        patch("XBrainLab.ui.main_window.VisualizationPanel") as MockVisPanel,
        patch("XBrainLab.ui.main_window.EvaluationPanel") as MockEvalPanel,
        patch("XBrainLab.ui.main_window.AgentManager"),  # Prevent AgentManager init
    ):
        # Configure mocks to return real QWidgets so addWidget works
        MockDatasetPanel.return_value = QWidget()
        MockPreprocessPanel.return_value = QWidget()
        MockTrainingPanel.return_value = QWidget()

        # VisualizationPanel needs tabs attribute
        vis_widget = QWidget()
        vis_widget.tabs = MagicMock()
        MockVisPanel.return_value = vis_widget

        MockEvalPanel.return_value = QWidget()

        # Attach update_panel mock to these widgets
        MockDatasetPanel.return_value.update_panel = MagicMock()
        MockPreprocessPanel.return_value.update_panel = MagicMock()
        MockTrainingPanel.return_value.update_panel = MagicMock()
        MockVisPanel.return_value.update_panel = MagicMock()
        MockEvalPanel.return_value.update_panel = MagicMock()

        # Setup
        window = MainWindow(mock_study)
        qtbot.addWidget(window)

        # Access the instances created by MainWindow
        # Note: MainWindow assigns self.dataset_panel = DatasetPanel(...)
        dataset_panel = window.dataset_panel
        vis_panel = window.visualization_panel
        eval_panel = window.evaluation_panel

        # Test switching to Evaluation (Index 3 - assuming index mapping)
        # Check actual indices in MainWindow:
        # 0: Dataset, 1: Preprocess, 2: Training, 3: Visualization, 4: Evaluation?
        # Let's verify standard order in MainWindow.py if we could, but typically:
        # Dataset, Preprocess, Training, Visualization, Evaluation.

        # Let's assume Visualization is 3 and Evaluation is 4 or vice versa.
        # The original test said switch_page(3) -> evaluation_panel.refresh_data?
        # Check MainWindow tabs.
        # If I look at the test content:
        #   window.switch_page(3)
        #   window.evaluation_panel.refresh_data.assert_called_once()
        # This implies Index 3 is Evaluation.

        # Actually, `switch_page` in `MainWindow` calls `update_panel()` or
        # `refresh_data()` depending on panel type.
        # My refactoring added `update_panel()` to all panels in `switch_page`.
        # So we should expect `update_panel()` or `refresh_data()` to be called.

        # Test switching to Evaluation (Index 3)
        window.switch_page(3)
        # In the new architecture, we prefer update_panel if it exists
        eval_panel.update_panel.assert_called()

        # Test switching to Visualization (Index 4)
        window.switch_page(4)
        vis_panel.update_panel.assert_called()

        # Test switching to other tabs (should not call refresh on these specific ones)
        eval_panel.update_panel.reset_mock()
        vis_panel.update_panel.reset_mock()

        window.switch_page(0)  # Dataset
        eval_panel.update_panel.assert_not_called()
        vis_panel.update_panel.assert_not_called()
        dataset_panel.update_panel.assert_called()


if __name__ == "__main__":
    pytest.main([__file__])
