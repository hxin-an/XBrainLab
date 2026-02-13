from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
)

from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.core.base_panel import BasePanel
from XBrainLab.ui.core.observer_bridge import QtObserverBridge
from XBrainLab.ui.styles.theme import Theme

from .actions import DatasetActionHandler
from .sidebar import DatasetSidebar


class DatasetPanel(BasePanel):
    """
    Panel for managing the dataset loading and metadata.
    Features: Import Data, Import Label, Smart Parse, Channel Selection, Table View.
    Integrates with `DatasetController`.
    """

    def __init__(self, controller=None, parent=None):
        # 1. Controller Resolution (Legacy/Test support)
        if controller is None and parent and hasattr(parent, "study"):
            controller = parent.study.get_controller("dataset")

        # 2. Base Init (sets self.controller, self.main_window)
        super().__init__(parent=parent, controller=controller)

        # 3. Helpers
        self.action_handler = DatasetActionHandler(self)

        # 4. Bridge & UI Setup (Explicit call required by new BasePanel contract)
        self._setup_bridges()
        self.init_ui()

    def _setup_bridges(self):
        if self.controller:
            self.bridge = QtObserverBridge(self.controller, "data_changed", self)
            self.bridge.connect_to(self.update_panel)

            self.bridge_import = QtObserverBridge(
                self.controller, "import_finished", self
            )
            self.bridge_import.connect_to(self.action_handler.on_import_finished)

    def init_ui(self):
        # Main Layout: Horizontal Split (Table | Info & Controls)
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Left Side: File List Table ---
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["Filename", "Subject", "Session", "Channels", "Sfreq", "Epochs", "Events"]
        )
        header = self.table.horizontalHeader()
        if header:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )  # Allow multiple selection
        self.table.itemChanged.connect(self.on_item_changed)

        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(
            self.action_handler.show_context_menu
        )

        main_layout.addWidget(self.table, stretch=2)

        # --- Right Side: Sidebar ---
        self.sidebar = DatasetSidebar(self, self)
        main_layout.addWidget(self.sidebar, stretch=0)

    def apply_loader(self, loader):
        if self.main_window and hasattr(self.main_window, "study"):
            try:
                # Use force_update=True to allow updating the dataset (e.g. appending)
                loader.apply(self.controller.study, force_update=True)
                self.update_panel()
                QMessageBox.information(
                    self, "Success", f"Dataset updated. Total files: {len(loader)}"
                )
            except Exception as e:
                logger.error("Failed to apply data", exc_info=True)
                QMessageBox.critical(self, "Error", f"Failed to apply data: {e}")

    def update_panel(self):
        if not hasattr(self, "controller"):
            return

        # Update Sidebar
        if hasattr(self, "sidebar"):
            self.sidebar.update_sidebar()

        # Update Table
        self.table.clearContents()
        self.table.blockSignals(True)  # Prevent itemChanged triggering during update
        self.table.setRowCount(0)

        data_list = self.controller.get_loaded_data_list()

        if data_list:
            self.table.setRowCount(len(data_list))
            for row, data in enumerate(data_list):
                # Filename (Read-only)
                item_name = QTableWidgetItem(data.get_filename())
                item_name.setFlags(item_name.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 0, item_name)

                # Subject (Editable)
                self.table.setItem(row, 1, QTableWidgetItem(data.get_subject_name()))

                # Session (Editable)
                self.table.setItem(row, 2, QTableWidgetItem(data.get_session_name()))

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
                    item_ev = QTableWidgetItem(f"Yes ({count_str})")

                    if data.is_labels_imported():
                        item_ev.setForeground(QBrush(QColor(Theme.ACCENT_SUCCESS)))
                    else:
                        item_ev.setData(Qt.ItemDataRole.ForegroundRole, None)
                else:
                    item_ev = QTableWidgetItem("No")
                    item_ev.setForeground(QBrush(QColor(Theme.TEXT_SECONDARY)))

                item_ev.setFlags(item_ev.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 6, item_ev)

                # Store raw object reference in first item
                item_name.setData(Qt.ItemDataRole.UserRole, data)

        self.table.blockSignals(False)

    def on_item_changed(self, item):
        row = item.row()
        col = item.column()

        name_item = self.table.item(row, 0)
        if name_item and name_item.data(Qt.ItemDataRole.UserRole):
            pass  # We have data
        else:
            return

        new_value = item.text()

        if col == 1:  # Subject
            if hasattr(self, "controller"):
                self.controller.update_metadata(row, subject=new_value)
            self.update_panel()  # Refresh aggregates
        elif col == 2:  # Session
            if hasattr(self, "controller"):
                self.controller.update_metadata(row, session=new_value)
            self.update_panel()  # Refresh aggregates
