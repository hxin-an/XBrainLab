"""Contracts for the non-frozen Assistant accuracy experiment corpora."""

import json
from pathlib import Path

import pytest

from scripts.dev.assistant_accuracy_case_packs import (
    DEVELOPMENT_CASE_COUNT,
    DIRECT_PARAMETER_FIELDS,
    HOLDOUT_CASE_COUNT,
    _load_cases,
    corpus_identity,
    load_development_cases,
    load_holdout_cases,
)

ROOT = Path(__file__).resolve().parents[3]


def _frozen_v8_case_count() -> int:
    paths = (
        ROOT / "XBrainLab" / "llm" / "rag" / "data" / "gold_set.json",
        ROOT / "scripts" / "dev" / "stable_assistant_challenge_cases.json",
        ROOT / "scripts" / "dev" / "stable_assistant_no_action_precision_cases.json",
        ROOT / "scripts" / "dev" / "stable_assistant_clarification_cases.json",
    )
    return sum(len(json.loads(path.read_text(encoding="utf-8"))) for path in paths)


def _frozen_single_turns() -> set[tuple[str, ...]]:
    paths = (
        ROOT / "XBrainLab" / "llm" / "rag" / "data" / "gold_set.json",
        ROOT / "scripts" / "dev" / "stable_assistant_challenge_cases.json",
        ROOT / "scripts" / "dev" / "stable_assistant_no_action_precision_cases.json",
        ROOT / "scripts" / "dev" / "stable_assistant_clarification_cases.json",
    )
    values: set[tuple[str, ...]] = set()
    for path in paths:
        for row in json.loads(path.read_text(encoding="utf-8")):
            if isinstance(row.get("input"), str):
                values.add((" ".join(row["input"].casefold().split()),))
            if isinstance(row.get("turns"), list):
                values.add(
                    tuple(" ".join(turn.casefold().split()) for turn in row["turns"])
                )
    return values


def test_experiment_case_packs_are_fixed_bilingual_and_separate_from_frozen_v8() -> (
    None
):
    development = load_development_cases()
    holdout = load_holdout_cases()
    assert _frozen_v8_case_count() == 81
    assert len(development) == DEVELOPMENT_CASE_COUNT == 48
    assert len(holdout) == HOLDOUT_CASE_COUNT == 32
    assert {case.language for case in development} == {"en", "zh"}
    assert {case.language for case in holdout} == {"en", "zh"}
    assert sum(case.language == "en" for case in development) == 24
    assert sum(case.language == "zh" for case in development) == 24
    assert sum(case.language == "en" for case in holdout) == 16
    assert sum(case.language == "zh" for case in holdout) == 16
    assert not {case.case_id for case in development}.intersection(
        case.case_id for case in holdout
    )
    assert not {case.normalized_turns for case in development}.intersection(
        case.normalized_turns for case in holdout
    )
    frozen_turns = _frozen_single_turns()
    assert not {case.normalized_turns for case in development}.intersection(
        frozen_turns
    )
    assert not {case.normalized_turns for case in holdout}.intersection(frozen_turns)
    development_single_turns = {
        (turn,) for case in development for turn in case.normalized_turns
    }
    holdout_single_turns = {
        (turn,) for case in holdout for turn in case.normalized_turns
    }
    assert not development_single_turns.intersection(frozen_turns)
    assert not holdout_single_turns.intersection(frozen_turns)


def test_every_turn_is_an_executable_boundary_contract() -> None:
    cases = (*load_development_cases(), *load_holdout_cases())

    for case in cases:
        for turn in case.turns:
            if turn.expected_boundary == "respond":
                assert turn.expected_tool is None
                assert turn.expected_parameters == {}
                assert turn.receipt is None
            elif turn.expected_boundary == "typed_receipt":
                assert turn.expected_tool in DIRECT_PARAMETER_FIELDS
                assert turn.receipt is not None
                assert turn.expected_parameters == turn.receipt.verified_values
                assert set(turn.receipt.missing_inputs).isdisjoint(
                    turn.receipt.verified_values
                )
            else:
                assert turn.expected_boundary == "verified_execute"
                assert turn.expected_tool in DIRECT_PARAMETER_FIELDS
                assert set(turn.expected_parameters) == set(
                    DIRECT_PARAMETER_FIELDS[turn.expected_tool]
                )
                assert turn.receipt is None
            if turn.publication_generation_advanced_before_turn:
                assert case.category == "stale_generation"
                assert turn.expected_boundary == "respond"


