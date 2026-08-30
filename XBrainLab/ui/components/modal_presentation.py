"""XBrainLab-styled modal alerts and confirmations.

This module deliberately owns only presentation.  Callers remain responsible
for choosing copy, recovery policy, and any mutation that follows a confirmed
action.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStyle,
    QVBoxLayout,
)

from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.dialog_button_policy import _SAFE_DEFAULT_PROPERTY
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
_SEVERITY_PIXMAPS = {
    AlertSeverity.INFORMATION: QStyle.StandardPixmap.SP_MessageBoxInformation,
    AlertSeverity.WARNING: QStyle.StandardPixmap.SP_MessageBoxWarning,
    AlertSeverity.CRITICAL: QStyle.StandardPixmap.SP_MessageBoxCritical,
}

_MODAL_MINIMUM_WIDTH = 420
_MODAL_MAXIMUM_WIDTH = 640
_LONG_MESSAGE_CHARACTER_THRESHOLD = 700
_LONG_MESSAGE_LINE_THRESHOLD = 14
_LONG_MESSAGE_MAXIMUM_HEIGHT = 320


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
        self.message_scroll_area: QScrollArea | None = None
        self.severity_icon_label: QLabel | None = None
        self.title_label: QLabel | None = None
        self.severity_label: QLabel
        self.acknowledge_button: QPushButton
        self.confirm_button: QPushButton | None = None
        self.cancel_button: QPushButton | None = None
        super().__init__(parent=parent, title=title, width=_MODAL_MINIMUM_WIDTH)
        self.fit_to_content(
            minimum_width=_MODAL_MINIMUM_WIDTH,
            maximum_width=_MODAL_MAXIMUM_WIDTH,
        )
        if not self.is_confirmation:
            layout = self.layout()
            if layout is not None:
                self.resize_preserving_center(
                    QSize(
                        self.width(),
                        layout.totalHeightForWidth(self.width()),
                    )
                )
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
        self.setProperty(
            "modalPresentation",
            "confirmation" if self.is_confirmation else "acknowledgement",
        )
        self.setModal(True)
        self.setAccessibleName(self.windowTitle())
        self.setStyleSheet(self.styleSheet() + self._presentation_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)

        if self.is_confirmation and self._severity is not AlertSeverity.WARNING:
            heading_row = QHBoxLayout()
            self.severity_label = self._create_severity_label()
            heading_row.addWidget(self.severity_label)
            heading_row.addStretch(1)
            layout.addLayout(heading_row)
        if self.is_confirmation:
            if self._severity is AlertSeverity.WARNING:
                self.severity_label = self._create_severity_label()
                self.severity_label.hide()
                heading_row = QHBoxLayout()
                heading_row.setSpacing(10)
                heading_row.addWidget(
                    self._create_severity_icon_label(),
                    alignment=Qt.AlignmentFlag.AlignTop,
                )
                copy_column = QVBoxLayout()
                copy_column.setSpacing(6)
                copy_column.setAlignment(Qt.AlignmentFlag.AlignTop)
                copy_column.addWidget(self._create_title_label())
                self._add_message(copy_column)
                heading_row.addLayout(copy_column, 1)
                layout.addLayout(heading_row)
            else:
                self._add_message(layout)
        else:
            self._add_acknowledgement_content(layout)

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
            cancel_button.setProperty(_SAFE_DEFAULT_PROPERTY, True)
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

    def _add_acknowledgement_content(self, layout: QVBoxLayout) -> None:
        heading_row = QHBoxLayout()
        heading_row.setSpacing(10)
        heading_row.addWidget(
            self._create_severity_icon_label(),
            alignment=Qt.AlignmentFlag.AlignTop,
        )

        copy_column = QVBoxLayout()
        copy_column.setSpacing(6)
        copy_column.setAlignment(Qt.AlignmentFlag.AlignTop)
        header_column = QVBoxLayout()
        header_column.setSpacing(2)
        header_column.addWidget(self._create_title_label())
        self.severity_label = self._create_severity_label()
        title_matches_severity = (
            self.windowTitle().strip().casefold()
            == self.severity_label.text().casefold()
        )
        if self._severity is not AlertSeverity.WARNING and not title_matches_severity:
            header_column.addWidget(self.severity_label)
        else:
            self.severity_label.hide()
        copy_column.addLayout(header_column)
        self._add_message(copy_column)
        heading_row.addLayout(copy_column, 1)

        layout.addLayout(heading_row)

    def _create_title_label(self) -> QLabel:
        title_label = QLabel(self.windowTitle())
        self.title_label = title_label
        title_label.setObjectName("ModalAlertTitle")
        title_label.setWordWrap(True)
        title_label.setAccessibleName("Alert title")
        return title_label

    def _create_severity_icon_label(self) -> QLabel:
        severity_icon_label = QLabel()
        self.severity_icon_label = severity_icon_label
        severity_icon_label.setObjectName("ModalAlertSeverityIcon")
        severity_icon_label.setAccessibleName(
            f"{_SEVERITY_LABELS[self._severity]} icon"
        )
        severity_icon_label.setFixedSize(24, 24)
        severity_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        severity_icon_label.setPixmap(
            self.style().standardIcon(_SEVERITY_PIXMAPS[self._severity]).pixmap(20, 20)
        )
        return severity_icon_label

    def _create_severity_label(self) -> QLabel:
        severity_label = QLabel(_SEVERITY_LABELS[self._severity])
        severity_label.setObjectName("ModalAlertSeverity")
        severity_label.setAccessibleName(f"{_SEVERITY_LABELS[self._severity]} message")
        return severity_label

    def _add_message(self, layout: QVBoxLayout) -> None:
        self.message_label = QLabel(self._message)
        self.message_label.setObjectName("ModalAlertMessage")
        self.message_label.setWordWrap(True)
        self.message_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.message_label.setAccessibleName("Message")
        if self._message_needs_scroll_area():
            message_scroll_area = QScrollArea()
            self.message_scroll_area = message_scroll_area
            message_scroll_area.setObjectName("ModalAlertMessageScrollArea")
            message_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
            message_scroll_area.setWidgetResizable(True)
            message_scroll_area.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            message_scroll_area.setMaximumHeight(_LONG_MESSAGE_MAXIMUM_HEIGHT)
            message_scroll_area.setStyleSheet(
                "QScrollArea#ModalAlertMessageScrollArea, "
                "QScrollArea#ModalAlertMessageScrollArea > QWidget > QWidget "
                "{ background-color: transparent; }"
            )
            message_scroll_area.setWidget(self.message_label)
            layout.addWidget(message_scroll_area)
        else:
            layout.addWidget(self.message_label)

    def _message_needs_scroll_area(self) -> bool:
        return (
            len(self._message) > _LONG_MESSAGE_CHARACTER_THRESHOLD
            or self._message.count("\n") >= _LONG_MESSAGE_LINE_THRESHOLD
        )

    def _presentation_stylesheet(self) -> str:
        accent = _SEVERITY_COLORS[self._severity]
        return f"""
            QDialog#XBrainLabModalAlert {{
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                border-radius: 8px;
            }}
            QLabel#ModalAlertTitle {{
                color: {Theme.TEXT_PRIMARY};
                font-size: 16px;
                font-weight: 700;
            }}
            QDialog#XBrainLabModalAlert[modalPresentation="acknowledgement"]
            QLabel#ModalAlertSeverity {{
                color: {accent};
                font-size: 12px;
                font-weight: 700;
            }}
            QDialog#XBrainLabModalAlert[modalPresentation="confirmation"]
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


def show_information(parent: Any, title: str, message: str) -> None:
    """Present a compact informational acknowledgement."""
    show_alert(
        parent,
        severity=AlertSeverity.INFORMATION,
        title=title,
        message=message,
    )


def show_warning(parent: Any, title: str, message: str) -> None:
    """Present a compact warning acknowledgement."""
    show_alert(
        parent,
        severity=AlertSeverity.WARNING,
        title=title,
        message=message,
    )


def show_error(parent: Any, title: str, message: str) -> None:
    """Present a compact critical-error acknowledgement."""
    show_alert(
        parent,
        severity=AlertSeverity.CRITICAL,
        title=title,
        message=message,
    )
