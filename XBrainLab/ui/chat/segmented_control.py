"""Compact segmented control shared by assistant-facing settings."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QSizePolicy, QWidget

from .styles import SEGMENTED_CONTROL_STYLE


class AssistantSegmentedControl(QWidget):
    """Exclusive text choices with restrained active-state styling."""

    selection_changed = pyqtSignal(str)

    def __init__(
        self,
        options: Iterable[tuple[str, str]],
        *,
        descriptions: Mapping[str, str] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("AssistantSegmentedControl")
        self.setStyleSheet(SEGMENTED_CONTROL_STYLE)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._buttons: dict[str, QPushButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        entries = tuple(options)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        for index, (key, label) in enumerate(entries):
            button = QPushButton(label, self)
            button.setObjectName("AssistantSegment")
            button.setProperty(
                "segmentPosition",
                "only"
                if len(entries) == 1
                else "first"
                if index == 0
                else "last"
                if index == len(entries) - 1
                else "middle",
            )
            button.setCheckable(True)
            button.setAutoDefault(False)
            button.setDefault(False)
            button.setMinimumHeight(38)
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            description = str((descriptions or {}).get(key, ""))
            if description:
                button.setToolTip(description)
                button.setAccessibleDescription(description)
            button.setAccessibleName(label)
            button.clicked.connect(
                lambda _checked=False, selected=key: self._select_from_user(selected)
            )
            self._buttons[key] = button
            self._group.addButton(button)
            layout.addWidget(button, 1)

    def button(self, key: str) -> QPushButton:
        """Return one segment button by stable key."""
        return self._buttons[key]

    def selected_key(self) -> str | None:
        """Return the selected stable key, if any."""
        for key, button in self._buttons.items():
            if button.isChecked():
                return key
        return None

    def set_selected(self, key: str | None, *, emit: bool = False) -> None:
        """Select a segment without relying on translated button text."""
        if key is None:
            self._group.setExclusive(False)
            for button in self._buttons.values():
                button.setChecked(False)
            self._group.setExclusive(True)
            return
        if key not in self._buttons:
            raise KeyError(f"Unknown assistant segment: {key}")
        changed = self.selected_key() != key
        self._buttons[key].setChecked(True)
        if emit and changed:
            self.selection_changed.emit(key)

    def _select_from_user(self, key: str) -> None:
        self.set_selected(key)
        self.selection_changed.emit(key)
