from math import ceil
from unittest.mock import patch

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QEvent, Qt, QUrl
from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication, QMessageBox, QStyle, QVBoxLayout, QWidget

from XBrainLab.ui.chat.message_bubble import MessageBubble, MessagePresentationKind
from XBrainLab.ui.styles.theme import Theme


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
        assert text_edit.palette().color(QPalette.ColorRole.Link) == QColor(
            Theme.CHART_PRIMARY
        )

    def test_adjust_width(self, qtbot):
        bubble = MessageBubble("Long text " * 10, is_user=False)
        qtbot.addWidget(bubble)

        container_width = 500
        bubble.adjust_width(container_width)

        bubble_frame = bubble.bubble_frame
        text_edit = bubble.text_edit
        assert bubble_frame is not None
        assert text_edit is not None

        # Product bubbles stay below 85% of the transcript viewport.
        assert bubble_frame.maximumWidth() == 420
        # Text width should be set
        document = text_edit.document()
        assert document is not None
        assert document.textWidth() == 384  # 420 - margins - guard

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
        assert bubble_frame.maximumWidth() == 420  # 84% of 500

        # Resize Larger: 1000
        bubble.adjust_width(1000)
        assert bubble_frame.maximumWidth() == 720

        # Resize Smaller: 200
        bubble.adjust_width(200)
        assert bubble_frame.maximumWidth() == 168  # 84% of 200

    def test_resize_reflows_existing_mixed_content_without_rebuild(
        self,
        qtbot,
    ) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        text = (
            "EEG metadata review includes English and 中文內容.\n\n"
            "- Verify the channel names.\n"
            "- 確認事件標記與資料一致。\n\n"
            "/mnt/d/workspace_v2/projects/lab/xbrainlab/"
            + ("unbroken-segment" * 18)
            + "\n\nhttps://example.com/"
            + ("resource" * 28)
        )
        bubble = MessageBubble(text, is_user=False)
        layout.addWidget(bubble)
        qtbot.addWidget(container)
        layout_changes: list[None] = []
        bubble.layout_changed.connect(lambda: layout_changes.append(None))
        container.resize(760, 900)
        container.show()
        qtbot.wait(20)
        layout_changes.clear()

        text_views = tuple(bubble.content_view.text_views)
        heights: dict[int, int] = {}
        for width in (760, 420, 320, 420, 760):
            container.resize(width, 900)
            bubble.adjust_width(width)
            qtbot.wait(20)
            heights.setdefault(width, bubble.height())

            assert container.width() == width
            assert bubble.bubble_frame.width() <= ceil(width * 0.84)
            assert tuple(bubble.content_view.text_views) == text_views
            for view in bubble.content_view.text_views:
                document = view.document()
                layout = document.documentLayout() if document is not None else None
                assert layout is not None
                assert view.horizontalScrollBar().maximum() == 0
                assert view.height() >= ceil(layout.documentSize().height()) + 8

        assert heights[320] > heights[420] > heights[760]
        assert layout_changes == []

    @pytest.mark.parametrize("width", [320, 420, 760])
    @pytest.mark.parametrize(
        ("kind", "expected_label"),
        [
            (MessagePresentationKind.CLARIFICATION, "Needs input"),
            (MessagePresentationKind.ATTENTION, "Needs attention"),
            (MessagePresentationKind.ERROR, "Error"),
        ],
    )
    def test_semantic_message_content_fits_requested_widths(
        self,
        qtbot,
        width,
        kind,
        expected_label,
    ) -> None:
        bubble = MessageBubble(
            "Review the proposed EEG setting.\n\n- 目前值: 32\n- Proposed value: 16",
            is_user=False,
            presentation_kind=kind,
        )
        qtbot.addWidget(bubble)

        bubble.adjust_width(width)

        assert bubble.presentation_kind is kind
        assert bubble.kind_label.text() == expected_label
        assert not bubble.kind_label.isHidden()
        assert bubble.bubble_frame.width() <= ceil(width * 0.84)
        assert bubble.kind_label.width() >= bubble.kind_label.sizeHint().width()
        document = bubble.text_edit.document()
        layout = document.documentLayout() if document is not None else None
        assert layout is not None
        assert bubble.text_edit.horizontalScrollBar().maximum() == 0
        assert bubble.text_edit.height() >= ceil(layout.documentSize().height()) + 8

    def test_resize_contains_code_and_reuses_rendered_widgets(
        self,
        qtbot,
    ) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        bubble = MessageBubble(
            "Before code.\n\n```python\npath = '"
            + ("/unbroken/path" * 30)
            + "'\n```\n\n完成後繼續檢查 metadata。",
            is_user=False,
        )
        layout.addWidget(bubble)
        qtbot.addWidget(container)
        container.resize(760, 700)
        container.show()
        qtbot.wait(20)

        text_views = tuple(bubble.content_view.text_views)
        code_block = bubble.code_blocks[0]
        for width in (760, 420, 320, 420, 760):
            container.resize(width, 700)
            bubble.adjust_width(width)
            qtbot.wait(20)

            assert container.width() == width
            assert tuple(bubble.content_view.text_views) == text_views
            assert bubble.code_blocks[0] is code_block
            assert bubble.bubble_frame.width() <= ceil(width * 0.84)
            assert code_block.width() <= bubble.content_view.width()
            assert code_block.horizontalScrollBar().maximum() > 0
            assert all(view.horizontalScrollBar().maximum() == 0 for view in text_views)

    def test_long_code_line_scrolls_inside_code_block_without_widening_bubble(
        self,
        qtbot,
    ) -> None:
        container = QWidget()
        container.resize(320, 420)
        layout = QVBoxLayout(container)
        bubble = MessageBubble(
            '```python\nvalue = "' + ("x" * 240) + '"\n```',
            is_user=False,
        )
        layout.addWidget(bubble)
        qtbot.addWidget(container)
        container.show()
        qtbot.wait(20)
        bubble.adjust_width(container.width())
        qtbot.wait(20)

        assert bubble.bubble_frame.width() <= int(container.width() * 0.84) + 1
        assert bubble.text_edit.horizontalScrollBarPolicy() == (
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        assert bubble.text_edit.horizontalScrollBar().maximum() == 0
        assert len(bubble.code_blocks) == 1
        code_block = bubble.code_blocks[0]
        assert code_block.horizontalScrollBarPolicy() == (
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        assert code_block.horizontalScrollBar().maximum() > 0
        assert code_block.toPlainText().endswith('"')

    def test_code_height_uses_scaled_scrollbar_extent_for_tabs_and_cjk(
        self,
        qtbot,
    ) -> None:
        container = QWidget()
        container.resize(320, 420)
        layout = QVBoxLayout(container)
        bubble = MessageBubble(
            "```text\nshort\n\t欄位名稱=" + ("資料" * 90) + "\nlast line\n```",
            is_user=False,
        )
        layout.addWidget(bubble)
        qtbot.addWidget(container)
        container.show()
        bubble.adjust_width(container.width())
        qtbot.wait(20)

        code_block = bubble.code_blocks[0]
        style = code_block.style()
        expected_scroll_extent = max(
            code_block.horizontalScrollBar().sizeHint().height(),
            style.pixelMetric(
                QStyle.PixelMetric.PM_ScrollBarExtent,
                None,
                code_block,
            ),
        )
        expected_content_height = (
            code_block.blockCount() * code_block.fontMetrics().lineSpacing()
        ) + 20

        assert code_block.horizontalScrollBar().maximum() > 0
        assert code_block.height() >= expected_content_height + expected_scroll_extent
        assert code_block.viewport().height() >= (
            code_block.blockCount() * code_block.fontMetrics().lineSpacing()
        )

    def test_cjk_before_tabs_uses_qt_layout_at_scroll_threshold(
        self,
        qtbot,
    ) -> None:
        bubble = MessageBubble(
            "```text\nA資料\tB資料\tC\nsecond line\n```",
            is_user=False,
        )
        qtbot.addWidget(bubble)
        bubble.show()
        qtbot.wait(20)
        code_block = bubble.code_blocks[0]

        document = code_block.document()
        block_layout = document.begin().layout()
        assert block_layout is not None
        qt_layout_width = ceil(block_layout.lineAt(0).naturalTextWidth()) + 24
        assert code_block.natural_content_width() == qt_layout_width

        style = code_block.style()
        expected_scroll_extent = max(
            code_block.horizontalScrollBar().sizeHint().height(),
            style.pixelMetric(
                QStyle.PixelMetric.PM_ScrollBarExtent,
                None,
                code_block,
            ),
        )
        content_height = (
            code_block.blockCount() * code_block.fontMetrics().lineSpacing()
        ) + 20
        threshold_width = max(qt_layout_width - 12, 1)
        code_block.fit_to_width(threshold_width)
        qtbot.wait(20)

        assert code_block.horizontalScrollBar().maximum() > 0
        assert code_block.height() >= content_height + expected_scroll_extent
        assert code_block.viewport().height() >= (
            code_block.blockCount() * code_block.fontMetrics().lineSpacing()
        )

    def test_cjk_tab_measurement_tracks_a_live_font_change(self, qtbot) -> None:
        bubble = MessageBubble(
            "```text\nA資料\tB資料\tC\nsecond line\n```",
            is_user=False,
        )
        qtbot.addWidget(bubble)
        bubble.show()
        qtbot.wait(20)
        code_block = bubble.code_blocks[0]
        enlarged = QFont(code_block.font())
        enlarged.setPointSize(max(enlarged.pointSize() + 4, 14))

        code_block.setFont(enlarged)
        qtbot.wait(20)

        block_layout = code_block.document().begin().layout()
        assert block_layout is not None
        qt_layout_width = ceil(block_layout.lineAt(0).naturalTextWidth()) + 24
        assert code_block.natural_content_width() == qt_layout_width

    def test_offscreen_cjk_tab_line_sets_scrollbar_before_user_scrolls(
        self,
        qtbot,
    ) -> None:
        short_lines = "\n".join(f"line {index}" for index in range(15))
        long_line = "資料欄位\t" + ("長路徑" * 80)
        bubble = MessageBubble(
            f"```text\n{short_lines}\n{long_line}\n```",
            is_user=False,
        )
        qtbot.addWidget(bubble)
        code_block = bubble.code_blocks[0]

        natural_width = code_block.natural_content_width()
        final_block = code_block.document().findBlockByNumber(
            code_block.blockCount() - 1,
        )
        document_layout = code_block.document().documentLayout()
        assert document_layout is not None
        document_layout.blockBoundingRect(final_block)
        final_layout = final_block.layout()
        assert final_layout is not None
        expected_width = ceil(final_layout.lineAt(0).naturalTextWidth()) + 24

        assert natural_width >= expected_width

        code_block.fit_to_width(260)
        bubble.show()
        qtbot.wait(20)

        assert code_block.verticalScrollBar().maximum() > 0
        assert code_block.horizontalScrollBar().maximum() > 0

    def test_mixed_markdown_and_code_keep_code_overflow_isolated(
        self,
        qtbot,
    ) -> None:
        bubble = MessageBubble(
            "Before code.\n\n```python\nvalue = '"
            + ("x" * 180)
            + "'\n```\n\nAfter code.",
            is_user=False,
        )
        qtbot.addWidget(bubble)
        bubble.show()
        bubble.adjust_width(320)
        qtbot.wait(20)

        assert len(bubble.content_view.text_views) == 2
        assert len(bubble.code_blocks) == 1
        assert all(
            view.horizontalScrollBar().maximum() == 0
            for view in bubble.content_view.text_views
        )
        assert bubble.code_blocks[0].horizontalScrollBar().maximum() > 0
        assert bubble.get_text().endswith("After code.")

    def test_streaming_unclosed_fence_uses_code_surface_before_completion(
        self,
        qtbot,
    ) -> None:
        bubble = MessageBubble(
            "Working...\n\n```python\nvalue = '" + ("x" * 160),
            is_user=False,
        )
        qtbot.addWidget(bubble)
        bubble.show()
        bubble.adjust_width(320)
        qtbot.wait(20)

        assert len(bubble.code_blocks) == 1
        assert bubble.code_blocks[0].horizontalScrollBar().maximum() > 0
        assert all(
            view.horizontalScrollBar().maximum() == 0
            for view in bubble.content_view.text_views
        )

    @pytest.mark.parametrize(
        "text",
        [
            "中文 EEG workflow, 包含 English、數字 123 與標點。" * 12,
            "/mnt/d/workspace_v2/projects/lab/xbrainlab/" + ("segment" * 40),
            "https://example.com/" + ("resource" * 40),
        ],
    )
    def test_mixed_and_unbroken_text_reflows_without_horizontal_overflow(
        self,
        qtbot,
        text,
    ) -> None:
        bubble = MessageBubble(text, is_user=False)
        qtbot.addWidget(bubble)

        bubble.adjust_width(460)
        wide_height = bubble.height()
        bubble.adjust_width(280)

        assert bubble.bubble_frame.width() <= int(280 * 0.84) + 1
        assert bubble.text_edit.horizontalScrollBar().maximum() == 0
        assert bubble.height() >= wide_height
        document = bubble.text_edit.document()
        assert document is not None
        layout = document.documentLayout()
        assert layout is not None
        assert bubble.text_edit.height() >= ceil(layout.documentSize().height()) + 8

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

    def test_short_two_word_message_stays_on_one_visual_line(self, qtbot) -> None:
        bubble = MessageBubble("EEG ready", is_user=False)
        qtbot.addWidget(bubble)

        bubble.adjust_width(380)

        document = bubble.text_edit.document()
        layout = document.documentLayout() if document is not None else None
        assert layout is not None
        assert layout.documentSize().height() <= (
            bubble.text_edit.fontMetrics().lineSpacing() + 3
        )

    def test_streaming_suffix_reuses_existing_code_widget_and_scroll(self, qtbot):
        initial = "Before.\n\n```python\nvalue = '" + ("x" * 220) + "'\n```"
        bubble = MessageBubble(initial, is_user=False)
        qtbot.addWidget(bubble)
        bubble.show()
        bubble.adjust_width(320)
        qtbot.wait(20)
        code_block = bubble.code_blocks[0]
        code_block.horizontalScrollBar().setValue(
            code_block.horizontalScrollBar().maximum()
        )
        scroll_value = code_block.horizontalScrollBar().value()

        bubble.set_text(initial + "\n\nAfter code.")
        qtbot.wait(20)

        assert bubble.code_blocks[0] is code_block
        assert code_block.horizontalScrollBar().value() == scroll_value
        assert len(bubble.content_view.text_views) == 2

    def test_streaming_unclosed_code_preserves_reader_scroll_position(self, qtbot):
        initial = "```python\n" + "\n".join(
            f"row_{index} = '{'x' * 220}'" for index in range(20)
        )
        bubble = MessageBubble(initial, is_user=False)
        qtbot.addWidget(bubble)
        bubble.show()
        bubble.adjust_width(320)
        qtbot.wait(20)
        code_block = bubble.code_blocks[0]
        horizontal = code_block.horizontalScrollBar()
        vertical = code_block.verticalScrollBar()
        horizontal.setValue(max(horizontal.maximum() // 2, 1))
        vertical.setValue(max(vertical.maximum() // 2, 1))
        old_horizontal = horizontal.value()
        old_vertical = vertical.value()

        bubble.set_text(initial + "\nnext_row = '" + ("y" * 240) + "'")
        qtbot.wait(20)

        assert bubble.code_blocks[0] is code_block
        assert horizontal.value() == old_horizontal
        assert vertical.value() == old_vertical

    def test_streaming_structure_change_releases_removed_code_widget(self, qtbot):
        bubble = MessageBubble(
            "Before.\n\n```python\nprint('ready')\n```",
            is_user=False,
        )
        qtbot.addWidget(bubble)
        bubble.show()
        old_code = bubble.code_blocks[0]

        bubble.set_text("Before.\n\nNo code remains.")
        qtbot.wait(20)

        assert bubble.code_blocks == ()
        assert sip.isdeleted(old_code)

    def test_medium_natural_width_uses_integer_qt_geometry(self, qtbot) -> None:
        bubble = MessageBubble(
            "I can help review EEG files before they are loaded.",
            is_user=False,
        )
        qtbot.addWidget(bubble)

        bubble.adjust_width(420)

        assert isinstance(bubble.bubble_frame.width(), int)
        assert bubble.bubble_frame.width() <= int(420 * 0.84) + 1

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
