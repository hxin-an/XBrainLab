"""Dataset panel for managing EEG data loading, metadata, and table display."""

from typing import Any

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
)

from XBrainLab.backend.application import (
    CommandName,
    QueryStateCommand,
    UpdateMetadataCommand,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.application_capabilities import (
    LegacyControllerFallbackUnavailableError,
    blocked_reason,
    execute_application_command,
    get_command_capability,
    get_legacy_controller_from_study,
    run_legacy_controller_fallback,
)
from XBrainLab.ui.core.base_panel import BasePanel
from XBrainLab.ui.styles.theme import Theme
from XBrainLab.ui.table_sizing import scaled_column_widths

from .actions import DatasetActionHandler
from .sidebar import DatasetSidebar


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

    def __init__(self, controller=None, parent=None):
        """Initialize the dataset panel.

        Args:
            controller: Optional ``DatasetController``. Resolved from the
                parent study if not provided.
            parent: Parent widget (typically the main window).

        """
        # 1. Controller Resolution (Legacy/Test support)
        if controller is None and parent and hasattr(parent, "study"):
            controller = get_legacy_controller_from_study(
                parent,
                parent.study,
                "dataset",
            )

        # 2. Base Init (sets self.controller, self.main_window)
        super().__init__(parent=parent, controller=controller)

        # 3. Helpers
        self.action_handler = DatasetActionHandler(self)
        self._table_fit_pending = False

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

        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(
            self.action_handler.show_context_menu,
        )

        main_layout.addWidget(self.table, stretch=2)

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
            self.table.updateGeometries()
            viewport = self.table.viewport()
            if viewport is None:
                return
            target_width = max(viewport.width() - 1, 0)
            widths = scaled_column_widths(
                self._TABLE_BASE_WIDTHS,
                target_width,
                min_width=self._TABLE_MIN_WIDTH,
            )
            for column, width in enumerate(widths):
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

    def apply_loader(self, loader):
        """Apply a legacy data loader only for mock or legacy UI contexts.

        Args:
            loader: A data loader instance that supports ``apply()``
                and ``__len__``.

        """
        try:
            total_files = run_legacy_controller_fallback(
                self,
                lambda: self._apply_legacy_loader(loader),
            )
        except LegacyControllerFallbackUnavailableError:
            logger.warning("Blocked legacy loader apply in real Study context.")
            QMessageBox.warning(
                self,
                "Import EEG Data",
                "Use Import file, Import folder, or Import BIDS folder so "
                "the data goes through the guided import workflow.",
            )
            return
        except Exception as exc:
            logger.error("Failed to apply data", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to apply data: {exc}")
            return

        QMessageBox.information(
            self,
            "Success",
            f"Dataset updated. Total files: {total_files}",
        )

    def _apply_legacy_loader(self, loader) -> int:
        # Kept for mock/unit-test compatibility; product data entry uses commands.
        controller = self.controller
        if controller is None or getattr(controller, "study", None) is None:
            raise RuntimeError("Legacy loader adapter requires a dataset controller.")
        loader.apply(controller.study, force_update=True)
        self.update_panel()
        return len(loader)

    def _update_panel_after_legacy_result(self, result) -> None:
        if result is None:
            self.update_panel()

    def update_panel(self):
        """Refresh the sidebar and table contents from the controller."""
        if not hasattr(self, "controller"):
            return

        # Update Sidebar
        if hasattr(self, "sidebar"):
            self.sidebar.update_sidebar()

        # Update Table
        self.table.clearContents()
        self.table.blockSignals(True)  # Prevent itemChanged triggering during update
        self.table.setRowCount(0)

        queried_data_list = self._query_loaded_data_list_for_render()
        controller = self.controller
        if controller is None:
            data_list = []
        elif queried_data_list is None:
            try:
                data_list = run_legacy_controller_fallback(
                    self,
                    controller.get_loaded_data_list,
                )
            except LegacyControllerFallbackUnavailableError:
                logger.warning(
                    "Blocked stale dataset controller render fallback in real "
                    "Study context.",
                )
                data_list = []
        else:
            data_list = queried_data_list
        metadata_capability = get_command_capability(self, CommandName.UPDATE_METADATA)
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
                        editable=metadata_editable,
                        blocked_tooltip=metadata_block_reason,
                    ),
                )

                # Session
                self.table.setItem(
                    row,
                    2,
                    self._metadata_item(
                        data.get_session_name(),
                        editable=metadata_editable,
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

                # Events (Read-only)
                has_event = data.has_event()
                if has_event:
                    try:
                        if data.is_raw():
                            events, _ = data.get_event_list()
                            count = len(events)
                        else:
                            count = data.get_epochs_length()
                    except Exception:
                        logger.exception("Failed to get event count")
                        count = -1

                    count_str = "?" if count == -1 else str(count)
                    if data.is_labels_imported():
                        item_ev = QTableWidgetItem(f"Labels ({count_str})")
                        item_ev.setForeground(QBrush(QColor(Theme.TEXT_MUTED)))
                        item_ev.setToolTip(
                            "External labels are attached to this recording."
                        )
                    else:
                        item_ev = QTableWidgetItem(f"Events ({count_str})")
                        item_ev.setToolTip("Events detected in the recording.")
                else:
                    item_ev = QTableWidgetItem("No events")
                    item_ev.setForeground(QBrush(QColor(Theme.TEXT_SECONDARY)))
                    item_ev.setToolTip("No events or labels detected.")

                item_ev.setFlags(item_ev.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 6, item_ev)

                # Store raw object reference in first item
                item_name.setData(Qt.ItemDataRole.UserRole, data)

        self.table.blockSignals(False)
        self._fit_table_columns_to_viewport()
        self._schedule_table_column_fit()

    def _query_loaded_data_list_for_render(self) -> list[Any] | None:
        result = execute_application_command(
            self,
            QueryStateCommand(query="data_lists", include_objects=True),
            refresh=False,
        )
        if result is None:
            return None
        if result.failed:
            return []
        data_list = result.diagnostics.get("loaded_data_list")
        return list(data_list) if isinstance(data_list, list) else []

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
        metadata_capability = get_command_capability(self, CommandName.UPDATE_METADATA)
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

        if col == 1:  # Subject
            controller = getattr(self, "controller", None)
            result = None
            if controller is not None:
                result = execute_application_command(
                    self,
                    UpdateMetadataCommand(index=row, subject=new_value),
                )
                if result is None:
                    try:
                        run_legacy_controller_fallback(
                            self,
                            lambda: controller.update_metadata(row, subject=new_value),
                        )
                    except LegacyControllerFallbackUnavailableError as exc:
                        QMessageBox.warning(self, "Metadata blocked", str(exc))
                        self._update_panel_after_legacy_result(None)
                        return
                elif result.failed:
                    QMessageBox.warning(self, "Metadata blocked", result.message)
                    self.update_panel()
                    return
            self._update_panel_after_legacy_result(result)
        elif col == 2:  # Session
            controller = getattr(self, "controller", None)
            result = None
            if controller is not None:
                result = execute_application_command(
                    self,
                    UpdateMetadataCommand(index=row, session=new_value),
                )
                if result is None:
                    try:
                        run_legacy_controller_fallback(
                            self,
                            lambda: controller.update_metadata(row, session=new_value),
                        )
                    except LegacyControllerFallbackUnavailableError as exc:
                        QMessageBox.warning(self, "Metadata blocked", str(exc))
                        self._update_panel_after_legacy_result(None)
                        return
                elif result.failed:
                    QMessageBox.warning(self, "Metadata blocked", result.message)
                    self.update_panel()
                    return
            self._update_panel_after_legacy_result(result)
