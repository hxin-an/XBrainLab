"""Centralized stylesheet constants for the Chat Panel.

Defines the styles used by visible assistant transcript and composer components.
"""

from ..styles.theme import Theme

ASSISTANT_BACKGROUND = Theme.BACKGROUND_DARK
ASSISTANT_SURFACE = Theme.METRICS_TABLE_BG
ASSISTANT_SURFACE_HOVER = Theme.METRICS_TABLE_ALT_BG
ASSISTANT_BORDER = Theme.METRICS_TABLE_GRID
ASSISTANT_BORDER_HOVER = Theme.BORDER
ASSISTANT_ACCENT = Theme.BLUE_PRIMARY
ASSISTANT_ACCENT_HOVER = Theme.BLUE_HOVER

MESSAGE_DOCUMENT_STYLE = f"""
    a {{ color: {Theme.CHART_PRIMARY}; text-decoration: none; }}
    code {{
        color: {Theme.TEXT_PRIMARY};
        font-family: 'Cascadia Mono', 'Consolas', monospace;
    }}
"""

ASSISTANT_PANEL_STYLE = f"""
    QWidget#AssistantPanel {{
        background-color: {ASSISTANT_BACKGROUND};
    }}
"""

EMPTY_STATE_STYLE = f"""
    QFrame#AssistantEmptyState {{
        background-color: {ASSISTANT_BACKGROUND};
        border: none;
        border-radius: 0px;
    }}
"""

EMPTY_STATE_TITLE_STYLE = f"""
    QLabel#AssistantEmptyTitle {{
        color: {Theme.TEXT_PRIMARY};
        background: transparent;
        border: none;
        font-size: 18px;
        font-weight: 700;
    }}
"""

EMPTY_STATE_TEXT_STYLE = f"""
    QLabel {{
        color: {Theme.TEXT_SECONDARY};
        background: transparent;
        border: none;
        font-size: 13px;
        line-height: 1.35;
    }}
"""

SUGGESTION_PROMPT_STYLE = f"""
    QPushButton#AssistantSuggestionPrompt {{
        background-color: transparent;
        border: 1px solid {ASSISTANT_BORDER};
        border-radius: 5px;
        text-align: left;
    }}
    QPushButton#AssistantSuggestionPrompt:hover {{
        background-color: {ASSISTANT_SURFACE_HOVER};
        border-color: {ASSISTANT_BORDER_HOVER};
    }}
    QPushButton#AssistantSuggestionPrompt:focus {{
        border: 1px solid {Theme.BLUE_FOCUS_BORDER};
    }}
    QPushButton#AssistantSuggestionPrompt:disabled {{
        background-color: {ASSISTANT_BACKGROUND};
        border-color: {ASSISTANT_BORDER};
    }}
"""

SUGGESTION_TITLE_STYLE = f"""
    QLabel#AssistantSuggestionTitle {{
        color: {Theme.TEXT_PRIMARY};
        background: transparent;
        border: none;
        font-size: 14px;
        font-weight: 600;
    }}
"""

SUGGESTION_SUBTITLE_STYLE = f"""
    QLabel#AssistantSuggestionSubtitle {{
        color: {Theme.TEXT_SECONDARY};
        background: transparent;
        border: none;
        font-size: 12px;
    }}
"""

SUGGESTION_CHEVRON_STYLE = f"""
    QLabel#AssistantSuggestionChevron {{
        color: {Theme.TEXT_SECONDARY};
        background: transparent;
        border: none;
        font-size: 18px;
        font-weight: 400;
    }}
"""

SUGGESTION_ICON_STYLES = """
    QLabel#AssistantSuggestionIcon {
        background-color: transparent;
        border: none;
    }
"""

