from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, 
    QGroupBox, QMenu, QFileDialog, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView
)
from PyQt6.QtCore import Qt
from XBrainLab.ui_pyqt.load_data.helper import load_set_file
from XBrainLab.ui_pyqt.load_data.gdf import load_gdf_file
from XBrainLab.ui_pyqt.dashboard_panel.smart_parser import SmartParserDialog
from XBrainLab.load_data import RawDataLoader, DataType
from XBrainLab.utils.logger import logger

class DatasetPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.init_ui()

    def init_ui(self):
        # Main Layout: Horizontal Split (Table | Info & Controls)
        main_layout = QHBoxLayout(self)

        # --- Left Side: File List Table ---
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Filename", "Subject", "Session", "Channels", 
            "Sfreq", "Epochs", "Events"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection) # Allow multiple selection
        self.table.itemChanged.connect(self.on_item_changed)
        
        # Context Menu
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        
        main_layout.addWidget(self.table, stretch=2)

        # --- Right Side: Info & Controls ---
        right_layout = QVBoxLayout()
        
        # 1. Aggregate Info Group
        info_group = QGroupBox("Aggregate Information")
        info_layout = QGridLayout()
        
        self.labels = {}
        keys = [
            "Type", "Total Files", "Subjects", "Sessions", "Total Epochs", 
            "Channel", "Sample rate", "tmin (sec)", "duration (sec)", 
            "Highpass", "Lowpass", "Classes"
        ]
        
        for i, key in enumerate(keys):
            info_layout.addWidget(QLabel(key), i, 0)
            val_label = QLabel("-")
            info_layout.addWidget(val_label, i, 1)
            self.labels[key] = val_label

        info_group.setLayout(info_layout)
        right_layout.addWidget(info_group)

        # 2. Operations Group
        ops_group = QGroupBox("Operations")
        ops_layout = QVBoxLayout()

        # Import Button
        self.import_btn = QPushButton("Import Data")
        self.import_menu = QMenu(self)
        
        action_set = self.import_menu.addAction("Import .set (EEGLAB)")
        action_set.triggered.connect(self.import_set)
        
        action_gdf = self.import_menu.addAction("Import .gdf (BIOSIG)")
        action_gdf.triggered.connect(self.import_gdf)
        
        self.import_menu.addAction("Import .mat (Coming Soon)")
        
        self.import_btn.setMenu(self.import_menu)
        ops_layout.addWidget(self.import_btn)
        
        # Clear Button
        self.clear_btn = QPushButton("Clear Dataset")
        self.clear_btn.clicked.connect(self.clear_dataset)
        ops_layout.addWidget(self.clear_btn)

        # Smart Parse Button
        self.smart_parse_btn = QPushButton("Smart Parse Metadata")
        self.smart_parse_btn.clicked.connect(self.open_smart_parser)
        ops_layout.addWidget(self.smart_parse_btn)

        ops_group.setLayout(ops_layout)
        right_layout.addWidget(ops_group)
        
        right_layout.addStretch()
        main_layout.addLayout(right_layout, stretch=1)

    def import_gdf(self):
        self._import_files("Open .gdf File", "GDF Files (*.gdf)", load_gdf_file)

    def import_set(self):
        self._import_files("Open .set File", "EEGLAB Files (*.set)", load_set_file)

    def _import_files(self, title, filter_str, loader_func):
        filepaths, _ = QFileDialog.getOpenFileNames(self, title, "", filter_str)
        if not filepaths:
            return

        # 1. Prepare Loader with Existing Data
        existing_data = []
        if self.main_window and hasattr(self.main_window, 'study') and self.main_window.study.loaded_data_list:
            existing_data = list(self.main_window.study.loaded_data_list)
            
        try:
            # Try to preserve existing data
            loader = RawDataLoader(existing_data)
        except Exception as e:
            # If existing data is invalid, ask user
            logger.warning(f"Existing data validation failed: {e}")
            reply = QMessageBox.question(
                self, "Dataset Inconsistency",
                f"Existing dataset seems inconsistent or corrupted:\n{e}\n\nDo you want to clear it and start fresh?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                loader = RawDataLoader()
                # Also clear the study's list to be safe
                self.main_window.study.clean_raw_data(force_update=True)
            else:
                return # Cancel import

        # 2. Load New Files
        success_count = 0
        errors = []
        
        for path in filepaths:
            # Check duplicates (check against loader which contains existing)
            if any(d.get_filepath() == path for d in loader):
                logger.info(f"Skipping duplicate: {path}")
                continue
                
            try:
                logger.info(f"Loading file: {path}")
                raw = loader_func(path)
                if raw:
                    # This append() call triggers consistency checks against existing data
                    loader.append(raw) 
                    success_count += 1
                else:
                    errors.append(f"{path}: Loader function returned None (check logs).")
            except Exception as e:
                logger.error(f"Error loading {path}: {e}")
                errors.append(f"{path}: {str(e)}")

        # 3. Apply Changes
        if success_count > 0:
            self.apply_loader(loader)
        
        # 4. Report Errors
        if errors:
            error_msg = "\n".join(errors[:10])
            if len(errors) > 10:
                error_msg += f"\n...and {len(errors)-10} more errors."
            
            QMessageBox.warning(
                self, "Import Warnings", 
                f"Successfully loaded {success_count} files.\n\nFailed to load {len(errors)} files:\n{error_msg}"
            )
        elif success_count == 0 and not errors:
             if filepaths:
                 QMessageBox.information(self, "Info", "No new files were loaded (duplicates ignored).")

    def show_context_menu(self, pos):
        menu = QMenu(self)
        
        selected_rows = sorted(set(index.row() for index in self.table.selectedIndexes()))
        if not selected_rows:
            return

        action_subject = menu.addAction("Set Subject for Selected")
        action_session = menu.addAction("Set Session for Selected")
        menu.addSeparator()
        action_remove = menu.addAction("Remove Selected Files")
        
        action = menu.exec(self.table.mapToGlobal(pos))
        
        if action == action_subject:
            self.batch_set_attribute(selected_rows, "Subject")
        elif action == action_session:
            self.batch_set_attribute(selected_rows, "Session")
        elif action == action_remove:
            self.remove_selected_files(selected_rows)

    def open_smart_parser(self):
        if not self.main_window or not hasattr(self.main_window, 'study') or not self.main_window.study.loaded_data_list:
            QMessageBox.warning(self, "Warning", "No data loaded to parse.")
            return

        data_list = self.main_window.study.loaded_data_list
        filepaths = [d.get_filepath() for d in data_list]
        
        dialog = SmartParserDialog(filepaths, self)
        if dialog.exec():
            results = dialog.get_results()
            # Apply results
            count = 0
            for data in data_list:
                path = data.get_filepath()
                if path in results:
                    sub, sess = results[path]
                    if sub != "-":
                        data.set_subject_name(sub)
                    if sess != "-":
                        data.set_session_name(sess)
                    count += 1
            
            self.update_panel()
            QMessageBox.information(self, "Success", f"Updated metadata for {count} files.")

    def batch_set_attribute(self, rows, attr_name):
        from PyQt6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, f"Batch Set {attr_name}", f"Enter {attr_name}:")
        if ok and text:
            data_list = self.main_window.study.loaded_data_list
            for row in rows:
                if row < len(data_list):
                    data = data_list[row]
                    if attr_name == "Subject":
                        data.set_subject_name(text)
                    elif attr_name == "Session":
                        data.set_session_name(text)
            self.update_panel()

    def remove_selected_files(self, rows):
        if not self.main_window or not hasattr(self.main_window, 'study'):
            return
            
        reply = QMessageBox.question(
            self, "Confirm Remove", 
            f"Are you sure you want to remove {len(rows)} files?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Remove from study.loaded_data_list
            # We need to be careful with indices shifting, so remove from end or by object
            current_list = self.main_window.study.loaded_data_list
            to_remove = []
            for row in rows:
                if row < len(current_list):
                    to_remove.append(current_list[row])
            
            # Create new list without removed items
            new_list = [d for d in current_list if d not in to_remove]
            
            # Update study
            try:
                self.main_window.study.set_loaded_data_list(new_list, force_update=True)
                self.update_panel()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to remove files: {e}")

    def apply_loader(self, loader):
        if self.main_window and hasattr(self.main_window, 'study'):
            try:
                # Use force_update=True to allow updating the dataset (e.g. appending)
                # This will reset downstream steps (preprocess, etc.) which is expected behavior
                loader.apply(self.main_window.study, force_update=True)
                self.update_panel()
                QMessageBox.information(self, "Success", f"Dataset updated. Total files: {len(loader)}")
            except Exception as e:
                logger.error("Failed to apply data", exc_info=True)
                QMessageBox.critical(self, "Error", f"Failed to apply data: {e}")

    def clear_dataset(self):
        if self.main_window and hasattr(self.main_window, 'study'):
            try:
                # Use study's clean method directly
                self.main_window.study.clean_raw_data(force_update=True)
                self.update_panel()
                QMessageBox.information(self, "Success", "Dataset cleared.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to clear dataset: {e}")

    def update_panel(self):
        if not self.main_window or not hasattr(self.main_window, 'study'):
            return

        data_list = self.main_window.study.loaded_data_list
        
        # 1. Update Table
        self.table.blockSignals(True) # Prevent itemChanged triggering during update
        self.table.setRowCount(0)
        
        if data_list:
            self.table.setRowCount(len(data_list))
            for row, data in enumerate(data_list):
                # Filename (Read-only)
                item_name = QTableWidgetItem(data.get_filename())
                item_name.setFlags(item_name.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 0, item_name)
                
                # Subject (Editable)
                self.table.setItem(row, 1, QTableWidgetItem(data.get_subject_name()))
                
                # Session (Editable)
                self.table.setItem(row, 2, QTableWidgetItem(data.get_session_name()))
                
                # Channels (Read-only)
                item_ch = QTableWidgetItem(str(data.get_nchan()))
                item_ch.setFlags(item_ch.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 3, item_ch)
                
                # Sfreq (Read-only)
                item_sf = QTableWidgetItem(str(data.get_sfreq()))
                item_sf.setFlags(item_sf.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 4, item_sf)
                
                # Epochs (Read-only)
                item_ep = QTableWidgetItem(str(data.get_epochs_length()))
                item_ep.setFlags(item_ep.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 5, item_ep)
                
                # Events (Read-only)
                item_ev = QTableWidgetItem(data.has_event_str())
                item_ev.setFlags(item_ev.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 6, item_ev)
                
                # Store raw object reference in first item
                item_name.setData(Qt.ItemDataRole.UserRole, data)

        self.table.blockSignals(False)

        # 2. Update Aggregate Info
        if not data_list:
            self.reset_labels()
            return

        subject_set = set()
        session_set = set()
        classes_set = set()
        total_epochs = 0
        
        first_data = data_list[0]
        
        for data in data_list:
            subject_set.add(data.get_subject_name())
            session_set.add(data.get_session_name())
            _, event_id = data.get_event_list()
            if event_id:
                classes_set.update(event_id)
            total_epochs += data.get_epochs_length()
            
        tmin = "None"
        duration = "None"
        
        if not first_data.is_raw():
            tmin = str(first_data.get_tmin())
            dur_val = int(first_data.get_epoch_duration() * 100 / first_data.get_sfreq()) / 100
            duration = str(dur_val)

        highpass, lowpass = first_data.get_filter_range()
        text_type = DataType.RAW.value if first_data.is_raw() else DataType.EPOCH.value

        self.labels["Type"].setText(str(text_type))
        self.labels["Total Files"].setText(str(len(data_list)))
        self.labels["Subjects"].setText(str(len(subject_set)))
        self.labels["Sessions"].setText(str(len(session_set)))
        self.labels["Total Epochs"].setText(str(total_epochs))
        self.labels["Channel"].setText(str(first_data.get_nchan()))
        self.labels["Sample rate"].setText(str(first_data.get_sfreq()))
        self.labels["tmin (sec)"].setText(tmin)
        self.labels["duration (sec)"].setText(duration)
        self.labels["Highpass"].setText(str(highpass))
        self.labels["Lowpass"].setText(str(lowpass))
        self.labels["Classes"].setText(str(len(classes_set)))

    def reset_labels(self):
        for label in self.labels.values():
            label.setText("-")

    def on_item_changed(self, item):
        row = item.row()
        col = item.column()
        
        # Get raw data object from the first column of this row
        name_item = self.table.item(row, 0)
        raw_data = name_item.data(Qt.ItemDataRole.UserRole)
        
        if not raw_data:
            return
            
        new_value = item.text()
        
        if col == 1: # Subject
            raw_data.set_subject_name(new_value)
            self.update_panel() # Refresh aggregates
        elif col == 2: # Session
            raw_data.set_session_name(new_value)
            self.update_panel() # Refresh aggregates
