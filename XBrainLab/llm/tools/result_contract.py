"""Typed results shared by assistant tools and their host controller."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from XBrainLab.backend.application.results import CommandResult
from XBrainLab.backend.application.state import ApplicationStateSnapshot
from XBrainLab.backend.application.view_publication import (
    ApplicationViewPublication,
)
from XBrainLab.backend.utils.public_diagnostics import (
    PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER,
    PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER,
    DiagnosticTextLayout,
    public_diagnostic_text,
    public_diagnostic_value,
    safe_exception_type_name,
)


@dataclass(frozen=True)
class ToolBoundaryFailure:
    """Stable machine-readable failure at a tool execution boundary."""

    code: str
    message: str
    recovery_action: str
    error_type: str = "contract"
    recoverable: bool = False


APPLICATION_TOOL_RUNTIME_REQUIRED_FAILURE = ToolBoundaryFailure(
    code="application_tool_runtime_required",
    message="ApplicationToolRuntime is required for mapped product tool execution.",
    recovery_action="provide_application_tool_runtime",
)

SAFE_UNEXPECTED_FAILURE_CODE = "unexpected_tool_failure"
SAFE_UNEXPECTED_FAILURE_MESSAGE = (
    "The assistant tool could not complete the action. "
    "Refresh application state before retrying."
)
SAFE_UNEXPECTED_FAILURE_RECOVERY_ACTION = "refresh_application_state"


@dataclass(frozen=True, slots=True)
class SafeUnexpectedFailure:
    """Public-safe failure metadata paired with one redacted incident log."""

    incident_id: str
    error_code: str = SAFE_UNEXPECTED_FAILURE_CODE
    message: str = SAFE_UNEXPECTED_FAILURE_MESSAGE
    recovery_action: str = SAFE_UNEXPECTED_FAILURE_RECOVERY_ACTION
    error_type: str = "runtime"
    recoverable: bool = False

    @property
    def diagnostics(self) -> dict[str, str]:
        """Return the only incident metadata safe for product/model feedback."""
        return {"incident_id": self.incident_id}


@dataclass(frozen=True, slots=True)
class PublicSafeResultProjection:
    """Redacted result fields safe for UI, logs, history, and model feedback."""

    message: str
    blocked_reason: str | None
    raw_result: Any
    state: dict[str, Any] | None
    capability: dict[str, Any] | None
    diagnostics: dict[str, Any]


@dataclass(frozen=True, slots=True)
class FailureStateRecovery:
    """Authoritative state evidence recovered after an unexpected failure."""

    state: dict[str, Any] | None
    changed_state: dict[str, bool]
    diagnostics: dict[str, Any]


class ApplicationPublicationReader(Protocol):
    """Minimal runtime surface needed for post-failure state recovery."""

    def get_view_publication(self) -> Any: ...


def redact_public_text(value: object) -> str:
    """Keep domain guidance while removing credentials and local paths."""
    return public_diagnostic_text(value)


def _public_safe_value(value: Any, *, field_name: str | None = None) -> Any:
    return public_diagnostic_value(value, field_name=field_name)


def public_safe_result_projection(
    *,
    message: object,
    blocked_reason: object | None = None,
    raw_result: Any = None,
    state: dict[str, Any] | None = None,
    capability: dict[str, Any] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> PublicSafeResultProjection:
    """Project one result onto fields safe for every public consumer."""
    safe_envelope = _public_safe_value(
        {
            "message": message,
            "blocked_reason": blocked_reason,
            "raw_result": raw_result,
            "state": state,
            "capability": capability,
            "diagnostics": diagnostics if type(diagnostics) is dict else {},
        }
    )
    if type(safe_envelope) is not dict:
        safe_envelope = {}
    safe_message = safe_envelope.get(
        "message",
        PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER,
    )
    safe_blocked_reason = safe_envelope.get("blocked_reason")
    safe_state = safe_envelope.get("state")
    safe_capability = safe_envelope.get("capability")
    safe_diagnostics = safe_envelope.get("diagnostics")
    return PublicSafeResultProjection(
        message=(
            safe_message
            if type(safe_message) is str
            else redact_public_text(safe_message)
        ),
        blocked_reason=(
            safe_blocked_reason if type(safe_blocked_reason) is str else None
        ),
        raw_result=safe_envelope.get(
            "raw_result",
            PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER,
        ),
        state=safe_state if type(safe_state) is dict else None,
        capability=(safe_capability if type(safe_capability) is dict else None),
        diagnostics=(safe_diagnostics if type(safe_diagnostics) is dict else {}),
    )


def redact_developer_error_detail(value: object) -> str:
    """Redact common private values before writing bounded developer detail."""
    text = public_diagnostic_text(
        value,
        layout=DiagnosticTextLayout.SINGLE_LINE,
    )
    return text[:500] or PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER


def safe_unexpected_failure(
    developer_logger: logging.Logger,
    error: BaseException,
    *,
    boundary: str,
    operation: str,
) -> SafeUnexpectedFailure:
    """Create one safe failure and write only redacted developer diagnostics."""
    failure = SafeUnexpectedFailure(incident_id=uuid.uuid4().hex)
    developer_logger.error(
        "Unexpected tool failure incident=%s boundary=%s operation=%s "
        "exception_type=%s detail=%s",
        failure.incident_id,
        redact_developer_error_detail(boundary),
        redact_developer_error_detail(operation),
        safe_exception_type_name(error),
        redact_developer_error_detail(error),
    )
    return failure


def recover_authoritative_failure_state(
    runtime: ApplicationPublicationReader | None,
    developer_logger: logging.Logger,
    *,
    operation: str,
    boundary: str,
) -> FailureStateRecovery:
    """Read post-execution state once, otherwise require a conservative refresh."""
    unavailable = FailureStateRecovery(
        state=None,
        changed_state={"state_unknown": True},
        diagnostics={
            "state_source": "unavailable",
            "refresh_required": True,
        },
    )
    if runtime is None:
        return unavailable
    try:
        publication = runtime.get_view_publication()
        if type(publication) is not ApplicationViewPublication:
            safe_unexpected_failure(
                developer_logger,
                TypeError("Application publication has an unsupported type"),
                boundary=boundary,
                operation=operation,
            )
            return unavailable
        if (
            type(publication.verified) is not bool
            or type(publication.stale) is not bool
            or not publication.verified
            or publication.stale
        ):
            return unavailable
        state_value = publication.state
        state = (
            state_value.to_dict()
            if type(state_value) is ApplicationStateSnapshot
            else None
        )
        if type(state) is not dict:
            safe_unexpected_failure(
                developer_logger,
                TypeError("Application publication state is not serializable"),
                boundary=boundary,
                operation=operation,
            )
            return unavailable
        generation = (
            publication.generation if type(publication.generation) is int else None
        )
        return FailureStateRecovery(
            state=state,
            changed_state={"state_unknown": False},
            diagnostics={
                "state_source": "authoritative_publication",
                "publication_generation": generation,
                "refresh_required": False,
            },
        )
    except BaseException as error:
        safe_unexpected_failure(
            developer_logger,
            error,
            boundary=boundary,
            operation=operation,
        )
        return unavailable


@dataclass(frozen=True)
class ToolResult:
    """Explicit success/failure envelope for non-ApplicationService tools."""

    ok: bool
    message: str
    payload: Any = None
    error_type: str = "none"
    recoverable: bool = True
    command_name: str | None = None
    error_code: str | None = None
    recovery_action: str | None = None
    state: dict[str, Any] | None = None
    capability: dict[str, Any] | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    changed_state: dict[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if type(self.ok) is not bool:
            object.__setattr__(self, "ok", False)
        if type(self.message) is not str:
            object.__setattr__(
                self,
                "message",
                PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER,
            )
        for field_name in (
            "error_type",
            "command_name",
            "error_code",
            "recovery_action",
        ):
            value = getattr(self, field_name)
            if value is not None and type(value) is not str:
                object.__setattr__(
                    self,
                    field_name,
                    "internal" if field_name == "error_type" else None,
                )
        if type(self.recoverable) is not bool:
            object.__setattr__(self, "recoverable", False)
        if not self.ok:
            projection = public_safe_result_projection(
                message=self.message,
                raw_result=self.payload,
                state=self.state,
                capability=self.capability,
                diagnostics=(
                    self.diagnostics if type(self.diagnostics) is dict else {}
                ),
            )
            object.__setattr__(self, "message", projection.message)
            object.__setattr__(self, "payload", projection.raw_result)
            object.__setattr__(self, "state", projection.state)
            object.__setattr__(self, "capability", projection.capability)
            object.__setattr__(self, "diagnostics", projection.diagnostics)
        for field_name in ("state", "capability"):
            value = getattr(self, field_name)
            if value is not None and type(value) is not dict:
                object.__setattr__(self, field_name, None)
        for field_name in ("diagnostics", "changed_state"):
            value = getattr(self, field_name)
            if type(value) is not dict:
                object.__setattr__(self, field_name, {})
        safe_changed_state = public_diagnostic_value(self.changed_state)
        object.__setattr__(
            self,
            "changed_state",
            safe_changed_state if type(safe_changed_state) is dict else {},
        )


class UiRequestKind(str, Enum):
    """UI effects a worker-side tool may request from the GUI host."""

    SWITCH_PANEL = "switch_panel"
    CONFIRM_MONTAGE = "confirm_montage"


@dataclass(frozen=True)
class UiRequest:
    """Structured request for an existing GUI surface or interaction."""

    kind: UiRequestKind
    params: dict[str, Any] = field(default_factory=dict)


ToolExecutionResult = ToolResult | UiRequest
"""Only result envelopes that a concrete assistant tool may return."""


def tool_result_from_command(
    result: CommandResult,
    *,
    message: str | None = None,
) -> ToolResult:
    """Project one backend result onto the assistant's public tool contract."""
    public = result.to_public_dict()
    public_state = public.get("state")
    public_diagnostics = public.get("diagnostics")
    public_changed_state = public.get("changed_state")
    public_message = public.get("message")
    public_error_type = public.get("error_type")
    return ToolResult(
        ok=result.ok,
        message=(
            public_diagnostic_text(message)
            if type(message) is str
            else public_message
            if type(public_message) is str
            else PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER
        ),
        payload=(
            dict.copy(public_diagnostics) if type(public_diagnostics) is dict else {}
        ),
        error_type=(
            public_error_type if type(public_error_type) is str else "internal"
        ),
        recoverable=result.recoverable,
        command_name=result.command_name,
        state=public_state if type(public_state) is dict else None,
        diagnostics=(
            dict.copy(public_diagnostics) if type(public_diagnostics) is dict else {}
        ),
        changed_state=(
            dict.copy(public_changed_state)
            if type(public_changed_state) is dict
            else {}
        ),
    )


def runtime_tool_failure(
    message: str,
    error: Exception,
    *,
    developer_logger: logging.Logger | None = None,
    command_name: str | None = None,
    capability: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
    changed_state: dict[str, bool] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> ToolResult:
    """Build a redacted typed result for an unexpected tool adapter error."""
    failure = safe_unexpected_failure(
        developer_logger or logging.getLogger(__name__),
        error,
        boundary="real_tool_adapter",
        operation=message,
    )
    public_diagnostics = (
        public_diagnostic_value(diagnostics) if type(diagnostics) is dict else {}
    )
    return ToolResult(
        ok=False,
        message=failure.message,
        error_type=failure.error_type,
        recoverable=failure.recoverable,
        error_code=failure.error_code,
        recovery_action=failure.recovery_action,
        command_name=command_name,
        state=state,
        capability=capability,
        diagnostics={
            **failure.diagnostics,
            **(public_diagnostics if type(public_diagnostics) is dict else {}),
        },
        changed_state=(dict.copy(changed_state) if type(changed_state) is dict else {}),
    )
