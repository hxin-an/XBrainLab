from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFileDialog, QComboBox, QTableWidget, QTableWidgetItem, 
    QHeaderView, QMessageBox, QGroupBox, QFormLayout, QDialogButtonBox,
    QListWidget, QListWidgetItem, QMenu
)
from PyQt6.QtCore import Qt, QSettings
import numpy as np
import scipy.io
import os
from XBrainLab.load_data.label_loader import load_label_file

class ImportLabelDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Labels")
        self.resize(500, 400)
        
        self.label_data_map = {} # {filename: label_array}
        self.unique_labels = []
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 1. File Selection
        file_group = QGroupBox("Select Label File")
        file_layout = QHBoxLayout()
        
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.file_list.itemSelectionChanged.connect(self.on_file_selection_changed)
        
        btn_layout = QVBoxLayout()
        browse_btn = QPushButton("Add Files...")
        browse_btn.clicked.connect(self.browse_files)
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self.remove_files)
        btn_layout.addWidget(browse_btn)
        btn_layout.addWidget(remove_btn)
        btn_layout.addStretch()
        
        file_layout.addWidget(self.file_list, stretch=1)
        file_layout.addLayout(btn_layout)
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)
        
        # 2. Mat Variable Selection (Hidden by default)
        # self.var_group = QGroupBox("Select Variable (.mat only)")
        # self.var_group.setVisible(False)
        # var_layout = QVBoxLayout()
        # self.var_combo = QComboBox()
        # # self.var_combo.currentIndexChanged.connect(self.on_var_changed) # Removed
        # var_layout.addWidget(self.var_combo)
        # self.var_group.setLayout(var_layout)
        # layout.addWidget(self.var_group)
        
        # 3. Label Mapping
        map_group = QGroupBox("Map Codes to Event Names")
        map_layout = QVBoxLayout()
        
        self.map_table = QTableWidget()
        self.map_table.setColumnCount(2)
        self.map_table.setHorizontalHeaderLabels(["Code", "Event Name"])
        self.map_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        map_layout.addWidget(self.map_table)
        
        map_group.setLayout(map_layout)
        layout.addWidget(map_group)
        
        # 4. Info Label
        self.info_label = QLabel("")
        layout.addWidget(self.info_label)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def browse_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Open Label Files", "", "Label Files (*.txt *.mat)")
        if not paths:
            return
            
        for path in paths:
            filename = os.path.basename(path)
            # Check duplicates
            if filename in self.label_data_map:
                continue
                
            try:
                self.load_file(path)
                self.file_list.addItem(filename)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to load {filename}: {e}")
                
        self.update_unique_labels()

    def remove_files(self):
        selected_items = self.file_list.selectedItems()
        if not selected_items:
            return
            
        for item in selected_items:
            filename = item.text()
            if filename in self.label_data_map:
                del self.label_data_map[filename]
            self.file_list.takeItem(self.file_list.row(item))
            
        self.update_unique_labels()

    def on_file_selection_changed(self):
        # Maybe show info for selected file?
        pass

    def load_file(self, path):
        filename = os.path.basename(path)
        try:
            labels = load_label_file(path)
            if labels is not None:
                self.label_data_map[filename] = labels
        except Exception as e:
            raise e # Let caller handle or re-raise

    # Removed load_txt and load_mat as they are now in XBrainLab.load_data.label_loader

    # Removed on_var_changed and process_labels as they are refactored into update_unique_labels

    def update_unique_labels(self):
        """
        Aggregates labels from all loaded files, finds unique codes, 
        and updates the mapping table.
        """
        all_labels = []
        for labels in self.label_data_map.values():
            all_labels.extend(labels)
            
        if not all_labels:
            self.unique_labels = []
            self.info_label.setText("No labels loaded.")
            self.map_table.setRowCount(0)
            return

        self.unique_labels = sorted(np.unique(all_labels))
        self.info_label.setText(f"Loaded {len(all_labels)} labels from {len(self.label_data_map)} files. Found {len(self.unique_labels)} unique codes.")
        
        # Preserve existing mapping if possible
        current_mapping = {}
        for i in range(self.map_table.rowCount()):
            code_item = self.map_table.item(i, 0)
            name_item = self.map_table.item(i, 1)
            if code_item and name_item:
                try:
                    code = int(code_item.text())
                    name = name_item.text()
                    current_mapping[code] = name
                except:
                    pass

        # Populate Table
        self.map_table.setRowCount(len(self.unique_labels))
        for i, code in enumerate(self.unique_labels):
            # Code (Read-only)
            item_code = QTableWidgetItem(str(code))
            item_code.setFlags(item_code.flags() ^ Qt.ItemFlag.ItemIsEditable)
            self.map_table.setItem(i, 0, item_code)
            
            # Name (Editable)
            # Use existing name if available, else default
            name = current_mapping.get(code, f"Event_{code}")
            item_name = QTableWidgetItem(name)
            self.map_table.setItem(i, 1, item_name)

    def get_results(self):
        """Returns (label_array, mapping_dict)"""
        """Returns (label_data_map, mapping_dict)"""
        if not self.label_data_map:
            return None, None
            
        mapping = {}
        for i in range(self.map_table.rowCount()):
            code_item = self.map_table.item(i, 0)
            name_item = self.map_table.item(i, 1)
            if code_item and name_item:
                code = int(code_item.text())
                name = name_item.text().strip()
                if name:
                    mapping[code] = name
                    
        return self.label_data_map, mapping

    def accept(self):
        if not self.label_data_map:
            QMessageBox.warning(self, "Warning", "No labels loaded.")
            return
            
        # Validate mapping
        _, mapping = self.get_results()
        if not mapping:
            QMessageBox.warning(self, "Warning", "Please provide event names.")
            return
            
        super().accept()

