import pytest
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication, QLabel

from XBrainLab.ui.panels.preprocess.preview_widget import PreviewWidget
from XBrainLab.ui.styles.theme import Theme


@pytest.fixture
def preview_widget(qtbot):
    """Own PyQtGraph teardown explicitly across Linux, Windows, and macOS."""
    widget = PreviewWidget()
    yield widget
    widget.prepare_for_shutdown()
    QApplication.processEvents()
    widget.close()
    QApplication.processEvents()
    widget.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()


def test_preprocess_plot_axis_titles_use_readable_text_color(
    preview_widget,
) -> None:
    widget = preview_widget

    for plot in (widget.plot_time, widget.plot_freq):
        for axis_name in ("left", "bottom"):
            axis = plot.getAxis(axis_name)
            assert axis.labelStyle["color"] == Theme.TEXT_MUTED
            assert axis.textPen().color().name() == Theme.TEXT_MUTED


def test_preprocess_event_markers_use_one_compact_legend(
    qtbot,
    preview_widget,
) -> None:
    widget = preview_widget
    widget.show()
    widget._set_preview_interactive(True, state="loaded")

    assert widget.signal_legend.isVisibleTo(widget)
    assert widget.loaded_signal_legend_text.text() == "Raw signal"
    assert "baseline-aligned" in widget.loaded_signal_legend.toolTip()
    assert "unchanged" in widget.loaded_signal_legend.toolTip()
    assert widget.current_signal_legend_text.text() == "Preprocessed signal"
    assert widget.event_legend_text.text() == "Events"
    assert widget.excluded_legend_text.text() == "Excluded"
    assert widget.event_legend.isVisibleTo(widget)
    assert widget.excluded_legend.isVisibleTo(widget)

    events = [
        (0.1, "left"),
        (0.2, "left"),
        (0.3, "right"),
        (0.4, "BAD_artifact", 0.2),
        (0.7, "BAD_boundary", 0.1),
    ]
    widget.show_time_event_markers(events)
    qtbot.wait(0)

    assert widget.event_legend.isVisibleTo(widget)
    assert widget.event_legend_text.text() == "Events"
    assert "2 event types" in widget.event_legend.toolTip()
    assert "left" in widget.event_legend.toolTip()
    assert "right" in widget.event_legend.toolTip()
    assert widget.excluded_legend.isVisibleTo(widget)
    assert widget.excluded_legend_text.text() == "Excluded"
    assert "2 excluded segments" in widget.excluded_legend.toolTip()
    assert "BAD_artifact" in widget.excluded_legend.toolTip()
    assert "0.2 s" in widget.excluded_legend.toolTip()
    assert len(widget.findChildren(QLabel, "PreprocessEventLegendText")) == 1
    assert all(marker.toolTip() for marker in widget.time_event_markers[: len(events)])
    assert all(
        getattr(marker, "label", None) is None for marker in widget.time_event_markers
    )
    assert (
        widget.time_event_markers[0].pen.color().name()
        != widget.time_event_markers[3].pen.color().name()
    )
    assert widget.time_excluded_regions[0].isVisible()
    legend_y_positions = {
        legend.mapTo(widget.signal_legend, legend.rect().topLeft()).y()
        for legend in (
            widget.loaded_signal_legend,
            widget.current_signal_legend,
            widget.event_legend,
            widget.excluded_legend,
        )
    }
    assert len(legend_y_positions) == 1

    widget.clear_time_event_markers()

    assert widget.event_legend.isVisibleTo(widget)
    assert widget.excluded_legend.isVisibleTo(widget)
    assert widget.event_legend.toolTip() == ""
    assert widget.excluded_legend.toolTip() == ""
    assert widget.signal_legend.isVisibleTo(widget)


def test_preprocess_signal_legend_only_appears_for_loaded_preview(
    preview_widget,
) -> None:
    widget = preview_widget
    widget.show()

    assert not widget.signal_legend.isVisible()

    widget._set_preview_interactive(True, state="loaded")
    assert widget.signal_legend.isVisibleTo(widget)

    widget._set_preview_interactive(False, state="locked")
    assert not widget.signal_legend.isVisible()


def test_preprocess_signal_legend_fits_constrained_preview_width(
    qtbot,
    preview_widget,
) -> None:
    widget = preview_widget
    widget.resize(700, 620)
    widget.show()
    widget._set_preview_interactive(True, state="loaded")
    widget.show_time_event_markers(
        [
            (0.1, "left"),
            (0.4, "BAD_artifact", 0.2),
        ]
    )
    qtbot.wait(0)

    assert widget.signal_legend.isVisibleTo(widget)
    legend_bottom_right = widget.signal_legend.mapTo(
        widget.plot_content,
        widget.signal_legend.rect().bottomRight(),
    )
    assert legend_bottom_right.x() <= widget.plot_content.contentsRect().right()
    assert widget.legend_wrap_row.isVisibleTo(widget)
    for label in (
        widget.loaded_signal_legend_text,
        widget.current_signal_legend_text,
        widget.event_legend_text,
        widget.excluded_legend_text,
    ):
        assert label.isVisibleTo(widget)
        assert label.fontMetrics().horizontalAdvance(label.text()) <= label.width()


