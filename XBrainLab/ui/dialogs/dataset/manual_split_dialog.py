"""Manual split chooser dialog for selecting specific items for data splitting.

Provides a multi-selection list for manually choosing subjects, sessions,
or trials to include in a particular data split.
"""

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialogButtonBox,
    QListWidget,
    QVBoxLayout,
)

from XBrainLab.ui.core.base_dialog import BaseDialog


class ManualSplitDialog(BaseDialog):
    """Dialog for manually selecting items for data splitting.

    Displays a multi-selection list of choices (subjects, sessions, or
    trials) and returns the selected indices or identifiers.

    Attributes:
        choices: List of items to choose from. Each item can be a value
            or a ``(id, name)`` tuple.
        selected_indices: List of selected item identifiers after acceptance.
        list_widget: QListWidget displaying the choices.

    """

    def __init__(self, parent, choices):
        self.choices = choices
        self.selected_indices = []

        # UI
        self.list_widget = None

        super().__init__(parent, title="Manual Split Chooser")
        self.resize(300, 400)

    def init_ui(self):
        """Initialize the dialog UI with a multi-selection list and buttons."""
        layout = QVBoxLayout(self)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection,
        )

        for item in self.choices:
            # item can be tuple (id, name) or just value
            if isinstance(item, tuple):
                self.list_widget.addItem(str(item[1]))
            else:
                self.list_widget.addItem(str(item))

        layout.addWidget(self.list_widget)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        """Collect selected items and accept the dialog."""
        if self.list_widget is None:
            super().accept()
            return

        self.selected_indices = [
            self.list_widget.row(item) for item in self.list_widget.selectedItems()
        ]

        final_result = []
        for idx in self.selected_indices:
            item = self.choices[idx]
            if isinstance(item, tuple):
                final_result.append(item[0])
            else:
                final_result.append(item)
        self.selected_indices = final_result
        super().accept()

    def get_result(self):
        """Return the list of selected item identifiers.

        Returns:
            List of selected identifiers. For tuple choices, returns the
            first element (id); otherwise returns the raw value.

        """
        return self.selected_indices
