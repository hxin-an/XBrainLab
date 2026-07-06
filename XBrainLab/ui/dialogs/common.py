"""Shared dialog helpers for consistent XBrainLab Qt dialogs."""

from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QPalette
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialogButtonBox,
    QPushButton,
    QTableWidget,
)

from XBrainLab.ui.styles.theme import Theme


def icon_path(name: str) -> str:
    """Return an absolute resource icon path usable from Qt stylesheets."""
    return (
        Path(__file__).resolve().parents[2] / "resources" / "icons" / name
    ).as_posix()


def normalize_dialog_button_box(
    button_box: QDialogButtonBox,
    *,
    ok_text: str = "OK",
    cancel_text: str = "Cancel",
) -> None:
    """Remove platform icons/default glyphs from OK/Cancel dialog buttons."""
    for standard_button, text in (
        (QDialogButtonBox.StandardButton.Ok, ok_text),
        (QDialogButtonBox.StandardButton.Cancel, cancel_text),
    ):
        button = button_box.button(standard_button)
        if isinstance(button, QPushButton):
            button.setText(text)
            button.setIcon(QIcon())
            button.setIconSize(QSize(0, 0))
            button.setAutoDefault(False)
            button.setDefault(False)


def configure_dark_table(
    table: QTableWidget,
    *,
    object_name: str | None = None,
    no_selection: bool = False,
    compact_rows: bool = True,
) -> None:
    """Apply the common dark table behavior and palette to a table widget."""
    if object_name:
        table.setObjectName(object_name)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setWordWrap(False)
    table.setStyleSheet(dark_table_stylesheet(object_name=object_name))
    if no_selection:
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    vertical_header = table.verticalHeader()
    if vertical_header is not None:
        vertical_header.setVisible(False)
        if compact_rows:
            vertical_header.setDefaultSectionSize(30)
            vertical_header.setMinimumSectionSize(28)
    header = table.horizontalHeader()
    if header is not None:
        header.setHighlightSections(False)
    palette = table.palette()
    for group in (
        QPalette.ColorGroup.Active,
        QPalette.ColorGroup.Inactive,
        QPalette.ColorGroup.Disabled,
    ):
        palette.setColor(group, QPalette.ColorRole.Base, QColor(Theme.METRICS_TABLE_BG))
        palette.setColor(
            group,
            QPalette.ColorRole.AlternateBase,
            QColor(Theme.METRICS_TABLE_ALT_BG),
        )
        palette.setColor(group, QPalette.ColorRole.Text, QColor(Theme.TEXT_PRIMARY))
        palette.setColor(
            group,
            QPalette.ColorRole.Highlight,
            QColor(Theme.METRICS_TABLE_SELECTION),
        )
        palette.setColor(
            group,
            QPalette.ColorRole.HighlightedText,
            QColor(Theme.TEXT_PRIMARY),
        )
    table.setPalette(palette)


def dark_dialog_stylesheet() -> str:
    """Common dark styling for compact setting dialogs."""
    return f"""
        QDialog {{
            background-color: {Theme.BACKGROUND_DARK};
            color: {Theme.TEXT_PRIMARY};
        }}
        QLabel, QGroupBox {{
            background-color: transparent;
            color: {Theme.TEXT_PRIMARY};
        }}
        QGroupBox {{
            border: 1px solid {Theme.BACKGROUND_LIGHT};
            border-radius: 6px;
            margin-top: 14px;
            padding-top: 8px;
            font-weight: 700;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
            color: {Theme.TEXT_PRIMARY};
        }}
        {form_control_stylesheet()}
        {button_stylesheet()}
        {checkbox_stylesheet()}
        QDialogButtonBox {{
            background-color: transparent;
        }}
    """


def form_control_stylesheet() -> str:
    """Common dark styling for line edits, combo boxes, and spin boxes."""
    chevron = icon_path("chevron-down.svg")
    return f"""
        QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
            background-color: {Theme.METRICS_TABLE_BG};
            color: {Theme.TEXT_PRIMARY};
            border: 1px solid {Theme.METRICS_TABLE_BORDER};
            border-radius: 4px;
            padding: 5px 8px;
            min-height: 24px;
        }}
        QComboBox {{
            padding-right: 28px;
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            border: none;
            background: transparent;
            width: 24px;
        }}
        QComboBox::down-arrow {{
            image: url("{chevron}");
            width: 10px;
            height: 10px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {Theme.METRICS_TABLE_BG};
            color: {Theme.TEXT_PRIMARY};
            border: 1px solid {Theme.METRICS_TABLE_BORDER};
            selection-background-color: {Theme.METRICS_TABLE_SELECTION};
            selection-color: {Theme.TEXT_PRIMARY};
        }}
    """


