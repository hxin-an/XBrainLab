"""Own Assistant-only publication delivery and correlated training notices."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import QObject, QTimer

from XBrainLab.backend.application import (
    APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
    ApplicationService,
)
from XBrainLab.backend.application.view_publication import ApplicationViewPublication
from XBrainLab.backend.training_state_contract import (
    TrainingOutcomeState,
    TrainingRunIdentity,
    TrainingTerminalOutcome,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.llm.agent.turn import AssistantTurnCorrelation
from XBrainLab.llm.tools.result_contract import (
    ToolCommandResult,
    safe_unexpected_failure,
)
from XBrainLab.ui.components.assistant_status_projection import (
    AssistantStatusProjection,
    build_assistant_status_projection,
)
from XBrainLab.ui.core.observer_bridge import QtObserverBridge


@dataclass(frozen=True, slots=True)
class AssistantTrainingAttemptSession:
    """Typed identity for one training job admitted through the Assistant."""

    run: TrainingRunIdentity | None
    correlation: AssistantTurnCorrelation


@dataclass(frozen=True, slots=True)
class AssistantTrainingTerminalNotice:
    """Typed terminal state waiting for the initiating turn to finish."""

    outcome: TrainingOutcomeState
    correlation: AssistantTurnCorrelation


class AssistantApplicationPublicationCoordinator(QObject):
    """Deliver committed backend truth without acknowledging Desktop delivery.

    The same owner retains failed renders, schedules retries, commits a rendered
    revision and correlates training completion. Callbacks only render UI or
    query turn idleness; they do not own delivery state.
    """

    def __init__(
        self,
        *,
        service: ApplicationService,
        render_status: Callable[[AssistantStatusProjection], bool],
        render_terminal: Callable[[AssistantTrainingTerminalNotice], bool],
        is_idle: Callable[[], bool],
        parent: QObject,
        retry_interval_ms: int = 25,
        max_fast_retries: int = 3,
        recovery_interval_ms: int = 500,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._render_status = render_status
        self._render_terminal = render_terminal
        self._is_idle = is_idle
        self._retry_interval_ms = retry_interval_ms
        self._max_fast_retries = max_fast_retries
        self._recovery_interval_ms = recovery_interval_ms
        self._closed = False
        self._projection: AssistantStatusProjection | None = None
        self._pending_publication: ApplicationViewPublication | None = None
        self._publication_retry_attempts = 0
        self._training_watch: AssistantTrainingAttemptSession | None = None
        self._pending_training_terminal: AssistantTrainingTerminalNotice | None = None
        self._publication_timer = QTimer(self)
        self._publication_timer.setSingleShot(True)
        self._publication_timer.timeout.connect(self._retry_publication)
        self._terminal_timer = QTimer(self)
        self._terminal_timer.setSingleShot(True)
        self._terminal_timer.setInterval(500)
        self._terminal_timer.timeout.connect(self.flush_terminal)
        self._bridge = QtObserverBridge(
            service,
            APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
            self,
        )
        self._bridge.connect_to(self.deliver)

    @property
    def projection(self) -> AssistantStatusProjection | None:
        """Last successfully rendered workflow truth, also used for runtime refresh."""
        return self._projection

    def refresh(self) -> None:
        """Pull and push use the same render/commit boundary."""
        try:
            self.deliver(self._service.get_view_publication())
        except Exception:
            self._projection = None
            raise

    def deliver(self, publication: object) -> bool:
        """Commit only newer successful renders; retain failures for retry."""
        if not isinstance(publication, ApplicationViewPublication):
            logger.error("Ignored malformed application publication event")
            return False
        if self._closed:
            return False
        if (
            self._projection is not None
            and publication.revision <= self._projection.publication_revision
        ):
            return True
        try:
            projection = build_assistant_status_projection(publication)
            rendered = self._render_status(projection)
        except Exception:
            self._schedule_publication_retry(publication)
            raise
        if rendered is not True:
            self._schedule_publication_retry(publication)
            return False
        self._projection = projection
        self._observe_training_publication(publication)
        pending = self._pending_publication
        if pending is not None and pending.revision <= publication.revision:
            self._pending_publication = None
            self._publication_retry_attempts = 0
            self._publication_timer.stop()
        return True

    def _schedule_publication_retry(
        self, publication: ApplicationViewPublication
    ) -> None:
        pending = self._pending_publication
        if self._closed:
            return
        if pending is None or publication.revision > pending.revision:
            self._pending_publication = publication
            self._publication_retry_attempts = 0
            self._publication_timer.stop()
        elif publication.revision < pending.revision:
            return
        if not self._publication_timer.isActive():
            self._publication_timer.start(
                self._recovery_interval_ms
                if self._publication_retry_attempts >= self._max_fast_retries
                else self._retry_interval_ms
            )

    def _retry_publication(self) -> None:
        publication = self._pending_publication
        if self._closed or publication is None:
            return
        if self._publication_retry_attempts >= self._max_fast_retries:
            self._publication_retry_attempts = 0
        self._publication_retry_attempts += 1
        try:
            self.deliver(publication)
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="assistant_application_publication",
                operation="retry_view_publication_render",
            )

    def begin_training_watch(
        self,
        result: object,
        correlation: AssistantTurnCorrelation | None,
    ) -> bool:
        """Track only a typed asynchronous training run from the active turn."""
        if (
            self._closed
            or not isinstance(result, ToolCommandResult)
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
            run=self._serialized_training_run(
                outcome.get("run") if isinstance(outcome, dict) else None
            ),
            correlation=correlation,
        )
        self._pending_training_terminal = None
        # A fast run may have finished before the command result reached the UI.
        try:
            self._observe_training_publication(self._service.get_view_publication())
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="assistant_application_publication",
                operation="reconcile_assistant_training_terminal",
            )
        return True

    def _observe_training_publication(
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
        if watch.run is None or outcome.run != watch.run:
            return None
        notice = AssistantTrainingTerminalNotice(
            outcome=outcome.state,
            correlation=watch.correlation,
        )
        self._training_watch = None
        self._pending_training_terminal = notice
        self.flush_terminal()
        return notice

    def flush_terminal(self) -> bool:
        """Keep an idle turn's notice until its visible transcript append succeeds."""
        notice = self._pending_training_terminal
        if self._closed or notice is None or not self._is_idle():
            return False
        if self._render_terminal(notice):
            if self._pending_training_terminal is notice:
                self._pending_training_terminal = None
                self._terminal_timer.stop()
            return True
        if not self._closed:
            self._terminal_timer.start()
        return False

    def clear_training(self) -> None:
        """Clear conversation correlation without losing workflow publications."""
        self._training_watch = None
        self._pending_training_terminal = None
        self._terminal_timer.stop()

    def close(self) -> None:
        self._closed = True
        self._bridge.cleanup()
        self._publication_timer.stop()
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
