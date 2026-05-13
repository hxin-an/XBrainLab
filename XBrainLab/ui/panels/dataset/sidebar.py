"""Sidebar widget for the dataset panel: info and primary dataset actions."""

from collections.abc import Callable
from typing import Any
from unittest.mock import Mock

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
    CommandName,
    PreprocessCommand,
    PreprocessOperation,
    QueryStateCommand,
    ResetSessionCommand,
)
from XBrainLab.ui.application_capabilities import (
    LegacyControllerFallbackUnavailableError,
    blocked_reason,
    execute_application_command,
    get_command_capability,
    run_legacy_controller_fallback,
)
from XBrainLab.ui.components.info_panel import AggregateInfoPanel
from XBrainLab.ui.dialogs.dataset import ChannelSelectionDialog
from XBrainLab.ui.styles.stylesheets import Stylesheets


class DatasetSidebar(QWidget):
    """Sidebar for ``DatasetPanel`` containing information and action controls.

    Hosts an aggregate info panel, primary import buttons, channel selection,
    and a clear-dataset button. Metadata parsing lives in the Data Import
    wizard; label attachment remains visible so skipped labels can be added
    after import.

    Attributes:
        panel: The parent ``DatasetPanel`` reference.
        info_panel: ``AggregateInfoPanel`` displaying summary statistics.
        import_btn: Button to import EEG data files.
        import_folder_btn: Button to import a folder.
        import_bids_btn: Button to import a BIDS EEG folder.
        reload_recipe_btn: Button to reload a saved import recipe.
        import_label_btn: Button to attach external labels to loaded data.
        smart_parse_btn: Hidden compatibility button to auto-extract metadata.
        chan_select_btn: Button to open channel selection dialog.
        clear_btn: Button to clear the entire dataset.

    """

    def __init__(self, panel, parent=None):
        """Initialize the dataset sidebar.

        Args:
            panel: The parent ``DatasetPanel``.
            parent: Optional parent widget.

        """
        super().__init__(parent)
        self.panel = panel  # Reference to main panel (for actions access)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.init_ui()

    @property
    def controller(self):
        """DatasetController: The dataset controller from the parent panel."""
        return self.panel.controller

    @property
    def main_window(self):
        """QMainWindow: The application main window reference."""
        return self.panel.main_window

    def _update_panel_after_legacy_result(self, result) -> None:
        if result is None:
            self.panel.update_panel()

    def init_ui(self):
        """Build sidebar layout: info panel, operation and execution buttons."""
        self.setFixedWidth(260)
        self.setObjectName("RightPanel")
        self.setStyleSheet(Stylesheets.SIDEBAR_CONTAINER)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 20, 10, 20)

        # 1. Aggregate Info
        self.info_panel = AggregateInfoPanel(self.main_window)
        self.info_panel.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        layout.addWidget(self.info_panel)

        # Separator
        layout.addSpacing(10)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet(Stylesheets.SEPARATOR_HORIZONTAL)
        line.setFixedHeight(1)
        layout.addWidget(line)
        layout.addSpacing(10)

        # 2. Import Group
        ops_group = QGroupBox("IMPORT")
        ops_group.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        ops_group.setMinimumHeight(Stylesheets.SIDEBAR_PRIMARY_GROUP_MIN_HEIGHT)
        ops_layout = QVBoxLayout(ops_group)
        ops_layout.setContentsMargins(0, 10, 0, 0)
        ops_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.import_btn = QPushButton("Import file")
        self.import_btn.setToolTip(
            "Choose EEG files, review metadata and labels, then import"
        )
        self.import_btn.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.import_btn.clicked.connect(self.panel.action_handler.import_data)
        ops_layout.addWidget(self.import_btn)

        self.import_folder_btn = QPushButton("Import folder")
        self.import_folder_btn.setToolTip(
            "Choose an EEG folder, review metadata and labels, then import",
        )
        self.import_folder_btn.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.import_folder_btn.clicked.connect(
            self.panel.action_handler.import_folder_source,
        )
        ops_layout.addWidget(self.import_folder_btn)

        self.import_bids_btn = QPushButton("Import BIDS folder")
        self.import_bids_btn.setToolTip(
            "Choose a BIDS EEG folder and review detected metadata and events",
        )
        self.import_bids_btn.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.import_bids_btn.clicked.connect(
            self.panel.action_handler.import_bids_source,
        )
        ops_layout.addWidget(self.import_bids_btn)

        self.reload_recipe_btn = QPushButton("Reload Import Recipe")
        self.reload_recipe_btn.setToolTip(
            "Review a saved import recipe before applying it",
        )
        self.reload_recipe_btn.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.reload_recipe_btn.clicked.connect(
            self.panel.action_handler.reload_interpretation_recipe,
        )
        ops_layout.addWidget(self.reload_recipe_btn)

        self.smart_parse_btn = QPushButton("Smart Parse Metadata", ops_group)
        self.smart_parse_btn.setToolTip("Auto-extract Subject/Session from filenames")
        self.smart_parse_btn.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.smart_parse_btn.clicked.connect(
            self.panel.action_handler.open_smart_parser,
        )
        self.smart_parse_btn.setVisible(False)

        layout.addWidget(ops_group)
        layout.addSpacing(Stylesheets.SIDEBAR_GROUP_GAP)

        # 3. Dataset Group
        exec_group = QGroupBox("DATASET")
        exec_group.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        exec_layout = QVBoxLayout(exec_group)
        exec_layout.setContentsMargins(0, 10, 0, 0)
        exec_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.import_label_btn = QPushButton("Add labels")
        self.import_label_btn.setToolTip("Attach labels to the loaded EEG data")
        self.import_label_btn.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.import_label_btn.clicked.connect(self.panel.action_handler.import_label)
        exec_layout.addWidget(self.import_label_btn)

        self.chan_select_btn = QPushButton("Channel Selection")
        self.chan_select_btn.setToolTip("Select specific channels to keep")
        self.chan_select_btn.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.chan_select_btn.clicked.connect(self.open_channel_selection)
        exec_layout.addWidget(self.chan_select_btn)

        self.clear_btn = QPushButton("Clear Dataset")
        self.clear_btn.setStyleSheet(Stylesheets.BTN_DANGER)
        self.clear_btn.setToolTip("Create epochs before clearing the dataset.")
        self.clear_btn.clicked.connect(self.clear_dataset)
        exec_layout.addWidget(self.clear_btn)

        layout.addWidget(exec_group)

        layout.addStretch()

    def _legacy_controller_value(
        self,
        fallback: Callable[[], Any],
        *,
        blocked_title: str | None = None,
    ) -> tuple[bool, Any]:
        """Read legacy controller state only for mock / legacy UI contexts."""
        try:
            return True, run_legacy_controller_fallback(self, fallback)
        except LegacyControllerFallbackUnavailableError as exc:
            if blocked_title is not None:
                QMessageBox.warning(self, blocked_title, str(exc))
            return False, None

    def _legacy_sidebar_state(self) -> tuple[bool, bool, bool]:
        """Return legacy lock/data state when no command capability is available."""
        available, is_locked = self._legacy_controller_value(
            lambda: bool(self.controller.is_locked()),
        )
        if not available:
            return False, False, False
        available, has_data = self._legacy_controller_value(
            lambda: bool(self.controller.has_data()),
        )
        if not available:
            return False, bool(is_locked), False
        return True, bool(is_locked), bool(has_data)

    def update_sidebar(self):
        """Update info panel and button states."""
        if self.controller:
            # Update Info Panel handled by Service

            # Update Button States (Tooltips only as per design)
            scan_capability = get_command_capability(self, CommandName.SCAN_SOURCE)
            reload_capability = get_command_capability(
                self,
                CommandName.RELOAD_INTERPRETATION_RECIPE,
            )
            preprocess_capability = get_command_capability(
                self,
                CommandName.PREPROCESS,
            )
            smart_parse_capability = get_command_capability(
                self,
                CommandName.APPLY_SMART_PARSE,
            )
            import_label_capability = get_command_capability(
                self,
                CommandName.IMPORT_LABELS,
            )
            legacy_state_available = True
            legacy_is_locked = False
            legacy_has_data = False
            if any(
                capability is None
                for capability in (
                    scan_capability,
                    reload_capability,
                    preprocess_capability,
                    smart_parse_capability,
                    import_label_capability,
                )
            ):
                (
                    legacy_state_available,
                    legacy_is_locked,
                    legacy_has_data,
                ) = self._legacy_sidebar_state()

            if scan_capability is not None:
                self.import_btn.setEnabled(scan_capability.enabled)
                self.import_folder_btn.setEnabled(scan_capability.enabled)
                self.import_bids_btn.setEnabled(scan_capability.enabled)
                source_tooltip = (
                    "Choose EEG data, review metadata and labels, then import"
                    if scan_capability.enabled
                    else blocked_reason(
                        scan_capability,
                        "Data interpretation is not available right now.",
                    )
                )
                self.import_btn.setToolTip(source_tooltip)
                self.import_folder_btn.setToolTip(
                    "Choose an EEG folder, review metadata and labels, then import"
                    if scan_capability.enabled
                    else source_tooltip,
                )
                self.import_bids_btn.setToolTip(
                    "Choose a BIDS EEG folder and review metadata and events"
                    if scan_capability.enabled
                    else source_tooltip,
                )
            elif not legacy_state_available:
                self.import_btn.setEnabled(False)
                self.import_folder_btn.setEnabled(False)
                self.import_bids_btn.setEnabled(False)
                self.import_btn.setToolTip(
                    "Data interpretation availability is unavailable right now.",
                )
                self.import_folder_btn.setToolTip(
                    "Data interpretation availability is unavailable right now.",
                )
                self.import_bids_btn.setToolTip(
                    "Data interpretation availability is unavailable right now.",
                )
            elif legacy_is_locked:
                self.import_btn.setEnabled(True)
                self.import_folder_btn.setEnabled(True)
                self.import_bids_btn.setEnabled(True)
                self.import_btn.setToolTip(
                    "Dataset is locked. Reset before interpreting a new source.",
                )
                self.import_folder_btn.setToolTip(
                    "Dataset is locked. Reset before interpreting a folder.",
                )
                self.import_bids_btn.setToolTip(
                    "Dataset is locked. Reset before importing a BIDS folder.",
                )
            else:
                self.import_btn.setEnabled(True)
                self.import_folder_btn.setEnabled(True)
                self.import_bids_btn.setEnabled(True)
                self.import_btn.setToolTip(
                    "Choose EEG data, review metadata and labels, then import",
                )
                self.import_folder_btn.setToolTip(
                    "Choose an EEG folder, review metadata and labels, then import",
                )
                self.import_bids_btn.setToolTip(
                    "Choose a BIDS EEG folder and review metadata and events",
                )

            if reload_capability is not None:
                self.reload_recipe_btn.setEnabled(reload_capability.enabled)
                self.reload_recipe_btn.setToolTip(
                    "Review a saved import recipe before applying it"
                    if reload_capability.enabled
                    else blocked_reason(
                        reload_capability,
                        "Recipe reload is not available right now.",
                    ),
                )
            elif not legacy_state_available:
                self.reload_recipe_btn.setEnabled(False)
                self.reload_recipe_btn.setToolTip(
                    "Recipe reload availability is unavailable right now.",
                )
            elif legacy_is_locked:
                self.reload_recipe_btn.setEnabled(True)
                self.reload_recipe_btn.setToolTip(
                    "Dataset is locked. Reset before reloading a recipe.",
                )
            else:
                self.reload_recipe_btn.setEnabled(True)
                self.reload_recipe_btn.setToolTip(
                    "Review a saved import recipe before applying it",
                )

            if preprocess_capability is not None:
                self.chan_select_btn.setEnabled(preprocess_capability.enabled)
                self.chan_select_btn.setToolTip(
                    "Select specific channels to keep"
                    if preprocess_capability.enabled
                    else blocked_reason(
                        preprocess_capability,
                        "Load raw data before selecting channels.",
                    ),
                )
            elif not legacy_state_available:
                self.chan_select_btn.setEnabled(False)
                self.chan_select_btn.setToolTip(
                    "Channel selection availability is unavailable right now.",
                )
            elif legacy_is_locked:
                self.chan_select_btn.setEnabled(True)
                self.chan_select_btn.setToolTip(
                    "Dataset is locked. Click to see details.",
                )
            else:
                self.chan_select_btn.setEnabled(True)
                self.chan_select_btn.setToolTip("Select specific channels to keep")

            if smart_parse_capability is not None:
                self.smart_parse_btn.setEnabled(smart_parse_capability.enabled)
                self.smart_parse_btn.setToolTip(
                    "Auto-extract Subject/Session from filenames"
                    if smart_parse_capability.enabled
                    else blocked_reason(
                        smart_parse_capability,
                        "Load raw data before applying smart parse.",
                    ),
                )
            elif not legacy_state_available:
                self.smart_parse_btn.setEnabled(False)
                self.smart_parse_btn.setToolTip(
                    "Smart parse availability is unavailable right now.",
                )
            elif legacy_is_locked:
                self.smart_parse_btn.setEnabled(True)
                self.smart_parse_btn.setToolTip(
                    "Dataset is locked. Click to see details.",
                )
            else:
                self.smart_parse_btn.setEnabled(True)
                self.smart_parse_btn.setToolTip(
                    "Auto-extract Subject/Session from filenames",
                )

            if import_label_capability is not None:
                self.import_label_btn.setEnabled(import_label_capability.enabled)
                self.import_label_btn.setToolTip(
                    "Add labels to loaded data and update the current recipe trace."
                    if import_label_capability.enabled
                    else blocked_reason(
                        import_label_capability,
                        "Interpret a data source before adding labels.",
                    ),
                )
            elif not legacy_state_available:
                self.import_label_btn.setEnabled(False)
                self.import_label_btn.setToolTip(
                    "Label import availability is unavailable right now.",
                )
            elif legacy_is_locked:
                self.import_label_btn.setEnabled(False)
                self.import_label_btn.setToolTip(
                    "Dataset is locked. Reset before changing labels.",
                )
            elif not legacy_has_data:
                self.import_label_btn.setEnabled(False)
                self.import_label_btn.setToolTip(
                    "Interpret a data source before adding labels.",
                )
            else:
                self.import_label_btn.setEnabled(True)
                self.import_label_btn.setToolTip(
                    "Add labels to loaded data and update the current recipe trace.",
                )

            clear_enabled, clear_tooltip = self._clear_dataset_availability()
            self.clear_btn.setEnabled(clear_enabled)
            self.clear_btn.setToolTip(clear_tooltip)

    # --- Actions moved from Panel ---

    def _clear_dataset_availability(self) -> tuple[bool, str]:
        result = execute_application_command(
            self,
            QueryStateCommand(query="state"),
            refresh=False,
        )
        if result is None:
            available, has_epoch = self._legacy_controller_value(
                self._legacy_has_epoch_data,
            )
            if not available:
                return False, "Dataset state is unavailable right now."
            return (
                bool(has_epoch),
                "Clear epoched dataset and downstream results."
                if has_epoch
                else "Create epochs before clearing the dataset.",
            )
        if result.failed:
            return False, "Dataset state is unavailable right now."
        state = result.diagnostics.get("state")
        if isinstance(state, dict) and self._state_has_clearable_epoch(state):
            return True, "Clear epoched dataset and downstream results."
        return False, "Create epochs before clearing the dataset."

    def _legacy_has_epoch_data(self) -> bool:
        if self.controller is None:
            return False
        is_epoched = getattr(self.controller, "is_epoched", None)
        if callable(is_epoched):
            result = is_epoched()
            return False if isinstance(result, Mock) else bool(result)
        return False

    def _legacy_clear_dataset(self) -> bool:
        available, _ = self._legacy_controller_value(
            self.controller.clean_dataset,
            blocked_title="Clear Dataset Blocked",
        )
        return bool(available)

    def _legacy_apply_channel_selection(self, result) -> bool:
        available, _ = self._legacy_controller_value(
            lambda: self.controller.apply_channel_selection(result),
            blocked_title="Channel Selection Blocked",
        )
        return bool(available)

    def _legacy_loaded_data_list_for_channel_selection(self) -> list[Any] | None:
        available, data_list = self._legacy_controller_value(
            self.controller.get_loaded_data_list,
            blocked_title="Channel Selection Blocked",
        )
        if not available:
            return None
        return list(data_list or [])

    @staticmethod
    def _state_has_clearable_epoch(state: dict[str, Any]) -> bool:
        epoch = DatasetSidebar._state_section(state, "epoch")
        return bool(epoch.get("exists")) or bool(epoch.get("available"))

    @staticmethod
    def _state_section(state: dict[str, Any], key: str) -> dict[str, Any]:
        value = state.get(key)
        return value if isinstance(value, dict) else {}

    def open_channel_selection(self):
        """Open the channel selection dialog.

        Blocked if the dataset is locked or no data is loaded.
        Shows a confirmation prompt before applying.
        """
        if not self.controller:
            return

        preprocess_capability = get_command_capability(self, CommandName.PREPROCESS)
        if preprocess_capability is not None and not preprocess_capability.enabled:
            QMessageBox.warning(
                self,
                "Channel Selection Blocked",
                blocked_reason(
                    preprocess_capability,
                    "Load raw data before selecting channels.",
                ),
            )
            return

        if preprocess_capability is None:
            available, has_data = self._legacy_controller_value(
                lambda: bool(self.controller.has_data()),
                blocked_title="Channel Selection Blocked",
            )
            if not available:
                return
            if not has_data:
                QMessageBox.warning(self, "Warning", "No data loaded.")
                return

            available, is_locked = self._legacy_controller_value(
                lambda: bool(self.controller.is_locked()),
                blocked_title="Channel Selection Blocked",
            )
            if not available:
                return
            if is_locked:
                QMessageBox.warning(
                    self,
                    "Action Blocked",
                    "Dataset is locked because a data operation has "
                    "been applied.\n"
                    "Please 'Reset All Preprocessing' to undo Channel Selection or "
                    "'Clear Dataset' to start over.",
                )
                return

        reply = QMessageBox.question(
            self,
            "Warning",
            "Performing Channel Selection will modify the dataset.\n"
            "You can undo this later using 'Reset All Preprocessing'.\n\n"
            "Do you want to proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.No:
            return

        data_list = self._loaded_data_list_for_channel_selection(preprocess_capability)
        if data_list is None:
            return
        dialog = ChannelSelectionDialog(self, data_list)
        if dialog.exec():
            result = dialog.get_result()
            if result:
                try:
                    command_result = execute_application_command(
                        self,
                        PreprocessCommand(
                            operation=PreprocessOperation.SELECT_CHANNELS,
                            channels=list(result),
                        ),
                    )
                    if command_result is None:
                        if not self._legacy_apply_channel_selection(result):
                            return
                    elif command_result.failed:
                        QMessageBox.critical(
                            self,
                            "Error",
                            f"Channel selection failed: {command_result.message}",
                        )
                        return
                    self._update_panel_after_legacy_result(command_result)
                    QMessageBox.information(
                        self,
                        "Success",
                        "Channel selection applied.",
                    )
                except Exception as e:
                    QMessageBox.critical(
                        self,
                        "Error",
                        f"Channel selection failed: {e}",
                    )

    def _loaded_data_list_for_channel_selection(
        self,
        preprocess_capability,
    ) -> list[Any] | None:
        result = execute_application_command(
            self,
            QueryStateCommand(query="data_lists", include_objects=True),
            refresh=False,
        )
        if result is None:
            if preprocess_capability is None:
                return self._legacy_loaded_data_list_for_channel_selection()
            return []
        if result.failed:
            return []
        data_list = result.diagnostics.get("loaded_data_list")
        return list(data_list) if isinstance(data_list, list) else []

    def clear_dataset(self):
        """Prompt the user and clear the entire loaded dataset."""
        clear_enabled, clear_tooltip = self._clear_dataset_availability()
        if not clear_enabled:
            QMessageBox.information(self, "Clear Dataset", clear_tooltip)
            return

        reset_capability = get_command_capability(self, CommandName.RESET_SESSION)
        if reset_capability is not None and not reset_capability.enabled:
            QMessageBox.warning(
                self,
                "Clear Dataset Blocked",
                blocked_reason(
                    reset_capability,
                    "Dataset cannot be cleared right now.",
                ),
            )
            return

        needs_confirmation = reset_capability is None or (
            reset_capability.confirmation_required
            or reset_capability.requires_confirmation
        )
        if needs_confirmation:
            reply = QMessageBox.question(
                self,
                "Confirm Clear",
                "Are you sure you want to clear the entire dataset?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            result = execute_application_command(
                self,
                ResetSessionCommand(confirmed=True),
            )
            if result is None:
                if not self._legacy_clear_dataset():
                    return
            elif result.failed:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to clear dataset: {result.message}",
                )
                return
            self._update_panel_after_legacy_result(result)
            QMessageBox.information(self, "Success", "Dataset cleared.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to clear dataset: {e}")
