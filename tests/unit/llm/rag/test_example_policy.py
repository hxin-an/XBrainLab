"""RAG examples must teach only the approved target action surface."""

import json
from pathlib import Path

from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.llm.rag.bm25 import BM25Index
from XBrainLab.llm.rag.example_policy import (
    is_primary_workflow_example,
    prompt_tool_call_from_metadata,
)

_GOLD_SET_PATH = (
    Path(__file__).resolve().parents[4]
    / "XBrainLab"
    / "llm"
    / "rag"
    / "data"
    / "gold_set.json"
)


def _metadata(tool_name: str, parameters: dict) -> dict[str, str]:
    return {
        "tool_calls": json.dumps([{"tool_name": tool_name, "parameters": parameters}])
    }


def test_rag_policy_accepts_target_gui_and_direct_actions() -> None:
    assert prompt_tool_call_from_metadata(_metadata("import_eeg_data", {})) == {
        "tool_name": "import_eeg_data",
        "parameters": {},
    }
    assert prompt_tool_call_from_metadata(
        _metadata("apply_bandpass_filter", {"low_freq": 4, "high_freq": 38})
    ) == {
        "tool_name": "apply_bandpass_filter",
        "parameters": {"low_freq": 4, "high_freq": 38},
    }


def test_rag_policy_rejects_retired_and_malformed_actions() -> None:
    for tool_name in (
        "list_files",
        "query_state",
        "scan_source",
        "set_model",
        "evaluate",
        "visualize",
        "saliency",
    ):
        assert prompt_tool_call_from_metadata(_metadata(tool_name, {})) is None
    invalid = (
        _metadata("apply_bandpass_filter", {"low_freq": 4}),
        {"tool_calls": '[{"tool_name":"import_eeg_data","parameters":{},"extra":1}]'},
        {"tool_calls": '[{"command":"import_eeg_data","parameters":{}}]'},
        {
            "tool_calls": json.dumps(
                [
                    {"tool_name": "import_eeg_data", "parameters": {}},
                    {
                        "tool_name": "switch_panel",
                        "parameters": {"panel_name": "dataset"},
                    },
                ]
            )
        },
    )
    for metadata in invalid:
        assert prompt_tool_call_from_metadata(metadata) is None
        assert is_primary_workflow_example(metadata) is False


def test_gold_set_exactly_covers_every_approved_action_with_live_schemas() -> None:
    from XBrainLab.llm.agent.verifier import ToolSchemaValidator
    from XBrainLab.llm.tools import get_all_tools

    items = json.loads(_GOLD_SET_PATH.read_text(encoding="utf-8"))
    schemas = {tool.name: tool.parameters for tool in get_all_tools(mode="mock")}
    validator = ToolSchemaValidator(schemas)
    covered: set[str] = set()

    for item in items:
        calls = item["expected_tool_calls"]
        assert len(calls) == 1, item["id"]
        call = calls[0]
        assert set(call) == {"tool_name", "parameters"}, item["id"]
        result = validator.validate(call["tool_name"], call["parameters"])
        assert result.is_valid, f"{item['id']}: {result.error_message}"
        assert is_primary_workflow_example({"tool_calls": json.dumps(calls)}), item[
            "id"
        ]
        covered.add(call["tool_name"])

    assert covered == AGENT_ACTION_CONTRACTS.model_tool_names()


def test_bm25_indexes_only_target_examples() -> None:
    index = BM25Index()

    index.build_from_json(_GOLD_SET_PATH)

    assert index.doc_count > 0
    assert all(is_primary_workflow_example(metadata) for _, _, metadata in index._docs)
