"""Data splitting configuration dialog for train/validation/test partitioning.

Provides a visual preview canvas and configuration controls for splitting
EEG datasets into training, validation, and testing sets using various
strategies such as subject-wise, session-wise, or trial-wise splits.
"""

from collections.abc import Callable
from enum import Enum
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter
from PyQt6.QtWidgets import (
    QWIDGETSIZE_MAX,
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application.dataset_split_preview import (
    DatasetSplitContext,
    DatasetSplitPreviewPublication,
    DatasetSplitPreviewReceipt,
    DatasetSplitPreviewRequest,
)
from XBrainLab.backend.dataset import (
    DataSplitter,
    DataSplittingConfig,
    SplitByType,
    TrainingType,
    ValSplitByType,
)
from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.dialogs.common import checkbox_stylesheet
from XBrainLab.ui.styles.theme import Theme

from .data_splitting_preview_dialog import (
    DataSplitterHolder,
    DataSplittingPreviewDialog,
)

_NARROW_FLOW_BREAKPOINT = 800
_CHEVRON_DOWN_ICON = (
    Path(__file__).resolve().parents[3] / "resources" / "icons" / "chevron-down.svg"
).as_posix()


class DrawColor(Enum):
    """Color definitions for data split preview regions.

    Attributes:
        TRAIN: Color used for training data regions.
        VAL: Color used for validation data regions.
        TEST: Color used for testing data regions.

    """

    TRAIN = QColor("#1f83d0")
    VAL = QColor("#7bb7c9")
    TEST = QColor("#2f9f64")


class DrawRegion:
    """Helper class for managing 2D drawing regions in the split preview.

    Handles coordinate mapping and canvas operations for rendering
    training, validation, and test split regions.

    Attributes:
        w: Width of the canvas grid.
        h: Height of the canvas grid.
        from_canvas: Numpy array tracking region start boundaries.
        to_canvas: Numpy array tracking region end boundaries.
        from_x: Starting X coordinate of the active region.
        from_y: Starting Y coordinate of the active region.
        to_x: Ending X coordinate of the active region.
        to_y: Ending Y coordinate of the active region.

    """

    def __init__(self, w: int, h: int):
        self.w = w
        self.h = h
        self.from_canvas = np.zeros((w, h))
        self.to_canvas = np.zeros((w, h))
        self.from_x = 0
        self.from_y = 0
        self.to_x = 0
        self.to_y = 0

    def reset(self) -> None:
        """Reset the canvas and coordinates."""
        self.from_canvas *= 0
        self.to_canvas *= 0

    def set_from(self, x, y):
        """Set the starting coordinates for the active region.

        Args:
            x: Starting X coordinate.
            y: Starting Y coordinate.

        """
        self.reset()
        self.from_x = x
        self.from_y = y

    def set_to_ref(self, x, y, ref):
        """Set ending coordinates using values from a reference region.

        Args:
            x: Ending X coordinate.
            y: Ending Y coordinate.
            ref: Reference DrawRegion to copy canvas values from.

        """
        self.to_x = x
        self.to_y = y
        self.from_canvas[self.from_x : self.to_x, self.from_y : self.to_y] = (
            ref.from_canvas[self.from_x : self.to_x, self.from_y : self.to_y]
        )
        self.to_canvas[self.from_x : self.to_x, self.from_y : self.to_y] = (
            ref.to_canvas[self.from_x : self.to_x, self.from_y : self.to_y]
        )

    def set_to(self, x, y, from_w, to_w):
        """Set ending coordinates and fill the canvas with given values.

        Args:
            x: Ending X coordinate.
            y: Ending Y coordinate.
            from_w: Value to fill in from_canvas.
            to_w: Value to fill in to_canvas.

        """
        self.to_x = x
        self.to_y = y
        self.from_canvas[self.from_x : self.to_x, self.from_y : self.to_y] = from_w
        self.to_canvas[self.from_x : self.to_x, self.from_y : self.to_y] = to_w

    def change_to(self, x, y):
        """Update only the ending coordinates without modifying canvas data.

        Args:
            x: New ending X coordinate.
            y: New ending Y coordinate.

        """
        self.to_x = x
        self.to_y = y

    def mask(self, rhs):
        """Apply a mask from another region, adjusting canvas boundaries.

        Args:
            rhs: DrawRegion whose boundaries define the mask.

        """
        idx = (
            rhs.from_canvas[rhs.from_x : rhs.to_x, rhs.from_y : rhs.to_y]
            != rhs.to_canvas[rhs.from_x : rhs.to_x, rhs.from_y : rhs.to_y]
        )
        filter_idx = (
            idx
            & (
                self.from_canvas[rhs.from_x : rhs.to_x, rhs.from_y : rhs.to_y]
                <= rhs.from_canvas[rhs.from_x : rhs.to_x, rhs.from_y : rhs.to_y]
            )
            & (
                rhs.from_canvas[rhs.from_x : rhs.to_x, rhs.from_y : rhs.to_y]
                <= self.to_canvas[rhs.from_x : rhs.to_x, rhs.from_y : rhs.to_y]
            )
        )

        self.to_canvas[rhs.from_x : rhs.to_x, rhs.from_y : rhs.to_y] *= np.logical_not(
            filter_idx,
        )
        self.to_canvas[rhs.from_x : rhs.to_x, rhs.from_y : rhs.to_y] += (
            filter_idx * rhs.from_canvas[rhs.from_x : rhs.to_x, rhs.from_y : rhs.to_y]
        )

        # Simplified boundary checks (might need full logic from original if buggy)
        if (
            self.to_x > 0
            and (
                self.to_canvas[self.to_x - 1, self.from_y : self.to_y]
                == self.from_canvas[self.to_x - 1, self.from_y : self.to_y]
            ).all()
        ):
            self.to_x -= 1
        if (
            self.to_y > 0
            and (
                self.to_canvas[self.from_x : self.to_x, self.to_y - 1]
                == self.from_canvas[self.from_x : self.to_x, self.to_y - 1]
            ).all()
        ):
            self.to_y -= 1

    def decrease_w_tail(self, w):
        """Shrink the region from the tail end by a proportional factor.

        Args:
            w: Proportion (0.0 to 1.0) to retain from the tail.

        """
        self.to_canvas[self.from_x : self.to_x, self.from_y : self.to_y] = (
            self.to_canvas[self.from_x : self.to_x, self.from_y : self.to_y]
            - self.from_canvas[self.from_x : self.to_x, self.from_y : self.to_y]
        ) * w + self.from_canvas[self.from_x : self.to_x, self.from_y : self.to_y]

    def decrease_w_head(self, w):
        """Shrink the region from the head end by a proportional factor.

        Args:
            w: Proportion (0.0 to 1.0) to retain from the head.

        """
        self.from_canvas[self.from_x : self.to_x, self.from_y : self.to_y] = (
            self.to_canvas[self.from_x : self.to_x, self.from_y : self.to_y]
            - self.from_canvas[self.from_x : self.to_x, self.from_y : self.to_y]
        ) * w + self.from_canvas[self.from_x : self.to_x, self.from_y : self.to_y]

    def copy(self, rhs):
        """Deep copy all attributes from another DrawRegion.

        Args:
            rhs: Source DrawRegion to copy from.

        """
        self.from_x = rhs.from_x
        self.from_y = rhs.from_y
        self.to_x = rhs.to_x
        self.to_y = rhs.to_y
        self.from_canvas = rhs.from_canvas.copy()
        self.to_canvas = rhs.to_canvas.copy()


class PreviewCanvas(QWidget):
    """Custom widget for rendering a visual preview of data split regions.

    Draws a grid representing subjects (rows) and sessions (columns),
    with colored regions indicating training, validation, and test splits.

    Attributes:
        regions: List of (DrawRegion, DrawColor) tuples to render.
        subject_num: Number of subjects (rows) in the grid.
        session_num: Number of sessions (columns) in the grid.

    """

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("DataSplitPreviewCanvas")
        self.setMinimumSize(460, 280)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.regions = []  # List of (DrawRegion, DrawColor)
        self.subject_num = 5
        self.session_num = 5

    def set_regions(self, regions):
        """Set the regions to draw and trigger a repaint.

        Args:
            regions: List of (DrawRegion, DrawColor) tuples.

        """
        self.regions = regions
        self.update()

    def paintEvent(self, event):  # noqa: N802
        """Render the split preview with colored regions and grid lines.

        Args:
            event: The paint event.

        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#181a1d"))

        w = self.width() - 100
        h = self.height() - 50
        left = 50
        top = 20

        delta_x = w / self.session_num
        delta_y = h / self.subject_num

        # Draw regions
        for region, color in self.regions:
            painter.setBrush(QBrush(color.value))
            painter.setPen(Qt.PenStyle.NoPen)

            for i in range(region.from_x, region.to_x):
                for j in range(region.from_y, region.to_y):
                    if region.from_canvas[i, j] == region.to_canvas[i, j]:
                        continue

                    x1 = left + delta_x * (i + region.from_canvas[i, j])
                    y1 = top + delta_y * j
                    x2 = left + delta_x * (i + region.to_canvas[i, j])
                    y2 = top + delta_y * (j + 1)

                    left_px = round(x1)
                    top_px = round(y1)
                    right_px = round(x2)
                    bottom_px = round(y2)
                    painter.drawRect(
                        QRect(
                            left_px,
                            top_px,
                            max(1, right_px - left_px),
                            max(1, bottom_px - top_px),
                        )
                    )

        # Draw box
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QColor("#d9e1ea"))
        painter.drawRect(left, top, int(w), int(h))

        # Grid lines
        painter.setPen(Qt.PenStyle.DashLine)
        for i in range(1, self.subject_num):
            d = top + h / self.subject_num * i
            painter.drawLine(left, int(d), int(left + w), int(d))

        for i in range(1, self.session_num):
            d = left + w / self.session_num * i
            painter.drawLine(int(d), top, int(d), int(top + h))

        # Labels
        painter.setPen(QColor("#edf2f7"))

        # X-axis Label
        painter.drawText(int(left + w / 2 - 20), int(top + h + 20), "Session")

        # Y-axis Label (Rotated)
        painter.save()
        # Translate to the position where we want the center of the text
        painter.translate(15, top + h / 2)
        painter.rotate(-90)
        # Draw text. Since we translated and rotated, (0,0) is the pivot.
        # We center the text horizontally (which is vertical on screen)
        # Assuming text width is approx 40-50px
        painter.drawText(-25, 0, "Subject")
        painter.restore()


class DataSplittingDialog(BaseDialog):
    """Dialog for configuring train/validation/test data splitting.

    Provides a visual preview of how data will be partitioned along with
    controls for selecting training type, testing strategy, validation
    strategy, and cross-validation options.

    Attributes:
        split_context: Detached counts and choices published by ApplicationService.
        subject_num: Number of subjects for preview grid.
        session_num: Number of sessions for preview grid.
        train_region: DrawRegion for training data visualization.
        val_region: DrawRegion for validation data visualization.
        test_region: DrawRegion for testing data visualization.
        step2_window: Reference to the preview dialog (step 2).
        split_result: The finalized split result after confirmation.

    """

    def __init__(
        self,
        parent,
        *,
        split_context: DatasetSplitContext | None = None,
        publication_generation: int | None = None,
        preview_provider: (
            Callable[[DatasetSplitPreviewRequest], DatasetSplitPreviewPublication]
            | None
        ) = None,
        preview_canceller: Callable[[str], bool] | None = None,
        initial_values: dict[str, str] | None = None,
    ):
        self.initial_values = {
            str(key): str(value)
            for key, value in (initial_values or {}).items()
            if str(key).strip() and str(value).strip()
        }
        if split_context is not None and not isinstance(
            split_context,
            DatasetSplitContext,
        ):
            raise TypeError("split_context must be a DatasetSplitContext")
        if publication_generation is not None and (
            isinstance(publication_generation, bool)
            or not isinstance(publication_generation, int)
            or publication_generation < 1
        ):
            raise ValueError("publication_generation must be a positive integer")
        self.split_context = split_context
        self.publication_generation = publication_generation
        self.preview_provider = preview_provider
        self.preview_canceller = preview_canceller

        self.subject_num = 5
        self.session_num = 5
        self.train_region = DrawRegion(self.session_num, self.subject_num)
        self.val_region = DrawRegion(self.session_num, self.subject_num)
        self.test_region = DrawRegion(self.session_num, self.subject_num)

        self.step2_window: DataSplittingPreviewDialog | None = None
        self.split_result: dict[str, object] | None = None
        self.split_preview_receipt: DatasetSplitPreviewReceipt | None = None

        # UI Elements
        self.canvas: PreviewCanvas | None = None
        self.train_type_combo: QComboBox | None = None
        self.test_combo: QComboBox | None = None
        self.val_combo: QComboBox | None = None
        self.cv_check: QCheckBox | None = None
        self.btn_confirm: QPushButton | None = None
        self.blocked_label: QLabel | None = None
        self.content_layout: QBoxLayout | None = None
        self.content_scroll: QScrollArea | None = None
        self.preview_group: QFrame | None = None
        self.options_group: QFrame | None = None

        super().__init__(parent, title="Data Splitting Setting")
        self.setObjectName("DataSplittingDialog")
        self.resize(820, 470)
        self.setStyleSheet(self._dialog_style())

        self._sync_availability()
        self.update_preview()

    def init_ui(self):
        """Initialize the dialog UI with preview canvas and split controls."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        content_scroll = QScrollArea()
        self.content_scroll = content_scroll
        content_scroll.setObjectName("DataSplitContentScroll")
        content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        content_scroll.setMinimumSize(500, 260)
        content_scroll.setWidgetResizable(True)
        content_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        content_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        content_widget = QWidget()
        content_widget.setObjectName("DataSplitContentWidget")
        content_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.content_layout = content_layout
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)
        content_widget.setLayout(content_layout)
        content_scroll.setWidget(content_widget)

        # Left: Preview
        preview_group = QFrame()
        self.preview_group = preview_group
        preview_group.setObjectName("DataSplitPreviewGroup")
        preview_group.setFrameShape(QFrame.Shape.NoFrame)
        left_layout = QVBoxLayout(preview_group)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(12)
        preview_title = QLabel("Data splitting preview")
        preview_title.setObjectName("DataSplitSectionTitle")
        left_layout.addWidget(preview_title)
        canvas = PreviewCanvas(self)
        self.canvas = canvas
        left_layout.addWidget(canvas)

        # Legend
        legend_layout = QHBoxLayout()
        legend_layout.setSpacing(8)
        for name, color in [
            ("Training", DrawColor.TRAIN),
            ("Validation", DrawColor.VAL),
            ("Testing", DrawColor.TEST),
        ]:
            lbl_color = QLabel("  ")
            lbl_color.setObjectName("DataSplitLegendSwatch")
            lbl_color.setStyleSheet(f"background-color: {color.value.name()};")
            legend_layout.addWidget(lbl_color)
            legend_layout.addWidget(QLabel(name))
        legend_layout.addStretch(1)
        left_layout.addLayout(legend_layout)
        content_layout.addWidget(preview_group, stretch=1)

        # Right: Options
        options_group = QFrame()
        self.options_group = options_group
        options_group.setObjectName("DataSplitOptionsGroup")
        options_group.setFrameShape(QFrame.Shape.NoFrame)
        options_group.setMinimumWidth(260)
        options_group.setMaximumWidth(300)
        options_group.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Maximum,
        )
        right_layout = QVBoxLayout(options_group)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(12)
        right_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        settings_title = QLabel("Split settings")
        settings_title.setObjectName("DataSplitSectionTitle")
        right_layout.addWidget(settings_title)

        form_layout = QGridLayout()
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(10)
        form_layout.setColumnStretch(1, 0)

        # Training Type
        train_type_combo = QComboBox()
        self.train_type_combo = train_type_combo
        train_type_combo.addItems([i.value for i in TrainingType])
        self._configure_split_combo(train_type_combo)
        train_type_combo.currentTextChanged.connect(self.update_preview)
        form_layout.addWidget(QLabel("Training"), 0, 0)
        form_layout.addWidget(train_type_combo, 0, 1)

        # Testing Set
        test_combo = QComboBox()
        self.test_combo = test_combo
        test_combo.addItems([i.value for i in SplitByType])
        self._configure_split_combo(test_combo)
        test_combo.setCurrentText(SplitByType.TRIAL.value)
        test_combo.currentTextChanged.connect(self.update_preview)
        form_layout.addWidget(QLabel("Testing"), 1, 0)
        form_layout.addWidget(test_combo, 1, 1)

        # Validation Set
        val_combo = QComboBox()
        self.val_combo = val_combo
        val_combo.addItems([i.value for i in ValSplitByType])
        self._configure_split_combo(val_combo)
        val_combo.setCurrentText(ValSplitByType.TRIAL.value)
        val_combo.currentTextChanged.connect(self.update_preview)
        form_layout.addWidget(QLabel("Validation"), 2, 0)
        form_layout.addWidget(val_combo, 2, 1)
        self._apply_initial_values()
        right_layout.addLayout(form_layout)

        cv_check = QCheckBox("Cross validation")
        self.cv_check = cv_check
        cv_check.setObjectName("DataSplitCrossValidationCheck")
        cv_check.stateChanged.connect(self.update_preview)
        right_layout.addWidget(cv_check)

        blocked_label = QLabel("")
        self.blocked_label = blocked_label
        blocked_label.setWordWrap(True)
        blocked_label.setStyleSheet("color: #f59e0b;")
        right_layout.addWidget(blocked_label)
        content_layout.addWidget(options_group, stretch=0)
        content_layout.setAlignment(
            options_group,
            Qt.AlignmentFlag.AlignTop,
        )
        layout.addWidget(content_scroll, stretch=1)

        action_layout = QHBoxLayout()
        action_layout.addStretch(1)
        btn_confirm = QPushButton("Confirm")
        self.btn_confirm = btn_confirm
        btn_confirm.setObjectName("PrimaryConfirmButton")
        btn_confirm.setAutoDefault(False)
        btn_confirm.setDefault(False)
        btn_confirm.clicked.connect(self.confirm)
        action_layout.addWidget(btn_confirm)
        layout.addLayout(action_layout)
        self._update_content_flow(self.width(), self.height())

    def resizeEvent(self, event):  # noqa: N802
        """Reflow preview and settings before narrow layouts can clip them."""
        self._update_content_flow(event.size().width(), event.size().height())
        super().resizeEvent(event)

    def _update_content_flow(self, width: int, height: int) -> None:
        if (
            self.content_layout is None
            or self.preview_group is None
            or self.options_group is None
        ):
            return
        is_short = height < 600
        is_narrow = width < _NARROW_FLOW_BREAKPOINT and not is_short
        direction = (
            QBoxLayout.Direction.TopToBottom
            if is_narrow
            else QBoxLayout.Direction.LeftToRight
        )
        if self.content_layout.direction() != direction:
            self.content_layout.setDirection(direction)

        if is_narrow:
            self.options_group.setMaximumWidth(QWIDGETSIZE_MAX)
            self.options_group.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Maximum,
            )
        else:
            self.options_group.setMaximumWidth(300)
            self.options_group.setSizePolicy(
                QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.Maximum,
            )
        self.content_layout.setAlignment(
            self.options_group,
            Qt.AlignmentFlag.AlignTop,
        )
        self.content_layout.invalidate()

    @staticmethod
    def _configure_split_combo(combo: QComboBox) -> None:
        combo.setMinimumWidth(148)
        combo.setMaximumWidth(178)
        combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def _apply_initial_values(self) -> None:
        """Prefill only choices explicitly supplied by an assistant handoff."""
        train_type_combo = self.train_type_combo
        test_combo = self.test_combo
        val_combo = self.val_combo
        if train_type_combo is None or test_combo is None or val_combo is None:
            return

        training_mode = self.initial_values.get("training_mode", "").casefold()
        if training_mode == "individual":
            train_type_combo.setCurrentText(TrainingType.IND.value)
        elif training_mode == "full":
            train_type_combo.setCurrentText(TrainingType.FULL.value)

        strategy = self.initial_values.get("split_strategy", "").casefold()
        strategy_text = {
            "trial": (SplitByType.TRIAL.value, ValSplitByType.TRIAL.value),
            "session": (SplitByType.SESSION.value, ValSplitByType.SESSION.value),
            "subject": (SplitByType.SUBJECT.value, ValSplitByType.SUBJECT.value),
        }.get(strategy)
        if strategy_text is not None:
            test_combo.setCurrentText(strategy_text[0])
            val_combo.setCurrentText(strategy_text[1])

    def update_preview(self, *args):
        """Recalculate and redraw the split preview based on current settings."""
        if not self.canvas or not self.train_type_combo:
            return

        # Reset regions
        self.train_region = DrawRegion(self.session_num, self.subject_num)
        self.val_region = DrawRegion(self.session_num, self.subject_num)
        self.test_region = DrawRegion(self.session_num, self.subject_num)

        # Handle Data
        train_type = self.train_type_combo.currentText()
        if train_type == TrainingType.FULL.value:
            self.train_region.set_to(self.session_num, self.subject_num, 0, 1)
        elif train_type == TrainingType.IND.value:
            self.train_region.set_to(self.session_num, 1, 0, 1)

        self.handle_testing()
        self.train_region.mask(self.test_region)

        self.handle_validation()
        self.train_region.mask(self.val_region)

        self.canvas.set_regions(
            [
                (self.train_region, DrawColor.TRAIN),
                (self.val_region, DrawColor.VAL),
                (self.test_region, DrawColor.TEST),
            ],
        )

    def handle_testing(self):
        """Calculate the testing region based on the selected split type."""
        if not self.test_combo:
            return
        test_type = self.test_combo.currentText()
        ref = DrawRegion(self.train_region.w, self.train_region.h)
        ref.copy(self.train_region)

        if test_type in [SplitByType.SESSION.value, SplitByType.SESSION_IND.value]:
            is_ind = test_type == SplitByType.SESSION_IND.value
            if is_ind:
                tmp = DrawRegion(self.train_region.w, self.train_region.h)
                tmp.copy(ref)
                tmp.change_to(ref.to_x - 1, ref.to_y)
            self.test_region.set_from(ref.to_x - 1, ref.from_y)
            self.test_region.set_to_ref(ref.to_x, ref.to_y, ref)
            if is_ind:
                self.train_region.mask(tmp)

        elif test_type in [SplitByType.TRIAL.value, SplitByType.TRIAL_IND.value]:
            is_ind = test_type == SplitByType.TRIAL_IND.value
            if is_ind:
                tmp = DrawRegion(ref.w, ref.h)
                tmp.copy(ref)
                tmp.decrease_w_tail(0.8)
            self.test_region.copy(ref)
            self.test_region.decrease_w_head(0.8)
            if is_ind:
                self.train_region.mask(tmp)

        elif test_type in [SplitByType.SUBJECT.value, SplitByType.SUBJECT_IND.value]:
            is_ind = test_type == SplitByType.SUBJECT_IND.value
            if is_ind:
                tmp = DrawRegion(self.train_region.w, self.train_region.h)
                tmp.copy(ref)
                tmp.change_to(ref.to_x, ref.to_y - 1)
            self.test_region.set_from(ref.from_x, ref.to_y - 1)
            self.test_region.set_to_ref(ref.to_x, ref.to_y, ref)
            if is_ind:
                self.train_region.mask(tmp)

    def handle_validation(self):
        """Calculate the validation region based on the selected split type."""
        if not self.val_combo:
            return
        val_type = self.val_combo.currentText()
        if val_type == ValSplitByType.SESSION.value:
            self.val_region.copy(self.train_region)
            self.val_region.set_from(
                self.train_region.to_x - 1,
                self.train_region.from_y,
            )
            self.val_region.set_to_ref(
                self.train_region.to_x,
                self.train_region.to_y,
                self.train_region,
            )
        elif val_type == ValSplitByType.TRIAL.value:
            self.val_region.copy(self.train_region)
            self.val_region.decrease_w_head(0.8)
        elif val_type == ValSplitByType.SUBJECT.value:
            self.val_region.copy(self.train_region)
            self.val_region.set_from(
                self.train_region.from_x,
                self.train_region.to_y - 1,
            )
            self.val_region.set_to_ref(
                self.train_region.to_x,
                self.train_region.to_y,
                self.train_region,
            )

    def confirm(self):
        """Build the splitting config and open the preview dialog (step 2)."""
        if (
            not self.train_type_combo
            or not self.val_combo
            or not self.test_combo
            or not self.cv_check
        ):
            return
        if not self._preview_available():
            self._sync_availability()
            return

        # Get Training Type
        train_type = TrainingType.FULL  # Default
        for t_type in TrainingType:
            if t_type.value == self.train_type_combo.currentText():
                train_type = t_type
                break

        if train_type is None:
            train_type = TrainingType.FULL

        # Get Val Types
        val_type_list = []
        for v_type in ValSplitByType:
            if v_type.value == self.val_combo.currentText():
                val_type_list.append(v_type)
                break

        # Get Test Types
        test_type_list = []
        for s_type in SplitByType:
            if s_type.value == self.test_combo.currentText():
                test_type_list.append(s_type)
                break

        # Create DataSplitter instances for val and test
        val_splitters: list[DataSplitter] = [
            DataSplitterHolder(True, t) for t in val_type_list
        ]
        test_splitters: list[DataSplitter] = [
            DataSplitterHolder(True, t) for t in test_type_list
        ]

        # Create DataSplittingConfig directly with backend class
        config = DataSplittingConfig(
            train_type=train_type,
            is_cross_validation=self.cv_check.isChecked(),
            val_splitter_list=val_splitters,
            test_splitter_list=test_splitters,
        )

        self.step2_window = DataSplittingPreviewDialog(
            self.parent(),
            "Data Splitting Step 2",
            split_context=self.split_context,
            publication_generation=self.publication_generation,
            config=config,
            preview_provider=self.preview_provider,
            preview_canceller=self.preview_canceller,
            initial_values=self.initial_values,
        )
        if self.step2_window.exec():
            split_result = self.step2_window.get_result()
            preview_receipt = self.step2_window.get_preview_receipt()
            if split_result is None or preview_receipt is None:
                return
            self.split_result = split_result
            self.split_preview_receipt = preview_receipt
            super().accept()
        else:
            return  # Allow user to retry instead of rejecting

    def get_result(self):
        """Return the split configuration payload from the preview dialog.

        Returns:
            A serializable split configuration or None if not confirmed.

        """
        return self.split_result

    def get_preview_receipt(self) -> DatasetSplitPreviewReceipt | None:
        """Return detached evidence for the exact accepted split preview."""
        return self.split_preview_receipt

    def _sync_availability(self) -> None:
        """Reflect whether detached context and preview service are available."""
        blocked = not self._preview_available()
        if self.split_context is None:
            message = "Dataset splitting context is unavailable."
        elif not self.split_context.epoch_available:
            message = "Create EEG epochs before splitting data."
        elif self.publication_generation is None:
            message = "Refresh the workflow before splitting data."
        elif self.preview_provider is None or self.preview_canceller is None:
            message = "Dataset split preview is unavailable."
        else:
            message = ""
        if self.btn_confirm is not None:
            self.btn_confirm.setEnabled(not blocked)
            self.btn_confirm.setToolTip(message)
        if self.blocked_label is not None:
            self.blocked_label.setText(message)
            self.blocked_label.setVisible(blocked)

    def _preview_available(self) -> bool:
        context = self.split_context
        return bool(
            context is not None
            and context.epoch_available
            and self.publication_generation is not None
            and self.preview_provider is not None
            and self.preview_canceller is not None
        )

    @staticmethod
    def _dialog_style() -> str:
        style = (
            """
        QDialog#DataSplittingDialog {
            background: #1b1b1d;
            color: #f2f5f8;
        }
        QScrollArea#DataSplitContentScroll,
        QScrollArea#DataSplitContentScroll > QWidget > QWidget,
        QWidget#DataSplitContentWidget {
            border: none;
            background: transparent;
        }
        QLabel {
            background: transparent;
            color: #f2f5f8;
        }
        QLabel#DataSplitTitle {
            font-size: 16px;
            font-weight: 700;
        }
        QFrame#DataSplitPreviewGroup,
        QFrame#DataSplitOptionsGroup {
            border: none;
            border-radius: 6px;
            background: #202225;
        }
        QLabel#DataSplitSectionTitle {
            color: #f2f5f8;
            font-weight: 700;
            font-size: 13px;
        }
        QLabel#DataSplitLegendSwatch {
            border-radius: 2px;
            min-width: 18px;
            max-width: 18px;
            min-height: 12px;
            max-height: 12px;
        }
        QWidget#DataSplitPreviewCanvas {
            background: #181a1d;
            border: 1px solid #3d454d;
            border-radius: 6px;
        }
        QComboBox {
            background: #25272a;
            color: #f2f5f8;
            border: 1px solid #3d454d;
            border-radius: 4px;
            padding: 5px 28px 5px 8px;
        }
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            border: none;
            background: transparent;
            width: 24px;
        }
        QComboBox::down-arrow {
            image: url("__CHEVRON_DOWN_ICON__");
            width: 10px;
            height: 10px;
        }
        QComboBox QAbstractItemView {
            background: #25272a;
            color: #f2f5f8;
            selection-background-color: __TABLE_SELECTION__;
            selection-color: #ffffff;
        }
        QCheckBox#DataSplitCrossValidationCheck {
            background: transparent;
            border: none;
        }
        """
            + checkbox_stylesheet()
            + """
        QPushButton#PrimaryConfirmButton {
            min-width: 128px;
            padding: 7px 12px;
            border-radius: 4px;
            border: 1px solid #0a7fc7;
            background: #0069a8;
            color: #f2f5f8;
            font-weight: 700;
        }
        QPushButton#PrimaryConfirmButton:hover {
            background: #0a7fc7;
        }
        QPushButton#PrimaryConfirmButton:disabled {
            border-color: #3d454d;
            background: #2a2c30;
            color: #87909b;
        }
        """
        )
        return style.replace("__CHEVRON_DOWN_ICON__", _CHEVRON_DOWN_ICON).replace(
            "__TABLE_SELECTION__",
            Theme.TABLE_SELECTION,
        )
