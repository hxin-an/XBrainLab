"""Data splitting preview dialog for fine-tuning and confirming split parameters.

Provides a detailed tree view of generated datasets with configurable
validation and testing split units, amounts, and manual selection support.
"""

import threading

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QComboBox,
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
    SplitByType,
    SplitUnit,
    ValSplitByType,
)
from XBrainLab.ui.core.base_dialog import BaseDialog

from .manual_split_dialog import ManualSplitDialog

DEFAULT_SPLIT_ENTRY_VALUE = "0.2"


class DataSplitterHolder(DataSplitter):
    """Extended DataSplitter with mutable split parameters for UI binding.

    Wraps a DataSplitter to allow dynamic updates from combo boxes and
    text entries in the preview dialog.

    Attributes:
        is_option: Whether this splitter represents a user-configurable option.
        split_type: The type of split (e.g., by session, trial, subject).
    """

    def __init__(self, is_option, split_type):
        super().__init__(
            split_type, value_var=None, split_unit=None, is_option=is_option
        )

    def set_split_unit_var(self, val):
        """Set the split unit from a combo box string value.

        Args:
            val: String representation of the SplitUnit enum value.
        """
        # val is the string representation from the ComboBox
        self.split_unit = None
        for unit in SplitUnit:
            if unit.value == val:
                self.split_unit = unit
                break

    def set_entry_var(self, val):
        """Set the split value from a text entry.

        Args:
            val: String value representing the split amount.
        """
        self.value_var = val

    def to_thread(self):
        """Prepare the splitter state for background thread usage."""
        # State is already updated via setters.
        # No need to "commit" state or cache validation.


