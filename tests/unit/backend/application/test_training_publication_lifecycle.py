from __future__ import annotations

import inspect
from threading import Event, Thread
from time import monotonic

from XBrainLab.backend.application import ApplicationService
from XBrainLab.backend.application.application_publication_lifecycle import (
    ApplicationPublicationLifecycle,
)
from XBrainLab.backend.application.post_training_saliency import (
    SaliencyTerminalNotification,
)
from XBrainLab.backend.application.training_publication_lifecycle import (
    SaliencyTerminalDeliveryDisposition,
    SaliencyTerminalDeliveryPlan,
    TrainingPublicationLifecycleCoordinator,
)
from XBrainLab.backend.study import Study
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    PostTrainingSaliencyStatus,
    TrainingLifecycleEvent,
    TrainingOutcomeState,
    TrainingRunIdentity,
    TrainingStateToken,
    TrainingTerminalOutcome,
)


def _training_event(
    *,
    token_generation: int,
    run_id: int,
    publication_generation: int,
) -> TrainingLifecycleEvent:
    return TrainingLifecycleEvent(
        token=TrainingStateToken(
            generation=token_generation,
            stable=True,
        ),
        outcome=TrainingTerminalOutcome(
            state=TrainingOutcomeState.COMPLETED,
            run=TrainingRunIdentity(
                trainer_id="publication-coordinator",
                run_id=run_id,
            ),
        ),
        publication_generation=publication_generation,
    )


def _saliency_status(*, generation: int) -> PostTrainingSaliencyStatus:
    return PostTrainingSaliencyStatus(
        phase=PostTrainingSaliencyPhase.SUCCEEDED,
        generation=generation,
        run=TrainingRunIdentity(
            trainer_id="publication-coordinator",
            run_id=generation,
        ),
        training_generation=generation + 10,
        methods=("Gradient",),
        message="Automatic saliency completed.",
    )


def _coordinator(
    *,
    publish_training_terminal=lambda _event: True,
    plan_saliency_delivery=lambda notification: SaliencyTerminalDeliveryPlan(
        disposition=SaliencyTerminalDeliveryDisposition.DELIVER,
        analysis_event=notification.analysis_event,
    ),
    publish_training_analysis=lambda _event: True,
    publish_saliency_changed=lambda _notification: True,
) -> TrainingPublicationLifecycleCoordinator:
    return TrainingPublicationLifecycleCoordinator(
        publish_training_terminal=publish_training_terminal,
        plan_saliency_delivery=plan_saliency_delivery,
        publish_training_analysis=publish_training_analysis,
        publish_saliency_changed=publish_saliency_changed,
    )


def test_application_service_delegates_publication_lifecycle_ownership() -> None:
    service = ApplicationService(Study())
    initialization = inspect.getsource(ApplicationService._initialize_components)
    service_source = inspect.getsource(ApplicationService)

    assert isinstance(
        service.publication_lifecycle,
        ApplicationPublicationLifecycle,
    )
    assert "TrainingPublicationLifecycleCoordinator(" not in initialization
    assert "self.training.subscribe(" not in service_source
    assert "subscribe_saliency_terminal(" not in service_source
    for forbidden_assignment in (
        "self._training_terminal_publication_lock =",
        "self._training_terminal_publication_active =",
        "self._training_terminal_publication_delivered =",
        "self._pending_saliency_terminal_lock =",
        "self._pending_saliency_terminal_status =",
        "self._saliency_terminal_delivery_progress =",
    ):
        assert forbidden_assignment not in initialization


def test_training_terminal_delivery_retries_once_before_acknowledgement() -> None:
    attempts: list[TrainingLifecycleEvent] = []
    acknowledgements = iter((False, True))

    def publish(event: TrainingLifecycleEvent) -> bool:
        attempts.append(event)
        return next(acknowledgements)

    coordinator = _coordinator(publish_training_terminal=publish)
    event = _training_event(
        token_generation=1,
        run_id=1,
        publication_generation=11,
    )

    assert coordinator.publish_training_terminal(event) is True
    assert coordinator.publish_training_terminal(event) is True

    assert attempts == [event, event]
    state = coordinator.training_delivery_state()
    assert state.pending_count == 0
    assert state.delivered_count == 1
    assert state.retry_count == 1


