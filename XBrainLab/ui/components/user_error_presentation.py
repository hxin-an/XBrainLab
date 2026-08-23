"""Stable user-facing presentation for unexpected UI exceptions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Never

from XBrainLab.backend.utils.logger import logger
from XBrainLab.ui.components.modal_presentation import AlertSeverity, show_alert


class _UnexpectedErrorSeverity(Enum):
    CRITICAL = "critical"
    WARNING = "warning"


@dataclass(frozen=True)
class _UnexpectedErrorPresentation:
    title: str
    message: str
    log_message: str
    severity: _UnexpectedErrorSeverity = _UnexpectedErrorSeverity.CRITICAL


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
    LABEL_IMPORT_PREVIEW = _UnexpectedErrorPresentation(
        title="Label preview failed",
        message=(
            "XBrainLab could not inspect the selected label files. "
            "Review the files and try again."
        ),
        log_message="Unexpected failure while previewing label files",
    )
    PREPROCESS_EXECUTION = _UnexpectedErrorPresentation(
        title="Preprocessing could not be applied",
        message=(
            "XBrainLab could not apply preprocessing because of an unexpected "
            "problem. Review the preprocessing settings and try again."
        ),
        log_message="Unexpected failure while applying preprocessing",
    )
    PREPROCESS_RESET = _UnexpectedErrorPresentation(
        title="Preprocessing could not be reset",
        message=(
            "XBrainLab could not reset preprocessing because of an unexpected "
            "problem. Review the current workflow state and try again."
        ),
        log_message="Unexpected failure while resetting preprocessing",
    )
    TRAINING_MODEL_SETTINGS = _UnexpectedErrorPresentation(
        title="Model settings could not be applied",
        message=(
            "XBrainLab could not apply the model settings because of an unexpected "
            "problem. Review the model parameters and selected weights, then try again."
        ),
        log_message="Unexpected failure while applying model settings",
        severity=_UnexpectedErrorSeverity.WARNING,
    )
    TRAINING_OPTIMIZER_SETTINGS = _UnexpectedErrorPresentation(
        title="Optimizer settings could not be applied",
        message=(
            "XBrainLab could not apply the optimizer settings because of an "
            "unexpected problem. Review the optimizer parameters and try again."
        ),
        log_message="Unexpected failure while applying optimizer settings",
        severity=_UnexpectedErrorSeverity.WARNING,
    )
    TRAINING_SETTINGS = _UnexpectedErrorPresentation(
        title="Training settings could not be applied",
        message=(
            "XBrainLab could not apply the training settings because of an "
            "unexpected problem. Review the training configuration and try again."
        ),
        log_message="Unexpected failure while applying training settings",
        severity=_UnexpectedErrorSeverity.WARNING,
    )
    TRAINING_TEST_SETTINGS = _UnexpectedErrorPresentation(
        title="Test settings could not be applied",
        message=(
            "XBrainLab could not apply the test settings because of an unexpected "
            "problem. Review the batch size, device, and output location, then try "
            "again."
        ),
        log_message="Unexpected failure while applying test-only settings",
        severity=_UnexpectedErrorSeverity.WARNING,
    )
    MONTAGE_MAPPING_PREPARE = _UnexpectedErrorPresentation(
        title="Montage mapping could not be prepared",
        message=(
            "XBrainLab could not prepare the montage channel mapping because of an "
            "unexpected problem. Reopen the montage setup and try again."
        ),
        log_message="Unexpected failure while preparing a montage mapping",
        severity=_UnexpectedErrorSeverity.WARNING,
    )
    MONTAGE_MAPPING_APPLY = _UnexpectedErrorPresentation(
        title="Montage mapping could not be applied",
        message=(
            "XBrainLab could not apply the montage channel mapping because of an "
            "unexpected problem. Review the mapped channels and try again."
        ),
        log_message="Unexpected failure while applying a montage mapping",
    )
    SALIENCY_SETTINGS = _UnexpectedErrorPresentation(
        title="Saliency settings could not be applied",
        message=(
            "XBrainLab could not apply the saliency settings because of an unexpected "
            "problem. Review the selected methods and parameters, then try again."
        ),
        log_message="Unexpected failure while applying saliency settings",
        severity=_UnexpectedErrorSeverity.WARNING,
    )
    MONTAGE_SETUP = _UnexpectedErrorPresentation(
        title="Montage setup could not be applied",
        message=(
            "XBrainLab could not apply the montage setup because of an unexpected "
            "problem. Reopen the channel mapping and try again."
        ),
        log_message="Unexpected failure while applying montage setup",
    )
    DATASET_LOADER_APPLY = _UnexpectedErrorPresentation(
        title="Dataset could not be updated",
        message=(
            "XBrainLab could not apply the loaded EEG data because of an unexpected "
            "problem. Reopen the data source and try again."
        ),
        log_message="Unexpected failure while applying loaded EEG data",
    )
    DATASET_CHANNEL_SELECTION = _UnexpectedErrorPresentation(
        title="Channel selection could not be applied",
        message=(
            "XBrainLab could not apply the channel selection because of an unexpected "
            "problem. Reopen channel selection and try again."
        ),
        log_message="Unexpected failure while applying channel selection",
    )
    DATASET_SESSION_RESET = _UnexpectedErrorPresentation(
        title="Session could not be reset",
        message=(
            "XBrainLab could not reset the current session because of an unexpected "
            "problem. Review the workflow state and try again."
        ),
        log_message="Unexpected failure while resetting the current session",
    )


def present_unexpected_error(
    parent: Any,
    context: UnexpectedErrorContext,
    *,
    error_info: object | None = None,
    message_box: Any | None = None,
    title: str | None = None,
) -> str:
    """Log technical details and show only stable recovery guidance."""
    # Keep the legacy injection argument temporarily so workflow callers can
    # migrate independently; visible presentation is always the shared shell.
    del message_box
    presentation = context.value
    if error_info is None:
        _safe_logger_error(presentation.log_message, exc_info=True)
    else:
        _log_worker_error(presentation.log_message, error_info)
    show_alert(
        parent,
        severity=(
            AlertSeverity.WARNING
            if presentation.severity is _UnexpectedErrorSeverity.WARNING
            else AlertSeverity.CRITICAL
        ),
        title=title or presentation.title,
        message=presentation.message,
    )
    return presentation.message


def _log_worker_error(log_message: str, error_info: object) -> None:
    """Log an untrusted worker payload without invoking its dynamic methods."""
    safe_log_message = (
        log_message if type(log_message) is str else "Unexpected worker failure"
    )
    error_value = _worker_tuple_item(error_info, 1)
    traceback_value = _worker_tuple_item(error_info, 2)
    formatted_traceback = (
        traceback_value
        if type(traceback_value) is str
        else "Traceback was not provided."
    )
    if not isinstance(error_value, Exception):
        error_value = RuntimeError("Worker error details were unavailable.")

    try:
        _raise_for_logging(error_value)
    except Exception:
        _safe_logger_error(
            "%s\nOriginal worker traceback:\n%s",
            safe_log_message,
            formatted_traceback,
            exc_info=True,
        )


def _worker_tuple_item(error_info: object, index: int) -> object | None:
    if not isinstance(error_info, tuple):
        return None
    try:
        if tuple.__len__(error_info) <= index:
            return None
        return tuple.__getitem__(error_info, index)
    except BaseException:
        return None


def _safe_logger_error(*args: Any, **kwargs: Any) -> None:
    try:
        logger.error(*args, **kwargs)
    except BaseException:
        return


def _raise_for_logging(error: Exception) -> Never:
    raise error
