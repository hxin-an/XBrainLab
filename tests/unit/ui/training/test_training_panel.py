import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from XBrainLab.backend.application.results import (
    ChangedState,
    CommandResult,
    ErrorType,
)
from XBrainLab.backend.controller.training_controller import TrainingLifecycleEvent
from XBrainLab.backend.study import Study
from XBrainLab.backend.training.record.key import RecordKey, TrainRecordKey
from XBrainLab.backend.training_state_contract import (
    TrainingOutcomeState,
    TrainingRunIdentity,
    TrainingStateToken,
    TrainingTerminalOutcome,
)
from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.panels.training.panel import MetricTab, TrainingPanel

# Ensure QApplication exists
app = QApplication.instance() or QApplication(sys.argv)


def test_undefined_metric_is_rendered_as_not_available() -> None:
    assert TrainingPanel._format_metric(None) == "N/A"


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
    Test that 'Start Training' blocks instead of mutating the controller compatibility.
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

        mock_controller.start_training.assert_not_called()
        assert not mock_critical.called
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Start Training Blocked"


def test_metric_tab_methods_exist():
    """
    Verify MetricTab now has the required methods.
    """
    tab = MetricTab("Test")
    assert callable(tab.update_plot)
    assert callable(tab.clear)


def test_training_panel_update_panel_refreshes_training_history(
    mock_main_window,
    mock_controller,
    qtbot,
):
    panel = TrainingPanel(
        parent=mock_main_window,
        controller=mock_controller,
        dataset_controller=mock_controller,
    )
    qtbot.addWidget(panel)
    panel.update_loop = MagicMock()

    panel.update_panel()

    panel.update_loop.assert_called_once_with()


def test_training_panel_gives_remaining_height_to_plots_for_small_history(
    mock_main_window,
    mock_controller,
    qtbot,
):
    panel = TrainingPanel(
        parent=mock_main_window,
        controller=mock_controller,
        dataset_controller=mock_controller,
    )
    qtbot.addWidget(panel)
    panel.resize(1100, 760)
    panel.show()
    panel.history_table.update_history([_make_history_entry()])
    qtbot.wait(0)

    assert panel.history_group.height() == panel.history_group.sizeHint().height()
    assert panel.plots_group.height() > panel.history_group.height()


def test_training_panel_keeps_large_history_inside_compact_viewport(
    mock_main_window,
    mock_controller,
    qtbot,
):
    host = QWidget()
    host.setFixedSize(900, 430)
    host_layout = QVBoxLayout(host)
    host_layout.setContentsMargins(0, 0, 0, 0)
    panel = TrainingPanel(
        parent=mock_main_window,
        controller=mock_controller,
        dataset_controller=mock_controller,
    )
    host_layout.addWidget(panel)
    qtbot.addWidget(host)
    host.show()
    panel.history_table.update_history(
        [
            _make_history_entry(run_name=str(index + 1))
            for index in range(panel.history_table.MAX_VISIBLE_ROWS + 3)
        ]
    )
    qtbot.wait(0)

    left_widget = panel.history_group.parentWidget()
    assert left_widget is not None
    compact_table_height = panel.history_table.height()
    assert panel.history_group.geometry().bottom() <= (
        left_widget.contentsRect().bottom() - 20
    )
    assert panel.history_group.height() >= panel.history_group.sizeHint().height()
    assert panel.plots_group.height() >= panel._MIN_PLOTS_GROUP_HEIGHT
    assert compact_table_height < panel.history_table.preferred_content_height()
    assert panel.history_table.verticalScrollBar().maximum() > 0

    host.setFixedHeight(760)
    qtbot.wait(0)

    assert panel.history_table.height() > compact_table_height
    assert (
        panel.history_table.height() == panel.history_table.preferred_content_height()
    )
    assert panel.history_group.height() >= panel.history_group.sizeHint().height()
    assert panel.history_group.geometry().bottom() <= (
        left_widget.contentsRect().bottom() - 20
    )

    host.setFixedHeight(430)
    qtbot.wait(0)

    assert panel.history_table.height() == compact_table_height
    assert panel.history_group.height() >= panel.history_group.sizeHint().height()
    assert panel.plots_group.height() >= panel._MIN_PLOTS_GROUP_HEIGHT
    assert panel.history_group.geometry().bottom() <= (
        left_widget.contentsRect().bottom() - 20
    )


