"""RAG examples teach the current proposal contract with actual user sources."""

import json
from collections import Counter

import pytest

from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS
from XBrainLab.llm.agent.decision_contract import MODEL_RESPONSE_TOOL_NAME
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


def _proposal(action, parameters=None, *, text="User Input"):
    return {
        "decision": "execute",
        "mode": "new_request",
        "action": action,
        "changes": {
            key: {"value": value, "source_turn": "U1", "quote": text}
            for key, value in (parameters or {}).items()
        },
        "message": None,
    }


def _metadata(proposal, text="User Input", prior_turn=None):
    metadata = {"proposal": json.dumps(proposal), "source_text": text}
    if prior_turn is not None:
        metadata["prior_turn"] = prior_turn
    return metadata


def test_new_proposal_policy_validates_original_source_and_rejects_legacy():
    proposal = _proposal("resample_data", {"rate": 128}, text="128 Hz")
    metadata = _metadata(proposal, "Resample to 128 Hz.")
    assert prompt_proposal_from_metadata(metadata) == proposal
    assert prompt_proposal_from_metadata({**metadata, "source_text": "1280 Hz"}) is None
    assert (
        prompt_proposal_from_metadata(
            {
                "tool_calls": [
                    {"tool_name": "resample_data", "parameters": {"rate": 128}}
                ]
            }
        )
        is None
    )


def test_rag_policy_accepts_target_gui_and_direct_actions():
    for proposal, source in [
        (_proposal("import_eeg_data"), "Import EEG."),
        (
            _proposal(
                "apply_bandpass_filter",
                {"low_freq": 4, "high_freq": 38},
                text="4 to 38 Hz",
            ),
            "Bandpass 4 to 38 Hz.",
        ),
    ]:
        assert prompt_proposal_from_metadata(_metadata(proposal, source)) == proposal
        assert example_decision_name(_metadata(proposal, source)) == proposal["action"]


def test_retired_nested_proposal_cannot_be_published_as_an_example():
    nested = {
        "decision": "execute",
        "request": {"mode": "replace", "action": "import_eeg_data", "changes": {}},
        "message": None,
    }
    assert prompt_proposal_from_metadata(_metadata(nested)) is None
    assert example_decision_name(_metadata(nested)) is None


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
def test_rag_policy_rejects_retired_actions(action):
    assert prompt_proposal_from_metadata(_metadata(_proposal(action))) is None


@pytest.mark.parametrize(
    "proposal",
    [
        _proposal("apply_bandpass_filter", {"low_freq": 4}, text="4 Hz"),
        {**_proposal("import_eeg_data"), "extra": 1},
        {"command": "import_eeg_data", "parameters": {}},
        [
            _proposal("import_eeg_data"),
            _proposal("switch_panel", {"panel_name": "dataset"}),
        ],
        _proposal("resample_data", {"rate": True}, text="True"),
        _proposal("resample_data", {"rate": float("nan")}, text="nan"),
    ],
)
def test_rag_policy_rejects_malformed_or_schema_invalid_proposals(proposal):
    metadata = _metadata(proposal, "4 Hz")
    assert prompt_proposal_from_metadata(metadata) is None
    assert not is_primary_workflow_example(metadata)
    assert example_decision_name(metadata) is None


@pytest.mark.parametrize("decision", ["reply", "clarify"])
def test_response_example_uses_non_executing_contract(decision):
    proposal = {
        "decision": decision,
        "mode": None,
        "action": None,
        "changes": {},
        "message": "No action.",
    }
    assert prompt_proposal_from_metadata(_metadata(proposal)) == proposal
    assert example_decision_name(_metadata(proposal)) == MODEL_RESPONSE_TOOL_NAME
    assert MODEL_RESPONSE_TOOL_NAME not in AGENT_ACTION_CONTRACTS.model_tool_names()


@pytest.mark.parametrize("message", [None, "", " "])
def test_empty_response_message_is_rejected(message):
    assert (
        prompt_proposal_from_metadata(
            _metadata(
                {
                    "decision": "reply",
                    "mode": None,
                    "action": None,
                    "changes": {},
                    "message": message,
                }
            )
        )
        is None
    )


