"""Coverage tests for AgentManager - 129 uncovered lines."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast
from unittest.mock import MagicMock, call, patch

import pytest
from PyQt6.QtCore import QEvent, QObject, QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QMainWindow

from XBrainLab.backend.application.capabilities import build_capability_policy
from XBrainLab.backend.application.state import (
    ActiveDatasetSnapshot,
    ApplicationStateSnapshot,
)
from XBrainLab.backend.controller.chat_controller import (
    ChatController,
    ChatMessagePresentationKind,
    ChatPanelTarget,
    ChatResponseAction,
    ChatResponseActionKind,
    ChatResponseActionSelection,
)
from XBrainLab.llm.agent.assistant_activity import (
    AssistantAttentionKind,
    AssistantTurnActivity,
    AssistantTurnActivityPhase,
)
from XBrainLab.llm.agent.confirmation import (
    AgentConfirmationRequest,
    AgentConfirmationResolutionStatus,
)
from XBrainLab.llm.agent.response_presentation import (
    AssistantPanelNavigationRequest,
    AssistantPanelTarget,
    AssistantResponseAction,
    AssistantResponseKind,
    AssistantResponsePresentation,
    user_facing_generation_error,
)
from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
    AssistantRuntimeSnapshot,
)
from XBrainLab.llm.agent.turn import (
    AssistantDebugToolRequest,
    AssistantTurnCorrelation,
    AssistantTurnRequest,
    AssistantTurnTerminal,
)
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolution,
    WorkflowUiHandoffResolutionStatus,
)
from XBrainLab.llm.core.runtime_selection import (
    AssistantRuntimeSelectionFailure,
    AssistantRuntimeSelectionFailureCode,
)
from XBrainLab.ui.chat.message_bubble import MessageBubble
from XBrainLab.ui.chat.presentation import (
    ChatResponseActionSelectionView,
    ChatResponseActionView,
    ChatResponseActionViewKind,
    ChatResponsePanelTargetView,
    ChatTurnCancelability,
    ChatTurnPresentationPhase,
)
from XBrainLab.ui.chat.turn_state import AssistantUiTurnPhase
from XBrainLab.ui.components.assistant_runtime_lifecycle import (
    AssistantRuntimeLifecycle,
    RuntimeActivationResult,
    RuntimeActivationStatus,
    RuntimeCommandAdmissionResult,
    RuntimeCommandAdmissionStatus,
    RuntimeSetupAction,
    RuntimeSetupOutcome,
)


def _handoff_resolution(
    request: WorkflowUiHandoffRequest,
    status: WorkflowUiHandoffResolutionStatus,
) -> WorkflowUiHandoffResolution:
    return WorkflowUiHandoffResolution.for_request(
        request,
        status=status,
        message="Dialog outcome",
    )


def _admit_ui_turn(agent_mgr: Any, *, turn_id: int = 1) -> AssistantTurnCorrelation:
    submission = agent_mgr._assistant_turn_state.begin_submission()
    correlation = AssistantTurnCorrelation(
        generation=submission.generation,
        turn_id=turn_id,
    )
    assert agent_mgr._assistant_turn_state.accept_admission(
        submission,
        correlation,
    )
    return correlation


@pytest.fixture
def agent_mgr(qtbot) -> Any:
    with (
        patch("XBrainLab.ui.components.agent_manager.LLMController") as MockCtrl,
        patch("XBrainLab.ui.components.agent_manager.ChatController"),
        patch("XBrainLab.ui.components.agent_manager.ChatPanel"),
        patch("XBrainLab.ui.components.agent_manager.ModelSettingsDialog"),
    ):
        from XBrainLab.ui.components.agent_manager import AgentManager

        # main_window must be a real QWidget (parent in super().__init__)
        main_window = cast(Any, QMainWindow())
        main_window.ai_btn = MagicMock()
        qtbot.addWidget(main_window)

        study = MagicMock()
        study.get_controller.return_value = MagicMock()
        runtime = MagicMock(spec=AssistantRuntimeLifecycle)
        runtime.controller = MockCtrl.return_value
        runtime.initialized = False
        runtime.current = AssistantRuntimeSnapshot(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id="test-model",
        )
        runtime.switch_model.side_effect = lambda model_name: RuntimeActivationResult(
            RuntimeActivationStatus.SWITCHING,
            model_id=str(model_name),
        )
        runtime.submit.return_value = RuntimeCommandAdmissionResult(
            command_name="submit",
            status=RuntimeCommandAdmissionStatus.ACCEPTED,
            turn_id=1,
            generation=1,
        )
        runtime.debug.side_effect = (
            lambda _tool_name, _params, *, generation: RuntimeCommandAdmissionResult(
                command_name="debug",
                status=RuntimeCommandAdmissionStatus.ACCEPTED,
                turn_id=1,
                generation=generation,
            )
        )
        for method_name in (
            "stop_generation",
            "set_execution_mode",
            "reset_conversation",
            "confirm",
            "resolve_ui_handoff",
        ):
            getattr(runtime, method_name).return_value = RuntimeCommandAdmissionResult(
                command_name=method_name,
                status=RuntimeCommandAdmissionStatus.ACCEPTED,
            )
        runtime.close.return_value = True
        mgr = cast(
            Any,
            AgentManager(main_window, study, runtime_lifecycle=runtime),
        )
        runtime.stop_generation.side_effect = lambda: (
            RuntimeCommandAdmissionResult(
                command_name="stop_generation",
                status=RuntimeCommandAdmissionStatus.ACCEPTED,
                turn_id=(
                    mgr._assistant_turn_state.lease.turn_id
                    if mgr._assistant_turn_state.lease is not None
                    else None
                ),
                generation=(
                    mgr._assistant_turn_state.lease.generation
                    if mgr._assistant_turn_state.lease is not None
                    else None
                ),
            )
        )
        mgr.chat_controller.is_processing = False
        yield mgr


class TestAgentManagerInit:
    def test_creates_instance(self, agent_mgr):
        assert isinstance(agent_mgr, QObject)
        assert cast(Any, agent_mgr).study is not None

    def test_not_initialized_by_default(self, agent_mgr):
        assert not agent_mgr.agent_initialized


class TestAgentManagerMethods:
    def test_update_ai_btn_state(self, agent_mgr):
        agent_mgr.update_ai_btn_state(True)
        agent_mgr.main_window.ai_btn.setChecked.assert_called()

    def test_toggle_float_no_dock(self, agent_mgr):
        agent_mgr.chat_dock = None
        agent_mgr._place_floating_dock = MagicMock()

        agent_mgr._toggle_float()

        agent_mgr._place_floating_dock.assert_not_called()

    def test_handle_user_input(self, agent_mgr):
        agent_mgr.handle_user_input("hello")
        agent_mgr._assistant_runtime.submit.assert_called_once_with(
            "hello",
            generation=1,
        )

    def test_debug_request_uses_the_same_correlated_ui_admission(self, agent_mgr):
        agent_mgr.chat_panel = MagicMock()

        agent_mgr._handle_debug_tool_requested("inspect_state", {"scope": "dataset"})

        agent_mgr._assistant_runtime.debug.assert_called_once_with(
            "inspect_state",
            {"scope": "dataset"},
            generation=1,
        )
        lease = agent_mgr._assistant_turn_state.lease
        assert lease is not None
        assert lease == AssistantTurnCorrelation(generation=1, turn_id=1)

    def test_rejected_runtime_submission_does_not_enter_processing(self, agent_mgr):
        agent_mgr.chat_panel = MagicMock()
        agent_mgr._assistant_runtime.submit.return_value = (
            RuntimeCommandAdmissionResult(
                command_name="submit",
                status=RuntimeCommandAdmissionStatus.REJECTED,
                message="Assistant runtime is shutting down.",
            )
        )

        agent_mgr.handle_user_input("hello")

        agent_mgr.chat_controller.set_processing.assert_not_called()
        agent_mgr.chat_controller.add_user_message.assert_not_called()
        agent_mgr.chat_panel.show_notice.assert_called_once_with(
            "Assistant runtime is shutting down."
        )

    def test_runtime_phase_rejection_is_owned_by_lifecycle(self, agent_mgr):
        agent_mgr.chat_panel = MagicMock()
        agent_mgr._assistant_runtime.current = AssistantRuntimeSnapshot(
            phase=AssistantRuntimePhase.LOADING,
            initialized=False,
        )
        agent_mgr._assistant_runtime.submit.return_value = (
            RuntimeCommandAdmissionResult(
                command_name="submit",
                status=RuntimeCommandAdmissionStatus.REJECTED,
                message="Assistant runtime is loading.",
            )
        )

        agent_mgr.handle_user_input("request during loading")

        agent_mgr._assistant_runtime.submit.assert_called_once_with(
            "request during loading",
            generation=1,
        )
        agent_mgr.chat_controller.add_user_message.assert_not_called()
        agent_mgr.chat_panel.show_notice.assert_called_once_with(
            "Assistant runtime is loading."
        )

    def test_busy_admission_uses_runtime_truth_without_orphan_user_turn(
        self,
        agent_mgr,
    ):
        agent_mgr.chat_panel = MagicMock()
        agent_mgr.chat_controller.is_processing = False
        agent_mgr._assistant_runtime.submit.return_value = (
            RuntimeCommandAdmissionResult(
                command_name="submit",
                status=RuntimeCommandAdmissionStatus.BUSY,
                message="The assistant is still processing the previous request.",
            )
        )

        agent_mgr.handle_user_input("second request")

        agent_mgr._assistant_runtime.submit.assert_called_once_with(
            "second request",
            generation=1,
        )
        agent_mgr.chat_controller.add_user_message.assert_not_called()
        agent_mgr.chat_panel.show_notice.assert_called_once_with(
            "The assistant is still processing the previous request."
        )

    def test_stale_chat_processing_projection_cannot_reject_admitted_turn(
        self,
        agent_mgr,
    ):
        agent_mgr.chat_panel = MagicMock()
        agent_mgr.chat_controller.is_processing = True

        agent_mgr.handle_user_input("runtime-owned admission")

        agent_mgr._assistant_runtime.submit.assert_called_once_with(
            "runtime-owned admission",
            generation=1,
        )
        agent_mgr.chat_controller.add_user_message.assert_called_once_with(
            "runtime-owned admission"
        )

    def test_controller_wiring_fails_fast_when_core_signals_are_missing(
        self,
        agent_mgr,
    ):
        incomplete_controller = QObject()

        with pytest.raises(TypeError, match="core signal contract"):
            agent_mgr._wire_assistant_controller(incomplete_controller)

    def test_default_controller_factory_closes_incomplete_product_controller(
        self,
        agent_mgr,
    ):
        incomplete_controller = MagicMock()
        incomplete_controller.response_presentation_ready.connect = MagicMock()
        incomplete_controller.status_update.connect = MagicMock()
        incomplete_controller.activity_changed.connect = MagicMock()
        incomplete_controller.confirmation_requested.connect = MagicMock()
        incomplete_controller.panel_navigation_requested.connect = MagicMock()
        incomplete_controller.workflow_ui_handoff_requested = None
        incomplete_controller.application_command_completed.connect = MagicMock()
        incomplete_controller.application_command_started.connect = MagicMock()
        incomplete_controller.execution_mode_changed.connect = MagicMock()

        with (
            patch(
                "XBrainLab.ui.components.agent_manager.LLMController",
                return_value=incomplete_controller,
            ),
            pytest.raises(TypeError, match="workflow_ui_handoff_requested"),
        ):
            agent_mgr._create_assistant_controller(object())

        incomplete_controller.close.assert_called_once_with()

    def test_invalid_runtime_admission_does_not_leave_an_orphaned_user_turn(
        self,
        agent_mgr,
    ):
        agent_mgr.chat_panel = MagicMock()
        agent_mgr._assistant_runtime.submit.return_value = None

        agent_mgr.handle_user_input("hello")

        agent_mgr.chat_controller.add_user_message.assert_not_called()
        agent_mgr.chat_panel.show_notice.assert_called_once_with(
            "The assistant could not accept this request. Try again."
        )

    def test_typed_response_presentation_renders_message_and_actions(
        self,
        agent_mgr,
    ):
        agent_mgr.chat_panel = MagicMock()
        correlation = _admit_ui_turn(agent_mgr)
        presentation = AssistantResponsePresentation(
            text="Choose a next step.",
            correlation=correlation,
            kind=AssistantResponseKind.CLARIFICATION,
            actions=(
                AssistantResponseAction.open_panel(
                    "Open Dataset",
                    AssistantPanelTarget.DATASET,
                ),
            ),
        )

        agent_mgr._handle_response_presentation(presentation)

        expected_action = ChatResponseAction(
            action_id=presentation.actions[0].action_id,
            label="Open Dataset",
            kind=ChatResponseActionKind.OPEN_PANEL,
            panel=ChatPanelTarget.DATASET,
        )
        agent_mgr.chat_controller.add_agent_message.assert_called_once_with(
            presentation.text,
            presentation_kind=ChatMessagePresentationKind.CLARIFICATION,
            presentation_id=presentation.presentation_id,
            actions=(expected_action,),
        )
        agent_mgr.chat_panel.show_response_actions.assert_not_called()
        assert agent_mgr._active_response_presentation_id is None
        agent_mgr._on_active_response_presentation_changed(presentation.presentation_id)
        assert (
            agent_mgr._active_response_presentation_id == presentation.presentation_id
        )

    @pytest.mark.parametrize(
        "text",
        [
            "Request: review the imported EEG metadata.",
            '{"status": "ready", "summary": "Dataset is ready."}',
            '```json\n{"status": "ready"}\n```',
        ],
    )
    def test_typed_response_text_is_rendered_verbatim_without_raw_filtering(
        self,
        agent_mgr,
        text,
    ):
        agent_mgr.chat_panel = MagicMock()
        correlation = _admit_ui_turn(agent_mgr)
        presentation = AssistantResponsePresentation(
            text=text,
            correlation=correlation,
        )

        agent_mgr._handle_response_presentation(presentation)

        agent_mgr.chat_controller.add_agent_message.assert_called_once_with(
            text,
            presentation_kind=ChatMessagePresentationKind.ASSISTANT,
            presentation_id=presentation.presentation_id,
            actions=(),
        )
        agent_mgr.chat_panel.show_response_actions.assert_not_called()

    def test_invalid_typed_response_payload_is_not_rendered_or_reclassified(
        self,
        agent_mgr,
    ):
        agent_mgr.chat_panel = MagicMock()

        agent_mgr._handle_response_presentation(
            {"text": "Request: do not infer this payload"}
        )

        agent_mgr.chat_controller.add_agent_message.assert_not_called()
        agent_mgr.chat_panel.show_response_actions.assert_not_called()

    def test_retry_label_does_not_classify_a_blocked_response_as_error(
        self,
        agent_mgr,
    ) -> None:
        correlation = _admit_ui_turn(agent_mgr)
        presentation = AssistantResponsePresentation(
            text="Review the workflow before continuing.",
            correlation=correlation,
            kind=AssistantResponseKind.BLOCKED,
            actions=(
                AssistantResponseAction.send_message(
                    "Retry",
                    "Check the current workflow.",
                ),
            ),
        )

        agent_mgr._handle_response_presentation(presentation)

        assert (
            agent_mgr.chat_controller.add_agent_message.call_args.kwargs[
                "presentation_kind"
            ]
            is ChatMessagePresentationKind.ATTENTION
        )

    @pytest.mark.parametrize(
        "message",
        ["", "generation failed with arbitrary user-facing copy"],
    )
    def test_ambient_attention_never_rewrites_persisted_response_kind(
        self,
        agent_mgr,
        message,
    ) -> None:
        correlation = _admit_ui_turn(agent_mgr)
        presentation = AssistantResponsePresentation(
            text="The assistant could not complete the request.",
            correlation=correlation,
            kind=AssistantResponseKind.BLOCKED,
        )
        agent_mgr._handle_response_presentation(presentation)
        agent_mgr._on_active_response_presentation_changed(presentation.presentation_id)

        agent_mgr.on_assistant_activity_changed(
            AssistantTurnActivity(
                AssistantTurnActivityPhase.NEEDS_ATTENTION,
                message=message,
                turn_id=correlation.turn_id,
                generation=correlation.generation,
                attention_kind=AssistantAttentionKind.ERROR,
            )
        )

        agent_mgr.chat_controller.update_presentation_kind.assert_not_called()

    @pytest.mark.parametrize("text", ["Short failure.", "Completely different copy."])
    def test_error_response_kind_is_message_invariant(self, agent_mgr, text) -> None:
        correlation = _admit_ui_turn(agent_mgr)
        agent_mgr._handle_response_presentation(
            AssistantResponsePresentation(
                text=text,
                correlation=correlation,
                kind=AssistantResponseKind.ERROR,
            )
        )

        assert (
            agent_mgr.chat_controller.add_agent_message.call_args.kwargs[
                "presentation_kind"
            ]
            is ChatMessagePresentationKind.ERROR
        )

    @pytest.mark.parametrize(
        ("ambient_phase", "response_kind", "expected_kind"),
        [
            (
                AssistantTurnActivityPhase.RUNNING_COMMAND,
                AssistantResponseKind.MESSAGE,
                ChatMessagePresentationKind.ASSISTANT,
            ),
            (
                AssistantTurnActivityPhase.THINKING,
                AssistantResponseKind.CANCELLED,
                ChatMessagePresentationKind.CANCELLED,
            ),
        ],
    )
    def test_response_kind_is_not_inferred_from_stale_or_next_turn_activity(
        self,
        agent_mgr,
        ambient_phase,
        response_kind,
        expected_kind,
    ) -> None:
        agent_mgr.chat_panel = MagicMock()
        correlation = _admit_ui_turn(agent_mgr, turn_id=901)
        agent_mgr.on_assistant_activity_changed(
            AssistantTurnActivity(
                ambient_phase,
                command_name=(
                    "create_epoch"
                    if ambient_phase is AssistantTurnActivityPhase.RUNNING_COMMAND
                    else ""
                ),
                turn_id=correlation.turn_id,
                generation=correlation.generation,
            )
        )

        agent_mgr._handle_response_presentation(
            AssistantResponsePresentation(
                text="Persist this response using only its own typed kind.",
                correlation=correlation,
                kind=response_kind,
            )
        )

        assert (
            agent_mgr.chat_controller.add_agent_message.call_args.kwargs[
                "presentation_kind"
            ]
            is expected_kind
        )

    def test_response_action_selection_is_correlated_and_bounded(self, agent_mgr):
        action = ChatResponseAction(
            action_id="open-dataset",
            label="Open Dataset",
            kind=ChatResponseActionKind.OPEN_PANEL,
            panel=ChatPanelTarget.DATASET,
        )
        presentation_id = "response-open-dataset"
        agent_mgr._on_active_response_presentation_changed(presentation_id)
        agent_mgr.main_window.switch_page = MagicMock()
        agent_mgr.chat_controller.resolve_and_consume_response_action.return_value = (
            action
        )

        agent_mgr._handle_response_action_selection(
            ChatResponseActionSelectionView(
                presentation_id=presentation_id,
                action=ChatResponseActionView(
                    action_id=action.action_id,
                    label=action.label,
                    kind=ChatResponseActionViewKind.OPEN_PANEL,
                    panel=ChatResponsePanelTargetView.DATASET,
                ),
            )
        )

        agent_mgr.main_window.switch_page.assert_called_once_with(0)
        selection = agent_mgr.chat_controller.resolve_and_consume_response_action.call_args.args[
            0
        ]
        assert selection == ChatResponseActionSelection.from_action(
            presentation_id,
            action,
        )
        assert agent_mgr._active_response_presentation_id is None

        agent_mgr._on_active_response_presentation_changed(presentation_id)
        agent_mgr.main_window.switch_page.reset_mock()
        agent_mgr._handle_response_action_selection(
            ChatResponseActionSelectionView(
                presentation_id="stale-presentation",
                action=ChatResponseActionView(
                    action_id=action.action_id,
                    label=action.label,
                    kind=ChatResponseActionViewKind.OPEN_PANEL,
                    panel=ChatResponsePanelTargetView.DATASET,
                ),
            )
        )
        agent_mgr.main_window.switch_page.assert_not_called()

    def test_panel_navigation_defers_sub_view_until_materialization(self, agent_mgr):
        callbacks = []

        def _switch_page(index, *, on_ready=None):
            assert index == 4
            callbacks.append(on_ready)
            return False

        agent_mgr.main_window.switch_page = MagicMock(side_effect=_switch_page)
        agent_mgr._switch_sub_view = MagicMock()

        agent_mgr.handle_panel_navigation(
            AssistantPanelNavigationRequest(
                AssistantPanelTarget.VISUALIZATION,
                view_mode="3d_plot",
            )
        )

        agent_mgr._switch_sub_view.assert_not_called()
        assert agent_mgr.main_window.statusBar().currentMessage() == (
            "Opening Visualization..."
        )
        assert len(callbacks) == 1
        assert callbacks[0] is not None

        callbacks[0](object())

        agent_mgr._switch_sub_view.assert_called_once_with(4, "3d_plot")
        assert agent_mgr.main_window.statusBar().currentMessage() == (
            "Visualization is open."
        )

    def test_send_message_response_action_reenters_normal_input_path(self, agent_mgr):
        action = ChatResponseAction(
            action_id="check-workflow",
            label="Check workflow",
            kind=ChatResponseActionKind.SEND_MESSAGE,
            prompt="Check what is ready now.",
        )
        presentation_id = "response-check-workflow"
        agent_mgr._on_active_response_presentation_changed(presentation_id)
        agent_mgr.handle_user_input = MagicMock()
        agent_mgr.chat_controller.resolve_and_consume_response_action.return_value = (
            action
        )

        agent_mgr._handle_response_action_selection(
            ChatResponseActionSelectionView(
                presentation_id=presentation_id,
                action=ChatResponseActionView(
                    action_id=action.action_id,
                    label=action.label,
                    kind=ChatResponseActionViewKind.SEND_MESSAGE,
                    prompt=action.prompt,
                ),
            )
        )

        agent_mgr.handle_user_input.assert_called_once_with(action.prompt)

    def test_manager_never_executes_forged_payload_even_with_valid_action_id(
        self,
        agent_mgr,
    ) -> None:
        controller = ChatController()
        canonical = ChatResponseAction(
            action_id="open-dataset",
            label="Open Dataset",
            kind=ChatResponseActionKind.OPEN_PANEL,
            panel=ChatPanelTarget.DATASET,
        )
        controller.add_agent_message(
            "Choose a next step.",
            presentation_id="presentation-1",
            actions=(canonical,),
        )
        agent_mgr.chat_controller = controller
        agent_mgr._on_active_response_presentation_changed("presentation-1")
        agent_mgr.main_window.switch_page = MagicMock()

        agent_mgr._handle_response_action_selection(
            ChatResponseActionSelectionView(
                presentation_id="presentation-1",
                action=ChatResponseActionView(
                    action_id="open-dataset",
                    label="Open Dataset",
                    kind=ChatResponseActionViewKind.OPEN_PANEL,
                    panel=ChatResponsePanelTargetView.TRAINING,
                ),
            )
        )

        agent_mgr.main_window.switch_page.assert_not_called()
        assert controller.get_typed_history()[0].has_active_actions

    def test_restored_open_panel_action_is_inert_audit_history(
        self,
        agent_mgr,
    ) -> None:
        action = ChatResponseAction(
            action_id="open-dataset",
            label="Open Dataset",
            kind=ChatResponseActionKind.OPEN_PANEL,
            panel=ChatPanelTarget.DATASET,
        )
        source = ChatController()
        source.add_agent_message(
            "Review the imported data.",
            presentation_id="restored-open-panel",
            actions=(action,),
        )
        restored = ChatController()
        assert restored.restore_history(source.get_history()) == 1
        agent_mgr.chat_controller = restored
        agent_mgr._on_active_response_presentation_changed("restored-open-panel")
        agent_mgr.main_window.switch_page = MagicMock()
        selection = ChatResponseActionSelectionView(
            presentation_id="restored-open-panel",
            action=ChatResponseActionView(
                action_id=action.action_id,
                label=action.label,
                kind=ChatResponseActionViewKind.OPEN_PANEL,
                panel=ChatResponsePanelTargetView.DATASET,
            ),
        )

        agent_mgr._handle_response_action_selection(selection)

        agent_mgr.main_window.switch_page.assert_not_called()
        assert restored.get_typed_history()[0].action_state.value == "consumed"

    def test_restored_send_message_action_cannot_start_a_new_turn(
        self,
        agent_mgr,
    ) -> None:
        action = ChatResponseAction(
            action_id="check-workflow",
            label="Check workflow",
            kind=ChatResponseActionKind.SEND_MESSAGE,
            prompt="Check what is ready now.",
        )
        source = ChatController()
        source.add_agent_message(
            "Choose a next step.",
            presentation_id="restored-send-message",
            actions=(action,),
        )
        restored = ChatController()
        assert restored.restore_history(source.get_history()) == 1
        agent_mgr.chat_controller = restored
        agent_mgr._on_active_response_presentation_changed("restored-send-message")
        agent_mgr._handle_response_action_selection(
            ChatResponseActionSelectionView(
                presentation_id="restored-send-message",
                action=ChatResponseActionView(
                    action_id=action.action_id,
                    label=action.label,
                    kind=ChatResponseActionViewKind.SEND_MESSAGE,
                    prompt=action.prompt,
                ),
            )
        )
        agent_mgr._assistant_runtime.submit.assert_not_called()
        assert agent_mgr._assistant_turn_state.lease is None
        records = restored.get_typed_history()
        assert records[0].action_state.value == "consumed"
        assert [record.content for record in records] == ["Choose a next step."]

    @pytest.mark.parametrize(
        ("existing_rows", "accepted"),
        [(498, True), (499, False), (500, False)],
    )
    def test_turn_admission_reserves_user_and_terminal_history_rows_before_runtime(
        self,
        agent_mgr,
        existing_rows: int,
        accepted: bool,
    ) -> None:
        controller = ChatController()
        for index in range(existing_rows):
            controller.add_user_message(f"History row {index}")
        agent_mgr.chat_controller = controller
        agent_mgr.chat_panel = MagicMock()
        agent_mgr._assistant_runtime.submit.reset_mock()

        agent_mgr.handle_user_input("Run the next safe step")

        if not accepted:
            agent_mgr._assistant_runtime.submit.assert_not_called()
            assert agent_mgr._assistant_turn_state.lease is None
            assert agent_mgr._assistant_turn_state.submission is None
            assert len(controller.get_typed_history()) == existing_rows
            agent_mgr.chat_panel.show_notice.assert_called_once_with(
                "Chat history is full. Clear the conversation before sending "
                "another request."
            )
            return

        agent_mgr._assistant_runtime.submit.assert_called_once_with(
            "Run the next safe step",
            generation=1,
        )
        correlation = agent_mgr._assistant_turn_state.lease
        assert correlation is not None
        agent_mgr._handle_response_presentation(
            AssistantResponsePresentation(
                correlation=correlation,
                text="The next safe step is ready.",
            )
        )
        assert len(controller.get_typed_history()) == 500

    @pytest.mark.parametrize("attempt", range(10))
    def test_stopping_turn_rejects_late_action_response_and_clears_existing_actions(
        self,
        agent_mgr,
        attempt: int,
    ) -> None:
        del attempt
        controller = ChatController()
        agent_mgr.chat_controller = controller
        agent_mgr.chat_panel = MagicMock()
        correlation = _admit_ui_turn(agent_mgr, turn_id=91)
        first = AssistantResponsePresentation(
            correlation=correlation,
            text="Choose a next step.",
            kind=AssistantResponseKind.CLARIFICATION,
            actions=(
                AssistantResponseAction.open_panel(
                    "Open Dataset",
                    AssistantPanelTarget.DATASET,
                ),
            ),
        )
        agent_mgr._handle_response_presentation(first)
        assert controller.get_typed_history()[-1].has_active_actions

        agent_mgr.stop_generation()
        late = AssistantResponsePresentation(
            correlation=correlation,
            text="This response arrived after Stop.",
            actions=(
                AssistantResponseAction.open_panel(
                    "Open Training",
                    AssistantPanelTarget.TRAINING,
                ),
            ),
        )
        agent_mgr._handle_response_presentation(late)
        agent_mgr._on_assistant_turn_finished(
            AssistantTurnTerminal(correlation=correlation, outcome="cancelled")
        )

        records = controller.get_typed_history()
        assert [record.content for record in records] == ["Choose a next step."]
        assert records[0].has_active_actions is False
        agent_mgr.chat_panel.clear_response_actions.assert_called()

    def test_stop_generation(self, agent_mgr):
        agent_mgr.chat_panel = MagicMock()
        _admit_ui_turn(agent_mgr)
        agent_mgr.stop_generation()
        agent_mgr._assistant_runtime.stop_generation.assert_called_once()
        agent_mgr.chat_controller.set_processing.assert_not_called()
        presentation = agent_mgr.chat_panel.set_turn_activity.call_args.args[0]
        assert presentation.phase is ChatTurnPresentationPhase.STOPPING
        assert presentation.cancelability is ChatTurnCancelability.STOPPING

    def test_stop_latch_ignores_late_activity_until_matching_terminal(
        self,
        agent_mgr,
    ) -> None:
        agent_mgr.chat_panel = MagicMock()
        agent_mgr._assistant_runtime.submit.return_value = (
            RuntimeCommandAdmissionResult(
                command_name="submit",
                status=RuntimeCommandAdmissionStatus.ACCEPTED,
                turn_id=41,
                generation=1,
            )
        )
        agent_mgr.handle_user_input("inspect the current workflow")
        agent_mgr.on_assistant_activity_changed(
            AssistantTurnActivity(
                AssistantTurnActivityPhase.THINKING,
                turn_id=41,
                generation=1,
            )
        )

        agent_mgr.stop_generation()
        stopping = agent_mgr.chat_panel.set_turn_activity.call_args.args[0]
        assert stopping.phase is ChatTurnPresentationPhase.STOPPING

        for phase in (
            AssistantTurnActivityPhase.THINKING,
            AssistantTurnActivityPhase.RUNNING_COMMAND,
        ):
            agent_mgr.on_assistant_activity_changed(
                AssistantTurnActivity(
                    phase,
                    turn_id=41,
                    generation=1,
                    command_name=(
                        "create_epoch" if phase.name == "RUNNING_COMMAND" else ""
                    ),
                )
            )
            still_stopping = agent_mgr.chat_panel.set_turn_activity.call_args.args[0]
            assert still_stopping.phase is ChatTurnPresentationPhase.STOPPING
            assert still_stopping.cancelability is ChatTurnCancelability.STOPPING

        agent_mgr._on_assistant_turn_finished(
            AssistantTurnTerminal(
                correlation=AssistantTurnCorrelation(generation=1, turn_id=40)
            )
        )
        still_stopping = agent_mgr.chat_panel.set_turn_activity.call_args.args[0]
        assert still_stopping.phase is ChatTurnPresentationPhase.STOPPING

        agent_mgr._on_assistant_turn_finished(
            AssistantTurnTerminal(
                correlation=AssistantTurnCorrelation(generation=1, turn_id=41),
                outcome="cancelled",
            )
        )
        terminal = agent_mgr.chat_panel.set_turn_activity.call_args.args[0]
        assert terminal.phase is ChatTurnPresentationPhase.IDLE

        agent_mgr._assistant_runtime.submit.return_value = (
            RuntimeCommandAdmissionResult(
                command_name="submit",
                status=RuntimeCommandAdmissionStatus.ACCEPTED,
                turn_id=42,
                generation=2,
            )
        )
        agent_mgr.handle_user_input("start a legitimate new turn")
        agent_mgr.on_assistant_activity_changed(
            AssistantTurnActivity(
                AssistantTurnActivityPhase.THINKING,
                turn_id=42,
                generation=2,
            )
        )
        new_turn = agent_mgr.chat_panel.set_turn_activity.call_args.args[0]
        assert new_turn.phase is ChatTurnPresentationPhase.WORKING
        assert new_turn.cancelability is ChatTurnCancelability.CANCELLABLE

    def test_new_admitted_generation_supersedes_an_older_stop_latch(
        self,
        agent_mgr,
    ) -> None:
        agent_mgr.chat_panel = MagicMock()
        agent_mgr._assistant_runtime.submit.return_value = (
            RuntimeCommandAdmissionResult(
                command_name="submit",
                status=RuntimeCommandAdmissionStatus.ACCEPTED,
                turn_id=60,
                generation=1,
            )
        )
        agent_mgr.handle_user_input("first turn")
        agent_mgr.stop_generation()

        agent_mgr._assistant_runtime.submit.return_value = (
            RuntimeCommandAdmissionResult(
                command_name="submit",
                status=RuntimeCommandAdmissionStatus.ACCEPTED,
                turn_id=61,
                generation=2,
            )
        )
        agent_mgr.handle_user_input("replacement turn")
        agent_mgr.on_assistant_activity_changed(
            AssistantTurnActivity(
                AssistantTurnActivityPhase.THINKING,
                turn_id=61,
                generation=2,
            )
        )
        agent_mgr.on_assistant_activity_changed(
            AssistantTurnActivity(
                AssistantTurnActivityPhase.RUNNING_COMMAND,
                command_name="create_epoch",
                turn_id=60,
                generation=1,
            )
        )

        presentation = agent_mgr.chat_panel.set_turn_activity.call_args.args[0]
        assert presentation.phase is ChatTurnPresentationPhase.WORKING
        assert presentation.cancelability is ChatTurnCancelability.CANCELLABLE

    def test_rejected_provisional_activity_cannot_clear_existing_stop(
        self,
        agent_mgr,
    ) -> None:
        agent_mgr.chat_panel = MagicMock()
        active = _admit_ui_turn(agent_mgr, turn_id=70)
        agent_mgr.stop_generation()

        def reject_after_late_activity(_text: str, *, generation: int):
            agent_mgr.on_assistant_activity_changed(
                AssistantTurnActivity(
                    AssistantTurnActivityPhase.THINKING,
                    turn_id=71,
                    generation=generation,
                )
            )
            return RuntimeCommandAdmissionResult(
                command_name="submit",
                status=RuntimeCommandAdmissionStatus.BUSY,
                message="The stopped turn is still terminating.",
            )

        agent_mgr._assistant_runtime.submit.side_effect = reject_after_late_activity
        agent_mgr.handle_user_input("must remain blocked")

        assert agent_mgr._assistant_turn_state.phase is AssistantUiTurnPhase.STOPPING
        assert agent_mgr._assistant_turn_state.lease == active
        visible = agent_mgr.chat_panel.set_turn_activity.call_args.args[0]
        assert visible.phase is ChatTurnPresentationPhase.STOPPING

    def test_synchronous_admission_events_replay_in_original_order(
        self,
        agent_mgr,
    ) -> None:
        agent_mgr.chat_panel = MagicMock()
        agent_mgr.chat_controller.is_processing = False
        agent_mgr.chat_controller.set_processing.side_effect = lambda state: setattr(
            agent_mgr.chat_controller,
            "is_processing",
            state,
        )

        def complete_during_submit(_text: str, *, generation: int):
            correlation = AssistantTurnCorrelation(
                generation=generation,
                turn_id=73,
            )
            agent_mgr.on_assistant_activity_changed(
                AssistantTurnActivity(
                    AssistantTurnActivityPhase.PREPARING,
                    turn_id=correlation.turn_id,
                    generation=correlation.generation,
                )
            )
            agent_mgr._handle_response_presentation(
                AssistantResponsePresentation(
                    correlation=correlation,
                    text="The synchronous turn completed.",
                )
            )
            agent_mgr._on_assistant_turn_finished(
                AssistantTurnTerminal(correlation=correlation)
            )
            return RuntimeCommandAdmissionResult(
                command_name="submit",
                status=RuntimeCommandAdmissionStatus.ACCEPTED,
                turn_id=correlation.turn_id,
                generation=correlation.generation,
            )

        agent_mgr._assistant_runtime.submit.side_effect = complete_during_submit

        agent_mgr.handle_user_input("complete synchronously")

        agent_mgr.chat_controller.add_user_message.assert_called_once_with(
            "complete synchronously"
        )
        agent_mgr.chat_controller.add_agent_message.assert_called_once()
        assert agent_mgr._assistant_turn_state.phase is AssistantUiTurnPhase.IDLE
        assert agent_mgr._assistant_turn_state.lease is None
        assert agent_mgr.chat_controller.set_processing.call_args_list == [
            call(True),
            call(False),
        ]

    def test_superseded_admission_preserves_newer_submission_without_transcript(
        self,
        agent_mgr,
    ) -> None:
        agent_mgr.chat_panel = MagicMock()
        newer_submission = None

        def supersede_during_submit(_text: str, *, generation: int):
            nonlocal newer_submission
            newer_submission = agent_mgr._assistant_turn_state.begin_submission()
            return RuntimeCommandAdmissionResult(
                command_name="submit",
                status=RuntimeCommandAdmissionStatus.ACCEPTED,
                turn_id=74,
                generation=generation,
            )

        agent_mgr._assistant_runtime.submit.side_effect = supersede_during_submit

        agent_mgr.handle_user_input("stale accepted admission")

        assert agent_mgr._assistant_turn_state.submission == newer_submission
        assert agent_mgr._assistant_turn_state.lease is None
        agent_mgr.chat_controller.add_user_message.assert_not_called()
        agent_mgr.chat_panel.show_notice.assert_called_once_with(
            "The assistant could not correlate this request. Try again."
        )

    def test_double_stop_is_idempotent_at_manager_boundary(self, agent_mgr) -> None:
        agent_mgr.chat_panel = MagicMock()
        _admit_ui_turn(agent_mgr, turn_id=72)

        agent_mgr.stop_generation()
        agent_mgr.stop_generation()

        agent_mgr._assistant_runtime.stop_generation.assert_called_once_with()
        assert agent_mgr._assistant_turn_state.phase is AssistantUiTurnPhase.STOPPING

    def test_synchronous_stopping_activity_completes_stop_admission_once(
        self,
        agent_mgr,
    ) -> None:
        agent_mgr.chat_panel = MagicMock()
        correlation = _admit_ui_turn(agent_mgr, turn_id=75)
        agent_mgr._workflow_ui_handoff_host.abandon_active = MagicMock()

        def emit_stopping_before_admission_returns():
            agent_mgr.on_assistant_activity_changed(
                AssistantTurnActivity(
                    AssistantTurnActivityPhase.STOPPING,
                    turn_id=correlation.turn_id,
                    generation=correlation.generation,
                )
            )
            return RuntimeCommandAdmissionResult(
                command_name="stop_generation",
                status=RuntimeCommandAdmissionStatus.ACCEPTED,
                turn_id=correlation.turn_id,
                generation=correlation.generation,
            )

        agent_mgr._assistant_runtime.stop_generation.side_effect = (
            emit_stopping_before_admission_returns
        )

        agent_mgr.stop_generation()

        assert agent_mgr._assistant_turn_state.phase is AssistantUiTurnPhase.STOPPING
        agent_mgr._workflow_ui_handoff_host.abandon_active.assert_called_once_with()
        visible = agent_mgr.chat_panel.set_turn_activity.call_args.args[0]
        assert visible.phase is ChatTurnPresentationPhase.STOPPING

    def test_late_response_cannot_render_into_reused_runtime_turn_id(
        self,
        agent_mgr,
    ) -> None:
        first = _admit_ui_turn(agent_mgr, turn_id=80)
        late = AssistantResponsePresentation(
            text="Late response from the previous generation.",
            correlation=first,
        )
        agent_mgr._on_assistant_turn_finished(AssistantTurnTerminal(correlation=first))
        second = _admit_ui_turn(agent_mgr, turn_id=80)

        agent_mgr._handle_response_presentation(late)
        agent_mgr.on_assistant_activity_changed(
            AssistantTurnActivity(
                AssistantTurnActivityPhase.THINKING,
                turn_id=second.turn_id,
                generation=second.generation,
            )
        )

        agent_mgr.chat_controller.add_agent_message.assert_not_called()
        assert agent_mgr._assistant_turn_state.lease == second

    def test_stop_does_not_claim_to_cancel_an_active_application_command(
        self,
        agent_mgr,
    ):
        agent_mgr.chat_panel = MagicMock()
        agent_mgr._workflow_ui_handoff_host.abandon_active = MagicMock()
        with patch(
            "XBrainLab.ui.components.agent_manager.begin_command_refresh_suppression"
        ):
            agent_mgr._on_application_command_started()

        agent_mgr.stop_generation()

        agent_mgr._assistant_runtime.stop_generation.assert_not_called()
        agent_mgr._workflow_ui_handoff_host.abandon_active.assert_not_called()
        agent_mgr.chat_panel.show_notice.assert_called_once_with(
            "This action has already started and cannot be stopped safely. "
            "Wait for it to finish."
        )

    def test_stop_returns_to_normal_after_application_command_finishes(
        self,
        agent_mgr,
    ):
        with (
            patch(
                "XBrainLab.ui.components.agent_manager.begin_command_refresh_suppression"
            ),
            patch(
                "XBrainLab.ui.components.agent_manager."
                "complete_command_refresh_suppression"
            ),
        ):
            agent_mgr._on_application_command_started()
            agent_mgr._on_application_command_completed(MagicMock())

        agent_mgr.stop_generation()

        agent_mgr._assistant_runtime.stop_generation.assert_called_once()

    def test_set_model(self, agent_mgr):
        agent_mgr.set_model("Gemini")
        agent_mgr._assistant_runtime.switch_model.assert_called_once_with("Gemini")

    def test_set_model_preserves_approved_local_model_identifier(self, agent_mgr):
        with patch(
            "XBrainLab.ui.components.agent_manager.LLMConfig.allowed_local_model_ids",
            return_value=["model-a", "model-b"],
        ):
            agent_mgr.set_model("model-b")

        agent_mgr._assistant_runtime.switch_model.assert_called_once_with("model-b")

    def test_new_chat_resets_only_conversation_state(self, agent_mgr):
        agent_mgr.chat_panel = MagicMock()
        application_service = MagicMock()
        agent_mgr.application_service = application_service
        agent_mgr.study.reset_mock()

        agent_mgr.start_new_conversation()

        agent_mgr.chat_controller.clear_conversation.assert_called_once_with()
        agent_mgr._assistant_runtime.reset_conversation.assert_called_once_with()
        application_service.execute.assert_not_called()
        assert agent_mgr.study.mock_calls == []

    def test_new_chat_does_not_clear_transcript_when_runtime_turn_is_busy(
        self,
        agent_mgr,
    ):
        agent_mgr.chat_panel = MagicMock()
        agent_mgr._last_user_input = "active request"
        agent_mgr._assistant_runtime.reset_conversation.return_value = (
            RuntimeCommandAdmissionResult(
                command_name="reset",
                status=RuntimeCommandAdmissionStatus.BUSY,
                message="The assistant is still processing the previous request.",
            )
        )

        agent_mgr.start_new_conversation()

        agent_mgr.chat_controller.clear_conversation.assert_not_called()
        assert agent_mgr._last_user_input == "active request"
        agent_mgr.chat_panel.show_notice.assert_called_once_with(
            "The assistant is still processing the previous request."
        )

    def test_new_chat_preserves_real_application_workflow_snapshot(self, qtbot):
        from XBrainLab.backend.study import Study
        from XBrainLab.ui.components.agent_manager import AgentManager

        main_window = cast(Any, QMainWindow())
        main_window.ai_btn = MagicMock()
        qtbot.addWidget(main_window)
        runtime = MagicMock(spec=AssistantRuntimeLifecycle)
        runtime.controller = MagicMock()
        runtime.current = AssistantRuntimeSnapshot(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id="test-model",
        )
        runtime.close.return_value = True
        manager = cast(
            Any,
            AgentManager(main_window, Study(), runtime_lifecycle=runtime),
        )
        manager.chat_panel = MagicMock()
        before = manager.application_service.get_view_publication()

        manager.start_new_conversation()

        after = manager.application_service.get_view_publication()
        assert after.generation == before.generation
        assert after.state == before.state
        runtime.reset_conversation.assert_called_once_with()

    def test_start_new_conversation_restores_runtime_setup_blocker(self, agent_mgr):
        agent_mgr.chat_panel = MagicMock()
        agent_mgr._assistant_runtime.current = AssistantRuntimeSnapshot(
            phase=AssistantRuntimePhase.FAILED,
            initialized=False,
            error="Local model is missing",
        )
        agent_mgr.chat_controller.add_agent_message.reset_mock()

        agent_mgr.start_new_conversation()

        agent_mgr.chat_panel.show_runtime_notice.assert_called_once()
        visible = agent_mgr.chat_panel.show_runtime_notice.call_args.args[0]
        assert "Assistant unavailable" in visible
        assert "settings" in visible

    def test_new_conversation_never_replays_raw_runtime_failure(self, agent_mgr):
        agent_mgr.chat_panel = MagicMock()
        raw = (
            "Traceback (most recent call last): File /private/runtime.py "
            "RuntimeError: secret-token-123"
        )
        agent_mgr._assistant_runtime.current = AssistantRuntimeSnapshot(
            phase=AssistantRuntimePhase.FAILED,
            initialized=False,
            error=raw,
        )
        agent_mgr.chat_controller.add_agent_message.reset_mock()

        agent_mgr.start_new_conversation()

        visible = agent_mgr.chat_panel.show_runtime_notice.call_args.args[0]
        assert "Assistant unavailable" in visible
        assert "Traceback" not in visible
        assert "RuntimeError" not in visible
        assert "/private/runtime.py" not in visible
        assert "secret-token-123" not in visible

    def test_failed_runtime_snapshot_is_sanitized_before_status_render(self, agent_mgr):
        agent_mgr.chat_panel = MagicMock()
        raw = "ValueError: secret-token-123 at /private/cache/model.bin"

        agent_mgr._render_assistant_runtime(
            AssistantRuntimeSnapshot(
                phase=AssistantRuntimePhase.FAILED,
                initialized=False,
                error=raw,
            )
        )

        phase, visible = agent_mgr.chat_panel.set_runtime_state.call_args.args
        assert phase == "failed"
        assert visible
        assert "ValueError" not in visible
        assert "secret-token-123" not in visible
        assert "/private/cache" not in visible

    @pytest.mark.parametrize(
        "raw_status",
        [
            "Thinking...",
            "Executing: create_epoch...",
            "Waiting for confirmation: train",
            "Stopping...",
            "Failed while executing but waiting for confirmation",
        ],
    )
    def test_raw_status_text_cannot_control_workflow_ui(
        self,
        agent_mgr,
        raw_status,
    ):
        agent_mgr.chat_panel = MagicMock()
        agent_mgr._execution_mode = "multi"

        agent_mgr.on_agent_status_update(raw_status)

        agent_mgr.chat_panel.set_workflow_status.assert_not_called()

    @pytest.mark.parametrize(
        ("activity", "expected_phase", "expected_cancelability"),
        [
            (
                AssistantTurnActivity(AssistantTurnActivityPhase.THINKING),
                ChatTurnPresentationPhase.WORKING,
                ChatTurnCancelability.CANCELLABLE,
            ),
            (
                AssistantTurnActivity(
                    AssistantTurnActivityPhase.RUNNING_COMMAND,
                    command_name="create_epoch",
                ),
                ChatTurnPresentationPhase.APPLICATION_COMMAND,
                ChatTurnCancelability.NOT_CANCELLABLE,
            ),
            (
                AssistantTurnActivity(
                    AssistantTurnActivityPhase.WAITING_FOR_DECISION,
                    command_name="start_training",
                ),
                ChatTurnPresentationPhase.WAITING,
                ChatTurnCancelability.NOT_CANCELLABLE,
            ),
            (
                AssistantTurnActivity(AssistantTurnActivityPhase.STOPPING),
                ChatTurnPresentationPhase.STOPPING,
                ChatTurnCancelability.STOPPING,
            ),
        ],
    )
    def test_typed_activity_controls_workflow_ui(
        self,
        agent_mgr,
        activity,
        expected_phase,
        expected_cancelability,
    ):
        agent_mgr.chat_panel = MagicMock()
        correlation = _admit_ui_turn(agent_mgr)
        activity = replace(
            activity,
            turn_id=correlation.turn_id,
            generation=correlation.generation,
        )

        agent_mgr.on_assistant_activity_changed(activity)

        presentation = agent_mgr.chat_panel.set_turn_activity.call_args.args[0]
        assert presentation.phase is expected_phase
        assert presentation.cancelability is expected_cancelability
        assert presentation.primary_status
        assert presentation.step
        agent_mgr.chat_panel.set_workflow_status.assert_not_called()

    def test_typed_workflow_handoff_does_not_publish_manager_owned_activity(
        self,
        agent_mgr,
    ):
        agent_mgr.chat_panel = MagicMock()
        agent_mgr._execution_mode = "multi"
        request = WorkflowUiHandoffRequest.for_decision(
            "create_epoch",
            decision_fields=("epoch_window", "target_event"),
        )
        agent_mgr._workflow_ui_handoff_host.open = MagicMock(
            return_value=_handoff_resolution(
                request,
                WorkflowUiHandoffResolutionStatus.COMMAND_PENDING,
            )
        )

        agent_mgr.handle_workflow_ui_handoff(request)

        agent_mgr.chat_panel.set_workflow_status.assert_not_called()
        agent_mgr.chat_panel.show_notice.assert_not_called()
        agent_mgr._assistant_runtime.resolve_ui_handoff.assert_called_once_with(
            _handoff_resolution(
                request,
                WorkflowUiHandoffResolutionStatus.COMMAND_PENDING,
            )
        )

    def test_typed_panel_navigation_does_not_publish_manager_owned_activity(
        self,
        agent_mgr,
    ):
        agent_mgr.chat_panel = MagicMock()
        agent_mgr._execution_mode = "multi"
        agent_mgr._open_assistant_panel_target = MagicMock()
        request = AssistantPanelNavigationRequest(target=AssistantPanelTarget.TRAINING)

        agent_mgr.handle_panel_navigation(request)

        agent_mgr._open_assistant_panel_target.assert_called_once_with(
            AssistantPanelTarget.TRAINING
        )
        agent_mgr.chat_panel.set_workflow_status.assert_not_called()

    @pytest.mark.parametrize(
        "status",
        [
            WorkflowUiHandoffResolutionStatus.COMPLETED,
            WorkflowUiHandoffResolutionStatus.CANCELLED,
            WorkflowUiHandoffResolutionStatus.BLOCKED,
            WorkflowUiHandoffResolutionStatus.UNAVAILABLE,
            WorkflowUiHandoffResolutionStatus.FAILED,
            WorkflowUiHandoffResolutionStatus.NAVIGATED,
            WorkflowUiHandoffResolutionStatus.DEFERRED_TO_UI,
            WorkflowUiHandoffResolutionStatus.COMMAND_PENDING,
        ],
    )
    def test_typed_handoff_outcome_resolves_controller_lifecycle_once(
        self,
        agent_mgr,
        status,
    ):
        agent_mgr.chat_panel = MagicMock()
        agent_mgr._execution_mode = "multi"
        request = WorkflowUiHandoffRequest.for_decision("create_epoch")
        resolution = _handoff_resolution(request, status)
        agent_mgr._workflow_ui_handoff_host.open = MagicMock(return_value=resolution)

        agent_mgr.handle_workflow_ui_handoff(request)

        agent_mgr._assistant_runtime.resolve_ui_handoff.assert_called_once_with(
            resolution
        )
        agent_mgr.chat_panel.set_workflow_status.assert_not_called()

    def test_async_handoff_terminal_callback_is_forwarded_after_pending_ack(
        self,
        agent_mgr,
    ):
        request = WorkflowUiHandoffRequest.for_decision("create_epoch")
        pending = _handoff_resolution(
            request,
            WorkflowUiHandoffResolutionStatus.COMMAND_PENDING,
        )
        completed = _handoff_resolution(
            request,
            WorkflowUiHandoffResolutionStatus.COMPLETED,
        )
        callbacks = []

        def _open(_request, *, on_terminal):
            callbacks.append(on_terminal)
            return pending

        agent_mgr._workflow_ui_handoff_host.open = MagicMock(side_effect=_open)

        agent_mgr.handle_workflow_ui_handoff(request)
        callbacks[0](completed)

        assert agent_mgr._assistant_runtime.resolve_ui_handoff.call_args_list == [
            call(pending),
            call(completed),
        ]

    def test_stop_abandons_host_handoff_session_after_runtime_accepts_stop(
        self,
        agent_mgr,
    ):
        agent_mgr._workflow_ui_handoff_host.abandon_active = MagicMock()
        _admit_ui_turn(agent_mgr)

        agent_mgr.stop_generation()

        agent_mgr._workflow_ui_handoff_host.abandon_active.assert_called_once_with()

    def test_rejected_handoff_resolution_is_visible_to_the_user(self, agent_mgr):
        agent_mgr.chat_panel = MagicMock()
        request = WorkflowUiHandoffRequest.for_decision("create_epoch")
        resolution = _handoff_resolution(
            request,
            WorkflowUiHandoffResolutionStatus.CANCELLED,
        )
        agent_mgr._workflow_ui_handoff_host.open = MagicMock(return_value=resolution)
        agent_mgr._assistant_runtime.resolve_ui_handoff.return_value = (
            RuntimeCommandAdmissionResult(
                command_name="resolve_ui_handoff",
                status=RuntimeCommandAdmissionStatus.REJECTED,
                message="Assistant runtime closed before the dialog returned.",
            )
        )

        agent_mgr.handle_workflow_ui_handoff(request)

        agent_mgr.chat_panel.show_notice.assert_called_once_with(
            "Assistant runtime closed before the dialog returned."
        )

    def test_rejected_confirmation_resolution_is_visible_to_the_user(
        self,
        agent_mgr,
    ):
        agent_mgr.chat_panel = MagicMock()
        request = AgentConfirmationRequest.for_action(
            command_name="clear_dataset",
            params={},
            action_label="Clear dataset",
            description="Clear the current dataset.",
            destructive=True,
            publication_generation=1,
        )
        approve_button = MagicMock()
        cancel_button = MagicMock()
        dialog = MagicMock()
        dialog.addButton.side_effect = [approve_button, cancel_button]
        dialog.clickedButton.return_value = cancel_button
        agent_mgr._assistant_runtime.confirm.return_value = (
            RuntimeCommandAdmissionResult(
                command_name="confirm",
                status=RuntimeCommandAdmissionStatus.REJECTED,
                message="Assistant runtime closed before confirmation returned.",
            )
        )

        with patch(
            "XBrainLab.ui.components.agent_manager.QMessageBox",
            return_value=dialog,
        ):
            agent_mgr._show_action_confirmation(request)

        sent_resolution = agent_mgr._assistant_runtime.confirm.call_args.args[0]
        assert sent_resolution.status is AgentConfirmationResolutionStatus.CANCELLED
        agent_mgr.chat_panel.show_notice.assert_called_once_with(
            "Assistant runtime closed before confirmation returned."
        )

    def test_invalid_typed_handoff_payload_is_not_guessed_or_routed(
        self,
        agent_mgr,
    ):
        agent_mgr.chat_panel = MagicMock()
        agent_mgr._workflow_ui_handoff_host.open = MagicMock()

        agent_mgr.handle_workflow_ui_handoff(
            {"tool_name": "create_epoch", "command": "generate_dataset"}
        )

        agent_mgr._workflow_ui_handoff_host.open.assert_not_called()
        agent_mgr._assistant_runtime.resolve_ui_handoff.assert_not_called()

    def test_mismatched_handoff_resolution_is_not_forwarded(self, agent_mgr):
        request = WorkflowUiHandoffRequest.for_decision("create_epoch")
        stale_request = WorkflowUiHandoffRequest.for_decision("create_epoch")
        agent_mgr._workflow_ui_handoff_host.open = MagicMock(
            return_value=_handoff_resolution(
                stale_request,
                WorkflowUiHandoffResolutionStatus.COMPLETED,
            )
        )

        agent_mgr.handle_workflow_ui_handoff(request)

        agent_mgr._assistant_runtime.resolve_ui_handoff.assert_not_called()

    def test_untyped_panel_navigation_payload_is_rejected(
        self,
        agent_mgr,
    ):
        agent_mgr.chat_panel = MagicMock()
        agent_mgr._open_assistant_panel_target = MagicMock()
        params = {
            "panel": "preprocess",
            "tool_name": "create_epoch",
            "command": "generate_dataset",
        }

        agent_mgr.handle_panel_navigation(params)

        agent_mgr._open_assistant_panel_target.assert_not_called()
        agent_mgr.chat_panel.show_notice.assert_called_once_with(
            "The requested XBrainLab view could not be opened."
        )

    def test_open_settings_dialog(self, agent_mgr):
        with patch(
            "XBrainLab.ui.components.agent_manager.ModelSettingsDialog"
        ) as MockDlg:
            MockDlg.return_value.exec.return_value = False
            agent_mgr.open_settings_dialog()

        MockDlg.assert_called_once_with(
            agent_mgr.main_window,
            agent_manager=agent_mgr,
            download_lifecycle=agent_mgr.model_download_lifecycle,
        )

    def test_saved_local_model_selection_activates_through_runtime_owner(
        self,
        agent_mgr,
    ):
        agent_mgr._assistant_runtime.activate_persisted.return_value = (
            RuntimeActivationResult(
                RuntimeActivationStatus.SWITCHING,
                model_id="new-model",
            )
        )

        with patch(
            "XBrainLab.ui.components.agent_manager.ModelSettingsDialog"
        ) as MockDlg:
            MockDlg.return_value.exec.return_value = True
            agent_mgr.open_settings_dialog()

        agent_mgr._assistant_runtime.activate_persisted.assert_called_once_with(
            execution_mode="single",
        )

    def test_runtime_publication_controls_the_visible_composer(self, agent_mgr):
        agent_mgr.chat_panel = MagicMock()

        agent_mgr._render_assistant_runtime(
            AssistantRuntimeSnapshot(
                phase=AssistantRuntimePhase.LOADING,
                initialized=False,
            )
        )
        agent_mgr.chat_panel.set_runtime_state.assert_called_with("loading", "")

        agent_mgr._render_assistant_runtime(
            AssistantRuntimeSnapshot(
                phase=AssistantRuntimePhase.READY,
                initialized=True,
            )
        )
        agent_mgr.chat_panel.set_runtime_state.assert_called_with("ready", "")

    def test_prepare_model_deletion_no_controller(self, agent_mgr):
        agent_mgr._assistant_runtime.controller = None
        assert agent_mgr.prepare_model_deletion("test") is True

    def test_prepare_model_deletion_local_mode(self, agent_mgr):
        agent_mgr._assistant_runtime.active_local_runtime_blocks_model_deletion.return_value = True
        with patch("XBrainLab.ui.components.agent_manager.QMessageBox.warning"):
            assert agent_mgr.prepare_model_deletion("test") is False

    def test_prepare_model_deletion_stale_remote_mode_still_blocks(self, agent_mgr):
        agent_mgr._assistant_runtime.active_local_runtime_blocks_model_deletion.return_value = True
        with patch("XBrainLab.ui.components.agent_manager.QMessageBox.warning"):
            assert agent_mgr.prepare_model_deletion("test") is False

    def test_prepare_model_deletion_uses_inference_mode_truth(self, agent_mgr):
        agent_mgr._assistant_runtime.active_local_runtime_blocks_model_deletion.return_value = True
        with patch("XBrainLab.ui.components.agent_manager.QMessageBox.warning"):
            assert agent_mgr.prepare_model_deletion("test") is False

    def test_on_processing_state_changed(self, agent_mgr):
        agent_mgr.chat_panel = MagicMock()
        agent_mgr.on_processing_state_changed(True)

    def test_toggle_first_open(self, agent_mgr):
        agent_mgr._assistant_runtime.initialized = False
        agent_mgr._assistant_runtime.needs_first_run.return_value = False
        agent_mgr._assistant_runtime.activate.return_value = RuntimeActivationResult(
            RuntimeActivationStatus.STARTED,
            model_id="test-model",
        )
        agent_mgr.chat_panel = MagicMock()
        agent_mgr.chat_dock = MagicMock()
        agent_mgr.toggle()
        agent_mgr.chat_dock.show.assert_called_once()
        agent_mgr._assistant_runtime.activate.assert_called_once_with(
            agent_mgr._assistant_runtime.load_config.return_value,
            execution_mode="single",
        )

    @pytest.mark.parametrize(
        ("choice", "message", "visible_message"),
        [
            (
                "later",
                "Assistant setup was deferred. Open assistant settings when you are "
                "ready to continue.",
                "Assistant setup was deferred. Open assistant settings when you are "
                "ready to continue.",
            ),
            (
                "disable",
                "Assistant is disabled. Open assistant settings when you want to "
                "enable it.",
                "Assistant is disabled. Open assistant settings to enable it.",
            ),
        ],
    )
    def test_first_run_stop_keeps_setup_recovery_surface(
        self,
        agent_mgr,
        choice,
        message,
        visible_message,
    ):
        agent_mgr._assistant_runtime.initialized = False
        agent_mgr._assistant_runtime.needs_first_run.return_value = True
        agent_mgr._assistant_runtime.apply_first_run_choice.return_value = (
            RuntimeSetupOutcome(
                RuntimeSetupAction.STOP,
                message,
            )
        )
        agent_mgr.chat_panel = MagicMock()
        agent_mgr.chat_dock = MagicMock()
        agent_mgr._show_local_runtime_first_run_dialog = MagicMock(
            return_value=choice,
        )
        status_messages: list[str] = []
        agent_mgr.status_message_received.connect(status_messages.append)

        agent_mgr.toggle()

        agent_mgr.chat_dock.show.assert_called_once_with()
        agent_mgr.chat_dock.close.assert_not_called()
        agent_mgr.main_window.ai_btn.setChecked.assert_called_with(True)
        agent_mgr._assistant_runtime.activate.assert_not_called()
        agent_mgr.chat_panel.set_runtime_state.assert_called_once_with(
            AssistantRuntimePhase.IDLE.value,
            visible_message,
        )
        agent_mgr.chat_controller.add_agent_message.assert_not_called()
        assert status_messages[-1] == visible_message

    def test_first_run_download_keeps_dock_open_and_routes_to_settings(
        self,
        agent_mgr,
    ):
        agent_mgr._assistant_runtime.initialized = False
        agent_mgr._assistant_runtime.needs_first_run.return_value = True
        agent_mgr._assistant_runtime.apply_first_run_choice.return_value = (
            RuntimeSetupOutcome(RuntimeSetupAction.OPEN_SETTINGS)
        )
        agent_mgr.chat_panel = MagicMock()
        agent_mgr.chat_dock = MagicMock()
        agent_mgr._show_local_runtime_first_run_dialog = MagicMock(
            return_value="download",
        )
        agent_mgr.open_settings_dialog = MagicMock()

        agent_mgr.toggle()

        agent_mgr.chat_dock.show.assert_called_once_with()
        agent_mgr.chat_dock.close.assert_not_called()
        agent_mgr.open_settings_dialog.assert_called_once_with()
        agent_mgr._assistant_runtime.activate.assert_not_called()

    def test_later_surface_can_close_and_reopen_without_losing_setup_recovery(
        self,
        agent_mgr,
    ):
        agent_mgr._assistant_runtime.initialized = False
        agent_mgr._assistant_runtime.needs_first_run.return_value = True
        message = (
            "Assistant setup was deferred. Open assistant settings when you are "
            "ready to continue."
        )
        agent_mgr._assistant_runtime.apply_first_run_choice.return_value = (
            RuntimeSetupOutcome(RuntimeSetupAction.STOP, message)
        )
        agent_mgr.chat_panel = MagicMock()
        agent_mgr.chat_dock = MagicMock()
        agent_mgr.chat_dock.isVisible.side_effect = [False, True, False]
        agent_mgr._show_local_runtime_first_run_dialog = MagicMock(
            return_value="later",
        )

        agent_mgr.toggle()
        agent_mgr.toggle()
        agent_mgr.toggle()

        assert agent_mgr.chat_dock.show.call_count == 2
        agent_mgr.chat_dock.close.assert_called_once_with()
        assert agent_mgr._show_local_runtime_first_run_dialog.call_count == 2
        assert agent_mgr.chat_panel.set_runtime_state.call_count == 2

    def test_disabled_surface_reopens_as_setup_required_not_crashed(
        self,
        agent_mgr,
    ):
        agent_mgr._assistant_runtime.initialized = False
        agent_mgr._assistant_runtime.needs_first_run.side_effect = [True, False]
        disabled_message = (
            "Local assistant runtime is disabled. Enable it in assistant settings "
            "when you want to use the local model."
        )
        agent_mgr._assistant_runtime.apply_first_run_choice.return_value = (
            RuntimeSetupOutcome(
                RuntimeSetupAction.STOP,
                "Assistant is disabled.",
            )
        )
        agent_mgr._assistant_runtime.activate.return_value = RuntimeActivationResult(
            RuntimeActivationStatus.UNAVAILABLE,
            message=disabled_message,
            failure=AssistantRuntimeSelectionFailure(
                code=AssistantRuntimeSelectionFailureCode.RUNTIME_DISABLED,
                message=disabled_message,
                requested_backend_id="local",
                requested_model_id="test-model",
            ),
        )
        agent_mgr.chat_panel = MagicMock()
        agent_mgr.chat_dock = MagicMock()
        agent_mgr.chat_dock.isVisible.side_effect = [False, True, False]
        agent_mgr._show_local_runtime_first_run_dialog = MagicMock(
            return_value="disable",
        )

        agent_mgr.toggle()
        agent_mgr.toggle()
        agent_mgr.toggle()

        assert agent_mgr.chat_dock.show.call_count == 2
        agent_mgr.chat_dock.close.assert_called_once_with()
        agent_mgr._assistant_runtime.activate.assert_called_once()
        phase, visible = agent_mgr.chat_panel.set_runtime_state.call_args.args
        assert phase == AssistantRuntimePhase.IDLE.value
        assert "disabled" in visible.lower()
        agent_mgr.chat_panel.show_runtime_notice.assert_not_called()

    def test_settings_retry_ready_recovery_uses_runtime_publications(
        self,
        agent_mgr,
    ):
        missing_message = "Model cache not found."

        def activation_sequence(*, execution_mode):
            assert execution_mode == "single"
            call_index = agent_mgr._assistant_runtime.activate_persisted.call_count
            if call_index == 1:
                agent_mgr._render_assistant_runtime(
                    AssistantRuntimeSnapshot(
                        phase=AssistantRuntimePhase.FAILED,
                        initialized=False,
                        error=missing_message,
                    )
                )
                return RuntimeActivationResult(
                    RuntimeActivationStatus.UNAVAILABLE,
                    message=missing_message,
                )
            agent_mgr._render_assistant_runtime(
                AssistantRuntimeSnapshot(
                    phase=AssistantRuntimePhase.LOADING,
                    initialized=False,
                )
            )
            return RuntimeActivationResult(
                RuntimeActivationStatus.STARTED,
                model_id="test-model",
            )

        agent_mgr.chat_panel = MagicMock()
        agent_mgr._assistant_runtime.activate_persisted.side_effect = (
            activation_sequence
        )
        with patch(
            "XBrainLab.ui.components.agent_manager.ModelSettingsDialog"
        ) as MockDlg:
            MockDlg.return_value.exec.return_value = True
            agent_mgr.open_settings_dialog()

        agent_mgr.retry_local_assistant()
        agent_mgr._render_assistant_runtime(
            AssistantRuntimeSnapshot(
                phase=AssistantRuntimePhase.READY,
                initialized=True,
                backend_mode="local",
                model_id="test-model",
            )
        )

        rendered_phases = [
            call_args.args[0]
            for call_args in agent_mgr.chat_panel.set_runtime_state.call_args_list
        ]
        assert rendered_phases[-3:] == ["failed", "loading", "ready"]
        assert agent_mgr._assistant_runtime.activate_persisted.call_count == 2
        assert agent_mgr._runtime_unavailable_notice is None

    def test_failed_runtime_retry_uses_persisted_runtime_owner(self, agent_mgr):
        agent_mgr._assistant_runtime.current = AssistantRuntimeSnapshot(
            phase=AssistantRuntimePhase.FAILED,
            initialized=False,
            error="model failed",
        )
        agent_mgr._assistant_runtime.activate_persisted.return_value = (
            RuntimeActivationResult(
                RuntimeActivationStatus.STARTED,
                model_id="test-model",
            )
        )

        agent_mgr.retry_local_assistant()

        agent_mgr._assistant_runtime.activate_persisted.assert_called_once_with(
            execution_mode="single",
        )
        assert agent_mgr._runtime_unavailable_notice is None

    def test_init_ui_uses_draggable_product_dock_titlebar(self, qtbot):
        from PyQt6.QtWidgets import QDockWidget, QLabel

        from XBrainLab.ui.components.agent_manager import (
            AgentManager,
            AssistantDockTitleBar,
        )

        main_window = cast(Any, QMainWindow())
        main_window.ai_btn = MagicMock()
        qtbot.addWidget(main_window)
        study = MagicMock()
        study.get_controller.return_value = MagicMock()
        manager = cast(Any, AgentManager(main_window, study))
        manager.retry_local_assistant = MagicMock()

        manager.init_ui()
        assert manager.chat_dock is not None

        assert isinstance(manager.chat_dock.titleBarWidget(), AssistantDockTitleBar)
        features = manager.chat_dock.features()
        assert features & QDockWidget.DockWidgetFeature.DockWidgetMovable
        assert features & QDockWidget.DockWidgetFeature.DockWidgetFloatable
        assert manager.chat_dock.minimumWidth() >= 320
        title = manager.chat_dock.findChild(QLabel, "AssistantDockTitle")
        assert title is not None
        assert title.minimumWidth() >= title.fontMetrics().horizontalAdvance(
            "XBrainLab"
        )
        manager.chat_panel.retry_local_assistant_requested.emit()
        manager.retry_local_assistant.assert_called_once_with()
        for control in (
            manager.retry_title_btn,
            manager.new_conv_title_btn,
            manager.settings_btn,
            manager.float_btn,
            manager.close_btn,
        ):
            assert control.width() >= 28
            assert control.height() >= 28
            assert control.focusPolicy() == Qt.FocusPolicy.StrongFocus
        assert manager.close_btn.accessibleName() == "Close assistant"
        assert manager.new_conv_title_btn.toolTip() == "New chat"
        assert manager.new_conv_title_btn.accessibleName() == "New chat"
        assert manager.clear_conversation_title_action.text() == "New chat"
        manager.chat_dock.show()
        manager.close_btn.click()
        assert manager.chat_dock.isHidden()

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
        agent_mgr._assistant_runtime.initialized = False
        agent_mgr._assistant_runtime.needs_first_run.return_value = False
        agent_mgr._assistant_runtime.activate.return_value = RuntimeActivationResult(
            RuntimeActivationStatus.UNAVAILABLE,
            message="Model cache not found.",
        )
        agent_mgr.chat_panel = MagicMock()
        agent_mgr.chat_dock = MagicMock()
        with patch(
            "XBrainLab.ui.components.agent_manager.ModelSettingsDialog"
        ) as MockDlg:
            agent_mgr.toggle()

        MockDlg.assert_not_called()
        agent_mgr.chat_dock.show.assert_called_once()
        agent_mgr.chat_panel.show_runtime_notice.assert_called_with(
            "**Assistant unavailable**: The selected local model is missing from "
            "the model cache. Open assistant settings to install or select a model."
        )

    def test_handle_user_input_reports_runtime_reason_when_controller_missing(
        self,
        agent_mgr,
    ):
        agent_mgr._assistant_runtime.controller = None
        agent_mgr._assistant_runtime.activate_persisted.return_value = (
            RuntimeActivationResult(
                RuntimeActivationStatus.UNAVAILABLE,
                message="Model cache not found.",
            )
        )
        agent_mgr.chat_panel = MagicMock()

        agent_mgr.handle_user_input("train")

        agent_mgr.chat_controller.add_user_message.assert_not_called()
        agent_mgr.chat_panel.show_runtime_notice.assert_called_with(
            "**Assistant unavailable**: The selected local model is missing from "
            "the model cache. Open assistant settings to install or select a model."
        )

    def test_toggle_already_visible(self, agent_mgr):
        agent_mgr._assistant_runtime.initialized = True
        agent_mgr.chat_dock = MagicMock()
        agent_mgr.chat_dock.isVisible.return_value = True
        agent_mgr.toggle()
        agent_mgr.chat_dock.close.assert_called()

    def test_toggle_show(self, agent_mgr):
        agent_mgr._assistant_runtime.initialized = True
        agent_mgr.chat_dock = MagicMock()
        agent_mgr.chat_dock.isVisible.return_value = False
        agent_mgr.toggle()
        agent_mgr.chat_dock.show.assert_called()

    def test_debug_tool_flow_surfaces_backend_blocked_result(self, qtbot):
        """UI -> agent -> backend command flow reports shared blocked reason."""
        from XBrainLab.backend.study import Study
        from XBrainLab.ui.components.agent_manager import AgentManager

        main_window = cast(Any, QMainWindow())
        main_window.ai_btn = MagicMock()
        qtbot.addWidget(main_window)
        study = Study()

        with (
            patch("XBrainLab.llm.agent.controller.AgentWorker") as MockWorker,
            patch("XBrainLab.llm.agent.controller.QThread") as MockThread,
            patch("XBrainLab.llm.agent.controller.LLMController.initialize"),
        ):
            MockWorker.return_value.generation_thread = None
            MockThread.return_value.isRunning.return_value = False

            manager = cast(Any, AgentManager(main_window, study))
            manager.init_ui()
            assert manager.chat_panel is not None
            try:
                manager.start_system()
                submission = manager._assistant_turn_state.begin_submission()
                correlation = AssistantTurnCorrelation(
                    generation=submission.generation,
                    turn_id=1,
                )
                assert manager._assistant_turn_state.accept_admission(
                    submission,
                    correlation,
                )
                manager.agent_controller._active_host_turn_generation = None
                manager.agent_controller._active_host_turn_id = None
                manager._assistant_runtime._active_turn = correlation
                manager.agent_controller.execute_debug_tool(
                    AssistantDebugToolRequest.from_params(
                        correlation=correlation,
                        tool_name="start_training",
                        params={},
                    )
                )
            finally:
                manager.close()

        messages = [message["content"] for message in manager.chat_controller.messages]
        visible = "\n".join(messages)

        assert "Training is not available yet" in visible
        assert "Load raw data before training" in visible
        assert "Generate datasets before training" in visible
        assert "Tool Output:" not in visible
        assert "command_name" not in visible
        assert manager.chat_panel.empty_state_backend_label.text() == (
            "No EEG files are open yet."
        )


class _FakeAgentController(QObject):
    response_presentation_ready = pyqtSignal(object)
    generation_started = pyqtSignal()
    processing_finished = pyqtSignal()
    turn_finished = pyqtSignal(object)
    status_update = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    panel_navigation_requested = pyqtSignal(object)
    confirmation_requested = pyqtSignal(object)
    workflow_ui_handoff_requested = pyqtSignal(object)
    application_command_completed = pyqtSignal(object)
    application_command_started = pyqtSignal()
    execution_mode_changed = pyqtSignal(str)
    runtime_state_changed = pyqtSignal(object)
    activity_changed = pyqtSignal(object)

    def __init__(self, mode: str):
        super().__init__()
        self.mode = mode
        self.is_processing = False
        self.received_inputs: list[str] = []
        self._active_correlation: AssistantTurnCorrelation | None = None

    def initialize(self, launch_spec):
        self.runtime_state_changed.emit(
            AssistantRuntimeSnapshot(
                phase=AssistantRuntimePhase.READY,
                initialized=True,
                backend_mode=launch_spec.backend_mode,
                model_id=launch_spec.model_id,
                requested_model_id=launch_spec.requested_model_id,
                selection_outcome=launch_spec.outcome,
                selection_detail=launch_spec.selection_detail,
                activation_id=launch_spec.activation_id,
            )
        )
        self.status_update.emit("Ready")

    def runtime_snapshot(self):
        return AssistantRuntimeSnapshot(
            phase=AssistantRuntimePhase.READY,
            initialized=True,
            backend_mode="local",
            model_id="test-model",
        )

    def handle_user_input(self, text: str):
        correlation = self._active_correlation
        if correlation is None:
            raise RuntimeError("Test controller requires an admitted host turn.")
        self.received_inputs.append(text)
        self.is_processing = True
        self.activity_changed.emit(
            AssistantTurnActivity(
                AssistantTurnActivityPhase.PREPARING,
                turn_id=correlation.turn_id,
                generation=correlation.generation,
            )
        )
        self.generation_started.emit()
        if self.mode == "normal":
            self.response_presentation_ready.emit(
                AssistantResponsePresentation(
                    correlation=correlation,
                    text=(
                        "Hello from XBrainLab. I can inspect state or guide the "
                        "EEG workflow."
                    ),
                )
            )
        elif self.mode == "empty":
            raw_error = (
                "Assistant returned an empty response. Try Retry or check local "
                "runtime status."
            )
            self.error_occurred.emit(raw_error)
            self.response_presentation_ready.emit(
                AssistantResponsePresentation(
                    correlation=correlation,
                    text=user_facing_generation_error(raw_error),
                    kind=AssistantResponseKind.BLOCKED,
                )
            )
        elif self.mode == "error":
            raw_error = "Model load failed: local runtime unavailable."
            self.error_occurred.emit(raw_error)
            self.response_presentation_ready.emit(
                AssistantResponsePresentation(
                    correlation=correlation,
                    text=user_facing_generation_error(raw_error),
                    kind=AssistantResponseKind.BLOCKED,
                )
            )
        self.is_processing = False
        self.activity_changed.emit(
            AssistantTurnActivity(
                AssistantTurnActivityPhase.IDLE,
                turn_id=correlation.turn_id,
                generation=correlation.generation,
            )
        )
        self.processing_finished.emit()

    def handle_user_turn(self, request: AssistantTurnRequest):
        self._active_correlation = request.correlation
        try:
            self.handle_user_input(request.text)
            self.turn_finished.emit(
                AssistantTurnTerminal(correlation=request.correlation)
            )
        finally:
            self._active_correlation = None

    def execute_debug_tool(self, _request: object):
        return None

    def set_execution_mode(self, _mode: str):
        return None

    def set_model(self, _model: str):
        return None

    def on_user_confirmation_resolved(self, _resolution: object):
        return None

    def on_workflow_ui_handoff_resolved(self, _resolution: object):
        return None

    def stop_generation(self):
        correlation = self._active_correlation
        if correlation is None:
            return
        self.is_processing = False
        self.activity_changed.emit(
            AssistantTurnActivity(
                AssistantTurnActivityPhase.STOPPING,
                turn_id=correlation.turn_id,
                generation=correlation.generation,
            )
        )
        self.processing_finished.emit()
        self.turn_finished.emit(
            AssistantTurnTerminal(
                correlation=correlation,
                outcome="cancelled",
            )
        )
        self._active_correlation = None

    def reset_conversation(self):
        return None

    def close(self):
        return None


def _make_real_manager_with_fake_controller(
    qtbot,
    mode: str,
) -> tuple[Any, _FakeAgentController]:
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.components.agent_manager import AgentManager

    main_window = cast(Any, QMainWindow())
    main_window.ai_btn = MagicMock()
    qtbot.addWidget(main_window)
    study = Study()
    fake = _FakeAgentController(mode)
    with patch(
        "XBrainLab.ui.components.agent_manager.LLMController", return_value=fake
    ):
        manager = cast(Any, AgentManager(main_window, study))
        manager.init_ui()
        manager.start_system()
    return manager, fake


class TestAgentManagerProductChatFlow:
    def test_product_next_steps_use_data_interpretation_in_empty_state(self):
        from XBrainLab.backend.application import ApplicationService
        from XBrainLab.backend.study import Study
        from XBrainLab.ui.components.assistant_status_projection import (
            build_assistant_status_projection,
        )

        service = ApplicationService(Study())

        projection = build_assistant_status_projection(
            service.get_view_publication(),
        )

        assert projection.available_commands == ("scan_source",)
        assert "load_data" not in projection.available_commands
        assert "attach_labels" not in projection.available_commands

    def test_product_next_steps_hide_legacy_label_tool_after_raw_load(self):
        from XBrainLab.backend.application.view_publication import (
            ApplicationViewPublication,
        )
        from XBrainLab.ui.components.assistant_status_projection import (
            build_assistant_status_projection,
        )

        state = replace(
            ApplicationStateSnapshot.empty(),
            pipeline_stage="data_loaded",
            active_dataset=ActiveDatasetSnapshot(
                has_datasets=False,
                has_epoch_data=False,
                has_preprocessed_data=False,
                has_raw_data=True,
            ),
        )
        capabilities = build_capability_policy(state)

        projection = build_assistant_status_projection(
            ApplicationViewPublication(
                generation=1,
                state=state,
                capabilities=capabilities,
            )
        )

        assert projection.available_commands == ("preprocess",)

    def test_normal_chat_response_product_flow(self, qtbot):
        manager, fake = _make_real_manager_with_fake_controller(qtbot, "normal")

        manager.chat_panel.input_field.setText("hello")
        manager.chat_panel._on_send()

        messages = manager.chat_controller.messages
        assert messages[0] == {"role": "user", "content": "hello"}
        assert fake.received_inputs == ["hello"]
        bubbles = manager.chat_panel.findChildren(MessageBubble)
        assert bubbles
        bubble = bubbles[-1]
        assert "Hello from XBrainLab" in bubble.get_text()
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
        assert any("could not complete" in message for message in assistant_messages)
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
        assert any(
            "could not start or continue" in message for message in assistant_messages
        )
        assert all("Model load failed" not in message for message in assistant_messages)
        assert manager.chat_panel.is_processing is False

    def test_retry_without_prior_request_uses_notice_not_transcript(self, qtbot):
        manager, _fake = _make_real_manager_with_fake_controller(qtbot, "normal")

        manager.retry_last_user_input()

        assert manager.chat_controller.messages == []
        assert manager.chat_panel.notice_label.isHidden() is False
        assert "Retry" in manager.chat_panel.notice_label.text()
        assert manager.retry_title_btn.isEnabled() is False

    def test_local_unavailable_first_open_is_visible_with_real_panel(self, qtbot):
        from XBrainLab.backend.study import Study
        from XBrainLab.ui.components.agent_manager import AgentManager

        main_window = cast(Any, QMainWindow())
        main_window.ai_btn = MagicMock()
        qtbot.addWidget(main_window)
        manager = cast(Any, AgentManager(main_window, Study()))
        manager.init_ui()
        assert manager.chat_dock is not None

        def fail_activation(*_args, **_kwargs):
            manager._assistant_runtime.mark_unavailable("Model cache not found.")
            return RuntimeActivationResult(
                RuntimeActivationStatus.UNAVAILABLE,
                message="Model cache not found.",
            )

        with (
            patch.object(
                manager._assistant_runtime,
                "load_config",
                return_value=MagicMock(),
            ),
            patch.object(
                manager._assistant_runtime,
                "needs_first_run",
                return_value=False,
            ),
            patch.object(
                manager._assistant_runtime,
                "activate",
                side_effect=fail_activation,
            ),
        ):
            manager.toggle()

        assert manager.chat_controller.messages == []
        assert manager.chat_panel.runtime_state_title.text() == (
            "Assistant unavailable"
        )
        assert manager.chat_panel.runtime_state_widget.isHidden() is False
        assert "Model cache not found" not in (
            manager.chat_panel.runtime_state_detail.text()
        )
        assert manager.chat_dock.isHidden() is False
