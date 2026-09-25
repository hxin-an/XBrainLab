"""Pure runtime evidence binds exact persistent operations, never poll luck."""

from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QPushButton

from scripts.dev.assistant_pilot_runtime_evidence import (
    collect_runtime_evidence,
    decision_boundary_ns,
)
from XBrainLab.backend.application.owned_work import OwnedWorkKind, OwnedWorkRegistry
from XBrainLab.backend.training_state_contract import (
    TrainingOutcomeState,
    TrainingRunIdentity,
    TrainingTerminalOutcome,
)


def test_intermediate_no_tool_does_not_stop_decision_deadline():
    trace = {
        "origin_monotonic_ns": 100,
        "events": [
            {
                "kind": "host_decision",
                "elapsed_ns": 10,
                "payload": {"kind": "envelope", "status": "no_tool"},
            },
            {
                "kind": "host_decision",
                "elapsed_ns": 11,
                "payload": {"kind": "envelope", "status": "format_error"},
            },
        ],
    }
    assert decision_boundary_ns(trace) is None
    trace["events"].append(
        {"kind": "command_started", "elapsed_ns": 90, "payload": None}
    )
    trace["events"].append({"kind": "turn_terminal", "elapsed_ns": 200, "payload": {}})
    assert decision_boundary_ns(trace) == 190


@pytest.mark.parametrize(
    "kind",
    ["confirmation_requested", "ui_requested", "navigation_requested", "turn_terminal"],
)
def test_every_final_boundary_uses_recorded_time_not_poll_time(kind):
    assert (
        decision_boundary_ns(
            {
                "origin_monotonic_ns": 1_000,
                "events": [
                    {"kind": kind, "elapsed_ns": 123},
                ],
            }
        )
        == 1_123
    )


def test_real_command_boundary_excludes_operation_and_late_poll_time(
    qtbot, monkeypatch, tmp_path
):
    from PyQt6.QtCore import Qt

    from scripts.dev.assistant_pilot_case import record_decision_clock
    from scripts.dev.assistant_pilot_observation import PilotCaseTrace
    from tests.integration.agent.test_product_flow import (
        _load_tiny_raw_via_command_spine,
    )
    from tests.integration.assistant_runtime.test_lifecycle import (
        WATCHDOG_MS,
        _release_initial_load,
        _runtime_harness,
        _send_request,
        _wait_for_event,
    )
    from XBrainLab.backend.application import PreprocessCommand, get_application_service
    from XBrainLab.llm.agent.turn import AssistantGenerationEventPhase

    # Real owners/events with an injected monotonic clock; model/RAG stay external seams.
    with _runtime_harness(
        qtbot, monkeypatch, use_real_workflow_router=True, use_real_main_window=True
    ) as harness:
        _release_initial_load(qtbot, harness)
        _load_tiny_raw_via_command_spine(harness.study, tmp_path)
        harness.engine.generation_output = (
            '{"workflow_stage":"data_loaded","tool_name":"resample_data",'
            '"parameters":{"rate":64}}'
        )
        clock = [1_000_000_000]

        def generation_progress(event):
            if event.phase is AssistantGenerationEventPhase.STARTED:
                clock[0] = 2_000_000_000
            elif event.phase is AssistantGenerationEventPhase.FINISHED:
                clock[0] = 3_000_000_000

        service = get_application_service(harness.study)
        execute = service.execute

        def measured_execute(command, **kwargs):
            if isinstance(command, PreprocessCommand):
                clock[0] = 8_000_000_000
            return execute(command, **kwargs)

        monkeypatch.setattr(service, "execute", measured_execute)
        harness.controller.generation_event.connect(
            generation_progress, Qt.ConnectionType.DirectConnection
        )
        trace = PilotCaseTrace("public-runtime-timing", clock=lambda: clock[0])
        trace.attach(harness.controller, harness.runtime)
        try:
            _send_request(harness, "Resample to 64 Hz")
            _wait_for_event(qtbot, harness.engine.generation_started)
            harness.engine.generation_release.set()
            qtbot.waitUntil(
                lambda: trace.snapshot()["turn_terminal"] is not None,
                timeout=WATCHDOG_MS,
            )
            snapshot = trace.snapshot()
            assert snapshot["measurement_issues"] == []
            assert harness.study.preprocessed_data_list[0].get_mne().info["sfreq"] == 64
            terminal = next(
                event
                for event in snapshot["events"]
                if event["kind"] == "turn_terminal"
            )
            assert (
                snapshot["origin_monotonic_ns"] + terminal["elapsed_ns"]
                == 8_000_000_000
            )
            assert decision_boundary_ns(snapshot) == 3_000_000_000
            # Deliberately late runner polling is not a model decision timestamp.
            clock[0] = 20_000_000_000
            result = {}
            record_decision_clock(
                result, 1_000_000_000, decision_boundary_ns(trace.snapshot()), clock[0]
            )
            assert result["decision_seconds"] == 2.0
            assert result["case_turn_seconds"] == 19.0
            assert result["case_operation_seconds"] == 17.0
            assert result["decision_clock"]["terminal_observed"] is True
        finally:
            trace.detach()
            harness.controller.generation_event.disconnect(generation_progress)


def service(outcome):
    registry = OwnedWorkRegistry()
    return SimpleNamespace(
        training_runtime=SimpleNamespace(terminal_outcome=lambda: outcome),
        get_owned_operation=registry.snapshot,
        registry=registry,
    )


def fixture(run=None, operation_id=None):
    return {
        "state": {"training": {"terminal_outcome": {"run": run}}},
        "jobs": {"training": {"operation_id": operation_id}} if operation_id else {},
    }


