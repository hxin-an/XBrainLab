"""Typed outcomes for assistant-owned user interactions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AgentInteractionStatus(str, Enum):
    """Structured resolution of one controller-owned user interaction."""

    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    DEFERRED_TO_UI = "deferred_to_ui"
    COMPLETED_IN_UI = "completed_in_ui"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


@dataclass(frozen=True)
class AgentInteractionOutcome:
    """Typed interaction result consumed by the GUI presentation layer."""

    status: AgentInteractionStatus
    command_name: str
    request_id: str = ""
    decision_fields: tuple[str, ...] = ()
    message: str = ""