@pytest.mark.parametrize("mode", ["update_pending", "cancel_pending"])
def test_standalone_example_cannot_invent_request_history(mode):
    proposal = _proposal("import_eeg_data")
    proposal["mode"] = mode
    if mode == "cancel_pending":
        proposal.update(decision="reply", message="Cancelled.")
        proposal["action"] = None
    assert prompt_proposal_from_metadata(_metadata(proposal)) is None


def test_partial_clarification_is_action_scoped_without_becoming_executable():
    proposal = _proposal("apply_bandpass_filter", {"low_freq": 7}, text="Lower 7 Hz")
    proposal.update(decision="clarify", message="What upper cutoff?")
    metadata = _metadata(proposal, "Lower 7 Hz")
    assert prompt_proposal_from_metadata(metadata) == proposal
    assert example_decision_name(metadata) == "apply_bandpass_filter"
    assert (
        CommandParser.parse_product(metadata["proposal"]).status
        is ToolEnvelopeStatus.NO_TOOL
    )


def _two_turn_metadata(*, correction=False):
    prior = _proposal(
        "apply_bandpass_filter", {"low_freq": 5}, text="Lower cutoff 5 Hz for bandpass."
    )
    prior.update(decision="clarify", message="What upper cutoff should I use?")
    text = (
        "Revise the lower cutoff to 9 Hz."
        if correction
        else "Set the upper cutoff to 42 Hz."
    )
    current = _proposal(
        "apply_bandpass_filter",
        {"low_freq" if correction else "high_freq": 9 if correction else 42},
        text=text,
    )
    current["mode"] = "update_pending"
    for change in current["changes"].values():
        change["source_turn"] = "U2"
    if correction:
        current.update(decision="clarify", message="What upper cutoff should I use?")
    return {
        "source_text": text,
        "proposal": current,
        "prior_turn": {
            "input": "Lower cutoff 5 Hz for bandpass.",
            "expected_proposal": prior,
        },
    }


@pytest.mark.parametrize("correction", [False, True])
def test_contextual_example_reuses_prior_sources_but_proposes_only_current_changes(
    correction,
):
    metadata = _two_turn_metadata(correction=correction)
    assert prompt_proposal_from_metadata(metadata) == metadata["proposal"]
    assert example_decision_name(metadata) == "apply_bandpass_filter"
    assert (
        example_search_text(metadata)
        == metadata["prior_turn"]["input"] + "\n" + metadata["source_text"]
    )
    rendered = prompt_example_from_metadata(metadata)
    assert list(rendered) == ["input", "context", "expected_proposal"]
    assert rendered["input"] == metadata["source_text"]
    assert "prior_turn" not in rendered
    assert rendered["context"]["current_user"] == {
        "id": "U2",
        "text": metadata["source_text"],
    }
    pending = rendered["context"]["pending_request"]
    assert pending["parameters"]["low_freq"]["value"] == 5
    assert pending["parameters"]["low_freq"]["source_turn"] == "U1"
    assert pending["user_sources"] == {"U1": metadata["prior_turn"]["input"]}


@pytest.mark.parametrize(
    "defect",
    [
        "prior_quote",
        "current_quote",
        "current_source",
        "prior_execute",
        "recursive",
        "action_change",
        "incomplete_execute",
    ],
)
def test_contextual_example_rejects_invalid_history_and_incomplete_execution(defect):
    metadata = _two_turn_metadata()
    prior = metadata["prior_turn"]
    proposal = metadata["proposal"]
    if defect == "prior_quote":
        prior["expected_proposal"]["changes"]["low_freq"]["quote"] = "Absent 5"
    elif defect == "current_quote":
        proposal["changes"]["high_freq"]["quote"] = "Absent 42"
    elif defect == "current_source":
        proposal["changes"]["high_freq"]["source_turn"] = "U3"
    elif defect == "prior_execute":
        prior["expected_proposal"].update(decision="execute", message=None)
    elif defect == "recursive":
        prior["prior_turn"] = prior.copy()
    elif defect == "action_change":
        proposal["action"] = "resample_data"
    else:
        proposal["changes"] = {}
    assert prompt_proposal_from_metadata(metadata) is None


