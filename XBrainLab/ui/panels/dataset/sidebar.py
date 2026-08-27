"""Sidebar widget for the dataset panel: info and primary dataset actions."""

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QEvent, Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application.commands import (
    ApplyMontageCommand,
    CommandName,
    PreprocessCommand,
    PreprocessOperation,
    QueryStateCommand,
)
from XBrainLab.backend.application.preprocess_preparation import (
    ApplicationPreprocessBoundary,
)
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.application_capabilities import (
    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
    ControllerCompatibilityUnavailableError,
    blocked_reason,
    execute_application_command,
    get_application_view_publication,
    get_command_capability,
    has_real_application_context,
    is_application_runtime_deferred,
    is_stale_publication_result,
    run_controller_compatibility_call,
)
from XBrainLab.ui.components.info_panel import AggregateInfoPanel, SidebarScrollArea
from XBrainLab.ui.components.modal_presentation import (
    show_error,
    show_warning,
)
from XBrainLab.ui.components.user_error_presentation import (
    UnexpectedErrorContext,
    present_unexpected_error,
)
from XBrainLab.ui.interaction_outcome import InteractionOutcome
from XBrainLab.ui.montage_positions import normalize_montage_positions
from XBrainLab.ui.status import show_status_message
from XBrainLab.ui.styles.stylesheets import Stylesheets

ChannelSelectionDialog: Any | None = None
_SIDEBAR_WIDTH = 260
_ACTION_TEXT_HORIZONTAL_PADDING = 26
_DATASET_SIDEBAR_BUTTON_STYLE = f"""
    {Stylesheets.SIDEBAR_BTN}
    QPushButton {{
        padding-left: {_ACTION_TEXT_HORIZONTAL_PADDING // 2}px;
        padding-right: {_ACTION_TEXT_HORIZONTAL_PADDING // 2}px;
    }}
"""
_DATA_INTERPRETATION_AVAILABILITY_UNAVAILABLE = (
    "Data interpretation availability is unavailable right now."
)
_RECIPE_RELOAD_AVAILABILITY_UNAVAILABLE = (
    "Recipe reload availability is unavailable right now."
)
_CHANNEL_SELECTION_AVAILABILITY_UNAVAILABLE = (
    "Channel selection availability is unavailable right now."
)
_CHANNELS_CHANGED_MESSAGE = (
    "Nothing was applied. Review the latest channels and try again."
)
_DATASET_CHANGED_MESSAGE = (
    "Nothing was applied. Review the latest dataset and try again."
)
_SMART_PARSE_AVAILABILITY_UNAVAILABLE = (
    "Smart parse availability is unavailable right now."
)
_LABEL_IMPORT_AVAILABILITY_UNAVAILABLE = (
    "Label import availability is unavailable right now."
)


def _electrode_layout_dialog_class():
    from XBrainLab.ui.dialogs.visualization.montage_picker_dialog import (  # noqa: PLC0415
        PickMontageDialog,
    )

    return PickMontageDialog


def _channel_selection_dialog_class():
    patched = globals()["ChannelSelectionDialog"]
    if patched is not None:
        return patched
    from XBrainLab.ui.dialogs.dataset.channel_selection_dialog import (  # noqa: PLC0415
        ChannelSelectionDialog,
    )

    return ChannelSelectionDialog


def _channel_selection_raw_identity(
    state: ApplicationStateSnapshot,
) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    raw = state.raw
    return raw.count, tuple(raw.files), tuple(raw.channels)


