"""Message Bubble Widget for Chat Panel.

Provides the ``MessageBubble`` widget that renders a single chat message
with dynamic width adjustment, link handling, and sender-based styling.
"""

from math import ceil

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QTextOption
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.controller.chat_controller import (
    ChatMessagePresentationKind,
)
from XBrainLab.backend.utils.logger import logger

from .styles import (
    AGENT_BUBBLE_FRAME_STYLE,
    AGENT_BUBBLE_TEXT_STYLE,
    ATTENTION_BUBBLE_FRAME_STYLE,
    CANCELLED_BUBBLE_FRAME_STYLE,
    CLARIFICATION_BUBBLE_FRAME_STYLE,
    ERROR_BUBBLE_FRAME_STYLE,
    MESSAGE_KIND_LABEL_STYLES,
    TOOL_RESULT_BUBBLE_FRAME_STYLE,
    USER_BUBBLE_FRAME_STYLE,
    USER_BUBBLE_TEXT_STYLE,
)

MessagePresentationKind = ChatMessagePresentationKind
"""Compatibility alias for the typed persisted presentation kind."""


_SEMANTIC_PRESENTATION = {
    MessagePresentationKind.CLARIFICATION: (
        "Needs input",
        CLARIFICATION_BUBBLE_FRAME_STYLE,
    ),
    MessagePresentationKind.ATTENTION: (
        "Needs attention",
        ATTENTION_BUBBLE_FRAME_STYLE,
    ),
    MessagePresentationKind.ERROR: (
        "Error",
        ERROR_BUBBLE_FRAME_STYLE,
    ),
    MessagePresentationKind.TOOL_RESULT: (
        "Completed",
        TOOL_RESULT_BUBBLE_FRAME_STYLE,
    ),
    MessagePresentationKind.CANCELLED: (
        "Cancelled",
        CANCELLED_BUBBLE_FRAME_STYLE,
    ),
}


