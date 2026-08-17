"""Thin chooser for one EEG source before backend interpretation begins."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.dialogs.common import icon_path, normalize_dialog_button_box
from XBrainLab.ui.styles.theme import Theme

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
        self.source_bar: QFrame
        self.heading_label: QLabel
        self.guidance_label: QLabel
        self.path_edit: QLineEdit
        self.selection_summary: QLabel
        self.choose_files_button: QPushButton
        self.choose_folder_button: QPushButton
        self.button_box: QDialogButtonBox
        self._suggested_path = str(suggested_path).strip()
        super().__init__(parent, title="Import EEG Data", width=560, height=250)

    def init_ui(self) -> None:
        self.setObjectName("EegSourceChooserDialog")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(8)

        self.heading_label = QLabel("Choose EEG data")
        self.heading_label.setObjectName("EegSourceHeading")
        layout.addWidget(self.heading_label)

        self.guidance_label = QLabel(
            "Select files or a dataset folder. BIDS is detected automatically."
        )
        self.guidance_label.setObjectName("EegSourceGuidance")
        self.guidance_label.setWordWrap(True)
        layout.addWidget(self.guidance_label)

        self.source_bar = QFrame(self)
        self.source_bar.setObjectName("EegSourceBar")
        self.source_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        source_bar_layout = QHBoxLayout(self.source_bar)
        source_bar_layout.setContentsMargins(0, 0, 0, 0)
        source_bar_layout.setSpacing(0)

        self.path_edit = QLineEdit(self.source_bar)
        self.path_edit.setObjectName("EegSourcePath")
        self.path_edit.setPlaceholderText("Paste a file or folder path…")
        self.path_edit.setClearButtonEnabled(True)
        self.path_edit.setAccessibleName("EEG source path")
        self.path_edit.textChanged.connect(self._use_typed_path)

        self.choose_files_button = QPushButton("Files…", self.source_bar)
        self.choose_files_button.setObjectName("EegSourceFilesButton")
        self.choose_files_button.setIcon(QIcon(icon_path("file-outline.svg")))
        self.choose_files_button.setIconSize(QSize(14, 14))
        self.choose_files_button.setAccessibleName("Choose EEG files")
        self.choose_folder_button = QPushButton("Folder…", self.source_bar)
        self.choose_folder_button.setObjectName("EegSourceFolderButton")
        self.choose_folder_button.setIcon(QIcon(icon_path("folder-outline.svg")))
        self.choose_folder_button.setIconSize(QSize(14, 14))
        self.choose_folder_button.setAccessibleName("Choose EEG dataset folder")
        self.choose_files_button.clicked.connect(self._select_files)
        self.choose_folder_button.clicked.connect(self._select_folder)
        source_bar_layout.addWidget(self.path_edit, stretch=1)
        source_bar_layout.addWidget(self.choose_files_button)
        source_bar_layout.addWidget(self.choose_folder_button)
        layout.addWidget(self.source_bar)

        self.selection_summary = QLabel("No source selected")
        self.selection_summary.setObjectName("EegSourceSelectionSummary")
        self.selection_summary.setWordWrap(True)
        layout.addWidget(self.selection_summary)
        layout.addStretch(1)

        separator = QFrame(self)
        separator.setObjectName("EegSourceFooterSeparator")
        separator.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(separator)

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

        self._apply_style()

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
        self._set_pending(EegSourceSelection(kind="files", paths=paths))

    def _select_folder(self) -> None:
        path = str(self._choose_folder()).strip()
        if not path:
            return
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
            tooltip = ""
        elif selection.kind == "files":
            count = len(selection.paths)
            first_name = Path(selection.paths[0]).name or selection.paths[0]
            summary = f"{count} file selected · {first_name}"
            if count > 1:
                summary = f"{count} files selected · {first_name} +{count - 1} more"
            tooltip = "\n".join(selection.paths)
            self._sync_path_display(selection.paths[0])
        elif selection.kind == "folder":
            summary = "Folder selected · BIDS is detected after Continue"
            tooltip = selection.paths[0]
            self._sync_path_display(selection.paths[0])
        else:
            summary = "Path ready · Source type is detected after Continue"
            tooltip = selection.paths[0]
        self.path_edit.setToolTip(tooltip)
        self.selection_summary.setText(summary)
        continue_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if continue_button is not None:
            continue_button.setEnabled(selection is not None)

    def _sync_path_display(self, value: str) -> None:
        if self.path_edit.text() != value:
            self.path_edit.blockSignals(True)
            self.path_edit.setText(value)
            self.path_edit.blockSignals(False)
        self.path_edit.setCursorPosition(0)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            self.styleSheet()
            + f"""
            QDialog#EegSourceChooserDialog {{
                background-color: {Theme.BACKGROUND_DARK};
                color: {Theme.TEXT_MUTED};
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 12px;
            }}
            QLabel#EegSourceHeading {{
                color: #f1f1f1;
                font-size: 17px;
                font-weight: 700;
            }}
            QLabel#EegSourceGuidance {{
                color: {Theme.TEXT_SECONDARY};
            }}
            QFrame#EegSourceBar {{
                background-color: #252526;
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                border-radius: 5px;
            }}
            QLineEdit#EegSourcePath {{
                background: transparent;
                color: {Theme.TEXT_PRIMARY};
                border: none;
                border-radius: 5px 0 0 5px;
                padding: 7px 9px;
                min-height: 24px;
            }}
            QPushButton#EegSourceFilesButton,
            QPushButton#EegSourceFolderButton {{
                background-color: {Theme.BACKGROUND_MID};
                color: #e8e8e8;
                border: none;
                border-left: 1px solid {Theme.BACKGROUND_LIGHT};
                border-radius: 0;
                padding: 6px 9px;
                min-width: 54px;
                min-height: 26px;
                font-weight: 600;
            }}
            QPushButton#EegSourceFolderButton {{
                border-radius: 0 4px 4px 0;
            }}
            QPushButton#EegSourceFilesButton:hover,
            QPushButton#EegSourceFolderButton:hover {{
                background-color: {Theme.BACKGROUND_LIGHT};
                border-left-color: {Theme.ACCENT_PRIMARY};
            }}
            QLabel#EegSourceSelectionSummary {{
                color: {Theme.TEXT_SECONDARY};
                font-size: 11px;
                padding: 1px 2px;
            }}
            QFrame#EegSourceFooterSeparator {{
                color: {Theme.BACKGROUND_LIGHT};
                background-color: {Theme.BACKGROUND_LIGHT};
                border: none;
                max-height: 1px;
            }}
            """
        )

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
