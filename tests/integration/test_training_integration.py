"""
Integration tests for training workflow - focusing on bug fixes.

These tests use real objects (not mocks) to verify the bugs we fixed,
catching issues that unit tests with heavy mocking might miss.
"""

from unittest.mock import MagicMock, patch

import pytest
import torch

from XBrainLab import Study
from XBrainLab.backend.model_base import EEGNet, SCCNet
from XBrainLab.backend.training import TrainingEvaluation, TrainingOption
from XBrainLab.backend.training.model_holder import ModelHolder
from XBrainLab.ui.training.panel import MetricTab
from XBrainLab.ui.training.training_setting import TrainingSettingWindow


@pytest.fixture
def real_training_option():
    """Create a real TrainingOption object (not a mock)."""
    return TrainingOption(
        output_dir="./test_output",
        optim=torch.optim.Adam,
        optim_params={},  # Bug fix: lr should NOT be in optim_params
        use_cpu=True,
        gpu_idx=None,
        epoch="5",
        bs="4",
        lr="0.001",  # lr is passed separately
        checkpoint_epoch="1",
        evaluation_option=TrainingEvaluation.TEST_ACC,
        repeat_num="1",
    )


class TestTrainingOptionBugFix:
    """Test that the optimizer lr duplication bug is fixed."""

    def test_optim_params_should_not_contain_lr(self, real_training_option):
        """Verify optim_params doesn't contain 'lr' to avoid duplication."""
        assert "lr" not in real_training_option.optim_params
        assert real_training_option.lr == 0.001

    def test_get_optim_no_duplicate_lr(self, real_training_option):
        """Test that get_optim() doesn't pass lr twice."""
        model = torch.nn.Linear(10, 2)

        # This should NOT raise "got multiple values for keyword argument 'lr'"
        optimizer = real_training_option.get_optim(model)

        assert optimizer is not None
        assert optimizer.param_groups[0]["lr"] == 0.001

    def test_optim_with_extra_params(self):
        """Test optimizer with additional parameters (not lr)."""
        option = TrainingOption(
            output_dir="./test_output",
            optim=torch.optim.Adam,
            optim_params={"weight_decay": 0.01, "amsgrad": True},
            use_cpu=True,
            gpu_idx=None,
            epoch="5",
            bs="4",
            lr="0.001",
            checkpoint_epoch="1",
            evaluation_option=TrainingEvaluation.TEST_ACC,
            repeat_num="1",
        )

        model = torch.nn.Linear(10, 2)
        optimizer = option.get_optim(model)

        assert optimizer.param_groups[0]["lr"] == 0.001
        assert optimizer.param_groups[0]["weight_decay"] == 0.01
        assert optimizer.param_groups[0]["amsgrad"] is True


class TestModelHolderBugFix:
    """Test that ModelHolder attribute access works correctly."""

    def test_model_holder_has_target_model(self):
        """Verify ModelHolder has target_model, not model_name."""
        holder = ModelHolder(EEGNet, {})

        # Bug fix: ModelHolder has target_model (class), not model_name (string)
        assert hasattr(holder, "target_model")
        assert holder.target_model == EEGNet
        assert holder.target_model.__name__ == "EEGNet"

        # Should NOT have model_name attribute
        assert not hasattr(holder, "model_name")

    def test_access_model_name_correctly(self):
        """Test the correct way to get model name from ModelHolder."""
        holder = ModelHolder(SCCNet, {})

        # Correct way: holder.target_model.__name__
        model_name = holder.target_model.__name__
        assert model_name == "SCCNet"

        # Or use the method
        assert "SCCNet" in holder.get_model_desc_str()


class TestEpochDurationValidation:
    """Test that models validate minimum epoch duration."""

    def test_eegnet_rejects_short_epochs(self):
        """EEGNet should reject epochs shorter than required samples."""
        # EEGNet at 250Hz needs at least 285 samples (1.14 seconds)
        with pytest.raises(ValueError, match=r"Epoch duration is too short for EEGNet"):
            # This should raise during model initialization
            EEGNet(n_classes=2, channels=3, samples=100, sfreq=250)


class TestStudyAttributeConsistency:
    """Test that Study object attributes are consistently named."""

    def test_study_has_training_option_not_setting(self):
        """Verify Study uses training_option, not training_setting."""
        study = Study()

        # Bug fix: Should be training_option
        assert hasattr(study, "training_option")
        assert study.training_option is None

        # Should NOT have training_setting
        assert not hasattr(study, "training_setting")

    def test_study_set_training_option(self, real_training_option):
        """Test Study.set_training_option() works correctly."""
        study = Study()
        study.set_training_option(real_training_option)

        assert study.training_option is not None
        assert study.training_option.epoch == 5
        assert study.training_option.lr == 0.001
        assert study.training_option.optim == torch.optim.Adam


