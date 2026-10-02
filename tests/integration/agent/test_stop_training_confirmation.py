"""Real CPU training keeps a stop confirmation bound to its original run."""

import pytest
from PyQt6.QtCore import Qt

from scripts.dev.assistant_pilot_fixture import prepare_fixture
from scripts.dev.assistant_pilot_observation import PilotCaseTrace
from scripts.dev.assistant_pilot_outcome import score_product_outcome
from scripts.dev.assistant_pilot_runtime_evidence import collect_runtime_evidence
from scripts.dev.assistant_pilot_scoring import score_case_decisions
from tests.integration.assistant_runtime.test_lifecycle import (
    WATCHDOG_MS,
    _release_initial_load,
    _runtime_harness,
    _send_request,
)
from tests.unit.scripts.test_assistant_pilot_fixture import _fixture
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
        fixture = prepare_fixture(
            harness.study,
            _fixture("training", tool="stop_training"),
            tmp_path / "training",
            running_training_epochs=10_000,
        )
        operation_id = fixture["jobs"]["training"]["operation_id"]
        owned_operations = [operation_id]
        recorder = PilotCaseTrace("same-run-stop-confirmation")
        recorder.attach(harness.controller, harness.runtime)
        try:
            before_state = service.get_state().to_dict()
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
                lambda: recorder.snapshot()["turn_terminal"] is not None,
                timeout=WATCHDOG_MS,
            )
            snapshot = recorder.snapshot()
            assert snapshot["measurement_issues"] == []
            expected = "completed" if transition == "progress" else "blocked"
            assert snapshot["turn_terminal"]["outcome"] == expected
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
            commands = [
                item["payload"]
                for item in snapshot["events"]
                if item["kind"] == "command_result"
            ]
            assert len(commands) == int(transition == "progress")
            if commands:
                assert commands[0]["tool_name"] == "stop_training"
                assert commands[0]["ok"] is True
            assert harness.engine.generation_calls == 1
            case = {
                "case_id": snapshot["case_id"],
                "decision": "Action",
                "expected_tool": "stop_training",
                "expected_parameters": {},
                "expected_workflow_stage": "training",
            }
            scores = score_case_decisions(case, snapshot)
            outcome = score_product_outcome(
                case,
                {
                    "case_id": case["case_id"],
                    "trace": snapshot,
                    "scores": scores,
                    "before_state": before_state,
                    "after_state": service.get_state().to_dict(),
                    "runtime_evidence": collect_runtime_evidence(
                        service, snapshot, fixture, harness.main_window
                    ),
                },
            )
            assert outcome["measurement_valid"], outcome["issues"]
            assert outcome["decision_correct"] is True
            assert outcome["outcome"] == expected
        finally:
            recorder.detach()
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
