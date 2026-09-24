from __future__ import annotations

from XBrainLab.ui.panels.visualization.saliency_views.base_saliency_view import (
    BaseSaliencyView,
)


def test_saliency_background_render_error_reaches_visible_sanitized_state(
    qtbot,
) -> None:
    view = BaseSaliencyView()
    qtbot.addWidget(view)
    view.resize(720, 480)
    view.show()

    def fail_render():
        raise RuntimeError("private saliency backend tuple")

    view._render_figure_async(fail_render, error_context="integration saliency")
    qtbot.waitUntil(
        lambda: "could not be rendered" in view.error_label.text(),
        timeout=3_000,
    )

    visible = view.error_label.text()
    assert visible == (
        "Error: Saliency could not be rendered. "
        "Try again or choose another saliency view."
    )
    assert "private saliency backend tuple" not in visible
    image = view.grab().toImage()
    assert not image.isNull()
    assert image.width() >= 720
    assert image.height() >= 480
