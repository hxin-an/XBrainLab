import pytest
from PyQt6.QtWidgets import QDialog, QLineEdit, QPushButton, QComboBox, QTableWidget, QTableWidgetItem, QWidget
from unittest.mock import MagicMock, patch
import torch
from XBrainLab.ui_pyqt.training.training_setting import (
    TrainingSettingWindow, SetOptimizerWindow, SetDeviceWindow
)
from XBrainLab.training import TRAINING_EVALUATION

class TestTrainingSetting:
    @pytest.fixture
    def window(self, qtbot):
        window = TrainingSettingWindow(None)
        qtbot.addWidget(window)
        return window

    def test_init(self, window):
        assert window.windowTitle() == "Training Setting"
        # Verify default values are set
        assert window.epoch_entry.text() == "10"
        assert window.bs_entry.text() == "32"
        assert window.lr_entry.text() == "0.001"
        assert window.checkpoint_entry.text() == "1"
        assert window.repeat_entry.text() == "1"
        assert window.output_dir == "./output"
        assert window.optim == torch.optim.Adam
        assert window.use_cpu == True
        
    def test_set_values_and_confirm(self, window):
        # Set simple values
        window.epoch_entry.setText("10")
        window.bs_entry.setText("32")
        window.lr_entry.setText("0.001")
        window.checkpoint_entry.setText("5")
        window.repeat_entry.setText("1")
        
        # Mock Optimizer and Device setting (since they open dialogs)
        window.optim = MagicMock()
        window.optim_params = {}  # lr is separate parameter
        window.use_cpu = True
        window.gpu_idx = None
        window.output_dir = "/tmp/output"
        
        # Select Evaluation
        window.evaluation_combo.setCurrentIndex(0)
        
        # Confirm
        with patch.object(window, 'accept') as mock_accept:
            window.confirm()
            mock_accept.assert_called_once()
            
        # Verify result
        option = window.get_result()
        assert option.epoch == 10
        assert option.bs == 32
        assert option.lr == 0.001
        assert option.output_dir == "/tmp/output"
        assert option.use_cpu is True

    def test_set_output_dir(self, window):
        with patch('PyQt6.QtWidgets.QFileDialog.getExistingDirectory', return_value="/tmp/test"):
            window.set_output_dir()
            assert window.output_dir == "/tmp/test"
            assert window.output_dir_label.text() == "/tmp/test"
            assert window.output_dir_label.text() == "/tmp/test"

    def test_load_settings(self, qtbot):
        # Create a real QWidget parent
        parent = QWidget()
        mock_study = MagicMock()
        mock_option = MagicMock()
        
        # Configure option
        mock_option.epoch = 50
        mock_option.bs = 64
        mock_option.lr = 0.005
        mock_option.checkpoint_epoch = 10
        mock_option.repeat_num = 3
        mock_option.output_dir = "/tmp/loaded"
        mock_option.use_cpu = False
        mock_option.gpu_idx = 0
        mock_option.optim = MagicMock()
        mock_option.optim.__name__ = "Adam"
        mock_option.optim_params = {}  # lr is separate parameter
        mock_option.evaluation_option.value = "Last Epoch"
        
        mock_study.training_option = mock_option
        parent.study = mock_study
        
        # Initialize window with real parent
        window = TrainingSettingWindow(parent)
        qtbot.addWidget(window)
        
        # Verify fields are populated
        assert window.epoch_entry.text() == "50"
        assert window.bs_entry.text() == "64"
        assert window.lr_entry.text() == "0.005"
        assert window.checkpoint_entry.text() == "10"
        assert window.repeat_entry.text() == "3"
        assert window.output_dir == "/tmp/loaded"
        assert window.output_dir_label.text() == "/tmp/loaded"
        assert window.use_cpu is False
        assert window.gpu_idx == 0
        assert "Adam" in window.opt_label.text()
        # GPU check depends on parse_device_name logic
        # If use_cpu is False and gpu_idx is 0, it calls torch.cuda.get_device_name(0)
        # We should mock torch.cuda.get_device_name
        with patch('torch.cuda.get_device_name', return_value="Test GPU"):
             # Re-load settings to trigger label update with mocked device name
             window.load_settings()
             assert "0 - Test GPU" in window.dev_label.text()
             
        assert window.evaluation_combo.currentText() == "Last Epoch"
class TestSetOptimizer:
    @pytest.fixture
    def window(self, qtbot):
        # Mock torch.optim members
        with patch('inspect.getmembers') as mock_members:
            mock_members.return_value = [('Adam', torch.optim.Adam)]
            window = SetOptimizerWindow(None)
            qtbot.addWidget(window)
            return window

    def test_init_and_populate(self, window):
        assert window.algo_combo.count() == 1
        assert window.algo_combo.currentText() == "Adam"
        # Check params table (Adam has betas, eps, weight_decay, amsgrad, ...)
        # We just check if it's populated
        assert window.params_table.rowCount() > 0

    def test_confirm(self, window):
        # Clear table to avoid parameter conflicts (like lr)
        window.params_table.setRowCount(0)

        # Inject mock target
        mock_target = MagicMock()
        window.algo_map['Adam'] = mock_target
        
        with patch.object(window, 'accept') as mock_accept:
            window.confirm()
            mock_accept.assert_called_once()
            
        mock_target.assert_called()
                
        optim, params = window.get_result()
        assert optim == mock_target
        assert isinstance(params, dict)

class TestSetDevice:
    @pytest.fixture
    def window(self, qtbot):
        with patch('torch.cuda.device_count', return_value=1):
            with patch('torch.cuda.get_device_name', return_value="Test GPU"):
                window = SetDeviceWindow(None)
                qtbot.addWidget(window)
                return window

    def test_init(self, window):
        assert window.device_list.count() == 2 # CPU + 1 GPU
        assert window.device_list.item(0).text() == "CPU"
        assert "Test GPU" in window.device_list.item(1).text()

    def test_confirm_cpu(self, window):
        window.device_list.setCurrentRow(0)
        with patch.object(window, 'accept') as mock_accept:
            window.confirm()
            mock_accept.assert_called_once()
            
        use_cpu, gpu_idx = window.get_result()
        assert use_cpu is True
        assert gpu_idx is None

    def test_confirm_gpu(self, window):
        window.device_list.setCurrentRow(1)
        with patch.object(window, 'accept') as mock_accept:
            window.confirm()
            mock_accept.assert_called_once()
            
        use_cpu, gpu_idx = window.get_result()
        assert use_cpu is False
        assert gpu_idx == 0
