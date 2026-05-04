"""Preview dialog for Data Interpretation import decisions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from XBrainLab.ui.core.base_dialog import BaseDialog


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
        self.event_tree: QTreeWidget
        self.review_text: QPlainTextEdit
        self.button_box: QDialogButtonBox
        self._metadata_items: list[tuple[QTreeWidgetItem, dict[str, Any]]] = []
        self._class_map_items: list[tuple[QTreeWidgetItem, str, str]] = []
        super().__init__(
            parent=parent,
            title="Interpret Data Source",
            width=880,
            height=640,
        )

    @property
    def decision(self) -> str:
        """Return the validation decision string."""
        return str(self.validation_decision.get("decision", "unknown"))

    def init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        self.workflow_steps_label = QLabel(
            "Scan -> Preview -> Validate -> Confirm -> Apply -> Save recipe"
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

        content_row = QHBoxLayout()
        content_row.setSpacing(12)

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
        metadata_layout.addWidget(self.file_tree)
        content_row.addWidget(metadata_group, stretch=3)

        label_group = QGroupBox("Labels, Events, and Recipe Trace")
        label_layout = QVBoxLayout(label_group)
        self.event_tree = QTreeWidget()
        self.event_tree.setHeaderLabels(["Item", "Role", "Meaning"])
        self.event_tree.setMinimumHeight(160)
        self.event_tree.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed,
        )
        self._populate_event_tree()
        label_layout.addWidget(self.event_tree)
        content_row.addWidget(label_group, stretch=2)
        layout.addLayout(content_row, stretch=1)

        self.review_text = QPlainTextEdit()
        self.review_text.setReadOnly(True)
        self.review_text.setPlainText(self._details_text())
        self.review_text.setMaximumHeight(120)
        layout.addWidget(self.review_text)

        self.confirmation_label = QLabel(self._confirmation_text())
        self.confirmation_label.setObjectName("InterpretationConfirmation")
        self.confirmation_label.setWordWrap(True)
        layout.addWidget(self.confirmation_label)

        self.save_recipe_check = QCheckBox("Save reusable import recipe after applying")
        self.save_recipe_check.setChecked(self.decision != "blocked")
        self.save_recipe_check.setEnabled(self.decision != "blocked")
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
                "Confirm and Apply"
                if self.decision == "needs_confirmation"
                else "Apply Interpretation"
            )
            ok_button.setEnabled(self.decision != "blocked")
        self.button_box.rejected.connect(self.reject)
        self.button_box.accepted.connect(self.accept)
        layout.addWidget(self.button_box)

    def get_result(self) -> dict[str, Any]:
        return {
            "confirmed": self.decision == "needs_confirmation",
            "save_recipe": self.save_recipe_check.isChecked(),
            "choices": self._edited_choices(),
        }

    @staticmethod
    def _wrapped_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

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
            return "Validation blocked: this source cannot be applied yet."
        if self.decision == "needs_confirmation":
            return "Validation needs confirmation before applying."
        if self.decision == "safe":
            return "Validation passed: ready to apply."
        return f"Validation status: {self.decision}"

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
                self.event_tree.addTopLevelItem(
                    QTreeWidgetItem([str(name), "event role", str(role)]),
                )

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

    def _details_text(self) -> str:
        lines: list[str] = []
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
        for label, values in (
            ("Warnings", warnings),
            ("Confirmations", confirmations),
            ("Blocked reasons", blocked),
        ):
            if values:
                lines.append(f"{label}:")
                lines.extend(f"- {item}" for item in values)
        impacts = self.preview.get(
            "downstream_impacts"
        ) or self.validation_decision.get("downstream_impacts")
        if impacts:
            lines.append("Downstream impact:")
            lines.extend(f"- {item}" for item in impacts)
        trace = self.preview.get("recipe_trace") or self.scan_result.get("recipe_trace")
        if trace:
            lines.append("Recipe trace:")
            lines.extend(f"- {item}" for item in trace)
        return "\n".join(lines) if lines else "No warnings or confirmations."

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

    def _confirmation_text(self) -> str:
        if self.decision == "blocked":
            return "This interpretation is blocked and cannot be applied."
        if self.decision == "needs_confirmation":
            items = self.validation_decision.get("required_confirmations") or []
            if items:
                return "Confirmation required: " + "; ".join(str(i) for i in items)
            return "Confirmation required before applying this interpretation."
        if self.decision == "safe":
            return "This interpretation can be applied."
        return "Review this interpretation before applying."
