"""Centralized stylesheet constants for the Chat Panel.

Defines the styles used by visible assistant transcript and composer components.
"""

from ..styles.theme import Theme

ASSISTANT_BACKGROUND = "#181c20"
ASSISTANT_SURFACE = "#1f252b"
ASSISTANT_SURFACE_HOVER = "#252d34"
ASSISTANT_BORDER = "#343f48"
ASSISTANT_BORDER_HOVER = "#4b5c69"
ASSISTANT_ACCENT = "#168be0"
ASSISTANT_ACCENT_HOVER = "#2a9bef"

ASSISTANT_PANEL_STYLE = """
    QWidget#AssistantPanel {
        background-color: #181c20;
    }
"""

EMPTY_STATE_STYLE = """
    QFrame#AssistantEmptyState {
        background-color: #181c20;
        border: none;
        border-radius: 0px;
    }
"""

EMPTY_STATE_TITLE_STYLE = """
    QLabel#AssistantEmptyTitle {
        color: #f3f7fb;
        background: transparent;
        border: none;
        font-size: 18px;
        font-weight: 700;
    }
"""

EMPTY_STATE_TEXT_STYLE = """
    QLabel {
        color: #aebac5;
        background: transparent;
        border: none;
        font-size: 13px;
        line-height: 1.35;
    }
"""

SUGGESTION_PROMPT_STYLE = """
    QPushButton#AssistantSuggestionPrompt {
        background-color: transparent;
        border: 1px solid #303a43;
        border-radius: 5px;
        text-align: left;
    }
    QPushButton#AssistantSuggestionPrompt:hover {
        background-color: #252d34;
        border-color: #4b5c69;
    }
    QPushButton#AssistantSuggestionPrompt:focus {
        border: 1px solid #168be0;
    }
    QPushButton#AssistantSuggestionPrompt:disabled {
        background-color: #1b2025;
        border-color: #2a3239;
    }
"""

SUGGESTION_TITLE_STYLE = """
    QLabel#AssistantSuggestionTitle {
        color: #edf3f8;
        background: transparent;
        border: none;
        font-size: 14px;
        font-weight: 600;
    }
"""

SUGGESTION_SUBTITLE_STYLE = """
    QLabel#AssistantSuggestionSubtitle {
        color: #9aa8b4;
        background: transparent;
        border: none;
        font-size: 12px;
    }
"""

SUGGESTION_CHEVRON_STYLE = """
    QLabel#AssistantSuggestionChevron {
        color: #9aa8b4;
        background: transparent;
        border: none;
        font-size: 22px;
        font-weight: 400;
    }
"""

SUGGESTION_ICON_STYLES = """
    QLabel#AssistantSuggestionIcon {
        background-color: transparent;
        border: none;
    }
"""

SEGMENTED_CONTROL_STYLE = """
    QWidget#AssistantSegmentedControl {
        background: transparent;
        border: none;
    }
    QPushButton#AssistantSegment {
        min-height: 36px;
        padding: 3px 10px;
        color: #b8c3cd;
        background-color: #1a1f24;
        border: 1px solid #39434c;
        border-radius: 0px;
        font-size: 12px;
        font-weight: 600;
    }
    QPushButton#AssistantSegment[segmentPosition="first"] {
        border-top-left-radius: 5px;
        border-bottom-left-radius: 5px;
    }
    QPushButton#AssistantSegment[segmentPosition="last"] {
        border-left: none;
        border-top-right-radius: 5px;
        border-bottom-right-radius: 5px;
    }
    QPushButton#AssistantSegment[segmentPosition="middle"] {
        border-left: none;
    }
    QPushButton#AssistantSegment[segmentPosition="only"] {
        border-radius: 5px;
    }
    QPushButton#AssistantSegment:hover:!checked {
        color: #edf3f8;
        background-color: #222a31;
    }
    QPushButton#AssistantSegment:checked {
        color: #42a5f5;
        background-color: #192530;
        border: 1px solid #168be0;
    }
    QPushButton#AssistantSegment:focus {
        border: 1px solid #4dabf5;
    }
    QPushButton#AssistantSegment:disabled {
        color: #6f7b85;
        background-color: #1b2025;
        border-color: #2d353c;
    }
"""

RUNTIME_STATE_STYLE = """
    QFrame#AssistantRuntimeState {
        background-color: #1f252b;
        border: 1px solid #3b4852;
        border-radius: 6px;
    }
"""

