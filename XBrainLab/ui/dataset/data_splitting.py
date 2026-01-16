import threading

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from XBrainLab.backend.dataset import (
    DatasetGenerator,
    DataSplitter,
    SplitUnit,
)

from .split_chooser import ManualSplitChooser

DEFAULT_SPLIT_ENTRY_VALUE = "0.2"

class DataSplitterHolder(DataSplitter):
    def __init__(self, is_option, split_type):
        super().__init__(
            split_type, value_var=None, split_unit=None, is_option=is_option
        )

    def set_split_unit_var(self, val):
        # val is the string representation from the ComboBox
        self.split_unit = None
        for unit in SplitUnit:
            if unit.value == val:
                self.split_unit = unit
                break

    def set_entry_var(self, val):
        self.value_var = val

    def to_thread(self):
        # State is already updated via setters.
        # No need to "commit" state or cache validation.
        pass

class DataSplittingWindow(QDialog):
    def __init__(self, parent, title, epoch_data, config):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(800, 600)

        self.epoch_data = epoch_data
        self.config = config
        self.datasets = []
        self.dataset_generator = None
        self.preview_worker = None

        self.init_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_table)
        self.timer.start(500)

        self.preview()

    def init_ui(self):
        layout = QHBoxLayout(self)

        # Left: Tree
        left_layout = QVBoxLayout()
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['select', 'name', 'train', 'val', 'test'])
        left_layout.addWidget(self.tree)

        self.btn_info = QPushButton("Show info")
        self.btn_info.clicked.connect(self.show_info)
        left_layout.addWidget(self.btn_info)
        layout.addLayout(left_layout, stretch=1)

        # Right: Controls
        right_layout = QVBoxLayout()

        # Dataset Info
        info_group = QGroupBox("Dataset Info")
        info_layout = QGridLayout(info_group)
        info_layout.addWidget(QLabel("Subject:"), 0, 0)
        info_layout.addWidget(QLabel(str(len(self.epoch_data.subject_map))), 0, 1)
        info_layout.addWidget(QLabel("Session:"), 1, 0)
        info_layout.addWidget(QLabel(str(len(self.epoch_data.session_map))), 1, 1)
        info_layout.addWidget(QLabel("Label:"), 2, 0)
        info_layout.addWidget(QLabel(str(len(self.epoch_data.label_map))), 2, 1)
        info_layout.addWidget(QLabel("Trial:"), 3, 0)
        info_layout.addWidget(QLabel(str(len(self.epoch_data.data))), 3, 1)
        right_layout.addWidget(info_group)

        # Training Type
        train_group = QGroupBox("Training type")
        train_layout = QVBoxLayout(train_group)
        train_layout.addWidget(QLabel(self.config.train_type.value))
        right_layout.addWidget(train_group)

        # Validation
        val_group = QGroupBox("Validation")
        val_layout = QGridLayout(val_group)
        self.val_widgets = []

        split_unit_list = [i.value for i in SplitUnit if i not in [SplitUnit.KFOLD, SplitUnit.MANUAL]]
        val_splitter_list, test_splitter_list = self.config.get_splitter_option()
        self.val_splitter_list = val_splitter_list
        self.test_splitter_list = test_splitter_list

        row = 0
        idx = 0
        for splitter in val_splitter_list:
            if splitter.is_option:
                idx += 1
                lbl = QLabel(splitter.text)
                val_layout.addWidget(lbl, row, 0, 1, 2)

                combo = QComboBox()
                opts = list(split_unit_list)
                if self.config.is_cross_validation and idx == 1:
                    opts.append(SplitUnit.KFOLD.value)
                else:
                    opts.append(SplitUnit.MANUAL.value)
                combo.addItems(opts)
                combo.currentTextChanged.connect(lambda t, s=splitter: self.on_split_type_change(s, t))
                val_layout.addWidget(combo, row+1, 0)

                entry = QLineEdit(DEFAULT_SPLIT_ENTRY_VALUE)
                entry.textChanged.connect(lambda t, s=splitter: self.on_entry_change(s, t))
                val_layout.addWidget(entry, row+1, 1)

                # Init splitter vars
                splitter.set_split_unit_var(combo.currentText())
                splitter.set_entry_var(entry.text())

                self.val_widgets.append((combo, entry))
                row += 2
            else:
                val_layout.addWidget(QLabel(splitter.text), row, 0, 1, 2)
                row += 1
        right_layout.addWidget(val_group)

        # Testing
        test_group = QGroupBox("Testing")
        test_layout = QGridLayout(test_group)
        row = 0
        if self.config.is_cross_validation:
            test_layout.addWidget(QLabel("Cross Validation"), row, 0, 1, 2)
            row += 1

        idx = 0
        self.test_widgets = []
        for splitter in test_splitter_list:
            if splitter.is_option:
                idx += 1
                lbl = QLabel(splitter.text)
                test_layout.addWidget(lbl, row, 0, 1, 2)

                combo = QComboBox()
                opts = list(split_unit_list)
                if self.config.is_cross_validation and idx == 1:
                    opts.append(SplitUnit.KFOLD.value)
                else:
                    opts.append(SplitUnit.MANUAL.value)
                combo.addItems(opts)
                combo.currentTextChanged.connect(lambda t, s=splitter: self.on_split_type_change(s, t))
                test_layout.addWidget(combo, row+1, 0)

                entry = QLineEdit(DEFAULT_SPLIT_ENTRY_VALUE)
                entry.textChanged.connect(lambda t, s=splitter: self.on_entry_change(s, t))
                test_layout.addWidget(entry, row+1, 1)

                splitter.set_split_unit_var(combo.currentText())
                splitter.set_entry_var(entry.text())

                self.test_widgets.append((combo, entry))
                row += 2
            else:
                test_layout.addWidget(QLabel(splitter.text), row, 0, 1, 2)
                row += 1
        right_layout.addWidget(test_group)

        # Confirm
        self.btn_confirm = QPushButton("Confirm")
        self.btn_confirm.clicked.connect(self.confirm)
        right_layout.addWidget(self.btn_confirm)

        layout.addLayout(right_layout)

    def on_split_type_change(self, splitter, text):
        splitter.set_split_unit_var(text)
        if text == SplitUnit.MANUAL.value:
            self.handle_manual_split(splitter)
        self.preview()

    def on_entry_change(self, splitter, text):
        splitter.set_entry_var(text)
        self.preview()

    def handle_manual_split(self, splitter):
        # Logic to open ManualSplitChooser
        # Need to determine choices based on split_type
        from XBrainLab.backend.dataset import SplitByType, ValSplitByType

        choices = []
        if splitter.split_type in [SplitByType.SESSION, SplitByType.SESSION_IND, ValSplitByType.SESSION]:
            choices = list(self.epoch_data.get_session_map().items())
        elif splitter.split_type in [SplitByType.TRIAL, SplitByType.TRIAL_IND, ValSplitByType.TRIAL]:
            choices = list(range(self.epoch_data.get_data_length()))
            choices = [(c, c) for c in choices]
        elif splitter.split_type in [SplitByType.SUBJECT, SplitByType.SUBJECT_IND, ValSplitByType.SUBJECT]:
            choices = list(self.epoch_data.get_subject_map().items())

        dlg = ManualSplitChooser(self, choices)
        if dlg.exec():
            result = dlg.get_result()
            value = " ".join(map(str, result)) + " "
            # Find the entry widget corresponding to this splitter and update it
            # This is a bit tricky since we don't have direct ref to widget in splitter
            # But we updated splitter.entry_var.
            # We need to update the UI QLineEdit.
            # Let's iterate widgets to find match? Or just trigger update.
            # In init_ui I stored widgets in lists.
            # Let's assume the order matches.

            # Find index in list
            if splitter in self.val_splitter_list:
                idx = [s for s in self.val_splitter_list if s.is_option].index(splitter)
                self.val_widgets[idx][1].setText(value)
            elif splitter in self.test_splitter_list:
                idx = [s for s in self.test_splitter_list if s.is_option].index(splitter)
                self.test_widgets[idx][1].setText(value)

    def preview(self):
        self.datasets = []
        self.tree.clear()
        item = QTreeWidgetItem(self.tree)
        item.setText(0, "...")
        item.setText(1, "calculating")

        # Prepare splitters
        for splitter in self.test_splitter_list:
            splitter.to_thread()
        for splitter in self.val_splitter_list:
            splitter.to_thread()

        if self.dataset_generator:
            self.dataset_generator.set_interrupt()

        self.dataset_generator = DatasetGenerator(
            self.epoch_data, config=self.config, datasets=self.datasets
        )
        self.preview_worker = threading.Thread(target=self.dataset_generator.generate)
        self.preview_worker.start()

    def update_table(self):
        if self.dataset_generator and self.dataset_generator.preview_failed:
             self.tree.clear()
             item = QTreeWidgetItem(self.tree)
             item.setText(1, "Nan")
        elif len(self.datasets) > 0:
            if self.tree.topLevelItemCount() == 1 and self.tree.topLevelItem(0).text(0) == "...":
                self.tree.clear()

            current_count = self.tree.topLevelItemCount()
            if current_count < len(self.datasets):
                for i in range(current_count, len(self.datasets)):
                    dataset = self.datasets[i]
                    item = QTreeWidgetItem(self.tree)
                    info = dataset.get_treeview_row_info()
                    for col, val in enumerate(info):
                        item.setText(col, str(val))

    def show_info(self):
        item = self.tree.currentItem()
        if not item: return
        idx = self.tree.indexOfTopLevelItem(item)
        if idx < 0 or idx >= len(self.datasets): return

        target = self.datasets[idx]
        # Show info window (Not implemented here, but could be another dialog)
        QMessageBox.information(self, "Info", f"Dataset: {target.name}\nTrain: {sum(target.train_mask)}\nVal: {sum(target.val_mask)}\nTest: {sum(target.test_mask)}")

    def confirm(self):
        if self.preview_worker and self.preview_worker.is_alive():
            QMessageBox.warning(self, "Warning", "Generating dataset, please wait.")
            return

        try:
            self.dataset_generator.prepare_reuslt()
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def get_result(self):
        return self.dataset_generator
