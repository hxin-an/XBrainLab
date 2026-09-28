"""Protect the pre-candidate six-case freeze; never run a model here."""

import hashlib
import json
from collections import Counter

import pytest

from scripts.dev import run_stable_assistant_model_eval as runner

MANIFEST = (
    runner.ROOT / "scripts/dev/stable_assistant_english_generalization_cases_v1.json"
)
FROZEN_SHA256 = "74f24fe9d8e7c17db5ee2abdafdd41b42f2a2ce6d92ffb75487eb585b9835d2b"
CASES = json.loads(MANIFEST.read_text(encoding="utf-8"))["cases"]


def test_six_case_freeze_remains_separate_from_fixed_twenty():
    assert hashlib.sha256(MANIFEST.read_bytes()).hexdigest() == FROZEN_SHA256
    assert len(CASES) == len({row["id"] for row in CASES}) == 6
    assert Counter(row["category"] for row in CASES) == {
        "complete": 2,
        "missing_parameter": 2,
        "prohibition": 2,
    }
    fixed = runner.load_single_turn_cases()
    assert len(fixed) == 20
    assert not {row["input"] for row in CASES} & {case.user_input for case in fixed}
    missing = [row for row in CASES if row["category"] == "missing_parameter"]
    assert sum(bool(row["provided_parameters"]) for row in missing) == 1
    with pytest.raises(ValueError, match="manifest changed"):
        runner.load_single_turn_cases(MANIFEST)


@pytest.mark.parametrize("row", CASES, ids=lambda row: row["id"])
def test_frozen_oracle_matches_required_fields_and_current_input(row):
    tool = runner.target_tool_registry().get_tool(row["requested_tool"])
    assert tool is not None
    provided = row["provided_parameters"]
    assert set(tool.parameters["required"]) - set(provided) == set(
        row.get("missing_fields", [])
    )
    assert provided.keys() == row["parameter_evidence"].keys()
    for field, quote in row["parameter_evidence"].items():
        assert quote in row["input"]
        assert str(provided[field]) == quote
    assert row["semantic_criteria"]
    if row["category"] == "complete":
        case = runner.TargetEvalCase(
            row["id"],
            row["input"],
            row["workflow_stage"],
            row["tool_name"],
            row["parameters"],
        )
        response = json.dumps(
            {"tool_name": row["tool_name"], "parameters": row["parameters"]}
        )
        assert runner.score_model_response(
            case, response, runner.target_tool_registry()
        ).passed
        assert row["parameters"] == provided
    else:
        assert row["tool_name"] == "respond_to_user"
        assert row["parameters"] is None