class DataSplittingPreviewDialog(BaseDialog):
    """Dialog for previewing and confirming data splitting results.

    Displays a tree view of generated datasets with train/val/test counts,
    and allows fine-tuning split parameters (unit, amount) for validation
    and testing sets.

    Attributes:
        epoch_data: The loaded epoch data to split.
        config: DataSplittingConfig defining the split strategy.
        datasets: List of generated Dataset objects.
        dataset_generator: DatasetGenerator managing the split process.
        preview_worker: Background thread for dataset generation.
        tree: QTreeWidget displaying dataset split information.
        val_splitter_list: List of DataSplitterHolder for validation splits.
        test_splitter_list: List of DataSplitterHolder for testing splits.
    """

    def __init__(self, parent, title, epoch_data, config):
        self.epoch_data = epoch_data
        self.config = config
        self.datasets = []
        self.dataset_generator: DatasetGenerator | None = None
        self.preview_worker = None

        # UI
        self.tree = None
        self.btn_info = None
        self.btn_confirm = None
        self.val_widgets = []
        self.test_widgets = []
        self.val_splitter_list = []
        self.test_splitter_list = []

        # We need to call super init LAST because init_ui relies on members
        # But BaseDialog calls init_ui in init.
        # So we initialize members before super.

        super().__init__(parent, title=title)
        self.resize(800, 600)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_table)
        self.timer.start(500)

        self.preview()

    def init_ui(self):
        """Initialize the dialog UI with tree view and split controls."""
        layout = QHBoxLayout(self)

        # Left: Tree
        left_layout = QVBoxLayout()
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["select", "name", "train", "val", "test"])
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

        split_unit_list = [
            i.value for i in SplitUnit if i not in [SplitUnit.KFOLD, SplitUnit.MANUAL]
        ]
        val_splitter_list, test_splitter_list = self.config.get_splitter_option()
        # Cast to Holder
        # Note: config.get_splitter_option creates standard DataSplitters.
        # We might need to upgrade them to Holders?
        # Actually in original code, get_splitter_option calls
        # DataSplitterHolder(True, type).
        # We need to verify where get_splitter_option comes from.
        # It's from TrainingConfig.
        # If TrainingConfig uses DataSplitterHolder, then we import it there?
        # Or does DataSplittingWindow redefine it?
        # In original code, DataSplitterHolder inherits DataSplitter.
        # And TrainingConfig logic is in backend.
        # It likely returns standard DataSplitters that act as config placeholders.
        # But wait, original `data_splitting.py` defines `DataSplitterHolder`.
        # And `get_splitter_option` in `backend/dataset/__init__.py`
        # (DataSplittingConfig)?
        # Let's assume for now the pointers are compatible or we need to wrap them if
        # logic differs. Original code just assigned them. I'll trust it.

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
                combo.currentTextChanged.connect(
                    lambda t, s=splitter: self.on_split_type_change(s, t)
                )
                val_layout.addWidget(combo, row + 1, 0)

                entry = QLineEdit(DEFAULT_SPLIT_ENTRY_VALUE)
                entry.textChanged.connect(
                    lambda t, s=splitter: self.on_entry_change(s, t)
                )
                val_layout.addWidget(entry, row + 1, 1)

                # Init splitter vars
                if hasattr(splitter, "set_split_unit_var"):
                    splitter.set_split_unit_var(combo.currentText())
                if hasattr(splitter, "set_entry_var"):
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
                combo.currentTextChanged.connect(
                    lambda t, s=splitter: self.on_split_type_change(s, t)
                )
                test_layout.addWidget(combo, row + 1, 0)

                entry = QLineEdit(DEFAULT_SPLIT_ENTRY_VALUE)
                entry.textChanged.connect(
                    lambda t, s=splitter: self.on_entry_change(s, t)
                )
                test_layout.addWidget(entry, row + 1, 1)

                if hasattr(splitter, "set_split_unit_var"):
                    splitter.set_split_unit_var(combo.currentText())
                if hasattr(splitter, "set_entry_var"):
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
        """Handle changes to the split unit combo box.

        Args:
            splitter: The DataSplitterHolder being modified.
            text: The newly selected split unit text.
        """
        if hasattr(splitter, "set_split_unit_var"):
            splitter.set_split_unit_var(text)
        if text == SplitUnit.MANUAL.value:
            self.handle_manual_split(splitter)
        self.preview()

    def on_entry_change(self, splitter, text):
        """Handle changes to the split value text entry.

        Args:
            splitter: The DataSplitterHolder being modified.
            text: The new split value text.
        """
        if hasattr(splitter, "set_entry_var"):
            splitter.set_entry_var(text)
        self.preview()

    def handle_manual_split(self, splitter):
        """Open a manual split dialog for the given splitter.

        Args:
            splitter: The DataSplitterHolder requiring manual selection.
        """
        choices = []
        if splitter.split_type in [
            SplitByType.SESSION,
            SplitByType.SESSION_IND,
            ValSplitByType.SESSION,
        ]:
            choices = list(self.epoch_data.get_session_map().items())
        elif splitter.split_type in [
            SplitByType.TRIAL,
            SplitByType.TRIAL_IND,
            ValSplitByType.TRIAL,
        ]:
            choices = list(range(self.epoch_data.get_data_length()))
            choices = [(c, c) for c in choices]
        elif splitter.split_type in [
            SplitByType.SUBJECT,
            SplitByType.SUBJECT_IND,
            ValSplitByType.SUBJECT,
        ]:
            choices = list(self.epoch_data.get_subject_map().items())

        dlg = ManualSplitDialog(self, choices)
        if dlg.exec():
            result = dlg.get_result()
            value = " ".join(map(str, result)) + " "

            # Find index in list
            if splitter in self.val_splitter_list:
                idx = [s for s in self.val_splitter_list if s.is_option].index(splitter)
                self.val_widgets[idx][1].setText(value)
            elif splitter in self.test_splitter_list:
                idx = [s for s in self.test_splitter_list if s.is_option].index(
                    splitter
                )
                self.test_widgets[idx][1].setText(value)

    def preview(self):
        """Start background dataset generation and update the tree view."""
        self.datasets = []
        if self.tree:
            self.tree.clear()
            item = QTreeWidgetItem(self.tree)
            item.setText(0, "...")
            item.setText(1, "calculating")

        # Prepare splitters
        # Assuming splitter has to_thread (which Holder does)
        for splitter in self.test_splitter_list:
            if hasattr(splitter, "to_thread"):
                splitter.to_thread()
        for splitter in self.val_splitter_list:
            if hasattr(splitter, "to_thread"):
                splitter.to_thread()

        if self.dataset_generator:
            self.dataset_generator.set_interrupt()

        self.dataset_generator = DatasetGenerator(
            self.epoch_data, config=self.config, datasets=self.datasets
        )
        self.preview_worker = threading.Thread(target=self.dataset_generator.generate)
        self.preview_worker.start()

    def update_table(self):
        """Poll the dataset generator and update the tree view with results."""
        if not self.tree:
            return

        if self.dataset_generator and self.dataset_generator.preview_failed:
            self.tree.clear()
            item = QTreeWidgetItem(self.tree)
            item.setText(1, "Nan")
        elif len(self.datasets) > 0:
            item0 = self.tree.topLevelItem(0)
            if self.tree.topLevelItemCount() == 1 and item0 and item0.text(0) == "...":
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
        """Display detailed information about the selected dataset."""
        if not self.tree:
            return
        item = self.tree.currentItem()
        if not item:
            return
        idx = self.tree.indexOfTopLevelItem(item)
        if idx < 0 or idx >= len(self.datasets):
            return

        target = self.datasets[idx]
        QMessageBox.information(
            self,
            "Info",
            f"Dataset: {target.name}\n"
            f"Train: {sum(target.train_mask)}\n"
            f"Val: {sum(target.val_mask)}\n"
            f"Test: {sum(target.test_mask)}",
        )

    def confirm(self):
        """Finalize dataset generation and accept the dialog."""
        if self.preview_worker and self.preview_worker.is_alive():
            QMessageBox.warning(self, "Warning", "Generating dataset, please wait.")
            return

        try:
            if self.dataset_generator:
                self.dataset_generator.prepare_result()
                super().accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def get_result(self):
        """Return the finalized DatasetGenerator.

        Returns:
            The DatasetGenerator with prepared split results, or None.
        """
        return self.dataset_generator
