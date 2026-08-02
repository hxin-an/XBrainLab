"""Detached ApplicationService reads used by the Preprocess UI."""

from __future__ import annotations

from typing import Any

from XBrainLab.backend.application import QueryStateCommand
from XBrainLab.backend.application.errors import ApplicationError
from XBrainLab.backend.application.preprocess_render import (
    DEFAULT_PREPROCESS_PREVIEW_SECONDS,
    PreprocessRenderPublication,
    PreprocessRenderRequest,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.application_capabilities import (
    execute_application_command,
    get_application_view_publication,
    get_preprocess_render_publication,
)

PREPROCESS_RENDER_DATA_UNAVAILABLE_MESSAGE = (
    "Preprocess preview is unavailable because application state could not be read."
)


class PreprocessRenderDataUnavailableError(RuntimeError):
    """Raised when the UI cannot obtain one authoritative render publication."""


def query_preprocess_render(
    context: Any,
    *,
    channel_index: int,
    start_seconds: float,
    duration_seconds: float = DEFAULT_PREPROCESS_PREVIEW_SECONDS,
) -> PreprocessRenderPublication | None:
    """Return one bounded detached signal publication for the active view."""
    view = get_application_view_publication(context)
    if view is None or not bool(getattr(view, "usable", False)):
        return None
    request = PreprocessRenderRequest(
        publication_generation=view.generation,
        channel_index=max(0, int(channel_index)),
        start_seconds=max(0.0, float(start_seconds)),
        duration_seconds=float(duration_seconds),
    )
    try:
        publication = get_preprocess_render_publication(context, request)
    except ApplicationError as error:
        raise PreprocessRenderDataUnavailableError(str(error)) from error
    except Exception as error:
        logger.error("Preprocess render publication failed.", exc_info=True)
        raise PreprocessRenderDataUnavailableError(
            PREPROCESS_RENDER_DATA_UNAVAILABLE_MESSAGE,
        ) from error
    if publication is None:
        return None
    return publication


def query_preprocess_data_rows(
    context: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
    """Return detached current/original aggregate rows for form validation."""
    result = execute_application_command(
        context,
        QueryStateCommand(query="data_lists"),
        refresh=False,
    )
    if result is None:
        return None
    if result.failed:
        return [], []
    diagnostics = result.diagnostics
    current = diagnostics.get("preprocessed_rows")
    original = diagnostics.get("raw_rows")
    return (
        [dict(row) for row in current if isinstance(row, dict)]
        if isinstance(current, list)
        else [],
        [dict(row) for row in original if isinstance(row, dict)]
        if isinstance(original, list)
        else [],
    )