class EventFilterDialog(QDialog):
    def __init__(self, parent, event_names):
        super().__init__(parent)
        self.setWindowTitle("Filter GDF Events")
        self.resize(300, 400)
        self.event_names = event_names # Already sorted list of strings
        self.selected_names = []
        self.settings = QSettings("XBrainLab", "EventFilter")
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("Select events to KEEP for synchronization:"))
        
        # Load last selection
        last_selected = self.settings.value("last_selected_events", [], type=list)
        # Ensure it's a list of strings (QSettings might return list of QVariant)
        last_selected = [str(x) for x in last_selected]
        
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
        
        for name in self.event_names:
            item = QListWidgetItem(str(name))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            
            # Check if it was selected last time OR if no history (default all checked)
            if not last_selected or str(name) in last_selected:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
                
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
        
        self.btn_toggle = QPushButton("Toggle Selected")
        self.btn_toggle.clicked.connect(self.toggle_selected)
        btn_layout.addWidget(self.btn_toggle)
        
        layout.addLayout(btn_layout)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def set_all_checked(self, checked):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(state)
            
    def toggle_selected(self):
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return
            
        # Toggle based on the first item's state
        first_state = selected_items[0].checkState()
        new_state = Qt.CheckState.Unchecked if first_state == Qt.CheckState.Checked else Qt.CheckState.Checked
        
        for item in selected_items:
            item.setCheckState(new_state)

    def show_context_menu(self, pos):
        menu = QMenu(self)
        action_check = menu.addAction("Check Selected")
        action_uncheck = menu.addAction("Uncheck Selected")
        action_toggle = menu.addAction("Toggle Selected")
        
        action = menu.exec(self.list_widget.mapToGlobal(pos))
        
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return
            
        if action == action_check:
            for item in selected_items:
                item.setCheckState(Qt.CheckState.Checked)
        elif action == action_uncheck:
            for item in selected_items:
                item.setCheckState(Qt.CheckState.Unchecked)
        elif action == action_toggle:
            self.toggle_selected()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self.toggle_selected()
        else:
            super().keyPressEvent(event)

    def accept(self):
        self.selected_names = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                self.selected_names.append(item.text())
        
        # Save to settings
        self.settings.setValue("last_selected_events", self.selected_names)
        
        super().accept()
        
    def get_selected_ids(self):
        # Kept name for compatibility, but returns names
        return self.selected_names

