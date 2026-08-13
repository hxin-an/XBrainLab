"""Lock-independent ownership and cooperative cancellation for product work."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from enum import Enum
from threading import Condition, Event, RLock
from time import monotonic
from uuid import uuid4

from XBrainLab.backend.utils.public_diagnostics import public_diagnostic_text

_MAX_RETAINED_TERMINAL_OPERATIONS = 256


class OwnedWorkKind(str, Enum):
    """Product work categories included in close and cancellation accounting."""

    IMPORT_REVIEW = "import_review"
    IMPORT_APPLY = "import_apply"
    PREPROCESS = "preprocess"
    EPOCH = "epoch"
    TRAINING = "training"
    EVALUATION = "evaluation"
    SALIENCY = "saliency"
    RENDER = "render"
    TRAINING_RESOURCE_PREVIEW = "training_resource_preview"
    SUBPROCESS = "subprocess"
    COMMAND = "command"


class OwnedWorkPhase(str, Enum):
    """Lifecycle phase for one owned operation."""

    PENDING = "pending"
    RUNNING = "running"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"

    @property
    def terminal(self) -> bool:
        return self in {
            OwnedWorkPhase.COMPLETED,
            OwnedWorkPhase.CANCELLED,
            OwnedWorkPhase.FAILED,
        }


@dataclass(frozen=True, slots=True)
class OwnedOperationSnapshot:
    """Immutable product-facing state for one background operation."""

    operation_id: str
    generation: int
    kind: OwnedWorkKind
    phase: OwnedWorkPhase
    cancellable: bool
    stage: str
    completed: int | None
    total: int | None
    indeterminate: bool
    cancel_requested: bool
    started_at_monotonic: float | None
    updated_at_monotonic: float
    message: str = ""


@dataclass(slots=True)
class _OwnedOperation:
    snapshot: OwnedOperationSnapshot
    cancel_event: Event
    command_identity: str
    claimed: bool = False


class OwnedOperationCancelledError(RuntimeError):
    """Raised at a cooperative checkpoint after cancellation was requested."""

    def __init__(self, operation_id: str, stage: str) -> None:
        self.operation_id = operation_id
        self.stage = stage
        super().__init__("The operation was cancelled.")


class OwnedOperationClaimError(RuntimeError):
    """Raised when an operation ID cannot admit one command execution."""

    def __init__(
        self,
        operation_id: str,
        reason: str,
        *,
        snapshot: OwnedOperationSnapshot | None = None,
    ) -> None:
        self.operation_id = str(operation_id)
        self.reason = reason
        self.snapshot = snapshot
        super().__init__("The owned operation could not be admitted.")


class OwnedWorkRegistry:
    """Own operation identity without depending on the shared command lock."""

    def __init__(self) -> None:
        self._condition = Condition(RLock())
        self._operations: dict[str, _OwnedOperation] = {}
        self._generation = 0

    def begin(
        self,
        kind: OwnedWorkKind,
        *,
        cancellable: bool,
        stage: str = "Queued",
        command_identity: str = "",
    ) -> OwnedOperationSnapshot:
        if not isinstance(kind, OwnedWorkKind):
            raise TypeError("Owned work kind must be typed.")
        now = monotonic()
        with self._condition:
            self._generation += 1
            operation_id = uuid4().hex
            snapshot = OwnedOperationSnapshot(
                operation_id=operation_id,
                generation=self._generation,
                kind=kind,
                phase=OwnedWorkPhase.PENDING,
                cancellable=bool(cancellable),
                stage=public_diagnostic_text(stage),
                completed=None,
                total=None,
                indeterminate=True,
                cancel_requested=False,
                started_at_monotonic=None,
                updated_at_monotonic=now,
            )
            self._operations[operation_id] = _OwnedOperation(
                snapshot,
                Event(),
                public_diagnostic_text(command_identity),
            )
            self._prune_terminal_operations_locked(excluding=operation_id)
            self._condition.notify_all()
            return snapshot

    def start(self, operation_id: str) -> OwnedOperationSnapshot:
        """Claim one operation without a command binding (low-level callers)."""
        return self.claim_start(operation_id)

    def claim_start(
        self,
        operation_id: str,
        *,
        kind: OwnedWorkKind | None = None,
        command_identity: str | None = None,
    ) -> OwnedOperationSnapshot:
        """Atomically admit the single command allowed to execute this ID."""
        with self._condition:
            operation = self._operations.get(str(operation_id))
            if operation is None:
                raise OwnedOperationClaimError(operation_id, "unknown_operation")
            snapshot = operation.snapshot
            if snapshot.phase.terminal:
                raise OwnedOperationClaimError(
                    operation_id,
                    "terminal_replay",
                    snapshot=snapshot,
                )
            if operation.claimed:
                raise OwnedOperationClaimError(
                    operation_id,
                    "already_claimed",
                    snapshot=snapshot,
                )
            if kind is not None and kind is not snapshot.kind:
                rejected = self._finish(
                    operation,
                    OwnedWorkPhase.FAILED,
                    message="The operation kind did not match the scheduled command.",
                )
                raise OwnedOperationClaimError(
                    operation_id,
                    "kind_mismatch",
                    snapshot=rejected,
                )
            if (
                command_identity is not None
                and public_diagnostic_text(command_identity)
                != operation.command_identity
            ):
                rejected = self._finish(
                    operation,
                    OwnedWorkPhase.FAILED,
                    message=(
                        "The operation command did not match the scheduled command."
                    ),
                )
                raise OwnedOperationClaimError(
                    operation_id,
                    "command_mismatch",
                    snapshot=rejected,
                )
            operation.claimed = True
            phase = (
                OwnedWorkPhase.CANCELLING
                if operation.cancel_event.is_set()
                else OwnedWorkPhase.RUNNING
            )
            now = monotonic()
            operation.snapshot = replace(
                snapshot,
                phase=phase,
                cancel_requested=operation.cancel_event.is_set(),
                started_at_monotonic=snapshot.started_at_monotonic or now,
                updated_at_monotonic=now,
            )
            self._condition.notify_all()
            return operation.snapshot

    def update(
        self,
        operation_id: str,
        *,
        stage: str,
        completed: int | None = None,
        total: int | None = None,
        message: str = "",
    ) -> OwnedOperationSnapshot:
        if completed is not None and (type(completed) is not int or completed < 0):
            raise ValueError("Completed work must be a non-negative integer.")
        if total is not None and (type(total) is not int or total <= 0):
            raise ValueError("Total work must be a positive integer.")
        if completed is not None and total is not None and completed > total:
            raise ValueError("Completed work cannot exceed total work.")
        with self._condition:
            operation = self._require(operation_id)
            snapshot = operation.snapshot
            if snapshot.phase.terminal:
                return snapshot
            operation.snapshot = replace(
                snapshot,
                stage=public_diagnostic_text(stage),
                completed=completed,
                total=total,
                indeterminate=completed is None or total is None,
                cancel_requested=operation.cancel_event.is_set(),
                phase=(
                    OwnedWorkPhase.CANCELLING
                    if operation.cancel_event.is_set()
                    else snapshot.phase
                ),
                updated_at_monotonic=monotonic(),
                message=public_diagnostic_text(message),
            )
            self._condition.notify_all()
            return operation.snapshot

    def cancel(self, operation_id: str) -> bool:
        with self._condition:
            operation = self._operations.get(operation_id)
            if operation is None:
                return False
            snapshot = operation.snapshot
            if snapshot.phase.terminal or not snapshot.cancellable:
                return False
            operation.cancel_event.set()
            operation.snapshot = replace(
                snapshot,
                phase=OwnedWorkPhase.CANCELLING,
                cancel_requested=True,
                updated_at_monotonic=monotonic(),
            )
            self._condition.notify_all()
            return True

    def cancel_all(self) -> tuple[str, ...]:
        """Request cancellation for every active cancellable operation."""
        cancelled: list[str] = []
        with self._condition:
            for operation_id, operation in self._operations.items():
                snapshot = operation.snapshot
                if snapshot.phase.terminal or not snapshot.cancellable:
                    continue
                operation.cancel_event.set()
                operation.snapshot = replace(
                    snapshot,
                    phase=OwnedWorkPhase.CANCELLING,
                    cancel_requested=True,
                    updated_at_monotonic=monotonic(),
                )
                cancelled.append(operation_id)
            if cancelled:
                self._condition.notify_all()
        return tuple(cancelled)

    def checkpoint(
        self,
        operation_id: str,
        stage: str,
        *,
        completed: int | None = None,
        total: int | None = None,
    ) -> OwnedOperationSnapshot:
        snapshot = self.update(
            operation_id,
            stage=stage,
            completed=completed,
            total=total,
        )
        with self._condition:
            operation = self._require(operation_id)
            if operation.cancel_event.is_set():
                raise OwnedOperationCancelledError(operation_id, snapshot.stage)
        return snapshot

    def enter_commit(
        self,
        operation_id: str,
        stage: str,
        *,
        completed: int | None = None,
        total: int | None = None,
    ) -> OwnedOperationSnapshot:
        """Atomically reject prior cancellation or close cancel admission."""
        with self._condition:
            snapshot = self.update(
                operation_id,
                stage=stage,
                completed=completed,
                total=total,
            )
            operation = self._require(operation_id)
            if operation.cancel_event.is_set():
                raise OwnedOperationCancelledError(operation_id, snapshot.stage)
            if snapshot.phase.terminal:
                return snapshot
            operation.snapshot = replace(
                snapshot,
                cancellable=False,
                updated_at_monotonic=monotonic(),
            )
            self._condition.notify_all()
            return operation.snapshot

    def complete(self, operation_id: str) -> OwnedOperationSnapshot:
        """Finish successful work unless an accepted cancellation won first."""
        with self._condition:
            operation = self._require(operation_id)
            phase = (
                OwnedWorkPhase.CANCELLED
                if operation.cancel_event.is_set()
                else OwnedWorkPhase.COMPLETED
            )
            return self._finish(operation, phase)

    def finish_cancelled(self, operation_id: str) -> OwnedOperationSnapshot:
        with self._condition:
            return self._finish(
                self._require(operation_id),
                OwnedWorkPhase.CANCELLED,
            )

    def fail(self, operation_id: str, *, message: str) -> OwnedOperationSnapshot:
        with self._condition:
            return self._finish(
                self._require(operation_id),
                OwnedWorkPhase.FAILED,
                message=message,
            )

    def snapshot(self, operation_id: str) -> OwnedOperationSnapshot:
        with self._condition:
            return self._require(operation_id).snapshot

    def active_snapshots(self) -> tuple[OwnedOperationSnapshot, ...]:
        with self._condition:
            return tuple(
                operation.snapshot
                for operation in self._operations.values()
                if not operation.snapshot.phase.terminal
            )

    def first_active(self, kind: OwnedWorkKind) -> OwnedOperationSnapshot | None:
        """Return the oldest active operation of one kind, if present."""
        with self._condition:
            return next(
                (
                    operation.snapshot
                    for operation in self._operations.values()
                    if operation.snapshot.kind is kind
                    and not operation.snapshot.phase.terminal
                ),
                None,
            )

    def wait_for_idle(
        self,
        timeout: float | None = None,
        *,
        excluding_operation_id: str | None = None,
    ) -> bool:
        deadline = None if timeout is None else monotonic() + max(0.0, timeout)
        with self._condition:
            while any(
                not operation.snapshot.phase.terminal
                and operation.snapshot.operation_id != excluding_operation_id
                for operation in self._operations.values()
            ):
                if deadline is None:
                    self._condition.wait()
                    continue
                remaining = deadline - monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True

    @contextmanager
    def bind(self, operation_id: str) -> Iterator[OwnedOperationSnapshot]:
        snapshot = self.snapshot(operation_id)
        with bind_captured_owned_work(
            CapturedOwnedWork(registry=self, operation_id=operation_id)
        ):
            try:
                yield snapshot
            except OwnedOperationCancelledError:
                self.finish_cancelled(operation_id)
                raise

    def _finish(
        self,
        operation: _OwnedOperation,
        phase: OwnedWorkPhase,
        *,
        message: str = "",
    ) -> OwnedOperationSnapshot:
        snapshot = operation.snapshot
        if snapshot.phase.terminal:
            return snapshot
        operation.snapshot = replace(
            snapshot,
            phase=phase,
            cancel_requested=operation.cancel_event.is_set(),
            updated_at_monotonic=monotonic(),
            message=public_diagnostic_text(message),
        )
        self._prune_terminal_operations_locked(
            excluding=operation.snapshot.operation_id,
        )
        self._condition.notify_all()
        return operation.snapshot

    def _prune_terminal_operations_locked(self, *, excluding: str) -> None:
        """Bound receipt history without ever discarding active or newest truth."""
        terminal_ids = [
            operation_id
            for operation_id, operation in self._operations.items()
            if operation_id != excluding and operation.snapshot.phase.terminal
        ]
        excess = (
            len(terminal_ids)
            + int(
                excluding in self._operations
                and self._operations[excluding].snapshot.phase.terminal
            )
            - _MAX_RETAINED_TERMINAL_OPERATIONS
        )
        for operation_id in terminal_ids[: max(0, excess)]:
            self._operations.pop(operation_id, None)

    def _require(self, operation_id: str) -> _OwnedOperation:
        operation = self._operations.get(str(operation_id))
        if operation is None:
            raise KeyError(f"Unknown owned operation: {operation_id}")
        return operation


_CURRENT_OWNED_WORK: ContextVar[tuple[OwnedWorkRegistry, str] | None] = ContextVar(
    "xbrainlab_current_owned_work",
    default=None,
)


@dataclass(frozen=True, slots=True)
class CapturedOwnedWork:
    """The only execution context explicitly admitted into a child worker."""

    registry: OwnedWorkRegistry
    operation_id: str


def capture_owned_work() -> CapturedOwnedWork | None:
    """Capture only owned-work identity, never the caller's other ContextVars."""
    current = _CURRENT_OWNED_WORK.get()
    if current is None:
        return None
    registry, operation_id = current
    return CapturedOwnedWork(registry=registry, operation_id=operation_id)


