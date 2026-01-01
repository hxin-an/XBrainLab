import pytest
from PyQt6.QtWidgets import QDialog
from unittest.mock import MagicMock, patch
from XBrainLab.ui_pyqt.dashboard_panel.preprocess import ICADialog

@pytest.fixture
def mock_data():
    return [MagicMock()]

def test_ica_dialog_init(mock_data, qtbot):
    """Test initialization of ICADialog."""
    # Mock Preprocessor.ICA to avoid backend logic
    with patch('XBrainLab.preprocessor.ICA'):
        dialog = ICADialog(None, mock_data)
        qtbot.addWidget(dialog)
        
        # Verify Window Title
        assert dialog.windowTitle() == "Auto ICA"
        
        # Verify Method Combo Items
        assert dialog.method_combo.count() == 3
        assert "fastica" in dialog.method_combo.itemText(0)
        assert "picard" in dialog.method_combo.itemText(1)
        assert "infomax" in dialog.method_combo.itemText(2)

def test_ica_dialog_accept(mock_data, qtbot):
    """Test accept logic and worker instantiation."""
    with patch('XBrainLab.preprocessor.ICA') as MockICA:
        dialog = ICADialog(None, mock_data)
        qtbot.addWidget(dialog)
        
        # Mock QProgressDialog to avoid showing it
        with patch('PyQt6.QtWidgets.QProgressDialog') as MockProgress:
            mock_progress = MockProgress.return_value
            
            # Mock ICAWorker
            with patch('XBrainLab.ui_pyqt.dashboard_panel.preprocess.ICAWorker') as MockWorker:
                mock_worker = MockWorker.return_value
                
                # Select "picard (Robust, slower)"
                # Assuming it's at index 1
                dialog.method_combo.setCurrentIndex(1)
                
                # Call accept (which triggers worker start)
                dialog.accept()
                
                # Verify Worker instantiated with correct arguments
                # args: preprocessor, n_components, method
                args, _ = MockWorker.call_args
                
                # Check method argument (should be 'picard', stripped of description)
                assert args[2] == 'picard'
                
                # Verify worker started
                mock_worker.start.assert_called_once()
