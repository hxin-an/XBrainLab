from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFileDialog, QComboBox, QTableWidget, QTableWidgetItem, 
    QHeaderView, QMessageBox, QGroupBox, QFormLayout, QDialogButtonBox,
    QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, QSettings
import numpy as np
import scipy.io
import os

class ImportLabelDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Labels")
        self.resize(500, 400)
        
        self.label_data = None # The loaded array of labels
        self.unique_labels = []
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 1. File Selection
        file_group = QGroupBox("Select Label File")
        file_layout = QHBoxLayout()
        
        self.path_label = QLabel("No file selected")
        self.path_label.setStyleSheet("color: gray; font-style: italic;")
        
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_file)
        
        file_layout.addWidget(self.path_label, stretch=1)
        file_layout.addWidget(browse_btn)
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)
        
        # 2. Mat Variable Selection (Hidden by default)
        self.var_group = QGroupBox("Select Variable (.mat only)")
        self.var_group.setVisible(False)
        var_layout = QVBoxLayout()
        self.var_combo = QComboBox()
        self.var_combo.currentIndexChanged.connect(self.on_var_changed)
        var_layout.addWidget(self.var_combo)
        self.var_group.setLayout(var_layout)
        layout.addWidget(self.var_group)
        
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
        
    def browse_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Label File", "", "Label Files (*.txt *.mat)")
        if not path:
            return
            
        self.path_label.setText(os.path.basename(path))
        self.path_label.setStyleSheet("color: #cccccc;") # Reset color
        self.load_file(path)
        
    def load_file(self, path):
        self.label_data = None
        self.unique_labels = []
        self.var_group.setVisible(False)
        self.map_table.setRowCount(0)
        
        try:
            if path.endswith('.txt'):
                self.load_txt(path)
            elif path.endswith('.mat'):
                self.load_mat(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load file: {e}")
            
    def load_txt(self, path):
        # Read space-separated integers
        labels = []
        with open(path, 'r') as f:
            for line in f:
                parts = line.strip().split()
                for p in parts:
                    try:
                        labels.append(int(p))
                    except ValueError:
                        pass
        
        self.process_labels(np.array(labels))
        
    def load_mat(self, path):
        try:
            mat = scipy.io.loadmat(path)
            # Filter out __header__, __version__, __globals__
            vars = [k for k in mat.keys() if not k.startswith('__')]
            
            if not vars:
                raise ValueError("No variables found in .mat file")
                
            self.mat_content = mat
            self.var_combo.blockSignals(True)
            self.var_combo.clear()
            self.var_combo.addItems(vars)
            self.var_combo.blockSignals(False)
            
            self.var_group.setVisible(True)
            # Load first variable by default
            self.on_var_changed(0)
            
        except Exception as e:
            raise ValueError(f"Invalid .mat file: {e}")

    def on_var_changed(self, index):
        var_name = self.var_combo.currentText()
        if not var_name or not hasattr(self, 'mat_content'):
            return
            
        data = self.mat_content[var_name]
        # Flatten if needed, similar to EventLoader logic
        data = np.array(data).flatten()
        self.process_labels(data)

    def process_labels(self, labels):
        self.label_data = labels
        self.unique_labels = sorted(np.unique(labels))
        
        self.info_label.setText(f"Loaded {len(labels)} labels. Found {len(self.unique_labels)} unique codes.")
        
        # Populate Table
        self.map_table.setRowCount(len(self.unique_labels))
        for i, code in enumerate(self.unique_labels):
            # Code (Read-only)
            item_code = QTableWidgetItem(str(code))
            item_code.setFlags(item_code.flags() ^ Qt.ItemFlag.ItemIsEditable)
            self.map_table.setItem(i, 0, item_code)
            
            # Name (Editable)
            item_name = QTableWidgetItem(f"Event_{code}")
            self.map_table.setItem(i, 1, item_name)

    def get_results(self):
        """Returns (label_array, mapping_dict)"""
        if self.label_data is None:
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
                    
        return self.label_data, mapping

    def accept(self):
        if self.label_data is None:
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
