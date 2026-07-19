"""Resizable multi-line composer for the in-app assistant."""

from __future__ import annotations

from PyQt6.QtCore import QMimeData, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QPlainTextEdit

from XBrainLab.chat_contract import MAX_CHAT_MESSAGE_CONTENT_LENGTH


class AssistantComposer(QPlainTextEdit):
    """Accept multi-line requests while keeping Enter as the send action."""

    submit_requested = pyqtSignal()

    _MIN_HEIGHT = 42
    _MAX_HEIGHT = 96

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._enforcing_character_limit = False
        self.setTabChangesFocus(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        document = self.document()
        if document is not None:
            document.contentsChanged.connect(self._fit_to_content)
            document.contentsChanged.connect(self._enforce_character_limit)
        self._fit_to_content()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """Submit on Enter and preserve Shift+Enter for a new line."""
        is_enter = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        if is_enter and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.submit_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def insertFromMimeData(self, source: QMimeData) -> None:  # noqa: N802
        """Paste only the bounded plain-text portion of external content."""
        if not source.hasText():
            return
        cursor = self.textCursor()
        selected_length = len(cursor.selectedText())
        current_length = len(self.toPlainText())
        available = max(
            MAX_CHAT_MESSAGE_CONTENT_LENGTH - (current_length - selected_length),
            0,
        )
        if available:
            cursor.insertText(source.text()[:available])

    def text(self) -> str:
        """Provide the former QLineEdit read API during the UI migration."""
        return self.toPlainText()

    def setText(self, text: str) -> None:  # noqa: N802
        """Provide the former QLineEdit write API during the UI migration."""
        self.setPlainText(text)

    def setPlainText(self, text: str) -> None:  # noqa: N802
        """Mirror QLineEdit maxLength behavior for programmatic input."""
        super().setPlainText(text[:MAX_CHAT_MESSAGE_CONTENT_LENGTH])

    def _enforce_character_limit(self) -> None:
        if self._enforcing_character_limit:
            return
        text = self.toPlainText()
        if len(text) <= MAX_CHAT_MESSAGE_CONTENT_LENGTH:
            return
        cursor = self.textCursor()
        cursor_position = min(
            cursor.position(),
            MAX_CHAT_MESSAGE_CONTENT_LENGTH,
        )
        self._enforcing_character_limit = True
        try:
            super().setPlainText(text[:MAX_CHAT_MESSAGE_CONTENT_LENGTH])
            cursor = self.textCursor()
            cursor.setPosition(cursor_position)
            self.setTextCursor(cursor)
        finally:
            self._enforcing_character_limit = False

    def _fit_to_content(self) -> None:
        document = self.document()
        document_height = int(document.size().height()) if document is not None else 20
        target = max(self._MIN_HEIGHT, min(self._MAX_HEIGHT, document_height + 18))
        self.setFixedHeight(target)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if target >= self._MAX_HEIGHT
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
