
import sys
from unittest.mock import MagicMock
import sys
sys.modules["mne"] = MagicMock()

import pytest
from PyQt6.QtWidgets import QApplication
from XBrainLab.ui.training.panel import TrainingPanel

def test_training_panel_layout(qtbot):
    """Test that the TrainingPanel has the correct new layout elements."""
    app = QApplication.instance() or QApplication(sys.argv)
    
    # Configure model_holder using a dummy object
    class DummyModel:
        __name__ = "DummyModel"
        
    class DummyModelHolder:
        target_model = DummyModel
        
    class DummyStudy:
        def __init__(self):
            self.dataset_generator = None
            self.model_holder = DummyModelHolder()
            self.training_option = None
            self.trainer = MagicMock()
            self.loaded_data_list = []
            self.epoch_data = None
            
            
    mock_study = DummyStudy()
    
    class DummyMainWindow:
        def __init__(self):
            self.study = mock_study
            
    mock_main_window = DummyMainWindow()
    
    # Instantiate TrainingPanel with main_window
    panel = TrainingPanel(mock_main_window)
    qtbot.addWidget(panel)
    
    # Check for Summary Table
    assert hasattr(panel, 'summary_table')
    assert panel.summary_table.columnCount() == 2
    
    # Check for History Table
    assert hasattr(panel, 'history_table')
    assert panel.history_table.columnCount() == 8
    header_labels = [panel.history_table.horizontalHeaderItem(i).text() for i in range(8)]
    assert header_labels == ["Model", "Progress", "Epoch", "Train Loss", "Train Acc", "Val Loss", "Val Acc", "LR"]
    
    # Check Buttons
    assert hasattr(panel, 'btn_split')
    assert hasattr(panel, 'btn_model')
    assert hasattr(panel, 'btn_setting')
    assert hasattr(panel, 'btn_start')
    assert hasattr(panel, 'btn_stop')
    assert hasattr(panel, 'btn_clear')
    
    # Check removed elements
    assert not hasattr(panel, 'btn_test_setting')
    assert not hasattr(panel, 'btn_gen_plan')
    assert not hasattr(panel, 'progress_bar')
    assert not hasattr(panel, 'history_list')

def test_update_summary_with_split_info(qtbot):
    """Test that update_summary displays split type info."""
    app = QApplication.instance() or QApplication(sys.argv)
    
    # Mock DataSplitter and Config
    class MockSplitter:
        def __init__(self, text, unit=None, val=None):
            self.text = text
            self.split_unit = MagicMock()
            if unit:
                self.split_unit.value = unit
            else:
                self.split_unit = None
            self.value_var = val
            self.is_option = True
            
    class MockConfig:
        def __init__(self):
            self.val_splitter_list = [MockSplitter("By Session", "Ratio", "0.2")]
            self.test_splitter_list = [MockSplitter("By Subject", "LeaveOneOut", "1")]
            
    class MockGenerator:
        def __init__(self):
            self.config = MockConfig()
            self.datasets = []
            
    class DummyStudy:
        def __init__(self):
            self.dataset_generator = MockGenerator()
            self.model_holder = None
            self.training_option = None
            self.trainer = MagicMock()
            
    mock_study = DummyStudy()
    
    class DummyMainWindow:
        def __init__(self):
            self.study = mock_study
            
    panel = TrainingPanel(DummyMainWindow())
    qtbot.addWidget(panel)
    
    # Trigger update
    panel.update_summary()
    
    # Verify Table Content
    # We expect rows for Val Split and Test Split
    found_val = False
    found_test = False
    
    for row in range(panel.summary_table.rowCount()):
        key = panel.summary_table.item(row, 0).text()
        val = panel.summary_table.item(row, 1).text()
        
        if key == "Val Split":
            assert "By Session" in val
            assert "Ratio: 0.2" in val
            found_val = True
        elif key == "Test Split":
            assert "By Subject" in val
            assert "LeaveOneOut: 1" in val
            found_test = True
            
    assert found_val
    assert found_test

if __name__ == "__main__":
    pytest.main([__file__])
