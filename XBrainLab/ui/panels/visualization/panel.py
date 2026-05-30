"""Visualization panel: saliency maps, topomaps, spectrograms, and 3-D views."""

import re

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application import SaliencyCommand, VisualizeCommand
from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.visualization import supported_saliency_methods
from XBrainLab.ui.application_capabilities import (
    ControllerCompatibilityUnavailableError,
    execute_application_command,
    execute_application_command_async,
    get_controller_for_compatibility_context,
    run_controller_compatibility_call,
)
from XBrainLab.ui.core.base_panel import BasePanel
from XBrainLab.ui.styles.stylesheets import Stylesheets

from .control_sidebar import ControlSidebar
from .saliency_views.map_view import SaliencyMapWidget
from .saliency_views.plot_3d_view import Saliency3DPlotWidget
from .saliency_views.spectrogram_view import SaliencySpectrogramWidget
from .saliency_views.topomap_view import SaliencyTopographicMapWidget

_MISSING = object()


class VisualizationPanel(BasePanel):
    """Panel for visualizing data and model explanations with unified controls.
    Manages multiple view tabs (Map, Topomap, Spectrogram, 3D) and coordinates updates.
    """

    def __init__(
        self,
        controller=None,
        training_controller=None,
        parent=None,
        preprocess_controller=None,
    ):
        """Initialize the visualization panel.

        Args:
            controller: Optional ``VisualizationController``. Resolved from
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
                "visualization",
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
        self.friendly_map = {}
        self.last_application_query = None
        self.last_saliency_query = None
        self._application_summary_dirty = True
        self._saliency_summary_dirty = True

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
        if self.controller:
            self._create_refresh_bridge(self.controller, "montage_changed")
            self._create_refresh_bridge(self.controller, "saliency_changed")
        if self.preprocess_controller:
            self._create_refresh_bridge(
                self.preprocess_controller,
                "preprocess_changed",
            )

    def init_ui(self):
        """Build the panel layout with control bar, tabbed plots, and sidebar."""
        # Main Layout: Horizontal (Left: Content, Right: Controls)
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Left Column: Visualization Content ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(10)

        # 1. Unified Control Bar
        ctrl_bar = QGroupBox("VISUALIZATION CONTROLS")
        ctrl_layout = QGridLayout(ctrl_bar)
        ctrl_layout.setContentsMargins(10, 15, 10, 10)
        ctrl_layout.setHorizontalSpacing(8)
        ctrl_layout.setVerticalSpacing(6)
        ctrl_layout.setColumnStretch(4, 1)

        # Plan Selector
        ctrl_layout.addWidget(QLabel("Plan:"), 0, 0)
        self.plan_combo = QComboBox()
        self.plan_combo.addItem("Select a plan")
        self.plan_combo.setMinimumWidth(150)
        self.plan_combo.setMaximumWidth(220)
        self.plan_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon,
        )
        self.plan_combo.setStyleSheet(Stylesheets.COMBO_BOX)
        self.plan_combo.currentTextChanged.connect(self.on_plan_changed)
        ctrl_layout.addWidget(self.plan_combo, 0, 1)

        # Run Selector
        ctrl_layout.addWidget(QLabel("Run:"), 0, 2)
        self.run_combo = QComboBox()
        self.run_combo.setMinimumWidth(120)
        self.run_combo.setMaximumWidth(180)
        self.run_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon,
        )
        self.run_combo.setStyleSheet(Stylesheets.COMBO_BOX)
        self.run_combo.currentTextChanged.connect(self.on_update)
        ctrl_layout.addWidget(self.run_combo, 0, 3)

        # Method Selector
        ctrl_layout.addWidget(QLabel("Method:"), 1, 0)
        self.method_combo = QComboBox()
        self.method_combo.addItem("Gradient")
        self.method_combo.addItem("Gradient * Input")
        self.method_combo.addItems(supported_saliency_methods)
        self.method_combo.setMinimumWidth(150)
        self.method_combo.setMaximumWidth(220)
        self.method_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon,
        )
        self.method_combo.setStyleSheet(Stylesheets.COMBO_BOX)
        self.method_combo.currentTextChanged.connect(self.on_update)
        ctrl_layout.addWidget(self.method_combo, 1, 1)

        # Absolute Checkbox
        self.abs_check = QCheckBox("Absolute")
        self.abs_check.setToolTip("Use absolute saliency values")
        self.abs_check.setStyleSheet(Stylesheets.CHECKBOX_MUTED)
        self.abs_check.stateChanged.connect(self.on_update)
        ctrl_layout.addWidget(self.abs_check, 1, 3)
        left_layout.addWidget(ctrl_bar)

        # 2. Plots Group
        plots_group = QGroupBox("EXPLANATION PLOTS")
        plots_layout = QVBoxLayout(plots_group)
        plots_layout.setContentsMargins(10, 20, 10, 10)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(Stylesheets.TAB_WIDGET_CLEAN)
        # Signal connected at the end of init_ui to avoid early triggering

        # Get trainers for initialization (empty initially)

        # Tab 1: Saliency Map
        self.tab_map = SaliencyMapWidget(self)
        self.tabs.addTab(self.tab_map, "Saliency Map")

        # Tab 2: Spectrogram (Swapped order)
        self.tab_spectro = SaliencySpectrogramWidget(self)
        self.tabs.addTab(self.tab_spectro, "Spectrogram")

        # Tab 3: Topographic Map
        self.tab_topo = SaliencyTopographicMapWidget(self)
        self.tabs.addTab(self.tab_topo, "Topographic Map")

        # Tab 4: 3D Plot
        self.tab_3d = Saliency3DPlotWidget(self)
        self.tabs.addTab(self.tab_3d, "3D Plot")

        plots_layout.addWidget(self.tabs)
        left_layout.addWidget(plots_group, stretch=1)
        main_layout.addWidget(left_widget, stretch=1)

        # --- Right Side: Sidebar ---
        self.sidebar = ControlSidebar(self, self)
        main_layout.addWidget(self.sidebar, stretch=0)

        # Connect tab signal now that everything is initialized
        self.tabs.currentChanged.connect(self.on_tab_changed)

        # Keep startup light; populate data-backed controls when the panel is opened.
        self._clear_plan_controls()

    def get_trainers(self):
        """Return the list of available trainers from the controller.

        Returns:
            list: Trainer instances available for visualization.

        """
        trainers = self._trainers_from_application_query()
        if trainers is not None:
            return trainers
        if self.last_application_query is not None:
            return []
        return self._compatibility_trainers_for_render()

    def _compatibility_trainers_for_render(self):
        if self.controller is None:
            return []
        try:
            return run_controller_compatibility_call(self, self.controller.get_trainers)
        except ControllerCompatibilityUnavailableError:
            return []

    def refresh_combos(self):
        """Refresh Plan ComboBox based on current trainers."""
        if self._application_summary_dirty or self.last_application_query is None:
            self._refresh_application_query(view="summary")
            self._application_summary_dirty = False

        if self._application_query_blocks_display(self.last_application_query):
            self._clear_plan_controls()
            return

        trainers = self.get_trainers()
        previous_plan = self.plan_combo.currentData()
        previous_plan_text = self.plan_combo.currentText()
        previous_run = self.run_combo.currentData()
        previous_run_text = self.run_combo.currentText()

        self.plan_combo.blockSignals(True)
        self.run_combo.blockSignals(True)
        self.plan_combo.clear()
        self.plan_combo.addItem("Select a plan")
        self.run_combo.clear()
        self.friendly_map = {}

        if not trainers:
            self.plan_combo.blockSignals(False)
            self.run_combo.blockSignals(False)
            self.on_update()
            return

        for i, trainer in enumerate(trainers):
            model_name = trainer.model_holder.target_model.__name__
            friendly_name = f"Fold {i + 1} ({model_name})"
            self.friendly_map[friendly_name] = trainer
            self.plan_combo.addItem(friendly_name, trainer)

        # If items exist, select first real plan
        if self.plan_combo.count() > 1:
            selected_index = 1
            for i in range(1, self.plan_combo.count()):
                if self.plan_combo.itemData(i) is previous_plan:
                    selected_index = i
                    break
                if (
                    previous_plan_text
                    and self.plan_combo.itemText(i) == previous_plan_text
                ):
                    selected_index = i
                    break
            self.plan_combo.setCurrentIndex(selected_index)
            self.plan_combo.blockSignals(False)
            self.run_combo.blockSignals(False)
            # Explicitly call on_plan_changed to ensure run_combo is populated
            self.on_plan_changed(
                self.plan_combo.currentText(),
                preferred_run=previous_run,
                preferred_run_text=previous_run_text,
            )
        else:
            self.plan_combo.blockSignals(False)
            self.run_combo.blockSignals(False)

    def on_plan_changed(self, text, preferred_run=None, preferred_run_text=""):
        """Update Run combo when Plan changes."""
        self.run_combo.blockSignals(True)
        self.run_combo.clear()

        if text in self.friendly_map:
            trainer = self.friendly_map[text]
            plans = trainer.get_plans()
            # Add runs
            for i in range(trainer.option.repeat_num):
                plan = plans[i] if i < len(plans) else None
                self.run_combo.addItem(f"Run {i + 1}", plan)
            # Add Average
            if plans:
                self.run_combo.addItem("Average", "average")

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
            self.on_update()
        else:
            self.run_combo.blockSignals(False)
            self.on_update()  # Trigger update to clear if empty

    def on_tab_changed(self, index):
        """Handle tab switch."""
        # Montage button is now always visible as per user request
        # self.btn_montage.setVisible(True) # It's visible by default

        self.on_update()

    def on_update(self):
        """Gather settings and call update_plot on current tab."""
        current_widget = self.tabs.currentWidget()
        if self._application_summary_dirty or self.last_application_query is None:
            self._refresh_application_query(
                view=self.tabs.tabText(self.tabs.currentIndex()),
            )
            self._application_summary_dirty = False

        if self._application_query_blocks_display(self.last_application_query):
            self._show_widget_error(current_widget, self._application_query_message())
            return

        plan_name = self.plan_combo.currentText()
        run_name = self.run_combo.currentText()
        method_name = self.method_combo.currentText()
        absolute = self.abs_check.isChecked()

        if plan_name not in self.friendly_map or not run_name:
            setup_message = self._setup_only_message()
            if setup_message:
                self._show_widget_message(current_widget, setup_message)
                return
            # Clear or show placeholder
            self._show_widget_error(current_widget, "Please select a Plan and Run.")
            return

        trainer = self.friendly_map[plan_name]

        # Resolve Plan and EvalRecord
        target_plan = None
        eval_record = None
        run_data = self.run_combo.currentData()

        if run_data == "average" or run_name == "Average":
            averaged_record = self._averaged_record_from_application_query(trainer)
            if averaged_record is _MISSING:
                if self._visualization_query_payload() is not None:
                    self._show_widget_message(
                        current_widget,
                        "Loading averaged saliency...",
                    )
                    if self._refresh_application_query_async(
                        view=self.tabs.tabText(self.tabs.currentIndex()),
                        include_averaged_records=True,
                        on_ready=self.on_update,
                    ):
                        return
                    self._refresh_application_query(
                        view=self.tabs.tabText(self.tabs.currentIndex()),
                        include_averaged_records=True,
                    )
                    averaged_record = self._averaged_record_from_application_query(
                        trainer,
                    )
                    eval_record = (
                        None if averaged_record is _MISSING else averaged_record
                    )
                else:
                    eval_record = self._compatibility_averaged_record_for_render(
                        trainer,
                    )
            else:
                eval_record = averaged_record
            if not eval_record:
                self._show_widget_error(current_widget, "No finished runs to average.")
                return
            target_plan = trainer.get_plans()[0]  # Dummy plan for context
        elif run_data is not None:
            target_plan = run_data
            eval_record = target_plan.get_eval_record()
        else:
            try:
                # Robust parsing: Expect "Run X" or similar
                match = re.search(r"(\d+)", run_name)
                if match:
                    run_idx = int(match.group(1)) - 1
                    plans = trainer.get_plans()
                    if 0 <= run_idx < len(plans):
                        target_plan = plans[run_idx]
                        eval_record = target_plan.get_eval_record()
                    else:
                        logger.warning(
                            "Run index %d out of range (0-%d)",
                            run_idx,
                            len(plans) - 1,
                        )
                else:
                    logger.warning("Could not parse run number from: %s", run_name)

            except Exception as e:
                logger.warning("Failed to find plan for run %s: %s", run_name, e)

        if not eval_record:
            self._show_widget_error(
                current_widget,
                "Selected run has no evaluation record.",
            )
            return

        # Call update_plot on the active widget
        if current_widget and hasattr(current_widget, "update_plot"):
            current_widget.update_plot(
                target_plan,
                trainer,
                method_name,
                absolute,
                eval_record,
            )

    def update_info(self):
        """Update the Sidebar Info Panel and refresh combos."""
        if self._saliency_summary_dirty or self.last_saliency_query is None:
            self.last_saliency_query = execute_application_command(
                self,
                SaliencyCommand(),
                refresh=False,
            )
            self._saliency_summary_dirty = False

        if hasattr(self, "sidebar"):
            self.sidebar.update_info()

        # Refresh combos as new training might have finished
        self.refresh_combos()

    def update_panel(self):
        """Called when switching to this panel."""
        self.update_info()
        # Explicitly trigger update to ensure plot is shown even if signals were
        # suppressed
        self.on_update()

    def mark_refresh_dirty(self) -> None:
        """Invalidate cached ApplicationService visualization summaries."""
        self._application_summary_dirty = True
        self._saliency_summary_dirty = True

    def _application_query_blocks_display(self, result) -> bool:
        if result is None:
            return False
        if result.failed:
            return True
        diagnostics = getattr(result, "diagnostics", {}) or {}
        return (
            diagnostics.get("payload_type") == "visualization_summary"
            and diagnostics.get("available") is False
        )

    def _visualization_query_payload(self) -> dict | None:
        result = self.last_application_query
        if result is None or result.failed:
            return None
        diagnostics = getattr(result, "diagnostics", {}) or {}
        if diagnostics.get("payload_type") != "visualization_summary":
            return None
        return diagnostics

    def _refresh_application_query(
        self,
        *,
        view: str | None = None,
        include_averaged_records: bool = False,
    ) -> bool:
        """Refresh visualization readiness without eager saliency averaging."""
        payload = self._visualization_query_payload()
        if payload is not None:
            include_averaged_records = include_averaged_records or (
                "averaged_records" in payload
            )
        result = execute_application_command(
            self,
            VisualizeCommand(
                view=view,
                include_objects=True,
                include_averaged_records=include_averaged_records,
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
        view: str | None = None,
        include_averaged_records: bool = False,
        on_ready=None,
    ) -> bool:
        """Load heavy visualization payloads off the UI thread when possible."""
        payload = self._visualization_query_payload()
        if payload is not None:
            include_averaged_records = include_averaged_records or (
                "averaged_records" in payload
            )

        def _handle_result(result) -> None:
            self.last_application_query = result
            if result.failed:
                return
            if callable(on_ready):
                on_ready()

        return execute_application_command_async(
            self,
            VisualizeCommand(
                view=view,
                include_objects=True,
                include_averaged_records=include_averaged_records,
            ),
            on_result=_handle_result,
            on_error=lambda _error: None,
            refresh=False,
            busy_target=self,
        )

    def _trainers_from_application_query(self):
        payload = self._visualization_query_payload()
        if payload is None:
            return None
        return list(payload.get("trainer_objects") or [])

    def _averaged_record_from_application_query(self, trainer):
        payload = self._visualization_query_payload()
        if payload is None:
            return _MISSING
        trainer_index = self._current_trainer_index(trainer)
        records = payload.get("averaged_records") or []
        if trainer_index < 0 or trainer_index >= len(records):
            return _MISSING
        return records[trainer_index]

    def _compatibility_averaged_record_for_render(self, trainer):
        controller = self.controller
        if controller is None:
            return None
        try:
            return run_controller_compatibility_call(
                self,
                lambda: controller.get_averaged_record(trainer),
            )
        except ControllerCompatibilityUnavailableError:
            return None

    def _current_trainer_index(self, trainer) -> int:
        for index in range(1, self.plan_combo.count()):
            if self.plan_combo.itemData(index) is trainer:
                return index - 1
        return -1

    def _application_query_message(self) -> str:
        result = self.last_application_query
        if result is not None and getattr(result, "message", ""):
            return str(result.message)
        return "No visualization views are ready yet."

    def _setup_only_message(self) -> str | None:
        payload = self._visualization_query_payload()
        if payload is None:
            return None
        if payload.get("plot_views_available", True) is not False:
            return None
        views = payload.get("available_views")
        if not isinstance(views, list) or "montage setup" not in views:
            return None
        return (
            "Complete training to view saliency plots. Set Montage remains available."
        )

    def _clear_plan_controls(self) -> None:
        self.plan_combo.blockSignals(True)
        self.run_combo.blockSignals(True)
        self.plan_combo.clear()
        self.plan_combo.addItem("Select a plan")
        self.run_combo.clear()
        self.friendly_map = {}
        self.plan_combo.blockSignals(False)
        self.run_combo.blockSignals(False)

    @staticmethod
    def _show_widget_error(widget, message: str) -> bool:
        show_error = getattr(widget, "show_error", None)
        if not callable(show_error):
            return False
        show_error(message)
        return True

    @staticmethod
    def _show_widget_message(widget, message: str) -> bool:
        show_message = getattr(widget, "show_message", None)
        if callable(show_message):
            show_message(message)
            return True
        return VisualizationPanel._show_widget_error(widget, message)
