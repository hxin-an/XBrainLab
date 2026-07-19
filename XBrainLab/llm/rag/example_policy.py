"""RAG example policy for product-safe tool-call prompt context."""

from __future__ import annotations

import json
import logging
import math
from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from XBrainLab.llm.agent.verifier import ToolSchemaValidator

logger = logging.getLogger(__name__)

LEGACY_COMPATIBILITY_TOOLS = frozenset(
    {
        "load_data",
        "attach_labels",
        "import_labels",
    }
)


@lru_cache(maxsize=1)
def _live_tool_schema_validator() -> ToolSchemaValidator | None:
    """Build the validator from the product tool registry, or fail closed."""
    try:
        from XBrainLab.llm.agent.verifier import (  # noqa: PLC0415
            ToolSchemaValidator,
        )
        from XBrainLab.llm.tools import get_all_tools  # noqa: PLC0415

        schemas = {tool.name: tool.parameters for tool in get_all_tools(mode="real")}
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


def tool_calls_from_metadata(metadata: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return normalized tool-call metadata from RAG payload metadata."""
    if not metadata:
        return []
    raw = metadata.get("tool_calls")
    if raw is None:
        raw = metadata.get("expected_tool_calls")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
    else:
        parsed = raw
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def tool_name_from_call(call: dict[str, Any]) -> str:
    """Return the best-effort tool name from known RAG tool-call shapes."""
    raw_name = (
        call.get("tool_name")
        or call.get("name")
        or call.get("tool")
        or call.get("command")
    )
    if raw_name:
        return str(raw_name)
    function = call.get("function")
    if isinstance(function, dict):
        return str(function.get("name") or "")
    return ""


def prompt_tool_call_from_metadata(
    metadata: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return one strict product-envelope example or reject the metadata.

    Few-shot output must teach the same two-key, one-action shape enforced by
    ``CommandParser.parse_product``. Legacy, multi-action, malformed, and
    explanation-bearing examples are unsuitable for the product prompt.
    """
    calls = tool_calls_from_metadata(metadata)
    if len(calls) != 1:
        return None
    call = calls[0]
    if set(call) != {"tool_name", "parameters"}:
        return None
    tool_name = call.get("tool_name")
    parameters = call.get("parameters")
    if (
        not isinstance(tool_name, str)
        or not tool_name.strip()
        or tool_name != tool_name.strip()
        or not isinstance(parameters, dict)
        or tool_name in LEGACY_COMPATIBILITY_TOOLS
        or not _is_strict_json_value(parameters)
    ):
        return None
    validator = _live_tool_schema_validator()
    if validator is None:
        return None
    try:
        if not validator.validate(tool_name, parameters).is_valid:
            return None
    except Exception:
        logger.debug(
            "RAG example tool-schema validation failed for %s",
            tool_name,
            exc_info=True,
        )
        return None
    return {"tool_name": tool_name, "parameters": parameters}


def is_primary_workflow_example(metadata: dict[str, Any] | None) -> bool:
    """Return whether a RAG example is safe for primary product prompting."""
    return prompt_tool_call_from_metadata(metadata) is not None
