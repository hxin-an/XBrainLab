"""Sidebar widget for the visualization panel with configuration and export controls."""

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
    blocked_reason,
    execute_application_command,
    get_command_capability,
    run_legacy_controller_fallback,
)
from XBrainLab.ui.components.info_panel import AggregateInfoPanel
from XBrainLab.ui.dialogs.visualization import (
    ExportSaliencyDialog,
    PickMontageDialog,
    SaliencySettingDialog,
)
from XBrainLab.ui.montage_positions import normalize_montage_positions
from XBrainLab.ui.styles.stylesheets import Stylesheets


class ControlSidebar(QWidget):
    """Sidebar for Visualization Panel (Configuration & Operations).
    Hosts controls for Montages, Saliency Settings, and export actions.
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

        self.btn_montage = QPushButton("Set Montage")
        self.btn_montage.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.btn_montage.clicked.connect(self.set_montage)
        config_layout.addWidget(self.btn_montage)

        self.btn_saliency = QPushButton("Saliency Settings")
        self.btn_saliency.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.btn_saliency.clicked.connect(self.set_saliency)
        config_layout.addWidget(self.btn_saliency)

        layout.addWidget(config_group)
        layout.addSpacing(20)

        # Group 2: Operations
        ops_group = QGroupBox("OPERATIONS")
        ops_group.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        ops_layout = QVBoxLayout(ops_group)
        ops_layout.setContentsMargins(0, 10, 0, 0)

        self.btn_export = QPushButton("Export Saliency")
        self.btn_export.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.btn_export.clicked.connect(self.export_saliency)
        ops_layout.addWidget(self.btn_export)

        layout.addWidget(ops_group)
        layout.addStretch()

    def update_info(self):
        """Refresh the aggregate info panel (delegated to InfoPanelService)."""
        if not self.info_panel:
            return

        # Handled by InfoPanelService

    # --- Actions ---

    def _on_update_after_legacy_result(self, result) -> None:
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

        if capability is None and not self.controller.has_epoch_data():
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

        chs = self._montage_channel_names(channel_query)
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
                    run_legacy_controller_fallback(
                        self,
                        lambda: self.controller.set_montage(
                            list(chs),
                            normalized_positions,
                        ),
                    )
                elif result.failed:
                    QMessageBox.warning(
                        self,
                        "Montage blocked" if result.recoverable else "Montage failed",
                        result.message,
                    )
                    return

                QMessageBox.information(self, "Success", "Montage set")

                # Notify parent to refresh view
                self._on_update_after_legacy_result(result)

    def _montage_channel_names(self, query_result) -> list[str]:
        if query_result is None:
            return run_legacy_controller_fallback(
                self,
                self.controller.get_channel_names,
            )
        diagnostics = getattr(query_result, "diagnostics", {}) or {}
        state = diagnostics.get("state")
        epoch = state.get("epoch") if isinstance(state, dict) else {}
        names = epoch.get("channel_names") if isinstance(epoch, dict) else None
        if not isinstance(names, list):
            return []
        return [str(name) for name in names]

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

        win = SaliencySettingDialog(
            self,
            self._saliency_dialog_params(query_result),
        )
        if win.exec():
            params = win.get_result()
            if params:
                result = execute_application_command(
                    self,
                    SaliencyCommand(params=dict(params)),
                )
                if result is None:
                    run_legacy_controller_fallback(
                        self,
                        lambda: self.controller.set_saliency_params(params),
                    )
                elif result.failed:
                    QMessageBox.critical(
                        self,
                        "Error",
                        f"Saliency setup failed: {result.message}",
                    )
                    return
                QMessageBox.information(self, "Success", "Saliency parameters set")

                self._on_update_after_legacy_result(result)

    def _saliency_dialog_params(self, query_result) -> dict | None:
        if query_result is None:
            return run_legacy_controller_fallback(
                self,
                self.controller.get_saliency_params,
            )
        diagnostics = getattr(query_result, "diagnostics", {}) or {}
        if diagnostics.get("payload_type") != "saliency_summary":
            return None
        params = diagnostics.get("params")
        return params if isinstance(params, dict) else None

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
            trainers = self._legacy_export_trainers()

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

    def _legacy_export_trainers(self):
        if self.panel and hasattr(self.panel, "get_trainers"):
            return run_legacy_controller_fallback(self, self.panel.get_trainers)
        return run_legacy_controller_fallback(self, self.controller.get_trainers)

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
