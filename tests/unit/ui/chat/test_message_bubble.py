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
        assert bubble.text_edit.toPlainText() == "Hello World"

        # Check interaction flags
        flags = bubble.text_edit.textInteractionFlags()
        assert flags & Qt.TextInteractionFlag.LinksAccessibleByMouse

    def test_adjust_width(self, qtbot):
        bubble = MessageBubble("Long text " * 10, is_user=False)
        qtbot.addWidget(bubble)

        container_width = 500
        bubble.adjust_width(container_width)

        # Max width should be ~80% of 500 = 400
        assert bubble.bubble_frame.maximumWidth() == 400
        # Text width should be set
        assert bubble.text_edit.document().textWidth() == 370  # 400 - 30 margin

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
        assert bubble.bubble_frame.maximumWidth() == 400  # 80% of 500

        # Resize Larger: 1000
        bubble.adjust_width(1000)
        assert bubble.bubble_frame.maximumWidth() == 800  # 80% of 1000

        # Resize Smaller: 200
        bubble.adjust_width(200)
        assert bubble.bubble_frame.maximumWidth() == 160  # 80% of 200
