"""Atomic read model published after verified application state transitions."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field, replace
from threading import Lock

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

PUBLIC_VIEW_UNAVAILABLE_CODE = "application_state_unavailable"
PUBLIC_VIEW_UNAVAILABLE_MESSAGE = "Workflow state is temporarily unavailable."


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
    training_boundary: TrainingReadBoundary = field(
        default_factory=TrainingReadBoundary.no_trainer
    )
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
            training_boundary=deepcopy(initial_training_boundary),
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
                    )
                    else current.generation + 1
                ),
                state=safe_state,
                capabilities=capabilities,
                training_boundary=deepcopy(training_boundary),
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
            self._publication = ApplicationViewPublication(
                generation=current.generation,
                state=fail_closed_state,
                capabilities=build_capability_policy(fail_closed_state),
                training_boundary=deepcopy(current.training_boundary),
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
                training_boundary=deepcopy(expected.training_boundary),
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
        capture_training_boundary: Callable[[], TrainingReadBoundary],
    ) -> None:
        self._store = ApplicationViewStore(
            initial_state,
            initial_training_boundary,
        )
        self._build_state = build_state
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
        before_boundary = self._capture_training_boundary()
        try:
            state = self._build_state()
            after_boundary = self._capture_training_boundary()
            state = self._state_with_verified_training_boundary(
                state,
                before=before_boundary,
                after=after_boundary,
            )
            if state.state_reliable:
                return (
                    self._store.publish(state, after_boundary).state
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
        before_boundary = self._capture_training_boundary()
        try:
            state = self._build_state()
            after_boundary = self._capture_training_boundary()
            state = self._state_with_verified_training_boundary(
                state,
                before=before_boundary,
                after=after_boundary,
            )
            if not state.state_reliable:
                return self._store.mark_stale(self._unreliable_state_error(state))
            return self._store.publish(state, after_boundary)
        except Exception as exc:
            return self._store.mark_stale(exc)

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
        if state != expected.state or after_boundary != expected.training_boundary:
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