def test_training_panel_split_data_success(mock_main_window, mock_controller, qtbot):
    """
    Test that 'Dataset Splitting' blocks instead of mutating the controller compatibility.
    """
    panel = TrainingPanel(
        parent=mock_main_window,
        controller=mock_controller,
        dataset_controller=mock_controller,
    )
    qtbot.addWidget(panel)
    mock_controller.has_datasets.return_value = False
    mock_controller.get_trainer.return_value = None

    with (
        patch("XBrainLab.ui.panels.training.sidebar.DataSplittingDialog") as MockDialog,
        patch(
            "XBrainLab.ui.panels.training.sidebar.QMessageBox.information"
        ) as mock_info,
        patch(
            "XBrainLab.ui.panels.training.sidebar.QMessageBox.warning"
        ) as mock_warning,
    ):
        # Setup Dialog Mock
        instance = MockDialog.return_value
        instance.exec.return_value = True
        instance.get_result.return_value = {
            "train_type": "Individual",
            "is_cross_validation": False,
            "val_splitters": [
                {"split_type": "By Trial", "split_unit": "Ratio", "value": "0.2"},
            ],
            "test_splitters": [
                {"split_type": "By Trial", "split_unit": "Ratio", "value": "0.2"},
            ],
        }

        panel.sidebar.split_data()

        # Verify Dialog checked with Controller
        MockDialog.assert_called_with(panel.sidebar, mock_controller)

        mock_controller.apply_data_splitting.assert_not_called()
        mock_info.assert_not_called()
        mock_warning.assert_called_once()
        assert mock_warning.call_args.args[1] == "Data Splitting Blocked"


def test_training_panel_stop_training(mock_main_window, mock_controller, qtbot):
    """
    Test that 'Stop Training' blocks instead of mutating the controller compatibility.
    """
    panel = TrainingPanel(
        parent=mock_main_window,
        controller=mock_controller,
        dataset_controller=mock_controller,
    )
    qtbot.addWidget(panel)

    # Simulate Training
    mock_controller.is_training.return_value = True

    with patch(
        "XBrainLab.ui.panels.training.sidebar.QMessageBox.warning"
    ) as mock_warning:
        panel.sidebar.stop_training()

    mock_controller.stop_training.assert_not_called()
    mock_warning.assert_called_once()
    assert mock_warning.call_args.args[1] == "Stop Training Blocked"


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


def test_training_panel_uses_application_history_before_stale_controller(
    qtbot,
    monkeypatch,
):
    class RealMainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.study = Study()

    service_entry = _make_history_entry(model_name="ServiceNet")
    query_result = CommandResult.success_result(
        command_name="query_state",
        message="Training history query ready.",
        state={},
        changed_state=ChangedState(),
        diagnostics={
            "payload_type": "training_history",
            "row_count": 1,
            "rows": [service_entry],
        },
    )
    monkeypatch.setattr(
        "XBrainLab.ui.panels.training.panel.execute_application_command",
        lambda *_args, **_kwargs: query_result,
    )
    stale_controller = Observable()
    stale_controller.validate_ready = MagicMock(return_value=True)
    stale_controller.has_datasets = MagicMock(return_value=True)
    stale_controller.has_model = MagicMock(return_value=True)
    stale_controller.has_training_option = MagicMock(return_value=True)
    stale_controller.get_formatted_history = MagicMock(
        return_value=[_make_history_entry(model_name="StaleNet")]
    )

    panel = TrainingPanel(
        parent=RealMainWindow(),
        controller=stale_controller,
        dataset_controller=Observable(),
    )
    qtbot.addWidget(panel)

    panel.update_loop()

    stale_controller.get_formatted_history.assert_not_called()
    assert panel.history_table.rowCount() == 1
    assert panel.history_table.item(0, 2).text() == "ServiceNet"
    assert panel.current_plotting_record is service_entry["record"]


