"""Complete single-turn examples retain schema/source and injection boundaries."""

import json
from collections import Counter

import pytest

from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.llm.agent.parser import CommandParser, ToolEnvelopeStatus
from XBrainLab.llm.rag.config import RAGConfig
from XBrainLab.llm.rag.example_policy import (
    example_decision_name,
    example_search_text,
    is_primary_workflow_example,
    prompt_example_from_metadata,
    prompt_proposal_from_metadata,
)

_GOLD_SET_PATH = RAGConfig.get_gold_set_path()


def _proposal(action, parameters=None):
    return {"tool_name": action, "parameters": parameters or {}}


def _metadata(proposal, text="User Input"):
    return {"proposal": json.dumps(proposal), "source_text": text}


def test_single_turn_examples_require_complete_current_input_only():
    proposal = _proposal("apply_bandpass_filter", {"low_freq": 7, "high_freq": 30})
    metadata = _metadata(proposal, "Bandpass from 7 to 30 Hz.")
    assert prompt_example_from_metadata(metadata) == {
        "input": metadata["source_text"],
        "expected_proposal": proposal,
    }
    assert example_search_text(metadata) == metadata["source_text"]
    assert prompt_proposal_from_metadata({**metadata, "source_text": "30 Hz"}) is None
    assert (
        prompt_proposal_from_metadata(
            {**metadata, "prior_turn": {"input": "7 Hz", "expected_proposal": proposal}}
        )
        is None
    )


@pytest.mark.parametrize("source", ["1280 Hz", "64 Hz", "", None])
def test_numeric_parameters_cannot_come_from_examples_or_partial_number(source):
    assert (
        prompt_proposal_from_metadata(
            _metadata(_proposal("resample_data", {"rate": 128}), source)
        )
        is None
    )


@pytest.mark.parametrize(
    "action,parameters,text",
    [
        ("import_eeg_data", {}, "Import EEG."),
        ("resample_data", {"rate": 128}, "Resample to 128 Hz."),
        (
            "apply_bandpass_filter",
            {"low_freq": 4, "high_freq": 38},
            "Bandpass 4 to 38 Hz.",
        ),
    ],
)
def test_current_gui_and_complete_direct_actions_are_valid(action, parameters, text):
    proposal = _proposal(action, parameters)
    metadata = _metadata(proposal, text)
    assert prompt_proposal_from_metadata(metadata) == proposal
    assert example_decision_name(metadata) == action


@pytest.mark.parametrize(
    "action",
    [
        "list_files",
        "query_state",
        "scan_source",
        "set_model",
        "evaluate",
        "visualize",
        "saliency",
    ],
)
def test_retired_actions_cannot_be_published(action):
    assert prompt_proposal_from_metadata(_metadata(_proposal(action))) is None


@pytest.mark.parametrize(
    "proposal",
    [
        _proposal("apply_bandpass_filter", {"low_freq": 4}),
        {**_proposal("import_eeg_data"), "extra": 1},
        {"command": "import_eeg_data", "parameters": {}},
        [_proposal("import_eeg_data")],
        _proposal("resample_data", {"rate": True}),
        _proposal("resample_data", {"rate": float("nan")}),
        {
            "decision": "execute",
            "mode": "new_request",
            "action": "import_eeg_data",
            "changes": {},
            "message": None,
        },
        {
            "decision": "execute",
            "request": {"mode": "replace", "action": "import_eeg_data", "changes": {}},
            "message": None,
        },
    ],
)
def test_malformed_partial_and_retired_wire_are_rejected(proposal):
    metadata = _metadata(proposal, "4 Hz")
    assert prompt_proposal_from_metadata(metadata) is None
    assert not is_primary_workflow_example(metadata)
    assert example_decision_name(metadata) is None


@pytest.mark.parametrize("message", [None, "", " "])
def test_response_requires_nonempty_message(message):
    assert (
        prompt_proposal_from_metadata(
            _metadata(
                {"tool_name": "respond_to_user", "parameters": {"message": message}}
            )
        )
        is None
    )


def test_response_is_not_an_executable_tool_or_partial_parameter_store():
    proposal = _proposal(
        "respond_to_user", {"message": "Please restate the complete request."}
    )
    assert prompt_proposal_from_metadata(_metadata(proposal)) == proposal
    assert example_decision_name(_metadata(proposal)) == "respond_to_user"
    assert "respond_to_user" not in AGENT_ACTION_CONTRACTS.model_tool_names()
    malformed = _proposal("respond_to_user", {"message": "Upper?", "low_freq": 4})
    assert prompt_proposal_from_metadata(_metadata(malformed)) is None


