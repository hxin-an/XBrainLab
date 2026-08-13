"""Small helpers for non-modal product status messages."""

from __future__ import annotations

import math
from time import monotonic
from typing import Any

from PyQt6 import sip
from PyQt6.QtCore import QTimer

DEFAULT_STATUS_TIMEOUT_MS = 7000
MAX_TRANSIENT_BEFORE_OWNED_PROGRESS_MS = 1000
MAX_OPERATION_DETAIL_CHARS = 240
IMPORT_REVIEW_STATUS_LABEL = "Checking selected EEG data"
IMPORT_APPLY_STATUS_LABEL = "Importing reviewed EEG data"
_TRANSIENT_MESSAGE_ATTRIBUTE = "_xbrainlab_transient_status_message"
_TRANSIENT_DEADLINE_ATTRIBUTE = "_xbrainlab_transient_status_deadline"
_OWNED_MESSAGE_ATTRIBUTE = "_xbrainlab_owned_operation_status_message"
_OWNED_OPERATION_ATTRIBUTE = "_xbrainlab_owned_operation_status_id"
_OWNED_DEFERRED_ATTRIBUTE = "_xbrainlab_owned_operation_deferred_token"
_OWNED_DEFERRED_OPERATION_ATTRIBUTE = "_xbrainlab_owned_operation_deferred_operation_id"


def show_status_message(
    owner: Any,
    message: str,
    timeout_ms: int = DEFAULT_STATUS_TIMEOUT_MS,
) -> bool:
    """Show a transient message on the nearest main-window status bar.

    Returns ``True`` when a status bar accepted the message. Callers can use
    this to fall back to an in-panel label in standalone/legacy dialogs.
    """
    for candidate in _status_owner_candidates(owner):
        status_bar = _status_bar(candidate)
        show_message = getattr(status_bar, "showMessage", None)
        if not callable(show_message):
            continue
        try:
            show_message(message, timeout_ms)
        except TypeError:
            show_message(message)
        _record_transient_status(status_bar, message, timeout_ms)
        return True
    return False


def publish_owned_operation_progress(
    owner: Any,
    *,
    operation_id: str,
    kind: str = "",
    stage: str,
    phase: str,
    detail: str = "",
    completed: int | None = None,
    total: int | None = None,
    indeterminate: bool = True,
    cancel_requested: bool = False,
) -> bool:
    """Publish one operation snapshot on the existing visible status surface."""
    operation_id = str(operation_id or "").strip()
    if not operation_id:
        return False
    for candidate in _status_owner_candidates(owner):
        status_bar = _status_bar(candidate)
        if status_bar is None:
            continue
        set_property = getattr(status_bar, "setProperty", None)
        if not callable(set_property):
            continue
        progress = (
            f"{completed}/{total}"
            if isinstance(completed, int) and isinstance(total, int) and total > 0
            else "indeterminate"
            if indeterminate
            else str(phase or "")
        )
        normalized_kind = str(kind or "")
        normalized_stage = str(stage or "Working")
        normalized_phase = str(phase or "running")
        operation_detail = (
            _bounded_operation_detail(detail or normalized_stage)
            if normalized_kind in {"import_review", "import_apply"}
            and normalized_phase.casefold() not in {"completed", "cancelled", "failed"}
            else ""
        )
        set_property("operationId", operation_id)
        set_property("operationKind", normalized_kind)
        set_property("stage", normalized_stage)
        set_property("operationDetail", operation_detail)
        set_property("progress", progress)
        set_property("indeterminate", bool(indeterminate))
        set_property("operationPhase", normalized_phase)
        set_property("cancelRequested", bool(cancel_requested))
        set_accessible_description = getattr(
            status_bar,
            "setAccessibleDescription",
            None,
        )
        if callable(set_accessible_description):
            set_accessible_description(
                operation_detail
                if normalized_kind in {"import_review", "import_apply"}
                else ""
            )
        _show_owned_operation_message(
            status_bar,
            operation_id=operation_id,
            kind=normalized_kind,
            stage=normalized_stage,
            phase=normalized_phase,
            progress=_display_progress(
                kind=normalized_kind,
                progress=progress,
                completed=completed,
                total=total,
            ),
            cancel_requested=cancel_requested,
        )
        repaint = getattr(status_bar, "repaint", None)
        if callable(repaint):
            repaint()
        return True
    return False


