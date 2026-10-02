"""Condition workers may reuse only one exact model/RAG runtime identity."""

import copy
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts.dev.assistant_pilot_condition import (
    DEV_EXPERIMENT,
    SCHEMA,
    PilotConditionSession,
    validate_condition_request,
)


def request():
    return {
        "case": {
            "case_id": "DEV-A01-01-V0",
            "split": "DEV",
            "input": "Open import",
            "fixture_id": "f",
            "expected_workflow_stage": "empty",
        },
        "fixture": {
            "metadata": {"fixture_id": "f"},
            "conditions": {"stage": "empty"},
        },
        "model_id": "google/gemma-3-4b-it",
        "model_cache": "D:/cache",
        "rag_enabled": False,
        "rag_cache": None,
        "seed": 0,
        "repeat": 0,
    }


def condition_request():
    first = request()
    second = copy.deepcopy(first)
    second["case"]["case_id"] = "DEV-A01-01-V1"
    return {
        "schema": SCHEMA,
        "condition": "gemma3-rag-off",
        "jobs": [
            {"id": "gemma3-rag-off__DEV-A01-01-V0", "payload": first},
            {"id": "gemma3-rag-off__DEV-A01-01-V1", "payload": second},
        ],
    }


def test_condition_accepts_distinct_cases_with_one_runtime_identity():
    validate_condition_request(condition_request())


def test_missing_research_profile_is_rejected_before_runtime_bootstrap(
    monkeypatch, tmp_path
):
    from scripts.dev import assistant_dev_context, assistant_pilot_condition
    from tests.unit.scripts.test_assistant_pilot_case import experiment_request

    payload = experiment_request(split="DEV", repeat=0)
    monkeypatch.delitem(assistant_dev_context._MODEL_EMPHASIS, payload["model_id"])
    monkeypatch.setattr(
        assistant_pilot_condition,
        "bootstrap_case_checkout",
        lambda: pytest.fail("bootstrapped before profile validation"),
    )
    with pytest.raises(ValueError, match="DEV prompt model"):
        PilotConditionSession(payload, tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "model_id",
    [
        "ibm-granite/granite-4.0-micro",
        "ibm-granite/granite-3.3-2b-instruct",
        "microsoft/Phi-4-mini-instruct",
        "meta-llama/Llama-3.2-3B-Instruct",
        "google/gemma-3-4b-it",
    ],
)
def test_experiment_session_wires_exact_model_presentation(
    qtbot,
    tmp_path,
    controlled_condition_runtime,
    model_id,
):
    from scripts.dev.assistant_dev_context import DevContextAssembler
    from tests.unit.scripts.test_assistant_pilot_case import experiment_request

    payload = experiment_request(split="DEV", repeat=0)
    payload["model_id"] = model_id
    payload["rag_cache"] = str(tmp_path / "external-rag")
    session = PilotConditionSession.__new__(PilotConditionSession)
    with patch.dict(os.environ):
        try:
            session.__init__(payload, tmp_path)
            assembler = session.manager.agent_controller.assembler
            assert isinstance(assembler, DevContextAssembler)
            assert assembler.model_id == model_id
            messages = assembler.get_generation_request(
                [
                    {"role": "user", "content": payload["case"]["input"]},
                ]
            ).to_model_messages()
            expected_catalog_heading = (
                "Available choices (guidance, not output):"
                if model_id
                in {"ibm-granite/granite-4.0-micro", "meta-llama/Llama-3.2-3B-Instruct"}
                else "Action Contract Catalog (input definitions, never an output array):"
            )
            assert expected_catalog_heading in messages[0]["content"]
            has_illustrations = model_id not in {
                "ibm-granite/granite-4.0-micro",
                "google/gemma-3-4b-it",
            }
            assert (
                "Complete output illustrations:" in messages[0]["content"]
            ) is has_illustrations
            assert "Output decision:" in messages[0]["content"]
            assert assembler._decision_instructions() in messages[0]["content"]
            assert controlled_condition_runtime["engines"][0].load_calls == 1
        finally:
            assert session.close()