SEGMENTED_CONTROL_STYLE = f"""
    QWidget#AssistantSegmentedControl {{
        background: transparent;
        border: none;
    }}
    QPushButton#AssistantSegment {{
        min-height: 36px;
        padding: 3px 10px;
        color: {Theme.TEXT_SECONDARY};
        background-color: {Theme.METRICS_TABLE_BG};
        border: 1px solid {Theme.METRICS_TABLE_GRID};
        border-radius: 0px;
        font-size: 12px;
        font-weight: 600;
    }}
    QPushButton#AssistantSegment[segmentPosition="first"] {{
        border-top-left-radius: 5px;
        border-bottom-left-radius: 5px;
    }}
    QPushButton#AssistantSegment[segmentPosition="last"] {{
        border-left: none;
        border-top-right-radius: 5px;
        border-bottom-right-radius: 5px;
    }}
    QPushButton#AssistantSegment[segmentPosition="middle"] {{
        border-left: none;
    }}
    QPushButton#AssistantSegment[segmentPosition="only"] {{
        border-radius: 5px;
    }}
    QPushButton#AssistantSegment:hover:!checked {{
        color: {Theme.TEXT_PRIMARY};
        background-color: {Theme.METRICS_TABLE_ALT_BG};
    }}
    QPushButton#AssistantSegment:checked {{
        color: {Theme.CHART_PRIMARY};
        background-color: {Theme.METRICS_TABLE_ALT_BG};
        border: 1px solid {Theme.BLUE_FOCUS_BORDER};
    }}
    QPushButton#AssistantSegment:focus {{
        border: 1px solid {Theme.BLUE_FOCUS_BORDER};
    }}
    QPushButton#AssistantSegment:disabled {{
        color: {Theme.BTN_DISABLED_TEXT};
        background-color: {Theme.BTN_DISABLED_BG};
        border-color: {Theme.BTN_DISABLED_BORDER};
    }}
"""

RUNTIME_STATE_STYLE = """
    QFrame#AssistantRuntimeState {
        background-color: transparent;
        border: none;
        border-radius: 0px;
    }
"""

RUNTIME_STATE_TITLE_STYLE = f"""
    QLabel#AssistantRuntimeTitle {{
        color: {Theme.TEXT_PRIMARY};
        background: transparent;
        border: none;
        font-size: 15px;
        font-weight: 700;
    }}
"""

RUNTIME_STATE_DETAIL_STYLE = f"""
    QLabel#AssistantRuntimeDetail {{
        color: {Theme.TEXT_MUTED};
        background: transparent;
        border: none;
        font-size: 13px;
    }}
"""

RUNTIME_PROGRESS_STYLE = f"""
    QProgressBar#AssistantRuntimeProgress {{
        background-color: {Theme.BACKGROUND_DARK};
        border: none;
        border-radius: 2px;
    }}
    QProgressBar#AssistantRuntimeProgress::chunk {{
        background-color: {Theme.ACCENT_PRIMARY};
        border-radius: 2px;
    }}
"""

TURN_ACTIVITY_STYLE = """
    QFrame#AssistantTurnActivity {
        background-color: transparent;
        border: none;
        border-radius: 0px;
    }
"""

CODE_BLOCK_STYLE = f"""
    QPlainTextEdit#AssistantCodeBlock {{
        color: {Theme.TEXT_PRIMARY};
        background-color: {Theme.METRICS_TABLE_BG};
        border: 1px solid {Theme.METRICS_TABLE_GRID};
        border-radius: 4px;
        padding: 7px 8px;
        font-family: 'Cascadia Mono', 'Consolas', monospace;
        font-size: 12px;
        selection-background-color: {Theme.TABLE_SELECTION};
    }}
    QPlainTextEdit#AssistantCodeBlock QScrollBar:horizontal {{
        height: 9px;
        margin: 1px 3px 1px 3px;
        background: transparent;
        border: none;
    }}
    QPlainTextEdit#AssistantCodeBlock QScrollBar::handle:horizontal {{
        min-width: 28px;
        background: {Theme.SCROLLBAR_HANDLE};
        border: none;
        border-radius: 3px;
    }}
    QPlainTextEdit#AssistantCodeBlock QScrollBar::handle:horizontal:hover {{
        background: {Theme.SCROLLBAR_HANDLE_HOVER};
    }}
    QPlainTextEdit#AssistantCodeBlock QScrollBar::add-line:horizontal,
    QPlainTextEdit#AssistantCodeBlock QScrollBar::sub-line:horizontal {{
        width: 0px;
        background: transparent;
        border: none;
    }}
    QPlainTextEdit#AssistantCodeBlock QScrollBar::add-page:horizontal,
    QPlainTextEdit#AssistantCodeBlock QScrollBar::sub-page:horizontal {{
        background: transparent;
    }}
"""

