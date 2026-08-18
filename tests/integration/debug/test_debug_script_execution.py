import json
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMainWindow, QToolButton, QWidget

from XBrainLab.debug.tool_debug_mode import ToolDebugMode
from XBrainLab.ui.chat.panel import ChatPanel
from XBrainLab.ui.main_window import MainWindow


class _ImmediateNavigationWindow(QMainWindow):
    """Minimal real Qt host for model-free diagnostic navigation."""

    def __init__(self) -> None:
        super().__init__()
        self.ai_btn = QToolButton(self)
        self.setCentralWidget(QWidget(self))
        self.opened_indices: list[int] = []

    def switch_page(self, index, *, on_ready=None, on_failed=None):
        del on_failed
        self.opened_indices.append(index)
        if on_ready is not None:
            on_ready(self.centralWidget())
        return True


@pytest.fixture
def debug_script_file(tmp_path):
    """Create a temporary debug script."""
    script_content = {
        "schema_version": "xbrainlab.assistant_walkthrough.v1",
        "profile_id": "navigation",
        "title": "Navigation",
        "calls": [
            {
                "id": "open-training",
                "tool": "switch_panel",
                "params": {"panel_name": "training"},
                "instruction": "Open Training",
                "expected_outcomes": ["completed"],
            }
        ],
    }
    p = tmp_path / "test_debug.json"
    p.write_text(json.dumps(script_content), encoding="utf-8")
    yield str(p)
    app = QApplication.instance()
    if isinstance(app, QApplication):
        app.setProperty("tool_debug_script", None)


def test_debug_mode_ui_flow(qtbot, debug_script_file):
    """
    Test the full flow:
    1. App sets property
    2. ChatPanel initializes ToolDebugMode
    3. User clicks Send
    4. Signal is emitted with correct tool/params
    """

    # 1. Set Property on QApplication instance
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    app.setProperty("tool_debug_script", debug_script_file)

    # 2. Init ChatPanel
    panel = ChatPanel()
    qtbot.addWidget(panel)

    # Check if ToolDebugMode is initialized
    assert panel.debug_mode is not None
    assert len(panel.debug_mode.calls) == 1

    # 3. Simulate User Interaction (Click Send)
    # Mock the signal receiver
    mock_receiver = MagicMock()
    panel.debug_tool_requested.connect(mock_receiver)

    qtbot.mouseClick(panel.send_btn, Qt.MouseButton.LeftButton)

    # 4. Verify Signal
    mock_receiver.assert_called_once_with(
        "switch_panel",
        {"panel_name": "training"},
        False,
        "",
    )

    # Verify State Update
    assert panel.debug_mode.index == 0
    assert panel.debug_mode.is_waiting
    assert panel.send_btn.isEnabled() is False

    # 5. A second click cannot consume the pending step.
    qtbot.mouseClick(panel.send_btn, Qt.MouseButton.LeftButton)
    assert mock_receiver.call_count == 1  # Still 1
    panel.complete_debug_step("cancelled")
    assert panel.debug_mode.index == 0
    assert not panel.debug_mode.can_dispatch
    assert panel.send_btn.isEnabled() is False
    assert "stopped" in panel.input_field.placeholderText().casefold()

    # Clean up property
    app.setProperty("tool_debug_script", None)


def test_debug_script_parsing(debug_script_file):
    """Verify ToolDebugMode parses generic JSON correctly."""
    debugger = ToolDebugMode(debug_script_file)
    assert len(debugger.calls) == 1
    call = debugger.begin_call()
    assert call is not None
    assert call.tool == "switch_panel"
    assert call.params["panel_name"] == "training"


