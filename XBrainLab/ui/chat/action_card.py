"""Transient action cards shown inside the assistant message area."""

from __future__ import annotations

import re
from collections.abc import Mapping

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QContextMenuEvent, QKeyEvent, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QFrame,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.llm.agent.confirmation import AgentConfirmationRequest

from .styles import (
    ACTION_CARD_DESTRUCTIVE_BUTTON_STYLE,
    ACTION_CARD_FRAME_STYLE,
    ACTION_CARD_LABEL_STYLE,
    ACTION_CARD_PRIMARY_BUTTON_STYLE,
    ACTION_CARD_SECONDARY_BUTTON_STYLE,
    ACTION_CARD_TEXT_STYLE,
    ACTION_CARD_TITLE_STYLE,
    ACTION_CARD_VALUE_STYLE,
)

_SOFT_WRAP_MARK = "\u200b"
_MAX_UNBROKEN_DISPLAY_CHARS = 12


def _add_soft_wrap_opportunities(text: str) -> str:
    """Let Qt wrap long paths, hashes, and identifiers without changing meaning."""

    def wrap_token(match: re.Match[str]) -> str:
        token = match.group(0)
        return _SOFT_WRAP_MARK.join(
            token[index : index + _MAX_UNBROKEN_DISPLAY_CHARS]
            for index in range(0, len(token), _MAX_UNBROKEN_DISPLAY_CHARS)
        )

    return re.sub(
        rf"[^\s{_SOFT_WRAP_MARK}]{{{_MAX_UNBROKEN_DISPLAY_CHARS + 1},}}",
        wrap_token,
        text,
    )