@pytest.fixture
def controlled_condition_runtime(monkeypatch):
    import transformers

    from scripts.dev import assistant_pilot_condition as condition
    from tests.integration.assistant_runtime.test_lifecycle import (
        _ControlledEngine,
        _NoopRagLifecycle,
    )
    from tests.unit.llm.core.test_runtime_prompt_capture import (
        _backend,
        _ImmediateThread,
        _Streamer,
    )
    from XBrainLab.llm.agent import controller, worker
    from XBrainLab.llm.core.backends import local
    from XBrainLab.llm.core.config import LLMConfig
    from XBrainLab.llm.core.generation import ResolvedGenerationOptions

    engines = []
    control = {"engines": engines, "load_error": False}

    class CapturingEngine(_ControlledEngine):
        def load_model(self):
            if control["load_error"]:
                self.load_started.set()
                self.load_calls += 1
                raise RuntimeError("Injected external model load failure")
            super().load_model()

        def generate_stream(self, messages, *, profile):
            self.generated_messages.append(messages)
            self.generated_profiles.append(profile)
            yield from _backend().generate_stream(
                messages,
                options=ResolvedGenerationOptions(max_new_tokens=128, do_sample=False),
            )

    def process_double(config, **_kwargs):
        engine = CapturingEngine(config)
        engine.release_all()
        engines.append(engine)
        return engine

    # Keep the real research worker, controller, runtime, host, and capture writer.
    # Only model/process work and environment readiness are controlled here.
    monkeypatch.setattr(worker, "LocalRuntimeProcessOwner", process_double)
    monkeypatch.setattr(controller, "ProcessRAGRetrieverLifecycle", _NoopRagLifecycle)
    monkeypatch.setattr(LLMConfig, "local_backend_ready", lambda *_: True)
    monkeypatch.setattr(LLMConfig, "save_to_file", lambda *_: True)
    monkeypatch.setattr(condition, "bootstrap_case_checkout", lambda: None)
    monkeypatch.setattr(
        transformers, "TextIteratorStreamer", lambda *_a, **_k: _Streamer()
    )
    monkeypatch.setattr(local, "Thread", _ImmediateThread)
    return control


def test_condition_warmup_uses_owned_engine_and_isolates_real_capture(
    qtbot, tmp_path, controlled_condition_runtime
):
    from XBrainLab.llm.core.generation import GenerationProfile

    engines = controlled_condition_runtime["engines"]
    session = PilotConditionSession.__new__(PilotConditionSession)
    with patch.dict(os.environ):
        try:
            session.__init__(request(), tmp_path)
            assert len(engines) == 1
            assert engines[0].load_calls == 1
            assert engines[0].generated_messages == [
                [{"role": "user", "content": "Reply with the single word READY."}]
            ]
            assert engines[0].generated_profiles == [
                GenerationProfile.STRUCTURED_DECISION
            ]
            assert session.condition_evidence["warmup"]["output"] == "raw output"
            captures = list(session.prompt_root.glob("*/*/metadata.json"))
            assert len(captures) == 1
            assert (captures[0].parent / "prompt.txt").read_text() == (
                "<user>Reply with the single word READY.<assistant>"
            )
            assert (captures[0].parent / "raw-output.txt").read_text() == "raw output"
            assert session.case_index == 0
            assert not session.runtime.turn_in_flight
            assert not (tmp_path / "first").exists()
            startup_capture = Path(session.driver._screenshot(session.window))
            assert startup_capture.parent == tmp_path / "ui"
            startup_bytes = startup_capture.read_bytes()
            first = tmp_path / "first"
            boundary = session._begin_case(request(), first)
            assert boundary["runtime_reused"] is False
            first_capture = Path(session.driver._screenshot(session.window))
            assert first_capture.parent == first / "ui"
            first_bytes = first_capture.read_bytes()
            session.case_index = 1
            second = tmp_path / "second"
            boundary = session._begin_case(request(), second)
            assert boundary["runtime_reused"] is True
            second_capture = Path(session.driver._screenshot(session.window))
            assert second_capture.parent == second / "ui"
            assert startup_capture.read_bytes() == startup_bytes
            assert first_capture.read_bytes() == first_bytes
            assert len(list(session.prompt_root.glob("*/*/metadata.json"))) == 1
        finally:
            assert session.close()
    assert engines[0].close_called.is_set()


