"""Coverage tests for AgentManager UI component interactions."""

from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QMainWindow

from XBrainLab.backend.application.capabilities import (
    CapabilityPolicy,
    CommandCapability,
)
from XBrainLab.backend.application.state import (
    ActiveDatasetSnapshot,
    ApplicationStateSnapshot,
)
from XBrainLab.backend.application.view_publication import (
    PUBLIC_VIEW_UNAVAILABLE_MESSAGE,
    ApplicationViewPublication,
)
from XBrainLab.backend.study import Study
from XBrainLab.llm.agent.assistant_activity import (
    AssistantTurnActivity,
    AssistantTurnActivityPhase,
)
from XBrainLab.llm.agent.confirmation import (
    AgentConfirmationRequest,
    AgentConfirmationResolution,
    AgentConfirmationResolutionStatus,
)
from XBrainLab.llm.agent.response_presentation import (
    AssistantPanelNavigationRequest,
    AssistantPanelTarget,
)
from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
    AssistantRuntimeSnapshot,
)
from XBrainLab.llm.agent.turn import AssistantTurnCorrelation
from XBrainLab.ui.components.assistant_runtime_lifecycle import (
    AssistantRuntimeLifecycle,
    RuntimeCommandAdmissionResult,
    RuntimeCommandAdmissionStatus,
)
from XBrainLab.ui.components.assistant_status_projection import (
    build_assistant_status_projection,
)


@pytest.fixture(autouse=True)
def _require_qapplication(qapp):
    """Keep QWidget-based coverage tests runnable in isolation."""
    return qapp


def _make_manager() -> Any:
    """Create a lightweight manager through its real QObject initialization."""
    from XBrainLab.ui.components.agent_manager import AgentManager

    main_window = cast(Any, QMainWindow())
    main_window.ai_btn = MagicMock()
    main_window.statusBar = MagicMock(return_value=MagicMock())
    study = MagicMock()
    application_service = MagicMock()
    runtime = MagicMock(spec=AssistantRuntimeLifecycle)
    runtime.controller = MagicMock()
    runtime.initialized = True
    runtime.current = AssistantRuntimeSnapshot(
        phase=AssistantRuntimePhase.IDLE,
        initialized=False,
    )
    runtime.active_local_runtime_blocks_model_deletion.return_value = False
    runtime.close.return_value = True
    runtime.submit.return_value = RuntimeCommandAdmissionResult(
        command_name="submit",
        status=RuntimeCommandAdmissionStatus.ACCEPTED,
    )
    with patch(
        "XBrainLab.ui.components.agent_manager.get_application_service",
        return_value=application_service,
    ):
        m = cast(
            Any,
            AgentManager(main_window, study, runtime_lifecycle=runtime),
        )
    m.chat_panel = MagicMock()
    m.chat_controller = MagicMock()
    m.application_service = application_service
    m.application_service.get_state.return_value = _empty_workflow_state()
    m.application_service.get_capabilities.return_value = {}
    m.application_service.get_view_publication.return_value = (
        ApplicationViewPublication(
            generation=1,
            state=cast(Any, _empty_workflow_state()),
            capabilities=CapabilityPolicy(capabilities={}),
        )
    )
    m.vram_checker = MagicMock()
    epoch_data = MagicMock()
    epoch_data.get_channel_names.return_value = ["Cz", "Fz"]
    epoch_data.get_mne.return_value.info = {"ch_names": ["Cz", "Fz"]}
    m.study.epoch_data = epoch_data
    return m


def _empty_workflow_state():
    return ApplicationStateSnapshot.empty()


def _own_confirmation(m: Any, request: AgentConfirmationRequest) -> None:
    """Bind one synthetic confirmation to the manager's exact active turn."""
    submission = m._assistant_turn_state.begin_submission()
    correlation = AssistantTurnCorrelation(
        generation=submission.generation,
        turn_id=1,
    )
    assert m._assistant_turn_state.accept_admission(submission, correlation)
    m._last_assistant_activity = AssistantTurnActivity(
        AssistantTurnActivityPhase.WAITING_FOR_DECISION,
        command_name=request.command_name,
        request_id=request.request_id,
        turn_id=correlation.turn_id,
        generation=correlation.generation,
    )


