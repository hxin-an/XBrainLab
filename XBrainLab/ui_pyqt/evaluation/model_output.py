from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout, QLabel, QComboBox, 
    QPushButton, QFileDialog, QMessageBox
)

class ModelOutputWindow(QDialog):
    def __init__(self, parent, trainers):
        super().__init__(parent)
        self.setWindowTitle("Export Model Output (csv)")
        self.resize(400, 150)
        
        self.trainers = trainers
        self.training_plan_map = {trainer.get_name(): trainer for trainer in trainers}
        self.real_plan_map = {}
        
        self.init_ui()
        
    def init_ui(self):
        layout = QGridLayout(self)
        
        # Plan
        layout.addWidget(QLabel("Plan Name:"), 0, 0)
        self.plan_combo = QComboBox()
        self.plan_combo.addItem("Select a plan")
        self.plan_combo.addItems(list(self.training_plan_map.keys()))
        self.plan_combo.currentTextChanged.connect(self.on_plan_select)
        layout.addWidget(self.plan_combo, 0, 1)
        
        # Repeat
        layout.addWidget(QLabel("Repeat:"), 1, 0)
        self.repeat_combo = QComboBox()
        self.repeat_combo.addItem("Select repeat")
        layout.addWidget(self.repeat_combo, 1, 1)
        
        # Export
        self.export_btn = QPushButton("Export")
        self.export_btn.clicked.connect(self.export)
        layout.addWidget(self.export_btn, 2, 0, 1, 2)
        
    def on_plan_select(self, plan_name):
        self.repeat_combo.clear()
        self.repeat_combo.addItem("Select repeat")
        
        if plan_name in self.training_plan_map:
            trainer = self.training_plan_map[plan_name]
            self.real_plan_map = {plan.get_name(): plan for plan in trainer.get_plans()}
            self.repeat_combo.addItems(list(self.real_plan_map.keys()))
        else:
            self.real_plan_map = {}

    def export(self):
        repeat_name = self.repeat_combo.currentText()
        if repeat_name not in self.real_plan_map:
            QMessageBox.warning(self, "Warning", "Please select a training plan")
            return
            
        real_plan = self.real_plan_map[repeat_name]
        record = real_plan.get_eval_record()
        
        if not record:
            QMessageBox.warning(self, "Warning", "No evaluation record for this training plan")
            return
            
        plan_name = self.plan_combo.currentText()
        default_name = f"{plan_name}-{real_plan.get_name()}.csv"
        
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save CSV", 
            f"{real_plan.target_path}/{default_name}", 
            "CSV files (*.csv)"
        )
        
        if filename:
            try:
                record.export_csv(filename)
                QMessageBox.information(self, "Success", "Done")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export: {e}")
