"""Tests for the application-wide standard dialog button policy."""

import pytest
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QMessageBox, QPushButton


def _visible_test_icon() -> QIcon:
    pixmap = QPixmap(QSize(12, 12))
    pixmap.fill(QColor("#00ff00"))
    return QIcon(pixmap)


def test_dialog_button_policy_removes_ok_cancel_icons_on_show(qapp, qtbot) -> None:
    from XBrainLab.ui.dialog_button_policy import install_dialog_button_policy

    install_dialog_button_policy(qapp)
    message_box = QMessageBox()
    qtbot.addWidget(message_box)
    message_box.setIcon(QMessageBox.Icon.Critical)
    message_box.setStandardButtons(
        QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
    )
    ok_button = message_box.button(QMessageBox.StandardButton.Ok)
    cancel_button = message_box.button(QMessageBox.StandardButton.Cancel)
    assert isinstance(ok_button, QPushButton)
    assert isinstance(cancel_button, QPushButton)
    ok_button.setIcon(_visible_test_icon())
    cancel_button.setIcon(_visible_test_icon())
    ok_button.setDefault(True)
    ok_button.setAutoDefault(True)

    message_box.show()
    qapp.processEvents()
    qtbot.waitUntil(lambda: not ok_button.isDefault(), timeout=1_000)

    assert ok_button.icon().isNull()
    assert cancel_button.icon().isNull()
    assert ok_button.isDefault() is False
    assert ok_button.autoDefault() is False
    assert message_box.icon() is QMessageBox.Icon.Critical


@pytest.mark.parametrize(
    ("confirm_text", "destructive"),
    (("Open link", False), ("Delete Model", True)),
)
def test_dialog_button_policy_preserves_modal_confirmation_safe_cancel_default(
    qapp, qtbot, confirm_text, destructive
) -> None:
    """The global visual policy must not override a confirmation's safe default."""
    from XBrainLab.ui.components.modal_presentation import (
        AlertSeverity,
        ModalAlertDialog,
    )
    from XBrainLab.ui.dialog_button_policy import install_dialog_button_policy

    install_dialog_button_policy(qapp)
    dialog = ModalAlertDialog(
        severity=AlertSeverity.WARNING,
        title="Confirm action",
        message="Continue with this action?",
        confirm_text=confirm_text,
        destructive=destructive,
    )
    qtbot.addWidget(dialog)

    dialog.show()
    qapp.processEvents()

    assert dialog.cancel_button is not None
    assert dialog.cancel_button.isDefault()
    assert dialog.cancel_button.autoDefault()
    assert dialog.confirm_button is not None
    assert dialog.confirm_button.isDefault() is False

    QTest.keyClick(dialog, Qt.Key.Key_Enter)

    assert dialog.result() == dialog.DialogCode.Rejected

    escape_dialog = ModalAlertDialog(
        severity=AlertSeverity.WARNING,
        title="Confirm action",
        message="Continue with this action?",
        confirm_text=confirm_text,
        destructive=destructive,
    )
    qtbot.addWidget(escape_dialog)
    escape_dialog.show()
    qapp.processEvents()

    QTest.keyClick(escape_dialog, Qt.Key.Key_Escape)

    assert escape_dialog.result() == escape_dialog.DialogCode.Rejected
