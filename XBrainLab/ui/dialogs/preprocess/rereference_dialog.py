"""Re-referencing dialog for changing the EEG reference scheme.

Provides options for average reference (CAR) or selecting specific
reference channels from the dataset.
"""

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialogButtonBox,
    QGroupBox,
    QListWidget,
    QMessageBox,
    QVBoxLayout,
)

from XBrainLab.ui.core.base_dialog import BaseDialog


class RereferenceDialog(BaseDialog):
    """Dialog for re-referencing EEG data.

    Supports average reference (CAR) or selection of specific channels
    as the new reference.

    Attributes:
        data_list: List of loaded EEG data objects.
        reref_params: Reference parameter: ``'average'`` or a list of
            channel names.
        avg_check: QCheckBox for enabling average reference.
        chan_group: QGroupBox containing the channel selection list.
        chan_list: QListWidget displaying available channels.
    """

    def __init__(self, parent, data_list: list):
        self.data_list = data_list
        self.reref_params: str | list[str] | None = None
        self.avg_check: QCheckBox | None = None
        self.chan_group: QGroupBox | None = None
        self.chan_list: QListWidget | None = None

        super().__init__(parent, title="Re-reference")
        self.resize(400, 300)

    def init_ui(self):
        """Initialize the dialog UI with reference mode controls."""
        layout = QVBoxLayout(self)

        self.avg_check = QCheckBox("Use Average Reference")
        self.avg_check.setChecked(True)
        self.avg_check.toggled.connect(self.toggle_avg)
        layout.addWidget(self.avg_check)

        self.chan_group = QGroupBox("Select Reference Channels")
        self.chan_group.setEnabled(False)
        chan_layout = QVBoxLayout()
        self.chan_list = QListWidget()
        self.chan_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)

        if self.data_list:
            first_data = self.data_list[0]
            self.chan_list.addItems(first_data.get_mne().ch_names)

        chan_layout.addWidget(self.chan_list)
        self.chan_group.setLayout(chan_layout)
        layout.addWidget(self.chan_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def toggle_avg(self, checked):
        """Toggle channel selection group based on average reference state.

        Args:
            checked: Whether average reference is enabled.
        """
        if self.chan_group:
            self.chan_group.setEnabled(not checked)

    def accept(self):
        """Validate channel selection and accept the dialog.

        Raises:
            QMessageBox: Warning if no reference channel is selected.
        """
        if not self.avg_check or not self.chan_list:
            return

        ref: str | list[str] | None = None
        if self.avg_check.isChecked():
            ref = "average"
        else:
            selected = self.chan_list.selectedItems()
            if not selected:
                QMessageBox.warning(
                    self,
                    "Warning",
                    "Please select at least one channel or use average reference.",
                )
                return
            ref = [item.text() for item in selected]

        self.reref_params = ref
        super().accept()

    def get_params(self):
        """Return the configured reference parameters.

        Returns:
            String ``'average'`` or list of channel name strings, or None.
        """
        return self.reref_params

    def get_result(self):
        """Return the configured reference parameters.

        Returns:
            String ``'average'`` or list of channel name strings, or None.
        """
        return self.get_params()
