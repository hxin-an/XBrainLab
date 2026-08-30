"""Focused behavior for the shared XBrainLab modal presentation shell."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPoint, Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QPushButton

from XBrainLab.ui.components.modal_presentation import (
    AlertSeverity,
    ModalAlertDialog,
    ask_confirmation,
    show_alert,
    show_error,
    show_information,
    show_warning,
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


@pytest.mark.parametrize(
    ("severity", "title", "severity_text"),
    [
        (AlertSeverity.INFORMATION, "Saved", "Information"),
        (AlertSeverity.WARNING, "Review import", "Warning"),
        (AlertSeverity.CRITICAL, "Import failed", "Error"),
    ],
)
def test_acknowledgement_alert_has_single_surface_hierarchy_without_inner_card(
    qtbot,
    severity,
    title,
    severity_text,
):
    dialog = ModalAlertDialog(
        severity=severity,
        title=title,
        message="Read the detail before continuing.",
    )
    qtbot.addWidget(dialog)

    assert dialog.findChild(QFrame, "ModalAlertContentCard") is None
    assert all(
        frame.frameShape() is not QFrame.Shape.StyledPanel
        for frame in dialog.findChildren(QFrame)
    )
    assert dialog.severity_icon_label.objectName() == "ModalAlertSeverityIcon"
    assert dialog.severity_icon_label.pixmap() is not None
    assert not dialog.severity_icon_label.pixmap().isNull()
    assert dialog.title_label.objectName() == "ModalAlertTitle"
    assert dialog.title_label.text() == title
    assert dialog.severity_label.text() == severity_text
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)
    assert dialog.message_label.x() == dialog.title_label.x()
    visible_labels = (dialog.title_label, dialog.message_label)
    if severity is not AlertSeverity.WARNING:
        visible_labels += (dialog.severity_label,)
    assert all(
        label.height() == label.minimumSizeHint().height() for label in visible_labels
    )


def test_acknowledgement_alert_has_exactly_one_ok_action(qtbot):
    dialog = ModalAlertDialog(
        severity=AlertSeverity.WARNING,
        title="Review import",
        message="Read the detail before continuing.",
    )
    qtbot.addWidget(dialog)

    assert dialog.confirm_button is None
    assert dialog.cancel_button is None
    assert dialog.acknowledge_button.text() == "OK"
    assert (
        dialog.findChild(QPushButton, "PrimaryConfirmButton")
        is dialog.acknowledge_button
    )


def test_generic_warning_title_does_not_repeat_visible_warning_copy(qtbot):
    dialog = ModalAlertDialog(
        severity=AlertSeverity.WARNING,
        title="Warning",
        message="No data loaded.",
    )
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)

    visible_warning_labels = [
        label
        for label in dialog.findChildren(QLabel)
        if label.isVisible() and label.text() == "Warning"
    ]

    assert visible_warning_labels == [dialog.title_label]
    assert dialog.message_label.x() == dialog.title_label.x()
    assert dialog.message_label.y() > dialog.title_label.geometry().bottom()
    assert (
        dialog.message_label.y() - dialog.title_label.geometry().bottom()
        < dialog.title_label.height()
    )


@pytest.mark.parametrize("confirm_text", [None, "Continue"])
def test_warning_modal_hides_redundant_severity_word(qtbot, confirm_text):
    dialog = ModalAlertDialog(
        severity=AlertSeverity.WARNING,
        title="VRAM Warning",
        message=(
            "This requires significant VRAM (Video Memory). "
            "If you experience crashes or lag, please close the 3D view "
            "before using the assistant."
        ),
        confirm_text=confirm_text,
    )
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)

    assert not any(
        label.isVisible() and label.text() == "Warning"
        for label in dialog.findChildren(QLabel)
    )


@pytest.mark.parametrize("destructive", [False, True])
def test_severity_typography_keeps_acknowledgement_and_confirmation_contracts(
    qtbot, destructive
):
    acknowledgement = ModalAlertDialog(
        severity=AlertSeverity.INFORMATION,
        title="Review import",
        message="Read the detail before continuing.",
    )
    confirmation = ModalAlertDialog(
        severity=AlertSeverity.CRITICAL,
        title="Delete model",
        message="Delete this model from this device?",
        confirm_text="Delete Model",
        destructive=destructive,
    )
    qtbot.addWidget(acknowledgement)
    qtbot.addWidget(confirmation)
    acknowledgement.show()
    confirmation.show()
    qtbot.waitUntil(confirmation.isVisible)

    assert acknowledgement.severity_label.font().pixelSize() == 12
    assert confirmation.severity_label.font().pixelSize() == 14


def test_acknowledgement_enter_accepts(qtbot):
    dialog = ModalAlertDialog(
        severity=AlertSeverity.INFORMATION,
        title="Project saved",
        message="Your project was saved successfully.",
    )
    qtbot.addWidget(dialog)
    dialog.show()

    QTest.keyClick(dialog, Qt.Key.Key_Return)

    assert dialog.result() == dialog.DialogCode.Accepted


def test_acknowledgement_escape_rejects(qtbot):
    dialog = ModalAlertDialog(
        severity=AlertSeverity.WARNING,
        title="Review import",
        message="Read the detail before continuing.",
    )
    qtbot.addWidget(dialog)
    dialog.show()

    QTest.keyClick(dialog, Qt.Key.Key_Escape)

    assert dialog.result() == dialog.DialogCode.Rejected


def test_short_alert_fits_content_without_fixed_vertical_gaps(qtbot):
    dialog = ModalAlertDialog(
        severity=AlertSeverity.WARNING,
        title="Storage warning",
        message="Storage is almost full.",
    )
    qtbot.addWidget(dialog)

    assert 420 <= dialog.width() <= 640
    assert dialog.height() < 210


def test_short_descriptive_alert_keeps_footer_close_to_message(qtbot):
    dialog = ModalAlertDialog(
        severity=AlertSeverity.WARNING,
        title="Review import settings",
        message="One or more imported values need your review.",
    )
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)

    footer_gap = (
        dialog.acknowledge_button.mapTo(dialog, QPoint(0, 0)).y()
        - dialog.message_label.geometry().bottom()
        - 1
    )

    assert footer_gap >= 0
    assert footer_gap <= dialog.acknowledge_button.height()


def test_long_alert_uses_bounded_scrollable_message_view(qtbot):
    dialog = ModalAlertDialog(
        severity=AlertSeverity.CRITICAL,
        title="Resource report",
        message="A detailed resource diagnostic line.\n" * 40,
    )
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.message_scroll_area is not None
    assert dialog.message_scroll_area.maximumHeight() == 320
    assert "background-color: transparent" in dialog.message_scroll_area.styleSheet()
    assert dialog.width() <= 640
    assert dialog.severity_icon_label.y() == dialog.title_label.y()
    assert dialog.message_scroll_area.x() == dialog.title_label.x()
    scroll_bar = dialog.message_scroll_area.verticalScrollBar()
    assert scroll_bar.maximum() > 0
    scroll_bar.setValue(scroll_bar.maximum())
    assert scroll_bar.value() == scroll_bar.maximum()


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


def test_destructive_confirmation_click_accepts(qtbot):
    dialog = ModalAlertDialog(
        severity=AlertSeverity.WARNING,
        title="Delete model",
        message="Delete this model from this device?",
        confirm_text="Delete Model",
        destructive=True,
    )
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.confirm_button is not None
    QTest.mouseClick(dialog.confirm_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == dialog.DialogCode.Accepted


def test_public_destructive_confirmation_returns_true_after_real_click(
    qtbot,
    allow_real_modals,
):
    del allow_real_modals

    def _confirm_active_dialog() -> None:
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, ModalAlertDialog)
        button = dialog.findChild(QPushButton, "ModalDestructiveConfirmButton")
        assert button is not None
        button.click()

    QTimer.singleShot(0, _confirm_active_dialog)

    assert ask_confirmation(
        None,
        severity=AlertSeverity.WARNING,
        title="Delete",
        message="Delete this item?",
        confirm_text="Delete",
        destructive=True,
    )


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


def test_severity_facades_delegate_to_shared_modal(monkeypatch):
    calls: list[dict[str, object]] = []

    def _show_alert(parent, *, severity, title, message):
        calls.append(
            {
                "parent": parent,
                "severity": severity,
                "title": title,
                "message": message,
            }
        )

    monkeypatch.setattr(
        "XBrainLab.ui.components.modal_presentation.show_alert",
        _show_alert,
    )

    show_information(None, "Saved", "The file was saved.")
    show_warning(None, "Review", "Review the selected values.")
    show_error(None, "Failed", "The operation failed.")

    assert [call["severity"] for call in calls] == [
        AlertSeverity.INFORMATION,
        AlertSeverity.WARNING,
        AlertSeverity.CRITICAL,
    ]


def test_public_confirmation_maps_rejected_result_to_false(monkeypatch):
    class _RejectedDialog:
        DialogCode = ModalAlertDialog.DialogCode

        def __init__(self, **_kwargs):
            pass

        def exec(self):
            return self.DialogCode.Rejected

    monkeypatch.setattr(
        "XBrainLab.ui.components.modal_presentation.ModalAlertDialog",
        _RejectedDialog,
    )

    assert not ask_confirmation(
        None,
        severity=AlertSeverity.WARNING,
        title="Delete",
        message="Delete this item?",
        confirm_text="Delete",
        destructive=True,
    )
