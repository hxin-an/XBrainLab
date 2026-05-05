"""Preview dialog for Data Interpretation import decisions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.styles.theme import Theme
from XBrainLab.ui.table_sizing import scaled_column_widths


class DataInterpretationPreviewDialog(BaseDialog):
    """Show scan, metadata, warning, and validation details before apply."""

    def __init__(
        self,
        parent=None,
        scan_result: dict[str, Any] | None = None,
        preview: dict[str, Any] | None = None,
        validation_decision: dict[str, Any] | None = None,
    ):
        self.scan_result = dict(scan_result or {})
        self.preview = dict(preview or {})
        self.validation_decision = dict(validation_decision or {})
        self.workflow_steps_label: QLabel
        self.summary_label: QLabel
        self.source_summary_label: QLabel
        self.decision_label: QLabel
        self.confirmation_label: QLabel
        self.save_recipe_check: QCheckBox
        self.file_tree: QTreeWidget
        self.label_carrier_tree: QTreeWidget
        self.event_tree: QTreeWidget
        self.review_tree: QTreeWidget
        self.button_box: QDialogButtonBox
        self._metadata_items: list[tuple[QTreeWidgetItem, dict[str, Any]]] = []
        self._label_carrier_items: list[tuple[QTreeWidgetItem, dict[str, Any]]] = []
        self._label_target_widgets: dict[int, QComboBox] = {}
        self._label_choice_widgets: dict[tuple[int, int], QComboBox] = {}
        self._eeg_file_remap_widgets: dict[str, QComboBox] = {}
        self._label_carrier_remap_widgets: dict[str, QComboBox] = {}
        self._event_role_widgets: dict[int, QComboBox] = {}
        self._event_role_items: list[tuple[QTreeWidgetItem, str, str]] = []
        self._class_map_items: list[tuple[QTreeWidgetItem, str, str]] = []
        self._tree_column_specs: dict[int, tuple[int, ...]] = {}
        super().__init__(
            parent=parent,
            title="Interpret Data Source",
            width=1040,
            height=760,
        )

    @property
    def decision(self) -> str:
        """Return the validation decision string."""
        return str(self.validation_decision.get("decision", "unknown"))

    def init_ui(self) -> None:
        self._apply_product_tree_style()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        self.workflow_steps_label = QLabel(
            "Select source | Scan result | Preview | Confirm | Apply | Save recipe"
        )
        self.workflow_steps_label.setObjectName("InterpretationWorkflowSteps")
        self.workflow_steps_label.setWordWrap(True)
        layout.addWidget(self.workflow_steps_label)

        source_path = str(self.scan_result.get("source_path", ""))
        self.summary_label = QLabel(
            str(self.preview.get("summary") or "Review the interpreted EEG source.")
        )
        self.summary_label.setObjectName("InterpretationSummary")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        source_group = QGroupBox("Source and Readiness")
        source_layout = QGridLayout(source_group)
        source_layout.setColumnStretch(1, 1)
        source_layout.addWidget(QLabel("Source"), 0, 0)
        source_layout.addWidget(
            self._wrapped_label(source_path or "Unknown source"), 0, 1
        )
        source_layout.addWidget(QLabel("Type"), 1, 0)
        source_layout.addWidget(
            self._wrapped_label(str(self.scan_result.get("source_kind", "unknown"))),
            1,
            1,
        )
        source_layout.addWidget(QLabel("Files"), 2, 0)
        source_layout.addWidget(
            self._wrapped_label(str(self._file_count())),
            2,
            1,
        )
        source_layout.addWidget(QLabel("Label carriers"), 3, 0)
        source_layout.addWidget(
            self._wrapped_label(str(self._label_carrier_count())),
            3,
            1,
        )
        source_layout.addWidget(QLabel("BIDS"), 4, 0)
        source_layout.addWidget(self._wrapped_label(self._bids_status()), 4, 1)
        layout.addWidget(source_group)

        decision_text = self._decision_text()
        self.decision_label = QLabel(decision_text)
        self.decision_label.setObjectName("InterpretationDecision")
        self.decision_label.setWordWrap(True)
        layout.addWidget(self.decision_label)

        metadata_group = QGroupBox("Metadata Preview")
        metadata_layout = QVBoxLayout(metadata_group)
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels(
            ["File", "Subject", "Session", "Task", "Run"],
        )
        self.file_tree.setMinimumHeight(160)
        self.file_tree.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed,
        )
        self._populate_files()
        self._fit_tree_columns(
            self.file_tree,
            (260, 110, 120, 150, 70),
            stretch_column=0,
        )
        metadata_layout.addWidget(self.file_tree)
        layout.addWidget(metadata_group)

        label_group = QGroupBox("Label and Event Interpretation")
        label_layout = QVBoxLayout(label_group)
        self.label_carrier_tree = QTreeWidget()
        self.label_carrier_tree.setHeaderLabels(
            [
                "Carrier",
                "Matched EEG",
                "Format",
                "Label field",
                "Anchor",
                "Time",
                "Granularity",
                "Role",
            ],
        )
        self.label_carrier_tree.setMinimumHeight(110)
        self.label_carrier_tree.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed,
        )
        self._populate_label_carrier_tree()
        self._fit_tree_columns(
            self.label_carrier_tree,
            (145, 145, 110, 115, 105, 100, 105, 157),
            stretch_column=7,
        )
        label_layout.addWidget(self.label_carrier_tree)

        self.event_tree = QTreeWidget()
        self.event_tree.setHeaderLabels(["Item", "Role", "Meaning"])
        self.event_tree.setMinimumHeight(160)
        self.event_tree.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed,
        )
        self._populate_event_tree()
        self._fit_tree_columns(self.event_tree, (220, 150, 420), stretch_column=2)
        label_layout.addWidget(self.event_tree)
        layout.addWidget(label_group, stretch=1)

        review_group = QGroupBox("Review Summary")
        review_layout = QVBoxLayout(review_group)
        self.review_tree = QTreeWidget()
        self.review_tree.setObjectName("InterpretationReviewSummary")
        self.review_tree.setHeaderLabels(["Item", "Status", "What it means"])
        self.review_tree.setRootIsDecorated(False)
        self.review_tree.setAlternatingRowColors(True)
        self.review_tree.setUniformRowHeights(True)
        self.review_tree.setMinimumHeight(120)
        self.review_tree.setMaximumHeight(220)
        self._fit_tree_columns(self.review_tree, (150, 145, 520), stretch_column=2)
        self._populate_review_tree()
        review_layout.addWidget(self.review_tree)
        layout.addWidget(review_group)

        self.confirmation_label = QLabel(self._confirmation_text())
        self.confirmation_label.setObjectName("InterpretationConfirmation")
        self.confirmation_label.setWordWrap(True)
        layout.addWidget(self.confirmation_label)

        self.save_recipe_check = QCheckBox("Save reusable import recipe after applying")
        apply_allowed = self._apply_allowed()
        self.save_recipe_check.setChecked(apply_allowed)
        self.save_recipe_check.setEnabled(apply_allowed)
        self.save_recipe_check.setToolTip(
            "Recipe records source, metadata decisions, label carriers, and "
            "confirmations for review or replay."
        )
        layout.addWidget(self.save_recipe_check)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText(
                "Apply Remap"
                if self.decision == "blocked" and self._has_remap_options()
                else "Confirm and Apply"
                if self.decision == "needs_confirmation"
                else "Apply Interpretation"
            )
            ok_button.setEnabled(apply_allowed)
        self.button_box.rejected.connect(self.reject)
        self.button_box.accepted.connect(self.accept)
        layout.addWidget(self.button_box)
        self._fit_all_tree_columns_to_viewport()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "review_tree"):
            self._fit_all_tree_columns_to_viewport()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, self._fit_all_tree_columns_to_viewport)

    def get_result(self) -> dict[str, Any]:
        return {
            "confirmed": self.decision == "needs_confirmation"
            or (self.decision == "blocked" and self._has_complete_remap_choices()),
            "save_recipe": self.save_recipe_check.isChecked(),
            "choices": self._edited_choices(),
        }

    @staticmethod
    def _wrapped_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _apply_product_tree_style(self) -> None:
        self.setStyleSheet(
            f"""
            QTreeWidget {{
                background-color: #202020;
                alternate-background-color: #242424;
                color: {Theme.TEXT_MUTED};
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                selection-background-color: {Theme.BLUE_PRESSED};
                selection-color: {Theme.TEXT_MUTED};
            }}
            QTreeWidget#InterpretationReviewSummary {{
                background-color: #212121;
                alternate-background-color: #232323;
            }}
            QTreeWidget::item {{
                padding: 4px 6px;
                border-bottom: 1px solid #2a2a2a;
            }}
            QHeaderView::section {{
                background-color: {Theme.BACKGROUND_MID};
                color: {Theme.TEXT_SECONDARY};
                padding: 5px 6px;
                border: 0;
                border-right: 1px solid {Theme.BACKGROUND_LIGHT};
                border-bottom: 1px solid {Theme.BACKGROUND_LIGHT};
            }}
            QComboBox {{
                background-color: {Theme.BACKGROUND_MID};
                color: {Theme.TEXT_MUTED};
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                padding: 2px 6px;
                min-width: 0px;
            }}
            """
        )

    def _fit_tree_columns(
        self,
        tree: QTreeWidget,
        widths: tuple[int, ...],
        *,
        stretch_column: int,  # retained for call-site readability
    ) -> None:
        _ = stretch_column
        tree.setTextElideMode(Qt.TextElideMode.ElideRight)
        tree.setWordWrap(False)
        tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._apply_tree_palette(tree)
        self._tree_column_specs[id(tree)] = widths
        header = tree.header()
        if header is None:
            return
        header.setMinimumSectionSize(56)
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        header.setStretchLastSection(False)
        for column in range(len(widths)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        self._fit_tree_columns_to_viewport(tree)

    def _fit_all_tree_columns_to_viewport(self) -> None:
        for tree_name in (
            "file_tree",
            "label_carrier_tree",
            "event_tree",
            "review_tree",
        ):
            tree = getattr(self, tree_name, None)
            if isinstance(tree, QTreeWidget):
                self._fit_tree_columns_to_viewport(tree)

    def _fit_tree_columns_to_viewport(self, tree: QTreeWidget) -> None:
        widths = self._tree_column_specs.get(id(tree))
        if not widths:
            return
        viewport = tree.viewport()
        if viewport is None:
            return
        header = tree.header()
        min_width = header.minimumSectionSize() if header is not None else 56
        scaled = scaled_column_widths(
            widths,
            viewport.width(),
            min_width=min_width,
        )
        for column, width in enumerate(scaled):
            tree.setColumnWidth(column, width)

    @staticmethod
    def _apply_tree_palette(tree: QTreeWidget) -> None:
        palette = tree.palette()
        if tree.objectName() == "InterpretationReviewSummary":
            base = QColor("#212121")
            alternate = QColor("#232323")
        else:
            base = QColor("#202020")
            alternate = QColor("#242424")
        palette.setColor(QPalette.ColorRole.Base, base)
        palette.setColor(QPalette.ColorRole.AlternateBase, alternate)
        palette.setColor(QPalette.ColorRole.Text, QColor(Theme.TEXT_MUTED))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(Theme.BLUE_PRESSED))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(Theme.TEXT_MUTED))
        tree.setPalette(palette)

    def _file_count(self) -> int:
        files = self.scan_result.get("eeg_files", []) or []
        if isinstance(files, list):
            return len(files)
        return int(self.preview.get("file_count", 0) or 0)

    def _label_carrier_count(self) -> int:
        carriers = self.scan_result.get("label_carriers", []) or []
        if isinstance(carriers, list):
            return len(carriers)
        return int(self.preview.get("label_carrier_count", 0) or 0)

    def _bids_status(self) -> str:
        bids = self.scan_result.get("bids") or {}
        if not isinstance(bids, dict) or not bids.get("is_bids"):
            return "Not detected"
        subjects = ", ".join(str(item) for item in bids.get("subjects", []) or [])
        events = bids.get("events_files", []) or []
        event_count = len(events) if isinstance(events, list) else 0
        subject_text = subjects or "subjects pending"
        return f"BIDS-like source, {subject_text}, {event_count} events.tsv file(s)"

    def _decision_text(self) -> str:
        if self.decision == "blocked":
            has_eeg_remap = self._has_eeg_file_remap_options()
            has_label_remap = self._has_label_carrier_remap_options()
            if has_eeg_remap and has_label_remap:
                return "Choose replacement recipe files before applying."
            if has_eeg_remap:
                return "Choose the replacement EEG file before applying."
            if has_label_remap:
                return "Choose the replacement label/event carrier before applying."
            return "This source cannot be applied yet. Review the blocked items below."
        if self.decision == "needs_confirmation":
            return "Review and confirm these choices before applying."
        if self.decision == "safe":
            return "Ready to apply."
        return "Review status is unavailable."

    def _populate_files(self) -> None:
        metadata_preview = self.preview.get("metadata_preview") or []
        if isinstance(metadata_preview, list) and metadata_preview:
            for item in metadata_preview:
                if isinstance(item, dict):
                    tree_item = QTreeWidgetItem(
                        [
                            str(item.get("file", "")),
                            self._field_value(item.get("subject")),
                            self._field_value(item.get("session")),
                            self._field_value(item.get("task")),
                            self._field_value(item.get("run")),
                        ],
                    )
                    tree_item.setFlags(tree_item.flags() | Qt.ItemFlag.ItemIsEditable)
                    for column in range(1, 5):
                        tree_item.setToolTip(
                            column,
                            self._field_tooltip(item, column),
                        )
                    self._metadata_items.append((tree_item, dict(item)))
                    self.file_tree.addTopLevelItem(tree_item)
            return

        for file_path in self.scan_result.get("eeg_files", []) or []:
            tree_item = QTreeWidgetItem([Path(str(file_path)).name, "", "", "", ""])
            tree_item.setFlags(tree_item.flags() | Qt.ItemFlag.ItemIsEditable)
            self._metadata_items.append(
                (
                    tree_item,
                    {
                        "file": Path(str(file_path)).name,
                        "subject": {},
                        "session": {},
                        "task": {},
                        "run": {},
                    },
                )
            )
            self.file_tree.addTopLevelItem(tree_item)

    def _populate_event_tree(self) -> None:
        carriers = self.scan_result.get("label_carriers", []) or []
        if isinstance(carriers, list):
            for carrier in carriers:
                self.event_tree.addTopLevelItem(
                    QTreeWidgetItem(
                        [
                            Path(str(carrier)).name,
                            "label / event carrier",
                            "Review alignment, anchor, and class map before apply.",
                        ],
                    ),
                )

        event_roles = self.preview.get("event_roles") or {}
        if isinstance(event_roles, dict):
            for name, role in event_roles.items():
                tree_item = QTreeWidgetItem(
                    [self._event_role_display_name(str(name)), "event role", str(role)]
                )
                tree_item.setToolTip(0, f"Source event field: {name}")
                self._event_role_items.append((tree_item, str(name), str(role)))
                self.event_tree.addTopLevelItem(tree_item)
                self._install_event_role_selector(tree_item, str(role))

        class_map = self.preview.get("class_map") or {}
        if isinstance(class_map, dict):
            for code, label in class_map.items():
                tree_item = QTreeWidgetItem([str(code), "class map", str(label)])
                tree_item.setFlags(tree_item.flags() | Qt.ItemFlag.ItemIsEditable)
                self._class_map_items.append((tree_item, str(code), str(label)))
                self.event_tree.addTopLevelItem(tree_item)

        if self.event_tree.topLevelItemCount() == 0:
            self.event_tree.addTopLevelItem(
                QTreeWidgetItem(
                    [
                        "No label/event carrier detected",
                        "recording only",
                        "Supervised labels require events or a later label import.",
                    ],
                ),
            )

    def _populate_label_carrier_tree(self) -> None:
        carriers = self.preview.get("label_carrier_preview") or []
        if not isinstance(carriers, list) or not carriers:
            carriers = [
                {
                    "path": str(carrier),
                    "name": Path(str(carrier)).name,
                    "format": Path(str(carrier)).suffix.lstrip(".").upper()
                    or "Unknown",
                    "label_candidates": [],
                    "anchor_candidates": [],
                    "selected_label_field": "",
                    "selected_anchor": "",
                    "time_model": "",
                    "granularity": "",
                    "reason": "Review this label carrier before applying.",
                }
                for carrier in self.scan_result.get("label_carriers", []) or []
            ]

        for carrier in carriers:
            if not isinstance(carrier, dict):
                continue
            match_text = self._label_carrier_match_text(carrier)
            original = dict(carrier)
            original["_matched_eeg_text"] = match_text
            item = QTreeWidgetItem(
                [
                    str(carrier.get("name") or Path(str(carrier.get("path", ""))).name),
                    match_text,
                    str(carrier.get("format") or "Unknown"),
                    str(carrier.get("selected_label_field") or ""),
                    str(carrier.get("selected_anchor") or ""),
                    str(carrier.get("time_model") or ""),
                    str(carrier.get("granularity") or ""),
                    str(carrier.get("role") or "external labels"),
                ],
            )
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            item.setToolTip(1, "The EEG file this label carrier can be matched to.")
            item.setToolTip(3, self._candidate_tooltip(carrier, "label_candidates"))
            item.setToolTip(4, self._candidate_tooltip(carrier, "anchor_candidates"))
            item.setToolTip(5, "How label timing aligns to the EEG recording.")
            item.setToolTip(6, "The data unit each label describes.")
            item.setToolTip(7, "How this label carrier should be used in the recipe.")
            self._label_carrier_items.append((item, original))
            self.label_carrier_tree.addTopLevelItem(item)
            self._install_label_carrier_selectors(item, carrier)
            if match_text == "Needs review" and self._file_count() > 1:
                target_selector = self._label_target_selector()
                self._label_target_widgets[id(item)] = target_selector
                self.label_carrier_tree.setItemWidget(item, 1, target_selector)
        if self.label_carrier_tree.topLevelItemCount() == 0:
            self.label_carrier_tree.addTopLevelItem(
                QTreeWidgetItem(
                    [
                        "No external label file",
                        "Recording",
                        "",
                        "Use internal events",
                        "",
                        "",
                        "",
                        "",
                    ],
                ),
            )

    @staticmethod
    def _field_text(value: Any) -> str:
        if not isinstance(value, dict):
            return ""
        resolved = value.get("value")
        decision = value.get("decision")
        if resolved in (None, ""):
            return str(decision or "missing")
        return f"{resolved} ({decision})" if decision else str(resolved)

    @staticmethod
    def _field_value(value: Any) -> str:
        if not isinstance(value, dict):
            return ""
        resolved = value.get("override") or value.get("value")
        if resolved in (None, ""):
            return ""
        return str(resolved)

    @staticmethod
    def _field_tooltip(item: dict[str, Any], column: int) -> str:
        field = ("subject", "session", "task", "run")[column - 1]
        value = item.get(field)
        if not isinstance(value, dict):
            return ""
        source = str(value.get("source") or "unknown")
        decision = str(value.get("decision") or "unknown")
        reason = str(value.get("reason") or "")
        return " | ".join(part for part in [source, decision, reason] if part)

    def _edited_choices(self) -> dict[str, Any]:
        choices: dict[str, Any] = {}
        metadata_overrides = self._metadata_overrides()
        if metadata_overrides:
            choices["metadata_overrides"] = metadata_overrides
        class_map = self._class_map_overrides()
        if class_map:
            choices["class_map"] = class_map
        event_roles = self._event_role_overrides()
        if event_roles:
            choices["event_roles"] = event_roles
        eeg_file_remap = self._eeg_file_remap_choices()
        if eeg_file_remap:
            choices["eeg_file_remap"] = eeg_file_remap
        label_carriers = self._label_carrier_choices()
        if label_carriers:
            choices["label_carrier_choices"] = label_carriers
        label_carrier_remap = self._label_carrier_remap_choices()
        if label_carrier_remap:
            choices["label_carrier_remap"] = label_carrier_remap
        return choices

    def _remap_choices(self) -> dict[str, dict[str, str]]:
        choices: dict[str, dict[str, str]] = {}
        eeg_file_remap = self._eeg_file_remap_choices()
        if eeg_file_remap:
            choices["eeg_file_remap"] = eeg_file_remap
        label_carrier_remap = self._label_carrier_remap_choices()
        if label_carrier_remap:
            choices["label_carrier_remap"] = label_carrier_remap
        return choices

    def _metadata_overrides(self) -> dict[str, dict[str, str]]:
        overrides: dict[str, dict[str, str]] = {}
        fields = ("subject", "session", "task", "run")
        for tree_item, original in self._metadata_items:
            file_key = str(original.get("file") or tree_item.text(0)).strip()
            if not file_key:
                continue
            changed: dict[str, str] = {}
            for column, field in enumerate(fields, start=1):
                current = tree_item.text(column).strip()
                original_value = self._field_value(original.get(field))
                if current and current != original_value:
                    changed[field] = current
            if changed:
                overrides[file_key] = changed
        return overrides

    def _class_map_overrides(self) -> dict[str, str]:
        if not self._class_map_items:
            return {}
        current = {
            code: tree_item.text(2).strip()
            for tree_item, code, _original in self._class_map_items
            if tree_item.text(2).strip()
        }
        changed = any(
            current.get(code, "") != original
            for _tree_item, code, original in self._class_map_items
        )
        return current if changed else {}

    def _event_role_overrides(self) -> dict[str, str]:
        if not self._event_role_items:
            return {}
        current = {
            name: self._event_role_item_text(tree_item).strip()
            for tree_item, name, _original in self._event_role_items
            if self._event_role_item_text(tree_item).strip()
        }
        changed = any(
            current.get(name, "") != original
            for _tree_item, name, original in self._event_role_items
        )
        return current if changed else {}

    def _install_event_role_selector(
        self,
        item: QTreeWidgetItem,
        current_value: str,
    ) -> None:
        selector = QComboBox(self.event_tree)
        self._prepare_table_combo(selector)
        selector.setToolTip("Choose how this event should be used in the recipe.")
        choices = [
            ("Class cue", "class cue"),
            ("Class label candidate", "class label candidate"),
            ("Time anchor", "time anchor"),
            ("Trial start", "trial start"),
            ("Response", "response"),
            ("Artifact", "artifact"),
            ("Boundary", "boundary"),
            ("Run marker", "run marker"),
            ("Ignored", "ignored"),
        ]
        seen_values: set[str] = set()
        for display, value in choices:
            selector.addItem(display, value)
            seen_values.add(value)
        if current_value and current_value not in seen_values:
            selector.addItem(self._label_choice_display(current_value), current_value)
        current_index = selector.findData(current_value)
        if current_index >= 0:
            selector.setCurrentIndex(current_index)
        self._event_role_widgets[id(item)] = selector
        self.event_tree.setItemWidget(item, 2, selector)

    def _event_role_item_text(self, item: QTreeWidgetItem) -> str:
        selector = self._event_role_widgets.get(id(item))
        if selector is not None:
            value = selector.currentData()
            return str(value) if value is not None else selector.currentText()
        return item.text(2)

    def _label_carrier_choices(self) -> dict[str, dict[str, str]]:
        choices: dict[str, dict[str, str]] = {}
        fields = (
            ("target_file", "_matched_eeg_text", 1),
            ("label_field", "selected_label_field", 3),
            ("anchor", "selected_anchor", 4),
            ("time_model", "time_model", 5),
            ("granularity", "granularity", 6),
            ("role", "role", 7),
        )
        for item, original in self._label_carrier_items:
            carrier_key = str(
                original.get("path") or original.get("name") or ""
            ).strip()
            if not carrier_key:
                continue
            changed: dict[str, str] = {}
            for choice_key, original_key, column in fields:
                current = self._label_carrier_choice_text(
                    choice_key,
                    self._label_carrier_item_text(item, column),
                )
                original_value = str(original.get(original_key) or "").strip()
                if current and current != original_value:
                    changed[choice_key] = current
            if changed:
                for choice_key, _original_key, column in fields:
                    if choice_key == "target_file":
                        continue
                    current = self._label_carrier_choice_text(
                        choice_key,
                        self._label_carrier_item_text(item, column),
                    )
                    if current and choice_key not in changed:
                        changed[choice_key] = current
                choices[carrier_key] = changed
        return choices

    def _eeg_file_remap_choices(self) -> dict[str, str]:
        choices: dict[str, str] = {}
        for saved, selector in self._eeg_file_remap_widgets.items():
            value = selector.currentData()
            replacement = str(value) if value is not None else ""
            if replacement:
                choices[saved] = replacement
        return choices

    def _label_carrier_remap_choices(self) -> dict[str, str]:
        choices: dict[str, str] = {}
        for saved, selector in self._label_carrier_remap_widgets.items():
            value = selector.currentData()
            replacement = str(value) if value is not None else ""
            if replacement:
                choices[saved] = replacement
        return choices

    def _has_remap_options(self) -> bool:
        return self._has_eeg_file_remap_options() or (
            self._has_label_carrier_remap_options()
        )

    def _apply_allowed(self) -> bool:
        return self.decision != "blocked" or self._has_complete_remap_choices()

    def _has_complete_remap_choices(self) -> bool:
        option_count = len(self._eeg_file_remap_options()) + len(
            self._label_carrier_remap_options()
        )
        if option_count == 0:
            return False
        choice_count = len(self._eeg_file_remap_choices()) + len(
            self._label_carrier_remap_choices()
        )
        return choice_count == option_count

    def _sync_apply_state(self, *_args: Any) -> None:
        if not hasattr(self, "button_box"):
            return
        apply_allowed = self._apply_allowed()
        ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setEnabled(apply_allowed)
        if hasattr(self, "save_recipe_check"):
            was_checked = self.save_recipe_check.isChecked()
            self.save_recipe_check.setEnabled(apply_allowed)
            if not apply_allowed:
                self.save_recipe_check.setChecked(False)
            elif self.decision == "blocked" and not was_checked:
                self.save_recipe_check.setChecked(True)

    def _has_eeg_file_remap_options(self) -> bool:
        return bool(self._eeg_file_remap_options())

    def _has_label_carrier_remap_options(self) -> bool:
        return bool(self._label_carrier_remap_options())

    def _eeg_file_remap_options(self) -> list[dict[str, Any]]:
        summary = self.preview.get("recipe_reload_summary")
        if not isinstance(summary, dict):
            return []
        options = summary.get("eeg_file_remap_options") or []
        return [dict(item) for item in options if isinstance(item, dict)]

    def _label_carrier_remap_options(self) -> list[dict[str, Any]]:
        summary = self.preview.get("recipe_reload_summary")
        if not isinstance(summary, dict):
            return []
        options = summary.get("label_carrier_remap_options") or []
        return [dict(item) for item in options if isinstance(item, dict)]

    def _install_label_carrier_selectors(
        self,
        item: QTreeWidgetItem,
        carrier: dict[str, Any],
    ) -> None:
        self._set_label_choice_selector(
            item,
            3,
            self._text_choices(carrier.get("label_candidates")),
            str(carrier.get("selected_label_field") or ""),
            "Choose the label or class column for this carrier.",
        )
        self._set_label_choice_selector(
            item,
            4,
            self._text_choices(carrier.get("anchor_candidates")),
            str(carrier.get("selected_anchor") or ""),
            "Choose the time anchor that aligns labels to the EEG.",
        )
        self._set_label_choice_selector(
            item,
            5,
            [
                ("Trial order", "trial_order"),
                ("Seconds", "seconds"),
                ("Relative time", "relative_time"),
                ("Sample index", "sample_index"),
                ("Absolute timestamp", "absolute_timestamp"),
            ],
            str(carrier.get("time_model") or ""),
            "Choose how label timing aligns to the EEG recording.",
        )
        self._set_label_choice_selector(
            item,
            6,
            [
                ("Trial", "trial"),
                ("Event", "event"),
                ("Epoch", "epoch"),
                ("Segment", "segment"),
                ("Session", "session"),
                ("Subject", "subject"),
                ("Sample", "sample"),
            ],
            str(carrier.get("granularity") or ""),
            "Choose the data unit each label describes.",
        )
        self._set_label_choice_selector(
            item,
            7,
            [
                ("External labels", "external labels"),
                ("Class cue labels", "class cue labels"),
                ("Trial anchors", "trial anchors"),
                ("Response labels", "response labels"),
                ("Artifact markers", "artifact markers"),
                ("Ignored markers", "ignored markers"),
            ],
            str(carrier.get("role") or "external labels"),
            "Choose how this carrier should be used in the recipe.",
        )

    def _set_label_choice_selector(
        self,
        item: QTreeWidgetItem,
        column: int,
        choices: list[tuple[str, str]],
        current_value: str,
        tooltip: str,
    ) -> None:
        if not choices and not current_value:
            return
        selector = QComboBox(self.label_carrier_tree)
        self._prepare_table_combo(selector)
        selector.setToolTip(tooltip)
        if not current_value:
            selector.addItem("Needs review", "")
        seen_values: set[str] = {""} if not current_value else set()
        for display, value in choices:
            if value in seen_values:
                continue
            selector.addItem(display, value)
            seen_values.add(value)
        if current_value and current_value not in seen_values:
            selector.addItem(self._label_choice_display(current_value), current_value)
        current_index = selector.findData(current_value)
        if current_index >= 0:
            selector.setCurrentIndex(current_index)
        self._label_choice_widgets[(id(item), column)] = selector
        self.label_carrier_tree.setItemWidget(item, column, selector)

    @staticmethod
    def _text_choices(values: Any) -> list[tuple[str, str]]:
        if not isinstance(values, list):
            return []
        choices: list[tuple[str, str]] = []
        for value in values:
            text = str(value).strip()
            if text:
                choices.append(
                    (DataInterpretationPreviewDialog._label_choice_display(text), text)
                )
        return choices

    @staticmethod
    def _label_choice_display(value: str) -> str:
        cleaned = value.replace("_", " ").strip()
        return cleaned[:1].upper() + cleaned[1:] if cleaned else value

    @staticmethod
    def _event_role_display_name(value: str) -> str:
        if value == "label_carrier":
            return "Label carrier"
        return DataInterpretationPreviewDialog._label_choice_display(value)

    def _label_target_selector(self) -> QComboBox:
        selector = QComboBox(self.label_carrier_tree)
        self._prepare_table_combo(selector)
        selector.addItem("Needs review")
        for file_path in self.scan_result.get("eeg_files", []) or []:
            text = Path(str(file_path)).name
            if text:
                selector.addItem(text)
        selector.setToolTip("Choose the EEG file this label carrier applies to.")
        return selector

    def _label_carrier_item_text(self, item: QTreeWidgetItem, column: int) -> str:
        if column == 1:
            selector = self._label_target_widgets.get(id(item))
            if selector is not None:
                return selector.currentText()
        choice_selector = self._label_choice_widgets.get((id(item), column))
        if choice_selector is not None:
            value = choice_selector.currentData()
            return str(value) if value is not None else choice_selector.currentText()
        return item.text(column)

    @staticmethod
    def _label_carrier_choice_text(choice_key: str, value: str) -> str:
        text = value.strip()
        if choice_key != "target_file":
            return text
        if text in {"", "Needs review", "Recording"}:
            return ""
        return text

    def _label_carrier_match_text(self, carrier: dict[str, Any]) -> str:
        eeg_files = [
            str(item)
            for item in (self.scan_result.get("eeg_files") or [])
            if str(item).strip()
        ]
        carrier_path = str(carrier.get("path") or carrier.get("name") or "").strip()
        if not eeg_files:
            return "Needs review"
        if len(eeg_files) == 1:
            return Path(eeg_files[0]).name

        carrier_key = self._label_mapping_key(carrier_path)
        matches = [
            Path(eeg_file).name
            for eeg_file in eeg_files
            if self._label_mapping_key(eeg_file) == carrier_key
        ]
        if len(matches) == 1:
            return matches[0]
        return "Needs review"

    @staticmethod
    def _label_mapping_key(path: str) -> str:
        name = Path(path).name
        lowered = name.lower()
        if lowered.endswith(".fif.gz"):
            stem = name[: -len(".fif.gz")]
        else:
            stem = Path(name).stem
        normalized = stem.lower()
        for suffix in (
            "_events",
            "-events",
            "_labels",
            "-labels",
            "_label",
            "-label",
            "_raw",
            "-raw",
            "_eeg",
            "-eeg",
        ):
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
                break
        return normalized.strip()

    @staticmethod
    def _candidate_tooltip(carrier: dict[str, Any], key: str) -> str:
        values = carrier.get(key) or []
        if isinstance(values, list) and values:
            return "Candidates: " + ", ".join(str(value) for value in values)
        reason = str(carrier.get("reason") or "")
        return reason or "No automatic candidates were found."

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
                    "Remap EEG file",
                    "Select",
                    saved_name,
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
            self.review_tree.setItemWidget(tree_item, 2, selector)
            remap_added = True
        for remap in self._label_carrier_remap_options():
            saved = str(remap.get("saved") or "").strip()
            if not saved:
                continue
            saved_name = str(remap.get("saved_name") or Path(saved).name or saved)
            tree_item = QTreeWidgetItem(
                [
                    "Remap label carrier",
                    "Select",
                    saved_name,
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
            self.review_tree.setItemWidget(tree_item, 2, selector)
            remap_added = True
        for item, status, detail in rows:
            tree_item = QTreeWidgetItem([item, status, detail])
            for column in range(3):
                tree_item.setToolTip(column, detail or status)
            self.review_tree.addTopLevelItem(tree_item)
        if not rows and not remap_added:
            self.review_tree.addTopLevelItem(
                QTreeWidgetItem(
                    [
                        "Review",
                        "Ready",
                        "No warnings or confirmations.",
                    ],
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

    def _review_rows(self) -> list[tuple[str, str, str]]:
        rows: list[tuple[str, str, str]] = []
        warnings = self._unique_strings(self.preview.get("warnings"))
        confirmations = self._unique_strings(
            [
                *(self.preview.get("confirmation_items") or []),
                *(self.validation_decision.get("required_confirmations") or []),
            ]
        )
        blocked = self._unique_strings(
            self.validation_decision.get("blocked_reasons")
            or self.preview.get("blocked_reasons")
        )
        recipe_reload_summary = self.preview.get("recipe_reload_summary")
        if isinstance(recipe_reload_summary, dict) and recipe_reload_summary:
            rows.append(
                (
                    "Reloaded recipe",
                    "Reapplied",
                    str(
                        recipe_reload_summary.get("message")
                        or "Saved recipe choices were reapplied before validation."
                    ),
                )
            )
            for diff_row in recipe_reload_summary.get("diff_rows", []) or []:
                if not isinstance(diff_row, dict):
                    continue
                item = str(diff_row.get("item") or "Recipe reload")
                status = str(diff_row.get("status") or "Review")
                detail = str(diff_row.get("detail") or "").strip()
                if detail:
                    rows.append((item, status, detail))
        for label, status, values in (
            ("Warning", "Review", warnings),
            ("Confirmation", "Needs confirmation", confirmations),
            ("Blocked reason", "Blocked", blocked),
        ):
            rows.extend((label, status, item) for item in values)
        impacts = self.preview.get(
            "downstream_impacts"
        ) or self.validation_decision.get("downstream_impacts")
        if impacts:
            rows.extend(
                ("Downstream impact", "After apply", str(item)) for item in impacts
            )
        trace = self.preview.get("recipe_trace") or self.scan_result.get("recipe_trace")
        if trace:
            rows.extend(("Recipe trace", "Saved", str(item)) for item in trace)
        format_capabilities = self.preview.get(
            "format_capabilities",
        ) or self.scan_result.get("format_capabilities")
        rows.extend(self._format_capability_rows(format_capabilities))
        return rows

    @staticmethod
    def _unique_strings(values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        result: list[str] = []
        for value in values:
            text = str(value)
            if text and text not in result:
                result.append(text)
        return result

    @staticmethod
    def _format_capability_rows(values: Any) -> list[tuple[str, str, str]]:
        if not isinstance(values, list):
            return []
        rows: list[tuple[str, str, str]] = []
        for value in values:
            if not isinstance(value, dict):
                continue
            format_name = str(value.get("format") or value.get("name") or "Source")
            status = str(value.get("status") or "review").replace("_", " ")
            message = str(value.get("message") or "").strip()
            detail = f"{format_name}: {status}."
            if message:
                detail = f"{detail} {message}"
            rows.append(("Format capability", status[:1].upper() + status[1:], detail))
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
            return "Review the items marked Needs confirmation, then confirm and apply."
        if self.decision == "safe":
            return "This interpretation can be applied."
        return "Review this interpretation before applying."

    @staticmethod
    def _prepare_table_combo(selector: QComboBox) -> None:
        selector.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        selector.setMinimumContentsLength(1)
        selector.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
