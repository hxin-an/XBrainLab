"""Saliency map export dialog for saving computed saliency data to pickle files.

Provides cascading selectors for plan, repeat, and saliency method,
followed by a file location picker for the output.
"""

import os
import pickle

from PyQt6.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QLabel,
    QMessageBox,
)

from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.visualization import supported_saliency_methods
from XBrainLab.ui.core.base_dialog import BaseDialog


class ExportSaliencyDialog(BaseDialog):
    """Dialog for exporting saliency maps to pickle files.

    Allows cascading selection of training plan, repeat, and saliency
    method before choosing an export directory.

    Attributes:
        trainers: List of available trainer instances.
        trainer_map: Dictionary mapping trainer names to trainer objects.
        real_plan_opt: Dictionary mapping plan names to plan objects.
        plan_combo: QComboBox for selecting a training plan.
        repeat_combo: QComboBox for selecting a repeat.
        method_combo: QComboBox for selecting the saliency method.

    """

    def __init__(self, parent, trainers):
        self.trainers = trainers
        self.trainer_map = {trainer.get_name(): trainer for trainer in trainers}
        self.real_plan_opt = {}

        # UI Elements
        self.plan_combo = None
        self.repeat_combo = None
        self.method_combo = None

        super().__init__(parent, title="Export saliency (pickle)")
        self.resize(400, 200)

    def init_ui(self):
        """Initialize the dialog UI with cascading selectors and export button."""
        layout = QGridLayout(self)

        # Plan Selection
        layout.addWidget(QLabel("Select a plan: "), 0, 0)
        self.plan_combo = QComboBox()
        self.plan_combo.addItem("---")
        self.plan_combo.addItems(list(self.trainer_map.keys()))
        self.plan_combo.currentTextChanged.connect(self.on_plan_change)
        layout.addWidget(self.plan_combo, 0, 1)

        # Repeat Selection
        layout.addWidget(QLabel("Select a repeat: "), 1, 0)
        self.repeat_combo = QComboBox()
        self.repeat_combo.addItem("---")
        self.repeat_combo.currentTextChanged.connect(self.on_repeat_change)
        layout.addWidget(self.repeat_combo, 1, 1)

        # Method Selection
        layout.addWidget(QLabel("Select a method: "), 2, 0)
        self.method_combo = QComboBox()
        self.method_combo.addItem("---")
        layout.addWidget(self.method_combo, 2, 1)

        # Standard Buttons
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn:
            ok_btn.setText("Export")
        self.button_box.accepted.connect(self.on_export_clicked)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box, 3, 0, 1, 2)

    def on_plan_change(self, plan_name):
        """Update repeat options when the selected plan changes.

        Args:
            plan_name: Name of the selected training plan.

        """
        if not self.repeat_combo:
            return
        self.repeat_combo.clear()
        self.repeat_combo.addItem("---")

        if plan_name != "---":
            trainer = self.trainer_map[plan_name]
            self.real_plan_opt = {plan.get_name(): plan for plan in trainer.get_plans()}
            self.repeat_combo.addItems(list(self.real_plan_opt.keys()))
        else:
            self.real_plan_opt = {}

    def on_repeat_change(self, repeat_name):
        """Update method options when the selected repeat changes.

        Args:
            repeat_name: Name of the selected repeat.

        """
        if not self.method_combo:
            return
        self.method_combo.clear()
        self.method_combo.addItem("---")

        if repeat_name != "---":
            self.method_combo.addItems(
                ["Gradient", "Gradient * Input", *supported_saliency_methods],
            )

    def on_export_clicked(self):
        """Validate selections, compute saliency, and export to pickle file."""
        if not self.plan_combo or not self.repeat_combo or not self.method_combo:
            return
        plan_name = self.plan_combo.currentText()
        repeat_name = self.repeat_combo.currentText()
        method_name = self.method_combo.currentText()

        if plan_name == "---" or repeat_name == "---" or method_name == "---":
            QMessageBox.warning(self, "Warning", "Please select all options.")
            return

        real_plan = self.real_plan_opt[repeat_name]
        try:
            eval_record = real_plan.get_eval_record()
        except Exception:
            logger.exception("Failed to get eval record")
            eval_record = None

        if not eval_record:
            QMessageBox.warning(
                self,
                "Warning",
                "No evaluation record found for selected plan.",
            )
            return

        file_location = QFileDialog.getExistingDirectory(self, "Export Saliency")
        if not file_location:
            return

        try:
            saliency = eval_record.export_saliency(method_name)

            file_name = [plan_name, repeat_name, method_name]
            output_path = os.path.join(file_location, "_".join(file_name) + ".pickle")

            with open(output_path, "wb") as fp:
                pickle.dump(saliency, fp, protocol=pickle.HIGHEST_PROTOCOL)

            QMessageBox.information(self, "Success", f"Exported to {output_path}")
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export: {e}")
