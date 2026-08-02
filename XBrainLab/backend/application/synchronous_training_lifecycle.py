"""Synchronous training completion and result-envelope ownership."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from threading import Condition
from typing import Any, Protocol

from .commands import CommandName
from .errors import ApplicationError
from .results import ChangedState, CommandResult, CommandStatus, ErrorType
from .state import ApplicationStateSnapshot
from .view_publication import ApplicationViewPublication


class TrainingTerminalNotificationPort(Protocol):
    """Exact terminal handoff wait required by synchronous command completion."""

    def wait_for_terminal_notification(
        self,
        generation: int | None = None,
        *,
        timeout: float | None = None,
    ) -> bool: ...


class TrainingCompletionRuntimePort(Protocol):
    """Narrow runtime surface needed for one exact synchronous completion."""

    def wait_for_training_completion(
        self,
        *,
        expected_trainer_identity: str,
        timeout: float | None = None,
    ) -> bool: ...


class PostStateVerificationFailureBuilder(Protocol):
    """Application boundary for fail-closed post-state verification results."""

    def __call__(
        self,
        *,
        name: CommandName,
        state: ApplicationStateSnapshot,
        diagnostics: dict[str, Any],
        error: Exception,
    ) -> CommandResult: ...


HandlerFailureBuilder = Callable[
    [
        CommandName,
        ApplicationStateSnapshot,
        ApplicationViewPublication,
        Exception,
    ],
    CommandResult,
]

_TERMINAL_NOTIFICATION_WAIT_SECONDS = 2.0
_WORKER_COMPLETION_WAIT_SECONDS = 21_600.0
_CLOSED_COMPLETION_MESSAGE = (
    "This application service is closed and cannot publish training completion."
)


class SynchronousTrainingLifecycleCoordinator:
    """Own deferred training completion without owning command dispatch.

    Worker and terminal-notification waits happen before the command lock is
    acquired. Terminal outcome verification, post-state verification, and result
    construction then run under the existing application command boundary.
    """

    def __init__(
        self,
        *,
        training_runtime: TrainingCompletionRuntimePort,
        terminal_notifications: TrainingTerminalNotificationPort,
        retry_terminal_delivery: Callable[[int], bool],
        command_lock: Any,
        complete_training: Callable[[str], tuple[str, dict[str, Any]]],
        committed_publication: Callable[[], ApplicationViewPublication],
        clear_last_error: Callable[[], None],
        state_after_command: Callable[
            [],
            tuple[ApplicationStateSnapshot, Exception | None],
        ],
        changed_state: Callable[
            [ApplicationStateSnapshot, ApplicationStateSnapshot],
            ChangedState,
        ],
        post_state_verification_failure: PostStateVerificationFailureBuilder,
        handler_failure: HandlerFailureBuilder,
        completion_is_closed: Callable[[], bool],
    ) -> None:
        self._training_runtime = training_runtime
        self._terminal_notifications = terminal_notifications
        self._retry_terminal_delivery = retry_terminal_delivery
        self._command_lock = command_lock
        self._complete_training = complete_training
        self._committed_publication = committed_publication
        self._clear_last_error = clear_last_error
        self._state_after_command = state_after_command
        self._changed_state = changed_state
        self._post_state_verification_failure = post_state_verification_failure
        self._handler_failure = handler_failure
        self._completion_is_closed = completion_is_closed
        self._activity_condition = Condition()
        self._active_deferred_completions = 0

    def admit_deferred_completion(self) -> Callable[[], None]:
        """Register one completion before releasing training-start admission."""
        with self._activity_condition:
            self._active_deferred_completions += 1
        released = False

        def release() -> None:
            nonlocal released
            with self._activity_condition:
                if released:
                    return
                released = True
                self._active_deferred_completions -= 1
                if self._active_deferred_completions < 0:
                    self._active_deferred_completions = 0
                    raise RuntimeError(
                        "Synchronous training completion activity became unbalanced."
                    )
                self._activity_condition.notify_all()

        return release

    def wait_until_quiescent(self, *, timeout: float | None = None) -> bool:
        """Wait until no admitted synchronous completion can still publish."""
        with self._activity_condition:
            return self._activity_condition.wait_for(
                lambda: self._active_deferred_completions == 0,
                timeout=timeout,
            )

    def complete_deferred(self, started: CommandResult) -> CommandResult:
        """Wait for and verify one deferred synchronous training command."""
        if self._completion_is_closed():
            return self._closed_completion_result(started)
        completion_error = self._resolve_completion_error(started)

        with self._command_lock:
            if self._completion_is_closed():
                return self._closed_completion_result(started)
            before_publication = self._committed_publication()
            try:
                self._raise_completion_error(completion_error)
                trainer_identity = self._require_trainer_identity(started)
                message, completion_diagnostics = self._complete_training(
                    trainer_identity
                )
                self._clear_last_error()
                after, refresh_error = self._state_after_command()
                if refresh_error is not None or not after.state_reliable:
                    verification_error = refresh_error or RuntimeError(
                        "; ".join(after.read_errors)
                        or "updated application state is unreliable",
                    )
                    completed = self._post_state_verification_failure(
                        name=CommandName.TRAIN,
                        state=after,
                        diagnostics=completion_diagnostics,
                        error=verification_error,
                    )
                else:
                    completed = CommandResult.success_result(
                        command_name=CommandName.TRAIN.value,
                        message=message,
                        state=after,
                        changed_state=self._changed_state(started.state, after),
                        diagnostics=completion_diagnostics,
                    )
            except Exception as exc:
                completed = self._handler_failure(
                    CommandName.TRAIN,
                    started.state,
                    before_publication,
                    exc,
                )

        return self._merge_result_envelopes(started, completed)

    @staticmethod
    def _closed_completion_result(started: CommandResult) -> CommandResult:
        diagnostics = dict(started.diagnostics)
        diagnostics.pop("synchronous_completion_deferred", None)
        diagnostics["application_service_closed"] = True
        return CommandResult.failure_result(
            command_name=CommandName.TRAIN.value,
            message=_CLOSED_COMPLETION_MESSAGE,
            state=started.state,
            changed_state=ChangedState(),
            error_type=ErrorType.PRECONDITION,
            recoverable=True,
            error_message=_CLOSED_COMPLETION_MESSAGE,
            diagnostics=diagnostics,
        )

    @staticmethod
    def _raise_completion_error(error: Exception | None) -> None:
        """Re-enter normal command failure mapping after the unlocked wait."""
        if error is not None:
            raise error

    def _resolve_completion_error(self, started: CommandResult) -> Exception | None:
        handoff_generation = self.handoff_generation(started)
        try:
            if handoff_generation is None:
                return ApplicationError(
                    message="Training terminal handoff identity is unavailable.",
                    error_type=ErrorType.TRAINING,
                    recoverable=True,
                    diagnostics={
                        "training_failed": True,
                        "training_handoff_generation_invalid": True,
                    },
                )
            trainer_identity = self._require_trainer_identity(started)
            worker_complete = self._training_runtime.wait_for_training_completion(
                expected_trainer_identity=trainer_identity,
                timeout=_WORKER_COMPLETION_WAIT_SECONDS,
            )
            if not worker_complete:
                return ApplicationError(
                    message="Training completion could not be verified.",
                    error_type=ErrorType.TRAINING,
                    recoverable=True,
                    diagnostics={"training_failed": True},
                )
            terminal_published = (
                self._terminal_notifications.wait_for_terminal_notification(
                    handoff_generation,
                    timeout=_TERMINAL_NOTIFICATION_WAIT_SECONDS,
                )
            )
            if not terminal_published and self._retry_terminal_delivery(
                handoff_generation
            ):
                terminal_published = (
                    self._terminal_notifications.wait_for_terminal_notification(
                        handoff_generation,
                        timeout=_TERMINAL_NOTIFICATION_WAIT_SECONDS,
                    )
                )
            if not terminal_published:
                return ApplicationError(
                    message="Training terminal status could not be verified.",
                    error_type=ErrorType.TRAINING,
                    recoverable=True,
                    diagnostics={
                        "training_failed": True,
                        "training_handoff_generation": handoff_generation,
                    },
                )
        except Exception as exc:
            return exc
        return None

    @staticmethod
    def handoff_generation(result: CommandResult) -> int | None:
        """Return the exact positive terminal handoff identity, if valid."""
        generation = result.diagnostics.get("training_handoff_generation")
        if (
            isinstance(generation, bool)
            or not isinstance(generation, int)
            or generation < 1
        ):
            return None
        return generation

    @staticmethod
    def trainer_identity(result: CommandResult) -> str | None:
        """Return the exact non-empty trainer identity admitted at start."""
        identity = result.diagnostics.get("training_trainer_identity")
        if not isinstance(identity, str) or not identity.strip():
            return None
        return identity.strip()

    @classmethod
    def _require_trainer_identity(cls, result: CommandResult) -> str:
        identity = cls.trainer_identity(result)
        if identity is None:
            raise ApplicationError(
                message="Training runtime identity is unavailable.",
                error_type=ErrorType.TRAINING,
                recoverable=True,
                diagnostics={
                    "training_failed": True,
                    "training_trainer_identity_invalid": True,
                },
            )
        return identity

    @staticmethod
    def background_delivery_failure(
        result: CommandResult,
        *,
        reason: str,
        invalid_handoff: bool = False,
    ) -> CommandResult:
        """Turn an unverified synchronous terminal handoff into a safe failure."""
        diagnostics = dict(result.diagnostics)
        diagnostics["background_delivery_incomplete"] = True
        if invalid_handoff:
            diagnostics["training_handoff_generation_invalid"] = True
        return replace(
            result,
            status=CommandStatus.FAILED,
            message=reason,
            error_type=ErrorType.INTERNAL,
            recoverable=True,
            error_message=reason,
            diagnostics=diagnostics,
        )

    @classmethod
    def _merge_result_envelopes(
        cls,
        started: CommandResult,
        completed: CommandResult,
    ) -> CommandResult:
        diagnostics = dict(completed.diagnostics)
        diagnostics.update(started.diagnostics)
        diagnostics.pop("synchronous_completion_deferred", None)
        return replace(
            completed,
            changed_state=cls._merge_changed_state(
                started.changed_state,
                completed.changed_state,
            ),
            diagnostics=diagnostics,
        )

    @staticmethod
    def _merge_changed_state(
        first: ChangedState,
        second: ChangedState,
    ) -> ChangedState:
        """Union state deltas produced by start and terminal completion phases."""
        return ChangedState(
            raw_changed=first.raw_changed or second.raw_changed,
            preprocessed_changed=(
                first.preprocessed_changed or second.preprocessed_changed
            ),
            epoch_changed=first.epoch_changed or second.epoch_changed,
            datasets_changed=first.datasets_changed or second.datasets_changed,
            training_changed=first.training_changed or second.training_changed,
            evaluation_changed=first.evaluation_changed or second.evaluation_changed,
            visualization_changed=(
                first.visualization_changed or second.visualization_changed
            ),
            interpretation_changed=(
                first.interpretation_changed or second.interpretation_changed
            ),
            error_changed=first.error_changed or second.error_changed,
            state_unknown=first.state_unknown or second.state_unknown,
        )
