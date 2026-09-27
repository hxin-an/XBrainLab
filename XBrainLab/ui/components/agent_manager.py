"""Qt composition and presentation adapter for the in-app assistant."""

from dataclasses import dataclass
from typing import Any, cast

from PyQt6.QtCore import (
    QObject,
    Qt,
    pyqtSignal,
)
from PyQt6.QtWidgets import QDockWidget

from XBrainLab.backend.application import (
    ApplicationService,
    get_application_service,
)
from XBrainLab.backend.controller.chat_controller import (
    ChatController,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.debug.tool_debug_mode import ToolDebugMode
from XBrainLab.llm.agent.assistant_activity import (
    AssistantTurnActivity,
    AssistantTurnActivityPhase,
)
from XBrainLab.llm.agent.confirmation import (
    AgentConfirmationRequest,
    AgentConfirmationResolution,
)
from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.llm.agent.response_presentation import (
    AssistantPanelNavigationRequest,
    AssistantPanelTarget,
    AssistantResponseKind,
    AssistantResponsePresentation,
)
from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
    AssistantRuntimeSnapshot,
)
from XBrainLab.llm.agent.turn import (
    AssistantTurnCorrelation,
    AssistantTurnTerminal,
)
from XBrainLab.llm.agent.ui_handoff import (
    WorkflowUiHandoffRequest,
    WorkflowUiHandoffResolution,
    WorkflowUiHandoffResolutionStatus,
)
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.model_catalog import local_model_spec
from XBrainLab.llm.core.model_download_lifecycle import ModelDownloadLifecycle
from XBrainLab.llm.core.runtime_selection import (
    AssistantRuntimeSelectionFailureCode,
)
from XBrainLab.llm.tools.result_contract import (
    redact_public_text,
    safe_unexpected_failure,
)
from XBrainLab.ui.chat.assistant_dock import AssistantDockView
from XBrainLab.ui.chat.panel import ChatPanel
from XBrainLab.ui.chat.presentation import (
    ChatTurnPresentation,
    present_assistant_activity,
)
from XBrainLab.ui.chat.turn_state import (
    AssistantUiTurnPhase,
    AssistantUiTurnStateMachine,
)
from XBrainLab.ui.components.agent_presentation_service import (
    AgentPresentationService,
)
from XBrainLab.ui.components.assistant_application_publication_coordinator import (
    AssistantApplicationPublicationCoordinator,
    AssistantTrainingTerminalNotice,
)
from XBrainLab.ui.components.assistant_runtime_lifecycle import (
    AssistantRuntimeLifecycle,
    RuntimeActivationResult,
    RuntimeActivationStatus,
    RuntimeCommandAdmissionResult,
    RuntimeSetupAction,
)
from XBrainLab.ui.components.assistant_status_projection import (
    AssistantStatusProjection,
)
from XBrainLab.ui.components.vram_checker import VRAMConflictChecker
from XBrainLab.ui.components.workflow_ui_handoff_host import WorkflowUiHandoffHost
from XBrainLab.ui.dialogs.model_settings_dialog import ModelSettingsDialog
from XBrainLab.ui.panel_navigation import (
    PANEL_DATASET,
    PANEL_EVALUATION,
    PANEL_PREPROCESS,
    PANEL_TRAINING,
    PANEL_VISUALIZATION,
    VISUALIZATION_TAB_3D_PLOT,
    VISUALIZATION_TAB_SALIENCY_MAP,
    VISUALIZATION_TAB_SPECTROGRAM,
    VISUALIZATION_TAB_TOPOGRAPHIC_MAP,
)

_CHAT_PRUNE_NOTICE = (
    "Older messages were removed from this view to keep the conversation responsive."
)


@dataclass(frozen=True, slots=True)
class AssistantTurnAdmissionResult:
    """Exact outcome of one UI-to-runtime assistant turn admission."""

    correlation: AssistantTurnCorrelation | None = None

    @property
    def accepted(self) -> bool:
        return self.correlation is not None


_ASSISTANT_CONTROLLER_UI_SIGNALS = (
    "response_presentation_ready",
    "status_update",
    "activity_changed",
    "confirmation_requested",
    "panel_navigation_requested",
    "workflow_ui_handoff_requested",
    "application_command_completed",
    "application_command_started",
    "turn_finished",
)

_DELIVERY_TERMINAL_MESSAGES = {
    "delivery_error": (
        "The assistant could not receive this request. Retry the request. "
        "If it happens again, restart the assistant from Settings."
    ),
    "delivery_rejected": (
        "The assistant did not accept this request. Retry the request. "
        "If it happens again, restart the assistant from Settings."
    ),
    "rejected_busy": (
        "The assistant did not accept this request. Retry the request. "
        "If it happens again, restart the assistant from Settings."
    ),
    "rejected_closing": (
        "The assistant did not accept this request. Retry the request. "
        "If it happens again, restart the assistant from Settings."
    ),
    "delivery_timeout": (
        "The assistant did not acknowledge this request. Retry the request. "
        "If it happens again, restart the assistant from Settings."
    ),
}