TURN_ACTIVITY_TITLE_STYLE = f"""
    QLabel#AssistantTurnActivityTitle {{
        color: {Theme.TEXT_PRIMARY};
        background: transparent;
        border: none;
        font-size: 15px;
        font-weight: 700;
    }}
"""

TURN_ACTIVITY_STEP_STYLE = f"""
    QLabel#AssistantTurnActivityStep {{
        color: {Theme.TEXT_MUTED};
        background: transparent;
        border: none;
        font-size: 13px;
        font-weight: 600;
    }}
"""

TURN_ACTIVITY_SCOPE_STYLE = f"""
    QLabel#AssistantTurnActivityScope {{
        color: {Theme.TEXT_SECONDARY};
        background: transparent;
        border: none;
        font-size: 12px;
    }}
"""

TURN_ACTIVITY_CANCELABILITY_STYLE = f"""
    QLabel#AssistantTurnActivityCancelability {{
        color: {Theme.TEXT_SECONDARY};
        background: transparent;
        border: none;
        font-size: 12px;
    }}
"""

TURN_ACTIVITY_PROGRESS_STYLE = f"""
    QProgressBar#AssistantTurnActivityProgress {{
        background-color: {Theme.BACKGROUND_DARK};
        border: none;
        border-radius: 2px;
    }}
    QProgressBar#AssistantTurnActivityProgress::chunk {{
        background-color: {Theme.ACCENT_PRIMARY};
        border-radius: 2px;
    }}
"""

# Scroll Area Styles
SCROLL_AREA_STYLE = f"""
    QScrollArea {{
        background-color: {ASSISTANT_BACKGROUND};
        border: none;
    }}
    QScrollBar:vertical {{
        border: none;
        background: {ASSISTANT_BACKGROUND};
        width: 10px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {Theme.SCROLLBAR_HANDLE};
        min-height: 20px;
        border-radius: 7px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {Theme.SCROLLBAR_HANDLE_HOVER};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}
"""

# Control Panel Styles
CONTROL_PANEL_STYLE = f"""
    QWidget#ControlPanel {{
        background-color: {ASSISTANT_BACKGROUND};
        border-top: 1px solid {ASSISTANT_BORDER};
        min-height: 56px;
    }}
"""

NOTICE_LABEL_STYLE = f"""
    QLabel#AssistantNotice {{
        color: {Theme.LOG_WARNING};
        background: transparent;
        border: none;
        font-size: 12px;
    }}
"""

# Input Field Styles
COMPOSER_SURFACE_STYLE = f"""
    QWidget#AssistantComposerSurface {{
        background-color: {ASSISTANT_SURFACE};
        border: 1px solid {ASSISTANT_BORDER};
        border-radius: 7px;
    }}
    QWidget#AssistantComposerSurface[inputFocused="true"] {{
        border-color: {Theme.BLUE_FOCUS_BORDER};
    }}
"""

INPUT_FIELD_STYLE = f"""
    QPlainTextEdit {{
        background-color: transparent;
        color: {Theme.TEXT_PRIMARY};
        border: none;
        padding: 6px 8px;
        font-size: 13px;
    }}
    QPlainTextEdit:focus {{
        border: none;
    }}
    QPlainTextEdit:disabled {{
        color: {Theme.BTN_DISABLED_TEXT};
        background-color: transparent;
    }}
"""

# Send Button Styles
SEND_BUTTON_STYLE = f"""
    QToolButton {{
        background-color: {Theme.BLUE_PRIMARY};
        color: white;
        border-radius: 5px;
        font-size: 13px;
        font-weight: 600;
        border: 1px solid transparent;
    }}
    QToolButton:hover {{ background-color: {Theme.BLUE_HOVER}; }}
    QToolButton:pressed {{ background-color: {Theme.BLUE_PRESSED}; }}
    QToolButton:focus {{ border-color: {Theme.BLUE_FOCUS_BORDER}; }}
    QToolButton:disabled {{
        color: {Theme.BTN_DISABLED_TEXT};
        background-color: {Theme.BTN_DISABLED_BG};
        border-color: {Theme.BTN_DISABLED_BORDER};
    }}
"""

