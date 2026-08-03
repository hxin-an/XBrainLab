"""Aggregate information panel displaying dataset summary statistics."""

from collections.abc import Mapping, Sequence
from typing import Any

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QFrame,
    QGroupBox,
    QHeaderView,
    QLayout,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.styles.theme import Theme

INFO_ROW_MIN_HEIGHT = 22
INFO_ROW_VERTICAL_PADDING = 8
INFO_TABLE_FRAME_BUFFER = 6
INFO_GROUP_VERTICAL_BUFFER = 42
INFO_KEY_COLUMN_PADDING = 16
INFO_VALUE_COLUMN_PADDING = 16
INFO_TABLE_HORIZONTAL_BUFFER = 0
INFO_PANEL_MIN_WIDTH = 200

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

_SUMMARY_LABELS = {
    "EEG epochs": "Epochs",
    "EEG events": "Events",
    "EEG epoch start": "Epoch start",
    "EEG epoch duration": "Epoch length",
    "Sampling rate": "Sample rate",
    "High-pass filter": "High pass",
    "Low-pass filter": "Low pass",
    "Training classes": "Classes",
}


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
        self.viewport().setStyleSheet(
            f"background-color: {Theme.BACKGROUND_MID}; border: none;",
        )

        self.content = QWidget(self)
        self.content.setObjectName("SidebarScrollContent")
        self.content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.content.setStyleSheet(
            f"background-color: {Theme.BACKGROUND_MID}; border: none;",
        )
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
            h_header.setMinimumSectionSize(20)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )

        self.table.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: {Theme.BACKGROUND_MID};
                border: 1px solid #3e3e42;
                border-radius: 4px;
                color: {Theme.TEXT_MUTED};
            }}
            QTableWidget::item {{
                padding: 4px 2px;
                border: none;
            }}
            """,
        )

        header = self.table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)

        self.table.setRowCount(len(_SUMMARY_KEYS))
        self.row_map = {}

        for i, key in enumerate(_SUMMARY_KEYS):
            label = _SUMMARY_LABELS.get(key, key)
            # Key Item
            key_item = QTableWidgetItem(label)
            key_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            key_item.setToolTip(label)
            self.table.setItem(i, 0, key_item)

            # Value Item
            val_item = QTableWidgetItem("-")
            val_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            val_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            )
            self.table.setItem(i, 1, val_item)

            self.row_map[key] = i

        main_layout.addWidget(self.table)

        v_header = self.table.verticalHeader()
        if v_header is not None:
            v_header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self._refresh_table_metrics()

        self.setMinimumWidth(INFO_PANEL_MIN_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.table.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )

        # Apply GroupBox Style
        self.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        self.reset_labels()

    def changeEvent(self, event: QEvent | None) -> None:  # noqa: N802
        """Keep metric labels readable after font or DPI-related changes."""
        super().changeEvent(event)
        if (
            event is not None
            and event.type()
            in {
                QEvent.Type.FontChange,
                QEvent.Type.ApplicationFontChange,
            }
            and hasattr(self, "table")
        ):
            self._refresh_table_metrics()
            self.presentation_changed.emit()

    def showEvent(self, event: QShowEvent | None) -> None:  # noqa: N802
        """Restore deterministic column geometry when a hidden page returns."""
        super().showEvent(event)
        self._refresh_table_metrics()

    @property
    def has_data(self) -> bool:
        """Return whether this presentation currently contains dataset metrics."""
        return self._has_data

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
        """Keep the accepted fixed 13-row summary readable at the active font."""
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
        horizontal_header = self.table.horizontalHeader()
        if horizontal_header is not None:
            key_width = (
                max(
                    self.table.fontMetrics().horizontalAdvance(item.text())
                    for row in range(self.table.rowCount())
                    if (item := self.table.item(row, 0)) is not None
                )
                + INFO_KEY_COLUMN_PADDING
            )
            horizontal_header.setSectionResizeMode(
                0,
                QHeaderView.ResizeMode.Fixed,
            )
            self.table.setColumnWidth(0, key_width)
            horizontal_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        total_height = self.table.rowCount() * row_height + INFO_TABLE_FRAME_BUFFER
        self.table.setFixedHeight(total_height)
        self.setFixedHeight(total_height + INFO_GROUP_VERTICAL_BUFFER)
        self.table.updateGeometry()
        self.updateGeometry()

    def update_info(
        self,
        loaded_data_list: Sequence[Mapping[str, Any]] | None = None,
        preprocessed_data_list: Sequence[Mapping[str, Any]] | None = None,
    ) -> None:
        """Update displayed metrics from detached application publication rows.

        If ``preprocessed_data_list`` is non-empty it takes precedence over
        ``loaded_data_list``. Non-Mapping payloads fail closed to the empty
        skeleton rather than inspecting live EEG domain objects.

        Args:
            loaded_data_list: Detached loaded-data rows, or ``None``.
            preprocessed_data_list: Detached preprocessed-data rows, or ``None``.

        """
        rows = preprocessed_data_list if preprocessed_data_list else loaded_data_list

        if not rows or not all(isinstance(row, Mapping) for row in rows):
            self.reset_labels()
            return

        self._update_info_from_rows(rows)

    def _update_info_from_rows(
        self,
        rows: Sequence[Mapping[str, Any]],
    ) -> None:
        """Render application-owned detached data rows."""
        subject_set = {
            text for row in rows if (text := self._available_text(row.get("subject")))
        }
        session_set = {
            text for row in rows if (text := self._available_text(row.get("session")))
        }
        classes_set: set[str] = set()
        total_epochs = 0
        total_events = 0
        event_count_available = False
        for row in rows:
            epochs = row.get("epochs_length")
            if isinstance(epochs, int) and not isinstance(epochs, bool):
                total_epochs += max(0, epochs)
            event = row.get("event")
            if not isinstance(event, Mapping):
                continue
            labels = event.get("labels")
            if isinstance(labels, list):
                classes_set.update(str(label) for label in labels)
            count = event.get("count")
            if isinstance(count, int) and not isinstance(count, bool) and count > 0:
                total_events += count
                event_count_available = True

        first = rows[0]
        is_raw = first.get("is_raw") is True
        sample_rate = self._number_or_none(first.get("sampling_frequency"))
        epoch_samples = self._number_or_none(first.get("epoch_duration_samples"))
        duration = (
            self._format_measurement(round(epoch_samples / sample_rate, 2), "s")
            if not is_raw
            and sample_rate is not None
            and sample_rate > 0
            and epoch_samples is not None
            else None
        )
        tmin_value = self._number_or_none(first.get("tmin"))
        highpass = self._number_or_none(first.get("highpass"))
        lowpass = self._number_or_none(first.get("lowpass"))
        channels = first.get("n_channels")
        values: dict[str, str | None] = {
            "Type": "Continuous EEG" if is_raw else "Epochs",
            "EEG files": str(len(rows)),
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
            "EEG epoch start": (
                self._format_measurement(tmin_value, "s")
                if not is_raw and tmin_value is not None
                else None
            ),
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
    def _number_or_none(value: Any) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)

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
                if item.text() != value:
                    item.setText(value)
                if item.toolTip() != value:
                    item.setToolTip(value)

    def _render_values(self, values: dict[str, str | None]) -> None:
        available_count = 0
        for key in _SUMMARY_KEYS:
            value = values.get(key)
            available = bool(str(value).strip()) if value is not None else False
            self.set_val(key, str(value) if available else "-")
            available_count += int(available)
        self._has_data = available_count > 0
        self.presentation_changed.emit()

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
        """Keep the stable table skeleton and reset unavailable values to ``-``."""
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 1)
            if item:
                if item.text() != "-":
                    item.setText("-")
                if item.toolTip() != "-":
                    item.setToolTip("-")
        self._has_data = False
        self.presentation_changed.emit()
