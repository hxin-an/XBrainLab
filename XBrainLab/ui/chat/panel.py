"""Chat Panel - Main chat interface component.

Provides the ``ChatPanel`` widget implementing a Copilot-style chat interface
using ``MessageBubble`` widgets. Handles user input, workflow mode selection,
streaming responses, and debug-mode interception.
"""

from contextlib import suppress
from uuid import uuid4

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.controller.chat_controller import (
    ChatActionState,
    ChatController,
    ChatMessagePresentationKind,
    ChatMessageRecord,
    ChatMessageRole,
)
from XBrainLab.debug.tool_debug_mode import ToolDebugMode
from XBrainLab.llm.agent.confirmation import (
    AgentConfirmationRequest,
    AgentConfirmationResolution,
    AgentConfirmationResolutionStatus,
)
from XBrainLab.llm.agent.runtime_state import AssistantRuntimePhase
from XBrainLab.ui.product_language import (
    ASSISTANT_MODE_DESCRIPTIONS,
    ASSISTANT_MODE_LABELS,
    command_labels,
    workflow_stage_text_label,
)

from ..styles.theme import Theme
from .action_card import AssistantConfirmationCard
from .composer import AssistantComposer
from .message_bubble import MessageBubble
from .presentation import (
    ChatResponseActionSelectionView,
    ChatResponseActionsView,
    ChatResponseActionView,
    ChatTurnCancelability,
    ChatTurnPresentation,
    ChatTurnPresentationPhase,
)
from .status_presenter import build_assistant_empty_state
from .styles import (
    ASSISTANT_PANEL_STYLE,
    CONTROL_PANEL_STYLE,
    EMPTY_STATE_STYLE,
    EMPTY_STATE_TEXT_STYLE,
    EMPTY_STATE_TITLE_STYLE,
    INPUT_FIELD_STYLE,
    NOTICE_LABEL_STYLE,
    RESPONSE_ACTION_STYLE,
    RESPONSE_ACTION_TITLE_STYLE,
    RUNTIME_PRIMARY_ACTION_STYLE,
    RUNTIME_PROGRESS_STYLE,
    RUNTIME_SECONDARY_ACTION_STYLE,
    RUNTIME_STATE_DETAIL_STYLE,
    RUNTIME_STATE_STYLE,
    RUNTIME_STATE_TITLE_STYLE,
    SCROLL_AREA_STYLE,
    SEND_BUTTON_LOCKED_STYLE,
    SEND_BUTTON_PROCESSING_STYLE,
    SEND_BUTTON_STYLE,
    SUGGESTION_PROMPT_STYLE,
    TURN_ACTIVITY_CANCELABILITY_STYLE,
    TURN_ACTIVITY_PROGRESS_STYLE,
    TURN_ACTIVITY_STEP_STYLE,
    TURN_ACTIVITY_STYLE,
    TURN_ACTIVITY_TITLE_STYLE,
)

PRODUCT_STATUS_HIDDEN_COMMANDS = frozenset(
    {
        "load_data",
        "attach_labels",
        "import_labels",
    }
)
CHAT_SURFACE_MAX_WIDTH = 720
CHAT_CONTROL_MAX_WIDTH = 900

EXECUTION_MODE_SELECTOR_STYLE = f"""
    QWidget#AssistantModeSelector {{
        background: transparent;
        border: none;
    }}
    QPushButton {{
        min-width: 72px;
        min-height: 28px;
        padding: 3px 10px;
        color: {Theme.TEXT_SECONDARY};
        background: {Theme.BACKGROUND_DARK};
        border: 1px solid {Theme.BORDER};
        font-size: 12px;
        font-weight: 600;
    }}
    QPushButton#AssistantAskMode {{
        border-top-left-radius: 5px;
        border-bottom-left-radius: 5px;
        border-top-right-radius: 0px;
        border-bottom-right-radius: 0px;
    }}
    QPushButton#AssistantWorkflowMode {{
        border-left: none;
        border-top-left-radius: 0px;
        border-bottom-left-radius: 0px;
        border-top-right-radius: 5px;
        border-bottom-right-radius: 5px;
    }}
    QPushButton:checked {{
        color: {Theme.TEXT_PRIMARY};
        background: {Theme.BLUE_PRESSED};
        border-color: {Theme.BLUE_FOCUS_BORDER};
    }}
    QPushButton:hover:!checked {{
        color: {Theme.TEXT_PRIMARY};
        background: {Theme.BACKGROUND_MID};
    }}
    QPushButton:disabled {{
        color: {Theme.BTN_DISABLED_TEXT};
        background: {Theme.BTN_DISABLED_BG};
        border-color: {Theme.BTN_DISABLED_BORDER};
    }}
    QPushButton:checked:disabled {{
        color: #c9d8e6;
        background: #29445a;
        border-color: #456b88;
    }}
    QPushButton:focus {{
        color: {Theme.TEXT_PRIMARY};
        border: 1px solid {Theme.BLUE_FOCUS_BORDER};
    }}
    QPushButton#AssistantWorkflowMode:focus {{
        border-left: 1px solid {Theme.BLUE_FOCUS_BORDER};
    }}
"""

WORKFLOW_RUN_STATUS_STYLE = f"""
    QLabel#AssistantWorkflowRunStatus {{
        color: {Theme.TEXT_SECONDARY};
        background: transparent;
        border: none;
        padding: 0px;
        font-size: 12px;
    }}
"""