def test_agent_manager_does_not_fetch_preprocess_controller_from_real_study(qtbot):
    from XBrainLab.ui.components.agent_manager import AgentManager

    study = Study()
    study.get_controller = MagicMock(
        side_effect=AssertionError("real Study controller lookup is not allowed"),
    )
    main_window = QMainWindow()
    qtbot.addWidget(main_window)

    with patch(
        "XBrainLab.ui.components.agent_manager.get_application_service",
        return_value=MagicMock(),
    ):
        manager = AgentManager(main_window, study)

    study.get_controller.assert_not_called()
    assert not hasattr(manager, "preprocess_controller")


def test_agent_manager_delegates_atomic_workflow_status_projection() -> None:
    source = Path("XBrainLab/ui/components/agent_manager.py").read_text(
        encoding="utf-8",
    )

    assert "build_assistant_status_projection(publication)" in source
    assert "build_workflow_projection" not in source
    assert "_product_next_steps" not in source
    assert 'capabilities.get("train")' not in source
    assert "get_state()" not in source
    assert "get_capabilities()" not in source


class TestAgentManagerPrepareModelDeletion:
    """Cover prepare_model_deletion paths."""

    def test_no_controller(self):
        """L231-235: Returns True when no controller."""
        m = _make_manager()
        m._assistant_runtime.controller = None
        assert m.prepare_model_deletion("test") is True

    def test_no_engine(self):
        """L235: Returns True when engine not initialized."""
        m = _make_manager()
        assert m.prepare_model_deletion("test") is True

    def test_active_local_model_blocks_deletion(self):
        """Deletion should fail closed instead of auto-switching to Gemini."""
        m = _make_manager()
        m._assistant_runtime.active_local_runtime_blocks_model_deletion.return_value = (
            True
        )
        with patch("XBrainLab.ui.components.agent_manager.QMessageBox.warning"):
            assert m.prepare_model_deletion("test") is False

    def test_inference_mode_truth_blocks_deletion_even_if_active_mode_stale(self):
        m = _make_manager()
        m._assistant_runtime.active_local_runtime_blocks_model_deletion.return_value = (
            True
        )
        with patch("XBrainLab.ui.components.agent_manager.QMessageBox.warning"):
            assert m.prepare_model_deletion("test") is False


class TestAgentManagerStartSystem:
    """Cover start_system paths."""

    def test_already_initialized(self):
        """Returns early when already initialized."""
        m = _make_manager()
        m._assistant_runtime.initialized = True
        m.start_system()  # should return early

    def test_no_chat_panel(self):
        """L263: Returns early when no chat panel."""
        m = _make_manager()
        m._assistant_runtime.initialized = False
        m.chat_panel = None
        m.start_system()


class TestAgentManagerBackendStatus:
    def test_refresh_backend_status_hides_commands_when_publication_is_stale(self):
        m = _make_manager()
        status_messages: list[str] = []
        m.status_message_received.connect(status_messages.append)
        m.application_service.get_view_publication.return_value = (
            ApplicationViewPublication(
                generation=1,
                state=cast(Any, _empty_workflow_state()),
                capabilities=CapabilityPolicy(
                    capabilities={
                        "scan_source": CommandCapability(
                            command_name="scan_source",
                            enabled=True,
                        ),
                    }
                ),
                verified=True,
                stale=True,
                refresh_error="training state changed during snapshot",
            )
        )

        m.refresh_backend_status()

        m.chat_panel.set_product_status.assert_called_once_with(
            stage="Workflow status unavailable",
            model_status="Unknown",
            available_commands=[],
            tooltip=PUBLIC_VIEW_UNAVAILABLE_MESSAGE,
            blocked_reason=PUBLIC_VIEW_UNAVAILABLE_MESSAGE,
        )
        assert status_messages == ["Workflow status unavailable · Try again"]

    def test_refresh_backend_status_handles_missing_train_capability(self):
        m = _make_manager()
        m.application_service.get_view_publication.return_value = (
            ApplicationViewPublication(
                generation=1,
                state=cast(Any, _empty_workflow_state()),
                capabilities=CapabilityPolicy(
                    capabilities={
                        "scan_source": CommandCapability(
                            command_name="scan_source",
                            enabled=True,
                        ),
                    }
                ),
            )
        )
        m.refresh_backend_status()

        m.chat_panel.set_product_status.assert_called_once()
        kwargs = m.chat_panel.set_product_status.call_args.kwargs
        assert kwargs["stage"] == "No data loaded"
        assert kwargs["available_commands"] == ["scan_source"]
        assert kwargs["blocked_reason"] is None
        m.chat_panel.set_status_summary.assert_not_called()

    def test_product_next_steps_ignores_missing_candidate_capabilities(self):
        state = replace(
            _empty_workflow_state(),
            active_dataset=ActiveDatasetSnapshot(has_raw_data=True),
        )

        projection = build_assistant_status_projection(
            ApplicationViewPublication(
                generation=1,
                state=state,
                capabilities=CapabilityPolicy(capabilities={}),
            )
        )

        assert projection.available_commands == ()

    def test_footer_hint_uses_data_interpretation_language_without_commands(self):
        state = _empty_workflow_state()
        projection = build_assistant_status_projection(
            ApplicationViewPublication(
                generation=1,
                state=state,
                capabilities=CapabilityPolicy(capabilities={}),
            )
        )

        assert projection.footer_hint == "No EEG data open"


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


