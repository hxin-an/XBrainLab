"""Compact BIDS subject selection before full import discovery."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.dialogs.common import (
    configure_dark_table,
    normalize_dialog_button_box,
)


class BidsSubjectSelectionDialog(BaseDialog):
    """Select the BIDS subjects admitted to the expensive import scan."""

    _SCOPE_TEXT_LIMIT = 24
    _SCOPE_ITEM_LIMIT = 3

    def __init__(self, parent, *, catalog: dict[str, Any]) -> None:
        self.catalog = dict(catalog)
        self.subject_rows = [
            dict(row)
            for row in list(self.catalog.get("subjects") or [])
            if isinstance(row, dict)
        ]
        self.subject_table: QTableWidget
        self.selection_summary: QLabel
        self.continue_button = None
        super().__init__(parent, title="Choose BIDS Subjects", width=780, height=430)

    def init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        title = QLabel("Choose subjects to import")
        title.setObjectName("DialogSectionTitle")
        layout.addWidget(title)

        helper = QLabel(
            "Only the selected subjects will be scanned and loaded. "
            "Sessions, tasks, and runs are summarized for review."
        )
        helper.setObjectName("DialogMutedText")
        helper.setWordWrap(True)
        layout.addWidget(helper)

        self.subject_table = QTableWidget(len(self.subject_rows), 5, self)
        self.subject_table.setHorizontalHeaderLabels(
            ["Subject", "EEG files", "Sessions", "Tasks", "Runs"]
        )
        configure_dark_table(
            self.subject_table,
            object_name="BidsSubjectSelectionTable",
            no_selection=True,
        )
        self.subject_table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.subject_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.subject_table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        header = self.subject_table.horizontalHeader()
        if header is None:
            raise RuntimeError("BIDS subject table header is unavailable.")
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        for column in (2, 3, 4):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        self.subject_table.setColumnWidth(0, 140)
        self.subject_table.setColumnWidth(1, 90)

        self.subject_table.blockSignals(True)
        first_importable_row = next(
            (
                index
                for index, row in enumerate(self.subject_rows)
                if int(row.get("eeg_file_count") or 0) > 0
            ),
            -1,
        )
        for row_index, subject in enumerate(self.subject_rows):
            eeg_file_count = int(subject.get("eeg_file_count") or 0)
            subject_item = QTableWidgetItem(
                str(subject.get("label") or f"sub-{subject.get('subject', '')}")
            )
            subject_item.setData(
                Qt.ItemDataRole.UserRole,
                str(subject.get("subject") or ""),
            )
            subject_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
                if eeg_file_count > 0
                else Qt.ItemFlag.NoItemFlags
            )
            subject_item.setCheckState(
                Qt.CheckState.Checked
                if row_index == first_importable_row
                else Qt.CheckState.Unchecked
            )
            if eeg_file_count > 0:
                subject_item.setToolTip(subject_item.text())
            self.subject_table.setItem(row_index, 0, subject_item)
            display_values = (
                str(eeg_file_count),
                self._summary(subject.get("sessions")),
                self._summary(subject.get("tasks")),
                self._summary(subject.get("runs")),
            )
            for column, value in enumerate(display_values, start=1):
                item = QTableWidgetItem(value)
                item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    if eeg_file_count > 0
                    else Qt.ItemFlag.NoItemFlags
                )
                if eeg_file_count > 0:
                    item.setToolTip(value)
                self.subject_table.setItem(row_index, column, item)
        self.subject_table.blockSignals(False)
        if first_importable_row >= 0:
            self.subject_table.setCurrentCell(first_importable_row, 0)
        self.subject_table.itemChanged.connect(self._update_selection_state)
        layout.addWidget(self.subject_table, 1)

        self.selection_summary = QLabel()
        self.selection_summary.setObjectName("DialogMutedText")
        layout.addWidget(self.selection_summary)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        normalize_dialog_button_box(buttons, ok_text="Continue")
        self.continue_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._update_selection_state()

    def get_result(self) -> list[str]:
        selected: list[str] = []
        for row in range(self.subject_table.rowCount()):
            item = self.subject_table.item(row, 0)
            if (
                item is not None
                and item.flags() & Qt.ItemFlag.ItemIsEnabled
                and item.flags() & Qt.ItemFlag.ItemIsUserCheckable
                and item.checkState() is Qt.CheckState.Checked
            ):
                selected.append(str(item.data(Qt.ItemDataRole.UserRole)))
        return selected

    def _update_selection_state(self, *_args) -> None:
        selected = self.get_result()
        if self.continue_button is not None:
            self.continue_button.setEnabled(bool(selected))
        if not selected:
            self.selection_summary.setText("Select at least one subject.")
            self.selection_summary.setToolTip("")
            return
        selected_set = set(selected)
        selected_rows = [
            row
            for row in self.subject_rows
            if str(row.get("subject") or "") in selected_set
        ]
        file_count = sum(int(row.get("eeg_file_count") or 0) for row in selected_rows)
        subject_ids = [
            str(row.get("label") or f"sub-{row.get('subject', '')}")
            for row in selected_rows
        ]
        runs = self._unique_values(
            run
            for row in selected_rows
            for run in self._normalized_values(row.get("runs"))
        )
        subject_label = "subject" if len(selected) == 1 else "subjects"
        file_label = "EEG file" if file_count == 1 else "EEG files"
        run_summary = self._compact_values(runs) if runs else "not specified"
        self.selection_summary.setText(
            f"{len(selected)} {subject_label} ({self._compact_values(subject_ids)}) "
            f"· {file_count} {file_label} · Runs {run_summary}"
        )
        self.selection_summary.setToolTip(
            f"Subjects: {', '.join(subject_ids)}\n"
            f"EEG files: {file_count}\n"
            f"Runs: {', '.join(runs) if runs else 'Not specified'}"
        )

    @staticmethod
    def _summary(values: Any) -> str:
        normalized = BidsSubjectSelectionDialog._normalized_values(values)
        return ", ".join(normalized) if normalized else "Not specified"

    @staticmethod
    def _normalized_values(values: Any) -> list[str]:
        if not isinstance(values, (list, tuple)):
            return []
        return [str(value).strip() for value in values if str(value).strip()]

    @staticmethod
    def _unique_values(values: Iterable[str]) -> list[str]:
        return list(dict.fromkeys(values))

    @classmethod
    def _compact_values(cls, values: list[str]) -> str:
        visible = values[: cls._SCOPE_ITEM_LIMIT]
        hidden_count = len(values) - len(visible)
        while len(visible) > 1:
            suffix = f", +{hidden_count}" if hidden_count else ""
            if len(", ".join(visible) + suffix) <= cls._SCOPE_TEXT_LIMIT:
                break
            visible.pop()
            hidden_count += 1

        suffix = f", +{hidden_count}" if hidden_count else ""
        text = ", ".join(visible)
        if len(text + suffix) <= cls._SCOPE_TEXT_LIMIT:
            return text + suffix

        available = cls._SCOPE_TEXT_LIMIT - len(suffix) - len("...")
        return f"{text[:available]}...{suffix}"
