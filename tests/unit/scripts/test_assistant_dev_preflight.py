"""The no-inference preflight must exercise each exact research prompt profile."""

import json

import pytest

from scripts.dev.assistant_dev_preflight import model_contexts
from scripts.dev.assistant_experiment_config import MODELS
from XBrainLab.backend.application import get_application_service
from XBrainLab.backend.study import Study
from XBrainLab.llm.tools import get_all_tools
from XBrainLab.llm.tools.tool_registry import ToolRegistry


def test_configured_preflight_selects_only_full_valid_without_repeating_contexts(
    tmp_path,
):
    from scripts.dev.assistant_dev_preflight import selected_cases
    from scripts.dev.assistant_experiment_config import CONFIG_SCHEMA

    cases = [
        {
            "case_id": f"VALID-{kind}{family:02}-V{variant}",
            "family_id": f"VALID-{kind}{family:02}",
            "split": "VALID",
            "decision": decision,
        }
        for kind, decision, families in (
            ("A", "Action", 18),
            ("C", "Clarification", 6),
            ("N", "No-call", 9),
        )
        for family in range(families)
        for variant in range(3)
    ]
    bank = {
        "source": {"sha256": "bank"},
        "cases": [*cases, {"case_id": "DEV-not-selected", "split": "DEV"}],
    }
    config = {
        "schema": CONFIG_SCHEMA,
        "split": "VALID",
        "purpose": "research",
        "embedding_cache": ".",
        "resource_inventory": "resources.json",
        "budget_seconds": 1000,
        "models": [
            {
                "alias": "phi4",
                "candidate_index": 5,
                "source": {"head": "a" * 40, "root": "."},
                "model_cache": ".",
            }
        ],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    selection, actual = selected_cases(bank, path)
    assert selection["split"] == "VALID"
    assert len(actual) == 99
    assert set(selection["case_ids"]) == {case["case_id"] for case in cases}
    assert actual == cases
    bank["cases"].pop(0)
    with pytest.raises(ValueError, match="denominator"):
        selected_cases(bank, path)
    config["split"] = "TEST"
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="selected cases"):
        selected_cases(bank, path)


def _test_config():
    from scripts.dev.assistant_experiment_config import CONFIG_SCHEMA

    return {
        "schema": CONFIG_SCHEMA,
        "split": "TEST",
        "purpose": "research",
        "embedding_cache": ".",
        "resource_inventory": "resources.json",
        "budget_seconds": 1000,
        "models": [
            {
                "alias": "phi4",
                "candidate_index": 5,
                "source": {"head": "a" * 40, "root": "."},
                "model_cache": ".",
            }
        ],
    }


def test_configured_test_preflight_selects_one_population_not_repeats_or_ablations():
    from scripts.dev.assistant_dev_preflight import selected_cases

    cases = [
        {
            "case_id": f"TEST-{kind}{family:02}-V{variant}",
            "family_id": f"TEST-{kind}{family:02}",
            "split": "TEST",
            "decision": decision,
        }
        for kind, decision, families in (
            ("A", "Action", 36),
            ("C", "Clarification", 12),
            ("N", "No-call", 18),
        )
        for family in range(families)
        for variant in range(2)
    ]
    bank = {
        "source": {"sha256": "bank"},
        "cases": [*cases, {"case_id": "DEV-not-selected", "split": "DEV"}],
    }
    selection, actual = selected_cases(bank, _test_config())
    assert selection["split"] == "TEST"
    assert len(actual) == 132
    assert actual == cases


def test_test_preflight_captures_four_conditions_only_with_identical_admission():
    from scripts.dev.assistant_dev_context import DevContextAssembler

    study = Study()
    service = get_application_service(study)
    registry = ToolRegistry()
    for tool in get_all_tools():
        registry.register(tool)
    cases = [
        {
            "case_id": "synthetic-preflight",
            "input": "Open import.",
            "expected_workflow_stage": "empty",
        }
    ]
    try:
        contexts = model_contexts(registry, study, cases, config=_test_config())
        assert set(contexts) == {
            "phi4-full",
            "phi4-rag-off",
            "phi4-tool-filter-off",
            "phi4-retry-off",
        }
        captures = {name: records[0] for name, records in contexts.items()}
        baseline = captures["phi4-full"]
        legacy = DevContextAssembler(registry, study, model_id=MODELS["phi4"])
        assert baseline["messages"] == legacy.get_messages(
            [{"role": "user", "content": cases[0]["input"]}]
        )
        assert captures["phi4-rag-off"]["messages"] == baseline["messages"]
        assert captures["phi4-retry-off"]["messages"] == baseline["messages"]
        assert captures["phi4-tool-filter-off"]["messages"] != baseline["messages"]
        assert baseline["condition_policy"] == {
            "rag_enabled": True,
            "tool_filter_enabled": True,
            "max_format_recovery_attempts": 1,
        }
        assert captures["phi4-rag-off"]["condition_policy"]["rag_enabled"] is False
        assert (
            captures["phi4-retry-off"]["condition_policy"][
                "max_format_recovery_attempts"
            ]
            == 0
        )
        assert (
            captures["phi4-tool-filter-off"]["condition_policy"]["tool_filter_enabled"]
            is False
        )
        for capture in captures.values():
            assert capture["model_id"] == MODELS["phi4"]
            assert capture["case_id"] == cases[0]["case_id"]
            assert (
                capture["actual_host_generation"]
                == service.get_view_publication().generation
            )
            assert capture["tool_names"] == baseline["tool_names"]
            assert capture["blocked_reasons"] == baseline["blocked_reasons"]
            assert (
                capture["rag_allowed_tool_names"] == baseline["rag_allowed_tool_names"]
            )
    finally:
        service.close()


