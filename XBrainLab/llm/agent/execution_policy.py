"""Minimal host safety policy for one assistant action per user turn."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

_Command = TypeVar("_Command")


@dataclass(frozen=True)
class ExecutionDecision:
    """Deterministic host decision before one tool attempt."""

    continue_workflow: bool
    reason: str


class HostExecutionPolicy:
    """Enforce one command and backend-owned confirmation per user turn."""

    ASK_MODE = "single"

    @staticmethod
    def first_command(commands: Sequence[_Command]) -> _Command | None:
        return commands[0] if commands else None

    @staticmethod
    def needs_confirmation(
        availability: Any | None,
        *,
        tool_requires_confirmation: bool,
    ) -> bool:
        return bool(
            tool_requires_confirmation
            or _flag(availability, "requires_confirmation")
            or _flag(availability, "confirmation_required")
            or _flag(availability, "long_running")
            or _flag(availability, "destructive")
            or not _flag(availability, "can_auto_execute", default=True)
        )

    def before_command(
        self,
        *,
        mode: str,
        execution_count: int,
        workflow_tool_cap: int,
        cancelled: bool,
    ) -> ExecutionDecision:
        """Enforce cancellation and per-turn tool caps before execution."""
        if cancelled:
            return ExecutionDecision(False, "cancelled")
        del mode, workflow_tool_cap
        if execution_count >= 1:
            return ExecutionDecision(False, "tool_cap")
        return ExecutionDecision(True, "execute")


def _value(subject: Any | None, name: str, *, default: Any = None) -> Any:
    if subject is None:
        return default
    if isinstance(subject, dict):
        return subject.get(name, default)
    return getattr(subject, name, default)


def _flag(subject: Any | None, name: str, *, default: bool = False) -> bool:
    return bool(_value(subject, name, default=default))
