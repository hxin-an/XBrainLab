"""Small presentation helpers for responsive Qt controls."""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QPaintEvent, QResizeEvent
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QComboBox,
    QGridLayout,
    QLabel,
    QSizePolicy,
    QStyle,
    QStyleOptionComboBox,
    QStylePainter,
    QTableWidget,
    QWidget,
)


class ElidingComboBox(QComboBox):
    """Combo box that elides its closed selection and exposes the full tooltip."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._elide_mode = Qt.TextElideMode.ElideRight
        self.currentTextChanged.connect(self._sync_selection_tooltip)

    def elideMode(self) -> Qt.TextElideMode:  # noqa: N802
        """Return the elision mode used for the closed combo selection."""
        return self._elide_mode

    def elided_current_text(self) -> str:
        """Return the selection text as it is painted at the current width."""
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        style = self.style()
        if style is None:
            return self.currentText()
        text_rect = style.subControlRect(
            QStyle.ComplexControl.CC_ComboBox,
            option,
            QStyle.SubControl.SC_ComboBoxEditField,
            self,
        )
        return self.fontMetrics().elidedText(
            self.currentText(),
            self._elide_mode,
            max(text_rect.width() - 4, 0),
        )

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        if self.isEditable():
            super().paintEvent(event)
            return
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        option.currentText = self.elided_current_text()
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)
        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, option)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_selection_tooltip(self.currentText())

    def showPopup(self) -> None:  # noqa: N802
        for index in range(self.count()):
            self.setItemData(index, self.itemText(index), Qt.ItemDataRole.ToolTipRole)
        super().showPopup()

    def _sync_selection_tooltip(self, text: str) -> None:
        if text:
            self.setToolTip(text)


class ResponsiveControlsBar(QWidget):
    """Lay out labeled controls in one row, wrapping them when space is tight."""

    def __init__(
        self,
        fields: Sequence[tuple[str, QWidget]],
        trailing_widgets: Sequence[QWidget] = (),
        *,
        wrap_width: int = 500,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._fields = [(self._make_label(text), widget) for text, widget in fields]
        self._trailing_widgets = list(trailing_widgets)
        self._wrap_width = wrap_width
        self._wrapped: bool | None = None
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 8)
        self._layout.setHorizontalSpacing(10)
        self._layout.setVerticalSpacing(8)
        self._apply_layout(self.width() < self._wrap_width)

    def is_wrapped(self) -> bool:
        """Return whether controls currently use the compact two-row layout."""
        return bool(self._wrapped)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        """Allow the parent to cross the wrap threshold before reflow occurs."""
        hint = super().minimumSizeHint()
        return QSize(min(hint.width(), self._wrap_width - 1), hint.height())

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_layout(event.size().width() < self._wrap_width)

    @staticmethod
    def _make_label(text: str) -> QLabel:
        label = QLabel(f"{text}:")
        label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        return label

    def _apply_layout(self, wrapped: bool) -> None:
        if self._wrapped is wrapped:
            return
        self._wrapped = wrapped
        widgets = [widget for pair in self._fields for widget in pair]
        widgets.extend(self._trailing_widgets)
        for widget in widgets:
            self._layout.removeWidget(widget)
        for column in range((len(self._fields) * 2) + len(self._trailing_widgets) + 1):
            self._layout.setColumnStretch(column, 0)

        if wrapped:
            last_row = len(self._fields) - 1
            trailing_span = max(len(self._trailing_widgets), 1)
            for row, (label, control) in enumerate(self._fields):
                self._layout.addWidget(label, row, 0)
                span = trailing_span + 1 if row < last_row else 1
                self._layout.addWidget(control, row, 1, 1, span)
            for column, widget in enumerate(self._trailing_widgets, start=2):
                self._layout.addWidget(
                    widget,
                    last_row,
                    column,
                    alignment=Qt.AlignmentFlag.AlignLeft
                    | Qt.AlignmentFlag.AlignVCenter,
                )
            self._layout.setColumnStretch(1, 1)
            return

        column = 0
        for label, control in self._fields:
            self._layout.addWidget(label, 0, column)
            self._layout.addWidget(control, 0, column + 1)
            self._layout.setColumnStretch(column + 1, 1)
            column += 2
        for widget in self._trailing_widgets:
            self._layout.addWidget(
                widget,
                0,
                column,
                alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            )
            column += 1
        self._layout.setColumnStretch(column, 1)


def fit_table_to_all_rows(table: QTableWidget, *, minimum_height: int = 116) -> int:
    """Fit a table to every row so its containing surface owns vertical scrolling."""
    table.resizeRowsToContents()
    header = table.horizontalHeader()
    header_height = header.sizeHint().height() if header is not None else 28
    row_height = sum(table.rowHeight(row) for row in range(table.rowCount()))
    target_height = max(
        minimum_height,
        header_height + row_height + (table.frameWidth() * 2) + 4,
    )
    table.setFixedHeight(target_height)
    table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    table.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    return target_height
