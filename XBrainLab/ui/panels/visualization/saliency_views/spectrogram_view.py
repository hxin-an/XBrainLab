from functools import partial

from XBrainLab.backend.application.saliency_render import (
    SaliencyRenderData,
    SaliencyRenderPublication,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.visualization import VisualizerType
from XBrainLab.backend.visualization.saliency_spectrogram_map import (
    SaliencySpectrogramPreparationCache,
)
from XBrainLab.ui.styles.theme import Theme

from .base_saliency_view import (
    SALIENCY_PREPARATION_FAILED_TEXT,
    BaseSaliencyView,
    SaliencyViewUnavailableError,
)


class SaliencySpectrogramWidget(BaseSaliencyView):
    """Widget for visualizing Saliency Spectrograms.
    Useful for time-frequency analysis of importance.
    """

    def init_ui(self):
        self._preparation_cache = SaliencySpectrogramPreparationCache()
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
            color=Theme.TEXT_MUTED,
            ha="center",
            va="center",
        )
        axis.axis("off")

    def update_plot(
        self,
        publication: SaliencyRenderPublication,
        absolute: bool,
        *,
        display_normalized: bool | None = None,
    ) -> None:
        del absolute
        if not isinstance(publication, SaliencyRenderPublication):
            message = "saliency render publication is invalid"
            logger.error("Error preparing spectrogram: %s", message)
            self.show_error(message)
            return
        try:
            data = publication.data
            method = data.method
            preparation_cache = self._preparation_cache
            self.require_complete_saliency_coverage(method)
            self._render_figure_async(
                partial(
                    SaliencySpectrogramWidget._render_plot,
                    data,
                    preparation_cache,
                    (
                        publication.generation,
                        publication.training_generation,
                        publication.request.run,
                        method,
                    ),
                    (
                        publication.data.normalized
                        if display_normalized is None
                        else bool(display_normalized)
                    ),
                ),
                error_context="saliency spectrogram",
                publication_generation=publication.generation,
            )
        except SaliencyViewUnavailableError as exc:
            self.show_error(str(exc))
        except Exception as e:
            logger.error("Error preparing spectrogram: %s", e, exc_info=True)
            self.show_error(SALIENCY_PREPARATION_FAILED_TEXT)

    @staticmethod
    def _render_plot(
        data: SaliencyRenderData,
        preparation_cache: SaliencySpectrogramPreparationCache,
        preparation_key: tuple[object, ...],
        display_normalized: bool,
    ):
        visualizer = VisualizerType.SaliencySpectrogramMap.value(data)
        return visualizer.get_plt(
            method=data.method,
            display_normalized=display_normalized,
            preparation_cache=preparation_cache,
            preparation_key=preparation_key,
        )

    def closeEvent(self, event):  # noqa: N802
        self._preparation_cache.clear()
        super().closeEvent(event)
