from math import ceil
from unittest.mock import patch

from PyQt6.QtCore import Qt, QUrl

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

    def test_link_handling(self, qtbot):
        bubble = MessageBubble("[Link](https://example.com)", is_user=False)
        qtbot.addWidget(bubble)

        with patch("PyQt6.QtGui.QDesktopServices.openUrl") as mock_open:
            url = QUrl("https://example.com")
            bubble._on_link_clicked(url)
            mock_open.assert_called_with(url)

    def test_file_link_windows_opens_explorer_selection(self, qtbot):
        bubble = MessageBubble("[File](file:///C:/test.txt)", is_user=False)
        qtbot.addWidget(bubble)

        with (
            patch(
                "XBrainLab.ui.chat.message_bubble.platform.system",
                return_value="Windows",
            ),
            patch("XBrainLab.ui.chat.message_bubble.subprocess.Popen") as mock_popen,
            patch(
                "XBrainLab.ui.chat.message_bubble.QDesktopServices.openUrl"
            ) as mock_open_url,
        ):
            url = QUrl("file:///C:/test.txt")
            bubble._on_link_clicked(url)

        mock_popen.assert_called_once_with(["explorer", "/select,", "/C:/test.txt"])
        mock_open_url.assert_not_called()

    def test_file_link_non_windows_uses_desktop_services(self, qtbot):
        bubble = MessageBubble("[File](file:///tmp/test.txt)", is_user=False)
        qtbot.addWidget(bubble)

        with (
            patch(
                "XBrainLab.ui.chat.message_bubble.platform.system", return_value="Linux"
            ),
            patch("XBrainLab.ui.chat.message_bubble.subprocess.Popen") as mock_popen,
            patch(
                "XBrainLab.ui.chat.message_bubble.QDesktopServices.openUrl"
            ) as mock_open_url,
        ):
            url = QUrl("file:///tmp/test.txt")
            bubble._on_link_clicked(url)

        mock_popen.assert_not_called()
        mock_open_url.assert_called_once_with(url)

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
        assert bubble_frame.maximumWidth() == 880  # 88% of 1000

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
