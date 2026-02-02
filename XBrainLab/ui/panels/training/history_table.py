import time

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

from XBrainLab.backend.training.record.key import RecordKey, TrainRecordKey
from XBrainLab.ui.styles.stylesheets import Stylesheets


class TrainingHistoryTable(QTableWidget):
    """
    Widget to display training history.
    """

    selection_changed_record = pyqtSignal(object)  # Emits record object

    def __init__(self, parent=None):
        super().__init__(parent)
        self.row_map = {}  # Map row -> (plan, record)
        self._init_ui()

    def _init_ui(self):
        self.setColumnCount(11)
        self.setHorizontalHeaderLabels(
            [
                "Group",
                "Run",
                "Model",
                "Status",
                "Progress",
                "Train Loss",
                "Train Acc",
                "Val Loss",
                "Val Acc",
                "LR",
                "Time",
            ]
        )

        self.setStyleSheet(Stylesheets.HISTORY_TABLE)

        header_v = self.verticalHeader()
        if header_v:
            header_v.setVisible(False)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        # Column widths
        header = self.horizontalHeader()
        if header:
            for i in range(11):
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)

        self.setColumnWidth(0, 80)  # Group
        self.setColumnWidth(1, 80)  # Run
        self.setColumnWidth(2, 150)  # Model
        self.setColumnWidth(3, 100)  # Status
        self.setColumnWidth(4, 80)  # Progress
        # Metrics
        for i in range(5, 11):
            self.setColumnWidth(i, 80)

        if header:
            header.setStretchLastSection(True)

        self.itemSelectionChanged.connect(self._on_selection_changed)

    def _on_selection_changed(self):
        selected_items = self.selectedItems()
        if not selected_items:
            self.selection_changed_record.emit(None)
            return

        row = selected_items[0].row()
        if row in self.row_map:
            _, record = self.row_map[row]
            self.selection_changed_record.emit(record)

    def clear_history(self):
        self.setRowCount(0)
        self.row_map.clear()

    def update_table(self, target_rows):
        """Alias for update_history to satisfy interface."""
        self.update_history(target_rows)

    def update_history(self, target_rows):
        """
        Update table content with formatted history from controller.
        """
        if self.rowCount() != len(target_rows):
            self.setRowCount(len(target_rows))

        for row_idx, data in enumerate(target_rows):
            plan = data["plan"]
            record = data["record"]
            group_name = data["group_name"]
            run_name = data["run_name"]
            model_name = data["model_name"]
            is_current_run = data.get("is_current_run", False)

            # Store mapping
            self.row_map[row_idx] = (plan, record)

            # Determine status
            epoch = record.get_epoch()
            max_epochs = plan.option.epoch

            if record.is_finished():
                status = "Done"
            elif is_current_run:
                status = "Running"
            elif record.epoch == 0:
                status = "Pending"
            else:
                status = "Stopped"

            def set_item(col, text, r=row_idx):
                item = self.item(r, col)
                if not item:
                    item = QTableWidgetItem()
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.setItem(r, col, item)
                if item.text() != text:
                    item.setText(text)

            set_item(0, group_name)
            set_item(1, run_name)
            set_item(2, model_name)
            set_item(3, status)
            set_item(4, f"{epoch}/{max_epochs}")

            # Metrics
            def get_last(key, source):
                if len(source[key]) > 0:
                    val = source[key][-1]
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        return 0.0
                return 0.0

            train_loss = get_last(TrainRecordKey.LOSS, record.train)
            train_acc = get_last(TrainRecordKey.ACC, record.train)
            val_loss = get_last(RecordKey.LOSS, record.val)
            val_acc = get_last(RecordKey.ACC, record.val)
            lr = get_last(TrainRecordKey.LR, record.train)

            val_loss_str = f"{val_loss:.4f}" if val_loss != 0 else "N/A"
            val_acc_str = f"{val_acc:.2f}%" if val_acc != 0 else "N/A"

            set_item(5, f"{train_loss:.4f}")
            set_item(6, f"{train_acc:.2f}%")
            set_item(7, val_loss_str)
            set_item(8, val_acc_str)
            set_item(9, f"{lr:.6f}")

            time_str = "-"
            start_ts = getattr(record, "start_timestamp", None)
            end_ts = getattr(record, "end_timestamp", None)

            if start_ts:
                duration = end_ts - start_ts if end_ts else time.time() - start_ts
                m, s = divmod(int(duration), 60)
                h, m = divmod(m, 60)
                time_str = f"{h:02d}:{m:02d}:{s:02d}"

            set_item(10, time_str)
