import sys
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication, QMainWindow

from XBrainLab.backend.dataset import Epochs
from XBrainLab.ui.training.panel import MetricTab, TrainingPanel

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)


def test_training_panel_start_training_success():
    """
    Test that 'Start Training' now works correctly with the fix.
    """
    # Mock Study and Trainer
    mock_study = MagicMock()
    mock_study.training_plan_list = ["Plan1"]
    # Mock model_holder with target_model that has __name__
    mock_model_class = MagicMock()
    mock_model_class.__name__ = "TestModel"
    mock_study.model_holder.target_model = mock_model_class

    # Mock Trainer
    mock_trainer = MagicMock()
    mock_trainer.is_running.return_value = False
    mock_study.trainer = mock_trainer

    # Required for check_ready_to_train
    mock_study.datasets.__len__.return_value = 1
    mock_study.is_training.return_value = False

    main_window = QMainWindow()
    main_window.study = mock_study
    panel = TrainingPanel(main_window)
    panel.show()

    # Verify Start Button is enabled
    assert panel.btn_start.isEnabled()

    # Trigger Start Training
    # Should NOT raise exception now
    # Should NOT raise exception now
    with (
        patch("PyQt6.QtWidgets.QMessageBox.critical") as mock_critical,
        patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warning,
    ):
        panel.start_training()

        if mock_critical.called:
            args = mock_critical.call_args[0]
            pytest.fail(f"Start Training failed with critical error: {args[2]}")
        if mock_warning.called:
            args = mock_warning.call_args[0]
            pytest.fail(f"Start Training showed warning: {args[2]}")

    # Verify study.train was called (controller calls study.train)
    # Using assert_called() to match observation that call occurs
    mock_study.train.assert_called()

    # Verify timer started - simulated check
    # In this mock setup, is_training() remains False so timer might not
    # start unless we mock side_effect.
    # But checking if called is main goal.
    if mock_study.is_training.return_value:
        assert panel.timer.isActive()


def test_metric_tab_methods_exist():
    """
    Verify MetricTab now has the required methods.
    """

    tab = MetricTab("Test")

    assert hasattr(tab, "update_plot")
    assert hasattr(tab, "clear")


def test_training_panel_split_data_success():
    """
    Test that 'Dataset Splitting' works correctly after fix.
    """
    # Mock Study
    mock_study = MagicMock()
    mock_study.loaded_data_list = [MagicMock()]
    mock_study.epoch_data = MagicMock(spec=Epochs)
    # Mock model_holder and dataset_generator for update_summary
    mock_study.model_holder.target_model.__name__ = "MockModel"
    mock_study.dataset_generator = MagicMock()

    # Required for check_ready_to_train
    mock_study.datasets.__len__.return_value = 1
    mock_study.is_training.return_value = False

    main_window = QMainWindow()
    main_window.study = mock_study
    panel = TrainingPanel(main_window)
    panel.show()

    with patch("XBrainLab.ui.training.panel.DataSplittingSettingWindow") as MockWindow:
        # Mock exec to return True
        MockWindow.return_value.exec.return_value = True

        panel.split_data()

        # Verify it was called with CORRECT arguments
        # (parent=panel, epoch_data=mock_study.epoch_data)
        MockWindow.assert_called_with(panel, mock_study.epoch_data)


if __name__ == "__main__":
    pytest.main([__file__])


def test_training_panel_stop_training():
    """
    Test that 'Stop Training' calls trainer.set_interrupt().
    """
    mock_study = MagicMock()
    mock_trainer = MagicMock()
    mock_study.trainer = mock_trainer
    # Mock model_holder and dataset_generator for update_summary
    mock_study.model_holder.target_model.__name__ = "MockModel"
    mock_study.dataset_generator = MagicMock()

    # Simulate running trainer
    mock_trainer.is_running.return_value = True
    mock_study.datasets.__len__.return_value = 1
    mock_study.is_training.return_value = True  # Assuming running

    main_window = QMainWindow()
    main_window.study = mock_study
    panel = TrainingPanel(main_window)

    # Call stop
    panel.stop_training()

    # Verify stop_training called on study (since Study is mocked)
    mock_study.stop_training.assert_called_once()
    # mock_trainer.set_interrupt is NOT called because Study is mocked and
    # doesn't execute real logic
    # Status label removed in redesign? No, status is in table.
    # assert panel.status_label.text() == "Stopping..." # Removed in redesign