SEND_BUTTON_PROCESSING_STYLE = f"""
    QToolButton {{
        background-color: {Theme.BTN_DANGER_BG};
        color: {Theme.TEXT_PRIMARY};
        border-radius: 5px;
        border: 1px solid {Theme.BTN_DANGER_BORDER};
        font-size: 13px;
        font-weight: 700;
    }}
    QToolButton:hover {{ background-color: {Theme.BTN_DANGER_HOVER}; }}
    QToolButton:focus {{ border-color: {Theme.ACCENT_ERROR}; }}
"""

SEND_BUTTON_LOCKED_STYLE = f"""
    QToolButton {{
        background-color: {Theme.BTN_DISABLED_BG};
        color: {Theme.BTN_DISABLED_TEXT};
        border-radius: 5px;
        border: 1px solid {Theme.BTN_DISABLED_BORDER};
        font-size: 13px;
        font-weight: 700;
    }}
    QToolButton:disabled {{
        background-color: {Theme.BTN_DISABLED_BG};
        color: {Theme.BTN_DISABLED_TEXT};
        border-color: {Theme.BTN_DISABLED_BORDER};
    }}
"""

RUNTIME_PRIMARY_ACTION_STYLE = f"""
    QPushButton {{
        min-height: 34px;
        padding: 4px 12px;
        color: {Theme.TEXT_PRIMARY};
        background-color: {Theme.BLUE_PRIMARY};
        border: 1px solid transparent;
        border-radius: 5px;
        font-size: 13px;
        font-weight: 700;
    }}
    QPushButton:hover {{ background-color: {Theme.BLUE_HOVER}; }}
    QPushButton:pressed {{ background-color: {Theme.BLUE_PRESSED}; }}
    QPushButton:focus {{ border-color: {Theme.BLUE_FOCUS_BORDER}; }}
"""

RUNTIME_SECONDARY_ACTION_STYLE = f"""
    QPushButton {{
        min-height: 34px;
        padding: 4px 12px;
        color: {Theme.TEXT_MUTED};
        background-color: {Theme.BACKGROUND_MID};
        border: 1px solid {Theme.BORDER};
        border-radius: 5px;
        font-size: 13px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        color: {Theme.TEXT_PRIMARY};
        background-color: {Theme.BACKGROUND_LIGHT};
        border-color: {Theme.GRAY_LIGHT};
    }}
    QPushButton:pressed {{ background-color: {Theme.METRICS_TABLE_BG}; }}
    QPushButton:focus {{ border-color: {Theme.BLUE_FOCUS_BORDER}; }}
"""

RESPONSE_ACTION_STYLE = f"""
    QToolButton#AssistantResponseAction {{
        min-height: 34px;
        padding: 4px 12px;
        color: {Theme.TEXT_MUTED};
        background-color: {Theme.METRICS_TABLE_BG};
        border: 1px solid {Theme.BORDER};
        border-radius: 5px;
        font-size: 13px;
        font-weight: 600;
        text-align: left;
    }}
    QToolButton#AssistantResponseAction:hover {{
        color: {Theme.TEXT_PRIMARY};
        background-color: {Theme.BACKGROUND_MID};
        border-color: {Theme.GRAY_LIGHT};
    }}
    QToolButton#AssistantResponseAction:pressed {{
        background-color: {Theme.BACKGROUND_DARK};
    }}
    QToolButton#AssistantResponseAction:focus {{
        border-color: {Theme.BLUE_FOCUS_BORDER};
    }}
"""

RESPONSE_ACTION_TITLE_STYLE = f"""
    QLabel#AssistantResponseActionTitle {{
        color: {Theme.TEXT_MUTED};
        background: transparent;
        border: none;
        font-size: 12px;
        font-weight: 700;
    }}
"""

ACTION_CARD_FRAME_STYLE = f"""
    QFrame#AssistantConfirmationCard {{
        background-color: {Theme.METRICS_TABLE_BG};
        border: 1px solid {Theme.BORDER};
        border-radius: 7px;
    }}
    QFrame#AssistantConfirmationCard[destructive="true"] {{
        background-color: {Theme.METRICS_TABLE_BG};
        border-color: {Theme.BTN_DANGER_BORDER};
    }}
"""

ACTION_CARD_TITLE_STYLE = f"""
    QLabel#AssistantActionCardTitle {{
        color: {Theme.TEXT_PRIMARY};
        background: transparent;
        border: none;
        font-size: 14px;
        font-weight: 700;
    }}
"""

