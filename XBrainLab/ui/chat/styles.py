"""Centralized stylesheet constants for the Chat Panel.

Defines all Qt stylesheet strings used by chat components including
bubble frames, scroll areas, status chips, control panels, and input fields.
"""

from ..styles.theme import Theme

ASSISTANT_PANEL_STYLE = """
    QWidget#AssistantPanel {
        background-color: #15191d;
    }
"""

HEADER_STYLE = """
    QWidget#AssistantHeader {
        background-color: #1b2025;
        border-bottom: 1px solid #303840;
    }
"""

HEADER_TITLE_STYLE = """
    QLabel#AssistantTitle {
        color: #f3f7fb;
        background: transparent;
        border: none;
        font-size: 16px;
        font-weight: 700;
    }
"""

HEADER_SUBTITLE_STYLE = """
    QLabel#AssistantSubtitle {
        color: #9aa8b5;
        background: transparent;
        border: none;
        font-size: 12px;
    }
"""

GUIDANCE_PANEL_STYLE = """
    QWidget#WorkflowGuidance {
        background-color: #15191d;
        border-bottom: 1px solid #26313a;
    }
"""

GUIDANCE_STAGE_STYLE = """
    QLabel#WorkflowStage {
        color: #f3f7fb;
        background: transparent;
        border: none;
        font-size: 13px;
        font-weight: 700;
    }
"""

GUIDANCE_TEXT_STYLE = """
    QLabel#WorkflowGuidanceText {
        color: #aebbc6;
        background: transparent;
        border: none;
        font-size: 12px;
    }
"""

STATUS_CHIP_STYLE = """
    QLabel {
        color: #d7e0ea;
        background-color: #26313a;
        border: 1px solid #394652;
        border-radius: 7px;
        padding: 4px 8px;
        font-size: 12px;
    }
"""

STATUS_CHIP_WARNING_STYLE = """
    QLabel {
        color: #ffdca8;
        background-color: #3a2f1f;
        border: 1px solid #6b5429;
        border-radius: 7px;
        padding: 4px 8px;
        font-size: 12px;
    }
"""

EMPTY_STATE_STYLE = """
    QFrame#AssistantEmptyState {
        background-color: #15191d;
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
        color: #b7c4cf;
        background: transparent;
        border: none;
        font-size: 13px;
        line-height: 1.35;
    }
"""

# Scroll Area Styles
SCROLL_AREA_STYLE = """
    QScrollArea {
        background-color: #15191d;
        border: none;
    }
    QScrollBar:vertical {
        border: none;
        background: #15191d;
        width: 14px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background: #3c4650;
        min-height: 20px;
        border-radius: 7px;
        margin: 2px;
    }
    QScrollBar::handle:vertical:hover {
        background: #53606b;
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
        background-color: #1b2025;
        border-top: 1px solid #303840;
        min-height: 64px;
    }
"""

# Toolbar Button Styles
TOOLBAR_BUTTON_STYLE = """
    QPushButton {
        background-color: #242b32;
        border: 1px solid #35404a;
        border-radius: 7px;
        color: #d5dee7;
        padding: 5px 9px;
        font-size: 13px;
        text-align: left;
    }
    QPushButton:hover {
        background-color: #2d3740;
        color: #ffffff;
    }
    QPushButton:disabled {
        color: #717c86;
        background-color: #1f252b;
        border: 1px solid #2c343c;
    }
    QPushButton::menu-indicator { image: none; }
    QToolButton {
        background-color: #242b32;
        border: 1px solid #35404a;
        border-radius: 7px;
        color: #d5dee7;
        padding: 4px 8px;
        font-size: 12px;
    }
    QToolButton:hover {
        background-color: #2d3740;
        color: #ffffff;
    }
    QToolButton:disabled {
        color: #717c86;
        background-color: #1f252b;
        border: 1px solid #2c343c;
    }
"""

FOOTER_BUTTON_STYLE = """
    QToolButton {
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 6px;
        color: #b9c4ce;
        padding: 3px 7px;
        font-size: 12px;
    }
    QToolButton:hover {
        background-color: #26313a;
        border: 1px solid #35404a;
        color: #f2f6fa;
    }
    QToolButton:disabled {
        color: #626d76;
        background-color: transparent;
        border: 1px solid transparent;
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

# Dropdown Menu Styles
DROPDOWN_MENU_STYLE = f"""
    QMenu {{
        background-color: #252526;
        color: {Theme.TEXT_MUTED};
        border: {Theme.BORDER_LIGHT};
    }}
    QMenu::item {{ padding: 5px 20px; }}
    QMenu::item:selected {{ background-color: {Theme.BACKGROUND_LIGHT}; }}
"""

# Input Field Styles
INPUT_FIELD_STYLE = """
    QLineEdit {
        background-color: #101418;
        color: #f1f5f9;
        border: 1px solid #394652;
        border-radius: 8px;
        padding: 9px 11px;
        font-size: 15px;
    }
    QLineEdit:focus {
        border: 1px solid #6c9bd2;
    }
    QLineEdit:disabled {
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
        border: none;
    }
    QToolButton:hover { background-color: #4d84bb; }
    QToolButton:pressed { background-color: #315b84; }
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
        border: none;
        font-size: 13px;
        font-weight: bold;
    }
    QToolButton:hover { background-color: #b54c4c; }
"""

# Message Bubble Styles
USER_BUBBLE_FRAME_STYLE = """
    QFrame#BubbleFrame {
        background-color: #1f5f54;
        border: 1px solid #2c7568;
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
        background-color: #202932;
        border: 1px solid #33404a;
        border-radius: 8px;
    }
"""

AGENT_BUBBLE_TEXT_STYLE = f"""
    QTextBrowser {{
        color: {Theme.TEXT_PRIMARY};
        font-size: 14px;
        background: transparent;
    }}
"""
