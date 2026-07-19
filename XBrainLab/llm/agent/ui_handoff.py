"""Typed assistant requests for continuing work in existing product UI."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4

from XBrainLab.backend.application.commands import CommandName
from XBrainLab.backend.application.view_publication import (
    InterpretationReviewIdentity,
)


class WorkflowUiHandoffKind(str, Enum):
    """Why the assistant is yielding control to an existing UI surface."""

    DECISION_REQUIRED = "decision_required"


class WorkflowUiHandoffResolutionStatus(str, Enum):
    """How an existing product surface resolved one assistant handoff."""

    NAVIGATED = "navigated"
    COMMAND_PENDING = "command_pending"
    DEFERRED_TO_UI = "deferred_to_ui"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        """Return whether this status can release the owning assistant turn."""
        return self in {
            WorkflowUiHandoffResolutionStatus.NAVIGATED,
            WorkflowUiHandoffResolutionStatus.DEFERRED_TO_UI,
            WorkflowUiHandoffResolutionStatus.COMPLETED,
            WorkflowUiHandoffResolutionStatus.CANCELLED,
            WorkflowUiHandoffResolutionStatus.BLOCKED,
            WorkflowUiHandoffResolutionStatus.UNAVAILABLE,
            WorkflowUiHandoffResolutionStatus.FAILED,
        }


class WorkflowUiHandoffSessionStatus(str, Enum):
    """Current phase of one request-correlated product-UI handoff."""

    REQUESTED = "requested"
    COMMAND_PENDING = "command_pending"
    TERMINAL = "terminal"


class WorkflowUiHandoffTransitionStatus(str, Enum):
    """Result of applying one resolution to a handoff session."""

    ADVANCED = "advanced"
    TERMINATED = "terminated"
    STALE = "stale"
    DUPLICATE = "duplicate"
    INVALID = "invalid"


def _require_typed_enum(
    value: object,
    expected_type: type[Enum],
    *,
    contract: str,
    field_name: str,
) -> None:
    """Reject raw strings and enums from a different contract field."""
    if type(value) is not expected_type:
        raise TypeError(f"Workflow UI handoff {contract} {field_name} must be typed.")


def _normalize_request_id(value: object, *, contract: str) -> str:
    """Return one stable correlation identity or reject malformed input."""
    if type(value) is not str:
        raise TypeError(f"Workflow UI handoff {contract} request id must be a string.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"Workflow UI handoff {contract} id cannot be empty.")
    return normalized


def _validate_decision_fields(
    value: object,
    *,
    contract: str,
) -> None:
    """Validate the immutable decision-field representation."""
    if type(value) is not tuple:
        raise TypeError(
            f"Workflow UI handoff {contract} decision_fields must be a tuple."
        )
    for field_name in value:
        if type(field_name) is not str:
            raise TypeError(
                "Workflow UI handoff "
                f"{contract} decision_fields entries must be strings."
            )
        if not field_name.strip():
            raise ValueError(
                "Workflow UI handoff "
                f"{contract} decision_fields entries cannot be empty."
            )


def _validate_suggested_values(
    value: object,
    *,
    contract: str,
) -> None:
    """Validate suggestions before callers can reach ``dict()`` conversion."""
    if type(value) is not tuple:
        raise TypeError(
            f"Workflow UI handoff {contract} suggested_values must be a tuple."
        )
    for pair in value:
        if type(pair) is not tuple or len(pair) != 2:
            raise TypeError(
                "Workflow UI handoff "
                f"{contract} suggested_values entries must be key/value tuples."
            )
        key, suggested_value = pair
        if type(key) is not str or type(suggested_value) is not str:
            raise TypeError(
                "Workflow UI handoff "
                f"{contract} suggested_values keys and values must be strings."
            )
        if not key.strip() or not suggested_value.strip():
            raise ValueError(
                "Workflow UI handoff "
                f"{contract} suggested_values cannot contain empty text."
            )


@dataclass(frozen=True)
class WorkflowUiHandoffRequest:
    """Backend-command handoff consumed by the host UI router."""

    kind: WorkflowUiHandoffKind
    command: CommandName
    request_id: str = field(default_factory=lambda: uuid4().hex)
    decision_fields: tuple[str, ...] = ()
    suggested_values: tuple[tuple[str, str], ...] = ()
    interpretation_identity: InterpretationReviewIdentity | None = None

    def __post_init__(self) -> None:
        _require_typed_enum(
            self.kind,
            WorkflowUiHandoffKind,
            contract="request",
            field_name="kind",
        )
        _require_typed_enum(
            self.command,
            CommandName,
            contract="request",
            field_name="command",
        )
        object.__setattr__(
            self,
            "request_id",
            _normalize_request_id(self.request_id, contract="request"),
        )
        _validate_decision_fields(self.decision_fields, contract="request")
        _validate_suggested_values(self.suggested_values, contract="request")
        if self.interpretation_identity is not None and not isinstance(
            self.interpretation_identity,
            InterpretationReviewIdentity,
        ):
            raise TypeError(
                "Workflow UI handoff request interpretation identity must be typed."
            )

    @property
    def command_name(self) -> str:
        """Return the stable ApplicationService command identifier."""
        return self.command.value

    @property
    def suggestions(self) -> dict[str, str]:
        """Return immutable request suggestions as a fresh mapping."""
        return dict(self.suggested_values)

    @classmethod
    def for_decision(
        cls,
        command_name: CommandName | str,
        *,
        decision_fields: Iterable[str] = (),
        suggested_values: Mapping[str, object] | None = None,
        request_id: str | None = None,
        interpretation_identity: InterpretationReviewIdentity | None = None,
    ) -> WorkflowUiHandoffRequest:
        """Build a decision handoff and reject unknown command text."""
        if isinstance(command_name, CommandName):
            command = command_name
        else:
            normalized = str(command_name or "").strip().lower()
            try:
                command = CommandName(normalized)
            except ValueError as exc:
                raise ValueError(
                    f"Unknown workflow UI handoff command: {normalized or '(empty)'}"
                ) from exc

        fields: list[str] = []
        for raw_field in decision_fields:
            field = str(raw_field or "").strip()
            if field and field not in fields:
                fields.append(field)
        normalized_request_id = (
            uuid4().hex if request_id is None else str(request_id).strip()
        )
        suggestions: list[tuple[str, str]] = []
        seen_suggestion_keys: set[str] = set()
        for raw_key, raw_value in (suggested_values or {}).items():
            key = str(raw_key or "").strip()
            value = " ".join(str(raw_value or "").split())
            if key and value and key not in seen_suggestion_keys:
                suggestions.append((key, value))
                seen_suggestion_keys.add(key)
        return cls(
            kind=WorkflowUiHandoffKind.DECISION_REQUIRED,
            command=command,
            request_id=normalized_request_id,
            decision_fields=tuple(fields),
            suggested_values=tuple(suggestions),
            interpretation_identity=interpretation_identity,
        )


@dataclass(frozen=True)
class WorkflowUiHandoffResolution:
    """Correlated result returned by the existing product UI surface."""

    request_id: str
    command: CommandName
    status: WorkflowUiHandoffResolutionStatus
    decision_fields: tuple[str, ...] = ()
    suggested_values: tuple[tuple[str, str], ...] = ()
    interpretation_identity: InterpretationReviewIdentity | None = None
    message: str = ""

    def __post_init__(self) -> None:
        _require_typed_enum(
            self.command,
            CommandName,
            contract="resolution",
            field_name="command",
        )
        _require_typed_enum(
            self.status,
            WorkflowUiHandoffResolutionStatus,
            contract="resolution",
            field_name="status",
        )
        object.__setattr__(
            self,
            "request_id",
            _normalize_request_id(self.request_id, contract="resolution"),
        )
        _validate_decision_fields(self.decision_fields, contract="resolution")
        _validate_suggested_values(self.suggested_values, contract="resolution")
        if self.interpretation_identity is not None and not isinstance(
            self.interpretation_identity,
            InterpretationReviewIdentity,
        ):
            raise TypeError(
                "Workflow UI handoff resolution interpretation identity must be typed."
            )

    @property
    def command_name(self) -> str:
        """Return the stable ApplicationService command identifier."""
        return self.command.value

    @property
    def suggestions(self) -> dict[str, str]:
        """Return the exact suggestions associated with this resolution."""
        return dict(self.suggested_values)

    @property
    def routed(self) -> bool:
        """Return whether the host reached a real product surface."""
        return self.status not in {
            WorkflowUiHandoffResolutionStatus.UNAVAILABLE,
            WorkflowUiHandoffResolutionStatus.FAILED,
        }

    @property
    def is_verified_completion(self) -> bool:
        """Return whether the product surface verified the requested mutation."""
        return self.status is WorkflowUiHandoffResolutionStatus.COMPLETED

    def matches(self, request: object) -> bool:
        """Return whether this result belongs to the exact typed request."""
        return bool(
            isinstance(request, WorkflowUiHandoffRequest)
            and self.request_id == request.request_id
            and self.command is request.command
            and self.decision_fields == request.decision_fields
            and self.suggested_values == request.suggested_values
            and self.interpretation_identity == request.interpretation_identity
        )

    @classmethod
    def for_request(
        cls,
        request: WorkflowUiHandoffRequest,
        *,
        status: WorkflowUiHandoffResolutionStatus,
        message: str = "",
    ) -> WorkflowUiHandoffResolution:
        """Build a resolution that cannot drop request correlation metadata."""
        if not isinstance(request, WorkflowUiHandoffRequest):
            raise TypeError("Workflow UI resolution requires a typed request.")
        if not isinstance(status, WorkflowUiHandoffResolutionStatus):
            raise TypeError("Workflow UI resolution status must be typed.")
        return cls(
            request_id=request.request_id,
            command=request.command,
            status=status,
            decision_fields=request.decision_fields,
            suggested_values=request.suggested_values,
            interpretation_identity=request.interpretation_identity,
            message=" ".join(str(message or "").split()),
        )

    def delivery_failed(self, message: str) -> WorkflowUiHandoffResolution:
        """Return a correlated failure when terminal transport rejects delivery."""
        return WorkflowUiHandoffResolution(
            request_id=self.request_id,
            command=self.command,
            status=WorkflowUiHandoffResolutionStatus.FAILED,
            decision_fields=self.decision_fields,
            suggested_values=self.suggested_values,
            interpretation_identity=self.interpretation_identity,
            message=" ".join(str(message or "").split()),
        )


@dataclass(slots=True)
class WorkflowUiHandoffSession:
    """Bounded lifecycle for one exact UI handoff request.

    Asynchronous command scheduling is observable progress, not completion.
    Navigation terminates explicitly as unverified manual continuation because
    a panel-only route has no future correlated callback.
    """

    request: WorkflowUiHandoffRequest
    status: WorkflowUiHandoffSessionStatus = WorkflowUiHandoffSessionStatus.REQUESTED
    terminal_resolution: WorkflowUiHandoffResolution | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request, WorkflowUiHandoffRequest):
            raise TypeError("Workflow UI handoff session requires a typed request.")
        if not isinstance(self.status, WorkflowUiHandoffSessionStatus):
            raise TypeError("Workflow UI handoff session status must be typed.")

    def resolve(
        self,
        resolution: WorkflowUiHandoffResolution,
    ) -> WorkflowUiHandoffTransitionStatus:
        """Apply one exact progress or terminal result without guessing identity."""
        if not isinstance(resolution, WorkflowUiHandoffResolution):
            raise TypeError("Workflow UI handoff session resolution must be typed.")
        if not resolution.matches(self.request):
            return WorkflowUiHandoffTransitionStatus.STALE
        if self.status is WorkflowUiHandoffSessionStatus.TERMINAL:
            return WorkflowUiHandoffTransitionStatus.DUPLICATE

        if resolution.status.is_terminal:
            self.status = WorkflowUiHandoffSessionStatus.TERMINAL
            self.terminal_resolution = resolution
            return WorkflowUiHandoffTransitionStatus.TERMINATED

        next_status = {
            WorkflowUiHandoffResolutionStatus.COMMAND_PENDING: (
                WorkflowUiHandoffSessionStatus.COMMAND_PENDING
            ),
        }.get(resolution.status)
        if next_status is None:
            return WorkflowUiHandoffTransitionStatus.INVALID
        if next_status is self.status:
            return WorkflowUiHandoffTransitionStatus.DUPLICATE
        self.status = next_status
        return WorkflowUiHandoffTransitionStatus.ADVANCED
