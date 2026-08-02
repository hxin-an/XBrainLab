"""Single UI owner for the local assistant runtime lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
    AssistantRuntimeSnapshot,
)
from XBrainLab.llm.core.runtime_selection import AssistantRuntimeLaunchSpec


class AssistantRuntimeCoordinator:
    """Publish one immutable runtime truth to the assistant presentation."""

    def __init__(
        self,
        on_change: Callable[[AssistantRuntimeSnapshot], None],
    ) -> None:
        self._on_change = on_change
        self._snapshot = AssistantRuntimeSnapshot(
            phase=AssistantRuntimePhase.IDLE,
            initialized=False,
        )
        self._expected_launch_spec: AssistantRuntimeLaunchSpec | None = None
        self._expected_activation_id: int | None = None
        self._active_runtime: AssistantRuntimeSnapshot | None = None
        self._last_rejection_reason = ""

    @property
    def current(self) -> AssistantRuntimeSnapshot:
        return self._snapshot

    @property
    def expected_activation_id(self) -> int | None:
        """Return the activation request allowed to finish the current load."""
        return self._expected_activation_id

    @property
    def last_rejection_reason(self) -> str:
        """Return the most recent rejected worker-transition reason."""
        return self._last_rejection_reason

    @property
    def owns_local_runtime(self) -> bool:
        """Return whether active or in-flight state still owns a local model."""
        active = self._active_runtime
        expected = self._expected_launch_spec
        return bool(
            (active is not None and active.backend_mode == "local")
            or (expected is not None and expected.backend_mode == "local")
        )

    def begin_loading(
        self,
        launch_spec: AssistantRuntimeLaunchSpec,
        *,
        activation_id: int | None = None,
    ) -> None:
        self._expected_launch_spec = launch_spec
        request_id = activation_id
        if request_id is None:
            request_id = self._activation_id(launch_spec)
        self._expected_activation_id = request_id
        self._publish(
            AssistantRuntimeSnapshot(
                phase=AssistantRuntimePhase.LOADING,
                initialized=False,
                backend_mode=launch_spec.backend_mode,
                model_id=launch_spec.model_id,
                requested_model_id=launch_spec.requested_model_id,
                selection_outcome=launch_spec.outcome,
                selection_detail=launch_spec.selection_detail,
                execution_device=launch_spec.execution_device,
                device_fallback_reason=launch_spec.device_fallback_reason,
                activation_id=request_id or 0,
            )
        )

    def mark_unavailable(
        self,
        message: str,
        *,
        preserve_active_runtime: bool = True,
        request_context: AssistantRuntimeSnapshot | None = None,
    ) -> None:
        self._expected_launch_spec = None
        self._expected_activation_id = None
        self._publish_failed(
            message,
            preserve_active_runtime=preserve_active_runtime,
            request_context=request_context,
        )

    def clear_active_runtime(self, message: str) -> None:
        """Retire runtime identity only after its controller has been released."""
        self._active_runtime = None
        self.mark_unavailable(message, preserve_active_runtime=False)

    def restore_active_runtime(self) -> bool:
        """Republish the last confirmed ready engine after a recoverable failure."""
        if self._active_runtime is None:
            return False
        self._expected_launch_spec = None
        self._expected_activation_id = None
        self._publish(self._active_runtime)
        return True

    def accept_worker_snapshot(self, payload: object) -> bool:
        """Accept a worker transition and report whether it ended activation.

        Tagged transitions are accepted only for the currently expected request.
        Once an activation is tagged, an untagged terminal update cannot complete
        it, even when the backend/model pair happens to match.
        """
        if not isinstance(payload, AssistantRuntimeSnapshot):
            self._last_rejection_reason = "runtime transition is not typed"
            return False
        snapshot = payload
        validation_error = snapshot.validation_error()
        if validation_error:
            self._last_rejection_reason = validation_error
            return False
        self._last_rejection_reason = ""
        expected = self._expected_launch_spec
        expected_id = self._expected_activation_id
        payload_id = self._activation_id(payload)
        if expected_id is not None and payload_id is None:
            return False
        if payload_id is not None and (
            expected_id is None or payload_id != expected_id
        ):
            return False
        if (
            snapshot.phase
            in {
                AssistantRuntimePhase.READY,
                AssistantRuntimePhase.FAILED,
            }
            and expected is not None
            and payload_id is None
            and (
                snapshot.backend_mode != expected.backend_mode
                or snapshot.model_id != expected.model_id
            )
        ):
            return False
        if expected is not None:
            snapshot = replace(
                snapshot,
                requested_model_id=expected.requested_model_id,
                selection_outcome=expected.outcome,
                selection_detail=expected.selection_detail,
                execution_device=expected.execution_device,
                device_fallback_reason=expected.device_fallback_reason,
            )
        terminal = snapshot.phase in {
            AssistantRuntimePhase.READY,
            AssistantRuntimePhase.FAILED,
        }
        if snapshot.phase is AssistantRuntimePhase.READY:
            self._active_runtime = snapshot
        elif (
            snapshot.phase is AssistantRuntimePhase.FAILED
            and expected is not None
            and self._active_runtime is not None
        ):
            snapshot = self._failed_snapshot(
                snapshot.error,
                preserve_active_runtime=True,
                activation_id=snapshot.activation_id,
                request_context=snapshot,
            )
        if terminal:
            self._expected_launch_spec = None
            self._expected_activation_id = None
        self._publish(snapshot)
        return terminal

    def fail_activation(
        self,
        activation_id: int,
        message: str,
        *,
        keep_expected: bool = False,
    ) -> bool:
        """Fail only the activation that still owns the loading state.

        A timed-out load keeps ownership so a late terminal worker update can
        reconcile UI truth with the engine that actually finished loading.
        """
        if activation_id != self._expected_activation_id:
            return False
        if not keep_expected:
            self._expected_launch_spec = None
            self._expected_activation_id = None
        self._publish_failed(
            message,
            preserve_active_runtime=self._active_runtime is not None,
            activation_id=activation_id,
            request_context=self._snapshot,
        )
        return True

    def replay(self) -> None:
        self._on_change(self._snapshot)

    def _publish(self, snapshot: AssistantRuntimeSnapshot) -> None:
        self._snapshot = snapshot
        self._on_change(snapshot)

    def _publish_failed(
        self,
        message: str,
        *,
        preserve_active_runtime: bool,
        activation_id: int = 0,
        request_context: AssistantRuntimeSnapshot | None = None,
    ) -> None:
        self._publish(
            self._failed_snapshot(
                message,
                preserve_active_runtime=preserve_active_runtime,
                activation_id=activation_id,
                request_context=request_context,
            )
        )

    def _failed_snapshot(
        self,
        message: str,
        *,
        preserve_active_runtime: bool,
        activation_id: int = 0,
        request_context: AssistantRuntimeSnapshot | None = None,
    ) -> AssistantRuntimeSnapshot:
        normalized_message = " ".join(str(message or "").split())
        if preserve_active_runtime and self._active_runtime is not None:
            failed = replace(
                self._active_runtime,
                phase=AssistantRuntimePhase.FAILED,
                initialized=True,
                error=normalized_message,
                activation_id=activation_id,
            )
            if request_context is not None:
                failed = replace(
                    failed,
                    requested_model_id=request_context.requested_model_id,
                    selection_outcome=request_context.selection_outcome,
                    selection_detail=request_context.selection_detail,
                    execution_device=request_context.execution_device,
                    device_fallback_reason=request_context.device_fallback_reason,
                )
            return failed
        failed = AssistantRuntimeSnapshot(
            phase=AssistantRuntimePhase.FAILED,
            initialized=False,
            error=normalized_message,
            activation_id=activation_id,
        )
        if request_context is not None:
            failed = replace(
                failed,
                backend_mode=request_context.backend_mode,
                requested_model_id=request_context.requested_model_id,
                selection_outcome=request_context.selection_outcome,
                selection_detail=request_context.selection_detail,
                execution_device=request_context.execution_device,
                device_fallback_reason=request_context.device_fallback_reason,
            )
        return failed

    @staticmethod
    def _activation_id(payload: object) -> int | None:
        raw_value: object
        if isinstance(payload, dict):
            raw_value = payload.get("activation_id")
        else:
            raw_value = getattr(payload, "activation_id", None)
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, str)):
            return None
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None
