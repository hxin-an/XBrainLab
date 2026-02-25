import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.visualization import VisualizerType
from XBrainLab.ui.styles.theme import Theme

from .base_saliency_view import BaseSaliencyView


class SaliencyMapWidget(BaseSaliencyView):
    """
    Widget for visualizing 2D Saliency Maps.
    Uses Matplotlib backend.
    """

    def init_ui(self):
        super().init_ui()
        # Add initial text to the default canvas
        self.ax = self.fig.add_subplot(111)
        Theme.apply_matplotlib_dark_theme(self.fig, ax=self.ax)
        self.ax.text(
            0.5,
            0.5,
            "Select a plan and method to visualize",
            color=Theme.TEXT_MUTED,
            ha="center",
            va="center",
        )
        self.ax.axis("off")

    def update_plot(self, plan, trainer, method, absolute, eval_record):
        # 2. Get Data (Validation before try block to avoid TRY301)
        if eval_record is None:
            eval_record = plan.get_eval_record()

        if not eval_record:
            self.show_error("No evaluation record found.")
            return

        try:
            # 1. Clear State
            self.clear_plot()

            epoch_data = trainer.get_dataset().get_epoch_data()

            # 3. Visualize
            visualizer = VisualizerType.SaliencyMap.value(eval_record, epoch_data)
            new_fig = visualizer.get_plt(method=method, absolute=absolute)

            if new_fig:
                # Replace Figure
                self.main_layout.removeWidget(self.canvas)
                self.canvas.close()
                if self.fig is not None:
                    plt.close(self.fig)

                self.fig = new_fig
                Theme.apply_matplotlib_dark_theme(self.fig)

                self.canvas = FigureCanvas(self.fig)
                # Insert at top (index 0), error label is at index 1
                self.main_layout.insertWidget(0, self.canvas)
            else:
                self.show_error("No Data Available")

        except Exception as e:
            logger.error(f"Error plotting saliency map: {e}", exc_info=True)
            self.show_error(str(e))
