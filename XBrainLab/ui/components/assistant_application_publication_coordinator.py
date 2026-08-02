"""State owner for Assistant application publications and training terminals."""

from __future__ import annotations

from dataclasses import dataclass

from XBrainLab.backend.application import ApplicationViewPublication
from XBrainLab.backend.training_state_contract import (
    TrainingOutcomeState,
    TrainingRunIdentity,
    TrainingTerminalOutcome,
)
from XBrainLab.llm.agent.turn import AssistantTurnCorrelation
from XBrainLab.llm.tools.application_surface import ToolCommandResult


@dataclass(frozen=True, slots=True)
class AssistantTrainingAttemptSession:
    """Typed identity for one training job admitted through the Assistant."""

    initial_finished_run_count: int
    handoff_generation: int
    run: TrainingRunIdentity | None
    correlation: AssistantTurnCorrelation


@dataclass(frozen=True, slots=True)
class AssistantTrainingTerminalNotice:
    """Typed terminal state waiting for the initiating turn to finish."""

    outcome: TrainingOutcomeState
    correlation: AssistantTurnCorrelation


@dataclass(frozen=True, slots=True)
class PublicationRetrySchedule:
    """Timer instruction produced from the latest publication obligation."""

    interval_ms: int
    pending_changed: bool


@dataclass(frozen=True, slots=True)
class AssistantApplicationPublicationSnapshot:
    """Read-only view of retained publication and training obligations."""

    pending_publication: ApplicationViewPublication | None
    publication_retry_attempts: int
    training_watch: AssistantTrainingAttemptSession | None
    pending_training_terminal: AssistantTrainingTerminalNotice | None


class AssistantApplicationPublicationCoordinator:
    """Own retry and training-correlation state outside the Qt presentation host."""

    def __init__(
        self,
        *,
        retry_interval_ms: int = 25,
        max_fast_retries: int = 3,
        recovery_interval_ms: int = 500,
    ) -> None:
        self._retry_interval_ms = retry_interval_ms
        self._max_fast_retries = max_fast_retries
        self._recovery_interval_ms = recovery_interval_ms
        self._pending_publication: ApplicationViewPublication | None = None
        self._publication_retry_attempts = 0
        self._training_watch: AssistantTrainingAttemptSession | None = None
        self._pending_training_terminal: AssistantTrainingTerminalNotice | None = None

    def snapshot(self) -> AssistantApplicationPublicationSnapshot:
        """Return current state without transferring mutation ownership."""
        return AssistantApplicationPublicationSnapshot(
            pending_publication=self._pending_publication,
            publication_retry_attempts=self._publication_retry_attempts,
            training_watch=self._training_watch,
            pending_training_terminal=self._pending_training_terminal,
        )

    def schedule_publication_retry(
        self,
        publication: ApplicationViewPublication,
    ) -> PublicationRetrySchedule | None:
        """Coalesce to the newest revision and select fast or recovery cadence."""
        pending = self._pending_publication
        pending_changed = pending is None or publication.revision > pending.revision
        if pending_changed:
            self._pending_publication = publication
            self._publication_retry_attempts = 0
        elif pending is not None and publication.revision < pending.revision:
            return None
        interval = (
            self._recovery_interval_ms
            if self._publication_retry_attempts >= self._max_fast_retries
            else self._retry_interval_ms
        )
        return PublicationRetrySchedule(
            interval_ms=interval,
            pending_changed=pending_changed,
        )

    def begin_publication_retry(self) -> ApplicationViewPublication | None:
        """Consume one retry attempt while keeping its delivery obligation."""
        publication = self._pending_publication
        if publication is None:
            return None
        if self._publication_retry_attempts >= self._max_fast_retries:
            self._publication_retry_attempts = 0
        self._publication_retry_attempts += 1
        return publication

    def complete_publication(self, revision: int) -> bool:
        """Clear retry state only after this or a newer revision rendered."""
        pending = self._pending_publication
        if pending is None or pending.revision > revision:
            return False
        self._pending_publication = None
        self._publication_retry_attempts = 0
        return True

    def begin_training_watch(
        self,
        result: object,
        correlation: AssistantTurnCorrelation | None,
    ) -> bool:
        """Track only a typed asynchronous training run from the active turn."""
        if (
            not isinstance(result, ToolCommandResult)
            or result.ok is not True
            or result.tool_name != "start_training"
            or result.command_name != "train"
            or not isinstance(correlation, AssistantTurnCorrelation)
        ):
            return False
        handoff_generation = result.diagnostics.get("training_handoff_generation")
        if (
            isinstance(handoff_generation, bool)
            or not isinstance(handoff_generation, int)
            or handoff_generation < 1
        ):
            return False
        training = self._serialized_training_state(result.state)
        if training is None:
            return False
        outcome = training.get("terminal_outcome")
        self._training_watch = AssistantTrainingAttemptSession(
            initial_finished_run_count=self._non_negative_int(
                training.get("finished_run_count")
            ),
            handoff_generation=handoff_generation,
            run=self._serialized_training_run(
                outcome.get("run") if isinstance(outcome, dict) else None
            ),
            correlation=correlation,
        )
        self._pending_training_terminal = None
        return True

    def observe_training_publication(
        self,
        publication: ApplicationViewPublication,
    ) -> AssistantTrainingTerminalNotice | None:
        """Correlate one authoritative terminal publication to its Assistant run."""
        watch = self._training_watch
        if (
            watch is None
            or not publication.usable
            or not publication.state.training_liveness_reliable
        ):
            return None
        training = publication.state.training
        outcome = training.terminal_outcome
        if not isinstance(outcome, TrainingTerminalOutcome) or not outcome.is_terminal:
            return None
        if (
            watch.run is not None
            and outcome.run is not None
            and outcome.run != watch.run
        ):
            return None
        if (
            outcome.state is TrainingOutcomeState.COMPLETED
            and outcome.run is None
            and training.finished_run_count <= watch.initial_finished_run_count
        ):
            return None
        notice = AssistantTrainingTerminalNotice(
            outcome=outcome.state,
            correlation=watch.correlation,
        )
        self._training_watch = None
        self._pending_training_terminal = notice
        return notice

    def terminal_notice_if_idle(
        self,
        *,
        is_idle: bool,
    ) -> AssistantTrainingTerminalNotice | None:
        if not is_idle:
            return None
        return self._pending_training_terminal

    def complete_terminal_notice(
        self,
        notice: AssistantTrainingTerminalNotice,
    ) -> bool:
        if self._pending_training_terminal is not notice:
            return False
        self._pending_training_terminal = None
        return True

    def clear_training(self) -> None:
        """Drop conversation-owned training correlation without losing publications."""
        self._training_watch = None
        self._pending_training_terminal = None

    def clear(self) -> None:
        self._pending_publication = None
        self._publication_retry_attempts = 0
        self.clear_training()

    @staticmethod
    def _serialized_training_state(state: object) -> dict[str, object] | None:
        if not isinstance(state, dict):
            return None
        training = state.get("training")
        return training if isinstance(training, dict) else None

    @staticmethod
    def _serialized_training_run(value: object) -> TrainingRunIdentity | None:
        if not isinstance(value, dict):
            return None
        trainer_id = value.get("trainer_id")
        run_id = value.get("run_id")
        if (
            not isinstance(trainer_id, str)
            or isinstance(run_id, bool)
            or not isinstance(run_id, int)
        ):
            return None
        try:
            return TrainingRunIdentity(trainer_id=trainer_id, run_id=run_id)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _non_negative_int(value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            return 0
        return max(0, value)