class AgentManager(QObject):
    """Compose assistant collaborators and adapt their signals to product UI.

    Runtime readiness, controller ownership, command dispatch, model switching,
    and shutdown belong to ``AssistantRuntimeLifecycle``. This class owns the
    dock, dialogs, navigation, presentation, and Qt signal wiring only.

    Attributes:
        main_window: Reference to the parent ``MainWindow``.
        study: The application ``Study`` instance.
        chat_panel: The ``ChatPanel`` widget, or ``None`` before init.
        chat_dock: The ``QDockWidget`` hosting the chat panel.
        chat_controller: The ``ChatController`` managing chat state.
        agent_controller: Read-only access to the lifecycle-owned controller.
        agent_initialized: Read-only lifecycle initialization state.

    """

    assistant_deactivation_finished = pyqtSignal(bool, str)

    def __init__(
        self,
        main_window,
        study,
        *,
        application_service: ApplicationService | None = None,
        runtime_lifecycle: AssistantRuntimeLifecycle | None = None,
        model_download_lifecycle: ModelDownloadLifecycle | None = None,
    ):
        """Initialize the AgentManager.

        Args:
            main_window: The parent ``MainWindow`` instance.
            study: The application ``Study`` instance providing
                controllers and shared state.

        """
        super().__init__(main_window)
        self.main_window = main_window
        self.study = study
        self.application_service = (
            application_service
            if application_service is not None
            else get_application_service(study)
        )
        self.chat_panel: ChatPanel | None = None
        self.chat_dock: QDockWidget | None = None
        self.chat_controller = ChatController()
        self._runtime_unavailable_notice: str | None = None
        self._application_command_in_flight = False
        self._assistant_turn_state = AssistantUiTurnStateMachine()
        self._application_publication_coordinator = (
            AssistantApplicationPublicationCoordinator(
                service=self.application_service,
                render_status=self._render_assistant_status_projection,
                render_terminal=self._render_training_terminal,
                is_idle=lambda: self._assistant_turn_state.phase
                is AssistantUiTurnPhase.IDLE,
                parent=self,
            )
        )
        self._assistant_runtime = runtime_lifecycle or AssistantRuntimeLifecycle(
            study,
            controller_factory=self._create_assistant_controller,
            parent=self,
        )
        self._assistant_runtime.controller_created.connect(
            self._wire_assistant_controller,
        )
        self._assistant_runtime.runtime_snapshot_changed.connect(
            self._render_assistant_runtime,
        )
        self._assistant_runtime.turn_finished.connect(
            self._on_assistant_turn_finished,
        )
        self._assistant_runtime.deactivation_finished.connect(
            self._on_assistant_deactivation_finished
        )
        self._model_download_lifecycle = (
            model_download_lifecycle or ModelDownloadLifecycle(parent=self)
        )
        self._presentation = AgentPresentationService()
        self._workflow_ui_handoff_host = WorkflowUiHandoffHost(self.main_window)
        # M3.4 VRAM Monitoring — delegated to VRAMConflictChecker
        self.vram_checker = VRAMConflictChecker(
            self.main_window,
            lambda: self._assistant_runtime.current,
        )
        self._visualization_monitor_connected = False
        self.connect_visualization_monitor()

    @property
    def agent_controller(self) -> LLMController | None:
        """Return the controller owned by ``AssistantRuntimeLifecycle``."""
        return cast(LLMController | None, self._assistant_runtime.controller)

    @property
    def assistant_runtime(self) -> AssistantRuntimeLifecycle:
        """Expose the focused runtime contract for diagnostics and integration."""
        return self._assistant_runtime

    @property
    def model_download_lifecycle(self) -> ModelDownloadLifecycle:
        """Expose app-owned model download state without transferring ownership."""
        return self._model_download_lifecycle

    @property
    def assistant_status_projection(self) -> AssistantStatusProjection | None:
        """Return the last atomically derived workflow status projection."""
        return self._application_publication_coordinator.projection

    @property
    def agent_initialized(self) -> bool:
        """Return whether the runtime owner initialized its controller."""
        return self._assistant_runtime.initialized

    def connect_visualization_monitor(self) -> None:
        """Connect visualization-tab VRAM checks when the panel has been loaded."""
        if self._visualization_monitor_connected:
            return
        visualization_panel = getattr(self.main_window, "visualization_panel", None)
        tabs = getattr(visualization_panel, "tabs", None)
        if tabs is None:
            return
        tabs.currentChanged.connect(self.vram_checker.on_viz_tab_changed)
        self._visualization_monitor_connected = True

    def init_ui(self):
        """Initialize the chat dock widget and panel UI components.

        Creates the ``ChatPanel``, wires its signals, builds the dock
        title bar with settings/new-conversation buttons, and
        adds the dock to the main window's right area.
        """
        chat_dock = AssistantDockView(self.main_window)
        chat_panel = chat_dock.chat_panel
        self.chat_dock = chat_dock
        self.chat_panel = chat_panel
        self._assistant_runtime.replay_runtime_snapshot()

        # Connect UI to ChatController
        chat_panel.connect_controller(self.chat_controller)

        # Connect ChatPanel signals to self (for further dispatch)
        chat_panel.send_message.connect(self.handle_user_input)
        chat_panel.stop_generation.connect(self.stop_generation)
        chat_panel.debug_tool_requested.connect(self._handle_debug_tool_requested)
        chat_panel.open_settings_requested.connect(self.open_settings_dialog)
        chat_panel.inline_setup_requested.connect(self._handle_inline_setup)
        chat_panel.retry_local_assistant_requested.connect(self.retry_local_assistant)
        chat_panel.confirmation_decision_requested.connect(
            self._resolve_action_confirmation
        )

        chat_dock.install_title_bar()
        chat_dock.new_conversation_requested.connect(self.start_new_conversation)
        chat_dock.settings_requested.connect(lambda: self.open_settings_dialog())
        self.main_window.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea,
            chat_dock,
        )

        chat_dock.visibilityChanged.connect(self.update_ai_btn_state)
        chat_dock.hide()
        self.refresh_backend_status()

    def update_ai_btn_state(self, visible):
        """Sync the AI toggle button checked state with dock visibility.

        Args:
            visible: Whether the dock is currently visible.

        """
        if hasattr(self.main_window, "ai_btn"):
            self.main_window.ai_btn.blockSignals(True)
            self.main_window.ai_btn.setChecked(visible)
            self.main_window.ai_btn.blockSignals(False)

    def toggle(self):
        """Toggle the Agent dock visibility, initializing on first open."""
        if (
            not self.agent_initialized
            and self.chat_dock
            and self.chat_dock.isVisible() is True
        ):
            self.chat_dock.close()
            return

        if not self.agent_initialized:
            if not self.chat_panel or not self.chat_dock:
                logger.warning("Agent dock requested before init_ui completed")
                if hasattr(self.main_window, "ai_btn"):
                    self.main_window.ai_btn.setChecked(False)
                return

            self.chat_dock.show()
            if hasattr(self.main_window, "ai_btn"):
                self.main_window.ai_btn.setChecked(True)

            if self._tool_debug_enabled():
                started = self._assistant_runtime.start_diagnostics()
                self.refresh_backend_status()
                if not started:
                    self._show_runtime_unavailable(
                        self._assistant_runtime.current.error
                        or "Tool diagnostics could not start."
                    )
                return

            config = self._assistant_runtime.load_config()
            if self._assistant_runtime.needs_first_run(config):
                self._show_inline_setup(config)
                return
            activation = self._assistant_runtime.activate(config)
            self._present_runtime_activation(activation)
        elif self.chat_dock and self.chat_dock.isVisible():
            self.chat_dock.close()
        elif self.chat_dock:
            self.chat_dock.show()

    def _show_inline_setup(self, config: LLMConfig) -> None:
        chat_panel = self.chat_panel
        if chat_panel is None:
            return
        resolution = self._assistant_runtime.preview_launch(config)
        spec = local_model_spec(config.model_name)
        label = spec.label if spec else str(config.model_name)
        memory = (
            f"Estimated {spec.estimated_vram_gb:g} GB VRAM"
            if spec
            else "Model details unavailable"
        )
        cache_ready = resolution.failure is None
        chat_panel.show_inline_setup(f"{label}\n{memory}", cache_ready=cache_ready)

    def _handle_inline_setup(self, action: str) -> None:
        config = self._assistant_runtime.load_config()
        if action == "open_settings":
            self.open_settings_dialog()
            return
        outcome = self._assistant_runtime.apply_first_run_choice(config, "enable")
        if outcome.action is RuntimeSetupAction.STOP:
            self._show_runtime_unavailable(outcome.message)
            return
        if outcome.action is RuntimeSetupAction.CONTINUE:
            activation = self._assistant_runtime.activate(
                self._assistant_runtime.load_config(),
            )
            self._present_runtime_activation(activation)

    def _show_runtime_unavailable(self, message: str) -> None:
        """Surface assistant startup blockers in the chat panel."""
        safe_message = redact_public_text(message)
        if self._runtime_unavailable_notice == safe_message:
            return

        self._runtime_unavailable_notice = safe_message
        logger.info(
            "Assistant runtime unavailable: %s",
            redact_public_text(safe_message),
        )
        if self.chat_panel:
            self.chat_panel.show_runtime_notice(
                self._presentation.runtime_unavailable_message(safe_message),
            )

    def _show_runtime_setup_required(self, message: str) -> None:
        """Keep intentional setup deferral visible without presenting a crash."""
        visible = self._presentation.runtime_setup_message(
            redact_public_text(message),
        )
        self._runtime_unavailable_notice = None
        if self.chat_panel:
            self.chat_panel.set_runtime_state(
                AssistantRuntimePhase.IDLE.value,
                visible,
            )
        self._show_global_status(visible)

    @staticmethod
    def _activation_is_disabled_setup(
        activation: RuntimeActivationResult,
    ) -> bool:
        failure = activation.failure
        return bool(
            failure is not None
            and failure.code is AssistantRuntimeSelectionFailureCode.RUNTIME_DISABLED
        )

    def _present_runtime_activation(
        self,
        activation: RuntimeActivationResult,
        *,
        repeat_failure_notice: bool = False,
    ) -> None:
        """Render one activation result without taking over runtime admission."""
        self.refresh_backend_status()
        if activation.available:
            self._runtime_unavailable_notice = None
        elif self._activation_is_disabled_setup(activation):
            self._show_runtime_setup_required(activation.message)
        else:
            if repeat_failure_notice:
                self._runtime_unavailable_notice = None
            self._show_runtime_unavailable(activation.message)

    def open_settings_dialog(self):
        """Open settings and apply an accepted local runtime selection."""
        # Pass self to allow the dialog to request model unloading/switching
        dialog = ModelSettingsDialog(
            self.main_window,
            agent_manager=self,
            download_lifecycle=self._model_download_lifecycle,
        )
        if not dialog.exec():
            return

        activation = self._assistant_runtime.activate_persisted()
        self._present_runtime_activation(activation)
        if (
            activation.status is RuntimeActivationStatus.ALREADY_READY
            and self.chat_panel
        ):
            self.chat_panel.set_runtime_state(AssistantRuntimePhase.READY.value)

    def request_assistant_deactivation(
        self,
        config: LLMConfig,
    ) -> RuntimeCommandAdmissionResult:
        """Delegate Disable admission to the existing runtime owner."""
        return self._assistant_runtime.request_deactivation(config)

    def _on_assistant_deactivation_finished(self, ok: bool, message: str) -> None:
        """Clear Assistant-only presentation after runtime ownership is released."""
        if ok:
            self._clear_conversation_presentation()
            self._runtime_unavailable_notice = None
            self.refresh_backend_status()
        self.assistant_deactivation_finished.emit(bool(ok), str(message or ""))

    def prepare_model_deletion(self, model_name: str) -> bool:
        """Return whether runtime ownership allows model file deletion.

        Called by ``ModelSettingsDialog`` before deleting a model. If the
        model is currently loaded in local mode, block deletion until the
        assistant is switched away from that active local backend.

        Args:
            model_name: The name of the model being deleted.

        Returns:
            ``True`` if it is safe to proceed with deletion.

        """
        if self._assistant_runtime.active_local_runtime_blocks_model_deletion():
            logger.info(
                "Blocking deletion of active local model: %s",
                redact_public_text(model_name),
            )
            return False

        return True

    def _tool_debug_enabled(self) -> bool:
        """Return whether this real chat panel owns a debug script session."""
        return isinstance(
            getattr(self.chat_panel, "debug_mode", None),
            ToolDebugMode,
        )

    def _create_assistant_controller(self, study: object) -> LLMController:
        """Create a controller only when its product UI contract is complete."""
        controller = LLMController(study)
        try:
            self._validate_assistant_controller_contract(controller)
        except Exception:
            close = getattr(controller, "close", None)
            if callable(close):
                close()
            raise
        return controller

    @staticmethod
    def _validate_assistant_controller_contract(controller: object) -> None:
        """Fail before wiring when a product controller lacks core signals."""
        missing = [
            signal_name
            for signal_name in _ASSISTANT_CONTROLLER_UI_SIGNALS
            if not callable(
                getattr(getattr(controller, signal_name, None), "connect", None)
            )
        ]
        if missing:
            formatted = ", ".join(missing)
            raise TypeError(
                f"Assistant controller core signal contract is incomplete: {formatted}."
            )

    def _wire_assistant_controller(self, controller) -> None:
        """Connect one newly created runtime controller to product UI slots."""
        self._validate_assistant_controller_contract(controller)
        controller.response_presentation_ready.connect(
            self._handle_response_presentation
        )
        controller.status_update.connect(self.on_agent_status_update)
        controller.activity_changed.connect(self.on_assistant_activity_changed)
        controller.confirmation_requested.connect(self._show_action_confirmation)
        controller.panel_navigation_requested.connect(self.handle_panel_navigation)
        controller.workflow_ui_handoff_requested.connect(
            self.handle_workflow_ui_handoff
        )
        controller.application_command_completed.connect(
            self._on_application_command_completed
        )
        controller.application_command_started.connect(
            self._on_application_command_started
        )

    def _on_application_command_started(self) -> None:
        """Mark one Assistant command as in flight and render its activity."""
        self._application_command_in_flight = True
        if not self.chat_controller.is_processing:
            self.chat_controller.set_processing(True)
        if self.chat_panel:
            if self._assistant_turn_state.phase is AssistantUiTurnPhase.STOPPING:
                presentation = ChatTurnPresentation.stopping()
            else:
                activity = self._assistant_turn_state.last_activity
                presentation = (
                    present_assistant_activity(
                        activity,
                        application_command_in_flight=True,
                    )
                    if isinstance(activity, AssistantTurnActivity)
                    else ChatTurnPresentation.application_command()
                )
            self.chat_panel.set_turn_activity(presentation)

    def _on_application_command_completed(self, result) -> None:
        """Release command ownership and track asynchronous training completion."""
        self._application_command_in_flight = False
        self._begin_assistant_training_watch(result)

    def _begin_assistant_training_watch(self, result: object) -> None:
        """Track only an asynchronous training run started by this Assistant."""
        correlation = self._assistant_turn_state.lease
        if not isinstance(correlation, AssistantTurnCorrelation):
            return
        self._application_publication_coordinator.begin_training_watch(
            result, correlation
        )

    def handle_user_input(self, text: str) -> AssistantTurnAdmissionResult:
        """Handle text input from ChatPanel.

        Adds the message to ``ChatController`` history and forwards it
        to the ``LLMController`` for processing.

        Args:
            text: The user's message text.

        """
        text = text.strip()
        if not text:
            return AssistantTurnAdmissionResult()
        if self.agent_controller is None:
            activation = self._assistant_runtime.activate_persisted()
            if activation.available:
                self._reject_user_submission(
                    text,
                    "Wait for the local assistant to finish loading.",
                )
            else:
                self._show_runtime_unavailable(activation.message)
                self._reject_user_submission(text, activation.message)
            return AssistantTurnAdmissionResult()

        # Reserve the runtime turn before changing the transcript. A rejected
        # command must not leave an unanswered user bubble behind.
        submission = self._assistant_turn_state.begin_submission()
        admission = self._assistant_runtime.submit(
            text,
            generation=submission.generation,
        )
        if not isinstance(admission, RuntimeCommandAdmissionResult):
            self._assistant_turn_state.reject_admission(submission)
            logger.error("Assistant runtime returned an invalid admission result")
            self._reject_user_submission(
                text,
                "The assistant could not accept this request. Try again.",
            )
            return AssistantTurnAdmissionResult()
        if not admission.accepted:
            self._assistant_turn_state.reject_admission(submission)
            self._reject_user_submission(text, admission.message)
            return AssistantTurnAdmissionResult()

        correlation = admission.correlation
        if correlation is None:
            self._assistant_turn_state.reject_admission(submission)
            logger.error("Assistant admission is missing exact turn correlation")
            self._reject_user_submission(
                text,
                "The assistant could not correlate this request. Try again.",
            )
            return AssistantTurnAdmissionResult()

        if not self._assistant_turn_state.complete_admission(
            submission,
            correlation,
        ):
            self._reject_user_submission(
                text,
                "The assistant could not correlate this request. Try again.",
            )
            return AssistantTurnAdmissionResult()
        self._prepare_admitted_transcript_turn()
        self.chat_controller.add_user_message(text)
        if self.chat_panel is not None:
            self.chat_panel.accept_composer_submission(text)
        return AssistantTurnAdmissionResult(correlation=correlation)

    def _handle_debug_tool_requested(
        self,
        tool_name: str,
        params: dict[str, Any],
        confirmed: bool = False,
        authorization_text: str = "",
    ) -> None:
        """Admit one debug-script action through the normal correlated turn lease."""
        if self.agent_controller is None:
            if self.chat_panel:
                self.chat_panel.reject_debug_step(
                    "The assistant runtime must be ready before running diagnostics."
                )
            self._show_low_priority_notice(
                "The assistant runtime must be ready before running diagnostics."
            )
            return
        submission = self._assistant_turn_state.begin_submission()
        debug_options: dict[str, Any] = {"generation": submission.generation}
        if confirmed:
            debug_options["confirmed"] = True
        if authorization_text:
            debug_options["authorization_text"] = authorization_text
        admission = self._assistant_runtime.debug(
            tool_name,
            dict(params),
            **debug_options,
        )
        if not isinstance(admission, RuntimeCommandAdmissionResult):
            self._assistant_turn_state.reject_admission(submission)
            logger.error("Assistant debug runtime returned an invalid admission result")
            self._show_low_priority_notice(
                "The diagnostic action could not be started. Try again."
            )
            if self.chat_panel:
                self.chat_panel.reject_debug_step(
                    "The diagnostic action could not be started. Try again."
                )
            return
        if not admission.accepted:
            self._assistant_turn_state.reject_admission(submission)
            self._show_low_priority_notice(admission.message)
            if self.chat_panel:
                self.chat_panel.reject_debug_step(admission.message)
            return
        correlation = admission.correlation
        if correlation is None:
            self._assistant_turn_state.reject_admission(submission)
            logger.error("Assistant debug admission is missing exact turn correlation")
            self._show_low_priority_notice(
                "The diagnostic action could not be correlated. Try again."
            )
            if self.chat_panel:
                self.chat_panel.reject_debug_step(
                    "The diagnostic action could not be correlated. Try again."
                )
            return
        if not self._assistant_turn_state.complete_admission(
            submission,
            correlation,
        ):
            self._show_low_priority_notice(
                "The diagnostic action could not be correlated. Try again."
            )
            if self.chat_panel:
                self.chat_panel.reject_debug_step(
                    "The diagnostic action could not be correlated. Try again."
                )
            return
        self._prepare_admitted_transcript_turn()

    def _prepare_admitted_transcript_turn(self) -> None:
        """Establish one bounded transcript budget after runtime admission."""
        pruned_rows = self.chat_controller.prepare_for_turn()
        self._assistant_turn_state.set_prune_notice_pending(bool(pruned_rows))
        if pruned_rows:
            self._show_low_priority_notice(_CHAT_PRUNE_NOTICE)

    def _render_visible_assistant_response(
        self,
        presentation: AssistantResponsePresentation,
    ) -> None:
        """Persist one response after mapping only its typed source state."""
        if not self._assistant_turn_state.pending_prune_notice and self.chat_panel:
            self.chat_panel.show_notice("")
        kind = self._presentation.chat_presentation_kind(presentation.kind)
        self.chat_controller.add_agent_message(
            presentation.text,
            presentation_kind=kind,
        )
        if self._assistant_turn_state.pending_prune_notice:
            self._show_low_priority_notice(_CHAT_PRUNE_NOTICE)

    def _handle_response_presentation(self, payload: object) -> None:
        """Render one typed response for its correlated turn."""
        if not isinstance(payload, AssistantResponsePresentation):
            logger.error(
                "Ignored invalid assistant response presentation: %s",
                redact_public_text(payload),
            )
            return
        terminal_cancellation = payload.kind is AssistantResponseKind.CANCELLED
        if not self._assistant_turn_state.accepts_response(
            payload.correlation,
            terminal_cancellation=terminal_cancellation,
        ):
            logger.warning(
                "Ignored stale assistant response presentation for %s",
                redact_public_text(payload.correlation),
            )
            return
        self._try_render_visible_assistant_response(payload)

    def _try_render_visible_assistant_response(
        self,
        presentation: AssistantResponsePresentation,
        *,
        recover_capacity: bool = False,
    ) -> bool:
        """Render one bounded response without leaking contract errors into Qt."""
        try:
            self._render_visible_assistant_response(presentation)
        except ValueError as exc:
            if not recover_capacity:
                logger.error(
                    "Ignored assistant response outside the chat presentation "
                    "contract: %s",
                    redact_public_text(exc),
                )
                return False
            self._prepare_admitted_transcript_turn()
            try:
                self._render_visible_assistant_response(presentation)
            except (TypeError, ValueError) as retry_exc:
                logger.error(
                    "Ignored assistant response outside the chat presentation "
                    "contract after capacity recovery: %s",
                    redact_public_text(retry_exc),
                )
                return False
            return True
        except TypeError as exc:
            logger.error(
                "Ignored assistant response outside the chat presentation contract: %s",
                redact_public_text(exc),
            )
            return False
        return True

    def _open_assistant_panel_target(
        self,
        target: AssistantPanelTarget,
        *,
        view_mode: str = "",
        on_terminal: Any | None = None,
    ) -> int:
        """Open one typed existing main-window panel without mutating workflow."""
        panel_index = {
            AssistantPanelTarget.DATASET: PANEL_DATASET,
            AssistantPanelTarget.PREPROCESS: PANEL_PREPROCESS,
            AssistantPanelTarget.TRAINING: PANEL_TRAINING,
            AssistantPanelTarget.EVALUATION: PANEL_EVALUATION,
            AssistantPanelTarget.VISUALIZATION: PANEL_VISUALIZATION,
        }[target]
        status_bar = self.main_window.statusBar()

        ready_callback_delivered = False

        def _on_ready(_panel: object) -> None:
            nonlocal ready_callback_delivered
            ready_callback_delivered = True
            if view_mode:
                self._switch_sub_view(panel_index, view_mode)
            if status_bar:
                status_bar.showMessage(f"Opened {target.value.title()} panel.")
            if on_terminal is not None:
                on_terminal(True)

        def _on_failed(_failure: object) -> None:
            if status_bar:
                status_bar.showMessage(f"Could not open {target.value.title()} panel.")
            if on_terminal is not None:
                on_terminal(False)

        if on_terminal is not None:
            materialized = self.main_window.switch_page(
                panel_index,
                on_ready=_on_ready,
                on_failed=_on_failed,
            )
        elif view_mode:
            materialized = self.main_window.switch_page(
                panel_index,
                on_ready=_on_ready,
            )
        else:
            materialized = self.main_window.switch_page(panel_index)
            if materialized is not False and status_bar:
                status_bar.showMessage(f"Opened {target.value.title()} panel.")
        if (
            materialized is not False
            and not ready_callback_delivered
            and (view_mode or on_terminal is not None)
        ):
            _on_ready(None)

        if materialized is False and status_bar:
            status_bar.showMessage(f"Opening {target.value.title()}...")
        return panel_index

    def retry_local_assistant(self) -> None:
        """Retry the persisted local runtime after a visible startup failure."""
        if self._assistant_runtime.current.phase is AssistantRuntimePhase.LOADING:
            return
        activation = self._assistant_runtime.activate_persisted()
        self._present_runtime_activation(activation, repeat_failure_notice=True)

    def stop_generation(self):
        """Stop the currently running LLM generation."""
        if self.agent_controller:
            if self._assistant_turn_state.phase is AssistantUiTurnPhase.STOPPING:
                return
            if self._application_command_in_flight:
                self._show_low_priority_notice(
                    "This action has already started and cannot be stopped safely. "
                    "Wait for it to finish."
                )
                return
            active_before_stop = self._assistant_turn_state.lease
            result = self._assistant_runtime.stop_generation()
            accepted = self._surface_runtime_command_result(
                result,
                fallback="The assistant could not stop the current request.",
            )
            if accepted:
                correlation = result.correlation
                if correlation is None or correlation != active_before_stop:
                    logger.error("Assistant Stop admission had no matching turn lease")
                    self._show_low_priority_notice(
                        "The assistant could not correlate the Stop request."
                    )
                    return
                if self._assistant_turn_state.lease is None:
                    return
                if (
                    self._assistant_turn_state.phase
                    is not AssistantUiTurnPhase.STOPPING
                    and not self._assistant_turn_state.latch_stop(correlation)
                ):
                    logger.error("Assistant Stop could not latch its active turn lease")
                    return
                self._workflow_ui_handoff_host.abandon_active()
                if self.chat_panel:
                    self.chat_panel.set_turn_activity(ChatTurnPresentation.stopping())

    def start_new_conversation(self):
        """Start a new chat without mutating the application workflow state."""
        logger.info("Starting new chat - clearing assistant conversation state")

        # Reset the runtime first so a busy turn cannot orphan visible output.
        if self.agent_controller and not self._surface_runtime_command_result(
            self._assistant_runtime.reset_conversation(),
            fallback="The assistant conversation could not be reset.",
        ):
            return

        # Clear the transcript only after the runtime accepts the boundary.
        self._clear_conversation_presentation()

        # Keep a runtime blocker actionable after the transcript is cleared.
        runtime = self._assistant_runtime.current
        if runtime.phase is AssistantRuntimePhase.FAILED:
            self._runtime_unavailable_notice = None
            self._show_runtime_unavailable(runtime.error)

        self.refresh_backend_status()

    def _clear_conversation_presentation(self) -> None:
        """Clear Assistant transcript/UI state without changing EEG workflow."""
        self.chat_controller.clear_conversation()
        self._assistant_turn_state.clear_prune_notice()
        self._application_publication_coordinator.clear_training()
        if self.chat_panel:
            self.chat_panel.clear_confirmation_request()
        if not self._assistant_turn_state.reset_idle():
            logger.error(
                "Runtime reset accepted while an assistant turn still owned UI"
            )
        if self.chat_panel:
            self.chat_panel.show_notice("")

        if self.agent_controller:
            logger.info("Assistant conversation state reset successfully")

    # Signal to notify Main Window (or other listeners) about status updates
    status_message_received = pyqtSignal(str)

    def _show_low_priority_notice(self, message: str) -> None:
        """Surface an assistant-owned notice without duplicating global status."""
        safe_message = redact_public_text(message)
        if self.chat_panel:
            self.chat_panel.show_notice(safe_message)

    def _reject_user_submission(self, text: str, message: str) -> None:
        """Keep a runtime-rejected request editable at the product boundary."""
        safe_message = redact_public_text(message)
        if self.chat_panel:
            self.chat_panel.reject_composer_submission(text, safe_message)
            return
        self._show_low_priority_notice(safe_message)

    def _surface_runtime_command_result(
        self,
        result: object,
        *,
        fallback: str,
    ) -> bool:
        """Surface a typed runtime transport rejection instead of dropping it."""
        if not isinstance(result, RuntimeCommandAdmissionResult):
            logger.error(
                "Assistant runtime returned an invalid command result: %s",
                redact_public_text(result),
            )
            self._show_low_priority_notice(fallback)
            return False
        if result.accepted:
            return True
        self._show_low_priority_notice(result.message or fallback)
        return False

    def _show_global_status(self, message: str) -> None:
        """Publish a host-level status when the assistant surface is not visible."""
        safe_message = redact_public_text(message)
        try:
            self.status_message_received.emit(safe_message)
        except RuntimeError:
            logger.debug(
                "Status notice could not be emitted: %s",
                redact_public_text(safe_message),
            )

    def on_agent_status_update(self, msg):
        """Forward agent status messages and handle error states.

        Args:
            msg: The status message string from the agent.

        """
        diagnostic = self._presentation.raw_status_diagnostic(redact_public_text(msg))
        logger.debug(
            "Assistant status update: %s",
            redact_public_text(diagnostic),
        )

    def on_assistant_activity_changed(self, payload: object) -> None:
        """Render one typed turn-local activity without inferring workflow state."""
        if not isinstance(payload, AssistantTurnActivity):
            logger.error(
                "Ignored untyped assistant activity: %s",
                redact_public_text(payload),
            )
            return
        if not self._assistant_turn_state.accepts_activity(
            payload.correlation, payload.phase
        ):
            return
        if payload.phase is AssistantTurnActivityPhase.STOPPING:
            correlation = payload.correlation
            if correlation is not None:
                self._assistant_turn_state.latch_stop(correlation)
        self._assistant_turn_state.record_activity(payload)
        presentation = present_assistant_activity(
            payload,
            application_command_in_flight=self._application_command_in_flight,
        )
        processing = presentation.is_busy
        if self.chat_controller.is_processing != processing:
            self.chat_controller.set_processing(processing)
        if self.chat_panel:
            if processing and not self._assistant_turn_state.pending_prune_notice:
                self.chat_panel.show_notice("")
            self.chat_panel.set_turn_activity(presentation)
        if not processing:
            self.refresh_backend_status()

    def _on_assistant_turn_finished(self, payload: object) -> None:
        """Release only the Stop/turn lease named by a typed terminal event."""
        if not isinstance(payload, AssistantTurnTerminal):
            logger.error(
                "Ignored untyped assistant turn terminal: %s",
                redact_public_text(payload),
            )
            return
        if not self._assistant_turn_state.accept_terminal(payload):
            logger.warning(
                "Ignored stale assistant UI terminal for %s",
                redact_public_text(payload.correlation),
            )
            return
        self._render_delivery_terminal_error(payload)
        if self.chat_panel:
            self.chat_panel.complete_debug_step(payload.outcome)
        self._assistant_turn_state.clear_prune_notice()
        if self.chat_panel:
            self.chat_panel.clear_confirmation_request()
        self._assistant_turn_state.clear_activity()
        if self.chat_controller.is_processing:
            self.chat_controller.set_processing(False)
        elif self.chat_panel:
            self.chat_panel.set_turn_activity(ChatTurnPresentation.idle())
        if self.chat_panel:
            self.chat_panel.restore_composer_focus_after_turn()
        self._application_publication_coordinator.flush_terminal()
        self.refresh_backend_status()

    def _render_delivery_terminal_error(
        self,
        terminal: AssistantTurnTerminal,
    ) -> None:
        """Persist one actionable error for a failed host-to-controller delivery."""
        message = _DELIVERY_TERMINAL_MESSAGES.get(terminal.outcome)
        if message is None:
            return
        self._try_render_visible_assistant_response(
            AssistantResponsePresentation(
                text=message,
                correlation=terminal.correlation,
                kind=AssistantResponseKind.ERROR,
            )
        )

    def _render_assistant_runtime(
        self,
        snapshot: AssistantRuntimeSnapshot,
    ) -> None:
        if snapshot.phase in {
            AssistantRuntimePhase.LOADING,
            AssistantRuntimePhase.READY,
        }:
            if self.chat_panel:
                self.chat_panel.clear_runtime_notice()
            self._runtime_unavailable_notice = None
        if self.chat_panel:
            safe_error = (
                self._presentation.runtime_status_message(snapshot.error)
                if snapshot.phase is AssistantRuntimePhase.FAILED
                else ""
            )
            runtime_kwargs = (
                {"execution_device": snapshot.execution_device}
                if snapshot.execution_device
                else {}
            )
            self.chat_panel.set_runtime_state(
                snapshot.phase.value,
                safe_error,
                **runtime_kwargs,
            )
            projection = self._application_publication_coordinator.projection
            if projection is not None:
                self._render_assistant_status_projection(
                    projection,
                    runtime_snapshot=snapshot,
                )

    def refresh_backend_status(self):
        """Refresh the compact backend/model status shown in the chat panel."""
        if not self.chat_panel:
            return

        try:
            self._application_publication_coordinator.refresh()
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="agent_manager",
                operation="refresh_backend_status",
            )
            self.chat_panel.set_product_status(
                stage="checking",
                model_status="checking",
                tooltip=self._presentation.status_refresh_error(),
            )
            self.status_message_received.emit(
                "Workflow status unavailable · Try again",
            )

    def _render_training_terminal(
        self,
        notice: AssistantTrainingTerminalNotice,
    ) -> bool:
        """Render copy only; the publication owner retains/commits delivery."""
        copy = self._presentation.training_terminal_presentation(notice.outcome)
        if copy is None:
            return True
        message, presentation_kind = copy
        return self._try_render_visible_assistant_response(
            AssistantResponsePresentation(
                text=message,
                correlation=notice.correlation,
                kind=presentation_kind,
            ),
            recover_capacity=True,
        )

    def _render_assistant_status_projection(
        self,
        projection: AssistantStatusProjection,
        *,
        runtime_snapshot: AssistantRuntimeSnapshot | None = None,
    ) -> bool:
        """Render workflow truth with the latest local-runtime phase."""
        if not self.chat_panel:
            return False
        runtime = runtime_snapshot or self._assistant_runtime.current
        model_status = (
            "Unknown"
            if not projection.usable
            else {
                AssistantRuntimePhase.READY: "Ready",
                AssistantRuntimePhase.LOADING: "Loading",
                AssistantRuntimePhase.IDLE: "Setup needed",
                AssistantRuntimePhase.FAILED: "Setup needed",
            }[runtime.phase]
        )

        self.chat_panel.set_product_status(
            stage=projection.stage,
            model_status=model_status,
            tooltip=projection.tooltip,
            blocked_reason=projection.blocked_reason,
        )
        self.status_message_received.emit(projection.footer_hint)
        return True

    def close(self) -> bool:
        """Clean up the agent controller resources."""
        self._application_publication_coordinator.close()
        if self.chat_panel:
            self.chat_panel.clear_confirmation_request()
        self._workflow_ui_handoff_host.abandon_active()
        downloads_idle = self._model_download_lifecycle.request_shutdown()
        runtime_closed = self._assistant_runtime.close()
        if runtime_closed:
            terminal = self._assistant_turn_state.shutdown_terminal()
            if terminal is not None:
                self._on_assistant_turn_finished(terminal)
        return runtime_closed and downloads_idle

    def handle_panel_navigation(self, payload: object) -> None:
        """Open one controller-validated panel request without guessing payloads."""
        if not isinstance(payload, AssistantPanelNavigationRequest):
            logger.error(
                "Ignored invalid assistant panel navigation: %s",
                redact_public_text(payload),
            )
            self._show_low_priority_notice(
                "The requested XBrainLab view could not be opened."
            )
            return

        def _resolve(success: bool) -> None:
            if payload.correlation != self._assistant_turn_state.lease:
                return
            self._surface_runtime_command_result(
                self._assistant_runtime.resolve_panel_navigation(
                    payload, success=success
                ),
                fallback="The assistant could not receive the panel navigation result.",
            )

        if payload.correlation is not None:
            self._open_assistant_panel_target(
                payload.target,
                view_mode=payload.view_mode or "",
                on_terminal=_resolve,
            )
        elif payload.view_mode:
            self._open_assistant_panel_target(
                payload.target,
                view_mode=payload.view_mode,
            )
        else:
            self._open_assistant_panel_target(payload.target)

    def handle_workflow_ui_handoff(self, payload: object) -> None:
        """Route one typed backend workflow decision to existing product UI."""
        if not isinstance(payload, WorkflowUiHandoffRequest):
            logger.error(
                "Ignored invalid workflow UI handoff: %s",
                redact_public_text(payload),
            )
            self._show_low_priority_notice(
                "The requested XBrainLab settings could not be opened."
            )
            return
        if not self._assistant_turn_state.accepts_workflow_handoff(payload):
            logger.warning(
                "Ignored workflow UI handoff outside its active turn: %s",
                redact_public_text(payload.request_id),
            )
            return
        try:
            resolution = self._workflow_ui_handoff_host.open(
                payload,
                on_terminal=self._handle_workflow_ui_handoff_terminal,
            )
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="agent_manager",
                operation="open_workflow_ui_handoff",
            )
            resolution = WorkflowUiHandoffResolution.for_request(
                payload,
                status=WorkflowUiHandoffResolutionStatus.FAILED,
                message="The requested XBrainLab settings could not be opened.",
            )
        if not resolution.matches(payload):
            logger.error("Ignored mismatched workflow UI handoff resolution")
            self._show_low_priority_notice(
                "The requested XBrainLab settings did not return a valid result."
            )
            return
        self._forward_workflow_ui_handoff_resolution(resolution)

    def _handle_workflow_ui_handoff_terminal(self, payload: object) -> bool:
        """Forward one host-validated terminal callback to the runtime owner."""
        if not isinstance(payload, WorkflowUiHandoffResolution):
            logger.error(
                "Ignored invalid terminal workflow UI handoff: %s",
                redact_public_text(payload),
            )
            self._show_low_priority_notice(
                "The XBrainLab settings command returned an invalid result."
            )
            return False
        if not payload.status.is_terminal:
            logger.error(
                "Ignored nonterminal workflow UI callback: %s",
                redact_public_text(payload.status),
            )
            return False
        return self._forward_workflow_ui_handoff_resolution(payload)

    def _forward_workflow_ui_handoff_resolution(
        self,
        resolution: WorkflowUiHandoffResolution,
    ) -> bool:
        accepted = self._surface_runtime_command_result(
            self._assistant_runtime.resolve_ui_handoff(resolution),
            fallback=(
                "The assistant could not receive the completed XBrainLab settings step."
            ),
        )
        if not accepted and not resolution.status.is_terminal:
            self._workflow_ui_handoff_host.abandon_active()
        return accepted

    def _show_action_confirmation(self, request: object) -> None:
        """Present one exact assistant action in the transcript for a decision."""
        if not isinstance(request, AgentConfirmationRequest):
            logger.error(
                "Ignored untyped assistant confirmation request: %s",
                redact_public_text(request),
            )
            return
        if not self._assistant_turn_state.accepts_confirmation(
            request_id=request.request_id,
            command_name=request.command_name,
        ):
            logger.warning(
                "Ignored assistant confirmation outside its active turn: %s",
                redact_public_text(request.request_id),
            )
            return
        if self.chat_panel is None:
            logger.error("Assistant confirmation arrived before the panel was ready.")
            return

        self.chat_panel.show_confirmation_request(
            request,
            current_context_changed=self._confirmation_context_changed(request),
        )
        if self.chat_dock is not None:
            self.chat_dock.show()
            self.chat_dock.raise_()

    def _resolve_action_confirmation(
        self,
        resolution: object,
    ) -> None:
        """Return one correlated card decision through the runtime transport."""
        if not isinstance(resolution, AgentConfirmationResolution):
            logger.error(
                "Ignored untyped assistant confirmation decision: %s",
                redact_public_text(resolution),
            )
            return
        if not self._assistant_turn_state.accepts_confirmation(
            request_id=resolution.request_id,
            command_name=resolution.command_name,
        ):
            logger.warning(
                "Ignored stale assistant confirmation decision: %s",
                redact_public_text(resolution.request_id),
            )
            if self.chat_panel is not None:
                self.chat_panel.clear_confirmation_request(resolution.request_id)
            return
        accepted = self._surface_runtime_command_result(
            self._assistant_runtime.confirm(resolution),
            fallback="The assistant could not receive your confirmation.",
        )
        if self.chat_panel is None:
            return
        if accepted:
            self.chat_panel.clear_confirmation_request(resolution.request_id)
        else:
            self.chat_panel.set_confirmation_submitting(
                resolution.request_id,
                False,
            )

    def _confirmation_context_changed(
        self,
        request: AgentConfirmationRequest,
    ) -> bool:
        """Check the request generation against the current publication."""
        try:
            publication = self.application_service.get_view_publication()
        except Exception as exc:
            logger.debug(
                "Could not read confirmation publication: %s",
                redact_public_text(exc),
            )
            return False
        return self._presentation.confirmation_context_changed(request, publication)

    def _switch_sub_view(self, panel_index, view_mode):
        """Switch to a specific tab or view within a panel.

        Args:
            panel_index: Index of the panel in the stacked widget.
            view_mode: String identifier for the target sub-view
                (e.g., ``"saliency_map"``, ``"3d_plot"``).

        """
        # Map panel index to view mode mapping
        view_map = {
            PANEL_VISUALIZATION: {
                "saliency_map": VISUALIZATION_TAB_SALIENCY_MAP,
                "spectrogram": VISUALIZATION_TAB_SPECTROGRAM,
                "topographic_map": VISUALIZATION_TAB_TOPOGRAPHIC_MAP,
                "3d_plot": VISUALIZATION_TAB_3D_PLOT,
            },
            # Future: Add Preprocess or Evaluation panels if they have tabs
        }

        if panel_index in view_map and view_mode in view_map[panel_index]:
            target_panel = self.main_window.stack.widget(panel_index)
            target_tab_index = view_map[panel_index][view_mode]

            if hasattr(target_panel, "tabs"):
                target_panel.tabs.setCurrentIndex(target_tab_index)
                logger.info(
                    "Switched sub-view to %s (Tab %d)",
                    redact_public_text(view_mode),
                    target_tab_index,
                )
