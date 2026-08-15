from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QDialogButtonBox, QPushButton, QScrollArea

from XBrainLab.backend.application.epoch_context import (
    EpochContextAvailability,
    EpochWindowMode,
)
from XBrainLab.ui.dialogs.preprocess.epoching_dialog import EpochingDialog


class _ScreenStub:
    def __init__(self, available: QRect) -> None:
        self._available = QRect(available)

    def availableGeometry(self) -> QRect:
        return QRect(self._available)

    def geometry(self) -> QRect:
        return QRect(self._available)


class _ScreenBoundEpochingDialog(EpochingDialog):
    def __init__(self, *args, available_geometry: QRect, **kwargs) -> None:
        self._screen_stub = _ScreenStub(available_geometry)
        super().__init__(*args, **kwargs)

    def screen(self):
        return self._screen_stub


def _epoch_context(
    event_count: int,
    *,
    confirmation_required: bool = False,
    window_warning: str = "",
) -> dict[str, object]:
    context: dict[str, object] = {
        "available_events": [
            {"name": f"event_{index:02d}", "count": 20} for index in range(event_count)
        ],
        "recommended_events": ["event_00", "event_01"],
        "suggested_t_min": -0.2,
        "suggested_t_max": 1.0,
        "suggested_baseline": (-0.2, 0.0),
        "has_import_hint": True,
        "source": "labels inside EEG files",
        "placement_method": "internal_events",
        "placement_label": "Events inside EEG files",
        "window_mode": "event_locked",
        "window_evidence": "Suggested from the import label matching step.",
        "window_warning": window_warning,
        "context_availability": EpochContextAvailability.ready(
            window_mode=EpochWindowMode.EVENT_LOCKED,
            window_explanation="Use one fixed event-locked window.",
        ).to_payload(),
    }
    if confirmation_required:
        context.update(
            {
                "confirmation_context_fingerprint": "epoch-layout-test",
                "window_confirmation_message": (
                    "The reviewed BIDS durations vary substantially."
                ),
            }
        )
    return context


def _content_scroll(dialog: EpochingDialog) -> QScrollArea:
    scroll = dialog.findChild(QScrollArea, "EpochDialogContentScroll")
    assert scroll is not None
    return scroll


def _footer(dialog: EpochingDialog) -> QDialogButtonBox:
    footer = dialog.findChild(QDialogButtonBox)
    assert footer is not None
    return footer


def _assert_footer_is_fixed_and_visible(dialog: EpochingDialog) -> None:
    scroll = _content_scroll(dialog)
    footer = _footer(dialog)
    footer_rect = QRect(footer.mapTo(dialog, QPoint(0, 0)), footer.size())
    scroll_rect = QRect(scroll.mapTo(dialog, QPoint(0, 0)), scroll.size())

    assert footer.isVisibleTo(dialog)
    assert dialog.contentsRect().contains(footer_rect)
    assert footer_rect.top() > scroll_rect.top()


def test_epoching_primary_action_uses_short_confirm_copy_at_larger_font(qapp, qtbot):
    original_font = QFont(qapp.font())
    larger_font = QFont(original_font)
    larger_font.setPointSizeF(max(original_font.pointSizeF() + 2.0, 11.0))
    qapp.setFont(larger_font)
    dialog = None
    try:
        dialog = _ScreenBoundEpochingDialog(
            None,
            epoch_context=_epoch_context(7),
            available_geometry=QRect(0, 0, 800, 620),
        )
        qtbot.addWidget(dialog)
        dialog.show()
        qtbot.wait(0)

        button = dialog.findChild(QPushButton, "EpochPrimaryButton")
        assert button is not None
        assert button.text() == "Confirm"
        assert button.fontMetrics().horizontalAdvance(button.text()) <= (
            button.contentsRect().width()
        )
        _assert_footer_is_fixed_and_visible(dialog)
    finally:
        if dialog is not None:
            dialog.close()
            dialog.deleteLater()
            qapp.processEvents()
        qapp.setFont(original_font)


def test_epoching_expands_seven_event_content_before_first_frame_when_space_allows(
    qtbot,
):
    dialog = _ScreenBoundEpochingDialog(
        None,
        epoch_context=_epoch_context(7),
        available_geometry=QRect(0, 0, 1600, 1200),
    )
    qtbot.addWidget(dialog)
    scroll = _content_scroll(dialog)

    pre_show_size = QSize(dialog.size())
    assert pre_show_size.height() > 740

    dialog.show()
    first_visible_size = QSize(dialog.size())
    qtbot.wait(50)

    assert dialog.size() == pre_show_size == first_visible_size
    assert scroll.verticalScrollBar().maximum() == 0
    assert dialog.baseline_group is not None
    assert dialog.baseline_group.isVisibleTo(dialog)
    _assert_footer_is_fixed_and_visible(dialog)


