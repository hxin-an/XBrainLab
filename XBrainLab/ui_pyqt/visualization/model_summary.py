from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QTextEdit, QMessageBox
)
from PyQt6.QtCore import Qt
from torchinfo import summary

class ModelSummaryWindow(QDialog):
    def __init__(self, parent, trainers):
        super().__init__(parent)
        self.setWindowTitle("Model Summary")
        self.resize(800, 600)
        
        self.trainers = trainers
        self.trainer_map = {t.get_name(): t for t in trainers}
        
        self.check_data()
        self.init_ui()
        
    def check_data(self):
        if not self.trainers:
            QMessageBox.warning(self, "Warning", "No valid training plan is generated")
            # We don't reject here immediately to allow window to show empty state if needed, 
            # but usually this is called before showing.
            
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Top: Plan Selection
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Select Plan:"))
        
        self.plan_combo = QComboBox()
        self.plan_combo.addItem("Select a plan")
        self.plan_combo.addItems(list(self.trainer_map.keys()))
        self.plan_combo.currentTextChanged.connect(self.on_plan_select)
        top_layout.addWidget(self.plan_combo)
        
        layout.addLayout(top_layout)
        
        # Center: Summary Text
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setFontFamily("Courier New") # Monospace for alignment
        layout.addWidget(self.summary_text)
        
    def on_plan_select(self, plan_name):
        self.summary_text.clear()
        if plan_name not in self.trainer_map:
            return
            
        trainer = self.trainer_map[plan_name]
        try:
            # Logic adapted from original
            model_instance = trainer.model_holder.get_model(
                trainer.dataset.get_epoch_data().get_model_args()
            ).to(trainer.option.get_device())
            
            X, _ = trainer.dataset.get_training_data()
            # Assuming X is [N, C, T] or similar
            # Original code: train_shape = (self.trainer.option.bs, 1, *X.shape[-2:])
            # We need to be careful about dimensions.
            # If X is [N, C, T], shape[-2:] is (C, T).
            # If model expects (Batch, 1, C, T) (e.g. EEGNet often treats channels as spatial dim), then this is correct.
            # But let's trust the original logic.
            
            train_shape = (trainer.option.bs, 1, *X.shape[-2:])
            
            summary_str = str(summary(
                model_instance, input_size=train_shape, verbose=0
            ))
            
            self.summary_text.setText(summary_str)
            
        except Exception as e:
            self.summary_text.setText(f"Error generating summary: {e}")