class LabelMappingDialog(QDialog):
    def __init__(self, parent, data_files, label_files):
        super().__init__(parent)
        self.setWindowTitle("Map Labels to Data Files")
        self.resize(600, 400)
        self.data_files = data_files # List of data file paths/names
        self.label_files = label_files # List of label file paths/names
        self.mapping = {} # {data_filename: label_filename}
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("Drag and drop Label files (Right) to align with Data files (Left):"))
        
        # Main layout for lists
        lists_layout = QHBoxLayout()
        
        # Left: Data Files (Fixed)
        data_layout = QVBoxLayout()
        data_layout.addWidget(QLabel("Data Files (Fixed)"))
        self.data_list = QListWidget()
        self.data_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection) # Allow selection for highlighting
        self.data_list.setUniformItemSizes(True)
        self.data_list.setAlternatingRowColors(True)
        self.data_list.setStyleSheet("QListWidget::item { height: 25px; }") # Enforce height
        # self.data_list.setEnabled(False) # Don't disable, just make non-selectable? Or just visual.
        # Better to keep enabled for scrolling, but disallow drag/drop
        for f in self.data_files:
            self.data_list.addItem(os.path.basename(f))
        data_layout.addWidget(self.data_list)
        lists_layout.addLayout(data_layout)
        
        # Right: Label Files (Reorderable)
        label_layout = QVBoxLayout()
        label_layout.addWidget(QLabel("Label Files (Drag to Reorder)"))
        self.label_list = QListWidget()
        self.label_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.label_list.setUniformItemSizes(True)
        self.label_list.setAlternatingRowColors(True)
        self.label_list.setStyleSheet("QListWidget::item { height: 25px; }") # Enforce height
        
        # Auto-sort label files to match data files
        sorted_labels = self.auto_sort_labels()
        
        for f in sorted_labels:
            item = QListWidgetItem(os.path.basename(f) if f else "-- No Label --")
            item.setData(Qt.ItemDataRole.UserRole, f) # Store full path/key
            if not f:
                item.setForeground(Qt.GlobalColor.gray)
            self.label_list.addItem(item)
            
        label_layout.addWidget(self.label_list)
        lists_layout.addLayout(label_layout)
        
        layout.addLayout(lists_layout)
        
        # Sync scrolling
        self.data_list.verticalScrollBar().valueChanged.connect(self.label_list.verticalScrollBar().setValue)
        self.label_list.verticalScrollBar().valueChanged.connect(self.data_list.verticalScrollBar().setValue)
        
        # Sync selection for visual alignment
        self.data_list.currentRowChanged.connect(self.label_list.setCurrentRow)
        self.label_list.currentRowChanged.connect(self.data_list.setCurrentRow)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def auto_sort_labels(self):
        # Create a list of labels aligned with data_files
        # If no match, put None? Or put at end?
        # User wants 1-to-1 mapping mostly.
        
        aligned_labels = [None] * len(self.data_files)
        used_indices = set()
        
        # 1. Try strict matching
        for i, data_file in enumerate(self.data_files):
            data_name = os.path.basename(data_file)
            data_stem = os.path.splitext(data_name)[0]
            
            best_match = None
            best_match_idx = -1
            
            for j, label_file in enumerate(self.label_files):
                if j in used_indices: continue
                
                label_name = os.path.basename(label_file)
                label_stem = os.path.splitext(label_name)[0]
                
                # Check for containment
                if data_stem in label_name or label_stem in data_name:
                    best_match = label_file
                    best_match_idx = j
                    break # Take first match?
            
            if best_match:
                aligned_labels[i] = best_match
                used_indices.add(best_match_idx)
                
        # 2. Fill gaps with remaining labels
        remaining_labels = [f for j, f in enumerate(self.label_files) if j not in used_indices]
        
        # If we have more data files than labels, some will be None (handled by None init)
        # If we have more labels than data files, we append them? 
        # But the lists should ideally be same length for 1-to-1 alignment.
        # Let's append remaining labels to the end of the list if there's space, 
        # or extend the list if needed (though data list is fixed length).
        
        # Fill None slots with remaining labels
        rem_idx = 0
        for i in range(len(aligned_labels)):
            if aligned_labels[i] is None and rem_idx < len(remaining_labels):
                aligned_labels[i] = remaining_labels[rem_idx]
                rem_idx += 1
                
        # If still remaining labels, append them? 
        # The user can drag them up. But data list won't have corresponding entry.
        # We should probably add placeholders to data list or just let label list be longer.
        # Let's let label list be longer.
        while rem_idx < len(remaining_labels):
            aligned_labels.append(remaining_labels[rem_idx])
            rem_idx += 1
            
        return aligned_labels

    def accept(self):
        self.mapping = {}
        # Map based on index
        count = min(self.data_list.count(), self.label_list.count())
        for i in range(count):
            data_file = self.data_files[i] # data list is fixed order
            label_item = self.label_list.item(i)
            label_file = label_item.data(Qt.ItemDataRole.UserRole)
            
            if label_file:
                self.mapping[data_file] = label_file
                
        super().accept()
        
    def get_mapping(self):
        return self.mapping
