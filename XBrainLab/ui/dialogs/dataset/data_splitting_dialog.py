from enum import Enum

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QPainter
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.dataset import (
    DataSplitter,
    DataSplittingConfig,
    SplitByType,
    TrainingType,
    ValSplitByType,
)
from XBrainLab.ui.core.base_dialog import BaseDialog

from .data_splitting_preview_dialog import (
    DataSplitterHolder,
    DataSplittingPreviewDialog,
)


class DrawColor(Enum):
    TRAIN = QColor("DodgerBlue")
    VAL = QColor("LightBlue")
    TEST = QColor("green")


class DrawRegion:
    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.from_canvas = np.zeros((w, h))
        self.to_canvas = np.zeros((w, h))
        self.from_x = 0
        self.from_y = 0
        self.to_x = 0
        self.to_y = 0

    def reset(self):
        self.from_canvas *= 0
        self.to_canvas *= 0

    def set_from(self, x, y):
        self.reset()
        self.from_x = x
        self.from_y = y

    def set_to_ref(self, x, y, ref):
        self.to_x = x
        self.to_y = y
        self.from_canvas[self.from_x : self.to_x, self.from_y : self.to_y] = (
            ref.from_canvas[self.from_x : self.to_x, self.from_y : self.to_y]
        )
        self.to_canvas[self.from_x : self.to_x, self.from_y : self.to_y] = (
            ref.to_canvas[self.from_x : self.to_x, self.from_y : self.to_y]
        )

    def set_to(self, x, y, from_w, to_w):
        self.to_x = x
        self.to_y = y
        self.from_canvas[self.from_x : self.to_x, self.from_y : self.to_y] = from_w
        self.to_canvas[self.from_x : self.to_x, self.from_y : self.to_y] = to_w

    def change_to(self, x, y):
        self.to_x = x
        self.to_y = y

    def mask(self, rhs):
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
            filter_idx
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
        self.to_canvas[self.from_x : self.to_x, self.from_y : self.to_y] = (
            self.to_canvas[self.from_x : self.to_x, self.from_y : self.to_y]
            - self.from_canvas[self.from_x : self.to_x, self.from_y : self.to_y]
        ) * w + self.from_canvas[self.from_x : self.to_x, self.from_y : self.to_y]

    def decrease_w_head(self, w):
        self.from_canvas[self.from_x : self.to_x, self.from_y : self.to_y] = (
            self.to_canvas[self.from_x : self.to_x, self.from_y : self.to_y]
            - self.from_canvas[self.from_x : self.to_x, self.from_y : self.to_y]
        ) * w + self.from_canvas[self.from_x : self.to_x, self.from_y : self.to_y]

    def copy(self, rhs):
        self.from_x = rhs.from_x
        self.from_y = rhs.from_y
        self.to_x = rhs.to_x
        self.to_y = rhs.to_y
        self.from_canvas = rhs.from_canvas.copy()
        self.to_canvas = rhs.to_canvas.copy()


