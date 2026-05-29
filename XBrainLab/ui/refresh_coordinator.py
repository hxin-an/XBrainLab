"""Command-result-driven UI refresh coordination."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from XBrainLab.backend.utils.logger import logger

_REFRESHING_MAIN_WINDOWS: set[int] = set()
_COMMAND_EXECUTING_MAIN_WINDOWS: dict[int, int] = {}
_PANEL_NAMES_BY_INDEX = (
    "dataset_panel",
    "preprocess_panel",
    "training_panel",
    "evaluation_panel",
    "visualization_panel",
)


@dataclass(frozen=True)
class _ChangedState:
    """Local route descriptor matching ApplicationService changed-state fields."""

    raw_changed: bool = False
    preprocessed_changed: bool = False
    epoch_changed: bool = False
    datasets_changed: bool = False
    training_changed: bool = False
    evaluation_changed: bool = False
    visualization_changed: bool = False
    interpretation_changed: bool = False
    error_changed: bool = False


_OBSERVER_EVENT_REFRESH_ROUTES = {
    "data_changed": ("dataset_panel", _ChangedState(raw_changed=True)),
    "preprocess_changed": (
        "preprocess_panel",
        _ChangedState(preprocessed_changed=True),
    ),
    "training_started": ("training_panel", _ChangedState(training_changed=True)),
    "training_stopped": ("training_panel", _ChangedState(training_changed=True)),
    "training_updated": ("training_panel", _ChangedState(training_changed=True)),
    "config_changed": ("training_panel", _ChangedState(training_changed=True)),
    "history_cleared": ("training_panel", _ChangedState(training_changed=True)),
    "montage_changed": (
        "visualization_panel",
        _ChangedState(visualization_changed=True),
    ),
    "saliency_changed": (
        "visualization_panel",
        _ChangedState(visualization_changed=True),
    ),
}
_OBSERVER_EVENT_PANEL_OVERRIDES = {
    # The training panel already handles live ticks with update_loop(). Routing the
    # one-second progress event through the full training_changed fan-out makes
    # evaluation, visualization, and agent status rebuild while the model is still
    # running, which is visible as UI lag.
    "training_updated": (),
}
_OBSERVER_EVENT_REFRESH_SHARED_STATUS = {
    "training_updated": False,
}


def refresh_after_command(context: Any, result: Any | None) -> bool:
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
            refreshed = refresh_panel(panel, mark_dirty=True) or refreshed

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


def refresh_after_observer(context: Any, *, event_name: str | None = None) -> bool:
    """Refresh UI surfaces affected by a backend observer event."""
    main_window = find_main_window(context)
    if main_window is None:
        return refresh_panel(context)

    main_window_id = id(main_window)
    if _COMMAND_EXECUTING_MAIN_WINDOWS.get(main_window_id, 0) > 0:
        return False
    if main_window_id in _REFRESHING_MAIN_WINDOWS:
        return False

    _REFRESHING_MAIN_WINDOWS.add(main_window_id)
    try:
        route = _OBSERVER_EVENT_REFRESH_ROUTES.get(str(event_name))
        refreshed = False
        if route is not None:
            source_panel_name, changed_state = route
            source_panel = getattr(main_window, source_panel_name, None)
            if source_panel is None:
                refreshed = refresh_panel(context, mark_dirty=True)
                if _should_refresh_shared_status(event_name):
                    return _refresh_shared_status(main_window) or refreshed
                return refreshed
            if not _is_source_context(context, source_panel):
                return False
            panel_names = _panel_names_for_observer_event(event_name, changed_state)
            for panel_name in panel_names:
                panel = getattr(main_window, panel_name, None)
                refreshed = refresh_panel(panel, mark_dirty=True) or refreshed
        else:
            refreshed = refresh_panel(context, mark_dirty=True)
        if _should_refresh_shared_status(event_name):
            return _refresh_shared_status(main_window) or refreshed
        return refreshed
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


@contextmanager
def suppress_observer_refresh_during_command(context: Any) -> Iterator[None]:
    """Skip observer-driven refreshes until command result refresh can run."""
    main_window = find_main_window(context)
    if main_window is None:
        yield
        return

    main_window_id = id(main_window)
    _COMMAND_EXECUTING_MAIN_WINDOWS[main_window_id] = (
        _COMMAND_EXECUTING_MAIN_WINDOWS.get(main_window_id, 0) + 1
    )
    try:
        yield
    finally:
        active_count = _COMMAND_EXECUTING_MAIN_WINDOWS.get(main_window_id, 0)
        if active_count <= 1:
            _COMMAND_EXECUTING_MAIN_WINDOWS.pop(main_window_id, None)
        else:
            _COMMAND_EXECUTING_MAIN_WINDOWS[main_window_id] = active_count - 1


def refresh_panel(panel: Any, *, mark_dirty: bool = False) -> bool:
    """Refresh one workflow panel through the shared safe call boundary."""
    if mark_dirty:
        _call_noarg(panel, "mark_refresh_dirty")
    return _call_noarg(panel, "update_panel")


def _refresh_shared_status(main_window: Any) -> bool:
    refreshed = _call_noarg(main_window, "update_info_panel")

    agent_manager = getattr(main_window, "agent_manager", None)
    refreshed = _call_noarg(agent_manager, "refresh_backend_status") or refreshed
    return refreshed


def _is_source_context(context: Any, source_panel: Any) -> bool:
    if source_panel is None:
        return False
    return context is source_panel or getattr(context, "panel", None) is source_panel


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


def _panel_names_for(changed: Any) -> tuple[str, ...]:
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


def _panel_names_for_observer_event(
    event_name: str | None,
    changed: Any,
) -> tuple[str, ...]:
    if str(event_name) in _OBSERVER_EVENT_PANEL_OVERRIDES:
        return _OBSERVER_EVENT_PANEL_OVERRIDES[str(event_name)]
    return _panel_names_for(changed)


def _should_refresh_shared_status(event_name: str | None) -> bool:
    return _OBSERVER_EVENT_REFRESH_SHARED_STATUS.get(str(event_name), True)


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
