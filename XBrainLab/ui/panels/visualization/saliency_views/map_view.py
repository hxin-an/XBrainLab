from functools import partial

from PyQt6.QtCore import pyqtSignal

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

    class_selected = pyqtSignal(object)
    _scrollable_canvas = True

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
            "Select a fold and method to visualize",
            color=Theme.WARNING,
            ha="center",
            va="center",
        )
        axis.axis("off")

    def update_plot(
        self,
        publication: SaliencyRenderPublication,
        absolute: bool,
        *,
        selected_label_key: object | None = None,
        display_mode: str = "all",
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
                partial(
                    SaliencyMapWidget._render_plot,
                    data,
                    absolute,
                    selected_label_key,
                    display_mode,
                ),
                error_context="saliency map",
                publication_generation=publication.generation,
            )
        except SaliencyViewUnavailableError as exc:
            self.show_error(str(exc))
        except Exception as e:
            logger.error("Error preparing saliency map: %s", e, exc_info=True)
            self.show_error(SALIENCY_PREPARATION_FAILED_TEXT)

    @staticmethod
    def _render_plot(
        data: SaliencyRenderData,
        absolute: bool,
        selected_label_key: object | None = None,
        display_mode: str = "all",
    ):
        visualizer = VisualizerType.SaliencyMap.value(data)
        return visualizer.get_plt(
            method=data.method,
            absolute=absolute,
            selected_label_key=selected_label_key,
            display_mode=display_mode,
        )

    def _install_canvas_interactions(self, canvas) -> None:
        super()._install_canvas_interactions(canvas)
        canvas.mpl_connect("button_release_event", self._on_tile_activated)

    def _on_tile_activated(self, event: object) -> None:
        axis = getattr(event, "inaxes", None)
        if getattr(event, "button", None) != 1 or axis is None:
            return
        key = getattr(axis, "_xbrainlab_class_key", None)
        if key is not None:
            self.class_selected.emit(key)
