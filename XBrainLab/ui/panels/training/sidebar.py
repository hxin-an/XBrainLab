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

from XBrainLab.backend.application import (
    ClearDatasetsCommand,
    ClearTrainingHistoryCommand,
    CommandName,
    ConfigureTrainingCommand,
    GenerateDatasetCommand,
    QueryStateCommand,
    StopTrainingCommand,
    TrainCommand,
)
from XBrainLab.ui.application_capabilities import (
    LegacyControllerFallbackUnavailableError,
    blocked_reason,
    execute_application_command,
    get_command_capability,
    run_legacy_controller_fallback,
)
from XBrainLab.ui.components.info_panel import AggregateInfoPanel

# Dialog imports will be local to avoid circular deps if needed,
# or top level if no circular dep.
# TrainingPanel imports Sidebar. Sidebar imports Dialogs.
# Dialogs don't import Panel/Sidebar.
from XBrainLab.ui.dialogs.dataset import DataSplittingDialog
from XBrainLab.ui.dialogs.training import ModelSelectionDialog, TrainingSettingDialog
from XBrainLab.ui.styles.stylesheets import Stylesheets

_DATASET_REPLACEMENT_REASON = (
    "Reset the session or start a new session before generating a new "
    "dataset from an existing active dataset."
)


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
        train_capability = get_command_capability(self, CommandName.TRAIN)
        if train_capability is None:
            ready = self.controller.validate_ready()
        else:
            ready = train_capability.enabled
        self.btn_start.setEnabled(ready)

        if not ready:
            if train_capability is None:
                missing = []
                if not self.controller.has_datasets():
                    missing.append("Data Splitting")
                if not self.controller.has_model():
                    missing.append("Model Selection")
                if not self.controller.has_training_option():
                    missing.append("Training Settings")
                self.btn_start.setToolTip(f"Please configure: {', '.join(missing)}")
            else:
                self.btn_start.setToolTip(
                    blocked_reason(
                        train_capability,
                        "Training is not ready. Check dataset, model, and settings.",
                    )
                )
        else:
            self.btn_start.setToolTip("Start Training")

    def update_info(self):
        """Refresh the aggregate info panel (delegated to InfoPanelService)."""
        if not self.info_panel:
            return

        # Handled by InfoPanelService

    # --- Actions ---

    def _configuration_blocked(self, fallback_message: str) -> bool:
        """Return whether training configuration edits should be blocked."""
        configure_capability = get_command_capability(
            self,
            CommandName.CONFIGURE_TRAINING,
        )
        if configure_capability is not None and not configure_capability.enabled:
            QMessageBox.warning(
                self,
                "Training Configuration Blocked",
                blocked_reason(configure_capability, fallback_message),
            )
            return True
        if configure_capability is None and self.controller.is_training():
            QMessageBox.warning(
                self,
                "Training Running",
                fallback_message,
            )
            return True
        return False

    def split_data(self):
        """Open the data-splitting dialog and apply the configuration.

        Validates that epoched data exists and training is not running.
        Warns if existing datasets/history will be cleared.
        """
        if self._data_splitting_blocked():
            return

        generate_capability = get_command_capability(
            self,
            CommandName.GENERATE_DATASET,
        )
        if generate_capability is None and not self.controller.get_loaded_data_list():
            QMessageBox.warning(
                self,
                "No Data",
                "Please load and preprocess data first.",
            )
            return

        if generate_capability is None and self.controller.get_epoch_data() is None:
            QMessageBox.warning(
                self,
                "No Epoched Data",
                "Please perform epoching in the Preprocess panel first.",
            )
            return

        if generate_capability is None and self.controller.is_training():
            QMessageBox.warning(
                self,
                "Training Running",
                "Cannot change data splitting while training is running.",
            )
            return

        dialog_context = self._data_splitting_dialog_context()
        if dialog_context is None:
            return

        win = DataSplittingDialog(self, self.controller, **dialog_context)
        if win.exec():
            if self._should_clear_datasets_before_split():
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
                clear_result = execute_application_command(
                    self,
                    ClearDatasetsCommand(confirmed=True),
                )
                if clear_result is None:
                    run_legacy_controller_fallback(
                        self,
                        lambda: self.controller.clean_datasets(force_update=True),
                    )
                elif clear_result.failed:
                    QMessageBox.critical(
                        self,
                        "Reset Training Data Failed",
                        clear_result.message,
                    )
                    return

            generator = win.get_result()
            if generator:
                result = execute_application_command(
                    self,
                    GenerateDatasetCommand(generator=generator),
                )
                if result is None:
                    run_legacy_controller_fallback(
                        self,
                        lambda: self.controller.apply_data_splitting(generator),
                    )
                elif result.failed:
                    QMessageBox.critical(
                        self,
                        "Data Splitting Failed",
                        result.message,
                    )
                    return
            QMessageBox.information(
                self,
                "Success",
                "Data splitting configuration saved.",
            )
            if generator:
                self._check_ready_after_legacy_result(result)

    def _data_splitting_blocked(self) -> bool:
        generate_capability = get_command_capability(
            self,
            CommandName.GENERATE_DATASET,
        )
        if generate_capability is None or generate_capability.enabled:
            return False

        if self._can_replace_existing_dataset(generate_capability.reasons):
            return False

        QMessageBox.warning(
            self,
            "Data Splitting Blocked",
            blocked_reason(
                generate_capability,
                "Create epochs before generating datasets.",
            ),
        )
        return True

    def _can_replace_existing_dataset(self, generate_reasons: list[str]) -> bool:
        clear_capability = get_command_capability(self, CommandName.CLEAR_DATASETS)
        return (
            generate_reasons == [_DATASET_REPLACEMENT_REASON]
            and clear_capability is not None
            and clear_capability.enabled
        )

    def _data_splitting_dialog_context(self) -> dict | None:
        result = execute_application_command(
            self,
            QueryStateCommand(
                query="dataset_generation_context",
                include_objects=True,
            ),
            refresh=False,
        )
        if result is None:
            return {}
        if result.failed:
            QMessageBox.warning(
                self,
                "Data Splitting Blocked",
                result.message,
            )
            return None
        diagnostics = getattr(result, "diagnostics", {}) or {}
        if diagnostics.get("payload_type") != "dataset_generation_context":
            return {}
        return {
            "epoch_data": diagnostics.get("epoch_data"),
            "dataset_generator": diagnostics.get("dataset_generator"),
        }

    def _should_clear_datasets_before_split(self) -> bool:
        """Return whether applying a new split must clear existing training data."""
        generate_capability = get_command_capability(
            self,
            CommandName.GENERATE_DATASET,
        )
        if generate_capability is None:
            return bool(self.controller.has_datasets() or self.controller.get_trainer())
        return self._can_replace_existing_dataset(generate_capability.reasons)

    def _check_ready_after_legacy_result(self, result) -> None:
        if result is None:
            self.check_ready_to_train()

    def select_model(self):
        """Open the model-selection dialog and store the chosen model.

        Blocked while training is running.
        """
        if self._configuration_blocked(
            "Cannot change model while training is running.",
        ):
            return

        win = ModelSelectionDialog(self, self.controller)
        if win.exec():
            model_holder = win.get_result()
            if model_holder is None:
                QMessageBox.warning(self, "Model Selection", "No model was selected.")
                return
            selected_model_name = model_holder.target_model.__name__
            result = execute_application_command(
                self,
                ConfigureTrainingCommand(
                    model_name=selected_model_name,
                    model_params=dict(model_holder.model_params_map),
                    pretrained_weight_path=model_holder.pretrained_weight_path,
                ),
            )
            if result is None:
                run_legacy_controller_fallback(
                    self,
                    lambda: self.controller.set_model_holder(model_holder),
                )
                model_holder = self.controller.get_model_holder()
                if model_holder is None:
                    QMessageBox.critical(
                        self,
                        "Model Selection Failed",
                        "The selected model was not applied.",
                    )
                    return
                selected_model_name = model_holder.target_model.__name__
            elif result.failed:
                QMessageBox.critical(self, "Model Selection Failed", result.message)
                return
            QMessageBox.information(
                self,
                "Success",
                f"Model selected: {selected_model_name}",
            )
            self._check_ready_after_legacy_result(result)

    def training_setting(self):
        """Open the training-settings dialog and store the configuration.

        Blocked while training is running.
        """
        if self._configuration_blocked(
            "Cannot change training settings while training is running.",
        ):
            return

        win = TrainingSettingDialog(
            self,
            self.controller,
            initial_option=self._training_option_snapshot(),
        )
        if win.exec():
            option = win.get_result()
            optimizer_name = getattr(getattr(option, "optim", None), "__name__", "adam")
            use_cpu = bool(getattr(option, "use_cpu", True))
            gpu_idx = getattr(option, "gpu_idx", None)
            result = execute_application_command(
                self,
                ConfigureTrainingCommand(
                    epoch=getattr(option, "epoch", None),
                    batch_size=getattr(option, "bs", None),
                    learning_rate=getattr(option, "lr", None),
                    repeat=getattr(option, "repeat_num", 1),
                    device=("cpu" if use_cpu else f"cuda:{gpu_idx or 0}"),
                    optimizer=optimizer_name,
                    optimizer_params=dict(getattr(option, "optim_params", {}) or {}),
                    save_checkpoints_every=getattr(option, "checkpoint_epoch", 0),
                    output_dir=getattr(option, "output_dir", "./output"),
                    evaluation_option=getattr(
                        getattr(option, "evaluation_option", None),
                        "value",
                        None,
                    ),
                ),
            )
            if result is None:
                run_legacy_controller_fallback(
                    self,
                    lambda: self.controller.set_training_option(option),
                )
            elif result.failed:
                QMessageBox.critical(
                    self,
                    "Training Settings Failed",
                    result.message,
                )
                return
            QMessageBox.information(self, "Success", "Training settings saved.")
            self._check_ready_after_legacy_result(result)

    def _training_option_snapshot(self) -> dict | None:
        result = execute_application_command(
            self,
            QueryStateCommand(query="state"),
            refresh=False,
        )
        if result is None:
            return None
        if result.failed:
            QMessageBox.warning(
                self,
                "Training Settings Blocked"
                if result.recoverable
                else "Training Settings Failed",
                result.message,
            )
            return {}
        diagnostics = getattr(result, "diagnostics", {}) or {}
        state = diagnostics.get("state")
        training = state.get("training") if isinstance(state, dict) else {}
        option = training.get("training_option") if isinstance(training, dict) else None
        return dict(option) if isinstance(option, dict) else {}

    def start_training_ui_action(self):
        """Start training via the application command spine and enable stop.

        Raises:
            Exception: Propagated from the controller on failure, shown
                in a critical message box.

        """
        try:
            train_capability = get_command_capability(self, CommandName.TRAIN)
            if train_capability is not None and not train_capability.enabled:
                QMessageBox.warning(
                    self,
                    "Training Not Ready",
                    blocked_reason(
                        train_capability,
                        "Training is not ready.",
                    ),
                )
                return
            if self._should_start_training(train_capability):
                if train_capability is not None and (
                    train_capability.requires_confirmation
                    or train_capability.confirmation_required
                ):
                    reply = QMessageBox.question(
                        self,
                        "Start Training",
                        (
                            "Training can take time and use CPU/GPU resources. "
                            "Start training now?"
                        ),
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    if reply == QMessageBox.StandardButton.No:
                        return
                result = execute_application_command(self, TrainCommand(confirmed=True))
                if result is None:
                    run_legacy_controller_fallback(
                        self,
                        self.controller.start_training,
                    )
                elif result.failed:
                    QMessageBox.critical(
                        self,
                        "Error",
                        f"Failed to start training: {result.message}",
                    )
                    return
                self.btn_stop.setEnabled(True)
                self._check_ready_after_legacy_result(result)
                # Panel should know training started to update log?
                # Observer in Panel handles "training_started" event.
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start training: {e}")

    def _should_start_training(self, train_capability) -> bool:
        if train_capability is None:
            return not self.controller.is_training()
        return train_capability.enabled

    def stop_training(self):
        """Request the controller to stop the current training run."""
        stop_capability = get_command_capability(self, CommandName.STOP_TRAINING)
        if stop_capability is not None and not stop_capability.enabled:
            QMessageBox.warning(
                self,
                "Stop Training Blocked",
                blocked_reason(stop_capability, "No training run is active."),
            )
            return

        if stop_capability is None and not self.controller.is_training():
            return

        result = execute_application_command(self, StopTrainingCommand())
        if result is None:
            try:
                run_legacy_controller_fallback(self, self.controller.stop_training)
            except LegacyControllerFallbackUnavailableError as exc:
                QMessageBox.warning(self, "Stop Training Blocked", str(exc))
                return
        elif result.failed:
            QMessageBox.warning(
                self,
                "Warning",
                f"Failed to stop training: {result.message}",
            )
            return
        self.btn_stop.setEnabled(False)
        # Controller will emit stopped event which panel handles

    def clear_history(self):
        """Clear all training history records.

        Blocked while training is running.
        """
        try:
            clear_capability = get_command_capability(
                self,
                CommandName.CLEAR_TRAINING_HISTORY,
            )
            if clear_capability is not None and not clear_capability.enabled:
                QMessageBox.warning(
                    self,
                    "Clear History Blocked",
                    blocked_reason(
                        clear_capability,
                        "No training history is available to clear.",
                    ),
                )
                return
            if clear_capability is None and self.controller.is_training():
                QMessageBox.warning(
                    self,
                    "Warning",
                    "Cannot clear history while training is running.",
                )
                return
            reply = QMessageBox.question(
                self,
                "Clear Training History",
                "Clear all training history records? This cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return
            result = execute_application_command(
                self,
                ClearTrainingHistoryCommand(confirmed=True),
            )
            if result is None:
                try:
                    run_legacy_controller_fallback(
                        self,
                        self.controller.clear_history,
                    )
                except LegacyControllerFallbackUnavailableError as exc:
                    QMessageBox.warning(self, "Clear History Blocked", str(exc))
                    return
            elif result.failed:
                QMessageBox.warning(self, "Warning", result.message)
                return

            self._check_ready_after_legacy_result(result)
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
