from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QLabel, QPushButton, QGroupBox, QMenu, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt
from XBrainLab.ui_pyqt.data_loader_helper import load_set_file
from XBrainLab.load_data import RawDataLoader, DataType
from XBrainLab.utils.logger import logger

class DatasetPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 1. Info Group
        info_group = QGroupBox("Dataset Information")
        info_layout = QGridLayout()
        
        # Labels map
        self.labels = {}
        keys = [
            "Type", "Subject", "Session", "Epochs", "Channel", 
            "Sample rate", "tmin (sec.)", "duration (sec.)", 
            "Highpass", "Lowpass", "Classes"
        ]
        
        for i, key in enumerate(keys):
            info_layout.addWidget(QLabel(key), i, 0)
            val_label = QLabel("None")
            info_layout.addWidget(val_label, i, 1)
            self.labels[key] = val_label

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # 2. Import Button
        self.import_btn = QPushButton("Import Data")
        self.import_menu = QMenu(self)
        
        # Add actions
        action_set = self.import_menu.addAction("Import .set (EEGLAB)")
        action_set.triggered.connect(self.import_set)
        
        # Placeholder for others
        self.import_menu.addAction("Import .mat (Coming Soon)")
        
        self.import_btn.setMenu(self.import_menu)
        layout.addWidget(self.import_btn)
        
        layout.addStretch()

    def import_set(self):
        filepaths, _ = QFileDialog.getOpenFileNames(
            self, "Open .set File", "", "EEGLAB Files (*.set)"
        )
        if not filepaths:
            return

        # Get or create DataLoader
        # In original logic, it seems to create a new loader or append?
        # dash_board.py: data_loader = current_import_module.get_result()
        # Then data_loader.apply(study)
        
        # We will create a temporary loader for this batch
        loader = RawDataLoader()
        
        for path in filepaths:
            try:
                logger.info(f"Loading file: {path}")
                raw = load_set_file(path)
                if raw:
                    loader.append(raw)
                else:
                    QMessageBox.warning(self, "Error", f"Failed to load {path}")
            except Exception as e:
                logger.error(f"Error loading {path}", exc_info=True)
                QMessageBox.critical(self, "Error", str(e))

        if len(loader) > 0:
            # Apply to study
            if self.main_window and hasattr(self.main_window, 'study'):
                try:
                    loader.apply(self.main_window.study)
                    self.update_panel()
                    QMessageBox.information(self, "Success", f"Loaded {len(loader)} files.")
                except Exception as e:
                    logger.error("Failed to apply data to study", exc_info=True)
                    QMessageBox.critical(self, "Error", f"Failed to apply data: {e}")

    def update_panel(self):
        if not self.main_window or not hasattr(self.main_window, 'study'):
            return

        data_list = self.main_window.study.preprocessed_data_list
        if not data_list:
            self.reset_labels()
            return

        # Logic copied from DatasetPanel.update_panel
        subject_set = set()
        session_set = set()
        classes_set = set()
        epoch_length = 0
        
        first_data = data_list[0] # Use first data for common attributes
        
        for data in data_list:
            subject_set.add(data.get_subject_name())
            session_set.add(data.get_session_name())
            _, event_id = data.get_event_list()
            if event_id:
                classes_set.update(event_id)
            epoch_length += data.get_epochs_length()
            
        tmin = "None"
        duration = "None"
        
        if not first_data.is_raw():
            tmin = first_data.get_tmin()
            # Calculate duration
            duration = int(
                first_data.get_epoch_duration() * 100 / first_data.get_sfreq()
            ) / 100

        highpass, lowpass = first_data.get_filter_range()
        text_type = DataType.RAW.value if first_data.is_raw() else DataType.EPOCH.value

        # Update Labels
        self.labels["Type"].setText(str(text_type))
        self.labels["Subject"].setText(str(len(subject_set)))
        self.labels["Session"].setText(str(len(session_set)))
        self.labels["Epochs"].setText(str(epoch_length))
        self.labels["Channel"].setText(str(first_data.get_nchan()))
        self.labels["Sample rate"].setText(str(first_data.get_sfreq()))
        self.labels["tmin (sec.)"].setText(str(tmin))
        self.labels["duration (sec.)"].setText(str(duration))
        self.labels["Highpass"].setText(str(highpass))
        self.labels["Lowpass"].setText(str(lowpass))
        self.labels["Classes"].setText(str(len(classes_set)))

    def reset_labels(self):
        for label in self.labels.values():
            label.setText("None")
