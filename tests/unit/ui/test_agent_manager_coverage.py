"""Coverage tests for AgentManager ??UI component interactions."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QMainWindow

from XBrainLab.backend.study import Study


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
    m.status_message_received = MagicMock()
    epoch_data = MagicMock()
    epoch_data.get_channel_names.return_value = ["Cz", "Fz"]
    epoch_data.get_mne.return_value.info = {"ch_names": ["Cz", "Fz"]}
    m.study.epoch_data = epoch_data
    return m


def _empty_workflow_state():
    return SimpleNamespace(
        active_dataset=SimpleNamespace(
            has_raw_data=False,
            has_preprocessed_data=False,
            has_epoch_data=False,
            has_datasets=False,
        ),
        active_training=SimpleNamespace(is_running=False),
        training=SimpleNamespace(
            is_running=False,
            has_model=False,
            has_training_option=False,
        ),
        evaluation=SimpleNamespace(finished_runs=0, metrics_available=False),
        pipeline_stage="empty",
        last_error=None,
    )


def test_agent_manager_does_not_fetch_preprocess_controller_from_real_study(qtbot):
    from XBrainLab.ui.components.agent_manager import AgentManager

    study = Study()
    study.get_controller = MagicMock(
        side_effect=AssertionError("real Study controller lookup is not allowed"),
    )
    main_window = QMainWindow()
    qtbot.addWidget(main_window)

    with patch("XBrainLab.ui.components.agent_manager.BackendFacade"):
        manager = AgentManager(main_window, study)

    study.get_controller.assert_not_called()
    assert manager.preprocess_controller is None


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

    def test_active_local_model_blocks_deletion(self):
        """Deletion should fail closed instead of auto-switching to Gemini."""
        m = _make_manager()
        m.agent_controller.worker.engine.config.active_mode = "local"
        m.agent_controller.worker.engine.config.inference_mode = "local"
        with patch("XBrainLab.ui.components.agent_manager.QMessageBox.warning"):
            assert m.prepare_model_deletion("test") is False
        m.agent_controller.set_model.assert_not_called()

    def test_inference_mode_truth_blocks_deletion_even_if_active_mode_stale(self):
        m = _make_manager()
        m.agent_controller.worker.engine.config.active_mode = "gemini"
        m.agent_controller.worker.engine.config.inference_mode = "local"
        with patch("XBrainLab.ui.components.agent_manager.QMessageBox.warning"):
            assert m.prepare_model_deletion("test") is False


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


class TestAgentManagerBackendStatus:
    def test_refresh_backend_status_handles_missing_train_capability(self):
        m = _make_manager()
        m.backend_facade = MagicMock()
        m.backend_facade.get_state.return_value = _empty_workflow_state()
        m.backend_facade.get_capabilities.return_value = {
            "scan_source": SimpleNamespace(enabled=True, reasons=[]),
        }
        model_config = MagicMock()
        model_config.local_backend_ready.return_value = True

        with (
            patch(
                "XBrainLab.ui.components.agent_manager.LLMConfig.load_from_file",
                return_value=model_config,
            ),
            patch(
                "XBrainLab.ui.components.agent_manager.LLMConfig.assistant_runtime_selection_from",
                return_value=SimpleNamespace(model_id="local-model"),
            ),
        ):
            m.refresh_backend_status()

        m.chat_panel.set_product_status.assert_called_once()
        kwargs = m.chat_panel.set_product_status.call_args.kwargs
        assert kwargs["stage"] == "No data loaded"
        assert kwargs["available_commands"] == ["scan_source"]
        assert kwargs["blocked_reason"] is None
        m.chat_panel.set_status_summary.assert_not_called()

    def test_product_next_steps_ignores_missing_candidate_capabilities(self):
        from XBrainLab.ui.components.agent_manager import AgentManager

        state = _empty_workflow_state()
        state.active_dataset.has_raw_data = True

        assert AgentManager._product_next_steps(state, {}) == []


class TestAgentManagerRetry:
    """Cover chat retry behaviour."""

    def test_retry_last_user_input(self):
        m = _make_manager()
        m.chat_controller.is_processing = False
        m._last_user_input = "train the model"
        with patch.object(m, "handle_user_input") as mock_handle:
            m.retry_last_user_input()
        mock_handle.assert_called_once_with("train the model")

    def test_retry_without_previous_message_reports_status(self):
        m = _make_manager()
        m.chat_controller.is_processing = False
        m._last_user_input = None
        m.retry_last_user_input()
        m.chat_controller.add_agent_message.assert_not_called()
        m.chat_panel.show_notice.assert_called_with(
            "Send a request before using Retry."
        )


class TestAgentManagerExecutionMode:
    """Cover execution mode forwarding."""

    def test_on_execution_mode_changed(self):
        """L398-399: Forwards mode to controller."""
        m = _make_manager()
        m._on_execution_mode_changed("multi")
        m.agent_controller.set_execution_mode.assert_called_with("multi")

    def test_sync_execution_mode_ui(self):
        """Execution mode sync must not surface unfinished step controls."""
        m = _make_manager()
        m._sync_execution_mode_ui("single")
        m.chat_panel.mode_btn.setText.assert_called_with("")

    def test_sync_multi(self):
        m = _make_manager()
        m._sync_execution_mode_ui("multi")
        m.chat_panel.mode_btn.setText.assert_called_with("")


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
        visible_text = mock_box.setText.call_args.args[0]
        assert "Action: Start training" in visible_text
        assert "start_training" not in visible_text
        assert "Tool:" not in visible_text
        assert (
            "Confirmed: Start training."
            in (m.chat_controller.add_agent_message.call_args.args[0])
        )

    def test_rejected(self):
        """User rejects action."""
        m = _make_manager()
        params = {
            "tool_name": "clear_dataset",
            "description": "Clear the current dataset",
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
        visible_text = mock_box.setText.call_args.args[0]
        assert "Action: Clear dataset" in visible_text
        assert "clear_dataset" not in visible_text
        assert "Tool:" not in visible_text
        assert (
            "Cancelled: Clear dataset."
            in (m.chat_controller.add_agent_message.call_args.args[0])
        )


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
        mock_dialog.get_result.return_value = (
            ["Cz", "Fz"],
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)],
        )
        with patch(
            "XBrainLab.ui.components.agent_manager.PickMontageDialog",
            return_value=mock_dialog,
        ):
            m.open_montage_picker_dialog({})
        m.chat_controller.add_user_message.assert_called_with("Montage Confirmed.")

    def test_real_study_montage_blocked_by_backend_capability(self):
        """Real Study UI paths must use the shared capability policy."""
        from XBrainLab.backend.study import Study

        m = _make_manager()
        m.study = Study()
        status_bar = MagicMock()
        m.main_window.statusBar.return_value = status_bar

        with patch(
            "XBrainLab.ui.components.agent_manager.PickMontageDialog",
        ) as mock_dialog:
            m.open_montage_picker_dialog({})

        mock_dialog.assert_not_called()
        status_bar.showMessage.assert_called_with(
            "Create epochs before applying a montage.",
        )

    def test_real_study_montage_success_uses_application_service(self):
        """Real Study acceptance applies montage through the command service."""
        from XBrainLab.backend.study import Study

        m = _make_manager()
        m.study = Study()
        m.preprocess_controller = MagicMock()
        m.chat_panel.debug_mode = True
        epoch_data = MagicMock()
        epoch_data.get_channel_names.return_value = ["C3", "C4"]
        epoch_data.get_mne.return_value.info = {"ch_names": ["C3", "C4"]}
        m.study.epoch_data = epoch_data
        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = True
        mock_dialog.get_result.return_value = (
            ["C3", "C4"],
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)],
        )

        with patch(
            "XBrainLab.ui.components.agent_manager.PickMontageDialog",
            return_value=mock_dialog,
        ):
            m.open_montage_picker_dialog({"montage_name": "standard_1020"})

        epoch_data.set_channels.assert_called_once_with(
            ["C3", "C4"],
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)],
        )
        m.preprocess_controller.apply_montage.assert_not_called()
        m.chat_controller.add_user_message.assert_called_with("Montage Confirmed.")

    def test_real_study_montage_uses_state_query_for_channel_names(self):
        """Agent montage picker should not read Study epoch objects for UI choices."""
        from XBrainLab.backend.application import (
            ApplyMontageCommand,
            ChangedState,
            CommandResult,
            QueryStateCommand,
        )
        from XBrainLab.backend.study import Study

        m = _make_manager()
        m.study = Study()
        m.preprocess_controller = MagicMock()
        m.chat_panel.debug_mode = True
        epoch_data = MagicMock()
        epoch_data.get_mne.side_effect = AssertionError("stale epoch object read")
        m.study.epoch_data = epoch_data
        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = True
        mock_dialog.get_result.return_value = (
            ["C3", "C4"],
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)],
        )

        def execute_side_effect(_context, command, **_kwargs):
            if isinstance(command, QueryStateCommand):
                return CommandResult.success_result(
                    "query_state",
                    "Application state snapshot ready.",
                    state={},
                    changed_state=ChangedState(),
                    diagnostics={
                        "state": {"epoch": {"channel_names": ["C3", "C4"]}},
                    },
                )
            if isinstance(command, ApplyMontageCommand):
                return CommandResult.success_result(
                    "apply_montage",
                    "Applied montage.",
                    state={},
                    changed_state=ChangedState(visualization_changed=True),
                )
            raise AssertionError(f"Unexpected command: {command!r}")

        with (
            patch(
                "XBrainLab.ui.components.agent_manager.get_command_capability",
                return_value=SimpleNamespace(enabled=True, reasons=[]),
            ),
            patch(
                "XBrainLab.ui.components.agent_manager.execute_application_command",
                side_effect=execute_side_effect,
            ) as execute,
            patch(
                "XBrainLab.ui.components.agent_manager.PickMontageDialog",
                return_value=mock_dialog,
            ) as dialog_cls,
        ):
            m.open_montage_picker_dialog({"montage_name": "standard_1020"})

        assert isinstance(execute.call_args_list[0].args[1], QueryStateCommand)
        dialog_cls.assert_called_once()
        assert dialog_cls.call_args.args[1] == ["C3", "C4"]
        assert dialog_cls.call_args.kwargs["default_montage"] == "standard_1020"
        epoch_data.get_mne.assert_not_called()
        m.preprocess_controller.apply_montage.assert_not_called()
        m.chat_controller.add_user_message.assert_called_with("Montage Confirmed.")

    def test_real_study_montage_normalizes_dialog_position_lists(self):
        """Agent montage path should share the sidebar's command argument shape."""
        from XBrainLab.backend.study import Study

        m = _make_manager()
        m.study = Study()
        m.preprocess_controller = MagicMock()
        m.chat_panel.debug_mode = True
        epoch_data = MagicMock()
        epoch_data.get_channel_names.return_value = ["C3", "C4"]
        epoch_data.get_mne.return_value.info = {"ch_names": ["C3", "C4"]}
        m.study.epoch_data = epoch_data
        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = True
        mock_dialog.get_result.return_value = (
            ["C3", "C4"],
            [[0, 0, 0], [1, 0, 0]],
        )

        with patch(
            "XBrainLab.ui.components.agent_manager.PickMontageDialog",
            return_value=mock_dialog,
        ):
            m.open_montage_picker_dialog({"montage_name": "standard_1020"})

        epoch_data.set_channels.assert_called_once_with(
            ["C3", "C4"],
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)],
        )
        m.preprocess_controller.apply_montage.assert_not_called()

    def test_real_study_montage_rejects_malformed_position_vectors(self):
        """Malformed dialog output should not reach ApplicationService."""
        from XBrainLab.backend.application import (
            ApplyMontageCommand,
            ChangedState,
            CommandResult,
            QueryStateCommand,
        )
        from XBrainLab.backend.study import Study

        m = _make_manager()
        m.study = Study()
        status_bar = MagicMock()
        m.main_window.statusBar.return_value = status_bar
        epoch_data = MagicMock()
        epoch_data.get_channel_names.return_value = ["C3"]
        epoch_data.get_mne.return_value.info = {"ch_names": ["C3"]}
        m.study.epoch_data = epoch_data
        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = True
        mock_dialog.get_result.return_value = (["C3"], [[0.0, 0.0]])

        def execute_side_effect(_context, command, **_kwargs):
            if isinstance(command, QueryStateCommand):
                return CommandResult.success_result(
                    "query_state",
                    "Application state snapshot ready.",
                    state={},
                    changed_state=ChangedState(),
                    diagnostics={"state": {"epoch": {"channel_names": ["C3"]}}},
                )
            if isinstance(command, ApplyMontageCommand):
                raise AssertionError("Malformed positions must not apply montage")
            raise AssertionError(f"Unexpected command: {command!r}")

        with (
            patch(
                "XBrainLab.ui.components.agent_manager.PickMontageDialog",
                return_value=mock_dialog,
            ),
            patch(
                "XBrainLab.ui.components.agent_manager.execute_application_command",
                side_effect=execute_side_effect,
            ) as mock_execute,
        ):
            m.open_montage_picker_dialog({"montage_name": "standard_1020"})

        assert len(mock_execute.call_args_list) == 1
        assert isinstance(mock_execute.call_args_list[0].args[1], QueryStateCommand)
        epoch_data.set_channels.assert_not_called()
        status_bar.showMessage.assert_called_once_with(
            "Montage setup failed: Each montage position must contain x, y, z values."
        )

    def test_real_study_montage_refuses_controller_fallback(self):
        """Real Study montage must show a blocked message instead of fallback."""
        from XBrainLab.backend.study import Study

        m = _make_manager()
        m.study = Study()
        m.preprocess_controller = MagicMock()
        status_bar = MagicMock()
        m.main_window.statusBar.return_value = status_bar
        epoch_data = MagicMock()
        epoch_data.get_channel_names.return_value = ["C3", "C4"]
        epoch_data.get_mne.return_value.info = {"ch_names": ["C3", "C4"]}
        m.study.epoch_data = epoch_data
        mock_dialog = MagicMock()
        mock_dialog.exec.return_value = True
        mock_dialog.get_result.return_value = (
            ["C3", "C4"],
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)],
        )

        from XBrainLab.backend.application import (
            ApplyMontageCommand,
            ChangedState,
            CommandResult,
            QueryStateCommand,
        )

        def execute_side_effect(_context, command, **_kwargs):
            if isinstance(command, QueryStateCommand):
                return CommandResult.success_result(
                    "query_state",
                    "Application state snapshot ready.",
                    state={},
                    changed_state=ChangedState(),
                    diagnostics={
                        "state": {"epoch": {"channel_names": ["C3", "C4"]}},
                    },
                )
            if isinstance(command, ApplyMontageCommand):
                return None
            raise AssertionError(f"Unexpected command: {command!r}")

        with (
            patch(
                "XBrainLab.ui.components.agent_manager.PickMontageDialog",
                return_value=mock_dialog,
            ),
            patch(
                "XBrainLab.ui.components.agent_manager.execute_application_command",
                side_effect=execute_side_effect,
            ),
            patch.object(m, "handle_user_input") as mock_hui,
        ):
            m.open_montage_picker_dialog({"montage_name": "standard_1020"})

        m.preprocess_controller.apply_montage.assert_not_called()
        mock_hui.assert_called_once_with("Montage Selection Failed.")
        status_bar.showMessage.assert_called_once_with(
            "Montage setup blocked: XBrainLab could not safely complete this "
            "action from the current window state. Refresh the workflow and "
            "try again."
        )
        m.chat_controller.add_agent_message.assert_not_called()
