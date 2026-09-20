"""Evidence collection never executes tools or converts missing evidence to success."""

from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QObject, pyqtSignal

from scripts.dev.assistant_pilot_observation import PilotCaseTrace
from XBrainLab.llm.agent.turn import (
    AssistantGenerationEvent,
    AssistantGenerationEventPhase,
    AssistantGenerationRequest,
    AssistantResponseContract,
    AssistantTurnCorrelation,
    AssistantTurnRequest,
    AssistantTurnTerminal,
)


class Signals(QObject):
    input_requested = pyqtSignal(object)
    turn_delivery_acknowledged = pyqtSignal(object)
    confirmation_requested = pyqtSignal(object)
    workflow_ui_handoff_resolved_requested = pyqtSignal(object)
    sig_generate = pyqtSignal(object)
    generation_event = pyqtSignal(object)
    decision_observed = pyqtSignal(object)
    application_command_started = pyqtSignal()
    application_command_completed = pyqtSignal(object)
    workflow_ui_handoff_requested = pyqtSignal(object)
    panel_navigation_requested = pyqtSignal(object)
    interaction_resolved = pyqtSignal(object)
    activity_changed = pyqtSignal(object)
    response_presentation_ready = pyqtSignal(object)
    turn_finished = pyqtSignal(object)


@pytest.fixture
def host(qtbot):
    controller, dispatcher, runtime = Signals(), Signals(), Signals()
    runtime.dispatcher = dispatcher
    return SimpleNamespace(
        controller=controller, dispatcher=dispatcher, runtime=runtime
    )


def begin(host, trace):
    trace.attach(host.controller, host.runtime)
    correlation = AssistantTurnCorrelation(generation=1, turn_id=2)
    host.dispatcher.input_requested.emit(
        AssistantTurnRequest(correlation, "User request")
    )
    return correlation


def generation(host, generation_id, text):
    request = AssistantGenerationRequest.from_messages(
        [{"role": "user", "content": "User request"}],
        response_contract=AssistantResponseContract.STRUCTURED_ACTION,
    ).correlated(generation_id)
    host.controller.sig_generate.emit(request)
    for phase, chunk in [
        (AssistantGenerationEventPhase.STARTED, ""),
        (AssistantGenerationEventPhase.CHUNK, text),
        (AssistantGenerationEventPhase.FINISHED, ""),
    ]:
        host.controller.generation_event.emit(
            AssistantGenerationEvent(generation_id, phase, chunk)
        )


def test_generations_retries_and_host_outcomes_remain_separate(host):
    trace = PilotCaseTrace("DEV-case")
    correlation = begin(host, trace)
    generation(host, 1, "wrong output")
    generation(host, 2, "correct output")
    host.controller.application_command_completed.emit({"ok": False})
    host.runtime.turn_finished.emit(AssistantTurnTerminal(correlation, "failed"))
    report = trace.snapshot()
    assert [item["raw_response"] for item in report["generations"]] == [
        "wrong output",
        "correct output",
    ]
    assert report["measurement_issues"] == []
    assert report["turn_terminal"]["outcome"] == "failed"
    assert "correct" not in report and "product_success" not in report
    assert report["ui_readiness"] == "not_observed"
    assert [item["sequence"] for item in report["events"]] == list(
        range(1, len(report["events"]) + 1)
    )
    assert all(item["elapsed_ns"] >= 0 for item in report["events"])
    trace.detach()


def test_missing_terminal_and_partial_output_are_not_complete(host):
    trace = PilotCaseTrace("DEV-case")
    begin(host, trace)
    generation(host, 1, "raw")
    assert "missing_turn_terminal" in trace.snapshot()["measurement_issues"]
    trace.detach()


def test_foreign_turn_does_not_replace_bound_identity(host):
    trace = PilotCaseTrace("DEV-case")
    correlation = begin(host, trace)
    host.runtime.turn_finished.emit(
        AssistantTurnTerminal(AssistantTurnCorrelation(9, 9))
    )
    assert trace.snapshot()["turn_terminal"] is None
    assert "foreign_correlation" in trace.snapshot()["measurement_issues"]
    host.runtime.turn_finished.emit(AssistantTurnTerminal(correlation))
    assert trace.snapshot()["turn_terminal"]["correlation"] == {
        "generation": 1,
        "turn_id": 2,
    }
    trace.detach()


