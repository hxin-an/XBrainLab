"""Service-backed data-list queries used by Preprocess UI rendering."""

from __future__ import annotations

from typing import Any

from XBrainLab.backend.application import QueryStateCommand
from XBrainLab.ui.application_capabilities import (
    execute_application_command,
    local_result_payload,
)


def query_preprocess_render_lists(context: Any) -> tuple[list[Any], list[Any]] | None:
    """Return current/original data lists, or None for compatibility mock fallback."""
    result = execute_application_command(
        context,
        QueryStateCommand(query="data_lists", include_objects=True),
        refresh=False,
    )
    if result is None:
        return None
    if result.failed:
        return [], []
    payload = local_result_payload(result)
    preprocessed = payload.get("preprocessed_data_list")
    loaded = payload.get("loaded_data_list")
    return (
        list(preprocessed) if isinstance(preprocessed, list) else [],
        list(loaded) if isinstance(loaded, list) else [],
    )
