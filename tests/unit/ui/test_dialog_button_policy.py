"""Tests for the application-wide standard dialog button policy."""

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor, QIcon, QPixmap
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
