from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from XBrainLab.llm.rag.bm25 import BM25Index
from XBrainLab.llm.rag.example_policy import (
    is_primary_workflow_example,
    prompt_tool_call_from_metadata,
    tool_calls_from_metadata,
    tool_name_from_call,
)

_GOLD_SET_PATH = (
    Path(__file__).resolve().parents[4]
    / "XBrainLab"
    / "llm"
    / "rag"
    / "data"
    / "gold_set.json"
)


def test_rag_example_policy_rejects_legacy_compatibility_tools() -> None:
    metadata = {
        "tool_calls": (
            '[{"tool_name": "load_data", "parameters": {"paths": ["/tmp/a.gdf"]}}]'
        ),
    }

    assert is_primary_workflow_example(metadata) is False


def test_rag_example_policy_accepts_data_interpretation_tools() -> None:
    metadata = {
        "tool_calls": (
            '[{"tool_name": "scan_source", "parameters": {"source_path": "/tmp/eeg"}}]'
        ),
    }

    assert tool_calls_from_metadata(metadata)[0]["tool_name"] == "scan_source"
    assert prompt_tool_call_from_metadata(metadata) == {
        "tool_name": "scan_source",
        "parameters": {"source_path": "/tmp/eeg"},
    }
    assert is_primary_workflow_example(metadata) is True


def test_rag_example_policy_rejects_calls_outside_live_tool_schema() -> None:
    invalid_calls = (
        {"tool_name": "unknown_tool", "parameters": {}},
        {"tool_name": "scan_source", "parameters": {}},
        {
            "tool_name": "scan_source",
            "parameters": {
                "source_path": "/tmp/eeg",
                "source_hint": "archive",
            },
        },
        {
            "tool_name": "validate_interpretation",
            "parameters": {"unexpected": True},
        },
        {
            "tool_name": "preview_interpretation",
            "parameters": {"choices": {"skip_labels": "yes"}},
        },
    )

    for call in invalid_calls:
        metadata = {"tool_calls": json.dumps([call])}

        assert prompt_tool_call_from_metadata(metadata) is None
        assert is_primary_workflow_example(metadata) is False


def test_rag_example_policy_rejects_shapes_that_violate_product_envelope() -> None:
    multi_call = {
        "tool_calls": (
            '[{"tool_name": "scan_source", "parameters": {"source_path": '
            '"/tmp/eeg"}}, {"tool_name": "preview_interpretation", '
            '"parameters": {}}]'
        )
    }
    extra_field = {
        "tool_calls": (
            '[{"tool_name": "scan_source", "parameters": {"source_path": '
            '"/tmp/eeg"}, "explanation": "scan first"}]'
        )
    }
    wrong_shape = {"tool_calls": '{"command": "scan_source"}'}

    for metadata in (multi_call, extra_field, wrong_shape):
        assert prompt_tool_call_from_metadata(metadata) is None
        assert is_primary_workflow_example(metadata) is False


def test_rag_example_policy_rejects_dict_and_function_legacy_shapes() -> None:
    function_metadata = {
        "tool_calls": '{"function": {"name": "attach_labels"}, "arguments": {}}',
    }
    tool_metadata = {
        "expected_tool_calls": {"tool": "import_labels", "parameters": {}},
    }

    assert tool_name_from_call(tool_calls_from_metadata(function_metadata)[0]) == (
        "attach_labels"
    )
    assert is_primary_workflow_example(function_metadata) is False
    assert is_primary_workflow_example(tool_metadata) is False


def test_bm25_gold_set_excludes_legacy_data_entry_examples() -> None:
    index = BM25Index()

    index.build_from_json(_GOLD_SET_PATH)

    assert index.doc_count > 0
    for _doc_id, _text, metadata in index._docs:
        assert is_primary_workflow_example(metadata) is True


