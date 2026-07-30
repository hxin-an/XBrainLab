from math import ceil
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QEvent, Qt, QUrl
from PyQt6.QtWidgets import QApplication, QMessageBox, QVBoxLayout, QWidget

from XBrainLab.ui.chat.message_bubble import MessageBubble


class TestMessageBubble:
    def test_initialization(self, qtbot):
        text = "Hello **World**"
        bubble = MessageBubble(text, is_user=True)
        qtbot.addWidget(bubble)

        # Check raw text
        assert bubble.get_text() == text
        # Check rendered markdown (rough check)
        text_edit = bubble.text_edit
        assert text_edit is not None
        assert text_edit.toPlainText() == "Hello World"

        # Check interaction flags
        flags = text_edit.textInteractionFlags()
        assert flags & Qt.TextInteractionFlag.LinksAccessibleByMouse
        assert flags & Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        assert flags & Qt.TextInteractionFlag.TextSelectableByKeyboard

    def test_adjust_width(self, qtbot):
        bubble = MessageBubble("Long text " * 10, is_user=False)
        qtbot.addWidget(bubble)

        container_width = 500
        bubble.adjust_width(container_width)

        bubble_frame = bubble.bubble_frame
        text_edit = bubble.text_edit
        assert bubble_frame is not None
        assert text_edit is not None

        # Max width should be ~88% of 500 = 440
        assert bubble_frame.maximumWidth() == 440
        # Text width should be set
        document = text_edit.document()
        assert document is not None
        assert document.textWidth() == 404  # 440 - margins - guard

    def test_https_link_opens_after_host_confirmation(self, qtbot):
        bubble = MessageBubble("[Link](https://example.com)", is_user=False)
        qtbot.addWidget(bubble)

        with (
            patch(
                "XBrainLab.ui.chat.message_bubble.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ) as mock_question,
            patch(
                "XBrainLab.ui.chat.message_bubble.QDesktopServices.openUrl"
            ) as mock_open,
        ):
            url = QUrl("https://example.com")
            bubble._on_link_clicked(url)

        assert "example.com" in mock_question.call_args.args[2]
        mock_open.assert_called_once_with(url)

    def test_https_link_does_not_open_when_confirmation_is_declined(self, qtbot):
        bubble = MessageBubble("[Link](https://example.com)", is_user=False)
        qtbot.addWidget(bubble)
        with (
            patch(
                "XBrainLab.ui.chat.message_bubble.QMessageBox.question",
                return_value=QMessageBox.StandardButton.No,
            ) as mock_question,
            patch(
                "XBrainLab.ui.chat.message_bubble.QDesktopServices.openUrl"
            ) as mock_open_url,
        ):
            url = QUrl("https://example.com/private")
            bubble._on_link_clicked(url)

        mock_question.assert_called_once()
        mock_open_url.assert_not_called()

    @pytest.mark.parametrize(
        "target",
        [
            "file:///tmp/private.edf",
            "data:text/html,<script>alert(1)</script>",
            "javascript:alert(1)",
            "http://example.com",
            "ftp://example.com/file",
            "custom://action",
            "/relative/path",
        ],
    )
    def test_untrusted_link_schemes_are_rejected(self, qtbot, target):
        bubble = MessageBubble(f"[Link]({target})", is_user=False)
        qtbot.addWidget(bubble)

        with (
            patch(
                "XBrainLab.ui.chat.message_bubble.QMessageBox.question"
            ) as mock_question,
            patch(
                "XBrainLab.ui.chat.message_bubble.QDesktopServices.openUrl"
            ) as mock_open_url,
        ):
            bubble._on_link_clicked(QUrl(target))

        mock_question.assert_not_called()
        mock_open_url.assert_not_called()

    def test_dynamic_resizing(self, qtbot):
        """Verify bubble adapts when container width changes (simulating resize)."""
        bubble = MessageBubble("Long text " * 20, is_user=False)
        qtbot.addWidget(bubble)

        # Initial Width: 500
        bubble.adjust_width(500)
        bubble_frame = bubble.bubble_frame
        assert bubble_frame is not None
        assert bubble_frame.maximumWidth() == 440  # 88% of 500

        # Resize Larger: 1000
        bubble.adjust_width(1000)
        assert bubble_frame.maximumWidth() == 720

        # Resize Smaller: 200
        bubble.adjust_width(200)
        assert bubble_frame.maximumWidth() == 176  # 88% of 200

    def test_short_user_message_has_minimum_text_column(self, qtbot):
        bubble = MessageBubble("hello", is_user=True)
        qtbot.addWidget(bubble)

        bubble.adjust_width(380)

        bubble_frame = bubble.bubble_frame
        text_edit = bubble.text_edit
        assert bubble_frame is not None
        assert text_edit is not None

        assert 72 <= bubble_frame.width() <= 110
        document = text_edit.document()
        assert document is not None
        assert document.textWidth() >= 48

    def test_short_assistant_message_does_not_use_large_minimum_width(self, qtbot):
        bubble = MessageBubble("Done.", is_user=False)
        qtbot.addWidget(bubble)

        bubble.adjust_width(380)

        bubble_frame = bubble.bubble_frame
        assert bubble_frame is not None

        assert 84 <= bubble_frame.width() <= 122

    def test_wrapped_message_keeps_descenders_visible(self, qtbot):
        bubble = MessageBubble(
            "The dataset and training settings are ready; evaluation needs "
            "a completed run.",
            is_user=False,
        )
        qtbot.addWidget(bubble)

        bubble.adjust_width(260)

        text_edit = bubble.text_edit
        assert text_edit is not None
        document = text_edit.document()
        assert document is not None
        layout = document.documentLayout()
        assert layout is not None
        assert text_edit.height() >= ceil(layout.documentSize().height()) + 8

    def test_visible_streaming_update_reflows_bubble_height(self, qtbot):
        container = QWidget()
        container.resize(280, 420)
        layout = QVBoxLayout(container)
        bubble = MessageBubble("Starting.", is_user=False)
        layout.addWidget(bubble)
        qtbot.addWidget(container)
        container.show()
        qtbot.wait(20)
        initial_height = bubble.height()

        bubble.set_text(
            "The assistant is checking the selected EEG files.\n\n"
            "- The metadata was read successfully.\n"
            "- Label alignment still needs a decision.\n"
            "- Open Match Labels to continue without losing the current import."
        )
        qtbot.wait(30)

        assert bubble.height() > initial_height
        assert bubble.text_edit is not None
        document = bubble.text_edit.document()
        assert document is not None
        assert bubble.text_edit.height() >= ceil(document.size().height()) + 8

    def test_deferred_reflow_is_owned_by_the_bubble(self, qapp):
        bubble = MessageBubble("Starting.", is_user=False)
        bubble.show()
        qapp.processEvents()

        bubble.set_text("Updated text that schedules a deferred reflow.")
        bubble.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        qapp.processEvents()
