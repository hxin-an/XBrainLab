"""Stable user-facing presentation for unexpected UI exceptions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Never

from PyQt6.QtWidgets import QMessageBox

from XBrainLab.backend.utils.logger import logger


@dataclass(frozen=True)
class _UnexpectedErrorPresentation:
    title: str
    message: str
    log_message: str


class UnexpectedErrorContext(Enum):
    """Product contexts with distinct recovery guidance for unexpected failures."""

    APPLICATION_UNEXPECTED = _UnexpectedErrorPresentation(
        title="XBrainLab encountered a problem",
        message=(
            "XBrainLab encountered an unexpected problem. Review the current "
            "workflow state and try the action again."
        ),
        log_message="Unexpected application failure",
    )
    TRAINING_START = _UnexpectedErrorPresentation(
        title="Training could not start",
        message=(
            "XBrainLab could not start training because of an unexpected problem. "
            "Review the training settings and try again."
        ),
        log_message="Unexpected failure while starting training",
    )
    TRAINING_DATA_SPLITTING = _UnexpectedErrorPresentation(
        title="Data Splitting Failed",
        message=(
            "XBrainLab could not create the training datasets because of an "
            "unexpected problem. Review the data splitting settings and try again."
        ),
        log_message="Unexpected failure while creating training datasets",
    )
    TRAINING_HISTORY_CLEAR = _UnexpectedErrorPresentation(
        title="Training history could not be cleared",
        message=(
            "XBrainLab could not clear the training history. "
            "Close any open training result views and try again."
        ),
        log_message="Unexpected failure while clearing training history",
    )
    DATA_IMPORT = _UnexpectedErrorPresentation(
        title="Data import could not continue",
        message=(
            "XBrainLab could not continue the data import because of an unexpected "
            "problem. Reopen the source and try again."
        ),
        log_message="Unexpected failure during Data Import",
    )
    DATA_IMPORT_REVIEW = _UnexpectedErrorPresentation(
        title="Import review unavailable",
        message=(
            "The current Data Import review could not be opened safely. "
            "Start a new import review and try again."
        ),
        log_message="Unexpected failure while opening the Data Import review",
    )
    DATA_INTERPRETATION_REVIEW = _UnexpectedErrorPresentation(
        title="Interpretation review failed",
        message=(
            "XBrainLab could not prepare the Data Import review. "
            "Reopen the source and try again."
        ),
        log_message="Unexpected failure while preparing a Data Import review",
    )
    DATA_INTERPRETATION_PREVIEW = _UnexpectedErrorPresentation(
        title="Interpretation preview failed",
        message=(
            "XBrainLab could not update the Data Import preview. "
            "Review the selected files and try again."
        ),
        log_message="Unexpected failure while updating a Data Import preview",
    )
    DATA_INTERPRETATION_VALIDATION = _UnexpectedErrorPresentation(
        title="Interpretation validation failed",
        message=(
            "XBrainLab could not validate the Data Import choices. "
            "Review the selections and try again."
        ),
        log_message="Unexpected failure while validating Data Import choices",
    )
    DATA_INTERPRETATION_APPLY = _UnexpectedErrorPresentation(
        title="Interpretation apply failed",
        message=(
            "XBrainLab could not apply the reviewed import. "
            "Reopen the review and try again."
        ),
        log_message="Unexpected failure while applying a Data Import review",
    )
    DATA_IMPORT_RECIPE_RELOAD = _UnexpectedErrorPresentation(
        title="Recipe reload failed",
        message=(
            "XBrainLab could not reload the import recipe. "
            "Check that the recipe is still available, then try again."
        ),
        log_message="Unexpected failure while reloading a Data Import recipe",
    )
    DATA_IMPORT_RECIPE_SAVE = _UnexpectedErrorPresentation(
        title="Recipe save failed",
        message=(
            "XBrainLab could not save the import recipe. "
            "Choose another location and try again."
        ),
        log_message="Unexpected failure while saving a Data Import recipe",
    )
    LABEL_IMPORT = _UnexpectedErrorPresentation(
        title="Label Import Failed",
        message=(
            "XBrainLab could not apply the selected labels. "
            "Review the label files and mapping, then try again."
        ),
        log_message="Unexpected failure while importing labels",
    )


def present_unexpected_error(
    parent: Any,
    context: UnexpectedErrorContext,
    *,
    error_info: tuple[Any, ...] | None = None,
    message_box: Any = QMessageBox,
    title: str | None = None,
) -> str:
    """Log technical details and show only stable recovery guidance."""
    presentation = context.value
    if error_info is None:
        logger.error(presentation.log_message, exc_info=True)
    else:
        _log_worker_error(presentation.log_message, error_info)
    message_box.critical(
        parent,
        title or presentation.title,
        presentation.message,
    )
    return presentation.message


def _log_worker_error(log_message: str, error_info: tuple[Any, ...]) -> None:
    error_type = error_info[0] if error_info else RuntimeError
    error_value = error_info[1] if len(error_info) > 1 else error_info
    formatted_traceback = str(error_info[2]) if len(error_info) > 2 else ""
    if not isinstance(error_value, Exception):
        type_name = getattr(error_type, "__name__", str(error_type))
        error_value = RuntimeError(f"{type_name}: {error_value}")

    try:
        _raise_for_logging(error_value)
    except Exception:
        logger.error(
            "%s\nOriginal worker traceback:\n%s",
            log_message,
            formatted_traceback or "Traceback was not provided.",
            exc_info=True,
        )


def _raise_for_logging(error: Exception) -> Never:
    raise error
