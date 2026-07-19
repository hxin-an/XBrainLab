"""Command-result-driven UI refresh coordination."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from weakref import ReferenceType, ref

from PyQt6 import sip

from XBrainLab.backend.application.results import ChangedState
from XBrainLab.backend.utils.logger import logger

_REFRESHING_MAIN_WINDOWS: set[int] = set()
_COMMAND_EXECUTING_MAIN_WINDOWS: dict[int, int] = {}
_DEFERRED_TERMINAL_REFRESHES: dict[
    int,
    dict[tuple[int, str], _DeferredObserverRefresh],
] = {}
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
    state_unknown: bool = False


@dataclass(frozen=True)
class _DeferredObserverRefresh:
    """Weak observer delivery retained until the command suppression lease ends."""

    context_ref: ReferenceType[Any]
    event_name: str


_OBSERVER_EVENT_REFRESH_ROUTES = {
    "data_changed": ("dataset_panel", _ChangedState(raw_changed=True)),
    "preprocess_changed": (
        "preprocess_panel",
        _ChangedState(preprocessed_changed=True),
    ),
    "training_started": ("training_panel", _ChangedState(training_changed=True)),
    "training_stopped": ("training_panel", _ChangedState(training_changed=True)),
    "training_terminal_published": (
        "training_panel",
        _ChangedState(training_changed=True),
    ),
    "training_analysis_published": (
        "training_panel",
        # The paired saliency_changed event owns the visualization refresh.
        # This typed publication only reconciles lifecycle generation and shared
        # status, so it intentionally has no workflow-panel changed state.
        _ChangedState(),
    ),
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


def refresh_after_serialized_command(
    context: Any,
    changed_state: dict[str, Any] | None,
) -> bool:
    """Refresh UI from an agent-safe serialized ``ChangedState`` payload."""
    normalized = _normalize_serialized_changed_state(changed_state)
    if normalized is None:
        return False
    if not normalized.any_changed():
        return False

    class _SerializedResult:
        def __init__(self, value: ChangedState) -> None:
            self.changed_state = value

    return refresh_after_command(context, _SerializedResult(normalized))


def complete_command_refresh_suppression(
    context: Any,
    changed_state: dict[str, Any] | None,
) -> bool:
    """Complete one agent command with a single coalesced panel refresh.

    Terminal observers carry renderer-specific semantics that a generic changed
    state cannot replace.  Merge both sources by target panel so the terminal
    renderer is preserved without repainting evaluation, visualization, or
    shared status twice.
    """
    normalized = _normalize_serialized_changed_state(changed_state)
    main_window = find_main_window(context)
    if main_window is None:
        end_command_refresh_suppression(context)
        return False

    main_window_id = id(main_window)
    released, deferred = _release_command_refresh_suppression_for(main_window_id)
    if not released:
        return False
    return _refresh_completed_command(
        main_window,
        normalized,
        deferred,
    )


def _normalize_serialized_changed_state(
    changed_state: dict[str, Any] | None,
) -> ChangedState | None:
    if not isinstance(changed_state, dict):
        return None
    field_names = ChangedState.__dataclass_fields__
    return ChangedState(
        **{name: bool(changed_state.get(name, False)) for name in field_names}
    )


def refresh_after_navigation(main_window: Any, index: int) -> bool:
    """Refresh the visible workflow panel selected by top-level navigation."""
    if index < 0 or index >= len(_PANEL_NAMES_BY_INDEX):
        return False

    main_window_id = id(main_window)
    if _COMMAND_EXECUTING_MAIN_WINDOWS.get(main_window_id, 0) > 0:
        return False
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
        _defer_terminal_observer_refresh(main_window_id, context, event_name)
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
                refreshed = _refresh_panel_after_observer(context, event_name)
                if _should_refresh_shared_status(event_name):
                    return _refresh_shared_status(main_window) or refreshed
                return refreshed
            if not _is_source_context(context, source_panel):
                return False
            panel_names = _panel_names_for_observer_event(event_name, changed_state)
            for panel_name in panel_names:
                panel = getattr(main_window, panel_name, None)
                refreshed = (
                    _refresh_panel_after_observer(panel, event_name) or refreshed
                )
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
    main_window_id = _command_refresh_suppression_key(context)
    if main_window_id is None:
        yield
        return
    _begin_command_refresh_suppression_for(main_window_id)
    try:
        yield
    finally:
        _end_command_refresh_suppression_for(main_window_id)


def begin_command_refresh_suppression(context: Any) -> bool:
    """Begin a nestable UI observer-suppression window for one command."""
    main_window_id = _command_refresh_suppression_key(context)
    if main_window_id is None:
        return False
    _begin_command_refresh_suppression_for(main_window_id)
    return True


def _begin_command_refresh_suppression_for(main_window_id: int) -> None:
    """Increment suppression by immutable owner id."""
    _COMMAND_EXECUTING_MAIN_WINDOWS[main_window_id] = (
        _COMMAND_EXECUTING_MAIN_WINDOWS.get(main_window_id, 0) + 1
    )


def end_command_refresh_suppression(context: Any) -> bool:
    """End one UI observer-suppression window opened for a command."""
    main_window_id = _command_refresh_suppression_key(context)
    if main_window_id is None:
        return False
    return _end_command_refresh_suppression_for(main_window_id)


def _end_command_refresh_suppression_for(main_window_id: int) -> bool:
    """Decrement suppression without dereferencing a possibly deleted Qt object."""
    released, deferred = _release_command_refresh_suppression_for(main_window_id)
    if released:
        _replay_deferred_terminal_refreshes(main_window_id, deferred)
    return released


def _release_command_refresh_suppression_for(
    main_window_id: int,
) -> tuple[bool, dict[tuple[int, str], _DeferredObserverRefresh]]:
    """Release the final suppression lease and return its deferred publications."""
    active_count = _COMMAND_EXECUTING_MAIN_WINDOWS.get(main_window_id, 0)
    if active_count > 1:
        _COMMAND_EXECUTING_MAIN_WINDOWS[main_window_id] = active_count - 1
        return False, {}
    _COMMAND_EXECUTING_MAIN_WINDOWS.pop(main_window_id, None)
    if active_count == 1:
        return True, _DEFERRED_TERMINAL_REFRESHES.pop(main_window_id, {})
    _DEFERRED_TERMINAL_REFRESHES.pop(main_window_id, None)
    return False, {}


def _defer_terminal_observer_refresh(
    main_window_id: int,
    context: Any,
    event_name: str | None,
) -> None:
    """Coalesce terminal publication delivery without retaining its Qt owner."""
    normalized_event = str(event_name)
    if normalized_event not in {
        "training_terminal_published",
        "training_analysis_published",
        "saliency_changed",
    }:
        return
    try:
        context_ref = ref(context)
    except TypeError:
        return
    pending = _DEFERRED_TERMINAL_REFRESHES.setdefault(main_window_id, {})
    pending[(id(context), normalized_event)] = _DeferredObserverRefresh(
        context_ref=context_ref,
        event_name=normalized_event,
    )


def _replay_deferred_terminal_refreshes(
    main_window_id: int,
    pending: dict[tuple[int, str], _DeferredObserverRefresh] | None = None,
) -> None:
    """Replay terminal observer delivery after the final suppression lease."""
    deferred_refreshes = (
        _DEFERRED_TERMINAL_REFRESHES.pop(main_window_id, {})
        if pending is None
        else pending
    )
    for deferred in deferred_refreshes.values():
        context = deferred.context_ref()
        if context is None or _qt_object_deleted(context):
            continue
        try:
            refresh_after_observer(context, event_name=deferred.event_name)
        except Exception:
            logger.debug("Deferred terminal UI refresh failed", exc_info=True)


def _refresh_completed_command(
    main_window: Any,
    changed_state: ChangedState | None,
    deferred: dict[tuple[int, str], _DeferredObserverRefresh],
) -> bool:
    """Refresh each command-affected panel once after observer suppression."""
    main_window_id = id(main_window)
    if main_window_id in _REFRESHING_MAIN_WINDOWS:
        return False

    panel_events: dict[str, str | None] = {}
    if changed_state is not None and changed_state.any_changed():
        panel_events.update(dict.fromkeys(_panel_names_for(changed_state)))

    refresh_shared_status = bool(
        changed_state is not None and changed_state.any_changed()
    )
    standalone_contexts: dict[str, Any] = {}
    for publication in deferred.values():
        context = publication.context_ref()
        if context is None or _qt_object_deleted(context):
            continue
        event_name = publication.event_name
        route = _OBSERVER_EVENT_REFRESH_ROUTES.get(event_name)
        if route is None:
            continue
        source_panel_name, event_changed_state = route
        source_panel = getattr(main_window, source_panel_name, None)
        if source_panel is not None and not _is_source_context(context, source_panel):
            continue
        if source_panel is None:
            standalone_contexts[source_panel_name] = context
        for panel_name in _panel_names_for_observer_event(
            event_name,
            event_changed_state,
        ):
            if event_name == "training_terminal_published" and (
                panel_name == "training_panel"
            ):
                panel_events[panel_name] = event_name
            else:
                panel_events.setdefault(panel_name, None)
        refresh_shared_status = (
            _should_refresh_shared_status(event_name) or refresh_shared_status
        )

    if not panel_events and not refresh_shared_status:
        return False

    _REFRESHING_MAIN_WINDOWS.add(main_window_id)
    try:
        refreshed = False
        for panel_name in _PANEL_NAMES_BY_INDEX:
            if panel_name not in panel_events:
                continue
            panel = getattr(main_window, panel_name, None)
            if panel is None:
                panel = standalone_contexts.get(panel_name)
            event_name = panel_events[panel_name]
            if event_name is None:
                refreshed = refresh_panel(panel, mark_dirty=True) or refreshed
            else:
                refreshed = (
                    _refresh_panel_after_observer(panel, event_name) or refreshed
                )
        if refresh_shared_status:
            refreshed = _refresh_shared_status(main_window) or refreshed
        return refreshed
    finally:
        _REFRESHING_MAIN_WINDOWS.discard(main_window_id)


def _qt_object_deleted(target: Any) -> bool:
    try:
        return bool(sip.isdeleted(target))
    except (TypeError, RuntimeError):
        return False


def _command_refresh_suppression_key(context: Any) -> int | None:
    """Resolve one stable owner key while the Qt context is known to be alive."""
    main_window = find_main_window(context)
    return id(main_window) if main_window is not None else None


def refresh_panel(panel: Any, *, mark_dirty: bool = False) -> bool:
    """Refresh one workflow panel through the shared safe call boundary."""
    if mark_dirty:
        _call_noarg(panel, "mark_refresh_dirty")
    return _call_noarg(panel, "update_panel")


def _refresh_panel_after_observer(
    panel: Any,
    event_name: str | None,
) -> bool:
    """Use the terminal renderer only at its authoritative observer boundary."""
    _call_noarg(panel, "mark_refresh_dirty")
    if str(event_name) == "training_terminal_published" and callable(
        getattr(panel, "refresh_terminal_publication", None)
    ):
        return _call_noarg(panel, "refresh_terminal_publication")
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
    if bool(getattr(changed, "state_unknown", False)):
        return _PANEL_NAMES_BY_INDEX
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
