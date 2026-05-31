"""Sidebar widget for the visualization panel with configuration controls."""

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
    ApplyMontageCommand,
    CommandName,
    QueryStateCommand,
    SaliencyCommand,
    VisualizeCommand,
)
from XBrainLab.ui.application_capabilities import (
    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
    ControllerCompatibilityUnavailableError,
    blocked_reason,
    execute_application_command,
    execute_application_command_async,
    get_command_capability,
    run_controller_compatibility_call,
)
from XBrainLab.ui.components.info_panel import AggregateInfoPanel
from XBrainLab.ui.dialogs.visualization import (
    ExportSaliencyDialog,
    PickMontageDialog,
    SaliencySettingDialog,
)
from XBrainLab.ui.montage_positions import normalize_montage_positions
from XBrainLab.ui.status import show_status_message
from XBrainLab.ui.styles.stylesheets import Stylesheets


class ControlSidebar(QWidget):
    """Sidebar for Visualization Panel configuration.

    Saliency export is kept as a backend action but no longer shown as a
    first-layer operation until the saliency workflow has a complete round trip.
    """

    def __init__(self, panel, parent=None):
        """Initialize the control sidebar.

        Args:
            panel: The parent ``VisualizationPanel``.
            parent: Optional parent widget.

        """
        super().__init__(parent)
        self.panel = panel
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.init_ui()

    @property
    def controller(self):
        """VisualizationController: The controller from the parent panel."""
        return self.panel.controller

    @property
    def main_window(self):
        """QMainWindow: The application main window reference."""
        return self.panel.main_window

    def _show_status(self, message: str) -> None:
        show_status_message(self.panel, message)

    def init_ui(self):
        """Build the sidebar layout with info, configuration, and operation groups."""
        self.setFixedWidth(260)
        self.setObjectName("RightPanel")
        self.setStyleSheet(Stylesheets.SIDEBAR_CONTAINER)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 20, 10, 20)

        # 1. Aggregate Information
        self.info_panel = AggregateInfoPanel(self.main_window)
        self.info_panel.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        layout.addWidget(self.info_panel)

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
        config_group.setMinimumHeight(Stylesheets.SIDEBAR_PRIMARY_GROUP_MIN_HEIGHT)
        config_layout = QVBoxLayout(config_group)
        config_layout.setContentsMargins(0, 10, 0, 0)
        config_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.btn_montage = QPushButton("Set Montage")
        self.btn_montage.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.btn_montage.clicked.connect(self.set_montage)
        config_layout.addWidget(self.btn_montage)

        self.btn_saliency = QPushButton("Saliency Settings")
        self.btn_saliency.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.btn_saliency.clicked.connect(self.set_saliency)
        config_layout.addWidget(self.btn_saliency)

        layout.addWidget(config_group)
        layout.addSpacing(Stylesheets.SIDEBAR_GROUP_GAP)

        self.btn_export = QPushButton("Export Saliency", self)
        self.btn_export.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.btn_export.setToolTip(
            "Hidden until the saliency workflow has a complete import/export path.",
        )
        self.btn_export.clicked.connect(self.export_saliency)
        self.btn_export.setVisible(False)
        layout.addStretch()

    def update_info(self):
        """Refresh the aggregate info panel (delegated to InfoPanelService)."""
        if not self.info_panel:
            return

        # Handled by InfoPanelService

    # --- Actions ---

    def _on_update_after_command_result(self, result) -> None:
        if result is None and self.panel and hasattr(self.panel, "on_update"):
            self.panel.on_update()

    def set_montage(self):
        """Open the montage-picker dialog and apply channel positions."""
        capability = get_command_capability(self, CommandName.APPLY_MONTAGE)
        if capability is not None and not capability.enabled:
            QMessageBox.warning(
                self,
                "Montage blocked",
                blocked_reason(capability, "Create epochs before applying a montage."),
            )
            return

        if capability is None:
            has_epoch_data = self._compatibility_has_epoch_data_for_montage()
            if has_epoch_data is None:
                self._show_compatibility_fallback_warning("Montage blocked")
                return
            if not has_epoch_data:
                QMessageBox.warning(self, "Warning", "No epoch data available.")
                return

        channel_query = execute_application_command(
            self,
            QueryStateCommand(query="state"),
            refresh=False,
        )
        if channel_query is not None and channel_query.failed:
            QMessageBox.warning(
                self,
                "Montage blocked" if channel_query.recoverable else "Montage failed",
                channel_query.message,
            )
            return

        try:
            chs = self._montage_channel_names(channel_query)
        except ControllerCompatibilityUnavailableError:
            self._show_compatibility_fallback_warning("Montage blocked")
            return
        if not chs:
            QMessageBox.warning(
                self,
                "Montage blocked",
                "No epoch channel names are available for montage setup.",
            )
            return
        win = PickMontageDialog(self, chs)
        if win.exec():
            chs, positions = win.get_result()
            if chs is not None and positions is not None:
                try:
                    normalized_positions = normalize_montage_positions(
                        chs,
                        positions,
                    )
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Montage setup failed: {e}")
                    return

                result = execute_application_command(
                    self,
                    ApplyMontageCommand(
                        channels=list(chs),
                        positions=normalized_positions,
                    ),
                )
                if result is None:
                    self._show_compatibility_fallback_warning("Montage blocked")
                    return
                elif result.failed:
                    QMessageBox.warning(
                        self,
                        "Montage blocked" if result.recoverable else "Montage failed",
                        result.message,
                    )
                    return

                self._show_status("Montage set")

                # Notify parent to refresh view
                self._on_update_after_command_result(result)

    def _montage_channel_names(self, query_result) -> list[str]:
        if query_result is None:
            return self._compatibility_montage_channel_names()
        diagnostics = getattr(query_result, "diagnostics", {}) or {}
        state = diagnostics.get("state")
        epoch = state.get("epoch") if isinstance(state, dict) else {}
        names = epoch.get("channel_names") if isinstance(epoch, dict) else None
        if not isinstance(names, list):
            return []
        return [str(name) for name in names]

    def _compatibility_has_epoch_data_for_montage(self) -> bool | None:
        """Return epoch availability only for mock / compatibility UI contexts."""
        try:
            return bool(
                run_controller_compatibility_call(
                    self,
                    self.controller.has_epoch_data,
                ),
            )
        except ControllerCompatibilityUnavailableError:
            return None

    def _compatibility_montage_channel_names(self) -> list[str]:
        """Return montage channel names only for mock / compatibility UI contexts."""
        return run_controller_compatibility_call(
            self,
            self.controller.get_channel_names,
        )

    def set_saliency(self):
        """Open the saliency-settings dialog and apply parameters."""
        capability = get_command_capability(self, CommandName.SALIENCY)
        if capability is not None and not capability.enabled:
            QMessageBox.warning(
                self,
                "Saliency blocked",
                blocked_reason(
                    capability,
                    "Saliency analysis is not ready yet.",
                ),
            )
            return

        query_result = execute_application_command(
            self,
            SaliencyCommand(),
            refresh=False,
        )
        if query_result is not None and query_result.failed:
            QMessageBox.warning(
                self,
                "Saliency blocked" if query_result.recoverable else "Saliency failed",
                query_result.message,
            )
            return
        configuration_block_reason = self._saliency_configuration_block_reason(
            query_result,
        )
        if configuration_block_reason is not None:
            QMessageBox.warning(self, "Saliency blocked", configuration_block_reason)
            return
        try:
            dialog_params = self._saliency_dialog_params(query_result)
        except ControllerCompatibilityUnavailableError:
            self._show_compatibility_fallback_warning("Saliency blocked")
            return

        win = SaliencySettingDialog(
            self,
            dialog_params,
        )
        if win.exec():
            params = win.get_result()
            if params:
                started = execute_application_command_async(
                    self,
                    SaliencyCommand(params=dict(params)),
                    on_result=self._on_saliency_configured,
                    on_error=self._on_saliency_configuration_error,
                )
                if not started:
                    self._show_compatibility_fallback_warning("Saliency blocked")
                    return

    def _on_saliency_configured(self, result) -> None:
        if result.failed:
            QMessageBox.critical(
                self,
                "Error",
                f"Saliency setup failed: {result.message}",
            )
            return
        self._show_status("Saliency parameters set")
        if self.panel and hasattr(self.panel, "mark_refresh_dirty"):
            self.panel.mark_refresh_dirty()
        if self.panel and hasattr(self.panel, "update_info"):
            self.panel.update_info()

    def _on_saliency_configuration_error(self, error: tuple) -> None:
        message = error[1] if len(error) > 1 else error
        QMessageBox.critical(self, "Error", f"Saliency setup failed: {message}")

    def _saliency_dialog_params(self, query_result) -> dict | None:
        if query_result is None:
            return self._compatibility_saliency_dialog_params()
        diagnostics = getattr(query_result, "diagnostics", {}) or {}
        if diagnostics.get("payload_type") != "saliency_summary":
            return None
        params = diagnostics.get("params")
        return params if isinstance(params, dict) else None

    @staticmethod
    def _saliency_configuration_block_reason(query_result) -> str | None:
        if query_result is None:
            return None
        diagnostics = getattr(query_result, "diagnostics", {}) or {}
        if diagnostics.get("payload_type") != "saliency_summary":
            return None
        if diagnostics.get("configure_available", True) is not False:
            return None
        reasons = diagnostics.get("configure_reasons")
        if isinstance(reasons, list):
            for reason in reasons:
                text = str(reason).strip()
                if text:
                    return text
        return "Select a model and training settings before configuring saliency."

    def _compatibility_saliency_dialog_params(self) -> dict | None:
        """Return saliency params only for mock / compatibility UI contexts."""
        return run_controller_compatibility_call(
            self,
            self.controller.get_saliency_params,
        )

    def export_saliency(self):
        """Open the saliency-export dialog to save computed saliency data."""
        result = execute_application_command(
            self,
            SaliencyCommand(),
            refresh=False,
        )
        block_reason = self._saliency_export_block_reason(result)
        if block_reason is not None:
            QMessageBox.warning(self, "Export Saliency Blocked", block_reason)
            return

        trainers = self._saliency_export_trainers()
        if trainers is None:
            try:
                trainers = self._compatibility_export_trainers()
            except ControllerCompatibilityUnavailableError:
                self._show_compatibility_fallback_warning("Export Saliency Blocked")
                return

        if not trainers:
            QMessageBox.warning(self, "Warning", "No training results available.")
            return
        win = ExportSaliencyDialog(self, trainers)
        win.exec()

    def _saliency_export_trainers(self):
        result = execute_application_command(
            self,
            VisualizeCommand(view="summary", include_objects=True),
            refresh=False,
        )
        if result is None:
            return None
        if result.failed:
            QMessageBox.warning(
                self,
                "Export Saliency Blocked",
                result.message,
            )
            return []
        diagnostics = getattr(result, "diagnostics", {}) or {}
        if diagnostics.get("payload_type") != "visualization_summary":
            return []
        trainers = diagnostics.get("trainer_objects")
        if not isinstance(trainers, list):
            return []
        return list(trainers)

    def _compatibility_export_trainers(self):
        if self.panel and hasattr(self.panel, "get_trainers"):
            return run_controller_compatibility_call(self, self.panel.get_trainers)
        return run_controller_compatibility_call(self, self.controller.get_trainers)

    @staticmethod
    def _saliency_export_block_reason(result) -> str | None:
        if result is None:
            return None
        if result.failed:
            return result.message
        diagnostics = getattr(result, "diagnostics", {}) or {}
        if diagnostics.get("payload_type") != "saliency_summary":
            return None
        if diagnostics.get("saliency_available") is True:
            return None
        return "Saliency output is not ready to export."

    def _show_compatibility_fallback_warning(self, title: str) -> None:
        QMessageBox.warning(self, title, CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE)
