"""Coverage tests for ChatPanel - 59 uncovered lines."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QLineEdit, QScrollArea, QToolButton, QWidget


@pytest.fixture
def chat_panel(qtbot):
    with patch("XBrainLab.ui.chat.panel.ToolDebugMode", return_value=None):
        from XBrainLab.ui.chat.panel import ChatPanel

        panel = ChatPanel()
        qtbot.addWidget(panel)
        return panel


class TestChatPanelInit:
    def test_creates_panel(self, chat_panel):
        assert isinstance(chat_panel, QWidget)

    def test_has_input_area(self, chat_panel):
        assert isinstance(chat_panel.input_field, QLineEdit)

    def test_has_send_button(self, chat_panel):
        assert isinstance(chat_panel.send_btn, QToolButton)

    def test_has_scroll_area(self, chat_panel):
        assert isinstance(chat_panel.scroll_area, QScrollArea)

    def test_not_processing_initially(self, chat_panel):
        assert chat_panel.is_processing is False


class TestChatPanelSendMessage:
    def test_send_empty_ignored(self, chat_panel):
        chat_panel.input_field.clear()
        # Should not emit send_message
        with patch.object(chat_panel, "send_message") as mock_sig:
            mock_sig.emit = MagicMock()
            chat_panel._on_send()
            mock_sig.emit.assert_not_called()

    def test_send_text(self, chat_panel):
        chat_panel.input_field.setText("hello")
        with patch.object(chat_panel, "send_message") as mock_sig:
            mock_sig.emit = MagicMock()
            chat_panel._on_send()
            mock_sig.emit.assert_called_once_with("hello")
        assert chat_panel.input_field.text() == ""

    def test_stop_when_processing(self, chat_panel):
        chat_panel.is_processing = True
        with patch.object(chat_panel, "stop_generation") as mock_sig:
            mock_sig.emit = MagicMock()
            chat_panel._on_send()
            mock_sig.emit.assert_called_once()


class TestChatPanelCallbacks:
    def test_on_chunk_received_no_bubble(self, chat_panel):
        chat_panel.current_agent_bubble = None
        chat_panel.on_chunk_received("hello")
        assert isinstance(chat_panel.current_agent_bubble, QWidget)

    def test_on_chunk_received_with_bubble(self, chat_panel):
        chat_panel.on_chunk_received("part1")
        chat_panel.on_chunk_received("part2")
        text = chat_panel.current_agent_bubble.get_text()
        assert "part1" in text and "part2" in text

    def test_append_message_user(self, chat_panel):
        chat_panel.append_message("user", "hi there")
        # Should have added a bubble
        assert chat_panel.chat_layout.count() > 1

    def test_append_message_agent(self, chat_panel):
        chat_panel.append_message("assistant", "response")
        assert isinstance(chat_panel.current_agent_bubble, QWidget)

    def test_set_processing_state(self, chat_panel):
        chat_panel.set_processing_state(True)
        assert chat_panel.is_processing is True
        assert "■" in chat_panel.send_btn.text()
        chat_panel.set_processing_state(False)
        assert chat_panel.is_processing is False

    def test_clear_ui(self, chat_panel):
        chat_panel.append_message("user", "msg1")
        chat_panel.append_message("assistant", "msg2")
        chat_panel._clear_ui()
        assert chat_panel.current_agent_bubble is None

    def test_collapse_agent_message(self, chat_panel):
        chat_panel.on_chunk_received("Tool call: xyz\nResult text")
        chat_panel.collapse_agent_message("Tool call: xyz\n")
        text = chat_panel.current_agent_bubble.get_text()
        assert "Tool call" not in text

    def test_collapse_empty_hides(self, chat_panel):
        chat_panel.on_chunk_received("remove me")
        chat_panel.collapse_agent_message("remove me")
        assert not chat_panel.current_agent_bubble.isVisible()

    def test_new_conversation_signal(self, chat_panel):
        with patch.object(chat_panel, "new_conversation_requested") as mock_sig:
            mock_sig.emit = MagicMock()
            chat_panel._on_new_conversation()
            mock_sig.emit.assert_called_once()

    def test_set_model(self, chat_panel):
        with patch.object(chat_panel, "model_changed") as mock_sig:
            mock_sig.emit = MagicMock()
            chat_panel._set_model("Gemini")
            assert "Gemini" in chat_panel.model_btn.text()
            mock_sig.emit.assert_called_once_with("Gemini")

    def test_set_feature(self, chat_panel):
        chat_panel._set_feature("EEG Analyst")
        assert "EEG Analyst" in chat_panel.feature_btn.text()

    def test_update_model_menu_disables_unready_local_mode(self, qtbot):
        config = MagicMock()
        config.local_model_enabled = True
        config.local_backend_ready.return_value = False
        config.local_backend_status_message.return_value = "Missing accelerate"
        config.gemini_enabled = False
        config.active_mode = "local"

        with (
            patch("XBrainLab.ui.chat.panel.ToolDebugMode", return_value=None),
            patch(
                "XBrainLab.ui.chat.panel.LLMConfig.load_from_file",
                return_value=config,
            ),
        ):
            from XBrainLab.ui.chat.panel import ChatPanel

            panel = ChatPanel()
            qtbot.addWidget(panel)

        local_action = next(
            action for action in panel.model_menu.actions() if "Local" in action.text()
        )
        assert local_action.isEnabled() is False
        assert "Unavailable" in local_action.text()

    def test_update_model_menu_hides_unverified_gemini(self, qtbot):
        config = MagicMock()
        config.local_model_enabled = True
        config.local_backend_ready.return_value = True
        config.local_backend_status_message.return_value = "Local runtime ready."
        config.gemini_enabled = False
        config.active_mode = "local"

        with (
            patch("XBrainLab.ui.chat.panel.ToolDebugMode", return_value=None),
            patch(
                "XBrainLab.ui.chat.panel.LLMConfig.load_from_file",
                return_value=config,
            ),
        ):
            from XBrainLab.ui.chat.panel import ChatPanel

            panel = ChatPanel()
            qtbot.addWidget(panel)

        assert all(
            "Gemini" not in action.text() for action in panel.model_menu.actions()
        )
        assert panel.model_btn.text() == "Model: Local ▼"

    def test_update_model_menu_demotes_verified_gemini(self, qtbot):
        config = MagicMock()
        config.local_model_enabled = True
        config.local_backend_ready.return_value = True
        config.local_backend_status_message.return_value = "Local runtime ready."
        config.gemini_enabled = True
        config.active_mode = "gemini"

        with (
            patch("XBrainLab.ui.chat.panel.ToolDebugMode", return_value=None),
            patch(
                "XBrainLab.ui.chat.panel.LLMConfig.load_from_file",
                return_value=config,
            ),
        ):
            from XBrainLab.ui.chat.panel import ChatPanel

            panel = ChatPanel()
            qtbot.addWidget(panel)

        gemini_action = next(
            action for action in panel.model_menu.actions() if "Gemini" in action.text()
        )
        assert "Remote" in gemini_action.text()
        assert panel.model_btn.text() == "Model: Gemini (Remote) ▼"
