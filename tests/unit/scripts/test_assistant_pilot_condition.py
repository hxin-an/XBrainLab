"""Condition workers may reuse only one exact model/RAG runtime identity."""

import copy
from types import SimpleNamespace

import pytest

from scripts.dev.assistant_pilot_condition import (
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
