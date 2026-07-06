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
    QSizePolicy,
    QTreeWidgetItem,
    QVBoxLayout,
)

from XBrainLab.ui.dialogs.dataset.review_import_presenter import (
    eeg_data_summary,
    internal_label_placement_summary,
    label_source_summary,
    metadata_summary,
    recipe_note,
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
        layout.addWidget(self.decision_label)
        rows_layout = QGridLayout()
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_layout.setHorizontalSpacing(12)
        rows_layout.setVerticalSpacing(6)
        for index, (label, value) in enumerate(self._review_import_summary_rows()):
            rows_layout.addWidget(
                self._review_summary_cell(label, value),
                index // 2,
                index % 2,
            )
        rows_layout.setColumnStretch(0, 1)
        rows_layout.setColumnStretch(1, 1)
        layout.addLayout(rows_layout)
        layout.addWidget(self._review_recipe_note_panel())

    def _review_recipe_note_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("DataImportApplyConfirmPanel")
        rows_layout = QGridLayout()
        rows_layout.setContentsMargins(10, 8, 10, 8)
        rows_layout.setHorizontalSpacing(12)
        rows_layout.setVerticalSpacing(4)
        note_title = QLabel("Recipe")
        note_title.setObjectName("DataImportSummaryLabel")
        self.review_recipe_note_label = QLabel(self._review_recipe_note_text())
        self.review_recipe_note_label.setObjectName("DataImportSummaryValue")
        self.review_recipe_note_label.setWordWrap(True)
        self.review_recipe_note_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        rows_layout.addWidget(note_title, 0, 0)
        rows_layout.addWidget(self.review_recipe_note_label, 0, 1)
        rows_layout.addWidget(self.confirmation_label, 1, 1)
        rows_layout.addWidget(
            self.save_recipe_check,
            0,
            2,
            2,
            1,
            alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        rows_layout.setColumnMinimumWidth(0, 100)
        rows_layout.setColumnStretch(1, 1)
        panel.setLayout(rows_layout)
        return panel

    def _review_import_summary_rows(self) -> list[tuple[str, str]]:
        return [
            ("EEG data", self._review_eeg_data_text()),
            ("Metadata", self._review_metadata_text()),
            ("Label source", self._review_label_source_text()),
            ("Label placement", self._review_label_placement_text()),
        ]

    def _review_summary_cell(self, label: str, value: str) -> QFrame:
        cell = QFrame()
        cell.setObjectName("DataImportSummaryCell")
        cell.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        layout = QVBoxLayout(cell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        label_widget = QLabel(label)
        label_widget.setObjectName("DataImportSummaryLabel")
        value_widget = QLabel(value)
        value_widget.setObjectName("DataImportSummaryValue")
        value_widget.setWordWrap(True)
        value_widget.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._review_summary_value_labels[label] = value_widget
        layout.addWidget(label_widget)
        layout.addWidget(value_widget)
        return cell

    def _refresh_review_import_summary(self) -> None:
        if not hasattr(self, "_review_summary_value_labels"):
            return
        for label, value in self._review_import_summary_rows():
            value_label = self._review_summary_value_labels.get(label)
            if value_label is not None:
                value_label.setText(value)
        if hasattr(self, "review_recipe_note_label"):
            self.review_recipe_note_label.setText(self._review_recipe_note_text())

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
        return metadata_summary(
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
            grouped.setdefault(group_title, []).append(
                (target_step, issue, impact, next_action)
            )
        for group_title in (
            "Cannot import yet",
            "Needs your decision",
            "Review before import",
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
        if any(
            token in lowered
            for token in (
                "choose",
                "fix",
                "select",
                "resolve",
                "provide",
                "confirm",
                "conversion",
                "missing",
                "needs review",
            )
        ):
            return "Needs your decision"
        if "review" in lowered:
            return "Review before import"
        return "Needs your decision"

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
        issue_label = QLabel(issue)
        issue_label.setObjectName("DataImportActionIssue")
        issue_label.setWordWrap(True)
        layout.addWidget(issue_label)

        details: list[str] = []
        is_local_review_item = target_step == "Review and Import"
        if impact:
            details.append(impact)
        if next_action and next_action not in details:
            details.append(next_action)
        for detail in details:
            detail_label = QLabel(detail)
            detail_label.setObjectName("DataImportActionMeta")
            detail_label.setWordWrap(True)
            layout.addWidget(detail_label)
        if not is_local_review_item and target_step in self._step_titles:
            action_row = QHBoxLayout()
            action_row.setContentsMargins(0, 2, 0, 0)
            action_row.addStretch()
            button = QPushButton(self._review_action_button_text(target_step))
            button.setObjectName("DataImportInlineAction")
            button.clicked.connect(
                lambda _checked=False, step=target_step: self._go_to_step(
                    self._step_titles.index(step)
                )
            )
            action_row.addWidget(button)
            layout.addLayout(action_row)
        return row

    @staticmethod
    def _review_action_button_text(target_step: str) -> str:
        return {
            "Choose EEG Data": "Review EEG Data",
            "Load Labels": "Fix Labels",
            "Review Metadata": "Review Metadata",
            "Match Labels": "Fix Match Labels",
        }.get(target_step, target_step)

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
        if self._review_metadata_is_complete():
            rows = [row for row in rows if not is_metadata_review_row(row)]
        return rows

    def _primary_review_rows(self) -> list[ReviewRow]:
        rows = build_primary_review_rows(
            preview=self.preview,
            validation_decision=self.validation_decision,
        )
        if self._review_metadata_is_complete():
            rows = [row for row in rows if not is_metadata_review_row(row)]
        return rows

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
