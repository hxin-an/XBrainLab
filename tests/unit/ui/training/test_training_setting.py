from unittest.mock import MagicMock, patch

import pytest
import torch

from XBrainLab.ui.dialogs.training import (
    DeviceSettingDialog,
    OptimizerSettingDialog,
    TrainingSettingDialog,
)


class TestTrainingSetting:
    @pytest.fixture
    def window(self, qtbot):
        mock_controller = MagicMock()
        # Ensure get_training_option returns None so load_settings is skipped
        mock_controller.get_training_option.return_value = None

        # Use actual torch.optim.Adam
        with patch(
            "XBrainLab.ui.dialogs.training.training_setting_dialog.get_optimizer_classes"
        ) as mock_get_classes:
            mock_get_classes.return_value = {"Adam": torch.optim.Adam}

            window = TrainingSettingDialog(None, mock_controller)
            qtbot.addWidget(window)
            yield window

    def test_init(self, window):
        assert window.windowTitle() == "Training Setting"
        # Verify default values are set
        assert window.epoch_entry.text() == "10"
        assert window.bs_entry.text() == "32"
        assert window.lr_entry.text() == "0.001"
        assert window.checkpoint_entry.text() == "1"
        assert window.repeat_entry.text() == "1"
        assert window.output_dir == "./output"
        assert window.optim == torch.optim.Adam  # Real Adam class
        assert window.use_cpu is True

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
        window.output_dir = "/mock/output"

        # Select Evaluation
        window.evaluation_combo.setCurrentIndex(0)

        # Confirm
        with patch("PyQt6.QtWidgets.QDialog.accept") as mock_accept:
            window.accept()
            mock_accept.assert_called_once()

        # Verify result
        option = window.get_result()
        assert option.epoch == 10
        assert option.bs == 32
        assert option.lr == 0.001
        assert option.output_dir == "/mock/output"
        assert option.use_cpu is True

    def test_set_output_dir(self, window):
        with patch(
            "PyQt6.QtWidgets.QFileDialog.getExistingDirectory",
            return_value="/mock/test",
        ):
            window.set_output_dir()
            assert window.output_dir == "/mock/test"
            assert window.output_dir_label.text() == "/mock/test"

    def test_load_settings(self, qtbot):
        # Create mock controller
        mock_controller = MagicMock()
        mock_option = MagicMock()

        # Configure option
        mock_option.epoch = 50
        mock_option.bs = 64
        mock_option.lr = 0.005
        mock_option.checkpoint_epoch = 10
        mock_option.repeat_num = 3
        mock_option.output_dir = "/mock/loaded"
        mock_option.use_cpu = False
        mock_option.gpu_idx = 0
        mock_option.optim = torch.optim.Adam  # Use real Adam
        mock_option.optim_params = {}  # lr is separate parameter
        mock_option.evaluation_option.value = "Last Epoch"

        mock_controller.get_training_option.return_value = mock_option

        # Use real Adam class in get_optimizer_classes
        # Use real Adam class in get_optimizer_classes
        with (
            patch(
                "XBrainLab.ui.dialogs.training.training_setting_dialog.get_optimizer_classes",
                return_value={"Adam": torch.optim.Adam},
            ),
            patch("torch.cuda.get_device_name", return_value="Test GPU"),
        ):
            window = TrainingSettingDialog(None, mock_controller)
            qtbot.addWidget(window)

            # Verify fields are populated
            assert window.epoch_entry.text() == "50"
            assert window.bs_entry.text() == "64"
            assert window.lr_entry.text() == "0.005"
            assert window.checkpoint_entry.text() == "10"
            assert window.repeat_entry.text() == "3"
            assert window.output_dir == "/mock/loaded"
            assert window.output_dir_label.text() == "/mock/loaded"
            assert window.use_cpu is False
            assert window.gpu_idx == 0
            assert "Adam" in window.opt_label.text()
            # GPU check depends on parse_device_name logic
            assert "0 - Test GPU" in window.dev_label.text()

        assert window.evaluation_combo.currentText() == "Last Epoch"


class TestSetOptimizer:
    @pytest.fixture
    def window(self, qtbot):
        # Mock torch.optim members
        mock_adam = MagicMock()
        mock_adam.__name__ = "Adam"

        with patch(
            "XBrainLab.ui.dialogs.training.optimizer_setting_dialog.get_optimizer_classes",
            return_value={"Adam": mock_adam},
        ):
            window = OptimizerSettingDialog(None)
            qtbot.addWidget(window)
            yield window

    def test_init_and_populate(self, window):
        assert window.algo_combo.count() == 1
        assert window.algo_combo.currentText() == "Adam"

    def test_confirm(self, window):
        window.accept()
        result = window.get_result()
        assert result is not None
        optim_class, optim_params = result
        assert optim_class is not None
        assert isinstance(optim_params, dict)


class TestSetDevice:
    @pytest.fixture
    def window(self, qtbot):
        with (
            patch("torch.cuda.device_count", return_value=1),
            patch("torch.cuda.get_device_name", return_value="Test GPU"),
        ):
            window = DeviceSettingDialog(None)
            qtbot.addWidget(window)
            yield window

    def test_init(self, window):
        assert window.device_list.count() == 2  # CPU + 1 GPU
        assert window.device_list.item(0).text() == "CPU"
        assert "Test GPU" in window.device_list.item(1).text()

    def test_confirm_cpu(self, window):
        window.device_list.setCurrentRow(0)
        with patch("PyQt6.QtWidgets.QDialog.accept") as mock_accept:
            window.accept()
            mock_accept.assert_called_once()

        use_cpu, gpu_idx = window.get_result()
        assert use_cpu is True
        assert gpu_idx is None

    def test_confirm_gpu(self, window):
        window.device_list.setCurrentRow(1)
        with patch("PyQt6.QtWidgets.QDialog.accept") as mock_accept:
            window.accept()
            mock_accept.assert_called_once()

        use_cpu, gpu_idx = window.get_result()
        assert use_cpu is False
        assert gpu_idx == 0
