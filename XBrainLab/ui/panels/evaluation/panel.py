"""Evaluation panel for viewing confusion matrices, metrics, and model summaries."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.training.record.wrappers import PooledRecordWrapper
from XBrainLab.ui.components.info_panel import AggregateInfoPanel
from XBrainLab.ui.core.base_panel import BasePanel
from XBrainLab.ui.panels.evaluation.confusion_matrix import ConfusionMatrixWidget
from XBrainLab.ui.panels.evaluation.metrics_bar_chart import MetricsBarChartWidget
from XBrainLab.ui.panels.evaluation.metrics_table import MetricsTableWidget
from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.styles.theme import Theme


class EvaluationPanel(BasePanel):
    """Panel for analysing trained-model performance.

    Displays confusion matrices, per-class metric tables and bar charts,
    and textual model summaries.  Supports plan/run selection and
    percentage-toggle options.

    Attributes:
        training_controller: Injected ``TrainingController`` for event
            subscription.
        model_combo: ``QComboBox`` for selecting a training fold/plan.
        run_combo: ``QComboBox`` for selecting an individual run or
            average.
        chk_percentage: ``QCheckBox`` toggling percentage display.
        matrix_widget: ``ConfusionMatrixWidget`` for the matrix plot.
        bar_chart: ``MetricsBarChartWidget`` for per-class bar chart.
        metrics_table: ``MetricsTableWidget`` for the metrics table.
        summary_text: ``QTextEdit`` displaying the model summary string.
        info_panel: ``AggregateInfoPanel`` in the sidebar.

    """

    def __init__(self, controller=None, training_controller=None, parent=None):
        """Initialize the evaluation panel.

        Args:
            controller: Optional ``EvaluationController``. Resolved from
                the parent study if not provided.
            training_controller: Optional ``TrainingController`` for
                subscribing to training-stopped events.
            parent: Parent widget (typically the main window).

        """
        # 1. Controller Resolution
        if controller is None and parent and hasattr(parent, "study"):
            controller = parent.study.get_controller("evaluation")

        # Store injected training controller
        self.training_controller = training_controller

        # 2. Base Init
        super().__init__(parent=parent, controller=controller)

        # 3. Bridge & UI Setup
        self._setup_bridges()
        self.init_ui()

    def _setup_bridges(self):
        """Listen to TrainingController to update when training finishes."""
        # Use injected controller if available, fallback to legacy
        training_ctrl = self.training_controller
        if not training_ctrl and self.controller and hasattr(self.controller, "study"):
            training_ctrl = self.controller.study.get_controller("training")

        if training_ctrl:
            self._create_bridge(
                training_ctrl,
                "training_stopped",
                self.update_panel,
            )

    def update_panel(self):
        """Update panel content when switched to."""
        if hasattr(self, "info_panel"):
            pass  # Handled by InfoPanelService

        # Update Model Combo
        self.model_combo.blockSignals(True)
        self.model_combo.clear()

        plans = self.controller.get_plans()
        if plans:
            for i, plan in enumerate(plans):
                self.model_combo.addItem(f"Fold {i + 1}: {plan.get_name()}", plan)

            if self.model_combo.count() > 0:
                self.model_combo.setCurrentIndex(0)
                self.on_model_changed(0)  # Manually trigger update for runs
                # Show Charts
                self.plot_stack.setCurrentIndex(0)
            else:
                # No models found despite plans? unlikely but possible
                self.plot_stack.setCurrentIndex(1)
        else:
            self.model_combo.addItem("No Data Available")
            self.run_combo.clear()
            self.matrix_widget.update_plot(None)  # Clear plot
            self.bar_chart.update_plot({})  # Clear bar chart
            self.metrics_table.update_data({})
            self.summary_text.clear()
            # Show No Data Label
            self.plot_stack.setCurrentIndex(1)

        self.model_combo.blockSignals(False)

    def on_model_changed(self, index):
        """Handle model selection change."""
        if index < 0:
            return

        plan = self.model_combo.currentData()
        if not plan:
            return

        # Update Run Combo
        self.run_combo.blockSignals(True)
        self.run_combo.clear()

        records = plan.get_plans()
        finished_records = [r for r in records if r.is_finished()]

        # Add Individual Runs
        for i, record in enumerate(records):
            status = " (Finished)" if record.is_finished() else ""
            self.run_combo.addItem(f"Repeat {i + 1}{status}", record)

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
            if not plan:
                return

            (
                pooled_labels,
                pooled_outputs,
                metrics,
            ) = self.controller.get_pooled_eval_result(plan)

            if pooled_labels is None:
                return

            # Create proxy record for Matrix plotting
            # We need to construct a lightweight object that mimics the interface
            # expected by ConfusionMatrixWidget
            # ConfusionMatrixWidget calls record.get_confusion_figure usually, or we
            # can update it to accept raw data.
            # But simpler to keep widget interface same and pass a proxy here.

            # But simpler to keep widget interface same and pass a proxy here.

            # Use the first finished record in the plan as a template/host
            template_record = next(r for r in plan.get_plans() if r.is_finished())

            proxy_record = PooledRecordWrapper(
                template_record,
                pooled_labels,
                pooled_outputs,
            )

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

    def update_info(self):
        """Update the aggregate info panel."""
        # Handled by InfoPanelService

    def init_ui(self):
        """Build the evaluation panel layout with plots, toolbar, tabs, and sidebar."""
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

        # Stacked Widget for Data vs No Data
        self.plot_stack = QStackedWidget()

        # Page 0: Charts View
        self.charts_container = QWidget()
        charts_layout = QHBoxLayout(self.charts_container)
        charts_layout.setContentsMargins(0, 0, 0, 0)

        # Matrix Widget
        self.matrix_widget = ConfusionMatrixWidget(self)
        charts_layout.addWidget(self.matrix_widget, stretch=1)

        # Bar Chart Widget
        self.bar_chart = MetricsBarChartWidget(self)
        charts_layout.addWidget(self.bar_chart, stretch=1)

        self.plot_stack.addWidget(self.charts_container)

        # Page 1: No Data View
        self.no_data_label = QLabel("No Data Available")
        self.no_data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_data_label.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11pt;")
        self.plot_stack.addWidget(self.no_data_label)

        plots_layout.addWidget(self.plot_stack)

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
        right_panel.setStyleSheet(Stylesheets.SIDEBAR_CONTAINER)

        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 20, 10, 20)

        # Aggregate Info
        self.info_panel = AggregateInfoPanel(self.main_window)
        self.info_panel.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        right_layout.addWidget(self.info_panel)

        right_layout.addStretch()

        # Add to main layout
        main_layout.addWidget(left_widget, stretch=1)
        main_layout.addWidget(right_panel, stretch=0)
