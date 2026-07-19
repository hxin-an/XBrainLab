"""Typed capability-policy publication for one agent prompt generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS

from ..tools.application_surface import (
    TOOL_TO_COMMAND,
    ApplicationToolRuntime,
    build_agent_tool_policy,
)
from .intent import command_for_intent

DIRECT_ACTION_TOOL_NAMES: dict[str, frozenset[str]] = (
    AGENT_ACTION_CONTRACTS.direct_action_tool_names()
)


def request_scoped_tool_names(
    tool_names: set[str] | frozenset[str],
    *,
    intent: str,
    authorized_command: str | None = None,
) -> frozenset[str]:
    """Narrow capabilities to tools relevant to this model turn.

    Capability policy remains the complete backend truth. This projection only
    reduces the choices shown to the model, using either a host-authorized
    continuation command or the current user intent.
    """
    published = frozenset(tool_names)
    if intent in {"no_tool", "ask_clarification"}:
        return frozenset()

    command_name = str(authorized_command or "").strip()
    if not command_name:
        command = command_for_intent(intent)
        command_name = command.value if command is not None else ""
    if command_name:
        return frozenset(
            tool_name
            for tool_name in published
            if (
                (mapped := TOOL_TO_COMMAND.get(tool_name)) is not None
                and mapped.value == command_name
            )
        )

    direct_tools = DIRECT_ACTION_TOOL_NAMES.get(intent)
    if direct_tools is not None:
        return published.intersection(direct_tools)
    return published


PromptPolicyErrorCode = Literal[
    "publication_read_failed",
    "policy_read_failed",
    "blocked_reasons_failed",
]

_POLICY_UNAVAILABLE_MESSAGE = (
    "Backend capability policy is temporarily unavailable. Workflow actions "
    "are disabled until XBrainLab can refresh it."
)


@dataclass(frozen=True)
class StrictToolResponsePromptPolicy:
    """Canonical model-owned structured decision contract for local models."""

    max_format_recovery_attempts: int = 1

    def __post_init__(self) -> None:
        if self.max_format_recovery_attempts < 0:
            raise ValueError("max_format_recovery_attempts must be non-negative")

    def decision_instructions(self) -> str:
        """Return a compact decision contract without evaluator answer fields."""
        return (
            "STRICT RESPONSE CONTRACT - DECISION ORDER (decide silently):\n"
            "1. Find the exact requested action in the enabled tool contracts.\n"
            "- No exact matching contract: use respond_to_user with decision blocked "
            "and a specific backend blocking reason.\n"
            "- Exact match but a required parameter is absent from the latest user "
            "request and verified state: use respond_to_user with decision "
            "missing_input and name only the absent required fields.\n"
            "- Exact match and every required parameter is present: call that exact "
            "enabled tool name with only supported parameters.\n"
            "- Informational request: use respond_to_user with decision answer.\n"
            "When action_policy is present, request_category is semantic text, not a "
            "tool name. Status blocked requires respond_to_user.blocked with a listed "
            "backend reason. Status enabled permits only "
            "callable_tool_names.\n"
            "2. Never call a prerequisite or substitute for a different exact "
            "requested action. A tool being enabled does not make it relevant.\n"
            "3. Broad workflow continuation is allowed only when the user asks to "
            "continue a broader workflow and broad_continuation.allowed is true. "
            "A request naming a blocked later action is not broad continuation.\n"
            "4. Required values must come from the latest user request or verified "
            "state. Defaults satisfy optional parameters only. Never invent paths, "
            "split strategies, model settings, labels, IDs, or file names.\n"
            "5. Host confirmation is separate. For an exact enabled action with "
            "complete inputs, still propose that exact tool call. The host will "
            "request confirmation before execution; do not describe it as blocked.\n"
            "6. Return exactly one DECISION ENVELOPE. The root object must be exactly "
            '{"tool_name":"<exact enabled name>","parameters":{...}}. '
            "Never wrap it in tool-call, tool_call, action, or function. For no-tool "
            "decisions use respond_to_user and exactly one parameters branch: "
            "blocked uses exactly decision and message "
            '({"decision":"blocked","message":"reason"}); missing_input '
            "uses exactly decision, missing_inputs, and message "
            '({"decision":"missing_input","missing_inputs":["field"],'
            '"message":"question"}); answer uses exactly decision and message '
            '({"decision":"answer","message":"answer"}).\n'
            "The first non-whitespace character must be { and the last must be "
            "}. Never use a Markdown code fence or add prose outside the object."
        )

    def recovery_instructions(self) -> str:
        """Return one safe correction that does not reflect model output."""
        return (
            "FORMAT CORRECTION REQUIRED. Re-evaluate the original latest user "
            "request against the workflow mode, decision context, and enabled "
            "tools; do not merely rewrite the previous object. A backend "
            "recommendation is not user permission. Do not convert a blocked "
            "explanation or missing-input request into a tool call. Return exactly "
            "one JSON object from the original discriminated contract. The root "
            'object must be exactly {"tool_name": "<name>", "parameters": '
            "{...}}. Never wrap it in tool-call, tool_call, action, or function. "
            "Use an exact enabled tool_name and its parameters for a direct action. "
            "Otherwise use tool_name respond_to_user and exactly one parameters "
            "branch: blocked uses exactly decision and message; missing_input uses "
            "exactly decision, missing_inputs, and message; answer uses exactly "
            "decision and message. The response "
            "must begin with { and end with }, with no prose or code fence. Do "
            "not add fields from another decision branch."
        )


STRICT_TOOL_RESPONSE_PROMPT_POLICY = StrictToolResponsePromptPolicy()


@dataclass(frozen=True)
class PromptPolicyReadError:
    """Safe prompt-facing description of a capability publication failure."""

    code: PromptPolicyErrorCode
    message: str = _POLICY_UNAVAILABLE_MESSAGE

    def to_prompt_payload(self) -> dict[str, str]:
        """Return JSON-safe data without exception text or traceback details."""
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True)
class PromptPolicyReadResult:
    """One atomic backend publication and all prompt-facing policy projections."""

    publication: ApplicationViewPublication | None
    published_tools: frozenset[str]
    blocked_reasons: tuple[tuple[str, str], ...]
    publication_error: PromptPolicyReadError | None = None
    policy_applies: bool = True

    @classmethod
    def not_applicable(cls) -> PromptPolicyReadResult:
        """Represent an explicit non-product context with no backend runtime."""
        return cls(
            publication=None,
            published_tools=frozenset(),
            blocked_reasons=(),
            policy_applies=False,
        )

    @classmethod
    def failed(
        cls,
        code: PromptPolicyErrorCode,
        *,
        publication: ApplicationViewPublication | None = None,
    ) -> PromptPolicyReadResult:
        """Return a fail-closed result for any publication projection failure."""
        return cls(
            publication=publication,
            published_tools=frozenset(),
            blocked_reasons=(),
            publication_error=PromptPolicyReadError(code=code),
        )

    @property
    def backend_generation(self) -> int | None:
        """Return the generation shared by state, tools, and blockers."""
        return self.publication.generation if self.publication is not None else None

    def blocked_reason_map(self) -> dict[str, str]:
        """Return a copy so prompt filtering cannot mutate the publication."""
        return dict(self.blocked_reasons)

    def to_prompt_payload(self) -> dict[str, Any]:
        """Serialize the prompt policy contract without backend implementation data."""
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
    """Read one backend generation and derive all prompt policy data from it.

    A missing runtime is supported only for explicit non-product contexts. Once
    a runtime exists, every failure discards all mapped tools so the model never
    receives permissions without matching blocker and publication evidence.
    """
    if runtime is None:
        return PromptPolicyReadResult.not_applicable()

    try:
        publication = runtime.get_view_publication()
    except Exception:
        return PromptPolicyReadResult.failed("publication_read_failed")
    if not isinstance(publication, ApplicationViewPublication):
        return PromptPolicyReadResult.failed("publication_read_failed")

    try:
        policy = build_agent_tool_policy(
            study_state,
            publication=publication,
            runtime=runtime,
        )
        published_tools = frozenset(
            tool_name
            for tool_name, availability in policy.items()
            if availability.enabled
        )
    except Exception:
        return PromptPolicyReadResult.failed(
            "policy_read_failed",
            publication=publication,
        )

    try:
        blocked = {
            availability.command_name or availability.tool_name: reason
            for availability in policy.values()
            if not availability.enabled
            and (reason := str(availability.reason_text).strip())
        }
    except Exception:
        return PromptPolicyReadResult.failed(
            "blocked_reasons_failed",
            publication=publication,
        )

    return PromptPolicyReadResult(
        publication=publication,
        published_tools=published_tools,
        blocked_reasons=tuple(sorted(blocked.items())),
    )