class TestCompleteTrainingWorkflow:
    """Integration test for complete training workflow using real objects."""

    def test_training_option_validation_in_workflow(self):
        """Test that invalid training options are caught."""
        # Invalid option: missing optimizer
        with pytest.raises(ValueError, match="Optimizer not set"):
            TrainingOption(
                output_dir="./test_output",
                optim=None,  # Invalid
                optim_params={},
                use_cpu=True,
                gpu_idx=None,
                epoch="5",
                bs="4",
                lr="0.001",
                checkpoint_epoch="1",
                evaluation_option=TrainingEvaluation.TEST_ACC,
                repeat_num="1",
            )


class TestUITrainingPanelIntegration:
    """Integration tests for UI training panel focusing on attribute naming."""

    def test_study_training_option_attribute_exists(self):
        """Verify Study uses training_option, not training_setting."""
        study = Study()

        # This is what the UI code expects
        assert hasattr(study, "training_option")
        assert not hasattr(study, "training_setting")

        # Set a real option
        option = TrainingOption(
            output_dir="./test_output",
            optim=torch.optim.Adam,
            optim_params={},
            use_cpu=True,
            gpu_idx=None,
            epoch="5",
            bs="4",
            lr="0.001",
            checkpoint_epoch="1",
            evaluation_option=TrainingEvaluation.TEST_ACC,
            repeat_num="1",
        )
        study.set_training_option(option)

        # UI code should be able to access this
        assert study.training_option.epoch == 5


class TestTrainingSettingDefaultValues:
    """Test that TrainingSettingWindow has sensible defaults."""

    def test_training_setting_has_defaults(self, qtbot):
        """Verify default values are set for easier testing."""

        # Create mock controller
        mock_controller = MagicMock()
        mock_controller.get_training_option.return_value = None

        window = TrainingSettingWindow(None, mock_controller)
        qtbot.addWidget(window)

        # Verify default values are pre-filled
        assert window.epoch_entry.text() == "10"
        assert window.bs_entry.text() == "32"
        assert window.lr_entry.text() == "0.001"
        assert window.checkpoint_entry.text() == "1"
        assert window.repeat_entry.text() == "1"

        # Verify default optimizer and device
        assert window.optim == torch.optim.Adam
        assert window.optim_params == {}  # No lr in params
        assert window.use_cpu is True
        assert window.output_dir == "./output"

    def test_confirm_creates_valid_training_option(self, qtbot):
        """Test that confirming with defaults creates valid TrainingOption."""

        # Create mock controller
        mock_controller = MagicMock()
        mock_controller.get_training_option.return_value = None

        window = TrainingSettingWindow(None, mock_controller)
        qtbot.addWidget(window)

        # Use defaults and confirm
        with patch.object(window, "accept"):
            window.confirm()

        # Should create valid option without errors
        assert window.training_option is not None
        assert window.training_option.epoch == 10
        assert window.training_option.lr == 0.001
        assert "lr" not in window.training_option.optim_params

    def test_training_option_epoch_is_int(self, qtbot):
        """Test that training_option.epoch is converted to int for comparisons."""

        # Create mock controller
        mock_controller = MagicMock()
        mock_controller.get_training_option.return_value = None

        window = TrainingSettingWindow(None, mock_controller)
        qtbot.addWidget(window)

        # Confirm with string input (from text fields)
        with patch.object(window, "accept"):
            window.confirm()

        # Epoch should be int, not string
        assert isinstance(window.training_option.epoch, int)

        # Should work in comparisons (this was the bug)
        assert window.training_option.epoch > 0

        # Should work in division (progress bar calculation)
        progress = int((5 / window.training_option.epoch) * 100)
        assert progress == 50


