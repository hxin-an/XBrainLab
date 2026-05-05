import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication, QMainWindow

from XBrainLab.backend.training.record.key import RecordKey, TrainRecordKey
from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.panels.training.panel import MetricTab, TrainingPanel

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def mock_main_window(qtbot):
    window = QMainWindow()
    window.study = MagicMock()
    window.subscribe = MagicMock()
    qtbot.addWidget(window)
    return window


@pytest.fixture
def mock_controller(mock_main_window):
    """
    Create a mock controller and ensure Study returns it.
    """
    controller = MagicMock()
    controller.is_training.return_value = False
    controller.has_datasets.return_value = True
    controller.get_trainer.return_value = None
    controller.validate_ready.return_value = True

    # Configure study logic
    # When panel calls get_controller, return this mock
    mock_main_window.study.get_controller.return_value = controller
    return controller


def test_training_panel_init_controller(mock_main_window, mock_controller, qtbot):
    """Test initialization creates controller."""
    panel = TrainingPanel(
        parent=mock_main_window,
        controller=mock_controller,
        dataset_controller=mock_controller,
    )
    qtbot.addWidget(panel)
    assert panel.controller is not None
    assert panel.controller == mock_controller
    panel.close()


def test_training_panel_start_training_success(
    mock_main_window, mock_controller, qtbot
):
    """
    Test that 'Start Training' works correctly using controller.
    """
    # Setup
    panel = TrainingPanel(
        parent=mock_main_window,
        controller=mock_controller,
        dataset_controller=mock_controller,
    )
    qtbot.addWidget(panel)

    # Verify Start Button is enabled (Mock returns Ready)
    panel.sidebar.check_ready_to_train()
    assert panel.sidebar.btn_start.isEnabled()

    # Trigger Start Training
    # Simulate state change: Not training -> Start called -> Training
    # Providing plenty of True values to avoid StopIteration during
    # subsequent UI updates
    mock_controller.is_training.side_effect = [False] + [True] * 50

    with (
        patch("PyQt6.QtWidgets.QMessageBox.critical") as mock_critical,
        patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warning,
    ):
        panel.sidebar.start_training_ui_action()

        # Should call controller.start_training
        mock_controller.start_training.assert_called_once()

        # Verify no errors
        assert not mock_critical.called
        assert not mock_warning.called


def test_metric_tab_methods_exist():
    """
    Verify MetricTab now has the required methods.
    """
    tab = MetricTab("Test")
    assert callable(tab.update_plot)
    assert callable(tab.clear)


def test_training_panel_split_data_success(mock_main_window, mock_controller, qtbot):
    """
    Test that 'Dataset Splitting' delegates to dialog and controller.
    """
    panel = TrainingPanel(
        parent=mock_main_window,
        controller=mock_controller,
        dataset_controller=mock_controller,
    )
    qtbot.addWidget(panel)

    with (
        patch("XBrainLab.ui.panels.training.sidebar.DataSplittingDialog") as MockDialog,
        patch("XBrainLab.ui.panels.training.sidebar.QMessageBox.information"),
    ):
        # Setup Dialog Mock
        instance = MockDialog.return_value
        instance.exec.return_value = True
        mock_generator = MagicMock()
        instance.get_result.return_value = mock_generator

        panel.sidebar.split_data()

        # Verify Dialog checked with Controller
        MockDialog.assert_called_with(panel.sidebar, mock_controller)

        # Verify Controller applied splitting
        mock_controller.apply_data_splitting.assert_called_once_with(mock_generator)


def test_training_panel_stop_training(mock_main_window, mock_controller, qtbot):
    """
    Test that 'Stop Training' delegates to controller.
    """
    panel = TrainingPanel(
        parent=mock_main_window,
        controller=mock_controller,
        dataset_controller=mock_controller,
    )
    qtbot.addWidget(panel)

    # Simulate Training
    mock_controller.is_training.return_value = True

    panel.sidebar.stop_training()

    mock_controller.stop_training.assert_called_once()


