"""Thin chooser for one EEG source before backend interpretation begins."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.dialogs.common import normalize_dialog_button_box

_EEG_FILE_FILTER = (
    "All files (*);;"
    "EEG files (*.set *.SET *.gdf *.GDF *.fif *.FIF *.edf *.EDF "
    "*.bdf *.BDF *.cnt *.CNT *.vhdr *.VHDR)"
)


@dataclass(frozen=True, slots=True)
class EegSourceSelection:
    """Detached chooser result; interpretation remains backend-owned."""

    kind: Literal["files", "folder", "auto"]
    paths: tuple[str, ...]


class EegSourceChooserDialog(BaseDialog):
    """Select files, one folder, or one pasted path without scanning it."""

    def __init__(
        self,
        parent=None,
        *,
        start_directory: str = "",
        suggested_path: str = "",
        choose_files: Callable[[], Sequence[str]] | None = None,
        choose_folder: Callable[[], str] | None = None,
    ) -> None:
        self._start_directory = start_directory
        self._choose_files = choose_files or self._open_files
        self._choose_folder = choose_folder or self._open_folder
        self._pending: EegSourceSelection | None = None
        self._result: EegSourceSelection | None = None
        self.path_edit: QLineEdit
        self.selection_summary: QLabel
        self.choose_files_button: QPushButton
        self.choose_folder_button: QPushButton
        self.button_box: QDialogButtonBox
        self._suggested_path = str(suggested_path).strip()
        super().__init__(parent, title="Import Data", width=460, height=300)

    def init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        guidance = QLabel("Choose EEG files or one folder to review before import.")
        guidance.setWordWrap(True)
        layout.addWidget(guidance)

        picker_row = QHBoxLayout()
        self.choose_files_button = QPushButton("Choose files…")
        self.choose_folder_button = QPushButton("Choose folder…")
        self.choose_files_button.clicked.connect(self._select_files)
        self.choose_folder_button.clicked.connect(self._select_folder)
        picker_row.addWidget(self.choose_files_button)
        picker_row.addWidget(self.choose_folder_button)
        layout.addLayout(picker_row)

        self.selection_summary = QLabel("No source selected")
        self.selection_summary.setObjectName("EegSourceSelectionSummary")
        self.selection_summary.setWordWrap(True)
        layout.addWidget(self.selection_summary)

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Or paste one file or folder path")
        self.path_edit.textChanged.connect(self._use_typed_path)
        layout.addWidget(self.path_edit)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        normalize_dialog_button_box(self.button_box)
        continue_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if continue_button is not None:
            continue_button.setText("Continue")
            continue_button.setEnabled(False)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        if self._suggested_path:
            self.path_edit.setText(self._suggested_path)

    def _open_files(self) -> Sequence[str]:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Choose EEG files",
            self._start_directory,
            _EEG_FILE_FILTER,
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        return paths

    def _open_folder(self) -> str:
        return QFileDialog.getExistingDirectory(
            self,
            "Choose EEG folder",
            self._start_directory,
            options=(
                QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontUseNativeDialog
            ),
        )

    def _select_files(self) -> None:
        paths = tuple(str(path).strip() for path in self._choose_files())
        paths = tuple(path for path in paths if path)
        if not paths:
            return
        self.path_edit.blockSignals(True)
        self.path_edit.clear()
        self.path_edit.blockSignals(False)
        self._set_pending(EegSourceSelection(kind="files", paths=paths))

    def _select_folder(self) -> None:
        path = str(self._choose_folder()).strip()
        if not path:
            return
        self.path_edit.blockSignals(True)
        self.path_edit.clear()
        self.path_edit.blockSignals(False)
        self._set_pending(EegSourceSelection(kind="folder", paths=(path,)))

    def _use_typed_path(self, value: str) -> None:
        path = str(value).strip()
        self._set_pending(
            EegSourceSelection(kind="auto", paths=(path,)) if path else None
        )

    def _set_pending(self, selection: EegSourceSelection | None) -> None:
        self._pending = selection
        if selection is None:
            summary = "No source selected"
        elif selection.kind == "files":
            summary = (
                "1 file selected"
                if len(selection.paths) == 1
                else f"{len(selection.paths)} files selected"
            )
        elif selection.kind == "folder":
            summary = f"Folder: {selection.paths[0]}"
        else:
            summary = f"Path: {selection.paths[0]}"
        self.selection_summary.setText(summary)
        continue_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if continue_button is not None:
            continue_button.setEnabled(selection is not None)

    def accept(self) -> None:
        if self._pending is None:
            return
        self._result = self._pending
        super().accept()

    def reject(self) -> None:
        self._result = None
        super().reject()

    def get_result(self) -> EegSourceSelection | None:
        return self._result
