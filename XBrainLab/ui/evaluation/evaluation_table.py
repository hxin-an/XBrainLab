from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QTreeWidget, QTreeWidgetItem, QHeaderView, QMessageBox
)
from PyQt6.QtCore import QTimer
from XBrainLab.backend.evaluation import Metric

class EvaluationTableWidget(QWidget):
    def __init__(self, parent, trainers, metric=None):
        super().__init__(parent)
        
        self.trainers = trainers
        self.check_data()
        
        self.metric_list = [i.value for i in Metric]
        
        self.init_ui()
        
        if metric:
            self.metric_combo.setCurrentText(metric.value)
            
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_loop)
        self.timer.start(1000)
        
        self.update_loop()

    def check_data(self):
        if not isinstance(self.trainers, list) or len(self.trainers) == 0:
            # QMessageBox.warning(self, "Warning", "No valid training plan is generated")
            pass # Suppress warning in embedded mode

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Metric Selection
        top_layout = QHBoxLayout()
        lbl = QLabel("Metric:")
        lbl.setStyleSheet("color: #cccccc;")
        top_layout.addWidget(lbl)
        
        self.metric_combo = QComboBox()
        self.metric_combo.addItems(self.metric_list)
        self.metric_combo.setStyleSheet("""
            QComboBox {
                background-color: #3e3e42;
                color: #cccccc;
                border: 1px solid #555;
                padding: 5px;
            }
            QComboBox::drop-down {
                border: 0px;
            }
        """)
        self.metric_combo.currentTextChanged.connect(self.on_metric_change)
        top_layout.addWidget(self.metric_combo)
        top_layout.addStretch()
        layout.addLayout(top_layout)
        
        layout.addSpacing(10) # Add breathing room
        
        # Tree
        self.tree = QTreeWidget()
        self.tree.setAlternatingRowColors(True)
        if self.trainers:
            # Use "Group X" naming for columns if needed, but here columns are usually Run names (e.g. Fold 1, Fold 2)
            # The rows are the Plans (Trainers).
            # So we need to update the ROW names to be "Group X".
            columns = [plan.get_name() for plan in self.trainers[0].get_plans()] + ['Average']
            self.tree.setHeaderLabels(['Group'] + columns)
        else:
            self.tree.setHeaderLabels(['Group', 'Average'])
            
        self.tree.setStyleSheet("""
            QTreeWidget {
                background-color: #1e1e1e;
                alternate-background-color: #252526;
                color: #cccccc;
                border: 1px solid #3e3e42;
            }
            QTreeWidget::item {
                height: 25px;
                color: #cccccc;
            }
            QTreeWidget::item:selected {
                background-color: #007acc;
                color: #ffffff;
            }
            QTreeWidget::item:hover {
                background-color: #2a2d2e;
            }
            QHeaderView::section {
                background-color: #2d2d2d;
                color: #cccccc;
                border: 1px solid #3e3e42;
                padding: 4px;
            }
        """)
        layout.addWidget(self.tree)
        
        # Init items
        self.items = {}
        if self.trainers:
            for i, trainer in enumerate(self.trainers):
                group_name = f"Group {i+1}"
                item = QTreeWidgetItem(self.tree)
                item.setText(0, group_name)
                self.items[trainer.get_name()] = item
                
            self.avg_item = QTreeWidgetItem(self.tree)
            self.avg_item.setText(0, "Average")
        
    def on_metric_change(self, text):
        self.update_loop()

    def update_loop(self):
        if not self.isVisible() or not self.trainers:
            return
            
        metric_name = self.metric_combo.currentText()
        total_values = []
        
        for trainer in self.trainers:
            values = []
            plans = trainer.get_plans()
            
            if metric_name == Metric.ACC.value:
                values = [plan.get_acc() for plan in plans]
            elif metric_name == Metric.AUC.value:
                values = [plan.get_auc() for plan in plans]
            elif metric_name == Metric.KAPPA.value:
                values = [plan.get_kappa() for plan in plans]
                
            # Calculate row average
            valid_values = [v for v in values if v is not None]
            if valid_values:
                row_avg = sum(valid_values) / len(valid_values)
                values.append(row_avg)
            else:
                values.append(None)
                
            total_values.append(values)
            
            # Update row
            if trainer.get_name() in self.items:
                item = self.items[trainer.get_name()]
                for i, val in enumerate(values):
                    item.setText(i+1, f"{val:.4f}" if val is not None else "")
                
        # Calculate column averages
        if total_values:
            num_cols = len(total_values[0])
            avg_values = []
            for i in range(num_cols):
                col_vals = [row[i] for row in total_values if row[i] is not None]
                if col_vals:
                    avg_values.append(sum(col_vals) / len(col_vals))
                else:
                    avg_values.append(None)
            
            if hasattr(self, 'avg_item'):
                for i, val in enumerate(avg_values):
                    self.avg_item.setText(i+1, f"{val:.4f}" if val is not None else "")
