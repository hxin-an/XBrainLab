"""Dataset panel for managing EEG data loading, metadata, and table display."""

import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, cast

from PyQt6.QtCore import QModelIndex, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application.capabilities import CommandCapability
from XBrainLab.backend.application.commands import (
    CommandName,
    QueryStateCommand,
    UpdateMetadataCommand,
)
from XBrainLab.backend.application.view_publication import (
    APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
    ApplicationViewPublication,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.application_capabilities import (
    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
    ApplicationViewPublicationPort,
    application_ui_runtime,
    blocked_reason,
    execute_application_command,
    get_application_view_publication,
    get_command_capability,
    has_real_application_context,
    is_application_runtime_deferred,
    is_stale_publication_result,
)
from XBrainLab.ui.application_publication_renderer import (
    ApplicationPublicationRenderLedger,
)
from XBrainLab.ui.components.modal_presentation import show_warning
from XBrainLab.ui.core.base_panel import BasePanel
from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.styles.theme import Theme
from XBrainLab.ui.table_sizing import scaled_column_widths

from .actions import (
    DatasetActionHandler,
    DatasetTableRowIdentity,
    DatasetTableSelection,
)
from .sidebar import DatasetSidebar

_METADATA_AVAILABILITY_UNAVAILABLE = (
    "Metadata editing availability is unavailable right now."
)


@dataclass(frozen=True)
class _DatasetRowsQueryOutcome:
    """Detached table rows or a classified read-side failure."""

    rows: list[dict[str, Any]] | None
    retryable: bool = False
    message: str = ""


class _DatasetMetadataEditDelegate(QStyledItemDelegate):
    """Capture the rendered row identity before Qt opens an inline editor."""

    def __init__(self, panel: "DatasetPanel") -> None:
        super().__init__(panel.table)
        self._panel = panel

    def createEditor(  # noqa: N802
        self,
        parent: QWidget | None,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> QWidget | None:
        if index.column() in (1, 2):
            self._panel._capture_metadata_edit(index.row(), index.column())
        return super().createEditor(parent, option, index)


class DatasetPanel(BasePanel):
    """Panel for managing dataset loading and metadata.

    Provides file import, label import, smart-parse, channel selection,
    and a table view of loaded EEG recordings.  Integrates with
    ``DatasetController`` via observer bridges.

    Attributes:
        action_handler: ``DatasetActionHandler`` for complex panel actions.
        table: ``QTableWidget`` displaying loaded file metadata.
        sidebar: ``DatasetSidebar`` with operations and info panel.
        bridge: Observer bridge for ``data_changed`` events.
        bridge_import: Observer bridge for ``import_finished`` events.

    """

    _TABLE_BASE_WIDTHS: tuple[int, ...] = (240, 84, 112, 56, 64, 74, 112)
    _TABLE_MIN_WIDTH = 48
    _COMPACT_TABLE_WIDTH = 620
    _FILE_ONLY_TABLE_WIDTH = 240
    _COMPACT_COLUMNS = (0, 3, 6)
    _ROW_IDENTITY_ROLE = int(Qt.ItemDataRole.UserRole) + 1

    def __init__(
        self,
        controller=None,
        parent=None,
        *,
        publication_port: ApplicationViewPublicationPort | None = None,
    ):
        """Initialize the dataset panel.

        Args:
            controller: Optional ``DatasetController``. Resolved from the
                parent study if not provided.
            parent: Parent widget (typically the main window).

        """
        # Dataset product state is publication/query-owned.  The optional
        # controller argument remains source-compatible for callers while this
        # panel intentionally never reads or mutates it.
        super().__init__(parent=parent, controller=None)

        runtime = application_ui_runtime(self)
        self._publication_port = (
            publication_port if publication_port is not None else runtime
        )
        self._application_view_publication: ApplicationViewPublication | None = None
        self._last_application_revision = 0
        self._replace_application_render_ledger()

        # Helpers
        self.action_handler = DatasetActionHandler(self)
        self._table_fit_pending = False
        self._table_publication_generation: int | None = None
        self._table_metadata_capability: CommandCapability | None = None
        self._metadata_edit_selections: dict[int, DatasetTableSelection] = {}

        # Bridge & UI Setup (Explicit call required by new BasePanel contract)
        self._setup_bridges()
        self.init_ui()

    def _setup_bridges(self):
        """Register the application-publication render bridge."""
        if self._publication_port is not None:
            self._create_bridge(
                cast(Any, self._publication_port),
                APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
                self._on_application_view_publication_changed,
            )
            return

    def rebind_application_publication_port(
        self,
        publication_port: ApplicationViewPublicationPort,
    ) -> None:
        """Reconnect this Dataset view after its command runtime is replaced."""
        for bridge in self._bridges:
            bridge.cleanup()
        self._bridges.clear()
        self._publication_port = publication_port
        self._application_view_publication = None
        self._last_application_revision = 0
        self._replace_application_render_ledger()
        self._setup_bridges()

    def _replace_application_render_ledger(self) -> None:
        previous = getattr(self, "_application_render_ledger", None)
        if previous is not None:
            previous.cleanup()
        self._application_render_ledger = ApplicationPublicationRenderLedger(
            panel_name="Dataset",
            render_publication=self._render_application_publication,
            commit_publication=self._commit_application_publication,
            parent=self,
        )
        self._application_refresh_timer = self._application_render_ledger.timer

    def _on_application_view_publication_changed(
        self,
        publication: object,
    ) -> bool:
        """Queue one Dataset render for each monotonic application revision."""
        if not self._valid_application_publication(publication):
            logger.error("Ignored malformed Dataset application publication.")
            return False
        typed_publication = cast(ApplicationViewPublication, publication)
        return self._application_render_ledger.queue(typed_publication)

    def _render_application_publication(
        self,
        publication: ApplicationViewPublication,
    ) -> bool:
        self._application_view_publication = publication
        return self.update_panel() is not False

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
            return get_application_view_publication(self)
        try:
            publication = port.get_view_publication()
        except Exception:
            logger.error(
                "Dataset application publication is unavailable.",
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

    def cleanup(self) -> None:
        """Cancel queued publication work before releasing observer bridges."""
        self._application_render_ledger.cleanup()
        super().cleanup()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.cleanup()
        super().closeEvent(event)

    def init_ui(self):
        """Build the panel layout with a file table and sidebar."""
        # Main Layout: Horizontal Split (Table | Info & Controls)
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.content_column = QWidget()
        content_layout = QVBoxLayout(self.content_column)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # --- Left Side: File List Table ---
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["File", "Subject", "Session", "Chan", "Hz", "EEG epochs", "Events"],
        )
        header = self.table.horizontalHeader()
        if header:
            header.setStretchLastSection(False)
            header.setMinimumSectionSize(48)
            for column in range(7):
                header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        for column, width in enumerate(self._TABLE_BASE_WIDTHS):
            self.table.setColumnWidth(column, width)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection,
        )  # Allow multiple selection
        self.table.itemChanged.connect(self.on_item_changed)
        self._metadata_edit_delegate = _DatasetMetadataEditDelegate(self)
        self.table.setItemDelegate(self._metadata_edit_delegate)

        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(
            self.action_handler.show_context_menu,
        )

        self.empty_state = QWidget()
        self.empty_state.setObjectName("DatasetEmptyState")
        empty_layout = QVBoxLayout(self.empty_state)
        empty_layout.setContentsMargins(20, 32, 20, 32)
        empty_layout.setSpacing(8)
        empty_layout.addStretch()
        self.empty_state_title = QLabel("No EEG data loaded")
        self.empty_state_title.setObjectName("DatasetEmptyStateTitle")
        self.empty_state_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state_title.setWordWrap(True)
        self.empty_state_title.setStyleSheet(
            f"color: {Theme.TEXT_MUTED}; font-size: 16px; font-weight: 600;"
        )
        empty_layout.addWidget(self.empty_state_title)
        self.empty_state_detail = QLabel(
            "Import a file, folder, or BIDS folder to begin."
        )
        self.empty_state_detail.setObjectName("DatasetEmptyStateDetail")
        self.empty_state_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state_detail.setWordWrap(True)
        self.empty_state_detail.setStyleSheet(
            f"color: {Theme.TEXT_SECONDARY}; font-size: 13px;"
        )
        empty_layout.addWidget(self.empty_state_detail)
        self.empty_state_import_btn = QPushButton("Import EEG Data")
        self.empty_state_import_btn.setObjectName("DatasetEmptyStatePrimaryAction")
        self.empty_state_import_btn.setStyleSheet(Stylesheets.BTN_PRIMARY)
        self.empty_state_import_btn.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Fixed,
        )
        self.empty_state_import_btn.clicked.connect(self.action_handler.import_data)
        empty_layout.addSpacing(8)
        empty_layout.addWidget(
            self.empty_state_import_btn,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )
        empty_layout.addStretch()

        self.data_surface = QStackedWidget()
        self.data_surface.setObjectName("DatasetContentSurface")
        self.data_surface.addWidget(self.table)
        self.data_surface.addWidget(self.empty_state)
        self.data_surface.setCurrentWidget(self.empty_state)

        content_layout.addWidget(self.data_surface, stretch=1)
        self.main_layout.addWidget(self.content_column, stretch=2)

        # --- Right Side: Sidebar ---
        self.sidebar = DatasetSidebar(self, self)
        self.main_layout.addWidget(self.sidebar, stretch=0)
        self._fit_fixed_sidebar_layout()
        self._fit_table_columns_to_viewport()
        self._schedule_table_column_fit()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._fit_fixed_sidebar_layout()
        if hasattr(self, "table"):
            self._fit_table_columns_to_viewport()
            self._schedule_table_column_fit()

    def showEvent(self, event) -> None:  # noqa: N802
        """Fit a size requested while the parent panel was still hidden."""
        super().showEvent(event)
        self._fit_fixed_sidebar_layout()
        self._fit_table_columns_to_viewport()
        self._schedule_table_column_fit()

    def _fit_fixed_sidebar_layout(self) -> None:
        """Reserve the product sidebar width and bound the remaining surface."""
        if not hasattr(self, "sidebar") or not hasattr(self, "content_column"):
            return
        margins = self.main_layout.contentsMargins()
        available_width = max(
            self.contentsRect().width()
            - margins.left()
            - margins.right()
            - self.main_layout.spacing()
            - self.sidebar.width(),
            0,
        )
        if available_width <= 0:
            return
        self.content_column.setMaximumWidth(available_width)

    def _schedule_table_column_fit(self) -> None:
        """Refit once Qt has settled row headers and scrollbars."""
        if self._table_fit_pending:
            return
        self._table_fit_pending = True
        QTimer.singleShot(0, self._run_scheduled_table_column_fit)

    def _run_scheduled_table_column_fit(self) -> None:
        self._table_fit_pending = False
        if hasattr(self, "table"):
            self._fit_table_columns_to_viewport()
            QTimer.singleShot(0, self._fit_table_columns_to_viewport)

    def _fit_table_columns_to_viewport(self) -> None:
        """Use the full table panel while keeping columns manually resizable."""
        panel_layout = self.layout()
        if panel_layout is not None:
            panel_layout.invalidate()
            panel_layout.activate()
        content_layout = self.content_column.layout()
        if content_layout is not None:
            content_layout.invalidate()
            content_layout.activate()
        for _ in range(3):
            surface_size = self.data_surface.contentsRect().size()
            if surface_size.isValid():
                self.table.resize(surface_size)
            self.table.updateGeometries()
            viewport = self.table.viewport()
            if viewport is None:
                return
            target_width = max(viewport.width() - 1, 0)
            visible_columns = self._visible_table_columns(target_width)
            for column in range(self.table.columnCount()):
                self.table.setColumnHidden(column, column not in visible_columns)
            widths = scaled_column_widths(
                tuple(self._TABLE_BASE_WIDTHS[column] for column in visible_columns),
                target_width,
                min_width=self._TABLE_MIN_WIDTH,
            )
            for column, width in zip(visible_columns, widths, strict=True):
                self.table.setColumnWidth(column, width)
            self.table.updateGeometries()
            header = self.table.horizontalHeader()
            scrollbar = self.table.horizontalScrollBar()
            settled_viewport = self.table.viewport()
            if (
                header is not None
                and scrollbar is not None
                and settled_viewport is not None
                and scrollbar.maximum() == 0
                and abs(header.length() - settled_viewport.width()) <= 2
            ):
                return

    def _visible_table_columns(self, viewport_width: int) -> tuple[int, ...]:
        """Keep the dataset readable when a dock narrows the central panel."""
        if viewport_width < self._FILE_ONLY_TABLE_WIDTH:
            return (0,)
        if viewport_width < self._COMPACT_TABLE_WIDTH:
            return self._COMPACT_COLUMNS
        return tuple(range(self.table.columnCount()))

    def update_panel(self, *args: Any, **kwargs: Any) -> Any:
        """Refresh Dataset and commit a direct render only after success."""
        del args, kwargs
        if self._update_panel_content() is False:
            return False
        if self._application_render_ledger.render_in_progress:
            return True
        publication = self._application_view_publication
        if publication is not None:
            return self._application_render_ledger.record_rendered(publication)
        return True

    def _update_panel_content(self) -> bool:
        """Refresh the sidebar and table from committed application truth."""
        # Update Sidebar
        if hasattr(self, "sidebar"):
            self.sidebar.update_sidebar()

        if is_application_runtime_deferred(self):
            self._clear_table_render_identity()
            self.table.clearContents()
            self.table.setRowCount(0)
            self._show_dataset_empty_state()
            self._fit_table_columns_to_viewport()
            self._schedule_table_column_fit()
            return True

        publication = self._read_application_publication()
        product_context = (
            self._publication_port is not None or has_real_application_context(self)
        )
        if product_context and (publication is None or not publication.usable):
            self._clear_table_render_identity()
            self.table.clearContents()
            self.table.setRowCount(0)
            self._show_dataset_empty_state()
            self._fit_table_columns_to_viewport()
            self._schedule_table_column_fit()
            return True

        render_generation = (
            int(publication.generation) if publication is not None else None
        )
        query_outcome = self._query_loaded_data_list_for_render(
            expected_publication_generation=render_generation,
        )
        queried_rows = query_outcome.rows
        if queried_rows is None and product_context and query_outcome.retryable:
            logger.debug(
                "Dataset table publication %s is waiting for a stable application "
                "snapshot: %s",
                render_generation,
                query_outcome.message,
            )
            return False
        if queried_rows is None and product_context:
            logger.error(
                "Dataset table rows are unavailable for application generation %s; "
                "the publication remains pending: %s",
                render_generation,
                query_outcome.message or "No detached rows were returned.",
            )
            self._show_dataset_empty_state(
                title="Dataset view unavailable",
                detail=(
                    "Dataset details could not be read. "
                    "XBrainLab will retry automatically."
                ),
            )
            return False

        # Update Table
        self._metadata_edit_selections.clear()
        self.table.clearContents()
        self.table.blockSignals(True)  # Prevent itemChanged triggering during update
        self.table.setRowCount(0)

        self._table_publication_generation = render_generation
        if queried_rows is not None:
            data_rows: list[dict[str, Any]] = queried_rows
        else:
            data_rows = []
        event_labels = sorted(
            {
                str(label).strip()
                for data in data_rows
                for label in (
                    data.get("event", {}).get("labels", [])
                    if isinstance(data.get("event"), dict)
                    else []
                )
                if str(label).strip()
            },
            key=str.casefold,
        )
        self.table.setProperty("eventLabels", event_labels)
        self.table.setProperty("publicationGeneration", render_generation)
        if publication is not None:
            metadata_capability = publication.effective_capabilities.get(
                CommandName.UPDATE_METADATA
            )
        elif product_context:
            metadata_capability = None
        else:
            metadata_capability = get_command_capability(
                self,
                CommandName.UPDATE_METADATA,
            )
        self._table_metadata_capability = metadata_capability
        metadata_editable = (
            metadata_capability.enabled
            if metadata_capability is not None
            else not product_context
        )
        metadata_block_reason = blocked_reason(
            metadata_capability,
            (
                _METADATA_AVAILABILITY_UNAVAILABLE
                if product_context
                else "Metadata editing is not available right now."
            ),
        )

        if data_rows:
            self.table.setRowCount(len(data_rows))
            for row, data in enumerate(data_rows):
                row_identity = self._row_identity_for_render(data, row)
                # Filename (Read-only)
                item_name = QTableWidgetItem(str(data.get("filename", "")))
                item_name.setFlags(item_name.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 0, item_name)

                # Subject
                self.table.setItem(
                    row,
                    1,
                    self._metadata_item(
                        str(data.get("subject", "")),
                        editable=metadata_editable and row_identity is not None,
                        blocked_tooltip=metadata_block_reason,
                    ),
                )

                # Session
                self.table.setItem(
                    row,
                    2,
                    self._metadata_item(
                        str(data.get("session", "")),
                        editable=metadata_editable and row_identity is not None,
                        blocked_tooltip=metadata_block_reason,
                    ),
                )

                # Channels (Read-only)
                item_ch = QTableWidgetItem(self._display_row_value(data, "n_channels"))
                item_ch.setFlags(item_ch.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 3, item_ch)

                # Sfreq (Read-only)
                item_sf = QTableWidgetItem(
                    self._display_row_value(data, "sampling_frequency")
                )
                item_sf.setFlags(item_sf.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 4, item_sf)

                # Epochs (Read-only)
                item_ep = QTableWidgetItem(
                    self._display_row_value(data, "epochs_length")
                )
                item_ep.setFlags(item_ep.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 5, item_ep)

                event_summary = data.get("event", {})
                if not isinstance(event_summary, dict):
                    event_summary = {}
                if event_summary.get("available"):
                    count = event_summary.get("count")
                    count_str = "?" if count is None else str(count)
                    if data.get("labels_imported") is True:
                        item_ev = QTableWidgetItem(f"Labels ({count_str})")
                        item_ev.setForeground(QBrush(QColor(Theme.TEXT_MUTED)))
                        item_ev.setToolTip(
                            "External labels are attached to this recording."
                        )
                    else:
                        item_ev = QTableWidgetItem(f"Events ({count_str})")
                        item_ev.setToolTip("Events detected in the recording.")
                elif event_summary.get("scanned") is False:
                    item_ev = QTableWidgetItem("Events not scanned")
                    item_ev.setForeground(QBrush(QColor(Theme.TEXT_SECONDARY)))
                    item_ev.setToolTip(
                        "Event count is deferred to keep the dataset table responsive."
                    )
                else:
                    item_ev = QTableWidgetItem("No events")
                    item_ev.setForeground(QBrush(QColor(Theme.TEXT_SECONDARY)))
                    item_ev.setToolTip("No events or labels detected.")

                item_ev.setFlags(item_ev.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 6, item_ev)

                if row_identity is not None:
                    item_name.setData(self._ROW_IDENTITY_ROLE, row_identity)

        self.table.blockSignals(False)
        if data_rows:
            self.data_surface.setCurrentWidget(self.table)
        else:
            self._show_dataset_empty_state()
        self._fit_table_columns_to_viewport()
        self._schedule_table_column_fit()
        return True

    def _show_dataset_empty_state(
        self,
        *,
        title: str = "No EEG data loaded",
        detail: str = "Import a file, folder, or BIDS folder to begin.",
    ) -> None:
        """Present an intentional zero-data surface without a blank table viewport."""
        self.empty_state_title.setText(title)
        self.empty_state_detail.setText(detail)
        self.empty_state_import_btn.setVisible(title == "No EEG data loaded")
        self.data_surface.setCurrentWidget(self.empty_state)

    @staticmethod
    def _event_summary_for_render(data) -> dict[str, Any]:
        summary_method = getattr(data, "get_event_summary", None)
        if callable(summary_method):
            try:
                summary = summary_method(allow_scan=False)
                if isinstance(summary, dict):
                    return summary
            except Exception:
                logger.debug("Failed to read cached event summary", exc_info=True)
        try:
            has_event = bool(data.has_event())
        except Exception:
            logger.exception("Failed to read event availability")
            return {
                "available": False,
                "count": None,
                "labels": [],
                "source": "error",
                "scanned": True,
            }
        if not has_event:
            return {
                "available": False,
                "count": 0,
                "labels": [],
                "source": "none",
                "scanned": True,
            }
        try:
            if data.is_raw():
                events, event_id = data.get_event_list()
                count = len(events)
                labels = sorted(str(label) for label in event_id)
            else:
                count = data.get_epochs_length()
                labels = []
        except Exception:
            logger.exception("Failed to get event count")
            count = None
            labels = []
        return {
            "available": True,
            "count": count,
            "labels": labels,
            "source": "compatibility",
            "scanned": True,
        }

    def _query_loaded_data_list_for_render(
        self,
        *,
        expected_publication_generation: int | None = None,
    ) -> _DatasetRowsQueryOutcome:
        query_runtime = (
            self._publication_port
            if callable(getattr(self._publication_port, "execute", None))
            else None
        )
        result = execute_application_command(
            self,
            QueryStateCommand(query="data_lists"),
            refresh=False,
            expected_publication_generation=expected_publication_generation,
            runtime=cast(Any, query_runtime),
        )
        if result is None:
            return _DatasetRowsQueryOutcome(
                rows=None,
                message="Application runtime is unavailable.",
            )
        if result.failed:
            diagnostics = result.diagnostics
            retryable = result.recoverable and (
                diagnostics.get("application_busy") is True
                or diagnostics.get("stale_publication") is True
            )
            if retryable:
                logger.debug(
                    "Dataset data-list query deferred: %s",
                    result.message,
                )
                return _DatasetRowsQueryOutcome(
                    rows=None,
                    retryable=True,
                    message=result.message,
                )
            logger.error(
                "Dataset data-list query failed: %s",
                result.message,
            )
            return _DatasetRowsQueryOutcome(rows=None, message=result.message)
        data_rows = result.diagnostics.get("raw_rows")
        if not isinstance(data_rows, list):
            logger.error("Dataset data-list query returned no detached row list.")
            return _DatasetRowsQueryOutcome(
                rows=None,
                message="The query returned no detached row list.",
            )
        return _DatasetRowsQueryOutcome(
            rows=[dict(row) for row in data_rows if isinstance(row, dict)],
        )

    def _clear_table_render_identity(self) -> None:
        self._table_publication_generation = None
        self._table_metadata_capability = None
        self._metadata_edit_selections.clear()

    @staticmethod
    def _canonical_filepath(data: Any) -> str | None:
        getter = getattr(data, "get_filepath", None)
        if not callable(getter):
            return None
        try:
            raw_path = str(getter()).strip()
        except Exception:
            logger.debug("Failed to read Dataset row filepath", exc_info=True)
            return None
        return DatasetPanel._canonical_path_text(raw_path)

    @staticmethod
    def _canonical_path_text(raw_path: Any) -> str | None:
        raw_path = str(raw_path).strip()
        if not raw_path:
            return None
        if re.match(r"^[A-Za-z]:[\\/]", raw_path):
            return str(PureWindowsPath(raw_path)).casefold()
        try:
            return str(Path(raw_path).expanduser().resolve(strict=False))
        except (OSError, RuntimeError):
            return str(Path(raw_path).expanduser().absolute())

    def _row_identity_for_render(
        self,
        data: dict[str, Any],
        row: int,
    ) -> DatasetTableRowIdentity | None:
        canonical_filepath = self._canonical_path_text(data.get("filepath"))
        if canonical_filepath is None:
            return None
        return DatasetTableRowIdentity(
            canonical_filepath=canonical_filepath,
            rendered_row=row,
        )

    def capture_table_selection(
        self,
        rows: list[int] | tuple[int, ...],
    ) -> DatasetTableSelection | None:
        """Capture stable file identities from the currently rendered table."""
        identities: list[DatasetTableRowIdentity] = []
        for row in rows:
            name_item = self.table.item(int(row), 0)
            if name_item is None:
                return None
            identity = name_item.data(self._ROW_IDENTITY_ROLE)
            if not isinstance(identity, DatasetTableRowIdentity):
                if self._table_publication_generation is not None:
                    return None
                identity = DatasetTableRowIdentity(
                    canonical_filepath="",
                    rendered_row=int(row),
                )
            identities.append(identity)
        return DatasetTableSelection(
            publication_generation=self._table_publication_generation,
            rows=tuple(identities),
        )

    @staticmethod
    def _display_row_value(data: dict[str, Any], key: str) -> str:
        value = data.get(key)
        return "" if value is None else str(value)

    def resolve_table_selection(
        self,
        selection: DatasetTableSelection,
        *,
        stale_title: str,
        action_description: str,
    ) -> list[int] | None:
        """Resolve rendered file identities against the same backend publication."""
        generation = selection.publication_generation
        if generation is None:
            if has_real_application_context(self):
                self._reject_stale_table_action(
                    stale_title,
                    action_description,
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                return None
            return [identity.rendered_row for identity in selection.rows]

        result = execute_application_command(
            self,
            QueryStateCommand(query="data_lists"),
            refresh=False,
            expected_publication_generation=generation,
        )
        if result is None:
            self._reject_stale_table_action(
                stale_title,
                action_description,
                CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
            )
            return None
        if result.failed:
            message = (
                result.message
                if is_stale_publication_result(result)
                else (
                    f"XBrainLab could not verify which files to {action_description}. "
                    "Refresh the Dataset table and try again."
                )
            )
            self._reject_stale_table_action(
                stale_title,
                action_description,
                message,
            )
            return None

        diagnostics = getattr(result, "diagnostics", {}) or {}
        raw_files = diagnostics.get("raw_files")
        if not isinstance(raw_files, list):
            self._reject_stale_table_action(
                stale_title,
                action_description,
                "The current Dataset file list could not be verified. Refresh the "
                "Dataset table and try again.",
            )
            return None

        indices_by_path: dict[str, list[int]] = {}
        for index, filepath in enumerate(raw_files):
            canonical_filepath = self._canonical_path_text(filepath)
            if canonical_filepath is not None:
                indices_by_path.setdefault(canonical_filepath, []).append(index)

        resolved: list[int] = []
        for identity in selection.rows:
            matches = indices_by_path.get(identity.canonical_filepath, [])
            if len(matches) != 1:
                self._reject_stale_table_action(
                    stale_title,
                    action_description,
                    "The selected Dataset files changed or are ambiguous. Refresh the "
                    "Dataset table and select the intended files again.",
                )
                return None
            resolved.append(matches[0])
        return resolved

    def _reject_stale_table_action(
        self,
        title: str,
        action_description: str,
        detail: str,
    ) -> None:
        show_warning(
            self,
            title,
            f"{detail}\n\nRefresh the Dataset table before you "
            f"{action_description} again.",
        )
        self.update_panel()

    def _capture_metadata_edit(self, row: int, column: int) -> None:
        item = self.table.item(row, column)
        if item is None:
            return
        selection = self.capture_table_selection([row])
        if selection is not None:
            self._metadata_edit_selections[id(item)] = selection

    def _restore_rejected_metadata_edit(self) -> None:
        """Restore the published row after an edit was blocked or became stale."""
        self.update_panel()

    @staticmethod
    def _metadata_item(
        value: str,
        *,
        editable: bool,
        blocked_tooltip: str,
    ) -> QTableWidgetItem:
        item = QTableWidgetItem(value)
        if not editable:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item.setToolTip(blocked_tooltip)
        return item

    def on_item_changed(self, item):
        """Handle in-place editing of Subject or Session cells.

        Args:
            item: The ``QTableWidgetItem`` that was modified.

        """
        row = item.row()
        col = item.column()

        name_item = self.table.item(row, 0)
        if not (
            name_item
            and isinstance(
                name_item.data(self._ROW_IDENTITY_ROLE),
                DatasetTableRowIdentity,
            )
        ):
            return
        if col not in (1, 2):
            return

        new_value = item.text()
        selection = self._metadata_edit_selections.pop(id(item), None)
        if selection is None:
            selection = self.capture_table_selection([row])
        if selection is None:
            self._reject_stale_table_action(
                "Refresh Dataset and Edit Again",
                "edit metadata",
                "The edited row no longer identifies one Dataset file.",
            )
            return

        if selection.publication_generation is None and has_real_application_context(
            self
        ):
            show_warning(
                self,
                "Metadata blocked",
                _METADATA_AVAILABILITY_UNAVAILABLE,
            )
            self.update_panel()
            return
        metadata_capability = (
            self._table_metadata_capability
            if selection.publication_generation is not None
            else get_command_capability(self, CommandName.UPDATE_METADATA)
        )
        if metadata_capability is None and has_real_application_context(self):
            show_warning(
                self,
                "Metadata blocked",
                _METADATA_AVAILABILITY_UNAVAILABLE,
            )
            self.update_panel()
            return
        if metadata_capability is not None and not metadata_capability.enabled:
            show_warning(
                self,
                "Metadata blocked",
                blocked_reason(
                    metadata_capability,
                    "Metadata editing is not available right now.",
                ),
            )
            self.update_panel()
            return

        resolved_rows = self.resolve_table_selection(
            selection,
            stale_title="Refresh Dataset and Edit Again",
            action_description="edit metadata",
        )
        if resolved_rows is None or len(resolved_rows) != 1:
            return
        resolved_row = resolved_rows[0]
        expected_generation = selection.publication_generation

        if col == 1:  # Subject
            result = execute_application_command(
                self,
                UpdateMetadataCommand(index=resolved_row, subject=new_value),
                expected_publication_generation=expected_generation,
            )
            if result is None:
                show_warning(
                    self,
                    "Metadata blocked",
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                self._restore_rejected_metadata_edit()
                return
            if result.failed:
                title = (
                    "Refresh Dataset and Edit Again"
                    if is_stale_publication_result(result)
                    else "Metadata blocked"
                )
                show_warning(self, title, result.message)
                self._restore_rejected_metadata_edit()
                return
        elif col == 2:  # Session
            result = execute_application_command(
                self,
                UpdateMetadataCommand(index=resolved_row, session=new_value),
                expected_publication_generation=expected_generation,
            )
            if result is None:
                show_warning(
                    self,
                    "Metadata blocked",
                    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
                )
                self._restore_rejected_metadata_edit()
                return
            if result.failed:
                title = (
                    "Refresh Dataset and Edit Again"
                    if is_stale_publication_result(result)
                    else "Metadata blocked"
                )
                show_warning(self, title, result.message)
                self._restore_rejected_metadata_edit()
                return