def test_epoching_grows_for_larger_font_warning_and_never_shrinks(qapp, qtbot):
    original_font = QFont(qapp.font())
    larger_font = QFont(original_font)
    larger_font.setPointSizeF(max(original_font.pointSizeF() + 1.0, 10.0))
    qapp.setFont(larger_font)
    dialog = None
    try:
        dialog = _ScreenBoundEpochingDialog(
            None,
            epoch_context=_epoch_context(4),
            available_geometry=QRect(0, 0, 1600, 1200),
        )
        qtbot.addWidget(dialog)
        dialog.show()
        qtbot.wait(0)
        before_warning = dialog.height()

        assert dialog.tmax_spin is not None
        assert dialog.warning_label is not None
        dialog.tmax_spin.setValue(0.5)
        height_with_warning = dialog.height()

        assert dialog.warning_label.isVisibleTo(dialog)
        assert height_with_warning > before_warning
        assert _content_scroll(dialog).verticalScrollBar().maximum() == 0

        dialog.tmax_spin.setValue(1.0)

        assert not dialog.warning_label.isVisibleTo(dialog)
        assert dialog.height() == height_with_warning
        assert _content_scroll(dialog).verticalScrollBar().maximum() == 0
    finally:
        if dialog is not None:
            dialog.close()
            dialog.deleteLater()
            qapp.processEvents()
        qapp.setFont(original_font)


def test_epoching_grows_for_baseline_error_and_never_shrinks(qtbot):
    dialog = _ScreenBoundEpochingDialog(
        None,
        epoch_context=_epoch_context(6),
        available_geometry=QRect(0, 0, 1600, 1200),
    )
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(0)
    before_error = dialog.height()

    assert dialog.b_min_spin is not None
    assert dialog.baseline_error_label is not None
    dialog.b_min_spin.setValue(0.5)
    height_with_error = dialog.height()

    assert dialog.baseline_error_label.isVisibleTo(dialog)
    assert height_with_error > before_error
    assert _content_scroll(dialog).verticalScrollBar().maximum() == 0

    dialog.b_min_spin.setValue(-0.2)

    assert not dialog.baseline_error_label.isVisibleTo(dialog)
    assert dialog.height() == height_with_error
    assert _content_scroll(dialog).verticalScrollBar().maximum() == 0


def test_epoching_initial_confirmation_uses_available_height(qtbot):
    dialog = _ScreenBoundEpochingDialog(
        None,
        epoch_context=_epoch_context(6, confirmation_required=True),
        available_geometry=QRect(0, 0, 1600, 1200),
    )
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(0)

    assert dialog.confirmation_check is not None
    assert dialog.confirmation_check.isVisibleTo(dialog)
    assert dialog.height() > 740
    assert _content_scroll(dialog).verticalScrollBar().maximum() == 0
    _assert_footer_is_fixed_and_visible(dialog)


def test_epoching_caps_to_short_screen_and_keeps_one_scroll_owner(qtbot):
    available = QRect(0, 0, 800, 620)
    dialog = _ScreenBoundEpochingDialog(
        None,
        epoch_context=_epoch_context(16),
        available_geometry=available,
    )
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(0)

    scroll = _content_scroll(dialog)
    event_list = dialog.event_list
    assert event_list is not None

    assert dialog.height() == available.height() - 48
    assert scroll.verticalScrollBar().maximum() > 0
    assert scroll.horizontalScrollBar().maximum() == 0
    assert event_list.verticalScrollBar().maximum() == 0
    _assert_footer_is_fixed_and_visible(dialog)


def test_epoching_content_owns_vertical_scroll_above_fixed_footer(qtbot):
    dialog = EpochingDialog(
        None,
        epoch_context=_epoch_context(16),
    )
    qtbot.addWidget(dialog)
    dialog.resize(620, 420)
    dialog.show()
    qtbot.wait(0)

    scroll = _content_scroll(dialog)
    event_list = dialog.event_list
    footer = _footer(dialog)
    assert event_list is not None
    event_scrollbar = event_list.verticalScrollBar()
    content_scrollbar = scroll.verticalScrollBar()
    last_event = event_list.item(15, 1)
    assert event_scrollbar is not None
    assert content_scrollbar is not None
    assert last_event is not None

    assert scroll.widgetResizable()
    assert scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert event_list.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert event_scrollbar.maximum() == 0
    assert last_event.text() == "event_15"
    assert content_scrollbar.maximum() > 0
    assert footer.isVisibleTo(dialog)

    footer_y = footer.mapTo(dialog, footer.rect().topLeft()).y()
    content_scrollbar.setValue(content_scrollbar.maximum())
    qtbot.wait(0)

    assert footer.mapTo(dialog, footer.rect().topLeft()).y() == footer_y
