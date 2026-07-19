"""Host-enforced execution policy for Ask and Workflow assistant turns.

The language model may propose actions, but it does not decide whether a
second action is allowed. This module keeps that decision deterministic and
independent from prompt compliance.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

_Command = TypeVar("_Command")


@dataclass(frozen=True)
class ExecutionSnapshot:
    """Fresh workflow facts read after one command completes."""

    state_reliable: bool
    decision_needed: tuple[str, ...]
    can_auto_continue: bool
    next_requires_confirmation: bool = False
    next_decision_boundary: str | None = None
    next_long_running: bool = False
    next_destructive: bool = False
    next_continue_allowed_after_success: bool = True
    next_stop_after_success: bool = False
    recommended_next_step: str | None = None
    read_error: str | None = None
    publication: Any | None = None

    @classmethod
    def safe_to_continue(cls) -> ExecutionSnapshot:
        return cls(True, (), True)

    @classmethod
    def unreliable(cls, error: str) -> ExecutionSnapshot:
        return cls(False, (), False, read_error=error)


@dataclass(frozen=True)
class ExecutionDecision:
    """Deterministic host decision after a tool attempt."""

    continue_workflow: bool
    reason: str


class HostExecutionPolicy:
    """Enforce one-command turns and bounded Workflow continuation."""

    ASK_MODE = "single"
    WORKFLOW_MODE = "multi"

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
        tool_cap = 1 if mode != self.WORKFLOW_MODE else workflow_tool_cap
        if execution_count >= tool_cap:
            return ExecutionDecision(False, "tool_cap")
        return ExecutionDecision(True, "execute")

    def after_success(
        self,
        *,
        mode: str,
        availability: Any | None,
        snapshot: ExecutionSnapshot,
        execution_count: int,
        tool_cap: int,
        after_confirmation: bool = False,
        cancelled: bool = False,
    ) -> ExecutionDecision:
        if cancelled:
            return ExecutionDecision(False, "cancelled")
        if mode != self.WORKFLOW_MODE:
            return ExecutionDecision(False, "ask_tool_limit")
        if after_confirmation:
            return ExecutionDecision(False, "confirmed_boundary")
        if execution_count >= tool_cap:
            return ExecutionDecision(False, "tool_cap")
        if not snapshot.state_reliable:
            return ExecutionDecision(False, "state_unreliable")
        if snapshot.decision_needed:
            return ExecutionDecision(False, "decision_needed")
        if _flag(availability, "requires_confirmation") or _flag(
            availability,
            "confirmation_required",
        ):
            return ExecutionDecision(False, "requires_confirmation")
        if _flag(availability, "long_running"):
            return ExecutionDecision(False, "long_running")
        if _flag(availability, "destructive"):
            return ExecutionDecision(False, "destructive")
        if _flag(availability, "stop_after_success"):
            return ExecutionDecision(False, "stop_after_success")
        if not _flag(
            availability,
            "continue_allowed_after_success",
            default=True,
        ):
            return ExecutionDecision(False, "continuation_disallowed")
        if snapshot.next_requires_confirmation:
            return ExecutionDecision(False, "next_requires_confirmation")
        if snapshot.next_long_running:
            return ExecutionDecision(False, "next_long_running")
        if snapshot.next_destructive:
            return ExecutionDecision(False, "next_destructive")
        if snapshot.next_stop_after_success:
            return ExecutionDecision(False, "next_stop_after_success")
        if not snapshot.next_continue_allowed_after_success:
            return ExecutionDecision(False, "next_continuation_disallowed")
        if not snapshot.can_auto_continue:
            return ExecutionDecision(False, "workflow_stop")
        return ExecutionDecision(True, "continue")

    def after_failure(
        self,
        *,
        mode: str,
        availability: Any | None,
        failure_count: int,
        global_retry_limit: int,
        execution_count: int,
        tool_cap: int,
        cancelled: bool,
    ) -> ExecutionDecision:
        if cancelled:
            return ExecutionDecision(False, "cancelled")
        if mode != self.WORKFLOW_MODE:
            return ExecutionDecision(False, "ask_tool_limit")
        if execution_count >= tool_cap:
            return ExecutionDecision(False, "tool_cap")
        retry_limit = int(_value(availability, "retry_limit", default=2))
        effective_limit = min(max(retry_limit, 0), max(global_retry_limit, 0))
        if failure_count >= effective_limit:
            return ExecutionDecision(False, "retry_cap")
        return ExecutionDecision(True, "retry")


def _value(subject: Any | None, name: str, *, default: Any = None) -> Any:
    if subject is None:
        return default
    if isinstance(subject, dict):
        return subject.get(name, default)
    return getattr(subject, name, default)


def _flag(subject: Any | None, name: str, *, default: bool = False) -> bool:
    return bool(_value(subject, name, default=default))
