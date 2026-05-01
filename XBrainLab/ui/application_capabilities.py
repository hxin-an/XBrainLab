"""UI helpers for reading backend ApplicationService capabilities."""

from __future__ import annotations

from typing import Any

from XBrainLab.backend.application import CommandName
from XBrainLab.backend.application.capabilities import CommandCapability
from XBrainLab.backend.facade import BackendFacade
from XBrainLab.backend.study import Study


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
    if study is None or not isinstance(study, Study):
        return None
    return BackendFacade(study).get_capabilities().get(command_name)


def blocked_reason(capability: CommandCapability | None, fallback: str) -> str:
    """Format a capability block reason for UI warnings/tooltips."""
    if capability is None:
        return fallback
    if capability.reasons:
        return "\n".join(capability.reasons)
    return fallback
