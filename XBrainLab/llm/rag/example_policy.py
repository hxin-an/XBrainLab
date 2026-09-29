"""Validate complete single-turn RAG examples, never execution authority."""

from __future__ import annotations

import json
import logging
import math
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.llm.agent.parser import CommandParser, ToolEnvelopeStatus
from XBrainLab.llm.agent.verifier import verify_direct_parameter_origins

if TYPE_CHECKING:
    from XBrainLab.llm.agent.verifier import ToolSchemaValidator

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _live_tool_schema_validator() -> ToolSchemaValidator | None:
    """Use the product schemas, failing closed when unavailable."""
    try:
        from XBrainLab.llm.agent.verifier import ToolSchemaValidator  # noqa: PLC0415
        from XBrainLab.llm.tools import get_all_tools  # noqa: PLC0415

        return ToolSchemaValidator(
            {tool.name: tool.parameters for tool in get_all_tools()}
        )
    except Exception:
        logger.exception("RAG example policy could not load live tool schemas")
        return None


def _is_strict_json_value(value: Any) -> bool:
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


def prompt_proposal_from_metadata(
    metadata: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Require the exact current wire and current-input parameter provenance."""
    if not isinstance(metadata, dict) or "prior_turn" in metadata:
        return None
    source = metadata.get("source_text")
    if not isinstance(source, str) or not source.strip():
        return None
    raw = metadata.get("proposal")
    if isinstance(raw, dict):
        if not _is_strict_json_value(raw):
            return None
        raw = json.dumps(raw)
    if not isinstance(raw, str):
        return None
    parsed = CommandParser.parse_product(raw)
    if parsed.status is ToolEnvelopeStatus.NO_TOOL:
        return parsed.proposal_dict()
    if parsed.status is not ToolEnvelopeStatus.VALID or parsed.command is None:
        return None
    action, parameters = parsed.command
    if action not in AGENT_ACTION_CONTRACTS.model_tool_names():
        return None
    validator = _live_tool_schema_validator()
    if (
        validator is None
        or not validator.validate(action, parameters).is_valid
        or not verify_direct_parameter_origins(action, parameters, source).is_valid
    ):
        return None
    return parsed.proposal_dict()


def example_search_text(metadata: dict[str, Any]) -> str | None:
    """Index only the complete current question; there is no prior-turn merge."""
    if prompt_proposal_from_metadata(metadata) is None:
        return None
    return metadata["source_text"]


def prompt_example_from_metadata(metadata: dict[str, Any]) -> dict[str, Any] | None:
    proposal = prompt_proposal_from_metadata(metadata)
    if proposal is None:
        return None
    return {"input": metadata["source_text"], "expected_proposal": proposal}


def example_decision_name(metadata: dict[str, Any] | None) -> str | None:
    proposal = prompt_proposal_from_metadata(metadata)
    return proposal["tool_name"] if proposal is not None else None


def is_primary_workflow_example(metadata: dict[str, Any] | None) -> bool:
    return prompt_proposal_from_metadata(metadata) is not None
