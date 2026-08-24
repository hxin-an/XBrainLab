"""Preprocessing panel for signal filtering, resampling, and epoching."""

from typing import cast

from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from XBrainLab.backend.application.owned_work import OwnedWorkKind
from XBrainLab.backend.application.preprocess_render import (
    PreprocessRenderPublication,
    PreprocessSignalState,
)
from XBrainLab.backend.application.view_publication import (
    APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
    ApplicationViewPublication,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.application_capabilities import (
    ApplicationViewPublicationPort,
    application_ui_runtime,
    get_controller_for_compatibility_context,
)
from XBrainLab.ui.application_publication_renderer import (
    ApplicationPublicationRenderLedger,
)
from XBrainLab.ui.core.base_panel import BasePanel
from XBrainLab.ui.panels.preprocess.data_query import (
    PreprocessRenderDataUnavailableError,
    query_preprocess_data_rows,
    query_preprocess_render,
)
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

    def __init__(
        self,
        controller=None,
        dataset_controller=None,
        parent=None,
        *,
        publication_port: ApplicationViewPublicationPort | None = None,
    ):
        """Initialize the preprocessing panel.

        Args:
            controller: Optional ``PreprocessController``. Resolved from
                the parent study if not provided.
            dataset_controller: Optional ``DatasetController`` for
                data-change event subscription.
            parent: Parent widget (typically the main window).

        """
        # 1. Controller Resolution
        if (
            controller is None
            and publication_port is None
            and parent
            and hasattr(parent, "study")
        ):
            controller = get_controller_for_compatibility_context(
                parent,
                parent.study,
                "preprocess",
            )
        if (
            dataset_controller is None
            and publication_port is None
            and parent
            and hasattr(parent, "study")
        ):
            dataset_controller = get_controller_for_compatibility_context(
                parent,
                parent.study,
                "dataset",
            )

        # 2. Base Init
        super().__init__(parent=parent, controller=controller)
        self.dataset_controller = dataset_controller
        runtime = application_ui_runtime(self)
        self._publication_port = (
            publication_port if publication_port is not None else runtime
        )
        self._application_view_publication: ApplicationViewPublication | None = None
        self._last_application_revision = 0
        self._application_render_ledger = ApplicationPublicationRenderLedger(
            panel_name="Preprocess",
            render_publication=self._render_application_publication,
            commit_publication=self._commit_application_publication,
            parent=self,
        )
        self._application_refresh_timer = self._application_render_ledger.timer

        # 3. Setup Components
        self.preview_widget = PreviewWidget(self)
        self.history_widget = HistoryWidget(self)
        self.sidebar = PreprocessSidebar(self, self)

        # 4. Setup Plotter
        self.plotter = PreprocessPlotter(self.preview_widget)

        # 5. Connect Component Signals
        self.preview_widget.request_plot_update.connect(self.update_plot_only)

        # 6. Setup Bridges & UI
        self._setup_bridges()
        self.init_ui()

    def _setup_bridges(self):
        """Register Qt observer bridges for preprocess and dataset events."""
        if self._publication_port is not None:
            self._create_bridge(
                cast(Observable, self._publication_port),
                APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
                self._on_application_view_publication_changed,
            )
            return
        if self.controller:
            self._create_refresh_bridge(self.controller, "preprocess_changed")

            if self.dataset_controller:
                self._create_refresh_bridge(self.dataset_controller, "data_changed")

    def _on_application_view_publication_changed(
        self,
        publication: object,
    ) -> bool:
        """Queue one Preprocess render for each monotonic application revision."""
        if not self._valid_application_publication(publication):
            logger.error("Ignored malformed Preprocess application publication.")
            return False
        typed_publication = cast(ApplicationViewPublication, publication)
        return self._application_render_ledger.queue(typed_publication)

    def _render_application_publication(
        self,
        publication: ApplicationViewPublication,
    ) -> None:
        self._application_view_publication = publication
        self.update_panel()

    def _commit_application_publication(
        self,
        publication: ApplicationViewPublication,
    ) -> None:
        self._last_application_revision = publication.revision

    @staticmethod
    def _valid_application_publication(publication: object) -> bool:
        return (
            isinstance(publication, ApplicationViewPublication)
            and not isinstance(publication.revision, bool)
            and isinstance(publication.revision, int)
            and publication.revision >= 1
        )

    def _read_application_publication(self) -> ApplicationViewPublication | None:
        pending = self._application_render_ledger.pending_publication
        if pending is not None and pending.revision > self._last_application_revision:
            self._application_view_publication = pending
            return pending
        port = self._publication_port
        if port is None:
            return None
        try:
            publication = port.get_view_publication()
        except Exception:
            logger.error(
                "Preprocess application publication is unavailable.",
                exc_info=True,
            )
            self._application_view_publication = None
            return None
        if not self._valid_application_publication(publication):
            self._application_view_publication = None
            return None
        typed_publication = cast(ApplicationViewPublication, publication)
        if typed_publication.revision >= self._last_application_revision:
            self._application_view_publication = typed_publication
        return self._application_view_publication

    def _application_publication_for_controls(
        self,
    ) -> ApplicationViewPublication | None:
        """Return ledger-owned truth without starting another runtime read."""
        pending = self._application_render_ledger.pending_publication
        if pending is not None and pending.revision > self._last_application_revision:
            return pending
        return self._application_view_publication

    def import_is_finishing(self) -> bool:
        """Return whether Data Import still owns review or apply work."""
        port = self._publication_port
        if port is None:
            return False
        active_operation = getattr(port, "get_active_owned_operation", None)
        if not callable(active_operation):
            return False
        try:
            return any(
                active_operation(kind) is not None
                for kind in (OwnedWorkKind.IMPORT_REVIEW, OwnedWorkKind.IMPORT_APPLY)
            )
        except Exception:
            logger.error(
                "Preprocess could not read active Data Import work.",
                exc_info=True,
            )
            return True

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

        left_layout.addWidget(self.preview_widget, stretch=1)
        left_layout.addWidget(self.history_widget, stretch=0)

        # --- Right Side: Sidebar ---
        main_layout.addWidget(left_widget, stretch=1)
        main_layout.addWidget(self.sidebar, stretch=0)

    def closeEvent(self, event) -> None:  # noqa: N802
        """Quiesce native plot callbacks before Qt tears down the panel."""
        if not self.preview_widget.finalize_native_plot_shutdown():
            event.ignore()
            return
        self.cleanup()
        super().closeEvent(event)

    def cleanup(self) -> None:
        """Cancel queued publication work and release observer bridges."""
        self._application_render_ledger.cleanup()
        super().cleanup()

    def update_panel(self, *args):
        """Refresh Preprocess and commit a direct render only after success."""
        self._update_panel_content(*args)
        if self._application_render_ledger.render_in_progress:
            return
        publication = self._application_view_publication
        if publication is not None:
            self._application_render_ledger.record_rendered(publication)

    def _update_panel_content(self, *args):
        """Refresh the sidebar, history, and preview from application truth."""
        application_publication = self._read_application_publication()
        # Update Sidebar
        if hasattr(self, "sidebar"):
            self.sidebar.update_sidebar(publication=application_publication)

        if self._publication_port is not None and (
            application_publication is None or not application_publication.usable
        ):
            self.history_widget.show_no_data()
            self.preview_widget.reset_view()
            return

        publication = self._query_render_publication()
        if publication is None:
            self.history_widget.show_no_data()
            self.preview_widget.reset_view()
            return
        self._apply_render_publication(publication, update_history=True)

    def update_plot_only(self):
        """Trigger a plot refresh without updating the sidebar or history."""
        publication = self._query_render_publication()
        if publication is None:
            return
        self._apply_render_publication(publication, update_history=False)

    def _apply_render_publication(
        self,
        publication: PreprocessRenderPublication,
        *,
        update_history: bool,
    ) -> None:
        data = publication.data
        if update_history:
            if data.state is PreprocessSignalState.NO_DATA:
                self.history_widget.show_no_data()
            else:
                self.history_widget.update_history(
                    list(data.history),
                    data.state is PreprocessSignalState.LOCKED,
                )

        if data.state is PreprocessSignalState.NO_DATA:
            self.preview_widget.reset_view()
            return
        if data.state is PreprocessSignalState.LOCKED:
            self.preview_widget.show_locked_message(
                "Preprocessing locked",
            )
            return

        self.preview_widget.chan_combo.blockSignals(True)
        self.preview_widget.chan_combo.clear()
        self.preview_widget.chan_combo.addItems(list(data.channels))
        selected_index = data.selected_channel_index
        if selected_index is not None:
            self.preview_widget.chan_combo.setCurrentIndex(selected_index)
        self.preview_widget.chan_combo.blockSignals(False)

        self.preview_widget.time_spin.setRange(0.0, data.cursor_max_seconds)
        self.preview_widget.time_slider.setRange(
            0,
            int(data.cursor_max_seconds * 10),
        )
        self.plotter.plot_sample_data(publication)

    def _query_render_publication(self) -> PreprocessRenderPublication | None:
        channel_index = max(0, self.preview_widget.chan_combo.currentIndex())
        start_seconds = max(0.0, float(self.preview_widget.time_spin.value()))
        try:
            publication = query_preprocess_render(
                self,
                channel_index=channel_index,
                start_seconds=start_seconds,
            )
        except PreprocessRenderDataUnavailableError as error:
            self.preview_widget.show_unavailable_message(str(error))
            return None
        return publication

    def _query_preprocess_data_rows(
        self,
    ) -> tuple[list[dict], list[dict]] | None:
        return query_preprocess_data_rows(self)
