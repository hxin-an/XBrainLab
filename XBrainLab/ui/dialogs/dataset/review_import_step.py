"""Review and Import step helpers for the Data Import wizard."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from os.path import commonprefix
from pathlib import Path
from posixpath import splitext
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from XBrainLab.backend.application.data_interpretation_pairing import (
    LabelPairingResult,
    resolve_label_file_pairing,
)
from XBrainLab.backend.application.data_interpretation_path_identity import (
    normalized_path_identity,
    path_basename,
)
from XBrainLab.backend.application.data_interpretation_review import (
    target_step_for_interpretation_text,
)
from XBrainLab.ui.components.presentation import ElidingLabel
from XBrainLab.ui.dialogs.dataset.review_import_presenter import (
    SubmissionFacts,
    SubmissionProjection,
    ValidationActionItem,
    ValidationReviewContract,
    adapt_serialized_validation_decision,
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
    compact_review_rows,
    format_capability_notes,
    merge_review_rows,
    recipe_reload_rows,
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
        # Parent the rows before rendering can show their controls. Otherwise Qt
        # briefly creates independent native windows for these labels/buttons.
        layout.addLayout(self._review_import_rows_layout)
        self._build_recipe_replacements(layout)
        self._render_review_import_rows()

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
            summary_label.setToolTip(row.get("detail", ""))
            summary_label.setAccessibleDescription(row.get("detail", ""))
            summary_label.setSizePolicy(
                QSizePolicy.Policy.Ignored,
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
            summary.setMinimumHeight(0)
            wrapped_height = summary.heightForWidth(summary.width())
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
                wrapped_height,
                text_bounds.height(),
                summary.fontMetrics().height() + 14,
            )
            if required_height > 0:
                if summary.minimumHeight() != required_height:
                    summary.setMinimumHeight(required_height)
                layout.setRowMinimumHeight(row, required_height)
        layout.activate()

    @staticmethod
    def _review_status_object_name(status: str) -> str:
        return {
            "Ready": "DataImportReviewStatusReady",
            "Completed": "DataImportReviewStatusReady",
            "Safe": "DataImportReviewStatusReady",
            "Saved": "DataImportReviewStatusReady",
            "Loaded": "DataImportReviewStatusNeutral",
            "Skipped": "DataImportReviewStatusNeutral",
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
            affected_count = self._metadata_affected_file_count(missing_notes)
            if affected_count > 1:
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
            not self._skip_labels
            and self._label_source_mode() == "loaded_label_files"
            and self._active_label_carrier_count() <= 0
        ):
            label_source_status = "Missing"
        label_placement_status = "Skipped" if self._skip_labels else "Ready"
        label_placement_summary = self._review_label_placement_text()
        if not self._skip_labels and self._should_show_label_table_fallback():
            label_placement_status = "Action required"
        elif self._label_placement_needs_review() or (
            self._has_review_action_for_step("Match Labels")
            and self._submission_projection().recheck_kind
            not in {"event_values", "interpretation_choices"}
        ):
            label_placement_status = "Needs review"

        recipe_selected = self.save_recipe_check.isChecked()
        if recipe_selected:
            recipe_status = "Will save"
            recipe_summary = "After successful import"
            recipe_action = "Cancel save"
        elif self._has_loaded_import_recipe() and not self._recipe_choices_changed():
            recipe_status = "Loaded"
            recipe_summary = "Saved settings applied"
            recipe_action = "Save recipe"
        else:
            recipe_status = "Not saved"
            recipe_summary = self._review_recipe_note_text()
            recipe_action = "Save recipe"

        rows = [
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

        notes_by_row = self._review_notes_by_row()
        for row in rows:
            notes = notes_by_row.get(row["item"], [])
            if notes:
                titles = list(dict.fromkeys(title for title, _ in notes if title))
                if titles:
                    brief = titles[0]
                    if len(titles) > 1:
                        brief += f" (+{len(titles) - 1} more)"
                    row["summary"] = f"{row['summary']} · {brief}"
                row["detail"] = "\n".join(dict.fromkeys(detail for _, detail in notes))
        return rows

    def _review_notes_by_row(self) -> dict[str, list[tuple[str, str]]]:
        notes: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for item, title, detail in self._validation_review_notes():
            notes[item].append((title, detail))
        for item, title, detail in self._format_review_notes():
            notes[item].append((title, detail))
        for _step, issue, detail, status in recipe_reload_rows(
            self.preview.get("recipe_reload_summary")
        ):
            if status.casefold() == "changed":
                notes["Recipe"].append((f"{issue} changed", f"{issue}: {detail}"))
        return notes

    def _format_review_notes(self) -> Iterator[tuple[str, str, str]]:
        capabilities = self.preview.get("format_capabilities") or self.scan_result.get(
            "format_capabilities"
        )
        if not capabilities:
            return
        scanned = self.scan_result.get("eeg_files") or []
        selected = self.preview.get(
            "selected_eeg_files",
            self._initial_choices.get("selected_eeg_files", scanned),
        )
        eeg_paths = {normalized_path_identity(str(path)) for path in selected or []}
        narrowed_scope = bool(
            {normalized_path_identity(str(path)) for path in scanned} - eeg_paths
        )
        use_label_files = (
            not self._skip_labels and self._label_source_mode() == "loaded_label_files"
        )
        label_paths = set()
        if use_label_files:
            for tree_item, carrier in self._label_carrier_items:
                key = self._label_carrier_key(tree_item, carrier)
                if key and not self._is_label_carrier_excluded(key):
                    label_paths.add(normalized_path_identity(key))
        associated_paths = eeg_paths | label_paths
        associated_stems = associated_paths | {
            splitext(path)[0] for path in associated_paths
        }
        by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for capability in capabilities or []:
            if not isinstance(capability, dict) or capability.get("status") not in {
                "needs_review",
                "limited",
                "blocked",
                "unsupported",
            }:
                continue
            role = str(capability.get("role") or "")
            path = normalized_path_identity(str(capability.get("path") or ""))
            if role == "eeg" and path and path not in eeg_paths:
                continue
            if role == "external_labels" and (
                not use_label_files or (path and path not in label_paths)
            ):
                continue
            if (
                role in {"sidecar", "device_export"}
                and narrowed_scope
                and path
                and path not in associated_paths
                and splitext(path)[0] not in associated_stems
            ):
                continue
            item = {
                "external_labels": "Label source",
                "sidecar": "Label source",
                "metadata": "Metadata",
            }.get(role, "EEG data")
            if item == "Label source" and (
                self._skip_labels
                or self._is_label_carrier_excluded(str(capability.get("path") or ""))
            ):
                continue
            by_item[item].append(capability)
        for item, group in by_item.items():
            for title, detail in format_capability_notes(group):
                yield item, title, detail

    def _validation_review_notes(self) -> Iterator[tuple[str, str, str]]:
        review = self._validation_review_contract()
        notes: list[ReviewRow] = []
        if review.is_valid:
            notes = self._unresolved_review_rows(
                [
                    item.to_review_row()
                    for item in review.action_items
                    if (
                        item.severity in {"warning", "limited"}
                        or (
                            review.decision == "blocked"
                            and item.severity == "needs_confirmation"
                        )
                    )
                ]
            )
        known_issues = {row[1] for row in notes}
        for issue in self._bids_carrier_notes():
            if issue not in known_issues:
                notes.append(("Match Labels", issue, "", ""))
                known_issues.add(issue)

        target_items = {
            "Choose EEG Data": "EEG data",
            "Review Metadata": "Metadata",
            "Load Labels": "Label source",
            "Match Labels": "Label placement",
        }
        for step, issue, impact, action in merge_review_rows(notes):
            target = (
                target_step_for_interpretation_text(issue)
                if step == "Review and Import"
                else step
            )
            item = target_items.get(
                target, "Recipe" if "recipe" in issue.casefold() else "EEG data"
            )
            if self._skip_labels and item in {"Label source", "Label placement"}:
                continue
            details = [issue]
            for text in (impact, action):
                if (
                    text
                    and text not in details
                    and not self._review_note_detail_is_generic(text)
                ):
                    details.append(text)
            title = issue
            count, _, _ = impact.partition(":")
            if count.endswith(" files affected"):
                title = f"{issue.rstrip('.')} ({count})"
            yield item, title, " ".join(details)

    def _bids_carrier_notes(self) -> Iterator[str]:
        if not (
            self._is_bids_source()
            and self._label_source_mode() == "loaded_label_files"
            and not self._skip_labels
        ):
            return
        for tree_item, carrier in self._label_carrier_items:
            if carrier.get("format") != "BIDS events":
                continue
            path = self._label_carrier_key(tree_item, carrier)
            if self._is_label_carrier_excluded(path):
                continue
            name = str(carrier.get("name") or Path(path).name)
            sidecar = carrier.get("events_json_sidecar_present")
            warnings = [
                str(value)
                for value in carrier.get("warnings", []) or []
                if value
                and not (
                    sidecar is True and "events.json sidecar is missing" in str(value)
                )
            ]
            if sidecar is False and not any(
                "events.json" in value for value in warnings
            ):
                warnings.append("events.json sidecar is missing.")
            for warning in warnings:
                yield warning if name in warning else f"{name}: {warning}"

    @classmethod
    def _review_note_detail_is_generic(cls, text: str) -> bool:
        return cls._review_action_detail_is_generic(text) or text.casefold() in {
            "open the report for details.",
            "no action needed.",
            "no action is required unless the import summary is unexpected.",
            "import may still be usable, but downstream labels or "
            "metadata may need review.",
            "open the target step and resolve or confirm this item before import.",
        }

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
        return self._validation_review_contract().requires_action_at(target_step)

    def _label_placement_needs_review(self) -> bool:
        if self._skip_labels:
            return False
        if self._label_source_mode() == "internal_events":
            if not self._internal_event_preview_payload():
                return not bool(self._class_map_items or self._event_role_items)
            selection = self._current_internal_event_selection()
            selected = set(selection["label_event_codes"])
            not_selected = set(selection["not_label_event_codes"])
            observed = selected | not_selected
            class_map = selection["class_map"]
            return (
                not observed
                or bool(selected & not_selected)
                or not all(str(class_map.get(code) or "").strip() for code in selected)
            )
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
        if not hasattr(self, "rule_placement_method_combo"):
            return False
        label_field = self._combo_current_data(self.rule_label_field_combo)
        use_as = self._combo_current_data(self.rule_use_as_combo)
        granularity = self._combo_current_data(self.rule_label_unit_combo)
        placement_method = self._combo_current_data(self.rule_placement_method_combo)
        if not all((label_field, use_as, granularity, placement_method)):
            return True
        if placement_method == "eeg_event":
            return not bool(self._event_order_target_codes())
        anchor = self._combo_current_data(self.rule_alignment_combo)
        if not anchor:
            return True
        if placement_method == "interval":
            return not bool(self._combo_current_data(self.rule_duration_field_combo))
        if placement_method == "time_field":
            return not bool(self._combo_current_data(self.rule_time_model_combo))
        return placement_method not in {"event_code"}

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

    def _validation_review_contract(self) -> ValidationReviewContract:
        """Adapt the serialized backend decision at the UI boundary."""
        return adapt_serialized_validation_decision(self.validation_decision)

    def _submission_facts(self) -> SubmissionFacts:
        return SubmissionFacts(
            validation=self._validation_review_contract(),
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
        edited_targets = self._edited_action_targets()
        if not edited_targets:
            return False

        review = self._validation_review_contract()
        if not review.is_valid:
            return False
        blocking_targets = review.blocking_action_targets
        return bool(blocking_targets) and blocking_targets.issubset(edited_targets)

    def _edited_action_targets(self) -> set[str]:
        choices = self._edited_choices()
        edited_targets: set[str] = set()
        if (
            self._is_bids_source()
            and self._skip_labels
            and not self._initial_choices.get("skip_labels")
        ):
            edited_targets.update({"Load Labels", "Match Labels"})
        if (
            self._is_bids_source()
            and choices.get("label_carrier") == "embedded_events"
            and choices.get("internal_event_selection", {}).get("label_event_codes")
            and choices["internal_event_selection"]
            != self._initial_choices.get("internal_event_selection")
        ):
            edited_targets.add("Load Labels")
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
        return edited_targets

    def _submission_projection(self) -> SubmissionProjection:
        return project_submission(self._submission_facts())

    def can_submit_for_backend_review(self) -> bool:
        """Return whether current choices may be sent back to the backend."""
        return self._submission_projection().can_submit_for_backend_review

    def _refresh_review_import_summary(self) -> None:
        if hasattr(self, "_review_import_rows_layout"):
            self._render_review_import_rows()
            self._settle_review_step_layout()

    def _default_review_action_row(self) -> tuple[str, str, str, str]:
        review = self._validation_review_contract()
        if (not review.is_valid or review.decision == "blocked") and not (
            self._review_ready_for_recheck()
        ):
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
            preview_text=names[0] if len(names) == 1 else "",
        )

    def _review_label_source_text(self) -> str:
        if self._skip_labels:
            return "Labels explicitly skipped"
        return label_source_summary(
            source_mode=self._label_source_mode(),
            internal_candidate_count=len(self._class_map_items)
            or len(self._event_role_items),
            active_carrier_count=self._active_label_carrier_count(),
            has_bids_events=self._has_bids_events(),
            has_extra_sources=bool(self._extra_label_sources),
        )

    def _review_label_placement_text(self) -> str:
        if self._skip_labels:
            return (
                "Supervised epoching and training are unavailable "
                "without reviewed labels"
            )
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
            field = self.rule_label_field_combo.currentText().strip() or "Label field"
            method = (
                self.rule_placement_method_combo.currentText().strip()
                or "Placement needs review"
            )
            unresolved = editor.unresolved_values()
            if unresolved:
                return f"{len(unresolved)} event values need review"
            return f"{field} · {method} · {editor.row_count()} event values reviewed"
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
        _target_step: str,
        _issue: str,
        _impact: str,
        _next_action: str,
    ) -> str:
        submission = self._submission_projection()
        if submission.recheck_kind is not None:
            return ""
        review = self._validation_review_contract()
        if not review.is_valid or review.decision == "blocked":
            return "Cannot import yet"
        if review.decision == "needs_confirmation":
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
        title = self._review_action_issue_title(target_step, issue, impact, next_action)
        issue_label = QLabel(title)
        issue_label.setObjectName("DataImportActionIssue")
        issue_label.setWordWrap(True)
        layout.addWidget(issue_label)

        details: list[str] = []
        is_local_review_item = target_step == "Review and Import"
        if (
            not is_local_review_item
            and issue not in (title, impact, next_action)
            and not self._review_action_detail_is_generic(issue)
        ):
            details.append(issue)
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
            "this import cannot be applied until the issue is fixed.",
            "fix this item before importing.",
            "review the target step and confirm the choice.",
            "review match labels.",
            "review metadata",
            "confirm label placement.",
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

    def _build_recipe_replacements(self, layout: QVBoxLayout) -> None:
        """Keep selectors mounted below Recipe while the six status rows refresh."""
        groups = (
            ("EEG", self._eeg_file_remap_options(), self._eeg_file_remap_widgets),
            (
                "label",
                self._label_carrier_remap_options(),
                self._label_carrier_remap_widgets,
            ),
        )
        for kind, options, widgets in groups:
            saved_labels = self._recipe_file_labels(options, "saved", "saved_name")
            for remap in options:
                saved = str(remap.get("saved") or "").strip()
                if not saved:
                    continue
                description = f"Replace {kind} file {saved_labels[saved]}"
                line = QHBoxLayout()
                layout.addLayout(line)
                label = ElidingLabel(description, layout.parentWidget())
                label.setSizePolicy(
                    QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
                )
                label.setToolTip(saved)
                selector = QComboBox(layout.parentWidget())
                self._prepare_table_combo(selector)
                selector.setAccessibleName(description)
                label.setBuddy(selector)
                selector.addItem("Choose replacement", "")
                candidates = self._recipe_file_labels(
                    remap.get("candidates") or [], "path", "name"
                )
                for path, name in candidates.items():
                    selector.addItem(name, path)
                    selector.setItemData(
                        selector.count() - 1, path, Qt.ItemDataRole.ToolTipRole
                    )
                selector.currentIndexChanged.connect(
                    lambda _index, combo=selector: combo.setToolTip(
                        str(combo.currentData() or combo.currentText())
                    )
                )
                selector.setToolTip(selector.currentText())
                if selector.count() == 2:
                    selector.setCurrentIndex(1)
                widgets[saved] = selector
                selector.currentIndexChanged.connect(self._on_remap_selection_changed)
                line.addWidget(label, 1)
                line.addWidget(selector, 1)

    @staticmethod
    def _recipe_file_labels(
        entries: list[dict[str, Any]], path_key: str, name_key: str
    ) -> dict[str, str]:
        labels = {}
        groups: dict[str, list[str]] = defaultdict(list)
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            path = str(entry.get(path_key) or "").strip()
            if not path or path in labels:
                continue
            name = str(entry.get(name_key) or path_basename(path))
            labels[path] = name
            groups[name.casefold()].append(path)
        for paths in groups.values():
            if len(paths) > 1:
                normalized = [path.replace("\\", "/") for path in paths]
                prefix = commonprefix(normalized)
                start = prefix.rfind("/") + 1
                for path in paths:
                    labels[path] = path[start:]
        return labels

    def _review_ready_for_recheck(self) -> bool:
        return self._submission_projection().recheck_kind is not None

    def _on_remap_selection_changed(self) -> None:
        self._sync_apply_state()
        self._sync_review_status_copy()
        self._refresh_review_action_cards()
        self._refresh_review_import_summary()

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

    def _primary_review_rows(self) -> list[ReviewRow]:
        review = self._validation_review_contract()
        if not review.is_valid:
            rows = [self._default_review_action_row()]
        elif review.decision == "blocked":
            rows = self._action_item_review_rows(review.items_with_severity("blocked"))
        elif review.decision == "needs_confirmation":
            rows = self._action_item_review_rows(
                review.items_with_severity("needs_confirmation")
            )
        else:
            rows = []
        return self._unresolved_review_rows(compact_review_rows(rows))

    @staticmethod
    def _action_item_review_rows(
        action_items: tuple[ValidationActionItem, ...],
    ) -> list[ReviewRow]:
        return [item.to_review_row() for item in action_items]

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

    def _unresolved_review_rows(self, rows: list[ReviewRow]) -> list[ReviewRow]:
        if not rows:
            return []
        resolved = (
            self._edited_action_targets() if self._review_ready_for_recheck() else set()
        )
        eeg_options = self._eeg_file_remap_options()
        label_options = self._label_carrier_remap_options()
        if eeg_options and len(self._eeg_file_remap_choices()) == len(eeg_options):
            resolved.add("Choose EEG Data")
        if label_options and len(self._label_carrier_remap_choices()) == len(
            label_options
        ):
            resolved.update({"Load Labels", "Match Labels"})
        return [self._current_review_row(row) for row in rows if row[0] not in resolved]

    @staticmethod
    def _merged_review_rows(rows: list[ReviewRow]) -> list[ReviewRow]:
        return merge_review_rows(rows)

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
