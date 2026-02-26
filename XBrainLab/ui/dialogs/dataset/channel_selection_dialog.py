"""Channel selection dialog for picking EEG channels.

Provides a searchable list interface for selecting specific channels
from an EEG dataset, with Select All/Deselect All convenience actions.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from XBrainLab.ui.core.base_dialog import BaseDialog


class ChannelSelectionDialog(BaseDialog):
    """Dialog for selecting specific channels from an EEG dataset.

    Provides a filterable list of available channels with Select All/None
    options and a search bar for quick channel lookup.

    Attributes:
        data_list: List of loaded EEG data objects.
        selected_channels: List of channel names selected by the user.
        list_widget: QListWidget displaying available channels.
        btn_all: Button to select all channels.
        btn_none: Button to deselect all channels.

    """

    def __init__(self, parent, data_list: list):
        self.data_list = data_list
        self.selected_channels: list[str] = []

        # UI
        self.list_widget: QListWidget | None = None
        self.btn_all: QPushButton | None = None
        self.btn_none: QPushButton | None = None

        super().__init__(parent, title="Channel Selection")
        self.resize(300, 400)

    def init_ui(self):
        """Initialize the dialog UI with search bar, channel list, and buttons."""
        layout = QVBoxLayout(self)

        # Search Filter
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search channels...")
        self.search_bar.textChanged.connect(self.filter_channels)
        layout.addWidget(self.search_bar)

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
        self.create_buttons(layout)

    def filter_channels(self, text: str):
        """Filter the list widget items based on search text.

        Args:
            text: Search string to filter channels by (case-insensitive).

        """
        if self.list_widget is None:
            return

        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item:
                item.setHidden(text.lower() not in item.text().lower())

    def create_buttons(self, layout: QVBoxLayout):
        """Create Select All, Deselect All, and OK/Cancel buttons.

        Args:
            layout: Parent layout to add buttons to.

        """
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
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def set_all_checked(self, checked):
        """Set the check state for all items in the list.

        Args:
            checked: If True, check all items; otherwise uncheck all.

        """
        if self.list_widget is None:
            return
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item:
                item.setCheckState(state)

    def accept(self):
        """Validate selection and accept the dialog.

        Raises:
            QMessageBox: Warning displayed if no channels are selected.

        """
        if self.list_widget is None:
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
        """Return the list of selected channel names.

        Returns:
            List of selected channel name strings.

        """
        return self.selected_channels
