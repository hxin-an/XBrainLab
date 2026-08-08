"""Small presentation helpers for responsive Qt controls."""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QPaintEvent, QResizeEvent
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStyle,
    QStyleOptionComboBox,
    QStylePainter,
    QTableWidget,
    QVBoxLayout,
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

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        """Honor an explicit compact width because the closed text is elided."""
        hint = super().minimumSizeHint()
        explicit_minimum = self.minimumWidth()
        if explicit_minimum > 0:
            return QSize(explicit_minimum, hint.height())
        return hint

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

    def paintEvent(self, event: QPaintEvent | None) -> None:  # noqa: N802
        if self.isEditable():
            super().paintEvent(event)
            return
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        option.currentText = self.elided_current_text()
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)
        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, option)

    def resizeEvent(self, event: QResizeEvent | None) -> None:  # noqa: N802
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
        greedy_wrap: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._fields = [(self._make_label(text), widget) for text, widget in fields]
        self._trailing_widgets = list(trailing_widgets)
        self._wrap_width = wrap_width
        self._greedy_wrap = greedy_wrap
        self._wrapped: bool | None = None
        self._layout_mode: str | None = None
        self._greedy_rows: list[QWidget] = []
        self._greedy_reflowing = False
        self._settled_reflow_pending = False
        self._horizontal_spacing = 10
        self._layout = QVBoxLayout(self) if greedy_wrap else QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 8)
        if isinstance(self._layout, QGridLayout):
            self._layout.setHorizontalSpacing(self._horizontal_spacing)
            self._layout.setVerticalSpacing(8)
        else:
            self._layout.setSpacing(8)
        # Start from the smallest valid geometry. QWidget's constructor width
        # is a desktop-sized placeholder; building the wide row first lets its
        # layout minimum prevent a narrow parent from ever reaching the stacked
        # breakpoint.
        self._apply_layout(0)

    def is_wrapped(self) -> bool:
        """Return whether controls currently use the compact two-row layout."""
        return bool(self._wrapped)

    def refresh_layout(self) -> None:
        """Reflow after a child changes its preferred presentation width."""
        self._layout_mode = None
        self._apply_layout(self.width())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        """Allow the parent to cross the wrap threshold before reflow occurs."""
        hint = super().minimumSizeHint()
        compact_width = min(240, max(self._wrap_width - 1, 1))
        return QSize(min(hint.width(), compact_width), hint.height())

    def resizeEvent(self, event: QResizeEvent | None) -> None:  # noqa: N802
        super().resizeEvent(event)
        width = event.size().width() if event is not None else self.width()
        self._apply_layout(width)
        if self._greedy_wrap and not self._settled_reflow_pending:
            self._settled_reflow_pending = True
            QTimer.singleShot(0, self._refresh_settled_layout)

    def _refresh_settled_layout(self) -> None:
        self._settled_reflow_pending = False
        self.refresh_layout()

    @staticmethod
    def _make_label(text: str) -> QLabel:
        label = QLabel(f"{text}:")
        label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        return label

    def _apply_layout(self, width: int) -> None:
        if self._greedy_wrap:
            self._apply_greedy_layout(width)
            return
        layout = self._layout
        if not isinstance(layout, QGridLayout):
            raise TypeError("Non-greedy controls require a grid layout")
        wrapped = width < self._wrap_width
        stacked_trailing = wrapped and width < 360 and bool(self._trailing_widgets)
        layout_mode = "stacked" if stacked_trailing else "wrapped" if wrapped else "row"
        if self._layout_mode == layout_mode:
            return
        self._layout_mode = layout_mode
        self._wrapped = wrapped
        widgets = [widget for pair in self._fields for widget in pair]
        widgets.extend(self._trailing_widgets)
        for widget in widgets:
            layout.removeWidget(widget)
        for column in range((len(self._fields) * 2) + len(self._trailing_widgets) + 1):
            layout.setColumnStretch(column, 0)

        if wrapped:
            last_row = len(self._fields) - 1
            trailing_span = max(len(self._trailing_widgets), 1)
            for row, (label, control) in enumerate(self._fields):
                layout.addWidget(label, row, 0)
                span = trailing_span + 1 if row < last_row or stacked_trailing else 1
                layout.addWidget(control, row, 1, 1, span)
            if stacked_trailing:
                trailing_row = len(self._fields)
                for offset, widget in enumerate(self._trailing_widgets):
                    layout.addWidget(
                        widget,
                        trailing_row + offset,
                        0,
                        1,
                        trailing_span + 2,
                        alignment=Qt.AlignmentFlag.AlignLeft
                        | Qt.AlignmentFlag.AlignVCenter,
                    )
            else:
                for column, widget in enumerate(self._trailing_widgets, start=2):
                    layout.addWidget(
                        widget,
                        last_row,
                        column,
                        alignment=Qt.AlignmentFlag.AlignLeft
                        | Qt.AlignmentFlag.AlignVCenter,
                    )
            layout.setColumnStretch(1, 1)
            layout.invalidate()
            self.updateGeometry()
            return

        column = 0
        for label, control in self._fields:
            layout.addWidget(label, 0, column)
            layout.addWidget(control, 0, column + 1)
            layout.setColumnStretch(column + 1, 1)
            column += 2
        for widget in self._trailing_widgets:
            layout.addWidget(
                widget,
                0,
                column,
                alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            )
            column += 1
        layout.setColumnStretch(column, 1)
        layout.invalidate()
        self.updateGeometry()

    def _apply_greedy_layout(self, width: int) -> None:
        if self._greedy_reflowing:
            return
        self._greedy_reflowing = True
        try:
            self._apply_greedy_layout_now(width)
        finally:
            self._greedy_reflowing = False

    def _apply_greedy_layout_now(self, width: int) -> None:
        """Pack atomic label/control groups without clipping at narrow widths."""
        units: list[tuple[tuple[QWidget, ...], int]] = []
        spacing = self._horizontal_spacing
        for label, control in self._fields:
            # Packing is based on the usable compressed width. Preferred widths
            # may contain a long current selection and would trigger wrapping
            # even though ElidingComboBox can render it safely.
            control_width = max(control.minimumWidth(), 1)
            units.append(
                ((label, control), label.sizeHint().width() + spacing + control_width)
            )
        units.extend(
            ((widget,), widget.sizeHint().width()) for widget in self._trailing_widgets
        )
        available = max(
            width
            - self._layout.contentsMargins().left()
            - self._layout.contentsMargins().right(),
            1,
        )
        rows: list[list[tuple[QWidget, ...]]] = [[]]
        row_width = 0
        for widgets, unit_width in units:
            candidate = unit_width if not rows[-1] else row_width + spacing + unit_width
            if rows[-1] and candidate > available:
                rows.append([])
                row_width = 0
            rows[-1].append(widgets)
            row_width = (
                unit_width if row_width == 0 else row_width + spacing + unit_width
            )

        layout_mode = "greedy:" + ",".join(str(len(row)) for row in rows)
        if self._layout_mode == layout_mode:
            return
        self._layout_mode = layout_mode
        self._wrapped = len(rows) > 1
        if not isinstance(self._layout, QVBoxLayout):
            raise TypeError("Greedy controls require a vertical row layout")
        product_widgets = [item for pair in self._fields for item in pair]
        product_widgets.extend(self._trailing_widgets)
        for row_widget in self._greedy_rows:
            row_layout = row_widget.layout()
            if row_layout is not None:
                for widget in product_widgets:
                    row_layout.removeWidget(widget)
            self._layout.removeWidget(row_widget)
            row_widget.deleteLater()
        for widget in product_widgets:
            widget.setParent(self)
        self._greedy_rows = []

        for row in rows:
            row_widget = QWidget(self)
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(spacing)
            for widgets in row:
                for widget in widgets:
                    row_layout.addWidget(
                        widget,
                        alignment=Qt.AlignmentFlag.AlignLeft
                        | Qt.AlignmentFlag.AlignVCenter,
                    )
            row_layout.addStretch(1)
            self._layout.addWidget(row_widget)
            row_widget.show()
            self._greedy_rows.append(row_widget)
        self._layout.invalidate()
        self.updateGeometry()


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
