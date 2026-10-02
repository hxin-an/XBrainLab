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
    with pytest.raises(ValueError, match="Unsupported"):
        selected_cases(bank, path)


def test_preflight_captures_all_profiles_with_current_request_and_real_publication():
    study = Study()
    service = get_application_service(study)
    registry = ToolRegistry()
    for tool in get_all_tools():
        registry.register(tool)
    cases = [{"case_id": "DEV-A01-01-V0", "input": "Open import."}]
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
