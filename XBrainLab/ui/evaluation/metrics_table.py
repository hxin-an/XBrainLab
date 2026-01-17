from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem


class MetricsTableWidget(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        # Setup columns: Class, Precision, Recall, F1-Score, Support
        columns = ["Class", "Precision", "Recall", "F1-Score", "Support"]
        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels(columns)

        # Style
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        # Dark mode friendly style
        self.setStyleSheet(
            """
            QTableWidget {
                background-color: #252526;
                color: #cccccc;
                gridline-color: #3e3e42;
                border: none;
            }
            QHeaderView::section {
                background-color: #333333;
                color: #cccccc;
                padding: 4px;
                border: 1px solid #3e3e42;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QTableWidget::item:selected {
                background-color: #094771;
                color: white;
            }
        """
        )

    def update_data(self, metrics: dict):
        """Update table with metrics data.

        Args:
            metrics: Dict returned by EvalRecord.get_per_class_metrics()
        """
        self.setRowCount(0)

        if not metrics:
            return

        # Sort keys to ensure order (integers first, then macro_avg)
        keys = sorted([k for k in metrics if isinstance(k, int)])

        # Add per-class rows
        for class_idx in keys:
            self._add_row(str(class_idx), metrics[class_idx])

        # Add Macro Avg row
        if "macro_avg" in metrics:
            self._add_row("Macro Avg", metrics["macro_avg"], is_summary=True)

    def _add_row(self, label: str, data: dict, is_summary: bool = False):
        row = self.rowCount()
        self.insertRow(row)

        # Helper to create item
        def create_item(text, is_bold=False):
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if is_bold:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            if is_summary:
                item.setBackground(QColor("#3e3e42"))
            return item

        self.setItem(row, 0, create_item(label, is_bold=is_summary))
        self.setItem(
            row, 1, create_item(f"{data['precision']:.4f}", is_bold=is_summary)
        )
        self.setItem(row, 2, create_item(f"{data['recall']:.4f}", is_bold=is_summary))
        self.setItem(row, 3, create_item(f"{data['f1-score']:.4f}", is_bold=is_summary))
        self.setItem(row, 4, create_item(str(data["support"]), is_bold=is_summary))
