"""Aggregate information panel displaying dataset summary statistics."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGroupBox,
    QHeaderView,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from XBrainLab.backend.load_data import DataType
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.styles.theme import Theme


class AggregateInfoPanel(QGroupBox):
    """A grouped information panel displaying aggregate dataset statistics.

    Shows key dataset metrics (type, subjects, channels, sample rate, etc.)
    in a two-column table format. Auto-registers with ``InfoPanelService``
    when available on the parent widget.

    Attributes:
        table: QTableWidget displaying key-value data rows.
        row_map: Dictionary mapping metric names to table row indices.

    """

    def __init__(self, parent=None):
        """Initialize the aggregate info panel.

        Args:
            parent: Optional parent widget. If the parent has an
                ``info_service`` attribute, the panel auto-registers.

        """
        super().__init__("Aggregate Information", parent)
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

        self.table.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: {Theme.BACKGROUND_MID};
                border: 1px solid #3e3e42;
                border-radius: 4px;
                color: {Theme.TEXT_MUTED};
            }}
            QTableWidget::item {{
                padding: 4px;
                border: none;
            }}
            """,
        )

        header = self.table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)

        keys = [
            "Type",
            "Total Files",
            "Subjects",
            "Sessions",
            "Total Epochs",
            "Total Events",
            "Channel",
            "Sample rate",
            "tmin (sec)",
            "duration (sec)",
            "Highpass",
            "Lowpass",
            "Classes",
        ]

        self.table.setRowCount(len(keys))
        self.row_map = {}

        for i, key in enumerate(keys):
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

        main_layout.addWidget(self.table)

        # Set height based on content
        v_header = self.table.verticalHeader()
        if v_header is not None:
            v_header.setDefaultSectionSize(25)

        # Set height based on content
        # 25px per row + 2px for borders/margins (tight fit)
        total_height = len(keys) * 25 + 2
        self.table.setMinimumHeight(150)  # Allow shrinking
        self.table.setMaximumHeight(total_height + 5)  # Minimal buffer

        # Limit the GroupBox height so it doesn't consume extra space when expanded
        # Table height + padding for GroupBox title (approx 20px) + margins
        # (approx 10px)
        self.setMaximumHeight(total_height + 35)

        self.setMinimumWidth(200)
        # Use Expanding to ensure it takes up available space up to MaximumHeight
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.table.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )

        # Apply GroupBox Style
        self.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)

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

        subject_set = set()
        session_set = set()
        classes_set = set()

        total_epochs = 0
        total_events = 0

        first_data = data_list[0]

        for data in data_list:
            subject_set.add(data.get_subject_name())
            session_set.add(data.get_session_name())
            try:
                _, event_id = data.get_event_list()
                if event_id:
                    classes_set.update(event_id)
            except Exception as e:
                logger.warning("Failed to get event list for data: %s", e)

            total_epochs += data.get_epochs_length()

            try:
                if data.is_raw():
                    events, _ = data.get_event_list()
                    if events is not None:
                        total_events += len(events)
                else:
                    total_events += data.get_epochs_length()
            except Exception as e:
                logger.warning("Failed to count events: %s", e)

        tmin = "None"
        duration = "None"

        if not first_data.is_raw():
            tmin = str(first_data.get_tmin())
            try:
                dur_val = (
                    int(first_data.get_epoch_duration() * 100 / first_data.get_sfreq())
                    / 100
                )
                duration = str(dur_val)
            except Exception as e:
                logger.warning("Failed to calc duration: %s", e)
                duration = "?"

        highpass, lowpass = first_data.get_filter_range()
        text_type = DataType.RAW.value if first_data.is_raw() else DataType.EPOCH.value

        self.set_val("Type", str(text_type))
        self.set_val("Total Files", str(len(data_list)))
        self.set_val("Subjects", str(len(subject_set)))
        self.set_val("Sessions", str(len(session_set)))
        self.set_val("Total Epochs", str(total_epochs))
        self.set_val("Total Events", str(total_events))
        self.set_val("Channel", str(first_data.get_nchan()))
        self.set_val("Sample rate", str(first_data.get_sfreq()))
        self.set_val("tmin (sec)", tmin)
        self.set_val("duration (sec)", duration)
        self.set_val("Highpass", f"{highpass:.2f}")
        self.set_val("Lowpass", f"{lowpass:.2f}")
        self.set_val("Classes", str(len(classes_set)))

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

    def reset_labels(self):
        """Reset all metric values to the default placeholder ``'-'``."""
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 1)
            if item:
                item.setText("-")