def test_training_panel_refuses_real_study_query_none_controller_history(
    qtbot,
    monkeypatch,
):
    class RealMainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.study = Study()

    monkeypatch.setattr(
        "XBrainLab.ui.panels.training.panel.execute_application_command",
        lambda *_args, **_kwargs: None,
    )
    stale_controller = Observable()
    stale_controller.validate_ready = MagicMock(return_value=True)
    stale_controller.has_datasets = MagicMock(return_value=True)
    stale_controller.has_model = MagicMock(return_value=True)
    stale_controller.has_training_option = MagicMock(return_value=True)
    stale_controller.get_formatted_history = MagicMock(
        side_effect=AssertionError("stale training history should not be read"),
    )

    panel = TrainingPanel(
        parent=RealMainWindow(),
        controller=stale_controller,
        dataset_controller=Observable(),
    )
    qtbot.addWidget(panel)

    panel.update_loop()

    stale_controller.get_formatted_history.assert_not_called()
    assert panel.history_table.rowCount() == 0
    assert panel.current_plotting_record is None


def test_training_panel_keeps_verified_history_when_live_query_is_busy(
    qtbot,
    monkeypatch,
):
    class RealMainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.study = Study()

    service_entry = _make_history_entry(model_name="ServiceNet")
    ready = CommandResult.success_result(
        command_name="query_state",
        message="Training history query ready.",
        state={},
        changed_state=ChangedState(),
        diagnostics={
            "payload_type": "training_history",
            "row_count": 1,
            "rows": [service_entry],
        },
    )
    busy = CommandResult.failure_result(
        command_name="query_state",
        message="Training state changed while results were being read.",
        state={},
        changed_state=ChangedState(),
        error_type=ErrorType.PRECONDITION,
        recoverable=True,
        diagnostics={"training_state_changed": True, "retryable": True},
    )
    recovered_entry = _make_history_entry(model_name="RecoveredNet")
    recovered = CommandResult.success_result(
        command_name="query_state",
        message="Training history query ready.",
        state={},
        changed_state=ChangedState(),
        diagnostics={
            "payload_type": "training_history",
            "row_count": 1,
            "rows": [recovered_entry],
        },
    )
    query = MagicMock(side_effect=[ready, busy, busy, recovered])
    monkeypatch.setattr(
        "XBrainLab.ui.panels.training.panel.execute_application_command",
        query,
    )
    stale_controller = Observable()
    stale_controller.validate_ready = MagicMock(return_value=True)
    stale_controller.has_datasets = MagicMock(return_value=True)
    stale_controller.has_model = MagicMock(return_value=True)
    stale_controller.has_training_option = MagicMock(return_value=True)
    stale_controller.get_formatted_history = MagicMock(
        side_effect=AssertionError("controller history must not replace query truth"),
    )

    panel = TrainingPanel(
        parent=RealMainWindow(),
        controller=stale_controller,
        dataset_controller=Observable(),
    )
    qtbot.addWidget(panel)

    panel.update_loop()
    verified_record = panel.current_plotting_record
    with patch.object(panel, "show_status_message") as status:
        panel.update_loop(log_epochs=True)
        panel.update_loop(log_epochs=True)

    stale_controller.get_formatted_history.assert_not_called()
    assert panel.history_table.rowCount() == 1
    assert panel.history_table.item(0, 2).text() == "ServiceNet"
    assert panel.current_plotting_record is verified_record
    status.assert_called_once_with(
        "Training view is updating · Keeping the last verified results"
    )

    panel.update_loop()

    assert panel.history_table.item(0, 2).text() == "RecoveredNet"
    assert panel.current_plotting_record is recovered_entry["record"]
    assert panel._history_query_unavailable_shown is False


