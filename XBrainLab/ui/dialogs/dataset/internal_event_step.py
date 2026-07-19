"""Internal EEG event step helpers for the Data Import wizard."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application.data_interpretation_pairing import (
    resolve_label_file_pairing,
)

if TYPE_CHECKING:
    from XBrainLab.ui.dialogs.dataset.wizard_host_protocol import (
        DataImportWizardStepHostProtocol,
    )
else:

    class DataImportWizardStepHostProtocol:
        pass


class InternalEventStepMixin(DataImportWizardStepHostProtocol):
    """Render and model helpers for labels stored inside EEG files."""

    def _build_internal_event_rules_view(self) -> None:
        self.event_group.setTitle("")
        group_title = QLabel("Labels inside EEG files")
        group_title.setObjectName("DataImportInternalGroupTitle")
        self.event_layout.insertWidget(0, group_title)
        self._event_detail_widgets.append(group_title)

        candidate_rows = self._internal_candidate_label_event_rows()
        not_used_rows = self._internal_not_used_event_rows()

        summary = QLabel(self._internal_event_summary_text())
        summary.setObjectName("DataImportInternalSummaryLine")
        summary.setWordWrap(True)
        self.event_layout.insertWidget(1, summary)
        self._event_detail_widgets.append(summary)

        if candidate_rows:
            self._add_event_section_spacing(7)
            self._add_event_section_title("Suggested training labels")
            candidate_help = self._event_section_help(
                "Confirm which EEG events become training labels.",
            )
            self._ensure_class_name_items_from_event_rows(candidate_rows)
            candidate_table = self._internal_training_labels_table(candidate_rows)
            self.event_layout.addWidget(candidate_table)
            self._event_detail_widgets.extend([candidate_help, candidate_table])
            self.event_tree.setVisible(False)
        else:
            self.event_tree.setVisible(bool(self._event_role_items))

        not_used_rows = self._internal_not_used_event_rows()
        if not_used_rows:
            self._add_event_section_spacing(9)
            self._add_event_section_title("Other EEG events")
            other_help = self._event_section_help(
                "These events are available in the EEG files but are not currently "
                "used as class labels.",
            )
            not_used_table = self._internal_other_events_table(not_used_rows)
            self.event_layout.addWidget(not_used_table)
            self._event_detail_widgets.extend([other_help, not_used_table])
        if candidate_rows or not_used_rows:
            self._add_event_section_spacing(7)
            selection_preview = QLabel(
                self._internal_event_selection_preview_text(
                    candidate_rows,
                    not_used_rows,
                )
            )
            selection_preview.setObjectName("DataImportInternalCheckLine")
            selection_preview.setWordWrap(True)
            self.event_layout.addWidget(selection_preview)
            self._event_detail_widgets.append(selection_preview)
        self.event_group.setMaximumHeight(16777215)

    def _add_event_section_spacing(self, height: int) -> QWidget:
        spacer = QWidget()
        spacer.setObjectName("DataImportEventSectionSpacer")
        spacer.setFixedHeight(max(height, 0))
        self.event_layout.addWidget(spacer)
        self._event_detail_widgets.append(spacer)
        return spacer

    def _add_event_section_title(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("DataImportSourceTitle")
        label.setWordWrap(False)
        self.event_layout.addWidget(label)
        self._event_detail_widgets.append(label)
        return label

    def _event_section_help(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("DataImportSourceDetail")
        label.setWordWrap(True)
        self.event_layout.addWidget(label)
        return label

    def _internal_training_labels_table(
        self,
        rows: list[dict[str, str]],
    ) -> QWidget:
        table = QFrame()
        table.setObjectName("DataImportInternalLabelsTable")
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        table.setMinimumHeight(42 + max(len(rows), 1) * 38)
        grid = QGridLayout(table)
        grid.setContentsMargins(13, 12, 13, 13)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(11)
        headers = [
            "Event",
            "Use as",
            "Suggestion evidence",
            "Count / coverage",
            "Class name",
            "",
        ]
        for column, header in enumerate(headers):
            label = QLabel(header)
            label.setObjectName("DataImportPairingHeaderLabel")
            grid.addWidget(label, 0, column)

        item_by_code = {code: item for item, code, _original in self._class_map_items}
        for row_index, row in enumerate(rows, start=1):
            code = str(row.get("code") or "").strip()
            self._grid_text(grid, row_index, 0, code, primary=True)
            self._grid_text(grid, row_index, 1, str(row.get("use_as") or "Class label"))
            self._grid_text(
                grid,
                row_index,
                2,
                str(row.get("evidence") or "Suggested by event pattern"),
            )
            self._grid_text(grid, row_index, 3, str(row.get("coverage") or ""))
            item = item_by_code.get(code)
            if item is not None:
                selector = self._clone_class_map_selector(item, table)
                selector.setMinimumHeight(28)
                grid.addWidget(selector, row_index, 4)
            else:
                self._grid_text(grid, row_index, 4, "")
            button = self._internal_event_action_button(
                "Not a label",
                code,
                "not a label",
                table,
            )
            grid.addWidget(button, row_index, 5)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 4)
        grid.setColumnStretch(3, 2)
        grid.setColumnStretch(4, 3)
        grid.setColumnStretch(5, 0)
        return table

    def _internal_other_events_table(self, rows: list[dict[str, str]]) -> QWidget:
        table = QFrame()
        table.setObjectName("DataImportInternalOtherEventsTable")
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        table.setMinimumHeight(42 + max(len(rows), 1) * 36)
        grid = QGridLayout(table)
        grid.setContentsMargins(13, 12, 13, 13)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(10)
        headers = [
            "Event",
            "Suggested use",
            "Suggestion evidence / reason",
            "Count / coverage",
            "",
        ]
        for column, header in enumerate(headers):
            label = QLabel(header)
            label.setObjectName("DataImportPairingHeaderLabel")
            grid.addWidget(label, 0, column)

        for row_index, row in enumerate(rows, start=1):
            code = str(row.get("code") or "").strip()
            self._grid_text(grid, row_index, 0, code, primary=True)
            self._grid_text(grid, row_index, 1, str(row.get("use_as") or "Ignore"))
            self._grid_text(grid, row_index, 2, str(row.get("reason") or ""))
            self._grid_text(grid, row_index, 3, str(row.get("coverage") or ""))
            button = self._internal_event_action_button(
                "Use as label",
                code,
                "class label",
                table,
            )
            grid.addWidget(button, row_index, 4)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 4)
        grid.setColumnStretch(3, 2)
        grid.setColumnStretch(4, 0)
        return table

    def _grid_text(
        self,
        grid: QGridLayout,
        row: int,
        column: int,
        text: str,
        *,
        primary: bool = False,
    ) -> QLabel:
        label = QLabel(text)
        label.setObjectName(
            "DataImportPairingFile" if primary else "DataImportSourceDetail"
        )
        label.setWordWrap(column in {1, 2})
        label.setMinimumHeight(24)
        grid.addWidget(label, row, column)
        return label

    def _internal_event_action_button(
        self,
        text: str,
        code: str,
        role: str,
        parent: QWidget,
    ) -> QPushButton:
        button = QPushButton(text, parent)
        button.setObjectName("DataImportInlineAction")
        button.setProperty("event_code", code)
        button.setFlat(True)
        button.setMinimumHeight(24)
        button.setMinimumWidth(104)
        button.setToolTip(
            "Move this EEG event into training labels."
            if role == "class label"
            else "Keep this EEG event, but do not use it as a training label."
        )
        button.clicked.connect(
            lambda _checked=False, event_code=code, event_role=role: (
                self._set_internal_event_role(event_code, event_role)
            )
        )
        return button

    def _set_internal_event_role(self, code: str, role: str) -> None:
        code = str(code).strip()
        if not code:
            return
        self._remember_internal_class_name_edits()
        self._internal_event_user_roles[code] = role
        self._refresh_event_detail_view()
        if hasattr(self, "event_group"):
            self.event_group.setVisible(True)
        if hasattr(self, "rule_status_label"):
            self.rule_status_label.setText(self._label_rule_status_text())
        self._sync_scroll_policy()

    def _remember_internal_class_name_edits(self) -> None:
        for tree_item, code, _original in self._class_map_items:
            value = self._class_map_item_text(tree_item).strip()
            if value:
                self._internal_class_name_edits[code] = value

    def _internal_event_check_text(
        self,
        candidate_rows: list[dict[str, str]],
        not_used_rows: list[dict[str, str]],
    ) -> str:
        label_count = len(candidate_rows)
        other_count = len(not_used_rows)
        if label_count:
            label_text = f"{label_count} EEG event(s) will be used as training labels."
        else:
            label_text = "No EEG events are currently selected as training labels."
        other_text = (
            f"{other_count} other EEG event(s) are kept out of training labels."
            if other_count
            else "No other EEG events are listed for this preview."
        )
        return f"{label_text} {other_text}"

    def _internal_event_selection_preview_text(
        self,
        candidate_rows: list[dict[str, str]],
        not_used_rows: list[dict[str, str]],
    ) -> str:
        training = self._event_code_list_text(row["code"] for row in candidate_rows)
        excluded = self._event_code_list_text(row["code"] for row in not_used_rows)
        if training and excluded:
            return f"Selection preview: train on {training}; not used: {excluded}."
        if training:
            return f"Selection preview: train on {training}."
        if excluded:
            return (
                f"Selection preview: no training labels selected; not used: {excluded}."
            )
        return "Selection preview: no EEG events are selected yet."

    @staticmethod
    def _event_code_list_text(codes: Iterable[str], *, limit: int = 6) -> str:
        values = [str(code).strip() for code in codes if str(code).strip()]
        if not values:
            return ""
        if len(values) <= limit:
            return ", ".join(values)
        visible = ", ".join(values[:limit])
        return f"{visible} +{len(values) - limit} more"

    def _build_bids_source_card(self, layout: QVBoxLayout) -> None:
        layout.addWidget(
            self._inline_notice(
                "BIDS EEG files and events.tsv were detected. XBrainLab uses "
                "this as an EEG task import path, not a full BIDS validator."
            )
        )
        layout.addWidget(
            self._event_rules_table(
                ["Item", "Detected", "Import behavior"],
                self._bids_source_rows(),
            )
        )

    def _bids_label_source_summary(self) -> QWidget:
        return self._event_rules_table(
            ["Item", "Detected", "Import behavior"],
            self._bids_label_source_rows(),
        )

    def _build_bids_metadata_card(self, layout: QVBoxLayout) -> None:
        layout.addWidget(
            self._inline_notice(
                "Subject, session, task, and run were read from BIDS-style "
                "entities. Participants metadata is shown when available."
            )
        )
        layout.addWidget(
            self._event_rules_table(
                ["Item", "Detected", "Recipe behavior"],
                self._bids_metadata_rows(),
            )
        )

    def _bids_source_rows(self) -> list[tuple[str, str, str]]:
        return [
            (
                "BIDS folder",
                self._bids_entities_summary_text(),
                "All detected EEG runs in the selected folder are included.",
            ),
            (
                "events.tsv",
                self._bids_event_count_text(),
                "Used as the default label and timing source.",
            ),
            (
                "Boundary",
                "Not a full BIDS validator",
                "Review labels, metadata, and events before applying.",
            ),
        ]

    def _bids_label_source_rows(self) -> list[tuple[str, str, str]]:
        carriers = self._bids_event_carriers()
        events = self._bids_event_count_text()
        matched = (
            self._matched_eeg_pair_count()
            if self._label_carrier_items
            else self._preview_matched_eeg_pair_count()
        )
        total = len(self._selected_eeg_file_names())
        if not carriers:
            return [
                (
                    "events.tsv",
                    "Not detected",
                    "Required for this BIDS import. Use Import folder for "
                    "non-BIDS labels.",
                )
            ]
        return [
            (
                "events.tsv",
                events,
                "Automatically loaded from the BIDS folder.",
            ),
            (
                "EEG pairing",
                f"{matched}/{total} EEG files paired",
                "Adjust only rows that are matched incorrectly.",
            ),
            (
                "events.json",
                self._bids_events_json_text(),
                "Used for class descriptions when present; otherwise class names "
                "need confirmation.",
            ),
        ]

    def _bids_metadata_rows(self) -> list[tuple[str, str, str]]:
        return [
            (
                "Entities",
                self._bids_entities_summary_text(),
                "Saved as subject/session/task/run metadata.",
            ),
            (
                "participants.tsv",
                self._bids_participants_text(),
                "Used to supplement participants when available.",
            ),
            (
                "Smart Parse",
                "Secondary adjustment",
                "Use only when BIDS-style entities need manual correction.",
            ),
        ]

    def _bids_entities_summary_text(self) -> str:
        parts: list[str] = []
        for key, label in (
            ("subjects", "subject"),
            ("sessions", "session"),
            ("tasks", "task"),
            ("runs", "run"),
        ):
            values = self._bids_values(key)
            if values:
                parts.append(f"{len(values)} {label}")
        return " · ".join(parts) or "Entities pending"

    def _bids_event_count_text(self) -> str:
        events = self._bids_values("events_files")
        if not events:
            return "No events.tsv"
        file_word = "file" if len(events) == 1 else "files"
        return f"{len(events)} events.tsv {file_word}"

    def _bids_participants_text(self) -> str:
        bids = self._bids_payload()
        for key in ("participants_tsv", "participants_file"):
            value = str(bids.get(key) or "").strip()
            if value:
                return Path(value).name
        if bool(bids.get("has_participants_tsv")):
            return "Found"
        return "Not found"

    def _bids_events_json_text(self) -> str:
        carriers = self._bids_event_carriers()
        found = any(
            carrier.get("events_json")
            or carrier.get("events_json_path")
            or carrier.get("has_events_json")
            for carrier in carriers
        )
        if found:
            return "Found"
        warnings = " ".join(
            str(item)
            for carrier in carriers
            for item in carrier.get("warnings", []) or []
        ).lower()
        if "events.json" in warnings:
            return "Missing"
        return "Not detected"

    def _preview_matched_eeg_pair_count(self) -> int:
        pairing = resolve_label_file_pairing(
            self._bids_event_carriers(),
            self._selected_eeg_file_names(),
        )
        return pairing.matched_count

    def _bids_payload(self) -> dict[str, Any]:
        bids = self.scan_result.get("bids") or {}
        return bids if isinstance(bids, dict) else {}

    def _bids_values(self, key: str) -> list[str]:
        values = self._bids_payload().get(key) or []
        if not isinstance(values, list):
            return []
        return [str(value).strip() for value in values if str(value).strip()]

    def _is_bids_source(self) -> bool:
        source_kind = str(self.scan_result.get("source_kind") or "").lower()
        return source_kind == "bids" and bool(self._bids_payload().get("is_bids"))

    def _has_bids_events(self) -> bool:
        return self._is_bids_source() and bool(self._bids_event_carriers())

    def _bids_event_carriers(self) -> list[dict[str, Any]]:
        carriers: list[dict[str, Any]] = []
        preview_carriers = self.preview.get("label_carrier_preview") or []
        if isinstance(preview_carriers, list):
            carriers.extend(
                dict(item)
                for item in preview_carriers
                if isinstance(item, dict)
                and str(item.get("format") or "") == "BIDS events"
            )
        carriers.extend(
            dict(original)
            for _item, original in self._label_carrier_items
            if str(original.get("format") or "") == "BIDS events"
        )
        unique: dict[str, dict[str, Any]] = {}
        for carrier in carriers:
            key = str(carrier.get("path") or carrier.get("name") or "").strip()
            if key and self._is_label_carrier_excluded(key):
                continue
            if key and key not in unique:
                unique[key] = carrier
        return list(unique.values())

    def _event_rules_table(
        self,
        headers: list[str],
        rows: list[tuple[str, ...]],
    ) -> QWidget:
        table = QFrame()
        table.setObjectName("DataImportEventRulesTable")
        table.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        table.setMinimumHeight(32 + max(len(rows), 1) * 24)
        grid = QGridLayout(table)
        grid.setContentsMargins(10, 7, 10, 8)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(5)
        for column, header in enumerate(headers):
            label = QLabel(header)
            label.setObjectName("DataImportPairingHeaderLabel")
            grid.addWidget(label, 0, column)
        for row_index, row in enumerate(rows, start=1):
            for column, value in enumerate(row):
                label = QLabel(value)
                label.setObjectName(
                    "DataImportPairingFile" if column == 0 else "DataImportSourceDetail"
                )
                label.setWordWrap(column == len(row) - 1)
                label.setMinimumHeight(18)
                grid.addWidget(label, row_index, column)
        for column in range(len(headers)):
            grid.setColumnStretch(column, 2 if column == len(headers) - 1 else 1)
        return table

    def _build_internal_event_card(self, layout: QVBoxLayout) -> None:
        self.internal_event_status_label = self._wrapped_label(
            self._internal_event_status_text()
        )
        layout.addWidget(self.internal_event_status_label)

    def _build_bids_event_review_card(self, layout: QVBoxLayout) -> None:
        intro = QLabel(self._bids_event_review_intro_text())
        intro.setObjectName("DataImportSourceDetail")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        rows = self._bids_event_review_rows()
        if rows:
            layout.addWidget(
                self._event_rules_table(
                    ["Item", "Detected", "Review note"],
                    rows,
                )
            )
        else:
            layout.addWidget(
                self._empty_state(
                    "No BIDS events.tsv carrier is available in this preview."
                )
            )
        self._bids_event_review_intro_label = intro

    def _bids_event_review_intro_text(self) -> str:
        context = self._bids_context_text()
        if context:
            return f"Review BIDS event timing and class fields for {context}."
        return "Review BIDS event timing and class fields before import."

    def _bids_event_review_rows(self) -> list[tuple[str, str, str]]:
        rows: list[tuple[str, str, str]] = []
        carriers = [
            original
            for _item, original in self._label_carrier_items
            if str(original.get("format") or "") == "BIDS events"
        ]
        if not carriers:
            return rows
        columns = self._unique_values(
            column
            for carrier in carriers
            for column in carrier.get("bids_event_columns", []) or []
        )
        label_fields = self._unique_values(
            str(carrier.get("selected_label_field") or "").strip()
            for carrier in carriers
            if str(carrier.get("selected_label_field") or "").strip()
        )
        start_fields = self._unique_values(
            str(carrier.get("selected_anchor") or "").strip()
            for carrier in carriers
            if str(carrier.get("selected_anchor") or "").strip()
        )
        duration_fields = self._unique_values(
            str(carrier.get("selected_duration_field") or "").strip()
            for carrier in carriers
            if str(carrier.get("selected_duration_field") or "").strip()
        )
        warnings = self._unique_values(
            str(item).strip()
            for carrier in carriers
            for item in carrier.get("warnings", []) or []
            if str(item).strip()
        )
        rows.append(
            (
                "events.tsv columns",
                self._list_preview(columns) or "Needs review",
                "Use onset/duration for timing and trial_type or value for labels.",
            )
        )
        selected_eeg_count = len(self._selected_eeg_file_names())
        carrier_count = len(carriers)
        if selected_eeg_count:
            matched_count = min(carrier_count, selected_eeg_count)
            rows.append(
                (
                    "EEG/event pairing",
                    f"{matched_count}/{selected_eeg_count} EEG files",
                    "Matched by BIDS subject/session/task/run entities.",
                )
            )
        label_field_text = self._list_preview(label_fields) or "Choose in Label values"
        if "trial_type" in label_fields:
            label_field_text = "trial_type recommended"
        elif "value" in label_fields:
            label_field_text = "value"
        rows.append(
            (
                "Label field",
                label_field_text,
                "This becomes the class or event label value.",
            )
        )
        rows.append(
            (
                "Timing fields",
                self._bids_timing_fields_text(start_fields, duration_fields),
                "Saved for import recipe and later epoch setup.",
            )
        )
        if warnings:
            rows.append(
                (
                    "Needs review",
                    self._list_preview(warnings, limit=2),
                    "Resolve or confirm before applying.",
                )
            )
        return rows

    @staticmethod
    def _unique_values(values: Iterable[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            text = str(value).strip()
            if text and text not in result:
                result.append(text)
        return result

    @staticmethod
    def _list_preview(values: Iterable[str], *, limit: int = 5) -> str:
        items = [str(value).strip() for value in values if str(value).strip()]
        if not items:
            return ""
        if len(items) <= limit:
            return ", ".join(items)
        return ", ".join(items[:limit]) + f" +{len(items) - limit} more"

    def _bids_timing_fields_text(
        self,
        start_fields: list[str],
        duration_fields: list[str],
    ) -> str:
        start = self._list_preview(start_fields) or "Missing onset/start"
        duration = self._list_preview(duration_fields) or "Duration set later"
        return f"{start} + {duration}"

    def _bids_context_text(self) -> str:
        bids = self.scan_result.get("bids") or {}
        if not isinstance(bids, dict):
            return ""
        parts: list[str] = []
        for key, label in (
            ("subjects", "subject"),
            ("sessions", "session"),
            ("tasks", "task"),
            ("runs", "run"),
        ):
            values = bids.get(key) or []
            if isinstance(values, list) and values:
                preview = self._list_preview(
                    (str(item) for item in values),
                    limit=3,
                )
                parts.append(f"{label} {preview}")
        return ", ".join(parts)

    def _internal_event_status_text(self) -> str:
        if self._event_role_items or self._class_map_items:
            return (
                "Detected event or class information inside the EEG import preview. "
                "Use the confirmation rows below to keep the role and names explicit."
            )
        return (
            "No internal event candidates are available in this preview yet. If the "
            "recording contains usable events, they can still be reviewed after load "
            "before epoching."
        )

    def _internal_event_summary_text(self) -> str:
        payload = self._internal_event_preview_payload()
        file_count = len(self._selected_eeg_file_names())
        parts = [
            f"{file_count} EEG file(s) selected"
            if file_count
            else "No selected EEG files",
        ]
        pattern_status = str(payload.get("pattern_status") or "").strip()
        if pattern_status:
            parts.append(pattern_status)
        elif self._internal_candidate_label_event_rows():
            parts.append("Event pattern ready for review")
        elif self._event_role_items or self._class_map_items:
            parts.append("Internal event information available")
        else:
            parts.append("No internal label events detected yet")
        if payload.get("names_reliable") is False:
            parts.append("Event names need review")
        return " · ".join(parts)

    def _internal_candidate_label_event_rows(self) -> list[dict[str, str]]:
        payload = self._internal_event_preview_payload()
        raw_rows = payload.get("candidate_label_events") or payload.get(
            "candidate_events"
        )
        rows: list[dict[str, str]] = []
        if isinstance(raw_rows, list):
            for raw in raw_rows:
                if not isinstance(raw, dict):
                    continue
                code = self._internal_event_code_from_row(raw)
                if not code:
                    continue
                if self._internal_event_user_roles.get(code) == "not a label":
                    continue
                rows.append(
                    {
                        "code": code,
                        "use_as": str(raw.get("use_as") or "Class label"),
                        "coverage": self._event_coverage_text(raw),
                        "class_name": self._internal_event_class_name(raw, payload),
                        "evidence": self._event_evidence_text(
                            raw,
                            "Suggested by event pattern",
                        ),
                    }
                )
        for row in self._base_not_used_event_rows():
            code = str(row.get("code") or "").strip()
            if self._internal_event_user_roles.get(code) != "class label":
                continue
            rows.append(
                {
                    "code": code,
                    "use_as": "Class label",
                    "coverage": str(row.get("coverage") or ""),
                    "class_name": self._internal_class_name_edits.get(code, ""),
                    "evidence": "Changed by user",
                }
            )
        if rows:
            return sorted(rows, key=self._event_code_sort_key)
        class_map = self._class_map_for_current_label_source()
        if class_map:
            return [
                {
                    "code": str(code),
                    "use_as": "Class label",
                    "coverage": self._default_event_coverage_text(),
                    "class_name": self._internal_class_name_edits.get(
                        str(code),
                        str(label),
                    ),
                    "evidence": "Existing class map",
                }
                for code, label in sorted(
                    class_map.items(),
                    key=self._class_map_sort_key,
                )
            ]
        return []

    def _internal_not_used_event_rows(self) -> list[dict[str, str]]:
        rows = []
        for row in self._base_not_used_event_rows():
            code = str(row.get("code") or "").strip()
            if self._internal_event_user_roles.get(code) == "class label":
                continue
            rows.append(row)
        for row in self._base_candidate_label_event_rows():
            code = str(row.get("code") or "").strip()
            if self._internal_event_user_roles.get(code) != "not a label":
                continue
            rows.append(
                {
                    "code": code,
                    "use_as": "Not used",
                    "reason": "Changed by user",
                    "coverage": str(row.get("coverage") or ""),
                }
            )
        return sorted(rows, key=self._event_code_sort_key)

    @staticmethod
    def _event_code_sort_key(item: dict[str, str]) -> tuple[int, int | str]:
        code = str(item.get("code") or "").strip()
        return (0, int(code)) if code.isdigit() else (1, code.casefold())

    def _base_candidate_label_event_rows(self) -> list[dict[str, str]]:
        payload = self._internal_event_preview_payload()
        raw_rows = payload.get("candidate_label_events") or payload.get(
            "candidate_events"
        )
        rows: list[dict[str, str]] = []
        if not isinstance(raw_rows, list):
            return rows
        for raw in raw_rows:
            if not isinstance(raw, dict):
                continue
            code = self._internal_event_code_from_row(raw)
            if not code:
                continue
            rows.append(
                {
                    "code": code,
                    "coverage": self._event_coverage_text(raw),
                }
            )
        return rows

    def _base_not_used_event_rows(self) -> list[dict[str, str]]:
        payload = self._internal_event_preview_payload()
        raw_rows = (
            payload.get("not_used_events")
            or payload.get("non_label_events")
            or payload.get("excluded_events")
            or []
        )
        rows: list[dict[str, str]] = []
        if not isinstance(raw_rows, list):
            return rows
        for raw in raw_rows:
            if not isinstance(raw, dict):
                continue
            code = self._internal_event_code_from_row(raw)
            if not code:
                continue
            rows.append(
                {
                    "code": code,
                    "use_as": str(raw.get("use_as") or raw.get("role") or "Ignore"),
                    "reason": str(raw.get("reason") or raw.get("meaning") or ""),
                    "coverage": self._event_coverage_text(raw),
                }
            )
        return rows

    def _internal_event_preview_payload(self) -> dict[str, Any]:
        payload = self.preview.get("internal_event_preview") or self.preview.get(
            "inside_eeg_events"
        )
        return dict(payload) if isinstance(payload, dict) else {}

    @staticmethod
    def _internal_event_code_from_row(row: dict[str, Any]) -> str:
        for key in (
            "event_code",
            "original_event_code",
            "original_code",
            "original_label",
            "value",
            "raw_value",
            "code",
            "label",
            "event_label",
        ):
            value = str(row.get(key) or "").strip()
            if value:
                return value
        return ""

    def _event_coverage_text(self, row: dict[str, Any]) -> str:
        coverage = str(row.get("coverage") or "").strip()
        event_count = self._event_count_text(row)
        if coverage and event_count:
            return f"{event_count} · {coverage}"
        if coverage:
            return coverage
        file_count = len(self._selected_eeg_file_names())
        present = row.get("present_files")
        total = row.get("total_files")
        if isinstance(present, int) and isinstance(total, int) and total > 0:
            file_coverage = f"{present}/{total} files"
            return f"{event_count} · {file_coverage}" if event_count else file_coverage
        missing = row.get("missing_files")
        if isinstance(missing, list) and file_count:
            file_coverage = f"{max(file_count - len(missing), 0)}/{file_count} files"
            return f"{event_count} · {file_coverage}" if event_count else file_coverage
        default_coverage = self._default_event_coverage_text()
        if event_count and default_coverage:
            return f"{event_count} · {default_coverage}"
        return event_count or default_coverage

    @staticmethod
    def _event_count_text(row: dict[str, Any]) -> str:
        for key in (
            "event_count",
            "total_events",
            "occurrence_count",
            "occurrences",
            "count",
            "total_count",
        ):
            value = row.get(key)
            if isinstance(value, int) and value >= 0:
                return f"{value} events"
            value_text = str(value or "").strip()
            if value_text.isdigit():
                return f"{value_text} events"
        file_counts = row.get("file_counts") or row.get("per_file_counts")
        if isinstance(file_counts, dict):
            total = sum(
                value for value in file_counts.values() if isinstance(value, int)
            )
            return f"{total} events" if total >= 0 else ""
        if isinstance(file_counts, list):
            total = sum(value for value in file_counts if isinstance(value, int))
            return f"{total} events" if total >= 0 else ""
        return ""

    def _target_eeg_event_choices(self) -> list[tuple[str, str]]:
        rows = self._target_eeg_event_rows()
        choices: list[tuple[str, str]] = []
        for row in sorted(rows, key=self._target_event_sort_key):
            code = self._internal_event_code_from_row(row)
            if not code:
                continue
            count = self._event_count_text(row)
            use_as = str(row.get("use_as") or row.get("reason") or "").strip()
            detail = " · ".join(part for part in [use_as, count] if part)
            display = f"{code} · {detail}" if detail else code
            choices.append((display, code))
        return choices

    def _target_eeg_event_rows(self) -> list[dict[str, Any]]:
        payload = self._internal_event_preview_payload()
        rows: list[dict[str, Any]] = []
        for key in ("not_used_events", "candidate_label_events", "candidate_events"):
            value = payload.get(key)
            if isinstance(value, list):
                rows.extend(item for item in value if isinstance(item, dict))
        return rows

    def _target_event_row(self, code: str) -> dict[str, Any]:
        target = str(code or "").strip()
        if not target:
            return {}
        for row in self._target_eeg_event_rows():
            if self._internal_event_code_from_row(row) == target:
                return row
        return {}

    def _target_event_sort_key(self, row: dict[str, Any]) -> tuple[int, str]:
        use_as = str(row.get("use_as") or row.get("reason") or "").lower()
        evidence = str(row.get("evidence") or "").lower()
        if "trial timing" in use_as or "candidate total" in evidence:
            rank = 0
        elif "class label" in use_as:
            rank = 1
        elif any(
            token in use_as for token in ("artifact", "boundary", "ignore", "system")
        ):
            rank = 3
        else:
            rank = 2
        return (rank, self._internal_event_code_from_row(row).casefold())

    def _default_event_coverage_text(self) -> str:
        file_count = len(self._selected_eeg_file_names())
        return f"{file_count}/{file_count} files" if file_count else ""

    def _internal_event_class_name(
        self,
        row: dict[str, Any],
        payload: dict[str, Any],
    ) -> str:
        code = self._internal_event_code_from_row(row)
        if code in self._internal_class_name_edits:
            return self._internal_class_name_edits[code]
        if payload.get("names_reliable") is False:
            return ""
        return str(row.get("class_name") or row.get("name") or "").strip()

    @staticmethod
    def _event_evidence_text(row: dict[str, Any], fallback: str) -> str:
        return str(row.get("evidence") or row.get("reason") or fallback).strip()

    def _ensure_class_name_items_from_event_rows(
        self,
        rows: list[dict[str, str]],
    ) -> None:
        if self._class_map_items:
            return
        # Replacing the event tree destroys its embedded role selectors. Clear
        # the matching Python registries first so later review serialization
        # cannot retain deleted Qt wrappers.
        self._event_role_items.clear()
        self._event_role_widgets.clear()
        self._class_map_widgets.clear()
        self.event_tree.clear()
        for row in rows:
            code = str(row.get("code") or "").strip()
            if not code:
                continue
            class_name = str(row.get("class_name") or "").strip()
            tree_item = QTreeWidgetItem([code, "class name", class_name])
            self._class_map_items.append((tree_item, code, class_name))
            self.event_tree.addTopLevelItem(tree_item)
            self._install_class_map_selector(tree_item, class_name)
