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
        assert "Stop" in chat_panel.send_btn.text()
        assert chat_panel.input_field.isEnabled() is False
        chat_panel.set_processing_state(False)
        assert chat_panel.is_processing is False
        assert "Send" in chat_panel.send_btn.text()
        assert chat_panel.input_field.isEnabled() is True

    def test_clear_ui(self, chat_panel):
        chat_panel.append_message("user", "msg1")
        chat_panel.append_message("assistant", "msg2")
        chat_panel._clear_ui()
        assert chat_panel.current_agent_bubble is None
        assert chat_panel.empty_state_widget.isHidden() is False

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

    def test_retry_signal_when_idle(self, chat_panel):
        with patch.object(chat_panel, "retry_requested") as mock_sig:
            mock_sig.emit = MagicMock()
            chat_panel._on_retry()
            mock_sig.emit.assert_called_once()

    def test_retry_ignored_while_processing(self, chat_panel):
        chat_panel.set_processing_state(True)
        with patch.object(chat_panel, "retry_requested") as mock_sig:
            mock_sig.emit = MagicMock()
            chat_panel._on_retry()
            mock_sig.emit.assert_not_called()

    def test_clear_uses_new_conversation_signal(self, chat_panel):
        with patch.object(chat_panel, "new_conversation_requested") as mock_sig:
            mock_sig.emit = MagicMock()
            chat_panel._on_clear()
            mock_sig.emit.assert_called_once()

    def test_status_summary_updates_label_and_tooltip(self, chat_panel):
        chat_panel.set_status_summary("Backend: empty", "Train blocked")
        assert chat_panel.status_label.text() == "Backend: empty"
        assert chat_panel.status_label.toolTip() == "Train blocked"
        assert chat_panel.backend_stage_chip.text() == "No data loaded"

    def test_set_model(self, chat_panel):
        with patch.object(chat_panel, "model_changed") as mock_sig:
            mock_sig.emit = MagicMock()
            chat_panel._set_model("Gemini")
            assert "Gemini" in chat_panel.model_btn.text()
            mock_sig.emit.assert_called_once_with("gemini")

    def test_set_model_keeps_ui_label_separate_from_runtime_mode(self, chat_panel):
        with patch.object(chat_panel, "model_changed") as mock_sig:
            mock_sig.emit = MagicMock()
            chat_panel._set_model("local", "Local model (CPU fallback)")
            assert "CPU fallback" in chat_panel.model_btn.text()
            mock_sig.emit.assert_called_once_with("local")

    def test_set_feature(self, chat_panel):
        chat_panel._set_feature("EEG analyst")
        assert "EEG analyst" in chat_panel.feature_btn.text()

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
        assert "unavailable" in local_action.text()

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
        assert panel.model_btn.text() == "Local model"

    def test_update_model_menu_demotes_verified_gemini(self, qtbot):
        config = MagicMock()
        config.local_model_enabled = True
        config.local_backend_ready.return_value = True
        config.local_backend_status_message.return_value = "Local runtime ready."
        config.gemini_enabled = True
        config.active_mode = "gemini"
        config.inference_mode = "gemini"

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
        assert panel.model_btn.text() == "Gemini (Remote)"

    def test_update_model_menu_surfaces_cpu_fallback(self, qtbot):
        config = MagicMock()
        config.local_model_enabled = True
        config.local_backend_ready.return_value = True
        config.local_backend_status_message.return_value = (
            "Local runtime ready. GPU execution is unavailable in this "
            "environment, so startup will fall back to CPU and disable "
            "4-bit loading."
        )
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
        assert "CPU fallback" in local_action.text()
        assert "fall back to CPU" in local_action.toolTip()
        assert panel.model_btn.text() == "Local model (CPU fallback)"

    def test_update_model_menu_prefers_inference_mode_for_gemini_label(self, qtbot):
        config = MagicMock()
        config.local_model_enabled = True
        config.local_backend_ready.return_value = True
        config.local_backend_status_message.return_value = "Local runtime ready."
        config.gemini_enabled = True
        config.active_mode = "local"
        config.inference_mode = "gemini"

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

        assert panel.model_btn.text() == "Gemini (Remote)"

    def test_product_ui_structure_is_visible(self, chat_panel):
        assert chat_panel.title_label.text() == "XBrainLab Assistant"
        assert chat_panel.empty_state_widget.isHidden() is False
        assert "Workflow" in chat_panel.empty_state_backend_label.text()
        assert chat_panel.backend_stage_chip.text()
        assert chat_panel.model_status_chip.text()
        assert chat_panel.available_commands_chip.text().startswith("Next steps:")
        assert chat_panel.input_field.isHidden() is False
        assert chat_panel.send_btn.text() == "Send"
        assert chat_panel.retry_btn.text() == "Retry"
        assert chat_panel.clear_btn.text() == "Clear"

    def test_product_status_updates_empty_state_and_chips(self, chat_panel):
        chat_panel.set_product_status(
            stage="empty",
            model_status="Local model unavailable",
            available_commands=["load_data", "reset_session"],
            tooltip="Local model cache missing",
            blocked_reason="Generate datasets before training.",
        )

        assert chat_panel.backend_stage_chip.text() == "No data loaded"
        assert chat_panel.model_status_chip.text() == "Local model unavailable"
        assert "Load EEG data" in chat_panel.available_commands_chip.text()
        assert "load_data" not in chat_panel.available_commands_chip.text()
        assert chat_panel.empty_state_backend_label.text() == "Workflow: No data loaded"
        assert chat_panel.empty_state_model_label.text() == (
            "Assistant runtime: Local model unavailable"
        )
        assert "Load EEG data" in chat_panel.empty_state_next_label.text()
