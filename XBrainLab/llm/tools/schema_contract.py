"""Prompt-facing tool schema helpers for local tool-call planning."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.llm.tools.base import BaseTool

TOOL_TAXONOMY: dict[str, str] = AGENT_ACTION_CONTRACTS.taxonomy()


def tool_contract_for_llm(
    tool: BaseTool,
) -> dict[str, Any]:
    """Return a compact, schema-constrained tool definition for the LLM."""
    payload: dict[str, Any] = {
        "name": tool.name,
        "taxonomy": TOOL_TAXONOMY.get(tool.name, "Workflow"),
        "description": tool.description,
        "parameters": strict_prompt_parameters(tool.parameters),
    }
    return payload


def strict_prompt_parameters(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize a JSON-like tool schema for prompt-visible tool contracts.

    The runtime verifier still validates the actual arguments. This helper
    makes the schema shown to local models explicit about object boundaries so
    the prompt resembles structured-output/function-call contracts.
    """
    normalized = deepcopy(schema)
    _normalize_object_schema(normalized)
    return normalized


def _normalize_object_schema(schema: dict[str, Any]) -> None:
    if schema.get("type") != "object":
        return

    properties = schema.get("properties")
    if isinstance(properties, dict):
        schema.setdefault("additionalProperties", False)
        for property_schema in properties.values():
            if isinstance(property_schema, dict):
                _normalize_object_schema(property_schema)
                _normalize_array_schema(property_schema)
    else:
        schema.setdefault("properties", {})
        schema.setdefault("additionalProperties", False)


def _normalize_array_schema(schema: dict[str, Any]) -> None:
    if schema.get("type") != "array":
        return
    items = schema.get("items")
    if isinstance(items, dict):
        _normalize_object_schema(items)
        _normalize_array_schema(items)
