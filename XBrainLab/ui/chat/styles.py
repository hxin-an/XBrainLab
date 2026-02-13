# Chat Panel Stylesheet Constants
# Centralized styles for maintainability
from ..styles.theme import Theme

# Scroll Area Styles
SCROLL_AREA_STYLE = f"""
    QScrollArea {{
        background-color: {Theme.BACKGROUND_DARK};
        border: none;
    }}
    QScrollBar:vertical {{
        border: none;
        background: {Theme.BACKGROUND_DARK};
        width: 14px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: #424242;
        min-height: 20px;
        border-radius: 7px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: #555555;
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
        background-color: #252526;
        border-top: {Theme.BORDER_LIGHT};
        min-height: 50px;
    }}
"""

# Toolbar Button Styles
TOOLBAR_BUTTON_STYLE = f"""
    QPushButton {{
        background: transparent;
        border: none;
        color: {Theme.TEXT_SECONDARY};
        padding: 5px;
        font-size: 13px;
        text-align: left;
    }}
    QPushButton:hover {{ color: {Theme.TEXT_MUTED}; }}
    QPushButton::menu-indicator {{ image: none; }}
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
INPUT_FIELD_STYLE = f"""
    QLineEdit {{
        background-color: {Theme.BACKGROUND_LIGHT};
        color: {Theme.TEXT_PRIMARY};
        border: 1px solid #454545;
        border-radius: 6px;
        padding: 8px;
        font-size: 15px;
    }}
    QLineEdit:focus {{
        border: 1px solid {Theme.ACCENT_PRIMARY};
    }}
"""

# Send Button Styles
SEND_BUTTON_STYLE = f"""
    QToolButton {{
        background-color: {Theme.ACCENT_PRIMARY};
        color: white;
        border-radius: 8px;
        font-size: 16px;
        border: none;
    }}
    QToolButton:hover {{ background-color: {Theme.ACCENT_HOVER}; }}
    QToolButton:pressed {{ background-color: #5b6eae; }}
"""

SEND_BUTTON_PROCESSING_STYLE = f"""
    QToolButton {{
        background-color: {Theme.ACCENT_ERROR};
        color: white;
        border-radius: 8px;
        border: none;
        font-size: 12px;
        font-weight: bold;
    }}
    QToolButton:hover {{ background-color: #ff6b6b; }}
"""

# Message Bubble Styles
USER_BUBBLE_FRAME_STYLE = f"""
    QFrame#BubbleFrame {{
        background-color: {Theme.CHAT_USER_BUBBLE};
        border-radius: 12px;
        border-bottom-right-radius: 2px;  /* Small tail effect */
    }}
"""

USER_BUBBLE_TEXT_STYLE = f"""
    QTextBrowser {{
        color: {Theme.TEXT_PRIMARY};
        font-size: 16px;
        background: transparent;
    }}
"""

AGENT_BUBBLE_FRAME_STYLE = f"""
    QFrame#BubbleFrame {{
        background-color: {Theme.CHAT_AI_BUBBLE};
        border-radius: 12px;
    }}
"""

AGENT_BUBBLE_TEXT_STYLE = f"""
    QTextBrowser {{
        color: {Theme.TEXT_PRIMARY};
        font-size: 16px;
        background: transparent;
    }}
"""