def test_terminal_publication_preserves_verified_objects_when_final_query_is_busy(
    qtbot,
    monkeypatch,
):
    class RealMainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.study = Study()

    service_entry = _make_history_entry(epoch_count=1)
    service_entry["plan"].option.epoch = 1
    ready = CommandResult.success_result(
        command_name="query_state",
        message="Training history query ready.",
        state={},
        changed_state=ChangedState(),
        diagnostics={
            "payload_type": "training_history",
            "row_count": 1,
            "rows": [service_entry],
        },
    )
    busy = CommandResult.failure_result(
        command_name="query_state",
        message="Application state is changing. Retry this query shortly.",
        state={},
        changed_state=ChangedState(),
        error_type=ErrorType.PRECONDITION,
        recoverable=True,
        diagnostics={"application_busy": True},
    )
    query = MagicMock(side_effect=[ready, busy])
    monkeypatch.setattr(
        "XBrainLab.ui.panels.training.panel.execute_application_command",
        query,
    )
    controller = Observable()
    controller.validate_ready = MagicMock(return_value=True)
    controller.has_datasets = MagicMock(return_value=True)
    controller.has_model = MagicMock(return_value=True)
    controller.has_training_option = MagicMock(return_value=True)

    panel = TrainingPanel(
        parent=RealMainWindow(),
        controller=controller,
        dataset_controller=Observable(),
    )
    qtbot.addWidget(panel)
    panel.sidebar.check_ready_to_train = MagicMock()
    panel.update_loop()
    assert panel.history_table.item(0, 3).text() == "Running"
    service_entry["record"].is_finished.return_value = True

    panel._on_training_terminal_published(
        TrainingLifecycleEvent(
            token=TrainingStateToken(generation=12, stable=True),
            outcome=TrainingTerminalOutcome(
                state=TrainingOutcomeState.COMPLETED,
                run=TrainingRunIdentity(trainer_id="trainer-1", run_id=1),
            ),
            publication_generation=31,
        )
    )

    assert query.call_count == 2
    assert panel.history_table.item(0, 3).text() == "Completed"
    assert "All training jobs finished." in panel.log_text.toPlainText()


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


def test_training_panel_log_tab_follows_selected_history_row(
    mock_main_window,
    qtbot,
):
    """Selecting a history row should replace Log with that run's epoch lines."""
    controller = Observable()
    controller.validate_ready = MagicMock(return_value=True)
    controller.has_datasets = MagicMock(return_value=True)
    controller.has_model = MagicMock(return_value=True)
    controller.has_training_option = MagicMock(return_value=True)

    group_1 = _make_history_entry(epoch_count=1, run_name="1", repeat=2)
    group_2 = _make_history_entry(epoch_count=1, run_name="2", repeat=2)
    group_1["record"].train[TrainRecordKey.LOSS] = [0.5]
    group_1["record"].train[TrainRecordKey.ACC] = [0.8]
    group_1["record"].val[RecordKey.LOSS] = [0.6]
    group_1["record"].val[RecordKey.ACC] = [0.75]
    group_2["record"].train[TrainRecordKey.LOSS] = [0.33]
    group_2["record"].train[TrainRecordKey.ACC] = [0.9]
    group_2["record"].val[RecordKey.LOSS] = [0.44]
    group_2["record"].val[RecordKey.ACC] = [0.85]
    controller.get_formatted_history = MagicMock(return_value=[group_1, group_2])

    panel = TrainingPanel(
        parent=mock_main_window,
        controller=controller,
        dataset_controller=Observable(),
    )
    qtbot.addWidget(panel)

    panel.on_history_selection_changed(group_1["record"])
    assert "train loss=0.5" in panel.log_text.toPlainText()
    assert "train loss=0.33" not in panel.log_text.toPlainText()

    panel.on_history_selection_changed(group_2["record"])
    assert "train loss=0.33" in panel.log_text.toPlainText()
    assert "train loss=0.5" not in panel.log_text.toPlainText()


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


def test_training_panel_refreshes_plot_when_validation_changes_without_new_train_epoch(
    mock_main_window,
    qtbot,
):
    """Validation points should redraw even if train epoch count is unchanged."""
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
    assert panel.tab_acc.val_vals == [0.75]

    active_entry["record"].val[RecordKey.ACC] = [0.77]
    controller.notify("training_updated")
    qtbot.wait(50)

    assert panel.tab_acc.epochs == [1]
    assert panel.tab_acc.val_vals == [0.77]


