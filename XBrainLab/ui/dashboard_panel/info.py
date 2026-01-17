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


class AggregateInfoPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Aggregate Information", parent)
        self.main_window = None
        if parent and hasattr(parent, "study"):
            self.main_window = parent

        self.init_ui()

    def init_ui(self):
        # Main Layout for the GroupBox
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        main_layout.setContentsMargins(0, 8, 0, 0)  # Space for title

        # Use QTableWidget to match TrainingPanel's Configuration Summary

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setStyleSheet(
            """
            QTableWidget {
                background-color: #2d2d2d;
                border: 1px solid #3e3e42;
                border-radius: 4px;
                color: #cccccc;
            }
            QTableWidget::item {
                padding: 4px;
                border: none;
            }
        """
        )

        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )

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
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(i, 1, val_item)

            self.row_map[key] = i

        main_layout.addWidget(self.table)

        # Set height based on content
        self.table.verticalHeader().setDefaultSectionSize(25)

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
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )

    def set_main_window(self, main_window):
        self.main_window = main_window
        self.update_info()

    def update_info(self):
        if not self.main_window or not hasattr(self.main_window, "study"):
            return

        study = self.main_window.study

        # Always use preprocessed data if available, otherwise loaded data.
        # This ensures consistent information across all panels.
        data_list = (
            study.preprocessed_data_list
            if study.preprocessed_data_list
            else study.loaded_data_list
        )
        use_loaded = data_list is study.loaded_data_list

        # Fallback: If preprocessed is empty but we have epoch_data (meaning we did
        # preprocess),
        # or if we just want to show something, try loaded_data_list as fallback.
        # This handles the case where preprocessed_data_list might be cleared or not
        # yet populated
        # but the user expects to see *some* info.
        # Specifically for the reported issue: "epoched data disappeared".
        # If epoch_data exists, we should definitely show info based on it or its
        # source.
        if (
            not data_list
            and not use_loaded
            and study.epoch_data
            and study.loaded_data_list
        ):
            # If we have epoch data, we can try to use its raw_list if accessible,
            # or fallback to loaded_data_list if preprocessed is empty.
            # Epochs object usually holds reference to data.
            # Let's fallback to loaded_data_list if preprocessed is empty but loaded is
            # not.
            data_list = study.loaded_data_list

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
                logger.warning(f"Failed to get event list for data: {e}")

            total_epochs += data.get_epochs_length()

            try:
                if data.is_raw():
                    events, _ = data.get_event_list()
                    if events is not None:
                        total_events += len(events)
                else:
                    total_events += data.get_epochs_length()
            except Exception as e:
                logger.warning(f"Failed to count events: {e}")

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
                logger.warning(f"Failed to calc duration: {e}")
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
        if key in self.row_map:
            row = self.row_map[key]
            item = self.table.item(row, 1)
            if item:
                item.setText(value)

    def reset_labels(self):
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 1)
            if item:
                item.setText("-")
