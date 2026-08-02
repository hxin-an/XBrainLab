"""Atomic read model published after verified application state transitions."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field, replace
from threading import Lock
from typing import Any

from XBrainLab.backend.training_state_contract import (
    TrainingOutcomeState,
    TrainingReadBoundary,
    TrainingTerminalOutcome,
)

from .capabilities import (
    CapabilityPolicy,
    build_capability_policy,
    fail_closed_capability_policy,
)
from .state import ApplicationStateSnapshot

APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT = "view_publication_changed"
PUBLIC_VIEW_UNAVAILABLE_CODE = "application_state_unavailable"
PUBLIC_VIEW_UNAVAILABLE_MESSAGE = "Workflow state is temporarily unavailable."
_STABLE_CAPTURE_ATTEMPTS = 3


@dataclass(frozen=True)
class InterpretationReviewIdentity:
    """Immutable domain identity for one published Data Import review."""

    publication_generation: int
    scan_id: str
    candidate_id: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.publication_generation, bool)
            or not isinstance(self.publication_generation, int)
            or self.publication_generation < 0
        ):
            raise ValueError(
                "Interpretation review publication generation must be a "
                "non-negative integer."
            )
        for field_name in ("scan_id", "candidate_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"Interpretation review {field_name} must be a string.")
            normalized = value.strip()
            if not normalized:
                raise ValueError(f"Interpretation review {field_name} cannot be empty.")
            object.__setattr__(self, field_name, normalized)


@dataclass(frozen=True)
class ApplicationViewPublication:
    """One consistent generation of state and its capability policy."""

    generation: int
    state: ApplicationStateSnapshot
    capabilities: CapabilityPolicy
    revision: int = 1
    training_boundary: TrainingReadBoundary = field(
        default_factory=TrainingReadBoundary.no_trainer
    )
    training_history: tuple[dict[str, Any], ...] | None = None
    data_summary_rows: tuple[dict[str, Any], ...] | None = None
    verified: bool = True
    stale: bool = False
    refresh_error: str | None = None

    @property
    def usable(self) -> bool:
        """Return whether consumers may act on this publication."""
        return self.verified and not self.stale

    @property
    def diagnostic_error(self) -> str | None:
        """Return the internal refresh diagnostic; never expose it to products."""
        return self.refresh_error

    @property
    def public_unavailable_code(self) -> str | None:
        """Return a stable code when consumers must fail closed."""
        return None if self.usable else PUBLIC_VIEW_UNAVAILABLE_CODE

    @property
    def public_unavailable_reason(self) -> str | None:
        """Return a safe product-facing reason without backend diagnostics."""
        return None if self.usable else PUBLIC_VIEW_UNAVAILABLE_MESSAGE

    @property
    def unavailable_reason(self) -> str | None:
        """Compatibility alias for the safe product-facing reason."""
        return self.public_unavailable_reason

    @property
    def effective_capabilities(self) -> CapabilityPolicy:
        """Return capabilities consumers may safely expose for this generation."""
        reason = self.public_unavailable_reason
        if reason is None:
            return self.capabilities
        failed_policy = fail_closed_capability_policy(self.capabilities, reason)
        return CapabilityPolicy(
            {
                name: replace(
                    capability,
                    reasons=[] if capability.enabled else [reason],
                )
                for name, capability in failed_policy.capabilities.items()
            }
        )


class ApplicationViewStore:
    """Own and copy the last atomically published application read model."""

    def __init__(
        self,
        initial_state: ApplicationStateSnapshot,
        initial_training_boundary: TrainingReadBoundary,
        *,
        initial_training_history: tuple[dict[str, Any], ...] | None = None,
        initial_data_summary_rows: tuple[dict[str, Any], ...] | None = None,
    ) -> None:
        self._lock = Lock()
        safe_state = deepcopy(initial_state)
        diagnostic_error = (
            None
            if safe_state.state_reliable
            else self._unreliable_state_message(safe_state)
        )
        if not safe_state.state_reliable:
            safe_state = self._fail_closed_state(safe_state)
        self._publication = ApplicationViewPublication(
            generation=1,
            state=safe_state,
            capabilities=build_capability_policy(safe_state),
            revision=1,
            training_boundary=deepcopy(initial_training_boundary),
            training_history=deepcopy(initial_training_history),
            data_summary_rows=deepcopy(initial_data_summary_rows),
            verified=safe_state.state_reliable,
            stale=not safe_state.state_reliable,
            refresh_error=diagnostic_error,
        )

    def read(self) -> ApplicationViewPublication:
        """Return an isolated copy of the committed publication."""
        with self._lock:
            return deepcopy(self._publication)

    def publish(
        self,
        state: ApplicationStateSnapshot,
        training_boundary: TrainingReadBoundary,
        *,
        training_history: tuple[dict[str, Any], ...] | None = None,
        data_summary_rows: tuple[dict[str, Any], ...] | None = None,
    ) -> ApplicationViewPublication:
        """Atomically publish one verified state, policy, and health outcome."""
        safe_state = deepcopy(state)
        if not safe_state.state_reliable:
            raise ValueError("Only verified application state may be published")
        capabilities = build_capability_policy(safe_state)
        with self._lock:
            current = self._publication
            if (
                current.state == safe_state
                and current.training_boundary == training_boundary
                and current.training_history == training_history
                and current.data_summary_rows == data_summary_rows
                and current.verified
                and not current.stale
                and current.refresh_error is None
            ):
                return deepcopy(current)
            self._publication = ApplicationViewPublication(
                generation=(
                    current.generation
                    if (
                        current.state == safe_state
                        and current.training_boundary == training_boundary
                        and current.training_history == training_history
                        and current.data_summary_rows == data_summary_rows
                    )
                    else current.generation + 1
                ),
                state=safe_state,
                capabilities=capabilities,
                revision=current.revision + 1,
                training_boundary=deepcopy(training_boundary),
                training_history=deepcopy(training_history),
                data_summary_rows=deepcopy(data_summary_rows),
                verified=True,
                stale=False,
                refresh_error=None,
            )
            return deepcopy(self._publication)

    def mark_stale(self, error: Exception | str) -> ApplicationViewPublication:
        """Publish a conservative state so stale data cannot look actionable."""
        message = str(error) or "application state could not be refreshed"
        with self._lock:
            current = self._publication
            fail_closed_state = self._fail_closed_state(current.state)
            if (
                current.stale
                and not current.verified
                and current.refresh_error == message
                and current.state == fail_closed_state
            ):
                return deepcopy(current)
            self._publication = ApplicationViewPublication(
                generation=current.generation,
                state=fail_closed_state,
                capabilities=build_capability_policy(fail_closed_state),
                revision=current.revision + 1,
                training_boundary=deepcopy(current.training_boundary),
                training_history=deepcopy(current.training_history),
                data_summary_rows=deepcopy(current.data_summary_rows),
                verified=False,
                stale=True,
                refresh_error=message,
            )
            return deepcopy(self._publication)

    def restore_verified(
        self,
        publication: ApplicationViewPublication,
    ) -> ApplicationViewPublication:
        """Restore one verified generation after a proven no-op control flow.

        The caller must rebuild backend state and prove that it still equals the
        supplied publication before using this method.  Generation matching keeps
        a concurrent or intervening domain transition from being hidden.
        """
        expected = deepcopy(publication)
        if not expected.usable or not expected.state.state_reliable:
            raise ValueError("Only a verified application publication may be restored")
        with self._lock:
            current = self._publication
            if current.generation != expected.generation:
                raise RuntimeError(
                    "Application publication changed during control-flow recovery"
                )
            if current.usable and current != expected:
                raise RuntimeError(
                    "A different verified application publication is already current"
                )
            self._publication = ApplicationViewPublication(
                generation=expected.generation,
                state=deepcopy(expected.state),
                capabilities=build_capability_policy(expected.state),
                revision=current.revision + 1,
                training_boundary=deepcopy(expected.training_boundary),
                training_history=deepcopy(expected.training_history),
                data_summary_rows=deepcopy(expected.data_summary_rows),
                verified=True,
                stale=False,
                refresh_error=None,
            )
            return deepcopy(self._publication)

    @staticmethod
    def _fail_closed_state(
        state: ApplicationStateSnapshot,
    ) -> ApplicationStateSnapshot:
        return replace(
            state,
            pipeline_stage="unavailable",
            training=replace(
                state.training,
                is_running=True,
                terminal_outcome=TrainingTerminalOutcome(
                    state=TrainingOutcomeState.UNKNOWN,
                    detail=PUBLIC_VIEW_UNAVAILABLE_MESSAGE,
                ),
            ),
            active_training=replace(state.active_training, is_running=True),
            state_reliable=False,
            training_liveness_reliable=False,
            read_errors=[PUBLIC_VIEW_UNAVAILABLE_MESSAGE],
        )

    @staticmethod
    def _unreliable_state_message(state: ApplicationStateSnapshot) -> str:
        detail = "; ".join(dict.fromkeys(state.read_errors))
        return detail or "application state snapshot is unreliable"


class ApplicationViewCoordinator:
    """Coordinate strict verification and fail-closed product read recovery.

    Strict and opportunistic refresh failures both make the publication
    unusable. A later reliable refresh publishes a new verified generation;
    stale state is never promoted back to usable without rebuilding it.
    """

    def __init__(
        self,
        initial_state: ApplicationStateSnapshot,
        *,
        initial_training_boundary: TrainingReadBoundary,
        build_state: Callable[[], ApplicationStateSnapshot],
        build_training_history: Callable[[], list[dict[str, Any]]] | None = None,
        build_data_summary_rows: Callable[[], list[dict[str, Any]]] | None = None,
        capture_training_boundary: Callable[[], TrainingReadBoundary],
        initial_training_history: tuple[dict[str, Any], ...] | None = None,
        initial_data_summary_rows: tuple[dict[str, Any], ...] | None = None,
    ) -> None:
        self._store = ApplicationViewStore(
            initial_state,
            initial_training_boundary,
            initial_training_history=initial_training_history,
            initial_data_summary_rows=initial_data_summary_rows,
        )
        self._build_state = build_state
        self._build_training_history = build_training_history
        self._build_data_summary_rows = build_data_summary_rows
        self._capture_training_boundary = capture_training_boundary

    def committed(self) -> ApplicationViewPublication:
        """Return an isolated copy of the current atomic publication."""
        return self._store.read()

    def refresh_strict(
        self,
        *,
        publish: bool = True,
    ) -> ApplicationStateSnapshot:
        """Build fresh state for verification and optionally publish it."""
        try:
            state, after_boundary, training_history, data_summary_rows = (
                self._build_with_stable_training_boundary()
            )
            if state.state_reliable:
                return (
                    self._store.publish(
                        state,
                        after_boundary,
                        training_history=training_history,
                        data_summary_rows=data_summary_rows,
                    ).state
                    if publish
                    else deepcopy(state)
                )
        except Exception as exc:
            self._store.mark_stale(exc)
            raise
        self._store.mark_stale(self._unreliable_state_error(state))
        return deepcopy(state)

    def refresh_opportunistic(self) -> ApplicationViewPublication:
        """Try to rebuild a usable publication without leaking read failures."""
        try:
            state, after_boundary, training_history, data_summary_rows = (
                self._build_with_stable_training_boundary()
            )
            if not state.state_reliable:
                return self._store.mark_stale(self._unreliable_state_error(state))
            return self._store.publish(
                state,
                after_boundary,
                training_history=training_history,
                data_summary_rows=data_summary_rows,
            )
        except Exception as exc:
            return self._store.mark_stale(exc)

    def _build_with_stable_training_boundary(
        self,
    ) -> tuple[
        ApplicationStateSnapshot,
        TrainingReadBoundary,
        tuple[dict[str, Any], ...] | None,
        tuple[dict[str, Any], ...] | None,
    ]:
        """Retry only transient training-boundary drift during snapshot capture."""
        state: ApplicationStateSnapshot | None = None
        training_history: tuple[dict[str, Any], ...] | None = None
        data_summary_rows: tuple[dict[str, Any], ...] | None = None
        after = self._capture_training_boundary()
        for _attempt in range(_STABLE_CAPTURE_ATTEMPTS):
            before = after
            state = self._build_state()
            training_history = (
                self._capture_training_history()
                if state.state_reliable and before.stable
                else None
            )
            data_summary_rows = (
                self._capture_data_summary_rows()
                if state.state_reliable and before.stable
                else None
            )
            after = self._capture_training_boundary()
            verified = self._state_with_verified_training_boundary(
                state,
                before=before,
                after=after,
            )
            if verified.state_reliable:
                return verified, after, training_history, data_summary_rows
            if before == after and after.stable:
                return verified, after, training_history, data_summary_rows
        if state is None:  # pragma: no cover - positive retry constant invariant
            raise RuntimeError("Application state capture did not run.")
        return (
            self._state_with_verified_training_boundary(
                state,
                before=before,
                after=after,
            ),
            after,
            training_history,
            data_summary_rows,
        )

    def _capture_training_history(self) -> tuple[dict[str, Any], ...] | None:
        """Detach Training rows inside the surrounding stable read boundary."""
        if self._build_training_history is None:
            return None
        return tuple(deepcopy(self._build_training_history()))

    def _capture_data_summary_rows(self) -> tuple[dict[str, Any], ...] | None:
        """Detach aggregate summary rows inside the publication boundary."""
        if self._build_data_summary_rows is None:
            return None
        return tuple(deepcopy(self._build_data_summary_rows()))

    def mark_stale(self, reason: str) -> ApplicationViewPublication:
        """Mark the committed generation stale while a command owns mutation."""
        return self._store.mark_stale(reason)

    def restore_control_flow_if_unchanged(
        self,
        expected: ApplicationViewPublication,
    ) -> tuple[ApplicationStateSnapshot, bool]:
        """Restore a command's prior publication only after a strict state check."""
        if not expected.usable:
            return deepcopy(expected.state), False
        before_boundary = self._capture_training_boundary()
        try:
            state = self._build_state()
            training_history = self._capture_training_history()
            data_summary_rows = self._capture_data_summary_rows()
            after_boundary = self._capture_training_boundary()
        except Exception as exc:
            self._store.mark_stale(exc)
            raise
        state = self._state_with_verified_training_boundary(
            state,
            before=before_boundary,
            after=after_boundary,
        )
        if not state.state_reliable:
            self._store.mark_stale(self._unreliable_state_error(state))
            return deepcopy(state), False
        if (
            state != expected.state
            or after_boundary != expected.training_boundary
            or training_history != expected.training_history
            or data_summary_rows != expected.data_summary_rows
        ):
            return deepcopy(state), False
        restored = self._store.restore_verified(expected)
        return restored.state, True

    @staticmethod
    def _unreliable_state_error(state: ApplicationStateSnapshot) -> RuntimeError:
        detail = "; ".join(dict.fromkeys(state.read_errors))
        return RuntimeError(detail or "application state snapshot is unreliable")

    @staticmethod
    def _state_with_verified_training_boundary(
        state: ApplicationStateSnapshot,
        *,
        before: TrainingReadBoundary,
        after: TrainingReadBoundary,
    ) -> ApplicationStateSnapshot:
        if before == after and after.stable:
            return state
        detail = "training read boundary changed while application state was captured"
        return replace(
            state,
            state_reliable=False,
            training_liveness_reliable=False,
            read_errors=sorted({*state.read_errors, detail}),
        )
