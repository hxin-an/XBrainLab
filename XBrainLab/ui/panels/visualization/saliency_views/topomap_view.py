from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.visualization import VisualizerType
from XBrainLab.ui.styles.theme import Theme

from .base_saliency_view import BaseSaliencyView


class SaliencyTopographicMapWidget(BaseSaliencyView):
    """Widget for visualizing Topographic Saliency Maps.
    Requires channel locations (montage) to be set.
    """

    def init_ui(self):
        super().init_ui()
        # Add initial text to the default canvas
        if self.fig is None:
            raise RuntimeError("Base saliency view figure was not initialized")
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

    def show_warning(self, msg):
        """Show a warning message (yellow/orange)."""
        self._cancel_pending_render()
        if self.canvas is not None:
            self.canvas.hide()
        self.error_label.setText(msg)
        self.error_label.setStyleSheet(
            f"color: {Theme.WARNING}; font-size: 16px; font-weight: bold;",
        )
        self.error_label.show()

    def update_plot(self, plan, trainer, method, absolute, eval_record):
        if eval_record is None:
            eval_record = plan.get_eval_record()

        if not eval_record:
            self.show_error("No evaluation record found.")
            return

        try:
            epoch_data = trainer.get_dataset().get_epoch_data()

            # Montage Check
            positions = epoch_data.get_montage_position()
            if positions is None or len(positions) == 0:
                self.show_warning(
                    "Please Set Montage First\n(Go to Configuration -> Set Montage)",
                )
                return

            self._render_figure_async(
                lambda: self._render_plot(eval_record, epoch_data, method, absolute),
                error_context="topographic saliency map",
            )

        except Exception as e:
            logger.error("Error preparing topomap: %s", e, exc_info=True)
            self.show_error(str(e))

    @staticmethod
    def _render_plot(eval_record, epoch_data, method, absolute):
        visualizer = VisualizerType.SaliencyTopoMap.value(eval_record, epoch_data)
        return visualizer.get_plt(method=method, absolute=absolute)
