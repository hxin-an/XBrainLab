"""Action handler for dataset panel operations.

Provides logic for importing EEG data files, applying labels,
running smart parse, and managing event filtering.
"""

from PyQt6.QtWidgets import QFileDialog, QInputDialog, QMenu, QMessageBox

from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.dialogs.dataset import (
    EventFilterDialog,
    ImportLabelDialog,
    LabelMappingDialog,
    SmartParserDialog,
)


class DatasetActionHandler:
    """Helper class to handle complex actions for DatasetPanel.

    Decouples action logic (import, labeling, parsing) from the main
    ``DatasetPanel`` view class.

    Attributes:
        panel: The parent ``DatasetPanel`` instance.

    """

    def __init__(self, panel):
        """Initialize the action handler.

        Args:
            panel: The parent ``DatasetPanel`` that owns this handler.

        """
        self.panel = panel

    @property
    def controller(self):
        """DatasetController: The dataset controller from the parent panel."""
        return getattr(self.panel, "controller", None)

    @property
    def main_window(self):
        """QMainWindow: The application main window reference."""
        return getattr(self.panel, "main_window", None)

    def import_data(self):
        """Opens a file dialog to select and import EEG data files."""
        if self.controller.is_locked():
            QMessageBox.warning(
                self.panel,
                "Import Blocked",
                "Dataset is locked. Please 'Clear Dataset' before importing.",
            )
            return

        filter_str = (
            "All Supported (*.set *.gdf *.fif *.edf *.bdf *.cnt *.vhdr);;"
            "EEGLAB (*.set);;GDF (*.gdf);;FIF (*.fif);;"
            "EDF/BDF (*.edf *.bdf);;Neuroscan CNT (*.cnt);;BrainVision (*.vhdr)"
        )
        filepaths, _ = QFileDialog.getOpenFileNames(
            self.panel,
            "Open EEG Data",
            "",
            filter_str,
        )
        if filepaths:
            try:
                self.controller.import_files(filepaths)
            except Exception as e:
                QMessageBox.critical(self.panel, "Error", f"Import failed: {e}")

    def on_import_finished(self, success_count, errors):
        """Handle the import-finished callback from the controller.

        Updates the panel on success and shows warnings for any failures.

        Args:
            success_count: Number of files successfully imported.
            errors: List of error message strings for failed imports.

        """
        if success_count > 0:
            self.panel.update_panel()

        if errors:
            error_msg = "\n".join(errors[:10])
            if len(errors) > 10:
                error_msg += f"\n...and {len(errors) - 10} more errors."
            QMessageBox.warning(
                self.panel,
                "Import Warnings",
                f"Failed files:\n{error_msg}",
            )

    def open_smart_parser(self):
        """Open the smart-parser dialog to auto-extract metadata from filenames.

        Blocked if the dataset is locked or no data is loaded.
        """
        if self.controller.is_locked():
            QMessageBox.warning(self.panel, "Blocked", "Dataset is locked.")
            return

        if not self.controller.has_data():
            QMessageBox.warning(self.panel, "Warning", "No data loaded.")
            return

        filepaths = self.controller.get_filenames()
        dialog = SmartParserDialog(filepaths, self.panel)
        if dialog.exec():
            results = dialog.get_result()
            count = self.controller.apply_smart_parse(results)
            self.panel.update_panel()

            QMessageBox.information(self.panel, "Success", f"Updated {count} files.")

    def import_label(self):
        """Import external label files and apply them to loaded EEG data.

        Supports single-file, batch, and timestamp-based label mapping.
        Prompts the user for event filtering when applicable.
        """
        target_files = self._get_target_files_for_import()
        if not target_files:
            return

        dialog = ImportLabelDialog(self.panel)
        if not dialog.exec():
            return
        label_map, mapping = dialog.get_result()
        if label_map is None:
            return

        try:
            # Determine mapping mode
            first_labels = next(iter(label_map.values()))
            is_timestamp = (
                isinstance(first_labels, list)
                and len(first_labels) > 0
                and isinstance(first_labels[0], dict)
            )

            selected_event_names = None
            if not is_timestamp:
                target_count = len(first_labels)
                selected_event_names = self._filter_events_for_import(
                    target_files,
                    target_count,
                )
                if selected_event_names is False:
                    return

            count = 0
            if len(label_map) > 1:  # Batch
                data_paths = [d.get_filepath() for d in target_files]
                map_dlg = LabelMappingDialog(
                    self.panel,
                    data_paths,
                    list(label_map.keys()),
                )
                if map_dlg.exec():
                    file_map = map_dlg.get_mapping()
                    count = self.controller.apply_labels_batch(
                        target_files,
                        label_map,
                        file_map,
                        mapping,
                        selected_event_names,
                    )
            elif is_timestamp:  # Legacy
                label_fname = next(iter(label_map.keys()))
                file_map = {d.get_filepath(): label_fname for d in target_files}
                count = self.controller.apply_labels_batch(
                    target_files,
                    label_map,
                    file_map,
                    mapping,
                    selected_event_names,
                )
            else:  # Single Same Length
                labels = next(iter(label_map.values()))
                count = self.controller.apply_labels_legacy(
                    target_files,
                    labels,
                    mapping,
                    selected_event_names,
                )

            if count > 0:
                self.panel.update_panel()
                QMessageBox.information(
                    self.panel,
                    "Success",
                    f"Applied to {count} files.",
                )

        except Exception as e:
            logger.error("Import label error: %s", e, exc_info=True)
            QMessageBox.critical(self.panel, "Error", f"Failed: {e}")

    def _get_target_files_for_import(self):
        """Determine which data files should receive imported labels.

        If no rows are selected in the table, asks the user whether to
        apply labels to all files.

        Returns:
            list: A list of data objects for the targeted files,
                or an empty list if the operation is cancelled.

        """
        selected_rows = sorted(
            {index.row() for index in self.panel.table.selectedIndexes()},
        )
        if not selected_rows:
            reply = QMessageBox.question(
                self.panel,
                "Import Label",
                "No files selected. Apply to ALL?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                selected_rows = list(range(self.panel.table.rowCount()))
            else:
                return []

        data_list = self.controller.get_loaded_data_list()
        return [data_list[i] for i in selected_rows if i < len(data_list)]

    def _filter_events_for_import(self, target_files, target_count):
        """Show an event filter dialog for selecting which events to relabel.

        Args:
            target_files: List of data objects that contain raw events.
            target_count: Expected number of labels per event category.

        Returns:
            set | None | False: A set of selected event names, ``None`` if
                no filtering is needed, or ``False`` if the user cancelled.

        """
        raw_files = [d for d in target_files if d.is_raw() and d.has_event()]
        if not raw_files:
            return None

        unique = set()
        for d in raw_files:
            _, ev_ids = d.get_raw_event_list()
            unique.update(ev_ids.keys())

        if not unique:
            return None
        sorted_names = sorted(unique)

        # Suggestions?
        suggested = []
        if target_count and raw_files:
            s_ids = self.controller.get_smart_filter_suggestions(
                raw_files[0],
                target_count,
            )
            _, ev_ids = raw_files[0].get_raw_event_list()
            id_map = {v: k for k, v in ev_ids.items()}
            suggested = [id_map[i] for i in s_ids if i in id_map]

        dlg = EventFilterDialog(self.panel, sorted_names)
        if suggested:
            dlg.set_selection(suggested)

        if dlg.exec():
            return set(dlg.get_selected_ids())
        return False

    def show_context_menu(self, pos):
        menu = QMenu(self.panel)
        rows = sorted({i.row() for i in self.panel.table.selectedIndexes()})
        if not rows:
            return

        a_subj = menu.addAction("Set Subject")
        a_sess = menu.addAction("Set Session")
        menu.addSeparator()
        a_rem = menu.addAction("Remove Files")

        action = menu.exec(self.panel.table.mapToGlobal(pos))
        if action == a_subj:
            self._batch_set(rows, "Subject")
        elif action == a_sess:
            self._batch_set(rows, "Session")
        elif action == a_rem:
            self._remove_files(rows)

    def _batch_set(self, rows, attr):
        text, ok = QInputDialog.getText(self.panel, f"Set {attr}", f"Enter {attr}:")
        if ok and text:
            for r in rows:
                if attr == "Subject":
                    self.controller.update_metadata(r, subject=text)
                elif attr == "Session":
                    self.controller.update_metadata(r, session=text)
            self.panel.update_panel()

    def _remove_files(self, rows):
        if (
            QMessageBox.question(
                self.panel,
                "Confirm",
                f"Remove {len(rows)} files?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.controller.remove_files(rows)
            self.panel.update_panel()
