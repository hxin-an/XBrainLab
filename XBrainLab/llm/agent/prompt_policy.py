"""Strict model response contract and atomic backend publication reader."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.backend.utils.public_diagnostics import (
    PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER,
    DiagnosticTextLayout,
    public_diagnostic_text,
)

from ..tools.application_surface import (
    ApplicationToolRuntime,
    build_agent_tool_policy,
)

PromptPolicyErrorCode = Literal["publication_read_failed"]
_MAX_BLOCKED_REASON_UTF8_BYTES = 512

_POLICY_UNAVAILABLE_MESSAGE = (
    "Backend workflow state is temporarily unavailable. Workflow actions "
    "are disabled until XBrainLab can refresh it."
)


def _bounded_public_reason(value: str) -> str:
    """Return one single-line, public-safe prompt reason with a hard byte cap."""
    reason = public_diagnostic_text(
        value,
        layout=DiagnosticTextLayout.SINGLE_LINE,
    ).strip()
    encoded = reason.encode("utf-8")
    if len(encoded) <= _MAX_BLOCKED_REASON_UTF8_BYTES:
        return reason
    marker = PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER.encode("utf-8")
    prefix = encoded[: _MAX_BLOCKED_REASON_UTF8_BYTES - len(marker)].decode(
        "utf-8",
        errors="ignore",
    )
    return f"{prefix.rstrip()}{PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER}"


@dataclass(frozen=True)
class StrictToolResponsePromptPolicy:
    """Canonical model-owned structured decision contract for local models."""

    max_format_recovery_attempts: int = 1

    def __post_init__(self) -> None:
        if self.max_format_recovery_attempts < 0:
            raise ValueError("max_format_recovery_attempts must be non-negative")

    def decision_instructions(self) -> str:
        """Separate permission to act from completeness of the user's values."""
        return (
            """Choose one response for current_user.text, in this order:
1. Information or explanation requests and prohibitions are not permission to
   act. Choose respond_to_user to answer or acknowledge them. Polite requests
   to perform an action, even when phrased as questions, are action requests:
   continue with steps 2-4.
2. For a requested action, check the callable list. If absent or unavailable,
   choose respond_to_user and explain why. Do not invent a tool, substitute
   another action, or perform prerequisite actions instead.
3. For an available action, check its required parameters. If any required
   value is missing or unclear in the current request, choose respond_to_user:
   name all missing values and ask for the complete request again, including
   values already supplied. Never fill gaps with null, empty values, defaults,
   state or examples.
   Optional parameters may be omitted. Zero-parameter tools need no values:
   opening a dialog does not require the values the user will enter inside it.
4. For a complete request to an available action, choose that action with only
   its defined parameters. A message promising to act does not execute it.
   The application handles any required confirmation; do not ask again first.
Each turn is independent: no draft or history supplies missing values. A bare
value or 'same as before' is not a complete request. For multiple requested
actions, or an explanation plus a requested action, ask which to do first;
never partially execute. Explaining a prohibited action is one answer: answer
the question and acknowledge the prohibition without treating it as an action.
Opening a dialog does not complete its operation. Never report completion
without a trusted tool result; starting training is not completion, and asking
to stop is not stopped. Write your own English reply, not a copy of the request;
use plain English instead of internal tool names in message.
Return exactly one JSON object with only tool_name and parameters. No prose,
Markdown or comments outside it. Only respond_to_user uses a message parameter.
"""
            "\nRemember: Check each required value against the current request. "
            "A partly supplied operation is still incomplete: ask for the missing "
            "value, without borrowing one from a reference. When every required "
            "value is supplied, use the tool. An enabled dialog needs no form "
            "values: return its action, not a reply promising to open it.\n"
        )

    def recovery_instructions(self) -> str:
        """One fixed correction; do not reflect malformed model output."""
        return (
            "FORMAT CORRECTION REQUIRED. Re-evaluate the current user request "
            "using the same backend tools. Return one JSON object with exactly "
            "tool_name and parameters. Follow the same response choices above: "
            "respond_to_user for questions, prohibitions or missing values; "
            "call an action only when requested, complete and enabled. "
            "No prose, wrappers or code fences."
        )


STRICT_TOOL_RESPONSE_PROMPT_POLICY = StrictToolResponsePromptPolicy()


@dataclass(frozen=True)
class PromptPolicyReadError:
    """Safe prompt-facing description of a publication read failure."""

    code: PromptPolicyErrorCode
    message: str = _POLICY_UNAVAILABLE_MESSAGE


@dataclass(frozen=True)
class PromptPolicyReadResult:
    """One atomic backend publication for prompt stage and state projection."""

    publication: ApplicationViewPublication | None
    published_tools: frozenset[str] = frozenset()
    blocked_reasons: tuple[tuple[str, str], ...] = ()
    publication_error: PromptPolicyReadError | None = None
    policy_applies: bool = True

    @classmethod
    def not_applicable(cls) -> PromptPolicyReadResult:
        return cls(publication=None, policy_applies=False)

    @classmethod
    def failed(cls) -> PromptPolicyReadResult:
        return cls(
            publication=None,
            publication_error=PromptPolicyReadError("publication_read_failed"),
        )

    @property
    def backend_generation(self) -> int | None:
        return self.publication.generation if self.publication is not None else None

    def blocked_reason_map(self) -> dict[str, str]:
        return dict(self.blocked_reasons)


def read_prompt_policy(
    study_state: Any,
    *,
    runtime: ApplicationToolRuntime | None,
) -> PromptPolicyReadResult:
    """Read one publication and project its existing agent capability policy."""
    if runtime is None:
        return PromptPolicyReadResult.not_applicable()
    try:
        publication = runtime.get_view_publication()
    except Exception:
        return PromptPolicyReadResult.failed()
    if not isinstance(publication, ApplicationViewPublication):
        return PromptPolicyReadResult.failed()
    try:
        tool_policy = build_agent_tool_policy(
            study_state,
            publication=publication,
            runtime=runtime,
        )
    except Exception:
        return PromptPolicyReadResult.failed()
    return PromptPolicyReadResult(
        publication=publication,
        published_tools=frozenset(
            tool_name
            for tool_name, availability in tool_policy.items()
            if availability.enabled
        ),
        blocked_reasons=tuple(
            sorted(
                (tool_name, reason)
                for tool_name, availability in tool_policy.items()
                if not availability.enabled
                and (reason := _bounded_public_reason(availability.reason_text))
            )
        ),
    )
