"""Evaluation panel for viewing confusion matrices, metrics, and model summaries."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application import EvaluateCommand
from XBrainLab.backend.training.record.wrappers import PooledRecordWrapper
from XBrainLab.ui.application_capabilities import (
    ControllerCompatibilityUnavailableError,
    execute_application_command,
    execute_application_command_async,
    get_controller_for_compatibility_context,
    run_controller_compatibility_call,
)
from XBrainLab.ui.components.info_panel import AggregateInfoPanel
from XBrainLab.ui.core.base_panel import BasePanel
from XBrainLab.ui.panels.evaluation.confusion_matrix import ConfusionMatrixWidget
from XBrainLab.ui.panels.evaluation.metrics_bar_chart import MetricsBarChartWidget
from XBrainLab.ui.panels.evaluation.metrics_table import MetricsTableWidget
from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.styles.theme import Theme

MODEL_SUMMARY_UNAVAILABLE_TEXT = (
    "Model summary unavailable for the selected run. "
    "Train or refresh the model, then open this tab again."
)
MODEL_SUMMARY_DEFERRED_TEXT = "Open Model Summary to load model details."
MODEL_SUMMARY_BACKGROUND_UNAVAILABLE_TEXT = (
    "Model summary could not start in the background. Try again after the current "
    "operation finishes."
)


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
            controller = get_controller_for_compatibility_context(
                parent,
                parent.study,
                "evaluation",
            )
        if preprocess_controller is None and parent and hasattr(parent, "study"):
            preprocess_controller = get_controller_for_compatibility_context(
                parent,
                parent.study,
                "preprocess",
            )

        # Store injected training controller
        self.training_controller = training_controller
        self.preprocess_controller = preprocess_controller
        self.last_application_query = None
        self._application_summary_dirty = True

        # 2. Base Init
        super().__init__(parent=parent, controller=controller)

        # 3. Bridge & UI Setup
        self._setup_bridges()
        self.init_ui()

    def _setup_bridges(self):
        """Listen to TrainingController to update when training finishes."""
        if self.training_controller:
            self._create_refresh_bridge(self.training_controller, "training_stopped")
            self._create_refresh_bridge(self.training_controller, "history_cleared")
            self._create_refresh_bridge(self.training_controller, "config_changed")
        if self.preprocess_controller:
            self._create_refresh_bridge(
                self.preprocess_controller,
                "preprocess_changed",
            )

    def update_panel(self):
        """Update panel content when switched to."""
        if hasattr(self, "info_panel"):
            pass  # Handled by InfoPanelService

        if self._application_summary_dirty or self.last_application_query is None:
            self._refresh_application_query()
            self._application_summary_dirty = False

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
            plans = self._compatibility_plans_for_render()
        if plans:
            self._show_evaluation_controls_available()
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

    def mark_refresh_dirty(self) -> None:
        """Invalidate the cached ApplicationService evaluation summary."""
        self._application_summary_dirty = True

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

    def _refresh_application_query(
        self,
        *,
        include_pooled_results: bool = False,
        include_model_summaries: bool = False,
        model_summary_plan_index: int | None = None,
        model_summary_run_index: int | None = None,
    ) -> bool:
        """Refresh the service-backed evaluation payload with explicit UI needs."""
        result = execute_application_command(
            self,
            EvaluateCommand(
                include_objects=True,
                include_metrics=False,
                include_pooled_results=include_pooled_results,
                include_model_summaries=include_model_summaries,
                model_summary_plan_index=model_summary_plan_index,
                model_summary_run_index=model_summary_run_index,
            ),
            refresh=False,
        )
        if result is None:
            return False
        self.last_application_query = result
        return not result.failed

    def _refresh_application_query_async(
        self,
        *,
        include_pooled_results: bool = False,
        include_model_summaries: bool = False,
        model_summary_plan_index: int | None = None,
        model_summary_run_index: int | None = None,
        on_ready=None,
    ) -> bool:
        """Load heavy evaluation payloads off the UI thread when possible."""

        def _handle_result(result) -> None:
            self.last_application_query = result
            if result.failed:
                self._clear_metric_views()
                return
            if callable(on_ready):
                on_ready()

        def _handle_error(_error: tuple) -> None:
            self._clear_metric_views()

        return execute_application_command_async(
            self,
            EvaluateCommand(
                include_objects=True,
                include_metrics=False,
                include_pooled_results=include_pooled_results,
                include_model_summaries=include_model_summaries,
                model_summary_plan_index=model_summary_plan_index,
                model_summary_run_index=model_summary_run_index,
            ),
            on_result=_handle_result,
            on_error=_handle_error,
            refresh=False,
            busy_target=self,
        )

    def _plans_from_application_query(self):
        payload = self._evaluation_query_payload()
        if payload is None:
            return None
        return list(payload.get("plan_objects") or [])

    def _compatibility_plans_for_render(self):
        if self.controller is None:
            return []
        try:
            return run_controller_compatibility_call(self, self.controller.get_plans)
        except ControllerCompatibilityUnavailableError:
            return []

    def _show_no_data_available(self) -> None:
        message = self._evaluation_empty_state_message()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.setEnabled(False)
        self.model_combo.setToolTip(message)
        self.model_combo.blockSignals(False)
        self.run_combo.blockSignals(True)
        self.run_combo.clear()
        self.run_combo.setEnabled(False)
        self.run_combo.setToolTip(message)
        self.run_combo.blockSignals(False)
        self.chk_percentage.setEnabled(False)
        self._clear_metric_views()
        self.summary_text.clear()
        self.no_data_label.setText(message)
        self.plot_stack.setCurrentIndex(1)
        self.bottom_tabs.setVisible(False)

    def _show_evaluation_controls_available(self) -> None:
        self.model_combo.setEnabled(True)
        self.model_combo.setToolTip("")
        self.run_combo.setEnabled(True)
        self.run_combo.setToolTip("")
        self.chk_percentage.setEnabled(True)
        self.bottom_tabs.setVisible(True)

    def _evaluation_empty_state_message(self) -> str:
        result = getattr(self, "last_application_query", None)
        if result is not None and getattr(result, "failed", False):
            message = str(getattr(result, "message", "")).strip()
            if message:
                return message
        diagnostics = getattr(result, "diagnostics", {}) if result is not None else {}
        if isinstance(diagnostics, dict):
            blocked_reason = str(diagnostics.get("blocked_reason", "")).strip()
            if blocked_reason:
                return blocked_reason
        return "No evaluation results available yet."

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
                payload = self._evaluation_query_payload()
                if payload is not None:
                    if "pooled_eval_results" not in payload:
                        self._clear_metric_views()
                        if self._refresh_application_query_async(
                            include_pooled_results=True,
                            on_ready=self.update_views,
                        ):
                            return
                        self._clear_metric_views()
                        return
                    pooled_result = self._pooled_result_from_application_query(plan)
                    if pooled_result is None:
                        self._clear_metric_views()
                        return
                else:
                    pooled_result = self._compatibility_pooled_result_for_render(plan)
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
            self._update_summary_if_visible(plan)
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
            self._update_summary_if_visible(plan, record=record)

    def update_model_summary(self, plan, record=None):
        """Generate and display model summary."""
        has_service_payload = self._evaluation_query_payload() is not None
        if has_service_payload:
            payload = self._evaluation_query_payload() or {}
            plan_index = self._current_plan_index(plan)
            run_index = None if record is None else self._plan_run_index(plan, record)
            if (
                "model_summaries" not in payload
                or not self._payload_matches_model_summary_request(
                    payload,
                    plan_index,
                    run_index,
                )
            ):
                self.summary_text.setText("Loading model details...")
                if self._refresh_application_query_async(
                    include_model_summaries=True,
                    model_summary_plan_index=plan_index,
                    model_summary_run_index=run_index,
                    on_ready=lambda: self.update_model_summary(plan, record=record),
                ):
                    return
                self.summary_text.setText(MODEL_SUMMARY_BACKGROUND_UNAVAILABLE_TEXT)
                return
        summary_str = self._summary_from_application_query(plan, record)
        if summary_str is None:
            summary_str = self._compatibility_summary_for_render(plan, record)
        if has_service_payload and not summary_str.strip():
            summary_str = MODEL_SUMMARY_UNAVAILABLE_TEXT
        self.summary_text.setText(summary_str)

    def _update_summary_if_visible(self, plan, record=None) -> None:
        if not self._summary_tab_visible():
            self.summary_text.setText(MODEL_SUMMARY_DEFERRED_TEXT)
            return
        self.update_model_summary(plan, record=record)

    def _summary_tab_visible(self) -> bool:
        return (
            hasattr(self, "bottom_tabs")
            and hasattr(self, "summary_tab")
            and self.bottom_tabs.currentWidget() is self.summary_tab
        )

    def _on_bottom_tab_changed(self, _index: int) -> None:
        if not self._summary_tab_visible():
            return
        plan = self.model_combo.currentData()
        if not plan:
            self.summary_text.clear()
            return
        data = self.run_combo.currentData()
        record = None if data == "average" else data
        self.update_model_summary(plan, record=record)

    def _compatibility_pooled_result_for_render(self, plan):
        controller = self.controller
        if controller is None:
            return None
        try:
            return run_controller_compatibility_call(
                self,
                lambda: controller.get_pooled_eval_result(plan),
            )
        except ControllerCompatibilityUnavailableError:
            return None

    def _compatibility_summary_for_render(self, plan, record=None) -> str:
        controller = self.controller
        if controller is None:
            return ""
        try:
            return run_controller_compatibility_call(
                self,
                lambda: controller.get_model_summary_str(plan, record),
            )
        except ControllerCompatibilityUnavailableError:
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

    @staticmethod
    def _payload_matches_model_summary_request(
        payload: dict,
        plan_index: int,
        run_index: int | None,
    ) -> bool:
        request = payload.get("model_summary_request")
        if not isinstance(request, dict):
            return True
        return (
            request.get("plan_index") == plan_index
            and request.get("run_index") == run_index
        )

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
        self.setObjectName("EvaluationPanel")
        self.setStyleSheet(
            f"""
            QWidget#EvaluationPanel,
            QWidget#EvaluationLeft,
            QWidget#EvaluationControlsBar {{
                background-color: {Theme.BACKGROUND_DARK};
                color: {Theme.TEXT_SECONDARY};
            }}
            QGroupBox#EvaluationPlotsGroup {{
                background-color: {Theme.BACKGROUND_DARK};
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                border-radius: 4px;
                margin-top: 18px;
                color: {Theme.TEXT_PRIMARY};
                font-weight: bold;
            }}
            QGroupBox#EvaluationPlotsGroup::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color: {Theme.TEXT_PRIMARY};
            }}
            QLabel {{
                background-color: transparent;
                color: {Theme.TEXT_SECONDARY};
            }}
            QTabWidget::pane {{
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                background-color: {Theme.BACKGROUND_DARK};
            }}
            QTabBar::tab {{
                background-color: {Theme.BACKGROUND_MID};
                color: {Theme.TEXT_MUTED};
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                padding: 6px 12px;
            }}
            QTabBar::tab:selected {{
                background-color: {Theme.BACKGROUND_DARK};
                color: {Theme.TEXT_PRIMARY};
            }}
            """
        )
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Left Side: Main Content ---
        left_widget = QWidget()
        left_widget.setObjectName("EvaluationLeft")
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(20)

        # 1. Plots Group (Top)
        plots_group = QGroupBox("EVALUATION PLOTS")
        plots_group.setObjectName("EvaluationPlotsGroup")
        plots_layout = QVBoxLayout(plots_group)
        plots_layout.setContentsMargins(10, 20, 10, 10)

        # Stacked Widget for Data vs No Data
        self.plot_stack = QStackedWidget()
        self.plot_stack.setStyleSheet(f"background-color: {Theme.BACKGROUND_DARK};")

        # Page 0: Charts View
        self.charts_container = QWidget()
        self.charts_container.setStyleSheet(
            f"background-color: {Theme.BACKGROUND_DARK};"
        )
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

        # Toolbar (Above Charts)
        self.evaluation_controls_bar = QWidget()
        self.evaluation_controls_bar.setObjectName("EvaluationControlsBar")
        toolbar_layout = QGridLayout(self.evaluation_controls_bar)
        toolbar_layout.setContentsMargins(0, 0, 0, 8)
        toolbar_layout.setHorizontalSpacing(10)
        toolbar_layout.setVerticalSpacing(8)
        toolbar_layout.setColumnStretch(1, 1)

        # Model Selection
        model_label = QLabel("Model:")
        model_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        toolbar_layout.addWidget(model_label, 0, 0)
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(360)
        self.model_combo.setMinimumContentsLength(36)
        self.model_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon,
        )
        self.model_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.model_combo.setStyleSheet(Stylesheets.COMBO_BOX)
        model_view = self.model_combo.view()
        if model_view is not None:
            model_view.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.model_combo.currentIndexChanged.connect(self.on_model_changed)
        toolbar_layout.addWidget(self.model_combo, 0, 1, 1, 3)

        # Run Selection
        run_label = QLabel("Run:")
        run_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        toolbar_layout.addWidget(run_label, 1, 0)
        self.run_combo = QComboBox()
        self.run_combo.setMinimumWidth(320)
        self.run_combo.setMinimumContentsLength(32)
        self.run_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon,
        )
        self.run_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.run_combo.setStyleSheet(Stylesheets.COMBO_BOX)
        run_view = self.run_combo.view()
        if run_view is not None:
            run_view.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.run_combo.currentIndexChanged.connect(self.update_views)
        toolbar_layout.addWidget(self.run_combo, 1, 1)

        # Options
        self.chk_percentage = QCheckBox("Percent")
        self.chk_percentage.setStyleSheet(Stylesheets.CHECKBOX_MUTED)
        self.chk_percentage.toggled.connect(self.update_views)
        toolbar_layout.addWidget(self.chk_percentage, 1, 2)
        plots_layout.addWidget(self.evaluation_controls_bar)
        plots_layout.addWidget(self.plot_stack, stretch=1)

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
        self.summary_text.setStyleSheet(Stylesheets.LOG_TEXT)
        summary_layout.addWidget(self.summary_text)
        self.bottom_tabs.addTab(self.summary_tab, "Model Summary")
        self.bottom_tabs.currentChanged.connect(self._on_bottom_tab_changed)

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