RUNTIME_STATE_TITLE_STYLE = """
    QLabel#AssistantRuntimeTitle {
        color: #f3f7fb;
        background: transparent;
        border: none;
        font-size: 15px;
        font-weight: 700;
    }
"""

RUNTIME_STATE_DETAIL_STYLE = """
    QLabel#AssistantRuntimeDetail {
        color: #c3cdd6;
        background: transparent;
        border: none;
        font-size: 13px;
    }
"""

RUNTIME_PROGRESS_STYLE = """
    QProgressBar#AssistantRuntimeProgress {
        background-color: #1b2025;
        border: none;
        border-radius: 2px;
    }
    QProgressBar#AssistantRuntimeProgress::chunk {
        background-color: #4d84bb;
        border-radius: 2px;
    }
"""

TURN_ACTIVITY_STYLE = """
    QFrame#AssistantTurnActivity {
        background-color: #222d34;
        border: 1px solid #4c6678;
        border-radius: 6px;
    }
"""

TURN_ACTIVITY_TITLE_STYLE = """
    QLabel#AssistantTurnActivityTitle {
        color: #f3f7fb;
        background: transparent;
        border: none;
        font-size: 15px;
        font-weight: 700;
    }
"""

TURN_ACTIVITY_STEP_STYLE = """
    QLabel#AssistantTurnActivityStep {
        color: #d5e1e9;
        background: transparent;
        border: none;
        font-size: 13px;
        font-weight: 600;
    }
"""

TURN_ACTIVITY_CANCELABILITY_STYLE = """
    QLabel#AssistantTurnActivityCancelability {
        color: #aebdc8;
        background: transparent;
        border: none;
        font-size: 12px;
    }
"""

TURN_ACTIVITY_PROGRESS_STYLE = """
    QProgressBar#AssistantTurnActivityProgress {
        background-color: #182026;
        border: none;
        border-radius: 2px;
    }
    QProgressBar#AssistantTurnActivityProgress::chunk {
        background-color: #5c91b5;
        border-radius: 2px;
    }
"""

# Scroll Area Styles
SCROLL_AREA_STYLE = """
    QScrollArea {
        background-color: #181c20;
        border: none;
    }
    QScrollBar:vertical {
        border: none;
        background: #181c20;
        width: 10px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background: #4f4f4f;
        min-height: 20px;
        border-radius: 7px;
        margin: 2px;
    }
    QScrollBar::handle:vertical:hover {
        background: #5f5f5f;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
        background: none;
    }
"""

# Control Panel Styles
CONTROL_PANEL_STYLE = """
    QWidget#ControlPanel {
        background-color: #181c20;
        border-top: 1px solid #303941;
        min-height: 56px;
    }
"""

NOTICE_LABEL_STYLE = """
    QLabel#AssistantNotice {
        color: #d6b36b;
        background: transparent;
        border: none;
        font-size: 12px;
    }
"""

# Input Field Styles
COMPOSER_SURFACE_STYLE = """
    QWidget#AssistantComposerSurface {
        background-color: #171b20;
        border: 1px solid #46515b;
        border-radius: 7px;
    }
    QWidget#AssistantComposerSurface[inputFocused="true"] {
        border-color: #168be0;
    }
"""

INPUT_FIELD_STYLE = """
    QPlainTextEdit {
        background-color: transparent;
        color: #f1f5f9;
        border: none;
        padding: 8px 9px;
        font-size: 14px;
    }
    QPlainTextEdit:focus {
        border: none;
    }
    QPlainTextEdit:disabled {
        color: #7c8792;
        background-color: #1b2025;
    }
"""

# Send Button Styles
SEND_BUTTON_STYLE = """
    QToolButton {
        background-color: #087dcc;
        color: white;
        border-radius: 5px;
        font-size: 13px;
        font-weight: 700;
        border: 1px solid transparent;
    }
    QToolButton:hover { background-color: #168fe0; }
    QToolButton:pressed { background-color: #0968a8; }
    QToolButton:focus { border-color: #74c0fc; }
    QToolButton:disabled {
        color: #87919b;
        background-color: #2b333b;
    }
"""

SEND_BUTTON_PROCESSING_STYLE = """
    QToolButton {
        background-color: #9b3f3f;
        color: white;
        border-radius: 8px;
        border: 1px solid transparent;
        font-size: 13px;
        font-weight: bold;
    }
    QToolButton:hover { background-color: #b54c4c; }
    QToolButton:focus { border-color: #e0a0a0; }
"""