def test_training_panel_logs_each_epoch_on_training_updated(
    mock_main_window,
    qtbot,
):
    """The log tab should include per-epoch train/validation metrics."""
    controller = Observable()
    controller.validate_ready = MagicMock(return_value=True)
    controller.has_datasets = MagicMock(return_value=True)
    controller.has_model = MagicMock(return_value=True)
    controller.has_training_option = MagicMock(return_value=True)

    active_entry = _make_history_entry(
        epoch_count=2,
        is_current_run=True,
        is_active=True,
        run_name="1",
        repeat=1,
    )
    active_entry["record"].train[TrainRecordKey.LOSS] = [0.5, 0.49]
    active_entry["record"].train[TrainRecordKey.ACC] = [0.8, 0.81]
    active_entry["record"].train[TrainRecordKey.LR] = [0.001, 0.001]
    active_entry["record"].val[RecordKey.LOSS] = [0.6, 0.59]
    active_entry["record"].val[RecordKey.ACC] = [0.75, 0.76]
    controller.get_formatted_history = MagicMock(return_value=[active_entry])

    panel = TrainingPanel(
        parent=mock_main_window,
        controller=controller,
        dataset_controller=Observable(),
    )
    qtbot.addWidget(panel)

    controller.notify("training_updated")
    qtbot.wait(50)

    log_text = panel.log_text.toPlainText()
    assert "Epoch 1: train loss=0.5 acc=0.8" in log_text
    assert "Epoch 2: train loss=0.49 acc=0.81" in log_text
    assert "val loss=0.59 acc=0.76" in log_text


def test_training_updated_observer_enters_refresh_coordinator(
    mock_main_window,
    qtbot,
):
    """training_updated should refresh live progress and shared UI status."""
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

    with patch(
        "XBrainLab.ui.panels.training.panel.refresh_after_observer",
        return_value=True,
    ) as refresh_after_observer:
        controller.notify("training_updated")
        qtbot.wait(50)

    refresh_after_observer.assert_called_once_with(
        panel,
        event_name="training_updated",
    )


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


def test_training_panel_reports_terminal_oom_as_failed(
    mock_main_window,
    qtbot,
):
    controller = Observable()
    controller.validate_ready = MagicMock(return_value=True)
    controller.has_datasets = MagicMock(return_value=True)
    controller.has_model = MagicMock(return_value=True)
    controller.has_training_option = MagicMock(return_value=True)
    controller.get_formatted_history = MagicMock(return_value=[])
    query_result = CommandResult.success_result(
        command_name="query_state",
        message="State query ready.",
        state={},
        changed_state=ChangedState(),
        diagnostics={
            "state": {
                "training": {
                    "terminal_outcome": {
                        "state": "failed",
                        "run": {"trainer_id": "trainer-1", "run_id": 1},
                        "detail": (
                            "Error: CUDA out of memory during training. "
                            "Try reducing batch size."
                        ),
                    },
                },
            },
        },
    )

    panel = TrainingPanel(
        parent=mock_main_window,
        controller=controller,
        dataset_controller=Observable(),
    )
    qtbot.addWidget(panel)

    with (
        patch(
            "XBrainLab.ui.panels.training.panel.execute_application_command",
            return_value=query_result,
        ),
        patch.object(panel, "show_status_message") as status_message,
    ):
        panel._on_training_stopped()

    status_message.assert_called_once_with("Training failed · Adjust settings")
    log = panel.log_text.toPlainText()
    assert "CUDA out of memory during training" in log
    assert "All training jobs finished" not in log


@pytest.mark.parametrize(
    ("terminal_state", "expected_status", "expected_log"),
    [
        ("completed", "Training complete · Review results", "finished"),
        ("cancelled", "Training stopped", "stopped before completion"),
    ],
)
def test_training_panel_uses_typed_terminal_outcome_for_terminal_copy(
    mock_main_window,
    qtbot,
    terminal_state,
    expected_status,
    expected_log,
):
    controller = Observable()
    controller.validate_ready = MagicMock(return_value=True)
    controller.has_datasets = MagicMock(return_value=True)
    controller.has_model = MagicMock(return_value=True)
    controller.has_training_option = MagicMock(return_value=True)
    controller.get_formatted_history = MagicMock(return_value=[])
    query_result = CommandResult.success_result(
        command_name="query_state",
        message="State query ready.",
        state={},
        changed_state=ChangedState(),
        diagnostics={
            "state": {
                "training": {
                    "terminal_outcome": {
                        "state": terminal_state,
                        "run": {"trainer_id": "trainer-1", "run_id": 1},
                        "detail": None,
                    },
                },
            },
        },
    )

    panel = TrainingPanel(
        parent=mock_main_window,
        controller=controller,
        dataset_controller=Observable(),
    )
    qtbot.addWidget(panel)

    with (
        patch(
            "XBrainLab.ui.panels.training.panel.execute_application_command",
            return_value=query_result,
        ),
        patch.object(panel, "show_status_message") as status_message,
    ):
        panel._on_training_stopped()

    status_message.assert_called_once_with(expected_status)
    assert expected_log in panel.log_text.toPlainText()


