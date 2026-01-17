from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.controller.visualization_controller import (
    VisualizationController,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.visualization import supported_saliency_methods
from XBrainLab.ui.dashboard_panel.info import AggregateInfoPanel

from .export_saliency import ExportSaliencyWindow
from .montage_picker import PickMontageWindow
from .saliency_3Dplot import Saliency3DPlotWidget
from .saliency_map import SaliencyMapWidget
from .saliency_setting import SetSaliencyWindow
from .saliency_spectrogram import SaliencySpectrogramWidget
from .saliency_topomap import SaliencyTopographicMapWidget


class VisualizationPanel(QWidget):
    """
    Panel for visualizing data and model explanations with unified controls.
    """

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        # self.study = main_window.study # Decoupled
        self.controller = VisualizationController(main_window.study)
        self.trainer_map = {}
        self.friendly_map = {}

        self.init_ui()

    def init_ui(self):
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
        self.plan_combo.setStyleSheet(self.get_combo_style())
        self.plan_combo.currentTextChanged.connect(self.on_plan_changed)
        ctrl_layout.addWidget(self.plan_combo)

        ctrl_layout.addSpacing(15)

        # Run Selector
        ctrl_layout.addWidget(QLabel("Run:"))
        self.run_combo = QComboBox()
        self.run_combo.setStyleSheet(self.get_combo_style())
        self.run_combo.currentTextChanged.connect(self.on_update)
        ctrl_layout.addWidget(self.run_combo)

        ctrl_layout.addSpacing(15)

        # Method Selector
        ctrl_layout.addWidget(QLabel("Method:"))
        self.method_combo = QComboBox()
        self.method_combo.addItem("Gradient")
        self.method_combo.addItem("Gradient * Input")
        self.method_combo.addItems(supported_saliency_methods)
        self.method_combo.setStyleSheet(self.get_combo_style())
        self.method_combo.currentTextChanged.connect(self.on_update)
        ctrl_layout.addWidget(self.method_combo)

        ctrl_layout.addSpacing(15)

        # Absolute Checkbox
        self.abs_check = QCheckBox("Absolute Value")
        self.abs_check.setStyleSheet("color: #cccccc;")
        self.abs_check.stateChanged.connect(self.on_update)
        ctrl_layout.addWidget(self.abs_check)

        ctrl_layout.addStretch()
        left_layout.addWidget(ctrl_bar)

        # 2. Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabWidget::pane { border: 0; }")
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

        left_layout.addWidget(self.tabs)
        main_layout.addWidget(left_widget, stretch=1)

        # --- Right Side: Sidebar ---
        right_panel = QWidget()
        right_panel.setFixedWidth(260)
        right_panel.setObjectName("RightPanel")
        right_panel.setStyleSheet(self.get_sidebar_style())

        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 20, 10, 20)

        # 1. Aggregate Information
        self.info_panel = AggregateInfoPanel(self.main_window)
        right_layout.addWidget(self.info_panel, stretch=1)

        self.add_separator(right_layout)

        # Group 1: Configuration
        config_group = QGroupBox("CONFIGURATION")
        config_layout = QVBoxLayout(config_group)
        config_layout.setContentsMargins(0, 10, 0, 0)

        self.btn_montage = QPushButton("Set Montage")
        self.btn_montage.clicked.connect(self.set_montage)
        config_layout.addWidget(self.btn_montage)

        self.btn_saliency = QPushButton("Saliency Settings")
        self.btn_saliency.clicked.connect(self.set_saliency)
        config_layout.addWidget(self.btn_saliency)

        right_layout.addWidget(config_group)
        right_layout.addSpacing(20)

        # Group 2: Operations
        ops_group = QGroupBox("OPERATIONS")
        ops_layout = QVBoxLayout(ops_group)
        ops_layout.setContentsMargins(0, 10, 0, 0)

        self.btn_export = QPushButton("Export Saliency")
        self.btn_export.clicked.connect(self.export_saliency)
        ops_layout.addWidget(self.btn_export)

        # Removed Model Summary and Refresh Data as requested

        right_layout.addWidget(ops_group)
        right_layout.addStretch()

        main_layout.addWidget(right_panel, stretch=0)

        # Connect tab signal now that everything is initialized
        self.tabs.currentChanged.connect(self.on_tab_changed)

        # Set initial state for tabs (visibility of buttons etc)
        self.on_tab_changed(self.tabs.currentIndex())

        # Initial refresh of combos
        self.refresh_combos()

    def get_combo_style(self):
        return """
            QComboBox {
                background-color: #3e3e42;
                color: #cccccc;
                border: 1px solid #555;
                padding: 5px;
                min-width: 120px;
            }
            QComboBox::drop-down {
                border: 0px;
            }
        """

    def get_sidebar_style(self):
        return """
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
                font-weight: normal;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #4e4e52;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #007acc;
            }
        """

    def add_separator(self, layout):
        layout.addSpacing(10)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #3e3e42; border: none;")
        line.setFixedHeight(1)
        layout.addWidget(line)
        layout.addSpacing(10)

    def get_trainers(self):
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

    def refresh_data(self):
        """Called by MainWindow when switching to this panel."""
        self.refresh_combos()

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
            if hasattr(current_widget, "show_error"):
                current_widget.show_error("Please select a Plan and Run.")
            return

        trainer = self.friendly_map[plan_name]

        # Resolve Plan and EvalRecord
        target_plan = None
        eval_record = None

        if run_name == "Average":
            eval_record = self.controller.get_averaged_record(trainer)
            if not eval_record:
                if hasattr(current_widget, "show_error"):
                    current_widget.show_error("No finished runs to average.")
                return
            target_plan = trainer.get_plans()[0]  # Dummy plan for context
        else:
            try:
                run_idx = int(run_name.split(" ")[1]) - 1
                plans = trainer.get_plans()
                if 0 <= run_idx < len(plans):
                    target_plan = plans[run_idx]
                    eval_record = target_plan.get_eval_record()
            except Exception as e:
                logger.warning(f"Failed to find plan for run {run_name}: {e}")

        if not eval_record:
            if hasattr(current_widget, "show_error"):
                current_widget.show_error("Selected run has no evaluation record.")
            return

        # Call update_plot on the active widget
        if hasattr(current_widget, "update_plot"):
            current_widget.update_plot(
                target_plan, trainer, method_name, absolute, eval_record
            )

            # Force UI update to ensure plot appears immediately
            current_widget.repaint()

            QApplication.processEvents()

    def set_montage(self):
        if not self.controller.has_epoch_data():
            QMessageBox.warning(self, "Warning", "No epoch data available.")
            return
        win = PickMontageWindow(self, self.controller.get_channel_names())
        if win.exec():
            chs, positions = win.get_result()
            if chs is not None and positions is not None:
                self.controller.set_montage(chs, positions)
                QMessageBox.information(self, "Success", "Montage set")
                # Refresh current view if it depends on montage
                self.on_update()

    def set_saliency(self):
        win = SetSaliencyWindow(self, self.controller.get_saliency_params())
        if win.exec():
            params = win.get_result()
            if params:
                self.controller.set_saliency_params(params)
                QMessageBox.information(self, "Success", "Saliency parameters set")
                self.on_update()

    def export_saliency(self):
        trainers = self.get_trainers()
        if not trainers:
            QMessageBox.warning(self, "Warning", "No training results available.")
            return
        win = ExportSaliencyWindow(self, trainers)
        win.exec()

    def update_info(self):
        """Update the Aggregate Info Panel and refresh combos if needed."""
        if hasattr(self, "info_panel"):
            self.info_panel.update_info()
        # Also refresh combos as new training might have finished
        self.refresh_combos()

    def update_panel(self):
        """Called when switching to this panel."""
        self.update_info()
        # Explicitly trigger update to ensure plot is shown even if signals were
        # suppressed
        self.on_update()
