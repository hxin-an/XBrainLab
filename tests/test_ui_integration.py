import pytest
import sys
import os
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

# Ensure XBrainLab is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from XBrainLab.ui.main_window import MainWindow

@pytest.fixture
def mock_study():
    """Mock the backend Study object."""
    study = MagicMock()
    
    # Mock trainer and training plans
    study.trainer = MagicMock()
    mock_holder = MagicMock()
    mock_holder.model_name = "TestModel"
    mock_holder.record = {"test_acc": 0.85, "val_acc": 0.80, "train_acc": 0.90}
    # Mocking get_training_plan_holders to return a list
    mock_holder.get_name.return_value = "TestModel"
    mock_holder.get_plans.return_value = [] # Mock get_plans
    study.trainer.get_training_plan_holders.return_value = [mock_holder]
    
    # Mock epoch data
    study.epoch_data = MagicMock()
    study.epoch_data.get_channel_names.return_value = ["C3", "C4", "Cz"]
    
    # Mock saliency params
    study.get_saliency_params.return_value = {}
    
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
    
    # Check tabs exist (Performance Table, Confusion Matrix, Model Output)
    assert eval_panel.tabs.count() >= 3
    assert eval_panel.tabs.tabText(0) == "Performance Table"
    assert eval_panel.tabs.tabText(1) == "Confusion Matrix"
    
    # Check if widgets inside tabs are initialized (not None)
    assert eval_panel.tab_table is not None
    assert eval_panel.tab_matrix is not None
    
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
    assert viz_panel.tabs.tabText(1) == "Topographic Map"
    
    # Check if widgets inside tabs are initialized
    assert viz_panel.tab_map is not None
    assert viz_panel.tab_topo is not None
    
    window.close()
