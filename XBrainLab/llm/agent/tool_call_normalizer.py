"""Preserve strict model tool calls without host intent substitution."""

from __future__ import annotations

from typing import Any


def normalize_tool_call(
    tool_name: str,
    params: dict[str, Any],
    *,
    latest_user_text: str = "",
    published_tool_names: frozenset[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return the exact proposal for schema and capability verification.

    Stable v2 does not rename tools, infer missing scientific values, drop extra
    fields, or substitute another command from user prose. The strict verifier
    owns all rejection and bounded-repair decisions after this identity step.
    """
    del latest_user_text, published_tool_names
    return tool_name, dict(params)