def test_training_terminal_delivery_retains_persistent_failure_for_later_retry() -> (
    None
):
    attempts: list[TrainingLifecycleEvent] = []
    acknowledge = False

    def publish(event: TrainingLifecycleEvent) -> bool:
        attempts.append(event)
        return acknowledge

    coordinator = _coordinator(publish_training_terminal=publish)
    event = _training_event(
        token_generation=2,
        run_id=2,
        publication_generation=12,
    )

    assert coordinator.publish_training_terminal(event) is False
    failed_state = coordinator.training_delivery_state()
    assert failed_state.pending_count == 1
    assert failed_state.active_count == 0
    assert failed_state.retry_count == 2

    acknowledge = True
    assert coordinator.retry_training_terminal_delivery() is True
    assert coordinator.wait_for_training_delivery(timeout=0.1) is True

    delivered_state = coordinator.training_delivery_state()
    assert delivered_state.pending_count == 0
    assert delivered_state.delivered_count == 1
    assert attempts == [event, event, event]


def test_training_terminal_delivery_autonomously_retries_persistent_failure() -> None:
    attempts: list[TrainingLifecycleEvent] = []
    autonomous_attempt = Event()

    def publish(event: TrainingLifecycleEvent) -> bool:
        attempts.append(event)
        if len(attempts) < 3:
            return False
        autonomous_attempt.set()
        return True

    coordinator = _coordinator(publish_training_terminal=publish)
    event = _training_event(
        token_generation=3,
        run_id=3,
        publication_generation=13,
    )

    assert coordinator.publish_training_terminal(event) is False
    assert autonomous_attempt.wait(timeout=1.0)
    assert coordinator.wait_for_training_delivery(timeout=1.0) is True

    state = coordinator.training_delivery_state()
    assert state.pending_count == 0
    assert state.active_count == 0
    assert state.delivered_count == 1
    assert attempts == [event, event, event]

    coordinator.close()


def test_close_fences_active_callback_without_waiting_or_committing() -> None:
    callback_started = Event()
    release_callback = Event()
    callback_finished = Event()
    close_returned = Event()
    publish_results: list[bool] = []

    def publish(_event: TrainingLifecycleEvent) -> bool:
        callback_started.set()
        released = release_callback.wait(timeout=1.0)
        callback_finished.set()
        return released

    coordinator = _coordinator(publish_training_terminal=publish)
    event = _training_event(
        token_generation=4,
        run_id=4,
        publication_generation=14,
    )
    publisher = Thread(
        target=lambda: publish_results.append(
            coordinator.publish_training_terminal(event)
        ),
        daemon=True,
    )
    closer = Thread(
        target=lambda: (coordinator.close(), close_returned.set()),
        daemon=True,
    )

    publisher.start()
    assert callback_started.wait(timeout=1.0)
    closer.start()

    assert close_returned.wait(timeout=1.0)
    assert coordinator.training_delivery_state().closed is True
    assert callback_finished.is_set() is False

    release_callback.set()
    publisher.join(timeout=1.0)
    closer.join(timeout=1.0)

    assert callback_finished.is_set()
    assert not publisher.is_alive()
    assert not closer.is_alive()
    assert publish_results == [False]

    state = coordinator.training_delivery_state()
    assert state.pending_count == 0
    assert state.active_count == 0
    assert state.delivered_count == 0
    assert state.closed is True


def test_close_rejects_new_training_terminal_delivery() -> None:
    attempts: list[TrainingLifecycleEvent] = []
    coordinator = _coordinator(
        publish_training_terminal=lambda event: attempts.append(event) or True
    )
    event = _training_event(
        token_generation=5,
        run_id=5,
        publication_generation=15,
    )

    coordinator.close()

    assert coordinator.publish_training_terminal(event) is False
    assert coordinator.retry_training_terminal_delivery() is False
    assert attempts == []

    state = coordinator.training_delivery_state()
    assert state.pending_count == 0
    assert state.active_count == 0
    assert state.delivered_count == 0
    assert state.retry_owner_active is False
    assert state.closed is True


def test_close_stops_the_pending_autonomous_retry_owner() -> None:
    attempts: list[TrainingLifecycleEvent] = []
    coordinator = _coordinator(
        publish_training_terminal=lambda event: attempts.append(event) or False
    )
    event = _training_event(
        token_generation=6,
        run_id=6,
        publication_generation=16,
    )

    assert coordinator.publish_training_terminal(event) is False
    assert coordinator.training_delivery_state().retry_owner_active is True

    coordinator.close()
    attempts_after_close = len(attempts)

    assert coordinator.publish_training_terminal(event) is False
    assert len(attempts) == attempts_after_close
    state = coordinator.training_delivery_state()
    assert state.pending_count == 0
    assert state.retry_owner_active is False
    assert state.closed is True


