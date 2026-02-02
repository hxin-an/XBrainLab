from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from XBrainLab.ui.core.base_dialog import BaseDialog


class ChannelSelectionDialog(BaseDialog):
    def __init__(self, parent, data_list):
        self.data_list = data_list
        self.selected_channels = []

        # UI
        self.list_widget = None
        self.btn_all = None
        self.btn_none = None

        super().__init__(parent, title="Channel Selection")
        self.resize(300, 400)

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Channel List
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.MultiSelection)

        # Get channels from first file
        if self.data_list:
            channels = self.data_list[0].get_mne().ch_names
            for ch in channels:
                item = QListWidgetItem(ch)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                self.list_widget.addItem(item)

        layout.addWidget(self.list_widget)

        # Select All / None
        btn_layout = QHBoxLayout()
        self.btn_all = QPushButton("Select All")
        self.btn_all.clicked.connect(lambda: self.set_all_checked(True))
        self.btn_none = QPushButton("Deselect All")
        self.btn_none.clicked.connect(lambda: self.set_all_checked(False))
        btn_layout.addWidget(self.btn_all)
        btn_layout.addWidget(self.btn_none)
        layout.addLayout(btn_layout)

        # Dialog Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def set_all_checked(self, checked):
        if not self.list_widget:
            return
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item:
                item.setCheckState(state)

    def accept(self):
        if not self.list_widget:
            super().accept()
            return

        selected_channels = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                selected_channels.append(item.text())

        if not selected_channels:
            QMessageBox.warning(self, "Warning", "Please select at least one channel.")
            return

        self.selected_channels = selected_channels
        super().accept()

    def get_result(self):
        return self.selected_channels