@pytest.mark.parametrize("terminal_state", ["running", "stop_requested", "unknown"])
def test_training_panel_does_not_treat_nonterminal_typed_state_as_finished(
    mock_main_window,
    qtbot,
    terminal_state,
):
    controller = Observable()
    controller.validate_ready = MagicMock(return_value=True)
    controller.has_datasets = MagicMock(return_value=True)
    controller.has_model = MagicMock(return_value=True)
    controller.has_training_option = MagicMock(return_value=True)
    controller.get_formatted_history = MagicMock(return_value=[])
    query_result = CommandResult.success_result(
        command_name="query_state",
        message="State query ready.",
        state={},
        changed_state=ChangedState(),
        diagnostics={
            "state": {
                "training": {
                    "terminal_outcome": {
                        "state": terminal_state,
                        "run": {"trainer_id": "trainer-1", "run_id": 1},
                        "detail": None,
                    },
                },
            },
        },
    )

    panel = TrainingPanel(
        parent=mock_main_window,
        controller=controller,
        dataset_controller=Observable(),
    )
    qtbot.addWidget(panel)

    with (
        patch(
            "XBrainLab.ui.panels.training.panel.execute_application_command",
            return_value=query_result,
        ),
        patch.object(panel, "show_status_message") as status_message,
    ):
        panel._on_training_stopped()

    status_message.assert_not_called()
    assert panel.training_completed_shown is False
    assert "All training jobs finished" not in panel.log_text.toPlainText()


@pytest.mark.parametrize(
    "query_result",
    [
        None,
        CommandResult.failure_result(
            command_name="query_state",
            message="State query failed.",
            state={},
            changed_state=ChangedState(),
            error_type=ErrorType.RUNTIME,
            recoverable=True,
        ),
        CommandResult.success_result(
            command_name="query_state",
            message="State query ready.",
            state={},
            changed_state=ChangedState(),
            diagnostics={"state": {}},
        ),
    ],
)
def test_training_panel_does_not_report_success_when_terminal_state_is_unknown(
    mock_main_window,
    qtbot,
    query_result,
):
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

    with (
        patch(
            "XBrainLab.ui.panels.training.panel.execute_application_command",
            return_value=query_result,
        ),
        patch.object(panel, "show_status_message") as status_message,
    ):
        panel._on_training_stopped()

    status_message.assert_not_called()
    log = panel.log_text.toPlainText()
    assert "Training outcome could not be verified" not in log
    assert "All training jobs finished" not in log


def test_training_panel_reconciles_transient_unknown_without_latching_it(
    mock_main_window,
    qtbot,
):
    """A stop event racing the train command must not hide its final OOM."""
    controller = Observable()
    controller.validate_ready = MagicMock(return_value=True)
    controller.has_datasets = MagicMock(return_value=True)
    controller.has_model = MagicMock(return_value=True)
    controller.has_training_option = MagicMock(return_value=True)
    controller.get_formatted_history = MagicMock(return_value=[])
    failed_result = CommandResult.success_result(
        command_name="query_state",
        message="State query ready.",
        state={},
        changed_state=ChangedState(),
        diagnostics={
            "state": {
                "training": {
                    "terminal_outcome": {
                        "state": "failed",
                        "run": {"trainer_id": "trainer-1", "run_id": 1},
                        "detail": (
                            "CUDA out of memory during training. "
                            "Try reducing batch size."
                        ),
                    },
                },
            },
        },
    )

    panel = TrainingPanel(
        parent=mock_main_window,
        controller=controller,
        dataset_controller=Observable(),
    )
    qtbot.addWidget(panel)

    with (
        patch(
            "XBrainLab.ui.panels.training.panel.execute_application_command",
            side_effect=[None, failed_result],
        ),
        patch.object(panel, "show_status_message") as status_message,
        patch(
            "XBrainLab.ui.panels.training.panel.refresh_after_observer",
            return_value=False,
        ),
    ):
        panel._on_training_stopped()

        assert panel.training_completed_shown is False
        assert "could not be verified" not in panel.log_text.toPlainText()

        panel.reconcile_training_terminal_outcome()

    assert panel.training_completed_shown is True
    status_message.assert_called_once_with("Training failed · Adjust settings")
    assert "CUDA out of memory during training" in panel.log_text.toPlainText()