SEND_BUTTON_LOCKED_STYLE = """
    QToolButton {
        background-color: #303840;
        color: #b9c4cd;
        border-radius: 8px;
        border: 1px solid #4d5963;
        font-size: 13px;
        font-weight: 700;
    }
    QToolButton:disabled {
        background-color: #303840;
        color: #b9c4cd;
        border-color: #4d5963;
    }
"""

RUNTIME_PRIMARY_ACTION_STYLE = """
    QPushButton {
        min-height: 34px;
        padding: 4px 12px;
        color: #f3f7fb;
        background-color: #3f6f9f;
        border: 1px solid transparent;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 700;
    }
    QPushButton:hover { background-color: #4d84bb; }
    QPushButton:pressed { background-color: #315b84; }
    QPushButton:focus { border-color: #78a9d4; }
"""

RUNTIME_SECONDARY_ACTION_STYLE = """
    QPushButton {
        min-height: 34px;
        padding: 4px 12px;
        color: #d8e0e7;
        background-color: #303840;
        border: 1px solid #56616b;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 600;
    }
    QPushButton:hover {
        color: #ffffff;
        background-color: #39434c;
        border-color: #697681;
    }
    QPushButton:pressed { background-color: #283038; }
    QPushButton:focus { border-color: #78a9d4; }
"""

RESPONSE_ACTION_STYLE = """
    QToolButton#AssistantResponseAction {
        min-height: 34px;
        padding: 4px 12px;
        color: #d8e0e7;
        background-color: #252b31;
        border: 1px solid #56616b;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 600;
        text-align: left;
    }
    QToolButton#AssistantResponseAction:hover {
        color: #ffffff;
        background-color: #303b44;
        border-color: #6f8292;
    }
    QToolButton#AssistantResponseAction:pressed {
        background-color: #20272d;
    }
    QToolButton#AssistantResponseAction:focus {
        border-color: #78a9d4;
    }
"""

RESPONSE_ACTION_TITLE_STYLE = """
    QLabel#AssistantResponseActionTitle {
        color: #c7d5df;
        background: transparent;
        border: none;
        font-size: 12px;
        font-weight: 700;
    }
"""

ACTION_CARD_FRAME_STYLE = """
    QFrame#AssistantConfirmationCard {
        background-color: #252b31;
        border: 1px solid #53616c;
        border-radius: 7px;
    }
    QFrame#AssistantConfirmationCard[destructive="true"] {
        background-color: #312728;
        border-color: #87575a;
    }
"""

ACTION_CARD_TITLE_STYLE = """
    QLabel#AssistantActionCardTitle {
        color: #f3f7fb;
        background: transparent;
        border: none;
        font-size: 14px;
        font-weight: 700;
    }
"""

ACTION_CARD_LABEL_STYLE = """
    QLabel#AssistantActionCardLabel {
        color: #aebdc8;
        background: transparent;
        border: none;
        font-size: 11px;
        font-weight: 700;
    }
"""

ACTION_CARD_TEXT_STYLE = """
    QLabel {
        color: #c8d3dc;
        background: transparent;
        border: none;
        font-size: 13px;
    }
"""

ACTION_CARD_CONTEXT_WARNING_STYLE = """
    QLabel#AssistantActionContextWarning {
        color: #dbc88f;
        background-color: #332f27;
        border: 1px solid #5b5137;
        border-radius: 5px;
        padding: 7px 9px;
        font-size: 12px;
    }
"""

ACTION_CARD_PROPOSAL_ROW_STYLE = """
    QFrame#AssistantProposalRow {
        background-color: #1b2126;
        border: 1px solid #303a43;
        border-radius: 5px;
    }
    QLabel#AssistantProposalLabel {
        color: #dfe7ee;
        background: transparent;
        border: none;
        font-size: 12px;
        font-weight: 700;
    }
    QLabel#AssistantProposalCaption {
        color: #788792;
        background: transparent;
        border: none;
        font-size: 10px;
        font-weight: 600;
    }
    QLabel#AssistantProposalCurrent {
        color: #9aa8b4;
        background: transparent;
        border: none;
        font-size: 13px;
    }
    QLabel#AssistantProposalArrow {
        color: #6f7d88;
        background: transparent;
        border: none;
        font-size: 13px;
    }
    QLabel#AssistantProposalValue {
        color: #f1f6fa;
        background: transparent;
        border: none;
        font-size: 13px;
        font-weight: 600;
    }
"""

