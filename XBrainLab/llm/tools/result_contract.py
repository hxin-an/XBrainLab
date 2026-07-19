"""Typed results shared by assistant tools and their host controller."""

from __future__ import annotations

import logging
import os
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from XBrainLab.backend.application.results import CommandResult


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

_EMAIL_PATTERN = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)
_SECRET_NAME = (
    r"(?:[a-z0-9]+[_-])*"  # noqa: S105 - secret-field matching regex
    r"(?:api[\s_-]*key|access[\s_-]*token|"
    r"auth(?:entication|orization)?[\s_-]*token|authorization|"
    r"bearer[\s_-]*token|hf[\s_-]*token|client[\s_-]*secret|"
    r"private[\s_-]*key|secret[\s_-]*key|password|passwd|token|secret)"
)
_JSON_SECRET_ASSIGNMENT_PATTERN = re.compile(
    rf"""(?ix)
    (?P<key_escape>\\?)
    (?P<quote>["'])
    {_SECRET_NAME}
    (?P=key_escape)
    (?P=quote)
    \s*:\s*
    (?:bearer\s+)?
    (?:
        (?P<value_escape>\\?)
        (?P<value_quote>["'])
        [^"'\r\n]*
        (?P=value_escape)
        (?P=value_quote)
        |
        [^\s,;}}\]]+
    )
    """,
)
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    rf"""(?ix)
    (?<![\w])
    {_SECRET_NAME}
    \s*(?::|=|%3d)\s*
    (?:bearer\s+)?
    (?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;&]+)
    """,
)
_BEARER_SECRET_PATTERN = re.compile(
    r"(?i)(?<![\w])bearer\s+[a-z0-9._~+/=-]+",
)
_TOKEN_LITERAL_PATTERN = re.compile(
    r"(?i)(?<![\w])(?:hf_[a-z0-9_-]{8,}|sk-[a-z0-9_-]{8,}|"
    r"github_pat_[a-z0-9_]{8,}|gh[pousr]_[a-z0-9]{8,})(?![\w])",
)
_SECRET_KEY_PATTERN = re.compile(rf"(?i)^{_SECRET_NAME}$")
_QUOTED_PATH_PATTERN = re.compile(
    r"""(?P<quote>["'`])"""
    r"""(?:[A-Za-z]:[\\/]|\\\\|//|/)"""
    r"""[^"'`\r\n]*"""
    r"""(?P=quote)""",
)
_ENV_PATH_PATTERN = re.compile(
    r"""(?ix)
    (?:
        \$HOME
        |
        %USERPROFILE%
    )
    [\\/][^\s,;:)\]}]+
    """,
)
_UNC_PATH_PATTERN = re.compile(
    r"(?<![\w:])(?:\\\\|//)[^\\/\s,;]+[\\/][^\s,;)\]}]+",
)
_WINDOWS_PATH_PATTERN = re.compile(
    r"(?<![\w])(?:[A-Za-z]:[\\/])[^\s,;)\]}]+",
)
_POSIX_PATH_PATTERN = re.compile(
    r"(?<![\w:/])/(?!/)[^\s,;:)\]}]+",
)


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
    text = str(value)
    text = _JSON_SECRET_ASSIGNMENT_PATTERN.sub("[REDACTED_SECRET]", text)
    text = _SECRET_ASSIGNMENT_PATTERN.sub("[REDACTED_SECRET]", text)
    text = _BEARER_SECRET_PATTERN.sub("[REDACTED_SECRET]", text)
    text = _TOKEN_LITERAL_PATTERN.sub("[REDACTED_SECRET]", text)
    text = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    text = _ENV_PATH_PATTERN.sub("[REDACTED_PATH]", text)
    text = _QUOTED_PATH_PATTERN.sub("[REDACTED_PATH]", text)
    text = _UNC_PATH_PATTERN.sub("[REDACTED_PATH]", text)
    text = _WINDOWS_PATH_PATTERN.sub("[REDACTED_PATH]", text)
    return _POSIX_PATH_PATTERN.sub("[REDACTED_PATH]", text)


def _public_safe_value(value: Any, *, field_name: str | None = None) -> Any:
    if field_name is not None and _SECRET_KEY_PATTERN.fullmatch(field_name):
        return "[REDACTED_SECRET]"
    if isinstance(value, str):
        return redact_public_text(value)
    if isinstance(value, os.PathLike):
        return "[REDACTED_PATH]"
    if isinstance(value, Enum):
        return _public_safe_value(value.value, field_name=field_name)
    if isinstance(value, Mapping):
        return {
            key: _public_safe_value(
                item,
                field_name=str(key),
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_public_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_public_safe_value(item) for item in value)
    if isinstance(value, set):
        return {_public_safe_value(item) for item in value}
    return value


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
    safe_state = _public_safe_value(state)
    safe_capability = _public_safe_value(capability)
    safe_diagnostics = _public_safe_value(diagnostics or {})
    return PublicSafeResultProjection(
        message=redact_public_text(message),
        blocked_reason=(
            redact_public_text(blocked_reason) if blocked_reason is not None else None
        ),
        raw_result=_public_safe_value(raw_result),
        state=safe_state if isinstance(safe_state, dict) else None,
        capability=(safe_capability if isinstance(safe_capability, dict) else None),
        diagnostics=(safe_diagnostics if isinstance(safe_diagnostics, dict) else {}),
    )


def redact_developer_error_detail(value: object) -> str:
    """Redact common private values before writing bounded developer detail."""
    text = redact_public_text(value).replace("\r", " ").replace("\n", " ")
    return text[:500] or type(value).__name__


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
        type(error).__name__,
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
        if getattr(publication, "usable", False) is not True:
            return unavailable
        state_value = getattr(publication, "state", None)
        state_serializer = getattr(state_value, "to_dict", None)
        state = state_serializer() if callable(state_serializer) else None
        if not isinstance(state, dict):
            safe_unexpected_failure(
                developer_logger,
                TypeError("Application publication state is not serializable"),
                boundary=boundary,
                operation=operation,
            )
            return unavailable
        generation = getattr(publication, "generation", None)
        return FailureStateRecovery(
            state=state,
            changed_state={"state_unknown": False},
            diagnostics={
                "state_source": "authoritative_publication",
                "publication_generation": generation,
                "refresh_required": False,
            },
        )
    except Exception as error:
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
        if not self.ok:
            object.__setattr__(self, "message", redact_public_text(self.message))


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
    """Preserve one backend command result in the assistant tool contract."""
    return ToolResult(
        ok=result.ok,
        message=message if message is not None else result.message,
        payload=dict(result.diagnostics),
        error_type=result.error_type.value,
        recoverable=result.recoverable,
        command_name=result.command_name,
        state=(
            result.state.to_dict()
            if hasattr(result.state, "to_dict")
            else dict(result.state)
            if isinstance(result.state, dict)
            else None
        ),
        diagnostics=dict(result.diagnostics),
        changed_state=result.changed_state.to_dict(),
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
            **dict(diagnostics or {}),
        },
        changed_state=dict(changed_state or {}),
    )
