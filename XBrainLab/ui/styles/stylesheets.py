from XBrainLab.ui.styles.theme import Theme


class Stylesheets:
    """
    Centralized collection of reusable CSS stylesheets.
    """

    # Generic GroupBox (Used in AggregateInfoPanel, etc.)
    GROUP_BOX_MINIMAL = f"""
        QGroupBox {{
            background-color: transparent;
            border: none;
            margin-top: 15px;
            font-weight: bold;
            color: {Theme.GRAY_MUTED};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 0px;
            padding: 0 0px;
            color: {Theme.GRAY_MUTED};
        }}
        QLabel {{
            color: {Theme.TEXT_MUTED};
            font-weight: normal;
        }}
    """

    # Success Button (Green)
    BTN_SUCCESS = f"""
        QPushButton {{
            background-color: {Theme.BTN_SUCCESS_BG};
            color: {Theme.LOG_INFO};
            border: 1px solid {Theme.BTN_SUCCESS_BORDER};
            padding: 5px;
            border-radius: 3px;
        }}
        QPushButton:hover {{
            background-color: {Theme.BTN_SUCCESS_HOVER};
            color: white;
        }}
        QPushButton:disabled {{
            background-color: rgba(27, 94, 32, 0.4);
            color: #888888;
            border: 1px solid rgba(27, 94, 32, 0.2);
        }}
    """

    # Danger Button (Red)
    BTN_DANGER = f"""
        QPushButton {{
            background-color: {Theme.BTN_DANGER_BG};
            color: {Theme.LOG_ERROR};
            border: 1px solid {Theme.BTN_DANGER_BORDER};
            padding: 5px;
            border-radius: 3px;
        }}
        QPushButton:hover {{
            background-color: {Theme.BTN_DANGER_HOVER};
            color: white;
        }}
        QPushButton:disabled {{
            background-color: rgba(183, 28, 28, 0.4);
            color: #888888;
            border: 1px solid rgba(183, 28, 28, 0.2);
        }}
    """

    # Warning Button (Orange/Red) - For Stop/Pause
    BTN_WARNING = f"""
        QPushButton {{
            background-color: {Theme.BTN_WARNING_BG};
            color: {Theme.BTN_WARNING_TEXT};
            border: 1px solid {Theme.BTN_WARNING_BORDER};
            padding: 5px;
            border-radius: 3px;
        }}
        QPushButton:hover {{
            background-color: {Theme.BTN_WARNING_HOVER};
            color: white;
        }}
        QPushButton:disabled {{
            background-color: rgba(191, 54, 12, 0.4);
            color: #888888;
            border: 1px solid rgba(191, 54, 12, 0.2);
        }}
    """

    # Primary Action Button (Blue/Blurple)
    BTN_PRIMARY = f"""
        QPushButton {{
            background-color: {Theme.ACCENT_PRIMARY};
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 4px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {Theme.ACCENT_HOVER};
        }}
    """

    # Transparent / Ghost Button
    BTN_GHOST = f"""
        QPushButton {{
            background-color: transparent;
            color: {Theme.TEXT_SECONDARY};
            border: 1px solid {Theme.BACKGROUND_LIGHT};
            padding: 5px;
            border-radius: 3px;
        }}
        QPushButton:hover {{
            color: {Theme.TEXT_PRIMARY};
            border-color: {Theme.ACCENT_PRIMARY};
        }}
    """

    # Separator Line
    SEPARATOR_HORIZONTAL = f"""
        QFrame {{
            background-color: {Theme.BACKGROUND_LIGHT};
            border: none;
            max-height: 1px;
        }}
    """

    # Main Window Theme (VSCode-like)
    MAIN_WINDOW = f"""
        QMainWindow {{
            background-color: {Theme.BACKGROUND_DARK};
            color: {Theme.TEXT_SECONDARY};
        }}
        QWidget {{
            background-color: {Theme.BACKGROUND_DARK};
            color: {Theme.TEXT_SECONDARY};
            font-family: 'Segoe UI', 'Arial';
            font-size: 10pt;
        }}
        /* Top Bar */
        QFrame#TopBar {{
            background-color: {Theme.BACKGROUND_MID};
            border-bottom: 1px solid {Theme.BACKGROUND_LIGHT};
        }}

        /* Nav Buttons (Tabs style) */
        QPushButton#NavButton {{
            background-color: transparent;
            color: {Theme.TEXT_SECONDARY};
            border: none;
            border-bottom: 2px solid transparent;
            padding: 0 15px;
            font-weight: bold;
            height: 48px;
        }}
        QPushButton#NavButton:hover {{
            background-color: {Theme.BACKGROUND_LIGHT};
            color: {Theme.TEXT_PRIMARY};
        }}
        QPushButton#NavButton:checked {{
            color: {Theme.TEXT_PRIMARY};
            border-bottom: 2px solid {Theme.ACCENT_PRIMARY};
            background-color: {Theme.BACKGROUND_DARK};
        }}

        /* Action Buttons (Import, AI) */
        QPushButton#ActionBtn {{
            background-color: {Theme.BLUE_PRIMARY};
            color: {Theme.TEXT_PRIMARY};
            border: none;
            padding: 6px 12px;
            border-radius: 4px;
            font-weight: bold;
        }}
        QPushButton#ActionBtn:hover {{
            background-color: {Theme.BLUE_HOVER};
        }}
        QPushButton#ActionBtn:pressed {{
            background-color: {Theme.BLUE_PRESSED};
        }}
        QPushButton#ActionBtn:checked {{
            background-color: {Theme.BLUE_PRESSED};
            border: 1px solid {Theme.ACCENT_PRIMARY};
        }}

        /* Content Area */
        QStackedWidget {{
            background-color: {Theme.BACKGROUND_DARK};
        }}

        /* Standard Widgets */
        QLabel {{ color: {Theme.TEXT_SECONDARY}; }}

        QGroupBox {{
            border: 1px solid {Theme.BACKGROUND_LIGHT};
            margin-top: 1.5em;
            border-radius: 4px;
            font-weight: bold;
            color: {Theme.TEXT_SECONDARY};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 5px;
            color: {Theme.TEXT_SECONDARY};
        }}

        /* Table Widget */
        QTableWidget {{
            background-color: {Theme.BACKGROUND_DARK};
            gridline-color: {Theme.BACKGROUND_MID};
            border: 1px solid {Theme.BACKGROUND_LIGHT};
            color: {Theme.TEXT_SECONDARY};
        }}
        QHeaderView::section {{
            background-color: {Theme.BACKGROUND_MID};
            color: {Theme.TEXT_SECONDARY};
            padding: 4px;
            border: 1px solid {Theme.BACKGROUND_MID};
        }}
        QTableWidget::item:selected {{
            background-color: {Theme.BLUE_PRESSED};
            color: {Theme.TEXT_PRIMARY};
        }}
        QDockWidget::title {{
            background: {Theme.BACKGROUND_MID};
            text-align: left;
            padding: 5px;
            color: {Theme.TEXT_SECONDARY};
        }}

        /* Card Widget */
        QFrame#CardWidget {{
            background-color: {Theme.BACKGROUND_MID};
            border: 1px solid {Theme.BACKGROUND_LIGHT};
            border-radius: 8px;
        }}
        QLabel#CardTitle {{
            font-size: 12pt;
            font-weight: bold;
            color: {Theme.TEXT_PRIMARY};
            padding-bottom: 10px;
            border-bottom: 1px solid {Theme.BACKGROUND_LIGHT};
            margin-bottom: 5px;
        }}

        /* ScrollBar */
        QScrollBar:vertical {{
            border: none;
            background: {Theme.BACKGROUND_DARK};
            width: 10px;
            margin: 0px 0px 0px 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {Theme.SCROLLBAR_BG};
            min-height: 20px;
            border-radius: 5px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {Theme.SCROLLBAR_HANDLE};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            border: none;
            background: none;
        }}
        QScrollBar:horizontal {{
            border: none;
            background: {Theme.BACKGROUND_DARK};
            height: 10px;
            margin: 0px 0px 0px 0px;
        }}
        QScrollBar::handle:horizontal {{
            background: {Theme.SCROLLBAR_BG};
            min-width: 20px;
            border-radius: 5px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {Theme.SCROLLBAR_HANDLE};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            border: none;
            background: none;
        }}
    """

    # ComboBox Style
    COMBO_BOX = f"""
        QComboBox {{
            background-color: {Theme.BACKGROUND_DARK};
            color: {Theme.TEXT_SECONDARY};
            border: 1px solid {Theme.BACKGROUND_LIGHT};
            padding: 5px;
            min-width: 120px;
        }}
        QComboBox::drop-down {{
            border: 0px;
        }}
    """

    # Sidebar Container
    SIDEBAR_CONTAINER = f"""
        QWidget {{
            background-color: {Theme.BACKGROUND_MID};
            border-right: 1px solid {Theme.BACKGROUND_LIGHT};
        }}
    """

    # Sidebar Button
    SIDEBAR_BTN = f"""
        QPushButton {{
            background-color: transparent;
            color: {Theme.TEXT_SECONDARY};
            text-align: left;
            padding: 8px 15px;
            border: none;
            border-radius: 4px;
        }}
        QPushButton:hover {{
            background-color: {Theme.BACKGROUND_LIGHT};
            color: {Theme.TEXT_PRIMARY};
        }}
        QPushButton:pressed {{
            background-color: {Theme.BACKGROUND_DARK};
        }}
    """

    # Dialog Info Label
    DIALOG_INFO_LABEL = f"""
        QLabel {{
            color: {Theme.TEXT_MUTED};
            font-size: 11px;
            font-style: italic;
        }}
    """

    # Dialog Warning Label
    DIALOG_WARNING_LABEL = f"""
        QLabel {{
            color: {Theme.WARNING};
            font-size: 11px;
            font-weight: bold;
        }}
    """

    # List Item Height
    LIST_ITEM_HEIGHT = """
        QListWidget::item {
            height: 30px;
        }
    """

    # History Table
    HISTORY_TABLE = f"""
        QTableWidget {{
            background-color: {Theme.BACKGROUND_DARK};
            border: 1px solid {Theme.HISTORY_TABLE_BORDER};
            color: {Theme.TEXT_MUTED};
            font-size: 13px;
            gridline-color: {Theme.HISTORY_TABLE_BORDER};
        }}
        QHeaderView::section {{
            background-color: {Theme.BACKGROUND_MID};
            color: {Theme.TEXT_MUTED};
            padding: 6px;
            border: 1px solid {Theme.HISTORY_TABLE_BORDER};
            font-weight: bold;
        }}
        QTableWidget::item {{
            padding: 4px;
            border-bottom: 1px solid {Theme.HISTORY_TABLE_ROW_BORDER};
        }}
        QTableWidget::item:selected {{
            background-color: {Theme.HISTORY_TABLE_SELECTION};
            color: {Theme.TEXT_PRIMARY};
        }}
    """