@contextmanager
def bind_captured_owned_work(
    captured: CapturedOwnedWork | None,
) -> Iterator[None]:
    """Bind one captured operation to a child worker and restore its prior state."""
    if captured is None:
        yield
        return
    binding = (captured.registry, captured.operation_id)
    current = _CURRENT_OWNED_WORK.get()
    if current is not None and current != binding:
        raise RuntimeError("A worker is already bound to a different owned operation.")
    if current == binding:
        yield
        return
    captured.registry.snapshot(captured.operation_id)
    token = _CURRENT_OWNED_WORK.set(binding)
    try:
        yield
    finally:
        _CURRENT_OWNED_WORK.reset(token)


def owned_work_checkpoint(
    stage: str,
    *,
    completed: int | None = None,
    total: int | None = None,
) -> OwnedOperationSnapshot | None:
    """Update and cooperatively cancel the operation bound to this thread."""
    current = _CURRENT_OWNED_WORK.get()
    if current is None:
        return None
    registry, operation_id = current
    return registry.checkpoint(
        operation_id,
        stage,
        completed=completed,
        total=total,
    )


def owned_work_commit_boundary(
    stage: str,
    *,
    completed: int | None = None,
    total: int | None = None,
) -> OwnedOperationSnapshot | None:
    """Admit an irreversible commit or reject a prior cancellation request."""
    current = _CURRENT_OWNED_WORK.get()
    if current is None:
        return None
    registry, operation_id = current
    return registry.enter_commit(
        operation_id,
        stage,
        completed=completed,
        total=total,
    )


def current_owned_operation_id() -> str | None:
    """Return the operation bound to this execution thread, if any."""
    current = _CURRENT_OWNED_WORK.get()
    return current[1] if current is not None else None


def owned_operation_diagnostics(
    snapshot: OwnedOperationSnapshot,
) -> dict[str, object]:
    """Return the stable JSON-safe projection used by command receipts."""
    return {
        "operation_id": snapshot.operation_id,
        "operation_generation": snapshot.generation,
        "operation_kind": snapshot.kind.value,
        "operation_phase": snapshot.phase.value,
        "operation_stage": snapshot.stage,
        "operation_cancel_requested": snapshot.cancel_requested,
        "operation_completed": snapshot.completed,
        "operation_total": snapshot.total,
        "operation_indeterminate": snapshot.indeterminate,
    }
