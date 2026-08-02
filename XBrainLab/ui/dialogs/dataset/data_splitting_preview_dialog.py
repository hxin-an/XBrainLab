"""Data splitting preview dialog for fine-tuning and confirming split parameters.

Provides a detailed tree view of generated datasets with configurable
validation and testing split units, amounts, and manual selection support.
"""

import threading
import time
from pathlib import Path
from typing import Any

from PyQt6 import sip
from PyQt6.QtCore import QModelIndex, QSize, Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from XBrainLab.backend.application.dataset_split_preview import (
    DatasetSplitContext,
    DatasetSplitPreviewPublication,
    DatasetSplitPreviewRequest,
    DatasetSplitPreviewRow,
    DatasetSplitSpecification,
)
from XBrainLab.backend.dataset import (
    DataSplitter,
    SplitByType,
    SplitUnit,
    ValSplitByType,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.utils.public_diagnostics import (
    public_exception_message,
)
from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.dialogs.common import checkbox_stylesheet
from XBrainLab.ui.styles.theme import Theme

from .manual_split_dialog import ManualSplitDialog

DEFAULT_SPLIT_ENTRY_VALUE = "0.2"
PREVIEW_DEBOUNCE_MS = 250
PREVIEW_WORKER_CLOSE_RETRY_MS = 100
PREVIEW_WORKER_CLOSE_SLOW_RETRY_MS = 500
PREVIEW_WORKER_SHUTDOWN_TIMEOUT_SEC = 5.0
PREVIEW_STATUS_IDLE = "idle"
PREVIEW_STATUS_RUNNING = "running"
PREVIEW_STATUS_SUCCEEDED = "succeeded"
PREVIEW_STATUS_FAILED = "failed"
PREVIEW_STATUS_CANCELLED = "cancelled"
_PREVIEW_FAILURE_MESSAGE = (
    "The split preview failed. Adjust the split settings and try again."
)
_CHEVRON_DOWN_ICON = (
    Path(__file__).resolve().parents[3] / "resources" / "icons" / "chevron-down.svg"
).as_posix()


def _public_split_failure(error: BaseException, *, fallback: str) -> str:
    return public_exception_message(error, fallback=fallback)


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
        border: none;
        border-radius: 6px;
    }}
    QFrame#SplitPreviewSummaryPanel {{
        background-color: {Theme.BACKGROUND_MID};
        border: none;
        border-radius: 6px;
    }}
    QFrame#SplitPreviewSummaryPanel QLabel {{
        background: transparent;
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
    {checkbox_stylesheet()}