def test_training_panel_check_ready(mock_main_window, mock_controller, qtbot):
    """Test check_ready_to_train logic."""
    panel = TrainingPanel(
        parent=mock_main_window,
        controller=mock_controller,
        dataset_controller=mock_controller,
    )
    qtbot.addWidget(panel)

    # 1. Not Ready
    mock_controller.validate_ready.return_value = False
    mock_controller.has_datasets.return_value = False
    mock_controller.has_model.return_value = True
    mock_controller.has_training_option.return_value = True

    panel.sidebar.check_ready_to_train()
    assert not panel.sidebar.btn_start.isEnabled()
    assert "Data Splitting" in panel.sidebar.btn_start.toolTip()

    # 2. Ready
    mock_controller.validate_ready.return_value = True
    panel.sidebar.check_ready_to_train()
    assert panel.sidebar.btn_start.isEnabled()


def test_training_panel_rechecks_readiness_on_preprocess_change(
    mock_main_window,
    mock_controller,
    qtbot,
):
    """Preprocess changes should refresh the start-ready state immediately."""
    preprocess_controller = Observable()
    panel = TrainingPanel(
        parent=mock_main_window,
        controller=mock_controller,
        dataset_controller=mock_controller,
        preprocess_controller=preprocess_controller,
    )
    qtbot.addWidget(panel)

    mock_controller.validate_ready.return_value = True
    panel.sidebar.check_ready_to_train()
    assert panel.sidebar.btn_start.isEnabled()

    mock_controller.validate_ready.return_value = False
    mock_controller.has_datasets.return_value = False
    mock_controller.has_model.return_value = True
    mock_controller.has_training_option.return_value = True

    preprocess_controller.notify("preprocess_changed")
    qtbot.wait(50)

    assert panel.sidebar.btn_start.isEnabled() is False
    assert "Data Splitting" in panel.sidebar.btn_start.toolTip()


def _make_history_entry(
    epoch_count=1,
    *,
    is_current_run=True,
    is_active=True,
    run_name="1",
    repeat=1,
    model_name="EEGNet",
):
    plan = MagicMock()
    plan.option.epoch = 5
    plan.get_training_repeat.return_value = repeat
    plan.model_holder.target_model.__name__ = model_name

    record = MagicMock()
    record.repeat = repeat
    record.is_finished.return_value = False
    record.epoch = epoch_count
    record.get_epoch.return_value = epoch_count
    record.train = {
        TrainRecordKey.LOSS: [0.5] * epoch_count,
        TrainRecordKey.ACC: [0.8] * epoch_count,
        TrainRecordKey.LR: [0.001] * epoch_count,
    }
    record.val = {
        RecordKey.LOSS: [0.6] * epoch_count,
        RecordKey.ACC: [0.75] * epoch_count,
    }

    return {
        "plan": plan,
        "record": record,
        "group_name": "Group 1",
        "run_name": run_name,
        "model_name": model_name,
        "is_active": is_active,
        "is_current_run": is_current_run,
    }


def test_training_panel_populates_history_immediately_on_training_started(
    mock_main_window,
    qtbot,
):
    """training_started should populate the active run without waiting 1s."""
    controller = Observable()
    controller.validate_ready = MagicMock(return_value=True)
    controller.has_datasets = MagicMock(return_value=True)
    controller.has_model = MagicMock(return_value=True)
    controller.has_training_option = MagicMock(return_value=True)
    controller.get_formatted_history = MagicMock(return_value=[_make_history_entry()])

    panel = TrainingPanel(
        parent=mock_main_window,
        controller=controller,
        dataset_controller=Observable(),
    )
    qtbot.addWidget(panel)

    assert panel.history_table.rowCount() == 0

    controller.notify("training_started")
    qtbot.wait(50)

    assert panel.history_table.rowCount() == 1
    assert panel.history_table.item(0, 3).text() == "Running"
    assert panel.current_plotting_record is not None


