from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QListWidget, QPushButton, QMessageBox, QAbstractItemView,
    QDialogButtonBox
)
from PyQt6.QtCore import Qt
import mne
import numpy as np

class PickMontageWindow(QDialog):
    def __init__(self, parent, channel_names):
        super().__init__(parent)
        self.setWindowTitle("Set Montage")
        self.resize(600, 400)
        
        self.channel_names = channel_names
        self.check_data()
        
        self.chs = None
        self.positions = None
        self.options = []
        
        self.init_ui()
        
    def check_data(self):
        if not self.channel_names:
            QMessageBox.critical(self, "Error", "No valid channel name is provided")
            self.reject()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Top: Montage Selection
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Montage:"))
        
        self.montage_combo = QComboBox()
        self.montage_list = mne.channels.get_builtin_montages()
        self.montage_combo.addItems(self.montage_list)
        self.montage_combo.currentTextChanged.connect(self.on_montage_select)
        top_layout.addWidget(self.montage_combo)
        
        layout.addLayout(top_layout)
        
        # Middle: Lists and Buttons
        mid_layout = QHBoxLayout()
        
        # Left: Available Options
        left_vbox = QVBoxLayout()
        left_vbox.addWidget(QLabel("Available Channels"))
        self.option_list = QListWidget()
        self.option_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        left_vbox.addWidget(self.option_list)
        mid_layout.addLayout(left_vbox)
        
        # Center: Buttons
        btn_vbox = QVBoxLayout()
        btn_vbox.addStretch()
        self.btn_add = QPushButton(">>")
        self.btn_add.clicked.connect(self.add_channels)
        btn_vbox.addWidget(self.btn_add)
        
        self.btn_remove = QPushButton("<<")
        self.btn_remove.clicked.connect(self.remove_channels)
        btn_vbox.addWidget(self.btn_remove)
        btn_vbox.addStretch()
        mid_layout.addLayout(btn_vbox)
        
        # Right: Selected Channels
        right_vbox = QVBoxLayout()
        self.selected_label = QLabel("Selected: 0")
        right_vbox.addWidget(self.selected_label)
        self.selected_list = QListWidget()
        self.selected_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        right_vbox.addWidget(self.selected_list)
        mid_layout.addLayout(right_vbox)
        
        layout.addLayout(mid_layout)
        
        # Bottom: Dialog Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.confirm)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        # Initialize with first montage
        if self.montage_list:
            self.on_montage_select(self.montage_list[0])

    def on_montage_select(self, montage_name):
        self.option_list.clear()
        self.selected_list.clear()
        
        try:
            montage = mne.channels.make_standard_montage(montage_name)
            self.options = list(montage.get_positions()['ch_pos'].keys())
            self.option_list.addItems(self.options)
            
            # Auto-select matching channels
            for ch in self.channel_names:
                if ch in self.options:
                    self.selected_list.addItem(ch)
                else:
                    # Stop at first mismatch? Original code did 'break'
                    break
            
            self.update_count()
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load montage: {e}")

    def add_channels(self):
        selected_items = self.option_list.selectedItems()
        current_selected = [self.selected_list.item(i).text() for i in range(self.selected_list.count())]
        
        for item in selected_items:
            text = item.text()
            if text not in current_selected:
                self.selected_list.addItem(text)
        
        self.update_count()

    def remove_channels(self):
        # Remove selected items from the selected_list
        # We need to collect rows first because removing items changes indices
        selected_items = self.selected_list.selectedItems()
        for item in selected_items:
            # takeItem requires row index
            row = self.selected_list.row(item)
            self.selected_list.takeItem(row)
            
        self.update_count()

    def update_count(self):
        self.selected_label.setText(f"Selected: {self.selected_list.count()}")

    def get_selected(self):
        return [self.selected_list.item(i).text() for i in range(self.selected_list.count())]

    def confirm(self):
        chs = self.get_selected()
        if len(chs) != len(self.channel_names):
            QMessageBox.warning(
                self, "Mismatch", 
                f"Number of channels mismatch ({len(chs)} != {len(self.channel_names)})"
            )
            return

        try:
            montage = mne.channels.make_standard_montage(self.montage_combo.currentText())
            positions = np.array([montage.get_positions()['ch_pos'][ch] for ch in chs])
            self.chs = chs
            self.positions = positions
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error processing montage: {e}")

    def get_result(self):
        return self.chs, self.positions
