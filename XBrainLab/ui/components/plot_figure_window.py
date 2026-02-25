"""Plot figure window with plan, repeat, and saliency method selectors."""

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QComboBox, QGroupBox, QHBoxLayout

from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.visualization import supported_saliency_methods

from .single_plot_window import SinglePlotWindow


class PlotFigureWindow(SinglePlotWindow):
    """A plot window with combo-box selectors for plan, repeat, and saliency.

    Extends ``SinglePlotWindow`` with a control panel for selecting a
    training plan, its repeat, and a saliency method. A polling timer
    drives periodic plot updates while visible.

    Attributes:
        trainers: List of trainer objects to select from.
        trainer: The currently selected trainer, or ``None``.
        plot_type: The plot type enum value to invoke.
        plan_to_plot: The selected plan object, or ``None``.
        saliency_name: Optional saliency method name.
        plan_combo: QComboBox for plan selection.
        real_plan_combo: QComboBox for repeat selection.
        saliency_combo: QComboBox for saliency method selection.
    """

    def __init__(
        self,
        parent,
        trainers,
        plot_type,
        figsize=None,
        title="Plot",
        plan_name=None,
        real_plan_name=None,
        saliency_name=None,
    ):
        """Initialize the plot figure window.

        Args:
            parent: Parent widget.
            trainers: List of trainer objects available for plotting.
            plot_type: Enum value specifying the plot function to call.
            figsize: Optional tuple ``(width, height)`` in inches.
            title: Window title string.
            plan_name: Optional pre-selected plan name.
            real_plan_name: Optional pre-selected repeat name.
            saliency_name: Optional pre-selected saliency method name.
        """
        self.trainers = trainers
        self.trainer = None
        self.check_data()
        self.plot_type = plot_type
        self.plan_to_plot = None
        self.current_plot = None
        self.plot_gap = 0
        self.saliency_name = saliency_name

        self.trainer_map = {trainer.get_name(): trainer for trainer in trainers}
        self.real_plan_map = {}

        self.init_ui()

        self.drawCounter = 0
        self.update_progress = -1

        # Timer for update loop
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_loop)
        self.timer.start(100)

        if plan_name:
            self.plan_combo.setCurrentText(plan_name)
        if real_plan_name:
            self.real_plan_combo.setCurrentText(real_plan_name)
        if saliency_name:
            self.saliency_combo.setCurrentText(saliency_name)

    def check_data(self):
        """Validate that trainers data is non-empty."""
        if not isinstance(self.trainers, list) or len(self.trainers) == 0:
            # In PyQt we might want to show a message box, but init shouldn't
            # block/fail ideally
            pass

    def init_ui(self):
        """Build the selector controls for plan, repeat, and saliency method."""
        # Insert selector frame at the top
        self.selector_group = QGroupBox("Controls")
        selector_layout = QHBoxLayout(self.selector_group)

        # Plan
        self.plan_combo = QComboBox()
        self.plan_combo.addItem("Select a plan")
        self.plan_combo.addItems(list(self.trainer_map.keys()))
        self.plan_combo.currentTextChanged.connect(self.on_plan_select)
        selector_layout.addWidget(self.plan_combo)

        # Real Plan (Repeat)
        self.real_plan_combo = QComboBox()
        self.real_plan_combo.addItem("Select repeat")
        self.real_plan_combo.currentTextChanged.connect(self.on_real_plan_select)
        selector_layout.addWidget(self.real_plan_combo)

        # Saliency
        self.saliency_combo = QComboBox()
        self.saliency_combo.addItem("Select saliency method")
        self.saliency_combo.addItems(
            ["Gradient", "Gradient * Input", *supported_saliency_methods]
        )
        self.saliency_combo.currentTextChanged.connect(self.on_saliency_method_select)
        selector_layout.addWidget(self.saliency_combo)

        # Add to main layout at index 0 (top)
        self.main_layout.insertWidget(0, self.selector_group)

    def on_plan_select(self, plan_name):
        """Handle plan combo-box selection change.

        Populates the repeat combo-box with plans from the selected trainer.

        Args:
            plan_name: The selected plan name string.
        """
        self.set_selection(False)
        self.plan_to_plot = None
        self.trainer = None

        self.real_plan_combo.clear()
        self.real_plan_combo.addItem("Select repeat")

        if plan_name not in self.trainer_map:
            return

        trainer = self.trainer_map[plan_name]
        self.trainer = trainer
        self.real_plan_map = {plan.get_name(): plan for plan in trainer.get_plans()}
        self.real_plan_combo.addItems(list(self.real_plan_map.keys()))

    def on_real_plan_select(self, plan_name):
        """Handle repeat combo-box selection change.

        Args:
            plan_name: The selected repeat plan name string.
        """
        self.set_selection(False)
        self.plan_to_plot = None
        if plan_name not in self.real_plan_map:
            return
        self.plan_to_plot = self.real_plan_map[plan_name]
        # self.add_plot_command() # Scripting not fully ported yet

    def on_saliency_method_select(self, method_name):
        """Handle saliency method combo-box selection change.

        Args:
            method_name: The selected saliency method name string.
        """
        self.set_selection(False)
        if method_name == "Select saliency method":
            return
        # self.add_plot_command()
        self.recreate_fig()

    def _create_figure(self):
        """Create a Matplotlib figure using the selected plan's plot function.

        Returns:
            A Matplotlib ``Figure`` object, or ``None`` on failure.
        """
        target_func = getattr(self.plan_to_plot, self.plot_type.value)
        # Ensure figure params are ready
        params = self.get_figure_params()
        figure = target_func(**params)
        return figure

    def update_loop(self):
        """Polling loop invoked by timer to refresh the plot when visible."""
        if not self.isVisible():
            return

        counter = self.drawCounter
        max_plot_gap = 20

        if self.current_plot != self.plan_to_plot:
            self.current_plot = self.plan_to_plot
            self.active_figure()

            if self.plan_to_plot is None:
                self.empty_data_figure()
            else:
                self.plot_gap += 1
                if self.plot_gap < max_plot_gap:
                    self.current_plot = True  # Keep waiting
                else:
                    self.plot_gap = 0
                    update_progress = self.plan_to_plot.get_epoch()

                    if (
                        update_progress != self.update_progress
                        or self.plan_to_plot.is_finished()
                    ):
                        self.update_progress = update_progress
                        self.show_drawing()

                        try:
                            figure = self._create_figure()
                            if figure is None:
                                self.empty_data_figure()
                            else:
                                # Update canvas with new figure
                                # We need to replace the figure in the canvas
                                # SinglePlotWindow.set_figure handles this
                                self.set_figure(figure, self.figsize, self.dpi)
                                self.redraw()
                        except Exception as e:
                            logger.error(f"Plotting error: {e}", exc_info=True)
                            self.empty_data_figure()

                    if not self.plan_to_plot.is_finished():
                        self.current_plot = True  # Keep updating if running
                    # self.redraw() # Redraw handled above

        if counter == self.drawCounter:
            self.set_selection(allow=True)

        # Check for new plans dynamically?
        # Original code did this, maybe we skip for now or implement if needed

    def set_selection(self, allow):
        """Enable or disable the selector controls.

        Args:
            allow: If ``True``, enables selectors; otherwise disables
                and increments the draw counter.
        """
        if not allow:
            self.drawCounter += 1
            self.selector_group.setEnabled(False)
        else:
            self.selector_group.setEnabled(True)

    def recreate_fig(self, *args, current_plot=True):
        """Force a figure recreation on the next update loop iteration.

        Args:
            *args: Unused positional arguments.
            current_plot: Value to assign to ``current_plot`` to trigger
                a re-check.
        """
        self.update_progress = -1
        self.current_plot = current_plot  # Force re-check in loop
        self.plot_gap = 100  # Force immediate update
