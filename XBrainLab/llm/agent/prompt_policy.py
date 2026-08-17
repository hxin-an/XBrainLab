"""Strict model response contract and atomic backend publication reader."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from XBrainLab.backend.application.view_publication import ApplicationViewPublication

from ..tools.application_surface import ApplicationToolRuntime

PromptPolicyErrorCode = Literal["publication_read_failed"]

_POLICY_UNAVAILABLE_MESSAGE = (
    "Backend workflow state is temporarily unavailable. Workflow actions "
    "are disabled until XBrainLab can refresh it."
)


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
            "STRICT RESPONSE CONTRACT - DECISION ORDER (decide silently):\n"
            "1. Find the exact requested action in the backend-stage-published "
            "tool contracts.\n"
            "- No exact matching contract or an informational request: use "
            "respond_to_user with a concise message.\n"
            "- Exact match but a required parameter is absent from the latest user "
            "request or verified state: use respond_to_user to ask only for it.\n"
            "- Exact match with complete inputs: call that exact enabled tool with "
            "only supported parameters.\n"
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
            "6. Return exactly one DECISION ENVELOPE. The root object must be exactly "
            '{"workflow_stage":"'
            + workflow_stage
            + '","tool_name":"<exact enabled name>","parameters":{...}}. '
            "Never wrap it in tool-call, tool_call, action, or function. For a "
            "no-tool decision use respond_to_user with parameters containing "
            "exactly message. workflow_stage acknowledges the backend publication; "
            "it does not grant permission.\n"
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
            "respond_to_user with parameters containing exactly message. Copy "
            "workflow_stage exactly. Add no prose or code fence: begin with { and "
            "end with }. Never wrap it in tool-call, tool_call, action, or function. "
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
    """Read exactly one ApplicationService publication without Host projection."""
    del study_state
    if runtime is None:
        return PromptPolicyReadResult.not_applicable()
    try:
        publication = runtime.get_view_publication()
    except Exception:
        return PromptPolicyReadResult.failed()
    if not isinstance(publication, ApplicationViewPublication):
        return PromptPolicyReadResult.failed()
    return PromptPolicyReadResult(publication=publication)
