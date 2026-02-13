import json
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QWidget

from XBrainLab.debug.tool_debug_mode import ToolDebugMode
from XBrainLab.ui.chat.panel import ChatPanel
from XBrainLab.ui.main_window import MainWindow


@pytest.fixture
def debug_script_file(tmp_path):
    """Create a temporary debug script."""
    script_content = {
        "version": "1.0",
        "calls": [{"tool": "switch_panel", "params": {"panel_name": "training"}}],
    }
    p = tmp_path / "test_debug.json"
    p.write_text(json.dumps(script_content), encoding="utf-8")
    return str(p)


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
    mock_receiver.assert_called_once_with("switch_panel", {"panel_name": "training"})

    # Verify State Update
    assert panel.debug_mode.index == 1
    assert panel.debug_mode.is_complete

    # 5. Click again -> Should not emit signal, show completion
    qtbot.mouseClick(panel.send_btn, Qt.MouseButton.LeftButton)
    assert mock_receiver.call_count == 1  # Still 1
    assert "Completed" in panel.input_field.text()

    # Clean up property
    app.setProperty("tool_debug_script", None)


def test_debug_script_parsing(debug_script_file):
    """Verify ToolDebugMode parses generic JSON correctly."""
    debugger = ToolDebugMode(debug_script_file)
    assert len(debugger.calls) == 1
    call = debugger.next_call()
    assert call.tool == "switch_panel"
    assert call.params["panel_name"] == "training"


def test_debug_mode_execution_integration(qtbot, debug_script_file):
    """
    Test that the signal actually triggers tool execution in MainWindow.
    M3.1 Verification.
    """
    # 1. Setup MainWindow with property
    app = QApplication.instance()
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

        # Mock the ToolExecutor to verify call
        window.debug_executor.execute = MagicMock(return_value="Success")

        # 3. Trigger Debug Step
        # Provide the script execution manually if needed, or rely on Signal?
        # ChatPanel init reads the property.
        # Since we instantiated `real_chat_panel` MANUALLY above, its `__init__` ran.
        # Did it see the property? Yes, if we set it BEFORE init.

        # Wait, `real_chat_panel` was created inside the `with patch` block?
        # No, I created it explicitly. It should work.

        # Ensure the signal from `real_chat_panel` is connected to `window._on_debug_tool_requested`
        # MainWindow init connects it:
        # `if self.agent_manager.chat_panel: ... connect(...)`
        # So it should work.

        qtbot.addWidget(real_chat_panel)  # Just to be safe regarding events
        qtbot.mouseClick(real_chat_panel.send_btn, Qt.MouseButton.LeftButton)

        # 4. Verify Execution
        # Script has switch_panel to training
        window.debug_executor.execute.assert_called_once_with(
            "switch_panel", {"panel_name": "training"}
        )

        # 5. Verify Feedback
        # DebugExecutor returns "Success"
        # MainWindow calls `agent_manager.chat_panel.append_message`
        # Check `real_chat_panel` content
        last_idx = real_chat_panel.chat_layout.count() - 2
        bubble = real_chat_panel.chat_layout.itemAt(last_idx).widget()
        assert "System" in bubble.get_text() or "tool" in bubble.get_text().lower()
        assert "Success" in bubble.get_text()

    app.setProperty("tool_debug_script", None)