ACTION_CARD_LABEL_STYLE = f"""
    QLabel#AssistantActionCardLabel {{
        color: {Theme.TEXT_SECONDARY};
        background: transparent;
        border: none;
        font-size: 11px;
        font-weight: 700;
    }}
"""

ACTION_CARD_TEXT_STYLE = f"""
    QLabel {{
        color: {Theme.TEXT_MUTED};
        background: transparent;
        border: none;
        font-size: 13px;
    }}
"""

ACTION_CARD_CONTEXT_WARNING_STYLE = f"""
    QLabel#AssistantActionContextWarning {{
        color: {Theme.LOG_WARNING};
        background-color: {Theme.BACKGROUND_MID};
        border: 1px solid {Theme.BTN_WARNING_BORDER};
        border-radius: 5px;
        padding: 7px 9px;
        font-size: 12px;
    }}
"""

ACTION_CARD_PROPOSAL_ROW_STYLE = f"""
    QFrame#AssistantProposalRow {{
        background-color: {Theme.BACKGROUND_DARK};
        border: 1px solid {Theme.METRICS_TABLE_GRID};
        border-radius: 5px;
    }}
    QLabel#AssistantProposalLabel {{
        color: {Theme.TEXT_PRIMARY};
        background: transparent;
        border: none;
        font-size: 12px;
        font-weight: 700;
    }}
    QLabel#AssistantProposalCaption {{
        color: {Theme.GRAY_MUTED};
        background: transparent;
        border: none;
        font-size: 10px;
        font-weight: 600;
    }}
    QLabel#AssistantProposalCurrent {{
        color: {Theme.TEXT_SECONDARY};
        background: transparent;
        border: none;
        font-size: 13px;
    }}
    QLabel#AssistantProposalArrow {{
        color: {Theme.GRAY_MUTED};
        background: transparent;
        border: none;
        font-size: 13px;
    }}
    QLabel#AssistantProposalValue {{
        color: {Theme.TEXT_PRIMARY};
        background: transparent;
        border: none;
        font-size: 13px;
        font-weight: 600;
    }}
"""

ACTION_CARD_PRIMARY_BUTTON_STYLE = f"""
    QPushButton {{
        min-height: 34px;
        padding: 4px 12px;
        color: {Theme.TEXT_PRIMARY};
        background-color: {Theme.BLUE_PRIMARY};
        border: 1px solid transparent;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 700;
    }}
    QPushButton:hover {{ background-color: {Theme.BLUE_HOVER}; }}
    QPushButton:pressed {{ background-color: {Theme.BLUE_PRESSED}; }}
    QPushButton:focus {{ border-color: {Theme.BLUE_FOCUS_BORDER}; }}
    QPushButton:disabled {{
        color: {Theme.BTN_DISABLED_TEXT};
        background-color: {Theme.BTN_DISABLED_BG};
        border-color: {Theme.BTN_DISABLED_BORDER};
    }}
"""

ACTION_CARD_DESTRUCTIVE_BUTTON_STYLE = f"""
    QPushButton {{
        min-height: 34px;
        padding: 4px 12px;
        color: {Theme.TEXT_PRIMARY};
        background-color: {Theme.BTN_DANGER_BG};
        border: 1px solid transparent;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 700;
    }}
    QPushButton:hover {{ background-color: {Theme.BTN_DANGER_HOVER}; }}
    QPushButton:pressed {{ background-color: {Theme.BTN_DANGER_BORDER}; }}
    QPushButton:focus {{ border-color: {Theme.ACCENT_ERROR}; }}
    QPushButton:disabled {{
        color: {Theme.BTN_DANGER_DISABLED_TEXT};
        background-color: {Theme.BTN_DANGER_DISABLED_BG};
        border-color: {Theme.BTN_DANGER_DISABLED_BORDER};
    }}
"""

