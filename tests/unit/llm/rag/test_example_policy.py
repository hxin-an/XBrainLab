"""RAG examples must teach only the approved target action surface."""

import json
from collections import Counter
from pathlib import Path

import pytest

from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.llm.agent.decision_contract import MODEL_RESPONSE_TOOL_NAME
from XBrainLab.llm.agent.parser import CommandParser, ToolEnvelopeStatus
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


def test_response_example_uses_the_existing_non_executing_contract() -> None:
    assert prompt_tool_call_from_metadata(
        _metadata("respond_to_user", {"message": "I will not run a filter."})
    ) == {
        "tool_name": "respond_to_user",
        "parameters": {"message": "I will not run a filter."},
    }
    for parameters in ({}, {"message": " "}, {"message": "OK", "execute": True}):
        assert (
            prompt_tool_call_from_metadata(_metadata("respond_to_user", parameters))
            is None
        )
    assert MODEL_RESPONSE_TOOL_NAME not in AGENT_ACTION_CONTRACTS.model_tool_names()


@pytest.mark.parametrize(
    ("pending_action", "missing"),
    [
        ("retired_filter", ["freq"]),
        ("create_epochs", ["tmin"]),
        ("resample_data", ["unknown"]),
    ],
)
def test_typed_response_examples_require_real_direct_tool_parameters(
    pending_action, missing
):
    assert (
        prompt_tool_call_from_metadata(
            _metadata(
                "respond_to_user",
                {
                    "message": "What value should I use?",
                    "pending_action": pending_action,
                    "missing_inputs": missing,
                },
            )
        )
        is None
    )


def test_corpus_demonstrates_missing_input_branch_for_each_direct_tool():
    from XBrainLab.llm.agent.verifier import DIRECT_PARAMETER_TOOLS
    from XBrainLab.llm.tools import get_all_tools

    schemas = {tool.name: tool.parameters for tool in get_all_tools()}
    covered = set()
    for example in json.loads(_GOLD_SET_PATH.read_text(encoding="utf-8")):
        decision = prompt_tool_call_from_metadata(example)
        assert decision is not None
        params = decision["parameters"]
        pending = params.get("pending_action")
        if pending:
            assert decision["tool_name"] == "respond_to_user"
            assert set(params["missing_inputs"]) <= set(schemas[pending]["required"])
            if set(params["missing_inputs"]) == set(schemas[pending]["required"]):
                covered.add(pending)
    assert covered == DIRECT_PARAMETER_TOOLS


@pytest.mark.parametrize("garbage", [None, "invalid", []])
@pytest.mark.parametrize("serialized", [False, True])
@pytest.mark.parametrize(
    "call",
    [
        {"tool_name": "import_eeg_data", "parameters": {}},
        {"tool_name": "respond_to_user", "parameters": {"message": "No action."}},
    ],
)
def test_malformed_list_is_not_silently_repaired_into_valid_example(
    garbage, serialized, call
):
    calls = [call, garbage]
    metadata = {"tool_calls": json.dumps(calls) if serialized else calls}
    assert prompt_tool_call_from_metadata(metadata) is None


def test_gold_set_exactly_covers_every_approved_action_with_live_schemas() -> None:
    from XBrainLab.llm.agent.verifier import ToolSchemaValidator
    from XBrainLab.llm.tools import get_all_tools

    items = json.loads(_GOLD_SET_PATH.read_text(encoding="utf-8"))
    schemas = {tool.name: tool.parameters for tool in get_all_tools()}
    validator = ToolSchemaValidator(schemas)
    covered: set[str] = set()

    for item in items:
        calls = item["expected_tool_calls"]
        assert len(calls) == 1, item["id"]
        call = calls[0]
        assert set(call) == {"tool_name", "parameters"}, item["id"]
        if call["tool_name"] != MODEL_RESPONSE_TOOL_NAME:
            result = validator.validate(call["tool_name"], call["parameters"])
            assert result.is_valid, f"{item['id']}: {result.error_message}"
        assert is_primary_workflow_example({"tool_calls": json.dumps(calls)}), item[
            "id"
        ]
        covered.add(call["tool_name"])

    assert covered == AGENT_ACTION_CONTRACTS.model_tool_names() | {
        MODEL_RESPONSE_TOOL_NAME
    }


def test_gold_set_has_no_cjk_or_duplicate_input_action_pairs() -> None:
    items = json.loads(_GOLD_SET_PATH.read_text(encoding="utf-8"))
    pairs = [
        (
            item["input"],
            json.dumps(
                item["expected_tool_calls"],
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        for item in items
    ]

    assert all(
        not any("\u3400" <= char <= "\u9fff" for char in item["input"])
        for item in items
    )
    assert len(pairs) == len(set(pairs))


def test_bundled_corpus_preserves_action_coverage_and_response_examples() -> None:
    items = json.loads(_GOLD_SET_PATH.read_text(encoding="utf-8"))
    counts = Counter(item["expected_tool_calls"][0]["tool_name"] for item in items)

    assert all(counts[name] >= 4 for name in AGENT_ACTION_CONTRACTS.model_tool_names())
    assert counts[MODEL_RESPONSE_TOOL_NAME] >= 12
    assert len({item["id"] for item in items}) == len(items)
    assert len({item["input"].strip().casefold() for item in items}) == len(items)


@pytest.mark.parametrize(
    "example_id",
    [
        "apply_bandpass_filter_09",
        "apply_notch_filter_09",
        "resample_data_08",
        "normalize_data_08",
    ],
)
def test_compound_requests_teach_a_choice_not_partial_execution(example_id) -> None:
    """Protect the four reviewed answers, not model comprehension of the rule."""
    items = json.loads(_GOLD_SET_PATH.read_text(encoding="utf-8"))
    example = next(item for item in items if item["id"] == example_id)
    decision = prompt_tool_call_from_metadata(
        {"tool_calls": example["expected_tool_calls"]}
    )

    assert decision is not None
    result = CommandParser.parse_product(json.dumps(decision))
    assert result.status is ToolEnvelopeStatus.NO_TOOL
    assert not result.commands
    assert set(decision["parameters"]) == {"message"}
    assert "first" in result.message and "?" in result.message
    assert example["category"] == "response_compound_request"


def test_bm25_indexes_only_target_examples() -> None:
    index = BM25Index()

    index.build_from_json(_GOLD_SET_PATH)

    assert index.doc_count > 0
    assert all(is_primary_workflow_example(metadata) for _, _, metadata in index._docs)
