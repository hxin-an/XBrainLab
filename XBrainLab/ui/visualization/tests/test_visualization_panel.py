
import sys
import pytest
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget
from unittest.mock import MagicMock, patch
from XBrainLab.ui.visualization.panel import VisualizationPanel

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)

class MockMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.study = MagicMock()
        self.study.trainer = MagicMock()
        self.study.trainer.get_training_plan_holders.return_value = []
        self.study.epoch_data = MagicMock()

@pytest.fixture
def mock_main_window(qapp):
    return MockMainWindow()

class DummyWidget(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()

def test_visualization_panel_init(mock_main_window, qtbot):
    """Test initialization of VisualizationPanel."""
    # Mock child widgets to avoid complex init
    with patch('XBrainLab.ui.visualization.panel.SaliencyMapWidget', side_effect=DummyWidget), \
         patch('XBrainLab.ui.visualization.panel.SaliencyTopographicMapWidget', side_effect=DummyWidget), \
         patch('XBrainLab.ui.visualization.panel.SaliencySpectrogramWidget', side_effect=DummyWidget), \
         patch('XBrainLab.ui.visualization.panel.Saliency3DPlotWidget', side_effect=DummyWidget):
        
        panel = VisualizationPanel(mock_main_window)
        qtbot.addWidget(panel)
        
        assert hasattr(panel, 'tabs')
        assert panel.tabs.count() == 4

def test_visualization_panel_refresh_data(mock_main_window, qtbot):
    """Test refresh_data recreates widgets."""
    # Mock Trainer to return some plans
    mock_main_window.study.trainer.get_training_plan_holders.return_value = [MagicMock()]
    
    with patch('XBrainLab.ui.visualization.panel.SaliencyMapWidget', side_effect=DummyWidget) as MockMap, \
         patch('XBrainLab.ui.visualization.panel.SaliencyTopographicMapWidget', side_effect=DummyWidget) as MockTopo, \
         patch('XBrainLab.ui.visualization.panel.SaliencySpectrogramWidget', side_effect=DummyWidget) as MockSpec, \
         patch('XBrainLab.ui.visualization.panel.Saliency3DPlotWidget', side_effect=DummyWidget) as Mock3D, \
         patch('XBrainLab.ui.visualization.panel.QMessageBox.information'):
        
        panel = VisualizationPanel(mock_main_window)
        qtbot.addWidget(panel)
        
        panel.refresh_data()
        
        # Verify widgets were re-created (Init + Refresh = 2 calls)
        assert MockMap.call_count == 2
        assert MockTopo.call_count == 2
        assert MockSpec.call_count == 2
        assert Mock3D.call_count == 2

def test_visualization_panel_set_montage(mock_main_window, qtbot):
    """Test set_montage logic."""
    panel = VisualizationPanel(mock_main_window)
    qtbot.addWidget(panel)
    
    # Mock Dialog
    with patch('XBrainLab.ui.visualization.panel.PickMontageWindow') as MockDialog, \
         patch('XBrainLab.ui.visualization.panel.QMessageBox.information') as mock_info:
        
        instance = MockDialog.return_value
        instance.exec.return_value = True
        instance.get_result.return_value = (['Ch1'], {'Ch1': [0,0,0]})
        
        panel.set_montage()
        
        # Verify study updated
        mock_main_window.study.set_channels.assert_called_with(['Ch1'], {'Ch1': [0,0,0]})
        mock_info.assert_called_once()

def test_visualization_panel_set_saliency(mock_main_window, qtbot):
    """Test set_saliency logic."""
    panel = VisualizationPanel(mock_main_window)
    qtbot.addWidget(panel)
    
    with patch('XBrainLab.ui.visualization.panel.SetSaliencyWindow') as MockDialog, \
         patch('XBrainLab.ui.visualization.panel.QMessageBox.information') as mock_info:
        
        instance = MockDialog.return_value
        instance.exec.return_value = True
        instance.get_result.return_value = {'param': 1}
        
        panel.set_saliency()
        
        mock_main_window.study.set_saliency_params.assert_called_with({'param': 1})
        mock_info.assert_called_once()

if __name__ == "__main__":
    pytest.main([__file__])
