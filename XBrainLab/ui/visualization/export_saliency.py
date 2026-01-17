import os
import pickle

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QLabel,
    QMessageBox,
    QPushButton,
)

from XBrainLab.backend.visualization import supported_saliency_methods


class ExportSaliencyWindow(QDialog):
    def __init__(self, parent, trainers):
        super().__init__(parent)
        self.setWindowTitle("Export saliency (pickle)")
        self.resize(400, 200)

        self.trainers = trainers
        self.trainer_map = {trainer.get_name(): trainer for trainer in trainers}
        self.real_plan_opt = {}

        self.init_ui()

    def init_ui(self):
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

        # Export Button
        self.export_btn = QPushButton("Export location")
        self.export_btn.clicked.connect(self.select_location)
        layout.addWidget(self.export_btn, 3, 0, 1, 2)

    def on_plan_change(self, plan_name):
        self.repeat_combo.clear()
        self.repeat_combo.addItem("---")

        if plan_name != "---":
            trainer = self.trainer_map[plan_name]
            self.real_plan_opt = {plan.get_name(): plan for plan in trainer.get_plans()}
            self.repeat_combo.addItems(list(self.real_plan_opt.keys()))
        else:
            self.real_plan_opt = {}

    def on_repeat_change(self, repeat_name):
        self.method_combo.clear()
        self.method_combo.addItem("---")

        if repeat_name != "---":
            self.method_combo.addItems(
                ["Gradient", "Gradient * Input", *supported_saliency_methods]
            )

    def select_location(self):
        plan_name = self.plan_combo.currentText()
        repeat_name = self.repeat_combo.currentText()
        method_name = self.method_combo.currentText()

        if plan_name == "---" or repeat_name == "---" or method_name == "---":
            QMessageBox.warning(self, "Warning", "Please select all options.")
            return

        real_plan = self.real_plan_opt[repeat_name]
        eval_record = real_plan.get_eval_record()

        file_location = QFileDialog.getExistingDirectory(self, "Export Saliency")
        if not file_location:
            return

        try:
            saliency = eval_record.export_saliency(method_name, file_location)

            file_name = [plan_name, repeat_name, method_name]
            output_path = os.path.join(file_location, "_".join(file_name) + ".pickle")

            with open(output_path, "wb") as fp:
                pickle.dump(saliency, fp, protocol=pickle.HIGHEST_PROTOCOL)

            QMessageBox.information(self, "Success", f"Exported to {output_path}")
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export: {e}")
