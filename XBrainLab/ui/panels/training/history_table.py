"""Training history table widget showing per-run status and live metrics."""

import time
from typing import ClassVar

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
)

from XBrainLab.backend.training.record.key import RecordKey, TrainRecordKey
from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.styles.theme import Theme


class TrainingHistoryTable(QTableWidget):
    """Table widget displaying real-time training history.

    Shows group, run, model, status, progress, and live metrics
    (loss, accuracy, learning rate, elapsed time) for every training
    record.

    Attributes:
        selection_changed_identity: Signal emitted with the selected
            plan/run identity when the user clicks a row.
        row_identity_by_index: Mapping of table row to detached identity.

    """

    selection_changed_identity = pyqtSignal(object)
    MAX_VISIBLE_ROWS = 5
    ROW_HEIGHT = 30
    HEADER_PADDING = 16
    KEY_COLUMN_PADDING = 20
    KEY_COLUMN_MAX_CHARACTERS = (28, 20, 22, 14)
    BASE_COLUMN_WIDTHS = (76, 60, 120, 88, 64, 76, 76, 72, 72, 76, 64, 80)
    FLEX_COLUMN_WEIGHTS: ClassVar[dict[int, float]] = {
        2: 0.5,
        3: 0.2,
        11: 0.3,
    }

    def __init__(self, parent=None):
        """Initialize the training history table.

        Args:
            parent: Optional parent widget.

        """
        super().__init__(parent)
        self.setObjectName("TrainingHistoryTable")
        self._syncing_geometry = False
        self._syncing_columns = False
        self.row_identity_by_index = {}
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
            "Training epochs",
            "Train Loss",
            "Train Acc",
            "Val Loss",
            "Val Acc",
            "Test Acc",
            "LR",
            "Time",
        ]
        self.setColumnCount(12)
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
        self.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel,
        )

        # Column widths
        header = self.horizontalHeader()
        if header:
            header_font = header.font()
            header_font.setBold(True)
            header.setFont(header_font)
            for i in range(self.columnCount()):
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)

        header_metrics = (
            header.fontMetrics() if header is not None else self.fontMetrics()
        )
        content_widths: list[int] = []
        minimum_widths: list[int] = []
        for column, preferred_width in enumerate(self.BASE_COLUMN_WIDTHS):
            header_item = self.horizontalHeaderItem(column)
            header_text = (
                header_item.text() if header_item is not None else header_labels[column]
            )
            readable_width = (
                header_metrics.horizontalAdvance(header_text) + self.HEADER_PADDING
            )
            minimum_widths.append(readable_width)
            width = max(preferred_width, readable_width)
            content_widths.append(width)
            self.setColumnWidth(column, width)

        self._content_column_widths = content_widths
        self._minimum_column_widths = minimum_widths
        self._minimum_content_width = sum(minimum_widths)

        if header:
            header.setStretchLastSection(False)

        self.itemSelectionChanged.connect(self._on_selection_changed)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._fit_columns_to_viewport()
        self._sync_content_height()
        self._position_empty_state()

    def preferred_content_height(self) -> int:
        """Return the stable height for the current table width."""
        return self._target_content_height()

    def _target_content_height(self) -> int:
        # Keep five complete rows visible even when the expanded metric set
        # requires a horizontal scrollbar at narrower product widths.
        header = self.horizontalHeader()
        vertical_header = self.verticalHeader()
        header_height = header.sizeHint().height() if header is not None else 0
        row_height = (
            vertical_header.defaultSectionSize()
            if vertical_header is not None
            else self.ROW_HEIGHT
        )
        horizontal_scrollbar = self.horizontalScrollBar()
        scrollbar_height = (
            horizontal_scrollbar.sizeHint().height()
            if self._horizontal_scrollbar_expected()
            and horizontal_scrollbar is not None
            else 0
        )
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
        if header is None or viewport is None:
            return False
        content_width = getattr(self, "_minimum_content_width", header.length())
        return content_width > max(0, viewport.width())

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
            self._fit_columns_to_viewport()
            self.updateGeometries()
            target_height = self._target_content_height()
            geometry_changed = policy_changed or self.height() != target_height
            if geometry_changed:
                self.setFixedHeight(target_height)
                self.updateGeometries()
                self._fit_columns_to_viewport()
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
        """Emit the selected detached row identity."""
        selected_items = self.selectedItems()
        if not selected_items:
            self.selection_changed_identity.emit(None)
            return

        row = selected_items[0].row()
        identity = self.row_identity_by_index.get(row)
        if identity is not None:
            self.selection_changed_identity.emit(dict(identity))

    def clear_history(self):
        """Remove all rows and reset the internal row mapping."""
        self.setRowCount(0)
        self.row_identity_by_index.clear()
        self._sync_content_height()

    def update_table(self, target_rows):
        """Alias for ``update_history`` to satisfy the panel interface.

        Args:
            target_rows: List of formatted row dictionaries.

        """
        self.update_history(target_rows)

    def update_history(self, target_rows):
        """Update the table with formatted training history rows.

        Each entry is a detached application row with primitive identity,
        lifecycle, progress, timestamp, and metric fields.

        Args:
            target_rows: List of dictionaries describing each row.

        """
        if self.rowCount() != len(target_rows):
            self.setRowCount(len(target_rows))
        self.row_identity_by_index.clear()
        terminal_devices: list[str] = []

        for row_idx, data in enumerate(target_rows):
            group_name = data["group_name"]
            run_name = data["run_name"]
            model_name = data["model_name"]

            identity = data.get("identity", {})
            if isinstance(identity, dict):
                self.row_identity_by_index[row_idx] = dict(identity)

            epoch = int(data.get("epoch", 0))
            max_epochs = int(data.get("max_epochs", 0))
            status = str(data.get("status", "Pending"))
            runtime_device = str(data.get("runtime_device") or "").strip()
            if status in {"Completed", "Completed early"} and runtime_device:
                terminal_devices.append(runtime_device)

            def set_item(col, text, r=row_idx, tooltip=None):
                item = self.item(r, col)
                if not item:
                    item = QTableWidgetItem()
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.setItem(r, col, item)
                if item.text() != text:
                    item.setText(text)
                item.setToolTip(tooltip if tooltip is not None else text)

            set_item(0, group_name)
            set_item(1, run_name)
            set_item(2, model_name)
            detail = data.get("status_detail")
            set_item(
                3,
                status,
                tooltip=(
                    f"{status}\n{detail}"
                    if isinstance(detail, str) and detail.strip()
                    else status
                ),
            )
            set_item(4, f"{epoch}/{max_epochs}")

            metrics = data.get("metrics", {})
            train_metrics = (
                metrics.get("train", {}) if isinstance(metrics, dict) else {}
            )
            validation_metrics = (
                metrics.get("validation", {}) if isinstance(metrics, dict) else {}
            )
            test_metrics = metrics.get("test", {}) if isinstance(metrics, dict) else {}

            def get_last(key, source):
                values = source.get(key, []) if hasattr(source, "get") else []
                if values:
                    val = values[-1]
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        return 0.0
                return 0.0

            def get_last_optional(key, source):
                values = source.get(key, []) if hasattr(source, "get") else []
                if not values:
                    return None
                try:
                    return float(values[-1])
                except (ValueError, TypeError):
                    return None

            train_loss = get_last(TrainRecordKey.LOSS, train_metrics)
            train_acc = get_last(TrainRecordKey.ACC, train_metrics)
            val_loss = get_last(RecordKey.LOSS, validation_metrics)
            val_acc = get_last(RecordKey.ACC, validation_metrics)
            test_acc = get_last_optional(RecordKey.ACC, test_metrics)
            lr = get_last(TrainRecordKey.LR, train_metrics)

            val_loss_str = f"{val_loss:.4f}" if val_loss != 0 else "N/A"
            val_acc_str = f"{val_acc:.2f}%" if val_acc != 0 else "N/A"
            test_acc_str = (
                f"{test_acc:.2f}%"
                if test_acc is not None
                else ("N/A" if status in {"Completed", "Completed early"} else "—")
            )

            set_item(5, f"{train_loss:.4f}")
            set_item(6, f"{train_acc:.2f}%")
            set_item(7, val_loss_str)
            set_item(8, val_acc_str)
            set_item(9, test_acc_str)
            set_item(10, f"{lr:.4g}")

            time_str = "-"
            start_ts = data.get("start_timestamp")
            end_ts = data.get("end_timestamp")

            if start_ts:
                duration = end_ts - start_ts if end_ts else time.time() - start_ts
                m, s = divmod(int(duration), 60)
                h, m = divmod(m, 60)
                time_str = f"{h:02d}:{m:02d}:{s:02d}"

            set_item(11, time_str)

        self.setProperty("terminalTrainingDevices", terminal_devices)

        self._fit_key_columns_to_content()
        self._sync_content_height()

    def _fit_key_columns_to_content(self) -> None:
        """Keep identity text readable, then use spare width without scrolling."""
        content_widths: list[int] = list(self.BASE_COLUMN_WIDTHS)
        minimum_widths: list[int] = [0] * self.columnCount()
        header = self.horizontalHeader()
        header_metrics = (
            header.fontMetrics() if header is not None else self.fontMetrics()
        )
        for column in range(self.columnCount()):
            item = self.horizontalHeaderItem(column)
            header_text = item.text() if item is not None else ""
            minimum_widths[column] = (
                header_metrics.horizontalAdvance(header_text) + self.HEADER_PADDING
            )
        for column in range(self.columnCount()):
            required_width = minimum_widths[column]
            for row in range(self.rowCount()):
                item = self.item(row, column)
                if item is None:
                    continue
                required_width = max(
                    required_width,
                    self.fontMetrics().horizontalAdvance(item.text())
                    + self.KEY_COLUMN_PADDING,
                )
            if column < len(self.KEY_COLUMN_MAX_CHARACTERS):
                # Cap unusually long identity values by a font-relative character
                # budget. A fixed pixel cap clips ordinary names under Windows DPI
                # and font metrics even though horizontal scrolling is available.
                max_width = (
                    self.fontMetrics().averageCharWidth()
                    * self.KEY_COLUMN_MAX_CHARACTERS[column]
                    + self.KEY_COLUMN_PADDING
                )
                required_width = min(
                    required_width,
                    max_width,
                )
            minimum_widths[column] = required_width
            content_widths[column] = max(
                content_widths[column],
                required_width,
            )
        self._content_column_widths = content_widths
        self._minimum_column_widths = minimum_widths
        self._minimum_content_width = sum(minimum_widths)
        self._fit_columns_to_viewport()

    @staticmethod
    def _shrink_widths_to_fit(
        preferred: list[int],
        minimum: list[int],
        available: int,
    ) -> list[int]:
        """Shrink preferred widths without crossing readable text bounds."""
        widths = list(preferred)
        deficit = max(0, sum(widths) - available)
        while deficit:
            candidates = [
                column for column, width in enumerate(widths) if width > minimum[column]
            ]
            if not candidates:
                break
            share = max(1, deficit // len(candidates))
            for column in candidates:
                reduction = min(
                    widths[column] - minimum[column],
                    share,
                    deficit,
                )
                widths[column] -= reduction
                deficit -= reduction
                if deficit == 0:
                    break
        return widths

    def _fit_columns_to_viewport(self) -> None:
        """Fit the standard surface and scroll only when genuinely narrow."""
        if self._syncing_columns:
            return
        viewport = self.viewport()
        if viewport is None:
            return
        self._syncing_columns = True
        try:
            preferred_widths: list[int] = list(
                getattr(self, "_content_column_widths", self.BASE_COLUMN_WIDTHS)
            )
            minimum_widths: list[int] = list(
                getattr(self, "_minimum_column_widths", preferred_widths)
            )
            available = max(0, viewport.width())
            needs_horizontal_scroll = sum(minimum_widths) > available
            horizontal_policy = (
                Qt.ScrollBarPolicy.ScrollBarAsNeeded
                if needs_horizontal_scroll
                else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            if self.horizontalScrollBarPolicy() != horizontal_policy:
                self.setHorizontalScrollBarPolicy(horizontal_policy)
                self.updateGeometries()
                available = max(0, viewport.width())
                needs_horizontal_scroll = sum(minimum_widths) > available
            widths = (
                preferred_widths
                if needs_horizontal_scroll
                else self._shrink_widths_to_fit(
                    preferred_widths,
                    minimum_widths,
                    available,
                )
            )
            extra = available - sum(widths)
            if extra > 0:
                assigned = 0
                weighted_columns = tuple(self.FLEX_COLUMN_WEIGHTS)
                for column in weighted_columns[:-1]:
                    addition = round(extra * self.FLEX_COLUMN_WEIGHTS[column])
                    widths[column] += addition
                    assigned += addition
                widths[weighted_columns[-1]] += extra - assigned
            for column, width in enumerate(widths):
                if self.columnWidth(column) != width:
                    self.setColumnWidth(column, width)
        finally:
            self._syncing_columns = False