@pytest.mark.parametrize("garbage", [None, "invalid", []])
@pytest.mark.parametrize("serialized", [False, True])
def test_malformed_lists_are_not_silently_repaired(garbage, serialized):
    raw = [_proposal("import_eeg_data"), garbage]
    assert (
        prompt_proposal_from_metadata(
            {
                "proposal": json.dumps(raw) if serialized else raw,
                "source_text": "Import EEG.",
            }
        )
        is None
    )


def test_corpus_covers_all_actions_with_complete_schemas_and_current_sources():
    items = json.loads(_GOLD_SET_PATH.read_text(encoding="utf-8"))
    assert len(items) == 157
    counts = Counter()
    for item in items:
        assert set(item) == {"id", "input", "category", "expected_proposal"}
        metadata = _metadata(item["expected_proposal"], item["input"])
        assert is_primary_workflow_example(metadata), item["id"]
        counts[example_decision_name(metadata)] += 1
        parsed = CommandParser.parse_product(json.dumps(item["expected_proposal"]))
        assert parsed.status in (ToolEnvelopeStatus.VALID, ToolEnvelopeStatus.NO_TOOL)
    assert set(counts) == AGENT_ACTION_CONTRACTS.model_tool_names() | {
        "respond_to_user"
    }
    assert all(counts[name] >= 4 for name in AGENT_ACTION_CONTRACTS.model_tool_names())
    assert counts["respond_to_user"] >= 12
    assert len({item["id"] for item in items}) == len(items)
    assert len({item["input"].strip().casefold() for item in items}) == len(items)
    assert RAGConfig.gold_set_integrity_ok()
    assert not any(item["category"] == "contextual_parameter" for item in items)


def test_gold_set_has_no_cjk_or_duplicate_input_proposal_pairs():
    items = json.loads(_GOLD_SET_PATH.read_text(encoding="utf-8"))
    pairs = [
        (item["input"], json.dumps(item["expected_proposal"], sort_keys=True))
        for item in items
    ]
    assert all(
        not any("\u3400" <= char <= "\u9fff" for char in item["input"])
        for item in items
    )
    assert len(pairs) == len(set(pairs))


def test_seven_missing_partial_examples_request_complete_restatement_not_saved_values():
    items = json.loads(_GOLD_SET_PATH.read_text(encoding="utf-8"))
    rows = [
        row
        for row in items
        if row["category"]
        in {"response_missing_parameter", "response_partial_parameter"}
    ]
    assert len(rows) == 7
    for row in rows:
        proposal = prompt_proposal_from_metadata(
            _metadata(row["expected_proposal"], row["input"])
        )
        assert proposal["tool_name"] == "respond_to_user"
        assert set(proposal["parameters"]) == {"message"}
        assert "complete operation" in proposal["parameters"]["message"]


@pytest.mark.parametrize(
    "topic", ["bandpass", "notch", "resample", "reference", "normalize"]
)
def test_fixed_definition_examples_remain_nonexecuting_explanations(topic):
    rows = json.loads(_GOLD_SET_PATH.read_text(encoding="utf-8"))
    (row,) = [row for row in rows if row["id"] == f"respond_definition_{topic}_01"]
    assert row["category"] == "response_definition"
    proposal = prompt_proposal_from_metadata(
        _metadata(row["expected_proposal"], row["input"])
    )
    assert proposal["tool_name"] == "respond_to_user"
    assert proposal["parameters"]["message"].strip()


@pytest.mark.parametrize(
    "example_id",
    [
        "apply_bandpass_filter_09",
        "apply_notch_filter_09",
        "resample_data_08",
        "normalize_data_08",
    ],
)
def test_compound_requests_teach_choice_not_partial_execution(example_id):
    rows = json.loads(_GOLD_SET_PATH.read_text(encoding="utf-8"))
    row = next(row for row in rows if row["id"] == example_id)
    proposal = prompt_proposal_from_metadata(
        _metadata(row["expected_proposal"], row["input"])
    )
    assert proposal["tool_name"] == "respond_to_user"
    assert "first" in proposal["parameters"]["message"]
    assert "?" in proposal["parameters"]["message"]
    assert row["category"] == "response_compound_request"