@pytest.mark.parametrize(
    "source_turn,quote,value",
    [
        ("RAG1", "128 Hz", 128),
        ("U2", "128 Hz", 128),
        ("U1", "absent", 128),
        ("U1", "128 Hz", 64),
    ],
)
def test_example_rejects_fabricated_source_quote_or_numeric_value(
    source_turn, quote, value
):
    proposal = _proposal("resample_data")
    proposal["changes"]["rate"] = {
        "value": value,
        "source_turn": source_turn,
        "quote": quote,
    }
    assert prompt_proposal_from_metadata(_metadata(proposal, "128 Hz")) is None


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


def test_gold_set_exactly_covers_approved_actions_with_live_schemas_and_sources():
    items = json.loads(_GOLD_SET_PATH.read_text(encoding="utf-8"))
    covered = set()
    for item in items:
        assert set(item) - {"prior_turn"} == {
            "id",
            "input",
            "category",
            "expected_proposal",
        }
        metadata = _metadata(
            item["expected_proposal"], item["input"], item.get("prior_turn")
        )
        assert is_primary_workflow_example(metadata), item["id"]
        covered.add(example_decision_name(metadata))
        parsed = CommandParser.parse_product(json.dumps(item["expected_proposal"]))
        assert parsed.status in (ToolEnvelopeStatus.VALID, ToolEnvelopeStatus.NO_TOOL)
    assert covered == AGENT_ACTION_CONTRACTS.model_tool_names() | {
        MODEL_RESPONSE_TOOL_NAME
    }
    assert RAGConfig.gold_set_integrity_ok()


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


def test_missing_and_partial_examples_keep_known_actions_without_guessed_values():
    items = json.loads(_GOLD_SET_PATH.read_text(encoding="utf-8"))
    additions = {
        row["id"]: row
        for row in items
        if row["category"]
        in {"response_missing_parameter", "response_partial_parameter"}
    }
    expected = {
        "apply_bandpass_filter_missing_01": ("apply_bandpass_filter", {}),
        "apply_bandpass_filter_partial_low_01": (
            "apply_bandpass_filter",
            {"low_freq": 6},
        ),
        "apply_bandpass_filter_partial_high_01": (
            "apply_bandpass_filter",
            {"high_freq": 44},
        ),
        "apply_notch_filter_missing_01": ("apply_notch_filter", {}),
        "resample_data_missing_01": ("resample_data", {}),
        "set_reference_missing_01": ("set_reference", {}),
        "normalize_data_missing_01": ("normalize_data", {}),
    }
    assert set(additions) == set(expected)
    for example_id, (action, values) in expected.items():
        row = additions[example_id]
        proposal = row["expected_proposal"]
        metadata = _metadata(proposal, row["input"])
        assert prompt_proposal_from_metadata(metadata) == proposal
        assert proposal["decision"] == "clarify"
        assert proposal["mode"] == "new_request"
        assert example_decision_name(metadata) == action
        assert {
            key: change["value"] for key, change in proposal["changes"].items()
        } == values
        assert (
            CommandParser.parse_product(json.dumps(proposal)).status
            is ToolEnvelopeStatus.NO_TOOL
        )


def test_bundled_corpus_preserves_action_coverage_and_response_examples():
    items = json.loads(_GOLD_SET_PATH.read_text(encoding="utf-8"))
    counts = Counter(
        example_decision_name(
            _metadata(item["expected_proposal"], item["input"], item.get("prior_turn"))
        )
        for item in items
    )
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
def test_compound_requests_teach_a_choice_not_partial_execution(example_id):
    items = json.loads(_GOLD_SET_PATH.read_text(encoding="utf-8"))
    example = next(item for item in items if item["id"] == example_id)
    proposal = prompt_proposal_from_metadata(
        _metadata(example["expected_proposal"], example["input"])
    )
    assert proposal["decision"] == "clarify"
    assert {key: proposal[key] for key in ("mode", "action", "changes")} == {
        "mode": "new_request",
        "action": None,
        "changes": {},
    }
    assert "first" in proposal["message"] and "?" in proposal["message"]
    assert example["category"] == "response_compound_request"
