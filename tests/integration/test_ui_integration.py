import os
import sys
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import Qt

# Ensure XBrainLab is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from XBrainLab.ui.main_window import MainWindow


@pytest.fixture
def mock_study():
    """Mock the backend Study object."""
    study = MagicMock()

    # Mock study.model_holder
    study.model_holder = MagicMock()
    study.model_holder.target_model.__name__ = "TestModel"

    # Mock trainer and training plans
    study.trainer = MagicMock()
    mock_plan = MagicMock()
    mock_plan.get_name.return_value = "TestPlan"
    mock_plan.model_holder.target_model.__name__ = "TestModel"
    mock_plan.record = {"test_acc": 0.85, "val_acc": 0.80, "train_acc": 0.90}
    mock_plan.get_plans.return_value = []
    study.trainer.get_training_plan_holders.return_value = [mock_plan]

    # Mock epoch data
    study.epoch_data = MagicMock()
    study.epoch_data.get_channel_names.return_value = ["C3", "C4", "Cz"]

    # Mock saliency params
    study.get_saliency_params.return_value = {}

    # Mock lists to be empty by default to comply with InfoPanel logic
    study.loaded_data_list = []
    study.preprocessed_data_list = []

    return study


def test_mainwindow_launch(qtbot, mock_study):
    """Test that MainWindow launches without error."""
    window = MainWindow(mock_study)
    qtbot.addWidget(window)

    # Check window title and visibility
    assert window.windowTitle() == "XBrainLab"
    window.show()
    assert window.isVisible()
    window.close()


def test_navigation(qtbot, mock_study):
    """Test navigation between main panels."""
    window = MainWindow(mock_study)
    qtbot.addWidget(window)
    window.show()

    # 1. Dataset (Default)
    assert window.stack.currentIndex() == 0

    # 2. Preprocess
    qtbot.mouseClick(window.nav_btns[1], Qt.MouseButton.LeftButton)
    assert window.stack.currentIndex() == 1

    # 3. Training
    qtbot.mouseClick(window.nav_btns[2], Qt.MouseButton.LeftButton)
    assert window.stack.currentIndex() == 2

    # 4. Evaluation
    qtbot.mouseClick(window.nav_btns[3], Qt.MouseButton.LeftButton)
    assert window.stack.currentIndex() == 3

    # 5. Visualization
    qtbot.mouseClick(window.nav_btns[4], Qt.MouseButton.LeftButton)
    assert window.stack.currentIndex() == 4

    window.close()


def test_evaluation_panel_init(qtbot, mock_study):
    """Test EvaluationPanel initialization and tab loading."""
    window = MainWindow(mock_study)
    qtbot.addWidget(window)

    # Switch to Evaluation
    window.switch_page(3)
    eval_panel = window.evaluation_panel

    # Check widgets exist (Matrix and Metrics Table are now separate/in
    # different layout)
    assert eval_panel.matrix_widget is not None
    assert eval_panel.metrics_table is not None

    # Check bottom tabs (Metrics Summary, Model Summary)
    assert eval_panel.bottom_tabs.count() >= 2
    assert eval_panel.bottom_tabs.tabText(0) == "Metrics Summary"
    assert eval_panel.bottom_tabs.tabText(1) == "Model Summary"

    window.close()


def test_visualization_panel_init(qtbot, mock_study):
    """Test VisualizationPanel initialization and tab loading."""
    window = MainWindow(mock_study)
    qtbot.addWidget(window)

    # Switch to Visualization
    window.switch_page(4)
    viz_panel = window.visualization_panel

    # Check tabs exist (Saliency Map, Topographic Map, Spectrogram, 3D Plot)
    assert viz_panel.tabs.count() >= 4
    assert viz_panel.tabs.tabText(0) == "Saliency Map"
    assert viz_panel.tabs.tabText(1) == "Spectrogram"
    assert viz_panel.tabs.tabText(2) == "Topographic Map"

    # Check if widgets inside tabs are initialized
    assert viz_panel.tab_map is not None
    assert viz_panel.tab_topo is not None

    window.close()
