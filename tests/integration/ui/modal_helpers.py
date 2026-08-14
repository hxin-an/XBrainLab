"""Shared helpers for driving real modal Qt surfaces in integration tests."""

from __future__ import annotations

from PyQt6.QtWidgets import QApplication, QDialog, QWidget


def visible_modal_dialog() -> QWidget | None:
    """Return the active modal or the one settled visible modal surface.

    Qt's offscreen platform can lose ``activeModalWidget()`` while an
    application-modal loading dialog hands ownership to an already-visible
    preview dialog. A user can still see and interact with that preview, so a
    UI driver should follow the unambiguous visible modal surface instead of
    waiting forever on platform bookkeeping.
    """
    active_modal = QApplication.activeModalWidget()
    if active_modal is not None and active_modal.isVisible():
        return active_modal
    visible_modals = [
        widget
        for widget in QApplication.topLevelWidgets()
        if isinstance(widget, QDialog) and widget.isVisible() and widget.isModal()
    ]
    return visible_modals[0] if len(visible_modals) == 1 else None
