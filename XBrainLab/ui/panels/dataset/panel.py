"""Dataset panel for managing EEG data loading, metadata, and table display."""

import re
from pathlib import Path, PureWindowsPath
from typing import Any

from PyQt6.QtCore import QModelIndex, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QStackedWidget,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application.commands import (
    CommandName,
    QueryStateCommand,
    UpdateMetadataCommand,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.application_capabilities import (
    CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
    ControllerCompatibilityUnavailableError,
    blocked_reason,
    execute_application_command,
    get_application_view_publication,
    get_command_capability,
    get_controller_for_compatibility_context,
    has_real_application_context,
    is_application_runtime_deferred,
    is_stale_publication_result,
    local_result_payload,
    run_controller_compatibility_call,
)
from XBrainLab.ui.core.base_panel import BasePanel
from XBrainLab.ui.status import show_status_message
from XBrainLab.ui.styles.theme import Theme
from XBrainLab.ui.table_sizing import scaled_column_widths

from .actions import (
    DatasetActionHandler,
    DatasetTableRowIdentity,
    DatasetTableSelection,
)
from .sidebar import DatasetSidebar


class _DatasetMetadataEditDelegate(QStyledItemDelegate):
    """Capture the rendered row identity before Qt opens an inline editor."""

    def __init__(self, panel: "DatasetPanel") -> None:
        super().__init__(panel.table)
        self._panel = panel

    def createEditor(  # noqa: N802
        self,
        parent: QWidget,
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
    _COMPACT_TABLE_WIDTH = 336
    _FILE_ONLY_TABLE_WIDTH = 240
    _COMPACT_COLUMNS = (0, 3, 6)
    _ROW_IDENTITY_ROLE = int(Qt.ItemDataRole.UserRole) + 1

    def __init__(self, controller=None, parent=None):
        """Initialize the dataset panel.

        Args:
            controller: Optional ``DatasetController``. Resolved from the
                parent study if not provided.
            parent: Parent widget (typically the main window).

        """
        # 1. Controller Resolution (Compatibility/Test support)
        if controller is None and parent and hasattr(parent, "study"):
            controller = get_controller_for_compatibility_context(
                parent,
                parent.study,
                "dataset",
            )

        # 2. Base Init (sets self.controller, self.main_window)
        super().__init__(parent=parent, controller=controller)

        # 3. Helpers
        self.action_handler = DatasetActionHandler(self)
        self._table_fit_pending = False
        self._table_publication_generation: int | None = None
        self._table_metadata_capability = None
        self._metadata_edit_selections: dict[int, DatasetTableSelection] = {}

        # 4. Bridge & UI Setup (Explicit call required by new BasePanel contract)
        self._setup_bridges()
        self.init_ui()

    def _setup_bridges(self):
        """Register Qt observer bridges for controller events."""
        if self.controller:
            self._create_refresh_bridge(self.controller, "data_changed")
            self._create_bridge(
                self.controller,
                "import_finished",
                self.action_handler.on_import_finished,
            )

    def init_ui(self):
        """Build the panel layout with a file table and sidebar."""
        # Main Layout: Horizontal Split (Table | Info & Controls)
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Left Side: File List Table ---
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["File", "Subject", "Session", "Chan", "Hz", "Epochs", "Events"],
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
        empty_layout.setContentsMargins(32, 32, 32, 32)
        empty_layout.setSpacing(8)
        empty_layout.addStretch()
        self.empty_state_title = QLabel("No EEG data loaded")
        self.empty_state_title.setObjectName("DatasetEmptyStateTitle")
        self.empty_state_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
        empty_layout.addStretch()

        self.data_surface = QStackedWidget()
        self.data_surface.setObjectName("DatasetContentSurface")
        self.data_surface.addWidget(self.table)
        self.data_surface.addWidget(self.empty_state)
        self.data_surface.setCurrentWidget(self.empty_state)
        main_layout.addWidget(self.data_surface, stretch=2)

        # --- Right Side: Sidebar ---
        self.sidebar = DatasetSidebar(self, self)
        main_layout.addWidget(self.sidebar, stretch=0)
        self._fit_table_columns_to_viewport()
        self._schedule_table_column_fit()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "table"):
            self._fit_table_columns_to_viewport()
            self._schedule_table_column_fit()

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
        for _ in range(3):
            if self.data_surface.currentWidget() is not self.table:
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

    def apply_loader(self, loader):
        """Apply a compatibility data loader only for mock or compatibility UI contexts.

        Args:
            loader: A data loader instance that supports ``apply()``
                and ``__len__``.

        """
        try:
            total_files = self._compatibility_apply_loader(loader)
        except Exception as exc:
            logger.error("Failed to apply data", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to apply data: {exc}")
            return
        if total_files is None:
            return

        show_status_message(self, f"Dataset updated · {total_files} files")

    def _compatibility_apply_loader(self, loader) -> int | None:
        try:
            return run_controller_compatibility_call(
                self,
                lambda: self._apply_compatibility_loader(loader),
            )
        except ControllerCompatibilityUnavailableError:
            logger.warning("Blocked compatibility loader apply in real Study context.")
            QMessageBox.warning(
                self,
                "Import EEG Data",
                "Use Import file, Import folder, or Import BIDS folder so "
                "the data goes through the guided import workflow.",
            )
            return None

    def _apply_compatibility_loader(self, loader) -> int:
        # Kept for mock/unit-test compatibility; product data entry uses commands.
        controller = self.controller
        if controller is None or getattr(controller, "study", None) is None:
            raise RuntimeError(
                "Compatibility loader adapter requires a dataset controller."
            )
        loader.apply(controller.study, force_update=True)
        self.update_panel()
        return len(loader)

    def update_panel(self):
        """Refresh the sidebar and table contents from the controller."""
        if not hasattr(self, "controller"):
            return

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
            return

        # Update Table
        self._metadata_edit_selections.clear()
        self.table.clearContents()
        self.table.blockSignals(True)  # Prevent itemChanged triggering during update
        self.table.setRowCount(0)

        publication = get_application_view_publication(self)
        render_generation = (
            int(publication.generation) if publication is not None else None
        )
        self._table_publication_generation = render_generation
        queried_data_list = self._query_loaded_data_list_for_render(
            expected_publication_generation=render_generation,
        )
        controller = self.controller
        if controller is None:
            data_list = []
        elif queried_data_list is None:
            data_list = self._compatibility_loaded_data_list_for_render(controller)
        else:
            data_list = queried_data_list
        metadata_capability = (
            publication.effective_capabilities.get(CommandName.UPDATE_METADATA)
            if publication is not None
            else get_command_capability(self, CommandName.UPDATE_METADATA)
        )
        self._table_metadata_capability = metadata_capability
        metadata_editable = (
            metadata_capability.enabled if metadata_capability is not None else True
        )
        metadata_block_reason = blocked_reason(
            metadata_capability,
            "Metadata editing is not available right now.",
        )

        if data_list:
            self.table.setRowCount(len(data_list))
            for row, data in enumerate(data_list):
                row_identity = self._row_identity_for_render(data, row)
                # Filename (Read-only)
                item_name = QTableWidgetItem(data.get_filename())
                item_name.setFlags(item_name.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 0, item_name)

                # Subject
                self.table.setItem(
                    row,
                    1,
                    self._metadata_item(
                        data.get_subject_name(),
                        editable=metadata_editable and row_identity is not None,
                        blocked_tooltip=metadata_block_reason,
                    ),
                )

                # Session
                self.table.setItem(
                    row,
                    2,
                    self._metadata_item(
                        data.get_session_name(),
                        editable=metadata_editable and row_identity is not None,
                        blocked_tooltip=metadata_block_reason,
                    ),
                )

                # Channels (Read-only)
                item_ch = QTableWidgetItem(str(data.get_nchan()))
                item_ch.setFlags(item_ch.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 3, item_ch)

                # Sfreq (Read-only)
                item_sf = QTableWidgetItem(str(data.get_sfreq()))
                item_sf.setFlags(item_sf.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 4, item_sf)

                # Epochs (Read-only)
                item_ep = QTableWidgetItem(str(data.get_epochs_length()))
                item_ep.setFlags(item_ep.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 5, item_ep)

                event_summary = self._event_summary_for_render(data)
                if event_summary.get("available"):
                    count = event_summary.get("count")
                    count_str = "?" if count is None else str(count)
                    if data.is_labels_imported():
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

                # Store raw object reference in first item
                item_name.setData(Qt.ItemDataRole.UserRole, data)
                if row_identity is not None:
                    item_name.setData(self._ROW_IDENTITY_ROLE, row_identity)

        self.table.blockSignals(False)
        if data_list:
            self.data_surface.setCurrentWidget(self.table)
        else:
            self._show_dataset_empty_state()
        self._fit_table_columns_to_viewport()
        self._schedule_table_column_fit()

    def _show_dataset_empty_state(
        self,
        *,
        title: str = "No EEG data loaded",
        detail: str = "Import a file, folder, or BIDS folder to begin.",
    ) -> None:
        """Present an intentional zero-data surface without a blank table viewport."""
        self.empty_state_title.setText(title)
        self.empty_state_detail.setText(detail)
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
    ) -> list[Any] | None:
        result = execute_application_command(
            self,
            QueryStateCommand(query="data_lists", include_objects=True),
            refresh=False,
            expected_publication_generation=expected_publication_generation,
        )
        if result is None:
            return None
        if result.failed:
            return []
        data_list = local_result_payload(result).get("loaded_data_list")
        return list(data_list) if isinstance(data_list, list) else []

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
        data: Any,
        row: int,
    ) -> DatasetTableRowIdentity | None:
        canonical_filepath = self._canonical_filepath(data)
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
        QMessageBox.warning(
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

    def _compatibility_loaded_data_list_for_render(self, controller) -> list[Any]:
        try:
            return run_controller_compatibility_call(
                self,
                controller.get_loaded_data_list,
            )
        except ControllerCompatibilityUnavailableError:
            logger.warning(
                "Blocked stale dataset controller render fallback in real "
                "Study context.",
            )
            return []

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
        if not (name_item and name_item.data(Qt.ItemDataRole.UserRole)):
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

        metadata_capability = (
            self._table_metadata_capability
            if selection.publication_generation is not None
            else get_command_capability(self, CommandName.UPDATE_METADATA)
        )
        if metadata_capability is not None and not metadata_capability.enabled:
            QMessageBox.warning(
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
                QMessageBox.warning(
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
                QMessageBox.warning(self, title, result.message)
                self._restore_rejected_metadata_edit()
                return
        elif col == 2:  # Session
            result = execute_application_command(
                self,
                UpdateMetadataCommand(index=resolved_row, session=new_value),
                expected_publication_generation=expected_generation,
            )
            if result is None:
                QMessageBox.warning(
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
                QMessageBox.warning(self, title, result.message)
                self._restore_rejected_metadata_edit()
                return