class PreviewCanvas(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setMinimumSize(400, 200)
        self.regions = []  # List of (DrawRegion, DrawColor)
        self.subject_num = 5
        self.session_num = 5

    def set_regions(self, regions):
        self.regions = regions
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

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

                    painter.drawRect(int(x1), int(y1), int(x2 - x1), int(y2 - y1))

        # Draw box
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(Qt.GlobalColor.white)  # Assuming dark theme
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
        painter.setPen(Qt.GlobalColor.white)

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
    def __init__(self, parent, controller, dataset_generator=None):
        self.controller = controller

        # Get data through controller
        self.epoch_data = self.controller.get_epoch_data() if self.controller else None

        # If dataset_generator is not passed (e.g. from TrainingPanel),
        # try to get it from controller
        if dataset_generator:
            self.dataset_generator = dataset_generator
        elif self.controller:
            self.dataset_generator = self.controller.get_dataset_generator()
        else:
            self.dataset_generator = None

        self.subject_num = 5
        self.session_num = 5
        self.train_region = DrawRegion(self.session_num, self.subject_num)
        self.val_region = DrawRegion(self.session_num, self.subject_num)
        self.test_region = DrawRegion(self.session_num, self.subject_num)

        self.step2_window = None
        self.split_result = None

        # UI Elements
        self.canvas = None
        self.train_type_combo = None
        self.test_combo = None
        self.val_combo = None
        self.cv_check = None
        self.btn_confirm = None

        super().__init__(parent, title="Data Splitting Setting")
        self.resize(800, 600)

        self.update_preview()

    def init_ui(self):
        layout = QHBoxLayout(self)

        # Left: Preview
        left_layout = QVBoxLayout()
        self.canvas = PreviewCanvas(self)
        left_layout.addWidget(self.canvas)

        # Legend
        legend_layout = QHBoxLayout()
        for name, color in [
            ("Training", DrawColor.TRAIN),
            ("Validation", DrawColor.VAL),
            ("Testing", DrawColor.TEST),
        ]:
            lbl_color = QLabel("  ")
            lbl_color.setStyleSheet(f"background-color: {color.value.name()};")
            legend_layout.addWidget(lbl_color)
            legend_layout.addWidget(QLabel(name))
        left_layout.addLayout(legend_layout)
        layout.addLayout(left_layout, stretch=1)

        # Right: Options
        right_layout = QVBoxLayout()

        # Training Type
        right_layout.addWidget(QLabel("Training Type"))
        self.train_type_combo = QComboBox()
        self.train_type_combo.addItems([i.value for i in TrainingType])
        self.train_type_combo.currentTextChanged.connect(self.update_preview)
        right_layout.addWidget(self.train_type_combo)

        # Testing Set
        right_layout.addWidget(QLabel("Testing Set"))
        self.test_combo = QComboBox()
        self.test_combo.addItems([i.value for i in SplitByType])
        self.test_combo.currentTextChanged.connect(self.update_preview)
        right_layout.addWidget(self.test_combo)

        self.cv_check = QCheckBox("Cross Validation")
        right_layout.addWidget(self.cv_check)

        # Validation Set
        right_layout.addWidget(QLabel("Validation Set"))
        self.val_combo = QComboBox()
        self.val_combo.addItems([i.value for i in ValSplitByType])
        self.val_combo.currentTextChanged.connect(self.update_preview)
        right_layout.addWidget(self.val_combo)

        right_layout.addStretch()

        self.btn_confirm = QPushButton("Confirm")
        self.btn_confirm.clicked.connect(self.confirm)
        right_layout.addWidget(self.btn_confirm)

        layout.addLayout(right_layout)

    def update_preview(self, *args):
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
            ]
        )

    def handle_testing(self):
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
        if not self.val_combo:
            return
        val_type = self.val_combo.currentText()
        if val_type == ValSplitByType.SESSION.value:
            self.val_region.copy(self.train_region)
            self.val_region.set_from(
                self.train_region.to_x - 1, self.train_region.from_y
            )
            self.val_region.set_to_ref(
                self.train_region.to_x, self.train_region.to_y, self.train_region
            )
        elif val_type == ValSplitByType.TRIAL.value:
            self.val_region.copy(self.train_region)
            self.val_region.decrease_w_head(0.8)
        elif val_type == ValSplitByType.SUBJECT.value:
            self.val_region.copy(self.train_region)
            self.val_region.set_from(
                self.train_region.from_x, self.train_region.to_y - 1
            )
            self.val_region.set_to_ref(
                self.train_region.to_x, self.train_region.to_y, self.train_region
            )

    def confirm(self):
        if (
            not self.train_type_combo
            or not self.val_combo
            or not self.test_combo
            or not self.cv_check
        ):
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
            self.parent(), "Data Splitting Step 2", self.epoch_data, config
        )
        if self.step2_window.exec():
            self.split_result = self.step2_window.get_result()
            self.split_result = self.step2_window.get_result()
            super().accept()  # Call BaseDialog.accept equivalent? No, mimic Original

        else:
            self.reject()

    def get_result(self):
        return self.split_result