def test_active_callback_can_close_without_deadlocking_or_committing() -> None:
    callback_returned = Event()
    publish_results: list[bool] = []
    coordinator: TrainingPublicationLifecycleCoordinator

    def publish(_event: TrainingLifecycleEvent) -> bool:
        coordinator.close()
        callback_returned.set()
        return True

    coordinator = _coordinator(publish_training_terminal=publish)
    event = _training_event(
        token_generation=7,
        run_id=7,
        publication_generation=17,
    )
    publisher = Thread(
        target=lambda: publish_results.append(
            coordinator.publish_training_terminal(event)
        ),
        daemon=True,
    )

    publisher.start()
    publisher.join(timeout=1.0)

    assert not publisher.is_alive()
    assert callback_returned.is_set()
    assert publish_results == [False]
    assert coordinator.training_delivery_state().delivered_count == 0


def test_training_terminal_delivery_is_monotonic_across_publications() -> None:
    delivered: list[TrainingLifecycleEvent] = []
    coordinator = _coordinator(
        publish_training_terminal=lambda event: delivered.append(event) or True
    )
    first = _training_event(
        token_generation=4,
        run_id=1,
        publication_generation=20,
    )
    second = _training_event(
        token_generation=5,
        run_id=2,
        publication_generation=21,
    )
    stale = _training_event(
        token_generation=3,
        run_id=3,
        publication_generation=19,
    )

    assert coordinator.publish_training_terminal(first) is True
    assert coordinator.publish_training_terminal(second) is True
    assert coordinator.publish_training_terminal(stale) is True

    assert delivered == [first, second]
    state = coordinator.training_delivery_state()
    assert state.latest_publication_generation == 21
    assert state.delivered_count == 2


def test_training_terminal_callback_runs_outside_the_ledger_lock() -> None:
    first = _training_event(
        token_generation=6,
        run_id=1,
        publication_generation=30,
    )
    second = _training_event(
        token_generation=7,
        run_id=2,
        publication_generation=31,
    )
    delivered: list[TrainingLifecycleEvent] = []
    nested_results: list[bool] = []
    coordinator: TrainingPublicationLifecycleCoordinator

    def publish(event: TrainingLifecycleEvent) -> bool:
        delivered.append(event)
        if event == first:
            nested_results.append(coordinator.publish_training_terminal(second))
        return True

    coordinator = _coordinator(publish_training_terminal=publish)
    result: list[bool] = []
    worker = Thread(
        target=lambda: result.append(coordinator.publish_training_terminal(first)),
        daemon=True,
    )

    worker.start()
    worker.join(timeout=1.0)

    assert not worker.is_alive()
    assert result == [True]
    assert nested_results == [False]
    assert delivered == [first, second]


def test_newer_training_publication_preserves_older_pending_delivery() -> None:
    attempts: list[TrainingLifecycleEvent] = []
    new_delivered = Event()
    allow_old = False
    old = _training_event(
        token_generation=8,
        run_id=1,
        publication_generation=40,
    )
    new = _training_event(
        token_generation=9,
        run_id=2,
        publication_generation=41,
    )

    def publish(event: TrainingLifecycleEvent) -> bool:
        attempts.append(event)
        if event == new:
            new_delivered.set()
            return True
        return allow_old

    coordinator = _coordinator(publish_training_terminal=publish)

    assert coordinator.publish_training_terminal(old) is False
    assert coordinator.training_delivery_state().pending_count == 1
    coordinator.publish_training_terminal(new)
    assert new_delivered.wait(timeout=1.0)

    state = coordinator.training_delivery_state()
    assert state.latest_publication_generation == 41
    assert state.pending_count == 1
    assert state.delivered_count == 1

    allow_old = True
    assert coordinator.retry_training_terminal_delivery() is True
    assert coordinator.wait_for_training_delivery(timeout=1.0) is True
    state = coordinator.training_delivery_state()
    assert state.pending_count == 0
    assert state.delivered_count == 2
    assert old in attempts
    assert new in attempts


