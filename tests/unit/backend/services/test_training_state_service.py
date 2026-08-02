from __future__ import annotations

from threading import Event, Thread
from typing import Any

import pytest

from XBrainLab.backend.application import ApplicationService
from XBrainLab.backend.controller.training_controller import TrainingController
from XBrainLab.backend.services.training_state_service import TrainingStateService
from XBrainLab.backend.study import Study
from XBrainLab.backend.training_state_contract import (
    TrainingLifecycleEvent,
    TrainingOutcomeState,
    TrainingRunIdentity,
    TrainingStateToken,
    TrainingTerminalOutcome,
)


class _Trainer:
    def __init__(self) -> None:
        self._run = TrainingRunIdentity(trainer_id="trainer-1", run_id=1)

    def get_state_snapshot_token(self) -> TrainingStateToken:
        return TrainingStateToken(generation=1, stable=True)

    def get_terminal_outcome(self) -> TrainingTerminalOutcome:
        return TrainingTerminalOutcome(
            state=TrainingOutcomeState.RUNNING,
            run=self._run,
        )


class _TrainingStudy:
    def __init__(self, trace: list[str]) -> None:
        self.trace = trace
        self.running = False
        self.trainer = _Trainer()
        self.loaded_data_list: list[Any] = []
        self.preprocessed_data_list: list[Any] = []
        self.epoch_data: Any | None = None
        self.datasets: list[Any] = [object()]
        self.model_holder: Any = object()
        self.training_option: Any = object()
        self.dataset_generator: Any | None = None

    def is_training(self) -> bool:
        return self.running

    def generate_plan(self, *, force_update: bool, append: bool) -> None:
        assert force_update is True
        self.trace.append(f"generate:{append}")

    def train(self, *, interact: bool) -> None:
        self.trace.append(f"train:{interact}")
        self.running = interact

    def stop_training(self) -> bool:
        self.trace.append("stop")
        self.running = False
        return True


def test_synchronous_training_preserves_command_and_event_order() -> None:
    trace: list[str] = []
    service = TrainingStateService(_TrainingStudy(trace))
    service.subscribe("training_started", lambda: trace.append("started"))
    service.subscribe("training_stopped", lambda: trace.append("stopped"))

    generation = service.start_training(append=False, interactive=False)

    assert trace == ["generate:False", "started", "train:False", "stopped"]
    assert service.wait_for_terminal_notification(generation, timeout=0.0)


def test_async_stop_waits_for_terminal_publication_before_restart() -> None:
    trace: list[str] = []
    study = _TrainingStudy(trace)
    service = TrainingStateService(study)
    updated = Event()
    terminal_entered = Event()
    release_terminal = Event()
    terminal_calls = 0

    service.subscribe("training_updated", updated.set)

    def publish_terminal() -> None:
        nonlocal terminal_calls
        terminal_calls += 1
        if terminal_calls == 1:
            terminal_entered.set()
            assert release_terminal.wait(timeout=5.0)

    service.subscribe("training_stopped", publish_terminal)
    first_generation = service.start_training(interactive=True)
    assert updated.wait(timeout=1.0)

    service.stop_training()
    assert terminal_entered.wait(timeout=2.0)
    restart_safe: list[bool] = []
    waiter = Thread(
        target=lambda: restart_safe.append(
            service.wait_until_restart_safe(timeout=5.0)
        ),
        name="training-service-restart-waiter",
    )
    waiter.start()
    assert waiter.is_alive()

    release_terminal.set()
    waiter.join(timeout=2.0)

    assert restart_safe == [True]
    assert service.wait_for_terminal_notification(first_generation, timeout=0.0)

    second_generation = service.start_training(interactive=True)
    assert second_generation == first_generation + 1
    service.stop_training()
    assert service.wait_for_terminal_notification(second_generation, timeout=2.0)
    assert trace.count("stop") == 2
    service.shutdown()