def _show_owned_operation_message(
    status_bar: Any,
    *,
    operation_id: str,
    kind: str,
    stage: str,
    phase: str,
    progress: str,
    cancel_requested: bool,
) -> None:
    """Keep active work visible without erasing higher-priority feedback."""
    current_message = getattr(status_bar, "currentMessage", None)
    show_message = getattr(status_bar, "showMessage", None)
    clear_message = getattr(status_bar, "clearMessage", None)
    if not callable(current_message) or not callable(show_message):
        return
    previous_message = str(getattr(status_bar, _OWNED_MESSAGE_ATTRIBUTE, "") or "")
    previous_operation = str(getattr(status_bar, _OWNED_OPERATION_ATTRIBUTE, "") or "")
    terminal = phase.casefold() in {"completed", "cancelled", "failed"}
    if terminal:
        _clear_deferred_owned_message(status_bar)
        if (
            previous_operation == operation_id
            and previous_message
            and current_message() == previous_message
            and callable(clear_message)
        ):
            clear_message()
        setattr(status_bar, _OWNED_MESSAGE_ATTRIBUTE, "")
        setattr(status_bar, _OWNED_OPERATION_ATTRIBUTE, "")
        return

    transient_remaining = transient_status_remaining_ms(status_bar)
    if transient_remaining > 0 and current_message() != previous_message:
        deferred_operation = str(
            getattr(status_bar, _OWNED_DEFERRED_OPERATION_ATTRIBUTE, "") or ""
        )
        if deferred_operation == operation_id:
            return
        token = int(getattr(status_bar, _OWNED_DEFERRED_ATTRIBUTE, 0) or 0) + 1
        setattr(status_bar, _OWNED_DEFERRED_ATTRIBUTE, token)
        setattr(
            status_bar,
            _OWNED_DEFERRED_OPERATION_ATTRIBUTE,
            operation_id,
        )
        QTimer.singleShot(
            min(transient_remaining, MAX_TRANSIENT_BEFORE_OWNED_PROGRESS_MS),
            lambda: _publish_deferred_owned_message(
                status_bar,
                token=token,
                operation_id=operation_id,
                kind=kind,
                stage=stage,
                phase=phase,
                progress=progress,
                cancel_requested=cancel_requested,
            ),
        )
        return
    _clear_deferred_owned_message(status_bar)
    message = _owned_operation_message(
        kind=kind,
        stage=stage,
        phase=phase,
        progress=progress,
        cancel_requested=cancel_requested,
    )
    show_message(message)
    setattr(status_bar, _OWNED_MESSAGE_ATTRIBUTE, message)
    setattr(status_bar, _OWNED_OPERATION_ATTRIBUTE, operation_id)


def _publish_deferred_owned_message(
    status_bar: Any,
    *,
    token: int,
    operation_id: str,
    kind: str,
    stage: str,
    phase: str,
    progress: str,
    cancel_requested: bool,
) -> None:
    """Reveal still-active owned work after bounded transient feedback."""
    try:
        if sip.isdeleted(status_bar):
            return
    except (RuntimeError, TypeError):
        # Lightweight status doubles are not SIP wrappers. Their public
        # methods below remain the compatibility boundary.
        pass
    try:
        if int(getattr(status_bar, _OWNED_DEFERRED_ATTRIBUTE, 0) or 0) != token:
            return
        if str(status_bar.property("operationId") or "") != operation_id:
            return
        current_phase = str(status_bar.property("operationPhase") or phase).casefold()
        if current_phase in {"completed", "cancelled", "failed"}:
            return
        setattr(status_bar, _OWNED_DEFERRED_OPERATION_ATTRIBUTE, "")
        show_message = getattr(status_bar, "showMessage", None)
        if not callable(show_message):
            return
        current_kind = str(status_bar.property("operationKind") or kind)
        current_stage = str(status_bar.property("stage") or stage)
        current_progress = str(status_bar.property("progress") or progress)
        current_cancel_requested = bool(
            status_bar.property("cancelRequested") or cancel_requested
        )
        message = _owned_operation_message(
            kind=current_kind,
            stage=current_stage,
            phase=current_phase,
            progress=_display_progress(
                kind=current_kind,
                progress=current_progress,
                completed=None,
                total=None,
            ),
            cancel_requested=current_cancel_requested,
        )
        _clear_transient_status(status_bar)
        show_message(message)
        setattr(status_bar, _OWNED_MESSAGE_ATTRIBUTE, message)
        setattr(status_bar, _OWNED_OPERATION_ATTRIBUTE, operation_id)
    except RuntimeError:
        # The QStatusBar can be destroyed after the liveness probe while this
        # queued callback is being delivered during MainWindow teardown.
        return