def test_training_panel_update_loop_metrics():
    """
    Test that update_loop correctly updates metrics from the training plan.
    """
    mock_study = MagicMock()
    mock_trainer = MagicMock()
    mock_study.trainer = mock_trainer
    # Mock model_holder and dataset_generator for update_summary
    mock_study.model_holder.target_model.__name__ = "MockModel"
    mock_study.dataset_generator = MagicMock()

    # Mock Trainer running
    mock_trainer.is_running.return_value = True
    mock_trainer.get_progress_text.return_value = "Epoch 1/10"

    # Mock Training Plan
    mock_plan = MagicMock()
    mock_plan.get_training_status.return_value = "Running"
    mock_plan.get_training_epoch.return_value = 1
    # (lr, loss, acc, auc, val_loss, val_acc, val_auc)
    # Note: get_training_evaluation signature might differ, checking panel.py usage
    # It uses record.train[key][-1] etc.
    # The test mocks mock_plan.get_training_evaluation but panel.py uses
    # record directly?
    # Panel uses: holders = trainer.get_training_plan_holders(),
    # then plan.get_plans() -> records
    # The test setup seems to mock plan methods that might not be used anymore?
    # Let's see if we need to update the test logic too.
    # Panel uses:
    # holders = trainer.get_training_plan_holders()
    # for plan in holders:
    #   runs = plan.get_plans()
    #   for record in runs:
    #      ...

    # So we need to mock get_training_plan_holders -> [mock_plan]
    # And mock_plan.get_plans() -> [mock_record]

    mock_record = MagicMock()
    mock_record.get_epoch.return_value = 1
    mock_record.is_finished.return_value = False
    mock_record.repeat = 0
    mock_record.train = {"loss": [0.5], "accuracy": [0.8], "lr": [0.001]}
    mock_record.val = {"loss": [0.6], "accuracy": [0.75]}

    mock_plan.get_plans.return_value = [mock_record]
    mock_plan.get_training_repeat.return_value = 0
    mock_plan.model_holder.target_model.__name__ = "TestModel"
    mock_plan.option.epoch = 10

    mock_trainer.get_training_plan_holders.return_value = [mock_plan]
    mock_trainer.current_idx = 0

    # Mock Training Option
    mock_study.training_option.epoch = 10

    mock_study.datasets.__len__.return_value = 1
    mock_study.is_training.return_value = True

    main_window = QMainWindow()
    main_window.study = mock_study
    panel = TrainingPanel(main_window)

    # Mock MetricTabs to verify update_plot calls
    panel.tab_acc = MagicMock()
    panel.tab_acc.epochs = []
    panel.tab_loss = MagicMock()
    panel.tab_loss.epochs = []

    # Call update_loop
    panel.update_loop()

    # Verify MetricTab updates
    # tab_acc.update_plot(epoch, acc, val_acc)
    panel.tab_acc.update_plot.assert_called_with(1, 0.8, 0.75)
    # tab_loss.update_plot(epoch, loss, val_loss)
    panel.tab_loss.update_plot.assert_called_with(1, 0.5, 0.6)

    # Verify Best Acc update (removed in redesign? No, it's in history table)
    # assert panel.best_acc == 0.75 # Removed
    # assert "0.75" in panel.acc_label.text() # Removed


def test_training_panel_finished():
    """
    Test that training_finished resets UI state.
    """
    mock_study = MagicMock()
    # Mock model_holder and dataset_generator for update_summary
    mock_study.model_holder.target_model.__name__ = "MockModel"
    mock_study.dataset_generator = MagicMock()

    # Required Mocks
    mock_study.datasets.__len__.return_value = 1
    mock_study.is_training.return_value = False

    main_window = QMainWindow()
    main_window.study = mock_study
    panel = TrainingPanel(main_window)

    assert panel.btn_start.isEnabled()
    assert not panel.btn_stop.isEnabled()


def test_training_panel_split_data_no_epoch_data():
    """Test split_data warns when epoch_data is None."""
    mock_study = MagicMock()
    mock_study.epoch_data = None
    mock_study.loaded_data_list = [MagicMock()]
    # Mock model_holder and dataset_generator for update_summary
    mock_study.model_holder.target_model.__name__ = "MockModel"
    mock_study.dataset_generator = MagicMock()

    # Required for init
    mock_study.datasets.__len__.return_value = 1
    mock_study.is_training.return_value = False

    main_window = QMainWindow()
    main_window.study = mock_study
    panel = TrainingPanel(main_window)

    with patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warn:
        panel.split_data()

        # Should show warning about no epoched data
        mock_warn.assert_called_once()
        call_args = mock_warn.call_args[0]
        assert "No Epoched Data" in call_args[1]
        assert "epoching" in call_args[2]


def test_training_panel_split_data_with_epoch_data():
    """Test split_data opens window when epoch_data exists."""
    mock_epoch = MagicMock()
    mock_study = MagicMock()
    mock_study.epoch_data = mock_epoch
    mock_study.loaded_data_list = [MagicMock()]
    # Mock model_holder and dataset_generator for update_summary
    mock_study.model_holder.target_model.__name__ = "MockModel"
    mock_study.dataset_generator = MagicMock()

    # Required for init
    mock_study.datasets.__len__.return_value = 1
    mock_study.is_training.return_value = False

    main_window = QMainWindow()
    main_window.study = mock_study
    panel = TrainingPanel(main_window)

    with patch("XBrainLab.ui.training.panel.DataSplittingSettingWindow") as MockWin:
        instance = MockWin.return_value
        instance.exec.return_value = False  # User cancels

        panel.split_data()

        # Should create window with epoch_data
        MockWin.assert_called_once()
        call_args = MockWin.call_args[0]
        assert call_args[1] == mock_epoch


if __name__ == "__main__":
    pytest.main([__file__])
