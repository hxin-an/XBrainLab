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
            "STRICT RESPONSE CONTRACT\n"
            "Return one JSON object with exactly tool_name and parameters. "
            "No prose, wrappers or Markdown.\n"
            "Read current_user.text. Choose the response for THIS request:\n"
            "- Information or explanation: respond_to_user with an English answer. "
            "Mentioned operations and numbers are not requests to execute.\n"
            "- Prohibition: respond_to_user and acknowledge that you will not "
            "perform the prohibited action. Do not call it, even when all "
            "parameter values are present. Do not ask for its missing values. "
            "If the user also asks a question, answer it; do not stop at "
            "acknowledging the prohibition.\n"
            "- Requested action with missing or unclear required values: "
            "respond_to_user, name ALL missing values and ask the user to "
            "restate the complete request: the operation and all required "
            "values together, including values already supplied. If one cutoff "
            "is supplied, ask for "
            "the other; if neither is supplied, ask for both. Do not call the "
            "action with empty, guessed or partial parameters.\n"
            "- One complete, enabled action requested: return its listed "
            "tool_name and the user's complete parameters, not a promise to act.\n"
            "- Unavailable action: respond_to_user with its listed blocker; "
            "do not substitute an action or perform prerequisites.\n"
            "For multiple requested actions or an explanation plus a requested "
            "action, ask which to do first. A prohibited action is not a "
            "requested action. "
            "Explaining a prohibited action is one answer, not two actions. "
            "Never partially execute.\n"
            "For respond_to_user, message is your reply to the user. Write your "
            "own reply, not a copy of the user's request.\n"
            "Each turn is independent. Never fill values from examples, history, "
            "application state or defaults. No draft is saved: a bare value or "
            "'same as before' is not a complete action request.\n"
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
            "tool_name and parameters. Follow the same response choices above: "
            "respond_to_user for questions, prohibitions or missing values; "
            "call an action only when requested, complete and enabled. "
            "Do not output both an action and a reply, or several action objects. "
            "For one requested action, return only its action object, without "
            "a separate acknowledgement. If the user requests multiple actions, "
            "return one respond_to_user object asking which to do first; "
            "do not choose or execute just the first. "
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
