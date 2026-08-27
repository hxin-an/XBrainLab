"""Contracts for the non-frozen Assistant accuracy experiment corpora."""

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from scripts.dev import assistant_accuracy_case_packs
from scripts.dev.assistant_accuracy_case_packs import (
    DEVELOPMENT_CASE_COUNT,
    FROZEN_V8_BASELINE_SOURCE_SHA,
    HOLDOUT_CASE_COUNT,
    PINNED_DEVELOPMENT_CASES_SHA256,
    PINNED_DIRECT_PARAMETER_SCHEMAS,
    PINNED_FROZEN_V8_CASES_SHA256,
    PINNED_HOLDOUT_CASES_SHA256,
    _load_cases,
    _validate_direct_parameter_values,
    corpus_identity,
    frozen_v8_identity,
    load_development_cases,
    load_holdout_cases,
    pinned_direct_parameter_schemas,
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


def test_every_turn_is_a_machine_loadable_boundary_oracle() -> None:
    cases = (*load_development_cases(), *load_holdout_cases())
    direct_schemas = pinned_direct_parameter_schemas()

    for case in cases:
        for turn in case.turns:
            if turn.expected_boundary == "respond":
                assert turn.expected_tool is None
                assert turn.expected_parameters == {}
                assert turn.receipt is None
            elif turn.expected_boundary == "typed_receipt":
                assert turn.expected_tool in direct_schemas
                assert turn.receipt is not None
                assert turn.expected_parameters == turn.receipt.verified_values
                assert set(turn.receipt.missing_inputs).isdisjoint(
                    turn.receipt.verified_values
                )
            else:
                assert turn.expected_boundary == "verified_execute"
                assert turn.expected_tool in direct_schemas
                assert set(turn.expected_parameters) == set(
                    direct_schemas[turn.expected_tool]["required"]
                )
                assert turn.receipt is None
            if turn.publication_generation_advanced_before_turn:
                assert case.category == "stale_generation"
                assert turn.expected_boundary == "respond"


def test_trajectory_taxonomy_locks_static_receipt_and_no_action_expectations() -> None:
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


def test_experiment_case_pack_identity_is_pinned_and_coverage_is_locked() -> None:
    identity = corpus_identity()

    assert identity["schema_version"] == "xbrainlab.assistant_accuracy_case_packs.v4"
    assert identity["development_cases_sha256"] == PINNED_DEVELOPMENT_CASES_SHA256
    assert identity["holdout_cases_sha256"] == PINNED_HOLDOUT_CASES_SHA256
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
    assert identity["frozen_v8"] == {
        "source_sha": FROZEN_V8_BASELINE_SOURCE_SHA,
        "case_sha256": PINNED_FROZEN_V8_CASES_SHA256,
    }
    assert frozen_v8_identity() == identity["frozen_v8"]


def test_oracle_uses_the_pinned_experiment_direct_tool_snapshot() -> None:
    schemas = pinned_direct_parameter_schemas()

    assert schemas["resample_data"]["properties"]["rate"]["type"] == "integer"
    assert schemas["normalize_data"]["properties"]["method"] == {
        "type": "string",
        "enum": ["z-score", "min-max"],
    }
    assert schemas["set_reference"]["properties"]["method"]["type"] == "string"


@pytest.fixture(scope="module")
def product_direct_parameter_schemas() -> dict[str, dict[str, Any]]:
    """Load real schemas only for full-product parity tests."""
    pytest.importorskip("torch", reason="full product schema parity requires torch")
    pytest.importorskip("mne", reason="full product schema parity requires mne")

    from XBrainLab.llm.agent.verifier import (
        DIRECT_PARAMETER_TOOLS,
    )
    from XBrainLab.llm.tools import get_all_tools

    registered = {
        tool.name: tool.parameters
        for tool in get_all_tools(mode="real")
        if tool.name in DIRECT_PARAMETER_TOOLS
    }
    assert frozenset(PINNED_DIRECT_PARAMETER_SCHEMAS) == DIRECT_PARAMETER_TOOLS
    return registered


def test_pinned_snapshot_matches_the_product_direct_tool_registry(
    product_direct_parameter_schemas: dict[str, dict[str, Any]],
) -> None:
    """The static snapshot must fail CI parity if the product schema changes."""
    assert product_direct_parameter_schemas == PINNED_DIRECT_PARAMETER_SCHEMAS


@pytest.mark.parametrize(
    ("tool_name", "parameters", "complete"),
    (
        ("resample_data", {"rate": 128}, True),
        ("resample_data", {}, True),
        ("resample_data", {"rate": 128, "unexpected": "value"}, True),
        ("resample_data", {"rate": 128.5}, True),
        ("normalize_data", {"method": "z-score"}, True),
        ("normalize_data", {"method": "Z-SCORE"}, True),
        ("normalize_data", {"method": "robust"}, True),
        ("set_reference", {"method": "average"}, True),
        ("set_reference", {"method": 7}, True),
        ("apply_bandpass_filter", {"low_freq": 1}, False),
    ),
)
def test_pinned_snapshot_validator_matches_product_schema_validation(
    tool_name: str,
    parameters: dict[str, object],
    complete: bool,
    product_direct_parameter_schemas: dict[str, dict[str, Any]],
) -> None:
    """Keep bounded snapshot semantics aligned without importing runtime on load."""
    pytest.importorskip("torch", reason="full product schema parity requires torch")
    pytest.importorskip("mne", reason="full product schema parity requires mne")

    from XBrainLab.llm.agent.verifier import ToolSchemaValidator

    product_schema = deepcopy(product_direct_parameter_schemas[tool_name])
    if not complete:
        product_schema["required"] = []
    product_result = ToolSchemaValidator({tool_name: product_schema}).validate(
        tool_name,
        parameters,
    )
    try:
        _validate_direct_parameter_values(
            tool_name,
            parameters,
            complete=complete,
            case_id="parity",
        )
    except ValueError:
        snapshot_is_valid = False
    else:
        snapshot_is_valid = True

    assert snapshot_is_valid is product_result.is_valid


def test_case_pack_module_loads_and_hashes_without_site_packages() -> None:
    """The static oracle must not need torch, MNE, or product-runtime imports."""
    result = subprocess.run(  # noqa: S603 - fixed local interpreter and source.
        [
            sys.executable,
            "-S",
            "-c",
            """
import sys

from scripts.dev.assistant_accuracy_case_packs import corpus_identity

identity = corpus_identity()
assert identity[\"development_case_count\"] == 48
assert identity[\"holdout_case_count\"] == 32
assert not any(
    module == root or module.startswith(root + \".\")
    for module in sys.modules
    for root in (\"torch\", \"mne\", \"XBrainLab\")
)
assert not any(\"site-packages\" in path for path in sys.path)
print(\"PASS\")
""",
        ],
        check=True,
        capture_output=True,
        cwd=ROOT,
        env={
            **os.environ,
            "MNE_DONTWRITE_HOME": "true",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": str(ROOT),
        },
        text=True,
        timeout=30,
    )

    assert result.stdout == "PASS\n"


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
            "no-action expectation",
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
            "violates pinned experiment schema",
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


@pytest.mark.parametrize(
    ("tool_name", "parameters"),
    (
        ("resample_data", {}),
        ("resample_data", {"rate": 128, "unexpected": "value"}),
        ("resample_data", {"rate": 128.5}),
        ("normalize_data", {"method": "robust"}),
        ("set_reference", {"method": 7}),
    ),
)
def test_loader_rejects_values_outside_the_pinned_experiment_schema(
    tmp_path: Path,
    tool_name: str,
    parameters: dict[str, object],
) -> None:
    malformed = tmp_path / "direct-schema.json"
    malformed.write_text(
        json.dumps(
            [
                {
                    "id": "bad",
                    "category": "format_recovery",
                    "language": "en",
                    "workflow_stage": "data_loaded",
                    "turns": [
                        {
                            "user_input": "Run the requested operation.",
                            "publication_generation_advanced_before_turn": False,
                            "expected_boundary": "verified_execute",
                            "expected_tool": tool_name,
                            "expected_parameters": parameters,
                            "receipt": None,
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="violates pinned experiment schema"):
        _load_cases(malformed, expected_count=1)


def test_pinned_development_digest_fails_closed_on_content_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    drifted = tmp_path / "development.json"
    source = assistant_accuracy_case_packs.DEVELOPMENT_CASES_PATH.read_text(
        encoding="utf-8"
    )
    drifted.write_text(source + "\n", encoding="utf-8")
    monkeypatch.setattr(
        assistant_accuracy_case_packs, "DEVELOPMENT_CASES_PATH", drifted
    )

    with pytest.raises(ValueError, match="corpus digest drifted"):
        load_development_cases()


def test_pinned_holdout_digest_fails_closed_on_content_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    drifted = tmp_path / "holdout.json"
    source = assistant_accuracy_case_packs.HOLDOUT_CASES_PATH.read_text(
        encoding="utf-8"
    )
    drifted.write_text(source + "\n", encoding="utf-8")
    monkeypatch.setattr(assistant_accuracy_case_packs, "HOLDOUT_CASES_PATH", drifted)

    with pytest.raises(ValueError, match="corpus digest drifted"):
        load_holdout_cases()


def test_pinned_frozen_v8_digest_fails_closed_on_content_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    drifted = tmp_path / "frozen.json"
    drifted.write_text("[]\n", encoding="utf-8")
    monkeypatch.setitem(
        assistant_accuracy_case_packs.FROZEN_V8_CASE_PATHS,
        "positive",
        drifted,
    )

    with pytest.raises(ValueError, match="Frozen Stable-v8 corpus digest drifted"):
        frozen_v8_identity()
