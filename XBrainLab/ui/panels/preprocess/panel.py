from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from XBrainLab.ui.core.base_panel import BasePanel
from XBrainLab.ui.core.observer_bridge import QtObserverBridge
from XBrainLab.ui.panels.preprocess.history_widget import HistoryWidget
from XBrainLab.ui.panels.preprocess.plotters.preprocess_plotter import PreprocessPlotter
from XBrainLab.ui.panels.preprocess.preview_widget import PreviewWidget
from XBrainLab.ui.panels.preprocess.sidebar import PreprocessSidebar

if TYPE_CHECKING:
    pass


class PreprocessPanel(BasePanel):
    """
    Panel for signal preprocessing.
    Features: Plotting (Time/Freq), Operations (Filter, Resample, etc.), History.
    Refactored to compose PreviewWidget, HistoryWidget, and Sidebar.
    Connects `PreprocessController` and `DatasetController`.
    """

    def __init__(self, controller=None, dataset_controller=None, parent=None):
        # 1. Controller Resolution
        if controller is None and parent and hasattr(parent, "study"):
            controller = parent.study.get_controller("preprocess")
        if dataset_controller is None and parent and hasattr(parent, "study"):
            dataset_controller = parent.study.get_controller("dataset")

        # 2. Base Init
        super().__init__(parent=parent, controller=controller)
        self.dataset_controller = dataset_controller

        # 3. Setup Components
        self.preview_widget = PreviewWidget(self)
        self.history_widget = HistoryWidget(self)
        self.sidebar = PreprocessSidebar(self, self)

        # 4. Setup Plotter
        # Note: Plotter now takes the widget and controller directly
        self.plotter = PreprocessPlotter(self.preview_widget, self.controller)

        # 5. Connect Component Signals
        self.preview_widget.request_plot_update.connect(self.plotter.plot_sample_data)

        # 6. Setup Bridges & UI
        self._setup_bridges()
        self.init_ui()

    def _setup_bridges(self):
        if self.controller:
            self.bridge = QtObserverBridge(self.controller, "preprocess_changed", self)
            self.bridge.connect_to(self.update_panel)

            if self.dataset_controller:
                self.data_bridge = QtObserverBridge(
                    self.dataset_controller, "data_changed", self
                )
                self.data_bridge.connect_to(self.update_panel)

                self.import_bridge = QtObserverBridge(
                    self.dataset_controller, "import_finished", self
                )
                self.import_bridge.connect_to(self.update_panel)

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Left Side: Preview & History ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(10)

        left_layout.addWidget(self.preview_widget, stretch=2)
        left_layout.addWidget(self.history_widget, stretch=1)

        # --- Right Side: Sidebar ---
        main_layout.addWidget(left_widget, stretch=1)
        main_layout.addWidget(self.sidebar, stretch=0)

    def update_panel(self, *args):
        # Update Sidebar
        if hasattr(self, "sidebar"):
            self.sidebar.update_sidebar()

        # Update History
        data_list = self.controller.get_preprocessed_data_list()
        is_epoched = False
        if data_list:
            first_data = data_list[0]
            is_epoched = not first_data.is_raw()
            self.history_widget.update_history(
                first_data.get_preprocess_history(), is_epoched
            )
        else:
            self.history_widget.show_no_data()

        # Update Plots (Delegated to Plotter/Widget)
        if data_list:
            first_data = data_list[0]
            if is_epoched:
                self.preview_widget.show_locked_message(
                    "Data is Epoched - Preprocessing Locked"
                )
                return

            # Update channel options
            ch_names = first_data.get_mne().ch_names

            # Use blockSignals to avoid triggering redraw during population
            self.preview_widget.chan_combo.blockSignals(True)
            current_idx = self.preview_widget.chan_combo.currentIndex()
            self.preview_widget.chan_combo.clear()
            self.preview_widget.chan_combo.addItems(ch_names)
            # Restore index if valid (e.g. channel name mapping logic or keep index)
            if 0 <= current_idx < len(ch_names):
                self.preview_widget.chan_combo.setCurrentIndex(current_idx)
            self.preview_widget.chan_combo.blockSignals(False)

            # Update time range
            duration = (
                first_data.get_epochs_length()
                if not first_data.is_raw()
                else (first_data.get_mne().times[-1])
            )
            self.preview_widget.time_spin.setRange(0, duration)
            self.preview_widget.time_slider.setRange(0, int(duration * 10))

            self.plotter.plot_sample_data()
        else:
            self.preview_widget.reset_view()

    def update_plot_only(self):
        self.plotter.plot_sample_data()
