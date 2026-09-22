"""Condition workers may reuse only one exact model/RAG runtime identity."""

import copy
from types import SimpleNamespace

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
    output = tmp_path / "case"
    output.mkdir()
    assert session._begin_case({}, output)["pipeline_stage"] == "empty"