def test_agent_manager_has_no_product_execution_mode_bridge() -> None:
    manager = _make_manager()

    assert not hasattr(manager, "_on_execution_mode_changed")
    assert not hasattr(manager, "_sync_execution_mode_ui")


class TestAgentManagerHandlePanelNavigation:
    """Cover typed panel navigation dispatch."""

    def test_switch_panel(self):
        m = _make_manager()
        with patch.object(m, "_open_assistant_panel_target") as open_panel:
            m.handle_panel_navigation(
                AssistantPanelNavigationRequest(AssistantPanelTarget.TRAINING)
            )
        open_panel.assert_called_once_with(AssistantPanelTarget.TRAINING)

    def test_untyped_payload_is_not_dispatched(self):
        m = _make_manager()
        with patch.object(m, "_open_assistant_panel_target") as open_panel:
            m.handle_panel_navigation({"panel": "training"})
        open_panel.assert_not_called()


class TestShowActionConfirmation:
    """Cover the inline typed confirmation lifecycle."""

    def test_approved(self):
        """Present first; send approval only after the card resolves."""
        m = _make_manager()
        request = AgentConfirmationRequest.for_action(
            command_name="start_training",
            params={"lr": 0.01},
            action_label="Start training",
            description="Start training",
            destructive=False,
            publication_generation=4,
        )
        m._assistant_runtime.confirm.return_value = RuntimeCommandAdmissionResult(
            command_name="confirm",
            status=RuntimeCommandAdmissionStatus.ACCEPTED,
        )
        _own_confirmation(m, request)

        m._show_action_confirmation(request)

        m.chat_panel.show_confirmation_request.assert_called_once()
        m._assistant_runtime.confirm.assert_not_called()
        m._resolve_action_confirmation(
            AgentConfirmationResolution.for_request(
                request,
                status=AgentConfirmationResolutionStatus.APPROVED,
            )
        )

        resolution = m._assistant_runtime.confirm.call_args.args[0]
        assert isinstance(resolution, AgentConfirmationResolution)
        assert resolution.matches(request)
        assert resolution.status is AgentConfirmationResolutionStatus.APPROVED
        m.chat_panel.clear_confirmation_request.assert_called_once_with(
            request.request_id
        )
        m.chat_controller.add_agent_message.assert_not_called()

    def test_rejected(self):
        """Present first; send cancellation only after the card resolves."""
        m = _make_manager()
        request = AgentConfirmationRequest.for_action(
            command_name="clear_dataset",
            params={},
            action_label="Clear dataset",
            description="Clear the current dataset",
            destructive=True,
            publication_generation=5,
        )
        m._assistant_runtime.confirm.return_value = RuntimeCommandAdmissionResult(
            command_name="confirm",
            status=RuntimeCommandAdmissionStatus.ACCEPTED,
        )
        _own_confirmation(m, request)

        m._show_action_confirmation(request)

        m.chat_panel.show_confirmation_request.assert_called_once()
        m._assistant_runtime.confirm.assert_not_called()
        m._resolve_action_confirmation(
            AgentConfirmationResolution.for_request(
                request,
                status=AgentConfirmationResolutionStatus.CANCELLED,
            )
        )

        resolution = m._assistant_runtime.confirm.call_args.args[0]
        assert isinstance(resolution, AgentConfirmationResolution)
        assert resolution.matches(request)
        assert resolution.status is AgentConfirmationResolutionStatus.CANCELLED
        m.chat_panel.clear_confirmation_request.assert_called_once_with(
            request.request_id
        )
        m.chat_controller.add_agent_message.assert_not_called()
