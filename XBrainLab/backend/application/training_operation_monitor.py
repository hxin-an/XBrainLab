"""Physical monitor-thread lifecycle for admitted training and saliency work."""

from __future__ import annotations

from collections.abc import Callable
from threading import Lock, Thread, current_thread
from time import monotonic

from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    TrainingOutcomeState,
)
from XBrainLab.backend.utils.public_diagnostics import public_exception_message

from .application_shutdown_lifecycle import ApplicationShutdownSnapshot
from .owned_work import (
    OwnedOperationSnapshot,
    OwnedWorkPhase,
    OwnedWorkRegistry,
)
from .training_runtime import TrainingRuntimePort


class TrainingOperationMonitor:
    """Own monitor threads while the registry remains operation truth."""

    def __init__(
        self,
        *,
        training_runtime: TrainingRuntimePort,
        registry: OwnedWorkRegistry,
        shutdown_snapshot: Callable[[], ApplicationShutdownSnapshot],
    ) -> None:
        self._training_runtime = training_runtime
        self._registry = registry
        self._shutdown_snapshot = shutdown_snapshot
        self._lock = Lock()
        self._threads: dict[str, Thread] = {}

    def start_saliency(
        self,
        operation_id: str,
        generation: object,
    ) -> OwnedOperationSnapshot:
        """Keep explicit saliency owned until generation-bound delivery ends."""
        self._registry.update(
            operation_id,
            stage="Computing saliency",
            message=f"Saliency generation {generation}",
        )
        return self._start(
            operation_id,
            target=self._monitor_saliency,
            args=(operation_id, generation),
            name=f"xbrainlab-owned-saliency-{operation_id[:8]}",
        )

    def start_training(
        self,
        operation_id: str,
        trainer_identity: str,
        handoff_generation: object,
    ) -> OwnedOperationSnapshot:
        """Keep interactive training owned until its exact run terminates."""
        self._registry.update(
            operation_id,
            stage="Training model",
            message=f"Training handoff {handoff_generation}",
        )
        return self._start(
            operation_id,
            target=self._monitor_training,
            args=(operation_id, trainer_identity),
            name=f"xbrainlab-owned-training-{operation_id[:8]}",
        )

    def wait_until_idle(self, *, timeout: float | None) -> bool:
        """Join monitor threads before reporting application idleness."""
        deadline = None if timeout is None else monotonic() + max(0.0, timeout)
        caller = current_thread()
        while True:
            with self._lock:
                monitors = tuple(self._threads.items())
            if not monitors:
                return True
            for operation_id, monitor in monitors:
                if monitor is caller:
                    return False
                remaining = (
                    None if deadline is None else max(0.0, deadline - monotonic())
                )
                monitor.join(timeout=remaining)
                if monitor.is_alive():
                    return False
                with self._lock:
                    if self._threads.get(operation_id) is monitor:
                        self._threads.pop(operation_id, None)

    def _start(
        self,
        operation_id: str,
        *,
        target: Callable[..., None],
        args: tuple[object, ...],
        name: str,
    ) -> OwnedOperationSnapshot:
        thread = Thread(target=target, args=args, name=name, daemon=True)
        with self._lock:
            self._threads[operation_id] = thread
        try:
            thread.start()
        except BaseException as exc:
            with self._lock:
                self._threads.pop(operation_id, None)
            return self._registry.fail(
                operation_id,
                message=public_exception_message(exc),
            )
        return self._registry.snapshot(operation_id)

    def _monitor_saliency(self, operation_id: str, generation: object) -> None:
        terminal_phase = OwnedWorkPhase.FAILED
        terminal_message = "Saliency computation failed."
        try:
            if (
                isinstance(generation, bool)
                or not isinstance(generation, int)
                or generation < 0
            ):
                terminal_message = "Saliency generation identity could not be verified."
            else:
                generation_matches = True
                while not self._training_runtime.wait_for_saliency_job(timeout=0.25):
                    status = self._training_runtime.saliency_status()
                    if status.generation != generation:
                        generation_matches = False
                        break
                    phase = status.phase
                    self._registry.update(
                        operation_id,
                        stage=(
                            "Cancelling saliency"
                            if self._registry.snapshot(operation_id).cancel_requested
                            else "Computing saliency"
                            if phase is PostTrainingSaliencyPhase.RUNNING
                            else "Preparing saliency"
                        ),
                        message=f"Saliency generation {generation}",
                    )
                if generation_matches:
                    while True:
                        shutdown = self._shutdown_snapshot()
                        if shutdown.fenced or shutdown.closing or shutdown.closed:
                            break
                        if self._training_runtime.wait_for_saliency_delivery(
                            timeout=0.25
                        ):
                            break
                    status = self._training_runtime.saliency_status()
                    generation_matches = status.generation == generation
                if not generation_matches:
                    terminal_message = (
                        "Saliency generation identity could not be verified."
                    )
                elif status.phase is PostTrainingSaliencyPhase.SUCCEEDED:
                    terminal_phase = OwnedWorkPhase.COMPLETED
                    terminal_message = ""
                elif status.phase is PostTrainingSaliencyPhase.CANCELLED:
                    terminal_phase = OwnedWorkPhase.CANCELLED
                    terminal_message = ""
                else:
                    terminal_message = status.message or "Saliency computation failed."
        except BaseException as exc:
            terminal_phase = OwnedWorkPhase.FAILED
            terminal_message = public_exception_message(exc)
        self._publish_terminal(
            operation_id,
            phase=terminal_phase,
            message=terminal_message,
        )

    def _monitor_training(self, operation_id: str, trainer_identity: str) -> None:
        terminal_phase = OwnedWorkPhase.FAILED
        terminal_message = "Training did not complete successfully."
        try:
            self._training_runtime.wait_for_training_completion(
                expected_trainer_identity=trainer_identity,
                timeout=None,
            )
            outcome = self._training_runtime.terminal_outcome()
            run = outcome.run
            if run is None or run.trainer_id != trainer_identity:
                terminal_message = "Training terminal identity could not be verified."
            elif outcome.state is TrainingOutcomeState.COMPLETED:
                terminal_phase = OwnedWorkPhase.COMPLETED
                terminal_message = ""
            elif outcome.state is TrainingOutcomeState.CANCELLED:
                terminal_phase = OwnedWorkPhase.CANCELLED
                terminal_message = ""
            else:
                terminal_message = (
                    outcome.detail or "Training did not complete successfully."
                )
        except BaseException as exc:
            terminal_phase = OwnedWorkPhase.FAILED
            terminal_message = public_exception_message(exc)
        self._publish_terminal(
            operation_id,
            phase=terminal_phase,
            message=terminal_message,
        )

    def _publish_terminal(
        self,
        operation_id: str,
        *,
        phase: OwnedWorkPhase,
        message: str,
    ) -> OwnedOperationSnapshot:
        if phase is OwnedWorkPhase.COMPLETED:
            return self._registry.complete(operation_id)
        if phase is OwnedWorkPhase.CANCELLED:
            return self._registry.finish_cancelled(operation_id)
        return self._registry.fail(operation_id, message=message)
