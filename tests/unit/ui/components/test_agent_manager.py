"""Coverage tests for AgentManager - 129 uncovered lines."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QEvent, QObject, QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QMainWindow


@pytest.fixture
def agent_mgr(qtbot):
    with (
        patch("XBrainLab.ui.components.agent_manager.LLMController") as MockCtrl,
        patch("XBrainLab.ui.components.agent_manager.ChatController"),
        patch("XBrainLab.ui.components.agent_manager.ChatPanel"),
        patch("XBrainLab.ui.components.agent_manager.ModelSettingsDialog"),
        patch("XBrainLab.ui.components.agent_manager.PickMontageDialog"),
    ):
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
        assert isinstance(agent_mgr, QObject)
        assert agent_mgr.study is not None

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
        agent_mgr.agent_controller.set_model.assert_called_once_with("local")

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
        ctrl.worker.engine.config.inference_mode = "local"
        agent_mgr.agent_controller = ctrl
        with patch("XBrainLab.ui.components.agent_manager.QMessageBox.warning"):
            assert agent_mgr.prepare_model_deletion("test") is False
        ctrl.set_model.assert_not_called()

    def test_prepare_model_deletion_stale_remote_mode_still_blocks(self, agent_mgr):
        ctrl = MagicMock()
        ctrl.worker.engine.config.active_mode = "gemini"
        ctrl.worker.engine.config.inference_mode = "gemini"
        agent_mgr.agent_controller = ctrl
        with patch("XBrainLab.ui.components.agent_manager.QMessageBox.warning"):
            assert agent_mgr.prepare_model_deletion("test") is False

    def test_prepare_model_deletion_uses_inference_mode_truth(self, agent_mgr):
        ctrl = MagicMock()
        ctrl.worker.engine.config.active_mode = "gemini"
        ctrl.worker.engine.config.inference_mode = "local"
        agent_mgr.agent_controller = ctrl
        with patch("XBrainLab.ui.components.agent_manager.QMessageBox.warning"):
            assert agent_mgr.prepare_model_deletion("test") is False

    def test_on_processing_state_changed(self, agent_mgr):
        agent_mgr.chat_panel = MagicMock()
        agent_mgr.on_processing_state_changed(True)

    def test_toggle_first_open(self, agent_mgr):
        agent_mgr.agent_initialized = False
        agent_mgr.chat_panel = MagicMock()
        agent_mgr.chat_dock = MagicMock()
        with (
            patch.object(agent_mgr, "_load_runtime_config", return_value=MagicMock()),
            patch.object(
                agent_mgr,
                "_assistant_runtime_start_status",
                return_value=(True, "Local runtime ready."),
            ),
            patch.object(agent_mgr, "start_system") as mock_start,
        ):
            agent_mgr.toggle()
        agent_mgr.chat_dock.show.assert_called_once()
        mock_start.assert_called_once()

    def test_init_ui_uses_draggable_product_dock_titlebar(self, qtbot):
        from PyQt6.QtWidgets import QDockWidget

        from XBrainLab.ui.components.agent_manager import (
            AgentManager,
            AssistantDockTitleBar,
        )

        main_window = QMainWindow()
        main_window.ai_btn = MagicMock()
        qtbot.addWidget(main_window)
        study = MagicMock()
        study.get_controller.return_value = MagicMock()
        manager = AgentManager(main_window, study)

        manager.init_ui()

        assert isinstance(manager.chat_dock.titleBarWidget(), AssistantDockTitleBar)
        features = manager.chat_dock.features()
        assert features & QDockWidget.DockWidgetFeature.DockWidgetMovable
        assert features & QDockWidget.DockWidgetFeature.DockWidgetFloatable
        assert manager.chat_dock.minimumWidth() >= 320

    def test_dock_titlebar_empty_space_preserves_native_drag_events(self, qtbot):
        from XBrainLab.ui.components.agent_manager import AssistantDockTitleBar

        toggle = MagicMock()
        title_bar = AssistantDockTitleBar(toggle)
        qtbot.addWidget(title_bar)

        for event_type in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseMove,
            QEvent.Type.MouseButtonRelease,
        ):
            event = QMouseEvent(
                event_type,
                QPointF(8, 8),
                QPointF(8, 8),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            event.accept()

            if event_type == QEvent.Type.MouseButtonPress:
                title_bar.mousePressEvent(event)
            elif event_type == QEvent.Type.MouseMove:
                title_bar.mouseMoveEvent(event)
            else:
                title_bar.mouseReleaseEvent(event)

            assert not event.isAccepted()

        double_click = QMouseEvent(
            QEvent.Type.MouseButtonDblClick,
            QPointF(8, 8),
            QPointF(8, 8),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        title_bar.mouseDoubleClickEvent(double_click)

        toggle.assert_called_once()
        assert double_click.isAccepted()

    def test_toggle_first_open_unavailable_keeps_panel_open(self, agent_mgr):
        agent_mgr.agent_initialized = False
        agent_mgr.chat_panel = MagicMock()
        agent_mgr.chat_dock = MagicMock()
        with (
            patch(
                "XBrainLab.ui.components.agent_manager.ModelSettingsDialog"
            ) as MockDlg,
            patch.object(agent_mgr, "_load_runtime_config", return_value=MagicMock()),
            patch.object(
                agent_mgr,
                "_assistant_runtime_start_status",
                return_value=(False, "Model cache not found."),
            ),
            patch.object(agent_mgr, "start_system") as mock_start,
        ):
            agent_mgr.toggle()

        MockDlg.assert_not_called()
        agent_mgr.chat_dock.show.assert_called_once()
        mock_start.assert_not_called()
        agent_mgr.chat_controller.add_agent_message.assert_called_with(
            "**Assistant unavailable**: Required assistant files are unavailable. "
            "Open assistant settings to finish setup."
        )

    def test_handle_user_input_reports_runtime_reason_when_controller_missing(
        self,
        agent_mgr,
    ):
        agent_mgr.agent_controller = None
        with (
            patch.object(agent_mgr, "_load_runtime_config", return_value=MagicMock()),
            patch.object(
                agent_mgr,
                "_assistant_runtime_start_status",
                return_value=(False, "Model cache not found."),
            ),
        ):
            agent_mgr.handle_user_input("train")

        agent_mgr.chat_controller.add_user_message.assert_called_with("train")
        agent_mgr.chat_controller.add_agent_message.assert_called_with(
            "**Assistant unavailable**: Required assistant files are unavailable. "
            "Open assistant settings to finish setup."
        )

    def test_first_run_later_keeps_runtime_unloaded(self, agent_mgr):
        from XBrainLab.llm.core.config import LLMConfig
        from XBrainLab.ui.dialogs.local_runtime_first_run_dialog import (
            LocalRuntimeFirstRunDialog,
        )

        config = LLMConfig()
        with patch.object(config, "save_to_file") as mock_save:
            should_continue = agent_mgr._handle_local_runtime_first_run_choice(
                config,
                LocalRuntimeFirstRunDialog.LATER,
            )

        assert should_continue is False
        mock_save.assert_not_called()
        agent_mgr.chat_controller.add_agent_message.assert_called_with(
            "Assistant setup was deferred. Open assistant settings when you are "
            "ready to continue."
        )

    def test_first_run_disable_persists_without_loading(self, agent_mgr):
        from XBrainLab.llm.core.config import LLMConfig
        from XBrainLab.ui.dialogs.local_runtime_first_run_dialog import (
            LocalRuntimeFirstRunDialog,
        )

        config = LLMConfig()
        with patch.object(config, "save_to_file") as mock_save:
            should_continue = agent_mgr._handle_local_runtime_first_run_choice(
                config,
                LocalRuntimeFirstRunDialog.DISABLE,
            )

        assert should_continue is False
        assert config.local_model_enabled is False
        assert config.local_runtime_notice_acknowledged is True
        mock_save.assert_called_once()

    def test_local_disabled_runtime_status_is_user_visible(self, agent_mgr):
        from XBrainLab.llm.core.config import LLMConfig

        config = LLMConfig()
        config.local_model_enabled = False

        ready, message = agent_mgr._assistant_runtime_start_status(config)

        assert ready is False
        assert "disabled" in message

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

    def test_debug_tool_flow_surfaces_backend_blocked_result(self, qtbot):
        """UI -> agent -> backend command flow reports shared blocked reason."""
        from XBrainLab.backend.study import Study
        from XBrainLab.ui.components.agent_manager import AgentManager

        main_window = QMainWindow()
        main_window.ai_btn = MagicMock()
        qtbot.addWidget(main_window)
        study = Study()

        with (
            patch("XBrainLab.llm.agent.controller.AgentWorker") as MockWorker,
            patch("XBrainLab.llm.agent.controller.QThread") as MockThread,
            patch("XBrainLab.llm.agent.controller.threading.Thread") as MockThreading,
        ):
            MockWorker.return_value.generation_thread = None
            MockThread.return_value.isRunning.return_value = False
            MockThreading.return_value.start = MagicMock()

            manager = AgentManager(main_window, study)
            manager.init_ui()
            manager.start_system()
            manager.agent_controller.execute_debug_tool("start_training", {})

        messages = [message["content"] for message in manager.chat_controller.messages]
        visible = "\n".join(messages)

        assert "Training is not available yet" in visible
        assert "Generate datasets before training" in visible
        assert "Tool Output:" not in visible
        assert "command_name" not in visible
        assert manager.chat_panel.status_label.text() == "No data loaded"


class _FakeAgentController(QObject):
    response_ready = pyqtSignal(str, str)
    chunk_received = pyqtSignal(str)
    generation_started = pyqtSignal()
    processing_finished = pyqtSignal()
    status_update = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    request_user_interaction = pyqtSignal(str, dict)
    remove_content = pyqtSignal(str)
    execution_mode_changed = pyqtSignal(str)

    def __init__(self, mode: str):
        super().__init__()
        self.mode = mode
        self.is_processing = False
        self.received_inputs: list[str] = []

    def initialize(self):
        self.status_update.emit("Ready")

    def handle_user_input(self, text: str):
        self.received_inputs.append(text)
        self.is_processing = True
        self.generation_started.emit()
        if self.mode == "normal":
            self.chunk_received.emit(
                "Hello from XBrainLab. I can inspect state or guide the EEG workflow."
            )
        elif self.mode == "empty":
            self.error_occurred.emit(
                "Assistant returned an empty response. Try Retry or check local runtime status."
            )
        elif self.mode == "error":
            self.error_occurred.emit("Model load failed: local runtime unavailable.")
        self.is_processing = False
        self.processing_finished.emit()

    def execute_debug_tool(self, _tool_name: str, _params: dict):
        return None

    def set_execution_mode(self, _mode: str):
        return None

    def stop_generation(self):
        self.is_processing = False
        self.processing_finished.emit()

    def reset_conversation(self):
        return None

    def close(self):
        return None


def _make_real_manager_with_fake_controller(qtbot, mode: str):
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.components.agent_manager import AgentManager

    main_window = QMainWindow()
    main_window.ai_btn = MagicMock()
    qtbot.addWidget(main_window)
    study = Study()
    fake = _FakeAgentController(mode)
    with patch(
        "XBrainLab.ui.components.agent_manager.LLMController", return_value=fake
    ):
        manager = AgentManager(main_window, study)
        manager.init_ui()
        manager.start_system()
    return manager, fake


class TestAgentManagerProductChatFlow:
    def test_normal_chat_response_product_flow(self, qtbot):
        manager, fake = _make_real_manager_with_fake_controller(qtbot, "normal")

        manager.chat_panel.input_field.setText("hello")
        manager.chat_panel._on_send()

        messages = manager.chat_controller.messages
        assert messages[0] == {"role": "user", "content": "hello"}
        assert fake.received_inputs == ["hello"]
        assert manager.chat_panel.current_agent_bubble is not None
        assert (
            "Hello from XBrainLab" in manager.chat_panel.current_agent_bubble.get_text()
        )
        assert manager.chat_controller.is_processing is False
        assert manager.chat_panel.is_processing is False

    def test_empty_response_fallback_is_visible(self, qtbot):
        manager, _fake = _make_real_manager_with_fake_controller(qtbot, "empty")

        manager.chat_panel.input_field.setText("hello")
        manager.chat_panel._on_send()

        assistant_messages = [
            message["content"]
            for message in manager.chat_controller.messages
            if message["role"] == "assistant"
        ]
        assert any("empty response" in message for message in assistant_messages)
        assert manager.chat_controller.is_processing is False

    def test_worker_error_is_visible(self, qtbot):
        manager, _fake = _make_real_manager_with_fake_controller(qtbot, "error")

        manager.chat_panel.input_field.setText("hello")
        manager.chat_panel._on_send()

        assistant_messages = [
            message["content"]
            for message in manager.chat_controller.messages
            if message["role"] == "assistant"
        ]
        assert any("Model load failed" in message for message in assistant_messages)
        assert manager.chat_panel.is_processing is False

    def test_retry_without_prior_request_uses_notice_not_transcript(self, qtbot):
        manager, _fake = _make_real_manager_with_fake_controller(qtbot, "normal")

        manager.retry_last_user_input()

        assert manager.chat_controller.messages == []
        assert manager.chat_panel.notice_label.isHidden() is False
        assert "Retry" in manager.chat_panel.notice_label.text()
        assert manager.chat_panel.retry_btn.isEnabled() is False

    def test_local_unavailable_first_open_is_visible_with_real_panel(self, qtbot):
        from XBrainLab.backend.study import Study
        from XBrainLab.ui.components.agent_manager import AgentManager

        main_window = QMainWindow()
        main_window.ai_btn = MagicMock()
        qtbot.addWidget(main_window)
        manager = AgentManager(main_window, Study())
        manager.init_ui()

        with (
            patch.object(manager, "_load_runtime_config", return_value=MagicMock()),
            patch.object(
                manager,
                "_assistant_runtime_start_status",
                return_value=(False, "Model cache not found."),
            ),
        ):
            manager.toggle()

        assistant_messages = [
            message["content"]
            for message in manager.chat_controller.messages
            if message["role"] == "assistant"
        ]
        assert any("Assistant unavailable" in message for message in assistant_messages)
        assert not any(
            "Model cache not found" in message for message in assistant_messages
        )
        assert manager.chat_dock.isHidden() is False
