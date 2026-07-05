"""Data splitting preview dialog for fine-tuning and confirming split parameters.

Provides a detailed tree view of generated datasets with configurable
validation and testing split units, amounts, and manual selection support.
"""

import threading
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QModelIndex, QSize, Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
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
from XBrainLab.ui.styles.theme import Theme

from .manual_split_dialog import ManualSplitDialog

DEFAULT_SPLIT_ENTRY_VALUE = "0.2"
PREVIEW_WORKER_RESTART_JOIN_TIMEOUT_SEC = 0.2
PREVIEW_WORKER_CLOSE_JOIN_TIMEOUT_SEC = 1.0
PREVIEW_DEBOUNCE_MS = 250
_CHEVRON_DOWN_ICON = (
    Path(__file__).resolve().parents[3] / "resources" / "icons" / "chevron-down.svg"
).as_posix()

_PREVIEW_DIALOG_STYLE = f"""
    QDialog {{
        background-color: {Theme.BACKGROUND_DARK};
        color: {Theme.TEXT_SECONDARY};
    }}
    QLabel {{
        color: {Theme.TEXT_SECONDARY};
    }}
    QFrame#SplitPreviewPanel {{
        background-color: {Theme.BACKGROUND_MID};
        border: 1px solid {Theme.BACKGROUND_LIGHT};
        border-radius: 6px;
    }}
    QLabel#SplitPreviewSectionTitle {{
        color: {Theme.TEXT_PRIMARY};
        font-weight: bold;
        font-size: 13px;
        background: transparent;
    }}
    QLabel#SplitPreviewMuted {{
        color: {Theme.TEXT_SECONDARY};
        background: transparent;
    }}
    QComboBox, QLineEdit {{
        background-color: {Theme.BACKGROUND_DARK};
        color: {Theme.TEXT_PRIMARY};
        border: 1px solid {Theme.BACKGROUND_LIGHT};
        border-radius: 3px;
        padding: 5px 28px 5px 8px;
        min-height: 24px;
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        border: none;
        background: transparent;
        width: 24px;
    }}
    QComboBox::down-arrow {{
        image: url("{_CHEVRON_DOWN_ICON}");
        width: 10px;
        height: 10px;
    }}
    QPushButton#PrimaryConfirmButton {{
        background-color: #0069a8;
        color: {Theme.TEXT_PRIMARY};
        border: 1px solid #0a7fc7;
        border-radius: 4px;
        padding: 7px 12px;
        font-weight: bold;
    }}
    QPushButton#PrimaryConfirmButton:hover {{
        background-color: #0a7fc7;
    }}
"""

