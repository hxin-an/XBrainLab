from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QListWidget,
    QVBoxLayout,
)


class ManualSplitChooser(QDialog):
    def __init__(self, parent, choices):
        super().__init__(parent)
        self.setWindowTitle("Manual Split Chooser")
        self.resize(300, 400)
        self.choices = choices
        self.selected_indices = []

        self.init_ui()

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
        self.selected_indices = [
            self.list_widget.row(item) for item in self.list_widget.selectedItems()
        ]
        # Map back to choice IDs/Values
        # Original code returns list of IDs or indices?
        # Original: result = ManualSplitChooser(self, choice).get_result()
        # choice is list of tuples or ints.
        # If choice is [(0, 'S1'), (1, 'S2')], result seems to be list of 0, 1.
        # Let's return the first element of tuple if tuple, else the item itself.

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
