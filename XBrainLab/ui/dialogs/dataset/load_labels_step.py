"""Load Labels step helpers for the Data Import wizard."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from XBrainLab.ui.dialogs.dataset.wizard_state import WizardStateChange

if TYPE_CHECKING:
    from XBrainLab.ui.dialogs.dataset.wizard_host_protocol import (
        DataImportWizardStepHostProtocol,
    )
else:

    class DataImportWizardStepHostProtocol:
        pass


class LoadLabelsStepMixin(DataImportWizardStepHostProtocol):
    """Render and mutation helpers for the Load Labels step."""

    def _add_label_source_rows(self, layout: QVBoxLayout) -> None:
        carriers = self._label_carrier_preview_rows()
        folder_sources = [
            source
            for source in self._extra_label_sources
            if not self._looks_like_file(source)
        ]
        if not carriers and not self._extra_label_sources:
            layout.addWidget(
                self._empty_state("No nearby label/event source detected.")
            )
        for source in folder_sources:
            layout.addWidget(self._source_scope_row(source))
        for carrier in carriers:
            name = str(
                carrier.get("name")
                or Path(str(carrier.get("path", ""))).name
                or "Label source"
            )
            carrier_path = str(carrier.get("path") or "").strip()
            layout.addWidget(
                self._source_row(
                    name,
                    self._label_source_detail(carrier, carrier_path),
                    remove_button_text="Remove file",
                    remove_tooltip="Remove this label file from the import.",
                    remove_callback=(
                        lambda _checked=False, item=carrier_path: (
                            self._remove_label_carrier(item)
                        )
                    )
                    if carrier_path
                    else None,
                )
            )

        for source in self._extra_label_sources:
            if not self._looks_like_file(source):
                continue
            if self._source_has_visible_label_carrier(source):
                continue
            layout.addWidget(
                self._source_row(
                    *self._user_label_source_row(source),
                    remove_button_text="Remove file",
                    remove_tooltip="Remove this loaded label file from the import.",
                    remove_callback=lambda _checked=False, item=source: (
                        self._remove_label_source(item)
                    ),
                )
            )

    def _refresh_label_source_rows(self) -> None:
        self._clear_layout(self.label_source_rows_layout)
        self._add_label_source_rows(self.label_source_rows_layout)

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def _label_carrier_preview_rows(
        self,
        *,
        include_excluded: bool = False,
    ) -> list[dict[str, Any]]:
        carriers = self.preview.get("label_carrier_preview") or []
        if not isinstance(carriers, list) or not carriers:
            carriers = [
                {
                    "name": Path(str(carrier)).name,
                    "path": str(carrier),
                    "source_kind": "auto",
                }
                for carrier in self.scan_result.get("label_carriers", []) or []
            ]
        result: list[dict[str, Any]] = []
        if not isinstance(carriers, list):
            return result
        for carrier in carriers:
            if not isinstance(carrier, dict):
                continue
            carrier_path = str(carrier.get("path") or "").strip()
            if (
                carrier_path
                and not include_excluded
                and self._is_label_carrier_excluded(carrier_path)
            ):
                continue
            result.append(carrier)
        return result

    def _source_has_visible_label_carrier(self, source: str) -> bool:
        if not self._looks_like_file(source):
            return False
        source_key = self._normalized_label_source_key(source)
        if not source_key:
            return False
        for carrier in self._label_carrier_preview_rows():
            carrier_path = str(carrier.get("path") or "").strip()
            if (
                carrier_path
                and self._normalized_label_source_key(carrier_path) == source_key
            ):
                return True
            source_location = str(carrier.get("source_location") or "").strip()
            if (
                source_location
                and self._looks_like_file(source_location)
                and self._normalized_label_source_key(source_location) == source_key
            ):
                return True
        return False

    def _source_scope_row(self, source: str) -> QFrame:
        row = QFrame()
        row.setObjectName("DataImportSourceScopeRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(10)
        source_label = QLabel(f"Label source: {source}")
        source_label.setObjectName("DataImportSourceScopeText")
        source_label.setWordWrap(True)
        source_label.setToolTip(source)
        source_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(source_label, stretch=1)
        remove_btn = QPushButton("Remove all from this folder")
        remove_btn.setObjectName("DataImportTertiaryButton")
        remove_btn.setToolTip("Remove this folder and all label files it contributed.")
        remove_btn.clicked.connect(
            lambda _checked=False, item=source: self._remove_label_source(item)
        )
        layout.addWidget(remove_btn)
        return row

    def _source_row(
        self,
        title: str,
        detail: str,
        *,
        remove_button_text: str = "Remove",
        remove_tooltip: str = "Remove this loaded label source from the import.",
        remove_callback: Any | None = None,
    ) -> QFrame:
        row = QFrame()
        row.setObjectName("DataImportSourceRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("DataImportSourceTitle")
        detail_label = QLabel(detail)
        detail_label.setObjectName("DataImportSourceDetail")
        detail_label.setWordWrap(True)
        detail_label.setToolTip(detail)
        detail_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        text_layout.addWidget(title_label)
        if detail:
            text_layout.addWidget(detail_label)
        layout.addLayout(text_layout, stretch=1)
        if remove_callback is not None:
            remove_btn = QPushButton(remove_button_text)
            remove_btn.setObjectName("DataImportTertiaryButton")
            remove_btn.setToolTip(remove_tooltip)
            remove_btn.clicked.connect(remove_callback)
            layout.addWidget(remove_btn)
        return row

    def _remove_label_source(self, source: str) -> None:
        source_key = self._normalized_label_source_key(source)
        if not source_key:
            return
        before = list(self._extra_label_sources)
        self._extra_label_sources = [
            item
            for item in self._extra_label_sources
            if self._normalized_label_source_key(item) != source_key
        ]
        if self._extra_label_sources == before:
            return
        self._exclude_carriers_from_source(source)
        self._skip_labels = False
        self._refresh_label_source_rows()
        self._notify_wizard_state_changed(WizardStateChange.LABEL_SOURCES)
        self.label_sources_label.setText("Removed label source.")
        self.label_sources_label.setVisible(True)
        self._sync_scroll_policy()

    def _remove_label_carrier(self, carrier_path: str) -> None:
        carrier = str(carrier_path).strip()
        if not carrier:
            return
        changed = False
        if self._wizard_state.label_sources.exclude_carrier(carrier):
            changed = True
        if self._remove_empty_label_sources_after_carrier_exclusion(carrier):
            changed = True
        if not changed:
            return
        self._skip_labels = False
        self._refresh_label_source_rows()
        self._notify_wizard_state_changed(WizardStateChange.LABEL_SOURCES)
        self.label_sources_label.setText("Removed label file.")
        self.label_sources_label.setVisible(True)
        self._sync_scroll_policy()

    def _remove_empty_label_sources_after_carrier_exclusion(
        self,
        carrier_path: str,
    ) -> bool:
        if not self._extra_label_sources:
            return False
        removed_key = self._normalized_label_source_key(carrier_path)
        if not removed_key:
            return False
        before = list(self._extra_label_sources)
        kept_sources: list[str] = []
        for source in self._extra_label_sources:
            if not self._label_source_covers_carrier(source, carrier_path):
                kept_sources.append(source)
                continue
            if self._looks_like_file(source):
                continue
            if self._label_source_has_other_active_carriers(source, removed_key):
                kept_sources.append(source)
        self._extra_label_sources = kept_sources
        return self._extra_label_sources != before

    def _label_source_covers_carrier(self, source: str, carrier_path: str) -> bool:
        source_key = self._normalized_label_source_key(source)
        carrier_key = self._normalized_label_source_key(carrier_path)
        if not source_key or not carrier_key:
            return False
        if self._looks_like_file(source):
            return source_key == carrier_key
        carrier_parent_key = self._normalized_label_source_key(
            Path(carrier_path).parent.as_posix()
        )
        return source_key == carrier_parent_key

    def _label_source_has_other_active_carriers(
        self,
        source: str,
        removed_key: str,
    ) -> bool:
        for carrier in self._label_carrier_preview_rows(include_excluded=True):
            carrier_path = str(carrier.get("path") or "").strip()
            carrier_key = self._normalized_label_source_key(carrier_path)
            if not carrier_path or carrier_key == removed_key:
                continue
            if self._is_label_carrier_excluded(carrier_path):
                continue
            if self._carrier_belongs_to_source(carrier, source):
                return True
        return False

    def _exclude_carriers_from_source(self, source: str) -> None:
        for carrier in self._label_carrier_preview_rows():
            carrier_path = str(carrier.get("path") or "").strip()
            if carrier_path and self._carrier_belongs_to_source(carrier, source):
                self._remove_label_carrier_without_refresh(carrier_path)

    def _remove_label_carrier_without_refresh(self, carrier_path: str) -> None:
        carrier = str(carrier_path).strip()
        if carrier:
            self._wizard_state.label_sources.exclude_carrier(carrier)

    def _refresh_load_labels_static_state(self) -> None:
        has_bids_events = self._has_bids_events()
        if hasattr(self, "label_sources_card_title_label"):
            self.label_sources_card_title_label.setText(
                "BIDS events detected" if has_bids_events else "Label files"
            )
        if hasattr(self, "label_detection_label"):
            self.label_detection_label.setText(self._label_detection_text())
        if hasattr(self, "add_label_file_btn"):
            self.add_label_file_btn.setText(
                "Add extra label file" if has_bids_events else "Load label file"
            )
        if hasattr(self, "add_label_folder_btn"):
            self.add_label_folder_btn.setText(
                "Add extra label folder" if has_bids_events else "Load label folder"
            )
        if hasattr(self, "skip_labels_btn"):
            self.skip_labels_btn.setVisible(not has_bids_events)
        if hasattr(self, "label_source_mode_combo"):
            loaded_label = (
                "BIDS events.tsv" if has_bids_events else "Loaded label files"
            )
            for index in range(self.label_source_mode_combo.count()):
                if self.label_source_mode_combo.itemData(index) == "loaded_label_files":
                    self.label_source_mode_combo.setItemText(index, loaded_label)

    def _select_loaded_label_source_if_available(self) -> None:
        if (
            not hasattr(self, "label_source_mode_combo")
            or not self._label_carrier_items
        ):
            return
        self._set_combo_current_data(
            self.label_source_mode_combo,
            "loaded_label_files",
        )

    @staticmethod
    def _empty_state(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("DataImportEmptyState")
        label.setWordWrap(True)
        return label

    @staticmethod
    def _inline_notice(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("DataImportInlineNotice")
        label.setWordWrap(True)
        return label

    @staticmethod
    def _label_source_detail(carrier: dict[str, Any], carrier_path: str) -> str:
        source_kind = str(carrier.get("source_kind") or "").strip().lower()
        source_location = str(carrier.get("source_location") or "").strip()
        if source_location:
            location_type = "file" if Path(source_location).suffix else "folder"
            action = "Added from" if source_kind == "user_added" else "Found in"
            return f"{action} {location_type}: {source_location}"
        if carrier_path:
            parent = Path(carrier_path).parent.as_posix()
            return f"Found in folder: {parent}"
        return ""

    @staticmethod
    def _looks_like_file(path: str) -> bool:
        return bool(Path(path).suffix)