class MessageBubble(QWidget):
    """A chat message bubble widget.

    Contains a ``QFrame`` bubble container with a ``QTextBrowser`` for
    rich text display. Supports dynamic width adjustment on window resize,
    Markdown rendering, and confirmed HTTPS links.

    Attributes:
        is_user: Whether this bubble represents a user message.
        bubble_frame: The styled QFrame container for the bubble.
        text_edit: The QTextBrowser displaying the message content.

    """

    def __init__(
        self,
        text: str,
        is_user: bool,
        parent=None,
        *,
        presentation_kind: MessagePresentationKind | None = None,
    ):
        """Initialize the message bubble.

        Args:
            text: The message text content (Markdown supported).
            is_user: Whether this is a user message (affects alignment
                and styling).
            parent: Optional parent widget.

        """
        super().__init__(parent)
        self.is_user = is_user
        self.bubble_frame: QFrame
        self.text_edit: QTextBrowser
        self.kind_label: QLabel
        self._raw_text = text  # Store raw text to preserve fidelity
        self._reflow_timer = QTimer(self)
        self._reflow_timer.setSingleShot(True)
        self._reflow_timer.timeout.connect(self._reflow_after_text_change)
        self.presentation_kind = presentation_kind or (
            MessagePresentationKind.USER
            if is_user
            else MessagePresentationKind.ASSISTANT
        )

        self._init_ui(text)

    def _init_ui(self, text: str):
        """Build the bubble layout and apply sender-based styling.

        Args:
            text: The initial text content to display.

        """
        # Main horizontal layout for this row
        row_layout = QHBoxLayout(self)
        row_layout.setContentsMargins(2, 0, 2, 0)
        row_layout.setSpacing(0)

        # Create the bubble frame
        self.bubble_frame = QFrame()
        self.bubble_frame.setObjectName("BubbleFrame")
        self.bubble_frame.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Minimum,
        )

        # Create bubble's internal layout
        bubble_layout = QVBoxLayout(self.bubble_frame)
        bubble_layout.setContentsMargins(15, 10, 15, 10)
        bubble_layout.setSpacing(5)

        self.kind_label = QLabel("")
        self.kind_label.setObjectName("MessageKindLabel")
        self.kind_label.setVisible(False)
        bubble_layout.addWidget(self.kind_label)

        # Create the text edit (ReadOnly)
        self.text_edit = QTextBrowser()
        self.text_edit.setMarkdown(text)
        self.text_edit.setReadOnly(True)
        self.text_edit.setFrameStyle(QFrame.Shape.NoFrame)
        self.text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_edit.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )

        # Interaction Flags: Enable selection AND links
        self.text_edit.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard,
        )
        self.text_edit.setOpenExternalLinks(False)
        self.text_edit.anchorClicked.connect(self._on_link_clicked)

        self.text_edit.setWordWrapMode(
            QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere
        )
        doc = self.text_edit.document()
        if doc:
            doc.setDocumentMargin(0)  # Remove internal document margin
        self.text_edit.setContentsMargins(0, 0, 0, 0)

        # Transparent background
        self.text_edit.setStyleSheet(
            "background: transparent; padding: 0px; margin: 0px; border: none;",
        )

        bubble_layout.addWidget(self.text_edit)

        # Apply styles based on sender
        if self.is_user:
            self.bubble_frame.setStyleSheet(USER_BUBBLE_FRAME_STYLE)
            self.text_edit.setStyleSheet(USER_BUBBLE_TEXT_STYLE)

            row_layout.addStretch(1)
            row_layout.addWidget(self.bubble_frame)
            row_layout.setAlignment(self.bubble_frame, Qt.AlignmentFlag.AlignRight)
        else:
            self.bubble_frame.setStyleSheet(AGENT_BUBBLE_FRAME_STYLE)
            self.text_edit.setStyleSheet(AGENT_BUBBLE_TEXT_STYLE)

            row_layout.addWidget(self.bubble_frame)
            row_layout.addStretch(1)
            row_layout.setAlignment(self.bubble_frame, Qt.AlignmentFlag.AlignLeft)
        self.set_presentation_kind(self.presentation_kind)

    def set_presentation_kind(self, kind: MessagePresentationKind) -> None:
        """Apply one semantic transcript treatment without changing message text."""
        if not isinstance(kind, MessagePresentationKind):
            raise TypeError("Message presentation kind must be typed.")
        if self.is_user:
            kind = MessagePresentationKind.USER
        self.presentation_kind = kind

        semantic = _SEMANTIC_PRESENTATION.get(kind)
        if semantic is None:
            self.kind_label.clear()
            self.kind_label.setVisible(False)
            self.bubble_frame.setStyleSheet(
                USER_BUBBLE_FRAME_STYLE
                if kind is MessagePresentationKind.USER
                else AGENT_BUBBLE_FRAME_STYLE
            )
        else:
            label, frame_style = semantic
            self.kind_label.setText(label)
            self.kind_label.setAccessibleName(label)
            self.kind_label.setStyleSheet(MESSAGE_KIND_LABEL_STYLES[kind.value])
            self.kind_label.setVisible(True)
            self.bubble_frame.setStyleSheet(frame_style)
        self.bubble_frame.setProperty("assistantMessageKind", kind.value)
        style = self.bubble_frame.style()
        if style is not None:
            style.unpolish(self.bubble_frame)
            style.polish(self.bubble_frame)
        if self.isVisible():
            self._reflow_timer.start(0)

    def _on_link_clicked(self, url: QUrl) -> bool:
        """Open a valid HTTPS link only after the user confirms its host.

        Assistant-authored Markdown is untrusted content. Local files and custom
        schemes must be exposed through a typed host action rather than opened
        directly from generated text.
        """
        scheme = url.scheme().lower()
        host = url.host().strip()
        if not url.isValid() or scheme != "https" or not host:
            logger.warning(
                "Blocked Assistant link with unsupported scheme '%s'",
                scheme or "none",
            )
            return False

        reply = QMessageBox.question(
            self,
            "Open external link?",
            f"Open this website in your browser?\n\n{host}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return False
        return QDesktopServices.openUrl(url)

    def adjust_width(self, container_width: int):
        """Adjust bubble width based on container and content size.

        Calculates optimal width and height dynamically, capping at
        80% of the container width.

        Args:
            container_width: The available width in pixels from the
                parent scroll area viewport.

        """
        if container_width <= 0:
            return

        max_bubble_width = min(int(container_width * 0.88), 720)
        min_bubble_width = 84 if self.is_user else 96

        # Margins: 15+15=30 horizontal, 10+10=20 vertical
        layout_h_margins = 30
        layout_v_margins = 20

        doc = self.text_edit.document()
        if not doc:
            return

        # 1. Start with infinite width to find natural width
        doc.setTextWidth(-1)
        natural_width = doc.idealWidth() + layout_h_margins
        if self.kind_label is not None and not self.kind_label.isHidden():
            natural_width = max(
                natural_width,
                self.kind_label.sizeHint().width() + layout_h_margins,
            )

        # 2. Determine actual width. Keep a modest minimum text column so short
        # words remain readable without turning tiny messages into large boxes.
        actual_width = max(natural_width, min_bubble_width)
        actual_width = min(actual_width, max_bubble_width)
        actual_width = max(actual_width, 50)

        # 3. Apply width constraint
        self.bubble_frame.setFixedWidth(int(actual_width))
        text_width = max(actual_width - layout_h_margins - 6, 1)
        doc.setTextWidth(text_width)

        # 4. Calculate Height based on wrapped text
        # Use documentLayout for precise height calculation
        desc_height = 20.0
        doc_layout = doc.documentLayout()
        if doc_layout:
            desc_height = doc_layout.documentSize().height()

        # Enforce minimum height
        desc_height = max(desc_height, 20)
        text_height = ceil(desc_height) + 8
        semantic_header_height = 0
        if self.kind_label is not None and not self.kind_label.isHidden():
            semantic_header_height = self.kind_label.sizeHint().height() + 5
        final_height = text_height + layout_v_margins + semantic_header_height + 4

        # 5. Apply Height
        self.text_edit.setFixedHeight(text_height)
        self.bubble_frame.setFixedHeight(final_height)
        self.setFixedHeight(final_height)

    def set_text(self, text: str):
        """Update the displayed text content.

        Args:
            text: New Markdown text to render in the bubble.

        """
        self._raw_text = text
        self.text_edit.setMarkdown(text)
        if self.isVisible():
            self._reflow_timer.start(0)

    def _reflow_after_text_change(self) -> None:
        """Resize a live bubble after streamed Markdown changes its height."""
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjust_width(parent.width())
        self.updateGeometry()

    def get_text(self) -> str:
        """Get the original raw text content.

        Returns:
            The unmodified text string stored in this bubble.

        """
        return self._raw_text

    def showEvent(self, event):  # noqa: N802
        """Ensure correct layout when the widget is first shown.

        Args:
            event: The QShowEvent.

        """
        super().showEvent(event)
        parent = self.parentWidget()
        if parent is not None:
            self.adjust_width(parent.width())

    def setText(self, text):  # noqa: N802
        """Compatibility alias for ``set_text``.

        Args:
            text: The text to set.

        """
        self.set_text(text)