def test_training_panel_clears_stale_history_on_config_changed(
    mock_main_window,
    qtbot,
):
    """config_changed should clear stale history/plots when trainer is gone."""
    controller = Observable()
    controller.validate_ready = MagicMock(return_value=True)
    controller.has_datasets = MagicMock(return_value=True)
    controller.has_model = MagicMock(return_value=True)
    controller.has_training_option = MagicMock(return_value=True)
    controller.get_formatted_history = MagicMock(return_value=[_make_history_entry()])

    panel = TrainingPanel(
        parent=mock_main_window,
        controller=controller,
        dataset_controller=Observable(),
    )
    qtbot.addWidget(panel)

    panel.update_loop()
    assert panel.history_table.rowCount() == 1
    assert panel.current_plotting_record is not None

    controller.get_formatted_history.return_value = []
    controller.validate_ready.return_value = False
    controller.has_datasets.return_value = False
    controller.notify("config_changed")
    qtbot.wait(50)

    assert panel.history_table.rowCount() == 0
    assert panel.current_plotting_record is None
    assert panel._last_epoch_count == -1


def test_training_panel_switches_to_active_run_on_training_started(
    mock_main_window,
    qtbot,
):
    """training_started should focus the new active run, not an older selection."""
    controller = Observable()
    controller.validate_ready = MagicMock(return_value=True)
    controller.has_datasets = MagicMock(return_value=True)
    controller.has_model = MagicMock(return_value=True)
    controller.has_training_option = MagicMock(return_value=True)

    old_entry = _make_history_entry(
        epoch_count=3,
        is_current_run=False,
        is_active=False,
        run_name="1",
        repeat=1,
    )
    active_entry = _make_history_entry(
        epoch_count=1,
        is_current_run=True,
        is_active=True,
        run_name="2",
        repeat=2,
    )
    controller.get_formatted_history = MagicMock(return_value=[old_entry])

    panel = TrainingPanel(
        parent=mock_main_window,
        controller=controller,
        dataset_controller=Observable(),
    )
    qtbot.addWidget(panel)

    panel.update_loop()
    assert panel.current_plotting_record is old_entry["record"]

    controller.get_formatted_history.return_value = [old_entry, active_entry]
    controller.notify("training_started")
    qtbot.wait(50)

    assert panel.history_table.rowCount() == 2
    assert panel.current_plotting_record is active_entry["record"]
    assert panel.tab_acc.epochs == [1]


def test_training_panel_replaces_stale_selected_record_when_history_changes(
    mock_main_window,
    qtbot,
):
    """Regenerated history should drop stale selections and plot the new record."""
    controller = Observable()
    controller.validate_ready = MagicMock(return_value=True)
    controller.has_datasets = MagicMock(return_value=True)
    controller.has_model = MagicMock(return_value=True)
    controller.has_training_option = MagicMock(return_value=True)

    old_entry = _make_history_entry(
        epoch_count=3,
        is_current_run=False,
        is_active=False,
        run_name="1",
        repeat=1,
    )
    new_entry = _make_history_entry(
        epoch_count=2,
        is_current_run=True,
        is_active=True,
        run_name="1",
        repeat=1,
        model_name="SCCNet",
    )
    controller.get_formatted_history = MagicMock(return_value=[old_entry])

    panel = TrainingPanel(
        parent=mock_main_window,
        controller=controller,
        dataset_controller=Observable(),
    )
    qtbot.addWidget(panel)

    panel.update_loop()
    assert panel.current_plotting_record is old_entry["record"]
    assert panel.tab_acc.epochs == [1, 2, 3]

    controller.get_formatted_history.return_value = [new_entry]
    controller.notify("config_changed")
    qtbot.wait(50)

    assert panel.history_table.rowCount() == 1
    assert panel.current_plotting_record is new_entry["record"]
    assert panel.tab_acc.epochs == [1, 2]