def trace(tool, *, run=None, operation_id=None, ok=True):
    diagnostics = {"operation_id": operation_id} if operation_id else {}
    if run is not None:
        diagnostics["training_run"] = run
    return {
        "events": [
            {
                "kind": "command_result",
                "payload": {
                    "tool_name": tool,
                    "ok": ok,
                    "diagnostics": diagnostics,
                    "state": {},
                },
            }
        ]
    }


def test_start_training_without_owned_operation_waits_for_bound_run():
    run = TrainingRunIdentity("trainer", 1)
    current = service(TrainingTerminalOutcome(TrainingOutcomeState.RUNNING, run))
    result = collect_runtime_evidence(
        current, trace("start_training", run=run.to_dict()), fixture(), None
    )
    assert result["waiting"] is True
    assert result["training"]["matched"] is True
    assert result["jobs"] == {} and result["issues"] == []
    current.training_runtime.terminal_outcome = lambda: TrainingTerminalOutcome(
        TrainingOutcomeState.COMPLETED, run
    )
    result = collect_runtime_evidence(
        current, trace("start_training", run=run.to_dict()), fixture(), None
    )
    assert result["waiting"] is False
    assert result["training"]["outcome"]["state"] == "completed"


def test_stop_training_waits_for_existing_fixture_run_not_command_ack():
    run = TrainingRunIdentity("trainer", 1)
    current = service(TrainingTerminalOutcome(TrainingOutcomeState.STOP_REQUESTED, run))
    result = collect_runtime_evidence(
        current, trace("stop_training", run=run.to_dict()), fixture(run.to_dict()), None
    )
    assert result["waiting"] is True
    assert result["training"]["expected_run"] == run.to_dict()
    current.training_runtime.terminal_outcome = lambda: TrainingTerminalOutcome(
        TrainingOutcomeState.CANCELLED, run
    )
    assert (
        collect_runtime_evidence(
            current,
            trace("stop_training", run=run.to_dict()),
            fixture(run.to_dict()),
            None,
        )["waiting"]
        is False
    )


def test_an_unrelated_completed_run_never_completes_the_target():
    current = service(
        TrainingTerminalOutcome(
            TrainingOutcomeState.COMPLETED, TrainingRunIdentity("other", 2)
        )
    )
    result = collect_runtime_evidence(
        current,
        trace("start_training", run={"trainer_id": "target", "run_id": 1}),
        fixture(),
        None,
    )
    assert "training_run_mismatch" in result["issues"]
    assert result["training"]["matched"] is False


def test_missing_training_identity_is_not_filled_from_latest_runtime():
    current = service(
        TrainingTerminalOutcome(
            TrainingOutcomeState.COMPLETED, TrainingRunIdentity("other", 2)
        )
    )
    result = collect_runtime_evidence(current, trace("start_training"), fixture(), None)
    assert "training_identity_missing" in result["issues"]


def test_terminal_saliency_between_polls_is_found_by_persistent_button_id(qtbot):
    current = service(TrainingTerminalOutcome(TrainingOutcomeState.NOT_STARTED))
    operation = current.registry.begin(OwnedWorkKind.SALIENCY, cancellable=True)
    current.registry.claim_start(operation.operation_id)
    current.registry.complete(operation.operation_id)
    button = QPushButton()
    qtbot.addWidget(button)
    button.setProperty("operationId", operation.operation_id)
    window = SimpleNamespace(
        visualization_panel=SimpleNamespace(compute_saliency_btn=button)
    )
    evidence = {
        "events": [
            {"kind": "ui_requested", "payload": {"tool_name": "compute_saliency"}}
        ]
    }
    result = collect_runtime_evidence(current, evidence, fixture(), window)
    assert result["saliency_operation_id"] == operation.operation_id
    assert result["jobs"][operation.operation_id]["phase"] == "completed"
    assert result["waiting"] is False and result["issues"] == []


def test_result_diagnostics_retain_completed_operation_without_active_scan():
    current = service(TrainingTerminalOutcome(TrainingOutcomeState.NOT_STARTED))
    operation = current.registry.begin(OwnedWorkKind.SALIENCY, cancellable=True)
    current.registry.claim_start(operation.operation_id)
    current.registry.complete(operation.operation_id)
    result = collect_runtime_evidence(
        current,
        trace("compute_saliency", operation_id=operation.operation_id),
        fixture(),
        None,
    )
    assert result["jobs"][operation.operation_id]["phase"] == "completed"


def test_unrelated_running_fixture_is_recorded_but_not_waited():
    run = TrainingRunIdentity("trainer", 1)
    current = service(TrainingTerminalOutcome(TrainingOutcomeState.RUNNING, run))
    operation = current.registry.begin(OwnedWorkKind.TRAINING, cancellable=True)
    current.registry.claim_start(operation.operation_id)
    result = collect_runtime_evidence(
        current, {"events": []}, fixture(run.to_dict(), operation.operation_id), None
    )
    assert result["jobs"][operation.operation_id]["phase"] == "running"
    assert result["waiting"] is False


def test_stop_waits_for_owned_fixture_cleanup_even_after_training_terminal():
    run = TrainingRunIdentity("trainer", 1)
    current = service(TrainingTerminalOutcome(TrainingOutcomeState.CANCELLED, run))
    operation = current.registry.begin(OwnedWorkKind.TRAINING, cancellable=True)
    current.registry.claim_start(operation.operation_id)
    prepared = fixture(run.to_dict(), operation.operation_id)
    result = collect_runtime_evidence(
        current, trace("stop_training", run=run.to_dict()), prepared, None
    )
    assert result["waiting"] is True
    current.registry.finish_cancelled(operation.operation_id)
    result = collect_runtime_evidence(
        current, trace("stop_training", run=run.to_dict()), prepared, None
    )
    assert result["waiting"] is False and result["issues"] == []
