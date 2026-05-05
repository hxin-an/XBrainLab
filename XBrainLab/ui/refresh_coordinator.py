"""Command-result-driven UI refresh coordination."""

from __future__ import annotations

from typing import Any

from XBrainLab.backend.application import ChangedState, CommandResult
from XBrainLab.backend.utils.logger import logger

_REFRESHING_MAIN_WINDOWS: set[int] = set()
_PANEL_NAMES_BY_INDEX = (
    "dataset_panel",
    "preprocess_panel",
    "training_panel",
    "evaluation_panel",
    "visualization_panel",
)


def refresh_after_command(context: Any, result: CommandResult | None) -> bool:
    """Refresh UI surfaces affected by an ApplicationService command result."""
    if result is None or not result.changed_state.any_changed():
        return False

    main_window = find_main_window(context)
    if main_window is None:
        return False

    main_window_id = id(main_window)
    if main_window_id in _REFRESHING_MAIN_WINDOWS:
        return False

    _REFRESHING_MAIN_WINDOWS.add(main_window_id)
    try:
        refreshed = False
        for panel_name in _panel_names_for(result.changed_state):
            panel = getattr(main_window, panel_name, None)
            refreshed = refresh_panel(panel) or refreshed

        return _refresh_shared_status(main_window) or refreshed
    finally:
        _REFRESHING_MAIN_WINDOWS.discard(main_window_id)


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
        refreshed = refresh_panel(panel)
        return _refresh_shared_status(main_window) or refreshed
    finally:
        _REFRESHING_MAIN_WINDOWS.discard(main_window_id)


def refresh_after_observer(context: Any) -> bool:
    """Refresh one observer source panel plus shared status surfaces."""
    main_window = find_main_window(context)
    if main_window is None:
        return refresh_panel(context)

    main_window_id = id(main_window)
    if main_window_id in _REFRESHING_MAIN_WINDOWS:
        return False

    _REFRESHING_MAIN_WINDOWS.add(main_window_id)
    try:
        refreshed = refresh_panel(context)
        return _refresh_shared_status(main_window) or refreshed
    finally:
        _REFRESHING_MAIN_WINDOWS.discard(main_window_id)


def refresh_shared_status(context: Any) -> bool:
    """Refresh shared status surfaces without refreshing a workflow panel."""
    main_window = find_main_window(context)
    if main_window is None:
        return False

    main_window_id = id(main_window)
    if main_window_id in _REFRESHING_MAIN_WINDOWS:
        return False

    _REFRESHING_MAIN_WINDOWS.add(main_window_id)
    try:
        return _refresh_shared_status(main_window)
    finally:
        _REFRESHING_MAIN_WINDOWS.discard(main_window_id)


def refresh_panel(panel: Any) -> bool:
    """Refresh one workflow panel through the shared safe call boundary."""
    return _call_noarg(panel, "update_panel")


def _refresh_shared_status(main_window: Any) -> bool:
    refreshed = _call_noarg(main_window, "update_info_panel")

    agent_manager = getattr(main_window, "agent_manager", None)
    refreshed = _call_noarg(agent_manager, "refresh_backend_status") or refreshed
    return refreshed


def find_main_window(context: Any) -> Any | None:
    """Find the nearest main-window-like object from a widget or helper."""
    current = context
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))

        main_window = getattr(current, "main_window", None)
        if main_window is not None:
            return main_window

        if getattr(current, "study", None) is not None and hasattr(current, "stack"):
            return current

        panel = getattr(current, "panel", None)
        if panel is not None and id(panel) not in visited:
            current = panel
            continue

        parent = getattr(current, "parent", None)
        current = parent() if callable(parent) else None
    return None


def _panel_names_for(changed: ChangedState) -> tuple[str, ...]:
    panel_names: list[str] = []
    if changed.raw_changed or changed.interpretation_changed:
        panel_names.append("dataset_panel")
    if changed.raw_changed or changed.preprocessed_changed or changed.epoch_changed:
        panel_names.append("preprocess_panel")
    if (
        changed.raw_changed
        or changed.preprocessed_changed
        or changed.epoch_changed
        or changed.datasets_changed
        or changed.training_changed
    ):
        panel_names.append("training_panel")
    if changed.training_changed or changed.evaluation_changed:
        panel_names.append("evaluation_panel")
    if (
        changed.preprocessed_changed
        or changed.epoch_changed
        or changed.training_changed
        or changed.evaluation_changed
        or changed.visualization_changed
    ):
        panel_names.append("visualization_panel")
    return tuple(dict.fromkeys(panel_names))


def _call_noarg(target: Any, method_name: str) -> bool:
    method = getattr(target, method_name, None)
    if not callable(method):
        return False
    try:
        method()
    except Exception:
        logger.debug("UI refresh failed for %s.%s", target, method_name, exc_info=True)
        return False
    return True
