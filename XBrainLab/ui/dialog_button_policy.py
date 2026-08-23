"""Application-wide presentation policy for standard dialog buttons."""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, QSize, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QDialog, QPushButton

_POLICY_ATTRIBUTE = "_xbrainlab_dialog_button_policy"
_NORMALIZED_LABELS = {"ok", "cancel"}
_NORMALIZE_EVENTS = {
    QEvent.Type.ParentChange,
    QEvent.Type.Polish,
    QEvent.Type.Show,
    QEvent.Type.StyleChange,
}


class _DialogButtonPolicy(QObject):
    """Remove platform glyphs from standard OK and Cancel dialog buttons."""

    def eventFilter(  # noqa: N802
        self,
        watched: QObject | None,
        event: QEvent | None,
    ) -> bool:
        if (
            isinstance(watched, QPushButton)
            and event is not None
            and event.type() in _NORMALIZE_EVENTS
            and _is_standard_dialog_button(watched)
        ):
            _normalize_button(watched)
            if event.type() is QEvent.Type.Show:
                # A platform dialog may assign its default button while handling
                # the show event. Normalize once more after that handler returns.
                QTimer.singleShot(
                    0,
                    lambda button=watched: _normalize_button_if_alive(button),
                )
        return False


def install_dialog_button_policy(app: QApplication) -> QObject:
    """Install the process-wide dialog button policy once."""
    existing = getattr(app, _POLICY_ATTRIBUTE, None)
    if isinstance(existing, QObject):
        return existing
    policy = _DialogButtonPolicy(app)
    app.installEventFilter(policy)
    setattr(app, _POLICY_ATTRIBUTE, policy)
    for widget in app.allWidgets():
        if isinstance(widget, QPushButton) and _is_standard_dialog_button(widget):
            _normalize_button(widget)
    return policy


def _is_standard_dialog_button(button: QPushButton) -> bool:
    label = button.text().replace("&", "").strip().casefold()
    return label in _NORMALIZED_LABELS and isinstance(button.window(), QDialog)


def _normalize_button(button: QPushButton) -> None:
    button.setIcon(QIcon())
    button.setIconSize(QSize(0, 0))
    button.setAutoDefault(False)
    button.setDefault(False)


def _normalize_button_if_alive(button: QPushButton) -> None:
    try:
        _normalize_button(button)
    except RuntimeError:
        # A modal dialog can close before the queued normalization runs.
        return
