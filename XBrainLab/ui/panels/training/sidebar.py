"""Sidebar widget for the training panel with configuration and execution controls."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGroupBox,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.ui.components.info_panel import AggregateInfoPanel

# Dialog imports will be local to avoid circular deps if needed,
# or top level if no circular dep.
# TrainingPanel imports Sidebar. Sidebar imports Dialogs.
# Dialogs don't import Panel/Sidebar.
from XBrainLab.ui.dialogs.dataset import DataSplittingDialog
from XBrainLab.ui.dialogs.training import ModelSelectionDialog, TrainingSettingDialog
from XBrainLab.ui.styles.stylesheets import Stylesheets


class TrainingSidebar(QWidget):
    """Sidebar for ``TrainingPanel`` providing configuration and execution controls.

    Hosts data-splitting, model-selection, training-setting dialogs,
    and start/stop/clear buttons.  Validates readiness before enabling
    the start button.

    Attributes:
        panel: The parent ``TrainingPanel`` reference.
        info_panel: ``AggregateInfoPanel`` displaying summary statistics.
        btn_split: Button for dataset splitting configuration.
        btn_model: Button for model selection.
        btn_setting: Button for training hyperparameter settings.
        btn_start: Button to start training (enabled when ready).
        btn_stop: Button to stop an in-progress training run.
        btn_clear: Button to clear training history.
    """

    def __init__(self, panel, parent=None):
        """Initialize the training sidebar.

        Args:
            panel: The parent ``TrainingPanel``.
            parent: Optional parent widget.
        """
        super().__init__()
        self.panel = panel
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.init_ui()

    @property
    def controller(self):
        """TrainingController: The training controller from the parent panel."""
        return self.panel.controller

    @property
    def dataset_controller(self):
        """DatasetController: The dataset controller from the parent panel."""
        return self.panel.dataset_controller

    @property
    def main_window(self):
        """QMainWindow: The application main window reference."""
        return self.panel.main_window

    def init_ui(self):
        """Build the sidebar layout with info, configuration, and execution groups."""
        self.setFixedWidth(260)
        self.setObjectName("RightPanel")
        self.setStyleSheet(Stylesheets.SIDEBAR_CONTAINER)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 20, 10, 20)

        # 1. Aggregate Information
        # Note: AggregateInfoPanel expects "main_window" as parent
        # potentially for referencing?
        # Let's check AggregateInfoPanel signature.
        # It usually takes parent=None.
        # In current code: self.info_panel = AggregateInfoPanel(self.main_window)
        # So we pass main_window.
        self.info_panel = AggregateInfoPanel(self.main_window)
        self.info_panel.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        layout.addWidget(self.info_panel, stretch=1)

        layout.addSpacing(10)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet(Stylesheets.SEPARATOR_HORIZONTAL)
        line.setFixedHeight(1)
        layout.addWidget(line)
        layout.addSpacing(10)

        # Group 1: Configuration
        config_group = QGroupBox("CONFIGURATION")
        config_group.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        config_layout = QVBoxLayout(config_group)
        config_layout.setContentsMargins(0, 10, 0, 0)

        self.btn_split = QPushButton("Dataset Splitting")
        self.btn_split.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.btn_split.clicked.connect(self.split_data)
        config_layout.addWidget(self.btn_split)

        self.btn_model = QPushButton("Model Selection")
        self.btn_model.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.btn_model.clicked.connect(self.select_model)
        config_layout.addWidget(self.btn_model)

        self.btn_setting = QPushButton("Training Setting")
        self.btn_setting.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.btn_setting.clicked.connect(self.training_setting)
        config_layout.addWidget(self.btn_setting)

        layout.addWidget(config_group)
        layout.addSpacing(20)

        # Group 2: Execution
        exec_group = QGroupBox("EXECUTION")
        exec_group.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        exec_layout = QVBoxLayout(exec_group)
        exec_layout.setContentsMargins(0, 10, 0, 0)

        self.btn_start = QPushButton("Start Training")
        self.btn_start.setStyleSheet(Stylesheets.BTN_SUCCESS)
        self.btn_start.clicked.connect(self.start_training_ui_action)
        self.btn_start.setEnabled(False)
        exec_layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("Stop Training")
        self.btn_stop.setStyleSheet(Stylesheets.BTN_WARNING)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_training)
        exec_layout.addWidget(self.btn_stop)

        self.btn_clear = QPushButton("Clear History")
        self.btn_clear.setStyleSheet(Stylesheets.BTN_DANGER)
        self.btn_clear.clicked.connect(self.clear_history)
        exec_layout.addWidget(self.btn_clear)

        layout.addWidget(exec_group)
        layout.addStretch()

        # Initial check
        self.check_ready_to_train()

    def check_ready_to_train(self, *args):
        """Check if all configurations are set and enable/disable start button."""
        ready = self.controller.validate_ready()
        self.btn_start.setEnabled(ready)

        if not ready:
            missing = []
            if not self.controller.has_datasets():
                missing.append("Data Splitting")
            if not self.controller.has_model():
                missing.append("Model Selection")
            if not self.controller.has_training_option():
                missing.append("Training Settings")
            self.btn_start.setToolTip(f"Please configure: {', '.join(missing)}")
        else:
            self.btn_start.setToolTip("Start Training")

    def update_info(self):
        """Refresh the aggregate info panel (delegated to InfoPanelService)."""
        if not self.info_panel:
            return

        # Handled by InfoPanelService

    # --- Actions ---

    def split_data(self):
        """Open the data-splitting dialog and apply the configuration.

        Validates that epoched data exists and training is not running.
        Warns if existing datasets/history will be cleared.
        """
        if not self.controller.get_loaded_data_list():
            QMessageBox.warning(
                self, "No Data", "Please load and preprocess data first."
            )
            return

        if self.controller.get_epoch_data() is None:
            QMessageBox.warning(
                self,
                "No Epoched Data",
                "Please perform epoching in the Preprocess panel first.",
            )
            return

        if self.controller.is_training():
            QMessageBox.warning(
                self,
                "Training Running",
                "Cannot change data splitting while training is running.",
            )
            return

        win = DataSplittingDialog(self, self.controller)
        if win.exec():
            if self.controller.has_datasets() or self.controller.get_trainer():
                reply = QMessageBox.question(
                    self,
                    "Reset Training Data",
                    "Applying new data splitting will clear existing datasets "
                    "and training history. Continue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.No:
                    return
                self.controller.clean_datasets(force_update=True)

            generator = win.get_result()
            if generator:
                self.controller.apply_data_splitting(generator)
            QMessageBox.information(
                self, "Success", "Data splitting configuration saved."
            )
            self.check_ready_to_train()

    def select_model(self):
        """Open the model-selection dialog and store the chosen model.

        Blocked while training is running.
        """
        if self.controller.is_training():
            QMessageBox.warning(
                self,
                "Training Running",
                "Cannot change model while training is running.",
            )
            return

        win = ModelSelectionDialog(self, self.controller)
        if win.exec():
            self.controller.set_model_holder(win.get_result())
            model_holder = self.controller.get_model_holder()
            model_name = model_holder.target_model.__name__
            QMessageBox.information(self, "Success", f"Model selected: {model_name}")
            self.check_ready_to_train()

    def training_setting(self):
        """Open the training-settings dialog and store the configuration.

        Blocked while training is running.
        """
        if self.controller.is_training():
            QMessageBox.warning(
                self,
                "Training Running",
                "Cannot change training settings while training is running.",
            )
            return

        win = TrainingSettingDialog(self, self.controller)
        if win.exec():
            self.controller.set_training_option(win.get_result())
            QMessageBox.information(self, "Success", "Training settings saved.")
            self.check_ready_to_train()

    def start_training_ui_action(self):
        """Start training via the controller and enable the stop button.

        Raises:
            Exception: Propagated from the controller on failure, shown
                in a critical message box.
        """
        try:
            if not self.controller.is_training():
                self.controller.start_training()
                self.btn_stop.setEnabled(True)
                self.check_ready_to_train()
                # Panel should know training started to update log?
                # Observer in Panel handles "training_started" event.
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start training: {e}")

    def stop_training(self):
        """Request the controller to stop the current training run."""
        if self.controller.is_training():
            self.controller.stop_training()
            self.btn_stop.setEnabled(False)
            # Controller will emit stopped event which panel handles

    def clear_history(self):
        """Clear all training history records.

        Blocked while training is running.
        """
        try:
            if self.controller.is_training():
                QMessageBox.warning(
                    self, "Warning", "Cannot clear history while training is running."
                )
                return
            self.controller.clear_history()
            # Panel needs to clear table/plots.
            # Controller emits "training_updated"? Or we should have a
            # "history_cleared" signal?
            # Or Panel should have an observer for history clear?
            # Currently Panel.clear_history calls controller.clear_history
            # then does UI cleanup.
            # If Sidebar calls controller.clear_history, Panel needs to know!
            # The current observer bridge on 'training_updated' might not cover clear.
            # Panel has:
            # self.bridge_updated.connect_to(lambda *args, **kwargs: self.update_loop())
            # If clear_history empties history, update_loop will see 0 rows and sync.
            # So Panel UI cleanup might be automatic IF update_loop runs.
            # But we should ensure update_loop runs.
            # If controller.clear_history() emits 'training_updated', we are good.
            # If not, we might need manual trigger.
            # Let's assume for now we might need to notify Panel.
            # But better design: Controller emits 'history_cleared'.

            self.check_ready_to_train()
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Error clearing history: {e}")

    def on_training_started(self):
        """Update button states when training begins."""
        self.btn_stop.setEnabled(True)
        self.check_ready_to_train()

    def on_training_stopped(self):
        """Update button states when training ends."""
        self.btn_stop.setEnabled(False)
        self.check_ready_to_train()
