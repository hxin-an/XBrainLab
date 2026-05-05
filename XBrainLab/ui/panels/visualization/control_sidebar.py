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
    SaliencyCommand,
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

    @staticmethod
    def _normalize_montage_positions(chs, positions):
        """Return montage positions as JSON-safe ``(x, y, z)`` tuples."""
        if isinstance(positions, dict):
            position_values = [positions[ch] for ch in chs]
        else:
            position_values = positions

        normalized = []
        for position in position_values:
            coords = list(position)
            if len(coords) != 3:
                raise ValueError("Each montage position must contain x, y, z values.")
            normalized.append((float(coords[0]), float(coords[1]), float(coords[2])))
        return normalized

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

        # We need channel names
        chs = self.controller.get_channel_names()
        win = PickMontageDialog(self, chs)
        if win.exec():
            chs, positions = win.get_result()
            if chs is not None and positions is not None:
                try:
                    normalized_positions = self._normalize_montage_positions(
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
                    return
                if result.failed:
                    QMessageBox.warning(
                        self,
                        "Montage blocked" if result.recoverable else "Montage failed",
                        result.message,
                    )
                    return

                QMessageBox.information(self, "Success", "Montage set")

                # Notify parent to refresh view
                if self.panel and hasattr(self.panel, "on_update"):
                    self.panel.on_update()

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

        win = SaliencySettingDialog(self, self.controller.get_saliency_params())
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

                if self.panel and hasattr(self.panel, "on_update"):
                    self.panel.on_update()

    def export_saliency(self):
        """Open the saliency-export dialog to save computed saliency data."""
        if self.panel and hasattr(self.panel, "get_trainers"):
            trainers = self.panel.get_trainers()
        else:
            trainers = self.controller.get_trainers()

        if not trainers:
            QMessageBox.warning(self, "Warning", "No training results available.")
            return
        win = ExportSaliencyDialog(self, trainers)
        win.exec()
