"""Study-owned training commands and lifecycle publication state."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum
from time import monotonic
from typing import TYPE_CHECKING, Any, ClassVar, Protocol

from XBrainLab.backend.training_state_contract import (
    TrainingLifecycleEvent,
    TrainingStateToken,
    TrainingTerminalOutcome,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.utils.observer import Observable

if TYPE_CHECKING:
    from XBrainLab.backend.dataset import Dataset, Epochs
    from XBrainLab.backend.load_data import Raw
    from XBrainLab.backend.training import ModelHolder, Trainer, TrainingOption

TrainingLifecycleCallback = Callable[..., object]
DATA_SPLITTING_REQUIREMENT = "Data Splitting"


def resolve_training_missing_requirements(
    requirements: Iterable[str],
    *,
    data_splitting_ready: bool,
) -> list[str]:
    """Align materialized training requirements with deferred split readiness."""
    missing = [str(requirement) for requirement in requirements]
    if not data_splitting_ready:
        return missing
    return [
        requirement
        for requirement in missing
        if requirement != DATA_SPLITTING_REQUIREMENT
    ]


class TrainingStudyPort(Protocol):
    """Study state and mutations required by training product operations."""

    @property
    def trainer(self) -> Trainer | None: ...
    @trainer.setter
    def trainer(self, value: Trainer | None) -> None: ...
    @property
    def loaded_data_list(self) -> list[Raw]: ...
    @property
    def preprocessed_data_list(self) -> list[Raw]: ...
    @property
    def epoch_data(self) -> Epochs | None: ...
    @property
    def datasets(self) -> list[Dataset]: ...
    @property
    def model_holder(self) -> ModelHolder | None: ...
    @property
    def training_option(self) -> TrainingOption | None: ...
    @property
    def dataset_generator(self) -> Any: ...

    def is_training(self) -> bool: ...
    def generate_plan(
        self,
        force_update: bool = False,
        append: bool = False,
    ) -> None: ...
    def train(self, interact: bool = False) -> None: ...
    def stop_training(self, wait_timeout: float | None = None) -> bool: ...
    def clean_datasets(self, force_update: bool = True) -> None: ...
    def set_model_holder(
        self,
        model_holder: ModelHolder,
        force_update: bool = False,
    ) -> None: ...
    def set_training_option(
        self,
        training_option: TrainingOption,
        force_update: bool = False,
    ) -> None: ...
    def apply_training_configuration(
        self,
        *,
        model_holder: ModelHolder | None,
        training_option: TrainingOption | None,
        update_model: bool,
        update_option: bool,
    ) -> None: ...


class TrainingProductPort(Protocol):
    """Training command and lifecycle surface consumed by the application."""

    def notify(self, event_name: str, *args: Any, **kwargs: Any) -> bool: ...
    def subscribe(self, event_name: str, callback: Callable[..., Any]) -> None: ...
    def unsubscribe(self, event_name: str, callback: Callable[..., Any]) -> None: ...
    def apply_configuration(
        self,
        *,
        model_holder: Any | None,
        training_option: Any | None,
        update_model: bool,
        update_option: bool,
    ) -> None: ...
    def start_training(
        self,
        *,
        append: bool = True,
        interactive: bool = True,
    ) -> int: ...
    def clear_history(self) -> None: ...
    def get_trainer(self) -> Any | None: ...
    def capture_trainer_startup_snapshot(self) -> Any | None: ...
    def restore_trainer_after_failed_start(
        self,
        trainer: Any | None,
        startup_snapshot: Any | None,
    ) -> None: ...
    def apply_data_splitting(self, generator: Any) -> None: ...
    def clean_datasets(self, force_update: bool = False) -> None: ...
    def is_training(self) -> bool: ...
    def wait_for_terminal_notification(
        self,
        generation: int | None = None,
        *,
        timeout: float | None = None,
    ) -> bool: ...
    def wait_until_restart_safe(self, *, timeout: float | None = None) -> bool: ...
    def cancel_terminal_notification_waits(self, reason: str) -> None: ...
    def get_progress_text(self) -> str: ...
    def get_formatted_history(self) -> list[dict[str, Any]]: ...
    def subscribe_training_started(
        self,
        callback: TrainingLifecycleCallback,
    ) -> None: ...
    def unsubscribe_training_started(
        self,
        callback: TrainingLifecycleCallback,
    ) -> None: ...
    def subscribe_training_updated(
        self,
        callback: TrainingLifecycleCallback,
    ) -> None: ...
    def unsubscribe_training_updated(
        self,
        callback: TrainingLifecycleCallback,
    ) -> None: ...
    def subscribe_training_stopped(
        self,
        callback: TrainingLifecycleCallback,
    ) -> None: ...
    def unsubscribe_training_stopped(
        self,
        callback: TrainingLifecycleCallback,
    ) -> None: ...
    def publish_training_terminal(self, event: TrainingLifecycleEvent) -> object: ...
    def publish_training_analysis(self, event: TrainingLifecycleEvent) -> object: ...


class _TerminalHandoffPhase(str, Enum):
    PENDING = "pending"
    UNACKNOWLEDGED = "unacknowledged"
    NOTIFIED = "notified"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class _TerminalHandoff:
    """Completion state for one exact service-admitted training run."""

    generation: int
    complete: threading.Event = field(default_factory=threading.Event)
    phase: _TerminalHandoffPhase = _TerminalHandoffPhase.PENDING
    detail: str | None = None


class TrainingStateService(Observable):
    """Own training commands, monitoring, and terminal handoff state."""

    events: ClassVar[list[str]] = [
        "training_started",
        "training_started_state",
        "training_stopped",
        "training_terminal_published",
        "training_analysis_published",
        "training_updated",
        "config_changed",
        "history_cleared",
    ]

    def __init__(self, study: TrainingStudyPort) -> None:
        super().__init__()
        self._study = study
        self._monitor_thread: threading.Thread | None = None
        self._shutdown_event = threading.Event()
        self._terminal_handoff_lock = threading.Lock()
        self._terminal_handoff_sequence = 0
        self._active_terminal_handoff: int | None = None
        self._terminal_handoffs: dict[int, _TerminalHandoff] = {}

    def is_training(self) -> bool:
        return self._study.is_training()

    def start_training(self, *, append: bool = True, interactive: bool = True) -> int:
        """Generate a plan and admit one synchronous or asynchronous run."""
        if self.is_training():
            raise RuntimeError("Training is already running")

        self._retire_previous_monitor()
        handoff = self._reserve_terminal_handoff()

        try:
            self._study.generate_plan(force_update=True, append=append)
            if interactive:
                self._study.train(interact=True)
                lifecycle = self._lifecycle_event()
                if lifecycle is not None:
                    self.notify("training_started_state", lifecycle)
                self.notify("training_started")
                self._start_monitoring(handoff.generation)
                return handoff.generation

            self.notify("training_started")
            try:
                self._study.train(interact=False)
            finally:
                self._publish_training_stopped(handoff.generation)
        except BaseException as exc:
            self._complete_terminal_handoff(
                handoff.generation,
                phase=_TerminalHandoffPhase.FAILED,
                detail=f"Training start failed: {type(exc).__name__}: {exc}",
            )
            raise
        return handoff.generation

    def _lifecycle_event(self) -> TrainingLifecycleEvent | None:
        trainer = self._study.trainer
        get_token = getattr(trainer, "get_state_snapshot_token", None)
        get_outcome = getattr(trainer, "get_terminal_outcome", None)
        if not callable(get_token) or not callable(get_outcome):
            return None
        try:
            token = get_token()
            outcome = get_outcome()
        except Exception:
            return None
        if not isinstance(token, TrainingStateToken) or not isinstance(
            outcome,
            TrainingTerminalOutcome,
        ):
            return None
        return TrainingLifecycleEvent(token=token, outcome=outcome)

    def stop_training(self) -> None:
        """Request stop; the monitor remains the sole terminal event emitter."""
        if self.is_training():
            self._study.stop_training()

    def shutdown(self) -> None:
        self._shutdown_event.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=1.0)
        self.cancel_terminal_notification_waits(
            "Training monitoring stopped during application shutdown."
        )

    def wait_for_terminal_notification(
        self,
        generation: int | None = None,
        *,
        timeout: float | None = None,
    ) -> bool:
        with self._terminal_handoff_lock:
            target_generation = (
                self._terminal_handoff_sequence if generation is None else generation
            )
            if target_generation == 0:
                return True
            handoff = self._terminal_handoffs.get(target_generation)
        if handoff is None or not handoff.complete.wait(timeout=timeout):
            return False
        with self._terminal_handoff_lock:
            current = self._terminal_handoffs.get(target_generation)
            return (
                current is not None
                and current is handoff
                and current.phase is _TerminalHandoffPhase.NOTIFIED
            )

    def wait_until_restart_safe(self, *, timeout: float | None = None) -> bool:
        """Wait until terminal publication and its monitor have both retired."""
        if self._study.is_training():
            return False

        deadline = None if timeout is None else monotonic() + max(0.0, timeout)

        def remaining() -> float | None:
            if deadline is None:
                return None
            return max(0.0, deadline - monotonic())

        with self._terminal_handoff_lock:
            active_generation = self._active_terminal_handoff
            handoff = (
                self._terminal_handoffs.get(active_generation)
                if active_generation is not None
                else None
            )
        if handoff is not None and not handoff.complete.wait(timeout=remaining()):
            return False
        if handoff is not None:
            with self._terminal_handoff_lock:
                current = self._terminal_handoffs.get(handoff.generation)
                if (
                    current is None
                    or current is not handoff
                    or current.phase is not _TerminalHandoffPhase.NOTIFIED
                ):
                    return False

        thread = self._monitor_thread
        if thread is None:
            return True
        if thread is threading.current_thread():
            return False
        if thread.is_alive():
            thread.join(timeout=remaining())
        if thread.is_alive():
            return False
        if self._monitor_thread is thread:
            self._monitor_thread = None
        return True

    def cancel_terminal_notification_waits(self, reason: str) -> None:
        detail = str(reason).strip() or "Training terminal notification was cancelled."
        with self._terminal_handoff_lock:
            pending = [
                handoff
                for handoff in self._terminal_handoffs.values()
                if handoff.phase
                in {
                    _TerminalHandoffPhase.PENDING,
                    _TerminalHandoffPhase.UNACKNOWLEDGED,
                }
            ]
            for handoff in pending:
                handoff.phase = _TerminalHandoffPhase.CANCELLED
                handoff.detail = detail
                handoff.complete.set()
                if self._active_terminal_handoff == handoff.generation:
                    self._active_terminal_handoff = None

    def _start_monitoring(self, generation: int) -> None:
        if self._monitor_thread and self._monitor_thread.is_alive():
            raise RuntimeError("The previous training monitor is still shutting down")

        self._shutdown_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(generation,),
            daemon=True,
        )
        self._monitor_thread.start()

    def _monitor_loop(self, generation: int) -> None:
        terminal_attempted = False
        try:
            while not self._shutdown_event.is_set():
                if not self.is_training():
                    terminal_attempted = True
                    self._publish_training_stopped(generation)
                    return

                self.notify("training_updated")
                if self._shutdown_event.wait(1.0):
                    return
        except BaseException as exc:
            logger.exception("Training monitor failed")
            self._complete_terminal_handoff(
                generation,
                phase=_TerminalHandoffPhase.FAILED,
                detail=f"Training monitor failed: {type(exc).__name__}: {exc}",
            )
        finally:
            if not terminal_attempted:
                phase = (
                    _TerminalHandoffPhase.CANCELLED
                    if self._shutdown_event.is_set()
                    else _TerminalHandoffPhase.FAILED
                )
                self._complete_terminal_handoff(
                    generation,
                    phase=phase,
                    detail=(
                        "Training monitor stopped before terminal notification."
                        if phase is _TerminalHandoffPhase.CANCELLED
                        else "Training monitor exited before terminal notification."
                    ),
                )

    def _publish_training_stopped(self, generation: int) -> bool:
        try:
            delivered = self.notify("training_stopped")
        except BaseException as exc:
            logger.exception("Training terminal notification failed")
            self._complete_terminal_handoff(
                generation,
                phase=_TerminalHandoffPhase.FAILED,
                detail=f"Terminal notification failed: {type(exc).__name__}: {exc}",
            )
            return False
        self._complete_terminal_handoff(
            generation,
            phase=(
                _TerminalHandoffPhase.NOTIFIED
                if delivered
                else _TerminalHandoffPhase.UNACKNOWLEDGED
            ),
            detail=(
                None if delivered else "Terminal publication was not acknowledged."
            ),
        )
        return delivered

    def _reserve_terminal_handoff(self) -> _TerminalHandoff:
        with self._terminal_handoff_lock:
            active_generation = self._active_terminal_handoff
            if active_generation is not None:
                active = self._terminal_handoffs.get(active_generation)
                if active is not None and active.phase in {
                    _TerminalHandoffPhase.PENDING,
                    _TerminalHandoffPhase.UNACKNOWLEDGED,
                }:
                    raise RuntimeError(
                        "The previous training terminal handoff was not delivered"
                    )
            self._terminal_handoff_sequence += 1
            handoff = _TerminalHandoff(generation=self._terminal_handoff_sequence)
            self._terminal_handoffs[handoff.generation] = handoff
            self._active_terminal_handoff = handoff.generation
            self._prune_terminal_handoffs_locked()
            return handoff

    def _complete_terminal_handoff(
        self,
        generation: int,
        *,
        phase: _TerminalHandoffPhase,
        detail: str | None,
    ) -> None:
        with self._terminal_handoff_lock:
            handoff = self._terminal_handoffs.get(generation)
            if handoff is None or handoff.phase is not _TerminalHandoffPhase.PENDING:
                return
            handoff.phase = phase
            handoff.detail = detail
            if phase is _TerminalHandoffPhase.UNACKNOWLEDGED:
                return
            handoff.complete.set()
            if self._active_terminal_handoff == generation:
                self._active_terminal_handoff = None

    def _retire_previous_monitor(self) -> None:
        thread = self._monitor_thread
        if thread is None or not thread.is_alive():
            return
        thread.join(timeout=1.0)
        if thread.is_alive():
            raise RuntimeError("The previous training monitor is still shutting down")

    def _prune_terminal_handoffs_locked(self) -> None:
        completed = [
            generation
            for generation, handoff in self._terminal_handoffs.items()
            if handoff.phase
            not in {
                _TerminalHandoffPhase.PENDING,
                _TerminalHandoffPhase.UNACKNOWLEDGED,
            }
        ]
        for generation in completed[:-32]:
            self._terminal_handoffs.pop(generation, None)

    def clear_history(self) -> None:
        if self.is_training():
            raise RuntimeError("Cannot clear history while training is running")
        if self._study.trainer:
            self._study.trainer.clear_history()
            self.notify("history_cleared")

    def get_trainer(self) -> Any | None:
        return self._study.trainer

    def capture_trainer_startup_snapshot(self) -> Any | None:
        """Capture an opaque quiescent trainer snapshot for startup rollback."""
        trainer = self._study.trainer
        if trainer is None:
            return None
        capture = getattr(trainer, "capture_startup_snapshot", None)
        if not callable(capture):
            raise RuntimeError("Trainer does not support startup rollback snapshots")
        return capture()

    def restore_trainer_after_failed_start(
        self,
        trainer: Any | None,
        startup_snapshot: Any | None,
    ) -> None:
        """Restore quiescent history after replacement training fails to start."""
        current = self._study.trainer
        restore_in_place = current is trainer and trainer is not None
        if current is not None and current is not trainer:
            clean = getattr(current, "clean", None)
            if callable(clean):
                clean(force_update=True)
            self._study.trainer = trainer
        elif current is None:
            self._study.trainer = trainer
        if trainer is None or startup_snapshot is None:
            return
        if restore_in_place:
            clean = getattr(trainer, "clean", None)
            if callable(clean):
                clean(force_update=True)
        restore = getattr(trainer, "restore_startup_snapshot", None)
        if not callable(restore):
            raise RuntimeError("Trainer does not support startup rollback snapshots")
        restore(startup_snapshot)

    def get_progress_text(self) -> str:
        trainer = self._study.trainer
        if trainer is None or not hasattr(trainer, "get_progress_text"):
            return ""
        try:
            progress = trainer.get_progress_text()
        except Exception:
            return ""
        return str(progress or "")

    def get_formatted_history(self) -> list[dict[str, Any]]:
        trainer = self._study.trainer
        if not trainer:
            return []

        history: list[dict[str, Any]] = []
        holders = trainer.get_training_plan_holders()
        for plan_idx, plan in enumerate(holders):
            group_id = plan_idx + 1
            model_name = plan.model_holder.target_model.__name__
            is_active_plan = trainer.is_running() and trainer.current_idx == plan_idx
            for run_idx, record in enumerate(plan.get_plans()):
                history.append(
                    {
                        "plan": plan,
                        "record": record,
                        "group_name": f"Group {group_id}",
                        "run_name": f"{run_idx + 1}",
                        "model_name": model_name,
                        "is_active": is_active_plan,
                        "is_current_run": (
                            is_active_plan
                            and plan.get_training_repeat() == record.repeat
                        ),
                    }
                )
        return history

    def validate_ready(self) -> bool:
        return self.has_datasets() and self.has_model() and self.has_training_option()

    def get_missing_requirements(self) -> list[str]:
        missing: list[str] = []
        if not self.has_datasets():
            missing.append(DATA_SPLITTING_REQUIREMENT)
        if not self.has_model():
            missing.append("Model Selection")
        if not self.has_training_option():
            missing.append("Training Settings")
        return resolve_training_missing_requirements(
            missing,
            data_splitting_ready=self.has_datasets(),
        )

    def has_loaded_data(self) -> bool:
        return bool(self._study.loaded_data_list)

    def has_epoch_data(self) -> bool:
        return self._study.epoch_data is not None

    def get_epoch_data(self) -> Any:
        return self._study.epoch_data

    def has_datasets(self) -> bool:
        return bool(self._study.datasets)

    def has_model(self) -> bool:
        return self._study.model_holder is not None

    def has_training_option(self) -> bool:
        return self._study.training_option is not None

    def clean_datasets(self, force_update: bool = False) -> None:
        self._study.clean_datasets(force_update=force_update)

    def apply_data_splitting(self, generator: Any) -> None:
        generator.apply(self._study)
        self.notify("config_changed")

    def set_model_holder(self, holder: Any) -> None:
        self._study.set_model_holder(holder)
        self.notify("config_changed")

    def set_training_option(self, option: Any) -> None:
        self._study.set_training_option(option)
        self.notify("config_changed")

    def apply_configuration(
        self,
        *,
        model_holder: Any | None,
        training_option: Any | None,
        update_model: bool,
        update_option: bool,
    ) -> None:
        self._study.apply_training_configuration(
            model_holder=model_holder,
            training_option=training_option,
            update_model=update_model,
            update_option=update_option,
        )
        self.notify("config_changed")

    def get_training_option(self) -> Any:
        return self._study.training_option

    def get_resource_preflight_context(self) -> dict[str, Any]:
        return {
            "datasets": list(self._study.datasets or []),
            "training_option": self._study.training_option,
            "model_holder": self._study.model_holder,
        }

    def get_model_holder(self) -> Any:
        return self._study.model_holder

    def get_dataset_generator(self) -> Any:
        return self._study.dataset_generator

    def get_loaded_data_list(self) -> list[Any]:
        return self._study.loaded_data_list

    def get_preprocessed_data_list(self) -> list[Any]:
        return self._study.preprocessed_data_list

    def subscribe_training_started(
        self,
        callback: TrainingLifecycleCallback,
    ) -> None:
        self.subscribe("training_started", callback)

    def unsubscribe_training_started(
        self,
        callback: TrainingLifecycleCallback,
    ) -> None:
        self.unsubscribe("training_started", callback)

    def subscribe_training_updated(
        self,
        callback: TrainingLifecycleCallback,
    ) -> None:
        self.subscribe("training_updated", callback)

    def unsubscribe_training_updated(
        self,
        callback: TrainingLifecycleCallback,
    ) -> None:
        self.unsubscribe("training_updated", callback)

    def subscribe_training_stopped(
        self,
        callback: TrainingLifecycleCallback,
    ) -> None:
        self.subscribe("training_stopped", callback)

    def unsubscribe_training_stopped(
        self,
        callback: TrainingLifecycleCallback,
    ) -> None:
        self.unsubscribe("training_stopped", callback)

    def publish_training_terminal(self, event: TrainingLifecycleEvent) -> object:
        delivered = self.notify("training_terminal_published", event)
        if delivered:
            with self._terminal_handoff_lock:
                generation = self._active_terminal_handoff
                handoff = (
                    self._terminal_handoffs.get(generation)
                    if generation is not None
                    else None
                )
                if handoff is not None and handoff.phase in {
                    _TerminalHandoffPhase.PENDING,
                    _TerminalHandoffPhase.UNACKNOWLEDGED,
                }:
                    handoff.phase = _TerminalHandoffPhase.NOTIFIED
                    handoff.detail = None
                    handoff.complete.set()
                    self._active_terminal_handoff = None
        return delivered

    def publish_training_analysis(self, event: TrainingLifecycleEvent) -> object:
        return self.notify("training_analysis_published", event)


__all__ = [
    "TrainingProductPort",
    "TrainingStateService",
    "TrainingStudyPort",
]