def test_newer_terminal_for_same_run_supersedes_unrendered_revision() -> None:
    old = _training_event(
        token_generation=10,
        run_id=1,
        publication_generation=42,
    )
    new = _training_event(
        token_generation=11,
        run_id=1,
        publication_generation=43,
    )
    coordinator = _coordinator(
        publish_training_terminal=lambda event: event == new,
    )

    assert coordinator.publish_training_terminal(old) is False
    assert coordinator.training_delivery_state().pending_count == 1

    assert coordinator.publish_training_terminal(new) is True

    state = coordinator.training_delivery_state()
    assert state.pending_count == 0
    assert state.delivered_count == 1
    coordinator.close()


def test_later_token_for_delivered_run_is_acknowledged_without_redelivery() -> None:
    delivered: list[TrainingLifecycleEvent] = []
    coordinator = _coordinator(
        publish_training_terminal=lambda event: delivered.append(event) or True,
    )
    first = _training_event(
        token_generation=12,
        run_id=1,
        publication_generation=44,
    )
    later = _training_event(
        token_generation=13,
        run_id=1,
        publication_generation=44,
    )

    assert coordinator.publish_training_terminal(first) is True
    assert coordinator.publish_training_terminal(later) is True

    state = coordinator.training_delivery_state()
    assert delivered == [first]
    assert state.pending_count == 0
    assert state.delivered_count == 1
    coordinator.close()


def test_persistent_failure_exhausts_autonomous_retry_without_hanging() -> None:
    attempts: list[TrainingLifecycleEvent] = []
    coordinator = _coordinator(
        publish_training_terminal=lambda event: attempts.append(event) or False
    )
    event = _training_event(
        token_generation=10,
        run_id=10,
        publication_generation=50,
    )

    assert coordinator.publish_training_terminal(event) is False

    deadline = monotonic() + 2.0
    while coordinator.training_delivery_state().retry_owner_active:
        assert monotonic() < deadline
        Event().wait(0.01)

    state = coordinator.training_delivery_state()
    assert state.pending_count == 1
    assert state.retry_exhausted is True
    assert len(attempts) < 20
    assert coordinator.wait_for_training_delivery(timeout=0.1) is False
    coordinator.close()


def test_saliency_partial_acknowledgement_retries_only_missing_event() -> None:
    analysis_events: list[TrainingLifecycleEvent] = []
    visualization_attempts: list[SaliencyTerminalNotification] = []
    visualization_acknowledged = False

    def publish_visualization(
        notification: SaliencyTerminalNotification,
    ) -> bool:
        visualization_attempts.append(notification)
        return visualization_acknowledged

    coordinator = _coordinator(
        publish_training_analysis=lambda event: analysis_events.append(event) or True,
        publish_saliency_changed=publish_visualization,
    )
    status = _saliency_status(generation=7)
    event = _training_event(
        token_generation=7,
        run_id=7,
        publication_generation=17,
    )
    notification = SaliencyTerminalNotification(
        status=status,
        analysis_event=event,
    )
    coordinator.remember_saliency_terminal(status)

    assert coordinator.deliver_saliency_terminal(notification) is False
    visualization_acknowledged = True
    assert coordinator.deliver_saliency_terminal(notification) is True

    assert analysis_events == [event]
    assert visualization_attempts == [notification, notification]
    assert coordinator.pending_saliency_terminal() is None


def test_saliency_retry_plan_retains_pending_generation() -> None:
    status = _saliency_status(generation=8)
    event = _training_event(
        token_generation=8,
        run_id=8,
        publication_generation=18,
    )
    coordinator = _coordinator(
        plan_saliency_delivery=lambda _notification: (
            SaliencyTerminalDeliveryPlan(
                disposition=SaliencyTerminalDeliveryDisposition.RETRY,
            )
        )
    )
    notification = SaliencyTerminalNotification(
        status=status,
        analysis_event=event,
    )
    coordinator.remember_saliency_terminal(status)

    assert coordinator.deliver_saliency_terminal(notification) is False
    assert coordinator.pending_saliency_terminal() == status


def test_saliency_newer_generation_supersedes_old_and_close_discards_it() -> None:
    coordinator = _coordinator()
    old = _saliency_status(generation=9)
    new = _saliency_status(generation=10)

    coordinator.remember_saliency_terminal(old)
    coordinator.remember_saliency_terminal(new)
    coordinator.remember_saliency_terminal(old)

    assert coordinator.pending_saliency_terminal() == new

    coordinator.discard_pending()

    assert coordinator.pending_saliency_terminal() is None
    assert coordinator.saliency_delivery_state().pending_generations == ()
