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
    safe_envelope = public_diagnostic_value(
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


class UiRequestKind(str, Enum):
    """UI effects a worker-side tool may request from the GUI host."""

    SWITCH_PANEL = "switch_panel"
    WORKFLOW_HANDOFF = "workflow_handoff"


@dataclass(frozen=True)
class UiRequest:
    """Structured request for an existing GUI surface or interaction."""

    kind: UiRequestKind
    params: dict[str, Any] = field(default_factory=dict)


_PUBLIC_TOOL_IDENTIFIER_MAX_BYTES = 1024
_PUBLIC_TOOL_MESSAGE_MAX_BYTES = 64 * 1024
_PUBLIC_TOOL_METADATA_MAX_BYTES = 4096


def _bounded_public_text(value: str, max_bytes: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    marker = PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER.encode("utf-8")
    prefix = encoded[: max(0, max_bytes - len(marker))].decode(
        "utf-8",
        errors="ignore",
    )
    return f"{prefix}{PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER}"


def _public_text_field(
    value: object,
    *,
    max_bytes: int,
    fallback: str,
    layout: DiagnosticTextLayout = DiagnosticTextLayout.SINGLE_LINE,
) -> str:
    if type(value) is not str:
        return fallback
    return _bounded_public_text(
        public_diagnostic_text(
            value,
            layout=layout,
        ),
        max_bytes,
    )


def _public_optional_text_field(
    value: object,
    *,
    max_bytes: int = _PUBLIC_TOOL_METADATA_MAX_BYTES,
) -> str | None:
    if value is None or type(value) is not str:
        return None
    return _public_text_field(value, max_bytes=max_bytes, fallback="")


def _public_changed_state_field(value: object) -> dict[str, bool]:
    if type(value) is not dict:
        return {}
    projected = public_diagnostic_value(value)
    if type(projected) is not dict:
        return {}
    return {
        key: item
        for key, item in dict.items(projected)
        if type(key) is str and type(item) is bool
    }


@dataclass(frozen=True)
class ToolCommandResult:
    """Agent-facing structured result for ApplicationService-backed tools."""

    ok: bool
    tool_name: str
    message: str
    command_name: str | None = None
    raw_result: Any = None
    error_type: str | None = None
    error_code: str | None = None
    recovery_action: str | None = None
    recoverable: bool = True
    blocked_reason: str | None = None
    state: dict[str, Any] | None = None
    capability: dict[str, Any] | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    changed_state: dict[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", self.ok if type(self.ok) is bool else False)
        object.__setattr__(
            self,
            "tool_name",
            _public_text_field(
                self.tool_name,
                max_bytes=_PUBLIC_TOOL_IDENTIFIER_MAX_BYTES,
                fallback=PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER,
            ),
        )
        object.__setattr__(
            self,
            "command_name",
            _public_optional_text_field(
                self.command_name,
                max_bytes=_PUBLIC_TOOL_IDENTIFIER_MAX_BYTES,
            ),
        )
        object.__setattr__(
            self,
            "message",
            _public_text_field(
                self.message,
                max_bytes=_PUBLIC_TOOL_MESSAGE_MAX_BYTES,
                fallback=PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER,
                layout=DiagnosticTextLayout.PRESERVE_LINES,
            ),
        )
        for field_name in ("error_type", "error_code", "recovery_action"):
            object.__setattr__(
                self,
                field_name,
                _public_optional_text_field(getattr(self, field_name)),
            )
        object.__setattr__(
            self,
            "recoverable",
            self.recoverable if type(self.recoverable) is bool else False,
        )
        object.__setattr__(
            self,
            "blocked_reason",
            _public_optional_text_field(
                self.blocked_reason,
                max_bytes=_PUBLIC_TOOL_MESSAGE_MAX_BYTES,
            ),
        )
        object.__setattr__(
            self,
            "changed_state",
            _public_changed_state_field(self.changed_state),
        )
        if self.ok is True:
            return
        projection = public_safe_result_projection(
            message=self.message,
            blocked_reason=self.blocked_reason,
        )
        object.__setattr__(self, "message", projection.message)
        object.__setattr__(self, "blocked_reason", projection.blocked_reason)

    def __str__(self) -> str:
        return self.message

    @classmethod
    def failure(
        cls,
        tool_name: str,
        message: str,
        command_name: str | None = None,
        state: dict[str, Any] | None = None,
        capability: dict[str, Any] | None = None,
        raw_result: Any = None,
        error_type: str = "runtime",
        error_code: str | None = None,
        recovery_action: str | None = None,
        recoverable: bool = True,
        diagnostics: dict[str, Any] | None = None,
        changed_state: dict[str, bool] | None = None,
    ) -> ToolCommandResult:
        """Build a failed structured tool result."""
        return cls(
            ok=False,
            tool_name=tool_name,
            command_name=command_name,
            message=message,
            raw_result=raw_result,
            error_type=error_type,
            error_code=error_code,
            recovery_action=recovery_action,
            recoverable=recoverable,
            state=state,
            capability=capability,
            diagnostics=(dict.copy(diagnostics) if type(diagnostics) is dict else {}),
            changed_state=(
                dict.copy(changed_state) if type(changed_state) is dict else {}
            ),
        )

    @classmethod
    def from_command_result(
        cls,
        tool_name: str,
        result: CommandResult,
        capability: dict[str, Any] | None = None,
    ) -> ToolCommandResult:
        """Convert a backend :class:`CommandResult` into an agent result."""
        return cls(
            ok=result.ok,
            tool_name=tool_name,
            command_name=result.command_name,
            message=result.message,
            raw_result=result.to_dict(),
            error_type=result.error_type.value,
            recoverable=result.recoverable,
            blocked_reason=result.error_message if result.failed else None,
            state=(
                result.state.to_dict()
                if hasattr(result.state, "to_dict")
                else dict(result.state)
                if isinstance(result.state, dict)
                else None
            ),
            capability=capability,
            diagnostics=result.diagnostics,
            changed_state=result.changed_state.to_dict(),
        )
