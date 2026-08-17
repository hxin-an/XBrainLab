"""Typed capability-policy publication for one agent prompt generation."""

from __future__ import annotations

import re
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
from .training_request import (
    contains_explicit_training_options,
    extract_explicit_training_model,
)

DIRECT_ACTION_TOOL_NAMES: dict[str, frozenset[str]] = (
    AGENT_ACTION_CONTRACTS.direct_action_tool_names()
)
_PROMPT_ACTION_AUTHORIZATION_PREFIX = "prompt_action:"
_NAVIGATION_PATTERNS = (
    r"\b(?:go|move|navigate|switch)\s+(?:to\s+)?(?:the\s+)?"
    r"(?:next\s+)?(?:workflow\s+)?(?:workspace\s+)?panel\b",
    r"\b(?:open|show)\s+(?:the\s+)?(?:workflow\s+)?(?:workspace\s+)?panel\b",
    r"(?:前往|切換|開啟|顯示).{0,12}(?:面板|畫面)",
)
_PREPROCESS_CLARIFICATION = (
    "Should I run the standard preprocessing pipeline, or apply one specific "
    "operation? Name one operation such as band-pass filtering, notch filtering, "
    "resampling, normalization, referencing, or channel selection."
)
_PREPROCESS_OPERATION_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "apply_bandpass_filter",
        (
            r"\bband[ -]?pass\b",
            r"\b\d+(?:\.\d+)?\s*(?:-|to)\s*\d+(?:\.\d+)?\s*hz\s+filter\b",
            r"帶通",
        ),
    ),
    (
        "apply_notch_filter",
        (r"\bnotch\b", r"\b(?:power|line)\s+noise\b", r"陷波"),
    ),
    (
        "resample_data",
        (r"\bresampl", r"\bsampling\s+rate\b", r"重新取樣", r"重採樣"),
    ),
    (
        "normalize_data",
        (r"\bnormaliz", r"\bz[ -]?score\b", r"\bmin[ -]?max\b", r"正規化"),
    ),
    (
        "set_reference",
        (r"\bre-?referenc", r"\baverage\s+reference\b", r"重新參考"),
    ),
    (
        "select_channels",
        (
            r"\b(?:select|keep|drop)\s+(?:the\s+)?channels?\b",
            r"通道選擇",
            r"選擇通道",
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class PromptActionSelection:
    """One host-selected model-visible action or a clarification boundary."""

    tool_name: str | None = None
    action_name: str | None = None
    clarification_message: str = ""

    def __post_init__(self) -> None:
        if self.tool_name and self.clarification_message:
            raise ValueError("Prompt action cannot both run and ask for clarification.")
        if bool(self.tool_name) != bool(self.action_name):
            raise ValueError("Prompt tool and action identities must be paired.")

    @property
    def requires_clarification(self) -> bool:
        return bool(self.clarification_message)


def classify_prompt_action(text: str, command_name: str) -> PromptActionSelection:
    """Choose one semantically exact schema for an admitted backend command."""
    normalized = " ".join(str(text or "").casefold().split())
    if any(re.search(pattern, normalized) for pattern in _NAVIGATION_PATTERNS):
        return PromptActionSelection(
            tool_name="switch_panel",
            action_name="navigate",
        )
    if command_name == "configure_training":
        names_model = extract_explicit_training_model(normalized) is not None
        tool_name = (
            "set_model"
            if names_model and not contains_explicit_training_options(normalized)
            else "configure_training"
        )
        return PromptActionSelection(
            tool_name=tool_name,
            action_name=command_name,
        )

    if command_name != "preprocess":
        return PromptActionSelection()

    standard_pipeline = bool(
        re.search(
            r"\b(?:standard|default|full)\s+"
            r"(?:preprocess(?:ing)?|pipeline)\b",
            normalized,
        )
        or re.search(
            r"\b(?:preprocess(?:ing)?|pipeline)\s+defaults?\b",
            normalized,
        )
        or any(
            marker in normalized
            for marker in ("標準前處理", "預設前處理", "完整前處理", "前處理預設值")
        )
    )
    matching_tools = {
        tool_name
        for tool_name, patterns in _PREPROCESS_OPERATION_PATTERNS
        if any(re.search(pattern, normalized) for pattern in patterns)
    }
    if standard_pipeline:
        return PromptActionSelection(
            tool_name="apply_standard_preprocess",
            action_name=command_name,
        )
    if len(matching_tools) == 1:
        return PromptActionSelection(
            tool_name=next(iter(matching_tools)),
            action_name=command_name,
        )
    return PromptActionSelection(clarification_message=_PREPROCESS_CLARIFICATION)


def prompt_action_authorization(*, command_name: str, tool_name: str) -> str:
    """Bind one host-selected prompt tool to its backend command."""
    normalized_command = str(command_name or "").strip()
    normalized_tool = str(tool_name or "").strip()
    mapped_command = TOOL_TO_COMMAND.get(normalized_tool)
    direct_action_match = normalized_tool in DIRECT_ACTION_TOOL_NAMES.get(
        normalized_command,
        frozenset(),
    )
    if not normalized_command or (mapped_command is None and not direct_action_match):
        raise ValueError("Prompt action authorization requires a mapped tool.")
    if mapped_command is not None and mapped_command.value != normalized_command:
        raise ValueError(
            f"Prompt tool {normalized_tool} does not implement {normalized_command}."
        )
    payload = f"{normalized_command}:{normalized_tool}"
    return f"{_PROMPT_ACTION_AUTHORIZATION_PREFIX}{payload}"


def backend_command_from_prompt_authorization(value: str | None) -> str | None:
    """Return the host action carried by a prompt-only authorization."""
    normalized = str(value or "").strip()
    if not normalized.startswith(_PROMPT_ACTION_AUTHORIZATION_PREFIX):
        return normalized or None
    payload = normalized.removeprefix(_PROMPT_ACTION_AUTHORIZATION_PREFIX)
    command_name, separator, tool_name = payload.partition(":")
    mapped_command = TOOL_TO_COMMAND.get(tool_name)
    direct_action_match = tool_name in DIRECT_ACTION_TOOL_NAMES.get(
        command_name,
        frozenset(),
    )
    if (
        not separator
        or not command_name
        or (
            not direct_action_match
            and (mapped_command is None or mapped_command.value != command_name)
        )
    ):
        return None
    return command_name


def _prompt_authorized_tool(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    if not normalized.startswith(_PROMPT_ACTION_AUTHORIZATION_PREFIX):
        return None
    payload = normalized.removeprefix(_PROMPT_ACTION_AUTHORIZATION_PREFIX)
    command_name, separator, tool_name = payload.partition(":")
    mapped_command = TOOL_TO_COMMAND.get(tool_name)
    direct_action_match = tool_name in DIRECT_ACTION_TOOL_NAMES.get(
        command_name,
        frozenset(),
    )
    if not separator or (
        not direct_action_match
        and (mapped_command is None or mapped_command.value != command_name)
    ):
        return None
    return tool_name


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
    prompt_tool = _prompt_authorized_tool(command_name)
    if prompt_tool is not None:
        return frozenset({prompt_tool}).intersection(published)
    if command_name.startswith(_PROMPT_ACTION_AUTHORIZATION_PREFIX):
        return frozenset()
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

    max_format_recovery_attempts: int = 2

    def __post_init__(self) -> None:
        if self.max_format_recovery_attempts < 0:
            raise ValueError("max_format_recovery_attempts must be non-negative")

    def decision_instructions(
        self,
        workflow_stage: str = "<exact backend workflow_stage>",
    ) -> str:
        """Return a compact decision contract without evaluator answer fields."""
        return (
            "STRICT RESPONSE CONTRACT - DECISION ORDER (decide silently):\n"
            "1. Find the exact requested action in the enabled tool contracts.\n"
            "- No exact matching contract: use respond_to_user with a specific "
            "backend blocking reason.\n"
            "- Exact match but a required parameter is absent from the latest user "
            "request and verified state: use respond_to_user to ask only for the "
            "absent required values.\n"
            "- Exact match and every required parameter is present: call that exact "
            "enabled tool name with only supported parameters.\n"
            "- Informational request: use respond_to_user with a concise answer.\n"
            "When action_policy is present, request_category is semantic text, not a "
            "tool name. Status blocked requires respond_to_user with a listed backend "
            "reason. Status enabled permits only "
            "callable_tool_names.\n"
            "2. Never call a prerequisite or substitute for a different exact "
            "requested action. A tool being enabled does not make it relevant.\n"
            "3. Broad workflow continuation is allowed only when the user asks to "
            "continue a broader workflow and broad_continuation.allowed is true. "
            "A request naming a blocked later action is not broad continuation.\n"
            "4. Required values must come from the latest user request or verified "
            "state. Defaults satisfy optional parameters only. Never invent paths, "
            "split strategies, model settings, labels, IDs, or file names. Copy "
            "every supported value explicitly stated in the latest user request, "
            "even when the schema marks it optional. Never omit an explicitly "
            "requested supported value.\n"
            "5. Host confirmation is separate. For an exact enabled action with "
            "complete inputs, still propose that exact tool call. The host will "
            "request confirmation before execution; do not describe it as blocked.\n"
            "6. Return exactly one DECISION ENVELOPE. The root object must be exactly "
            '{"workflow_stage":"'
            + workflow_stage
            + '","tool_name":"<exact enabled name>","parameters":{...}}. '
            "Never wrap it in tool-call, tool_call, action, or function. For no-tool "
            "decisions use respond_to_user with parameters containing exactly message. "
            "The workflow_stage value above is a required acknowledgement of the "
            "backend publication, not permission to change state.\n"
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
            'object must be exactly {"workflow_stage": "<exact backend '
            'workflow_stage>", "tool_name": "<name>", "parameters": {...}}. '
            "Never wrap it in tool-call, tool_call, action, or function. "
            "Use an exact enabled tool_name and its parameters for a direct action. "
            "Otherwise use tool_name respond_to_user with parameters containing "
            "exactly message. Copy the current backend workflow_stage exactly. The "
            "response "
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