EXECUTION_MODE_DESCRIPTION_STYLE = f"""
    QLabel#AssistantModeDescription {{
        color: {Theme.TEXT_SECONDARY};
        background: transparent;
        border: none;
        padding: 0px;
        font-size: 11px;
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
        scroll_area: Scrollable area containing chat messages.
        input_field: Text input for user messages.
        send_btn: Button to send messages or stop generation.
    """

    # UI-driven Signals
    send_message = pyqtSignal(str)
    stop_generation = pyqtSignal()
    execution_mode_changed = pyqtSignal(str)  # 'single' or 'multi'
    debug_tool_requested = pyqtSignal(str, dict, bool, str)
    open_settings_requested = pyqtSignal()
    retry_local_assistant_requested = pyqtSignal()
    response_action_requested = pyqtSignal(object)
    active_response_presentation_changed = pyqtSignal(object)
    confirmation_decision_requested = pyqtSignal(AgentConfirmationResolution)
    header_status_changed = pyqtSignal(str)

    def __init__(self):
        """Initialize the ChatPanel with UI components and optional debug mode."""
        super().__init__()
        self.is_processing = False
        self._runtime_phase = AssistantRuntimePhase.IDLE
        self.current_execution_mode = "single"
        self._workflow_status_text = ""
        self._pending_scroll_to_bottom = False
        self._applying_tail_scroll = False
        self._viewport_reflow_pending = False
        self._notice_owner: str | None = None
        self._runtime_recovery = False
        self._response_presentation: ChatResponseActionsView | None = None
        self._follow_transcript_updates = True
        self._header_status_text = "Local · Setup"
        self._turn_presentation = ChatTurnPresentation.idle()
        self._chat_controller: ChatController | None = None
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

        # --- Chat Display (Scroll Area) ---
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.scroll_area.setStyleSheet(SCROLL_AREA_STYLE)

        # Container Widget inside ScrollArea
        self.chat_content_widget = QWidget()
        self.chat_content_widget.setStyleSheet("background-color: #1e1e1e;")
        self.chat_layout = QVBoxLayout(self.chat_content_widget)
        self.chat_layout.setContentsMargins(12, 12, 12, 12)
        self.chat_layout.setSpacing(12)
        self.content_top_spacer = QSpacerItem(
            0,
            0,
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Expanding,
        )
        self.content_bottom_spacer = QSpacerItem(
            0,
            0,
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Expanding,
        )
        self.chat_layout.addItem(self.content_top_spacer)
        self.runtime_state_widget = self._build_runtime_state()
        self.empty_state_widget = self._build_empty_state()
        self.turn_activity_widget = self._build_turn_activity()
        self.response_actions_widget = self._build_response_actions()
        self.confirmation_card_widget = AssistantConfirmationCard()
        self.confirmation_card_widget.decision_requested.connect(
            self._on_confirmation_decision
        )
        for surface in (
            self.runtime_state_widget,
            self.empty_state_widget,
            self.response_actions_widget,
            self.confirmation_card_widget,
            self.turn_activity_widget,
        ):
            surface.setMaximumWidth(CHAT_SURFACE_MAX_WIDTH)
            surface.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Maximum,
            )
        self.chat_layout.addWidget(self.runtime_state_widget)
        self.chat_layout.addWidget(self.empty_state_widget)
        self.chat_layout.addWidget(self.response_actions_widget)
        self.chat_layout.addWidget(self.confirmation_card_widget)
        self.chat_layout.addWidget(self.turn_activity_widget)
        for surface in (
            self.runtime_state_widget,
            self.empty_state_widget,
            self.response_actions_widget,
            self.confirmation_card_widget,
            self.turn_activity_widget,
        ):
            self.chat_layout.setAlignment(
                surface,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            )
        self.chat_layout.addItem(self.content_bottom_spacer)

        self.scroll_area.setWidget(self.chat_content_widget)
        scroll_bar = self.scroll_area.verticalScrollBar()
        if scroll_bar:
            scroll_bar.rangeChanged.connect(self._on_scroll_range_changed)
            scroll_bar.valueChanged.connect(self._on_scroll_value_changed)
        layout.addWidget(self.scroll_area, 1)

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
        control_layout.setContentsMargins(10, 8, 10, 8)
        control_layout.setSpacing(7)
        self.mode_section_label = QLabel("Agent mode")
        self.mode_section_label.setObjectName("AssistantModeSectionLabel")
        self.mode_section_label.setStyleSheet(
            f"color: {Theme.TEXT_SECONDARY}; background: transparent; "
            "border: none; font-size: 11px; font-weight: 700;"
        )
        self.mode_section_label.setMaximumWidth(CHAT_CONTROL_MAX_WIDTH)
        self.mode_section_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        control_layout.addWidget(self.mode_section_label)

        mode_row = QWidget()
        self.mode_selector_widget = mode_row
        mode_row.setObjectName("AssistantModeSelector")
        mode_row.setStyleSheet(EXECUTION_MODE_SELECTOR_STYLE)
        mode_row.setMaximumWidth(CHAT_CONTROL_MAX_WIDTH)
        mode_row.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        mode_layout = QHBoxLayout(mode_row)
        mode_layout.setContentsMargins(4, 0, 4, 0)
        mode_layout.setSpacing(0)

        self.execution_mode_group = QButtonGroup(self)
        self.execution_mode_group.setExclusive(True)

        self.ask_mode_btn = QPushButton(ASSISTANT_MODE_LABELS["single"])
        self.ask_mode_btn.setObjectName("AssistantAskMode")
        self.ask_mode_btn.setCheckable(True)
        self.ask_mode_btn.setChecked(True)
        self.ask_mode_btn.setMinimumHeight(30)
        self.ask_mode_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.ask_mode_btn.setAccessibleName(ASSISTANT_MODE_LABELS["single"])
        self.ask_mode_btn.setToolTip(ASSISTANT_MODE_DESCRIPTIONS["single"])
        self.ask_mode_btn.setAccessibleDescription(
            ASSISTANT_MODE_DESCRIPTIONS["single"]
        )
        self.ask_mode_btn.clicked.connect(
            lambda _checked=False: self._set_execution_mode("single")
        )
        self.execution_mode_group.addButton(self.ask_mode_btn)
        mode_layout.addWidget(self.ask_mode_btn)

        self.workflow_mode_btn = QPushButton(ASSISTANT_MODE_LABELS["multi"])
        self.workflow_mode_btn.setObjectName("AssistantWorkflowMode")
        self.workflow_mode_btn.setCheckable(True)
        self.workflow_mode_btn.setMinimumHeight(30)
        self.workflow_mode_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.workflow_mode_btn.setAccessibleName(ASSISTANT_MODE_LABELS["multi"])
        self.workflow_mode_btn.setToolTip(ASSISTANT_MODE_DESCRIPTIONS["multi"])
        self.workflow_mode_btn.setAccessibleDescription(
            ASSISTANT_MODE_DESCRIPTIONS["multi"]
        )
        self.workflow_mode_btn.clicked.connect(
            lambda _checked=False: self._set_execution_mode("multi")
        )
        self.execution_mode_group.addButton(self.workflow_mode_btn)
        mode_layout.addWidget(self.workflow_mode_btn)
        mode_layout.addStretch(1)

        self.mode_description_label = QLabel("")
        self.mode_description_label.setObjectName("AssistantModeDescription")
        self.mode_description_label.setStyleSheet(EXECUTION_MODE_DESCRIPTION_STYLE)
        self.mode_description_label.setWordWrap(True)
        self.mode_description_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.mode_description_label.setContentsMargins(4, 0, 4, 0)
        self.mode_description_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        self.mode_description_label.setAccessibleName("Execution mode behavior")
        self.mode_description_label.setVisible(False)
        control_layout.addWidget(self.mode_description_label)
        self._update_mode_description()

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
        input_widget.setStyleSheet("background: transparent; border: none;")
        input_widget.setMaximumWidth(CHAT_CONTROL_MAX_WIDTH)
        input_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        input_layout = QBoxLayout(
            QBoxLayout.Direction.LeftToRight,
            input_widget,
        )
        self.input_layout = input_layout
        input_layout.setContentsMargins(4, 4, 4, 4)
        input_layout.setSpacing(10)

        self.input_field = AssistantComposer()
        self.input_field.setPlaceholderText("Ask about the current EEG workflow...")
        self.input_field.setStyleSheet(INPUT_FIELD_STYLE)
        self.input_field.submit_requested.connect(self._on_send)
        self.input_field.textChanged.connect(self._apply_composer_activity_state)
        input_layout.addWidget(self.input_field, 1)

        self.send_btn = QToolButton()
        self.send_btn.setText("Send")
        self.send_btn.setFixedSize(88, 36)
        self.send_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.clicked.connect(self._on_send)
        self.send_btn.setStyleSheet(SEND_BUTTON_STYLE)
        input_layout.addWidget(self.send_btn)
        input_layout.setAlignment(
            self.send_btn,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

        control_layout.addWidget(mode_row)
        control_layout.addWidget(input_widget)
        control_layout.setAlignment(input_widget, Qt.AlignmentFlag.AlignHCenter)
        control_layout.setAlignment(mode_row, Qt.AlignmentFlag.AlignHCenter)

        self.notice_label = QLabel("")
        self.notice_label.setObjectName("AssistantNotice")
        self.notice_label.setStyleSheet(NOTICE_LABEL_STYLE)
        self.notice_label.setWordWrap(True)
        self.notice_label.setVisible(False)
        control_layout.addWidget(self.notice_label)
        layout.addWidget(control_panel, 0)

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
        self.retry_runtime_btn.setObjectName("AssistantRetryRuntimeButton")
        self.retry_runtime_btn.setMinimumHeight(34)
        self.retry_runtime_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.retry_runtime_btn.setAccessibleName("Retry local assistant")
        self.retry_runtime_btn.setToolTip(
            "Try to start the selected local model again."
        )
        self.retry_runtime_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry_runtime_btn.setStyleSheet(RUNTIME_PRIMARY_ACTION_STYLE)
        self.retry_runtime_btn.clicked.connect(
            lambda _checked=False: self._request_runtime_retry()
        )
        self.retry_runtime_btn.setVisible(False)
        self.retry_runtime_btn.setEnabled(False)
        action_layout.addWidget(self.retry_runtime_btn, 1)

        self.setup_btn = QPushButton("Open Assistant Settings")
        self.setup_btn.setObjectName("AssistantSetupButton")
        self.setup_btn.setMinimumHeight(34)
        self.setup_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setup_btn.setAccessibleName("Open Assistant Settings")
        self.setup_btn.setStyleSheet(RUNTIME_PRIMARY_ACTION_STYLE)
        self.setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setup_btn.clicked.connect(self.open_settings_requested)
        self.setup_btn.setVisible(False)
        action_layout.addWidget(self.setup_btn, 1)
        self.runtime_actions.setVisible(False)
        state_layout.addWidget(self.runtime_actions)
        state.setVisible(False)
        return state

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
        """Build the initial guidance panel shown before conversation starts."""
        empty = QFrame()
        empty.setObjectName("AssistantEmptyState")
        empty.setStyleSheet(EMPTY_STATE_STYLE)
        empty_layout = QVBoxLayout(empty)
        empty_layout.setContentsMargins(14, 14, 14, 14)
        empty_layout.setSpacing(8)

        self.empty_state_title = QLabel("How can I help with your EEG workflow?")
        self.empty_state_title.setObjectName("AssistantEmptyTitle")
        self.empty_state_title.setStyleSheet(EMPTY_STATE_TITLE_STYLE)
        self.empty_state_title.setWordWrap(True)
        self.empty_state_title.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        empty_layout.addWidget(self.empty_state_title)

        self.empty_state_intro = QLabel(
            "Ask the local assistant to explain the current state, review settings, "
            "or guide the next safe step."
        )
        self.empty_state_intro.setWordWrap(True)
        self.empty_state_intro.setStyleSheet(EMPTY_STATE_TEXT_STYLE)
        empty_layout.addWidget(self.empty_state_intro)

        self.empty_state_backend_label = QLabel("No EEG files are open yet.")
        self.empty_state_backend_label.setStyleSheet(EMPTY_STATE_TEXT_STYLE)
        self.empty_state_backend_label.setWordWrap(True)
        empty_layout.addWidget(self.empty_state_backend_label)

        self.empty_state_next_label = QLabel("")
        self.empty_state_next_label.setStyleSheet(EMPTY_STATE_TEXT_STYLE)
        self.empty_state_next_label.setWordWrap(True)
        self.empty_state_next_label.setVisible(False)
        empty_layout.addWidget(self.empty_state_next_label)

        self.suggestion_prompt_widget = QWidget(empty)
        self.suggestion_prompt_widget.setObjectName("AssistantSuggestionPrompts")
        self.suggestion_prompt_widget.setStyleSheet(
            "background: transparent; border: none;"
        )
        self.suggestion_prompt_layout = QGridLayout(self.suggestion_prompt_widget)
        self.suggestion_prompt_layout.setContentsMargins(0, 4, 0, 0)
        self.suggestion_prompt_layout.setSpacing(7)

        prompts = (
            (
                "Check the current workflow status",
                "Check the current workflow status",
            ),
            (
                "Explain the current settings",
                "Explain the current settings",
            ),
            (
                "Suggest the next step",
                "Suggest the next step",
            ),
            (
                "Review the training configuration",
                "Review the training configuration",
            ),
        )
        self.suggestion_prompt_buttons: list[QToolButton] = []
        for label, prompt in prompts:
            button = QToolButton(self.suggestion_prompt_widget)
            button.setObjectName("AssistantSuggestionPrompt")
            button.setText(label)
            button.setProperty("assistantPrompt", prompt)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            button.setMinimumHeight(32)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(SUGGESTION_PROMPT_STYLE)
            button.clicked.connect(
                lambda _checked=False, selected=button: (
                    self._fill_suggestion_prompt(selected)
                )
            )
            self.suggestion_prompt_buttons.append(button)
        self._layout_suggestion_prompts(1)
        empty_layout.addWidget(self.suggestion_prompt_widget)

        # Compatibility alias: the stage-aware next-step prompt now fills the
        # composer instead of starting an assistant turn without review.
        self.empty_state_action_button = self.suggestion_prompt_buttons[2]
        self._empty_state_action_prompt = "Suggest the next step"

        return empty

    def _fill_suggestion_prompt(self, button: QToolButton) -> None:
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

    def _layout_suggestion_prompts(self, columns: int) -> None:
        """Lay out complete prompt labels without eliding their meaning."""
        columns = 1 if columns <= 1 else 2
        for button in self.suggestion_prompt_buttons:
            self.suggestion_prompt_layout.removeWidget(button)
        for index, button in enumerate(self.suggestion_prompt_buttons):
            self.suggestion_prompt_layout.addWidget(
                button,
                index // columns,
                index % columns,
            )
        for column in range(2):
            self.suggestion_prompt_layout.setColumnStretch(
                column,
                1 if column < columns else 0,
            )

    def _build_response_actions(self) -> QWidget:
        """Build the lightweight action list attached to the latest response."""
        widget = QWidget()
        widget.setObjectName("AssistantResponseActions")
        widget.setStyleSheet("background: transparent; border: none;")
        widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.response_action_title = QLabel("Suggested next step", widget)
        self.response_action_title.setObjectName("AssistantResponseActionTitle")
        self.response_action_title.setStyleSheet(RESPONSE_ACTION_TITLE_STYLE)
        layout.addWidget(self.response_action_title)
        widget.setVisible(False)
        return widget

    def show_response_actions(
        self,
        record: ChatMessageRecord,
    ) -> None:
        """Render active actions from one persisted typed response record."""
        if not isinstance(record, ChatMessageRecord):
            raise TypeError("Assistant response actions require a typed chat record.")
        presentation = ChatResponseActionsView.from_history_record(record)
        self.clear_response_actions()
        if presentation is None:
            return
        self._response_presentation = presentation
        self.active_response_presentation_changed.emit(presentation.presentation_id)
        layout = self.response_actions_widget.layout()
        if layout is None:
            raise RuntimeError("Assistant response action layout is unavailable.")
        for action in presentation.actions:
            button = QToolButton(self.response_actions_widget)
            button.setObjectName("AssistantResponseAction")
            button.setText(action.label)
            button.setProperty("assistantFullLabel", action.label)
            button.setToolTip(action.label)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            button.setMinimumHeight(34)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setAccessibleName(action.label)
            button.setStyleSheet(RESPONSE_ACTION_STYLE)
            button.clicked.connect(
                lambda _checked=False, selected=action: self._select_response_action(
                    selected
                )
            )
            layout.addWidget(button)
        self.response_actions_widget.setVisible(True)
        self.response_actions_widget.updateGeometry()
        response_layout = self.response_actions_widget.layout()
        if response_layout is not None:
            response_layout.activate()
        self._place_transient_surfaces_after_messages()
        self._reflow_chat_content()
        QTimer.singleShot(0, self._reflow_chat_content)
        if self._follow_transcript_updates:
            self._scroll_to_bottom()

    def _select_response_action(self, action: ChatResponseActionView) -> None:
        presentation = self._response_presentation
        if presentation is None or action not in presentation.actions:
            return
        selection = ChatResponseActionSelectionView(
            presentation_id=presentation.presentation_id,
            action=action,
        )
        self.response_action_requested.emit(selection)
        if self._chat_controller is not None:
            self._chat_controller.consume_response_actions(presentation.presentation_id)
        self.clear_response_actions()

    def clear_response_actions(self) -> None:
        """Remove actions as soon as their response is no longer current."""
        had_presentation = self._response_presentation is not None
        self._response_presentation = None
        layout = getattr(self, "response_actions_widget", None)
        layout = layout.layout() if layout is not None else None
        if layout is not None:
            while layout.count() > 1:
                item = layout.takeAt(1)
                widget = item.widget() if item is not None else None
                if widget is not None:
                    widget.deleteLater()
        if hasattr(self, "response_actions_widget"):
            self.response_actions_widget.setVisible(False)
            self.response_actions_widget.updateGeometry()
        if had_presentation:
            self.active_response_presentation_changed.emit(None)

    def show_confirmation_request(
        self,
        request: AgentConfirmationRequest,
        *,
        current_values: dict[str, str] | None = None,
        current_context_changed: bool = False,
    ) -> None:
        """Show one transient typed confirmation inside the message area."""
        follow_tail = self._follow_transcript_updates or self._is_near_bottom()
        self.clear_response_actions()
        self.empty_state_widget.setVisible(False)
        self.confirmation_card_widget.present(
            request,
            current_values=current_values,
            current_context_changed=current_context_changed,
        )
        if self._turn_presentation.phase is ChatTurnPresentationPhase.WAITING:
            self.turn_activity_widget.setVisible(False)
        self._place_transient_surfaces_after_messages()
        self._sync_content_alignment()
        self._reflow_chat_content()
        self._follow_transcript_updates = follow_tail
        if follow_tail:
            self._scroll_to_bottom()

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
            and not self._has_transcript_messages()
            and not self.turn_activity_widget.isVisible()
        ):
            self.empty_state_widget.setVisible(True)
        self._sync_content_alignment()

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

        Wires the controller's signals (``message_added``,
        ``processing_state_changed``, ``conversation_cleared``) to the
        corresponding UI rendering methods.

        Args:
            controller: The ``ChatController`` instance to bind.

        """
        if not isinstance(controller, ChatController):
            raise TypeError("ChatPanel requires a ChatController.")
        previous = self._chat_controller
        if previous is not None and previous is not controller:
            with suppress(TypeError):
                previous.message_record_added.disconnect(self._render_message_record)
            with suppress(TypeError):
                previous.message_record_updated.disconnect(self._update_rendered_record)
            with suppress(TypeError):
                previous.processing_state_changed.disconnect(self._update_processing_ui)
            with suppress(TypeError):
                previous.conversation_cleared.disconnect(self._clear_ui)
        if self._chat_controller is not controller:
            controller.message_record_added.connect(self._render_message_record)
            controller.message_record_updated.connect(self._update_rendered_record)
            controller.processing_state_changed.connect(self._update_processing_ui)
            controller.conversation_cleared.connect(self._clear_ui)
        self._chat_controller = controller
        self._restore_controller_state(controller)

    def _restore_controller_state(self, controller: ChatController) -> None:
        """Replay view state when the panel is recreated or reconnected."""
        self._clear_ui()
        records = controller.get_typed_history()
        for record in records:
            self._render_message_record(record, show_actions=False)
        if records and records[-1].has_active_actions:
            self.show_response_actions(records[-1])
        self._update_processing_ui(controller.is_processing)
        self._reflow_chat_content()
        self._scroll_to_bottom()

    def _set_execution_mode(self, mode_key: str):
        """Update the execution mode selector and emit mode change signal.

        Args:
            mode_key: The mode identifier (``'single'`` or ``'multi'``).
        """
        normalized_mode = "multi" if mode_key in {"multi", "workflow"} else "single"
        self.current_execution_mode = normalized_mode
        self.ask_mode_btn.setChecked(normalized_mode == "single")
        self.workflow_mode_btn.setChecked(normalized_mode == "multi")
        self._update_mode_description()
        self._sync_control_context_visibility()
        self.execution_mode_changed.emit(normalized_mode)

    def set_execution_mode(self, mode: str) -> None:
        """Synchronize the product selector without emitting another change."""
        normalized_mode = "multi" if mode in {"multi", "workflow"} else "single"
        self.current_execution_mode = normalized_mode
        self.ask_mode_btn.setChecked(normalized_mode == "single")
        self.workflow_mode_btn.setChecked(normalized_mode == "multi")
        self._update_mode_description()
        self._sync_control_context_visibility()

    def _update_mode_description(self) -> None:
        """Keep visible and accessible mode guidance on one product truth."""
        description = ASSISTANT_MODE_DESCRIPTIONS[self.current_execution_mode]
        self.mode_description_label.setText(description)
        self.mode_description_label.setToolTip(description)
        self.mode_description_label.setAccessibleDescription(description)

    def set_workflow_status(self, text: str) -> None:
        """Update a legacy status caller without using its text as state."""
        self._workflow_status_text = " ".join(str(text or "").split())
        self.workflow_run_status_label.setText(self._workflow_status_text)
        self.workflow_run_status_label.setToolTip(self._workflow_status_text)
        if self.is_processing and self._workflow_status_text:
            current = self._turn_presentation
            if current.is_busy:
                self.set_turn_activity(
                    ChatTurnPresentation(
                        phase=current.phase,
                        primary_status=current.primary_status,
                        step=self._workflow_status_text,
                        cancelability=current.cancelability,
                        cancelability_text=current.cancelability_text,
                    )
                )

    def _sync_control_context_visibility(self) -> None:
        """Keep mode choices discoverable while limiting contextual guidance."""
        runtime_ready = (
            self._runtime_phase is AssistantRuntimePhase.READY
            or self.debug_mode is not None
        )
        self.mode_selector_widget.setVisible(True)
        self.mode_description_label.setVisible(runtime_ready and not self.is_processing)
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
        self._place_transient_surfaces_after_messages()
        self._apply_composer_activity_state()
        self._sync_control_context_visibility()
        self._publish_header_status()
        self._sync_content_alignment()
        self._reflow_chat_content()
        if presentation.is_visible and self._is_near_bottom():
            self._scroll_to_bottom()

    def _apply_composer_activity_state(self) -> None:
        """Expose Stop only while the typed state says cancellation is accepted."""
        runtime_ready = (
            self._runtime_phase is AssistantRuntimePhase.READY
            or self.debug_mode is not None
        )
        cancelability = self._turn_presentation.cancelability
        if self.is_processing and cancelability is ChatTurnCancelability.CANCELLABLE:
            self.send_btn.setText("Stop")
            self.send_btn.setToolTip("Stop this request before an action starts.")
            self.send_btn.setStyleSheet(SEND_BUTTON_PROCESSING_STYLE)
            send_enabled = runtime_ready
        elif self.is_processing:
            stopping = cancelability is ChatTurnCancelability.STOPPING
            self.send_btn.setText("Stopping" if stopping else "Working")
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
            self.send_btn.setToolTip("Send request")
            self.send_btn.setStyleSheet(SEND_BUTTON_STYLE)
            send_enabled = runtime_ready and bool(self.input_field.text().strip())

        self.input_field.setEnabled(not self.is_processing and runtime_ready)
        self.send_btn.setEnabled(send_enabled)
        self.ask_mode_btn.setEnabled(not self.is_processing and runtime_ready)
        self.workflow_mode_btn.setEnabled(not self.is_processing and runtime_ready)
        for button in getattr(self, "suggestion_prompt_buttons", ()):
            prompt = button.property("assistantPrompt")
            button.setEnabled(
                isinstance(prompt, str)
                and bool(prompt.strip())
                and not self.is_processing
                and runtime_ready
            )

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
            if not self.debug_mode.is_complete:
                call = self.debug_mode.next_call()
                if call:
                    # Clear input just in case
                    self.input_field.clear()
                    # Emit debug request
                    self.debug_tool_requested.emit(
                        call.tool,
                        call.params,
                        call.confirmed,
                        call.authorization_text,
                    )
                else:
                    self.input_field.setText("Debug Script Completed.")
            else:
                self.input_field.setText("Debug Script Completed.")
            return

        if self._runtime_phase is not AssistantRuntimePhase.READY:
            return

        text = self.input_field.text().strip()
        if not text:
            return

        self.input_field.clear()
        self.send_message.emit(text)
        # The typed assistant activity publication owns the processing state.

    def _request_empty_state_action(self) -> None:
        """Send the current stage-aware suggestion as an assistant request."""
        prompt = self._empty_state_action_prompt.strip()
        if (
            not prompt
            or self.is_processing
            or self._runtime_phase is not AssistantRuntimePhase.READY
        ):
            return
        self.clear_response_actions()
        self.send_message.emit(prompt)

    def set_processing_state(self, is_processing: bool):
        """Update the processing state and refresh the UI accordingly.

        Args:
            is_processing: Whether the agent is currently generating.

        """
        self._update_processing_ui(is_processing)

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
        self._workflow_status_text = ""
        self.workflow_run_status_label.clear()
        self.workflow_run_status_label.setToolTip("")
        self.set_turn_activity(ChatTurnPresentation.idle())

    def set_runtime_state(self, phase: str, message: str = "") -> None:
        """Apply one worker-published runtime state to the visible composer."""
        previous_phase = self._runtime_phase
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
            self.input_field.setPlaceholderText("Run next diagnostic action")
            self.workflow_run_status_label.setText("")
            self.workflow_run_status_label.setVisible(False)
            self.runtime_progress.setVisible(False)
            self.retry_runtime_btn.setVisible(False)
            self.retry_runtime_btn.setEnabled(False)
            self.setup_btn.setVisible(False)
            self.runtime_actions.setVisible(False)
            self.runtime_state_widget.setVisible(False)
            self._update_processing_ui(self.is_processing)
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
            self.input_field.setPlaceholderText("Ask about the current EEG workflow...")
            if not (self.is_processing and self.current_execution_mode == "multi"):
                self.workflow_run_status_label.setVisible(False)
            self.runtime_progress.setVisible(False)
            self.retry_runtime_btn.setVisible(False)
            self.retry_runtime_btn.setEnabled(False)
            self.setup_btn.setVisible(False)
            self.runtime_actions.setVisible(False)
            self.runtime_state_widget.setVisible(False)
            if not self._has_transcript_messages():
                self.empty_state_widget.setVisible(True)
        else:
            is_failed = self._runtime_phase is AssistantRuntimePhase.FAILED
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
        self._sync_content_alignment()
        self._reflow_chat_content()

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
            status = (
                "Local · Working"
                if self._turn_presentation.is_busy
                else "Local · Ready"
            )
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
        self.runtime_actions.adjustSize()
        self.runtime_state_widget.adjustSize()
        self.runtime_actions.updateGeometry()
        self.runtime_state_widget.updateGeometry()

    def set_status_summary(self, text: str, tooltip: str | None = None) -> None:
        """Update stage-aware assistant guidance from a compact status string."""
        stage = "checking"
        model_status = "checking"
        if "|" in text:
            stage_part, model_part = text.split("|", 1)
            stage = stage_part.replace("Backend:", "").strip()
            model_status = model_part.strip()
        elif text.lower().startswith("backend:"):
            stage = text.replace("Backend:", "").strip()
        stage = workflow_stage_text_label(stage)

        self._update_status_widgets(
            stage=stage,
            model_status=model_status,
            available_commands=None,
            tooltip=tooltip,
        )

    def set_product_status(
        self,
        stage: str,
        model_status: str,
        available_commands: list[str],
        tooltip: str | None = None,
        blocked_reason: str | None = None,
    ) -> None:
        """Update workflow guidance and low-priority diagnostics."""
        stage = workflow_stage_text_label(stage)
        self._update_status_widgets(
            stage=stage,
            model_status=model_status,
            available_commands=available_commands,
            tooltip=tooltip,
            blocked_reason=blocked_reason,
        )

    def _update_status_widgets(
        self,
        stage: str,
        model_status: str,
        available_commands: list[str] | None,
        tooltip: str | None = None,
        blocked_reason: str | None = None,
    ) -> None:
        """Apply status text to guidance and empty-state labels."""
        status_tooltip = f"Workflow: {stage}\nSetup: {model_status}"
        if tooltip:
            status_tooltip = f"{status_tooltip}\n\n{tooltip}"
        self.empty_state_widget.setToolTip(status_tooltip)

        visible_command_names = (
            None
            if available_commands is None
            else [
                name
                for name in available_commands
                if str(name) not in PRODUCT_STATUS_HIDDEN_COMMANDS
            ]
        )
        display_commands = (
            None
            if visible_command_names is None
            else command_labels(visible_command_names)
        )
        presentation = build_assistant_empty_state(
            stage,
            display_commands,
            blocked_reason,
        )
        if hasattr(self, "empty_state_backend_label"):
            self.empty_state_backend_label.setText(presentation.stage_sentence)
        if hasattr(self, "empty_state_next_label"):
            self.empty_state_next_label.setText(presentation.next_text)
            self.empty_state_next_label.setVisible(
                bool(presentation.next_text) and not bool(display_commands)
            )
        if hasattr(self, "empty_state_action_button"):
            action_text = display_commands[0] if display_commands else ""
            self._empty_state_action_prompt = action_text or "Suggest the next step"
            self.empty_state_action_button.setProperty(
                "assistantPrompt",
                self._empty_state_action_prompt,
            )
            self.empty_state_action_button.setAccessibleName("Suggest the next step")
            self.empty_state_action_button.setVisible(True)
            self.empty_state_action_button.setEnabled(
                not self.is_processing
                and self._runtime_phase is AssistantRuntimePhase.READY
            )

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

    def resizeEvent(self, event):  # noqa: N802
        """Re-adjust all bubble widths on window resize.

        Args:
            event: The ``QResizeEvent``.

        """
        scroll_bar = self.scroll_area.verticalScrollBar()
        was_at_bottom = self._follow_transcript_updates or self._is_near_bottom()
        super().resizeEvent(event)
        self._reflow_chat_content()
        if was_at_bottom:
            self._scroll_to_bottom()
        elif scroll_bar is not None:
            self._pending_scroll_to_bottom = False

    def showEvent(self, event):  # noqa: N802
        """Reflow content that may have arrived while the dock was hidden."""
        super().showEvent(event)
        self._reflow_chat_content()
        QTimer.singleShot(0, self._reflow_chat_content)

    def _reflow_chat_content(self) -> None:
        """Fit transcript bubbles and response actions to the live viewport."""
        viewport = self.scroll_area.viewport()
        if viewport is None or viewport.width() <= 0:
            return
        container_width = viewport.width()
        transcript_surface_width = max(
            min(
                container_width
                - self.chat_layout.contentsMargins().left()
                - self.chat_layout.contentsMargins().right(),
                CHAT_SURFACE_MAX_WIDTH,
            ),
            1,
        )
        for surface in (
            self.runtime_state_widget,
            self.empty_state_widget,
            self.response_actions_widget,
            self.confirmation_card_widget,
            self.turn_activity_widget,
        ):
            surface.setFixedWidth(transcript_surface_width)

        control_width = max(
            min(self.width() - 20, CHAT_CONTROL_MAX_WIDTH),
            1,
        )
        for control in (
            self.input_widget,
            self.mode_selector_widget,
        ):
            control.setMaximumWidth(control_width)

        for index in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if isinstance(widget, MessageBubble):
                widget.adjust_width(container_width)
        self._fit_response_action_labels(transcript_surface_width)
        self.runtime_action_layout.setDirection(
            QBoxLayout.Direction.TopToBottom
            if container_width < 360
            else QBoxLayout.Direction.LeftToRight
        )
        self._layout_suggestion_prompts(2 if container_width >= 520 else 1)
        self.input_layout.setDirection(
            QBoxLayout.Direction.TopToBottom
            if control_width < 380
            else QBoxLayout.Direction.LeftToRight
        )
        self._fit_runtime_state_to_contents()
        self._sync_content_alignment()
        self.chat_content_widget.updateGeometry()

    def _place_transient_surfaces_after_messages(self) -> None:
        """Keep current transcript activity after the durable messages."""
        for surface in (
            self.response_actions_widget,
            self.confirmation_card_widget,
            self.turn_activity_widget,
        ):
            self.chat_layout.removeWidget(surface)
            self.chat_layout.insertWidget(
                self._bottom_spacer_index(),
                surface,
            )
            self.chat_layout.setAlignment(
                surface,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            )

    def _bottom_spacer_index(self) -> int:
        """Return the insertion point immediately before the bottom spacer."""
        for index in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(index)
            if item is not None and item.spacerItem() is self.content_bottom_spacer:
                return index
        return self.chat_layout.count()

    def _sync_content_alignment(self) -> None:
        """Center owned empty/runtime states and top-align real transcripts."""
        centered_surface_visible = (
            not self._has_transcript_messages()
            and (
                self.runtime_state_widget.isVisible()
                or self.empty_state_widget.isVisible()
            )
            and not self.confirmation_card_widget.isVisible()
            and not self.turn_activity_widget.isVisible()
        )
        vertical_policy = (
            QSizePolicy.Policy.Expanding
            if centered_surface_visible
            else QSizePolicy.Policy.Minimum
        )
        self.content_top_spacer.changeSize(
            0,
            0,
            QSizePolicy.Policy.Minimum,
            vertical_policy,
        )
        self.content_bottom_spacer.changeSize(
            0,
            0,
            QSizePolicy.Policy.Minimum,
            (
                QSizePolicy.Policy.Expanding
                if centered_surface_visible
                else QSizePolicy.Policy.Minimum
            ),
        )
        self.chat_layout.invalidate()

    def _is_near_bottom(self, tolerance: int = 12) -> bool:
        """Return whether transcript updates should continue following the tail."""
        scroll_bar = self.scroll_area.verticalScrollBar()
        return bool(
            scroll_bar is None
            or scroll_bar.maximum() <= 0
            or scroll_bar.value() >= scroll_bar.maximum() - tolerance
        )

    def _fit_response_action_labels(self, container_width: int) -> None:
        """Elide long action labels while retaining their full accessible text."""
        available_width = max(container_width - 48, 40)
        for button in self.response_actions_widget.findChildren(QToolButton):
            full_label = button.property("assistantFullLabel")
            if not isinstance(full_label, str) or not full_label:
                continue
            text_width = max(available_width - 24, 20)
            button.setText(
                button.fontMetrics().elidedText(
                    full_label,
                    Qt.TextElideMode.ElideRight,
                    text_width,
                )
            )

    def _render_message_record(
        self,
        record: ChatMessageRecord,
        *,
        show_actions: bool = True,
    ) -> None:
        """Create one bubble directly from the typed persistence record."""
        if not isinstance(record, ChatMessageRecord):
            raise TypeError("ChatPanel messages require typed chat records.")
        is_user = record.role is ChatMessageRole.USER
        follow_tail = is_user or self._is_near_bottom()
        self._follow_transcript_updates = follow_tail
        if is_user or not record.has_active_actions:
            self.clear_response_actions()
        bubble = MessageBubble(
            record.content,
            is_user,
            presentation_kind=record.presentation_kind,
        )
        bubble.setProperty("chatMessageId", record.message_id)

        # M0.4: Initial width adjustment
        viewport = self.scroll_area.viewport()
        if viewport:
            bubble.adjust_width(viewport.width())

        # Insert before stretch
        if hasattr(self, "empty_state_widget"):
            self.empty_state_widget.setVisible(False)
        self.chat_layout.insertWidget(self._bottom_spacer_index(), bubble)
        self._place_transient_surfaces_after_messages()
        if show_actions and record.has_active_actions:
            self.show_response_actions(record)
        self._reflow_chat_content()
        self._sync_content_alignment()
        QTimer.singleShot(0, self._reflow_chat_content)
        if follow_tail:
            self._scroll_to_bottom()
        else:
            self._pending_scroll_to_bottom = False

    def _update_rendered_record(self, record: ChatMessageRecord) -> None:
        """Apply a correlated typed history update to its existing bubble/actions."""
        if not isinstance(record, ChatMessageRecord):
            return
        for bubble in self.chat_content_widget.findChildren(MessageBubble):
            if bubble.property("chatMessageId") == record.message_id:
                bubble.set_presentation_kind(record.presentation_kind)
                break
        if (
            self._response_presentation is not None
            and self._response_presentation.presentation_id == record.presentation_id
        ):
            if record.action_state is ChatActionState.ACTIVE:
                self.show_response_actions(record)
            else:
                self.clear_response_actions()
        self._reflow_chat_content()

    def _render_message(self, text: str, is_user: bool) -> None:
        """Compatibility helper that uses safe default typed presentation."""
        record = ChatMessageRecord.from_history_value(
            {
                "role": "user" if is_user else "assistant",
                "content": text,
            }
        )
        if record is not None:
            self._render_message_record(record)

    def _clear_ui(self):
        """Remove all message bubbles from the chat layout."""
        runtime_state = getattr(self, "runtime_state_widget", None)
        empty_state = getattr(self, "empty_state_widget", None)
        response_actions = getattr(self, "response_actions_widget", None)
        confirmation_card = getattr(self, "confirmation_card_widget", None)
        turn_activity = getattr(self, "turn_activity_widget", None)
        preserved = {
            runtime_state,
            empty_state,
            response_actions,
            confirmation_card,
            turn_activity,
        }
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            if item:
                w = item.widget()
                if w and w not in preserved:
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()
        self.chat_layout.addItem(self.content_top_spacer)
        for surface in (
            runtime_state,
            empty_state,
            response_actions,
            confirmation_card,
            turn_activity,
        ):
            if surface is None:
                continue
            self.chat_layout.addWidget(surface)
            self.chat_layout.setAlignment(
                surface,
                Qt.AlignmentFlag.AlignHCenter,
            )
        self.clear_response_actions()
        self.clear_confirmation_request()
        self.chat_layout.addItem(self.content_bottom_spacer)
        if empty_state is not None:
            empty_state.setVisible(self._runtime_phase is AssistantRuntimePhase.READY)
        self._sync_content_alignment()

    def _has_transcript_messages(self) -> bool:
        """Return transcript truth even while the assistant dock is hidden."""
        return bool(self.chat_content_widget.findChildren(MessageBubble))

    def _scroll_to_bottom(self):
        """Scroll the chat area to the bottom."""
        self._follow_transcript_updates = True
        self._pending_scroll_to_bottom = True

        def apply_scroll() -> None:
            self._apply_pending_scroll_to_bottom()

        apply_scroll()
        QTimer.singleShot(0, apply_scroll)

    def _on_scroll_range_changed(self, _minimum: int, _maximum: int) -> None:
        """Reflow after scrollbar visibility changes, then follow the tail."""
        self._queue_viewport_reflow()
        if self._pending_scroll_to_bottom:
            self._apply_pending_scroll_to_bottom()

    def _queue_viewport_reflow(self) -> None:
        """Coalesce scrollbar-driven width changes into one settled reflow."""
        if self._viewport_reflow_pending:
            return
        self._viewport_reflow_pending = True

        def apply_reflow() -> None:
            self._viewport_reflow_pending = False
            self._reflow_chat_content()
            if self._follow_transcript_updates or self._pending_scroll_to_bottom:
                self._scroll_to_bottom()

        QTimer.singleShot(0, apply_reflow)

    def _on_scroll_value_changed(self, _value: int) -> None:
        """Track explicit reading position without fighting internal follow."""
        if self._applying_tail_scroll:
            return
        near_bottom = self._is_near_bottom()
        if not near_bottom:
            self._pending_scroll_to_bottom = False
        self._follow_transcript_updates = near_bottom

    def _apply_pending_scroll_to_bottom(self) -> None:
        """Apply a pending bottom scroll once the scroll range is available."""
        if not self._pending_scroll_to_bottom:
            return
        self.chat_content_widget.adjustSize()
        self.chat_content_widget.updateGeometry()
        scroll_bar = self.scroll_area.verticalScrollBar()
        if not scroll_bar:
            return
        self._applying_tail_scroll = True
        try:
            scroll_bar.setValue(scroll_bar.maximum())
            latest_bubble = self._latest_message_bubble()
            if latest_bubble is not None:
                self.scroll_area.ensureWidgetVisible(latest_bubble, 0, 8)
                scroll_bar.setValue(scroll_bar.maximum())
        finally:
            self._applying_tail_scroll = False
        if scroll_bar.maximum() > 0 and scroll_bar.value() >= scroll_bar.maximum() - 2:
            self._pending_scroll_to_bottom = False
            self._follow_transcript_updates = True

    def _latest_message_bubble(self) -> MessageBubble | None:
        for index in range(self.chat_layout.count() - 1, -1, -1):
            item = self.chat_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if isinstance(widget, MessageBubble) and widget.isVisible():
                return widget
        return None

    def _latest_layout_message_bubble(self) -> MessageBubble | None:
        """Return the latest transcript bubble even while the dock is hidden."""
        for index in range(self.chat_layout.count() - 1, -1, -1):
            item = self.chat_layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if isinstance(widget, MessageBubble):
                return widget
        return None

    def _message_bubble_visible(self, bubble: MessageBubble | None) -> bool:
        if bubble is None:
            return True
        viewport = self.scroll_area.viewport()
        if viewport is None:
            return True
        bottom_y = bubble.mapTo(viewport, bubble.rect().bottomLeft()).y()
        return bottom_y <= viewport.height() + 2

    def append_message(
        self,
        sender: str,
        text: str,
        *,
        presentation_kind: ChatMessagePresentationKind | None = None,
    ) -> None:
        """Append a message bubble.

        Args:
            sender: Message sender identifier (e.g., ``"user"``,
                ``"assistant"``).
            text: The message text content.

        """
        is_user = sender.lower() == "user"
        role = ChatMessageRole.USER if is_user else ChatMessageRole.ASSISTANT
        kind = presentation_kind or (
            ChatMessagePresentationKind.USER
            if is_user
            else ChatMessagePresentationKind.ASSISTANT
        )
        record = ChatMessageRecord(
            role=role,
            content=text,
            presentation_kind=kind,
            message_id=uuid4().hex,
        )
        self._render_message_record(record)
