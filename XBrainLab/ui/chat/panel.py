"""Chat Panel - Main chat interface component.

Provides the ``ChatPanel`` widget implementing a Copilot-style chat interface
using ``MessageBubble`` widgets. Handles user input, streaming responses, and
debug-mode interception.
"""

from contextlib import suppress
from weakref import ReferenceType, ref

from PyQt6.QtCore import QEvent, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.controller.chat_controller import (
    ChatController,
    ChatHistoryReplacement,
    ChatHistoryReplacementKind,
)
from XBrainLab.debug.tool_debug_mode import ToolDebugMode
from XBrainLab.llm.agent.confirmation import (
    AgentConfirmationRequest,
    AgentConfirmationResolution,
    AgentConfirmationResolutionStatus,
)
from XBrainLab.llm.agent.runtime_state import AssistantRuntimePhase
from XBrainLab.ui.product_language import workflow_stage_text_label

from ..styles.theme import Theme
from .action_card import AssistantConfirmationCard
from .composer import AssistantComposer
from .presentation import (
    ChatTurnCancelability,
    ChatTurnPresentation,
    ChatTurnPresentationPhase,
)
from .styles import (
    ASSISTANT_PANEL_STYLE,
    COMPOSER_SURFACE_STYLE,
    CONTROL_PANEL_STYLE,
    EMPTY_STATE_STYLE,
    EMPTY_STATE_TEXT_STYLE,
    EMPTY_STATE_TITLE_STYLE,
    INPUT_FIELD_STYLE,
    NOTICE_LABEL_STYLE,
    RUNTIME_PRIMARY_ACTION_STYLE,
    RUNTIME_PROGRESS_STYLE,
    RUNTIME_SECONDARY_ACTION_STYLE,
    RUNTIME_STATE_DETAIL_STYLE,
    RUNTIME_STATE_STYLE,
    RUNTIME_STATE_TITLE_STYLE,
    SEND_BUTTON_LOCKED_STYLE,
    SEND_BUTTON_PROCESSING_STYLE,
    SEND_BUTTON_STYLE,
    TURN_ACTIVITY_CANCELABILITY_STYLE,
    TURN_ACTIVITY_PROGRESS_STYLE,
    TURN_ACTIVITY_STEP_STYLE,
    TURN_ACTIVITY_STYLE,
    TURN_ACTIVITY_TITLE_STYLE,
)
from .suggestion_card import AssistantSuggestionCard
from .transcript_view import ChatTranscriptView

CHAT_SURFACE_MAX_WIDTH = 620
CHAT_CONTROL_MAX_WIDTH = 620
EMPTY_STATE_MAX_WIDTH = 560
STATE_SURFACE_MAX_WIDTH = 540
COMPOSER_ACTION_WIDTH = 84
COMPOSER_ACTION_HEIGHT = 34

EMPTY_STATE_TITLE = "Get started with XBrainLab"
EMPTY_STATE_INTRO = "Choose a prompt or ask your own question."
EMPTY_STATE_SUGGESTIONS = (
    (
        "What should I do next?",
        "Get guidance for the next step in your workflow.",
        "What should I do next?",
    ),
    (
        "Explain my current workflow",
        "Review what is ready and what still needs attention.",
        "Explain my current workflow",
    ),
    (
        "What can you help me with?",
        "See how the Assistant can support your EEG workflow.",
        "What can you help me with?",
    ),
)

WORKFLOW_RUN_STATUS_STYLE = f"""
    QLabel#AssistantWorkflowRunStatus {{
        color: {Theme.TEXT_SECONDARY};
        background: transparent;
        border: none;
        padding: 0px;
        font-size: 12px;
    }}
"""