def test_training_panel_auto_follows_new_active_run_on_training_updated(
    mock_main_window,
    qtbot,
):
    """Auto-managed selection should follow repeat transitions."""
    controller = Observable()
    controller.validate_ready = MagicMock(return_value=True)
    controller.has_datasets = MagicMock(return_value=True)
    controller.has_model = MagicMock(return_value=True)
    controller.has_training_option = MagicMock(return_value=True)

    first_active = _make_history_entry(
        epoch_count=3,
        is_current_run=True,
        is_active=True,
        run_name="1",
        repeat=1,
    )
    second_active = _make_history_entry(
        epoch_count=1,
        is_current_run=True,
        is_active=True,
        run_name="2",
        repeat=2,
    )
    controller.get_formatted_history = MagicMock(return_value=[first_active])

    panel = TrainingPanel(
        parent=mock_main_window,
        controller=controller,
        dataset_controller=Observable(),
    )
    qtbot.addWidget(panel)

    panel.update_loop()
    assert panel.current_plotting_record is first_active["record"]
    assert panel.tab_acc.epochs == [1, 2, 3]

    first_active["is_current_run"] = False
    first_active["is_active"] = False
    controller.get_formatted_history.return_value = [first_active, second_active]
    controller.notify("training_updated")
    qtbot.wait(50)

    assert panel.current_plotting_record is second_active["record"]
    assert panel.tab_acc.epochs == [1]


def test_training_panel_keeps_manual_selection_on_training_updated(
    mock_main_window,
    qtbot,
):
    """A user-selected historical run should stay pinned across updates."""
    controller = Observable()
    controller.validate_ready = MagicMock(return_value=True)
    controller.has_datasets = MagicMock(return_value=True)
    controller.has_model = MagicMock(return_value=True)
    controller.has_training_option = MagicMock(return_value=True)

    old_run = _make_history_entry(
        epoch_count=3,
        is_current_run=False,
        is_active=False,
        run_name="1",
        repeat=1,
    )
    active_run = _make_history_entry(
        epoch_count=1,
        is_current_run=True,
        is_active=True,
        run_name="2",
        repeat=2,
    )
    controller.get_formatted_history = MagicMock(return_value=[old_run, active_run])

    panel = TrainingPanel(
        parent=mock_main_window,
        controller=controller,
        dataset_controller=Observable(),
    )
    qtbot.addWidget(panel)

    panel.update_loop()
    assert panel.current_plotting_record is active_run["record"]

    panel.on_history_selection_changed(old_run["record"])
    assert panel.current_plotting_record is old_run["record"]

    active_run["record"].train[TrainRecordKey.ACC] = [0.8, 0.81]
    active_run["record"].train[TrainRecordKey.LOSS] = [0.5, 0.49]
    active_run["record"].train[TrainRecordKey.LR] = [0.001, 0.001]
    active_run["record"].val[RecordKey.ACC] = [0.75, 0.76]
    active_run["record"].val[RecordKey.LOSS] = [0.6, 0.59]
    controller.notify("training_updated")
    qtbot.wait(50)

    assert panel.current_plotting_record is old_run["record"]
    assert panel._selection_pinned_by_user is True


def test_training_panel_refreshes_progress_and_plot_on_training_updated(
    mock_main_window,
    qtbot,
):
    """training_updated should refresh live progress text and plot history."""
    controller = Observable()
    controller.validate_ready = MagicMock(return_value=True)
    controller.has_datasets = MagicMock(return_value=True)
    controller.has_model = MagicMock(return_value=True)
    controller.has_training_option = MagicMock(return_value=True)

    active_entry = _make_history_entry(
        epoch_count=1,
        is_current_run=True,
        is_active=True,
        run_name="1",
        repeat=1,
    )
    controller.get_formatted_history = MagicMock(return_value=[active_entry])

    panel = TrainingPanel(
        parent=mock_main_window,
        controller=controller,
        dataset_controller=Observable(),
    )
    qtbot.addWidget(panel)

    panel.update_loop()
    assert panel.history_table.item(0, 4).text() == "1/5"
    assert panel.tab_acc.epochs == [1]

    active_entry["record"].epoch = 2
    active_entry["record"].get_epoch.return_value = 2
    active_entry["record"].train[TrainRecordKey.ACC] = [0.8, 0.81]
    active_entry["record"].train[TrainRecordKey.LOSS] = [0.5, 0.49]
    active_entry["record"].train[TrainRecordKey.LR] = [0.001, 0.001]
    active_entry["record"].val[RecordKey.ACC] = [0.75, 0.76]
    active_entry["record"].val[RecordKey.LOSS] = [0.6, 0.59]

    controller.notify("training_updated")
    qtbot.wait(50)

    assert panel.history_table.item(0, 4).text() == "2/5"
    assert panel.tab_acc.epochs == [1, 2]
    assert panel.tab_acc.train_vals[-1] == 0.81


