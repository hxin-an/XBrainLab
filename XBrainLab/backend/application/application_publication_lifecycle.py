"""Application-owned observer and training publication lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from weakref import finalize, ref

from XBrainLab.backend.controller.training_controller import TrainingLifecycleEvent
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    PostTrainingSaliencyStatus,
)
from XBrainLab.backend.utils.logger import logger

from .controller_adapters import (
    TrainingControllerAdapter,
    VisualizationControllerAdapter,
)
from .post_training_saliency import (
    SaliencyTerminalNotification,
)
from .state import ApplicationStateSnapshot
from .state_service import StateSnapshotService
from .training_publication_lifecycle import (
    SaliencyTerminalDeliveryDisposition,
    SaliencyTerminalDeliveryPlan,
    TrainingPublicationLifecycleCoordinator,
)
from .training_runtime import TrainingRuntimePort
from .view_publication import ApplicationViewPublication

_ObserverCleanup = tuple[Callable[..., Any], tuple[Any, ...]]


class ApplicationPublicationLifecycle:
    """Own observer subscriptions and application publication delivery.

    ``ApplicationService`` remains the command boundary. This component owns the
    asynchronous training/saliency observer lifecycle and translates those events
    into verified application publications.
    """

    def __init__(
        self,
        *,
        training: TrainingControllerAdapter,
        training_runtime: TrainingRuntimePort,
        visualization: VisualizationControllerAdapter,
        state_snapshot: StateSnapshotService,
        command_lock: Any,
        command_admission_lock: Any,
        is_closed: Callable[[], bool],
        is_mutation_in_progress: Callable[[], bool],
        is_shutdown_fenced: Callable[[], bool],
        refresh_training_publication: Callable[[], ApplicationStateSnapshot],
        committed_view_publication: Callable[[], ApplicationViewPublication],
        publish_view_changed: Callable[[ApplicationViewPublication], bool],
        view_revision_delivered: Callable[[int], bool],
    ) -> None:
        self._training = training
        self._training_runtime = training_runtime
        self._visualization = visualization
        self._state_snapshot = state_snapshot
        self._command_lock = command_lock
        self._command_admission_lock = command_admission_lock
        self._is_closed = is_closed
        self._is_mutation_in_progress = is_mutation_in_progress
        self._is_shutdown_fenced = is_shutdown_fenced
        self._refresh_training_publication = refresh_training_publication
        self._committed_view_publication = committed_view_publication
        self._publish_view_changed = publish_view_changed
        self._view_revision_delivered = view_revision_delivered

        self.coordinator = TrainingPublicationLifecycleCoordinator(
            publish_training_terminal=self._publish_acknowledged_training_terminal,
            plan_saliency_delivery=self.plan_saliency_terminal_delivery,
            publish_training_analysis=lambda event: self._training.notify(
                "training_analysis_published",
                event,
            ),
            publish_saliency_changed=self.notify_saliency_publication_changed,
        )
        self._observer_finalizer = self._subscribe_lifecycle_observers()

    @property
    def observer_finalizer(self) -> Callable[[], Any]:
        """Return the active observer cleanup callable."""
        return self._observer_finalizer

    @observer_finalizer.setter
    def observer_finalizer(self, cleanup: Callable[[], Any]) -> None:
        """Allow lifecycle tests to fence observer cleanup deterministically."""
        self._observer_finalizer = cleanup

    @property
    def saliency_notification_boundary(self) -> Any:
        """Expose queue state for shutdown coordination and diagnostics."""
        return self.coordinator.saliency_notification_boundary

    def _subscribe_lifecycle_observers(self) -> Callable[[], Any]:
        """Bind callbacks without letting controller observers retain this owner."""
        lifecycle_ref = ref(self)
        cleanups: list[_ObserverCleanup] = []

        def weak_callback(method_name: str) -> Callable[..., object]:
            def callback(*args: Any, **kwargs: Any) -> object:
                lifecycle = lifecycle_ref()
                if lifecycle is None or lifecycle._is_closed():
                    return True
                method = getattr(lifecycle, method_name)
                return method(*args, **kwargs)

            return callback

        for event, method_name in (
            ("training_started", "publish_training_live_state"),
            ("training_updated", "publish_training_live_state"),
            ("training_stopped", "publish_training_terminal_state"),
        ):
            callback = weak_callback(method_name)
            self._training.subscribe(event, callback)
            cleanups.append((self._training.unsubscribe, (event, callback)))

        saliency_callback = weak_callback(
            "publish_post_training_saliency_terminal_state"
        )
        self._training_runtime.subscribe_saliency_terminal(saliency_callback)
        cleanups.append(
            (
                self._training_runtime.unsubscribe_saliency_terminal,
                (saliency_callback,),
            )
        )
        observer_finalizer = finalize(
            self,
            ApplicationPublicationLifecycle._unsubscribe_lifecycle_observers,
            tuple(cleanups),
        )
        observer_finalizer.atexit = False
        return observer_finalizer

    @staticmethod
    def _unsubscribe_lifecycle_observers(
        cleanups: tuple[_ObserverCleanup, ...],
    ) -> None:
        """Release subscriptions in reverse registration order."""
        for cleanup in reversed(cleanups):
            ApplicationPublicationLifecycle._unsubscribe_lifecycle_observer(cleanup)

    @staticmethod
    def _unsubscribe_lifecycle_observer(cleanup: _ObserverCleanup) -> None:
        unsubscribe, args = cleanup
        try:
            unsubscribe(*args)
        except Exception:
            logger.debug(
                "Could not remove an application publication observer",
                exc_info=True,
            )

    def close(self) -> None:
        """Idempotently release observers and retained delivery obligations."""
        self._observer_finalizer()
        self.coordinator.discard_pending()

    def publish_training_live_state(
        self,
        *_args: Any,
        **_kwargs: Any,
    ) -> None:
        """Publish one stable live-training view without delaying the monitor."""
        if self._is_mutation_in_progress():
            return
        acquired = self._command_lock.acquire(blocking=False)
        if not acquired:
            return
        publication: ApplicationViewPublication | None = None
        try:
            if self._is_mutation_in_progress():
                return
            boundary = self._state_snapshot.capture_training_read_boundary()
            if not boundary.stable:
                return
            state = self._refresh_training_publication()
            if not state.state_reliable:
                logger.debug(
                    "Skipped an unstable live training publication; a later "
                    "training event will retry."
                )
            else:
                publication = self._committed_view_publication()
        except Exception:
            logger.debug(
                "Could not publish live training state; keeping the last verified "
                "UI view until the next training event.",
                exc_info=True,
            )
        finally:
            self._command_lock.release()
        if publication is not None:
            self._publish_view_changed(publication)

    def publish_training_terminal_state(
        self,
        *_args: Any,
        **_kwargs: Any,
    ) -> bool:
        """Commit terminal training truth from the backend monitor thread."""
        lifecycle_event: TrainingLifecycleEvent | None = None
        publication: ApplicationViewPublication | None = None
        try:
            with self._command_lock:
                state = self._refresh_training_publication()
                lifecycle_event = self.terminal_training_publication_event(state)
                if state.state_reliable:
                    publication = self._committed_view_publication()
        except Exception:
            logger.exception("Could not publish terminal training state")
            return False
        view_delivered = publication is None or self._publish_view_changed(publication)
        if lifecycle_event is None:
            return view_delivered
        terminal_delivered = self.deliver_training_terminal_publication(lifecycle_event)
        return view_delivered and terminal_delivered

    def deliver_training_terminal_publication(
        self,
        lifecycle_event: TrainingLifecycleEvent,
    ) -> bool:
        """Delegate terminal acknowledgement ownership to the coordinator."""
        return self.coordinator.publish_training_terminal(lifecycle_event)

    def terminal_training_publication_event(
        self,
        state: ApplicationStateSnapshot,
    ) -> TrainingLifecycleEvent | None:
        """Describe the exact committed terminal generation for UI delivery."""
        publication = self._committed_view_publication()
        boundary = publication.training_boundary
        outcome = state.training.terminal_outcome
        run = outcome.run
        if (
            not boundary.stable
            or not publication.usable
            or publication.state != state
            or not outcome.is_terminal
            or run is None
            or run.trainer_id != boundary.trainer_identity
        ):
            return None
        return TrainingLifecycleEvent(
            token=boundary.token,
            outcome=outcome,
            publication_generation=publication.generation,
            publication_revision=publication.revision,
        )

    def _publish_acknowledged_training_terminal(
        self,
        event: TrainingLifecycleEvent,
    ) -> object:
        """Notify terminal observers only after the matching view was rendered."""
        revision = event.publication_revision
        if revision is not None and not self._view_revision_delivered(revision):
            return False
        return self._training.notify(
            "training_terminal_published",
            event,
        )

    def publish_post_training_saliency_terminal_state(
        self,
        status: PostTrainingSaliencyStatus,
    ) -> bool:
        """Publish a terminal saliency status through the coordinator."""
        return self.coordinator.publish_saliency_terminal(
            status,
            reconcile=self.reconcile_pending_saliency_terminal,
        )

    def commit_post_training_saliency_terminal_state(
        self,
        status: PostTrainingSaliencyStatus,
    ) -> bool:
        """Commit a manager-deferred status through the coordinator ledger."""
        return self.coordinator.commit_saliency_terminal(
            status,
            reconcile=self.reconcile_pending_saliency_terminal,
        )

    def remember_pending_saliency_terminal(
        self,
        status: PostTrainingSaliencyStatus,
    ) -> None:
        """Retain one terminal status until delivery can be reconciled."""
        self.coordinator.remember_saliency_terminal(status)

    def pending_saliency_terminal(self) -> PostTrainingSaliencyStatus | None:
        """Return the terminal identity awaiting delivery."""
        return self.coordinator.pending_saliency_terminal()

    def clear_pending_saliency_terminal(
        self,
        status: PostTrainingSaliencyStatus,
    ) -> None:
        """Discard one exact delivery obligation."""
        self.coordinator.discard_saliency_terminal(status)

    def reconcile_pending_saliency_terminal(
        self,
        *,
        allow_shutdown_fenced: bool = False,
        blocking: bool = True,
    ) -> bool:
        """Reserve and stage retryable terminal delivery outside observers."""
        if self._is_shutdown_fenced() and not allow_shutdown_fenced:
            return False
        status = self.pending_saliency_terminal()
        if status is None:
            return True
        notification: SaliencyTerminalNotification | None = None
        discard_pending = False
        command_acquired = self._command_lock.acquire(blocking=blocking)
        if not command_acquired:
            return False
        admission_acquired = False
        try:
            admission_acquired = self._command_admission_lock.acquire(blocking=blocking)
            if not admission_acquired:
                return False
            if self._is_closed():
                discard_pending = True
            elif self._is_shutdown_fenced() and not allow_shutdown_fenced:
                return False
            else:
                current = self._training_runtime.saliency_status()
                if current != status:
                    discard_pending = True
                else:
                    publication = self._committed_view_publication()
                    published_status = (
                        publication.state.visualization.post_training_saliency
                    )
                    analysis_event = None
                    if published_status == status:
                        analysis_event = self.terminal_training_publication_event(
                            publication.state
                        )
                    if analysis_event is None:
                        state = self._refresh_training_publication()
                        if state.visualization.post_training_saliency != status:
                            discard_pending = True
                        else:
                            analysis_event = self.terminal_training_publication_event(
                                state
                            )
                    if analysis_event is not None:
                        notification = SaliencyTerminalNotification(
                            status=status,
                            analysis_event=analysis_event,
                            visualization_batch_generation=(
                                self.visualization_batch_generation()
                            ),
                        )
        except Exception:
            logger.exception("Could not publish terminal saliency state")
            return False
        finally:
            if admission_acquired:
                self._command_admission_lock.release()
            self._command_lock.release()

        if discard_pending:
            self.clear_pending_saliency_terminal(status)
            return True
        if notification is None:
            return False
        return self.coordinator.stage_saliency_notification(notification)

    def plan_saliency_terminal_delivery(
        self,
        notification: SaliencyTerminalNotification,
    ) -> SaliencyTerminalDeliveryPlan:
        """Resolve current backend truth without owning delivery progress."""
        if self._is_closed():
            return SaliencyTerminalDeliveryPlan(
                disposition=SaliencyTerminalDeliveryDisposition.DISCARD,
            )
        current = self._training_runtime.saliency_status()
        publication = self._committed_view_publication()
        retired_cancellation = (
            notification.status.phase is PostTrainingSaliencyPhase.CANCELLED
            and current.phase is PostTrainingSaliencyPhase.IDLE
            and current.generation > notification.status.generation
        )
        if current != notification.status and not retired_cancellation:
            return SaliencyTerminalDeliveryPlan(
                disposition=SaliencyTerminalDeliveryDisposition.DISCARD,
            )
        if not retired_cancellation and (
            not publication.usable
            or publication.state.visualization.post_training_saliency
            != notification.status
        ):
            return SaliencyTerminalDeliveryPlan(
                disposition=SaliencyTerminalDeliveryDisposition.RETRY,
            )

        analysis_event = notification.analysis_event
        if not retired_cancellation:
            latest_event = self.terminal_training_publication_event(publication.state)
            if latest_event is not None:
                analysis_event = latest_event
        return SaliencyTerminalDeliveryPlan(
            disposition=SaliencyTerminalDeliveryDisposition.DELIVER,
            analysis_event=analysis_event,
        )

    def notify_saliency_publication_changed(
        self,
        notification: SaliencyTerminalNotification | None = None,
    ) -> bool:
        """Deliver a visualization refresh after publication locks are released."""
        if self._is_closed():
            return True
        if self._is_mutation_in_progress():
            return False
        if not self._publish_view_changed(self._committed_view_publication()):
            return False
        if notification is not None:
            generation = notification.visualization_batch_generation
            if generation is not None:
                batched_result = self._visualization.consume_batched_delivery(
                    "saliency_changed",
                    generation,
                )
                if batched_result is True:
                    return True
                if self._visualization.is_notification_batch_active(generation):
                    return False
        if self._visualization.notifications_deferred:
            return False
        try:
            return self._visualization.notify("saliency_changed") is not False
        except Exception:
            logger.exception("Could not deliver terminal saliency publication")
            return False

    def visualization_batch_generation(self) -> int | None:
        """Return the controller batch owning the current command, if any."""
        generation = self._visualization.notification_batch_generation
        return generation if isinstance(generation, int) else None
