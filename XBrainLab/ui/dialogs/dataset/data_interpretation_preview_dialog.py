"""Preview dialog for Data Interpretation import decisions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtWidgets import (
    QDialogButtonBox,
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
        self.summary_label: QLabel
        self.decision_label: QLabel
        self.confirmation_label: QLabel
        self.file_tree: QTreeWidget
        super().__init__(
            parent=parent,
            title="Review Data Interpretation",
            width=760,
            height=520,
        )

    @property
    def decision(self) -> str:
        """Return the validation decision string."""
        return str(self.validation_decision.get("decision", "unknown"))

    def init_ui(self) -> None:
        layout = QVBoxLayout(self)

        source_path = str(self.scan_result.get("source_path", ""))
        self.summary_label = QLabel(
            str(self.preview.get("summary") or "Review the interpreted EEG source.")
        )
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        source_label = QLabel(f"Source: {source_path or 'Unknown source'}")
        source_label.setWordWrap(True)
        layout.addWidget(source_label)

        self.decision_label = QLabel(f"Validation: {self.decision}")
        self.decision_label.setWordWrap(True)
        layout.addWidget(self.decision_label)

        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels(
            ["File", "Subject", "Session", "Task", "Run"],
        )
        self._populate_files()
        layout.addWidget(self.file_tree, stretch=1)

        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlainText(self._details_text())
        details.setMaximumHeight(140)
        layout.addWidget(details)

        self.confirmation_label = QLabel(self._confirmation_text())
        self.confirmation_label.setWordWrap(True)
        layout.addWidget(self.confirmation_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText("Apply Interpretation")
            ok_button.setEnabled(self.decision != "blocked")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_result(self) -> dict[str, Any]:
        return {"confirmed": self.decision == "needs_confirmation"}

    def _populate_files(self) -> None:
        metadata_preview = self.preview.get("metadata_preview") or []
        if isinstance(metadata_preview, list) and metadata_preview:
            for item in metadata_preview:
                if isinstance(item, dict):
                    self.file_tree.addTopLevelItem(
                        QTreeWidgetItem(
                            [
                                str(item.get("file", "")),
                                self._field_text(item.get("subject")),
                                self._field_text(item.get("session")),
                                self._field_text(item.get("task")),
                                self._field_text(item.get("run")),
                            ],
                        ),
                    )
            return

        for file_path in self.scan_result.get("eeg_files", []) or []:
            self.file_tree.addTopLevelItem(
                QTreeWidgetItem([Path(str(file_path)).name, "", "", "", ""]),
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

    def _details_text(self) -> str:
        lines: list[str] = []
        for label, key in (
            ("Warnings", "warnings"),
            ("Confirmations", "confirmation_items"),
            ("Blocked reasons", "blocked_reasons"),
            ("Required confirmations", "required_confirmations"),
        ):
            values = self.preview.get(key)
            if key in {"blocked_reasons", "required_confirmations"}:
                values = self.validation_decision.get(key, values)
            if values:
                lines.append(f"{label}:")
                lines.extend(f"- {item}" for item in values)
        return "\n".join(lines) if lines else "No warnings or confirmations."

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
