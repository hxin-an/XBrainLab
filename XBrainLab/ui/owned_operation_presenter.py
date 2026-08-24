"""Visible, lock-independent presentation for one application-owned operation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QPushButton, QWidget

from XBrainLab.ui.status import publish_owned_operation_progress


class OwnedOperationPresenter(QObject):
    """Bind a visible Cancel action and status surface to immutable snapshots."""

    terminal = pyqtSignal(str, str)
    snapshot_updated = pyqtSignal(str, object)

    def __init__(
        self,
        owner: QWidget,
        *,
        cancel_button: QPushButton,
        snapshot_getter: Callable[[str], Any | None],
        canceller: Callable[[str], bool],
        interval_ms: int = 250,
        connect_button: bool = True,
        hide_when_idle: bool = True,
    ) -> None:
        super().__init__(owner)
        self._owner = owner
        self._cancel_button = cancel_button
        self._snapshot_getter = snapshot_getter
        self._canceller = canceller
        self._hide_when_idle = hide_when_idle
        self._active_operation_id: str | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.refresh)
        if connect_button:
            self._cancel_button.clicked.connect(self.request_cancel)
        self._cancel_button.setVisible(not hide_when_idle)
        self._cancel_button.setEnabled(False)

    @property
    def active_operation_id(self) -> str | None:
        """Return the currently presented non-terminal operation identity."""
        return self._active_operation_id

    def bind(self, operation_id: str, *, stage: str = "Queued") -> None:
        """Present a newly allocated operation without waiting for first polling."""
        normalized = str(operation_id or "").strip()
        if not normalized:
            raise ValueError("Owned operation identity must be non-empty.")
        self._active_operation_id = normalized
        self._cancel_button.setVisible(True)
        self._cancel_button.setEnabled(True)
        publish_owned_operation_progress(
            self._owner,
            operation_id=normalized,
            stage=stage,
            phase="pending",
            indeterminate=True,
        )
        self._timer.start()
        self.refresh()

    def request_cancel(self) -> bool:
        """Request cooperative cancellation without waiting for the worker."""
        operation_id = self._active_operation_id
        if operation_id is None:
            return False
        self._cancel_button.setEnabled(False)
        requested = bool(self._canceller(operation_id))
        if not requested:
            self._cancel_button.setEnabled(True)
        self.refresh()
        return requested

    def refresh(self) -> None:
        """Render the latest immutable operation snapshot and terminal state."""
        operation_id = self._active_operation_id
        if operation_id is None:
            self._timer.stop()
            return
        snapshot = self._snapshot_getter(operation_id)
        if snapshot is None:
            return
        raw_phase = getattr(snapshot, "phase", "running")
        phase = str(getattr(raw_phase, "value", raw_phase))
        raw_kind = getattr(snapshot, "kind", "")
        kind = str(getattr(raw_kind, "value", raw_kind) or "")
        completed = getattr(snapshot, "completed", None)
        total = getattr(snapshot, "total", None)
        indeterminate = bool(getattr(snapshot, "indeterminate", True))
        cancel_requested = bool(getattr(snapshot, "cancel_requested", False))
        publish_owned_operation_progress(
            self._owner,
            operation_id=operation_id,
            kind=kind,
            stage=str(getattr(snapshot, "stage", "") or "Working"),
            detail=str(getattr(snapshot, "stage", "") or "Working"),
            phase=phase,
            completed=completed if isinstance(completed, int) else None,
            total=total if isinstance(total, int) else None,
            indeterminate=indeterminate,
            cancel_requested=cancel_requested,
        )
        # A single immutable snapshot drives every visible surface for this
        # operation. Consumers must not start a second poll loop merely to
        # mirror it in another widget.
        self.snapshot_updated.emit(operation_id, snapshot)
        terminal = phase in {"completed", "cancelled", "failed"}
        self._cancel_button.setEnabled(
            not terminal
            and bool(getattr(snapshot, "cancellable", True))
            and not cancel_requested
        )
        if not terminal:
            return
        self._timer.stop()
        self._cancel_button.setVisible(not self._hide_when_idle)
        self._active_operation_id = None
        self.terminal.emit(operation_id, phase)

    def abandon(self) -> None:
        """Stop presentation during widget teardown without cancelling work."""
        self._timer.stop()
        self._active_operation_id = None
        self._cancel_button.setVisible(not self._hide_when_idle)
        self._cancel_button.setEnabled(False)
