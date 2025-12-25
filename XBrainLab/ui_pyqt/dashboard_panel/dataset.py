from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, 
    QGroupBox, QMenu, QFileDialog, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QDialog, QListWidget, QDialogButtonBox
)
from PyQt6.QtCore import Qt
import numpy as np
from XBrainLab.ui_pyqt.load_data.helper import load_set_file
from XBrainLab.ui_pyqt.load_data.gdf import load_gdf_file
from XBrainLab.ui_pyqt.dashboard_panel.smart_parser import SmartParserDialog
from XBrainLab.ui_pyqt.dashboard_panel.import_label import ImportLabelDialog, EventFilterDialog
from XBrainLab.load_data import RawDataLoader, DataType, EventLoader
from XBrainLab import preprocessor as Preprocessor
from XBrainLab.utils.logger import logger

class ChannelSelectionDialog(QDialog):
    def __init__(self, parent, data_list):
        super().__init__(parent)
        self.setWindowTitle("Channel Selection")
        self.resize(300, 400)
        # Note: ChannelSelection preprocessor usually works on preprocessed_data_list
        # But here we are applying it to loaded_data_list (Raw objects)
        # The backend logic is generic for Raw objects, so it should work.
        self.preprocessor = Preprocessor.ChannelSelection(data_list)
        self.data_list = data_list
        self.return_data = None
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Channel List
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        
        # Get channels from first file
        if self.data_list:
            channels = self.data_list[0].get_mne().ch_names
            for ch in channels:
                from PyQt6.QtWidgets import QListWidgetItem
                item = QListWidgetItem(ch)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                self.list_widget.addItem(item)
                
        layout.addWidget(self.list_widget)
        
        # Select All / None
        btn_layout = QHBoxLayout()
        self.btn_all = QPushButton("Select All")
        self.btn_all.clicked.connect(lambda: self.set_all_checked(True))
        self.btn_none = QPushButton("Deselect All")
        self.btn_none.clicked.connect(lambda: self.set_all_checked(False))
        btn_layout.addWidget(self.btn_all)
        btn_layout.addWidget(self.btn_none)
        layout.addLayout(btn_layout)
        
        # Dialog Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def set_all_checked(self, checked):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(state)
            
    def accept(self):
        selected_channels = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_channels.append(item.text())
        
        if not selected_channels:
            QMessageBox.warning(self, "Warning", "Please select at least one channel.")
            return
            
        try:
            self.return_data = self.preprocessor.data_preprocess(selected_channels)
            super().accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            
    def get_result(self):
        return self.return_data

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
        
        # --- Right Side: Controls ---
        # Operations Group
        ops_group = QGroupBox("Operations")
        ops_group.setFixedWidth(200)
        right_layout = QVBoxLayout(ops_group)
        
        # Import Button
        self.import_btn = QPushButton("Import Data")
        self.import_btn.clicked.connect(self.import_data)
        right_layout.addWidget(self.import_btn)
        
        # Import Label Button
        self.import_label_btn = QPushButton("Import Label")
        self.import_label_btn.clicked.connect(self.import_label)
        right_layout.addWidget(self.import_label_btn)
        
        # Smart Parse Button
        self.smart_parse_btn = QPushButton("Smart Parse Metadata")
        self.smart_parse_btn.clicked.connect(self.open_smart_parser)
        right_layout.addWidget(self.smart_parse_btn)

        right_layout.addStretch()

        # Channel Selection Button (Moved here)
        self.chan_select_btn = QPushButton("Channel Selection")
        self.chan_select_btn.setStyleSheet("background-color: #2e7d32; color: white;") # Green
        self.chan_select_btn.clicked.connect(self.open_channel_selection)
        right_layout.addWidget(self.chan_select_btn)

        # Clear Button
        self.clear_btn = QPushButton("Clear Dataset")
        self.clear_btn.setStyleSheet("background-color: #d32f2f; color: white;")
        self.clear_btn.clicked.connect(self.clear_dataset)
        right_layout.addWidget(self.clear_btn)
        
        main_layout.addWidget(ops_group)

    def import_data(self):
        if self.main_window and hasattr(self.main_window, 'study') and self.main_window.study.is_locked():
            QMessageBox.warning(self, "Import Blocked", 
                                "Dataset is locked because Channel Selection (or other operations) has been applied.\n"
                                "Please 'Clear Dataset' before importing new data.")
            return
            
        filter_str = "EEG Data (*.set *.gdf);;EEGLAB (*.set);;GDF (*.gdf)"
        self._import_files("Open EEG Data", filter_str)

    def _import_files(self, title, filter_str):
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
                
                # Auto-detect loader based on extension
                loader_func = None
                if path.lower().endswith('.set'):
                    loader_func = load_set_file
                elif path.lower().endswith('.gdf'):
                    loader_func = load_gdf_file
                
                if loader_func:
                    raw = loader_func(path)
                    if raw:
                        # This append() call triggers consistency checks against existing data
                        loader.append(raw) 
                        success_count += 1
                    else:
                        errors.append(f"{path}: Loader function returned None (check logs).")
                else:
                    errors.append(f"{path}: Unsupported file extension.")
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
            self.update_panel()
            QMessageBox.information(self, "Success", f"Updated metadata for {count} files.")

    def open_channel_selection(self):
        if not self.main_window or not hasattr(self.main_window, 'study') or not self.main_window.study.loaded_data_list:
            QMessageBox.warning(self, "Warning", "No data loaded.")
            return

        # Warning before proceeding
        reply = QMessageBox.question(
            self, "Warning",
            "Performing Channel Selection will modify the dataset.\n"
            "You will NOT be able to import new data afterwards unless you clear the dataset.\n\n"
            "Do you want to proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.No:
            return

        # We operate on loaded_data_list directly
        data_list = self.main_window.study.loaded_data_list
        
        dialog = ChannelSelectionDialog(self, data_list)
        if dialog.exec():
            result = dialog.get_result()
            if result:
                # Lock the dataset
                self.main_window.study.lock_dataset()
                
                # Result is the modified list (in-place modification usually, but let's be safe)
                # The preprocessor modifies the objects in the list.
                # We need to notify study that data changed? 
                # Actually, since it modifies Raw objects in place, we just need to update UI.
                # But to be safe and trigger any signals, we can set it back.
                self.main_window.study.set_loaded_data_list(result, force_update=True)
                self.update_panel()
                QMessageBox.information(self, "Success", "Channel selection applied.")

    def import_label(self):
        try:
            # Get selected files
            selected_rows = sorted(set(index.row() for index in self.table.selectedIndexes()))
            if not selected_rows:
                # If nothing selected, maybe apply to all?
                reply = QMessageBox.question(
                    self, "Import Label", 
                    "No files selected. Apply labels to ALL loaded files?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    selected_rows = range(self.table.rowCount())
                else:
                    return

            data_list = self.main_window.study.loaded_data_list
            if not data_list:
                QMessageBox.warning(self, "Warning", "No data loaded.")
                return

            target_files = [data_list[i] for i in selected_rows]
            
            dialog = ImportLabelDialog(self)
            if dialog.exec():
                labels, mapping = dialog.get_results()
                if labels is None: return
                
                # --- Step 2: GDF Event Filtering (New) ---
                # Check if we have Raw files with events
                raw_files_with_events = [d for d in target_files if d.is_raw() and d.has_event()]
                selected_event_names = None
                
                if raw_files_with_events:
                    # Collect all unique event NAMES (Descriptions)
                    unique_names = set()
                    for d in raw_files_with_events:
                        try:
                            _, ev_ids = d.get_raw_event_list()
                            if ev_ids:
                                unique_names.update(ev_ids.keys())
                        except:
                            pass
                    
                    if unique_names:
                        # Sort numerically if possible, else alphabetically
                        try:
                            sorted_names = sorted(list(unique_names), key=lambda x: int(x) if x.isdigit() else x)
                        except:
                            sorted_names = sorted(list(unique_names))
                            
                        filter_dialog = EventFilterDialog(self, sorted_names)
                        if filter_dialog.exec():
                            selected_event_names = set(filter_dialog.get_selected_ids()) # Reusing method name, but returns names now
                        else:
                            return # User cancelled filtering
                
                # --- Step 3: Calculate Total Epochs (using filtered events) ---
                total_epochs = 0
                for d in target_files:
                    if d.is_raw():
                        events, event_id_map = d.get_event_list()
                        if selected_event_names is not None and event_id_map:
                            # Find IDs for selected names in THIS file
                            # event_id_map is {name: id}
                            relevant_ids = [eid for name, eid in event_id_map.items() if name in selected_event_names]
                            
                            if relevant_ids:
                                mask = np.isin(events[:, -1], relevant_ids)
                                total_epochs += np.sum(mask)
                            else:
                                # None of the selected events exist in this file
                                total_epochs += 0
                        else:
                            total_epochs += len(events)
                    else:
                        total_epochs += d.get_epochs_length()
                
                label_count = len(labels)
                applied_count = 0
                
                try:
                    # Case 1: Labels match total length -> Split and distribute
                    if label_count == total_epochs and total_epochs > 0:
                        current_idx = 0
                        for data in target_files:
                            if data.is_raw():
                                events, event_id_map = data.get_event_list()
                                file_specific_ids = []
                                if selected_event_names is not None and event_id_map:
                                    file_specific_ids = [eid for name, eid in event_id_map.items() if name in selected_event_names]
                                
                                if file_specific_ids:
                                    mask = np.isin(events[:, -1], file_specific_ids)
                                    n = np.sum(mask)
                                else:
                                    # If filtering was active but no match, n=0
                                    # If filtering NOT active, use all
                                    if selected_event_names is not None:
                                        n = 0
                                    else:
                                        n = len(events)
                            else:
                                n = data.get_epochs_length()
                                
                            file_labels = labels[current_idx : current_idx + n]
                            current_idx += n
                            
                            if n == 0:
                                continue

                            loader = EventLoader(data)
                            loader.label_list = file_labels
                            
                            # If we have selected_event_names, we need to sync manually
                            if selected_event_names is not None and data.is_raw() and file_specific_ids:
                                # Manually prepare events with synced timestamps
                                events, _ = data.get_event_list()
                                mask = np.isin(events[:, -1], file_specific_ids)
                                filtered_events = events[mask]
                                
                                # Verify length matches
                                if len(filtered_events) == len(file_labels):
                                    # Create new events array
                                    new_events = np.zeros((len(file_labels), 3), dtype=int)
                                    new_events[:, 0] = filtered_events[:, 0] # Sync timestamps
                                    new_events[:, -1] = file_labels
                                    
                                    # Create event_id dict
                                    new_event_id = {mapping[i]: i for i in np.unique(file_labels)}
                                    
                                    # Apply directly
                                    data.set_event(new_events, new_event_id)
                                    data.set_labels_imported(True)
                                    applied_count += 1
                                    continue # Skip standard loader.create_event
                                
                            loader.create_event(mapping)
                            loader.apply()
                            data.set_labels_imported(True)
                            applied_count += 1
                            
                    # Case 2: Labels match each file length (Apply same to all)
                    elif all(self._check_length(d, label_count, selected_event_names) for d in target_files):
                        for data in target_files:
                            if selected_event_names is not None and data.is_raw():
                                events, event_id_map = data.get_event_list()
                                file_specific_ids = [eid for name, eid in event_id_map.items() if name in selected_event_names]
                                
                                if file_specific_ids:
                                    mask = np.isin(events[:, -1], file_specific_ids)
                                    filtered_events = events[mask]
                                    
                                    if len(filtered_events) == len(labels):
                                        new_events = np.zeros((len(labels), 3), dtype=int)
                                        new_events[:, 0] = filtered_events[:, 0]
                                        new_events[:, -1] = labels
                                        new_event_id = {mapping[i]: i for i in np.unique(labels)}
                                        data.set_event(new_events, new_event_id)
                                        data.set_labels_imported(True)
                                        applied_count += 1
                                        continue

                            loader = EventLoader(data)
                            loader.label_list = labels
                            loader.create_event(mapping)
                            loader.apply()
                            data.set_labels_imported(True)
                            applied_count += 1
                            
                    else:
                        # Mismatch detected
                        reply = QMessageBox.question(
                            self, "Mismatch Detected", 
                            f"Label count ({label_count}) does not match expected events ({total_epochs}).\n\n"
                            "Do you want to FORCE import?\n"
                            "WARNING: Original timestamps will be lost (set to 0, 1, 2...).",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                        )
                        
                        if reply == QMessageBox.StandardButton.Yes:
                            for data in target_files:
                                loader = EventLoader(data)
                                loader.label_list = labels
                                loader.create_event(mapping)
                                loader.apply()
                                data.set_labels_imported(True)
                                applied_count += 1
                        else:
                            return

                    self.update_panel()
                    QMessageBox.information(self, "Success", f"Applied labels to {applied_count} files.")
                
                except Exception as e:
                    logger.error(f"Error during label distribution: {e}", exc_info=True)
                    QMessageBox.critical(self, "Error", f"Failed to distribute labels: {e}")
        
        except Exception as e:
            logger.error(f"Import label failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to import labels: {e}")

    def _check_length(self, data, label_count, selected_event_names=None):
        if data.is_raw():
            events, event_id_map = data.get_event_list()
            if selected_event_names is not None and event_id_map:
                file_specific_ids = [eid for name, eid in event_id_map.items() if name in selected_event_names]
                if file_specific_ids:
                    mask = np.isin(events[:, -1], file_specific_ids)
                    return np.sum(mask) == label_count
                else:
                    return 0 == label_count
            else:
                return len(events) == label_count
        else:
            return data.get_epochs_length() == label_count

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
                # self.dataset_locked = False # Unlock handled by clean_raw_data
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
                has_event = data.has_event()
                if has_event:
                    # Get event count
                    try:
                        if data.is_raw():
                            events, _ = data.get_event_list()
                            count = len(events)
                        else:
                            count = data.get_epochs_length()
                    except:
                        count = "?"
                    
                    item_ev = QTableWidgetItem(f"Yes ({count})")
                    
                    # Color logic: Green if imported labels, Default (Gray/Black) if original
                    if data.is_labels_imported():
                        item_ev.setForeground(Qt.GlobalColor.green)
                    else:
                        # Use default color (or explicitly set to something neutral if needed)
                        # Setting to None usually resets to default theme color
                        item_ev.setForeground(Qt.GlobalColor.white) # Assuming dark theme, or just don't set foreground
                        # Actually, let's just not set it for default, or set to a standard color
                        # But wait, previous code set it to gray for "No".
                        # Let's set it to white/black depending on theme? 
                        # Better: clear the foreground brush to use default.
                        item_ev.setData(Qt.ItemDataRole.ForegroundRole, None)
                else:
                    item_ev = QTableWidgetItem("No")
                    item_ev.setForeground(Qt.GlobalColor.gray)
                    
                item_ev.setFlags(item_ev.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 6, item_ev)
                
                # Store raw object reference in first item
                item_name.setData(Qt.ItemDataRole.UserRole, data)

        self.table.blockSignals(False)

        # 2. Update Global Info Panel
        if self.main_window and hasattr(self.main_window, 'update_info_panel'):
            self.main_window.update_info_panel()

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
