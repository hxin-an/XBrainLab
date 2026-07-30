"""Sidebar widget for the dataset panel: info and primary dataset actions."""

from collections.abc import Callable
from typing import Any, Protocol, cast

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application.commands import (
    CommandName,
    PreprocessCommand,
    PreprocessOperation,
    QueryStateCommand,
    ResetSessionCommand,
)
from XBrainLab.ui.application_capabilities import (
    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
    ControllerCompatibilityUnavailableError,
    blocked_reason,
    execute_application_command,
    get_application_view_publication,
    get_command_capability,
    is_application_runtime_deferred,
    is_stale_publication_result,
    local_result_payload,
    run_controller_compatibility_call,
)
from XBrainLab.ui.components.info_panel import AggregateInfoPanel, SidebarScrollArea
from XBrainLab.ui.status import show_status_message
from XBrainLab.ui.styles.stylesheets import Stylesheets

ChannelSelectionDialog: Any | None = None
_SIDEBAR_WIDTH = 260
_COMPACT_VERTICAL_MARGIN = 8
_DEFAULT_VERTICAL_MARGIN = 20
_QWIDGETSIZE_MAX = 16777215


class _EpochStatePort(Protocol):
    """Compatibility controller contract for reading epoch availability."""

    def is_epoched(self) -> bool: ...


def _channel_selection_dialog_class():
    patched = globals()["ChannelSelectionDialog"]
    if patched is not None:
        return patched
    from XBrainLab.ui.dialogs.dataset.channel_selection_dialog import (  # noqa: PLC0415
        ChannelSelectionDialog,
    )

    return ChannelSelectionDialog


