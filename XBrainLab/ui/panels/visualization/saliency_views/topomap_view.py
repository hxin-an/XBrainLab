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


class SaliencyTopographicMapWidget(BaseSaliencyView):
    """Widget for visualizing Topographic Saliency Maps.
    Requires channel locations (montage) to be set.
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
            "Select a fold and method to visualize",
            color=Theme.TEXT_MUTED,
            ha="center",
            va="center",
        )
        axis.axis("off")

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
            logger.error("Error preparing topomap: %s", message)
            self.show_error(message)
            return
        try:
            data = publication.data
            method = data.method
            self.require_complete_saliency_coverage(method)

            # Montage Check
            positions = data.channel_positions
            if positions is None or len(positions) == 0:
                self.show_warning(
                    "Please Set Montage First\n(Go to Configuration -> Set Montage)",
                )
                return

            self._render_figure_async(
                partial(
                    SaliencyTopographicMapWidget._render_plot,
                    data,
                    absolute,
                    selected_label_key,
                    display_mode,
                ),
                error_context="topographic saliency map",
                publication_generation=publication.generation,
            )

        except SaliencyViewUnavailableError as exc:
            self.show_error(str(exc))
        except Exception as e:
            logger.error("Error preparing topomap: %s", e, exc_info=True)
            self.show_error(SALIENCY_PREPARATION_FAILED_TEXT)

    @staticmethod
    def _render_plot(
        data: SaliencyRenderData,
        absolute: bool,
        selected_label_key: object | None = None,
        display_mode: str = "all",
    ):
        visualizer = VisualizerType.SaliencyTopoMap.value(data)
        return visualizer.get_plt(
            method=data.method,
            absolute=absolute,
            selected_label_key=selected_label_key,
            display_mode=display_mode,
        )
