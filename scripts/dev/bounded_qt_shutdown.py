"""Bounded Qt shutdown used by native assistant walkthroughs."""

from __future__ import annotations

from collections.abc import Callable, MutableMapping
from contextlib import suppress
from typing import Any


class BoundedQtShutdown:
    """Keep the event loop alive until the window and assistant both close."""

    def __init__(
        self,
        *,
        app: Any,
        window: Any,
        manager_provider: Callable[[], Any | None],
        state: MutableMapping[str, Any],
        schedule: Callable[[int, Callable[[], None]], None],
        now: Callable[[], float],
        poll_interval_ms: int = 250,
        grace_seconds: float = 20.0,
    ) -> None:
        self._app = app
        self._window = window
        self._manager_provider = manager_provider
        self._state = state
        self._schedule = schedule
        self._now = now
        self._poll_interval_ms = poll_interval_ms
        self._grace_seconds = grace_seconds
        self._deadline = 0.0
        self._app.setQuitOnLastWindowClosed(False)

    def start(self) -> None:
        """Begin product close and retain Qt ownership while cleanup runs."""
        status = (self._state.get("shutdown") or {}).get("status")
        if status in {"closing", "completed", "timed_out", "interrupted"}:
            return
        self._state["shutdown"] = {"status": "closing", "detail": ""}
        self._deadline = self._now() + self._grace_seconds
        self._window.close()
        self._schedule(self._poll_interval_ms, self._poll)

    def reconcile_after_event_loop(self) -> None:
        """Fail closed if Qt exited before both native owners were terminal."""
        if (self._state.get("shutdown") or {}).get("status") != "closing":
            return
        detail = "Qt event loop exited before assistant shutdown was observable."
        self._state["shutdown"] = {"status": "interrupted", "detail": detail}
        self._mark_failed(detail)

    def _poll(self) -> None:
        manager = self._manager_provider()
        try:
            window_visible = bool(self._window.isVisible())
            lifecycle_state = (
                manager.assistant_runtime.state.value
                if manager is not None
                else "closed"
            )
        except RuntimeError:
            window_visible = False
            lifecycle_state = "closed"

        if not window_visible and lifecycle_state == "closed":
            self._state["shutdown"] = {"status": "completed", "detail": ""}
            self._app.quit()
            return
        if self._now() >= self._deadline:
            detail = (
                "Assistant or window shutdown exceeded "
                f"{self._grace_seconds:.0f} seconds."
            )
            self._state["shutdown"] = {"status": "timed_out", "detail": detail}
            self._mark_failed(detail)
            if manager is not None:
                with suppress(RuntimeError):
                    manager.close()
            self._app.quit()
            return
        self._window.close()
        self._schedule(self._poll_interval_ms, self._poll)

    def _mark_failed(self, detail: str) -> None:
        prior = str(self._state.get("failure_reason") or "").strip()
        self._state["status"] = "failed"
        self._state["failure_reason"] = f"{prior} {detail}".strip()
