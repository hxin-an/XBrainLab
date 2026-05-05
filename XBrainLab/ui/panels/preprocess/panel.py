"""Preprocessing panel for signal filtering, resampling, and epoching."""

from typing import Any

from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from XBrainLab.backend.application import QueryStateCommand
from XBrainLab.ui.application_capabilities import execute_application_command
from XBrainLab.ui.core.base_panel import BasePanel
from XBrainLab.ui.panels.preprocess.history_widget import HistoryWidget
from XBrainLab.ui.panels.preprocess.plotters.preprocess_plotter import PreprocessPlotter
from XBrainLab.ui.panels.preprocess.preview_widget import PreviewWidget
from XBrainLab.ui.panels.preprocess.sidebar import PreprocessSidebar


class PreprocessPanel(BasePanel):
    """Panel for signal preprocessing.
    Features: Plotting (Time/Freq), Operations (Filter, Resample, etc.), History.
    Refactored to compose PreviewWidget, HistoryWidget, and Sidebar.
    Connects `PreprocessController` and `DatasetController`.
    """

    def __init__(self, controller=None, dataset_controller=None, parent=None):
        """Initialize the preprocessing panel.

        Args:
            controller: Optional ``PreprocessController``. Resolved from
                the parent study if not provided.
            dataset_controller: Optional ``DatasetController`` for
                data-change event subscription.
            parent: Parent widget (typically the main window).

        """
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
        self.preview_widget.request_plot_update.connect(self.update_plot_only)

        # 6. Setup Bridges & UI
        self._setup_bridges()
        self.init_ui()

    def _setup_bridges(self):
        """Register Qt observer bridges for preprocess and dataset events."""
        if self.controller:
            self._create_refresh_bridge(self.controller, "preprocess_changed")

            if self.dataset_controller:
                self._create_refresh_bridge(self.dataset_controller, "data_changed")

    def init_ui(self):
        """Build the panel layout with preview, history, and sidebar widgets."""
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
        """Refresh the sidebar, history, and preview plots from controller state."""
        # Update Sidebar
        if hasattr(self, "sidebar"):
            self.sidebar.update_sidebar()

        # Update History
        queried_lists = self._query_data_lists_for_render()
        original_data_list: list[Any] = []
        controller = self.controller
        if controller is None:
            data_list = []
        elif queried_lists is None:
            data_list = controller.get_preprocessed_data_list()
            study = getattr(controller, "study", None)
            if study is not None:
                original_data_list = list(getattr(study, "loaded_data_list", []))
        else:
            data_list, original_data_list = queried_lists
        is_epoched = False
        if data_list:
            first_data = data_list[0]
            is_epoched = not first_data.is_raw()
            self.history_widget.update_history(
                first_data.get_preprocess_history(),
                is_epoched,
            )
        else:
            self.history_widget.show_no_data()

        # Update Plots (Delegated to Plotter/Widget)
        if data_list:
            first_data = data_list[0]
            if is_epoched:
                self.preview_widget.show_locked_message(
                    "Data is Epoched - Preprocessing Locked",
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

            self.plotter.plot_sample_data(
                data_list=data_list,
                original_data_list=original_data_list,
            )
        else:
            self.preview_widget.reset_view()

    def update_plot_only(self):
        """Trigger a plot refresh without updating the sidebar or history."""
        queried_lists = self._query_data_lists_for_render()
        if queried_lists is None:
            self.plotter.plot_sample_data()
            return
        data_list, original_data_list = queried_lists
        self.plotter.plot_sample_data(
            data_list=data_list,
            original_data_list=original_data_list,
        )

    def _query_data_lists_for_render(self) -> tuple[list[Any], list[Any]] | None:
        result = execute_application_command(
            self,
            QueryStateCommand(query="data_lists", include_objects=True),
            refresh=False,
        )
        if result is None:
            return None
        if result.failed:
            return [], []
        diagnostics = result.diagnostics
        preprocessed = diagnostics.get("preprocessed_data_list")
        loaded = diagnostics.get("loaded_data_list")
        return (
            list(preprocessed) if isinstance(preprocessed, list) else [],
            list(loaded) if isinstance(loaded, list) else [],
        )
