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

from XBrainLab.backend.application import EvaluateCommand
from XBrainLab.backend.training.record.wrappers import PooledRecordWrapper
from XBrainLab.ui.application_capabilities import (
    LegacyControllerFallbackUnavailableError,
    execute_application_command,
    get_legacy_controller_from_study,
    run_legacy_controller_fallback,
)
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
        preprocess_controller: Injected ``PreprocessController`` for
            preprocess-state invalidation events.
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

    def __init__(
        self,
        controller=None,
        training_controller=None,
        parent=None,
        preprocess_controller=None,
    ):
        """Initialize the evaluation panel.

        Args:
            controller: Optional ``EvaluationController``. Resolved from
                the parent study if not provided.
            training_controller: Optional ``TrainingController`` for
                subscribing to training-stopped events.
            preprocess_controller: Optional ``PreprocessController`` for
                subscribing to preprocess invalidation events.
            parent: Parent widget (typically the main window).

        """
        # 1. Controller Resolution
        if controller is None and parent and hasattr(parent, "study"):
            controller = get_legacy_controller_from_study(
                parent,
                parent.study,
                "evaluation",
            )
        if preprocess_controller is None and parent and hasattr(parent, "study"):
            preprocess_controller = get_legacy_controller_from_study(
                parent,
                parent.study,
                "preprocess",
            )

        # Store injected training controller
        self.training_controller = training_controller
        self.preprocess_controller = preprocess_controller
        self.last_application_query = None

        # 2. Base Init
        super().__init__(parent=parent, controller=controller)

        # 3. Bridge & UI Setup
        self._setup_bridges()
        self.init_ui()

    def _setup_bridges(self):
        """Listen to TrainingController to update when training finishes."""
        training_ctrl = (
            self.training_controller or self._legacy_training_controller_for_bridges()
        )

        if training_ctrl:
            self._create_refresh_bridge(training_ctrl, "training_stopped")
            self._create_refresh_bridge(training_ctrl, "history_cleared")
            self._create_refresh_bridge(training_ctrl, "config_changed")
        if self.preprocess_controller:
            self._create_refresh_bridge(
                self.preprocess_controller,
                "preprocess_changed",
            )

    def _legacy_training_controller_for_bridges(self):
        study = getattr(self.controller, "study", None)
        if study is None:
            return None
        try:
            return run_legacy_controller_fallback(
                self,
                lambda: study.get_controller("training"),
            )
        except LegacyControllerFallbackUnavailableError:
            return None

    def update_panel(self):
        """Update panel content when switched to."""
        if hasattr(self, "info_panel"):
            pass  # Handled by InfoPanelService

        self.last_application_query = execute_application_command(
            self,
            EvaluateCommand(include_objects=True),
            refresh=False,
        )
        if self._application_query_blocks_display():
            self._show_no_data_available()
            return

        previous_plan = (
            self.model_combo.currentData() if hasattr(self, "model_combo") else None
        )
        previous_plan_text = (
            self.model_combo.currentText() if hasattr(self, "model_combo") else ""
        )
        previous_run = (
            self.run_combo.currentData() if hasattr(self, "run_combo") else None
        )
        previous_run_text = (
            self.run_combo.currentText() if hasattr(self, "run_combo") else ""
        )

        # Update Model Combo
        self.model_combo.blockSignals(True)
        self.model_combo.clear()

        plans = self._plans_from_application_query()
        if plans is None:
            plans = self._legacy_plans_for_render()
        if plans:
            for i, plan in enumerate(plans):
                self.model_combo.addItem(f"Fold {i + 1}: {plan.get_name()}", plan)

            if self.model_combo.count() > 0:
                selected_index = 0
                for i in range(self.model_combo.count()):
                    if self.model_combo.itemData(i) is previous_plan:
                        selected_index = i
                        break
                    if (
                        previous_plan_text
                        and self.model_combo.itemText(i) == previous_plan_text
                    ):
                        selected_index = i
                        break

                self.model_combo.setCurrentIndex(selected_index)
                self.on_model_changed(
                    selected_index,
                    preferred_run=previous_run,
                    preferred_run_text=previous_run_text,
                )
                # Show Charts
                self.plot_stack.setCurrentIndex(0)
            else:
                # No models found despite plans? unlikely but possible
                self.plot_stack.setCurrentIndex(1)
        else:
            self._show_no_data_available()

        self.model_combo.blockSignals(False)

    def _application_query_blocks_display(self) -> bool:
        """Return whether ApplicationService says evaluation is not displayable."""
        result = self.last_application_query
        if result is None:
            return False
        if result.failed:
            return True
        diagnostics = getattr(result, "diagnostics", {}) or {}
        return (
            diagnostics.get("payload_type") == "evaluation_summary"
            and diagnostics.get("available") is False
        )

    def _evaluation_query_payload(self) -> dict | None:
        """Return the current service-backed evaluation payload, if available."""
        result = getattr(self, "last_application_query", None)
        if result is None or result.failed:
            return None
        diagnostics = getattr(result, "diagnostics", {}) or {}
        if diagnostics.get("payload_type") != "evaluation_summary":
            return None
        return diagnostics

    def _plans_from_application_query(self):
        payload = self._evaluation_query_payload()
        if payload is None:
            return None
        return list(payload.get("plan_objects") or [])

    def _legacy_plans_for_render(self):
        if self.controller is None:
            return []
        try:
            return run_legacy_controller_fallback(self, self.controller.get_plans)
        except LegacyControllerFallbackUnavailableError:
            return []

    def _show_no_data_available(self) -> None:
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItem("No Data Available")
        self.model_combo.blockSignals(False)
        self.run_combo.clear()
        self._clear_metric_views()
        self.summary_text.clear()
        self.plot_stack.setCurrentIndex(1)

    def _clear_metric_views(self) -> None:
        self.matrix_widget.update_plot(None)
        self.bar_chart.update_plot({})
        self.metrics_table.update_data({})

    def on_model_changed(self, index, preferred_run=None, preferred_run_text=""):
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
            selected_index = 0
            for i in range(self.run_combo.count()):
                if self.run_combo.itemData(i) is preferred_run:
                    selected_index = i
                    break
                if (
                    preferred_run_text
                    and self.run_combo.itemText(i) == preferred_run_text
                ):
                    selected_index = i
                    break
            self.run_combo.setCurrentIndex(selected_index)

        self.run_combo.blockSignals(False)
        self.update_views()
        self.update_model_summary(plan)

    def update_views(self):
        """Update Matrix and Table based on current selection."""
        data = self.run_combo.currentData()
        if not data:
            self._clear_metric_views()
            return

        # Handle Average
        if data == "average":
            plan = self.model_combo.currentData()
            if not plan:
                self._clear_metric_views()
                return

            pooled_result = self._pooled_result_from_application_query(plan)
            if pooled_result is None:
                if self._evaluation_query_payload() is not None:
                    self._clear_metric_views()
                    return
                pooled_result = self._legacy_pooled_result_for_render(plan)
                if pooled_result is None:
                    self._clear_metric_views()
                    return
            pooled_labels, pooled_outputs, metrics = pooled_result

            if pooled_labels is None:
                self._clear_metric_views()
                return

            # Create proxy record for Matrix plotting
            # We need to construct a lightweight object that mimics the interface
            # expected by ConfusionMatrixWidget
            # ConfusionMatrixWidget calls record.get_confusion_figure usually, or we
            # can update it to accept raw data.
            # But simpler to keep widget interface same and pass a proxy here.

            # But simpler to keep widget interface same and pass a proxy here.

            # Use the first finished record in the plan as a template/host
            template_record = next(
                (r for r in plan.get_plans() if r.is_finished()), None
            )
            if template_record is None:
                return

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
        summary_str = self._summary_from_application_query(plan, record)
        if summary_str is None:
            summary_str = self._legacy_summary_for_render(plan, record)
        self.summary_text.setText(summary_str)

    def _legacy_pooled_result_for_render(self, plan):
        controller = self.controller
        if controller is None:
            return None
        try:
            return run_legacy_controller_fallback(
                self,
                lambda: controller.get_pooled_eval_result(plan),
            )
        except LegacyControllerFallbackUnavailableError:
            return None

    def _legacy_summary_for_render(self, plan, record=None) -> str:
        controller = self.controller
        if controller is None:
            return ""
        try:
            return run_legacy_controller_fallback(
                self,
                lambda: controller.get_model_summary_str(plan, record),
            )
        except LegacyControllerFallbackUnavailableError:
            return ""

    def _pooled_result_from_application_query(self, plan):
        payload = self._evaluation_query_payload()
        if payload is None:
            return None
        plan_index = self._current_plan_index(plan)
        results = payload.get("pooled_eval_results") or []
        if plan_index < 0 or plan_index >= len(results):
            return None
        return results[plan_index]

    def _summary_from_application_query(self, plan, record=None) -> str | None:
        payload = self._evaluation_query_payload()
        if payload is None:
            return None
        plan_index = self._current_plan_index(plan)
        summaries = payload.get("model_summaries") or []
        if plan_index < 0 or plan_index >= len(summaries):
            return ""
        summary = summaries[plan_index] or {}
        if record is None:
            return str(summary.get("plan") or "")
        run_index = self._plan_run_index(plan, record)
        run_summaries = summary.get("runs") or []
        if 0 <= run_index < len(run_summaries):
            return str(run_summaries[run_index] or "")
        return str(summary.get("plan") or "")

    def _current_plan_index(self, plan) -> int:
        for index in range(self.model_combo.count()):
            if self.model_combo.itemData(index) is plan:
                return index
        return -1

    @staticmethod
    def _plan_run_index(plan, record) -> int:
        try:
            records = list(plan.get_plans())
        except Exception:
            return -1
        for index, item in enumerate(records):
            if item is record:
                return index
        return -1

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
        toolbar_layout.setSpacing(8)

        # Model Selection
        toolbar_layout.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(96)
        self.model_combo.setMaximumWidth(180)
        self.model_combo.currentIndexChanged.connect(self.on_model_changed)
        toolbar_layout.addWidget(self.model_combo)

        toolbar_layout.addSpacing(4)

        # Run Selection
        toolbar_layout.addWidget(QLabel("Run:"))
        self.run_combo = QComboBox()
        self.run_combo.setMinimumWidth(96)
        self.run_combo.setMaximumWidth(180)
        self.run_combo.currentIndexChanged.connect(self.update_views)
        toolbar_layout.addWidget(self.run_combo)

        toolbar_layout.addSpacing(4)

        # Options
        self.chk_percentage = QCheckBox("Percent")
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
