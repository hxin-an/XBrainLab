from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.controller.dataset_controller import DatasetController
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.dashboard_panel.import_label import (
    EventFilterDialog,
    ImportLabelDialog,
    LabelMappingDialog,
)
from XBrainLab.ui.dashboard_panel.info import AggregateInfoPanel
from XBrainLab.ui.dashboard_panel.smart_parser import SmartParserDialog


class ChannelSelectionDialog(QDialog):
    def __init__(self, parent, data_list):
        super().__init__(parent)
        self.setWindowTitle("Channel Selection")
        self.resize(300, 400)
        self.data_list = data_list
        self.selected_channels = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Channel List
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.MultiSelection)

        # Get channels from first file
        if self.data_list:
            channels = self.data_list[0].get_mne().ch_names
            for ch in channels:
                item = QListWidgetItem(ch)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                self.list_widget.addItem(item)

        layout.addWidget(self.list_widget)

        # Select All / None
        btn_layout = QHBoxLayout()
        self.btn_all = QPushButton("Select All")
        self.btn_all.clicked.connect(lambda: self.set_all_checked(True))
        self.btn_none = QPushButton("Deselect All")
        self.btn_none.clicked.connect(lambda: self.set_all_checked(False))
        btn_layout.addWidget(self.btn_all)
        btn_layout.addWidget(self.btn_none)
        layout.addLayout(btn_layout)

        # Dialog Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def set_all_checked(self, checked):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item:
                item.setCheckState(state)

    def accept(self):
        selected_channels = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                selected_channels.append(item.text())

        if not selected_channels:
            QMessageBox.warning(self, "Warning", "Please select at least one channel.")
            return

        self.selected_channels = selected_channels
        super().accept()

    def get_result(self):
        return self.selected_channels