def test_preprocess_signal_legend_shares_the_control_row_when_space_allows(
    qtbot,
    preview_widget,
) -> None:
    widget = preview_widget
    control_width = sum(
        max(control.minimumSizeHint().width(), control.minimumWidth())
        for control in (
            widget.channel_label,
            widget.chan_combo,
            widget.yscale_label,
            widget.yscale_spin,
        )
    )
    spacing = max(widget.ctrl_layout.spacing(), 0)
    inline_width = control_width + widget.signal_legend.sizeHint().width() + 80
    inline_width += spacing * widget.ctrl_layout.count()
    widget.resize(max(1100, inline_width), 620)
    widget.show()
    widget._set_preview_interactive(True, state="loaded")
    qtbot.wait(0)

    available_width = max(
        widget.controls_legend_container.contentsRect().width(),
        widget.contentsRect().width() - 40,
    )
    required_width = (
        control_width + widget.signal_legend.sizeHint().width() + 40 + spacing * 4 + 12
    )
    wraps = widget.legend_wrap_row.isVisibleTo(widget)
    assert wraps is (available_width < required_width)
    if not wraps:
        control_center = widget.chan_combo.mapTo(
            widget.controls_legend_container,
            widget.chan_combo.rect().center(),
        ).y()
        legend_center = widget.signal_legend.mapTo(
            widget.controls_legend_container,
            widget.signal_legend.rect().center(),
        ).y()
        assert abs(control_center - legend_center) <= 2
    for label in (
        widget.loaded_signal_legend_text,
        widget.current_signal_legend_text,
        widget.event_legend_text,
        widget.excluded_legend_text,
    ):
        assert label.isVisibleTo(widget)
        assert label.fontMetrics().horizontalAdvance(label.text()) <= label.width()


def test_preprocess_psd_hides_time_only_event_legends(
    qtbot,
    preview_widget,
) -> None:
    widget = preview_widget
    widget.show()
    widget._set_preview_interactive(True, state="loaded")
    widget.show_time_event_markers(
        [
            (0.1, "left"),
            (0.4, "BAD_artifact", 0.2),
        ]
    )
    assert widget.event_legend.isVisibleTo(widget)
    assert widget.excluded_legend.isVisibleTo(widget)

    widget.plot_tabs.setCurrentIndex(1)
    qtbot.wait(0)

    assert not widget.event_legend.isVisibleTo(widget)
    assert not widget.excluded_legend.isVisibleTo(widget)
    assert widget.loaded_signal_legend_text.isVisibleTo(widget)
    assert widget.current_signal_legend_text.isVisibleTo(widget)


def test_preprocess_preview_resumes_after_cancelled_close(
    preview_widget,
) -> None:
    widget = preview_widget
    widget.show()
    original_time_proxy = widget.proxy_time
    original_freq_proxy = widget.proxy_freq
    widget.show_time_event_markers(
        [
            (0.1, "left", 0.0),
            (0.4, "BAD_artifact", 0.2),
        ]
    )
    event_marker = widget.time_event_markers[0]
    excluded_region = widget.time_excluded_regions[0]
    excluded_line = excluded_region.lines[0]

    widget.prepare_for_shutdown()

    assert widget._native_plot_shutdown is True
    assert original_time_proxy.slot is None
    assert original_freq_proxy.slot is None
    assert not widget.plot_time.updatesEnabled()
    assert not widget.plot_freq.updatesEnabled()
    assert widget.time_current_curve.scene() is None
    assert widget.v_line_time.scene() is None
    assert widget.v_line_freq.scene() is None
    assert widget.v_line_time.getViewBox() is None
    assert widget.v_line_freq.getViewBox() is None
    assert event_marker.scene() is None
    assert event_marker.getViewBox() is None
    assert excluded_region.scene() is None
    assert excluded_region.getViewBox() is None
    assert excluded_line.scene() is None
    assert excluded_line.getViewBox() is None

    widget.resume_after_cancelled_shutdown()

    assert widget._native_plot_shutdown is False
    assert widget.proxy_time is not original_time_proxy
    assert widget.proxy_freq is not original_freq_proxy
    assert widget.proxy_time.slot is not None
    assert widget.proxy_freq.slot is not None
    assert widget.plot_time.updatesEnabled()
    assert widget.plot_freq.updatesEnabled()
    assert widget.time_current_curve.scene() is widget.plot_time.scene()
    time_plot_item = widget.plot_time.getPlotItem()
    frequency_plot_item = widget.plot_freq.getPlotItem()
    assert time_plot_item is not None
    assert frequency_plot_item is not None
    assert widget.v_line_time.getViewBox() is time_plot_item.vb
    assert widget.v_line_freq.getViewBox() is frequency_plot_item.vb
    assert event_marker.getViewBox() is time_plot_item.vb
    assert excluded_region.getViewBox() is time_plot_item.vb
    assert excluded_line.getViewBox() is time_plot_item.vb

    widget._on_plot_param_changed()
    assert widget.plot_timer.isActive()

    widget.prepare_for_shutdown()
    assert widget._native_plot_shutdown is True
    assert not widget.plot_timer.isActive()