def test_late_started_generation_cannot_overwrite_terminal_ui(
    mock_main_window,
    qtbot,
):
    controller = Observable()
    controller.validate_ready = MagicMock(return_value=True)
    controller.has_datasets = MagicMock(return_value=True)
    controller.has_model = MagicMock(return_value=True)
    controller.has_training_option = MagicMock(return_value=True)
    history_entry = _make_history_entry()
    history_entry["record"].is_finished.return_value = True
    controller.get_formatted_history = MagicMock(return_value=[history_entry])
    panel = TrainingPanel(
        parent=mock_main_window,
        controller=controller,
        dataset_controller=Observable(),
    )
    qtbot.addWidget(panel)
    panel.update_loop()
    run = TrainingRunIdentity(trainer_id="trainer-1", run_id=1)
    terminal = TrainingLifecycleEvent(
        token=TrainingStateToken(generation=12, stable=True),
        outcome=TrainingTerminalOutcome(
            state=TrainingOutcomeState.COMPLETED,
            run=run,
        ),
        publication_generation=31,
    )
    late_started = TrainingLifecycleEvent(
        token=TrainingStateToken(generation=11, stable=True),
        outcome=TrainingTerminalOutcome(
            state=TrainingOutcomeState.RUNNING,
            run=run,
        ),
    )

    with patch(
        "XBrainLab.ui.panels.training.panel.refresh_after_observer",
    ) as refresh:
        panel._on_training_terminal_published(terminal)
        terminal_log = panel.log_text.toPlainText()
        panel._on_training_started_state(late_started)

    assert panel.history_table.item(0, 3).text() == "Completed"
    assert panel.sidebar.btn_start.isEnabled()
    assert not panel.sidebar.btn_stop.isEnabled()
    assert panel.log_text.toPlainText() == terminal_log
    assert "All training jobs finished." in terminal_log
    assert "Training started (event)." not in terminal_log
    refresh.assert_called_once_with(
        panel,
        event_name="training_terminal_published",
    )


def test_completed_terminal_publication_refreshes_running_history_before_saliency(
    mock_main_window,
    qtbot,
):
    controller = Observable()
    controller.validate_ready = MagicMock(return_value=True)
    controller.has_datasets = MagicMock(return_value=True)
    controller.has_model = MagicMock(return_value=True)
    controller.has_training_option = MagicMock(return_value=True)
    history_entry = _make_history_entry()
    controller.get_formatted_history = MagicMock(return_value=[history_entry])
    panel = TrainingPanel(
        parent=mock_main_window,
        controller=controller,
        dataset_controller=Observable(),
    )
    qtbot.addWidget(panel)
    panel.update_loop()
    panel.sidebar.btn_stop.setEnabled(True)
    assert panel.history_table.item(0, 3).text() == "Running"
    history_entry["record"].is_finished.return_value = True
    event = TrainingLifecycleEvent(
        token=TrainingStateToken(generation=12, stable=True),
        outcome=TrainingTerminalOutcome(
            state=TrainingOutcomeState.COMPLETED,
            run=TrainingRunIdentity(trainer_id="trainer-1", run_id=1),
        ),
        publication_generation=31,
    )

    def refresh_training(*_args, **_kwargs) -> bool:
        panel.update_panel()
        return True

    with patch(
        "XBrainLab.ui.panels.training.panel.refresh_after_observer",
        side_effect=refresh_training,
    ) as refresh:
        panel._on_training_terminal_published(event)

    assert panel.history_table.item(0, 3).text() == "Completed"
    assert panel.sidebar.btn_start.isEnabled()
    assert not panel.sidebar.btn_stop.isEnabled()
    assert "All training jobs finished." in panel.log_text.toPlainText()
    refresh.assert_called_once_with(
        panel,
        event_name="training_terminal_published",
    )