class ChatPanel(QWidget):
    """Copilot-style chat interface using MessageBubble widgets.

    Features QFrame-based bubbles, sender-based alignment, and dynamic width
    adjustment. UI state is decoupled from business logic via
    ``ChatController``; only completed typed assistant presentations enter the
    transcript.

    Attributes:
        is_processing: Whether the panel is currently awaiting a response.
        debug_mode: Optional ``ToolDebugMode`` for interactive debug
            script playback.
        transcript_view: Scrollable transcript and transient surfaces.
        input_field: Text input for user messages.
        send_btn: Button to send messages or stop generation.
    """

    # UI-driven Signals
    send_message = pyqtSignal(str)
    stop_generation = pyqtSignal()
    debug_tool_requested = pyqtSignal(str, dict, bool, str)
    open_settings_requested = pyqtSignal()
    inline_setup_requested = pyqtSignal(str)
    retry_local_assistant_requested = pyqtSignal()
    confirmation_decision_requested = pyqtSignal(AgentConfirmationResolution)
    header_status_changed = pyqtSignal(str)

    def __init__(self):
        """Initialize the ChatPanel with UI components and optional debug mode."""
        super().__init__()
        self.is_processing = False
        self._runtime_phase = AssistantRuntimePhase.IDLE
        self._notice_owner: str | None = None
        self._runtime_recovery = False
        self._header_status_text = "Local · Setup"
        self._runtime_execution_device = ""
        self._turn_presentation = ChatTurnPresentation.idle()
        self._chat_controller_ref: ReferenceType[ChatController] | None = None
        app = QApplication.instance()
        script_path = app.property("tool_debug_script") if app else None
        self.debug_mode = ToolDebugMode(script_path) if script_path else None
        self.setObjectName("AssistantPanel")
        self.setStyleSheet(ASSISTANT_PANEL_STYLE)
        self.init_ui()
        self._notice_timer = QTimer(self)
        self._notice_timer.setSingleShot(True)
        self._notice_timer.timeout.connect(self._expire_notice)
        self.set_runtime_state(AssistantRuntimePhase.IDLE.value)

    def init_ui(self):
        """Initialize all UI sub-components including chat display and controls."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Shared transcript and transient surfaces ---
        self.runtime_state_widget = self._build_runtime_state()
        self.empty_state_widget = self._build_empty_state()
        self.turn_activity_widget = self._build_turn_activity()
        self.confirmation_card_widget = AssistantConfirmationCard()
        self.confirmation_card_widget.decision_requested.connect(
            self._on_confirmation_decision
        )
        for surface, maximum_width in (
            (self.runtime_state_widget, STATE_SURFACE_MAX_WIDTH),
            (self.empty_state_widget, EMPTY_STATE_MAX_WIDTH),
            (self.confirmation_card_widget, CHAT_SURFACE_MAX_WIDTH),
            (self.turn_activity_widget, STATE_SURFACE_MAX_WIDTH),
        ):
            surface.setMaximumWidth(maximum_width)
            surface.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Maximum,
            )
        self.transcript_view = ChatTranscriptView(
            runtime_surface=self.runtime_state_widget,
            empty_surface=self.empty_state_widget,
            confirmation_surface=self.confirmation_card_widget,
            activity_surface=self.turn_activity_widget,
        )
        layout.addWidget(self.transcript_view, 1)

        # --- Control Panel (Bottom) ---
        control_panel = QWidget()
        self.control_panel = control_panel
        control_panel.setObjectName("ControlPanel")
        control_panel.setStyleSheet(CONTROL_PANEL_STYLE)
        control_panel.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        control_layout = QVBoxLayout(control_panel)
        self.control_layout = control_layout
        control_layout.setContentsMargins(12, 10, 12, 11)
        control_layout.setSpacing(8)

        self.workflow_run_status_label = QLabel("")
        self.workflow_run_status_label.setObjectName("AssistantWorkflowRunStatus")
        self.workflow_run_status_label.setStyleSheet(WORKFLOW_RUN_STATUS_STYLE)
        self.workflow_run_status_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.workflow_run_status_label.setWordWrap(True)
        self.workflow_run_status_label.setContentsMargins(4, 0, 4, 0)
        self.workflow_run_status_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        self.workflow_run_status_label.setVisible(False)
        control_layout.addWidget(self.workflow_run_status_label)

        # Composer: Input Field and Send / Stop Button
        input_widget = QWidget()
        self.input_widget = input_widget
        input_widget.setObjectName("AssistantComposerSurface")
        input_widget.setProperty("inputFocused", False)
        input_widget.setStyleSheet(COMPOSER_SURFACE_STYLE)
        input_widget.setMaximumWidth(CHAT_CONTROL_MAX_WIDTH)
        input_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        input_layout = QBoxLayout(
            QBoxLayout.Direction.LeftToRight,
            input_widget,
        )
        self.input_layout = input_layout
        input_layout.setContentsMargins(6, 6, 6, 6)
        input_layout.setSpacing(6)

        self.input_field = AssistantComposer()
        self._restore_composer_focus_after_turn = False
        self.input_field.setPlaceholderText("Ask about EEG...")
        self.input_field.setAccessibleName("Assistant message")
        self.input_field.setAccessibleDescription(
            "Ask about the current EEG workflow or describe the next action you need."
        )
        self.input_field.setStyleSheet(INPUT_FIELD_STYLE)
        self.input_field.installEventFilter(self)
        self.input_field.submit_requested.connect(self._on_send)
        self.input_field.textChanged.connect(self._apply_composer_activity_state)
        input_layout.addWidget(self.input_field, 1)

        self.composer_actions = QWidget(input_widget)
        self.composer_actions.setObjectName("AssistantComposerActions")
        self.composer_actions.setStyleSheet("background: transparent; border: none;")
        self.composer_actions.setFixedSize(
            COMPOSER_ACTION_WIDTH,
            COMPOSER_ACTION_HEIGHT,
        )
        self.composer_actions.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        composer_action_layout = QHBoxLayout(self.composer_actions)
        self.composer_action_layout = composer_action_layout
        composer_action_layout.setContentsMargins(0, 0, 0, 0)
        composer_action_layout.setSpacing(0)

        self.send_btn = QToolButton()
        self.send_btn.setObjectName("AssistantSendButton")
        self.send_btn.setText("Send")
        self.send_btn.setAccessibleName("Send")
        self.send_btn.setFixedSize(COMPOSER_ACTION_WIDTH, COMPOSER_ACTION_HEIGHT)
        self.send_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.send_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.clicked.connect(self._on_send)
        self.send_btn.setStyleSheet(SEND_BUTTON_STYLE)
        composer_action_layout.addWidget(self.send_btn)
        composer_action_layout.setAlignment(
            self.send_btn,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
        )
        input_layout.addWidget(
            self.composer_actions,
            0,
            Qt.AlignmentFlag.AlignBottom,
        )

        self.composer_host = self._build_centered_control_host(input_widget)
        control_layout.addWidget(self.composer_host)

        self.notice_label = QLabel("")
        self.notice_label.setObjectName("AssistantNotice")
        self.notice_label.setStyleSheet(NOTICE_LABEL_STYLE)
        self.notice_label.setWordWrap(True)
        self.notice_label.setVisible(False)
        control_layout.addWidget(self.notice_label)
        layout.addWidget(control_panel, 0)
        self.transcript_view.surface_fit_requested.connect(
            self._fit_chat_surfaces_to_viewport
        )
        self.transcript_view.content_changed.connect(
            self._on_transcript_content_changed
        )
        self.transcript_view.history_replacement_started.connect(
            self._on_history_replacement_started
        )

    @staticmethod
    def _build_centered_control_host(control: QWidget) -> QWidget:
        """Center one expanding control without making its max width a minimum."""
        host = QWidget()
        host.setStyleSheet("background: transparent; border: none;")
        host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        host_layout = QHBoxLayout(host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(0)
        host_layout.addStretch(1)
        host_layout.addWidget(control, 1000)
        host_layout.addStretch(1)
        return host

    def _build_runtime_state(self) -> QFrame:
        """Build the single inline local-runtime status and recovery surface."""
        state = QFrame()
        state.setObjectName("AssistantRuntimeState")
        state.setStyleSheet(RUNTIME_STATE_STYLE)
        state_layout = QVBoxLayout(state)
        state_layout.setContentsMargins(14, 12, 14, 12)
        state_layout.setSpacing(7)

        self.runtime_state_title = QLabel("")
        self.runtime_state_title.setObjectName("AssistantRuntimeTitle")
        self.runtime_state_title.setStyleSheet(RUNTIME_STATE_TITLE_STYLE)
        self.runtime_state_title.setWordWrap(True)
        state_layout.addWidget(self.runtime_state_title)

        self.runtime_state_detail = QLabel("")
        self.runtime_state_detail.setObjectName("AssistantRuntimeDetail")
        self.runtime_state_detail.setStyleSheet(RUNTIME_STATE_DETAIL_STYLE)
        self.runtime_state_detail.setWordWrap(True)
        state_layout.addWidget(self.runtime_state_detail)

        self.runtime_progress = QProgressBar()
        self.runtime_progress.setObjectName("AssistantRuntimeProgress")
        self.runtime_progress.setRange(0, 0)
        self.runtime_progress.setTextVisible(False)
        self.runtime_progress.setFixedHeight(4)
        self.runtime_progress.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.runtime_progress.setAccessibleName("Local assistant startup progress")
        self.runtime_progress.setStyleSheet(RUNTIME_PROGRESS_STYLE)
        self.runtime_progress.setVisible(False)
        state_layout.addWidget(self.runtime_progress)

        self.runtime_actions = QWidget()
        self.runtime_actions.setObjectName("AssistantRuntimeActions")
        self.runtime_actions.setStyleSheet("background: transparent; border: none;")
        action_layout = QBoxLayout(
            QBoxLayout.Direction.LeftToRight,
            self.runtime_actions,
        )
        self.runtime_action_layout = action_layout
        action_layout.setContentsMargins(0, 2, 0, 0)
        action_layout.setSpacing(8)

        self.retry_runtime_btn = QPushButton("Retry local assistant")
        self._runtime_primary_action = "retry"
        self.retry_runtime_btn.setObjectName("AssistantRetryRuntimeButton")
        self.retry_runtime_btn.setMinimumHeight(34)
        self.retry_runtime_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.retry_runtime_btn.setAccessibleName("Retry local assistant")
        self.retry_runtime_btn.setProperty(
            "assistantFullLabel",
            "Retry local assistant",
        )
        self.retry_runtime_btn.setToolTip(
            "Try to start the selected local model again."
        )
        self.retry_runtime_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry_runtime_btn.setStyleSheet(RUNTIME_PRIMARY_ACTION_STYLE)
        self.retry_runtime_btn.ensurePolished()
        self.retry_runtime_btn.setMinimumWidth(0)
        self.retry_runtime_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.retry_runtime_btn.clicked.connect(self._dispatch_runtime_primary_action)
        self.retry_runtime_btn.setVisible(False)
        self.retry_runtime_btn.setEnabled(False)
        action_layout.addWidget(self.retry_runtime_btn, 1)

        self.setup_btn = QPushButton("Open Assistant Settings")
        self.setup_btn.setObjectName("AssistantSetupButton")
        self.setup_btn.setMinimumHeight(34)
        self.setup_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setup_btn.setAccessibleName("Open Assistant Settings")
        self.setup_btn.setProperty(
            "assistantFullLabel",
            "Open Assistant Settings",
        )
        self.setup_btn.setStyleSheet(RUNTIME_PRIMARY_ACTION_STYLE)
        self.setup_btn.ensurePolished()
        self.setup_btn.setMinimumWidth(0)
        self.setup_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setup_btn.clicked.connect(self.open_settings_requested)
        self.setup_btn.setVisible(False)
        action_layout.addWidget(self.setup_btn, 1)
        self.runtime_actions.setVisible(False)
        state_layout.addWidget(self.runtime_actions)
        state.setVisible(False)
        return state

    def show_inline_setup(self, detail: str, *, cache_ready: bool) -> None:
        """Present first-run setup without starting the local runtime."""
        self._hide_runtime_surfaces()
        self.runtime_state_title.setText("Start XBrainLab Assistant")
        self.runtime_state_detail.setText(detail)
        self.runtime_state_widget.setVisible(True)
        self.retry_runtime_btn.setVisible(True)
        self.retry_runtime_btn.setEnabled(True)
        self._runtime_primary_action = "enable" if cache_ready else "open_settings"
        primary_label = "Enable Assistant" if cache_ready else "Set up model"
        self.retry_runtime_btn.setText(primary_label)
        self.retry_runtime_btn.setProperty("assistantFullLabel", primary_label)
        self.retry_runtime_btn.setAccessibleName(self.retry_runtime_btn.text())
        self.retry_runtime_btn.setStyleSheet(RUNTIME_PRIMARY_ACTION_STYLE)
        self.setup_btn.setText("Assistant Settings")
        self.setup_btn.setProperty("assistantFullLabel", "Assistant Settings")
        self.setup_btn.setAccessibleName("Assistant Settings")
        self.setup_btn.setStyleSheet(RUNTIME_SECONDARY_ACTION_STYLE)
        self.setup_btn.setVisible(True)
        self.runtime_actions.setVisible(True)
        self._fit_runtime_state_to_contents()
        self._publish_header_status()
        self.transcript_view.refresh_layout()

    def _dispatch_runtime_primary_action(self) -> None:
        if self._runtime_primary_action == "retry":
            self._request_runtime_retry()
        else:
            self.inline_setup_requested.emit(self._runtime_primary_action)

    def _request_runtime_retry(self) -> None:
        """Request another local-runtime start only from a failed state."""
        if self._runtime_phase is AssistantRuntimePhase.FAILED:
            self.retry_local_assistant_requested.emit()

    def _build_turn_activity(self) -> QFrame:
        """Build the primary progress surface for one active assistant turn."""
        activity = QFrame()
        activity.setObjectName("AssistantTurnActivity")
        activity.setStyleSheet(TURN_ACTIVITY_STYLE)
        activity.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Minimum,
        )
        activity_layout = QVBoxLayout(activity)
        activity_layout.setContentsMargins(14, 12, 14, 12)
        activity_layout.setSpacing(7)

        self.turn_activity_title = QLabel("")
        self.turn_activity_title.setObjectName("AssistantTurnActivityTitle")
        self.turn_activity_title.setStyleSheet(TURN_ACTIVITY_TITLE_STYLE)
        self.turn_activity_title.setWordWrap(True)
        activity_layout.addWidget(self.turn_activity_title)

        self.turn_activity_step = QLabel("")
        self.turn_activity_step.setObjectName("AssistantTurnActivityStep")
        self.turn_activity_step.setStyleSheet(TURN_ACTIVITY_STEP_STYLE)
        self.turn_activity_step.setWordWrap(True)
        activity_layout.addWidget(self.turn_activity_step)

        self.turn_activity_progress = QProgressBar()
        self.turn_activity_progress.setObjectName("AssistantTurnActivityProgress")
        self.turn_activity_progress.setRange(0, 0)
        self.turn_activity_progress.setTextVisible(False)
        self.turn_activity_progress.setFixedHeight(4)
        self.turn_activity_progress.setAccessibleName("Assistant request progress")
        self.turn_activity_progress.setStyleSheet(TURN_ACTIVITY_PROGRESS_STYLE)
        activity_layout.addWidget(self.turn_activity_progress)

        self.turn_activity_cancelability = QLabel("")
        self.turn_activity_cancelability.setObjectName(
            "AssistantTurnActivityCancelability"
        )
        self.turn_activity_cancelability.setStyleSheet(
            TURN_ACTIVITY_CANCELABILITY_STYLE
        )
        self.turn_activity_cancelability.setWordWrap(True)
        activity_layout.addWidget(self.turn_activity_cancelability)

        activity.setVisible(False)
        return activity

    def _build_empty_state(self) -> QFrame:
        """Build the fixed onboarding shown before conversation starts."""
        empty = QFrame()
        empty.setObjectName("AssistantEmptyState")
        empty.setStyleSheet(EMPTY_STATE_STYLE)
        empty_layout = QVBoxLayout(empty)
        self.empty_state_layout = empty_layout
        empty_layout.setContentsMargins(10, 12, 10, 12)
        empty_layout.setSpacing(10)
        empty.setAccessibleName(EMPTY_STATE_TITLE)
        empty.setAccessibleDescription(EMPTY_STATE_INTRO)

        self.empty_state_title = QLabel(EMPTY_STATE_TITLE)
        self.empty_state_title.setObjectName("AssistantEmptyTitle")
        self.empty_state_title.setStyleSheet(EMPTY_STATE_TITLE_STYLE)
        self.empty_state_title.setWordWrap(True)
        self.empty_state_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state_title.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        empty_layout.addWidget(self.empty_state_title)

        self.empty_state_intro = QLabel(EMPTY_STATE_INTRO)
        self.empty_state_intro.setWordWrap(True)
        self.empty_state_intro.setStyleSheet(EMPTY_STATE_TEXT_STYLE)
        self.empty_state_intro.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_state_intro)

        empty_layout.addSpacing(98)

        self.suggestion_prompt_widget = QWidget(empty)
        self.suggestion_prompt_widget.setObjectName("AssistantSuggestionPrompts")
        self.suggestion_prompt_widget.setStyleSheet(
            "background: transparent; border: none;"
        )
        self.suggestion_prompt_layout = QVBoxLayout(self.suggestion_prompt_widget)
        self.suggestion_prompt_layout.setContentsMargins(0, 0, 0, 0)
        self.suggestion_prompt_layout.setSpacing(14)

        self.suggestion_prompt_buttons: list[AssistantSuggestionCard] = []
        for title, subtitle, prompt in EMPTY_STATE_SUGGESTIONS:
            button = AssistantSuggestionCard(
                title,
                subtitle,
                parent=self.suggestion_prompt_widget,
            )
            button.setProperty("assistantPrompt", prompt)
            button.clicked.connect(
                lambda _checked=False, selected=button: (
                    self._fill_suggestion_prompt(selected)
                )
            )
            self.suggestion_prompt_buttons.append(button)
            self.suggestion_prompt_layout.addWidget(button)
        empty_layout.addWidget(self.suggestion_prompt_widget)

        return empty

    def _fill_suggestion_prompt(self, button: AssistantSuggestionCard) -> None:
        """Place a suggestion in the composer so the user remains in control."""
        prompt = button.property("assistantPrompt")
        if (
            not isinstance(prompt, str)
            or not prompt.strip()
            or self.is_processing
            or self._runtime_phase is not AssistantRuntimePhase.READY
        ):
            return
        self.input_field.setText(prompt)
        self.input_field.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def show_confirmation_request(
        self,
        request: AgentConfirmationRequest,
        *,
        current_context_changed: bool = False,
    ) -> None:
        """Show one transient typed confirmation inside the message area."""
        follow_tail = (
            self.transcript_view.following_tail or self.transcript_view.is_near_bottom()
        )
        self.empty_state_widget.setVisible(False)
        self.confirmation_card_widget.present(
            request,
            current_context_changed=current_context_changed,
        )
        if self._turn_presentation.phase is ChatTurnPresentationPhase.WAITING:
            self.turn_activity_widget.setVisible(False)
        self.transcript_view.refresh_layout(follow_tail=follow_tail)

    def set_confirmation_submitting(
        self,
        request_id: str,
        submitting: bool,
    ) -> None:
        """Update only the currently visible correlated confirmation card."""
        if self.confirmation_card_widget.request_id == request_id:
            self.confirmation_card_widget.set_submitting(submitting)

    def clear_confirmation_request(self, request_id: str | None = None) -> None:
        """Clear one matching transient confirmation view lease."""
        if (
            request_id is not None
            and self.confirmation_card_widget.request_id != request_id
        ):
            return
        self.confirmation_card_widget.clear()
        if (
            self._runtime_phase is AssistantRuntimePhase.READY
            and self._turn_presentation.phase is ChatTurnPresentationPhase.WAITING
        ):
            self.turn_activity_widget.setVisible(True)
        if (
            self._runtime_phase is AssistantRuntimePhase.READY
            and not self.transcript_view.has_messages()
            and not self.turn_activity_widget.isVisible()
        ):
            self.empty_state_widget.setVisible(True)
        self.transcript_view.refresh_layout(deferred=True)

    def _on_confirmation_decision(
        self,
        request: AgentConfirmationRequest,
        approved: bool,
    ) -> None:
        """Forward one complete correlated resolution without applying state."""
        status = (
            AgentConfirmationResolutionStatus.APPROVED
            if approved
            else AgentConfirmationResolutionStatus.CANCELLED
        )
        self.confirmation_decision_requested.emit(
            AgentConfirmationResolution.for_request(request, status=status)
        )

    def connect_controller(self, controller: ChatController):
        """Connect to a backend ChatController for state synchronization.

        Wires the controller's typed transcript and processing signals to the
        corresponding UI rendering methods.

        Args:
            controller: The ``ChatController`` instance to bind.

        """
        if not isinstance(controller, ChatController):
            raise TypeError("ChatPanel requires a ChatController.")
        previous = (
            self._chat_controller_ref()
            if self._chat_controller_ref is not None
            else None
        )
        if previous is not None and previous is not controller:
            with suppress(TypeError):
                previous.message_record_added.disconnect(
                    self.transcript_view.append_record
                )
            with suppress(TypeError):
                previous.processing_state_changed.disconnect(self._update_processing_ui)
            with suppress(TypeError):
                previous.history_replaced.disconnect(self._on_history_replaced)
        if previous is not controller:
            controller.message_record_added.connect(self.transcript_view.append_record)
            controller.processing_state_changed.connect(self._update_processing_ui)
            controller.history_replaced.connect(self._on_history_replaced)
        self._chat_controller_ref = ref(controller)
        self._restore_controller_state(controller)

    def _restore_controller_state(self, controller: ChatController) -> None:
        """Rebuild a controller snapshot without monopolizing the Qt thread."""
        self._on_history_replaced(
            ChatHistoryReplacement(
                kind=ChatHistoryReplacementKind.RESTORE,
                records=controller.get_typed_history(),
            )
        )
        self._update_processing_ui(controller.is_processing)

    def _on_history_replaced(self, replacement: ChatHistoryReplacement) -> None:
        """Render one immutable controller snapshot without polling live truth."""
        if not isinstance(replacement, ChatHistoryReplacement):
            raise TypeError("ChatPanel history replacements must be typed.")
        self.transcript_view.replace_history(replacement)

    def _on_history_replacement_started(self, has_records: bool) -> None:
        """Clear transient decisions only after the viewport captures its reader."""
        self.clear_confirmation_request()
        if has_records:
            self.empty_state_widget.setVisible(False)

    def _on_transcript_content_changed(self) -> None:
        """Project transcript presence without duplicating its rendered state."""
        self.empty_state_widget.setVisible(
            not self.transcript_view.has_messages()
            and self._runtime_phase is AssistantRuntimePhase.READY
        )

    def _sync_control_context_visibility(self) -> None:
        """Keep transient workflow copy in the typed activity surface."""
        self.workflow_run_status_label.setVisible(False)

    def set_turn_activity(self, presentation: ChatTurnPresentation) -> None:
        """Render one complete typed status, step, and cancelability state."""
        if not isinstance(presentation, ChatTurnPresentation):
            raise TypeError("ChatPanel turn activity must be typed.")
        self._turn_presentation = presentation
        self.is_processing = presentation.is_busy
        self.turn_activity_title.setText(presentation.primary_status)
        self.turn_activity_step.setText(
            f"Current step: {presentation.step}" if presentation.step else ""
        )
        self.turn_activity_cancelability.setText(presentation.cancelability_text)
        self.turn_activity_widget.setProperty(
            "assistantCancelability",
            presentation.cancelability.value,
        )
        confirmation_owns_waiting_state = (
            presentation.phase is ChatTurnPresentationPhase.WAITING
            and self.confirmation_card_widget.isVisible()
        )
        self.turn_activity_widget.setVisible(
            presentation.is_visible
            and self._runtime_phase is AssistantRuntimePhase.READY
            and not confirmation_owns_waiting_state
        )
        if presentation.is_visible:
            self.empty_state_widget.setVisible(False)
        elif (
            self._runtime_phase is AssistantRuntimePhase.READY
            and not self.transcript_view.has_messages()
            and not self.confirmation_card_widget.isVisible()
        ):
            self.empty_state_widget.setVisible(True)
        self._apply_composer_activity_state()
        self._sync_control_context_visibility()
        self._publish_header_status()
        self.transcript_view.refresh_layout()
        if presentation.is_visible and self.transcript_view.is_near_bottom():
            self.transcript_view.follow_tail()

    def _apply_composer_activity_state(self) -> None:
        """Expose Stop only while the typed state says cancellation is accepted."""
        runtime_ready = (
            self._runtime_phase is AssistantRuntimePhase.READY
            or self.debug_mode is not None
        )
        cancelability = self._turn_presentation.cancelability
        waiting_for_user = (
            self._turn_presentation.phase is ChatTurnPresentationPhase.WAITING
        )
        if self.is_processing and waiting_for_user:
            self.send_btn.setText("Waiting")
            self.send_btn.setAccessibleName("Waiting for your decision")
            self.send_btn.setIcon(QIcon())
            self.send_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            self.send_btn.setToolTip(self._turn_presentation.cancelability_text)
            self.send_btn.setStyleSheet(SEND_BUTTON_LOCKED_STYLE)
            send_enabled = False
        elif self.is_processing and cancelability is ChatTurnCancelability.CANCELLABLE:
            self.send_btn.setText("Stop")
            self.send_btn.setAccessibleName("Stop current request")
            self.send_btn.setIcon(QIcon())
            self.send_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            self.send_btn.setToolTip("Stop this request before an action starts.")
            self.send_btn.setStyleSheet(SEND_BUTTON_PROCESSING_STYLE)
            send_enabled = runtime_ready
        elif self.is_processing:
            stopping = cancelability is ChatTurnCancelability.STOPPING
            self.send_btn.setText("Stopping" if stopping else "Working")
            self.send_btn.setAccessibleName(
                "Stopping current request" if stopping else "Assistant is working"
            )
            self.send_btn.setIcon(QIcon())
            self.send_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            self.send_btn.setToolTip(
                "Waiting for the local assistant to stop."
                if stopping
                else (
                    "This XBrainLab action has already started and cannot be "
                    "stopped safely."
                )
            )
            self.send_btn.setStyleSheet(SEND_BUTTON_LOCKED_STYLE)
            send_enabled = False
        else:
            self.send_btn.setText("Send")
            self.send_btn.setAccessibleName("Send request")
            self.send_btn.setIcon(QIcon())
            self.send_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            self.send_btn.setToolTip("Send request")
            self.send_btn.setStyleSheet(SEND_BUTTON_STYLE)
            send_enabled = runtime_ready and (
                self.debug_mode.can_dispatch
                if self.debug_mode is not None
                else bool(self.input_field.text().strip())
            )

        self._fit_composer_action_width()
        self.input_field.setEnabled(
            not self.is_processing
            and runtime_ready
            and (self.debug_mode is None or self.debug_mode.can_dispatch)
        )
        self.send_btn.setEnabled(send_enabled)
        for button in getattr(self, "suggestion_prompt_buttons", ()):
            prompt = button.property("assistantPrompt")
            button.setEnabled(
                isinstance(prompt, str)
                and bool(prompt.strip())
                and not self.is_processing
                and runtime_ready
            )

    def reject_debug_step(self, message: str) -> None:
        """Release a step rejected before controller ownership was established."""
        if self.debug_mode is None:
            return
        self.debug_mode.reject_pending()
        if message:
            self.show_notice(message)
        self._refresh_debug_walkthrough_ui()

    def complete_debug_step(self, outcome: str) -> None:
        """Commit one diagnostic step only after its correlated terminal."""
        if self.debug_mode is None or not self.debug_mode.is_waiting:
            return
        self.debug_mode.complete_pending(str(outcome or ""))
        if self.debug_mode.failure:
            self.show_notice(self.debug_mode.failure)
        self._refresh_debug_walkthrough_ui()

    def _refresh_debug_walkthrough_ui(self) -> None:
        """Render the approved slim walkthrough progress and Enter gate."""
        if self.debug_mode is None:
            return
        progress = self.debug_mode.progress_text
        self.workflow_run_status_label.setText(progress)
        self.workflow_run_status_label.setToolTip(progress)
        self.workflow_run_status_label.setVisible(True)
        if self.debug_mode.is_complete:
            placeholder = "Walkthrough complete"
        elif self.debug_mode.failure:
            placeholder = "Walkthrough stopped"
        elif self.debug_mode.is_waiting:
            placeholder = "Complete the current action in XBrainLab"
        else:
            placeholder = "Press Enter to run the next action"
        self.input_field.setPlaceholderText(placeholder)
        self._apply_composer_activity_state()

    def eventFilter(self, watched, event):  # noqa: N802
        """Reflect composer focus on its integrated input surface."""
        input_field = getattr(self, "input_field", None)
        input_widget = getattr(self, "input_widget", None)
        if (
            watched is input_field
            and input_widget is not None
            and event.type()
            in {
                QEvent.Type.FocusIn,
                QEvent.Type.FocusOut,
            }
        ):
            input_widget.setProperty(
                "inputFocused",
                event.type() is QEvent.Type.FocusIn,
            )
            style = input_widget.style()
            if style is not None:
                style.unpolish(input_widget)
                style.polish(input_widget)
        return super().eventFilter(watched, event)

    def _on_send(self):
        """Handle send button click or Enter key press.

        If currently processing, emits ``stop_generation``. If debug mode
        is active, dispatches the next debug tool call. Otherwise, emits
        ``send_message`` with the user's input text.
        """
        # UI Check: Processing state is now managed via signals
        # Use internal state instead of checking button text
        if (
            self.is_processing
            and self._turn_presentation.cancelability
            is ChatTurnCancelability.CANCELLABLE
        ):
            self.stop_generation.emit()
            return
        if self.is_processing:
            return

        # M3.1 Debug Mode Interception
        if self.debug_mode:
            call = self.debug_mode.begin_call()
            if call is not None:
                self.input_field.clear()
                self._refresh_debug_walkthrough_ui()
                self.debug_tool_requested.emit(call.tool, call.params, False, "")
            return

        if self._runtime_phase is not AssistantRuntimePhase.READY:
            return

        text = self.input_field.text().strip()
        if not text:
            return

        self.send_message.emit(text)
        # The typed assistant activity publication owns the processing state.

    def accept_composer_submission(self, text: str) -> None:
        """Clear only the exact draft that the runtime accepted."""
        submitted = str(text or "").strip()
        if submitted and self.input_field.text().strip() == submitted:
            self._restore_composer_focus_after_turn = self.input_field.hasFocus()
            self.input_field.clear()
        if self._notice_owner == "submission":
            self._set_notice("", timeout_ms=0, owner=None)

    def restore_composer_focus_after_turn(self) -> None:
        """Return focus only to the composer that submitted the completed turn."""
        restore = self._restore_composer_focus_after_turn
        self._restore_composer_focus_after_turn = False
        if (
            restore
            and self.isVisible()
            and self.input_field.isEnabled()
            and not self.confirmation_card_widget.isVisible()
        ):
            self.input_field.setFocus(Qt.FocusReason.OtherFocusReason)

    def reject_composer_submission(self, text: str, message: str) -> None:
        """Keep a rejected request editable and expose a persistent inline reason."""
        submitted = str(text or "").strip()
        if submitted and not self.input_field.text().strip():
            self.input_field.setText(submitted)
        self.input_field.setFocus(Qt.FocusReason.OtherFocusReason)
        self._set_notice(str(message or "").strip(), timeout_ms=0, owner="submission")

    def _update_processing_ui(self, is_processing: bool):
        """Restore legacy boolean state without assuming cancellation is safe."""
        if is_processing:
            if (
                self._runtime_phase is not AssistantRuntimePhase.READY
                and self.debug_mode is None
            ):
                self.set_turn_activity(ChatTurnPresentation.idle())
                return
            if not self._turn_presentation.is_busy:
                self.set_turn_activity(ChatTurnPresentation.restored_busy())
            else:
                self._apply_composer_activity_state()
            return
        self.workflow_run_status_label.clear()
        self.workflow_run_status_label.setToolTip("")
        self.set_turn_activity(ChatTurnPresentation.idle())

    def set_runtime_state(
        self,
        phase: str,
        message: str = "",
        *,
        execution_device: str = "",
    ) -> None:
        """Apply one worker-published runtime state to the visible composer."""
        previous_phase = self._runtime_phase
        self._runtime_execution_device = str(execution_device or "").strip().lower()
        try:
            self._runtime_phase = AssistantRuntimePhase(str(phase).lower())
        except ValueError:
            self._runtime_phase = AssistantRuntimePhase.FAILED
        if (
            self._runtime_phase is not AssistantRuntimePhase.FAILED
            and self._notice_owner == "runtime"
        ):
            self._notice_owner = None
            self.notice_label.setText("")
            self.notice_label.setVisible(False)
        self._runtime_recovery = (
            self._runtime_phase is AssistantRuntimePhase.LOADING
            and (
                previous_phase is AssistantRuntimePhase.FAILED
                or (
                    previous_phase is AssistantRuntimePhase.LOADING
                    and self._runtime_recovery
                )
            )
        )

        self._hide_runtime_surfaces()

        if self._runtime_phase is not AssistantRuntimePhase.READY:
            self.is_processing = False

        if self.debug_mode is not None:
            self.input_widget.setVisible(True)
            self.runtime_progress.setVisible(False)
            self.retry_runtime_btn.setVisible(False)
            self.retry_runtime_btn.setEnabled(False)
            self.setup_btn.setVisible(False)
            self.runtime_actions.setVisible(False)
            self.runtime_state_widget.setVisible(False)
            self._update_processing_ui(self.is_processing)
            self._refresh_debug_walkthrough_ui()
            return

        if self._runtime_phase is AssistantRuntimePhase.LOADING:
            self.input_widget.setVisible(True)
            title = (
                "Retrying local assistant"
                if self._runtime_recovery
                else "Loading local assistant"
            )
            detail = (
                "Applying Assistant Settings and retrying the local model."
                if self._runtime_recovery
                else "Preparing the selected local model...\nThis may take a moment."
            )
            placeholder = (
                "Retrying assistant..."
                if self._runtime_recovery
                else "Loading assistant..."
            )
            self.input_field.setPlaceholderText(placeholder)
            self.runtime_state_title.setText(title)
            self.runtime_state_detail.setText(detail)
            self.runtime_state_widget.setVisible(True)
            self.runtime_progress.setVisible(True)
            self.workflow_run_status_label.setText("")
            self.workflow_run_status_label.setVisible(False)
            self.retry_runtime_btn.setVisible(False)
            self.retry_runtime_btn.setEnabled(False)
            self.setup_btn.setVisible(False)
            self.runtime_actions.setVisible(False)
        elif self._runtime_phase is AssistantRuntimePhase.READY:
            self.input_widget.setVisible(True)
            self.input_field.setPlaceholderText("Ask about EEG...")
            self.workflow_run_status_label.setVisible(False)
            self.runtime_progress.setVisible(False)
            self.retry_runtime_btn.setVisible(False)
            self.retry_runtime_btn.setEnabled(False)
            self.setup_btn.setVisible(False)
            self.runtime_actions.setVisible(False)
            self.runtime_state_widget.setVisible(False)
            if not self.transcript_view.has_messages():
                self.empty_state_widget.setVisible(True)
        else:
            is_failed = self._runtime_phase is AssistantRuntimePhase.FAILED
            self._runtime_primary_action = "retry"
            title = "Assistant unavailable" if is_failed else "Assistant setup required"
            detail = self._plain_runtime_message(message)
            if not detail:
                detail = (
                    "The selected local model could not start. Review the assistant "
                    "settings and try again."
                    if is_failed
                    else "Choose a local model before using the assistant."
                )
            self.input_field.setPlaceholderText(
                "Assistant unavailable" if is_failed else "Set up assistant"
            )
            self.runtime_state_title.setText(title)
            self.runtime_state_detail.setText(detail)
            self.runtime_state_widget.setVisible(True)
            self.runtime_progress.setVisible(False)
            self.empty_state_widget.setVisible(False)
            self.workflow_run_status_label.setText("")
            self.workflow_run_status_label.setVisible(False)
            self.retry_runtime_btn.setVisible(is_failed)
            self.retry_runtime_btn.setEnabled(is_failed)
            self.setup_btn.setText(
                "Settings" if is_failed else "Open Assistant Settings"
            )
            self.setup_btn.setProperty(
                "assistantFullLabel",
                self.setup_btn.text(),
            )
            self.setup_btn.setAccessibleName("Open Assistant Settings")
            self.setup_btn.setStyleSheet(
                RUNTIME_SECONDARY_ACTION_STYLE
                if is_failed
                else RUNTIME_PRIMARY_ACTION_STYLE
            )
            self.setup_btn.setVisible(True)
            self.runtime_actions.setVisible(True)
            self.input_widget.setVisible(True)
        self._fit_runtime_state_to_contents()
        self._update_processing_ui(self.is_processing)
        self._publish_header_status()
        self.transcript_view.refresh_layout()
        if (
            self._runtime_phase is not AssistantRuntimePhase.READY
            and self.transcript_view.has_messages()
            and (
                self.transcript_view.following_tail
                or self.transcript_view.is_near_bottom()
            )
        ):
            self.transcript_view.follow_tail()

    def _hide_runtime_surfaces(self) -> None:
        """Reset mutually exclusive runtime surfaces before rendering a phase."""
        self.runtime_state_widget.setVisible(False)
        self.empty_state_widget.setVisible(False)

    def _publish_header_status(self) -> None:
        """Publish one compact header state derived from existing typed state."""
        if self._runtime_phase is AssistantRuntimePhase.LOADING:
            status = "Local · Loading"
        elif self._runtime_phase is AssistantRuntimePhase.FAILED:
            status = "Local · Error"
        elif self._runtime_phase is AssistantRuntimePhase.READY:
            if self._turn_presentation.phase is ChatTurnPresentationPhase.WAITING:
                status = "Local · Waiting"
            elif self._turn_presentation.is_busy:
                status = "Local · Working"
            elif self._runtime_execution_device == "cpu":
                status = "Local · CPU"
            else:
                status = "Local · Ready"
        else:
            status = "Local · Setup"
        self._header_status_text = status
        self.header_status_changed.emit(status)

    @property
    def header_status_text(self) -> str:
        """Return the latest UI-only compact runtime status."""
        return self._header_status_text

    def _fit_runtime_state_to_contents(self) -> None:
        """Synchronize recovery-card geometry before the next Qt paint cycle."""
        action_layout = self.runtime_actions.layout()
        if action_layout is not None:
            for button in (self.retry_runtime_btn, self.setup_btn):
                button.setText(str(button.property("assistantFullLabel")))
                button.ensurePolished()
                button.setMinimumWidth(0)
            action_layout.invalidate()
            action_layout.activate()
            for button in (self.retry_runtime_btn, self.setup_btn):
                self._fit_button_label(button)
            action_layout.activate()
            self.runtime_actions.setMinimumHeight(action_layout.sizeHint().height())
        state_layout = self.runtime_state_widget.layout()
        if state_layout is not None:
            state_layout.activate()
            self.runtime_state_widget.setMinimumHeight(
                state_layout.sizeHint().height() + 4
            )
        self.runtime_actions.updateGeometry()
        self.runtime_state_widget.updateGeometry()

    def _fit_composer_action_width(self) -> None:
        """Reserve native button chrome and the current state label at any DPI."""
        self.send_btn.ensurePolished()
        required_width = max(
            COMPOSER_ACTION_WIDTH,
            self.send_btn.sizeHint().width(),
            self.send_btn.fontMetrics().horizontalAdvance(self.send_btn.text()) + 24,
        )
        self.composer_actions.setFixedSize(
            required_width,
            COMPOSER_ACTION_HEIGHT,
        )
        self.send_btn.setFixedSize(required_width, COMPOSER_ACTION_HEIGHT)

    @staticmethod
    def _fit_button_label(button: QPushButton) -> None:
        """Elide a native button from its measured decoration and live width."""
        full_label = button.property("assistantFullLabel")
        if not isinstance(full_label, str) or not full_label:
            return
        button.setText(full_label)
        button.ensurePolished()
        metrics = button.fontMetrics()
        available_width = button.width()
        full_size_hint = button.sizeHint().width()
        if full_size_hint <= available_width:
            return
        decoration_width = max(
            full_size_hint - metrics.horizontalAdvance(full_label),
            0,
        )
        text_width = max(available_width - decoration_width, 1)
        rendered = metrics.elidedText(
            full_label,
            Qt.TextElideMode.ElideRight,
            text_width,
        )
        button.setText(rendered)
        if rendered != full_label and not button.toolTip():
            button.setToolTip(full_label)

    @staticmethod
    def _fit_wrapped_label_height(label: QLabel) -> None:
        """Reserve the Qt-measured height of a wrapped label at its live width."""
        if label.isHidden() or not label.text():
            label.setMinimumHeight(0)
            return
        label.ensurePolished()
        width = max(label.contentsRect().width(), 1)
        needed = (
            label.fontMetrics()
            .boundingRect(
                QRect(0, 0, width, 10_000),
                int(
                    Qt.AlignmentFlag.AlignLeft
                    | Qt.AlignmentFlag.AlignTop
                    | Qt.TextFlag.TextWordWrap
                ),
                label.text(),
            )
            .height()
        )
        label.setMinimumHeight(max(needed, label.fontMetrics().height()))

    def set_product_status(
        self,
        stage: str,
        model_status: str,
        tooltip: str | None = None,
        blocked_reason: str | None = None,
    ) -> None:
        """Update workflow guidance and low-priority diagnostics."""
        stage = workflow_stage_text_label(stage)
        status_tooltip = f"Workflow: {stage}\nSetup: {model_status}"
        if blocked_reason:
            status_tooltip = f"{status_tooltip}\n\nAction required: {blocked_reason}"
        if tooltip:
            status_tooltip = f"{status_tooltip}\n\n{tooltip}"
        self.empty_state_widget.setToolTip(status_tooltip)

    def show_notice(self, text: str, timeout_ms: int = 6000) -> None:
        """Show a low-priority inline notice outside the transcript."""
        self._set_notice(text, timeout_ms=timeout_ms, owner="general")

    def show_runtime_notice(self, text: str) -> None:
        """Update the inline runtime blocker without duplicating the transcript."""
        if self._runtime_phase not in {
            AssistantRuntimePhase.IDLE,
            AssistantRuntimePhase.FAILED,
        }:
            return
        normalized = self._plain_runtime_message(text)
        if normalized:
            unavailable_prefix = "Assistant unavailable:"
            if (
                self._runtime_phase is AssistantRuntimePhase.FAILED
                and normalized.lower().startswith(unavailable_prefix.lower())
            ):
                normalized = normalized[len(unavailable_prefix) :].strip()
            self.runtime_state_detail.setText(normalized)
            self.runtime_state_widget.setVisible(True)
            self._notice_owner = "runtime"
        else:
            self.clear_runtime_notice()

    @staticmethod
    def _plain_runtime_message(text: str) -> str:
        """Normalize presentation-service emphasis into plain QLabel text."""
        return " ".join(str(text or "").replace("**", "").split())

    def clear_runtime_notice(self) -> None:
        """Clear only a runtime-owned notice, preserving newer UI feedback."""
        if self._notice_owner == "runtime":
            self._notice_owner = None
            self.notice_label.setText("")
            self.notice_label.setVisible(False)

    def _expire_notice(self) -> None:
        self._set_notice("", timeout_ms=0, owner=None)

    def _set_notice(
        self,
        text: str,
        *,
        timeout_ms: int,
        owner: str | None,
    ) -> None:
        if not hasattr(self, "notice_label"):
            return
        self.notice_label.setText(text)
        self.notice_label.setVisible(bool(text.strip()))
        self._notice_owner = owner if text.strip() else None
        self._notice_timer.stop()
        if text.strip() and timeout_ms > 0:
            self._notice_timer.start(timeout_ms)

    def _fit_chat_surfaces_to_viewport(self, container_width: int) -> None:
        """Fit non-transcript surfaces without scanning every message bubble."""
        transcript_surface_width = max(
            min(
                container_width
                - self.transcript_view.content_layout.contentsMargins().left()
                - self.transcript_view.content_layout.contentsMargins().right(),
                CHAT_SURFACE_MAX_WIDTH,
            ),
            1,
        )
        surface_widths = (
            (self.runtime_state_widget, STATE_SURFACE_MAX_WIDTH),
            (self.empty_state_widget, EMPTY_STATE_MAX_WIDTH),
            (self.confirmation_card_widget, CHAT_SURFACE_MAX_WIDTH),
            (self.turn_activity_widget, STATE_SURFACE_MAX_WIDTH),
        )
        for surface, maximum_width in surface_widths:
            target_width = min(transcript_surface_width, maximum_width)
            if surface.width() != target_width:
                surface.setFixedWidth(target_width)
                surface_layout = surface.layout()
                if surface_layout is not None:
                    surface_layout.invalidate()
                    surface_layout.activate()

        if not self.empty_state_widget.isHidden():
            empty_margins = self.empty_state_layout.contentsMargins()
            suggestion_width = max(
                self.empty_state_widget.width()
                - empty_margins.left()
                - empty_margins.right(),
                1,
            )
            for suggestion in self.suggestion_prompt_buttons:
                suggestion.fit_to_width(suggestion_width)
            for label in (
                self.empty_state_title,
                self.empty_state_intro,
            ):
                self._fit_wrapped_label_height(label)
                label.setFixedHeight(label.minimumHeight())
            visible_suggestions = [
                suggestion
                for suggestion in self.suggestion_prompt_buttons
                if not suggestion.isHidden()
            ]
            prompt_margins = self.suggestion_prompt_layout.contentsMargins()
            prompt_height = (
                prompt_margins.top()
                + prompt_margins.bottom()
                + sum(suggestion.height() for suggestion in visible_suggestions)
                + self.suggestion_prompt_layout.spacing()
                * max(len(visible_suggestions) - 1, 0)
            )
            self.suggestion_prompt_widget.setFixedHeight(prompt_height)
            self.suggestion_prompt_widget.updateGeometry()
            self.empty_state_layout.invalidate()
            self.empty_state_layout.activate()
            self.empty_state_widget.setFixedHeight(
                max(
                    self.empty_state_layout.minimumSize().height(),
                    self.empty_state_layout.sizeHint().height(),
                )
                + 8
            )
            self.empty_state_widget.updateGeometry()

        if not self.runtime_state_widget.isHidden():
            for button in (self.retry_runtime_btn, self.setup_btn):
                full_label = button.property("assistantFullLabel")
                if isinstance(full_label, str) and full_label:
                    button.setText(full_label)
                    button.ensurePolished()
            runtime_state_layout = self.runtime_state_widget.layout()
            runtime_action_width = self.runtime_state_widget.width()
            if runtime_state_layout is not None:
                runtime_margins = runtime_state_layout.contentsMargins()
                runtime_action_width -= runtime_margins.left() + runtime_margins.right()
            runtime_action_width = max(runtime_action_width, 1)
            visible_runtime_actions = [
                button
                for button in (self.retry_runtime_btn, self.setup_btn)
                if not button.isHidden()
            ]
            required_runtime_action_width = sum(
                button.sizeHint().width() for button in visible_runtime_actions
            ) + self.runtime_action_layout.spacing() * max(
                len(visible_runtime_actions) - 1,
                0,
            )
            self.runtime_action_layout.setDirection(
                QBoxLayout.Direction.TopToBottom
                if (
                    container_width < 360
                    or required_runtime_action_width > runtime_action_width
                )
                else QBoxLayout.Direction.LeftToRight
            )
            for label in (
                self.runtime_state_title,
                self.runtime_state_detail,
            ):
                self._fit_wrapped_label_height(label)
            self._fit_runtime_state_to_contents()

        self.input_layout.setDirection(QBoxLayout.Direction.LeftToRight)
        self.input_layout.setAlignment(
            self.composer_actions,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
        )
        if not self.turn_activity_widget.isHidden():
            for label in (
                self.turn_activity_title,
                self.turn_activity_step,
                self.turn_activity_cancelability,
            ):
                self._fit_wrapped_label_height(label)
            turn_layout = self.turn_activity_widget.layout()
            if turn_layout is not None:
                turn_layout.invalidate()
                turn_layout.activate()
                self.turn_activity_widget.setMinimumHeight(
                    max(
                        turn_layout.minimumSize().height(),
                        turn_layout.sizeHint().height(),
                    )
                )
                self.turn_activity_widget.updateGeometry()