def test_preflight_captures_all_profiles_with_current_request_and_real_publication():
    study = Study()
    service = get_application_service(study)
    registry = ToolRegistry()
    for tool in get_all_tools():
        registry.register(tool)
    cases = [
        {
            "case_id": "DEV-A01-01-V0",
            "input": "Open import.",
            "expected_workflow_stage": "empty",
        }
    ]
    try:
        contexts = model_contexts(registry, study, cases)
        assert set(contexts) == set(MODELS.values())
        systems = set()
        for model_cases in contexts.values():
            assert len(model_cases) == 1
            capture = model_cases[0]
            assert capture["case_id"] == cases[0]["case_id"]
            assert (
                capture["actual_host_generation"]
                == service.get_view_publication().generation
            )
            messages = capture["messages"]
            systems.add(messages[0]["content"])
            request = json.loads(messages[-1]["content"])
            assert request["current_user"]["text"] == "Open import."
            assert "backend_generation" not in request["application_state"]
            assert capture["message_utf8_bytes"] == sum(
                len(message["content"].encode("utf-8")) for message in messages
            )
        assert len(systems) == 5
    finally:
        service.close()


@pytest.mark.parametrize("candidate", range(1, 6))
def test_preflight_uses_explicit_historical_candidate(live_study, candidate):
    from tests.unit.scripts.test_assistant_dev_profiles import archived_class

    study, _service = live_study
    registry = ToolRegistry()
    for tool in get_all_tools():
        registry.register(tool)
    config = _test_config()
    config["split"] = "VALID"
    config["prompt_profile"] = "frozen-dev-round"
    config["models"][0]["candidate_index"] = candidate
    cases = [
        {
            "case_id": "synthetic",
            "input": "Open import.",
            "expected_workflow_stage": "empty",
        }
    ]
    contexts = model_contexts(registry, study, cases, config=config)
    kwargs = {"model_id": MODELS["phi4"]} if candidate != 1 else {}
    original = archived_class(candidate)(registry, study, **kwargs)
    capture = contexts[MODELS["phi4"]][0]
    assert capture["messages"] == original.get_messages(
        [{"role": "user", "content": cases[0]["input"]}]
    )
    assert capture["candidate_index"] == candidate
    assert capture["prompt_profile"] == "frozen-dev-round"


@pytest.fixture
def live_study():
    study = Study()
    service = get_application_service(study)
    try:
        yield study, service
    finally:
        service.close()


@pytest.mark.parametrize("drift", ["unavailable", "trained"])
def test_preflight_rejects_actual_context_drift_with_valid_backend(
    live_study, monkeypatch, drift
):
    from scripts.dev.assistant_dev_context import DevContextAssembler

    study, service = live_study
    registry = ToolRegistry()
    for tool in get_all_tools():
        registry.register(tool)
    original = DevContextAssembler.get_messages

    def drifting_messages(self, *args, **kwargs):
        messages = original(self, *args, **kwargs)
        value = json.loads(messages[-1]["content"])
        value["application_state"].update(
            workflow_stage=drift, state_reliable=drift != "unavailable"
        )
        messages[-1]["content"] = json.dumps(value)
        return messages

    monkeypatch.setattr(DevContextAssembler, "get_messages", drifting_messages)
    assert service.get_state().pipeline_stage == "empty"
    with pytest.raises(ValueError, match="initial_workflow_stage_mismatch"):
        model_contexts(
            registry,
            study,
            [
                {
                    "case_id": "synthetic",
                    "input": "Do nothing.",
                    "expected_workflow_stage": "empty",
                }
            ],
            config=_test_config(),
        )
