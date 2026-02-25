import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.visualization import VisualizerType
from XBrainLab.ui.styles.theme import Theme

from .base_saliency_view import BaseSaliencyView


class SaliencySpectrogramWidget(BaseSaliencyView):
    """
    Widget for visualizing Saliency Spectrograms.
    Useful for time-frequency analysis of importance.
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
        if eval_record is None:
            eval_record = plan.get_eval_record()

        if not eval_record:
            self.show_error("No evaluation record found.")
            return

        try:
            self.clear_plot()
            epoch_data = trainer.get_dataset().get_epoch_data()

            # Visualizer
            visualizer = VisualizerType.SaliencySpectrogramMap.value(
                eval_record, epoch_data
            )
            # Spectrogram ignores 'absolute' param usually
            new_fig = visualizer.get_plt(method=method)

            if new_fig:
                # Replace Figure
                self.main_layout.removeWidget(self.canvas)
                self.canvas.close()
                if self.fig is not None:
                    plt.close(self.fig)

                self.fig = new_fig
                Theme.apply_matplotlib_dark_theme(self.fig)

                self.canvas = FigureCanvas(self.fig)
                self.main_layout.insertWidget(0, self.canvas)
            else:
                self.show_error("No Data Available")

        except Exception as e:
            logger.error("Error plotting spectrogram: %s", e, exc_info=True)
            self.show_error(str(e))
