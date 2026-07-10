"""Review and Import step helpers for the Data Import wizard."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidgetItem,
    QVBoxLayout,
)

from XBrainLab.backend.application.data_interpretation_pairing import (
    LabelPairingResult,
    resolve_label_file_pairing,
)
from XBrainLab.backend.application.resource_guard import (
    RISK_BLOCKING,
    RISK_SAFE,
    RISK_UNKNOWN,
    RISK_WARNING,
    ResourceChecker,
)
from XBrainLab.ui.dialogs.dataset.review_import_presenter import (
    eeg_data_summary,
    internal_label_placement_summary,
    label_source_summary,
    recipe_note,
)
from XBrainLab.ui.dialogs.dataset.review_import_presenter import (
    metadata_summary as metadata_review_summary_text,
)
from XBrainLab.ui.dialogs.dataset.review_presenter import (
    ReviewRow,
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
        self.save_recipe_check.setText("Save recipe")
        self._review_import_rows_layout = QGridLayout()
        self._review_import_rows_layout.setContentsMargins(0, 0, 0, 0)
        self._review_import_rows_layout.setHorizontalSpacing(10)
        self._review_import_rows_layout.setVerticalSpacing(6)
        self._render_review_import_rows()
        layout.addLayout(self._review_import_rows_layout)

        if hasattr(self, "import_report_toggle"):
            footer = QHBoxLayout()
            footer.setContentsMargins(0, 2, 0, 0)
            footer.addStretch()
            footer.addWidget(self.import_report_toggle)
            layout.addLayout(footer)

    def _render_review_import_rows(self) -> None:
        self._clear_review_import_rows()
        self._review_summary_value_labels.clear()
        for row_index, row in enumerate(self._review_import_status_rows()):
            item_label = QLabel(row["item"])
            item_label.setObjectName("DataImportReviewItem")
            status_label = QLabel(row["status"])
            status_label.setObjectName(self._review_status_object_name(row["status"]))
            summary_label = QLabel(row["summary"])
            summary_label.setObjectName("DataImportReviewSummary")
            summary_label.setWordWrap(True)
            summary_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self._review_summary_value_labels[row["item"]] = summary_label

            self._review_import_rows_layout.addWidget(item_label, row_index, 0)
            self._review_import_rows_layout.addWidget(status_label, row_index, 1)
            self._review_import_rows_layout.addWidget(summary_label, row_index, 2)
            action = row.get("action", "")
            if action:
                self._review_import_rows_layout.addWidget(
                    self._review_import_action(row),
                    row_index,
                    3,
                    alignment=Qt.AlignmentFlag.AlignRight,
                )
        self._review_import_rows_layout.setColumnMinimumWidth(0, 118)
        self._review_import_rows_layout.setColumnMinimumWidth(1, 96)
        self._review_import_rows_layout.setColumnStretch(2, 1)
        self.save_recipe_check.setVisible(True)

    @staticmethod
    def _review_status_object_name(status: str) -> str:
        return {
            "Ready": "DataImportReviewStatusReady",
            "Completed": "DataImportReviewStatusReady",
            "Safe": "DataImportReviewStatusReady",
            "Warning": "DataImportReviewStatusNeedsReview",
            "Too large": "DataImportReviewStatusMissing",
            "Unknown": "DataImportReviewStatusNeedsReview",
            "Needs review": "DataImportReviewStatusNeedsReview",
            "Missing": "DataImportReviewStatusMissing",
            "Incomplete": "DataImportReviewStatusIncomplete",
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
                if widget is self.save_recipe_check:
                    widget.setParent(None)
                else:
                    widget.deleteLater()

    def _review_import_action(self, row: dict[str, str]) -> QPushButton:
        action = row.get("action", "")
        if action == "Save recipe":
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
            label_placement_status = "Incomplete"
        elif (
            "need review" in label_placement_summary.lower()
            or self._has_review_action_for_step("Match Labels")
        ):
            label_placement_status = "Needs review"

        recipe_status = "Ready" if self._apply_allowed() else "Incomplete"
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
                    "Go to Label Placement"
                    if label_placement_status in {"Needs review", "Incomplete"}
                    else ""
                ),
            },
            self._resource_check_status_row(),
            {
                "item": "Recipe",
                "status": recipe_status,
                "summary": self._review_recipe_note_text(),
                "action": "Save recipe",
            },
        ]

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

    def _refresh_review_import_summary(self) -> None:
        if hasattr(self, "_review_import_rows_layout"):
            self._render_review_import_rows()

    def _default_review_action_row(self) -> tuple[str, str, str, str]:
        if self.decision == "blocked":
            return (
                "Review and Import",
                "Cannot import yet",
                "Blocking items must be resolved before this recipe can be applied.",
                "Fix the action items below, then apply.",
            )
        if self.decision == "needs_confirmation":
            return (
                "Review and Import",
                "Review import choices",
                "No blocking items were found.",
                "Apply when the summary matches your data.",
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
        return recipe_note(
            decision=self.decision,
            source_mode=self._label_source_mode(),
            has_internal_choices=bool(self._class_map_items or self._event_role_items),
            active_carrier_count=self._active_label_carrier_count(),
            needs_label_conversion=self._should_show_label_table_fallback(),
        )

    def _resource_check_status_row(self) -> dict[str, str]:
        result = self._import_resource_check_result()
        status = {
            RISK_SAFE: "Safe",
            RISK_WARNING: "Warning",
            RISK_BLOCKING: "Too large",
            RISK_UNKNOWN: "Unknown",
        }.get(result.risk_level, "Unknown")
        action = "Go to EEG Data" if result.risk_level == RISK_BLOCKING else ""
        return {
            "item": "Resource check",
            "status": status,
            "summary": self._review_resource_check_text(result),
            "action": action,
            "target_step": "Choose EEG Data",
        }

    def _review_resource_check_text(self, result) -> str:
        required = ResourceChecker.format_memory_size(result.required_memory_bytes)
        available = ResourceChecker.format_memory_size(result.available_memory_bytes)
        if result.risk_level == RISK_SAFE:
            return f"Estimated RAM {required} / Available RAM {available}"
        if result.risk_level == RISK_WARNING:
            return (
                f"Estimated RAM {required} / Available RAM {available} · "
                "review before import"
            )
        if result.risk_level == RISK_BLOCKING:
            return (
                f"Estimated RAM {required} / Available RAM {available} · "
                "select fewer files"
            )
        return "RAM availability could not be estimated on this system"

    def _resource_check_blocks_import(self) -> bool:
        return self._import_resource_check_result().risk_level == RISK_BLOCKING

    def _import_resource_check_result(self):
        paths = tuple(self._selected_eeg_file_paths())
        cached_paths = getattr(self, "_import_resource_check_paths", None)
        cached_result = getattr(self, "_import_resource_check", None)
        if cached_result is not None and cached_paths == paths:
            return cached_result
        result = ResourceChecker.check_dataset_load_safe(paths)
        self._import_resource_check_paths = paths
        self._import_resource_check = result
        return result

    def _selected_eeg_file_paths(self) -> list[str]:
        selected_files = self.preview.get("selected_eeg_files")
        if isinstance(selected_files, list) and selected_files:
            return [str(path) for path in selected_files if str(path).strip()]
        scan_files = [
            str(path)
            for path in self.scan_result.get("eeg_files", []) or []
            if str(path).strip()
        ]
        file_count = self.preview.get("file_count")
        selection = str(self.preview.get("source_selection") or "").lower()
        if (
            isinstance(file_count, int)
            and file_count >= 0
            and "selected" in selection
            and file_count < len(scan_files)
        ):
            return scan_files[:file_count]
        return scan_files

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
            if self.decision == "blocked":
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

    def _review_action_group_title(
        self,
        target_step: str,
        issue: str,
        impact: str,
        next_action: str,
    ) -> str:
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
                return "Event role mapping is incomplete"
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
        lowered = " ".join((issue, next_action)).lower()
        if target_step == "Match Labels":
            if "alignment" in lowered or "pair" in lowered or "carrier" in lowered:
                return "Go to Label Alignment"
            if "event role" in lowered or "event mapping" in lowered:
                return "Go to Event Mapping"
            return "Go to Label Placement"
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
        rows = self._review_rows()
        remap_added = False
        for remap in self._eeg_file_remap_options():
            saved = str(remap.get("saved") or "").strip()
            if not saved:
                continue
            saved_name = str(remap.get("saved_name") or Path(saved).name or saved)
            tree_item = QTreeWidgetItem(
                [
                    "Review and Import",
                    "Recipe EEG file",
                    f"Saved recipe file is missing: {saved_name}.",
                    "Choose file",
                ]
            )
            tree_item.setToolTip(
                2,
                "Choose the current EEG file that replaces this saved recipe file.",
            )
            self.review_tree.addTopLevelItem(tree_item)
            selector = self._remap_selector(
                remap,
                "Choose the replacement EEG file.",
            )
            self._eeg_file_remap_widgets[saved] = selector
            self.review_tree.setItemWidget(tree_item, 3, selector)
            remap_added = True
        for remap in self._label_carrier_remap_options():
            saved = str(remap.get("saved") or "").strip()
            if not saved:
                continue
            saved_name = str(remap.get("saved_name") or Path(saved).name or saved)
            tree_item = QTreeWidgetItem(
                [
                    "Review and Import",
                    "Recipe label file",
                    f"Saved recipe label is missing: {saved_name}.",
                    "Choose file",
                ]
            )
            tree_item.setToolTip(
                2,
                "Choose the current label/event carrier that replaces this "
                "saved recipe carrier.",
            )
            self.review_tree.addTopLevelItem(tree_item)
            selector = self._remap_selector(
                remap,
                "Choose the replacement label/event carrier.",
            )
            self._label_carrier_remap_widgets[saved] = selector
            self.review_tree.setItemWidget(tree_item, 3, selector)
            remap_added = True
        rows = self._merged_review_rows(rows)
        for target_step, issue, impact, next_action in rows:
            tree_item = QTreeWidgetItem([target_step, issue, impact, next_action])
            for column in range(4):
                tree_item.setToolTip(column, next_action or impact or issue)
            self.review_tree.addTopLevelItem(tree_item)
        if not rows and not remap_added:
            target_step, issue, impact, next_action = self._default_review_action_row()
            self.review_tree.addTopLevelItem(
                QTreeWidgetItem(
                    [target_step, issue, impact, next_action],
                )
            )

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
        selector.currentIndexChanged.connect(self._sync_apply_state)
        return selector

    def _review_rows(self) -> list[ReviewRow]:
        rows = build_review_rows(
            preview=self.preview,
            validation_decision=self.validation_decision,
            scan_result=self.scan_result,
        )
        return [row for row in rows if not self._review_row_is_resolved(row)]

    def _primary_review_rows(self) -> list[ReviewRow]:
        rows = build_primary_review_rows(
            preview=self.preview,
            validation_decision=self.validation_decision,
        )
        return [row for row in rows if not self._review_row_is_resolved(row)]

    def _review_row_is_resolved(self, row: ReviewRow) -> bool:
        if self._review_metadata_is_complete() and is_metadata_review_row(row):
            return True
        return row[0] == "Match Labels" and not self._label_placement_needs_review()

    def _toggle_import_report(self) -> None:
        visible = not self.import_report_card.isVisible()
        self.import_report_card.setVisible(visible)
        self.import_report_toggle.setText(
            "Hide import report" if visible else "View import report"
        )
        self._fit_review_tree_height()
        if visible:
            self._fit_tree_columns_to_viewport(self.review_tree)
            self.review_tree.updateGeometry()
        self.import_report_card.updateGeometry()
        self._sync_scroll_policy()

    def _review_metadata_is_complete(self) -> bool:
        _complete_count, missing_fields = self._metadata_completion_counts()
        return metadata_required_fields_complete(
            row_count=len(self._metadata_items),
            missing_fields=missing_fields,
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
            return "This interpretation is blocked and cannot be applied."
        if self.decision == "needs_confirmation":
            return ""
        if self.decision == "safe":
            return ""
        return "Review this interpretation before applying."
