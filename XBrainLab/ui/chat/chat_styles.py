# Chat Panel Stylesheet Constants
# Centralized styles for maintainability

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
        background: #424242;
        min-height: 20px;
        border-radius: 7px;
        margin: 2px;
    }
    QScrollBar::handle:vertical:hover {
        background: #555555;
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
    QWidget {
        background-color: #252526;
        border-top: 1px solid #3e3e42;
    }
"""

# Toolbar Button Styles
TOOLBAR_BUTTON_STYLE = """
    QPushButton {
        background: transparent;
        border: none;
        color: #606060;
        padding: 5px;
        font-size: 13px;
        text-align: left;
    }
    QPushButton:hover { color: #cccccc; }
    QPushButton::menu-indicator { image: none; }
"""

# Dropdown Menu Styles
DROPDOWN_MENU_STYLE = """
    QMenu {
        background-color: #252526;
        color: #cccccc;
        border: 1px solid #3e3e42;
    }
    QMenu::item { padding: 5px 20px; }
    QMenu::item:selected { background-color: #3e3e42; }
"""

# Input Field Styles
INPUT_FIELD_STYLE = """
    QLineEdit {
        background-color: transparent;
        color: #ffffff;
        border: none;
        font-size: 15px;
    }
"""

# Send Button Styles
SEND_BUTTON_STYLE = """
    QToolButton {
        background-color: #007acc;
        color: white;
        border-radius: 8px;
        font-size: 16px;
        border: none;
    }
    QToolButton:hover { background-color: #0098ff; }
    QToolButton:pressed { background-color: #005a9e; }
"""

SEND_BUTTON_PROCESSING_STYLE = """
    QToolButton {
        background-color: #d32f2f;
        color: white;
        border-radius: 8px;
        border: none;
        font-size: 14px;
    }
    QToolButton:hover { background-color: #f44336; }
"""

# Message Bubble Styles
USER_BUBBLE_FRAME_STYLE = """
    QFrame#BubbleFrame {
        background-color: #008080;
        border-radius: 12px;
    }
"""

USER_BUBBLE_TEXT_STYLE = """
    QLabel {
        color: white;
        font-size: 15px;
        background: transparent;
    }
"""

AGENT_BUBBLE_FRAME_STYLE = """
    QFrame#BubbleFrame {
        background-color: #2d2d2d;
        border-radius: 12px;
    }
"""

AGENT_BUBBLE_TEXT_STYLE = """
    QLabel {
        color: #d4d4d4;
        font-size: 15px;
        background: transparent;
    }
"""
