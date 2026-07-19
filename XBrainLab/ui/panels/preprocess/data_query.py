"""Service-backed data-list queries used by Preprocess UI rendering."""

from __future__ import annotations

from typing import Any

from XBrainLab.backend.application import QueryStateCommand
from XBrainLab.ui.application_capabilities import (
    execute_application_command,
    local_result_payload,
)

PREPROCESS_RENDER_DATA_UNAVAILABLE_MESSAGE = (
    "Preprocess preview is unavailable because application state could not be read."
)


class PreprocessRenderDataUnavailableError(RuntimeError):
    """Raised when the UI cannot obtain one authoritative render publication."""


def query_preprocess_render_lists(
    context: Any,
    *,
    require_available: bool = False,
) -> tuple[list[Any], list[Any]] | None:
    """Return current/original objects from one ApplicationService query.

    ``require_available`` is used by product renderers that must fail closed.
    The default preserves the temporary panel compatibility boundary while it
    is migrated independently.
    """
    result = execute_application_command(
        context,
        QueryStateCommand(query="data_lists", include_objects=True),
        refresh=False,
    )
    if result is None:
        if require_available:
            raise PreprocessRenderDataUnavailableError(
                PREPROCESS_RENDER_DATA_UNAVAILABLE_MESSAGE,
            )
        return None
    if result.failed:
        if require_available:
            reason = result.error_message or result.message
            raise PreprocessRenderDataUnavailableError(reason)
        return [], []
    payload = local_result_payload(result)
    preprocessed = payload.get("preprocessed_data_list")
    loaded = payload.get("loaded_data_list")
    if require_available and not (
        isinstance(preprocessed, list) and isinstance(loaded, list)
    ):
        raise PreprocessRenderDataUnavailableError(
            "Preprocess application state did not publish both data lists.",
        )
    return (
        list(preprocessed) if isinstance(preprocessed, list) else [],
        list(loaded) if isinstance(loaded, list) else [],
    )
