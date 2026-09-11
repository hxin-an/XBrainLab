"""Guarded refresh of the workflow panel selected by navigation."""

from __future__ import annotations

from typing import Any

from XBrainLab.backend.utils.logger import logger

_REFRESHING_MAIN_WINDOWS: set[int] = set()
_PANEL_NAMES_BY_INDEX = (
    "dataset_panel",
    "preprocess_panel",
    "training_panel",
    "evaluation_panel",
    "visualization_panel",
)


def refresh_after_navigation(main_window: Any, index: int) -> bool:
    """Refresh the visible workflow panel selected by top-level navigation."""
    if index < 0 or index >= len(_PANEL_NAMES_BY_INDEX):
        return False

    main_window_id = id(main_window)
    if main_window_id in _REFRESHING_MAIN_WINDOWS:
        return False

    _REFRESHING_MAIN_WINDOWS.add(main_window_id)
    try:
        panel = getattr(main_window, _PANEL_NAMES_BY_INDEX[index], None)
        return refresh_panel(panel)
    finally:
        _REFRESHING_MAIN_WINDOWS.discard(main_window_id)


def refresh_panel(panel: Any) -> bool:
    """Refresh one workflow panel through the shared safe call boundary."""
    method = getattr(panel, "update_panel", None)
    if not callable(method):
        return False
    try:
        method()
    except Exception:
        logger.debug("UI refresh failed for %s.update_panel", panel, exc_info=True)
        return False
    return True