def test_training_panel_clears_log_on_history_cleared(
    mock_main_window,
    qtbot,
):
    """history_cleared should not leave stale event logs visible."""
    controller = Observable()
    controller.validate_ready = MagicMock(return_value=True)
    controller.has_datasets = MagicMock(return_value=True)
    controller.has_model = MagicMock(return_value=True)
    controller.has_training_option = MagicMock(return_value=True)
    controller.get_formatted_history = MagicMock(return_value=[])

    panel = TrainingPanel(
        parent=mock_main_window,
        controller=controller,
        dataset_controller=Observable(),
    )
    qtbot.addWidget(panel)

    with patch("PyQt6.QtWidgets.QMessageBox.information"):
        panel._on_training_started()
        panel._on_training_stopped()

    assert "Training started" in panel.log_text.toPlainText()

    controller.notify("history_cleared")
    qtbot.wait(50)

    assert panel.log_text.toPlainText() == ""


def test_training_panel_high_level_events_refresh_shared_status(
    mock_main_window,
    qtbot,
):
    """Named training callbacks should keep shared UI status current."""
    controller: Any = Observable()
    controller.validate_ready = MagicMock(return_value=True)
    controller.has_datasets = MagicMock(return_value=True)
    controller.has_model = MagicMock(return_value=True)
    controller.has_training_option = MagicMock(return_value=True)
    controller.get_formatted_history = MagicMock(return_value=[])

    panel = TrainingPanel(
        parent=mock_main_window,
        controller=controller,
        dataset_controller=Observable(),
    )
    qtbot.addWidget(panel)

    with (
        patch("PyQt6.QtWidgets.QMessageBox.information"),
        patch(
            "XBrainLab.ui.panels.training.panel.refresh_shared_status",
        ) as refresh,
    ):
        controller.notify("training_started")
        qtbot.wait(50)
        controller.notify("config_changed")
        qtbot.wait(50)
        controller.notify("training_stopped")
        qtbot.wait(50)
        controller.notify("history_cleared")
        qtbot.wait(50)

    assert refresh.call_count == 4
    refresh.assert_any_call(panel)


def test_training_panel_clears_log_on_config_changed(
    mock_main_window,
    qtbot,
):
    """config_changed should clear stale logs even when new history replaces old."""
    controller = Observable()
    controller.validate_ready = MagicMock(return_value=True)
    controller.has_datasets = MagicMock(return_value=True)
    controller.has_model = MagicMock(return_value=True)
    controller.has_training_option = MagicMock(return_value=True)

    old_entry = _make_history_entry(
        epoch_count=2,
        is_current_run=True,
        is_active=True,
        run_name="1",
        repeat=1,
    )
    new_entry = _make_history_entry(
        epoch_count=1,
        is_current_run=True,
        is_active=True,
        run_name="1",
        repeat=1,
        model_name="SCCNet",
    )
    controller.get_formatted_history = MagicMock(return_value=[old_entry])

    panel = TrainingPanel(
        parent=mock_main_window,
        controller=controller,
        dataset_controller=Observable(),
    )
    qtbot.addWidget(panel)

    panel.update_loop()

    with patch("PyQt6.QtWidgets.QMessageBox.information"):
        panel._on_training_started()
        panel._on_training_stopped()

    controller.get_formatted_history.return_value = [new_entry]
    controller.notify("config_changed")
    qtbot.wait(50)

    assert panel.log_text.toPlainText() == ""
    assert panel.current_plotting_record is new_entry["record"]
    assert panel.tab_acc.epochs == [1]