def test_duplicate_failed_terminal_publication_refreshes_once(
    mock_main_window,
    qtbot,
):
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
    event = TrainingLifecycleEvent(
        token=TrainingStateToken(generation=8, stable=True),
        outcome=TrainingTerminalOutcome(
            state=TrainingOutcomeState.FAILED,
            run=TrainingRunIdentity(trainer_id="trainer-1", run_id=1),
            detail="CUDA out of memory during training.",
        ),
        publication_generation=22,
    )

    with patch(
        "XBrainLab.ui.panels.training.panel.refresh_after_observer",
    ) as refresh:
        panel._on_training_terminal_published(event)
        panel._on_training_terminal_published(event)

    refresh.assert_called_once_with(
        panel,
        event_name="training_terminal_published",
    )
    assert panel.log_text.toPlainText().count("Training failed:") == 1


def test_terminal_refresh_restores_failure_copy_after_history_rerender(
    mock_main_window,
    qtbot,
):
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
    panel.training_completed_shown = True
    panel._latest_terminal_outcome = TrainingTerminalOutcome(
        state=TrainingOutcomeState.FAILED,
        run=TrainingRunIdentity(trainer_id="trainer-1", run_id=1),
        detail="CUDA out of memory during training.",
    )
    panel.log_text.append(
        "Training failed: CUDA out of memory during training.",
    )

    with patch.object(panel, "update_panel", side_effect=panel.log_text.clear):
        panel.refresh_terminal_publication()

    assert panel.log_text.toPlainText() == (
        "Training failed: CUDA out of memory during training."
    )


def test_duplicate_analysis_publication_refreshes_once(
    mock_main_window,
    qtbot,
):
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
    event = TrainingLifecycleEvent(
        token=TrainingStateToken(generation=8, stable=True),
        outcome=TrainingTerminalOutcome(
            state=TrainingOutcomeState.COMPLETED,
            run=TrainingRunIdentity(trainer_id="trainer-1", run_id=1),
        ),
        publication_generation=24,
    )

    with patch(
        "XBrainLab.ui.panels.training.panel.refresh_after_observer",
    ) as refresh:
        panel._on_training_analysis_published(event)
        panel._on_training_analysis_published(event)

    refresh.assert_called_once_with(
        panel,
        event_name="training_analysis_published",
    )


def test_training_panel_high_level_events_refresh_coordinator_scope(
    mock_main_window,
    qtbot,
):
    """Named training callbacks should hand lifecycle refresh to the coordinator."""
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
            "XBrainLab.ui.panels.training.panel.refresh_after_observer",
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
    refresh.assert_any_call(panel, event_name="training_started")
    refresh.assert_any_call(panel, event_name="config_changed")
    refresh.assert_any_call(panel, event_name="training_stopped")
    refresh.assert_any_call(panel, event_name="history_cleared")


def test_training_lifecycle_observers_do_not_locally_render_before_coordinator(
    mock_main_window,
    qtbot,
):
    """Lifecycle observer handlers should leave panel rendering to the coordinator."""
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
        patch.object(panel, "update_loop") as update_loop,
        patch.object(panel.sidebar, "check_ready_to_train") as check_ready,
        patch(
            "XBrainLab.ui.panels.training.panel.refresh_after_observer",
            return_value=True,
        ) as refresh,
    ):
        panel._on_config_changed()
        panel._on_training_started()
        panel._on_training_stopped()
        panel._on_history_cleared()

    update_loop.assert_not_called()
    check_ready.assert_not_called()
    assert refresh.call_count == 4


def test_training_updated_observer_keeps_local_live_tick_refresh(
    mock_main_window,
    qtbot,
):
    """training_updated is the live-tick exception because coordinator fan-out is off."""
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
        patch.object(panel, "update_loop") as update_loop,
        patch(
            "XBrainLab.ui.panels.training.panel.refresh_after_observer",
            return_value=False,
        ) as refresh,
    ):
        panel._on_training_updated()

    update_loop.assert_called_once_with(log_epochs=True)
    refresh.assert_called_once_with(panel, event_name="training_updated")


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
