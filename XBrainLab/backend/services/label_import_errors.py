"""Lightweight exception contracts for atomic label application."""

from dataclasses import dataclass
from typing import Literal, TypeAlias

AtomicLabelFailurePhase: TypeAlias = Literal["preparation", "commit"]


@dataclass(frozen=True)
class AtomicLabelRollbackFailure:
    """One failed compensation after an atomic label commit error."""

    target_path: str
    exception_type: str
    message: str


class AtomicLabelStateUnknownError(RuntimeError):
    """Raised when a failed label commit cannot restore every live target."""

    state_unknown = True
    recoverable = False

    def __init__(
        self,
        *,
        operation_name: str,
        commit_error: Exception,
        rollback_failures: list[AtomicLabelRollbackFailure],
    ) -> None:
        self.operation_name = operation_name
        self.commit_error = commit_error
        self.rollback_failures = tuple(rollback_failures)
        rollback_summary = "; ".join(
            f"{failure.target_path}: {failure.message}" for failure in rollback_failures
        )
        super().__init__(
            f"Atomic {operation_name} commit failed ({commit_error}) and rollback "
            f"was incomplete ({rollback_summary}). Active label state is unknown; "
            "do not retry automatically."
        )


class AtomicLabelApplyError(RuntimeError):
    """Recoverable atomic failure with a bounded user-facing explanation."""

    state_unknown = False
    recoverable = True

    def __init__(
        self,
        *,
        operation_name: str,
        phase: AtomicLabelFailurePhase,
        cause: Exception,
    ) -> None:
        self.operation_name = operation_name
        self.phase = phase
        self.cause = cause
        if isinstance(cause, ValueError) and str(cause).strip():
            self.error_code = "label_validation_failed"
            self.user_message = str(cause).strip()
        else:
            self.error_code = "label_application_failed"
            self.user_message = (
                "Reviewed labels could not be applied safely; no labels were changed."
            )
        super().__init__(f"Atomic label {phase} failed.")
