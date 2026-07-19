from functools import partial

from XBrainLab.backend.application.saliency_render import (
    SaliencyRenderData,
    SaliencyRenderPublication,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.visualization import VisualizerType
from XBrainLab.ui.styles.theme import Theme

from .base_saliency_view import (
    SALIENCY_PREPARATION_FAILED_TEXT,
    BaseSaliencyView,
    SaliencyViewUnavailableError,
)


class SaliencyMapWidget(BaseSaliencyView):
    """Widget for visualizing 2D Saliency Maps.
    Uses Matplotlib backend.
    """

    def init_ui(self):
        super().init_ui()
        # Add initial text to the default canvas
        if self.fig is None:
            raise RuntimeError("Base saliency view figure was not initialized")
        axis = self.fig.add_subplot(111)
        Theme.apply_matplotlib_dark_theme(self.fig, ax=axis)
        axis.text(
            0.5,
            0.5,
            "Select a plan and method to visualize",
            color=Theme.TEXT_MUTED,
            ha="center",
            va="center",
        )
        axis.axis("off")

    def update_plot(
        self,
        publication: SaliencyRenderPublication,
        absolute: bool,
    ) -> None:
        if not isinstance(publication, SaliencyRenderPublication):
            message = "saliency render publication is invalid"
            logger.error("Error preparing saliency map: %s", message)
            self.show_error(message)
            return
        try:
            data = publication.data
            method = data.method
            self.require_complete_saliency_coverage(method)
            self._render_figure_async(
                partial(SaliencyMapWidget._render_plot, data, absolute),
                error_context="saliency map",
                publication_generation=publication.generation,
            )
        except SaliencyViewUnavailableError as exc:
            self.show_error(str(exc))
        except Exception as e:
            logger.error("Error preparing saliency map: %s", e, exc_info=True)
            self.show_error(SALIENCY_PREPARATION_FAILED_TEXT)

    @staticmethod
    def _render_plot(data: SaliencyRenderData, absolute: bool):
        visualizer = VisualizerType.SaliencyMap.value(data)
        return visualizer.get_plt(method=data.method, absolute=absolute)
