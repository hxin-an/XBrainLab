from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, 
    QGroupBox, QMenu, QFileDialog, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QInputDialog, QFrame, QDialog, QListWidget, QDialogButtonBox,
    QAbstractItemView
)
from PyQt6.QtCore import Qt
import numpy as np
import os
from XBrainLab.backend.load_data.raw_data_loader import (
    load_set_file, load_gdf_file, load_fif_file, load_edf_file, 
    load_bdf_file, load_cnt_file, load_brainvision_file
)
from XBrainLab.ui.dashboard_panel.smart_parser import SmartParserDialog
from XBrainLab.ui.dashboard_panel.import_label import ImportLabelDialog, EventFilterDialog, LabelMappingDialog
from XBrainLab.backend.load_data import RawDataLoader, DataType, EventLoader
from XBrainLab.backend import preprocessor as Preprocessor
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.services.label_import_service import LabelImportService

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
    """
    Panel for managing the dataset.
    
    Features:
    - Import Data: Load EEG files (.set, .gdf).
    - Import Label: Assign labels to loaded data.
    - Smart Parse: Automatically extract subject/session info from filenames.
    - Channel Selection: Filter channels.
    - Table View: Display loaded files and their metadata.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.label_service = LabelImportService()
        self.init_ui()

    def init_ui(self):
        # Main Layout: Horizontal Split (Table | Info & Controls)
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

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
        # --- Right Side: Info & Controls ---
        # --- Right Side: Info & Controls ---
        right_panel = QWidget()
        right_panel.setFixedWidth(260) # Increased width
        # Slightly lighter gray with border
        right_panel.setObjectName("RightPanel")
        right_panel.setStyleSheet("""
            #RightPanel { 
                background-color: #252526; 
                border-left: 1px solid #3e3e42; 
            }
            /* Minimal Group Style (No borders, no cards) */
            QGroupBox {
                background-color: transparent;
                border: none;
                margin-top: 15px;
                font-weight: bold;
                color: #808080; /* Subtle title */
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 0px;
                padding: 0 0px;
                color: #808080;
            }
            /* Flat, Minimal Buttons - Maximized Width */
            /* Flat, Minimal Buttons - Maximized Width */
            QPushButton {
                background-color: #3e3e42; /* Lighter gray (VS Code style) */
                border: none; 
                border-radius: 4px;
                padding: 8px 12px; 
                color: #ffffff; /* White text */
                font-weight: normal;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #4e4e52;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #007acc;
            }
        """)
        
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 20, 10, 20) # Reduced margins for wider buttons
        
        # 0. Logo (Minimal, no frame)
        logo_frame = QFrame()
        logo_frame.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: none;
            }
        """)
        logo_layout = QVBoxLayout(logo_frame)
        logo_layout.setContentsMargins(0, 0, 0, 10)
        
        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        logo_label.setStyleSheet("border: none; background: transparent;") 
        
        logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "logo.svg")
        if os.path.exists(logo_path):
            from PyQt6.QtGui import QPixmap
            pixmap = QPixmap(logo_path)
            # Scale pixmap to fit panel width (260 - 20 margin = 240)
            scaled_pixmap = pixmap.scaledToWidth(240, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(scaled_pixmap)
            logo_label.setScaledContents(False)
        else:
            logo_label.setText("XBrainLab")
            logo_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #cccccc; margin-bottom: 5px; border: none;")
            
        logo_layout.addWidget(logo_label)
        right_layout.addWidget(logo_frame)
        
        # 1. Dynamic Tips (Always visible)
        self.tips_group = QGroupBox("GETTING STARTED")
        # Explicitly set transparent background to avoid black box
        self.tips_group.setStyleSheet("QGroupBox { background-color: transparent; border: none; margin-top: 10px; } QGroupBox::title { color: #808080; }")
        
        tips_layout = QVBoxLayout(self.tips_group)
        tips_layout.setContentsMargins(0, 10, 0, 0)
        tips_label = QLabel(
            "<div style='line-height: 1.2; color: #999999;'>"
            "<div style='margin-bottom: 6px;'><b style='color: #cccccc;'>1. Import Data</b><br>Load EEG recordings</div>"
            "<div style='margin-bottom: 6px;'><b style='color: #cccccc;'>2. Import Label</b><br>Add events (optional)</div>"
            "<div style='margin-bottom: 6px;'><b style='color: #cccccc;'>3. Smart Parse</b><br>Organize metadata</div>"
            "<div><br>When ready, do <b>Channel Selection</b></div>"
            "</div>"
        )
        tips_label.setWordWrap(True)
        tips_label.setStyleSheet("background-color: transparent; border: none;") # Explicitly transparent
        tips_layout.addWidget(tips_label)
        right_layout.addWidget(self.tips_group)
        
        right_layout.addSpacing(10)

        # 2. Dataset Actions Group
        actions_group = QGroupBox("Dataset Actions")
        actions_layout = QVBoxLayout(actions_group)
        actions_layout.setContentsMargins(0, 10, 0, 0) # Maximize width
        
        self.import_btn = QPushButton("Import Data")
        self.import_btn.setToolTip("Load .set or .gdf files")
        self.import_btn.clicked.connect(self.import_data)
        actions_layout.addWidget(self.import_btn)
        
        self.import_label_btn = QPushButton("Import Label")
        self.import_label_btn.setToolTip("Import labels from external files")
        self.import_label_btn.clicked.connect(self.import_label)
        actions_layout.addWidget(self.import_label_btn)
        
        self.smart_parse_btn = QPushButton("Smart Parse Metadata")
        self.smart_parse_btn.setToolTip("Auto-extract Subject/Session from filenames")
        self.smart_parse_btn.clicked.connect(self.open_smart_parser)
        actions_layout.addWidget(self.smart_parse_btn)
        
        right_layout.addWidget(actions_group)

        # Spacer to push Danger Zone to bottom
        right_layout.addStretch()

        # 3. Channel Selection (Moved here, Green)
        self.chan_select_btn = QPushButton("Channel Selection")
        self.chan_select_btn.setToolTip("Select specific channels to keep")
        self.chan_select_btn.setStyleSheet("""
            QPushButton {
                background-color: #1b5e20; 
                color: #a5d6a7;
                border: 1px solid #2e7d32;
            }
            QPushButton:hover {
                background-color: #2e7d32;
                color: white;
            }
            QPushButton:disabled {
                background-color: #2d2d2d;
                color: #555555;
                border: 1px solid #3e3e42;
            }
        """)
        self.chan_select_btn.clicked.connect(self.open_channel_selection)
        right_layout.addWidget(self.chan_select_btn)



        # 4. Danger Zone (Button Only)
        self.clear_btn = QPushButton("Clear Dataset")
        # Match Preprocess Reset Button Style
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a1818; 
                color: #ff9999;
                border: 1px solid #802020;
            }
            QPushButton:hover {
                background-color: #602020;
            }
        """)
        self.clear_btn.setToolTip("Remove all loaded data")
        self.clear_btn.clicked.connect(self.clear_dataset)
        right_layout.addWidget(self.clear_btn)
        
        main_layout.addWidget(right_panel)

    def import_data(self):
        """
        Opens a file dialog to select and import EEG data files.
        Supports .set and .gdf formats.
        """
        if self.main_window and hasattr(self.main_window, 'study') and self.main_window.study.is_locked():
            QMessageBox.warning(self, "Import Blocked", 
                                "Dataset is locked because Channel Selection (or other operations) has been applied.\n"
                                "Please 'Clear Dataset' before importing new data.")
            return
            
        filter_str = (
            "All Supported (*.set *.gdf *.fif *.edf *.bdf *.cnt *.vhdr);;"
            "EEGLAB (*.set);;"
            "GDF (*.gdf);;"
            "FIF (*.fif);;"
            "EDF/BDF (*.edf *.bdf);;"
            "Neuroscan CNT (*.cnt);;"
            "BrainVision (*.vhdr)"
        )
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
                elif path.lower().endswith('.fif'):
                    loader_func = load_fif_file
                elif path.lower().endswith('.edf'):
                    loader_func = load_edf_file
                elif path.lower().endswith('.bdf'):
                    loader_func = load_bdf_file
                elif path.lower().endswith('.cnt'):
                    loader_func = load_cnt_file
                elif path.lower().endswith('.vhdr'):
                    loader_func = load_brainvision_file
                
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
        if self.main_window and hasattr(self.main_window, 'study') and self.main_window.study.is_locked():
            QMessageBox.warning(self, "Action Blocked", 
                                "Dataset is locked because Channel Selection (or other operations) has been applied.\n"
                                "Please 'Clear Dataset' before modifying metadata.")
            return

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

    def open_channel_selection(self):
        if not self.main_window or not hasattr(self.main_window, 'study') or not self.main_window.study.loaded_data_list:
            QMessageBox.warning(self, "Warning", "No data loaded.")
            return

        # Check lock
        if self.main_window.study.is_locked():
             QMessageBox.warning(self, "Action Blocked", 
                                "Dataset is locked because Channel Selection (or other operations) has been applied.\n"
                                "Please 'Reset All Preprocessing' to undo Channel Selection or 'Clear Dataset' to start over.")
             return

        # Warning before proceeding
        reply = QMessageBox.question(
            self, "Warning",
            "Performing Channel Selection will modify the dataset.\n"
            "You can undo this later using 'Reset All Preprocessing'.\n\n"
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
                # Backup before applying changes
                self.main_window.study.backup_loaded_data()
                
                # Result is the modified list (in-place modification usually, but let's be safe)
                # The preprocessor modifies the objects in the list.
                # We need to notify study that data changed? 
                # Actually, since it modifies Raw objects in place, we just need to update UI.
                # But to be safe and trigger any signals, we can set it back.
                self.main_window.study.set_loaded_data_list(result, force_update=True)
                
                # Lock the dataset AFTER updating data (because set_loaded_data_list resets the lock)
                self.main_window.study.lock_dataset()
                
                self.update_panel()
                QMessageBox.information(self, "Success", "Channel selection applied.")

    def import_label(self):
        """
        Imports labels from external files (e.g., .mat) and applies them to the loaded data.
        Handles event synchronization and batch application.
        """
        try:
            if self.main_window and hasattr(self.main_window, 'study') and self.main_window.study.is_locked():
                QMessageBox.warning(self, "Import Blocked", 
                                    "Dataset is locked because Channel Selection (or other operations) has been applied.\n"
                                    "Please 'Clear Dataset' or 'Reset Preprocessing' before importing labels.")
                return

            # 1. Select Files
            target_files = self._get_target_files_for_import()
            if not target_files: return

            # 2. Select Label File
            dialog = ImportLabelDialog(self)
            if not dialog.exec(): return
            label_map, mapping = dialog.get_results()
            if label_map is None: return

            # 3. Filter Events (Optional, for Raw files)
            selected_event_names = self._filter_events_for_import(target_files)
            if selected_event_names is False: return # User cancelled

            # 4. Distribute Labels
            is_batch_mode = len(label_map) > 1
            count = 0
            
            if is_batch_mode:
                # Batch Mode
                data_filepaths = [d.get_filepath() for d in target_files]
                label_filenames = list(label_map.keys())
                
                mapping_dialog = LabelMappingDialog(self, data_filepaths, label_filenames)
                if not mapping_dialog.exec():
                    return
                    
                file_mapping = mapping_dialog.get_mapping()
                count = self.label_service.apply_labels_batch(
                    target_files, label_map, file_mapping, mapping, selected_event_names
                )
            else:
                # Legacy Mode (Single label file to multiple data files)
                labels = list(label_map.values())[0]
                label_count = len(labels)
                
                # Check if exact match first
                total_epochs = sum(self.label_service.get_epoch_count_for_file(d, selected_event_names) for d in target_files)
                
                if label_count == total_epochs and total_epochs > 0:
                    count = self.label_service.apply_labels_legacy(
                        target_files, labels, mapping, selected_event_names
                    )
                else:
                    # Mismatch
                    reply = QMessageBox.question(
                        self, "Mismatch Detected",
                        f"Total labels ({label_count}) != Total epochs ({total_epochs}).\n"
                        "Do you want to FORCE import? (This will assign labels sequentially to files and overwrite timestamps!)",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    
                    if reply == QMessageBox.StandardButton.Yes:
                        count = self.label_service.apply_labels_legacy(
                            target_files, labels, mapping, selected_event_names, force_import=True
                        )
                    else:
                        count = 0

            if count > 0:
                # IMPORTANT: Reset preprocess to propagate new events to preprocessed_data_list
                if self.main_window and hasattr(self.main_window, 'study'):
                    self.main_window.study.reset_preprocess(force_update=True)
                
                self.update_panel()
                QMessageBox.information(self, "Success", f"Applied labels to {count} files.")

        except Exception as e:
            logger.error(f"Import label failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to import labels: {e}")

    def _get_target_files_for_import(self):
        selected_rows = sorted(set(index.row() for index in self.table.selectedIndexes()))
        if not selected_rows:
            reply = QMessageBox.question(
                self, "Import Label", 
                "No files selected. Apply labels to ALL loaded files?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                selected_rows = range(self.table.rowCount())
            else:
                return []
        
        if not self.main_window or not hasattr(self.main_window, 'study') or not self.main_window.study.loaded_data_list:
            QMessageBox.warning(self, "Warning", "No data loaded.")
            return []
            
        data_list = self.main_window.study.loaded_data_list
        return [data_list[i] for i in selected_rows if i < len(data_list)]

    def _filter_events_for_import(self, target_files):
        """
        Returns:
            set: selected event names
            None: no filtering needed/applied
            False: user cancelled
        """
        raw_files_with_events = [d for d in target_files if d.is_raw() and d.has_event()]
        if not raw_files_with_events:
            return None
            
        unique_names = set()
        for d in raw_files_with_events:
            try:
                _, ev_ids = d.get_raw_event_list()
                if ev_ids:
                    unique_names.update(ev_ids.keys())
            except:
                pass
        
        if not unique_names:
            return None
            
        # Sort numerically if possible, else alphabetically
        try:
            sorted_names = sorted(list(unique_names), key=lambda x: int(x) if x.isdigit() else x)
        except:
            sorted_names = sorted(list(unique_names))
            
        filter_dialog = EventFilterDialog(self, sorted_names)
        if filter_dialog.exec():
            selected = set(filter_dialog.get_selected_ids())
            logger.info(f"User selected event names: {selected}")
            return selected
        else:
            return False



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
        if not self.main_window and not hasattr(self.main_window, 'study'):
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
            reply = QMessageBox.question(
                self, "Confirm Clear",
                "Are you sure you want to clear the entire dataset?\nThis action cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return

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
        
        # Toggle Tips Visibility (User requested to keep it always visible)
        # if hasattr(self, 'tips_group'):
        #     self.tips_group.setVisible(not bool(data_list))
        
        # 1. Update Table
        self.table.clearContents()
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
                        logger.info(f"File {data.get_filename()} has imported labels. Setting green.")
                        item_ev.setForeground(Qt.GlobalColor.green)
                    else:
                        # Use default color (or explicitly set to something neutral if needed)
                        # Setting to None usually resets to default theme color
                        # item_ev.setForeground(Qt.GlobalColor.white) 
                        
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

        # Also update the global info panel
        if hasattr(self.main_window, 'update_info_panel'):
            self.main_window.update_info_panel()

        # 2. Update Global Info Panel
        if self.main_window and hasattr(self.main_window, 'update_info_panel'):
            self.main_window.update_info_panel()
            
        # 3. Update Channel Selection Button State
        if self.main_window and hasattr(self.main_window, 'study'):
            is_locked = self.main_window.study.is_locked()
            if hasattr(self, 'chan_select_btn'):
                # self.chan_select_btn.setEnabled(not is_locked) # Keep enabled to show warning
                if is_locked:
                    self.chan_select_btn.setToolTip("Dataset is locked. Click to see details.")
                else:
                    self.chan_select_btn.setToolTip("Select specific channels to keep")
                    
        # 4. Update Smart Parse Button State
        if self.main_window and hasattr(self.main_window, 'study'):
            is_locked = self.main_window.study.is_locked()
            if hasattr(self, 'smart_parse_btn'):
                # self.smart_parse_btn.setEnabled(not is_locked) # Keep enabled to show warning
                if is_locked:
                    self.smart_parse_btn.setToolTip("Dataset is locked. Click to see details.")
                else:
                    self.smart_parse_btn.setToolTip("Auto-extract Subject/Session from filenames")

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
