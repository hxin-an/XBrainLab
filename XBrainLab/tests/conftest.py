# Global mocks have been disabled as the environment has all dependencies installed.
# Previously, this file mocked mne, captum, and torch, which caused import errors.

import sys
import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QMessageBox, QDialog

# Mock mne to avoid import errors globally if needed (currently disabled)
if "mne" not in sys.modules:
    pass 

@pytest.fixture(autouse=True)
def mock_ui_blocking():
    """
    Globally mock blocking UI calls to prevent tests from hanging.
    This handles QMessageBox and QDialog.exec().
    """
    # Patch QMessageBox static methods
    with patch('PyQt6.QtWidgets.QMessageBox.information') as mock_info, \
         patch('PyQt6.QtWidgets.QMessageBox.warning') as mock_warn, \
         patch('PyQt6.QtWidgets.QMessageBox.critical') as mock_crit, \
         patch('PyQt6.QtWidgets.QMessageBox.question') as mock_quest, \
         patch('PyQt6.QtWidgets.QMessageBox.exec', return_value=QMessageBox.StandardButton.Ok) as mock_msg_exec, \
         patch('PyQt6.QtWidgets.QDialog.exec', return_value=QDialog.DialogCode.Accepted) as mock_dlg_exec:
        
        # Configure defaults
        mock_quest.return_value = QMessageBox.StandardButton.Yes
        
        yield
