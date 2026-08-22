"""XBrainLab-styled modal alerts and confirmations.

This module deliberately owns only presentation.  Callers remain responsible
for choosing copy, recovery policy, and any mutation that follows a confirmed
action.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.styles.theme import Theme


class AlertSeverity(Enum):
    """Visual severity only; it does not change product error policy."""

    INFORMATION = "information"
    WARNING = "warning"
    CRITICAL = "critical"


_SEVERITY_LABELS = {
    AlertSeverity.INFORMATION: "Information",
    AlertSeverity.WARNING: "Warning",
    AlertSeverity.CRITICAL: "Error",
}
_SEVERITY_COLORS = {
    AlertSeverity.INFORMATION: Theme.BLUE_PRIMARY,
    AlertSeverity.WARNING: Theme.ACCENT_WARNING,
    AlertSeverity.CRITICAL: Theme.ACCENT_ERROR,
}


class ModalAlertDialog(BaseDialog):
    """A compact, accessible modal alert or confirmation dialog."""

    def __init__(
        self,
        *,
        severity: AlertSeverity,
        title: str,
        message: str,
        confirm_text: str | None = None,
        cancel_text: str = "Cancel",
        destructive: bool = False,
        parent: Any = None,
    ) -> None:
        self._severity = severity
        self._message = message
        self._confirm_text = confirm_text
        self._cancel_text = cancel_text
        self._destructive = destructive
        self.message_label: QLabel
        self.severity_label: QLabel
        self.acknowledge_button: QPushButton
        self.confirm_button: QPushButton | None = None
        self.cancel_button: QPushButton | None = None
        super().__init__(parent=parent, title=title, width=460, height=210)
        self.fit_to_content(minimum_width=460)
        if self.cancel_button is not None:
            # BaseDialog intentionally strips default styling globally.  A
            # confirmation is the exception: its safe action must receive
            # Enter focus, while Escape still follows QDialog.reject().
            self.cancel_button.setAutoDefault(True)
            self.cancel_button.setDefault(True)
            self.cancel_button.setFocus(Qt.FocusReason.OtherFocusReason)

    @property
    def is_confirmation(self) -> bool:
        """Whether this instance requires an explicit affirmative action."""
        return self._confirm_text is not None

    def init_ui(self) -> None:
        self.setObjectName("XBrainLabModalAlert")
        self.setModal(True)
        self.setAccessibleName(self.windowTitle())
        self.setStyleSheet(self.styleSheet() + self._presentation_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        heading_row = QHBoxLayout()
        self.severity_label = QLabel(_SEVERITY_LABELS[self._severity])
        self.severity_label.setObjectName("ModalAlertSeverity")
        self.severity_label.setAccessibleName(
            f"{_SEVERITY_LABELS[self._severity]} message"
        )
        heading_row.addWidget(self.severity_label)
        heading_row.addStretch(1)
        layout.addLayout(heading_row)

        self.message_label = QLabel(self._message)
        self.message_label.setObjectName("ModalAlertMessage")
        self.message_label.setWordWrap(True)
        self.message_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.message_label.setAccessibleName("Message")
        layout.addWidget(self.message_label)

        button_box = QDialogButtonBox()
        button_box.setObjectName("ModalAlertButtons")
        if self.is_confirmation:
            confirm_text = self._confirm_text
            if confirm_text is None:
                raise RuntimeError("Confirmation dialog requires confirm text")
            role = (
                QDialogButtonBox.ButtonRole.DestructiveRole
                if self._destructive
                else QDialogButtonBox.ButtonRole.AcceptRole
            )
            confirm_button = button_box.addButton(confirm_text, role)
            if confirm_button is None:
                raise RuntimeError("Confirmation button could not be created")
            self.confirm_button = confirm_button
            confirm_button.setObjectName(
                "ModalDestructiveConfirmButton"
                if self._destructive
                else "PrimaryConfirmButton"
            )
            cancel_button = button_box.addButton(
                self._cancel_text,
                QDialogButtonBox.ButtonRole.RejectRole,
            )
            if cancel_button is None:
                raise RuntimeError("Cancel button could not be created")
            self.cancel_button = cancel_button
            cancel_button.setObjectName("AssistantSecondaryButton")
            if self._destructive:
                confirm_button.clicked.connect(self.accept)
            else:
                button_box.accepted.connect(self.accept)
            button_box.rejected.connect(self.reject)
        else:
            acknowledge_button = button_box.addButton(
                "OK", QDialogButtonBox.ButtonRole.AcceptRole
            )
            if acknowledge_button is None:
                raise RuntimeError("Acknowledge button could not be created")
            self.acknowledge_button = acknowledge_button
            acknowledge_button.setObjectName("PrimaryConfirmButton")
            button_box.accepted.connect(self.accept)
        if self.is_confirmation:
            if self.confirm_button is None:
                raise RuntimeError("Confirmation button was not created")
            self.acknowledge_button = self.confirm_button
        layout.addWidget(button_box, alignment=Qt.AlignmentFlag.AlignRight)

    def _presentation_stylesheet(self) -> str:
        accent = _SEVERITY_COLORS[self._severity]
        return f"""
            QDialog#XBrainLabModalAlert {{
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                border-radius: 8px;
            }}
            QLabel#ModalAlertSeverity {{
                color: {accent};
                font-size: 14px;
                font-weight: 700;
            }}
            QLabel#ModalAlertMessage {{
                color: {Theme.TEXT_PRIMARY};
                font-size: 13px;
                line-height: 1.35;
            }}
            QPushButton#ModalDestructiveConfirmButton {{
                background-color: {Theme.BTN_DANGER_BG};
                border-color: {Theme.BTN_DANGER_BORDER};
                color: {Theme.TEXT_PRIMARY};
                font-weight: 700;
            }}
            QPushButton#ModalDestructiveConfirmButton:hover {{
                background-color: {Theme.BTN_DANGER_HOVER};
            }}
        """


def show_alert(
    parent: Any,
    *,
    severity: AlertSeverity,
    title: str,
    message: str,
) -> None:
    """Present a blocking acknowledgement dialog with existing caller copy."""
    ModalAlertDialog(
        parent=parent,
        severity=severity,
        title=title,
        message=message,
    ).exec()


def ask_confirmation(
    parent: Any,
    *,
    severity: AlertSeverity,
    title: str,
    message: str,
    confirm_text: str,
    cancel_text: str = "Cancel",
    destructive: bool = False,
) -> bool:
    """Return true only after the explicit affirmative action."""
    dialog = ModalAlertDialog(
        parent=parent,
        severity=severity,
        title=title,
        message=message,
        confirm_text=confirm_text,
        cancel_text=cancel_text,
        destructive=destructive,
    )
    return dialog.exec() == dialog.DialogCode.Accepted
