"""Small helpers for non-modal product status messages."""

from __future__ import annotations

from typing import Any

DEFAULT_STATUS_TIMEOUT_MS = 7000


def show_status_message(
    owner: Any,
    message: str,
    timeout_ms: int = DEFAULT_STATUS_TIMEOUT_MS,
) -> bool:
    """Show a transient message on the nearest main-window status bar.

    Returns ``True`` when a status bar accepted the message. Callers can use
    this to fall back to an in-panel label in standalone/legacy dialogs.
    """
    for candidate in _status_owner_candidates(owner):
        status_bar = _status_bar(candidate)
        show_message = getattr(status_bar, "showMessage", None)
        if not callable(show_message):
            continue
        try:
            show_message(message, timeout_ms)
        except TypeError:
            show_message(message)
        return True
    return False


def _status_owner_candidates(owner: Any):
    seen: set[int] = set()
    for candidate in (
        getattr(owner, "main_window", None),
        owner,
        getattr(owner, "parent", lambda: None)(),
        getattr(owner, "window", lambda: None)(),
    ):
        if candidate is None:
            continue
        marker = id(candidate)
        if marker in seen:
            continue
        seen.add(marker)
        yield candidate


def _status_bar(candidate: Any) -> Any:
    status_bar = getattr(candidate, "statusBar", None)
    if not callable(status_bar):
        return None
    try:
        return status_bar()
    except RuntimeError:
        return None
