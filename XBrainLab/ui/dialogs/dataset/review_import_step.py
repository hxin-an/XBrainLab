"""Review and Import step helpers for the Data Import wizard."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QRect, QSize, Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTreeWidgetItem,
    QVBoxLayout,
)

from XBrainLab.backend.application.data_interpretation_pairing import (
    LabelPairingResult,
    resolve_label_file_pairing,
)
from XBrainLab.ui.dialogs.dataset.review_import_presenter import (
    SubmissionFacts,
    SubmissionProjection,
    eeg_data_summary,
    internal_label_placement_summary,
    label_source_summary,
    project_submission,
    recipe_note,
)
from XBrainLab.ui.dialogs.dataset.review_import_presenter import (
    metadata_summary as metadata_review_summary_text,
)
from XBrainLab.ui.dialogs.dataset.review_presenter import (
    ReviewRow,
    action_item_rows,
    build_primary_review_rows,
    build_review_rows,
    compact_review_rows,
    is_metadata_review_row,
    merge_review_rows,
    metadata_required_fields_complete,
    target_step_for_review_text,
)

if TYPE_CHECKING:
    from XBrainLab.ui.dialogs.dataset.wizard_host_protocol import (
        DataImportWizardStepHostProtocol,
    )
else:

    class DataImportWizardStepHostProtocol:
        pass


class ReviewImportStepMixin(DataImportWizardStepHostProtocol):
    """Render helpers for final review, action items, and recipe trace."""

    def _build_review_import_summary(self, layout: QVBoxLayout) -> None:
        self._review_import_rows_layout = QGridLayout()
        self._review_import_rows_layout.setContentsMargins(0, 0, 0, 0)
        self._review_import_rows_layout.setHorizontalSpacing(10)
        self._review_import_rows_layout.setVerticalSpacing(6)
        self._render_review_import_rows()
        layout.addLayout(self._review_import_rows_layout)

    def _render_review_import_rows(self) -> None:
        self._clear_review_import_rows()
        self._review_summary_value_labels.clear()
        for row_index, row in enumerate(self._review_import_status_rows()):
            item_label = QLabel(row["item"])
            item_label.setObjectName("DataImportReviewItem")
            status_label = QLabel(row["status"])
            status_label.setObjectName(self._review_status_object_name(row["status"]))
            status_label.setAlignment(
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
            )
            status_label.setSizePolicy(
                QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.Fixed,
            )
            status_label.setFixedWidth(132)
            status_height = max(status_label.fontMetrics().height() + 14, 30)
            status_label.setFixedHeight(status_height)
            summary_label = QLabel(row["summary"])
            summary_label.setObjectName("DataImportReviewSummary")
            summary_label.setWordWrap(True)
            summary_label.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Minimum,
            )
            summary_label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            summary_width_floor = 220
            text_bounds = summary_label.fontMetrics().boundingRect(
                QRect(0, 0, summary_width_floor, 10_000),
                int(
                    Qt.AlignmentFlag.AlignLeft
                    | Qt.AlignmentFlag.AlignVCenter
                    | Qt.TextFlag.TextWordWrap
                ),
                summary_label.text(),
            )
            summary_minimum_height = max(
                status_height,
                text_bounds.height() + 10,
            )
            summary_label.setMinimumHeight(summary_minimum_height)
            summary_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self._review_summary_value_labels[row["item"]] = summary_label

            item_label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            self._review_import_rows_layout.addWidget(
                item_label,
                row_index,
                0,
                alignment=Qt.AlignmentFlag.AlignVCenter,
            )
            self._review_import_rows_layout.addWidget(
                status_label,
                row_index,
                1,
                alignment=(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            )
            self._review_import_rows_layout.addWidget(summary_label, row_index, 2)
            action = row.get("action", "")
            if action:
                self._review_import_rows_layout.addWidget(
                    self._review_import_action(row),
                    row_index,
                    3,
                    alignment=(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    ),
                )
            self._review_import_rows_layout.setRowMinimumHeight(
                row_index,
                summary_minimum_height,
            )
        self._review_import_rows_layout.setColumnMinimumWidth(0, 118)
        self._review_import_rows_layout.setColumnMinimumWidth(1, 132)
        self._review_import_rows_layout.setColumnStretch(2, 1)
        self.save_recipe_check.setVisible(True)
        self._review_import_rows_layout.invalidate()
        self._review_import_rows_layout.activate()
        for index in range(self._review_import_rows_layout.count()):
            item = self._review_import_rows_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.show()
        parent = self._review_import_rows_layout.parentWidget()
        if parent is not None:
            parent.updateGeometry()

    def _sync_review_import_row_heights(self) -> None:
        """Fit wrapped review summaries without inflating compact final steps."""
        layout = getattr(self, "_review_import_rows_layout", None)
        if layout is None:
            return
        layout.activate()
        for index in range(layout.count()):
            item = layout.itemAt(index)
            if item is None:
                continue
            row, column, _row_span, _column_span = layout.getItemPosition(index)
            if column != 2:
                continue
            summary = item.widget()
            if not isinstance(summary, QLabel) or summary.width() <= 0:
                continue
            text_bounds = summary.fontMetrics().boundingRect(
                QRect(0, 0, summary.width(), 10_000),
                int(
                    Qt.AlignmentFlag.AlignLeft
                    | Qt.AlignmentFlag.AlignVCenter
                    | Qt.TextFlag.TextWordWrap
                ),
                summary.text(),
            )
            required_height = max(
                summary.heightForWidth(summary.width()),
                text_bounds.height(),
                summary.fontMetrics().height() + 14,
            )
            if required_height > 0:
                if summary.minimumHeight() != required_height:
                    summary.setMinimumHeight(required_height)
                layout.setRowMinimumHeight(
                    row,
                    max(layout.rowMinimumHeight(row), required_height),
                )
        layout.activate()

    @staticmethod
    def _review_status_object_name(status: str) -> str:
        return {
            "Ready": "DataImportReviewStatusReady",
            "Completed": "DataImportReviewStatusReady",
            "Safe": "DataImportReviewStatusReady",
            "Saved": "DataImportReviewStatusReady",
            "Loaded": "DataImportReviewStatusNeutral",
            "Ready with notes": "DataImportReviewStatusReadyWithNotes",
            "Will save": "DataImportReviewStatusNeutral",
            "Warning": "DataImportReviewStatusNeedsReview",
            "Blocking": "DataImportReviewStatusMissing",
            "Too large": "DataImportReviewStatusMissing",
            "Unknown": "DataImportReviewStatusNeedsReview",
            "Needs review": "DataImportReviewStatusNeedsReview",
            "Missing": "DataImportReviewStatusMissing",
            "Incomplete": "DataImportReviewStatusIncomplete",
            "Action required": "DataImportReviewStatusIncomplete",
            "Not saved": "DataImportReviewStatusNeutral",
        }.get(status, "DataImportReviewStatus")

    def _clear_review_import_rows(self) -> None:
        if not hasattr(self, "_review_import_rows_layout"):
            return
        while self._review_import_rows_layout.count():
            item = self._review_import_rows_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                if widget is self.save_recipe_check:
                    continue
                widget.deleteLater()

    def _review_import_action(self, row: dict[str, str]) -> QPushButton:
        action = row.get("action", "")
        if action in {
            "Save recipe",
            "Cancel save",
        }:
            self.save_recipe_check.setText(action)
            return self.save_recipe_check
        button = QPushButton(action)
        button.setObjectName("DataImportReviewAction")
        target_step = row.get("target_step", "")
        if target_step:
            button.clicked.connect(
                lambda _checked=False, step=target_step: self._go_to_review_target(step)
            )
        return button

    def _review_import_status_rows(self) -> list[dict[str, str]]:
        complete_count, missing_fields = self._metadata_completion_counts()
        missing_required = self._metadata_required_missing_fields(missing_fields)
        missing_notes = set(missing_fields) & {"session", "task", "run"}
        metadata_file_count = self.file_tree.topLevelItemCount()
        if missing_required:
            metadata_status = "Needs review"
            metadata_row_summary = self._metadata_missing_text(missing_required)
            if metadata_file_count:
                file_word = "file" if metadata_file_count == 1 else "files"
                metadata_row_summary = (
                    f"{metadata_row_summary} · "
                    f"{metadata_file_count} {file_word} affected"
                )
            metadata_action = "Edit Metadata"
        elif missing_notes:
            metadata_status = "Ready with notes"
            field_word = "field" if len(missing_notes) == 1 else "fields"
            ordered_notes = [
                field for field in ("session", "task", "run") if field in missing_notes
            ]
            metadata_row_summary = (
                f"Optional {field_word} missing: {', '.join(ordered_notes)}"
            )
            if self._is_bids_source():
                metadata_row_summary = (
                    f"BIDS entities reviewed · {metadata_row_summary}"
                )
            affected_count = self._metadata_affected_file_count(missing_notes)
            if affected_count:
                file_word = "file" if affected_count == 1 else "files"
                metadata_row_summary = (
                    f"{metadata_row_summary} · {affected_count} {file_word} affected"
                )
            metadata_action = "Edit Metadata"
        else:
            metadata_status = "Ready"
            metadata_row_summary = metadata_review_summary_text(
                row_count=metadata_file_count,
                complete_count=complete_count,
                missing_fields=missing_required,
                is_bids_source=self._is_bids_source(),
                fallback_summary=self._metadata_review_summary(
                    complete_count,
                    missing_required,
                ),
            )
            metadata_action = ""

        label_source_status = "Ready"
        if (
            self._label_source_mode() == "loaded_label_files"
            and self._active_label_carrier_count() <= 0
        ):
            label_source_status = "Missing"
        label_placement_status = "Ready"
        label_placement_summary = self._review_label_placement_text()
        if self._should_show_label_table_fallback():
            label_placement_status = "Action required"
        elif (
            "need review" in label_placement_summary.lower()
            or self._has_review_action_for_step("Match Labels")
        ):
            label_placement_status = "Needs review"

        recipe_selected = self.save_recipe_check.isChecked()
        if recipe_selected:
            recipe_status = "Will save"
            recipe_summary = "Recipe will be saved after this import succeeds."
            recipe_action = "Cancel save"
        elif self._has_loaded_import_recipe() and not self._recipe_choices_changed():
            recipe_status = "Loaded"
            recipe_summary = (
                "A saved recipe was loaded. Save the current import settings "
                "again to keep any changes."
            )
            recipe_action = "Save recipe"
        else:
            recipe_status = "Not saved"
            recipe_summary = self._review_recipe_note_text()
            recipe_action = "Save recipe"

        return [
            {
                "item": "EEG data",
                "status": "Ready" if self._file_count() else "Missing",
                "summary": self._review_eeg_data_text(),
            },
            {
                "item": "Metadata",
                "status": metadata_status,
                "summary": metadata_row_summary,
                "action": metadata_action,
                "target_step": "Review Metadata",
            },
            {
                "item": "Label source",
                "status": label_source_status,
                "summary": self._review_label_source_text(),
            },
            {
                "item": "Label placement",
                "status": label_placement_status,
                "summary": label_placement_summary,
                "target_step": "Match Labels",
                "action": (
                    "Go to Match Labels"
                    if label_placement_status in {"Needs review", "Action required"}
                    else ""
                ),
            },
            self._resource_check_status_row(),
            {
                "item": "Recipe",
                "status": recipe_status,
                "summary": recipe_summary,
                "action": recipe_action,
            },
        ]

    def _has_loaded_import_recipe(self) -> bool:
        summary = self.preview.get("recipe_reload_summary")
        return isinstance(summary, dict) and bool(summary)

    def _recipe_choices_changed(self) -> bool:
        """Return whether the loaded recipe required current-scan substitutions."""
        return bool(
            self._eeg_file_remap_options() or self._label_carrier_remap_options()
        )

    def _pending_recipe_action_text(self, checked: bool) -> str:
        return "Cancel save" if checked else "Save recipe"

    def _metadata_affected_file_count(self, fields: set[str]) -> int:
        """Count rows missing at least one requested metadata field."""
        field_columns = {
            "subject": 1,
            "session": 2,
            "task": 3,
            "run": 4,
        }
        columns = [field_columns[field] for field in fields if field in field_columns]
        return sum(
            1
            for item, _original in self._metadata_items
            if any(not item.text(column).strip() for column in columns)
        )

    def _has_review_action_for_step(self, target_step: str) -> bool:
        if target_step == "Match Labels":
            return self._label_placement_needs_review()
        return any(row[0] == target_step for row in self._primary_review_rows())

    def _label_placement_needs_review(self) -> bool:
        if self._label_source_mode() == "internal_events":
            return not bool(self._class_map_items or self._event_role_items)
        if self._label_source_mode() == "loaded_label_files":
            if self._active_label_carrier_count() <= 0:
                return True
            if self._should_show_label_table_fallback():
                return True
            if self._loaded_label_pairing_needs_review():
                return True
            editor = self.event_value_editor
            if editor is not None and editor.has_rows():
                if not editor.is_complete():
                    return True
                if self._is_bids_source():
                    return False
        summary = self._review_label_placement_text().casefold()
        return any(
            marker in summary
            for marker in (
                "need review",
                "needs review",
                "needs conversion",
                "no external labels selected",
            )
        )

    def _loaded_label_pairing_needs_review(self) -> bool:
        result = self._loaded_label_pairing_result()
        return bool(self._selected_eeg_file_names()) and not result.complete

    def _loaded_label_pairing_result(self) -> LabelPairingResult:
        plans: list[dict[str, Any]] = []
        for item, original in self._label_carrier_items:
            carrier_key = self._label_carrier_key(item, original)
            if self._is_label_carrier_excluded(carrier_key):
                continue
            plan = dict(original)
            plan["path"] = carrier_key
            plan["selected_target_file"] = self._label_carrier_choice_text(
                "target_file",
                self._label_carrier_item_text(item, 1),
            )
            plans.append(plan)
        return resolve_label_file_pairing(plans, self._selected_eeg_file_names())

    def _has_unresolved_required_decisions(self) -> bool:
        _complete_count, missing_fields = self._metadata_completion_counts()
        if self._metadata_required_missing_fields(missing_fields):
            return True
        if self._file_count() <= 0:
            return True
        return self._label_placement_needs_review()

    def _submission_facts(self) -> SubmissionFacts:
        return SubmissionFacts(
            decision=self.decision,
            resource_blocked=self._resource_check_blocks_import(),
            has_unresolved_required_decisions=(
                self._has_unresolved_required_decisions()
            ),
            has_remap_options=self._has_remap_options(),
            has_complete_remap_choices=self._has_complete_remap_choices(),
            event_values_ready_for_recheck=(
                self._event_value_decisions_ready_for_recheck()
            ),
            interpretation_choices_ready_for_recheck=(
                self._edited_choices_can_resolve_blocker()
            ),
        )

    def _edited_choices_can_resolve_blocker(self) -> bool:
        """Only recheck edits that target at least one current blocker."""
        choices = self._edited_choices()
        if not choices:
            return False

        edited_targets: set[str] = set()
        if choices.get("metadata_overrides"):
            edited_targets.add("Review Metadata")
        if any(
            choices.get(key)
            for key in (
                "class_map",
                "event_roles",
                "excluded_label_carriers",
                "label_carrier",
                "internal_event_selection",
                "run_event_mappings",
                "required_label_carriers",
                "label_carrier_choices",
            )
        ):
            edited_targets.add("Match Labels")
        if not edited_targets:
            return False

        action_items = self.preview.get("action_items") or self.validation_decision.get(
            "action_items"
        )
        blocking_targets = {
            str(item.get("target_step") or "Review and Import")
            for item in action_items or []
            if isinstance(item, dict)
            and str(item.get("severity") or "").strip().lower() == "blocked"
        }
        if not blocking_targets:
            blocking_targets = {
                target_step_for_review_text(str(reason))
                for reason in (
                    self.validation_decision.get("blocked_reasons")
                    or self.preview.get("blocked_reasons")
                    or []
                )
                if str(reason).strip()
            }
        return bool(blocking_targets) and blocking_targets.issubset(edited_targets)

    def _submission_projection(self) -> SubmissionProjection:
        return project_submission(self._submission_facts())

    def can_submit_for_backend_review(self) -> bool:
        """Return whether current choices may be sent back to the backend."""
        return self._submission_projection().can_submit_for_backend_review

    def _refresh_review_import_summary(self) -> None:
        if hasattr(self, "_review_import_rows_layout"):
            self._render_review_import_rows()
        self._refresh_import_report_summary()

    def _refresh_import_report_summary(self) -> None:
        if not hasattr(self, "import_report_summary"):
            return
        self.import_report_summary.setText(self._import_report_summary_text())

    def _import_report_summary_text(self) -> str:
        eeg_names = self._selected_eeg_file_names()
        eeg_summary = self._event_code_list_text(eeg_names, limit=5) or "None"
        label_names = [
            Path(self._label_carrier_key(item, original)).name
            for item, original in self._label_carrier_items
            if not self._is_label_carrier_excluded(
                self._label_carrier_key(item, original),
            )
        ]
        label_summary = self._event_code_list_text(label_names, limit=5) or "None"
        review_rows = {row["item"]: row for row in self._review_import_status_rows()}
        metadata = review_rows.get("Metadata", {})
        resource = review_rows.get("Resource check", {})
        if self._label_source_mode() == "loaded_label_files":
            pairing = self._loaded_label_pairing_result()
            alignment = (
                f"{pairing.matched_count}/{len(eeg_names)} EEG files paired"
                if eeg_names
                else "No EEG files selected"
            )
        else:
            alignment = "Labels are read from EEG events; file pairing is not required"

        optional_notes = self._import_report_optional_notes_text(metadata)
        blocking_issues = self._import_report_blocking_issues_text()
        return "\n".join(
            (
                f"EEG files: {eeg_summary}",
                f"Label files: {label_summary}",
                "Metadata: "
                f"{metadata.get('status', 'Unknown')} - "
                f"{metadata.get('summary', 'No metadata status available')}",
                f"Label alignment: {alignment}",
                f"Label placement: {self._review_label_placement_text()}",
                "Resource check: "
                f"{resource.get('status', 'Unknown')} - "
                f"{resource.get('summary', 'No resource status available')}",
                f"Optional notes: {optional_notes}",
                f"Blocking issues: {blocking_issues}",
            )
        )

    def _import_report_optional_notes_text(
        self,
        metadata_row: dict[str, str],
    ) -> str:
        notes: list[str] = []
        if metadata_row.get("status") == "Ready with notes":
            notes.append(str(metadata_row.get("summary") or "").strip())
        action_items = self.preview.get("action_items") or self.validation_decision.get(
            "action_items"
        )
        notes.extend(
            str(item.get("issue") or "").strip()
            for item in action_items or []
            if isinstance(item, dict)
            and str(item.get("severity") or "").strip().lower()
            not in {"blocked", "needs_confirmation"}
            and str(item.get("issue") or "").strip()
        )
        return "; ".join(dict.fromkeys(note for note in notes if note)) or "None"

    def _import_report_blocking_issues_text(self) -> str:
        """Return only issues that currently block applying the import."""
        action_items = self.preview.get("action_items") or self.validation_decision.get(
            "action_items"
        )
        blocking_items = [
            item
            for item in action_items or []
            if isinstance(item, dict)
            and str(item.get("severity") or "").strip().lower() == "blocked"
        ]
        issues: list[str] = []
        for row in action_item_rows(blocking_items):
            current_row = self._current_review_row(row)
            if not self._review_row_is_resolved(current_row):
                issues.append(current_row[1])
        if (
            not issues
            and self.decision == "blocked"
            and not self._review_ready_for_recheck()
        ):
            issues = [
                str(reason).strip()
                for reason in (
                    self.validation_decision.get("blocked_reasons")
                    or self.preview.get("blocked_reasons")
                    or []
                )
                if str(reason).strip()
            ]
        return "; ".join(dict.fromkeys(issues)) if issues else "None"

    def _default_review_action_row(self) -> tuple[str, str, str, str]:
        if self.decision == "blocked" and not self._review_ready_for_recheck():
            return (
                "Review and Import",
                "Import requirements are incomplete",
                "Blocking items must be resolved before the data can be imported.",
                "Resolve the action items below, then import.",
            )
        return (
            "Review and Import",
            "Ready to import",
            "No blocking review items.",
            "Confirm and apply when the summary matches your data.",
        )

    def _review_eeg_data_text(self) -> str:
        names = self._selected_eeg_file_names()
        return eeg_data_summary(
            selected_names=names,
            file_count=self._file_count() or len(names),
            preview_text=self._event_code_list_text(names, limit=3),
        )

    def _review_metadata_text(self) -> str:
        complete_count, missing_fields = self._metadata_completion_counts()
        missing_fields = self._metadata_required_missing_fields(missing_fields)
        return metadata_review_summary_text(
            row_count=self.file_tree.topLevelItemCount(),
            complete_count=complete_count,
            missing_fields=missing_fields,
            is_bids_source=self._is_bids_source(),
            fallback_summary=self._metadata_review_summary(
                complete_count,
                missing_fields,
            ),
        )

    def _review_label_source_text(self) -> str:
        return label_source_summary(
            source_mode=self._label_source_mode(),
            internal_candidate_count=len(self._class_map_items)
            or len(self._event_role_items),
            active_carrier_count=self._active_label_carrier_count(),
            has_bids_events=self._has_bids_events(),
            has_extra_sources=bool(self._extra_label_sources),
        )

    def _review_label_placement_text(self) -> str:
        if self._label_source_mode() == "internal_events":
            return internal_label_placement_summary(
                selected_class_count=len(self._class_map_items),
                event_role_count=len(self._event_role_items),
            )
        if self._active_label_carrier_count() <= 0:
            return "No external labels selected"
        if self._should_show_label_table_fallback():
            return "Label format needs conversion before matching labels to EEG"
        if self._loaded_label_pairing_needs_review():
            pairing = self._loaded_label_pairing_result()
            total = len(self._selected_eeg_file_names())
            return (
                f"{pairing.matched_count}/{total} EEG files paired · "
                f"{len(pairing.unmatched_eeg_files)} need label"
            )
        editor = self.event_value_editor
        if editor is not None and editor.has_rows() and self._is_bids_source():
            unresolved = editor.unresolved_values()
            if unresolved:
                return f"{len(unresolved)} event values need review"
            return (
                f"{editor.row_count()} event values reviewed · "
                "BIDS onset and duration preserved"
            )
        if not hasattr(self, "rule_placement_method_combo"):
            return self._label_rule_status_text()

        field = self.rule_label_field_combo.currentText().strip() or "Label field"
        method = self._combo_current_data(self.rule_placement_method_combo)
        method_text = self.rule_placement_method_combo.currentText().strip()
        if method == "eeg_event":
            targets = self._event_code_list_text(self._event_order_target_codes())
            if targets:
                return f"{field} · {method_text} · target EEG events {targets}"
            return f"{field} · {method_text} · target EEG events need review"
        if method == "time_field":
            time_field = self.rule_alignment_combo.currentText().strip()
            time_model = self.rule_time_model_combo.currentText().strip()
            return f"{field} · {method_text} · {time_field} · {time_model}"
        if method == "interval":
            start = self.rule_alignment_combo.currentText().strip()
            duration = self.rule_duration_field_combo.currentText().strip()
            return f"{field} · {method_text} · start {start} · duration/end {duration}"
        if method == "event_code":
            code_field = self.rule_alignment_combo.currentText().strip()
            return f"{field} · {method_text} · event code field {code_field}"
        return self._label_rule_status_text()

    def _review_recipe_note_text(self) -> str:
        return recipe_note()

    def _resource_check_status_row(self) -> dict[str, str]:
        preflight = self._current_resource_preflight()
        risk_level = self._resource_preflight_risk_level(preflight)
        status = {
            "safe": "Safe",
            "warning": "Warning",
            "blocking": "Blocking",
            "unknown": "Unknown",
        }[risk_level]
        action = "Go to EEG Data" if risk_level == "blocking" else ""
        return {
            "item": "Resource check",
            "status": status,
            "summary": self._review_resource_check_text(preflight),
            "action": action,
            "target_step": "Choose EEG Data",
        }

    def _review_resource_check_text(self, preflight: dict[str, Any]) -> str:
        required = self._format_resource_memory_size(
            preflight.get(
                "required_memory_bytes",
                preflight.get("estimated_ram_working_set_bytes"),
            )
        )
        available = self._format_resource_memory_size(
            preflight.get(
                "available_memory_bytes",
                preflight.get("available_ram_bytes"),
            )
        )
        if required != "Unknown" and available != "Unknown":
            return f"Estimated RAM {required} / Available RAM {available}"

        message = str(preflight.get("message") or "").strip()
        if message:
            return message.splitlines()[0]
        return "Resource availability was not reported for this preview"

    def _resource_check_blocks_import(self) -> bool:
        return (
            self._resource_preflight_risk_level(self._current_resource_preflight())
            == "blocking"
        )

    def _current_resource_preflight(self) -> dict[str, Any]:
        preflight = self.preview.get("resource_preflight")
        return dict(preflight) if isinstance(preflight, dict) else {}

    @staticmethod
    def _resource_preflight_risk_level(preflight: dict[str, Any]) -> str:
        risk_level = str(preflight.get("risk_level") or "unknown").casefold()
        if risk_level in {"safe", "warning", "blocking", "unknown"}:
            return risk_level
        return "unknown"

    @staticmethod
    def _format_resource_memory_size(value: Any) -> str:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            return "Unknown"
        number = float(value)
        units = ("B", "KB", "MB", "GB", "TB")
        unit = units[0]
        for unit in units:
            if number < 1024 or unit == units[-1]:
                break
            number /= 1024
        if unit == "B":
            return f"{int(number)} {unit}"
        return f"{number:.1f} {unit}"

    def _active_label_carrier_count(self) -> int:
        return sum(
            1
            for item, original in self._label_carrier_items
            if not self._is_label_carrier_excluded(
                self._label_carrier_key(item, original)
            )
        )

    def _populate_review_action_cards(self) -> None:
        rows = self._merged_review_rows(self._primary_review_rows())
        if not rows:
            if self.decision == "blocked" and not self._review_ready_for_recheck():
                rows = [self._default_review_action_row()]
            else:
                self.review_actions_panel.setVisible(False)
                return
        self.review_actions_panel.setVisible(True)
        grouped: dict[str, list[tuple[str, str, str, str]]] = {}
        for target_step, issue, impact, next_action in rows:
            group_title = self._review_action_group_title(
                target_step,
                issue,
                impact,
                next_action,
            )
            if not group_title:
                continue
            grouped.setdefault(group_title, []).append(
                (target_step, issue, impact, next_action)
            )
        if not grouped:
            self.review_actions_panel.setVisible(False)
            return
        for group_title in (
            "Cannot import yet",
            "Needs your decision",
        ):
            items = grouped.get(group_title)
            if not items:
                continue
            group_card, group_layout = self._card(group_title)
            for target_step, issue, impact, next_action in items:
                group_layout.addWidget(
                    self._action_item_card(target_step, issue, impact, next_action)
                )
            self.review_actions_layout.addWidget(group_card)

    def _refresh_review_action_cards(self) -> None:
        """Rebuild first-layer actions from the current visible wizard choices."""
        while self.review_actions_layout.count():
            item = self.review_actions_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is None:
                continue
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        self._populate_review_action_cards()

    def _review_action_group_title(
        self,
        target_step: str,
        issue: str,
        impact: str,
        next_action: str,
    ) -> str:
        submission = self._submission_projection()
        if submission.recheck_kind is not None:
            return ""
        lowered = " ".join((issue, impact, next_action)).lower()
        if (
            self.decision == "blocked"
            or "cannot import" in lowered
            or "cannot be applied" in lowered
            or "blocked" in lowered
        ):
            return "Cannot import yet"
        if target_step == "Review Metadata":
            return ""
        if target_step == "Review and Import":
            return ""
        if target_step == "Match Labels" and not self._label_placement_needs_review():
            return ""
        if target_step == "Match Labels" and any(
            token in lowered
            for token in ("alignment", "placement", "event role", "event mapping")
        ):
            return "Needs your decision"
        if any(
            token in lowered
            for token in (
                "ambiguous",
                "unresolved",
                "incomplete",
                "not paired",
                "cannot tell",
                "conversion",
                "choose",
                "select",
                "provide",
                "resolve",
            )
        ):
            return "Needs your decision"
        return ""

    def _action_item_card(
        self,
        target_step: str,
        issue: str,
        impact: str,
        next_action: str,
    ) -> QFrame:
        row = QFrame()
        row.setObjectName("DataImportActionCard")
        row.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        layout = QVBoxLayout(row)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)
        issue_label = QLabel(
            self._review_action_issue_title(target_step, issue, impact, next_action)
        )
        issue_label.setObjectName("DataImportActionIssue")
        issue_label.setWordWrap(True)
        layout.addWidget(issue_label)

        details: list[str] = []
        is_local_review_item = target_step == "Review and Import"
        if impact and not self._review_action_detail_is_generic(impact):
            details.append(impact)
        if (
            next_action
            and next_action not in details
            and not self._review_action_detail_is_generic(next_action)
        ):
            details.append(next_action)
        if not details and not is_local_review_item:
            details.append(self._review_action_default_detail(target_step))
        for detail in details:
            detail_label = QLabel(detail)
            detail_label.setObjectName("DataImportActionMeta")
            detail_label.setWordWrap(True)
            layout.addWidget(detail_label)
        if not is_local_review_item and target_step in self._step_titles:
            action_row = QHBoxLayout()
            action_row.setContentsMargins(0, 2, 0, 0)
            action_row.addStretch()
            button = QPushButton(
                self._review_action_button_text(target_step, issue, next_action)
            )
            button.setObjectName("DataImportInlineAction")
            button.clicked.connect(
                lambda _checked=False, step=target_step: self._go_to_review_target(step)
            )
            action_row.addWidget(button)
            layout.addLayout(action_row)
        return row

    @staticmethod
    def _review_action_detail_is_generic(text: str) -> bool:
        lowered = " ".join(str(text).strip().lower().split())
        if not lowered:
            return True
        generic_phrases = (
            "this choice affects imported metadata, labels, or downstream "
            "training readiness.",
            "this choice affects imported metadata, labels, and downstream "
            "training readiness.",
            "this choice affects training readiness.",
            "review the target step and confirm the choice.",
            "review match labels.",
            "confirm the choice.",
        )
        return lowered in generic_phrases

    @staticmethod
    def _review_action_default_detail(target_step: str) -> str:
        return {
            "Choose EEG Data": "Confirm which EEG files belong in this import.",
            "Load Labels": (
                "Load or choose the label source before import can continue."
            ),
            "Review Metadata": "Fill required metadata fields before import.",
            "Match Labels": (
                "Choose how label values align with EEG events before import."
            ),
        }.get(target_step, "Review this setting before import.")

    @staticmethod
    def _review_action_issue_title(
        target_step: str,
        issue: str,
        impact: str,
        next_action: str,
    ) -> str:
        lowered = " ".join((issue, impact, next_action)).lower()
        if target_step == "Review Metadata":
            return "Required metadata is missing"
        if target_step == "Match Labels":
            if "alignment" in lowered or "pair" in lowered or "carrier" in lowered:
                return "Label alignment is unresolved"
            if "event role" in lowered or "event mapping" in lowered:
                return "EEG event mapping is incomplete"
            if "placement" in lowered or "class" in lowered or "event" in lowered:
                return "Label placement is ambiguous"
            return "Label matching is incomplete"
        if target_step == "Load Labels":
            return "Label source is incomplete"
        if target_step == "Choose EEG Data":
            return "EEG data is incomplete"
        return issue.removeprefix("Confirm ").removeprefix("Review ").strip() or issue

    @staticmethod
    def _review_action_button_text(
        target_step: str,
        issue: str = "",
        next_action: str = "",
    ) -> str:
        if target_step == "Match Labels":
            return "Go to Match Labels"
        return {
            "Choose EEG Data": "Go to EEG Data",
            "Load Labels": "Go to Labels",
            "Review Metadata": "Go to Metadata",
        }.get(target_step, target_step)

    def _go_to_review_target(self, target_step: str) -> None:
        if target_step not in self._step_titles:
            return
        self._go_to_step(self._step_titles.index(target_step))
        self._focus_review_target(target_step)

    def _focus_review_target(self, target_step: str) -> None:
        if target_step == "Review Metadata" and hasattr(self, "file_tree"):
            self.file_tree.setFocus(Qt.FocusReason.OtherFocusReason)
            item = self.file_tree.topLevelItem(0)
            if item is not None:
                self.file_tree.setCurrentItem(item)
            return
        if target_step == "Match Labels" and hasattr(self, "placement_card"):
            self.placement_card.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if target_step == "Load Labels" and hasattr(self, "label_carrier_tree"):
            self.label_carrier_tree.setFocus(Qt.FocusReason.OtherFocusReason)

    def _populate_review_tree(self) -> None:
        self._eeg_file_remap_report_items = {}
        self._label_carrier_remap_report_items = {}
        rows = self._review_rows()
        remap_added = False
        for remap in self._eeg_file_remap_options():
            saved = str(remap.get("saved") or "").strip()
            if not saved:
                continue
            saved_name = str(remap.get("saved_name") or Path(saved).name or saved)
            tree_item = self._review_report_item(
                (
                    "Review and Import",
                    "Recipe EEG file",
                    f"Saved recipe file is missing: {saved_name}.",
                    "Choose file",
                )
            )
            self.review_tree.addTopLevelItem(tree_item)
            selector = self._remap_selector(
                remap,
                "Choose the replacement EEG file.",
            )
            self._eeg_file_remap_widgets[saved] = selector
            self._eeg_file_remap_report_items[saved] = tree_item
            self.review_tree.setItemWidget(tree_item, 3, selector)
            remap_added = True
        for remap in self._label_carrier_remap_options():
            saved = str(remap.get("saved") or "").strip()
            if not saved:
                continue
            saved_name = str(remap.get("saved_name") or Path(saved).name or saved)
            tree_item = self._review_report_item(
                (
                    "Review and Import",
                    "Recipe label file",
                    f"Saved recipe label is missing: {saved_name}.",
                    "Choose file",
                )
            )
            self.review_tree.addTopLevelItem(tree_item)
            selector = self._remap_selector(
                remap,
                "Choose the replacement label/event carrier.",
            )
            self._label_carrier_remap_widgets[saved] = selector
            self._label_carrier_remap_report_items[saved] = tree_item
            self.review_tree.setItemWidget(tree_item, 3, selector)
            remap_added = True
        rows = self._merged_review_rows(rows)
        for target_step, issue, impact, next_action in rows:
            tree_item = self._review_report_item(
                (target_step, issue, impact, next_action)
            )
            self.review_tree.addTopLevelItem(tree_item)
        if (
            not rows
            and not remap_added
            and self.decision == "blocked"
            and not self._review_ready_for_recheck()
        ):
            target_step, issue, impact, next_action = self._default_review_action_row()
            self.review_tree.addTopLevelItem(
                self._review_report_item(
                    (target_step, issue, impact, next_action),
                )
            )
        self._sync_remap_report_rows()
        self._sync_review_report_empty_state()

    def _sync_review_report_empty_state(self) -> None:
        """Show a real ready state instead of manufacturing an issue row."""
        if not hasattr(self, "import_report_card"):
            return
        if not hasattr(self, "review_report_empty_label"):
            self.review_report_empty_label = QLabel(
                "No review items. This import is ready to apply.",
                self.import_report_card,
            )
            self.review_report_empty_label.setObjectName("DataImportReportEmptyState")
            self.review_report_empty_label.setWordWrap(True)
            self.review_report_empty_label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            layout = self.import_report_card.layout()
            if layout is not None:
                layout.addWidget(self.review_report_empty_label)

        has_report_items = self.review_tree.topLevelItemCount() > 0
        self.review_tree.setVisible(has_report_items)
        self.review_report_empty_label.setVisible(not has_report_items)

    @staticmethod
    def _review_report_item(values: tuple[str, str, str, str]) -> QTreeWidgetItem:
        """Build one report row whose tooltip matches each visible cell."""
        item = QTreeWidgetItem(list(values))
        for column, value in enumerate(values):
            item.setToolTip(column, value)
        return item

    def _fit_review_report_rows(self) -> None:
        """Size report rows for their wrapped text at the current column widths."""
        if not hasattr(self, "review_tree"):
            return
        tree = self.review_tree
        text_flags = (
            Qt.TextFlag.TextWordWrap
            | Qt.TextFlag.TextExpandTabs
            | Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter
        )
        vertical_padding = 12
        horizontal_padding = 18
        for row in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(row)
            if item is None:
                continue
            row_height = tree.fontMetrics().height() + vertical_padding
            for column in range(tree.columnCount()):
                widget = tree.itemWidget(item, column)
                if widget is not None:
                    row_height = max(
                        row_height,
                        widget.sizeHint().height() + vertical_padding,
                    )
                    continue
                text = item.text(column)
                if not text:
                    continue
                available_width = max(
                    tree.columnWidth(column) - horizontal_padding,
                    40,
                )
                bounds = tree.fontMetrics().boundingRect(
                    QRect(0, 0, available_width, 10_000),
                    int(text_flags),
                    text,
                )
                row_height = max(row_height, bounds.height() + vertical_padding)
            row_size = QSize(0, row_height)
            for column in range(tree.columnCount()):
                item.setSizeHint(column, row_size)

    def _remap_selector(self, remap: dict[str, Any], tooltip: str) -> QComboBox:
        selector = QComboBox(self.review_tree)
        self._prepare_table_combo(selector)
        selector.setToolTip(tooltip)
        selector.addItem("Choose replacement", "")
        for candidate in remap.get("candidates", []) or []:
            if not isinstance(candidate, dict):
                continue
            path = str(candidate.get("path") or "").strip()
            if not path:
                continue
            name = str(candidate.get("name") or Path(path).name or path)
            selector.addItem(name, path)
        if selector.count() == 2:
            selector.setCurrentIndex(1)
        selector.currentIndexChanged.connect(self._on_remap_selection_changed)
        if selector.currentData():
            self._schedule_remap_review_refresh()
        return selector

    def _review_ready_for_recheck(self) -> bool:
        return self._submission_projection().recheck_kind is not None

    def _on_remap_selection_changed(self, *_args: Any) -> None:
        """Synchronize every visible review surface after a remap choice."""
        if getattr(self, "_refreshing_remap_review", False):
            return
        self._sync_apply_state()
        self._sync_remap_status_copy()
        if hasattr(self, "review_actions_layout"):
            self._refresh_review_action_cards()
        self._refresh_review_import_summary()
        self._sync_remap_report_rows()
        self._schedule_remap_review_refresh()

    def _schedule_remap_review_refresh(self) -> None:
        if getattr(self, "_refreshing_remap_review", False) or getattr(
            self,
            "_remap_review_refresh_scheduled",
            False,
        ):
            return
        self._remap_review_refresh_scheduled = True
        QTimer.singleShot(0, self._finish_remap_review_refresh)

    def _finish_remap_review_refresh(self) -> None:
        self._remap_review_refresh_scheduled = False
        if not hasattr(self, "review_tree"):
            return
        self._refreshing_remap_review = True
        try:
            self._refresh_review_tree()
            self._sync_remap_report_rows()
            self._sync_apply_state()
            self._sync_remap_status_copy()
            if hasattr(self, "review_actions_layout"):
                self._refresh_review_action_cards()
            self._refresh_review_import_summary()
            self._fit_tree_columns_to_viewport(self.review_tree)
            self._fit_review_tree_height()
        finally:
            self._refreshing_remap_review = False

    def _sync_remap_status_copy(self) -> None:
        self._sync_review_status_copy()

    def _sync_review_status_copy(self) -> None:
        if not hasattr(self, "decision_label"):
            return
        recheck_kind = self._submission_projection().recheck_kind
        if recheck_kind == "remap":
            self.decision_label.setText("Ready to apply remap.")
            self.confirmation_label.setText(
                "Replacement files selected. Apply remap to recheck this recipe."
            )
        elif recheck_kind in {"event_values", "interpretation_choices"}:
            self.decision_label.setText("Ready to recheck and import.")
            self.confirmation_label.clear()
        else:
            self.decision_label.setText(self._decision_text())
            self.confirmation_label.setText(self._confirmation_text())
        if hasattr(self, "step_stack"):
            final_step = self.step_stack.currentIndex() == len(self._step_titles) - 1
            self.confirmation_label.setVisible(
                final_step and bool(self.confirmation_label.text())
            )

    def _sync_remap_report_rows(self) -> None:
        for widgets_name, items_name in (
            ("_eeg_file_remap_widgets", "_eeg_file_remap_report_items"),
            (
                "_label_carrier_remap_widgets",
                "_label_carrier_remap_report_items",
            ),
        ):
            widgets = getattr(self, widgets_name, {})
            items = getattr(self, items_name, {})
            for saved, selector in widgets.items():
                item = items.get(saved)
                if item is None:
                    continue
                replacement = self._combo_current_data(selector)
                saved_name = Path(saved).name or saved
                if replacement:
                    detail = (
                        f"Replacement selected for {saved_name}: "
                        f"{Path(replacement).name}."
                    )
                    item.setText(2, detail)
                    item.setToolTip(2, detail)
                    continue
                detail = f"Saved recipe file is missing: {saved_name}."
                item.setText(2, detail)
                item.setToolTip(2, detail)

    def _review_rows(self) -> list[ReviewRow]:
        rows = build_review_rows(
            preview=self.preview,
            validation_decision=self.validation_decision,
            scan_result=self.scan_result,
        )
        return [
            self._current_review_row(row)
            for row in rows
            if not self._review_row_is_resolved(row)
        ]

    def _primary_review_rows(self) -> list[ReviewRow]:
        action_items = self.preview.get("action_items") or self.validation_decision.get(
            "action_items"
        )
        blocking_items = [
            item
            for item in action_items or []
            if isinstance(item, dict)
            and str(item.get("severity") or "").strip().lower() == "blocked"
        ]
        if self.decision == "blocked" and blocking_items:
            rows = action_item_rows(blocking_items)
        else:
            rows = build_primary_review_rows(
                preview=self.preview,
                validation_decision=self.validation_decision,
            )
        return [
            self._current_review_row(row)
            for row in rows
            if not self._review_row_is_resolved(row)
        ]

    def _current_review_row(self, row: ReviewRow) -> ReviewRow:
        """Replace stale backend pairing counts with the user's current mapping."""
        target_step, issue, impact, next_action = row
        if target_step != "Match Labels":
            return row
        pairing_marker = "label carrier pairing is incomplete"
        if pairing_marker not in " ".join((issue, impact)).casefold():
            return row
        current_reason = self._loaded_label_pairing_result().blocking_reason()
        if not current_reason:
            return row
        if pairing_marker in issue.casefold():
            issue = current_reason
        elif pairing_marker in impact.casefold():
            impact = current_reason
        return target_step, issue, impact, next_action

    def _review_row_is_resolved(self, row: ReviewRow) -> bool:
        if self._review_metadata_is_complete() and is_metadata_review_row(row):
            return True
        if self._review_row_is_resolved_by_remap(row):
            return True
        return row[0] == "Match Labels" and not self._label_placement_needs_review()

    def _review_row_is_resolved_by_remap(self, row: ReviewRow) -> bool:
        text = " ".join(row[1:]).casefold()
        eeg_options = self._eeg_file_remap_options()
        label_options = self._label_carrier_remap_options()
        snapshots = getattr(self, "_remap_review_choice_snapshot", None)
        if snapshots is None:
            eeg_choices = self._eeg_file_remap_choices()
            label_choices = self._label_carrier_remap_choices()
        else:
            eeg_choices, label_choices = snapshots
        eeg_complete = bool(eeg_options) and len(eeg_choices) == len(eeg_options)
        label_complete = bool(label_options) and len(label_choices) == len(
            label_options
        )
        if eeg_complete and any(
            marker in text
            for marker in (
                "selected eeg file",
                "recipe eeg file",
                "replacement eeg file",
            )
        ):
            return True
        return label_complete and any(
            marker in text
            for marker in (
                "label/event carrier",
                "recipe label file",
                "replacement label",
            )
        )

    def _toggle_import_report(self) -> None:
        visible = not self.import_report_card.isVisible()
        if visible:
            self._refresh_review_tree()
            self._refresh_import_report_summary()
        self.import_report_card.setVisible(visible)
        self.import_report_toggle.setText(
            "Hide import report" if visible else "View import report"
        )
        if visible:
            self._fit_tree_columns_to_viewport(self.review_tree)
        self._fit_review_tree_height()
        if visible:
            self.review_tree.updateGeometry()
        self.import_report_card.updateGeometry()
        self._sync_review_dialog_geometry()
        self._sync_scroll_policy()
        QTimer.singleShot(0, self._refit_review_tree_after_layout)

    def _refit_review_tree_after_layout(self) -> None:
        """Fill the settled report viewport without a trailing header gap."""
        if hasattr(self, "review_tree") and self.import_report_card.isVisible():
            self._fit_tree_columns_to_viewport(self.review_tree)

    def _refresh_review_tree(self) -> None:
        """Rebuild the detailed report without losing current remap choices."""
        eeg_choices = self._eeg_file_remap_choices()
        label_choices = self._label_carrier_remap_choices()
        self._remap_review_choice_snapshot = (eeg_choices, label_choices)
        try:
            self._eeg_file_remap_widgets.clear()
            self._label_carrier_remap_widgets.clear()
            self._eeg_file_remap_report_items = {}
            self._label_carrier_remap_report_items = {}
            self.review_tree.clear()
            self._populate_review_tree()
            for saved, replacement in eeg_choices.items():
                selector = self._eeg_file_remap_widgets.get(saved)
                if selector is not None:
                    self._set_combo_current_data(selector, replacement)
            for saved, replacement in label_choices.items():
                selector = self._label_carrier_remap_widgets.get(saved)
                if selector is not None:
                    self._set_combo_current_data(selector, replacement)
            self._sync_remap_report_rows()
        finally:
            del self._remap_review_choice_snapshot

    def _review_metadata_is_complete(self) -> bool:
        _complete_count, missing_fields = self._metadata_completion_counts()
        return metadata_required_fields_complete(
            row_count=len(self._metadata_items),
            missing_fields=missing_fields,
            required_fields=({"subject"}),
        )

    @staticmethod
    def _compact_review_rows(rows: list[ReviewRow]) -> list[ReviewRow]:
        return compact_review_rows(rows)

    @staticmethod
    def _merged_review_rows(rows: list[ReviewRow]) -> list[ReviewRow]:
        return merge_review_rows(rows)

    @staticmethod
    def _target_step_for_review_text(text: str) -> str:
        return target_step_for_review_text(text)

    def _recipe_trace_rows(self, values: Any) -> list[tuple[str, str, str, str]]:
        if not isinstance(values, list):
            return []
        rows: list[tuple[str, str, str, str]] = []
        trace_labels = {
            "scan": "Source scan",
            "candidate": "Interpretation candidate",
            "preview": "Interpretation preview",
            "validate": "Validation decision",
            "validation": "Validation decision",
            "apply": "Applied interpretation",
            "metadata": "Metadata decision",
            "metadata_override": "Metadata override",
            "label": "Label decision",
            "labels": "Label decision",
            "label_carrier": "Label carrier decision",
            "label_import": "Label import",
            "class_map": "Class map decision",
            "recipe": "Recipe",
        }
        choice_labels = {
            "metadata_overrides": "Metadata choices",
            "event_roles": "Event use choices",
            "label_carriers": "Label carrier choices",
            "class_map": "Class map choices",
            "eeg_file_remap": "EEG file remap",
            "label_carrier_remap": "Label carrier remap",
            "label_sources": "Label source choices",
            "skip_labels": "Label skip choice",
        }
        for value in values:
            raw = str(value).strip()
            if not raw:
                continue
            trace_key, _, trace_detail = raw.partition(":")
            trace_key = trace_key.strip().lower()
            trace_detail = trace_detail.strip().lower()
            item = trace_labels.get(trace_key)
            if trace_key == "choices":
                item = choice_labels.get(trace_detail, "Saved choices")
            if item is None:
                item = self._label_choice_display(trace_key)
            rows.append(
                (
                    "Review and Import",
                    item,
                    f"{item} is saved in the import recipe.",
                    "No action needed.",
                )
            )
        return rows

    def _confirmation_text(self) -> str:
        if self.decision == "blocked":
            has_eeg_remap = self._has_eeg_file_remap_options()
            has_label_remap = self._has_label_carrier_remap_options()
            if has_eeg_remap and has_label_remap:
                return (
                    "Choose replacement EEG files and label/event carriers, then "
                    "apply the remap to recheck this saved recipe."
                )
            if has_eeg_remap:
                return (
                    "Choose a replacement EEG file, then apply the remap "
                    "to recheck this saved recipe."
                )
            if has_label_remap:
                return (
                    "Choose a replacement label/event carrier, then apply the remap "
                    "to recheck this saved recipe."
                )
            return ""
        if self.decision == "needs_confirmation":
            return ""
        if self.decision == "safe":
            return ""
        return ""