def test_condition_close_destroys_native_window_before_certifying_cleanup(
    qtbot, tmp_path, controlled_condition_runtime
):
    from PyQt6 import sip

    from XBrainLab.ui.qt_runtime import drain_qt_runtime_after_event_loop

    session = PilotConditionSession.__new__(PilotConditionSession)
    with patch.dict(os.environ):
        try:
            session.__init__(request(), tmp_path)
            window = session.window
            destroyed = []
            window.destroyed.connect(lambda: destroyed.append(True))

            assert session.close() is True
            assert controlled_condition_runtime["engines"][0].close_called.is_set()
            assert sip.isdeleted(window), "Hidden is not native QWidget destruction"
            assert destroyed == [True]
            assert not sip.isdeleted(session.app)
        finally:
            session.close()
            if session.window is not None and not sip.isdeleted(session.window):
                session.window.deleteLater()
                drain_qt_runtime_after_event_loop(session.app)


def test_condition_close_retries_failed_cleanup_before_certifying_success(
    qtbot, tmp_path, controlled_condition_runtime, monkeypatch
):
    from PyQt6 import sip

    from XBrainLab.ui.qt_runtime import drain_qt_runtime_after_event_loop

    session = PilotConditionSession.__new__(PilotConditionSession)
    with patch.dict(os.environ):
        session.__init__(request(), tmp_path)
        window = session.window
        cancel = session.service.cancel_all_owned_operations
        attempts = []

        def fail_once():
            attempts.append(True)
            if len(attempts) == 1:
                raise RuntimeError("Injected first cleanup failure")
            return cancel()

        monkeypatch.setattr(session.service, "cancel_all_owned_operations", fail_once)
        try:
            assert session.close() is False
            assert not controlled_condition_runtime["engines"][0].close_called.is_set()
            assert session.close() is True
            assert len(attempts) >= 2, "A failed close must not latch cleanup success"
            assert controlled_condition_runtime["engines"][0].close_called.is_set()
            assert sip.isdeleted(window)
        finally:
            monkeypatch.setattr(session.service, "cancel_all_owned_operations", cancel)
            # Release real worker ownership even against the defective baseline,
            # whose first failure incorrectly latches closed=True.
            session.closed = False
            session.close()
            if session.window is not None and not sip.isdeleted(session.window):
                session.window.deleteLater()
                drain_qt_runtime_after_event_loop(session.app)


def test_condition_close_can_retry_after_native_window_was_destroyed(
    qtbot, tmp_path, controlled_condition_runtime, monkeypatch
):
    from PyQt6 import sip

    session = PilotConditionSession.__new__(PilotConditionSession)
    with patch.dict(os.environ):
        session.__init__(request(), tmp_path)
        wait = session.wait_until

        def late_deadline(predicate, seconds):
            wait(predicate, seconds)
            if seconds == 15:
                raise TimeoutError("Close completed at its deadline boundary")

        try:
            with monkeypatch.context() as fault:
                fault.setattr(session, "wait_until", late_deadline)
                assert session.close() is False
            assert sip.isdeleted(session.window)
            assert session.close() is True
            assert session.closed is True
        finally:
            session.close()


@pytest.mark.parametrize("failure", ["load_error", "startup_timeout"])
def test_unstarted_condition_cleanup_leaves_case_resumable(
    qtbot, monkeypatch, tmp_path, controlled_condition_runtime, failure
):
    from scripts.dev import assistant_pilot_condition as condition
    from scripts.dev import run_assistant_pilot as runner

    payload = condition_request()
    payload["jobs"] = payload["jobs"][:1]
    job = payload["jobs"][0]
    cases = tmp_path / "cases"
    cases.mkdir()
    failed_output = tmp_path / "failed-condition"
    control = controlled_condition_runtime
    control["load_error"] = failure == "load_error"
    real_wait = PilotConditionSession.wait_until

    def startup_deadline(session, predicate, seconds):
        if seconds == 180:
            qtbot.waitUntil(
                lambda: bool(control["engines"])
                and control["engines"][0].load_started.is_set()
            )
            raise TimeoutError("Injected elapsed startup deadline")
        return real_wait(session, predicate, seconds)

    with patch.dict(os.environ):
        with monkeypatch.context() as failing_start:
            if failure == "startup_timeout":
                failing_start.setattr(
                    PilotConditionSession, "wait_until", startup_deadline
                )
            result = condition.run_condition(payload, cases, failed_output)
        assert result["status"] == "measurement_failed"
        assert result["results"] == []
        assert result["cleanup_ok"] is True
        assert result["error_type"] == (
            "RuntimeError" if failure == "load_error" else "TimeoutError"
        )
        assert control["engines"][0].close_called.is_set()
        preserved_failure = (failed_output / "result.json").read_bytes()
        assert not (cases / job["id"]).exists()
        records = [
            {"event": "condition_end", "cleanup_certified": True},
            {"event": "session_end", "cleanup_certified": True},
        ]
        pending, invalid = runner._dev_pending_jobs([job], records, tmp_path, False)
        assert not invalid and [item["id"] for item in pending] == [job["id"]]

        control["load_error"] = False
        resumed_output = tmp_path / "resumed-condition"
        resumed_output.mkdir()
        session = PilotConditionSession.__new__(PilotConditionSession)
        try:
            session.__init__(job["payload"], resumed_output)
            boundary = session._begin_case(job["payload"], cases / job["id"])
            assert boundary["runtime_reused"] is False
            assert (cases / job["id"] / "ui").is_dir()
        finally:
            assert session.close()
        assert control["engines"][-1].close_called.is_set()
        assert (failed_output / "result.json").read_bytes() == preserved_failure