class DatasetPanel(QWidget):
    """
    Panel for managing the dataset.

    Features:
    - Import Data: Load EEG files (.set, .gdf).
    - Import Label: Assign labels to loaded data.
    - Smart Parse: Automatically extract subject/session info from filenames.
    - Channel Selection: Filter channels.
    - Table View: Display loaded files and their metadata.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.main_window = parent
        if parent and hasattr(parent, "study"):
            self.controller = DatasetController(parent.study)
        self.init_ui()

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

        # Context Menu
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        main_layout.addWidget(self.table, stretch=2)

        # --- Right Side: Info & Controls ---
        # --- Right Side: Info & Controls ---
        # --- Right Side: Info & Controls ---
        right_panel = QWidget()
        right_panel.setFixedWidth(260)  # Increased width
        # Slightly lighter gray with border
        right_panel.setObjectName("RightPanel")
        right_panel.setStyleSheet(
            """
            #RightPanel {
                background-color: #252526;
                border-left: 1px solid #3e3e42;
            }
            /* Minimal Group Style (No borders, no cards) */
            QGroupBox {
                background-color: transparent;
                border: none;
                margin-top: 15px;
                font-weight: bold;
                color: #808080; /* Subtle title */
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 0px;
                padding: 0 0px;
                color: #808080;
            }
            /* Flat, Minimal Buttons - Maximized Width */
            /* Flat, Minimal Buttons - Maximized Width */
            QPushButton {
                background-color: #3e3e42; /* Lighter gray (VS Code style) */
                border: none;
                border-radius: 4px;
                padding: 8px 12px;
                color: #ffffff; /* White text */
                font-weight: normal;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #4e4e52;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #007acc;
            }
        """
        )

        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(
            10, 20, 10, 20
        )  # Reduced margins for wider buttons

        # 0. Logo Removed

        # 1. Aggregate Info (Replaces Getting Started)
        self.info_panel = AggregateInfoPanel(self.main_window)
        # Style it to match the panel look (transparent background if needed, but
        # AggregateInfoPanel is a GroupBox)
        # We might need to adjust its style slightly or let it inherit.
        # AggregateInfoPanel sets its own title "Aggregate Information".

        # Remove the default border/background from AggregateInfoPanel to match our
        # minimal style
        self.info_panel.setStyleSheet(
            """
            QGroupBox {
                background-color: transparent;
                border: none;
                margin-top: 15px;
                font-weight: bold;
                color: #808080;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 0px;
                padding: 0 0px;
                color: #808080;
            }
            QLabel {
                color: #cccccc;
                font-weight: normal;
            }
        """
        )

        right_layout.addWidget(self.info_panel, stretch=1)

        # Add separator line with spacing to center it
        right_layout.addSpacing(10)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #3e3e42; border: none;")
        line.setFixedHeight(1)
        right_layout.addWidget(line)
        right_layout.addSpacing(10)
        # right_layout.addStretch() # Removed to align buttons up

        # 2. Dataset Actions Group
        actions_group = QGroupBox("OPERATIONS")
        actions_layout = QVBoxLayout(actions_group)
        actions_layout.setContentsMargins(0, 10, 0, 0)  # Maximize width

        self.import_btn = QPushButton("Import Data")
        self.import_btn.setToolTip("Load .set or .gdf files")
        self.import_btn.clicked.connect(self.import_data)
        actions_layout.addWidget(self.import_btn)

        self.import_label_btn = QPushButton("Import Label")
        self.import_label_btn.setToolTip("Import labels from external files")
        self.import_label_btn.clicked.connect(self.import_label)
        actions_layout.addWidget(self.import_label_btn)

        self.smart_parse_btn = QPushButton("Smart Parse Metadata")
        self.smart_parse_btn.setToolTip("Auto-extract Subject/Session from filenames")
        self.smart_parse_btn.clicked.connect(self.open_smart_parser)
        actions_layout.addWidget(self.smart_parse_btn)

        right_layout.addWidget(actions_group)

        # 3. EXECUTION Group
        exec_group = QGroupBox("EXECUTION")
        exec_layout = QVBoxLayout(exec_group)
        exec_layout.setContentsMargins(0, 10, 0, 0)

        # Channel Selection (Moved here, Green)
        self.chan_select_btn = QPushButton("Channel Selection")
        self.chan_select_btn.setToolTip("Select specific channels to keep")
        self.chan_select_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #1b5e20;
                color: #a5d6a7;
                border: 1px solid #2e7d32;
            }
            QPushButton:hover {
                background-color: #2e7d32;
                color: white;
            }
            QPushButton:disabled {
                background-color: #2d2d2d;
                color: #555555;
                border: 1px solid #3e3e42;
            }
        """
        )
        self.chan_select_btn.clicked.connect(self.open_channel_selection)
        exec_layout.addWidget(self.chan_select_btn)

        # 4. Danger Zone (Button Only)
        self.clear_btn = QPushButton("Clear Dataset")
        # Match Preprocess Reset Button Style
        self.clear_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #4a1818;
                color: #ff9999;
                border: 1px solid #802020;
            }
            QPushButton:hover {
                background-color: #602020;
            }
        """
        )
        self.clear_btn.setToolTip("Remove all loaded data")
        self.clear_btn.clicked.connect(self.clear_dataset)
        exec_layout.addWidget(self.clear_btn)

        right_layout.addWidget(exec_group)

        right_layout.addStretch()  # Push everything to top

        main_layout.addWidget(right_panel)

    def import_data(self):
        """
        Opens a file dialog to select and import EEG data files.
        """
        if not hasattr(self, "controller"):
            return

        if self.controller.is_locked():
            QMessageBox.warning(
                self,
                "Import Blocked",
                "Dataset is locked because Channel Selection (or other operations) has "
                "been applied.\n"
                "Please 'Clear Dataset' before importing new data.",
            )
            return

        filter_str = (
            "All Supported (*.set *.gdf *.fif *.edf *.bdf *.cnt *.vhdr);;"
            "EEGLAB (*.set);;"
            "GDF (*.gdf);;"
            "FIF (*.fif);;"
            "EDF/BDF (*.edf *.bdf);;"
            "Neuroscan CNT (*.cnt);;"
            "BrainVision (*.vhdr)"
        )
        self._import_files("Open EEG Data", filter_str)

    def _import_files(self, title, filter_str):
        filepaths, _ = QFileDialog.getOpenFileNames(self, title, "", filter_str)
        if not filepaths:
            return

        try:
            success_count, errors = self.controller.import_files(filepaths)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Import failed: {e}")
            return

        # Apply Changes
        if success_count > 0 and self.main_window:
            self.main_window.refresh_panels()

        # Report Errors
        if errors:
            error_msg = "\n".join(errors[:10])
            if len(errors) > 10:
                error_msg += f"\n...and {len(errors) - 10} more errors."

            QMessageBox.warning(
                self,
                "Import Warnings",
                f"Successfully loaded {success_count} files.\n\nFailed to load "
                f"{len(errors)} files:\n{error_msg}",
            )
        elif success_count == 0 and not errors:
            if filepaths:
                QMessageBox.information(
                    self, "Info", "No new files were loaded (duplicates ignored)."
                )

    def show_context_menu(self, pos):
        menu = QMenu(self)

        selected_rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if not selected_rows:
            return

        action_subject = menu.addAction("Set Subject for Selected")
        action_session = menu.addAction("Set Session for Selected")
        menu.addSeparator()
        action_remove = menu.addAction("Remove Selected Files")

        action = menu.exec(self.table.mapToGlobal(pos))

        if action == action_subject:
            self.batch_set_attribute(selected_rows, "Subject")
        elif action == action_session:
            self.batch_set_attribute(selected_rows, "Session")
        elif action == action_remove:
            self.remove_selected_files(selected_rows)

    def open_smart_parser(self):
        if not hasattr(self, "controller"):
            return

        if self.controller.is_locked():
            QMessageBox.warning(
                self,
                "Action Blocked",
                "Dataset is locked because Channel Selection (or other operations) has "
                "been applied.\n"
                "Please 'Clear Dataset' before modifying metadata.",
            )
            return

        if not self.controller.has_data():
            QMessageBox.warning(self, "Warning", "No data loaded to parse.")
            return

        filepaths = self.controller.get_filenames()

        dialog = SmartParserDialog(filepaths, self)
        if dialog.exec():
            results = dialog.get_results()

            count = self.controller.apply_smart_parse(results)

            self.update_panel()
            if self.main_window:
                self.main_window.refresh_panels()

            QMessageBox.information(
                self, "Success", f"Updated metadata for {count} files."
            )

    def open_channel_selection(self):
        if not hasattr(self, "controller"):
            return

        if not self.controller.has_data():
            QMessageBox.warning(self, "Warning", "No data loaded.")
            return

        # Check lock
        if self.controller.is_locked():
            QMessageBox.warning(
                self,
                "Action Blocked",
                "Dataset is locked because Channel Selection (or other operations) has "
                "been applied.\n"
                "Please 'Reset All Preprocessing' to undo Channel Selection or "
                "'Clear Dataset' to start over.",
            )
            return

        # Warning before proceeding
        reply = QMessageBox.question(
            self,
            "Warning",
            "Performing Channel Selection will modify the dataset.\n"
            "You can undo this later using 'Reset All Preprocessing'.\n\n"
            "Do you want to proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.No:
            return

        data_list = self.controller.get_loaded_data_list()

        dialog = ChannelSelectionDialog(self, data_list)
        if dialog.exec():
            result = dialog.get_result()
            if result:
                try:
                    self.controller.apply_channel_selection(result)
                    self.update_panel()
                    QMessageBox.information(
                        self, "Success", "Channel selection applied."
                    )
                except Exception as e:
                    QMessageBox.critical(
                        self, "Error", f"Channel selection failed: {e}"
                    )

    def import_label(self):
        """
        Imports labels from external files (e.g., .mat, .csv) and applies them to
        the loaded data.
        """
        try:
            if not hasattr(self, "controller"):
                return

            if self.controller.is_locked():
                QMessageBox.warning(
                    self,
                    "Import Blocked",
                    "Dataset is locked because Channel Selection (or other operations) "
                    "has been applied.\n"
                    "Please 'Clear Dataset' or 'Reset Preprocessing' before importing "
                    "labels.",
                )
                return

            # 1. Select Files
            target_files = self._get_target_files_for_import()
            if not target_files:
                return

            # 2. Select Label File
            dialog = ImportLabelDialog(self)
            if not dialog.exec():
                return
            label_map, mapping = dialog.get_results()
            if label_map is None:
                return

            # Check Mode (Timestamp vs Sequence)
            first_labels = next(iter(label_map.values()))
            is_timestamp_mode = (
                isinstance(first_labels, list)
                and len(first_labels) > 0
                and isinstance(first_labels[0], dict)
            )

            selected_event_names = None

            if not is_timestamp_mode:
                # Sequence Mode: Filter Events
                target_count = len(first_labels)
                selected_event_names = self._filter_events_for_import(
                    target_files, target_count
                )
                if selected_event_names is False:
                    return  # User cancelled

            # 4. Distribute Labels
            is_batch_mode = len(label_map) > 1
            count = 0

            if is_batch_mode:
                # Batch Mode
                data_filepaths = [d.get_filepath() for d in target_files]
                label_filenames = list(label_map.keys())

                mapping_dialog = LabelMappingDialog(
                    self, data_filepaths, label_filenames
                )
                if not mapping_dialog.exec():
                    return

                file_mapping = mapping_dialog.get_mapping()
                count = self.controller.apply_labels_batch(
                    target_files, label_map, file_mapping, mapping, selected_event_names
                )
            # Legacy Mode
            elif is_timestamp_mode:
                label_fname = next(iter(label_map.keys()))
                file_mapping = {d.get_filepath(): label_fname for d in target_files}
                count = self.controller.apply_labels_batch(
                    target_files, label_map, file_mapping, mapping, selected_event_names
                )
            else:
                labels = next(iter(label_map.values()))
                label_count = len(labels)

                total_epochs = sum(
                    self.controller.get_epoch_count(d, selected_event_names)
                    for d in target_files
                )

                if label_count == total_epochs and total_epochs > 0:
                    count = self.controller.apply_labels_legacy(
                        target_files, labels, mapping, selected_event_names
                    )
                else:
                    reply = QMessageBox.question(
                        self,
                        "Mismatch Detected",
                        f"Total labels ({label_count}) != Total epochs "
                        f"({total_epochs}).\n"
                        "Do you want to FORCE import?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    )

                    if reply == QMessageBox.StandardButton.Yes:
                        count = self.controller.apply_labels_legacy(
                            target_files,
                            labels,
                            mapping,
                            selected_event_names,
                            force_import=True,
                        )
                    else:
                        count = 0

            if count > 0:
                self.update_panel()
                QMessageBox.information(
                    self, "Success", f"Applied labels to {count} files."
                )

        except Exception as e:
            logger.error(f"Import label failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to import labels: {e}")

    def _get_target_files_for_import(self):
        selected_rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if not selected_rows:
            reply = QMessageBox.question(
                self,
                "Import Label",
                "No files selected. Apply labels to ALL loaded files?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                selected_rows = list(range(self.table.rowCount()))
            else:
                return []

        if not hasattr(self, "controller") or not self.controller.has_data():
            QMessageBox.warning(self, "Warning", "No data loaded.")
            return []

        data_list = self.controller.get_loaded_data_list()
        return [data_list[i] for i in selected_rows if i < len(data_list)]

    def _filter_events_for_import(self, target_files, target_count=None):
        """
        Returns:
            set: selected event names
            None: no filtering needed/applied
            False: user cancelled
        """
        raw_files_with_events = [
            d for d in target_files if d.is_raw() and d.has_event()
        ]
        if not raw_files_with_events:
            return None

        unique_names = set()
        for d in raw_files_with_events:
            try:
                _, ev_ids = d.get_raw_event_list()
                if ev_ids:
                    unique_names.update(ev_ids.keys())
            except Exception:  # noqa: PERF203
                pass

        if not unique_names:
            return None

        # Sort numerically if possible, else alphabetically
        try:
            sorted_names = sorted(
                unique_names, key=lambda x: int(x) if x.isdigit() else x
            )
        except Exception:
            sorted_names = sorted(unique_names)

        # Smart Filter Suggestion using Controller
        suggested_names = []
        if target_count is not None and len(raw_files_with_events) > 0:
            d = raw_files_with_events[0]
            suggested_ids = self.controller.get_smart_filter_suggestions(
                d, target_count
            )

            # Map IDs back to names
            _, ev_ids = d.get_raw_event_list()
            id_to_name = {v: k for k, v in ev_ids.items()}
            suggested_names = [id_to_name[i] for i in suggested_ids if i in id_to_name]

        filter_dialog = EventFilterDialog(self, sorted_names)

        # Apply suggestions
        if suggested_names:
            filter_dialog.set_selection(suggested_names)

        if filter_dialog.exec():
            selected = set(filter_dialog.get_selected_ids())
            logger.info(f"User selected event names: {selected}")
            return selected

        return False

    def batch_set_attribute(self, rows, attr_name):
        text, ok = QInputDialog.getText(
            self, f"Batch Set {attr_name}", f"Enter {attr_name}:"
        )
        if ok and text:
            for row in rows:
                if attr_name == "Subject":
                    self.controller.update_metadata(row, subject=text)
                elif attr_name == "Session":
                    self.controller.update_metadata(row, session=text)

            self.update_panel()

    def remove_selected_files(self, rows):
        if not hasattr(self, "controller"):
            return

        reply = QMessageBox.question(
            self,
            "Confirm Remove",
            f"Are you sure you want to remove {len(rows)} files?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.controller.remove_files(rows)
                self.update_panel()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to remove files: {e}")

    def apply_loader(self, loader):
        if self.main_window and hasattr(self.main_window, "study"):
            try:
                # Use force_update=True to allow updating the dataset (e.g. appending)
                # This will reset downstream steps (preprocess, etc.) which is
                # expected behavior
                loader.apply(self.controller.study, force_update=True)
                self.update_panel()
                QMessageBox.information(
                    self, "Success", f"Dataset updated. Total files: {len(loader)}"
                )
            except Exception as e:
                logger.error("Failed to apply data", exc_info=True)
                QMessageBox.critical(self, "Error", f"Failed to apply data: {e}")

    def clear_dataset(self):
        """Clear Dataset"""
        if self.message_box_confirm(
            "Confirm Clear", "Are you sure you want to clear the entire dataset?"
        ):
            self.clear_dataset_action()

    def message_box_confirm(self, title, text):
        reply = QMessageBox.question(
            self,
            title,
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def clear_dataset_action(self):
        try:
            self.controller.clean_dataset()
            self.update_panel()
            QMessageBox.information(self, "Success", "Dataset cleared.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to clear dataset: {e}")

    def update_panel(self):
        if not hasattr(self, "controller"):
            return

        data_list = self.controller.get_loaded_data_list()

        # Toggle Tips Visibility (User requested to keep it always visible)
        # if hasattr(self, 'tips_group'):
        #     self.tips_group.setVisible(not bool(data_list))

        # 1. Update Table
        if hasattr(self, "info_panel"):
            self.info_panel.update_info()

        self.table.clearContents()
        self.table.blockSignals(True)  # Prevent itemChanged triggering during update
        self.table.setRowCount(0)

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
                    # Get event count
                    try:
                        if data.is_raw():
                            events, _ = data.get_event_list()
                            count = len(events)
                        else:
                            count = data.get_epochs_length()
                    except Exception:
                        count = -1

                    count_str = "?" if count == -1 else str(count)
                    item_ev = QTableWidgetItem(f"Yes ({count_str})")

                    # Color logic: Green if imported labels, Default (Gray/Black) if
                    # original
                    if data.is_labels_imported():
                        logger.info(
                            f"File {data.get_filename()} has imported labels. "
                            "Setting green."
                        )
                        item_ev.setForeground(Qt.GlobalColor.green)
                    else:
                        # Use default color (or explicitly set to something neutral if
                        # needed)
                        # Setting to None usually resets to default theme color
                        # item_ev.setForeground(Qt.GlobalColor.white)

                        # Let's set it to white/black depending on theme?
                        # Better: clear the foreground brush to use default.
                        item_ev.setData(Qt.ItemDataRole.ForegroundRole, None)
                else:
                    item_ev = QTableWidgetItem("No")
                    item_ev.setForeground(Qt.GlobalColor.gray)

                item_ev.setFlags(item_ev.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 6, item_ev)

                # Store raw object reference in first item
                item_name.setData(Qt.ItemDataRole.UserRole, data)

        self.table.blockSignals(False)

        # Also update the global info panel
        # if hasattr(self.main_window, 'update_info_panel'):
        #     self.main_window.update_info_panel()

        # 2. Update Global Info Panel (Redundant, handled by refresh_panels or
        # individual updates)
        # if self.main_window and hasattr(self.main_window, 'update_info_panel'):
        #     self.main_window.update_info_panel()

        # 3. Update Channel Selection Button State
        if self.main_window and hasattr(self.main_window, "study"):
            is_locked = self.controller.is_locked()
            if hasattr(self, "chan_select_btn"):
                # self.chan_select_btn.setEnabled(not is_locked) # Keep enabled to
                # show warning
                if is_locked:
                    self.chan_select_btn.setToolTip(
                        "Dataset is locked. Click to see details."
                    )
                else:
                    self.chan_select_btn.setToolTip("Select specific channels to keep")

        # 4. Update Smart Parse Button State
        if self.main_window and hasattr(self.main_window, "study"):
            is_locked = self.controller.is_locked()
            if hasattr(self, "smart_parse_btn"):
                # self.smart_parse_btn.setEnabled(not is_locked) # Keep enabled to
                # show warning
                if is_locked:
                    self.smart_parse_btn.setToolTip(
                        "Dataset is locked. Click to see details."
                    )
                else:
                    self.smart_parse_btn.setToolTip(
                        "Auto-extract Subject/Session from filenames"
                    )

    def on_item_changed(self, item):
        row = item.row()
        col = item.column()

        name_item = self.table.item(row, 0)
        if name_item and name_item.data(Qt.ItemDataRole.UserRole):
            raw_data = name_item.data(Qt.ItemDataRole.UserRole)
        else:
            return

        if not raw_data:
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
