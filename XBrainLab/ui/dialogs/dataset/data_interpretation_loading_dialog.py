"""Visible loading and recovery surface for the Data Import wizard."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.styles.theme import Theme


class DataInterpretationLoadingDialog(BaseDialog):
    """Keep the wizard visible while source review runs off the UI thread."""

    retry_requested = pyqtSignal()

    _STEP_TITLES = (
        "Choose EEG Data",
        "Load Labels",
        "Review Metadata",
        "Match Labels",
        "Review and Import",
    )
    _COMPACT_STEP_TITLES = ("EEG", "Labels", "Details", "Match", "Review")

    def __init__(self, parent=None, *, initial_step: str = "") -> None:
        self.initial_step = str(initial_step or "").strip()
        self.cancelled_by_user = False
        self.step_labels: list[QLabel] = []
        self.status_title: QLabel
        self.status_detail: QLabel
        self.progress_bar: QProgressBar
        self.retry_button: QPushButton
        self.cancel_button: QPushButton
        super().__init__(
            parent=parent,
            title="Import EEG Data",
            width=1040,
            height=760,
        )
        self.setModal(True)

    def init_ui(self) -> None:
        self.setObjectName("DataImportLoadingDialog")
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(14)

        steps = QHBoxLayout()
        steps.setContentsMargins(0, 0, 0, 0)
        steps.setSpacing(8)
        active_index = self._active_step_index()
        for index, title in enumerate(self._STEP_TITLES):
            label = QLabel(f"{index + 1}. {title}")
            label.setObjectName("DataImportLoadingStep")
            label.setProperty(
                "stepState",
                "active" if index == active_index else "upcoming",
            )
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumHeight(34)
            steps.addWidget(label, stretch=1)
            self.step_labels.append(label)
        root.addLayout(steps)

        root.addStretch(2)
        center_holder = QWidget()
        center_holder.setObjectName("DataImportLoadingContent")
        center_holder.setMaximumWidth(560)
        center_holder.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        center = QVBoxLayout(center_holder)
        center.setContentsMargins(28, 26, 28, 26)
        center.setSpacing(12)

        self.status_title = QLabel()
        self.status_title.setObjectName("DataImportLoadingTitle")
        self.status_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_detail = QLabel()
        self.status_detail.setObjectName("DataImportLoadingDetail")
        self.status_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_detail.setWordWrap(True)
        self.progress_bar = QProgressBar()
        # Keep the modal progress identity distinct from the always-present
        # MainWindow status surface. Both expose the same public operation
        # properties, but only one is the active user context at a time.
        self.progress_bar.setObjectName("DataImportLoadingProgress")
        self.progress_bar.setProperty("operationId", "")
        self.progress_bar.setProperty("operationKind", "")
        self.progress_bar.setProperty("stage", "Preparing import review")
        self.progress_bar.setProperty("progress", "indeterminate")
        self.progress_bar.setProperty("indeterminate", True)
        self.progress_bar.setProperty("operationPhase", "pending")
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMinimumHeight(8)
        center.addWidget(self.status_title)
        center.addWidget(self.status_detail)
        center.addSpacing(4)
        center.addWidget(self.progress_bar)

        center_row = QHBoxLayout()
        center_row.addStretch()
        center_row.addWidget(center_holder, stretch=1)
        center_row.addStretch()
        root.addLayout(center_row)
        root.addStretch(3)

        separator = QFrame()
        separator.setObjectName("DataImportLoadingFooterSeparator")
        separator.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(separator)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(8)
        self.cancel_button = QPushButton("Cancel Import")
        self.cancel_button.setObjectName("DataImportLoadingSecondaryButton")
        self.cancel_button.clicked.connect(self.reject)
        self.retry_button = QPushButton("Retry")
        self.retry_button.setObjectName("DataImportLoadingPrimaryButton")
        self.retry_button.clicked.connect(self._request_retry)
        self.retry_button.setVisible(False)
        footer.addWidget(self.cancel_button)
        footer.addStretch()
        footer.addWidget(self.retry_button)
        root.addLayout(footer)

        if self.initial_step == "Match Labels":
            self.set_stage(
                "Updating label matches",
                "Checking the selected label values and EEG events.",
            )
        else:
            self.set_stage(
                "Preparing import review",
                "Scanning the selected EEG data and nearby label files.",
            )
        self._apply_style()

    def get_result(self) -> dict[str, bool]:
        return {"cancelled": self.cancelled_by_user}

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_step_text()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._sync_step_text()

    def reject(self) -> None:
        self.cancelled_by_user = True
        super().reject()

    def set_stage(self, title: str, detail: str) -> None:
        """Show a busy stage without leaking implementation details."""
        self.status_title.setText(str(title))
        self.status_detail.setText(str(detail))
        self.progress_bar.setVisible(True)
        self.retry_button.setVisible(False)

    def show_error(self, message: str, *, retry_available: bool = True) -> None:
        """Replace the spinner with an actionable, user-facing failure state."""
        self.status_title.setText("Import review could not be prepared")
        self.status_detail.setText(str(message).strip() or "Try the import again.")
        self.progress_bar.setVisible(False)
        self.retry_button.setVisible(bool(retry_available))

    def _request_retry(self) -> None:
        self.set_stage(
            "Preparing import review",
            "Checking the selected source again.",
        )
        self.retry_requested.emit()

    def _active_step_index(self) -> int:
        try:
            return self._STEP_TITLES.index(self.initial_step)
        except ValueError:
            return 0

    def _sync_step_text(self) -> None:
        if not self.step_labels:
            return
        full = tuple(
            f"{index}. {title}" for index, title in enumerate(self._STEP_TITLES, 1)
        )
        compact = tuple(
            f"{index}. {title}"
            for index, title in enumerate(self._COMPACT_STEP_TITLES, 1)
        )
        use_compact = any(
            label.contentsRect().width() > 0
            and label.fontMetrics().horizontalAdvance(text)
            > label.contentsRect().width()
            for label, text in zip(self.step_labels, full, strict=True)
        )
        for label, full_text, compact_text, title in zip(
            self.step_labels,
            full,
            compact,
            self._STEP_TITLES,
            strict=True,
        ):
            label.setText(compact_text if use_compact else full_text)
            label.setToolTip(title if use_compact else "")

    def _apply_style(self) -> None:
        self.setStyleSheet(
            self.styleSheet()
            + f"""
            QDialog#DataImportLoadingDialog {{
                background-color: {Theme.BACKGROUND_DARK};
                color: {Theme.TEXT_MUTED};
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 12px;
            }}
            QLabel {{
                color: {Theme.TEXT_MUTED};
                background: transparent;
                border: none;
            }}
            QLabel#DataImportLoadingStep {{
                color: {Theme.TEXT_SECONDARY};
                background-color: {Theme.BACKGROUND_MID};
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                border-radius: 4px;
                padding: 7px 8px;
                font-weight: 600;
            }}
            QLabel#DataImportLoadingStep[stepState="active"] {{
                color: #e8e8e8;
                background-color: {Theme.BLUE_PRESSED};
                border-color: {Theme.BLUE_FOCUS_BORDER};
            }}
            QWidget#DataImportLoadingContent {{
                background-color: #252526;
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                border-radius: 6px;
            }}
            QLabel#DataImportLoadingTitle {{
                color: #f1f1f1;
                font-size: 17px;
                font-weight: 700;
            }}
            QLabel#DataImportLoadingDetail {{
                color: {Theme.TEXT_SECONDARY};
                font-size: 12px;
            }}
            QProgressBar#DataImportLoadingProgress {{
                background-color: {Theme.BACKGROUND_MID};
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                border-radius: 4px;
            }}
            QProgressBar#DataImportLoadingProgress::chunk {{
                background-color: {Theme.BLUE_PRIMARY};
                border-radius: 3px;
            }}
            QFrame#DataImportLoadingFooterSeparator {{
                color: {Theme.BACKGROUND_LIGHT};
                background-color: {Theme.BACKGROUND_LIGHT};
                border: none;
                max-height: 1px;
            }}
            QPushButton#DataImportLoadingPrimaryButton {{
                background-color: {Theme.BLUE_PRIMARY};
                color: #e8e8e8;
                border: 1px solid {Theme.BLUE_HOVER};
                border-radius: 4px;
                padding: 6px 14px;
                min-height: 20px;
                font-weight: 600;
            }}
            QPushButton#DataImportLoadingPrimaryButton:hover {{
                background-color: {Theme.BLUE_HOVER};
            }}
            QPushButton#DataImportLoadingSecondaryButton {{
                background-color: {Theme.BACKGROUND_MID};
                color: {Theme.TEXT_MUTED};
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                border-radius: 4px;
                padding: 6px 12px;
                min-height: 20px;
            }}
            QPushButton#DataImportLoadingSecondaryButton:hover {{
                color: #e8e8e8;
                border-color: {Theme.ACCENT_PRIMARY};
            }}
            """
        )
