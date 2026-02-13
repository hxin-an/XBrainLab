"""
Centralized Theme Definitions for XBrainLab.
Refactoring Goal: Remove hardcoded colors from UI components.
"""


class Theme:
    """
    Centralized Theme Definitions for XBrainLab.
    Provides color constants and utility methods for styling (e.g., Matplotlib
    integration).
    """

    # Main Application Colors
    BACKGROUND_DARK = "#1e1e1e"
    BACKGROUND_MID = "#2d2d2d"
    BACKGROUND_LIGHT = "#3e3e3e"

    # Text Colors
    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#a0a0a0"

    # Accent Colors
    ACCENT_PRIMARY = "#5B7DB1"  # Muted blue with more blue
    ACCENT_HOVER = "#4A6A9A"
    ACCENT_ERROR = "#ff5555"
    ACCENT_SUCCESS = "#50fa7b"
    ACCENT_WARNING = "#f1fa8c"

    # Chat Specific
    CHAT_USER_BUBBLE = "#005c4b"  # Original dark green
    CHAT_AI_BUBBLE = "#202c33"
    CHAT_SYSTEM_BUBBLE = "#3e3e3e"

    # Borders
    BORDER_LIGHT = "1px solid #3e3e3e"
    BORDER_ACCENT = f"1px solid {ACCENT_PRIMARY}"

    # Action Buttons
    BTN_SUCCESS_BG = "#1b5e20"
    BTN_SUCCESS_BORDER = "#2e7d32"
    BTN_SUCCESS_HOVER = "#2e7d32"

    BTN_DANGER_BG = "#4a1818"
    BTN_DANGER_BORDER = "#802020"
    BTN_DANGER_HOVER = "#602020"

    BTN_WARNING_BG = "#bf360c"
    BTN_WARNING_TEXT = "#ffccbc"
    BTN_WARNING_BORDER = "#d84315"
    BTN_WARNING_HOVER = "#d84315"

    # Disabled Button States
    BTN_DISABLED_TEXT = "#888888"

    BTN_SUCCESS_DISABLED_BG = "rgba(27, 94, 32, 0.4)"
    BTN_SUCCESS_DISABLED_BORDER = "rgba(27, 94, 32, 0.2)"

    BTN_DANGER_DISABLED_BG = "rgba(183, 28, 28, 0.4)"
    BTN_DANGER_DISABLED_BORDER = "rgba(183, 28, 28, 0.2)"

    BTN_WARNING_DISABLED_BG = "rgba(191, 54, 12, 0.4)"
    BTN_WARNING_DISABLED_BORDER = "rgba(191, 54, 12, 0.2)"

    # Plot Colors
    BORDER = "#555555"
    TEXT_MUTED = "#cccccc"

    # Semantic Colors
    ERROR = "#ef5350"
    WARNING = "#ff9800"

    # Visualization
    BRAIN_MESH = "#FDEBD0"
    CHECKBOX_ON = "#456071"

    # --- UI Elements ---
    GRAY_MUTED = "#808080"
    GRAY_LIGHT = "#a0a0a0"

    # Blue / Action Colors (VS Code style)
    BLUE_PRIMARY = "#0e639c"
    BLUE_HOVER = "#1177bb"
    BLUE_PRESSED = "#094771"
    BLUE_FOCUS_BORDER = "#007acc"

    # Scrollbar
    SCROLLBAR_BG = "#424242"
    SCROLLBAR_HANDLE = "#4f4f4f"
    SCROLLBAR_HANDLE_HOVER = "#5f5f5f"

    # Status / Logs
    LOG_DEBUG = "#808080"
    LOG_INFO = "#a5d6a7"
    LOG_WARNING = "#ffcc80"
    LOG_ERROR = "#ff9999"

    # History Table
    HISTORY_TABLE_BORDER = "#333"
    HISTORY_TABLE_ROW_BORDER = "#2a2a2a"
    HISTORY_TABLE_SELECTION = "#007acc"

    # Charts
    CHART_PRIMARY = "#2196F3"  # Blue
    CHART_SECONDARY = "#4CAF50"  # Green
    CHART_TERTIARY = "#FFC107"  # Amber
    CHART_ORIGINAL_DATA = "#808080"  # Gray

    # Metrics Table
    METRICS_TABLE_BG = "#252526"
    METRICS_TABLE_GRID = "#3e3e42"
    METRICS_TABLE_HEADER_BG = "#094771"
    METRICS_TABLE_BORDER = "#3e3e42"
    METRICS_TABLE_SELECTION = "#3e3e42"

    @staticmethod
    def apply_matplotlib_dark_theme(fig, ax=None, axes=None):
        """
        Apply standard dark theme to Matplotlib Figure and Axes.
        """
        if fig:
            fig.patch.set_facecolor(Theme.BACKGROUND_MID)

        targets = []
        if ax:
            targets.append(ax)
        if axes:
            targets.extend(axes)

        # If no explicit axes passed, try to get from figure (careful)
        if not targets and fig:
            targets = fig.axes

        for axis in targets:
            axis.set_facecolor(Theme.BACKGROUND_MID)
            axis.tick_params(colors=Theme.TEXT_MUTED)
            for spine in axis.spines.values():
                spine.set_color(Theme.BORDER)
            axis.xaxis.label.set_color(Theme.TEXT_MUTED)
            axis.yaxis.label.set_color(Theme.TEXT_MUTED)
            axis.title.set_color(Theme.TEXT_MUTED)

            # If legend exists
            if axis.legend_:
                legend = axis.legend_
                frame = legend.get_frame()
                frame.set_facecolor(Theme.BACKGROUND_MID)
                frame.set_edgecolor(Theme.TEXT_MUTED)
                for text in legend.get_texts():
                    text.set_color(Theme.TEXT_MUTED)

    @staticmethod
    def get_style_sheet() -> str:
        """Global Update for QWidget generic styles if needed."""
        return f"""
            QWidget {{
                background-color: {Theme.BACKGROUND_DARK};
                color: {Theme.TEXT_PRIMARY};
                font-family: 'Segoe UI', sans-serif;
            }}
            QScrollBar:vertical {{
                background: {Theme.BACKGROUND_DARK};
                width: 10px;
            }}
            QScrollBar::handle:vertical {{
                background: {Theme.BACKGROUND_LIGHT};
                border-radius: 5px;
            }}
        """
