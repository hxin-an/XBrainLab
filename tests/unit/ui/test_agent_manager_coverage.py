"""Coverage tests for AgentManager ??UI component interactions."""

from unittest.mock import MagicMock, patch


def _make_manager():
    """Create a stub AgentManager without calling __init__."""
    from XBrainLab.ui.components.agent_manager import AgentManager

    m = AgentManager.__new__(AgentManager)
    m.study = MagicMock()
    m.main_window = MagicMock()
    m.chat_panel = MagicMock()
    m.chat_controller = MagicMock()
    m.preprocess_controller = MagicMock()
    m.agent_controller = MagicMock()
    m.agent_initialized = True
    m.vram_checker = MagicMock()
    return m


class TestAgentManagerPrepareModelDeletion:
    """Cover prepare_model_deletion paths."""

    def test_no_controller(self):
        """L231-235: Returns True when no controller."""
        m = _make_manager()
        m.agent_controller = None
        assert m.prepare_model_deletion("test") is True

    def test_no_engine(self):
        """L235: Returns True when engine not initialized."""
        m = _make_manager()
        m.agent_controller.worker.engine = None
        assert m.prepare_model_deletion("test") is True


class TestAgentManagerStartSystem:
    """Cover start_system paths."""

    def test_already_initialized(self):
        """Returns early when already initialized."""
        m = _make_manager()
        m.agent_initialized = True
        m.start_system()  # should return early

    def test_no_chat_panel(self):
        """L263: Returns early when no chat panel."""
        m = _make_manager()
        m.agent_initialized = False
        m.chat_panel = None
        m.start_system()


class TestAgentManagerExecutionMode:
    """Cover execution mode forwarding."""

    def test_on_execution_mode_changed(self):
        """L398-399: Forwards mode to controller."""
        m = _make_manager()
        m._on_execution_mode_changed("multi")
        m.agent_controller.set_execution_mode.assert_called_with("multi")

    def test_sync_execution_mode_ui(self):
        """L408-410: Syncs mode btn text."""
        m = _make_manager()
        m._sync_execution_mode_ui("single")
        m.chat_panel.mode_btn.setText.assert_called_with("Single \u25bc")

    def test_sync_multi(self):
        m = _make_manager()
        m._sync_execution_mode_ui("multi")
        m.chat_panel.mode_btn.setText.assert_called_with("Multi \u25bc")


class TestAgentManagerHandleUICommand:
    """Cover handle_user_interaction dispatch."""

    def test_switch_panel(self):
        """L485: switch_panel dispatch."""
        m = _make_manager()
        with patch.object(m, "switch_panel") as mock_sp:
            m.handle_user_interaction("switch_panel", {"panel": "training"})
        mock_sp.assert_called_once()

    def test_confirm_action(self):
        """L488-489: confirm_action dispatch."""
        m = _make_manager()
        with patch.object(m, "_show_action_confirmation") as mock_sa:
            m.handle_user_interaction("confirm_action", {"tool_name": "start_training"})
        mock_sa.assert_called_once()


class TestShowActionConfirmation:
    """Cover _show_action_confirmation L548-584."""

    def test_approved(self):
        """User approves action."""
        m = _make_manager()
        params = {
            "tool_name": "start_training",
            "description": "Start training",
            "params": {"lr": 0.01},
        }
        from PyQt6.QtWidgets import QMessageBox

        mock_box = MagicMock()
        mock_box.exec.return_value = QMessageBox.StandardButton.Yes
        mock_cls = MagicMock(return_value=mock_box)
        # Preserve real Icon and StandardButton so comparisons work
        mock_cls.Icon = QMessageBox.Icon
        mock_cls.StandardButton = QMessageBox.StandardButton
        with patch(
            "XBrainLab.ui.components.agent_manager.QMessageBox",
            mock_cls,
        ):
            m._show_action_confirmation(params)
        m.agent_controller.on_user_confirmed.assert_called_with(True)
        m.chat_controller.add_agent_message.assert_called()

    def test_rejected(self):
        """User rejects action."""
        m = _make_manager()
        params = {
            "tool_name": "start_training",
            "description": "Start training",
            "params": {},
        }
        from PyQt6.QtWidgets import QMessageBox

        mock_box = MagicMock()
        mock_box.exec.return_value = QMessageBox.StandardButton.No
        mock_cls = MagicMock(return_value=mock_box)
        mock_cls.Icon = QMessageBox.Icon
        mock_cls.StandardButton = QMessageBox.StandardButton
        with patch(
            "XBrainLab.ui.components.agent_manager.QMessageBox",
            mock_cls,
        ):
            m._show_action_confirmation(params)
        m.agent_controller.on_user_confirmed.assert_called_with(False)


class TestMontagePicker:
    """Cover montage picker dialog paths."""

    def test_montage_cancel(self):
        """L668-670: Dialog cancelled."""
        m = _make_manager()
        with patch.object(m, "handle_user_input") as mock_hui:
            mock_dialog = MagicMock()
            mock_dialog.exec.return_value = False
            with patch(
                "XBrainLab.ui.components.agent_manager.PickMontageDialog",
                return_value=mock_dialog,
            ):
                m.open_montage_picker_dialog({})

        m.chat_controller.add_agent_message.assert_called_with("Operation Cancelled.")
        mock_hui.assert_called_with("Montage Selection Cancelled by User.")

    def test_montage_no_valid_config(self):
        """L664-667: Dialog accepted but no valid result."""
        m = _make_manager()
        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = True
        mock_dialog.get_result.return_value = (None, None)
        with (
            patch(
                "XBrainLab.ui.components.agent_manager.PickMontageDialog",
                return_value=mock_dialog,
            ),
            patch.object(m, "handle_user_input") as mock_hui,
        ):
            m.open_montage_picker_dialog({})

        mock_hui.assert_called_with("Montage Selection Failed.")

    def test_montage_success_debug_mode(self):
        """L655, L659: Debug mode path after confirmed montage."""
        m = _make_manager()
        m.chat_panel.debug_mode = True
        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = True
        mock_dialog.get_result.return_value = (["Cz", "Fz"], MagicMock())
        with patch(
            "XBrainLab.ui.components.agent_manager.PickMontageDialog",
            return_value=mock_dialog,
        ):
            m.open_montage_picker_dialog({})
        m.chat_controller.add_user_message.assert_called_with("Montage Confirmed.")