def test_pending_jobs_rejects_unknown_case_directory_without_removing_it(tmp_path):
    from scripts.dev import run_assistant_pilot as runner

    job = condition_request()["jobs"][0]
    unknown = tmp_path / "cases" / job["id"]
    unknown.mkdir(parents=True)
    marker = unknown / "unknown-partial.txt"
    marker.write_text("preserve this unclassified evidence")
    with pytest.raises(ValueError, match="Unresolved case directory"):
        runner._dev_pending_jobs([job], [], tmp_path, False)
    assert marker.read_text() == "preserve this unclassified evidence"


def test_condition_rejects_existing_first_case_without_overwriting_evidence(
    qtbot, tmp_path, controlled_condition_runtime
):
    from scripts.dev import assistant_pilot_condition as condition

    payload = condition_request()
    first = tmp_path / "cases" / payload["jobs"][0]["id"]
    first.mkdir(parents=True)
    result_path = first / "result.json"
    original = b'{"status":"recorded","correct":false,"cleanup_ok":true}'
    result_path.write_bytes(original)
    with patch.dict(os.environ):
        result = condition.run_condition(
            payload, tmp_path / "cases", tmp_path / "condition"
        )
    assert result["status"] == "measurement_failed"
    assert result["error_type"] == "FileExistsError"
    assert result["results"] == [] and result["cleanup_ok"] is True
    assert result_path.read_bytes() == original
    assert not (first / "ui").exists()
    engine = controlled_condition_runtime["engines"][0]
    assert len(engine.generated_messages) == 1  # Warm-up only, no case resubmission.
    assert engine.close_called.is_set()


def test_condition_cannot_mix_candidates_even_with_the_same_model_and_repeat():
    from tests.unit.scripts.test_assistant_pilot_case import experiment_request

    first = experiment_request()
    payload = {
        "schema": SCHEMA,
        "condition": "gemma3-rag-on",
        "experiment": first["experiment"],
        "case_start_budget_seconds": 1000,
        **{
            key: first[key]
            for key in ("candidate_index", "split", "repeat", "source_head")
        },
        "jobs": [{"id": "first", "payload": first}],
    }
    validate_condition_request(payload)
    payload["source_head"] = "b" * 40
    with pytest.raises(ValueError, match="identity"):
        validate_condition_request(payload)
    payload["source_head"] = first["source_head"]
    second = copy.deepcopy(first)
    second["candidate_index"] = 3
    payload["jobs"].append({"id": "second", "payload": second})
    with pytest.raises(ValueError, match="identit"):
        validate_condition_request(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("model_id", "microsoft/Phi-4-mini-instruct"),
        ("model_cache", "D:/other"),
        ("rag_enabled", True),
        ("rag_cache", "D:/rag"),
        ("seed", 1),
    ],
)
def test_condition_rejects_cross_case_runtime_drift(field, value):
    payload = condition_request()
    payload["jobs"][1]["payload"][field] = value
    with pytest.raises(ValueError):
        validate_condition_request(payload)


def test_condition_rejects_duplicate_case_artifact_identity():
    payload = condition_request()
    payload["jobs"][1]["id"] = payload["jobs"][0]["id"]
    with pytest.raises(ValueError, match="condition request"):
        validate_condition_request(payload)


