"""Widget for displaying preprocessing history in a stable viewport."""

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QListWidget,
    QSizePolicy,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)


class _HistoryItemDelegate(QStyledItemDelegate):
    """Give every history entry one predictable, DPI-aware row height."""

    def __init__(self, row_height: int, parent=None):
        super().__init__(parent)
        self._row_height = row_height

    def sizeHint(self, option, index):  # noqa: N802
        size = super().sizeHint(option, index)
        return QSize(size.width(), self._row_height)


class HistoryWidget(QWidget):
    """Widget to display preprocessing history as a list.
    Updates dynamically based on controller state.
    """

    MAX_VISIBLE_ROWS = 5
    MIN_ROW_HEIGHT = 24

    def __init__(self, parent=None):
        """Initialize the history widget.

        Args:
            parent: Optional parent widget.

        """
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.init_ui()
        self._apply_stable_geometry()

    def init_ui(self):
        """Build the layout with a group box and list widget."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.group = QGroupBox("PREPROCESSING HISTORY")
        group_layout = QVBoxLayout(self.group)
        group_layout.setContentsMargins(10, 20, 10, 10)

        self.history_list = QListWidget()
        self.history_list.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection,
        )
        self.history_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.history_list.setUniformItemSizes(True)
        self._row_height = max(
            self.fontMetrics().height() + 6,
            self.MIN_ROW_HEIGHT,
        )
        self.history_list.setItemDelegate(
            _HistoryItemDelegate(self._row_height, self.history_list),
        )
        self.history_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.history_list.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )
        self.history_list.addItem("No preprocessing history yet.")
        group_layout.addWidget(self.history_list)

        layout.addWidget(self.group)

    def _apply_stable_geometry(self) -> None:
        """Reserve complete rows without making outer height content-dependent."""
        list_height = (2 * self.history_list.frameWidth()) + (
            self._row_height * self.MAX_VISIBLE_ROWS
        )
        self.history_list.setFixedHeight(list_height)
        group_layout = self.group.layout()
        if group_layout is not None:
            group_layout.activate()
        own_layout = self.layout()
        if own_layout is not None:
            own_layout.activate()
        self.setFixedHeight(self.sizeHint().height())

    def update_history(self, history: list[str] | None, is_epoched: bool):
        """Refresh the history list with the current preprocessing steps.

        Args:
            history: Ordered list of step description strings, or ``None``
                if no preprocessing has been applied.
            is_epoched: Whether the data has been epoched (locks further
                preprocessing).

        """
        self.history_list.clear()

        if history:
            for step in history:
                self.history_list.addItem(str(step))
        else:
            self.history_list.addItem(
                "No preprocessing operations have been applied yet."
            )

        if is_epoched:
            self.history_list.addItem(
                "Epoching completed. Preprocessing is now locked."
            )

    def show_no_data(self):
        """Display a placeholder message when no data is loaded."""
        self.history_list.clear()
        self.history_list.addItem("No preprocessing history yet.")
