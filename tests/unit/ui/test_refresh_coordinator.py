"""Navigation refresh does not own command or publication state."""

from types import SimpleNamespace

import pytest
from PyQt6 import sip
from PyQt6.QtWidgets import QWidget

from XBrainLab.ui.refresh_coordinator import refresh_after_navigation, refresh_panel


@pytest.mark.parametrize("index", range(5))
def test_navigation_refreshes_only_selected_panel(index):
    calls = []
    panels = [
        SimpleNamespace(update_panel=lambda i=i: calls.append(i)) for i in range(5)
    ]
    window = SimpleNamespace(
        **dict(
            zip(
                (
                    "dataset_panel",
                    "preprocess_panel",
                    "training_panel",
                    "evaluation_panel",
                    "visualization_panel",
                ),
                panels,
                strict=True,
            )
        ),
        update_info_panel=lambda: calls.append("unexpected status pull"),
    )
    assert refresh_after_navigation(window, index)
    assert calls == [index]


def test_navigation_is_not_reentrant():
    nested = []
    window = SimpleNamespace()
    window.training_panel = SimpleNamespace(
        update_panel=lambda: nested.append(refresh_after_navigation(window, 2))
    )
    assert refresh_after_navigation(window, 2)
    assert nested == [False]


@pytest.mark.parametrize("index", [-1, 5, 99])
def test_navigation_ignores_unknown_panel(index):
    assert not refresh_after_navigation(SimpleNamespace(), index)


def test_failed_render_releases_navigation_guard():
    def fail():
        raise RuntimeError("renderer failed")

    calls = []
    window = SimpleNamespace(training_panel=SimpleNamespace(update_panel=fail))
    assert not refresh_after_navigation(window, 2)
    window.training_panel.update_panel = lambda: calls.append("retried")
    assert refresh_after_navigation(window, 2)
    assert calls == ["retried"]


def test_missing_panel_does_not_render():
    assert not refresh_after_navigation(SimpleNamespace(), 0)
    assert not refresh_panel(None)


def test_deleted_native_widget_render_is_contained(qtbot):
    class Panel(QWidget):
        def update_panel(self):
            self.setEnabled(True)

    panel = Panel()
    panel.deleteLater()
    qtbot.waitUntil(lambda: sip.isdeleted(panel), timeout=1_000)
    assert not refresh_panel(panel)
