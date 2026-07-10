"""Thread-affinity coverage for Assistant command dispatch."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMainWindow


class _ThreadedAgentController(QObject):
    response_ready = pyqtSignal(str, str)
    chunk_received = pyqtSignal(str)
    generation_started = pyqtSignal()
    processing_finished = pyqtSignal()
    status_update = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    request_user_interaction = pyqtSignal(str, dict)
    remove_content = pyqtSignal(str)
    execution_mode_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.worker_thread = QThread()
        self.worker_thread.start()
        self.input_thread: QThread | None = None
        self.is_processing = False

    def initialize(self):
        self.status_update.emit("Ready")

    def handle_user_input(self, text: str):
        self.input_thread = QThread.currentThread()
        self.is_processing = True
        self.generation_started.emit()
        self.response_ready.emit("Assistant", f"Checked: {text}")
        self.is_processing = False
        self.processing_finished.emit()

    def execute_debug_tool(self, _tool_name: str, _params: dict):
        return None

    def set_execution_mode(self, mode: str):
        self.execution_mode_changed.emit(mode)

    def set_model(self, _model: str):
        return None

    def stop_generation(self):
        self.is_processing = False
        self.processing_finished.emit()

    def reset_conversation(self):
        return None

    def on_user_confirmed(self, _approved: bool):
        return None

    def close(self):
        self.worker_thread.quit()
        self.worker_thread.wait(1000)


def test_controller_commands_run_off_gui_thread(qtbot):
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.components.agent_manager import AgentManager

    app = QApplication.instance()
    assert isinstance(app, QApplication)
    main_window = cast(Any, QMainWindow())
    main_window.ai_btn = MagicMock()
    qtbot.addWidget(main_window)
    controller = _ThreadedAgentController()

    with patch(
        "XBrainLab.ui.components.agent_manager.LLMController",
        return_value=controller,
    ):
        manager = cast(Any, AgentManager(main_window, Study()))
        manager.init_ui()
        manager.start_system()
        command_thread = manager._agent_dispatcher.command_thread
        assert isinstance(command_thread, QThread)
        manager.handle_user_input("inspect the dataset")

    qtbot.waitUntil(lambda: controller.input_thread is not None, timeout=2000)
    assert controller.input_thread is command_thread
    assert controller.input_thread is not controller.worker_thread
    assert controller.input_thread is not app.thread()
    manager.close()
    assert command_thread.isRunning() is False
    assert controller.worker_thread.isRunning() is False
    assert controller.thread() is app.thread()


def test_close_is_idempotent_after_queued_shutdown(qtbot):
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.components.agent_manager import AgentManager

    main_window = cast(Any, QMainWindow())
    main_window.ai_btn = MagicMock()
    qtbot.addWidget(main_window)
    controller = _ThreadedAgentController()
    with patch(
        "XBrainLab.ui.components.agent_manager.LLMController",
        return_value=controller,
    ):
        manager = cast(Any, AgentManager(main_window, Study()))
        manager.init_ui()
        manager.start_system()

    manager.close()
    manager.close()
    assert controller.worker_thread.isRunning() is False
