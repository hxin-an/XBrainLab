"""Capability and confirmation gate for application commands."""

from __future__ import annotations

from .capabilities import (
    SALIENCY_TRAINING_ACTIVE_REASON,
    build_capability_policy,
)
from .commands import Command, SaliencyCommand, command_name
from .errors import ApplicationError, ConfirmationRequiredError, PreconditionError
from .results import ErrorType
from .state import ApplicationStateSnapshot


def ensure_command_allowed(
    command: Command,
    state: ApplicationStateSnapshot,
) -> None:
    """Validate backend capability and confirmation policy before execution."""
    name = command_name(command)
    _validate_confirmation_fields(command, name.value)
    capability = build_capability_policy(state).get(name)
    if not capability.enabled:
        reasons = list(capability.reasons)
        if (
            isinstance(command, SaliencyCommand)
            and command.method is None
            and command.params is None
        ):
            reasons = [
                reason
                for reason in reasons
                if reason != SALIENCY_TRAINING_ACTIVE_REASON
            ]
        if reasons:
            raise PreconditionError("; ".join(reasons))
    if (
        capability.confirmation_required or capability.requires_confirmation
    ) and getattr(command, "confirmed", False) is not True:
        raise ConfirmationRequiredError(f"{name.value} requires confirmation.")


def _validate_confirmation_fields(command: Command, command_name: str) -> None:
    for field_name, value in vars(command).items():
        if not _is_confirmation_field(field_name) or type(value) is bool:
            continue
        received_type = type(value).__name__
        raise ApplicationError(
            message=(
                f"{command_name} argument {field_name} must be a boolean; "
                f"received {received_type}."
            ),
            error_type=ErrorType.VALIDATION,
            recoverable=True,
            diagnostics={
                "confirmation_field": field_name,
                "expected_type": "boolean",
                "received_type": received_type,
            },
        )


def _is_confirmation_field(name: str) -> bool:
    return name == "confirmed" or name.endswith("_confirmed")
