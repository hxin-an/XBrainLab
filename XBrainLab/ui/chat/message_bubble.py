"""Message Bubble Widget for Chat Panel.

Provides the ``MessageBubble`` widget that renders a single chat message
with dynamic width adjustment, link handling, and sender-based styling.
"""

import platform
import subprocess

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QTextOption
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.utils.logger import logger

from .styles import (
    AGENT_BUBBLE_FRAME_STYLE,
    AGENT_BUBBLE_TEXT_STYLE,
    USER_BUBBLE_FRAME_STYLE,
    USER_BUBBLE_TEXT_STYLE,
)


class MessageBubble(QWidget):
    """A chat message bubble widget.

    Contains a ``QFrame`` bubble container with a ``QTextBrowser`` for
    rich text display. Supports dynamic width adjustment on window resize,
    Markdown rendering, and clickable links (including local ``file://`` URLs).

    Attributes:
        is_user: Whether this bubble represents a user message.
        bubble_frame: The styled QFrame container for the bubble.
        text_edit: The QTextBrowser displaying the message content.
    """

    def __init__(self, text: str, is_user: bool, parent=None):
        """Initialize the message bubble.

        Args:
            text: The message text content (Markdown supported).
            is_user: Whether this is a user message (affects alignment
                and styling).
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.is_user = is_user
        self.bubble_frame: QFrame | None = None
        self.text_edit: QTextBrowser | None = None
        self._raw_text = text  # Store raw text to preserve fidelity

        self._init_ui(text)

    def _init_ui(self, text: str):
        """Build the bubble layout and apply sender-based styling.

        Args:
            text: The initial text content to display.
        """
        # Main horizontal layout for this row
        row_layout = QHBoxLayout(self)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)

        # Create the bubble frame
        self.bubble_frame = QFrame()
        self.bubble_frame.setObjectName("BubbleFrame")
        self.bubble_frame.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )

        # Create bubble's internal layout
        bubble_layout = QVBoxLayout(self.bubble_frame)
        bubble_layout.setContentsMargins(15, 10, 15, 10)
        bubble_layout.setSpacing(0)

        # Create the text edit (ReadOnly)
        self.text_edit = QTextBrowser()
        self.text_edit.setMarkdown(text)
        self.text_edit.setReadOnly(True)
        self.text_edit.setFrameStyle(QFrame.Shape.NoFrame)
        self.text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_edit.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        # Interaction Flags: Enable selection AND links
        self.text_edit.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self.text_edit.setOpenExternalLinks(
            False
        )  # We handle links manually for file:// support
        self.text_edit.anchorClicked.connect(self._on_link_clicked)

        if self.text_edit:
            # Use WordWrap to break at word boundaries, not in the middle of words
            self.text_edit.setWordWrapMode(QTextOption.WrapMode.WordWrap)
            doc = self.text_edit.document()
            if doc:
                doc.setDocumentMargin(0)  # Remove internal document margin
            self.text_edit.setContentsMargins(0, 0, 0, 0)

        # Transparent background
        self.text_edit.setStyleSheet(
            "background: transparent; padding: 0px; margin: 0px; border: none;"
        )

        bubble_layout.addWidget(self.text_edit)

        # Apply styles based on sender
        if self.is_user:
            self.bubble_frame.setStyleSheet(USER_BUBBLE_FRAME_STYLE)
            self.text_edit.setStyleSheet(USER_BUBBLE_TEXT_STYLE)

            row_layout.addWidget(self.bubble_frame)
            row_layout.setAlignment(self.bubble_frame, Qt.AlignmentFlag.AlignRight)
        else:
            self.bubble_frame.setStyleSheet(AGENT_BUBBLE_FRAME_STYLE)
            self.text_edit.setStyleSheet(AGENT_BUBBLE_TEXT_STYLE)

            row_layout.addWidget(self.bubble_frame)
            row_layout.setAlignment(self.bubble_frame, Qt.AlignmentFlag.AlignLeft)

    def _on_link_clicked(self, url: QUrl):
        """Handle link clicks, supporting local file URLs.

        On Windows, opens Explorer with the file selected for ``file://``
        URLs. For other schemes, delegates to ``QDesktopServices``.

        Args:
            url: The clicked URL.
        """
        scheme = url.scheme()
        if scheme == "file":
            local_path = url.toLocalFile()
            if platform.system() == "Windows":
                # Open explorer with file selected
                try:
                    subprocess.Popen(  # noqa: S603
                        ["explorer", "/select,", local_path],  # noqa: S607
                    )
                except Exception:
                    logger.exception("Failed to open explorer for %s", local_path)
                    # Fallback to standard open
                    QDesktopServices.openUrl(url)
            else:
                QDesktopServices.openUrl(url)
        else:
            QDesktopServices.openUrl(url)

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

        max_bubble_width = int(container_width * 0.80)

        # Margins: 15+15=30 horizontal, 10+10=20 vertical
        layout_h_margins = 30
        layout_v_margins = 20

        if self.text_edit is None or self.bubble_frame is None:
            return

        doc = self.text_edit.document()
        if not doc:
            return

        # 1. Start with infinite width to find natural width
        doc.setTextWidth(-1)
        natural_width = doc.idealWidth() + layout_h_margins

        # 2. Determine actual width: min(natural, max_allowed)
        actual_width = min(natural_width, max_bubble_width)
        # Ensure a minimum reasonable width (e.g. 50px)
        actual_width = max(actual_width, 50)

        # 3. Apply width constraint
        self.bubble_frame.setFixedWidth(int(actual_width))
        doc.setTextWidth(actual_width - layout_h_margins)

        # 4. Calculate Height based on wrapped text
        # Use documentLayout for precise height calculation
        desc_height = 20.0
        doc_layout = doc.documentLayout()
        if doc_layout:
            desc_height = doc_layout.documentSize().height()

        # Enforce minimum height
        desc_height = max(desc_height, 20)
        final_height = int(desc_height) + layout_v_margins

        # 5. Apply Height
        if self.text_edit:
            self.text_edit.setFixedHeight(int(desc_height))
        self.bubble_frame.setFixedHeight(final_height)
        self.setFixedHeight(final_height)

    def set_text(self, text: str):
        """Update the displayed text content.

        Args:
            text: New Markdown text to render in the bubble.
        """
        self._raw_text = text
        if self.text_edit:
            self.text_edit.setMarkdown(text)

            # Re-adjust if visible
            if self.isVisible() and self.parent():
                # Trigger re-layout if width allows
                pass

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
        parent = self.parent()
        if parent and hasattr(parent, "width"):
            self.adjust_width(parent.width())

    def setText(self, text):  # noqa: N802
        """Compatibility alias for ``set_text``.

        Args:
            text: The text to set.
        """
        self.set_text(text)
