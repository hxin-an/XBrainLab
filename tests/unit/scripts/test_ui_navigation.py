"""Tests for lazy workflow navigation used by UI evidence scripts."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QTimer

from scripts.dev.ui_navigation import open_workflow_panel


def test_open_workflow_panel_returns_an_already_materialized_panel(qapp) -> None:
    del qapp
    panel = object()

    def switch_page(_index: int, *, on_ready):
        on_ready(panel)
        return True

    window = SimpleNamespace(switch_page=switch_page)

    assert open_workflow_panel(window, 2, timeout_ms=50) is panel


def test_open_workflow_panel_waits_for_lazy_materialization(qapp) -> None:
    del qapp
    panel = object()

    def switch_page(_index: int, *, on_ready):
        QTimer.singleShot(0, lambda: on_ready(panel))
        return False

    window = SimpleNamespace(switch_page=switch_page)

    assert open_workflow_panel(window, 4, timeout_ms=100) is panel


def test_open_workflow_panel_times_out_without_a_ready_callback(qapp) -> None:
    del qapp
    window = SimpleNamespace(
        switch_page=lambda _index, *, on_ready: False,
    )

    with pytest.raises(TimeoutError, match="panel 1"):
        open_workflow_panel(window, 1, timeout_ms=1)