class _SoftWrappingValueLabel(QLabel):
    """Wrap long tokens visually while copying the exact original value."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._raw_text = ""

    def set_wrapped_text(self, text: str) -> None:
        self._raw_text = text
        self.setText(_add_soft_wrap_opportunities(text))
        self.setAccessibleDescription(text)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.matches(QKeySequence.StandardKey.Copy):
            self._copy_selection()
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        menu = QMenu(self)
        copy_action = menu.addAction("Copy")
        if copy_action is None:
            return
        copy_action.setEnabled(bool(self.selectedText()))
        copy_action.triggered.connect(self._copy_selection)
        menu.exec(event.globalPos())

    def _copy_selection(self) -> None:
        selected = self.selectedText()
        if not selected:
            return
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        clipboard.setText(selected.replace(_SOFT_WRAP_MARK, "").replace("\u2029", "\n"))


class AssistantConfirmationCard(QFrame):
    """Present one exact correlated assistant action for user approval."""

    decision_requested = pyqtSignal(object, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._request: AgentConfirmationRequest | None = None
        self.setObjectName("AssistantConfirmationCard")
        self.setStyleSheet(ACTION_CARD_FRAME_STYLE)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        self.title_label = QLabel("Confirmation required")
        self.title_label.setObjectName("AssistantActionCardTitle")
        self.title_label.setStyleSheet(ACTION_CARD_TITLE_STYLE)
        layout.addWidget(self.title_label)

        self.description_label = QLabel("")
        self.description_label.setObjectName("AssistantActionCardDescription")
        self.description_label.setStyleSheet(ACTION_CARD_TEXT_STYLE)
        self.description_label.setWordWrap(True)
        self.description_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        layout.addWidget(self.description_label)

        self.values_summary = _SoftWrappingValueLabel()
        self.values_summary.setObjectName("AssistantActionCardValues")
        self.values_summary.setStyleSheet(ACTION_CARD_VALUE_STYLE)
        self.values_summary.setWordWrap(True)
        self.values_summary.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        self.values_summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        layout.addWidget(self.values_summary)

        self.reason_title = QLabel("Reason")
        self.reason_title.setObjectName("AssistantActionCardLabel")
        self.reason_title.setStyleSheet(ACTION_CARD_LABEL_STYLE)
        layout.addWidget(self.reason_title)

        self.reason_label = QLabel("")
        self.reason_label.setObjectName("AssistantActionCardReason")
        self.reason_label.setStyleSheet(ACTION_CARD_TEXT_STYLE)
        self.reason_label.setWordWrap(True)
        self.reason_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        layout.addWidget(self.reason_label)

        button_row = QWidget(self)
        button_row.setObjectName("AssistantActionCardButtons")
        button_row.setStyleSheet("background: transparent; border: none;")
        button_layout = QBoxLayout(
            QBoxLayout.Direction.LeftToRight,
            button_row,
        )
        self.button_layout = button_layout
        button_layout.setContentsMargins(0, 2, 0, 0)
        button_layout.setSpacing(8)

        self.secondary_button = QPushButton("Keep current value")
        self.secondary_button.setObjectName("AssistantActionCardSecondary")
        self.secondary_button.setStyleSheet(ACTION_CARD_SECONDARY_BUTTON_STYLE)
        self.secondary_button.setMinimumHeight(34)
        self.secondary_button.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.secondary_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.secondary_button.clicked.connect(
            lambda _checked=False: self._resolve(False)
        )
        button_layout.addWidget(self.secondary_button)

        self.primary_button = QPushButton("Apply change")
        self.primary_button.setObjectName("AssistantActionCardPrimary")
        self.primary_button.setStyleSheet(ACTION_CARD_PRIMARY_BUTTON_STYLE)
        self.primary_button.setMinimumHeight(34)
        self.primary_button.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.primary_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.primary_button.clicked.connect(lambda _checked=False: self._resolve(True))
        button_layout.addWidget(self.primary_button)
        layout.addWidget(button_row)
        self.setVisible(False)

    @property
    def request_id(self) -> str | None:
        """Return the id of the request currently leased to this card."""
        return self._request.request_id if self._request is not None else None

    def present(
        self,
        request: AgentConfirmationRequest,
        *,
        current_values: Mapping[str, str] | None = None,
        current_context_changed: bool = False,
    ) -> None:
        """Render a request without changing or reconstructing its parameters."""
        if not isinstance(request, AgentConfirmationRequest):
            raise TypeError("Assistant confirmation cards require a typed request.")
        self._request = request
        self.setProperty("destructive", request.destructive)
        self.title_label.setText(
            "Confirmation required"
            if request.destructive
            else (
                "Suggested change"
                if request.parameter_rows
                else "Confirmation required"
            )
        )
        self.description_label.setText(request.action_label)
        self.description_label.setVisible(not request.parameter_rows)
        self.reason_label.setText(request.description)
        values_text = self._format_values(
            request,
            current_values=current_values,
            current_context_changed=current_context_changed,
        )
        self.values_summary.set_wrapped_text(values_text)

        self.primary_button.setText(request.action_label)
        self.primary_button.setStyleSheet(
            ACTION_CARD_DESTRUCTIVE_BUTTON_STYLE
            if request.destructive
            else ACTION_CARD_PRIMARY_BUTTON_STYLE
        )
        self.secondary_button.setText(
            "Cancel"
            if request.destructive or not request.parameter_rows
            else "Keep current value"
        )
        self.set_submitting(False)
        self.setVisible(True)
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)

    def resizeEvent(self, event) -> None:  # noqa: N802
        """Stack actions when both labels cannot remain readable."""
        super().resizeEvent(event)
        self.button_layout.setDirection(
            QBoxLayout.Direction.TopToBottom
            if self.width() < 360
            else QBoxLayout.Direction.LeftToRight
        )

    def set_submitting(self, submitting: bool) -> None:
        """Prevent duplicate decisions while the runtime accepts the response."""
        self.primary_button.setEnabled(not submitting)
        self.secondary_button.setEnabled(not submitting)
        if submitting:
            self.primary_button.setText("Applying...")
        elif self._request is not None:
            self.primary_button.setText(self._request.action_label)

    def clear(self) -> None:
        """Release the UI lease without creating any backend resolution."""
        self._request = None
        self.setVisible(False)

    def _resolve(self, approved: bool) -> None:
        request = self._request
        if request is None or not self.primary_button.isEnabled():
            return
        self.set_submitting(True)
        self.decision_requested.emit(request, approved)

    @staticmethod
    def _format_values(
        request: AgentConfirmationRequest,
        *,
        current_values: Mapping[str, str] | None,
        current_context_changed: bool,
    ) -> str:
        if current_context_changed:
            prefix = (
                "The workflow changed after this suggestion. XBrainLab will "
                "validate the action again before applying it."
            )
        else:
            prefix = ""

        rows: list[str] = []
        current = {
            str(key): str(value) for key, value in (current_values or {}).items()
        }
        for label, proposed in request.parameter_rows:
            existing = current.get(label)
            if existing is not None and existing != proposed:
                rows.append(f"{label}\n{existing}  ->  {proposed}")
            else:
                rows.append(f"{label}\n{proposed}")
        if not rows:
            rows.append("This action changes the current XBrainLab workflow.")
        return "\n\n".join(part for part in (prefix, *rows) if part)
