"""RAG example policy for product-safe tool-call prompt context."""

from __future__ import annotations

import json
import logging
import math
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.llm.agent.decision_contract import MODEL_RESPONSE_TOOL_NAME
from XBrainLab.llm.agent.parser import (
    CommandParser,
    ToolEnvelopeParseResult,
    ToolEnvelopeStatus,
)

if TYPE_CHECKING:
    from XBrainLab.llm.agent.turn import AssistantPendingRequest
    from XBrainLab.llm.agent.verifier import ToolSchemaValidator

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _live_tool_schema_validator() -> ToolSchemaValidator | None:
    """Build the validator from the product tool registry, or fail closed."""
    try:
        from XBrainLab.llm.agent.verifier import (  # noqa: PLC0415
            ToolSchemaValidator,
        )
        from XBrainLab.llm.tools import get_all_tools  # noqa: PLC0415

        schemas = {tool.name: tool.parameters for tool in get_all_tools()}
        return ToolSchemaValidator(schemas)
    except Exception:
        logger.exception("RAG example policy could not load live tool schemas")
        return None


def _is_strict_json_value(value: Any) -> bool:
    """Return whether a value can appear unchanged in strict JSON output."""
    if value is None or type(value) in {bool, int, str}:
        return True
    if type(value) is float:
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_strict_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_strict_json_value(item)
            for key, item in value.items()
        )
    return False


def _parse_proposal(raw: Any) -> ToolEnvelopeParseResult | None:
    if not isinstance(raw, (dict, str)):
        return None
    if isinstance(raw, dict):
        if not _is_strict_json_value(raw):
            return None
        raw = json.dumps(raw)
    parsed = CommandParser.parse_product(raw)
    return (
        parsed
        if parsed.status in (ToolEnvelopeStatus.VALID, ToolEnvelopeStatus.NO_TOOL)
        else None
    )


def _validated_example(
    metadata: dict[str, Any] | None,
) -> tuple[dict[str, Any], AssistantPendingRequest | None] | None:
    """Validate one example and derive, never trust, its optional prior draft."""
    if not isinstance(metadata, dict):
        return None
    parsed = _parse_proposal(metadata.get("proposal"))
    if parsed is None:
        return None
    update = parsed.request
    prior = metadata.get("prior_turn")
    pending = None
    source = metadata.get("source_text")
    sources = {"U1": source} if isinstance(source, str) else {}
    validator = _live_tool_schema_validator()
    if validator is None:
        return None
    from XBrainLab.llm.agent.tool_attempt_coordinator import (  # noqa: PLC0415
        merge_parameter_changes,
    )
    from XBrainLab.llm.agent.turn import AssistantPendingRequest  # noqa: PLC0415

    def schema_for(action: str | None) -> dict | None:
        if action is None:
            return None
        if action not in AGENT_ACTION_CONTRACTS.model_tool_names():
            raise ValueError("Unsupported example action.")
        return validator.tool_schemas.get(action)

    try:
        if "prior_turn" in metadata:
            if not isinstance(prior, dict) or set(prior) != {
                "input",
                "expected_proposal",
            }:
                return None
            prior_text = prior["input"]
            if (
                not isinstance(prior_text, str)
                or not prior_text.strip()
                or not isinstance(source, str)
                or not source.strip()
            ):
                return None
            previous = _parse_proposal(prior["expected_proposal"])
            if (
                previous is None
                or previous.decision != "clarify"
                or previous.request is None
                or previous.request.mode != "replace"
            ):
                return None
            previous_update = previous.request
            prior_sources = {"U1": prior_text}
            parameters = merge_parameter_changes(
                previous_update.action,
                schema_for(previous_update.action),
                previous_update.changes,
                sources=prior_sources,
            )
            pending = AssistantPendingRequest(
                command_name=previous_update.action,
                original_turn_id="U1",
                publication_generation=None,
                parameters=tuple(parameters.items()),
                sources=tuple(prior_sources.items()),
                question=previous.message,
            )
            if (
                update is None
                or update.mode != "continue"
                or pending.command_name not in {None, update.action}
            ):
                return None
            sources = {**prior_sources, "U2": source}
        elif update is not None and update.mode != "replace":
            return None
        if update is not None:
            merged = merge_parameter_changes(
                update.action,
                schema_for(update.action),
                update.changes,
                parameters=pending.parameters if pending is not None else (),
                sources=sources,
            )
            if parsed.decision == "execute" and (
                update.action is None
                or not validator.validate(
                    update.action,
                    {name: change.value for name, change in merged.items()},
                ).is_valid
            ):
                return None
    except (ValueError, TypeError):
        return None
    proposal = parsed.proposal_dict()
    return (proposal, pending) if proposal is not None else None


def prompt_proposal_from_metadata(
    metadata: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return only a source/schema-validated proposal, never execution authority."""
    validated = _validated_example(metadata)
    return validated[0] if validated is not None else None


def example_search_text(metadata: dict[str, Any]) -> str | None:
    """Build the real product query while keeping U1/U2 evidence separate."""
    validated = _validated_example(metadata)
    source = metadata.get("source_text")
    if validated is None or not isinstance(source, str) or not source.strip():
        return None
    from XBrainLab.llm.agent.assembler import ContextAssembler  # noqa: PLC0415

    return ContextAssembler.retrieval_query(source, pending_request=validated[1])


def prompt_example_from_metadata(metadata: dict[str, Any]) -> dict[str, Any] | None:
    """Revalidate transport data and render the product's compact pending view."""
    validated = _validated_example(metadata)
    if validated is None:
        return None
    proposal, pending = validated
    source = metadata.get("source_text")
    data = {"input": source}
    if pending is not None:
        data["context"] = {
            "current_user": {"id": "U2", "text": source},
            "pending_request": pending.prompt_context(),
        }
    data["expected_proposal"] = proposal
    return data


def example_decision_name(metadata: dict[str, Any] | None) -> str | None:
    """Derive action-scoped eligibility, not whether the example executes."""
    proposal = prompt_proposal_from_metadata(metadata)
    if proposal is None:
        return None
    if proposal["action"] is not None:
        return proposal["action"]
    return MODEL_RESPONSE_TOOL_NAME


def is_primary_workflow_example(metadata: dict[str, Any] | None) -> bool:
    """Return whether an example satisfies the current source-backed contract."""
    return prompt_proposal_from_metadata(metadata) is not None
