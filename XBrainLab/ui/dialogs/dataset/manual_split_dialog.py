from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialogButtonBox,
    QListWidget,
    QVBoxLayout,
)

from XBrainLab.ui.core.base_dialog import BaseDialog


class ManualSplitDialog(BaseDialog):
    def __init__(self, parent, choices):
        self.choices = choices
        self.selected_indices = []

        # UI
        self.list_widget = None

        super().__init__(parent, title="Manual Split Chooser")
        self.resize(300, 400)

    def init_ui(self):
        layout = QVBoxLayout(self)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection
        )

        for item in self.choices:
            # item can be tuple (id, name) or just value
            if isinstance(item, tuple):
                self.list_widget.addItem(str(item[1]))
            else:
                self.list_widget.addItem(str(item))

        layout.addWidget(self.list_widget)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        if not self.list_widget:
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
        return self.selected_indices
