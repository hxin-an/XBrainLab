"""Shared lightweight sections for preprocessing setting dialogs."""

from __future__ import annotations

from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


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
    layout.setSpacing(8)
    title_label = QLabel(title, section)
    title_label.setObjectName("PreprocessSectionTitle")
    layout.addWidget(title_label)
    return section, title_label, layout
