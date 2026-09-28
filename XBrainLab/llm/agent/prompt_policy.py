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
        """Describe one independent complete request, without saved parameters."""
        return (
            "STRICT RESPONSE CONTRACT\n"
            "Return one JSON object with exactly tool_name and parameters. "
            "No prose, wrappers or Markdown.\n"
            "Read current_user.text as the current request. Each turn is independent: "
            "never fill missing parameters from chat history, application state, "
            "examples or guesses.\n"
            "For one clear, complete, enabled action, use its listed tool_name "
            "and complete parameters now, not a promise to act.\n"
            "If any required value is missing or ambiguous, use respond_to_user "
            "with parameters containing only a non-empty English message. "
            "Name the missing information and ask the user to restate the complete "
            "request. No draft is saved; a bare value or reference to an earlier "
            "request is not a complete request.\n"
            "For information or a prohibition, use respond_to_user to answer "
            "without executing. For an unavailable action, explain its listed "
            "blocker; do not substitute another action.\n"
            "For multiple actions or an explanation plus an action, ask which "
            "to do first. Never partially execute or do unrequested prerequisites.\n"
            "Zero-parameter GUI actions use parameters={}; choices are made in "
            "the dialog. Opening a dialog does not complete the operation.\n"
            "Host confirmation is separate; never report completion without a "
            "trusted tool result. Starting training is not training completion; "
            "requesting stop is not stopped.\n"
            "Tool names are internal; use plain English in message.\n"
        )

    def recovery_instructions(self) -> str:
        """One fixed correction; do not reflect malformed model output."""
        return (
            "FORMAT CORRECTION REQUIRED. Re-evaluate the current user request "
            "using the same backend tools. Return one JSON object with exactly "
            "tool_name and parameters. For a reply or missing information, use "
            "respond_to_user with parameters containing only a non-empty message; "
            "ask for a complete request if values are missing. Do not invent values "
            "or substitute an action for a blocker. No prose, wrappers or code fences."
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