def test_all_prompt_eligible_gold_examples_match_live_tool_schema() -> None:
    from XBrainLab.llm.agent.verifier import ToolSchemaValidator
    from XBrainLab.llm.tools import get_all_tools

    items = json.loads(_GOLD_SET_PATH.read_text(encoding="utf-8"))
    schemas = {tool.name: tool.parameters for tool in get_all_tools(mode="mock")}
    validator = ToolSchemaValidator(schemas)
    eligible_count = 0

    for item in items:
        prompt_call = prompt_tool_call_from_metadata(
            {"tool_calls": json.dumps(item.get("expected_tool_calls"))}
        )
        if prompt_call is None:
            continue

        eligible_count += 1
        assert list(prompt_call) == ["tool_name", "parameters"]
        result = validator.validate(
            prompt_call["tool_name"],
            prompt_call["parameters"],
        )
        assert result.is_valid, f"{item.get('id')}: {result.error_message}"

    assert eligible_count > 0


def test_gold_set_has_live_schema_valid_data_interpretation_workflow_examples() -> None:
    from XBrainLab.llm.agent.verifier import ToolSchemaValidator
    from XBrainLab.llm.tools import get_all_tools

    items = json.loads(_GOLD_SET_PATH.read_text(encoding="utf-8"))
    examples_by_id = {item["id"]: item for item in items}
    expected_examples = {
        "scan_source_01": "scan_source",
        "preview_interpretation_01": "preview_interpretation",
        "validate_interpretation_01": "validate_interpretation",
        "apply_interpretation_01": "apply_interpretation",
    }
    schemas = {tool.name: tool.parameters for tool in get_all_tools(mode="mock")}
    validator = ToolSchemaValidator(schemas)

    for example_id, expected_tool_name in expected_examples.items():
        example = examples_by_id[example_id]
        calls = example["expected_tool_calls"]

        assert len(calls) == 1
        assert set(calls[0]) == {"tool_name", "parameters"}
        assert calls[0]["tool_name"] == expected_tool_name
        result = validator.validate(expected_tool_name, calls[0]["parameters"])
        assert result.is_valid, f"{example_id}: {result.error_message}"
        assert is_primary_workflow_example({"tool_calls": json.dumps(calls)}) is True


def test_retriever_filters_legacy_examples_from_existing_vector_store() -> None:
    from XBrainLab.llm.rag.retriever import RAGRetriever

    legacy_payload = {
        "page_content": "Load the file /tmp/a.gdf",
        "metadata": {
            "tool_calls": (
                '[{"tool_name": "load_data", "parameters": {"paths": ["/tmp/a.gdf"]}}]'
            ),
        },
    }
    primary_payload = {
        "page_content": "Scan the EEG source /tmp/eeg",
        "metadata": {
            "tool_calls": (
                '[{"tool_name": "scan_source", "parameters": {"source_path": '
                '"/tmp/eeg"}}]'
            ),
        },
    }
    invalid_payload = {
        "page_content": "Scan without identifying a source",
        "metadata": {
            "tool_calls": '[{"tool_name": "scan_source", "parameters": {}}]',
        },
    }
    retriever = RAGRetriever()
    test_retriever = cast(Any, retriever)
    test_retriever.embeddings = SimpleNamespace(
        embed_query=lambda _query: [0.1, 0.2],
    )
    test_retriever.client = SimpleNamespace(
        close=lambda: None,
        query_points=lambda **_kwargs: SimpleNamespace(
            points=[
                SimpleNamespace(id="legacy", score=1.0, payload=legacy_payload),
                SimpleNamespace(id="invalid", score=0.95, payload=invalid_payload),
                SimpleNamespace(id="primary", score=0.9, payload=primary_payload),
            ],
        ),
    )

    try:
        result = retriever.get_similar_examples("load EEG data", k=2)
    finally:
        retriever.close()

    envelope = json.loads(result)
    assert envelope["schema"] == "xbrainlab.untrusted_context.v1"
    assert len(envelope["items"]) == 1
    example = envelope["items"][0]
    assert "scan_source" in result
    assert "Scan the EEG source" in result
    assert "```" not in result
    assert '[{"tool_name"' not in result
    assert "Assistant action:" not in result
    expected_action = example["data"]["expected_action"]
    assert expected_action["tool_name"] == "scan_source"
    assert "/tmp/eeg" not in expected_action["parameters"]["source_path"]
    assert "[REDACTED_PATH]" in expected_action["parameters"]["source_path"]
    assert "load_data" not in result
    assert "Load the file" not in result
    assert "Scan without identifying a source" not in result