class DatasetSidebar(QWidget):
    """Sidebar for ``DatasetPanel`` containing information and action controls.

    Hosts an aggregate info panel, primary import buttons, and channel selection.
    Metadata parsing and external labels live in
    the Data Import wizard; the old post-load label button is retained only as
    hidden compatibility wiring for tests and compatibility adapters.

    Attributes:
        panel: The parent ``DatasetPanel`` reference.
        info_panel: ``AggregateInfoPanel`` displaying summary statistics.
        import_btn: Button to import EEG data files.
        reload_recipe_btn: Button to reload a saved import recipe.
        import_label_btn: Hidden compatibility button for old label attachment.
        smart_parse_btn: Hidden compatibility button to auto-extract metadata.
        chan_select_btn: Button to open channel selection dialog.

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

        self.import_btn = QPushButton("Import Data")
        self.import_btn.setToolTip(
            "Choose EEG files or a folder, review metadata and labels, then import"
        )
        self.import_btn.setStyleSheet(_DATASET_SIDEBAR_BUTTON_STYLE)
        self.import_btn.clicked.connect(self.panel.action_handler.import_data)
        self.ops_layout.addWidget(self.import_btn, 0, 0)

        self.reload_recipe_btn = QPushButton("Reload recipe")
        self.reload_recipe_btn.setToolTip(
            "Review a saved import recipe before applying it",
        )
        self.reload_recipe_btn.setStyleSheet(_DATASET_SIDEBAR_BUTTON_STYLE)
        self.reload_recipe_btn.clicked.connect(
            self.panel.action_handler.reload_interpretation_recipe,
        )
        self.ops_layout.addWidget(self.reload_recipe_btn, 1, 0)

        self.import_cancel_btn = QPushButton("Cancel Import")
        self.import_cancel_btn.setObjectName("OwnedOperationCancelButton")
        self.import_cancel_btn.setToolTip("Cancel the active import safely")
        self.import_cancel_btn.setStyleSheet(Stylesheets.BTN_WARNING)
        self.import_cancel_btn.setVisible(False)
        self.import_cancel_btn.setEnabled(False)
        self.ops_layout.addWidget(self.import_cancel_btn, 2, 0)

        self.smart_parse_btn = QPushButton("Smart Parse Metadata", self.ops_group)
        self.smart_parse_btn.setToolTip("Auto-extract Subject/Session from filenames")
        self.smart_parse_btn.setStyleSheet(_DATASET_SIDEBAR_BUTTON_STYLE)
        self.smart_parse_btn.clicked.connect(
            self.panel.action_handler.open_smart_parser,
        )
        self.smart_parse_btn.setVisible(False)

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
        self.import_label_btn.setStyleSheet(_DATASET_SIDEBAR_BUTTON_STYLE)
        self.import_label_btn.clicked.connect(self.panel.action_handler.import_label)
        self.import_label_btn.setVisible(False)
        self.exec_layout.addWidget(self.import_label_btn)

        self.chan_select_btn = QPushButton("Channels")
        self.chan_select_btn.setToolTip("Select specific channels to keep")
        self.chan_select_btn.setStyleSheet(_DATASET_SIDEBAR_BUTTON_STYLE)
        self.chan_select_btn.clicked.connect(self.open_channel_selection)
        self.exec_layout.addWidget(self.chan_select_btn)

        self.electrode_layout_btn = QPushButton("Electrode Layout")
        self.electrode_layout_btn.setToolTip(
            "Map existing EEG channels to reviewed electrode positions",
        )
        self._last_layout_status: tuple[str, str | None, int, int] | None = None
        self.electrode_layout_btn.setStyleSheet(_DATASET_SIDEBAR_BUTTON_STYLE)
        self.electrode_layout_btn.clicked.connect(self.open_electrode_layout)
        self.exec_layout.addWidget(self.electrode_layout_btn)
        self.electrode_layout_status = QLabel("No electrode layout")
        self.electrode_layout_status.setObjectName("ElectrodeLayoutStatus")
        self.electrode_layout_status.setWordWrap(True)
        self.electrode_layout_status.setProperty("role", "secondary-status")
        self.exec_layout.addWidget(self.electrode_layout_status)

        layout.addWidget(exec_group)

        layout.addStretch()
        self._action_buttons = (
            self.import_btn,
            self.reload_recipe_btn,
            self.import_cancel_btn,
            self.smart_parse_btn,
            self.import_label_btn,
            self.chan_select_btn,
            self.electrode_layout_btn,
        )
        for button in self._action_buttons:
            full_label = button.text()
            button.setProperty("datasetFullLabel", full_label)
            button.setAccessibleName(full_label)
        self._apply_startup_bootstrap_state()
        self._fit_action_labels()

    def open_electrode_layout(
        self,
        _checked: bool = False,
        *,
        default_montage: str | None = None,
        warning: str = "",
    ) -> InteractionOutcome:
        """Open the one Dataset-owned layout review surface."""
        capability = get_command_capability(self, CommandName.APPLY_MONTAGE)
        query = execute_application_command(
            self, QueryStateCommand(query="state"), refresh=False
        )
        if query is None or query.failed:
            message = (
                query.message
                if query is not None
                else CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
            )
            show_warning(self, "Electrode Layout blocked", message)
            return InteractionOutcome.blocked(message)
        state = (getattr(query, "diagnostics", {}) or {}).get("state", {})
        layout = state.get("electrode_layout", {}) if isinstance(state, dict) else {}
        epoch = state.get("epoch", {}) if isinstance(state, dict) else {}
        raw = state.get("raw", {}) if isinstance(state, dict) else {}
        channels = epoch.get("channel_names") or raw.get("channels") or []
        if not isinstance(channels, list) or not channels:
            message = "No EEG channel names are available for electrode layout."
            show_warning(self, "Electrode Layout blocked", message)
            return InteractionOutcome.blocked(message)
        if warning:
            self._show_status(" ".join(str(warning).split()))
        dialog_type = _electrode_layout_dialog_class()
        kwargs = {"default_montage": default_montage} if default_montage else {}
        active_training = (
            state.get("active_training", {}) if isinstance(state, dict) else {}
        )
        interpretation = (
            state.get("interpretation", {}) if isinstance(state, dict) else {}
        )
        dialog = dialog_type(
            self,
            channels,
            current_layout=layout,
            is_bids_source=interpretation.get("source_kind") == "bids",
            layout_changes_allowed=(
                capability.enabled
                if capability is not None
                else not bool(active_training.get("has_trainer"))
            ),
            **kwargs,
        )
        if not dialog.exec():
            return InteractionOutcome.cancelled("Electrode layout was cancelled.")
        restore_bids_requested = getattr(dialog, "restore_bids_requested", None)
        if callable(restore_bids_requested) and restore_bids_requested() is True:
            result = execute_application_command(
                self,
                ApplyMontageCommand(restore_bids=True),
            )
            if result is None or result.failed:
                message = (
                    result.message
                    if result is not None
                    else CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
                )
                show_warning(self, "Electrode Layout blocked", message)
                return InteractionOutcome.blocked(message)
            self._show_status("BIDS electrode layout restored")
            return InteractionOutcome.completed("BIDS electrode layout restored.")
        selected_channels, positions = dialog.get_result()
        if not selected_channels or not positions:
            return InteractionOutcome.blocked("No electrode layout was selected.")
        try:
            normalized = normalize_montage_positions(selected_channels, positions)
        except Exception:
            present_unexpected_error(self, UnexpectedErrorContext.MONTAGE_SETUP)
            return InteractionOutcome.failed("Electrode layout could not be applied.")
        montage_combo = getattr(dialog, "montage_combo", None)
        montage_name = (
            montage_combo.currentText()
            if isinstance(montage_combo, QComboBox) and montage_combo is not None
            else None
        )
        result = execute_application_command(
            self,
            ApplyMontageCommand(
                channels=list(selected_channels),
                positions=normalized,
                montage_name=montage_name,
                electrode_names=dialog.get_electrode_names(),
            ),
        )
        if result is None or result.failed:
            message = (
                result.message
                if result is not None
                else CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
            )
            show_warning(self, "Electrode Layout blocked", message)
            return InteractionOutcome.blocked(message)
        self._show_status("Electrode layout applied")
        return InteractionOutcome.completed("Electrode layout applied.")

    def resizeEvent(self, event) -> None:  # noqa: N802
        """Refit action labels after the fixed sidebar viewport settles."""
        super().resizeEvent(event)
        self._fit_action_labels()
        QTimer.singleShot(0, self._fit_action_labels)

    def showEvent(self, event) -> None:  # noqa: N802
        """Apply native style metrics after first polish."""
        super().showEvent(event)
        self._fit_action_labels()

    def changeEvent(self, event: QEvent | None) -> None:  # noqa: N802
        """Refit labels when the application font or native style changes."""
        super().changeEvent(event)
        if (
            event is not None
            and event.type()
            in {
                QEvent.Type.FontChange,
                QEvent.Type.ApplicationFontChange,
                QEvent.Type.StyleChange,
            }
            and hasattr(self, "_action_buttons")
        ):
            self._fit_action_labels()
            QTimer.singleShot(0, self._fit_action_labels)

    def _fit_action_labels(self) -> None:
        """Elide labels inside the fixed product width and retain full tooltips."""
        for button in getattr(self, "_action_buttons", ()):
            if button.isHidden():
                continue
            full_label = button.property("datasetFullLabel")
            if not isinstance(full_label, str) or not full_label:
                continue
            metrics = button.fontMetrics()
            text_width = max(
                button.contentsRect().width() - _ACTION_TEXT_HORIZONTAL_PADDING,
                1,
            )
            rendered = metrics.elidedText(
                full_label,
                Qt.TextElideMode.ElideRight,
                text_width,
            )
            while 1 < text_width < metrics.horizontalAdvance(rendered):
                overflow = metrics.horizontalAdvance(rendered) - text_width
                text_width = max(text_width - overflow - 1, 1)
                rendered = metrics.elidedText(
                    full_label,
                    Qt.TextElideMode.ElideRight,
                    text_width,
                )
            button.setText(rendered)

            tooltip_prefix = f"{full_label}\n\n"
            tooltip = button.toolTip()
            if tooltip.startswith(tooltip_prefix):
                tooltip = tooltip[len(tooltip_prefix) :]
            button.setToolTip(
                tooltip_prefix + tooltip if rendered != full_label else tooltip
            )

    def _apply_startup_bootstrap_state(self) -> None:
        """Present the known empty-workspace actions before command runtime startup."""
        if has_real_application_context(self):
            unavailable_actions = {
                self.import_btn: _DATA_INTERPRETATION_AVAILABILITY_UNAVAILABLE,
                self.reload_recipe_btn: _RECIPE_RELOAD_AVAILABILITY_UNAVAILABLE,
                self.smart_parse_btn: _SMART_PARSE_AVAILABILITY_UNAVAILABLE,
                self.import_label_btn: _LABEL_IMPORT_AVAILABILITY_UNAVAILABLE,
                self.chan_select_btn: _CHANNEL_SELECTION_AVAILABILITY_UNAVAILABLE,
            }
            for button, tooltip in unavailable_actions.items():
                button.setEnabled(False)
                button.setToolTip(tooltip)
            return

        for button in (
            self.import_btn,
            self.reload_recipe_btn,
        ):
            button.setEnabled(True)
        self.chan_select_btn.setEnabled(False)
        self.chan_select_btn.setToolTip("Import EEG data before selecting channels.")

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
                show_warning(self, blocked_title, str(exc))
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
        if self.controller is not None or has_real_application_context(self):
            if self._uses_startup_bootstrap_state():
                self._apply_startup_bootstrap_state()
                self._fit_action_labels()
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
            layout_capability = (
                capabilities.get(CommandName.APPLY_MONTAGE)
                if capabilities is not None
                else None
            )
            product_context = has_real_application_context(self)
            compatibility_state_available = not product_context
            compatibility_is_locked = False
            compatibility_has_data = False
            if not product_context and any(
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
                source_tooltip = (
                    "Choose EEG files or a folder, review metadata and labels, "
                    "then import"
                    if scan_capability.enabled
                    else blocked_reason(
                        scan_capability,
                        "Data interpretation is not available right now.",
                    )
                )
                self.import_btn.setToolTip(source_tooltip)
            elif not compatibility_state_available:
                self.import_btn.setEnabled(False)
                self.import_btn.setToolTip(
                    _DATA_INTERPRETATION_AVAILABILITY_UNAVAILABLE,
                )
            elif compatibility_is_locked:
                self.import_btn.setEnabled(True)
                self.import_btn.setToolTip(
                    "Dataset is locked. Reset before interpreting a new source.",
                )
            else:
                self.import_btn.setEnabled(True)
                self.import_btn.setToolTip(
                    "Choose EEG files or a folder, review metadata and labels, "
                    "then import",
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
                    _RECIPE_RELOAD_AVAILABILITY_UNAVAILABLE,
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
                    _CHANNEL_SELECTION_AVAILABILITY_UNAVAILABLE,
                )
            elif compatibility_is_locked:
                self.chan_select_btn.setEnabled(True)
                self.chan_select_btn.setToolTip(
                    "Dataset is locked. Click to see details.",
                )
            else:
                self.chan_select_btn.setEnabled(True)
                self.chan_select_btn.setToolTip("Select specific channels to keep")

            if layout_capability is not None:
                state_snapshot = getattr(publication, "state", None)
                layout_channels = (
                    list(
                        getattr(
                            getattr(state_snapshot, "epoch", None),
                            "channel_names",
                            (),
                        )
                        or ()
                    )
                    + list(
                        getattr(
                            getattr(state_snapshot, "raw", None),
                            "channels",
                            (),
                        )
                        or ()
                    )
                    if publication is not None
                    else []
                )
                self.electrode_layout_btn.setEnabled(
                    layout_capability.enabled or bool(layout_channels)
                )
                self.electrode_layout_btn.setToolTip(
                    "Map existing EEG channels to reviewed electrode positions"
                    if layout_capability.enabled
                    else blocked_reason(
                        layout_capability,
                        "Load EEG data before configuring electrode layout.",
                    )
                )
            elif not compatibility_state_available:
                self.electrode_layout_btn.setEnabled(False)
            else:
                self.electrode_layout_btn.setEnabled(compatibility_has_data)

            if publication is not None:
                layout = publication.state.electrode_layout
                current_layout = (
                    layout.status,
                    layout.source,
                    layout.positioned_channel_count,
                    layout.channel_count,
                )
                self.electrode_layout_btn.setToolTip(
                    f"Electrode layout: {layout.status}"
                    + (f" ({layout.source})" if layout.source else "")
                    + f" — {layout.positioned_channel_count}/"
                    f"{layout.channel_count} EEG channels positioned"
                )
                self.electrode_layout_status.setText(
                    self._electrode_layout_status_text(layout),
                )
                if current_layout != self._last_layout_status:
                    self._last_layout_status = current_layout
                    if layout.source == "bids" and layout.status in {
                        "ready",
                        "limited",
                        "failed",
                    }:
                        source = (
                            f" from {layout.source.upper()}" if layout.source else ""
                        )
                        self._show_status(
                            f"Electrode layout {layout.status}{source} — "
                            f"{layout.positioned_channel_count}/"
                            f"{layout.channel_count} EEG channels positioned."
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
            elif not compatibility_state_available:
                self.smart_parse_btn.setEnabled(False)
                self.smart_parse_btn.setToolTip(
                    _SMART_PARSE_AVAILABILITY_UNAVAILABLE,
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
                    _LABEL_IMPORT_AVAILABILITY_UNAVAILABLE,
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

            self._fit_action_labels()

    @staticmethod
    def _electrode_layout_status_text(layout: Any) -> str:
        """Project the published layout state into a compact sidebar status."""
        status = str(getattr(layout, "status", "not_configured"))
        source = str(getattr(layout, "source", "") or "").lower()
        positioned = int(getattr(layout, "positioned_channel_count", 0) or 0)
        channel_count = int(getattr(layout, "channel_count", 0) or 0)
        if status in {"pending", "preparing"}:
            return "Preparing BIDS layout…"
        if status == "failed":
            return "BIDS layout unavailable"
        if not source:
            return "No electrode layout"
        source_label = "BIDS" if source == "bids" else "Manual"
        return f"{source_label} layout · {positioned}/{channel_count} positioned"

    # --- Actions moved from Panel ---

    def _compatibility_loaded_data_list_for_channel_selection(self) -> list[str] | None:
        available, data_list = self._compatibility_controller_value(
            self.controller.get_loaded_data_list,
            blocked_title="Channel Selection Blocked",
        )
        if not available:
            return None
        values = list(data_list or [])
        if not values:
            return []
        try:
            return [str(channel) for channel in values[0].get_mne().ch_names]
        except Exception:
            logger.debug(
                "Compatibility channel-name projection failed",
                exc_info=True,
            )
            return []

    def open_channel_selection(self) -> InteractionOutcome:
        """Open the channel selection dialog.

        Blocked if the dataset is locked or no data is loaded.
        The dialog's OK action is the single confirmation before applying.
        """
        if self.controller is None and not has_real_application_context(self):
            return InteractionOutcome.failed(
                "Channel Selection is unavailable in this session."
            )

        publication = get_application_view_publication(self)
        if publication is None and has_real_application_context(self):
            show_warning(
                self,
                "Channel Selection Blocked",
                _CHANNEL_SELECTION_AVAILABILITY_UNAVAILABLE,
            )
            return InteractionOutcome.blocked(
                _CHANNEL_SELECTION_AVAILABILITY_UNAVAILABLE
            )
        preprocess_capability = (
            publication.effective_capabilities.get(CommandName.PREPROCESS)
            if publication is not None
            else get_command_capability(self, CommandName.PREPROCESS)
        )
        if preprocess_capability is not None and not preprocess_capability.enabled:
            show_warning(
                self,
                "Channel Selection Blocked",
                blocked_reason(
                    preprocess_capability,
                    "Load raw data before selecting channels.",
                ),
            )
            return InteractionOutcome.blocked(
                blocked_reason(
                    preprocess_capability,
                    "Load raw data before selecting channels.",
                )
            )

        if preprocess_capability is None:
            if has_real_application_context(self):
                show_warning(
                    self,
                    "Channel Selection Blocked",
                    _CHANNEL_SELECTION_AVAILABILITY_UNAVAILABLE,
                )
                return InteractionOutcome.blocked(
                    _CHANNEL_SELECTION_AVAILABILITY_UNAVAILABLE
                )
            available, has_data = self._compatibility_controller_value(
                lambda: bool(self.controller.has_data()),
                blocked_title="Channel Selection Blocked",
            )
            if not available:
                return InteractionOutcome.failed(
                    "Channel Selection is unavailable in this session."
                )
            if not has_data:
                show_warning(self, "Warning", "No data loaded.")
                return InteractionOutcome.blocked(
                    "Load raw data before selecting channels."
                )

            available, is_locked = self._compatibility_controller_value(
                lambda: bool(self.controller.is_locked()),
                blocked_title="Channel Selection Blocked",
            )
            if not available:
                return InteractionOutcome.failed(
                    "Channel Selection is unavailable in this session."
                )
            if is_locked:
                show_warning(
                    self,
                    "Action Blocked",
                    "Dataset is locked because a data operation has "
                    "been applied.\n"
                    "Use 'Reset All Preprocessing' before changing channels.",
                )
                return InteractionOutcome.blocked(
                    "Reset preprocessing before changing channels."
                )

        channels = (
            [str(channel) for channel in publication.state.raw.channels]
            if publication is not None
            else self._compatibility_loaded_data_list_for_channel_selection()
        )
        if channels is None:
            return InteractionOutcome.failed(
                "Channel Selection could not read the current channels."
            )
        dialog_class = _channel_selection_dialog_class()
        dialog = dialog_class(self, channels)
        reviewed_boundary = (
            ApplicationPreprocessBoundary(
                publication_generation=publication.generation,
                publication_revision=publication.revision,
                state=publication.state,
            )
            if publication is not None
            else None
        )
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
                        reviewed_preprocess_boundary=reviewed_boundary,
                    )
                    if command_result is None:
                        show_warning(
                            self,
                            "Channel Selection Blocked",
                            CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                        )
                        return InteractionOutcome.failed(
                            CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE
                        )
                    elif is_stale_publication_result(command_result) or (
                        isinstance(command_result.diagnostics, dict)
                        and command_result.diagnostics.get(
                            "stale_prepared_preprocess",
                        )
                        is True
                    ):
                        raw_identity_changed = (
                            reviewed_boundary is not None
                            and isinstance(
                                command_result.state,
                                ApplicationStateSnapshot,
                            )
                            and _channel_selection_raw_identity(
                                reviewed_boundary.state,
                            )
                            != _channel_selection_raw_identity(command_result.state)
                        )
                        show_warning(
                            self,
                            (
                                "Channels Changed"
                                if raw_identity_changed
                                else "Dataset Changed"
                            ),
                            (
                                _CHANNELS_CHANGED_MESSAGE
                                if raw_identity_changed
                                else _DATASET_CHANGED_MESSAGE
                            ),
                        )
                        return InteractionOutcome.blocked(
                            _CHANNELS_CHANGED_MESSAGE
                            if raw_identity_changed
                            else _DATASET_CHANGED_MESSAGE
                        )
                    elif command_result.failed:
                        show_error(
                            self,
                            "Error",
                            f"Channel selection failed: {command_result.message}",
                        )
                        return InteractionOutcome.failed(command_result.message)
                    self._show_status("Channel selection applied")
                    return InteractionOutcome.completed("Channel selection applied.")
                except Exception:
                    present_unexpected_error(
                        self,
                        UnexpectedErrorContext.DATASET_CHANNEL_SELECTION,
                    )
                    return InteractionOutcome.failed(
                        "Channel selection could not be applied."
                    )
            return InteractionOutcome.cancelled("Channel Selection was cancelled.")
        return InteractionOutcome.cancelled("Channel Selection was cancelled.")
