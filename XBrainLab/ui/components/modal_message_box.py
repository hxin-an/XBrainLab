"""Stateless compatibility facade for legacy acknowledgement call sites.

New product code should call :mod:`modal_presentation` directly.  This tiny
adapter exists only while older workflows still use the Qt static-message-box
shape; it preserves their injected ``QMessageBox`` seam while routing the
visible dialog through the shared XBrainLab presentation.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtWidgets import QMessageBox as _QtMessageBox

from .modal_presentation import AlertSeverity, ask_confirmation, show_alert


class ModalMessageBox:
    """Map the legacy static acknowledgement API to the shared modal shell."""

    StandardButton = _QtMessageBox.StandardButton

    @staticmethod
    def warning(parent: Any, title: str, message: str, *_args: Any) -> None:
        show_alert(
            parent,
            severity=AlertSeverity.WARNING,
            title=title,
            message=message,
        )

    @staticmethod
    def critical(parent: Any, title: str, message: str, *_args: Any) -> None:
        show_alert(
            parent,
            severity=AlertSeverity.CRITICAL,
            title=title,
            message=message,
        )

    @staticmethod
    def information(parent: Any, title: str, message: str, *_args: Any) -> None:
        show_alert(
            parent,
            severity=AlertSeverity.INFORMATION,
            title=title,
            message=message,
        )

    @classmethod
    def question(
        cls,
        parent: Any,
        title: str,
        message: str,
        _buttons: object = None,
        _default: object = None,
    ) -> _QtMessageBox.StandardButton:
        accepted = ask_confirmation(
            parent,
            severity=AlertSeverity.WARNING,
            title=title,
            message=message,
            confirm_text="Continue",
            cancel_text="Cancel",
        )
        return cls.StandardButton.Yes if accepted else cls.StandardButton.No
