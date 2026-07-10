"""UI helpers for reading backend ApplicationService capabilities."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from typing import Any, TypeVar
from unittest.mock import Mock

from PyQt6 import sip
from PyQt6.QtCore import QThreadPool

from XBrainLab.backend.application.capabilities import CommandCapability
from XBrainLab.backend.application.commands import Command, CommandName
from XBrainLab.backend.application.results import CommandResult
from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.core.worker import Worker
from XBrainLab.ui.refresh_coordinator import (
    refresh_after_command,
    suppress_observer_refresh_during_command,
)

_FallbackResult = TypeVar("_FallbackResult")
CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE = (
    "XBrainLab could not safely complete this action from the current window "
    "state. Refresh the workflow and try again."
)
get_application_service: Callable[[Study], Any] | None = None


class ControllerCompatibilityUnavailableError(RuntimeError):
    """Raised when product runtime attempts a controller compatibility mutation."""


def find_study(context: Any) -> Any | None:
    """Find the nearest Study object from a widget/panel/manager context."""
    current = context
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))

        study = getattr(current, "study", None)
        if study is not None:
            return study

        main_window = getattr(current, "main_window", None)
        study = getattr(main_window, "study", None)
        if study is not None:
            return study

        controller = getattr(current, "controller", None)
        study = getattr(controller, "study", None)
        if study is not None:
            return study

        current_attrs = getattr(current, "__dict__", {})
        for attr_name, maybe_controller in current_attrs.items():
            if attr_name == "controller" or not attr_name.endswith("_controller"):
                continue
            study = getattr(maybe_controller, "study", None)
            if study is not None:
                return study

        parent = getattr(current, "parent", None)
        current = parent() if callable(parent) else None

    return None


def has_real_application_context(context: Any) -> bool:
    """Return whether a UI context is backed by a real product ``Study``."""
    study = find_study(context)
    return (
        study is not None and isinstance(study, Study) and not isinstance(study, Mock)
    )


def get_command_capability(
    context: Any,
    command_name: CommandName | str,
) -> CommandCapability | None:
    """Read one command capability from the shared ApplicationService policy."""
    study = find_study(context)
    if study is None or not isinstance(study, Study) or isinstance(study, Mock):
        return None
    return _application_service_for(study).get_capabilities().get(command_name)


def blocked_reason(capability: CommandCapability | None, fallback: str) -> str:
    """Format a capability block reason for UI warnings/tooltips."""
    if capability is None:
        return fallback
    if capability.reasons:
        return "\n".join(capability.reasons)
    return fallback


def execute_application_command(
    context: Any,
    command: Command,
    *,
    refresh: bool = True,
) -> CommandResult | None:
    """Execute an ApplicationService command for real Study-backed UI paths.

    Returns ``None`` when the caller is backed by a mock or compatibility non-Study
    object. Product UI callers should treat that as blocked for state-changing
    commands; read-only compatibility adapters are handled separately.
    """
    study = find_study(context)
    if study is None or not isinstance(study, Study) or isinstance(study, Mock):
        return None
    with suppress_observer_refresh_during_command(context):
        result = _application_service_for(study).execute(command)
    if refresh:
        refresh_after_command(context, result)
    return result


def execute_application_shutdown_command(
    context: Any,
    command: Command,
) -> CommandResult | None:
    """Execute a teardown command while the owning widget is closing.

    This is intentionally narrower than ``execute_application_command(...,
    refresh=False)``: it is for close-time cleanup where refreshing disappearing
    widgets would be misleading, while Study detection and observer suppression
    still remain centralized in the UI command helper layer.
    """
    study = find_study(context)
    if study is None or not isinstance(study, Study) or isinstance(study, Mock):
        return None
    with suppress_observer_refresh_during_command(context):
        return _application_service_for(study).execute(command)


def execute_application_command_async(
    context: Any,
    command: Command,
    *,
    on_result: Callable[[CommandResult], None],
    on_error: Callable[[tuple], None] | None = None,
    refresh: bool = True,
    busy_target: Any | None = None,
) -> bool:
    """Execute an ApplicationService command through QThreadPool for UI flows.

    The backend command still runs through the same ApplicationService contract,
    but expensive work is offloaded from the GUI thread. Result handling and UI
    refresh are delivered through Qt signals on the receiver thread.

    Returns ``False`` for mock/compatibility contexts so callers can show an explicit
    blocked state for state-changing commands or use read-only compatibility
    adapters where that is still intentional.
    """
    study = find_study(context)
    if study is None or not isinstance(study, Study) or isinstance(study, Mock):
        return False

    service = _application_service_for(study)
    target = busy_target if busy_target is not None else context
    set_busy = getattr(target, "set_busy", None)
    if callable(set_busy):
        set_busy(True)

    suppression = suppress_observer_refresh_during_command(context)
    suppression.__enter__()

    worker = Worker(lambda: service.execute(command))
    active_workers = _active_application_workers(context)
    active_workers.append(worker)
    worker_finished = False

    def _finish_worker() -> None:
        nonlocal worker_finished
        if worker_finished:
            return
        worker_finished = True
        with suppress(Exception):
            suppression.__exit__(None, None, None)
        if callable(set_busy) and not _qt_object_deleted(target):
            set_busy(False)
        with suppress(ValueError):
            active_workers.remove(worker)

    def _handle_result(result: CommandResult) -> None:
        _finish_worker()
        if _qt_object_deleted(context):
            return
        if refresh:
            refresh_after_command(context, result)
        on_result(result)

    def _handle_error(error: tuple) -> None:
        _finish_worker()
        message = error[1] if len(error) > 1 else error
        formatted_traceback = error[2] if len(error) > 2 else ""
        logger.error(
            "Async application command failed: %s: %s",
            command.name,
            message,
        )
        if formatted_traceback:
            logger.debug(
                "Async application command traceback:\n%s",
                formatted_traceback,
            )
        if on_error is not None and not _qt_object_deleted(context):
            on_error(error)

    def _handle_finished() -> None:
        _finish_worker()

    worker.signals.result.connect(_handle_result)
    worker.signals.error.connect(_handle_error)
    worker.signals.finished.connect(_handle_finished)

    thread_pool = QThreadPool.globalInstance()
    if thread_pool is None:
        _finish_worker()
        return False

    try:
        thread_pool.start(worker)
    except Exception as exc:
        _finish_worker()
        logger.warning(
            "Could not start async application command %s: %s",
            command.name,
            exc,
        )
        return False
    return True


def _active_application_workers(context: Any) -> list[Worker]:
    workers = getattr(context, "_xbrainlab_active_application_workers", None)
    if isinstance(workers, list):
        return workers
    workers = []
    context._xbrainlab_active_application_workers = workers
    return workers


def _qt_object_deleted(obj: Any) -> bool:
    """Return ``True`` when a Qt wrapper was deleted before async callbacks."""
    if obj is None:
        return False
    try:
        return bool(sip.isdeleted(obj))
    except (AttributeError, TypeError, RuntimeError):
        return False


def _application_service_for(study: Study):
    """Load the ApplicationService runtime only when a real command needs it."""
    patched = globals()["get_application_service"]
    if patched is not None:
        return patched(study)
    from XBrainLab.backend.application.runtime import (  # noqa: PLC0415
        get_application_service as runtime_get_application_service,
    )

    return runtime_get_application_service(study)


def run_controller_compatibility_call(
    context: Any,
    fallback: Callable[[], _FallbackResult],
) -> _FallbackResult:
    """Run controller fallback only for mock or compatibility non-Study UI contexts."""
    study = find_study(context)
    if study is None or not isinstance(study, Study) or isinstance(study, Mock):
        return fallback()
    raise ControllerCompatibilityUnavailableError(
        CONTROLLER_COMPATIBILITY_UNAVAILABLE_MESSAGE,
    )


def get_controller_for_compatibility_context(
    context: Any,
    study: Any,
    controller_name: str,
) -> Any | None:
    """Return a controller only for mock / compatibility UI contexts.

    Product MainWindow wiring injects controllers into panels. This helper keeps
    older tests and standalone contexts working without allowing real Study UI
    components to walk back through the controller tree.
    """
    getter = getattr(study, "get_controller", None)
    if not callable(getter):
        return None
    try:
        return run_controller_compatibility_call(
            context,
            lambda: getter(controller_name),
        )
    except ControllerCompatibilityUnavailableError:
        return None


def local_result_payload(result) -> dict:
    """Return serializable diagnostics plus process-local UI references."""
    diagnostics = dict(getattr(result, "diagnostics", {}) or {})
    runtime = getattr(result, "runtime", {}) or {}
    if isinstance(runtime, dict):
        diagnostics.update(runtime)
    return diagnostics
