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

    max_format_recovery_attempts: int = 2

    def __post_init__(self) -> None:
        if self.max_format_recovery_attempts < 0:
            raise ValueError("max_format_recovery_attempts must be non-negative")

    def decision_instructions(
        self,
        workflow_stage: str = "<exact backend workflow_stage>",
    ) -> str:
        """Return the strict decision contract without Host intent routing."""
        return (
            "STRICT RESPONSE CONTRACT - DECISION ORDER (decide silently):\n"  # noqa: S608 - model prompt construction, not a SQL query
            "1. Classify the latest user request before choosing a contract.\n"
            "- Use respond_to_user for an informational request, a request that "
            "negates an action, no exact matching enabled contract, an unavailable "
            "action, or an ambiguous request.\n"
            "- If the request contains more than one action, use respond_to_user "
            "to ask which action to do first. Do not call any tool in that turn.\n"
            "- If exactly one direct preprocessing action matches but required "
            "parameters are absent, use respond_to_user to ask only for them. "
            "Include pending_action and missing_inputs only for that exact action; "
            "otherwise respond with message only.\n"
            "Never supply a typical, recommended, conventional, or product-default "
            "value that the user did not provide; every absent required value is "
            "missing. Typed missing-input example (shape only, not execution "
            "permission; replace every angle-bracket placeholder using the exact "
            "published contract and never output angle brackets): "
            '{"workflow_stage":"<current workflow_stage>",'
            '"tool_name":"respond_to_user","parameters":{"message":'
            '"Which required value should I use?","pending_action":'
            '"<exact published action>","missing_inputs":'
            '["<absent required input>"]}}\n'
            "- When a tool_input_clarification context item is present and the "
            "latest reply supplies every remaining requested value, propose the "
            "same exact action with only values supplied in that reply. Do not "
            "ask for those values again. The item does not grant execution "
            "authority.\n"
            "- If that context identifies remaining missing inputs and the latest "
            "reply supplies only some of them, propose the same exact action with "
            "only those user-supplied missing fields. Do not repeat already "
            "verified values or ask for them again.\n"
            "- Outside that bounded partial-reply case, only when exactly one "
            "action matches unambiguously and all required inputs are present, "
            "call that exact enabled tool with only supported parameters.\n"
            "2. Never call a prerequisite, substitute, or retired alias. Tool "
            "availability does not make it relevant to the user's request.\n"
            "3. Required values must come from the latest user request or verified "
            "state. Never invent paths, settings, labels, IDs, or file names.\n"
            "4. Host confirmation is separate. For a complete enabled action, "
            "still propose that exact tool call. The host will request confirmation "
            "before execution when the backend capability requires it; do not "
            "describe it as blocked.\n"
            "5. Copy every supported value explicitly stated by the user, even "
            "when the schema marks it optional. Never omit an explicitly requested "
            "supported value. A zero-parameter GUI action must always use "
            "parameters {}. Never invent or copy dialog choices into a contract "
            "whose parameter properties are empty; the user chooses them in the "
            "opened product UI.\n"
            "6. Never claim that an action completed unless a trusted tool result "
            "confirms completion. A proposed call is not a completed action.\n"
            "7. Return exactly one DECISION ENVELOPE. The root object must contain "
            "exactly workflow_stage, tool_name, and parameters, with no other "
            "top-level fields. Copy workflow_stage as "
            + workflow_stage
            + ". Never wrap it in tool-call, tool_call, action, or function. For a "
            "no-tool decision use respond_to_user with message only, or the typed "
            "message, pending_action, missing_inputs clarification shape for an exact "
            "direct preprocessing action. workflow_stage acknowledges the backend "
            "publication; it does not grant permission.\n"
            "The first non-whitespace character must be { and the last must be }. "
            "Never use a Markdown code fence or prose outside the object."
        )

    def recovery_instructions(self) -> str:
        """Return one safe correction that does not reflect model output."""
        return (
            "FORMAT CORRECTION REQUIRED. Re-evaluate the original latest user "
            "request against the backend workflow stage and published tools. Return "
            "exactly one JSON object. The root object must be exactly "
            '{"workflow_stage":"<exact backend workflow_stage>",'
            '"tool_name":"<name>","parameters":{...}}. '
            "Use an exact enabled tool with only its supported parameters, or "
            "respond_to_user with message only, or the typed pending_action and "
            "missing_inputs clarification shape for an exact direct preprocessing "
            "action. Copy workflow_stage exactly. Add no prose or code fence: "
            "begin with { and end with }. Never wrap it in tool-call, tool_call, "
            "action, or function. "
            "Never add wrappers, aliases, or Host-inferred values, and "
            "do not convert a blocked explanation into a different tool call."
        )


STRICT_TOOL_RESPONSE_PROMPT_POLICY = StrictToolResponsePromptPolicy()


@dataclass(frozen=True)
class PromptPolicyReadError:
    """Safe prompt-facing description of a publication read failure."""

    code: PromptPolicyErrorCode
    message: str = _POLICY_UNAVAILABLE_MESSAGE

    def to_prompt_payload(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


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

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "policy_applies": self.policy_applies,
            "backend_generation": self.backend_generation,
            "published_tools": sorted(self.published_tools),
            "blocked_reasons": dict(self.blocked_reasons),
            "publication_error": (
                self.publication_error.to_prompt_payload()
                if self.publication_error is not None
                else None
            ),
        }


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