def test_failed_terminal_callback_blocks_restart_until_typed_delivery_recovers() -> (
    None
):
    service = TrainingStateService(_TrainingStudy([]))
    service.subscribe("training_stopped", lambda: False)

    generation = service.start_training(append=False, interactive=False)

    assert service.wait_for_terminal_notification(generation, timeout=0.0) is False
    assert service.wait_until_restart_safe(timeout=0.0) is False
    with pytest.raises(
        RuntimeError,
        match="previous training terminal handoff",
    ):
        service.start_training(append=False, interactive=False)

    terminal = TrainingLifecycleEvent(
        token=TrainingStateToken(generation=7, stable=True),
        outcome=TrainingTerminalOutcome(
            state=TrainingOutcomeState.COMPLETED,
            run=TrainingRunIdentity(trainer_id="trainer-1", run_id=1),
        ),
    )
    assert service.publish_training_terminal(terminal) is True

    assert service.wait_for_terminal_notification(generation, timeout=0.0) is True
    assert service.wait_until_restart_safe(timeout=0.0) is True


def test_terminal_publication_false_keeps_waiter_pending_until_retry_succeeds() -> None:
    service = TrainingStateService(_TrainingStudy([]))
    terminal = TrainingLifecycleEvent(
        token=TrainingStateToken(generation=7, stable=True),
        outcome=TrainingTerminalOutcome(
            state=TrainingOutcomeState.COMPLETED,
            run=TrainingRunIdentity(trainer_id="trainer-1", run_id=1),
        ),
    )
    acknowledge_terminal = False

    def publish_terminal(event: TrainingLifecycleEvent) -> bool:
        assert event == terminal
        return acknowledge_terminal

    service.subscribe("training_terminal_published", publish_terminal)
    service.subscribe(
        "training_stopped",
        lambda: service.publish_training_terminal(terminal),
    )

    generation = service.start_training(append=False, interactive=False)
    waiter_started = Event()
    wait_results: list[bool] = []

    def wait_for_handoff() -> None:
        waiter_started.set()
        wait_results.append(
            service.wait_for_terminal_notification(generation, timeout=1.0)
        )

    waiter = Thread(target=wait_for_handoff, name="training-terminal-handoff-waiter")
    waiter.start()
    assert waiter_started.wait(timeout=0.2)
    waiter.join(timeout=0.05)

    assert waiter.is_alive()
    assert service.wait_until_restart_safe(timeout=0.0) is False
    with pytest.raises(RuntimeError, match="previous training terminal handoff"):
        service.start_training(append=False, interactive=False)

    acknowledge_terminal = True
    assert service.publish_training_terminal(terminal) is True
    waiter.join(timeout=0.5)

    assert waiter.is_alive() is False
    assert wait_results == [True]
    assert service.wait_until_restart_safe(timeout=0.0) is True

    next_generation = service.start_training(append=False, interactive=False)
    assert next_generation == generation + 1


def test_controller_relays_shared_transient_progress_without_owning_monitor() -> None:
    study = Study()
    controller = TrainingController(study)
    observed: list[str] = []
    controller.subscribe("training_updated", lambda: observed.append("updated"))

    study.training_state_service.notify("training_updated")

    assert observed == ["updated"]
    assert controller._training_state is study.training_state_service
    assert "_monitor_thread" not in controller.__dict__
    assert "_terminal_handoffs" not in controller.__dict__


def test_application_composes_the_study_training_service_without_controller() -> None:
    study = Study()
    service = ApplicationService(study)

    assert service.training is study.training_state_service
    assert service.training_lifecycle_events is study.training_state_service
    assert "training" not in study._controllers

    service.close()
    assert "training" not in study._controllers


def test_training_service_exposes_typed_lifecycle_publication_port() -> None:
    service = TrainingStateService(_TrainingStudy([]))
    observed: list[tuple[str, TrainingLifecycleEvent]] = []
    event = TrainingLifecycleEvent(
        token=TrainingStateToken(generation=4, stable=True),
        outcome=TrainingTerminalOutcome(state=TrainingOutcomeState.NOT_STARTED),
    )
    service.subscribe(
        "training_terminal_published",
        lambda published: observed.append(("terminal", published)),
    )
    service.subscribe(
        "training_analysis_published",
        lambda published: observed.append(("analysis", published)),
    )

    service.publish_training_terminal(event)
    service.publish_training_analysis(event)

    assert observed == [("terminal", event), ("analysis", event)]