def _display_progress(
    *,
    kind: str,
    progress: str,
    completed: int | None,
    total: int | None,
) -> str:
    """Use a compact percentage only for stable Data Import status copy."""
    if kind != "import_apply":
        return progress
    if not isinstance(completed, int) or not isinstance(total, int):
        try:
            completed_text, total_text = progress.split("/", maxsplit=1)
            completed = int(completed_text)
            total = int(total_text)
        except (TypeError, ValueError):
            return progress
    if total <= 0:
        return progress
    percentage = min(max(int((completed / total) * 100), 0), 100)
    return f"{percentage}%"


def _owned_operation_message(
    *,
    kind: str,
    stage: str,
    phase: str,
    progress: str,
    cancel_requested: bool,
) -> str:
    """Project exact operation truth into stable primary product copy."""
    if cancel_requested or phase.casefold() == "cancelling":
        cancelling_stage = _stable_import_status_label(kind) or stage
        return f"Cancelling · {cancelling_stage}"
    display_stage = _stable_import_status_label(kind) or stage
    if progress == "indeterminate":
        return f"{display_stage} · Working…"
    return f"{display_stage} · {progress}"


def _stable_import_status_label(kind: str) -> str:
    if kind == "import_review":
        return IMPORT_REVIEW_STATUS_LABEL
    if kind == "import_apply":
        return IMPORT_APPLY_STATUS_LABEL
    return ""


def _bounded_operation_detail(detail: str) -> str:
    """Keep exact-stage context useful without exposing unbounded snapshot text."""
    normalized = " ".join(str(detail or "").split())
    if len(normalized) <= MAX_OPERATION_DETAIL_CHARS:
        return normalized
    return normalized[: MAX_OPERATION_DETAIL_CHARS - 1].rstrip() + "…"


def _clear_deferred_owned_message(status_bar: Any) -> None:
    """Invalidate one pending reveal without repeatedly resetting its timer."""
    deferred_operation = str(
        getattr(status_bar, _OWNED_DEFERRED_OPERATION_ATTRIBUTE, "") or ""
    )
    if not deferred_operation:
        return
    token = int(getattr(status_bar, _OWNED_DEFERRED_ATTRIBUTE, 0) or 0) + 1
    setattr(status_bar, _OWNED_DEFERRED_ATTRIBUTE, token)
    setattr(status_bar, _OWNED_DEFERRED_OPERATION_ATTRIBUTE, "")


def transient_status_remaining_ms(status_bar: Any) -> int:
    """Return how long the current action feedback must remain visible."""
    current_message = getattr(status_bar, "currentMessage", None)
    if not callable(current_message):
        return 0
    expected_message = getattr(status_bar, _TRANSIENT_MESSAGE_ATTRIBUTE, "")
    deadline = getattr(status_bar, _TRANSIENT_DEADLINE_ATTRIBUTE, 0.0)
    if not expected_message or current_message() != expected_message:
        _clear_transient_status(status_bar)
        return 0
    try:
        remaining_seconds = float(deadline) - monotonic()
    except (TypeError, ValueError, OverflowError):
        _clear_transient_status(status_bar)
        return 0
    if remaining_seconds <= 0:
        _clear_transient_status(status_bar)
        return 0
    return max(1, math.ceil(remaining_seconds * 1000))


def _record_transient_status(
    status_bar: Any,
    message: str,
    timeout_ms: int,
) -> None:
    """Mark product feedback so routine state refresh cannot erase it early."""
    if timeout_ms <= 0:
        _clear_transient_status(status_bar)
        return
    setattr(status_bar, _TRANSIENT_MESSAGE_ATTRIBUTE, message)
    setattr(
        status_bar,
        _TRANSIENT_DEADLINE_ATTRIBUTE,
        monotonic() + (timeout_ms / 1000),
    )


def _clear_transient_status(status_bar: Any) -> None:
    setattr(status_bar, _TRANSIENT_MESSAGE_ATTRIBUTE, "")
    setattr(status_bar, _TRANSIENT_DEADLINE_ATTRIBUTE, 0.0)


def _status_owner_candidates(owner: Any):
    seen: set[int] = set()
    for candidate in (
        getattr(owner, "main_window", None),
        owner,
        getattr(owner, "parent", lambda: None)(),
        getattr(owner, "window", lambda: None)(),
    ):
        if candidate is None:
            continue
        marker = id(candidate)
        if marker in seen:
            continue
        seen.add(marker)
        yield candidate


def _status_bar(candidate: Any) -> Any:
    status_bar = getattr(candidate, "statusBar", None)
    if not callable(status_bar):
        return None
    try:
        return status_bar()
    except RuntimeError:
        return None
