"""Clickable assistant suggestion row used by the empty state."""

from __future__ import annotations

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
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


class AssistantSuggestionCard(QPushButton):
    """Native button presenting one prompt suggestion with supporting context."""

    def __init__(
        self,
        title: str,
        subtitle: str,
        *,
        icon: QStyle.StandardPixmap,
        accent: str,
        parent=None,
    ) -> None:
        super().__init__("", parent)
        self._title = title
        self._subtitle = subtitle
        self.setObjectName("AssistantSuggestionPrompt")
        self.setProperty("accent", accent)
        self.setProperty("assistantCustomContent", True)
        self.setStyleSheet(SUGGESTION_PROMPT_STYLE)
        self.setMinimumHeight(52)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAutoDefault(False)
        self.setDefault(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(title)
        self.setAccessibleDescription(subtitle)
        self.setToolTip(f"{title}\n{subtitle}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 8, 6)
        layout.setSpacing(6)

        self.icon_label = QLabel(self)
        self.icon_label.setObjectName("AssistantSuggestionIcon")
        self.icon_label.setProperty("accent", accent)
        self.icon_label.setFixedSize(0, 0)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet(SUGGESTION_ICON_STYLES)
        self.icon_label.setVisible(False)
        self.icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.icon_label)

        copy = QWidget(self)
        copy.setObjectName("AssistantSuggestionCopy")
        copy.setStyleSheet("background: transparent; border: none;")
        copy.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        copy_layout = QVBoxLayout(copy)
        copy_layout.setContentsMargins(0, 0, 0, 0)
        copy_layout.setSpacing(2)
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
        self.chevron_label.setFixedWidth(16)
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
            - (self.icon_label.width() if self.icon_label.isVisible() else 0)
            - self.chevron_label.width()
            - spacing,
            40,
        )

        def wrapped_height(label: QLabel) -> int:
            label.ensurePolished()
            required = (
                label.fontMetrics()
                .boundingRect(
                    QRect(0, 0, copy_width, 10_000),
                    int(
                        Qt.AlignmentFlag.AlignLeft
                        | Qt.AlignmentFlag.AlignTop
                        | Qt.TextFlag.TextWordWrap
                    ),
                    label.text(),
                )
                .height()
            )
            required = max(required, label.fontMetrics().height())
            label.setMinimumHeight(required)
            return required

        copy_height = (
            wrapped_height(self.title_label) + wrapped_height(self.subtitle_label) + 2
        )
        target_height = max(
            52,
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

    def setText(self, title: str | None) -> None:  # noqa: N802
        """Update the visible and accessible action title."""
        self._title = str(title)
        self.title_label.setText(self._title)
        self.setAccessibleName(self._title)
        self.setToolTip(f"{self._title}\n{self._subtitle}")

    def subtitle(self) -> str:
        """Return the supporting copy shown under the title."""
        return self._subtitle

    def set_subtitle(self, subtitle: str) -> None:
        """Update the supporting copy without rebuilding the prompt row."""
        self._subtitle = str(subtitle)
        self.subtitle_label.setText(self._subtitle)
        self.setAccessibleDescription(self._subtitle)
        self.setToolTip(f"{self._title}\n{self._subtitle}")
