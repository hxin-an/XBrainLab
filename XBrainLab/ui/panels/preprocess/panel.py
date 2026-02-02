from typing import TYPE_CHECKING

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.ui.core.base_panel import BasePanel
from XBrainLab.ui.core.observer_bridge import QtObserverBridge
from XBrainLab.ui.panels.preprocess.sidebar import PreprocessSidebar
from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.styles.theme import Theme

if TYPE_CHECKING:
    pass


class PreprocessPanel(BasePanel):
    """
    Panel for signal preprocessing.
    Features: Plotting (Time/Freq), Operations (Filter, Resample, etc.), History.
    """

    def __init__(self, controller=None, dataset_controller=None, parent=None):
        # 1. Controller Resolution (Legacy/Test support)
        if controller is None and parent and hasattr(parent, "study"):
            controller = parent.study.get_controller("preprocess")
        if dataset_controller is None and parent and hasattr(parent, "study"):
            dataset_controller = parent.study.get_controller("dataset")

        # 2. Base Init
        super().__init__(parent=parent, controller=controller)

        self.dataset_controller = dataset_controller

        from .plotters.preprocess_plotter import PreprocessPlotter  # noqa: PLC0415

        self.plotter = PreprocessPlotter(self)

        # 3. Setup
        self.bridge = None
        self.data_bridge = None
        self.import_bridge = None

        self._setup_bridges()
        self.init_ui()

    def _setup_bridges(self):
        if self.controller:
            # Connect to Preprocess events
            self.bridge = QtObserverBridge(self.controller, "preprocess_changed", self)
            self.bridge.connect_to(self.update_panel)

            # Connect to Dataset events (for Info Panel and Button states)
            if self.dataset_controller:
                self.data_bridge = QtObserverBridge(
                    self.dataset_controller, "data_changed", self
                )
                self.data_bridge.connect_to(self.update_panel)

                # Also listen to import finished which might trigger data changes
                self.import_bridge = QtObserverBridge(
                    self.dataset_controller, "import_finished", self
                )
                self.import_bridge.connect_to(self.update_panel)

        assert self.controller is not None, "PreprocessController not initialized"  # noqa: S101

        # QTimer for plot debouncing (valid use - prevents rapid re-plotting)
        self.plot_timer = QTimer()
        self.plot_timer.setSingleShot(True)
        self.plot_timer.timeout.connect(self.plot_sample_data)

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Left Side: Plot & Preview ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(0)

        # Plot Group
        plot_group = QGroupBox("SIGNAL PREVIEW")
        plot_layout = QVBoxLayout()
        plot_layout.setContentsMargins(10, 20, 10, 10)

        # Tabs for Time/Freq
        self.plot_tabs = QTabWidget()

        # Tab 1: Time Domain
        self.tab_time = QWidget()
        time_layout = QVBoxLayout(self.tab_time)
        self.fig_time = Figure(figsize=(5, 3), dpi=100)
        self.canvas_time = FigureCanvas(self.fig_time)
        self.ax_time = self.fig_time.add_subplot(111)

        # Apply Theme
        Theme.apply_matplotlib_dark_theme(self.fig_time, ax=self.ax_time)

        # Add Title and Labels with Units
        self.ax_time.set_title("Time Domain Signal")
        self.ax_time.set_xlabel("Time (s)")
        self.ax_time.set_ylabel("Amplitude (uV)")

        self.fig_time.tight_layout()
        time_layout.addWidget(self.canvas_time)
        self.plot_tabs.addTab(self.tab_time, "Time Domain")

        # Tab 2: Frequency Domain (PSD)
        self.tab_freq = QWidget()
        freq_layout = QVBoxLayout(self.tab_freq)
        self.fig_freq = Figure(figsize=(5, 3), dpi=100)
        self.canvas_freq = FigureCanvas(self.fig_freq)
        self.ax_freq = self.fig_freq.add_subplot(111)

        # Apply Theme
        Theme.apply_matplotlib_dark_theme(self.fig_freq, ax=self.ax_freq)

        # Add Title and Labels with Units
        self.ax_freq.set_title("Power Spectral Density")
        self.ax_freq.set_xlabel("Frequency (Hz)")
        self.ax_freq.set_ylabel("Power (uV²/Hz)")

        self.fig_freq.tight_layout()
        freq_layout.addWidget(self.canvas_freq)
        self.plot_tabs.addTab(self.tab_freq, "Frequency (PSD)")

        plot_layout.addWidget(self.plot_tabs)

        # Controls
        ctrl_layout = QHBoxLayout()
        ctrl_layout.addWidget(QLabel("Channel:"))
        self.chan_combo = QComboBox()
        self.chan_combo.setMinimumWidth(100)
        self.chan_combo.setStyleSheet(Stylesheets.COMBO_BOX)
        self.chan_combo.currentIndexChanged.connect(self.update_plot_only)
        ctrl_layout.addWidget(self.chan_combo)

        ctrl_layout.addSpacing(20)
        ctrl_layout.addWidget(QLabel("Y-Scale (uV):"))
        self.yscale_spin = QDoubleSpinBox()
        self.yscale_spin.setRange(0, 5000)
        self.yscale_spin.setValue(0)  # 0 = Auto
        self.yscale_spin.setSpecialValueText("Auto")
        self.yscale_spin.setSingleStep(10)
        self.yscale_spin.valueChanged.connect(self.update_plot_only)
        ctrl_layout.addWidget(self.yscale_spin)

        ctrl_layout.addStretch()
        ctrl_layout.addStretch()
        plot_layout.addLayout(ctrl_layout)

        # Time Navigation
        time_nav_layout = QHBoxLayout()
        time_nav_layout.addWidget(QLabel("Time / Epoch:"))

        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setRange(0, 100)  # Placeholder
        self.time_slider.valueChanged.connect(self.on_time_slider_changed)
        time_nav_layout.addWidget(self.time_slider)

        self.time_spin = QDoubleSpinBox()
        self.time_spin.setRange(0, 10000)
        self.time_spin.setSingleStep(1.0)
        self.time_spin.valueChanged.connect(self.on_time_spin_changed)
        time_nav_layout.addWidget(self.time_spin)

        plot_layout.addLayout(time_nav_layout)
        plot_group.setLayout(plot_layout)

        left_layout.addWidget(plot_group, stretch=2)  # Give more space to plots

        # History Group (Bottom)
        from PyQt6.QtWidgets import QListWidget  # noqa: PLC0415 Ensure import

        history_group = QGroupBox("PREPROCESSING HISTORY")
        history_layout = QVBoxLayout(history_group)
        history_layout.setContentsMargins(10, 20, 10, 10)

        self.history_list = QListWidget()
        history_layout.addWidget(self.history_list)

        left_layout.addWidget(history_group, stretch=1)

        # --- Right Side: Sidebar ---
        self.sidebar = PreprocessSidebar(self, self)

        main_layout.addWidget(left_widget, stretch=1)
        main_layout.addWidget(self.sidebar, stretch=0)

    def on_time_slider_changed(self, value):
        self.time_spin.blockSignals(True)
        self.time_spin.setValue(
            value / 10.0
        )  # Slider is int, spin is float (0.1s step)
        self.time_spin.blockSignals(False)
        self.plot_timer.start(50)  # Debounce: Wait 50ms before plotting

    def on_time_spin_changed(self, value):
        self.time_slider.blockSignals(True)
        self.time_slider.setValue(int(value * 10))
        self.time_slider.blockSignals(False)
        self.plot_timer.start(50)  # Debounce

    def update_panel(self, *args):
        if hasattr(self, "sidebar"):
            self.sidebar.update_sidebar()

        # Update History List
        if hasattr(self, "history_list"):
            self.history_list.clear()
            data_list = self.controller.get_preprocessed_data_list()
            is_epoched = False

            if data_list:
                first_data = data_list[0]
                is_epoched = not first_data.is_raw()

                # History Items
                history = first_data.get_preprocess_history()
                if history:
                    for step in history:
                        self.history_list.addItem(str(step))
                else:
                    self.history_list.addItem("No preprocessing applied.")

                if is_epoched:
                    self.history_list.addItem("Preprocessing Locked (Epoched).")
            else:
                self.history_list.addItem("No data loaded.")

        # Update Plots (Panel Logic)
        data_list = self.controller.get_preprocessed_data_list()

        is_epoched = False
        if data_list:
            first_data = data_list[0]
            is_epoched = not first_data.is_raw()

            if is_epoched:
                # Clear plots logic
                self.ax_time.clear()
                self.ax_time.text(
                    0.5,
                    0.5,
                    "Data is Epoched\nPreprocessing Locked",
                    ha="center",
                    va="center",
                    color=Theme.TEXT_MUTED,
                )
                self.canvas_time.draw()
                self.ax_freq.clear()
                self.ax_freq.text(
                    0.5,
                    0.5,
                    "Data is Epoched",
                    ha="center",
                    va="center",
                    color=Theme.TEXT_MUTED,
                )
                self.canvas_freq.draw()
                return

            # Update channel list
            ch_names = first_data.get_mne().ch_names
            self.chan_combo.blockSignals(True)
            self.chan_combo.clear()
            self.chan_combo.addItems(ch_names)
            self.chan_combo.blockSignals(False)

            # Update time range
            duration = (
                first_data.get_epochs_length()
                if not first_data.is_raw()
                else (first_data.get_mne().times[-1])
            )
            self.time_spin.setRange(0, duration)
            self.time_slider.setRange(0, int(duration * 10))

            self.plot_sample_data()
        else:
            self.ax_time.clear()
            self.ax_time.text(
                0.5, 0.5, "No Data", ha="center", va="center", color=Theme.TEXT_MUTED
            )
            self.canvas_time.draw()
            self.ax_freq.clear()
            self.ax_freq.text(
                0.5, 0.5, "No Data", ha="center", va="center", color=Theme.TEXT_MUTED
            )
            self.canvas_freq.draw()

    def update_plot_only(self):
        self.plot_sample_data()

    def plot_sample_data(self):
        self.plotter.plot_sample_data()