def button_stylesheet() -> str:
    """Common dark button style with subdued default-button treatment."""
    return f"""
        QPushButton {{
            background-color: {Theme.BACKGROUND_MID};
            color: {Theme.TEXT_PRIMARY};
            border: 1px solid {Theme.BACKGROUND_LIGHT};
            border-radius: 4px;
            padding: 6px 12px;
            min-height: 24px;
        }}
        QPushButton:hover {{
            background-color: {Theme.BACKGROUND_LIGHT};
        }}
        QPushButton:disabled {{
            background-color: {Theme.BTN_DISABLED_BG};
            color: {Theme.BTN_DISABLED_TEXT};
            border-color: {Theme.BTN_DISABLED_BORDER};
        }}
        QPushButton:default {{
            border-color: {Theme.BACKGROUND_LIGHT};
            background-color: {Theme.BACKGROUND_MID};
        }}
        QPushButton#PrimaryConfirmButton,
        QPushButton#EpochPrimaryButton {{
            background-color: {Theme.BLUE_PRIMARY};
            border-color: {Theme.BLUE_HOVER};
            color: {Theme.TEXT_PRIMARY};
            font-weight: 700;
        }}
        QPushButton#PrimaryConfirmButton:hover,
        QPushButton#EpochPrimaryButton:hover {{
            background-color: {Theme.BLUE_HOVER};
        }}
    """


def checkbox_stylesheet() -> str:
    """Checkboxes use a visible check mark instead of a filled blue block."""
    checkmark = icon_path("checkmark.svg")
    return f"""
        QCheckBox {{
            background-color: transparent;
            color: {Theme.TEXT_PRIMARY};
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            background-color: {Theme.METRICS_TABLE_BG};
            border: 1px solid {Theme.BACKGROUND_LIGHT};
            border-radius: 3px;
            width: 14px;
            height: 14px;
        }}
        QCheckBox::indicator:checked {{
            image: url("{checkmark}");
            background-color: {Theme.BLUE_PRESSED};
            border-color: {Theme.BLUE_HOVER};
        }}
        QTreeView::indicator,
        QListView::indicator,
        QTableView::indicator {{
            background-color: {Theme.METRICS_TABLE_BG};
            border: 1px solid {Theme.BACKGROUND_LIGHT};
            border-radius: 3px;
            width: 14px;
            height: 14px;
        }}
        QTreeView::indicator:checked,
        QListView::indicator:checked,
        QTableView::indicator:checked {{
            image: url("{checkmark}");
            background-color: {Theme.BLUE_PRESSED};
            border-color: {Theme.BLUE_HOVER};
        }}
    """


def dark_table_stylesheet(*, object_name: str | None = None) -> str:
    """Common low-contrast dark table style."""
    selector = f"QTableWidget#{object_name}" if object_name else "QTableWidget"
    return f"""
        {selector} {{
            background-color: {Theme.METRICS_TABLE_BG};
            alternate-background-color: {Theme.METRICS_TABLE_ALT_BG};
            color: {Theme.TEXT_PRIMARY};
            gridline-color: {Theme.METRICS_TABLE_GRID};
            border: 1px solid {Theme.METRICS_TABLE_BORDER};
            selection-background-color: {Theme.METRICS_TABLE_SELECTION};
            selection-color: {Theme.TEXT_PRIMARY};
        }}
        {selector}::item {{
            padding: 4px 8px;
            color: {Theme.TEXT_PRIMARY};
            border: none;
        }}
        {selector}::item:selected {{
            background-color: {Theme.METRICS_TABLE_SELECTION};
            color: {Theme.TEXT_PRIMARY};
        }}
        QHeaderView::section {{
            background-color: {Theme.BACKGROUND_MID};
            color: {Theme.TEXT_SECONDARY};
            border: none;
            border-bottom: 1px solid {Theme.METRICS_TABLE_GRID};
            padding: 5px 8px;
            font-weight: 700;
        }}
        QScrollBar:vertical {{
            border: none;
            background: {Theme.BACKGROUND_DARK};
            width: 10px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {Theme.SCROLLBAR_HANDLE};
            border-radius: 5px;
            min-height: 24px;
        }}
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {{
            height: 0;
            border: none;
            background: transparent;
        }}
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {{
            background: transparent;
        }}
    """
