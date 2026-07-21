"""Training history table widget showing per-run status and live metrics."""

import time

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHeaderView, QLabel, QTableWidget, QTableWidgetItem

from XBrainLab.backend.training.record.key import RecordKey, TrainRecordKey
from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.styles.theme import Theme


class TrainingHistoryTable(QTableWidget):
    """Table widget displaying real-time training history.

    Shows group, run, model, status, progress, and live metrics
    (loss, accuracy, learning rate, elapsed time) for every training
    record.

    Attributes:
        selection_changed_record: Signal emitted with the selected
            ``TrainRecord`` when the user clicks a row.
        row_map: Mapping of row index to ``(plan, record)`` tuples.

    """

    selection_changed_record = pyqtSignal(object)  # Emits record object
    MAX_VISIBLE_ROWS = 3
    ROW_HEIGHT = 30
    KEY_COLUMN_PADDING = 26
    KEY_COLUMN_MAX_WIDTHS = (220, 180, 190, 120)

    def __init__(self, parent=None):
        """Initialize the training history table.

        Args:
            parent: Optional parent widget.

        """
        super().__init__(parent)
        self._syncing_geometry = False
        self.row_map = {}  # Map row -> (plan, record)
        self._init_ui()
        self.empty_state_label = QLabel("No training runs yet", self.viewport())
        self.empty_state_label.setObjectName("TrainingHistoryEmptyState")
        self.empty_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
        )
        self.empty_state_label.setStyleSheet(
            f"background: transparent; color: {Theme.TEXT_SECONDARY}; font-size: 13px;"
        )
        self._sync_content_height()

    def _init_ui(self):
        """Configure columns, headers, widths, and styling for the table."""
        header_labels = [
            "Group",
            "Run",
            "Model",
            "Status",
            "Epochs",
            "Train Loss",
            "Train Acc",
            "Val Loss",
            "Val Acc",
            "LR",
            "Time",
        ]
        self.setColumnCount(11)
        self.setHorizontalHeaderLabels(header_labels)

        self.setStyleSheet(Stylesheets.HISTORY_TABLE)

        header_v = self.verticalHeader()
        if header_v:
            header_v.setVisible(False)
            header_v.setDefaultSectionSize(30)
            header_v.setMinimumSectionSize(28)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        # Column widths
        header = self.horizontalHeader()
        if header:
            for i in range(11):
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)

        preferred_widths = [70, 70, 130, 90, 70, 88, 88, 82, 82, 70, 82]
        header_metrics = (
            header.fontMetrics() if header is not None else self.fontMetrics()
        )
        for column, preferred_width in enumerate(preferred_widths):
            header_item = self.horizontalHeaderItem(column)
            header_text = (
                header_item.text() if header_item is not None else header_labels[column]
            )
            readable_width = header_metrics.horizontalAdvance(header_text) + 28
            self.setColumnWidth(column, max(preferred_width, readable_width))

        self._minimum_content_width = sum(
            self.columnWidth(column) for column in range(self.columnCount())
        )

        if header:
            header.setStretchLastSection(True)

        self.itemSelectionChanged.connect(self._on_selection_changed)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._sync_content_height()
        self._position_empty_state()

    def preferred_content_height(self) -> int:
        """Return the stable height for the current table width."""
        return self._target_content_height()

    def _target_content_height(self) -> int:
        # Reserve one stable viewport for the header and three complete rows.
        # A horizontal-scrollbar gutter is included only when the current width
        # actually needs it; reserving it unconditionally reveals part of the
        # next row on wider tables.
        header = self.horizontalHeader()
        vertical_header = self.verticalHeader()
        header_height = header.sizeHint().height() if header is not None else 0
        row_height = (
            vertical_header.defaultSectionSize()
            if vertical_header is not None
            else self.ROW_HEIGHT
        )
        horizontal_scrollbar = self.horizontalScrollBar()
        horizontal_overflow = self._horizontal_scrollbar_expected()
        scrollbar_height = 0
        if horizontal_overflow and horizontal_scrollbar is not None:
            scrollbar_height = horizontal_scrollbar.sizeHint().height()
        return (
            header_height
            + (row_height * self.MAX_VISIBLE_ROWS)
            + scrollbar_height
            + (2 * self.frameWidth())
        )

    def _horizontal_scrollbar_expected(self) -> bool:
        """Predict overflow without making it depend on the current row count."""
        header = self.horizontalHeader()
        viewport = self.viewport()
        vertical_scrollbar = self.verticalScrollBar()
        if header is None or viewport is None:
            return False
        reserved_width = (
            vertical_scrollbar.sizeHint().width()
            if vertical_scrollbar is not None
            else 0
        )
        content_width = getattr(self, "_minimum_content_width", header.length())
        return content_width > max(0, viewport.width() - reserved_width)

    def _sync_content_height(self) -> None:
        if self._syncing_geometry:
            return
        self._syncing_geometry = True
        has_overflow = self.rowCount() > self.MAX_VISIBLE_ROWS
        try:
            target_policy = (
                Qt.ScrollBarPolicy.ScrollBarAsNeeded
                if has_overflow
                else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            policy_changed = self.verticalScrollBarPolicy() != target_policy
            if policy_changed:
                self.setVerticalScrollBarPolicy(target_policy)
            self.updateGeometries()
            target_height = self._target_content_height()
            geometry_changed = policy_changed or self.height() != target_height
            if geometry_changed:
                self.setFixedHeight(target_height)
                self.updateGeometries()
            self.empty_state_label.setVisible(self.rowCount() == 0)
            self._position_empty_state()
            if geometry_changed:
                self.updateGeometry()
        finally:
            self._syncing_geometry = False

    def _position_empty_state(self) -> None:
        viewport = self.viewport()
        if viewport is None or not hasattr(self, "empty_state_label"):
            return
        self.empty_state_label.setGeometry(viewport.rect())
        self.empty_state_label.raise_()

    def _on_selection_changed(self):
        """Emit the selected record when the table selection changes."""
        selected_items = self.selectedItems()
        if not selected_items:
            self.selection_changed_record.emit(None)
            return

        row = selected_items[0].row()
        if row in self.row_map:
            _, record = self.row_map[row]
            self.selection_changed_record.emit(record)

    def clear_history(self):
        """Remove all rows and reset the internal row mapping."""
        self.setRowCount(0)
        self.row_map.clear()
        self._sync_content_height()

    def update_table(self, target_rows):
        """Alias for ``update_history`` to satisfy the panel interface.

        Args:
            target_rows: List of formatted row dictionaries.

        """
        self.update_history(target_rows)

    def update_history(self, target_rows):
        """Update the table with formatted training history rows.

        Each entry in *target_rows* is a dictionary with keys
        ``plan``, ``record``, ``group_name``, ``run_name``,
        ``model_name``, and optionally ``is_current_run``.

        Args:
            target_rows: List of dictionaries describing each row.

        """
        if self.rowCount() != len(target_rows):
            self.setRowCount(len(target_rows))
        self.row_map.clear()

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
            plan_status = ""
            get_status = getattr(plan, "get_training_status", None)
            if callable(get_status):
                try:
                    plan_status = str(get_status() or "")
                except Exception:
                    plan_status = ""

            if "out of memory" in plan_status.lower() or plan_status.startswith(
                "Failed",
            ):
                status = "Failed"
            elif record.is_finished():
                status = "Completed"
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

        self._fit_key_columns_to_content()
        self._sync_content_height()

    def _fit_key_columns_to_content(self) -> None:
        """Keep identity and lifecycle text readable without removing scrolling."""
        for column, maximum_width in enumerate(self.KEY_COLUMN_MAX_WIDTHS):
            required_width = self.columnWidth(column)
            for row in range(self.rowCount()):
                item = self.item(row, column)
                if item is None:
                    continue
                required_width = max(
                    required_width,
                    self.fontMetrics().horizontalAdvance(item.text())
                    + self.KEY_COLUMN_PADDING,
                )
            self.setColumnWidth(column, min(required_width, maximum_width))
