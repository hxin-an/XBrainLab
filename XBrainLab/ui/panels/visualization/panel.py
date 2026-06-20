"""Visualization panel: saliency maps, topomaps, spectrograms, and 3-D views."""

import re

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application import SaliencyCommand, VisualizeCommand
from XBrainLab.backend.application.saliency_policy import (
    baseline_saliency_params,
    is_recommended_saliency_method,
    recommended_saliency_params_for_method,
    selected_saliency_methods_from_params,
)
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
from XBrainLab.ui.refresh_coordinator import refresh_after_observer
from XBrainLab.ui.status import show_status_message
from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.styles.theme import Theme

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
        self._saliency_compute_in_progress = False
        self._saliency_compute_attempted: set[tuple[object, ...]] = set()

        # 2. Base Init
        super().__init__(parent=parent, controller=controller)

        # 3. Bridge & UI Setup
        self._setup_bridges()
        self.init_ui()

    def _setup_bridges(self):
        """Listen to TrainingController to update when training finishes."""
        if self.training_controller:
            self._create_bridge(
                self.training_controller,
                "training_stopped",
                self._on_training_stopped,
            )
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

    def _on_training_stopped(self, *args, **kwargs) -> bool:
        """Refresh after training and start configured saliency as a background job."""
        refreshed = refresh_after_observer(self, event_name="training_stopped")
        self._maybe_start_configured_saliency_compute()
        return refreshed

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
        self.ctrl_bar = QGroupBox("VISUALIZATION CONTROLS")
        self.ctrl_layout = QGridLayout(self.ctrl_bar)
        self.ctrl_layout.setContentsMargins(10, 15, 10, 10)
        self.ctrl_layout.setHorizontalSpacing(8)
        self.ctrl_layout.setVerticalSpacing(6)

        # Plan Selector
        self.plan_label = QLabel("Plan:")
        self.plan_combo = QComboBox()
        self.plan_combo.addItem("Select a plan")
        self.plan_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon,
        )
        self.plan_combo.setStyleSheet(Stylesheets.COMBO_BOX)
        self.plan_combo.currentTextChanged.connect(self.on_plan_changed)

        # Run Selector
        self.run_label = QLabel("Run:")
        self.run_combo = QComboBox()
        self.run_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon,
        )
        self.run_combo.setStyleSheet(Stylesheets.COMBO_BOX)
        self.run_combo.currentTextChanged.connect(self.on_update)

        # Method Selector
        self.method_label = QLabel("Method:")
        self.method_combo = QComboBox()
        self.method_combo.addItem("Gradient")
        self.method_combo.addItem("Gradient * Input")
        self.method_combo.addItems(supported_saliency_methods)
        self.method_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon,
        )
        self.method_combo.setStyleSheet(Stylesheets.COMBO_BOX)
        self.method_combo.currentTextChanged.connect(self.on_update)

        # Absolute Checkbox
        self.abs_check = QCheckBox("Absolute")
        self.abs_check.setToolTip("Use absolute saliency values")
        self.abs_check.setStyleSheet(Stylesheets.CHECKBOX_MUTED)
        self.abs_check.stateChanged.connect(self.on_update)
        self._controls_single_row = None
        self._apply_visualization_control_layout(single_row=False)
        left_layout.addWidget(self.ctrl_bar)

        # 2. Saliency compute entry point
        self.saliency_action_bar = self._build_saliency_action_bar()
        self.saliency_action_bar.setVisible(False)
        left_layout.addWidget(self.saliency_action_bar)

        # 3. Plots Group
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

    def _build_saliency_action_bar(self) -> QFrame:
        """Build the explicit saliency compute prompt shown for metric-only runs."""
        frame = QFrame()
        frame.setObjectName("SaliencyActionBar")
        frame.setStyleSheet(
            f"""
            QFrame#SaliencyActionBar {{
                background-color: {Theme.BACKGROUND_MID};
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                border-radius: 6px;
            }}
            QLabel#SaliencyActionTitle {{
                background-color: transparent;
                color: {Theme.TEXT_PRIMARY};
                font-weight: bold;
            }}
            QLabel#SaliencyActionDetail {{
                background-color: transparent;
                color: {Theme.TEXT_SECONDARY};
            }}
            """
        )

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        self.saliency_action_title = QLabel("Saliency not computed yet")
        self.saliency_action_title.setObjectName("SaliencyActionTitle")
        self.saliency_action_detail = QLabel(
            "Recommended profile computes Gradient + Gradient * Input."
        )
        self.saliency_action_detail.setObjectName("SaliencyActionDetail")
        self.saliency_action_detail.setWordWrap(True)
        text_layout.addWidget(self.saliency_action_title)
        text_layout.addWidget(self.saliency_action_detail)

        self.compute_saliency_btn = QPushButton("Compute Saliency")
        self.compute_saliency_btn.setMinimumWidth(140)
        self.compute_saliency_btn.setStyleSheet(
            Stylesheets.BTN_PRIMARY
            + f"""
            QPushButton:disabled {{
                background-color: {Theme.BTN_DISABLED_BG};
                color: {Theme.BTN_DISABLED_TEXT};
            }}
            """
        )
        self.compute_saliency_btn.clicked.connect(
            self._compute_saliency_from_action_bar
        )

        self.saliency_settings_btn = QPushButton("Settings")
        self.saliency_settings_btn.setMinimumWidth(86)
        self.saliency_settings_btn.setStyleSheet(Stylesheets.BTN_GHOST)
        self.saliency_settings_btn.clicked.connect(self._open_saliency_settings)

        layout.addLayout(text_layout, stretch=1)
        layout.addWidget(self.saliency_settings_btn)
        layout.addWidget(self.compute_saliency_btn)
        return frame

    def resizeEvent(self, event):  # noqa: N802
        """Switch visualization controls between compact and full-width layouts."""
        super().resizeEvent(event)
        self._refresh_control_layout_for_width()

    def _refresh_control_layout_for_width(self) -> None:
        if not hasattr(self, "ctrl_bar"):
            return
        available_width = max(self.ctrl_bar.width(), self.width() - 340)
        self._apply_visualization_control_layout(
            single_row=available_width >= 720,
        )

    def _apply_visualization_control_layout(self, single_row: bool) -> None:
        if getattr(self, "_controls_single_row", None) == single_row:
            return

        self._controls_single_row = single_row
        for column in range(9):
            self.ctrl_layout.setColumnStretch(column, 0)

        if single_row:
            self.plan_combo.setMinimumWidth(150)
            self.plan_combo.setMaximumWidth(210)
            self.run_combo.setMinimumWidth(105)
            self.run_combo.setMaximumWidth(145)
            self.method_combo.setMinimumWidth(150)
            self.method_combo.setMaximumWidth(190)

            self.ctrl_layout.addWidget(self.plan_label, 0, 0)
            self.ctrl_layout.addWidget(self.plan_combo, 0, 1)
            self.ctrl_layout.addWidget(self.run_label, 0, 2)
            self.ctrl_layout.addWidget(self.run_combo, 0, 3)
            self.ctrl_layout.addWidget(self.method_label, 0, 4)
            self.ctrl_layout.addWidget(self.method_combo, 0, 5)
            self.ctrl_layout.addWidget(self.abs_check, 0, 6)
            self.ctrl_layout.setColumnStretch(7, 1)
            return

        self.plan_combo.setMinimumWidth(150)
        self.plan_combo.setMaximumWidth(220)
        self.run_combo.setMinimumWidth(120)
        self.run_combo.setMaximumWidth(180)
        self.method_combo.setMinimumWidth(150)
        self.method_combo.setMaximumWidth(220)

        self.ctrl_layout.addWidget(self.plan_label, 0, 0)
        self.ctrl_layout.addWidget(self.plan_combo, 0, 1)
        self.ctrl_layout.addWidget(self.run_label, 0, 2)
        self.ctrl_layout.addWidget(self.run_combo, 0, 3)
        self.ctrl_layout.addWidget(self.method_label, 1, 0)
        self.ctrl_layout.addWidget(self.method_combo, 1, 1)
        self.ctrl_layout.addWidget(self.abs_check, 1, 3)
        self.ctrl_layout.setColumnStretch(4, 1)

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
        self._hide_saliency_action_bar()
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
                    self._show_widget_message(
                        current_widget,
                        "Average saliency could not start in the background. "
                        "Try again after the current operation finishes.",
                    )
                    return
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

        if self._has_service_saliency_summary() and not self._eval_record_has_saliency(
            eval_record,
            method_name,
        ):
            self._show_saliency_action_bar(method_name)
            if self._start_lazy_saliency_compute(
                current_widget,
                eval_record,
                method_name,
            ):
                return
            self._show_widget_message(
                current_widget,
                "Saliency has not been computed for this run.",
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

    def _compute_saliency_from_action_bar(self) -> None:
        """Compute saliency for the current run using a product-friendly default."""
        method_name = (
            self.method_combo.currentText() if hasattr(self, "method_combo") else ""
        ) or "Gradient"
        params = recommended_saliency_params_for_method(method_name)
        methods = params.get("methods")
        methods_key = tuple(methods) if isinstance(methods, (list, tuple, set)) else ()
        current_widget = self.tabs.currentWidget() if hasattr(self, "tabs") else None
        started = self._start_saliency_compute(
            params=params,
            method_name=method_name,
            current_widget=current_widget,
            attempt_key=(
                "manual",
                self.plan_combo.currentText() if hasattr(self, "plan_combo") else "",
                self.run_combo.currentText() if hasattr(self, "run_combo") else "",
                method_name,
                methods_key,
            ),
        )
        if not started:
            self._set_saliency_action_busy(False)
            show_status_message(self, "Saliency compute could not start.")

    def _open_saliency_settings(self) -> None:
        sidebar = getattr(self, "sidebar", None)
        set_saliency = getattr(sidebar, "set_saliency", None)
        if callable(set_saliency):
            set_saliency()

    def _show_saliency_action_bar(self, method_name: str | None = None) -> None:
        if not hasattr(self, "saliency_action_bar"):
            return
        method_name = method_name or "Gradient"
        if self._saliency_compute_in_progress:
            self.saliency_action_title.setText("Preparing saliency baseline")
            detail = "Computing Gradient + Gradient * Input in the background."
        elif is_recommended_saliency_method(method_name):
            self.saliency_action_title.setText("Preparing saliency baseline")
            detail = "XBrainLab prepares Gradient + Gradient * Input automatically."
        else:
            self.saliency_action_title.setText("Advanced saliency not computed")
            detail = f"{method_name} uses default noise settings. Adjust in Settings."
        self.saliency_action_detail.setText(detail)
        self.saliency_action_bar.setVisible(True)

    def _hide_saliency_action_bar(self) -> None:
        if not hasattr(self, "saliency_action_bar"):
            return
        if self._saliency_compute_in_progress:
            return
        self.saliency_action_bar.setVisible(False)
        self._set_saliency_action_busy(False)

    def _set_saliency_action_busy(self, busy: bool) -> None:
        if not hasattr(self, "compute_saliency_btn"):
            return
        self.compute_saliency_btn.setEnabled(not busy)
        self.compute_saliency_btn.setText(
            "Computing..." if busy else "Compute Saliency"
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
        self._saliency_compute_attempted.clear()

    def _start_lazy_saliency_compute(
        self,
        current_widget,
        eval_record,
        method_name: str,
    ) -> bool:
        """Compute saliency on demand when a finished run has metrics only."""
        params = self._configured_saliency_params()
        if is_recommended_saliency_method(method_name):
            configured_methods = selected_saliency_methods_from_params(params)
            if not params or method_name not in configured_methods:
                params = baseline_saliency_params()
        elif not params or method_name not in selected_saliency_methods_from_params(
            params
        ):
            return False
        return self._start_saliency_compute(
            params=params,
            method_name=method_name,
            current_widget=current_widget,
            attempt_key=(id(eval_record), method_name),
        )

    def _maybe_start_configured_saliency_compute(self) -> bool:
        """Start background saliency after training when finished runs exist."""
        query_result = execute_application_command(
            self,
            SaliencyCommand(),
            refresh=False,
        )
        if query_result is None or query_result.failed:
            return False
        self.last_saliency_query = query_result
        self._saliency_summary_dirty = False
        diagnostics = getattr(query_result, "diagnostics", {}) or {}
        if diagnostics.get("payload_type") != "saliency_summary":
            return False
        if diagnostics.get("saliency_available") is True:
            return False
        if int(diagnostics.get("finished_run_count") or 0) < 1:
            return False
        params = self._configured_saliency_params()
        profile = "configured"
        if not params:
            params = baseline_saliency_params()
            profile = "recommended-baseline"
        return self._start_saliency_compute(
            params=params,
            method_name=self.method_combo.currentText()
            if hasattr(self, "method_combo")
            else "Gradient",
            current_widget=self.tabs.currentWidget() if hasattr(self, "tabs") else None,
            attempt_key=("training_stopped", id(query_result), profile),
        )

    def _start_saliency_compute(
        self,
        *,
        params: dict[str, object],
        method_name: str,
        current_widget,
        attempt_key: tuple[object, ...],
    ) -> bool:
        """Run configured saliency computation in the ApplicationService worker."""
        if self._saliency_compute_in_progress:
            if current_widget is not None:
                self._show_widget_message(current_widget, "Computing saliency...")
            return True

        if attempt_key in self._saliency_compute_attempted:
            return False

        self._saliency_compute_attempted.add(attempt_key)
        self._saliency_compute_in_progress = True
        self._show_saliency_action_bar(method_name)
        self._set_saliency_action_busy(True)
        if current_widget is not None:
            self._show_widget_message(current_widget, "Computing saliency...")
        show_status_message(self, "Computing saliency...")

        started = execute_application_command_async(
            self,
            SaliencyCommand(method=method_name, params=params),
            on_result=self._on_lazy_saliency_configured,
            on_error=self._on_lazy_saliency_error,
            refresh=False,
            busy_target=self.main_window,
        )
        if not started:
            self._saliency_compute_in_progress = False
            self._set_saliency_action_busy(False)
            return False
        return True

    def _on_lazy_saliency_configured(self, result) -> None:
        self._saliency_compute_in_progress = False
        self._set_saliency_action_busy(False)
        if result.failed:
            self._saliency_summary_dirty = True
            self._saliency_compute_attempted.clear()
            show_status_message(self, f"Saliency failed: {result.message}")
            return
        show_status_message(self, "Saliency ready")
        self.mark_refresh_dirty()
        self.update_panel()

    def _on_lazy_saliency_error(self, error: tuple) -> None:
        self._saliency_compute_in_progress = False
        self._set_saliency_action_busy(False)
        self._saliency_summary_dirty = True
        self._saliency_compute_attempted.clear()
        message = error[1] if len(error) > 1 else error
        show_status_message(self, f"Saliency failed: {message}")

    @staticmethod
    def _eval_record_has_saliency(eval_record, method_name: str) -> bool:
        stores = {
            "Gradient": getattr(eval_record, "gradient", {}),
            "Gradient * Input": getattr(eval_record, "gradient_input", {}),
            "SmoothGrad": getattr(eval_record, "smoothgrad", {}),
            "SmoothGrad_Squared": getattr(eval_record, "smoothgrad_sq", {}),
            "VarGrad": getattr(eval_record, "vargrad", {}),
        }
        store = stores.get(method_name)
        if not store:
            return False
        values = store.values() if isinstance(store, dict) else store
        for value in values:
            if VisualizationPanel._has_nonempty_saliency_value(value):
                return True
        return False

    @staticmethod
    def _has_nonempty_saliency_value(value) -> bool:
        try:
            return len(value) > 0
        except TypeError:
            return False

    def _configured_saliency_params(self) -> dict[str, object]:
        diagnostics = (
            getattr(self.last_saliency_query, "diagnostics", {})
            if self.last_saliency_query is not None
            else {}
        )
        if diagnostics.get("payload_type") != "saliency_summary":
            return {}
        params = diagnostics.get("params")
        return dict(params) if isinstance(params, dict) else {}

    def _has_service_saliency_summary(self) -> bool:
        diagnostics = (
            getattr(self.last_saliency_query, "diagnostics", {})
            if self.last_saliency_query is not None
            else {}
        )
        return diagnostics.get("payload_type") == "saliency_summary"

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
