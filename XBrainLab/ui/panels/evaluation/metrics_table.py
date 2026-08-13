"""Metrics table widget for displaying per-class classification metrics."""

from PyQt6.QtCore import QModelIndex, Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QHeaderView, QSizePolicy, QTableWidget, QTableWidgetItem

from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.styles.theme import Theme


class MetricsTableWidget(QTableWidget):
    """Table widget showing precision, recall, F1-score, and support per class.

    Renders per-class rows followed by an optional macro-average summary row.
    Read-only, non-selectable, dark-theme styled.
    """

    MAX_VISIBLE_ROWS = 12

    def __init__(self, parent=None):
        """Initialize the metrics table widget.

        Args:
            parent: Optional parent widget.

        """
        super().__init__(parent)
        self.setObjectName("EvaluationMetricsTable")
        self.init_ui()

    def init_ui(self):
        """Configure columns, headers, and styling for the table."""
        # Setup columns: Class, Precision, Recall, F1-Score, Support
        columns = ["Class", "Precision", "Recall", "F1-Score", "Support"]
        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels(columns)

        # Style
        header = self.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        v_header = self.verticalHeader()
        if v_header is not None:
            v_header.setVisible(False)
        self.setAlternatingRowColors(True)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        # Dark mode friendly style
        self.setStyleSheet(Stylesheets.METRICS_TABLE)
        palette = self.palette()
        for group in (
            QPalette.ColorGroup.Active,
            QPalette.ColorGroup.Inactive,
            QPalette.ColorGroup.Disabled,
        ):
            palette.setColor(
                group,
                QPalette.ColorRole.Base,
                QColor(Theme.METRICS_TABLE_BG),
            )
            palette.setColor(
                group,
                QPalette.ColorRole.AlternateBase,
                QColor(Theme.METRICS_TABLE_ALT_BG),
            )
            palette.setColor(group, QPalette.ColorRole.Text, QColor(Theme.TEXT_PRIMARY))
            palette.setColor(
                group,
                QPalette.ColorRole.Highlight,
                QColor(Theme.TABLE_SELECTION),
            )
            palette.setColor(
                group,
                QPalette.ColorRole.HighlightedText,
                QColor(Theme.TEXT_PRIMARY),
            )
        self.setPalette(palette)

    def update_data(
        self,
        metrics: dict,
        *,
        class_names: dict[int, str] | None = None,
    ):
        """Update table with metrics data.

        Args:
            metrics: Dict returned by EvalRecord.get_per_class_metrics()

        """
        self.setRowCount(0)

        if not metrics:
            self._clear_current_selection()
            self._fit_height_to_rows()
            return

        # Sort keys to ensure order (integers first, then macro_avg)
        keys = sorted([k for k in metrics if isinstance(k, int)])

        # Add per-class rows
        for class_idx in keys:
            label = (class_names or {}).get(class_idx, str(class_idx))
            self._add_row(label, metrics[class_idx])

        # Add Macro Avg row
        if "macro_avg" in metrics:
            self._add_row("Macro Avg", metrics["macro_avg"], is_summary=True)

        self._clear_current_selection()
        self._fit_height_to_rows()

    def _fit_height_to_rows(self) -> None:
        """Fit small metric sets and cap larger tables behind a scrollbar."""
        visible_rows = min(max(self.rowCount(), 1), self.MAX_VISIBLE_ROWS)
        row_heights = [
            self.rowHeight(index) for index in range(min(self.rowCount(), visible_rows))
        ]
        vertical_header = self.verticalHeader()
        default_row_height = (
            vertical_header.defaultSectionSize() if vertical_header is not None else 30
        )
        content_height = sum(
            height if height > 0 else default_row_height for height in row_heights
        )
        if not row_heights:
            content_height = default_row_height
        header = self.horizontalHeader()
        header_height = header.sizeHint().height() if header is not None else 0
        target_height = header_height + content_height + (self.frameWidth() * 2) + 2
        self.setMinimumHeight(target_height)
        self.setMaximumHeight(target_height)

    def _clear_current_selection(self) -> None:
        self.clearSelection()
        model_index = QModelIndex()
        self.setCurrentIndex(model_index)
        selection_model = self.selectionModel()
        if selection_model is not None:
            selection_model.clear()

    def _add_row(self, label: str, data: dict, is_summary: bool = False):
        """Append a single row of metrics to the table.

        Args:
            label: Display label for the row (e.g., class index or
                ``'Macro Avg'``).
            data: Dictionary with keys ``'precision'``, ``'recall'``,
                ``'f1-score'``, and ``'support'``.
            is_summary: If ``True``, render the row with bold font and
                a highlighted background.

        """
        row = self.rowCount()
        self.insertRow(row)

        # Helper to create item
        row_color = (
            Theme.TABLE_SELECTION
            if is_summary
            else (Theme.METRICS_TABLE_ALT_BG if row % 2 else Theme.METRICS_TABLE_BG)
        )

        def create_item(text, is_bold=False):
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if is_bold:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            item.setForeground(QColor(Theme.TEXT_PRIMARY))
            item.setBackground(QColor(row_color))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            return item

        self.setItem(row, 0, create_item(label, is_bold=is_summary))
        self.setItem(
            row,
            1,
            create_item(f"{data['precision']:.4f}", is_bold=is_summary),
        )
        self.setItem(row, 2, create_item(f"{data['recall']:.4f}", is_bold=is_summary))
        self.setItem(row, 3, create_item(f"{data['f1-score']:.4f}", is_bold=is_summary))
        self.setItem(row, 4, create_item(str(data["support"]), is_bold=is_summary))
