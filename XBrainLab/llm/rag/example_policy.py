"""RAG example policy for product-safe tool-call prompt context."""

from __future__ import annotations

import json
from typing import Any

LEGACY_COMPATIBILITY_TOOLS = frozenset(
    {
        "load_data",
        "attach_labels",
        "import_labels",
    }
)


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


def is_primary_workflow_example(metadata: dict[str, Any] | None) -> bool:
    """Return whether a RAG example is safe for primary product prompting."""
    for call in tool_calls_from_metadata(metadata):
        tool_name = tool_name_from_call(call)
        if tool_name in LEGACY_COMPATIBILITY_TOOLS:
            return False
    return True
