"""The no-inference preflight must exercise each exact research prompt profile."""

import json

from scripts.dev.assistant_dev_preflight import model_contexts
from scripts.dev.assistant_experiment_config import MODELS
from XBrainLab.backend.application import get_application_service
from XBrainLab.backend.study import Study
from XBrainLab.llm.tools import get_all_tools
from XBrainLab.llm.tools.tool_registry import ToolRegistry


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