def test_event_payload_is_copied_and_detach_stops_collection(host):
    trace = PilotCaseTrace("DEV-case")
    begin(host, trace)
    payload = {"stage": "parsed", "parameters": {"rate": 128}}
    host.controller.decision_observed.emit(payload)
    payload["parameters"]["rate"] = 64
    report = trace.snapshot()
    assert report["events"][-1]["payload"]["parameters"]["rate"] == 128
    report["events"].clear()
    trace.detach()
    count = len(trace.snapshot()["events"])
    host.controller.application_command_started.emit()
    assert len(trace.snapshot()["events"]) == count


def test_limit_and_unserializable_payload_fail_measurement_not_product(host):
    trace = PilotCaseTrace("DEV-case", max_events=2)
    begin(host, trace)
    host.controller.decision_observed.emit({"opaque": object()})
    host.controller.application_command_started.emit()
    host.controller.application_command_started.emit()
    issues = trace.snapshot()["measurement_issues"]
    assert "unserializable_event" in issues and "trace_limit_exceeded" in issues
    trace.detach()


def test_missing_request_and_generation_terminal_are_visible(host):
    trace = PilotCaseTrace("DEV-case")
    correlation = begin(host, trace)
    host.controller.generation_event.emit(
        AssistantGenerationEvent(5, AssistantGenerationEventPhase.CHUNK, "partial")
    )
    host.runtime.turn_finished.emit(AssistantTurnTerminal(correlation, "failed"))
    report = trace.snapshot()
    assert report["generations"][0]["raw_response"] == "partial"
    assert "missing_generation_request:5" in report["measurement_issues"]
    assert "missing_generation_terminal:5" in report["measurement_issues"]
    trace.detach()


@pytest.mark.parametrize(
    "payload,issue",
    [
        (
            {"kind": "rag_request", "enabled": True, "accepted": False},
            "rag_retrieval_unavailable",
        ),
        (
            {"kind": "rag", "enabled": True, "error": "retrieval failed"},
            "rag_retrieval_error",
        ),
    ],
)
def test_degraded_rag_on_invalidates_condition_measurement(host, payload, issue):
    trace = PilotCaseTrace("DEV-case")
    begin(host, trace)
    host.controller.decision_observed.emit(payload)
    assert issue in trace.snapshot()["measurement_issues"]
    trace.detach()


def test_byte_limit_keeps_original_input_outside_product_mutation(host):
    trace = PilotCaseTrace("DEV-case", max_bytes=150)
    begin(host, trace)
    generation(host, 1, "oversize" * 100)
    assert "trace_limit_exceeded" in trace.snapshot()["measurement_issues"]
    trace.detach()


def test_unknown_generation_payload_is_an_issue_not_a_snapshot_crash(host):
    trace = PilotCaseTrace("DEV-case")
    begin(host, trace)
    host.controller.generation_event.emit(
        {"generation_id": True, "phase": "chunk", "text": "bad"}
    )
    assert "invalid_generation_identity" in trace.snapshot()["measurement_issues"]
    trace.detach()


def test_concurrent_signal_receipts_are_ordered_and_bounded(host):
    from concurrent.futures import ThreadPoolExecutor

    trace = PilotCaseTrace("DEV-case", max_events=50)
    begin(host, trace)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(
            pool.map(
                lambda _: host.controller.application_command_started.emit(), range(60)
            )
        )
    snapshot = trace.snapshot()
    assert len(snapshot["events"]) == 50
    assert [event["sequence"] for event in snapshot["events"]] == list(range(1, 51))
    assert "trace_limit_exceeded" in snapshot["measurement_issues"]
    trace.detach()