class DatasetSidebar(QWidget):
    """Sidebar for ``DatasetPanel`` containing information and action controls.

    Hosts an aggregate info panel, primary import buttons, channel selection,
    and a reset-session button. Metadata parsing and external labels live in
    the Data Import wizard; the old post-load label button is retained only as
    hidden compatibility wiring for tests and compatibility adapters.

    Attributes:
        panel: The parent ``DatasetPanel`` reference.
        info_panel: ``AggregateInfoPanel`` displaying summary statistics.
        import_btn: Button to import EEG data files.
        import_folder_btn: Button to import a folder.
        import_bids_btn: Button to import a BIDS EEG folder.
        reload_recipe_btn: Button to reload a saved import recipe.
        import_label_btn: Hidden compatibility button for old label attachment.
        smart_parse_btn: Hidden compatibility button to auto-extract metadata.
        chan_select_btn: Button to open channel selection dialog.
        clear_btn: Destructive button that resets the active EEG session.

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

    def _update_panel_after_command_result(self, result) -> None:
        if result is None:
            self.panel.update_panel()

    def _show_status(self, message: str) -> None:
        show_status_message(self.panel, message)

    def init_ui(self):
        """Build sidebar layout: info panel, operation and execution buttons."""
        self.setFixedWidth(_SIDEBAR_WIDTH)
        self.setObjectName("RightPanel")
        self.setStyleSheet(Stylesheets.SIDEBAR_CONTAINER)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.scroll_area = SidebarScrollArea(self)
        root_layout.addWidget(self.scroll_area)
        layout = self.scroll_area.content_layout

        # 1. Aggregate Info
        self.info_panel = AggregateInfoPanel(self.main_window)
        self.info_panel.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        layout.addWidget(self.info_panel)

        # Separator
        self.info_separator_before = QSpacerItem(
            0,
            10,
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Fixed,
        )
        layout.addItem(self.info_separator_before)
        self.info_separator_line = QFrame()
        self.info_separator_line.setFrameShape(QFrame.Shape.HLine)
        self.info_separator_line.setFrameShadow(QFrame.Shadow.Sunken)
        self.info_separator_line.setStyleSheet(Stylesheets.SEPARATOR_HORIZONTAL)
        self.info_separator_line.setFixedHeight(1)
        layout.addWidget(self.info_separator_line)
        self.info_separator_after = QSpacerItem(
            0,
            10,
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Fixed,
        )
        layout.addItem(self.info_separator_after)

        # 2. Import Group
        self.ops_group = QGroupBox("IMPORT")
        self.ops_group.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        self.ops_group.setMinimumHeight(Stylesheets.SIDEBAR_PRIMARY_GROUP_MIN_HEIGHT)
        self.ops_layout = QGridLayout(self.ops_group)
        self.ops_layout.setContentsMargins(0, 10, 0, 0)
        self.ops_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.import_btn = QPushButton("Import file")
        self.import_btn.setToolTip(
            "Choose EEG files, review metadata and labels, then import"
        )
        self.import_btn.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.import_btn.clicked.connect(self.panel.action_handler.import_data)
        self.ops_layout.addWidget(self.import_btn, 0, 0)

        self.import_folder_btn = QPushButton("Import folder")
        self.import_folder_btn.setToolTip(
            "Choose an EEG folder, review metadata and labels, then import",
        )
        self.import_folder_btn.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.import_folder_btn.clicked.connect(
            self.panel.action_handler.import_folder_source,
        )
        self.ops_layout.addWidget(self.import_folder_btn, 1, 0)

        self.import_bids_btn = QPushButton("Import BIDS folder")
        self.import_bids_btn.setToolTip(
            "Choose a BIDS EEG folder and review detected metadata and events",
        )
        self.import_bids_btn.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.import_bids_btn.clicked.connect(
            self.panel.action_handler.import_bids_source,
        )
        self.ops_layout.addWidget(self.import_bids_btn, 2, 0)

        self.reload_recipe_btn = QPushButton("Reload Import Recipe")
        self.reload_recipe_btn.setToolTip(
            "Review a saved import recipe before applying it",
        )
        self.reload_recipe_btn.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.reload_recipe_btn.clicked.connect(
            self.panel.action_handler.reload_interpretation_recipe,
        )
        self.ops_layout.addWidget(self.reload_recipe_btn, 3, 0)

        self.smart_parse_btn = QPushButton("Smart Parse Metadata", self.ops_group)
        self.smart_parse_btn.setToolTip("Auto-extract Subject/Session from filenames")
        self.smart_parse_btn.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.smart_parse_btn.clicked.connect(
            self.panel.action_handler.open_smart_parser,
        )
        self.smart_parse_btn.setVisible(False)

        self._import_buttons = (
            self.import_btn,
            self.import_folder_btn,
            self.import_bids_btn,
            self.reload_recipe_btn,
        )
        layout.addWidget(self.ops_group)
        layout.addSpacing(Stylesheets.SIDEBAR_GROUP_GAP)

        # 3. Dataset Group
        exec_group = QGroupBox("DATASET")
        exec_group.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        self.exec_layout = QVBoxLayout(exec_group)
        self.exec_layout.setContentsMargins(0, 10, 0, 0)
        self.exec_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.import_label_btn = QPushButton("Add labels")
        self.import_label_btn.setToolTip("Attach labels to the loaded EEG data")
        self.import_label_btn.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.import_label_btn.clicked.connect(self.panel.action_handler.import_label)
        self.import_label_btn.setVisible(False)
        self.exec_layout.addWidget(self.import_label_btn)

        self.chan_select_btn = QPushButton("Channel Selection")
        self.chan_select_btn.setToolTip("Select specific channels to keep")
        self.chan_select_btn.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.chan_select_btn.clicked.connect(self.open_channel_selection)
        self.exec_layout.addWidget(self.chan_select_btn)

        self.clear_btn = QPushButton("Reset Session")
        self.clear_btn.setStyleSheet(Stylesheets.BTN_DANGER)
        self.clear_btn.setToolTip("No active session to reset.")
        self.clear_btn.clicked.connect(self.clear_dataset)
        self.exec_layout.addWidget(self.clear_btn)

        layout.addWidget(exec_group)

        layout.addStretch()
        self._apply_startup_bootstrap_state()

    def set_compact_mode(self, compact: bool) -> None:
        """Reflow actions when the Dataset panel is stacked below a dock."""
        if compact:
            self.setMinimumWidth(0)
            self.setMaximumWidth(_QWIDGETSIZE_MAX)
            self.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            self.scroll_area.content_layout.setContentsMargins(
                10,
                _COMPACT_VERTICAL_MARGIN,
                10,
                _COMPACT_VERTICAL_MARGIN,
            )
            self.ops_group.setMinimumHeight(0)
            import_columns = 2
            direction = QBoxLayout.Direction.LeftToRight
        else:
            self.setFixedWidth(_SIDEBAR_WIDTH)
            self.setSizePolicy(
                QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.Expanding,
            )
            self.scroll_area.content_layout.setContentsMargins(
                10,
                _DEFAULT_VERTICAL_MARGIN,
                10,
                _DEFAULT_VERTICAL_MARGIN,
            )
            self.ops_group.setMinimumHeight(
                Stylesheets.SIDEBAR_PRIMARY_GROUP_MIN_HEIGHT
            )
            import_columns = 1
            direction = QBoxLayout.Direction.TopToBottom
        available_wide_button_width = _SIDEBAR_WIDTH - 20
        use_short_copy = compact or (
            self.fontMetrics().horizontalAdvance("Reload Import Recipe") + 32
            > available_wide_button_width
        )
        self.import_bids_btn.setText(
            "Import BIDS" if use_short_copy else "Import BIDS folder"
        )
        self.reload_recipe_btn.setText(
            "Reload Recipe" if use_short_copy else "Reload Import Recipe"
        )
        self.chan_select_btn.setText(
            "Select Channels" if use_short_copy else "Channel Selection"
        )
        for button in self._import_buttons:
            self.ops_layout.removeWidget(button)
        for index, button in enumerate(self._import_buttons):
            self.ops_layout.addWidget(
                button,
                index // import_columns,
                index % import_columns,
            )
        for column in range(2):
            self.ops_layout.setColumnStretch(
                column,
                1 if column < import_columns else 0,
            )
        if self.exec_layout.direction() != direction:
            self.exec_layout.setDirection(direction)
        self.ops_layout.invalidate()
        self.exec_layout.invalidate()
        self.scroll_area.content_layout.invalidate()
        self.updateGeometry()

    def set_summary_visible(self, visible: bool) -> None:
        """Keep the summary separator tied to the summary it introduces."""
        self.info_panel.setVisible(visible)
        spacer_height = 10 if visible else 0
        self.info_separator_before.changeSize(
            0,
            spacer_height,
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Fixed,
        )
        self.info_separator_after.changeSize(
            0,
            spacer_height,
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Fixed,
        )
        self.info_separator_line.setVisible(visible)
        self.scroll_area.content_layout.invalidate()
        self.updateGeometry()

    def _apply_startup_bootstrap_state(self) -> None:
        """Present the known empty-workspace actions before command runtime startup."""
        for button in (
            self.import_btn,
            self.import_folder_btn,
            self.import_bids_btn,
            self.reload_recipe_btn,
        ):
            button.setEnabled(True)
        self.chan_select_btn.setEnabled(False)
        self.chan_select_btn.setToolTip("Import EEG data before selecting channels.")
        self.clear_btn.setEnabled(False)
        self.clear_btn.setToolTip("No active session to reset.")

    def _uses_startup_bootstrap_state(self) -> bool:
        """Avoid constructing the full command spine for first-paint decoration."""
        return is_application_runtime_deferred(self)

    def _compatibility_controller_value(
        self,
        fallback: Callable[[], Any],
        *,
        blocked_title: str | None = None,
    ) -> tuple[bool, Any]:
        """Read controller compatibility state only for mock UI contexts."""
        try:
            return True, run_controller_compatibility_call(self, fallback)
        except ControllerCompatibilityUnavailableError as exc:
            if blocked_title is not None:
                QMessageBox.warning(self, blocked_title, str(exc))
            return False, None

    def _compatibility_sidebar_state(self) -> tuple[bool, bool, bool]:
        """Return compatibility state when no command capability is available."""
        available, is_locked = self._compatibility_controller_value(
            lambda: bool(self.controller.is_locked()),
        )
        if not available:
            return False, False, False
        available, has_data = self._compatibility_controller_value(
            lambda: bool(self.controller.has_data()),
        )
        if not available:
            return False, bool(is_locked), False
        return True, bool(is_locked), bool(has_data)

    def update_sidebar(self):
        """Update info panel and button states."""
        if self.controller:
            if self._uses_startup_bootstrap_state():
                self._apply_startup_bootstrap_state()
                return
            # Update Info Panel handled by Service

            # Update Button States (Tooltips only as per design)
            publication = get_application_view_publication(self)
            capabilities = (
                publication.effective_capabilities if publication is not None else None
            )
            scan_capability = (
                capabilities.get(CommandName.SCAN_SOURCE)
                if capabilities is not None
                else None
            )
            reload_capability = (
                capabilities.get(CommandName.RELOAD_INTERPRETATION_RECIPE)
                if capabilities is not None
                else None
            )
            preprocess_capability = (
                capabilities.get(CommandName.PREPROCESS)
                if capabilities is not None
                else None
            )
            smart_parse_capability = (
                capabilities.get(CommandName.APPLY_SMART_PARSE)
                if capabilities is not None
                else None
            )
            import_label_capability = (
                capabilities.get(CommandName.IMPORT_LABELS)
                if capabilities is not None
                else None
            )
            reset_capability = (
                capabilities.get(CommandName.RESET_SESSION)
                if capabilities is not None
                else None
            )
            compatibility_state_available = True
            compatibility_is_locked = False
            compatibility_has_data = False
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
                    compatibility_state_available,
                    compatibility_is_locked,
                    compatibility_has_data,
                ) = self._compatibility_sidebar_state()

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
            elif not compatibility_state_available:
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
            elif compatibility_is_locked:
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
            elif not compatibility_state_available:
                self.reload_recipe_btn.setEnabled(False)
                self.reload_recipe_btn.setToolTip(
                    "Recipe reload availability is unavailable right now.",
                )
            elif compatibility_is_locked:
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
            elif not compatibility_state_available:
                self.chan_select_btn.setEnabled(False)
                self.chan_select_btn.setToolTip(
                    "Channel selection availability is unavailable right now.",
                )
            elif compatibility_is_locked:
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
            elif not compatibility_state_available:
                self.smart_parse_btn.setEnabled(False)
                self.smart_parse_btn.setToolTip(
                    "Smart parse availability is unavailable right now.",
                )
            elif compatibility_is_locked:
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
            elif not compatibility_state_available:
                self.import_label_btn.setEnabled(False)
                self.import_label_btn.setToolTip(
                    "Label import availability is unavailable right now.",
                )
            elif compatibility_is_locked:
                self.import_label_btn.setEnabled(False)
                self.import_label_btn.setToolTip(
                    "Dataset is locked. Reset before changing labels.",
                )
            elif not compatibility_has_data:
                self.import_label_btn.setEnabled(False)
                self.import_label_btn.setToolTip(
                    "Interpret a data source before adding labels.",
                )
            else:
                self.import_label_btn.setEnabled(True)
                self.import_label_btn.setToolTip(
                    "Add labels to loaded data and update the current recipe trace.",
                )

            clear_enabled, clear_tooltip = (
                self._clear_dataset_availability_for_capability(reset_capability)
            )
            self.clear_btn.setEnabled(clear_enabled)
            self.clear_btn.setToolTip(clear_tooltip)

    # --- Actions moved from Panel ---

    def _clear_dataset_availability(self) -> tuple[bool, str]:
        reset_capability = get_command_capability(self, CommandName.RESET_SESSION)
        return self._clear_dataset_availability_for_capability(reset_capability)

    def _clear_dataset_availability_for_capability(
        self,
        reset_capability,
    ) -> tuple[bool, str]:
        if reset_capability is None:
            available, has_data = self._compatibility_controller_value(
                self._compatibility_has_clearable_data,
            )
            if not available:
                return False, "Dataset state is unavailable right now."
            return (
                bool(has_data),
                "Clear all loaded data and start over."
                if has_data
                else "No active session to reset.",
            )
        if not reset_capability.enabled:
            return False, blocked_reason(
                reset_capability,
                "Session cannot be reset right now.",
            )
        has_active_session = bool(
            reset_capability.confirmation_required
            or reset_capability.requires_confirmation
        )
        return (
            has_active_session,
            "Clear all loaded data and start over."
            if has_active_session
            else "No active session to reset.",
        )

    def _compatibility_has_clearable_data(self) -> bool:
        return self._compatibility_has_epoch_data()

    def _compatibility_has_epoch_data(self) -> bool:
        if self.controller is None:
            return False
        controller = cast(_EpochStatePort, self.controller)
        is_epoched = getattr(controller, "is_epoched", None)
        if callable(is_epoched):
            result = is_epoched()
            return result if isinstance(result, bool) else False
        return False

    def _compatibility_loaded_data_list_for_channel_selection(self) -> list[Any] | None:
        available, data_list = self._compatibility_controller_value(
            self.controller.get_loaded_data_list,
            blocked_title="Channel Selection Blocked",
        )
        if not available:
            return None
        return list(data_list or [])

    def open_channel_selection(self):
        """Open the channel selection dialog.

        Blocked if the dataset is locked or no data is loaded.
        Shows a confirmation prompt before applying.
        """
        if not self.controller:
            return

        publication = get_application_view_publication(self)
        preprocess_capability = (
            publication.effective_capabilities.get(CommandName.PREPROCESS)
            if publication is not None
            else get_command_capability(self, CommandName.PREPROCESS)
        )
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
            available, has_data = self._compatibility_controller_value(
                lambda: bool(self.controller.has_data()),
                blocked_title="Channel Selection Blocked",
            )
            if not available:
                return
            if not has_data:
                QMessageBox.warning(self, "Warning", "No data loaded.")
                return

            available, is_locked = self._compatibility_controller_value(
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
                    "'Reset Session' to start over.",
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

        data_list = self._loaded_data_list_for_channel_selection(
            preprocess_capability,
            expected_publication_generation=(
                publication.generation if publication is not None else None
            ),
        )
        if data_list is None:
            return
        dialog_class = _channel_selection_dialog_class()
        dialog = dialog_class(self, data_list)
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
                        expected_publication_generation=(
                            publication.generation if publication is not None else None
                        ),
                    )
                    if command_result is None:
                        QMessageBox.warning(
                            self,
                            "Channel Selection Blocked",
                            CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                        )
                        return
                    elif is_stale_publication_result(command_result):
                        QMessageBox.warning(
                            self,
                            "Review Channel Selection Again",
                            command_result.message,
                        )
                        return
                    elif command_result.failed:
                        QMessageBox.critical(
                            self,
                            "Error",
                            f"Channel selection failed: {command_result.message}",
                        )
                        return
                    self._update_panel_after_command_result(command_result)
                    self._show_status("Channel selection applied")
                except Exception as e:
                    QMessageBox.critical(
                        self,
                        "Error",
                        f"Channel selection failed: {e}",
                    )

    def _loaded_data_list_for_channel_selection(
        self,
        preprocess_capability,
        *,
        expected_publication_generation: int | None = None,
    ) -> list[Any] | None:
        command_kwargs: dict[str, Any] = {"refresh": False}
        if expected_publication_generation is not None:
            command_kwargs["expected_publication_generation"] = (
                expected_publication_generation
            )
        result = execute_application_command(
            self,
            QueryStateCommand(query="data_lists", include_objects=True),
            **command_kwargs,
        )
        if result is None:
            if preprocess_capability is None:
                return self._compatibility_loaded_data_list_for_channel_selection()
            return []
        if result.failed:
            return []
        data_list = local_result_payload(result).get("loaded_data_list")
        return list(data_list) if isinstance(data_list, list) else []

    def clear_dataset(self):
        """Prompt the user and reset the entire active EEG session."""
        publication = get_application_view_publication(self)
        reset_capability = (
            publication.effective_capabilities.get(CommandName.RESET_SESSION)
            if publication is not None
            else get_command_capability(self, CommandName.RESET_SESSION)
        )
        clear_enabled, clear_tooltip = self._clear_dataset_availability_for_capability(
            reset_capability
        )
        if not clear_enabled:
            self._show_status(clear_tooltip)
            return

        if reset_capability is not None and not reset_capability.enabled:
            QMessageBox.warning(
                self,
                "Reset Session Blocked",
                blocked_reason(
                    reset_capability,
                    "Session cannot be reset right now.",
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
                "Confirm Reset",
                "Clear all loaded data and start over?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            result = execute_application_command(
                self,
                ResetSessionCommand(confirmed=True),
                expected_publication_generation=(
                    publication.generation if publication is not None else None
                ),
            )
            if result is None:
                QMessageBox.warning(
                    self,
                    "Reset Session Blocked",
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                return
            elif is_stale_publication_result(result):
                QMessageBox.warning(
                    self,
                    "Review Reset Session Again",
                    result.message,
                )
                return
            elif result.failed:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to reset session: {result.message}",
                )
                return
            self._update_panel_after_command_result(result)
            self._show_status("Session reset")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to reset session: {e}")
