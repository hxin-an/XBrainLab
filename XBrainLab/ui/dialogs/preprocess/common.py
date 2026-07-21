"""Shared lightweight sections for preprocessing setting dialogs."""

from __future__ import annotations

from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from XBrainLab.ui.core.base_dialog import BaseDialog

_DIALOG_MARGINS = (18, 12, 18, 12)
_DIALOG_SPACING = 12
_SECTION_SPACING = 6


def configure_preprocess_dialog_layout(layout: QVBoxLayout) -> None:
    """Apply compact, DPI-safe spacing shared by preprocessing dialogs."""
    layout.setContentsMargins(*_DIALOG_MARGINS)
    layout.setSpacing(_DIALOG_SPACING)


def fit_preprocess_dialog_to_content(
    dialog: BaseDialog,
    *,
    minimum_width: int,
) -> None:
    """Remove surplus vertical space while preserving a stable dialog width."""
    dialog.fit_to_content(minimum_width=minimum_width)


def create_preprocess_section(
    title: str,
    *,
    parent: QWidget | None = None,
) -> tuple[QFrame, QLabel, QVBoxLayout]:
    """Return an unframed titled section that remains readable at high DPI."""
    section = QFrame(parent)
    section.setObjectName("PreprocessSection")
    layout = QVBoxLayout(section)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(_SECTION_SPACING)
    title_label = QLabel(title, section)
    title_label.setObjectName("PreprocessSectionTitle")
    layout.addWidget(title_label)
    return section, title_label, layout