def test_full_condition_requires_exact_initial_dev_authorization():
    payload = condition_request()
    first = payload["jobs"][0]
    payload["jobs"] = []
    for index in range(264):
        job = copy.deepcopy(first)
        job["id"] = f"gemma3-rag-on__DEV-A01-{index:03}-V0"
        job["payload"]["case"]["case_id"] = f"DEV-A01-{index:03}-V0"
        job["payload"]["rag_enabled"] = True
        job["payload"]["experiment"] = dict(DEV_EXPERIMENT)
        payload["jobs"].append(job)
    with pytest.raises(ValueError, match="condition request"):
        validate_condition_request(payload)
    payload["experiment"] = dict(DEV_EXPERIMENT)
    payload["case_start_budget_seconds"] = 14_000
    validate_condition_request(payload)
    payload["jobs"].append(copy.deepcopy(payload["jobs"][-1]))
    with pytest.raises(ValueError, match="condition request"):
        validate_condition_request(payload)
    payload["jobs"].pop()
    payload["jobs"][0]["payload"]["rag_enabled"] = False
    with pytest.raises(ValueError, match="RAG on"):
        validate_condition_request(payload)


def test_dev_condition_stops_cleanly_before_case_without_full_budget(
    tmp_path, monkeypatch
):
    from scripts.dev import assistant_pilot_condition as condition

    payload = condition_request()
    payload["experiment"] = dict(DEV_EXPERIMENT)
    payload["case_start_budget_seconds"] = 400
    for job in payload["jobs"]:
        job["payload"].update(experiment=dict(DEV_EXPERIMENT), rag_enabled=True)

    class Session:
        def __init__(self, *_):
            self.condition_evidence = {}

        def run_case(self, *_):
            pytest.fail("A case cannot start without its full bounded budget")

        def close(self):
            return True

    monkeypatch.setattr(condition, "PilotConditionSession", Session)
    result = condition.run_condition(
        payload, tmp_path / "cases", tmp_path / "condition"
    )
    assert result["stop_reason"] == "budget_exhausted"
    assert result["cleanup_ok"] is True
    assert result["results"] == []


def test_dev_budget_stop_keeps_completed_case_and_does_not_start_next(
    tmp_path, monkeypatch
):
    from scripts.dev import assistant_pilot_condition as condition

    payload = condition_request()
    payload.update(experiment=dict(DEV_EXPERIMENT), case_start_budget_seconds=900)
    for job in payload["jobs"]:
        job["payload"].update(experiment=dict(DEV_EXPERIMENT), rag_enabled=True)
    clock = [100.0]
    calls = []

    class Session:
        def __init__(self, *_):
            self.condition_evidence = {}

        def run_case(self, request, _destination):
            calls.append(request["case"]["case_id"])
            clock[0] += 500
            return {"case_id": calls[-1], "status": "recorded", "cleanup_ok": True}

        def close(self):
            return True

    monkeypatch.setattr(condition, "PilotConditionSession", Session)
    monkeypatch.setattr(condition.time, "perf_counter", lambda: clock[0])
    result = condition.run_condition(
        payload, tmp_path / "cases", tmp_path / "condition"
    )
    assert calls == ["DEV-A01-01-V0"]
    assert result["results"][0]["status"] == "recorded"
    assert result["stop_reason"] == "budget_exhausted"
    assert result["cleanup_ok"] is True


def test_first_case_boundary_records_product_string_pipeline_stage(tmp_path):
    session = PilotConditionSession.__new__(PilotConditionSession)
    session.case_index = 0
    session._assert_identity = lambda _payload: None
    session._boundary_clean = lambda: True
    session.service = SimpleNamespace(
        get_state=lambda: SimpleNamespace(pipeline_stage="empty")
    )
    session.runtime = SimpleNamespace(
        current=SimpleNamespace(model_id="google/gemma-3-4b-it")
    )
    session.manager = SimpleNamespace(agent_controller=SimpleNamespace(history=[]))
    session.driver = SimpleNamespace(begin_case=lambda path: path.mkdir())
    output = tmp_path / "case"
    assert session._begin_case({}, output)["pipeline_stage"] == "empty"
    assert (output / "ui").is_dir()


