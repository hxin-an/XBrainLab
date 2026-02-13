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
from XBrainLab.ui.dialogs.dataset import ChannelSelectionDialog
from XBrainLab.ui.styles.stylesheets import Stylesheets


class DatasetSidebar(QWidget):
    """
    Sidebar for DatasetPanel containing Info, Operations, and Execution controls.
    Hosts aggregate info panel and buttons for imports/clearing.
    """

    def __init__(self, panel, parent=None):
        super().__init__(parent)
        self.panel = panel  # Reference to main panel (for actions access)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.init_ui()

    @property
    def controller(self):
        return self.panel.controller

    @property
    def main_window(self):
        return self.panel.main_window

    def init_ui(self):
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

        self.import_btn = QPushButton("Import Data")
        self.import_btn.setToolTip("Load .set or .gdf files")
        self.import_btn.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.import_btn.clicked.connect(self.panel.action_handler.import_data)
        ops_layout.addWidget(self.import_btn)

        self.import_label_btn = QPushButton("Import Label")
        self.import_label_btn.setToolTip("Import labels from external files")
        self.import_label_btn.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.import_label_btn.clicked.connect(self.panel.action_handler.import_label)
        ops_layout.addWidget(self.import_label_btn)

        self.smart_parse_btn = QPushButton("Smart Parse Metadata")
        self.smart_parse_btn.setToolTip("Auto-extract Subject/Session from filenames")
        self.smart_parse_btn.setStyleSheet(Stylesheets.SIDEBAR_BTN)
        self.smart_parse_btn.clicked.connect(
            self.panel.action_handler.open_smart_parser
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
        self.chan_select_btn.setStyleSheet(Stylesheets.BTN_SUCCESS)
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
            is_locked = self.controller.is_locked()

            # Channel Selection
            if is_locked:
                self.chan_select_btn.setToolTip(
                    "Dataset is locked. Click to see details."
                )
            else:
                self.chan_select_btn.setToolTip("Select specific channels to keep")

            # Smart Parse
            if is_locked:
                self.smart_parse_btn.setToolTip(
                    "Dataset is locked. Click to see details."
                )
            else:
                self.smart_parse_btn.setToolTip(
                    "Auto-extract Subject/Session from filenames"
                )

    # --- Actions moved from Panel ---

    def open_channel_selection(self):
        if not self.controller:
            return

        if not self.controller.has_data():
            QMessageBox.warning(self, "Warning", "No data loaded.")
            return

        if self.controller.is_locked():
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

        data_list = self.controller.get_loaded_data_list()
        dialog = ChannelSelectionDialog(self, data_list)
        if dialog.exec():
            result = dialog.get_result()
            if result:
                try:
                    self.controller.apply_channel_selection(result)
                    self.panel.update_panel()
                    QMessageBox.information(
                        self, "Success", "Channel selection applied."
                    )
                except Exception as e:
                    QMessageBox.critical(
                        self, "Error", f"Channel selection failed: {e}"
                    )

    def clear_dataset(self):
        reply = QMessageBox.question(
            self,
            "Confirm Clear",
            "Are you sure you want to clear the entire dataset?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.controller.clean_dataset()
                self.panel.update_panel()
                QMessageBox.information(self, "Success", "Dataset cleared.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to clear dataset: {e}")
