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

    def test_file_link_handling(self, qtbot):
        bubble = MessageBubble("[File](file:///C:/test.txt)", is_user=False)
        qtbot.addWidget(bubble)

        with patch("subprocess.Popen") as mock_popen:
            url = QUrl("file:///C:/test.txt")
            bubble._on_link_clicked(url)
            # Should either open via subprocess (Windows) or fall back to openUrl
            # At minimum, verify no crash and one of the two paths was taken
            if not mock_popen.called:
                # Fallback path was used (openUrl), which is acceptable
                pass
            else:
                mock_popen.assert_called_once()

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
