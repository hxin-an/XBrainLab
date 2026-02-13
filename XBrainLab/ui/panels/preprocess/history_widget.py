from PyQt6.QtWidgets import QGroupBox, QListWidget, QVBoxLayout, QWidget


class HistoryWidget(QWidget):
    """
    Widget to display preprocessing history as a list.
    Updates dynamically based on controller state.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.group = QGroupBox("PREPROCESSING HISTORY")
        group_layout = QVBoxLayout(self.group)
        group_layout.setContentsMargins(10, 20, 10, 10)

        self.history_list = QListWidget()
        group_layout.addWidget(self.history_list)

        layout.addWidget(self.group)

    def update_history(self, history: list[str] | None, is_epoched: bool):
        self.history_list.clear()

        if history:
            for step in history:
                self.history_list.addItem(str(step))
        else:
            self.history_list.addItem("No preprocessing applied.")

        if is_epoched:
            self.history_list.addItem("Preprocessing Locked (Epoched).")

    def show_no_data(self):
        self.history_list.clear()
        self.history_list.addItem("No data loaded.")
