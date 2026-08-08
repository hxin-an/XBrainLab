"""Compact BIDS subject selection before full import discovery."""

from __future__ import annotations

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
        self.subject_table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.subject_table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        header = self.subject_table.horizontalHeader()
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
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
                if eeg_file_count > 0
                else Qt.ItemFlag.NoItemFlags
            )
            subject_item.setCheckState(
                Qt.CheckState.Checked
                if row_index == first_importable_row
                else Qt.CheckState.Unchecked
            )
            self.subject_table.setItem(row_index, 0, subject_item)
            self.subject_table.setItem(
                row_index,
                1,
                QTableWidgetItem(str(eeg_file_count)),
            )
            self.subject_table.setItem(
                row_index,
                2,
                QTableWidgetItem(self._summary(subject.get("sessions"))),
            )
            self.subject_table.setItem(
                row_index,
                3,
                QTableWidgetItem(self._summary(subject.get("tasks"))),
            )
            self.subject_table.setItem(
                row_index,
                4,
                QTableWidgetItem(self._summary(subject.get("runs"))),
            )
        self.subject_table.blockSignals(False)
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
            if item is not None and item.checkState() is Qt.CheckState.Checked:
                selected.append(str(item.data(Qt.ItemDataRole.UserRole)))
        return selected

    def _update_selection_state(self, *_args) -> None:
        selected = self.get_result()
        if self.continue_button is not None:
            self.continue_button.setEnabled(bool(selected))
        if not selected:
            self.selection_summary.setText("Select at least one subject.")
            return
        selected_set = set(selected)
        file_count = sum(
            int(row.get("eeg_file_count") or 0)
            for row in self.subject_rows
            if str(row.get("subject") or "") in selected_set
        )
        subject_label = "subject" if len(selected) == 1 else "subjects"
        file_label = "EEG file" if file_count == 1 else "EEG files"
        self.selection_summary.setText(
            f"{len(selected)} {subject_label} selected · {file_count} {file_label}"
        )

    @staticmethod
    def _summary(values: Any) -> str:
        if not isinstance(values, (list, tuple)):
            return "Not specified"
        normalized = [str(value).strip() for value in values if str(value).strip()]
        return ", ".join(normalized) if normalized else "Not specified"