def test_real_controller_rag_off_keeps_normal_assembly_and_observes_admission(qtbot):
    from scripts.dev.assistant_pilot_models import make_launch_spec
    from tests.qt_lifecycle import close_controller_and_wait
    from XBrainLab.backend.study import Study
    from XBrainLab.llm.agent.controller import LLMController

    class RagProbe:
        def start(self):
            pytest.fail("RAG off must not start retrieval")

        def retrieve(self, *args, **kwargs):
            pytest.fail("RAG off must not retrieve")

        def close(self, **kwargs):
            return True

    controller = LLMController(Study(), rag_lifecycle=RagProbe(), rag_enabled=False)
    requests, decisions = [], []
    controller.sig_generate.connect(requests.append)
    controller.decision_observed.connect(decisions.append)
    # Isolate native inference only; retain actual context assembly and parsing.
    controller._sig_dispatch_generation.disconnect()
    controller.sig_initialize.disconnect()
    try:
        controller.initialize(
            make_launch_spec("ibm-granite/granite-4.0-micro", "unused")
        )
        controller.handle_user_turn(
            AssistantTurnRequest(AssistantTurnCorrelation(1, 1), "Explain EEG")
        )
        assert len(requests) == 1
        assert any(
            dict(message).get("role") == "user" for message in requests[0].messages
        )
        rag = next(item for item in decisions if item["kind"] == "rag")
        assert rag["enabled"] is False and rag["error"] == ""
        controller.current_response = '{"workflow_stage":"empty","tool_name":"respond_to_user","parameters":{"message":"EEG explanation"}}'
        controller._on_generation_finished(requests[0].generation_id, [])
        envelope = next(item for item in decisions if item["kind"] == "envelope")
        assert envelope["status"] == "no_tool"
        assert envelope["generation_id"] == requests[0].generation_id
        assert envelope["correlation"] == {"generation": 1, "turn_id": 1}
    finally:
        close_controller_and_wait(controller, qtbot)


@pytest.mark.parametrize("wrong_stage", [False, True])
def test_real_host_rejection_is_recorded_not_recomputed_from_oracle(qtbot, wrong_stage):
    from tests.qt_lifecycle import close_controller_and_wait
    from XBrainLab.backend.study import Study
    from XBrainLab.llm.agent.controller import LLMController

    controller = LLMController(Study(), rag_enabled=False)
    controller._sig_dispatch_generation.disconnect()
    decisions, requests = [], []
    controller.decision_observed.connect(decisions.append)
    controller.sig_generate.connect(requests.append)
    try:
        controller.handle_user_turn(
            AssistantTurnRequest(AssistantTurnCorrelation(1, 1), "Resample to 128 Hz")
        )
        stage = "data_loaded" if wrong_stage else "empty"
        controller.current_response = (
            '{"workflow_stage":"'
            + stage
            + '","tool_name":"resample_data","parameters":{"rate":128}}'
        )
        controller._on_generation_finished(requests[0].generation_id, [])
        if wrong_stage:
            rejection = next(item for item in decisions if item["kind"] == "envelope")
            assert rejection["status"] == "format_error"
            assert "workflow_stage" in rejection["error"]
        else:
            rejection = next(item for item in decisions if item["kind"] == "admission")
            assert rejection["action"].endswith("blocked")
            assert rejection["command_name"] == "resample_data"
            assert rejection["params"] == {"rate": 128}
        assert rejection["generation_id"] == requests[0].generation_id
    finally:
        close_controller_and_wait(controller, qtbot)


def test_observer_exception_and_mutation_do_not_change_owner_decision(qtbot):
    from tests.qt_lifecycle import close_controller_and_wait
    from XBrainLab.backend.study import Study
    from XBrainLab.llm.agent.controller import LLMController
    from XBrainLab.llm.agent.parser import CommandParser

    controller = LLMController(Study(), rag_enabled=False)

    def broken_observer(payload):
        payload["commands"][0][1]["rate"] = 64
        raise RuntimeError("diagnostic sink failed")

    controller.decision_observed.connect(broken_observer)
    envelope = CommandParser.parse_product(
        '{"workflow_stage":"empty","tool_name":"resample_data","parameters":{"rate":128}}'
    )
    try:
        assert controller._handle_tool_envelope_failure("unused", envelope) is False
        assert envelope.commands[0][1] == {"rate": 128}
    finally:
        close_controller_and_wait(controller, qtbot)