"""

_RESULT_TREE_STYLE = f"""
    QTreeWidget {{
        background-color: {Theme.METRICS_TABLE_BG};
        alternate-background-color: {Theme.METRICS_TABLE_ALT_BG};
        color: {Theme.TEXT_PRIMARY};
        border: none;
        border-radius: 4px;
        gridline-color: transparent;
    }}
    QTreeWidget::viewport {{
        background-color: {Theme.METRICS_TABLE_BG};
        border: none;
    }}
    QTreeWidget::item {{
        padding: 5px 8px;
        min-height: 26px;
    }}
    QTreeWidget::item:selected {{
        background-color: {Theme.TABLE_SELECTION};
        color: {Theme.TEXT_PRIMARY};
    }}
    QHeaderView::section {{
        background-color: {Theme.BACKGROUND_MID};
        color: {Theme.TEXT_SECONDARY};
        border: none;
        border-bottom: 1px solid {Theme.METRICS_TABLE_GRID};
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
        split_context: Detached subject/session/label/trial summary.
        config: DataSplittingConfig defining the split strategy.
        preview_worker: Background thread for dataset generation.
        tree: QTreeWidget displaying dataset split information.
        val_splitter_list: List of DataSplitterHolder for validation splits.
        test_splitter_list: List of DataSplitterHolder for testing splits.

    """

    def __init__(
        self,
        parent,
        title,
        *,
        split_context: DatasetSplitContext | None,
        publication_generation: int | None,
        config: Any,
        preview_provider: Any,
        preview_canceller: Any,
        initial_values: dict[str, str] | None = None,
    ):
        if split_context is None or not split_context.epoch_available:
            raise ValueError("Create EEG epochs before previewing data splitting.")
        if (
            isinstance(publication_generation, bool)
            or not isinstance(publication_generation, int)
            or publication_generation < 1
        ):
            raise ValueError("A current application publication is required.")
        if not callable(preview_provider) or not callable(preview_canceller):
            raise TypeError("Dataset split preview callbacks must be callable.")
        self.split_context = split_context
        self.publication_generation = publication_generation
        self.config = config
        self.preview_provider = preview_provider
        self.preview_canceller = preview_canceller
        self.initial_values = dict(initial_values or {})
        self._preview_state_lock = threading.Lock()
        self._preview_generation_id = 0
        self._preview_status = PREVIEW_STATUS_IDLE
        self._preview_error = ""
        self._preview_rows: tuple[DatasetSplitPreviewRow, ...] = ()
        self._active_preview_request: tuple[int, str] | None = None
        self._cancel_requested_generations: set[int] = set()
        self.preview_worker: threading.Thread | None = None
        self.preview_debounce_timer: QTimer | None = None
        self._preview_close_retry_pending = False
        self._preview_close_started_at: float | None = None
        self._preview_pending_close_action: str | None = None
        self._preview_close_warning_shown = False

        # UI
        self.tree: QTreeWidget | None = None
        self.btn_info: QLabel | None = None
        self.btn_confirm: QPushButton | None = None
        self.val_widgets: list[tuple[QComboBox, QLineEdit]] = []
        self.test_widgets: list[tuple[QComboBox, QLineEdit]] = []
        self.val_splitter_list: list[DataSplitter] = []
        self.test_splitter_list: list[DataSplitter] = []

        # We need to call super init LAST because init_ui relies on members
        # But BaseDialog calls init_ui in init.
        # So we initialize members before super.

        super().__init__(parent, title=title)
        self.fit_to_content(minimum_width=920)

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
        self.setMinimumWidth(920)
        layout = QHBoxLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(18)

        # Left: Tree
        left_layout = QVBoxLayout()
        left_layout.setSpacing(10)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        results_group = QFrame()
        results_group.setObjectName("SplitPreviewPanel")
        results_group.setFrameShape(QFrame.Shape.NoFrame)
        results_group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        results_layout = QVBoxLayout(results_group)
        results_layout.setContentsMargins(12, 12, 12, 12)
        results_layout.setSpacing(10)
        results_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        results_title = QLabel("Split results")
        results_title.setObjectName("SplitPreviewSectionTitle")
        results_layout.addWidget(results_title)
        self.tree = QTreeWidget()
        self.tree.setFrameShape(QFrame.Shape.NoFrame)
        self.tree.setHeaderLabels(["Split", "Train", "Validation", "Test"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setIndentation(0)
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tree.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
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

        layout.addLayout(left_layout, stretch=3)

        # Right: Controls
        right_layout = QVBoxLayout()
        right_layout.setSpacing(12)
        right_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Dataset Info
        info_group, info_layout = self._panel_grid("Split overview")
        info_layout.setHorizontalSpacing(12)
        info_layout.setVerticalSpacing(8)
        summary_rows = [
            ("Subjects", str(self.split_context.subject_count)),
            ("Sessions", str(self.split_context.session_count)),
            ("Labels", str(self.split_context.label_count)),
            ("Trials", str(self.split_context.trial_count)),
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
                        initial_key="validation_ratio",
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
                        initial_key="test_ratio",
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
        self.btn_confirm = QPushButton("Confirm")
        self.btn_confirm.setObjectName("PrimaryConfirmButton")
        self.btn_confirm.setAutoDefault(False)
        self.btn_confirm.setDefault(False)
        self.btn_confirm.clicked.connect(self.confirm)
        right_layout.addWidget(self.btn_confirm)

        layout.addLayout(right_layout, stretch=0)

    @staticmethod
    def _panel_grid(title: str) -> tuple[QFrame, QGridLayout]:
        panel = QFrame()
        panel.setObjectName("SplitPreviewSummaryPanel")
        panel.setFrameShape(QFrame.Shape.NoFrame)
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
        initial_key: str,
    ) -> str:
        if split_unit == SplitUnit.KFOLD:
            return str(self._default_kfold_count(splitter))
        explicit_value = str(self.initial_values.get(initial_key) or "").strip()
        if explicit_value:
            return explicit_value
        return DEFAULT_SPLIT_ENTRY_VALUE

    def _default_kfold_count(self, splitter: DataSplitter) -> int:
        target_count = self._split_target_count(splitter)
        if target_count <= 0:
            return 2
        return max(2, min(5, target_count))

    def _split_target_count(self, splitter: DataSplitter) -> int:
        split_type = getattr(splitter, "split_type", None)
        if split_type in {SplitByType.SUBJECT, SplitByType.SUBJECT_IND}:
            return self.split_context.subject_count
        if split_type in {SplitByType.SESSION, SplitByType.SESSION_IND}:
            return self.split_context.session_count
        if split_type in {SplitByType.TRIAL, SplitByType.TRIAL_IND}:
            return self.split_context.trial_count
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
            choices = [
                (choice.value, choice.label)
                for choice in self.split_context.session_choices
            ]
        elif splitter.split_type in [
            SplitByType.TRIAL,
            SplitByType.TRIAL_IND,
            ValSplitByType.TRIAL,
        ]:
            choices = [
                (trial_index, str(trial_index))
                for trial_index in range(self.split_context.trial_count)
            ]
        elif splitter.split_type in [
            SplitByType.SUBJECT,
            SplitByType.SUBJECT_IND,
            ValSplitByType.SUBJECT,
        ]:
            choices = [
                (choice.value, choice.label)
                for choice in self.split_context.subject_choices
            ]

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
        """Request a detached preview from the application-owned generator."""
        if self.preview_debounce_timer:
            self.preview_debounce_timer.stop()
        if not self._request_preview_worker_stop():
            if self.preview_debounce_timer:
                self.preview_debounce_timer.start(PREVIEW_DEBOUNCE_MS)
            return
        if self.tree:
            self.tree.clear()
            item = QTreeWidgetItem(self.tree)
            item.setSizeHint(0, QSize(0, 28))
            item.setText(0, "Calculating")
            self._resize_tree_to_rows()

        self._preview_generation_id += 1
        generation_id = self._preview_generation_id
        try:
            specification = DatasetSplitSpecification.from_payload(
                self._split_config_payload()
            )
            request = DatasetSplitPreviewRequest(
                request_id=f"split-preview-{id(self):x}-{generation_id}",
                publication_generation=self.publication_generation,
                specification=specification,
            )
        except (TypeError, ValueError) as exc:
            self._set_preview_state(
                generation_id,
                PREVIEW_STATUS_FAILED,
                _public_split_failure(exc, fallback=_PREVIEW_FAILURE_MESSAGE),
            )
            return
        with self._preview_state_lock:
            self._active_preview_request = (generation_id, request.request_id)
            self._cancel_requested_generations.discard(generation_id)
        self._set_preview_state(
            generation_id,
            PREVIEW_STATUS_RUNNING,
        )
        if self.btn_confirm is not None:
            self.btn_confirm.setEnabled(False)
        self.preview_worker = threading.Thread(
            target=self._run_preview_generation,
            args=(generation_id, request),
            name=f"xbrainlab-split-preview-{generation_id}",
        )
        self.preview_worker.start()

    def _run_preview_generation(
        self,
        generation_id: int,
        request: DatasetSplitPreviewRequest,
    ) -> None:
        """Capture completion so the GUI never infers success from thread exit."""
        try:
            publication = self.preview_provider(request)
            publication = self._validated_preview_publication(publication, request)
        except KeyboardInterrupt:
            self._set_preview_state(
                generation_id,
                PREVIEW_STATUS_CANCELLED,
            )
        except Exception as exc:
            if self._cancel_was_requested(generation_id):
                self._set_preview_state(
                    generation_id,
                    PREVIEW_STATUS_CANCELLED,
                )
            else:
                logger.exception("Data-splitting preview generation failed")
                self._set_preview_state(
                    generation_id,
                    PREVIEW_STATUS_FAILED,
                    _public_split_failure(exc, fallback=_PREVIEW_FAILURE_MESSAGE),
                )
        else:
            if self._cancel_was_requested(generation_id):
                self._set_preview_state(
                    generation_id,
                    PREVIEW_STATUS_CANCELLED,
                )
            else:
                self._set_preview_state(
                    generation_id,
                    PREVIEW_STATUS_SUCCEEDED,
                    rows=publication.rows,
                )

    @staticmethod
    def _validated_preview_publication(
        publication: Any,
        request: DatasetSplitPreviewRequest,
    ) -> DatasetSplitPreviewPublication:
        if not isinstance(publication, DatasetSplitPreviewPublication):
            raise TypeError("Dataset split preview returned an invalid publication.")
        if publication.request != request:
            raise ValueError("Dataset split preview returned a mismatched request.")
        return publication

    def _set_preview_state(
        self,
        generation_id: int,
        status: str,
        error: str = "",
        *,
        rows: tuple[DatasetSplitPreviewRow, ...] = (),
    ) -> None:
        """Publish one generation result without letting stale workers overwrite it."""
        with self._preview_state_lock:
            if generation_id != self._preview_generation_id:
                return
            self._preview_status = status
            self._preview_error = error
            self._preview_rows = tuple(rows)
            if status != PREVIEW_STATUS_RUNNING:
                active = self._active_preview_request
                if active is not None and active[0] == generation_id:
                    self._active_preview_request = None
                self._cancel_requested_generations.discard(generation_id)

    def _preview_state(
        self,
    ) -> tuple[str, str, tuple[DatasetSplitPreviewRow, ...]]:
        """Return current status, safe error text, and detached rows."""
        with self._preview_state_lock:
            return self._preview_status, self._preview_error, self._preview_rows

    def _cancel_was_requested(self, generation_id: int) -> bool:
        with self._preview_state_lock:
            return generation_id in self._cancel_requested_generations

    def update_table(self):
        """Render detached preview rows without touching Dataset objects."""
        if not self.tree:
            return

        status, error, rows = self._preview_state()
        if status == PREVIEW_STATUS_FAILED:
            self.tree.clear()
            item = QTreeWidgetItem(self.tree)
            item.setSizeHint(0, QSize(0, 28))
            item.setText(0, "Preview failed")
            if error:
                item.setToolTip(0, error)
            if self.btn_confirm is not None:
                self.btn_confirm.setEnabled(False)
            self._resize_tree_to_rows()
        elif status == PREVIEW_STATUS_CANCELLED:
            self.tree.clear()
            item = QTreeWidgetItem(self.tree)
            item.setSizeHint(0, QSize(0, 28))
            item.setText(0, "Preview cancelled")
            if self.btn_confirm is not None:
                self.btn_confirm.setEnabled(False)
            self._resize_tree_to_rows()
        elif rows:
            item0 = self.tree.topLevelItem(0)
            if (
                self.tree.topLevelItemCount() == 1
                and item0
                and item0.text(0) == "Calculating"
            ):
                self.tree.clear()

            current_count = self.tree.topLevelItemCount()
            if current_count < len(rows):
                for i in range(current_count, len(rows)):
                    row = rows[i]
                    item = QTreeWidgetItem(self.tree)
                    item.setSizeHint(0, QSize(0, 28))
                    visible_info = (
                        row.name,
                        row.train_count,
                        row.validation_count,
                        row.test_count,
                    )
                    for col, val in enumerate(visible_info):
                        item.setText(col, str(val))
            self._clear_tree_current_item()
            self._resize_tree_to_rows()
            if (
                status == PREVIEW_STATUS_SUCCEEDED
                and self.btn_confirm is not None
                and self._preview_pending_close_action is None
            ):
                self.btn_confirm.setEnabled(True)

    def _clear_tree_current_item(self) -> None:
        if self.tree is None:
            return
        self.tree.clearSelection()
        self.tree.setCurrentIndex(QModelIndex())

    def _resize_tree_to_rows(self) -> None:
        if self.tree is None:
            return
        header = self.tree.header()
        header_height = header.sizeHint().height() if header is not None else 28
        row_count = max(1, self.tree.topLevelItemCount())
        max_visible_rows = 8
        visible_rows = min(row_count, max_visible_rows)
        row_height_total = 0
        for row in range(visible_rows):
            row_height = self.tree.sizeHintForRow(row)
            row_height_total += row_height if row_height > 0 else 30
        target_height = max(64, header_height + row_height_total + 8)
        if row_count > max_visible_rows:
            target_height = min(360, target_height)
            self.tree.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded,
            )
        else:
            self.tree.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
            )
        self.tree.setFixedHeight(target_height)
        if self.isVisible():
            self.fit_to_content(minimum_width=920)

    def confirm(self):
        """Accept a successful preview; the command later owns final generation."""
        status, error, rows = self._preview_state()
        if status == PREVIEW_STATUS_RUNNING or (
            self.preview_worker and self.preview_worker.is_alive()
        ):
            self._show_message_box(
                QMessageBox.Icon.Warning,
                "Data splitting",
                "Generating dataset, please wait.",
            )
            return
        if status in {PREVIEW_STATUS_FAILED, PREVIEW_STATUS_CANCELLED}:
            message = error or (
                _PREVIEW_FAILURE_MESSAGE
                if status == PREVIEW_STATUS_FAILED
                else (
                    "The split preview was cancelled. Adjust the split settings "
                    "and try again."
                )
            )
            self._show_message_box(
                QMessageBox.Icon.Critical,
                "Data splitting failed",
                message,
            )
            return

        if status != PREVIEW_STATUS_SUCCEEDED or not rows:
            self._show_message_box(
                QMessageBox.Icon.Critical,
                "Data splitting failed",
                _PREVIEW_FAILURE_MESSAGE,
            )
            return
        self._stop_preview_ui_timers()
        self._clear_preview_close_state()
        super().accept()

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
        self._prepare_preview_shutdown("close")
        if not self._request_preview_worker_stop():
            event.ignore()
            self._schedule_preview_close_retry()
            return
        self._clear_preview_close_state()
        super().closeEvent(event)

    def reject(self) -> None:
        """Apply the same worker-ownership teardown when Escape rejects dialog."""
        self._prepare_preview_shutdown("reject")
        if not self._request_preview_worker_stop():
            self._schedule_preview_close_retry()
            return
        self._clear_preview_close_state()
        super().reject()
        self.hide()

    def schedule_preview(self) -> None:
        """Debounce expensive dataset preview regeneration while editing fields."""
        if self.preview_debounce_timer:
            self.preview_debounce_timer.start(PREVIEW_DEBOUNCE_MS)
        else:
            self.preview()

    def _request_preview_worker_stop(self) -> bool:
        """Interrupt active preview work without blocking the Qt event loop."""
        worker = self.preview_worker
        if worker is None or not worker.is_alive():
            return True
        with self._preview_state_lock:
            active = self._active_preview_request
            if active is not None:
                generation_id, request_id = active
                self._cancel_requested_generations.add(generation_id)
            else:
                request_id = None
        if request_id is not None:
            try:
                self.preview_canceller(request_id)
            except Exception:
                logger.exception("Could not cancel data-splitting preview")
        return False

    def _close_when_preview_worker_stops(self) -> None:
        """Retry dialog close after the Python preview thread releases ownership."""
        if sip.isdeleted(self):
            return
        self._preview_close_retry_pending = False
        worker = self.preview_worker
        if worker is not None and worker.is_alive():
            started_at = self._preview_close_started_at
            if (
                started_at is not None
                and time.monotonic() - started_at >= PREVIEW_WORKER_SHUTDOWN_TIMEOUT_SEC
            ):
                if not self._preview_close_warning_shown:
                    self._preview_close_warning_shown = True
                    QMessageBox.warning(
                        self,
                        "Preview is still stopping",
                        "The data-splitting preview is taking longer than expected "
                        "to stop. This dialog will close automatically when the "
                        "worker releases its data.",
                    )
                self._schedule_preview_close_retry(
                    delay_ms=PREVIEW_WORKER_CLOSE_SLOW_RETRY_MS,
                )
                return
            self._schedule_preview_close_retry()
            return
        action = self._preview_pending_close_action
        self._clear_preview_close_state()
        if action == "reject":
            super().reject()
            self.hide()
            return
        self.close()

    def _schedule_preview_close_retry(
        self,
        *,
        delay_ms: int = PREVIEW_WORKER_CLOSE_RETRY_MS,
    ) -> None:
        """Keep one pending close poll while the preview thread stops."""
        if sip.isdeleted(self) or self._preview_close_retry_pending:
            return
        self._preview_close_retry_pending = True
        QTimer.singleShot(
            delay_ms,
            self._close_when_preview_worker_stops,
        )

    def _prepare_preview_shutdown(self, action: str) -> None:
        """Stop UI polling and remember how deferred teardown should finish."""
        self._stop_preview_ui_timers()
        if self._preview_close_started_at is None:
            self._preview_close_started_at = time.monotonic()
        self._preview_pending_close_action = action
        if self.btn_confirm is not None:
            self.btn_confirm.setEnabled(False)

    def _stop_preview_ui_timers(self) -> None:
        """Stop timers whenever the dialog leaves its active preview state."""
        if self.preview_debounce_timer:
            self.preview_debounce_timer.stop()
        if self.timer:
            self.timer.stop()

    def _clear_preview_close_state(self) -> None:
        """Clear deferred-close bookkeeping after success or a bounded timeout."""
        self._preview_close_retry_pending = False
        self._preview_close_started_at = None
        self._preview_pending_close_action = None
        self._preview_close_warning_shown = False

    def get_result(self):
        """Return the finalized split configuration payload.

        Returns:
            A serializable split configuration accepted by GenerateDatasetCommand,
            or None when no successful detached preview exists.

        """
        status, _error, rows = self._preview_state()
        if status != PREVIEW_STATUS_SUCCEEDED or not rows:
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
