"""Centralized stylesheet constants for the Chat Panel.

Defines the styles used by visible assistant transcript and composer components.
"""

from ..styles.theme import Theme

ASSISTANT_PANEL_STYLE = """
    QWidget#AssistantPanel {
        background-color: #1e1e1e;
    }
"""

EMPTY_STATE_STYLE = """
    QFrame#AssistantEmptyState {
        background-color: #1e1e1e;
        border: none;
        border-radius: 0px;
    }
"""

EMPTY_STATE_TITLE_STYLE = """
    QLabel#AssistantEmptyTitle {
        color: #f3f7fb;
        background: transparent;
        border: none;
        font-size: 17px;
        font-weight: 700;
    }
"""

EMPTY_STATE_TEXT_STYLE = """
    QLabel {
        color: #b7c4cf;
        background: transparent;
        border: none;
        font-size: 13px;
        line-height: 1.35;
    }
"""

SUGGESTION_PROMPT_STYLE = """
    QToolButton#AssistantSuggestionPrompt {
        min-height: 30px;
        padding: 3px 10px;
        color: #c8d3dc;
        background-color: #252b31;
        border: 1px solid #46515b;
        border-radius: 6px;
        font-size: 12px;
        font-weight: 600;
        text-align: left;
    }
    QToolButton#AssistantSuggestionPrompt:hover {
        color: #ffffff;
        background-color: #303940;
        border-color: #61717e;
    }
    QToolButton#AssistantSuggestionPrompt:focus {
        border-color: #78a9d4;
    }
"""

RUNTIME_STATE_STYLE = """
    QFrame#AssistantRuntimeState {
        background-color: #252b31;
        border: 1px solid #45515c;
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
        background-color: #1e1e1e;
        border: none;
    }
    QScrollBar:vertical {
        border: none;
        background: #1e1e1e;
        width: 14px;
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
        background-color: #252526;
        border-top: 1px solid #3e3e3e;
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
INPUT_FIELD_STYLE = """
    QPlainTextEdit {
        background-color: #1e1e1e;
        color: #f1f5f9;
        border: 1px solid #4a4a4a;
        border-radius: 8px;
        padding: 9px 11px;
        font-size: 15px;
    }
    QPlainTextEdit:focus {
        border: 1px solid #5B7DB1;
    }
    QPlainTextEdit:disabled {
        color: #7c8792;
        background-color: #1b2025;
    }
"""

# Send Button Styles
SEND_BUTTON_STYLE = """
    QToolButton {
        background-color: #3f6f9f;
        color: white;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 700;
        border: 1px solid transparent;
    }
    QToolButton:hover { background-color: #4d84bb; }
    QToolButton:pressed { background-color: #315b84; }
    QToolButton:focus { border-color: #78a9d4; }
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

ACTION_CARD_VALUE_STYLE = """
    QLabel#AssistantActionCardValues {
        color: #eef4f8;
        background-color: #1e2429;
        border: 1px solid #3f4b54;
        border-radius: 5px;
        padding: 8px 10px;
        font-size: 13px;
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
        background-color: #2d2d2d;
        border: 1px solid #3e3e3e;
        border-radius: 8px;
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