def test_debug_mode_execution_integration(qtbot, debug_script_file):
    """Debug requests have one Agent owner instead of a MainWindow bypass."""
    # 1. Setup MainWindow with property
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    app.setProperty("tool_debug_script", debug_script_file)

    # Mock specific return values if any called during init
    # e.g. study.get_controller() calls

    # Patch the panel classes to avoid real instantiation (which might fail with mocks)
    with (
        patch("XBrainLab.ui.main_window.DatasetPanel") as MockDatasetPanel,
        patch("XBrainLab.ui.main_window.PreprocessPanel") as MockPreprocessPanel,
        patch("XBrainLab.ui.main_window.TrainingPanel") as MockTrainingPanel,
        patch("XBrainLab.ui.main_window.VisualizationPanel") as MockVisPanel,
        patch("XBrainLab.ui.main_window.EvaluationPanel") as MockEvalPanel,
        patch("XBrainLab.ui.main_window.InfoPanelService") as MockInfoService,
        patch("XBrainLab.ui.main_window.AgentManager") as MockAgentManager,
    ):
        # Configure mocks
        MockDatasetPanel.return_value = QWidget()
        MockPreprocessPanel.return_value = QWidget()
        MockTrainingPanel.return_value = QWidget()
        MockVisPanel.return_value = QWidget()
        MockEvalPanel.return_value = QWidget()

        # AgentManager Mock needs special care because we access its attributes
        mock_agent_manager_instance = MockAgentManager.return_value

        # We need a real ChatPanel or a mock that behaves like one
        # Let's use a real ChatPanel but detached from logic if possible,
        # OR mock the chat panel completely and only verify the signal connection?
        # The test clicks a button on ChatPanel. Real ChatPanel is easiest if we can.
        # But AgentManager creates it.
        # Let's let AgentManager be mocked, but assign a REAL ChatPanel to it manually
        # so we can click buttons. Or just mock the chat panel signal?

        # BETTER APPROACH: Let's use REAL AgentManager but Mock the Panels it uses?
        # AgentManager uses ChatPanel. ChatPanel uses ChatController.
        # Let's mock AgentManager in MainWindow init, then replace the mock with something we control?
        # No, MainWindow creates AgentManager.

        # If we patch AgentManager, `window.agent_manager` will be the mock.
        # We need `window.agent_manager.chat_panel` to be reachable.

        from XBrainLab.ui.chat.panel import ChatPanel

        real_chat_panel = ChatPanel()
        mock_agent_manager_instance.chat_panel = real_chat_panel

        study = MagicMock()
        window = MainWindow(study)
        qtbot.addWidget(window)
        window.init_agent()

        dispatcher_debug = MagicMock()
        real_chat_panel.debug_tool_requested.connect(dispatcher_debug)

        # 3. Trigger Debug Step
        # Provide the script execution manually if needed, or rely on Signal?
        # ChatPanel init reads the property.
        # Since we instantiated `real_chat_panel` MANUALLY above, its `__init__` ran.
        # Did it see the property? Yes, if we set it BEFORE init.

        # Wait, `real_chat_panel` was created inside the `with patch` block?
        # No, I created it explicitly. It should work.

        qtbot.addWidget(real_chat_panel)  # Just to be safe regarding events
        qtbot.mouseClick(real_chat_panel.send_btn, Qt.MouseButton.LeftButton)

        dispatcher_debug.assert_called_once_with(
            "switch_panel",
            {"panel_name": "training"},
            False,
            "",
        )
        assert not hasattr(window, "debug_executor")
        assert not hasattr(window, "_on_debug_tool_requested")

    app.setProperty("tool_debug_script", None)


