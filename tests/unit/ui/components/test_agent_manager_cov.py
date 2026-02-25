"""Coverage tests for AgentManager - 129 uncovered lines."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def agent_mgr(qtbot):
    with (
        patch("XBrainLab.ui.components.agent_manager.LLMController") as MockCtrl,
        patch("XBrainLab.ui.components.agent_manager.ChatController"),
        patch("XBrainLab.ui.components.agent_manager.ChatPanel"),
        patch("XBrainLab.ui.components.agent_manager.ModelSettingsDialog"),
        patch("XBrainLab.ui.components.agent_manager.PickMontageDialog"),
    ):
        from PyQt6.QtWidgets import QMainWindow

        from XBrainLab.ui.components.agent_manager import AgentManager

        # main_window must be a real QWidget (parent in super().__init__)
        main_window = QMainWindow()
        main_window.ai_btn = MagicMock()
        qtbot.addWidget(main_window)

        study = MagicMock()
        study.get_controller.return_value = MagicMock()
        mgr = AgentManager(main_window, study)
        mgr.agent_controller = MockCtrl.return_value
        yield mgr


class TestAgentManagerInit:
    def test_creates_instance(self, agent_mgr):
        assert agent_mgr is not None
        assert hasattr(agent_mgr, "study")

    def test_not_initialized_by_default(self, agent_mgr):
        assert not agent_mgr.agent_initialized


class TestAgentManagerMethods:
    def test_update_ai_btn_state(self, agent_mgr):
        agent_mgr.update_ai_btn_state(True)
        agent_mgr.main_window.ai_btn.setChecked.assert_called()

    def test_toggle_float_no_dock(self, agent_mgr):
        agent_mgr.chat_dock = None
        agent_mgr._toggle_float()  # should not raise

    def test_handle_user_input(self, agent_mgr):
        agent_mgr.handle_user_input("hello")
        agent_mgr.agent_controller.handle_user_input.assert_called_once_with("hello")

    def test_stop_generation(self, agent_mgr):
        agent_mgr.stop_generation()
        agent_mgr.agent_controller.stop_generation.assert_called_once()

    def test_set_model(self, agent_mgr):
        agent_mgr.set_model("Gemini")
        agent_mgr.agent_controller.set_model.assert_called_once_with("Gemini")

    def test_start_new_conversation(self, agent_mgr):
        agent_mgr.chat_panel = MagicMock()
        agent_mgr.agent_controller.reset_conversation = MagicMock()
        agent_mgr.start_new_conversation()
        agent_mgr.agent_controller.reset_conversation.assert_called()

    def test_open_settings_dialog(self, agent_mgr):
        with patch(
            "XBrainLab.ui.components.agent_manager.ModelSettingsDialog"
        ) as MockDlg:
            MockDlg.return_value.exec.return_value = False
            agent_mgr.open_settings_dialog()

    def test_prepare_model_deletion_no_controller(self, agent_mgr):
        agent_mgr.agent_controller = None
        assert agent_mgr.prepare_model_deletion("test") is True

    def test_prepare_model_deletion_local_mode(self, agent_mgr):
        ctrl = MagicMock()
        ctrl.worker.engine.config.active_mode = "local"
        agent_mgr.agent_controller = ctrl
        assert agent_mgr.prepare_model_deletion("test") is True
        ctrl.set_model.assert_called_once_with("Gemini")

    def test_prepare_model_deletion_gemini_mode(self, agent_mgr):
        ctrl = MagicMock()
        ctrl.worker.engine.config.active_mode = "gemini"
        agent_mgr.agent_controller = ctrl
        assert agent_mgr.prepare_model_deletion("test") is True

    def test_on_processing_state_changed(self, agent_mgr):
        agent_mgr.chat_panel = MagicMock()
        agent_mgr.on_processing_state_changed(True)

    def test_toggle_first_open(self, agent_mgr):
        agent_mgr.agent_initialized = False
        with patch(
            "XBrainLab.ui.components.agent_manager.ModelSettingsDialog"
        ) as MockDlg:
            MockDlg.return_value.exec.return_value = False
            agent_mgr.toggle()
            # Cancelled, so not initialized

    def test_toggle_already_visible(self, agent_mgr):
        agent_mgr.agent_initialized = True
        agent_mgr.chat_dock = MagicMock()
        agent_mgr.chat_dock.isVisible.return_value = True
        agent_mgr.toggle()
        agent_mgr.chat_dock.close.assert_called()

    def test_toggle_show(self, agent_mgr):
        agent_mgr.agent_initialized = True
        agent_mgr.chat_dock = MagicMock()
        agent_mgr.chat_dock.isVisible.return_value = False
        agent_mgr.toggle()
        agent_mgr.chat_dock.show.assert_called()
