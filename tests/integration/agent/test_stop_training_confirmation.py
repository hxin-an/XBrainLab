"""Real CPU training keeps a stop confirmation bound to its original run."""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QSignalSpy

from tests.integration.agent.runtime_workflow_support import start_cpu_training
from tests.integration.assistant_runtime.test_lifecycle import (
    WATCHDOG_MS,
    _release_initial_load,
    _runtime_harness,
    _send_request,
)
from XBrainLab.backend.application import TrainCommand, get_application_service
from XBrainLab.backend.training_state_contract import TrainingOutcomeState


@pytest.mark.parametrize("transition", ["progress", "terminal", "replaced_run"])
def test_stop_confirmation_follows_original_live_run(
    qtbot, monkeypatch, tmp_path, transition
):
    with _runtime_harness(
        qtbot, monkeypatch, use_real_workflow_router=True, use_real_main_window=True
    ) as harness:
        _release_initial_load(qtbot, harness)
        service = get_application_service(harness.study)
        operation_id = start_cpu_training(harness.study, tmp_path, epochs=10_000)
        owned_operations = [operation_id]
        terminals = QSignalSpy(harness.runtime.turn_finished)
        commands = QSignalSpy(harness.controller.application_command_completed)
        submissions = QSignalSpy(harness.runtime.dispatcher.input_requested)
        try:
            initial_run = service.training_runtime.terminal_outcome().run
            assert initial_run is not None
            harness.engine.generation_output = (
                '{"tool_name":"stop_training","parameters":{}}'
            )
            harness.engine.generation_release.set()
            _send_request(harness, "Stop the current training run")
            card = harness.panel.confirmation_card_widget
            qtbot.waitUntil(
                lambda: card.isVisibleTo(harness.panel), timeout=WATCHDOG_MS
            )
            confirmation = harness.controller.pending_interactions.confirmation
            assert confirmation is not None
            request = confirmation.request
            pending = service.get_view_publication()
            qtbot.waitUntil(
                lambda: service.get_view_publication().generation > pending.generation,
                timeout=WATCHDOG_MS,
            )
            current = service.training_runtime.terminal_outcome()
            assert current.run == initial_run
            assert current.state is TrainingOutcomeState.RUNNING
            if transition != "progress":
                assert service.cancel_owned_operation(operation_id)
                qtbot.waitUntil(
                    lambda: service.get_owned_operation(operation_id).phase.terminal
                    and service.training.wait_until_restart_safe(timeout=0),
                    timeout=WATCHDOG_MS,
                )
                assert (
                    service.training_runtime.terminal_outcome().state
                    is TrainingOutcomeState.CANCELLED
                )
                if transition == "replaced_run":
                    command = TrainCommand(confirmed=True, interactive=True)
                    replacement = service.begin_owned_operation(command)
                    owned_operations.append(replacement.operation_id)
                    assert service.execute(
                        command, operation_id=replacement.operation_id
                    ).ok
                    new_run = service.training_runtime.terminal_outcome()
                    assert new_run.run != initial_run
                    assert new_run.state is TrainingOutcomeState.RUNNING
            # The presentation predicate evaluates this original request's identity.
            assert harness.manager._confirmation_context_changed(request) is (
                transition != "progress"
            )
            qtbot.mouseClick(card.primary_button, Qt.MouseButton.LeftButton)
            qtbot.waitUntil(
                lambda: len(terminals) == 1,
                timeout=WATCHDOG_MS,
            )
            expected = "completed" if transition == "progress" else "blocked"
            assert terminals[0][0].outcome == expected
            assert len(submissions) == 1
            assert terminals[0][0].correlation == submissions[0][0].correlation
            qtbot.waitUntil(
                lambda: service.get_owned_operation(operation_id).phase.terminal,
                timeout=WATCHDOG_MS,
            )
            terminal = service.training_runtime.terminal_outcome()
            if transition == "replaced_run":
                assert terminal.run == new_run.run
                assert terminal.state is TrainingOutcomeState.RUNNING
            else:
                assert terminal.run == initial_run
                assert terminal.state is TrainingOutcomeState.CANCELLED
            assert len(commands) == int(transition == "progress")
            if commands:
                assert commands[0][0].tool_name == "stop_training"
                assert commands[0][0].ok is True
            assert harness.engine.generation_calls == 1
        finally:
            for owned_operation in owned_operations:
                if not service.get_owned_operation(owned_operation).phase.terminal:
                    service.cancel_owned_operation(owned_operation)
            qtbot.waitUntil(
                lambda: all(
                    service.get_owned_operation(item).phase.terminal
                    for item in owned_operations
                )
                and service.training.wait_until_restart_safe(timeout=0),
                timeout=WATCHDOG_MS,
            )
