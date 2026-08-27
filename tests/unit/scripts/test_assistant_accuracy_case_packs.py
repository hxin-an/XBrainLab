"""Contracts for the non-frozen Assistant accuracy experiment corpora."""

import json
from pathlib import Path

from scripts.dev.assistant_accuracy_case_packs import (
    DEVELOPMENT_CASE_COUNT,
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


def test_experiment_case_pack_identity_is_hashed_and_coverage_is_locked() -> None:
    identity = corpus_identity()

    assert identity["schema_version"] == "xbrainlab.assistant_accuracy_case_packs.v1"
    assert len(identity["development_cases_sha256"]) == 64
    assert len(identity["holdout_cases_sha256"]) == 64
    assert identity["development_case_count"] == DEVELOPMENT_CASE_COUNT
    assert identity["holdout_case_count"] == HOLDOUT_CASE_COUNT
    assert identity["development_category_counts"] == {
        "ambiguous": 6,
        "cancellation": 2,
        "different_tool": 1,
        "format_recovery": 2,
        "general": 6,
        "generic_action_selection": 3,
        "missing_parameter": 5,
        "multi_action": 6,
        "negated": 8,
        "out_of_stage": 6,
        "partial_accumulation": 2,
        "stale_generation": 1,
    }
    assert identity["holdout_category_counts"] == {
        "ambiguous": 4,
        "cancellation": 2,
        "different_tool": 1,
        "format_recovery": 1,
        "general": 4,
        "generic_action_selection": 2,
        "missing_parameter": 5,
        "multi_action": 4,
        "negated": 4,
        "out_of_stage": 3,
        "partial_accumulation": 1,
        "stale_generation": 1,
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
                    "turns": ["hello"],
                    "expected_disposition": "respond",
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
