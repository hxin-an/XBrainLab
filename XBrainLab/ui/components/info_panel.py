"""Aggregate information panel displaying dataset summary statistics."""

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QFrame,
    QGroupBox,
    QHeaderView,
    QLabel,
    QLayout,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.styles.theme import Theme

INFO_ROW_MIN_HEIGHT = 22
INFO_ROW_VERTICAL_PADDING = 2
INFO_TABLE_FRAME_BUFFER = 6
INFO_GROUP_VERTICAL_BUFFER = 42
INFO_KEY_COLUMN_PADDING = 20
INFO_VALUE_COLUMN_PADDING = 16
INFO_TABLE_HORIZONTAL_BUFFER = 0
INFO_EMPTY_HEIGHT = 66

_SUMMARY_KEYS = (
    "Type",
    "EEG files",
    "Subjects",
    "Sessions",
    "EEG epochs",
    "EEG events",
    "Channels",
    "Sampling rate",
    "EEG epoch start",
    "EEG epoch duration",
    "High-pass filter",
    "Low-pass filter",
    "Training classes",
)


class SidebarScrollArea(QScrollArea):
    """Single responsive scroll owner for an action-bearing sidebar."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("SidebarScrollArea")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored,
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.content = QWidget(self)
        self.content.setObjectName("SidebarScrollContent")
        self.content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(10, 20, 10, 20)
        self.content_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.setWidget(self.content)


class AggregateInfoPanel(QGroupBox):
    """A grouped information panel displaying aggregate dataset statistics.

    Shows key dataset metrics (type, subjects, channels, sample rate, etc.)
    in a two-column table format. Auto-registers with ``InfoPanelService``
    when available on the parent widget.

    Attributes:
        table: QTableWidget displaying key-value data rows.
        row_map: Dictionary mapping metric names to table row indices.

    """

    presentation_changed = pyqtSignal()

    def __init__(self, parent=None):
        """Initialize the aggregate info panel.

        Args:
            parent: Optional parent widget. If the parent has an
                ``info_service`` attribute, the panel auto-registers.

        """
        super().__init__("Data Summary", parent)
        self._has_data = False
        self.init_ui()

        # Auto-register with InfoPanelService if available
        if parent and hasattr(parent, "info_service"):
            parent.info_service.register(self)

    def init_ui(self):
        """Build the table layout with predefined metric rows."""
        # Main Layout for the GroupBox
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        main_layout.setContentsMargins(0, 8, 0, 0)  # Space for title

        # Use QTableWidget to match TrainingPanel's Configuration Summary
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        v_header = self.table.verticalHeader()
        if v_header is not None:
            v_header.setVisible(False)
        h_header = self.table.horizontalHeader()
        if h_header is not None:
            h_header.setVisible(False)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.table.installEventFilter(self)

        self.table.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: {Theme.BACKGROUND_MID};
                border: 1px solid #3e3e42;
                border-radius: 4px;
                color: {Theme.TEXT_MUTED};
            }}
            QTableWidget::item {{
                padding: 1px 4px;
                border: none;
            }}
            """,
        )

        header = self.table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)

        self.empty_label = QLabel("No EEG data loaded")
        self.empty_label.setObjectName("DataSummaryEmpty")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(
            f"color: {Theme.TEXT_SECONDARY}; padding: 12px 4px;"
        )
        main_layout.addWidget(self.empty_label)

        self.table.setRowCount(len(_SUMMARY_KEYS))
        self.row_map = {}

        for i, key in enumerate(_SUMMARY_KEYS):
            # Key Item
            key_item = QTableWidgetItem(key)
            key_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(i, 0, key_item)

            # Value Item
            val_item = QTableWidgetItem("-")
            val_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            val_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            )
            self.table.setItem(i, 1, val_item)

            self.row_map[key] = i

        self._refresh_key_column_width()
        main_layout.addWidget(self.table)

        v_header = self.table.verticalHeader()
        if v_header is not None:
            v_header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self._refresh_table_metrics()

        self.setMinimumWidth(200)
        # Use Expanding to ensure it takes up available space up to MaximumHeight
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.table.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )

        # Apply GroupBox Style
        self.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        self.reset_labels()

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        """Keep metric labels readable after font or DPI-related changes."""
        super().changeEvent(event)
        if event.type() in {
            QEvent.Type.FontChange,
            QEvent.Type.ApplicationFontChange,
        } and hasattr(self, "table"):
            self._refresh_table_metrics()
            self.presentation_changed.emit()

    def eventFilter(self, watched, event):  # noqa: N802
        """Respond when the table receives a font change independently."""
        if watched is getattr(self, "table", None) and event.type() in {
            QEvent.Type.FontChange,
            QEvent.Type.ApplicationFontChange,
        }:
            self._refresh_table_metrics()
            self.presentation_changed.emit()
        return super().eventFilter(watched, event)

    @property
    def has_data(self) -> bool:
        """Return whether this presentation currently contains dataset metrics."""
        return self._has_data

    def _refresh_key_column_width(self) -> None:
        visible_rows = [
            row
            for row in range(self.table.rowCount())
            if not self.table.isRowHidden(row)
        ]
        rows = visible_rows or list(range(self.table.rowCount()))
        key_width = max(
            (
                self.table.fontMetrics().horizontalAdvance(item.text())
                for row in rows
                if (item := self.table.item(row, 0)) is not None
            ),
            default=0,
        )
        self.table.setColumnWidth(0, key_width + INFO_KEY_COLUMN_PADDING)

    def minimum_readable_table_width(self) -> int:
        """Return the width needed by the currently visible key/value cells."""
        metrics = self.table.fontMetrics()
        visible_rows = [
            row
            for row in range(self.table.rowCount())
            if not self.table.isRowHidden(row)
        ]
        if not visible_rows:
            return 0
        key_width = max(
            metrics.horizontalAdvance(item.text())
            for row in visible_rows
            if (item := self.table.item(row, 0)) is not None
        )
        value_width = max(
            metrics.horizontalAdvance(item.text())
            for row in visible_rows
            if (item := self.table.item(row, 1)) is not None
        )
        return (
            key_width
            + INFO_KEY_COLUMN_PADDING
            + value_width
            + INFO_VALUE_COLUMN_PADDING
            + INFO_TABLE_HORIZONTAL_BUFFER
        )

    def _refresh_table_metrics(self) -> None:
        """Fit rows and key labels to the active font and display scale."""
        row_height = max(
            INFO_ROW_MIN_HEIGHT,
            self.table.fontMetrics().height() + INFO_ROW_VERTICAL_PADDING,
        )
        header = self.table.verticalHeader()
        if header is not None:
            header.setMinimumSectionSize(row_height)
            header.setDefaultSectionSize(row_height)
            for row in range(self.table.rowCount()):
                header.resizeSection(row, row_height)
        self._refresh_key_column_width()
        visible_count = sum(
            not self.table.isRowHidden(row) for row in range(self.table.rowCount())
        )
        if visible_count:
            self._fit_visible_rows(visible_count)

    def update_info(self, loaded_data_list=None, preprocessed_data_list=None):
        """Update displayed metrics from the provided data lists.

        If ``preprocessed_data_list`` is non-empty it takes precedence over
        ``loaded_data_list`` to ensure consistent information.

        Args:
            loaded_data_list: List of loaded data objects, or ``None``.
            preprocessed_data_list: List of preprocessed data objects,
                or ``None``.

        """
        # Always use preprocessed data if available, otherwise loaded data.
        # This ensures consistent information across all panels.
        data_list = (
            preprocessed_data_list if preprocessed_data_list else loaded_data_list
        )

        if not data_list:
            self.reset_labels()
            return

        subject_set: set[str] = set()
        session_set: set[str] = set()
        classes_set = set()

        total_epochs = 0
        total_events = 0
        event_count_available = False

        first_data = data_list[0]

        for data in data_list:
            subject = self._available_text(data.get_subject_name())
            session = self._available_text(data.get_session_name())
            if subject:
                subject_set.add(subject)
            if session:
                session_set.add(session)
            event_summary = self._event_summary_for_render(data)
            classes_set.update(event_summary.get("labels", []))

            total_epochs += data.get_epochs_length()

            count = event_summary.get("count")
            if isinstance(count, int) and count > 0:
                total_events += count
                event_count_available = True

        tmin: str | None = None
        duration: str | None = None

        if not first_data.is_raw():
            tmin_value = first_data.get_tmin()
            if tmin_value is not None:
                tmin = self._format_measurement(tmin_value, "s")
            try:
                dur_val = (
                    int(first_data.get_epoch_duration() * 100 / first_data.get_sfreq())
                    / 100
                )
                duration = f"{self._format_number(dur_val)} s"
            except Exception as e:
                logger.warning("Failed to calc duration: %s", e)

        highpass, lowpass = first_data.get_filter_range()
        is_raw = bool(first_data.is_raw())
        channels = first_data.get_nchan()
        sample_rate = first_data.get_sfreq()
        values: dict[str, str | None] = {
            "Type": "Continuous EEG" if is_raw else "Epochs",
            "EEG files": str(len(data_list)),
            "Subjects": str(len(subject_set)) if subject_set else None,
            "Sessions": str(len(session_set)) if session_set else None,
            "EEG epochs": (
                str(total_epochs) if not is_raw and total_epochs > 0 else None
            ),
            "EEG events": str(total_events) if event_count_available else None,
            "Channels": str(channels) if self._positive_number(channels) else None,
            "Sampling rate": (
                self._format_measurement(sample_rate, "Hz")
                if self._positive_number(sample_rate)
                else None
            ),
            "EEG epoch start": tmin,
            "EEG epoch duration": duration,
            "High-pass filter": (
                self._format_measurement(highpass, "Hz")
                if highpass is not None
                else None
            ),
            "Low-pass filter": (
                self._format_measurement(lowpass, "Hz") if lowpass is not None else None
            ),
            "Training classes": str(len(classes_set)) if classes_set else None,
        }
        self._render_values(values)

    @staticmethod
    def _event_summary_for_render(data) -> dict:
        summary_method = getattr(data, "get_event_summary", None)
        if callable(summary_method):
            try:
                summary = summary_method(allow_scan=False)
                if isinstance(summary, dict):
                    return summary
            except Exception as e:
                logger.warning("Failed to get cached event summary for data: %s", e)
        try:
            events, event_id = data.get_event_list()
            labels = sorted(str(label) for label in event_id)
            count = len(events) if data.is_raw() and events is not None else None
            if count is None:
                count = data.get_epochs_length()
        except Exception as e:
            logger.warning("Failed to count events: %s", e)
            return {"available": False, "count": 0, "labels": []}
        return {
            "available": bool(event_id),
            "count": count,
            "labels": labels,
            "source": "compatibility",
            "scanned": True,
        }

    def set_val(self, key, value):
        """Set the display value for a specific metric row.

        Args:
            key: The metric name (must exist in ``row_map``).
            value: The string value to display.

        """
        if key in self.row_map:
            row = self.row_map[key]
            item = self.table.item(row, 1)
            if item:
                item.setText(value)
                item.setToolTip(value)

    def _render_values(self, values: dict[str, str | None]) -> None:
        self.empty_label.setVisible(False)
        self.table.setVisible(True)
        visible_count = 0
        for key in _SUMMARY_KEYS:
            row = self.row_map[key]
            value = values.get(key)
            available = bool(str(value).strip()) if value is not None else False
            self.table.setRowHidden(row, not available)
            if not available:
                continue
            self.set_val(key, str(value))
            visible_count += 1
        self._refresh_key_column_width()
        self._fit_visible_rows(visible_count)
        self._has_data = visible_count > 0
        self.presentation_changed.emit()

    def _fit_visible_rows(self, visible_count: int) -> None:
        if visible_count <= 0:
            self.table.setVisible(False)
            self.empty_label.setVisible(True)
            self.setMinimumHeight(INFO_EMPTY_HEIGHT)
            self.setMaximumHeight(INFO_EMPTY_HEIGHT)
            return
        row_height = max(
            INFO_ROW_MIN_HEIGHT,
            self.table.fontMetrics().height() + INFO_ROW_VERTICAL_PADDING,
        )
        total_height = visible_count * row_height + INFO_TABLE_FRAME_BUFFER
        self.table.setMinimumHeight(total_height)
        self.table.setMaximumHeight(total_height)
        group_height = total_height + INFO_GROUP_VERTICAL_BUFFER
        self.setMinimumHeight(group_height)
        self.setMaximumHeight(group_height)

    @staticmethod
    def _available_text(value: object) -> str:
        text = str(value or "").strip()
        return "" if text.casefold() in {"", "-", "none", "unknown", "n/a"} else text

    @staticmethod
    def _positive_number(value: object) -> bool:
        try:
            return float(str(value)) > 0
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _format_number(value: object) -> str:
        try:
            number = float(str(value))
        except (TypeError, ValueError):
            return ""
        return str(int(number)) if number.is_integer() else f"{number:g}"

    @classmethod
    def _format_measurement(cls, value: object, unit: str) -> str | None:
        number = cls._format_number(value)
        return f"{number} {unit}" if number else None

    def reset_labels(self):
        """Hide unavailable metric rows and show one product empty state."""
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 1)
            if item:
                item.setText("")
                item.setToolTip("")
            self.table.setRowHidden(i, True)
        self._fit_visible_rows(0)
        self._has_data = False
        self.presentation_changed.emit()
