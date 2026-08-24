"""Message Bubble Widget for Chat Panel.

Provides the ``MessageBubble`` widget that renders a single chat message
with dynamic width adjustment, link handling, and sender-based styling.
"""

import re
from dataclasses import dataclass
from math import ceil

from PyQt6.QtCore import QEvent, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QPalette, QTextOption
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QSizePolicy,
    QStyle,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.controller.chat_controller import (
    ChatMessagePresentationKind,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.styles.theme import Theme

from .styles import (
    AGENT_BUBBLE_FRAME_STYLE,
    AGENT_BUBBLE_TEXT_STYLE,
    ATTENTION_BUBBLE_FRAME_STYLE,
    CANCELLED_BUBBLE_FRAME_STYLE,
    CLARIFICATION_BUBBLE_FRAME_STYLE,
    CODE_BLOCK_STYLE,
    ERROR_BUBBLE_FRAME_STYLE,
    MESSAGE_DOCUMENT_STYLE,
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


_FENCED_CODE_PATTERN = re.compile(
    r"```(?P<language>[^\n`]*)\n(?P<code>.*?)```",
    re.DOTALL,
)
_UNCLOSED_FENCED_CODE_PATTERN = re.compile(
    r"```(?P<language>[^\n`]*)\n(?P<code>.*)\Z",
    re.DOTALL,
)


@dataclass(frozen=True, slots=True)
class _MessageContentBlock:
    """One renderable Markdown or fenced-code block."""

    kind: str
    text: str
    language: str = ""


def _parse_message_content(text: str) -> tuple[_MessageContentBlock, ...]:
    """Split fenced code from Markdown without changing the persisted text."""
    blocks: list[_MessageContentBlock] = []
    cursor = 0
    for match in _FENCED_CODE_PATTERN.finditer(text):
        markdown = text[cursor : match.start()]
        if markdown:
            blocks.append(_MessageContentBlock("markdown", markdown))
        code = match.group("code")
        if code.endswith("\n"):
            code = code[:-1]
        blocks.append(
            _MessageContentBlock(
                "code",
                code,
                match.group("language").strip(),
            )
        )
        cursor = match.end()
    remainder = text[cursor:]
    unclosed = _UNCLOSED_FENCED_CODE_PATTERN.search(remainder)
    if unclosed is not None:
        markdown = remainder[: unclosed.start()]
        if markdown:
            blocks.append(_MessageContentBlock("markdown", markdown))
        blocks.append(
            _MessageContentBlock(
                "code",
                unclosed.group("code"),
                unclosed.group("language").strip(),
            )
        )
    elif remainder or not blocks:
        blocks.append(_MessageContentBlock("markdown", remainder))
    return tuple(blocks)


class _CodeBlockView(QPlainTextEdit):
    """Read-only code surface whose overflow stays inside the code block."""

    _MAX_VISIBLE_LINES = 12

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("AssistantCodeBlock")
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(CODE_BLOCK_STYLE)
        self._sync_tab_stop_distance()
        self.setPlainText(text)

    def _sync_tab_stop_distance(self) -> None:
        """Keep tab rendering deterministic across fonts and display scales."""
        target = float(self.fontMetrics().horizontalAdvance(" ") * 4)
        if abs(self.tabStopDistance() - target) >= 0.5:
            self.setTabStopDistance(target)

    def event(self, event) -> bool:
        """Synchronize tab geometry after Qt applies a font or style change."""
        handled = super().event(event)
        if event is not None and event.type() in {
            QEvent.Type.FontChange,
            QEvent.Type.ApplicationFontChange,
            QEvent.Type.StyleChange,
        }:
            self._sync_tab_stop_distance()
        return handled

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._sync_tab_stop_distance()

    def natural_content_width(self) -> int:
        """Return the unwrapped code width including internal padding."""
        self._sync_tab_stop_distance()
        document = self.document()
        if document is None:
            return 24
        rendered_widths: list[float] = []
        document_layout = document.documentLayout()
        block = document.begin()
        while block.isValid():
            if document_layout is not None:
                document_layout.blockBoundingRect(block)
            block_layout = block.layout()
            if block_layout is not None:
                rendered_widths.extend(
                    block_layout.lineAt(index).naturalTextWidth()
                    for index in range(block_layout.lineCount())
                )
            block = block.next()
        return ceil(max(rendered_widths, default=0.0)) + 24

    def fit_to_width(self, width: int) -> int:
        """Fit the viewport width and return a stable, content-derived height."""
        self.setFixedWidth(max(width, 1))
        line_count = max(self.blockCount(), 1)
        visible_lines = min(line_count, self._MAX_VISIBLE_LINES)
        content_height = (visible_lines * self.fontMetrics().lineSpacing()) + 20
        needs_horizontal_scroll = self.natural_content_width() > max(width - 18, 1)
        style = self.style()
        horizontal_extent = 0
        if needs_horizontal_scroll:
            horizontal_scrollbar = self.horizontalScrollBar()
            horizontal_extent = max(
                (
                    horizontal_scrollbar.sizeHint().height()
                    if horizontal_scrollbar is not None
                    else 0
                ),
                (
                    style.pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent, None, self)
                    if style is not None
                    else 0
                ),
            )
        target_height = content_height + horizontal_extent
        self.setFixedHeight(target_height)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if line_count > self._MAX_VISIBLE_LINES
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        return target_height

    def set_streaming_text(self, text: str) -> None:
        """Update code without discarding an active reader's scroll position."""
        horizontal = self.horizontalScrollBar()
        vertical = self.verticalScrollBar()
        if horizontal is None or vertical is None:
            self.setPlainText(text)
            return
        horizontal_value = horizontal.value()
        vertical_value = vertical.value()
        horizontal_follow_tail = (
            horizontal.maximum() > 0 and horizontal_value >= horizontal.maximum() - 1
        )
        vertical_follow_tail = (
            vertical.maximum() > 0 and vertical_value >= vertical.maximum() - 1
        )

        self.setPlainText(text)

        horizontal.setValue(
            horizontal.maximum()
            if horizontal_follow_tail
            else min(horizontal_value, horizontal.maximum())
        )
        vertical.setValue(
            vertical.maximum()
            if vertical_follow_tail
            else min(vertical_value, vertical.maximum())
        )


class _MessageContentView(QWidget):
    """Composite renderer that isolates code overflow from normal prose."""

    def __init__(self, text: str, link_handler, parent=None) -> None:
        super().__init__(parent)
        self._link_handler = link_handler
        self._prose_vertical_margin = 0
        self._blocks: tuple[_MessageContentBlock, ...] = ()
        self.text_views: list[QTextBrowser] = []
        self.code_blocks: list[_CodeBlockView] = []
        self._views: list[QWidget] = []
        self._text_style = ""
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._compat_text_view = self._new_text_view()
        self._compat_text_view.hide()
        self.set_content(text)

    @property
    def primary_text_view(self) -> QTextBrowser:
        """Expose a compatibility text view for callers inspecting plain text."""
        return self.text_views[0] if self.text_views else self._compat_text_view

    def set_text_style(self, style: str) -> None:
        self._text_style = style
        self._compat_text_view.setStyleSheet(style)
        for view in self.text_views:
            view.setStyleSheet(style)
            self._sync_text_view_font(view)

    def set_prose_vertical_margin(self, margin: int) -> None:
        """Center prose inside its clipping guard without changing its height."""
        margin = max(int(margin), 0)
        if margin == self._prose_vertical_margin:
            return
        self._prose_vertical_margin = margin
        for view in (self._compat_text_view, *self.text_views):
            view.setViewportMargins(0, margin, 0, margin)

    def set_content(self, text: str) -> None:
        """Update existing segments when possible to keep streaming stable."""
        blocks = _parse_message_content(text)
        if self._same_structure(blocks):
            text_index = 0
            code_index = 0
            for block in blocks:
                if block.kind == "markdown":
                    self.text_views[text_index].setMarkdown(block.text)
                    text_index += 1
                else:
                    self.code_blocks[code_index].set_streaming_text(block.text)
                    code_index += 1
            self._blocks = blocks
            self._compat_text_view.setMarkdown(text)
            return
        self._rebuild(blocks, text)

    def natural_content_width(self) -> float:
        widths: list[float] = []
        for view in self.text_views:
            document = view.document()
            if document is None:
                continue
            document.setTextWidth(-1)
            widths.append(document.idealWidth())
        widths.extend(block.natural_content_width() for block in self.code_blocks)
        return max(widths or [1.0])

    def fit_to_width(self, width: int) -> int:
        """Fit every child and return the exact composite content height."""
        width = max(width, 1)
        self.setFixedWidth(width)
        heights: list[int] = []
        for view in self.text_views:
            view.ensurePolished()
            view.setFixedWidth(width)
            document = view.document()
            if document is None:
                height = 20
            else:
                self._sync_text_view_font(view)
                viewport = view.viewport()
                text_width = max(
                    viewport.width() if viewport is not None else width,
                    1,
                )
                document.setTextWidth(text_width)
                layout = document.documentLayout()
                height = (
                    ceil(layout.documentSize().height()) + 8
                    if layout is not None
                    else 20
                )
            view.setFixedHeight(max(height, 20))
            heights.append(max(height, 20))
        heights.extend(block.fit_to_width(width) for block in self.code_blocks)
        visible_count = len(heights)
        total_height = sum(heights)
        if visible_count > 1:
            total_height += self._layout.spacing() * (visible_count - 1)
        self.setFixedHeight(max(total_height, 20))
        return max(total_height, 20)

    def _same_structure(self, blocks: tuple[_MessageContentBlock, ...]) -> bool:
        return len(blocks) == len(self._blocks) and all(
            new.kind == old.kind and new.language == old.language
            for new, old in zip(blocks, self._blocks, strict=True)
        )

    def _rebuild(
        self,
        blocks: tuple[_MessageContentBlock, ...],
        raw_text: str,
    ) -> None:
        common_prefix = 0
        for old, new in zip(self._blocks, blocks, strict=False):
            if old.kind != new.kind or old.language != new.language:
                break
            common_prefix += 1

        retained_views = self._views[:common_prefix]
        for index, block in enumerate(blocks[:common_prefix]):
            if block.text == self._blocks[index].text:
                continue
            view = retained_views[index]
            if isinstance(view, QTextBrowser):
                view.setMarkdown(block.text)
            elif isinstance(view, _CodeBlockView):
                view.set_streaming_text(block.text)

        while self._layout.count() > common_prefix:
            item = self._layout.takeAt(common_prefix)
            if item is None:
                break
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self._views = retained_views
        for block in blocks[common_prefix:]:
            if block.kind == "code":
                view: QWidget = _CodeBlockView(block.text, self)
            else:
                text_view = self._new_text_view()
                text_view.setMarkdown(block.text)
                if self._text_style:
                    text_view.setStyleSheet(self._text_style)
                    self._sync_text_view_font(text_view)
                view = text_view
            self._views.append(view)
            self._layout.addWidget(view)
        self.text_views = [
            view for view in self._views if isinstance(view, QTextBrowser)
        ]
        self.code_blocks = [
            view for view in self._views if isinstance(view, _CodeBlockView)
        ]
        self._blocks = blocks
        self._compat_text_view.setMarkdown(raw_text)

    def _new_text_view(self) -> QTextBrowser:
        view = QTextBrowser(self)
        view.setReadOnly(True)
        view.setFrameStyle(QFrame.Shape.NoFrame)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        view.setOpenExternalLinks(False)
        view.anchorClicked.connect(self._link_handler)
        palette = view.palette()
        palette.setColor(QPalette.ColorRole.Link, QColor(Theme.CHART_PRIMARY))
        palette.setColor(QPalette.ColorRole.LinkVisited, QColor(Theme.CHART_PRIMARY))
        view.setPalette(palette)
        view.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        document = view.document()
        if document is not None:
            document.setDocumentMargin(0)
            document.setDefaultStyleSheet(MESSAGE_DOCUMENT_STYLE)
        view.setContentsMargins(0, 0, 0, 0)
        view.setViewportMargins(
            0,
            self._prose_vertical_margin,
            0,
            self._prose_vertical_margin,
        )
        view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return view

    @staticmethod
    def _sync_text_view_font(view: QTextBrowser) -> None:
        """Keep QTextDocument metrics aligned with the polished viewport font."""
        view.ensurePolished()
        document = view.document()
        if document is not None and document.defaultFont() != view.font():
            document.setDefaultFont(view.font())


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

    layout_changed = pyqtSignal()

    _MAX_WIDTH_RATIO = 0.84
    _MAX_WIDTH_PX = 720
    _PLAIN_PROSE_VERTICAL_MARGIN = 3

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
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.is_user = is_user
        self.bubble_frame: QFrame
        self.text_edit: QTextBrowser
        self.content_view: _MessageContentView
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

        self.content_view = _MessageContentView(text, self._on_link_clicked)
        self.text_edit = self.content_view.primary_text_view
        for view in (*self.content_view.text_views, *self.content_view.code_blocks):
            view.installEventFilter(self)
        bubble_layout.addWidget(self.content_view)

        # Apply styles based on sender
        if self.is_user:
            self.bubble_frame.setStyleSheet(USER_BUBBLE_FRAME_STYLE)
            self.content_view.set_text_style(USER_BUBBLE_TEXT_STYLE)

            row_layout.addStretch(1)
            row_layout.addWidget(self.bubble_frame)
            row_layout.setAlignment(self.bubble_frame, Qt.AlignmentFlag.AlignRight)
        else:
            self.bubble_frame.setStyleSheet(AGENT_BUBBLE_FRAME_STYLE)
            self.content_view.set_text_style(AGENT_BUBBLE_TEXT_STYLE)

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
        self.content_view.set_prose_vertical_margin(
            self._PLAIN_PROSE_VERTICAL_MARGIN
            if kind
            in {
                MessagePresentationKind.USER,
                MessagePresentationKind.ASSISTANT,
            }
            else 0
        )

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

        self.ensurePolished()
        self.bubble_frame.ensurePolished()
        self.content_view.ensurePolished()
        for view in (*self.content_view.text_views, *self.content_view.code_blocks):
            view.ensurePolished()

        max_bubble_width = min(
            int(container_width * self._MAX_WIDTH_RATIO),
            self._MAX_WIDTH_PX,
        )
        min_bubble_width = 50

        # Margins: 15+15=30 horizontal, 10+10=20 vertical
        layout_h_margins = 30
        content_width_guard = 6
        layout_v_margins = 20

        # 1. Start with infinite width to find natural width
        natural_width = (
            self.content_view.natural_content_width()
            + layout_h_margins
            + content_width_guard
        )
        if self.kind_label is not None and not self.kind_label.isHidden():
            natural_width = max(
                natural_width,
                self.kind_label.sizeHint().width() + layout_h_margins,
            )

        # 2. Determine actual width. User bubbles follow their content down to
        # the safety floor; assistant bubbles retain a modest text column.
        actual_width = max(natural_width, min_bubble_width)
        actual_width = min(actual_width, max_bubble_width)
        actual_width = ceil(max(actual_width, 50))

        # 3. Apply width constraint
        self.bubble_frame.setFixedWidth(actual_width)
        text_width = max(actual_width - layout_h_margins - content_width_guard, 1)
        text_height = self.content_view.fit_to_width(text_width)
        semantic_header_height = 0
        if self.kind_label is not None and not self.kind_label.isHidden():
            semantic_header_height = self.kind_label.sizeHint().height() + 5
        final_height = text_height + layout_v_margins + semantic_header_height

        # 5. Apply Height
        self.bubble_frame.setFixedHeight(final_height)
        self.setFixedHeight(final_height)

    def set_text(self, text: str):
        """Update the displayed text content.

        Args:
            text: New Markdown text to render in the bubble.

        """
        self._raw_text = text
        self.content_view.set_content(text)
        self.text_edit = self.content_view.primary_text_view
        for view in (*self.content_view.text_views, *self.content_view.code_blocks):
            view.installEventFilter(self)
        if self.isVisible():
            self._reflow_timer.start(0)

    def _reflow_after_text_change(self) -> None:
        """Resize a live bubble after streamed Markdown changes its height."""
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjust_width(parent.width())
        self.updateGeometry()
        self.layout_changed.emit()

    def eventFilter(self, watched, event):  # noqa: N802
        """Recalculate geometry after font, style, or DPI-related changes."""
        content_view = getattr(self, "content_view", None)
        watched_views = (
            {*content_view.text_views, *content_view.code_blocks}
            if content_view is not None
            else set()
        )
        if watched in watched_views and event.type() in {
            QEvent.Type.FontChange,
            QEvent.Type.ApplicationFontChange,
            QEvent.Type.StyleChange,
            QEvent.Type.PaletteChange,
        }:
            self._reflow_timer.start(0)
        return super().eventFilter(watched, event)

    @property
    def code_blocks(self) -> tuple[QPlainTextEdit, ...]:
        """Return independent code surfaces for UI evidence and accessibility."""
        return tuple(self.content_view.code_blocks)

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
