"""Clickable assistant suggestion row used by the empty state."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QTextLayout, QTextOption
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from .styles import (
    SUGGESTION_CHEVRON_STYLE,
    SUGGESTION_ICON_STYLES,
    SUGGESTION_PROMPT_STYLE,
    SUGGESTION_SUBTITLE_STYLE,
    SUGGESTION_TITLE_STYLE,
)


class AssistantSuggestionCard(QFrame):
    """Keyboard-accessible suggestion with title, context, and direction cue."""

    clicked = pyqtSignal()

    def __init__(
        self,
        title: str,
        subtitle: str,
        *,
        icon: QStyle.StandardPixmap,
        accent: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._subtitle = subtitle
        self.setObjectName("AssistantSuggestionPrompt")
        self.setProperty("accent", accent)
        self.setStyleSheet(SUGGESTION_PROMPT_STYLE)
        self.setMinimumHeight(70)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(title)
        self.setAccessibleDescription(subtitle)
        self.setToolTip(f"{title}\n{subtitle}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 12, 10)
        layout.setSpacing(12)

        self.icon_label = QLabel(self)
        self.icon_label.setObjectName("AssistantSuggestionIcon")
        self.icon_label.setProperty("accent", accent)
        self.icon_label.setFixedSize(38, 38)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet(SUGGESTION_ICON_STYLES)
        style = self.style()
        if style is not None:
            self.icon_label.setPixmap(style.standardIcon(icon).pixmap(18, 18))
        self.icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.icon_label)

        copy = QWidget(self)
        copy.setObjectName("AssistantSuggestionCopy")
        copy.setStyleSheet("background: transparent; border: none;")
        copy.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        copy_layout = QVBoxLayout(copy)
        copy_layout.setContentsMargins(0, 0, 0, 0)
        copy_layout.setSpacing(3)
        self.title_label = QLabel(title, copy)
        self.title_label.setObjectName("AssistantSuggestionTitle")
        self.title_label.setStyleSheet(SUGGESTION_TITLE_STYLE)
        self.title_label.setWordWrap(True)
        self.subtitle_label = QLabel(subtitle, copy)
        self.subtitle_label.setObjectName("AssistantSuggestionSubtitle")
        self.subtitle_label.setStyleSheet(SUGGESTION_SUBTITLE_STYLE)
        self.subtitle_label.setWordWrap(True)
        for label in (self.title_label, self.subtitle_label):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        copy_layout.addWidget(self.title_label)
        copy_layout.addWidget(self.subtitle_label)
        layout.addWidget(copy, 1)

        self.chevron_label = QLabel(self)
        self.chevron_label.setObjectName("AssistantSuggestionChevron")
        self.chevron_label.setStyleSheet(SUGGESTION_CHEVRON_STYLE)
        self.chevron_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.chevron_label.setFixedWidth(18)
        self.chevron_label.setText("\N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK}")
        self.chevron_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.chevron_label)

    def fit_to_width(self, width: int) -> None:
        """Reserve enough height for both wrapped copy lines at ``width``."""
        layout = self.layout()
        if layout is None:
            return
        margins = layout.contentsMargins()
        spacing = layout.spacing()
        copy_width = max(
            int(width)
            - margins.left()
            - margins.right()
            - self.icon_label.width()
            - self.chevron_label.width()
            - (spacing * 2),
            40,
        )

        def wrapped_height(label: QLabel) -> int:
            text_layout = QTextLayout(label.text(), label.font())
            options = QTextOption()
            options.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
            text_layout.setTextOption(options)
            text_layout.beginLayout()
            line_heights: list[int] = []
            try:
                while True:
                    line = text_layout.createLine()
                    if not line.isValid():
                        break
                    line.setLineWidth(float(copy_width))
                    line_heights.append(
                        max(round(line.height()), label.fontMetrics().height())
                    )
            finally:
                text_layout.endLayout()
            required = sum(line_heights)
            label.setMinimumHeight(required)
            return required

        copy_height = (
            wrapped_height(self.title_label) + wrapped_height(self.subtitle_label) + 3
        )
        target_height = max(
            70,
            margins.top()
            + margins.bottom()
            + max(self.icon_label.height(), copy_height),
        )
        if self.height() != target_height:
            self.setFixedHeight(target_height)
            self.updateGeometry()

    def text(self) -> str:
        """Return the visible action title for compatibility with buttons."""
        return self._title

    def setText(self, title: str) -> None:  # noqa: N802
        """Update the visible and accessible action title."""
        self._title = str(title)
        self.title_label.setText(self._title)
        self.setAccessibleName(self._title)
        self.setToolTip(f"{self._title}\n{self._subtitle}")

    def subtitle(self) -> str:
        """Return the supporting copy shown under the title."""
        return self._subtitle

    def click(self) -> None:
        """Trigger the suggestion using the same contract as a button click."""
        if self.isEnabled():
            self.clicked.emit()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.isEnabled()
            and self.rect().contains(event.position().toPoint())
        ):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.click()
            event.accept()
            return
        super().keyPressEvent(event)
