"""Visualization panel: saliency maps, topomaps, spectrograms, and 3-D views."""

import re

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.visualization import supported_saliency_methods
from XBrainLab.ui.core.base_panel import BasePanel
from XBrainLab.ui.core.observer_bridge import QtObserverBridge
from XBrainLab.ui.styles.stylesheets import Stylesheets

from .control_sidebar import ControlSidebar
from .saliency_views.map_view import SaliencyMapWidget
from .saliency_views.plot_3d_view import Saliency3DPlotWidget
from .saliency_views.spectrogram_view import SaliencySpectrogramWidget
from .saliency_views.topomap_view import SaliencyTopographicMapWidget


class VisualizationPanel(BasePanel):
    """
    Panel for visualizing data and model explanations with unified controls.
    Manages multiple view tabs (Map, Topomap, Spectrogram, 3D) and coordinates updates.
    """

    def __init__(self, controller=None, training_controller=None, parent=None):
        """Initialize the visualization panel.

        Args:
            controller: Optional ``VisualizationController``. Resolved from
                the parent study if not provided.
            training_controller: Optional ``TrainingController`` for
                subscribing to training-stopped events.
            parent: Parent widget (typically the main window).
        """
        # 1. Controller Resolution
        if controller is None and parent and hasattr(parent, "study"):
            controller = parent.study.get_controller("visualization")

        # Store injected training controller
        self.training_controller = training_controller
        self.friendly_map = {}

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
            # When training stops, update the plan lists
            self.training_bridge = QtObserverBridge(
                training_ctrl, "training_stopped", self
            )
            self.training_bridge.connect_to(self.update_panel)

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
        ctrl_layout = QHBoxLayout(ctrl_bar)
        ctrl_layout.setContentsMargins(10, 15, 10, 10)

        # Plan Selector
        ctrl_layout.addWidget(QLabel("Plan:"))
        self.plan_combo = QComboBox()
        self.plan_combo.addItem("Select a plan")
        self.plan_combo.setStyleSheet(Stylesheets.COMBO_BOX)
        self.plan_combo.currentTextChanged.connect(self.on_plan_changed)
        ctrl_layout.addWidget(self.plan_combo)

        ctrl_layout.addSpacing(15)

        # Run Selector
        ctrl_layout.addWidget(QLabel("Run:"))
        self.run_combo = QComboBox()
        self.run_combo.setStyleSheet(Stylesheets.COMBO_BOX)
        self.run_combo.currentTextChanged.connect(self.on_update)
        ctrl_layout.addWidget(self.run_combo)

        ctrl_layout.addSpacing(15)

        # Method Selector
        ctrl_layout.addWidget(QLabel("Method:"))
        self.method_combo = QComboBox()
        self.method_combo.addItem("Gradient")
        self.method_combo.addItem("Gradient * Input")
        self.method_combo.addItems(supported_saliency_methods)
        self.method_combo.setStyleSheet(Stylesheets.COMBO_BOX)
        self.method_combo.currentTextChanged.connect(self.on_update)
        ctrl_layout.addWidget(self.method_combo)

        ctrl_layout.addSpacing(15)

        # Absolute Checkbox
        self.abs_check = QCheckBox("Absolute Value")
        self.abs_check.setStyleSheet(Stylesheets.CHECKBOX_MUTED)
        self.abs_check.stateChanged.connect(self.on_update)
        ctrl_layout.addWidget(self.abs_check)

        ctrl_layout.addStretch()
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

        # Set initial state for tabs (visibility of buttons etc)
        self.on_tab_changed(self.tabs.currentIndex())

        # Initial refresh of combos
        self.refresh_combos()

    def get_trainers(self):
        """Return the list of available trainers from the controller.

        Returns:
            list: Trainer instances available for visualization.
        """
        return self.controller.get_trainers()

    def refresh_combos(self):
        """Refresh Plan ComboBox based on current trainers."""
        trainers = self.get_trainers()
        if not trainers:
            return

        self.plan_combo.blockSignals(True)
        self.plan_combo.clear()
        self.plan_combo.addItem("Select a plan")

        self.friendly_map = {}
        for i, trainer in enumerate(trainers):
            model_name = trainer.model_holder.target_model.__name__
            friendly_name = f"Fold {i + 1} ({model_name})"
            self.friendly_map[friendly_name] = trainer
            self.plan_combo.addItem(friendly_name)

        self.plan_combo.blockSignals(False)

        # If items exist, select first real plan
        if self.plan_combo.count() > 1:
            self.plan_combo.setCurrentIndex(1)
            # Explicitly call on_plan_changed to ensure run_combo is populated
            self.on_plan_changed(self.plan_combo.currentText())

    def on_plan_changed(self, text):
        """Update Run combo when Plan changes."""
        self.run_combo.blockSignals(True)
        self.run_combo.clear()

        if text in self.friendly_map:
            trainer = self.friendly_map[text]
            # Add runs
            for i in range(trainer.option.repeat_num):
                self.run_combo.addItem(f"Run {i + 1}")
            # Add Average
            self.run_combo.addItem("Average")

        self.run_combo.blockSignals(False)

        if self.run_combo.count() > 0:
            self.run_combo.setCurrentIndex(0)  # Select first run by default
        else:
            self.on_update()  # Trigger update to clear if empty

    def on_tab_changed(self, index):
        """Handle tab switch."""
        # Montage button is now always visible as per user request
        # self.btn_montage.setVisible(True) # It's visible by default

        self.on_update()

    def on_update(self):
        """Gather settings and call update_plot on current tab."""
        plan_name = self.plan_combo.currentText()
        run_name = self.run_combo.currentText()
        method_name = self.method_combo.currentText()
        absolute = self.abs_check.isChecked()

        current_widget = self.tabs.currentWidget()

        if plan_name not in self.friendly_map or not run_name:
            # Clear or show placeholder
            if current_widget and hasattr(current_widget, "show_error"):
                current_widget.show_error("Please select a Plan and Run.")
            return

        trainer = self.friendly_map[plan_name]

        # Resolve Plan and EvalRecord
        target_plan = None
        eval_record = None

        if run_name == "Average":
            eval_record = self.controller.get_averaged_record(trainer)
            if not eval_record:
                if current_widget and hasattr(current_widget, "show_error"):
                    current_widget.show_error("No finished runs to average.")
                return
            target_plan = trainer.get_plans()[0]  # Dummy plan for context
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
                            f"Run index {run_idx} out of range (0-{len(plans) - 1})"
                        )
                else:
                    logger.warning("Could not parse run number from: %s", run_name)

            except Exception as e:
                logger.warning("Failed to find plan for run %s: %s", run_name, e)

        if not eval_record:
            if current_widget and hasattr(current_widget, "show_error"):
                current_widget.show_error("Selected run has no evaluation record.")
            return

        # Call update_plot on the active widget
        if current_widget and hasattr(current_widget, "update_plot"):
            current_widget.update_plot(
                target_plan, trainer, method_name, absolute, eval_record
            )

            # Force UI update to ensure plot appears immediately
            if current_widget:
                current_widget.repaint()

    def update_info(self):
        """Update the Sidebar Info Panel and refresh combos."""
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
