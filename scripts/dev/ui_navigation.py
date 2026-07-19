"""Deterministic workflow-panel navigation for UI evidence scripts."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QCoreApplication, QEventLoop, QTimer


def open_workflow_panel(
    window: Any,
    index: int,
    *,
    timeout_ms: int = 10_000,
) -> Any:
    """Open one lazy workflow panel and wait for GUI-thread materialization."""
    if QCoreApplication.instance() is None:
        raise RuntimeError("A Qt application is required to open workflow panels.")
    ready_panels: list[Any] = []
    loop = QEventLoop()

    def _on_ready(panel: Any) -> None:
        if ready_panels:
            return
        ready_panels.append(panel)
        if loop.isRunning():
            loop.quit()

    materialized = window.switch_page(index, on_ready=_on_ready)
    if materialized is not False and ready_panels:
        return ready_panels[0]

    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(max(1, int(timeout_ms)))
    loop.exec()
    timer.stop()

    if not ready_panels:
        raise TimeoutError(
            f"Workflow panel {index} did not finish opening within {timeout_ms} ms."
        )
    return ready_panels[0]
