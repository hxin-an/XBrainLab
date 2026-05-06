"""Sidebar widget for the dataset panel: info, operations, and controls."""

from typing import Any

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
    LEGACY_FALLBACK_UNAVAILABLE_MESSAGE,
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

    Hosts an aggregate info panel, import/parse buttons, channel selection,
    and a clear-dataset button.

    Attributes:
        panel: The parent ``DatasetPanel`` reference.
        info_panel: ``AggregateInfoPanel`` displaying summary statistics.
        import_btn: Button to import EEG data files.
        import_folder_btn: Button to interpret a folder or BIDS root.
        reload_recipe_btn: Button to reload a saved import recipe.
        import_label_btn: Button to import external labels.
        smart_parse_btn: Button to auto-extract metadata from filenames.
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
        layout.addWidget(self.info_panel, stretch=1)

        # Separator
        layout.addSpacing(10)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet(Stylesheets.SEPARATOR_HORIZONTAL)
        line.setFixedHeight(1)
        layout.addWidget(line)
        layout.addSpacing(10)

        # 2. Operations Group
        ops_group = QGroupBox("OPERATIONS")
        ops_group.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        ops_layout = QVBoxLayout(ops_group)
        ops_layout.setContentsMargins(0, 10, 0, 0)

        self.import_btn = QPushButton("Interpret Data Source")
        self.import_btn.setToolTip("Scan, preview, validate, and apply EEG data")
        self.import_btn.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.import_btn.clicked.connect(self.panel.action_handler.import_data)
        ops_layout.addWidget(self.import_btn)

        self.import_folder_btn = QPushButton("Interpret Folder / BIDS")
        self.import_folder_btn.setToolTip(
            "Scan a folder or BIDS root, then preview and confirm it",
        )
        self.import_folder_btn.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.import_folder_btn.clicked.connect(
            self.panel.action_handler.import_folder_source,
        )
        ops_layout.addWidget(self.import_folder_btn)

        self.reload_recipe_btn = QPushButton("Reload Import Recipe")
        self.reload_recipe_btn.setToolTip(
            "Review a saved import recipe before applying it",
        )
        self.reload_recipe_btn.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.reload_recipe_btn.clicked.connect(
            self.panel.action_handler.reload_interpretation_recipe,
        )
        ops_layout.addWidget(self.reload_recipe_btn)

        self.import_label_btn = QPushButton("Add Labels to Loaded Data")
        self.import_label_btn.setToolTip("Apply external labels to loaded files")
        self.import_label_btn.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.import_label_btn.clicked.connect(self.panel.action_handler.import_label)
        ops_layout.addWidget(self.import_label_btn)

        self.smart_parse_btn = QPushButton("Smart Parse Metadata")
        self.smart_parse_btn.setToolTip("Auto-extract Subject/Session from filenames")
        self.smart_parse_btn.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.smart_parse_btn.clicked.connect(
            self.panel.action_handler.open_smart_parser,
        )
        ops_layout.addWidget(self.smart_parse_btn)

        layout.addWidget(ops_group)

        # 3. Execution Group
        exec_group = QGroupBox("EXECUTION")
        exec_group.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        exec_layout = QVBoxLayout(exec_group)
        exec_layout.setContentsMargins(0, 10, 0, 0)

        self.chan_select_btn = QPushButton("Channel Selection")
        self.chan_select_btn.setToolTip("Select specific channels to keep")
        self.chan_select_btn.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.chan_select_btn.clicked.connect(self.open_channel_selection)
        exec_layout.addWidget(self.chan_select_btn)

        self.clear_btn = QPushButton("Clear Dataset")
        self.clear_btn.setStyleSheet(Stylesheets.BTN_DANGER)
        self.clear_btn.setToolTip("Remove all loaded data")
        self.clear_btn.clicked.connect(self.clear_dataset)
        exec_layout.addWidget(self.clear_btn)

        layout.addWidget(exec_group)

        layout.addStretch()

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
            if scan_capability is not None:
                self.import_btn.setEnabled(scan_capability.enabled)
                self.import_folder_btn.setEnabled(scan_capability.enabled)
                source_tooltip = (
                    "Scan, preview, validate, and apply EEG data"
                    if scan_capability.enabled
                    else blocked_reason(
                        scan_capability,
                        "Data interpretation is not available right now.",
                    )
                )
                self.import_btn.setToolTip(source_tooltip)
                self.import_folder_btn.setToolTip(
                    "Scan a folder or BIDS root, then preview and confirm it"
                    if scan_capability.enabled
                    else source_tooltip,
                )
            elif scan_capability is None and self.controller.is_locked():
                self.import_btn.setToolTip(
                    "Dataset is locked. Reset before interpreting a new source.",
                )
                self.import_folder_btn.setToolTip(
                    "Dataset is locked. Reset before interpreting a folder.",
                )
            else:
                self.import_btn.setToolTip(
                    "Scan, preview, validate, and apply EEG data",
                )
                self.import_folder_btn.setToolTip(
                    "Scan a folder or BIDS root, then preview and confirm it",
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
            elif reload_capability is None and self.controller.is_locked():
                self.reload_recipe_btn.setToolTip(
                    "Dataset is locked. Reset before reloading a recipe.",
                )
            else:
                self.reload_recipe_btn.setToolTip(
                    "Review a saved import recipe before applying it",
                )

            preprocess_capability = get_command_capability(
                self,
                CommandName.PREPROCESS,
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
            elif preprocess_capability is None and self.controller.is_locked():
                self.chan_select_btn.setToolTip(
                    "Dataset is locked. Click to see details.",
                )
            else:
                self.chan_select_btn.setToolTip("Select specific channels to keep")

            smart_parse_capability = get_command_capability(
                self,
                CommandName.APPLY_SMART_PARSE,
            )
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
            elif smart_parse_capability is None and self.controller.is_locked():
                self.smart_parse_btn.setToolTip(
                    "Dataset is locked. Click to see details.",
                )
            else:
                self.smart_parse_btn.setToolTip(
                    "Auto-extract Subject/Session from filenames",
                )

            import_label_capability = get_command_capability(
                self,
                CommandName.IMPORT_LABELS,
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
            elif import_label_capability is None and self.controller.is_locked():
                self.import_label_btn.setEnabled(False)
                self.import_label_btn.setToolTip(
                    "Dataset is locked. Reset before changing labels.",
                )
            elif import_label_capability is None and not bool(
                self.controller.has_data()
            ):
                self.import_label_btn.setEnabled(False)
                self.import_label_btn.setToolTip(
                    "Interpret a data source before adding labels.",
                )
            else:
                self.import_label_btn.setEnabled(True)
                self.import_label_btn.setToolTip(
                    "Add labels to loaded data and update the current recipe trace.",
                )

    # --- Actions moved from Panel ---

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

        if preprocess_capability is None and not self.controller.has_data():
            QMessageBox.warning(self, "Warning", "No data loaded.")
            return

        if preprocess_capability is None and self.controller.is_locked():
            QMessageBox.warning(
                self,
                "Action Blocked",
                "Dataset is locked because Channel Selection (or other operations) has "
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
                        run_legacy_controller_fallback(
                            self,
                            lambda: self.controller.apply_channel_selection(result),
                        )
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
                try:
                    return run_legacy_controller_fallback(
                        self,
                        self.controller.get_loaded_data_list,
                    )
                except LegacyControllerFallbackUnavailableError:
                    QMessageBox.warning(
                        self,
                        "Channel Selection Blocked",
                        LEGACY_FALLBACK_UNAVAILABLE_MESSAGE,
                    )
                    return None
            return []
        if result.failed:
            return []
        data_list = result.diagnostics.get("loaded_data_list")
        return list(data_list) if isinstance(data_list, list) else []

    def clear_dataset(self):
        """Prompt the user and clear the entire loaded dataset."""
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
                try:
                    run_legacy_controller_fallback(
                        self,
                        self.controller.clean_dataset,
                    )
                except LegacyControllerFallbackUnavailableError as exc:
                    QMessageBox.warning(self, "Clear Dataset Blocked", str(exc))
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