def test_condition_boundary_refuses_existing_confirmation_or_finalizing_training(
    monkeypatch,
):
    pending = SimpleNamespace(confirmation=None, workflow_handoff=None)
    session = PilotConditionSession.__new__(PilotConditionSession)
    session.runtime = SimpleNamespace(accepts_commands=True, turn_in_flight=False)
    session.manager = SimpleNamespace(
        agent_controller=SimpleNamespace(
            pending_interactions=pending, is_processing=False, history=[]
        ),
        chat_panel=object(),
    )
    training = SimpleNamespace(ready=True)
    session.service = SimpleNamespace(
        training=SimpleNamespace(wait_until_restart_safe=lambda **_: training.ready),
        get_state=lambda: SimpleNamespace(
            raw=SimpleNamespace(loaded=False),
            epoch=SimpleNamespace(available=False),
            dataset=SimpleNamespace(available=False),
            training=SimpleNamespace(is_running=False),
        ),
        get_active_owned_operation=lambda _kind: None,
    )
    monkeypatch.setattr(
        "scripts.dev.capture_chatpanel_local_walkthrough.collect_visible_messages",
        lambda _panel: [],
    )
    assert session._boundary_clean()
    pending.confirmation = object()
    assert not session._boundary_clean()
    pending.confirmation = None
    assert session._boundary_clean()
    training.ready = False
    assert not session._boundary_clean()


@pytest.mark.parametrize("boundary", ["reset", "cleanup", "cleanup_without_ack"])
def test_condition_drains_cancelled_training_view_before_case_boundary(
    qtbot, tmp_path, monkeypatch, controlled_condition_runtime, boundary
):
    from PyQt6.QtCore import QTimer

    from scripts.dev import assistant_pilot_condition as condition
    from scripts.dev.assistant_pilot_fixture import prepare_fixture
    from tests.unit.scripts.test_assistant_pilot_fixture import _fixture
    from XBrainLab.backend.application.owned_work import OwnedWorkKind

    session = PilotConditionSession.__new__(PilotConditionSession)
    held = []
    delivered = []
    holding = False
    real_wait = None
    timer = QTimer()
    with patch.dict(os.environ):
        try:
            session.__init__(request(), tmp_path)
            real_wait = session.wait_until
            acknowledge = session.service.acknowledge_view_publication_delivery

            def hold_terminal(revision, **kwargs):
                if holding:
                    held.append((revision, kwargs))
                    return False
                return acknowledge(revision, **kwargs)

            def release_terminal():
                nonlocal holding
                if held:
                    holding = False
                    delivered.extend(held)
                    for revision, kwargs in held:
                        acknowledge(revision, **kwargs)
                    held.clear()
                    timer.stop()

            monkeypatch.setattr(
                session.service, "acknowledge_view_publication_delivery", hold_terminal
            )
            timer.timeout.connect(release_terminal)

            def stop_and_queue_ack():
                nonlocal holding
                holding = True
                session.service.cancel_all_owned_operations()
                session.wait_until(
                    lambda: session.service.get_active_owned_operation(
                        OwnedWorkKind.TRAINING
                    )
                    is None
                    and bool(held),
                    15,
                )
                assert not session.service.training.wait_until_restart_safe(timeout=0)
                if boundary != "cleanup_without_ack":
                    timer.start(0)

            if boundary == "reset":
                prepare_fixture(
                    session.study,
                    _fixture("training"),
                    tmp_path / "training",
                    running_training_epochs=10000,
                )
                stop_and_queue_ack()
                session.case_index = 1
                state = session._begin_case(request(), tmp_path / "next")
                assert state["pipeline_stage"] == "empty"
            else:
                payload = request()
                payload["fixture"] = _fixture("training")
                payload["case"].update(
                    expected_workflow_stage="training",
                    fixture_id=payload["fixture"]["metadata"]["fixture_id"],
                )

                def fail_submission(*_args):
                    stop_and_queue_ack()
                    if boundary == "cleanup_without_ack":
                        monkeypatch.setattr(
                            session,
                            "wait_until",
                            lambda predicate, seconds: real_wait(
                                predicate, min(seconds, 0.1)
                            ),
                        )
                    raise RuntimeError("Injected input submission failure")

                monkeypatch.setattr(condition, "submit_case_input", fail_submission)
                result = session.run_case(payload, tmp_path / "case")
                assert result["status"] == "measurement_failed"
                assert result["detail"] == "Injected input submission failure"
                if boundary == "cleanup_without_ack":
                    assert result["cleanup_ok"] is False
                    assert "deadline exceeded" in result["cleanup_error"]
                    assert not delivered
                else:
                    assert result["cleanup_ok"] is True
            if boundary != "cleanup_without_ack":
                assert delivered
                assert session.service.training.wait_until_restart_safe(timeout=0)
        finally:
            timer.stop()
            holding = False
            if real_wait is not None:
                monkeypatch.setattr(session, "wait_until", real_wait)
            for revision, kwargs in held:
                acknowledge(revision, **kwargs)
            assert session.close()
