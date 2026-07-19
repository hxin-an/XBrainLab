"""Shared Qt lifecycle assertions for integration tests."""

from __future__ import annotations

from typing import Any


def close_controller_and_wait(
    controller: Any,
    qtbot: Any,
    *,
    timeout_ms: int = 2_000,
) -> None:
    """Await one typed terminal when controller shutdown is asynchronous."""
    terminals: list[tuple[bool, str]] = []
    controller.shutdown_finished.connect(
        lambda ok, message: terminals.append((bool(ok), str(message or "")))
    )
    closed = bool(controller.close())
    if not closed:
        qtbot.waitUntil(lambda: bool(terminals), timeout=timeout_ms)
    assert controller.close() is True
    assert not terminals or terminals == [(True, "")]