def test_trajectory_taxonomy_locks_receipt_and_zero_execution_lifecycles() -> None:
    cases = (*load_development_cases(), *load_holdout_cases())
    no_action_categories = {
        "ambiguous",
        "general",
        "multi_action",
        "negated",
        "out_of_stage",
    }
    for case in cases:
        boundaries = tuple(turn.expected_boundary for turn in case.turns)
        if case.category in no_action_categories:
            assert set(boundaries) == {"respond"}
        if case.category == "missing_parameter":
            assert boundaries[0] == "typed_receipt"
            assert boundaries[-1] == "verified_execute"
            assert case.turns[0].expected_tool == case.turns[-1].expected_tool
        if case.category == "generic_action_selection":
            assert boundaries[:2] == ("respond", "typed_receipt")
            assert boundaries[-1] == "verified_execute"
        if case.category == "partial_accumulation":
            assert boundaries[:2] == ("typed_receipt", "typed_receipt")
            assert boundaries[-1] == "verified_execute"
        if case.category in {
            "cancellation",
            "different_tool",
            "stale_generation",
            "unrelated",
        }:
            assert "typed_receipt" in boundaries
            assert "respond" in boundaries
        if case.category == "different_tool":
            clear_index = boundaries.index("respond")
            assert clear_index > boundaries.index("typed_receipt")
            assert all(
                boundary != "verified_execute"
                for boundary in boundaries[: clear_index + 1]
            )
        if case.category == "stale_generation":
            assert (
                sum(
                    turn.publication_generation_advanced_before_turn
                    for turn in case.turns
                )
                == 1
            )


def test_experiment_case_pack_identity_is_hashed_and_coverage_is_locked() -> None:
    identity = corpus_identity()

    assert identity["schema_version"] == "xbrainlab.assistant_accuracy_case_packs.v2"
    assert len(identity["development_cases_sha256"]) == 64
    assert len(identity["holdout_cases_sha256"]) == 64
    assert identity["development_case_count"] == DEVELOPMENT_CASE_COUNT
    assert identity["holdout_case_count"] == HOLDOUT_CASE_COUNT
    assert identity["development_category_counts"] == {
        "ambiguous": 6,
        "cancellation": 2,
        "different_tool": 1,
        "format_recovery": 2,
        "general": 5,
        "generic_action_selection": 3,
        "missing_parameter": 5,
        "multi_action": 6,
        "negated": 8,
        "out_of_stage": 6,
        "partial_accumulation": 2,
        "stale_generation": 1,
        "unrelated": 1,
    }
    assert identity["holdout_category_counts"] == {
        "ambiguous": 4,
        "cancellation": 2,
        "different_tool": 1,
        "format_recovery": 1,
        "general": 3,
        "generic_action_selection": 2,
        "missing_parameter": 5,
        "multi_action": 4,
        "negated": 4,
        "out_of_stage": 3,
        "partial_accumulation": 1,
        "stale_generation": 1,
        "unrelated": 1,
    }


def test_loader_rejects_schema_drift(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.json"
    malformed.write_text(
        json.dumps(
            [
                {
                    "id": "bad",
                    "category": "general",
                    "language": "en",
                    "workflow_stage": "empty",
                    "turns": [],
                    "unexpected": True,
                }
            ]
        ),
        encoding="utf-8",
    )

    try:
        _load_cases(malformed, expected_count=1)
    except ValueError as exc:
        assert "exact schema" in str(exc)
    else:
        raise AssertionError("Schema drift must fail closed.")


@pytest.mark.parametrize(
    ("category", "turns", "message"),
    (
        (
            "general",
            [
                {
                    "user_input": "What can this do?",
                    "publication_generation_advanced_before_turn": False,
                    "expected_boundary": "respond",
                    "expected_tool": "resample_data",
                    "expected_parameters": {},
                    "receipt": None,
                }
            ],
            "zero execution authority",
        ),
        (
            "format_recovery",
            [
                {
                    "user_input": "Resample at 128 Hz.",
                    "publication_generation_advanced_before_turn": False,
                    "expected_boundary": "verified_execute",
                    "expected_tool": "apply_bandpass_filter",
                    "expected_parameters": {"low_freq": 1},
                    "receipt": None,
                }
            ],
            "direct parameter fields",
        ),
        (
            "general",
            [
                {
                    "user_input": "What can this do?",
                    "publication_generation_advanced_before_turn": True,
                    "expected_boundary": "respond",
                    "expected_tool": None,
                    "expected_parameters": {},
                    "receipt": None,
                }
            ],
            "invalid turn values",
        ),
        (
            "generic_action_selection",
            [
                {
                    "user_input": "Filter this EEG.",
                    "publication_generation_advanced_before_turn": False,
                    "expected_boundary": "respond",
                    "expected_tool": None,
                    "expected_parameters": {},
                    "receipt": None,
                },
                {
                    "user_input": "Band-pass.",
                    "publication_generation_advanced_before_turn": False,
                    "expected_boundary": "typed_receipt",
                    "expected_tool": "apply_bandpass_filter",
                    "expected_parameters": {},
                    "receipt": {
                        "missing_inputs": ["low_freq", "high_freq"],
                        "verified_values": {},
                    },
                },
            ],
            "invalid admission order",
        ),
    ),
)
def test_loader_rejects_boundary_authority_and_step_drift(
    tmp_path: Path,
    category: str,
    turns: list[dict[str, object]],
    message: str,
) -> None:
    malformed = tmp_path / "trajectory.json"
    malformed.write_text(
        json.dumps(
            [
                {
                    "id": "bad",
                    "category": category,
                    "language": "en",
                    "workflow_stage": "data_loaded",
                    "turns": turns,
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        _load_cases(malformed, expected_count=1)