def test_tool_debug_session_runs_backend_without_runtime_activation(qtbot, tmp_path):
    """The real diagnostic transport executes tools without loading Granite."""
    from XBrainLab.backend.study import Study
    from XBrainLab.llm.agent.controller import LLMController
    from XBrainLab.ui.components.agent_manager import AgentManager
    from XBrainLab.ui.components.assistant_runtime_lifecycle import (
        AssistantRuntimeLifecycle,
        AssistantRuntimeLifecycleState,
    )

    script_path = tmp_path / "backend-blocked.json"
    script_path.write_text(
        json.dumps(
            {
                "schema_version": "xbrainlab.assistant_walkthrough.v1",
                "profile_id": "blocked-training",
                "title": "Blocked training",
                "calls": [
                    {
                        "id": "start-empty",
                        "tool": "start_training",
                        "params": {},
                        "instruction": "Verify training is blocked",
                        "expected_outcomes": ["blocked"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    app.setProperty("tool_debug_script", str(script_path))

    window = QMainWindow()
    window.ai_btn = QToolButton(window)
    window.setCentralWidget(QWidget(window))
    qtbot.addWidget(window)
    study = Study()

    def reject_config_load():
        raise AssertionError("Tool diagnostics must not resolve model settings.")

    runtime = AssistantRuntimeLifecycle(
        study,
        controller_factory=lambda current: LLMController(current),
        config_loader=reject_config_load,
    )
    manager = AgentManager(window, study, runtime_lifecycle=runtime)
    try:
        manager.init_ui()
        manager.toggle()
        assert manager.chat_panel is not None
        assert runtime.current.backend_mode == "diagnostic"

        qtbot.mouseClick(manager.chat_panel.send_btn, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(
            lambda: any(
                "Training can't start yet" in message["content"]
                for message in manager.chat_controller.messages
            ),
            timeout=10_000,
        )

        visible = "\n".join(
            message["content"] for message in manager.chat_controller.messages
        )
        assert "**Required first:** Import EEG data." in visible
        assert "Running a diagnostic action" not in visible
        assert "Save a valid data splitting specification" not in visible
        assert "Tool Output:" not in visible
    finally:
        manager.close()
        qtbot.waitUntil(
            lambda: runtime.state is AssistantRuntimeLifecycleState.CLOSED,
            timeout=10_000,
        )
        app.setProperty("tool_debug_script", None)


def test_contract_failure_profile_advances_only_on_real_terminals(qtbot):
    """The empty-state profile runs through the real no-model frontend boundary."""
    from XBrainLab.backend.controller.chat_controller import (
        ChatMessagePresentationKind,
    )
    from XBrainLab.backend.study import Study
    from XBrainLab.llm.agent.controller import LLMController
    from XBrainLab.ui.components.agent_manager import AgentManager
    from XBrainLab.ui.components.assistant_runtime_lifecycle import (
        AssistantRuntimeLifecycle,
        AssistantRuntimeLifecycleState,
    )

    profile = "scripts/dev/agent_tool_walkthrough/contract-failures.json"
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    app.setProperty("tool_debug_script", profile)
    window = _ImmediateNavigationWindow()
    qtbot.addWidget(window)
    study = Study()
    runtime = AssistantRuntimeLifecycle(
        study,
        controller_factory=lambda current: LLMController(current),
        config_loader=lambda: (_ for _ in ()).throw(
            AssertionError("Diagnostic profile must not load Granite settings.")
        ),
    )
    manager = AgentManager(window, study, runtime_lifecycle=runtime)
    try:
        manager.init_ui()
        manager.toggle()
        panel = manager.chat_panel
        assert panel is not None and panel.debug_mode is not None
        total = len(panel.debug_mode.calls)
        for expected_index in range(1, total + 1):
            assert panel.send_btn.isEnabled()
            qtbot.mouseClick(panel.send_btn, Qt.MouseButton.LeftButton)
            qtbot.waitUntil(
                lambda value=expected_index: panel.debug_mode.index == value,
                timeout=10_000,
            )
        assert panel.debug_mode.is_complete
        assert runtime.current.backend_mode == "diagnostic"
        assert window.opened_indices == [0, 1]
        dataset_terminal = next(
            record
            for record in manager.chat_controller.get_typed_history()
            if record.content == "Opened the Dataset panel in XBrainLab."
        )
        assert (
            dataset_terminal.presentation_kind
            is ChatMessagePresentationKind.TOOL_RESULT
        )
    finally:
        manager.close()
        qtbot.waitUntil(
            lambda: runtime.state is AssistantRuntimeLifecycleState.CLOSED,
            timeout=10_000,
        )
        app.setProperty("tool_debug_script", None)