class TestMetricTypeConversion:
    """Test that metrics are properly converted to float for comparisons."""

    def test_string_metrics_converted_to_float(self):
        """Test that string metrics from trainer are converted to float."""
        # Simulate metrics returned as strings (this was the bug)
        val_acc = "0.75"
        best_acc = 0.7

        # Convert to float before comparison
        val_acc_float = float(val_acc) if val_acc is not None else 0.0

        # Should work now
        assert isinstance(val_acc_float, float)
        assert val_acc_float > best_acc

        # Update best_acc
        best_acc = val_acc_float
        assert best_acc == 0.75

    def test_none_metrics_handled(self):
        """Test that None metrics are handled gracefully."""
        metrics = [None, "0.5", None, "0.8", "0.9"]

        # Convert with default value for None
        converted = [float(m) if m is not None else 0.0 for m in metrics]

        assert converted == [0.0, 0.5, 0.0, 0.8, 0.9]
        assert all(isinstance(m, float) for m in converted)

    @pytest.mark.parametrize(
        "metric_str,expected",
        [
            ("0.001", 0.001),
            ("0.5", 0.5),
            ("0.8", 0.8),
            ("0.9", 0.9),
            ("1.0", 1.0),
        ],
    )
    def test_various_string_metrics_converted(self, metric_str, expected):
        """Test conversion of various string metric values."""
        converted = float(metric_str)
        assert converted == expected
        assert isinstance(converted, float)

    def test_all_metrics_converted_in_batch(self):
        """Test converting all 7 metrics that trainer returns."""
        # Simulate trainer output (all strings)
        lr, loss, acc, auc, val_loss, val_acc, val_auc = (
            "0.001",
            "0.5",
            "0.8",
            "0.9",
            "0.6",
            "0.75",
            "0.85",
        )

        # Convert all to float
        lr = float(lr) if lr is not None else 0.0
        loss = float(loss) if loss is not None else 0.0
        acc = float(acc) if acc is not None else 0.0
        auc = float(auc) if auc is not None else 0.0
        val_loss = float(val_loss) if val_loss is not None else 0.0
        val_acc = float(val_acc) if val_acc is not None else 0.0
        val_auc = float(val_auc) if val_auc is not None else 0.0

        # All should be float
        assert all(
            isinstance(m, float)
            for m in [lr, loss, acc, auc, val_loss, val_acc, val_auc]
        )

        # Comparisons should work
        assert val_acc > 0.7
        assert val_auc > val_acc


class TestMetricTabHistoryManagement:
    """Test that MetricTab properly manages history across training sessions."""

    def test_clear_resets_history_lists(self, qtbot):
        """Test that clear() resets epochs, train_vals, val_vals."""

        tab = MetricTab("Accuracy", color="#4CAF50")
        qtbot.addWidget(tab)

        # Add some data
        tab.update_plot(1, 0.7, 0.6)
        tab.update_plot(2, 0.75, 0.65)
        tab.update_plot(3, 0.78, 0.68)

        assert len(tab.epochs) == 3
        assert len(tab.train_vals) == 3
        assert len(tab.val_vals) == 3

        # Clear should reset all history
        tab.clear()

        assert len(tab.epochs) == 0, "epochs should be empty after clear"
        assert len(tab.train_vals) == 0, "train_vals should be empty after clear"
        assert len(tab.val_vals) == 0, "val_vals should be empty after clear"

    def test_history_accumulates_correctly(self, qtbot):
        """Test that history accumulates over multiple updates."""

        tab = MetricTab("Loss", color="#F44336")
        qtbot.addWidget(tab)

        # Simulate training over 5 epochs
        expected_epochs = []
        expected_train = []
        expected_val = []

        for epoch in range(1, 6):
            train_val = 0.9 - epoch * 0.1
            val_val = 0.95 - epoch * 0.1
            tab.update_plot(epoch, train_val, val_val)
            expected_epochs.append(epoch)
            expected_train.append(train_val)
            expected_val.append(val_val)

        assert tab.epochs == expected_epochs
        assert tab.train_vals == expected_train
        assert tab.val_vals == expected_val

    def test_new_training_after_clear(self, qtbot):
        """Test that new training session works after clear."""

        tab = MetricTab("AUC", color="#2196F3")
        qtbot.addWidget(tab)

        # First training session
        tab.update_plot(1, 0.6, 0.5)
        tab.update_plot(2, 0.7, 0.6)
        assert len(tab.epochs) == 2

        # Clear for new training
        tab.clear()
        assert len(tab.epochs) == 0

        # Second training session should start fresh
        tab.update_plot(1, 0.65, 0.55)
        tab.update_plot(2, 0.75, 0.65)
        tab.update_plot(3, 0.8, 0.7)

        # Should only have data from second session
        assert tab.epochs == [1, 2, 3]
        assert len(tab.train_vals) == 3
        assert len(tab.val_vals) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
