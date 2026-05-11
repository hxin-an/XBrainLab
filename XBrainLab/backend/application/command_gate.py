"""Capability and confirmation gate for application commands."""

from __future__ import annotations

from .capabilities import build_capability_policy
from .commands import Command, command_name
from .errors import ConfirmationRequiredError, PreconditionError
from .state import ApplicationStateSnapshot


def ensure_command_allowed(
    command: Command,
    state: ApplicationStateSnapshot,
) -> None:
    """Validate backend capability and confirmation policy before execution."""
    name = command_name(command)
    capability = build_capability_policy(state).get(name)
    if not capability.enabled:
        raise PreconditionError("; ".join(capability.reasons))
    if (
        capability.confirmation_required or capability.requires_confirmation
    ) and not bool(getattr(command, "confirmed", False)):
        raise ConfirmationRequiredError(f"{name.value} requires confirmation.")