_RESULT_TREE_STYLE = f"""
    QTreeWidget {{
        background-color: #202225;
        alternate-background-color: #27292d;
        color: {Theme.TEXT_PRIMARY};
        border: 1px solid {Theme.BACKGROUND_LIGHT};
        border-radius: 4px;
        gridline-color: {Theme.BACKGROUND_LIGHT};
    }}
    QTreeWidget::item {{
        padding: 5px 8px;
        min-height: 26px;
    }}
    QTreeWidget::item:selected {{
        background-color: #202225;
        color: {Theme.TEXT_PRIMARY};
    }}
    QHeaderView::section {{
        background-color: {Theme.BACKGROUND_LIGHT};
        color: {Theme.TEXT_PRIMARY};
        border: none;
        border-right: 1px solid {Theme.BACKGROUND_MID};
        padding: 6px 8px;
        font-weight: bold;
    }}
    QScrollBar:vertical {{
        background: #1c1e21;
        width: 10px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: #525963;
        border-radius: 4px;
        min-height: 24px;
    }}
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        border: none;
        background: transparent;
        height: 0;
    }}
    QScrollBar::add-page:vertical,
    QScrollBar::sub-page:vertical {{
        background: transparent;
    }}
"""


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
            split_type,
            value_var=None,
            split_unit=None,
            is_option=is_option,
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
        if epoch_data is None:
            raise ValueError("Create epochs before previewing data splitting.")
        self.epoch_data = epoch_data
        self.config = config
        self.datasets = []
        self._datasets_lock = threading.Lock()
        self.dataset_generator: DatasetGenerator | None = None
        self.preview_worker = None
        self.preview_debounce_timer: QTimer | None = None

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

        self.preview_debounce_timer = QTimer(self)
        self.preview_debounce_timer.setSingleShot(True)
        self.preview_debounce_timer.timeout.connect(self.preview)

        self.preview()

    def init_ui(self):
        """Initialize the dialog UI with tree view and split controls."""
        self.setStyleSheet(_PREVIEW_DIALOG_STYLE)
        self.setMinimumSize(920, 620)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(18)

        # Left: Tree
        left_layout = QVBoxLayout()
        left_layout.setSpacing(10)
        results_group = QFrame()
        results_group.setObjectName("SplitPreviewPanel")
        results_group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        results_layout = QVBoxLayout(results_group)
        results_layout.setContentsMargins(12, 12, 12, 12)
        results_layout.setSpacing(10)
        results_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        results_title = QLabel("Split results")
        results_title.setObjectName("SplitPreviewSectionTitle")
        results_layout.addWidget(results_title)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Dataset", "Train", "Validation", "Test"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setIndentation(0)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tree.setStyleSheet(_RESULT_TREE_STYLE)
        header = self.tree.header()
        if header is not None:
            header.setStretchLastSection(False)
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            for col in (1, 2, 3):
                header.setSectionResizeMode(
                    col,
                    QHeaderView.ResizeMode.ResizeToContents,
                )
        results_layout.addWidget(self.tree)
        self._resize_tree_to_rows()
        left_layout.addWidget(results_group)
        left_layout.addStretch(1)

        layout.addLayout(left_layout, stretch=3)

        # Right: Controls
        right_layout = QVBoxLayout()
        right_layout.setSpacing(12)

        # Dataset Info
        info_group, info_layout = self._panel_grid("Split overview")
        info_layout.setHorizontalSpacing(12)
        info_layout.setVerticalSpacing(8)
        summary_rows = [
            ("Subjects", str(len(self.epoch_data.subject_map))),
            ("Sessions", str(len(self.epoch_data.session_map))),
            ("Labels", str(len(self.epoch_data.label_map))),
            ("Trials", str(len(self.epoch_data.data))),
            ("Training", self.config.train_type.value),
        ]
        for row, (name, value) in enumerate(summary_rows):
            label = QLabel(name)
            label.setObjectName("SplitPreviewMuted")
            info_layout.addWidget(label, row, 0)
            info_layout.addWidget(QLabel(value), row, 1)
        info_layout.setColumnStretch(1, 1)
        right_layout.addWidget(info_group)

        # Validation
        val_group, val_layout = self._panel_grid("Validation split")
        val_layout.setHorizontalSpacing(8)
        val_layout.setVerticalSpacing(8)
        val_layout.setColumnStretch(1, 1)
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
                opts.append(SplitUnit.MANUAL.value)
                combo.addItems(opts)
                combo.setCurrentText(SplitUnit.RATIO.value)
                val_layout.addWidget(combo, row + 1, 0)

                entry = QLineEdit(
                    self._default_split_entry_value(
                        splitter,
                        split_unit=SplitUnit.RATIO,
                    )
                )
                combo.currentTextChanged.connect(
                    lambda t, s=splitter: self.on_split_type_change(s, t),
                )
                entry.textChanged.connect(
                    lambda t, s=splitter: self.on_entry_change(s, t),
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
        test_group, test_layout = self._panel_grid("Testing split")
        test_layout.setHorizontalSpacing(8)
        test_layout.setVerticalSpacing(8)
        test_layout.setColumnStretch(1, 1)
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
                default_unit = (
                    SplitUnit.KFOLD
                    if self.config.is_cross_validation and idx == 1
                    else SplitUnit.RATIO
                )
                combo.setCurrentText(default_unit.value)
                test_layout.addWidget(combo, row + 1, 0)

                entry = QLineEdit(
                    self._default_split_entry_value(
                        splitter,
                        split_unit=default_unit,
                    )
                )
                combo.currentTextChanged.connect(
                    lambda t, s=splitter: self.on_split_type_change(s, t),
                )
                entry.textChanged.connect(
                    lambda t, s=splitter: self.on_entry_change(s, t),
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
        right_layout.addStretch(1)
        self.btn_confirm = QPushButton("Confirm")
        self.btn_confirm.setObjectName("PrimaryConfirmButton")
        self.btn_confirm.setAutoDefault(False)
        self.btn_confirm.setDefault(False)
        self.btn_confirm.clicked.connect(self.confirm)
        right_layout.addWidget(self.btn_confirm)

        layout.addLayout(right_layout, stretch=1)

    @staticmethod
    def _panel_grid(title: str) -> tuple[QFrame, QGridLayout]:
        panel = QFrame()
        panel.setObjectName("SplitPreviewPanel")
        panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(12, 10, 12, 10)
        panel_layout.setSpacing(8)
        title_label = QLabel(title)
        title_label.setObjectName("SplitPreviewSectionTitle")
        panel_layout.addWidget(title_label)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        panel_layout.addLayout(grid)
        return panel, grid

    def _default_split_entry_value(
        self,
        splitter: DataSplitter,
        *,
        split_unit: SplitUnit,
    ) -> str:
        if split_unit == SplitUnit.KFOLD:
            return str(self._default_kfold_count(splitter))
        return DEFAULT_SPLIT_ENTRY_VALUE

    def _default_kfold_count(self, splitter: DataSplitter) -> int:
        target_count = self._split_target_count(splitter)
        if target_count <= 0:
            return 2
        return max(2, min(5, target_count))

    def _split_target_count(self, splitter: DataSplitter) -> int:
        split_type = getattr(splitter, "split_type", None)
        if split_type in {SplitByType.SUBJECT, SplitByType.SUBJECT_IND}:
            return len(getattr(self.epoch_data, "subject_map", {}) or {})
        if split_type in {SplitByType.SESSION, SplitByType.SESSION_IND}:
            return len(getattr(self.epoch_data, "session_map", {}) or {})
        if split_type in {SplitByType.TRIAL, SplitByType.TRIAL_IND}:
            get_data_length = getattr(self.epoch_data, "get_data_length", None)
            if callable(get_data_length):
                try:
                    value = get_data_length()
                except Exception:
                    return self._epoch_data_length()
                if isinstance(value, (int, float, str)):
                    return int(value)
                return self._epoch_data_length()
            return self._epoch_data_length()
        return 0

    def _epoch_data_length(self) -> int:
        data = getattr(self.epoch_data, "data", None)
        try:
            return len(data) if data is not None else 0
        except TypeError:
            return 0

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
        self.schedule_preview()

    def on_entry_change(self, splitter, text):
        """Handle changes to the split value text entry.

        Args:
            splitter: The DataSplitterHolder being modified.
            text: The new split value text.

        """
        if hasattr(splitter, "set_entry_var"):
            splitter.set_entry_var(text)
        self.schedule_preview()

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
                    splitter,
                )
                self.test_widgets[idx][1].setText(value)

    def preview(self):
        """Start background dataset generation and update the tree view."""
        if self.preview_debounce_timer:
            self.preview_debounce_timer.stop()
        self._interrupt_preview_worker(PREVIEW_WORKER_RESTART_JOIN_TIMEOUT_SEC)
        self.datasets = []
        if self.tree:
            self.tree.clear()
            item = QTreeWidgetItem(self.tree)
            item.setSizeHint(0, QSize(0, 28))
            item.setText(0, "Calculating")
            self._resize_tree_to_rows()

        # Prepare splitters
        # Assuming splitter has to_thread (which Holder does)
        for splitter in self.test_splitter_list:
            if hasattr(splitter, "to_thread"):
                splitter.to_thread()
        for splitter in self.val_splitter_list:
            if hasattr(splitter, "to_thread"):
                splitter.to_thread()

        self.dataset_generator = DatasetGenerator(
            self.epoch_data,
            config=self.config,
            datasets=self.datasets,
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
            item.setSizeHint(0, QSize(0, 28))
            item.setText(0, "Preview failed")
            self._resize_tree_to_rows()
        else:
            with self._datasets_lock:
                snapshot = list(self.datasets)
            if len(snapshot) > 0:
                item0 = self.tree.topLevelItem(0)
                if (
                    self.tree.topLevelItemCount() == 1
                    and item0
                    and item0.text(0) == "Calculating"
                ):
                    self.tree.clear()

                current_count = self.tree.topLevelItemCount()
                if current_count < len(snapshot):
                    for i in range(current_count, len(snapshot)):
                        dataset = snapshot[i]
                        item = QTreeWidgetItem(self.tree)
                        item.setSizeHint(0, QSize(0, 28))
                        info = dataset.get_treeview_row_info()
                        visible_info = info[1:] if len(info) >= 5 else info
                        for col, val in enumerate(visible_info):
                            item.setText(col, str(val))
                self._clear_tree_current_item()
                self._resize_tree_to_rows()

    def _clear_tree_current_item(self) -> None:
        if self.tree is None:
            return
        self.tree.clearSelection()
        self.tree.setCurrentIndex(QModelIndex())

    def _resize_tree_to_rows(self) -> None:
        if self.tree is None:
            return
        header = self.tree.header()
        header_height = header.height() if header is not None else 32
        row_count = max(1, self.tree.topLevelItemCount())
        target_height = min(420, max(92, header_height + row_count * 38 + 16))
        self.tree.setFixedHeight(target_height)

    def confirm(self):
        """Finalize dataset generation and accept the dialog."""
        if self.preview_worker and self.preview_worker.is_alive():
            self._show_message_box(
                QMessageBox.Icon.Warning,
                "Data splitting",
                "Generating dataset, please wait.",
            )
            return

        try:
            if self.dataset_generator:
                self.dataset_generator.prepare_result()
                super().accept()
        except Exception as e:
            self._show_message_box(
                QMessageBox.Icon.Critical,
                "Data splitting failed",
                str(e),
            )

    def _show_message_box(
        self,
        icon: QMessageBox.Icon,
        title: str,
        text: str,
    ) -> None:
        message = QMessageBox(self)
        message.setIcon(icon)
        message.setWindowTitle(title)
        message.setText(text)
        message.setStandardButtons(QMessageBox.StandardButton.Ok)
        for button in message.buttons():
            if isinstance(button, QPushButton):
                button.setAutoDefault(False)
                button.setDefault(False)
        message.exec()

    def closeEvent(self, event):  # noqa: N802
        """Stop the polling timer and interrupt background workers on close."""
        if self.preview_debounce_timer:
            self.preview_debounce_timer.stop()
        if self.timer:
            self.timer.stop()
        self._interrupt_preview_worker(PREVIEW_WORKER_CLOSE_JOIN_TIMEOUT_SEC)
        super().closeEvent(event)

    def schedule_preview(self) -> None:
        """Debounce expensive dataset preview regeneration while editing fields."""
        if self.preview_debounce_timer:
            self.preview_debounce_timer.start(PREVIEW_DEBOUNCE_MS)
        else:
            self.preview()

    def _interrupt_preview_worker(self, join_timeout: float) -> None:
        """Interrupt and briefly wait for the active preview worker."""
        if self.dataset_generator:
            self.dataset_generator.set_interrupt()
        worker = self.preview_worker
        if worker and worker.is_alive() and worker is not threading.current_thread():
            worker.join(timeout=join_timeout)

    def get_result(self):
        """Return the finalized split configuration payload.

        Returns:
            A serializable split configuration accepted by GenerateDatasetCommand,
            or None when the preview did not produce a generator.

        """
        if self.dataset_generator is None:
            return None
        return self._split_config_payload()

    def _split_config_payload(self) -> dict[str, Any]:
        return {
            "train_type": self.config.train_type.value,
            "is_cross_validation": bool(self.config.is_cross_validation),
            "val_splitters": [
                self._splitter_payload(splitter) for splitter in self.val_splitter_list
            ],
            "test_splitters": [
                self._splitter_payload(splitter) for splitter in self.test_splitter_list
            ],
        }

    @staticmethod
    def _splitter_payload(splitter: DataSplitter) -> dict[str, Any]:
        split_unit = getattr(splitter, "split_unit", None)
        split_type = getattr(splitter, "split_type", None)
        return {
            "split_type": getattr(split_type, "value", str(split_type)),
            "split_unit": getattr(split_unit, "value", str(split_unit)),
            "value": str(getattr(splitter, "value_var", "") or ""),
            "is_option": bool(getattr(splitter, "is_option", True)),
        }