ACTION_CARD_PRIMARY_BUTTON_STYLE = """
    QPushButton {
        min-height: 34px;
        padding: 4px 12px;
        color: #ffffff;
        background-color: #3f6f9f;
        border: 1px solid transparent;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 700;
    }
    QPushButton:hover { background-color: #4d84bb; }
    QPushButton:pressed { background-color: #315b84; }
    QPushButton:focus { border-color: #78a9d4; }
    QPushButton:disabled {
        color: #8b959e;
        background-color: #303840;
        border-color: #46515b;
    }
"""

ACTION_CARD_DESTRUCTIVE_BUTTON_STYLE = """
    QPushButton {
        min-height: 34px;
        padding: 4px 12px;
        color: #ffffff;
        background-color: #984b50;
        border: 1px solid transparent;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 700;
    }
    QPushButton:hover { background-color: #ad5a60; }
    QPushButton:pressed { background-color: #7f3e42; }
    QPushButton:focus { border-color: #e1a0a4; }
    QPushButton:disabled {
        color: #a28f91;
        background-color: #493536;
        border-color: #604548;
    }
"""

ACTION_CARD_SECONDARY_BUTTON_STYLE = """
    QPushButton {
        min-height: 34px;
        padding: 4px 12px;
        color: #d8e0e7;
        background-color: #303840;
        border: 1px solid #56616b;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 600;
    }
    QPushButton:hover {
        color: #ffffff;
        background-color: #39434c;
        border-color: #697681;
    }
    QPushButton:focus { border-color: #78a9d4; }
    QPushButton:disabled {
        color: #7f8992;
        background-color: #2a3036;
        border-color: #414a52;
    }
"""

EMPTY_STATE_ACTION_STYLE = RESPONSE_ACTION_STYLE.replace(
    "AssistantResponseAction",
    "AssistantEmptyStateAction",
)

# Message Bubble Styles
USER_BUBBLE_FRAME_STYLE = """
    QFrame#BubbleFrame {
        background-color: #263f39;
        border: 1px solid #3b5f56;
        border-radius: 8px;
    }
"""

USER_BUBBLE_TEXT_STYLE = f"""
    QTextBrowser {{
        color: {Theme.TEXT_PRIMARY};
        font-size: 14px;
        background: transparent;
    }}
"""

AGENT_BUBBLE_FRAME_STYLE = """
    QFrame#BubbleFrame {
        background-color: transparent;
        border: none;
        border-radius: 0px;
    }
"""

CLARIFICATION_BUBBLE_FRAME_STYLE = """
    QFrame#BubbleFrame {
        background-color: #27313a;
        border: 1px solid #587a96;
        border-radius: 8px;
    }
"""

ATTENTION_BUBBLE_FRAME_STYLE = """
    QFrame#BubbleFrame {
        background-color: #332f27;
        border: 1px solid #806b3f;
        border-radius: 8px;
    }
"""

ERROR_BUBBLE_FRAME_STYLE = """
    QFrame#BubbleFrame {
        background-color: #362829;
        border: 1px solid #8a5053;
        border-radius: 8px;
    }
"""

TOOL_RESULT_BUBBLE_FRAME_STYLE = """
    QFrame#BubbleFrame {
        background-color: #26322f;
        border: 1px solid #4b7668;
        border-radius: 8px;
    }
"""

CANCELLED_BUBBLE_FRAME_STYLE = """
    QFrame#BubbleFrame {
        background-color: #292d31;
        border: 1px solid #5b6670;
        border-radius: 8px;
    }
"""

MESSAGE_KIND_LABEL_STYLES = {
    "clarification": """
        QLabel#MessageKindLabel {
            color: #9cc5e3;
            background: transparent;
            border: none;
            font-size: 11px;
            font-weight: 700;
        }
    """,
    "attention": """
        QLabel#MessageKindLabel {
            color: #e1c47d;
            background: transparent;
            border: none;
            font-size: 11px;
            font-weight: 700;
        }
    """,
    "error": """
        QLabel#MessageKindLabel {
            color: #e9a2a6;
            background: transparent;
            border: none;
            font-size: 11px;
            font-weight: 700;
        }
    """,
    "tool_result": """
        QLabel#MessageKindLabel {
            color: #9ed3bf;
            background: transparent;
            border: none;
            font-size: 11px;
            font-weight: 700;
        }
    """,
    "cancelled": """
        QLabel#MessageKindLabel {
            color: #b8c2cb;
            background: transparent;
            border: none;
            font-size: 11px;
            font-weight: 700;
        }
    """,
}

AGENT_BUBBLE_TEXT_STYLE = f"""
    QTextBrowser {{
        color: {Theme.TEXT_PRIMARY};
        font-size: 14px;
        background: transparent;
    }}
"""
