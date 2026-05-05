"""UI helpers for reading backend ApplicationService capabilities."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar
from unittest.mock import Mock

from XBrainLab.backend.application import Command, CommandName, CommandResult
from XBrainLab.backend.application.capabilities import CommandCapability
from XBrainLab.backend.facade import BackendFacade
from XBrainLab.backend.study import Study
from XBrainLab.ui.refresh_coordinator import refresh_after_command

_FallbackResult = TypeVar("_FallbackResult")


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

        parent = getattr(current, "parent", None)
        current = parent() if callable(parent) else None

    return None


def get_command_capability(
    context: Any,
    command_name: CommandName | str,
) -> CommandCapability | None:
    """Read one command capability from the shared ApplicationService policy."""
    study = find_study(context)
    if study is None or not isinstance(study, Study) or isinstance(study, Mock):
        return None
    return BackendFacade(study).get_capabilities().get(command_name)


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

    Returns ``None`` when the caller is backed by a mock or legacy non-Study
    object, allowing existing unit-test and compatibility paths to fall back to
    controller methods.
    """
    study = find_study(context)
    if study is None or not isinstance(study, Study) or isinstance(study, Mock):
        return None
    result = BackendFacade(study).service.execute(command)
    if refresh:
        refresh_after_command(context, result)
    return result


def run_legacy_controller_fallback(
    context: Any,
    fallback: Callable[[], _FallbackResult],
) -> _FallbackResult:
    """Run controller fallback only for mock or legacy non-Study UI contexts."""
    study = find_study(context)
    if study is None or not isinstance(study, Study) or isinstance(study, Mock):
        return fallback()
    raise RuntimeError(
        "ApplicationService command was unavailable for a real Study; "
        "refusing controller fallback.",
    )
