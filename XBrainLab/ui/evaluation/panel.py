from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QCheckBox, 
    QLabel, QGroupBox, QFrame, QPushButton, QSpacerItem, QSizePolicy,
    QTabWidget, QTextEdit
)
from PyQt6.QtCore import Qt
from torchinfo import summary
from XBrainLab.ui.dashboard_panel.info import AggregateInfoPanel
from XBrainLab.ui.evaluation.confusion_matrix import ConfusionMatrixWidget
from XBrainLab.ui.evaluation.metrics_table import MetricsTableWidget
from XBrainLab.ui.evaluation.metrics_bar_chart import MetricsBarChartWidget

class EvaluationPanel(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        # self.study = main_window.study # Decoupled
        from XBrainLab.backend.controller.evaluation_controller import EvaluationController
        self.controller = EvaluationController(main_window.study)
        self.init_ui()

    def update_panel(self):
        """Update panel content when switched to."""
        if hasattr(self, 'info_panel'):
            self.info_panel.update_info()
            
        # Update Model Combo
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        
        plans = self.controller.get_plans()
        if plans:
            for i, plan in enumerate(plans):
                self.model_combo.addItem(f"Fold {i+1}: {plan.get_name()}", plan)
                
            if self.model_combo.count() > 0:
                self.model_combo.setCurrentIndex(0)
                self.on_model_changed(0) # Manually trigger update for runs
        else:
            self.model_combo.addItem("No Data Available")
            self.run_combo.clear()
            self.matrix_widget.update_plot(None) # Clear plot
            self.bar_chart.update_plot({}) # Clear bar chart
            self.metrics_table.update_data({})
            self.summary_text.clear()
            
        self.model_combo.blockSignals(False)

    def on_model_changed(self, index):
        """Handle model selection change."""
        if index < 0: return
        
        plan = self.model_combo.currentData()
        if not plan: return
        
        # Update Run Combo
        self.run_combo.blockSignals(True)
        self.run_combo.clear()
        
        records = plan.get_plans()
        finished_records = [r for r in records if r.is_finished()]
        
        # Add Individual Runs
        for i, record in enumerate(records):
            status = " (Finished)" if record.is_finished() else ""
            self.run_combo.addItem(f"Repeat {i+1}{status}", record)
            
        # Add Average Option if we have finished runs
        if finished_records:
            self.run_combo.addItem("Average (Finished Runs)", "average")
            
        if self.run_combo.count() > 0:
            self.run_combo.setCurrentIndex(0)
            
        self.run_combo.blockSignals(False)
        self.update_views()
        self.update_model_summary(plan)

    def update_views(self):
        """Update Matrix and Table based on current selection."""
        data = self.run_combo.currentData()
        if not data:
            return
            
        # Handle Average
        if data == "average":
            plan = self.model_combo.currentData()
            if not plan: return
            
            pooled_labels, pooled_outputs, metrics = self.controller.get_pooled_eval_result(plan)
            
            if pooled_labels is None: 
                return
            
            # Create proxy record for Matrix plotting
            # We need to construct a lightweight object that mimics the interface expected by ConfusionMatrixWidget
            # ConfusionMatrixWidget calls record.get_confusion_figure usually, or we can update it to accept raw data.
            # But simpler to keep widget interface same and pass a proxy here.
            
            from XBrainLab.backend.training.record import EvalRecord
            
            class ProxyRecord:
                def __init__(self, labels, outputs):
                    self.eval_record = EvalRecord(labels, outputs, {}, {}, {}, {}, {})
                    
                def get_confusion_figure(self, fig=None, show_percentage=False):
                    from XBrainLab.backend.training.record.train import TrainRecord
                    # Reuse static method if available or instantiate TrainRecord dynamically
                    # Wait, TrainRecord.get_confusion_figure is instance method.
                    # We can use a helper or modify the widget. 
                    # Actually, we can use the first record of the plan as a "host" for the plotting logic?
                    pass

            # Update Matrix
            # Hack: The ConfusionMatrixWidget.update_plot(record) calls record.get_confusion_figure(self.figure, ...)
            # We can create a temporary object that has get_confusion_figure method.
            
            # Strategy: Use one real record but patch its eval_record momentarily? No, not thread safe/clean.
            # Better: Let the controller return a full ProxyRecord object that has the method?
            # Or better: The controller just returns data, and we construct the plot here?
            # Or we pass the data to widget.
            
            # Let's see ConfusionMatrixWidget implementation via assumption (or I can read it if needed).
            # But wait, I see logic in lines 259-286 of original file attempting to create DummyRecord.
            # I should reuse that concept but cleaner.
            
            # Actually, let's use the first available finished record in the plan to drive the plot, 
            # but substitute its data.
            template_record = [r for r in plan.get_plans() if r.is_finished()][0]
            
            class PooledRecordWrapper:
                def __init__(self, original, labels, outputs):
                    self.original = original
                    self.eval_record = EvalRecord(labels, outputs, {}, {}, {}, {}, {})
                    self.dataset = original.dataset # Needed for class names
                
                def get_confusion_figure(self, fig=None, show_percentage=False):
                    # Delegate finding class names etc to original class method?
                    # `TrainRecord.get_confusion_figure` heavily depends on `self.dataset`
                    return self.original.__class__.get_confusion_figure(self, fig, show_percentage=show_percentage)
            
            proxy_record = PooledRecordWrapper(template_record, pooled_labels, pooled_outputs)
            
            show_pct = self.chk_percentage.isChecked()
            self.matrix_widget.update_plot(proxy_record, show_percentage=show_pct)
            
            self.metrics_table.update_data(metrics)
            self.bar_chart.update_plot(metrics)
            return

        # Handle Single Record
        record = data
        
        # Update Matrix
        show_pct = self.chk_percentage.isChecked()
        self.matrix_widget.update_plot(record, show_percentage=show_pct)
        
        # Update Table and Bar Chart
        if record.eval_record:
            metrics = record.eval_record.get_per_class_metrics()
            self.metrics_table.update_data(metrics)
            self.bar_chart.update_plot(metrics)
        else:
            self.metrics_table.update_data({})
            self.bar_chart.update_plot({})
            
        plan = self.model_combo.currentData()
        if plan:
             self.update_model_summary(plan, record=record)

    def update_model_summary(self, plan, record=None):
        """Generate and display model summary."""
        summary_str = self.controller.get_model_summary_str(plan, record)
        self.summary_text.setText(summary_str)

    def refresh_data(self):
        """Alias for update_panel to maintain compatibility with MainWindow."""
        self.update_panel()

    def update_info(self):
        """Update the aggregate info panel."""
        if hasattr(self, 'info_panel'):
            self.info_panel.update_info()
        
    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # --- Left Side: Main Content ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(20)
        
        # 1. Plots Group (Top)
        plots_group = QGroupBox("EVALUATION PLOTS")
        plots_layout = QVBoxLayout(plots_group)
        plots_layout.setContentsMargins(10, 20, 10, 10)
        
        # Horizontal Layout for Matrix and Bar Chart
        charts_layout = QHBoxLayout()
        
        # Matrix Widget
        self.matrix_widget = ConfusionMatrixWidget(self)
        charts_layout.addWidget(self.matrix_widget, stretch=1)
        
        # Bar Chart Widget
        self.bar_chart = MetricsBarChartWidget(self)
        charts_layout.addWidget(self.bar_chart, stretch=1)
        
        plots_layout.addLayout(charts_layout)
        
        # Toolbar (Below Charts)
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(0, 10, 0, 0)
        
        # Model Selection
        toolbar_layout.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(150)
        self.model_combo.currentIndexChanged.connect(self.on_model_changed)
        toolbar_layout.addWidget(self.model_combo)
        
        toolbar_layout.addSpacing(15)
        
        # Run Selection
        toolbar_layout.addWidget(QLabel("Run:"))
        self.run_combo = QComboBox()
        self.run_combo.setMinimumWidth(150)
        self.run_combo.currentIndexChanged.connect(self.update_views)
        toolbar_layout.addWidget(self.run_combo)
        
        toolbar_layout.addSpacing(15)
        
        # Options
        self.chk_percentage = QCheckBox("Show Percentage")
        self.chk_percentage.toggled.connect(self.update_views)
        toolbar_layout.addWidget(self.chk_percentage)
        
        toolbar_layout.addStretch()
        plots_layout.addLayout(toolbar_layout)
        
        # 2. Bottom Section (Tabs: Metrics & Model Summary)
        self.bottom_tabs = QTabWidget()
        
        # Tab 1: Metrics
        self.metrics_tab = QWidget()
        metrics_layout = QVBoxLayout(self.metrics_tab)
        metrics_layout.setContentsMargins(10, 10, 10, 10)
        self.metrics_table = MetricsTableWidget(self)
        metrics_layout.addWidget(self.metrics_table)
        self.bottom_tabs.addTab(self.metrics_tab, "Metrics Summary")
        
        # Tab 2: Model Summary
        self.summary_tab = QWidget()
        summary_layout = QVBoxLayout(self.summary_tab)
        summary_layout.setContentsMargins(10, 10, 10, 10)
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setFontFamily("Courier New")
        summary_layout.addWidget(self.summary_text)
        self.bottom_tabs.addTab(self.summary_tab, "Model Summary")
        
        # Add to left layout directly
        left_layout.addWidget(plots_group, stretch=2)
        left_layout.addWidget(self.bottom_tabs, stretch=1)
        
        # --- Right Side: Sidebar ---
        right_panel = QWidget()
        right_panel.setFixedWidth(260)
        right_panel.setObjectName("RightPanel")
        right_panel.setStyleSheet("""
            #RightPanel { 
                background-color: #252526; 
                border-left: 1px solid #3e3e42; 
            }
            QGroupBox {
                background-color: transparent;
                border: none;
                margin-top: 15px;
                font-weight: bold;
                color: #808080;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 0px;
                padding: 0 0px;
                color: #808080;
            }
            QPushButton {
                background-color: #3e3e42;
                border: none;
                border-radius: 4px;
                padding: 8px 12px;
                color: #ffffff;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #4e4e52;
            }
        """)
        
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 20, 10, 20)
        
        # Aggregate Info
        self.info_panel = AggregateInfoPanel(self.main_window)
        self.info_panel.setStyleSheet("""
            QGroupBox {
                background-color: transparent;
                border: none;
                margin-top: 15px;
                font-weight: bold;
                color: #808080;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 0px;
                padding: 0 0px;
                color: #808080;
            }
            QLabel {
                color: #cccccc;
                font-weight: normal;
            }
        """)
        right_layout.addWidget(self.info_panel)
        
        right_layout.addStretch()
        
        # Add to main layout
        main_layout.addWidget(left_widget, stretch=1)
        main_layout.addWidget(right_panel, stretch=0)


