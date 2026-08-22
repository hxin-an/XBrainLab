"""Focused behavior for the shared XBrainLab modal presentation shell."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

from XBrainLab.ui.components.modal_presentation import (
    AlertSeverity,
    ModalAlertDialog,
    ask_confirmation,
    show_alert,
)


def test_alert_uses_xbrainlab_dialog_shell_and_wraps_message(qtbot):
    dialog = ModalAlertDialog(
        severity=AlertSeverity.WARNING,
        title="Storage warning",
        message="A deliberately long recovery message " * 12,
    )
    qtbot.addWidget(dialog)

    assert dialog.objectName() == "XBrainLabModalAlert"
    assert dialog.message_label.wordWrap()
    assert dialog.windowTitle() == "Storage warning"
    assert dialog.severity_label.text() == "Warning"
    assert dialog.acknowledge_button.text() == "OK"


def test_confirmation_keeps_cancel_as_default_and_escape_returns_rejected(qtbot):
    dialog = ModalAlertDialog(
        severity=AlertSeverity.WARNING,
        title="Delete model",
        message="Delete this model from this device?",
        confirm_text="Delete Model",
        cancel_text="Cancel",
        destructive=True,
    )
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.confirm_button is not None
    assert dialog.cancel_button is not None
    assert dialog.cancel_button.isDefault()

    QTest.keyClick(dialog, Qt.Key.Key_Escape)

    assert dialog.result() == dialog.DialogCode.Rejected


def test_confirmation_cancel_stays_default_after_show(qtbot):
    dialog = ModalAlertDialog(
        severity=AlertSeverity.WARNING,
        title="Delete model",
        message="Delete this model from this device?",
        confirm_text="Delete Model",
        destructive=True,
    )
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)

    assert dialog.cancel_button is not None
    assert dialog.cancel_button.isDefault()


def test_public_functions_preserve_exec_result_mapping(monkeypatch):
    constructed: list[dict[str, object]] = []

    class _FakeDialog:
        DialogCode = ModalAlertDialog.DialogCode

        def __init__(self, **kwargs):
            constructed.append(kwargs)

        def exec(self):
            return self.DialogCode.Accepted

    monkeypatch.setattr(
        "XBrainLab.ui.components.modal_presentation.ModalAlertDialog",
        _FakeDialog,
    )

    show_alert(
        None,
        severity=AlertSeverity.INFORMATION,
        title="Success",
        message="Saved.",
    )
    assert ask_confirmation(
        None,
        severity=AlertSeverity.WARNING,
        title="Delete",
        message="Delete this item?",
        confirm_text="Delete",
        destructive=True,
    )
    assert constructed[0].get("confirm_text") is None
    assert constructed[1]["confirm_text"] == "Delete"
    assert constructed[1]["destructive"] is True