ACTION_CARD_SECONDARY_BUTTON_STYLE = f"""
    QPushButton {{
        min-height: 34px;
        padding: 4px 12px;
        color: {Theme.TEXT_MUTED};
        background-color: {Theme.BACKGROUND_MID};
        border: 1px solid {Theme.BORDER};
        border-radius: 6px;
        font-size: 13px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        color: {Theme.TEXT_PRIMARY};
        background-color: {Theme.BACKGROUND_LIGHT};
        border-color: {Theme.GRAY_LIGHT};
    }}
    QPushButton:focus {{ border-color: {Theme.BLUE_FOCUS_BORDER}; }}
    QPushButton:disabled {{
        color: {Theme.BTN_DISABLED_TEXT};
        background-color: {Theme.BTN_DISABLED_BG};
        border-color: {Theme.BTN_DISABLED_BORDER};
    }}
"""

EMPTY_STATE_ACTION_STYLE = RESPONSE_ACTION_STYLE.replace(
    "AssistantResponseAction",
    "AssistantEmptyStateAction",
)

# Message Bubble Styles
USER_BUBBLE_FRAME_STYLE = f"""
    QFrame#BubbleFrame {{
        background-color: {Theme.BACKGROUND_MID};
        border: 1px solid {Theme.BORDER};
        border-radius: 8px;
    }}
"""

USER_BUBBLE_TEXT_STYLE = f"""
    QTextBrowser {{
        color: {Theme.TEXT_PRIMARY};
        font-size: 14px;
        background: transparent;
    }}
"""

AGENT_BUBBLE_FRAME_STYLE = f"""
    QFrame#BubbleFrame {{
        background-color: {Theme.CHAT_AI_BUBBLE};
        border: 1px solid {Theme.ACCENT_PRIMARY};
        border-radius: 8px;
    }}
"""

CLARIFICATION_BUBBLE_FRAME_STYLE = f"""
    QFrame#BubbleFrame {{
        background-color: {Theme.METRICS_TABLE_BG};
        border: 1px solid {Theme.ACCENT_PRIMARY};
        border-radius: 8px;
    }}
"""

ATTENTION_BUBBLE_FRAME_STYLE = f"""
    QFrame#BubbleFrame {{
        background-color: {Theme.METRICS_TABLE_BG};
        border: 1px solid {Theme.BTN_WARNING_BORDER};
        border-radius: 8px;
    }}
"""

ERROR_BUBBLE_FRAME_STYLE = f"""
    QFrame#BubbleFrame {{
        background-color: {Theme.METRICS_TABLE_BG};
        border: 1px solid {Theme.BTN_DANGER_BORDER};
        border-radius: 8px;
    }}
"""

TOOL_RESULT_BUBBLE_FRAME_STYLE = f"""
    QFrame#BubbleFrame {{
        background-color: {Theme.METRICS_TABLE_BG};
        border: 1px solid {Theme.BTN_SUCCESS_BORDER};
        border-radius: 8px;
    }}
"""

CANCELLED_BUBBLE_FRAME_STYLE = f"""
    QFrame#BubbleFrame {{
        background-color: {Theme.METRICS_TABLE_BG};
        border: 1px solid {Theme.BORDER};
        border-radius: 8px;
    }}
"""

MESSAGE_KIND_LABEL_STYLES = {
    "clarification": f"""
        QLabel#MessageKindLabel {{
            color: {Theme.CHART_PRIMARY};
            background: transparent;
            border: none;
            font-size: 11px;
            font-weight: 700;
        }}
    """,
    "attention": f"""
        QLabel#MessageKindLabel {{
            color: {Theme.LOG_WARNING};
            background: transparent;
            border: none;
            font-size: 11px;
            font-weight: 700;
        }}
    """,
    "error": f"""
        QLabel#MessageKindLabel {{
            color: {Theme.LOG_ERROR};
            background: transparent;
            border: none;
            font-size: 11px;
            font-weight: 700;
        }}
    """,
    "tool_result": f"""
        QLabel#MessageKindLabel {{
            color: {Theme.LOG_INFO};
            background: transparent;
            border: none;
            font-size: 11px;
            font-weight: 700;
        }}
    """,
    "cancelled": f"""
        QLabel#MessageKindLabel {{
            color: {Theme.TEXT_SECONDARY};
            background: transparent;
            border: none;
            font-size: 11px;
            font-weight: 700;
        }}
    """,
}

AGENT_BUBBLE_TEXT_STYLE = f"""
    QTextBrowser {{
        color: {Theme.TEXT_PRIMARY};
        font-size: 14px;
        background: transparent;
    }}
"""
