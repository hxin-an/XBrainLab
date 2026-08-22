from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from XBrainLab.experiments.agent_benchmark.contracts import (
    BenchmarkContractError,
    canonical_sha256,
    load_benchmark,
    validate_benchmark,
)

ROOT = Path(__file__).resolve().parents[4]
BENCHMARK_ROOT = ROOT / "benchmarks" / "xbrainlab_agent" / "v1"


def test_checked_in_pilot_is_family_locked_bilingual_and_covered() -> None:
    benchmark = load_benchmark(BENCHMARK_ROOT)

    assert len(benchmark.cases) == 24
    assert len({case["semantic_family_id"] for case in benchmark.cases}) == 12
    assert {case["partition"] for case in benchmark.cases} == {
        "architecture_development"
    }
    assert {case["stratum"] for case in benchmark.cases} == {
        "acquisition_orientation",
        "direct_preprocessing",
        "pipeline_configuration",
        "execution_result_navigation",
        "clarification_refusal_recovery",
    }

    variants: dict[str, set[str]] = {}
    for case in benchmark.cases:
        variants.setdefault(case["semantic_family_id"], set()).add(case["language"])
    assert all(languages == {"en", "zh-TW"} for languages in variants.values())


def test_schema_documents_are_strict_versioned_interfaces() -> None:
    schema_paths = sorted((BENCHMARK_ROOT / "schemas").glob("*.schema.json"))

    assert [path.name for path in schema_paths] == [
        "case.schema.json",
        "corpus.schema.json",
        "run.schema.json",
        "trace.schema.json",
        "verdict.schema.json",
    ]
    for path in schema_paths:
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"].startswith(
            "https://xbrainlab.org/schemas/agent-benchmark/v1/"
        )
        assert schema["additionalProperties"] is False


def test_validator_rejects_family_leakage_unknown_catalog_and_hash_mismatch() -> None:
    benchmark = load_benchmark(BENCHMARK_ROOT)
    corpus = deepcopy(benchmark.corpus)
    catalogs = deepcopy(benchmark.catalogs)

    leaked = deepcopy(corpus)
    leaked["cases"][1]["partition"] = "sealed_human_test"
    with pytest.raises(BenchmarkContractError, match=r"family.*partition"):
        validate_benchmark(leaked, catalogs)

    unknown = deepcopy(corpus)
    unknown["cases"][0]["oracle"]["terminal_predicates"][0]["predicate_id"] = (
        "unknown.predicate"
    )
    with pytest.raises(BenchmarkContractError, match="predicate_id"):
        validate_benchmark(unknown, catalogs)

    unknown_contract = deepcopy(corpus)
    unknown_contract["cases"][0]["oracle"]["terminal_predicates"][0][
        "parameter_contract_id"
    ] = "unknown.contract"
    with pytest.raises(BenchmarkContractError, match="parameter_contract_id"):
        validate_benchmark(unknown_contract, catalogs)

    unknown_semantic_field = deepcopy(corpus)
    unknown_semantic_field["cases"][0]["oracle"]["terminal_predicates"][0][
        "judge_hint"
    ] = "accept"
    with pytest.raises(BenchmarkContractError, match="predicate fields"):
        validate_benchmark(unknown_semantic_field, catalogs)

    mismatched = deepcopy(corpus)
    mismatched["case_hashes"][mismatched["cases"][0]["case_id"]] = "0" * 64
    with pytest.raises(BenchmarkContractError, match="hash"):
        validate_benchmark(mismatched, catalogs)


def test_validator_rejects_broken_bilingual_pair_even_with_valid_hash() -> None:
    benchmark = load_benchmark(BENCHMARK_ROOT)
    corpus = deepcopy(benchmark.corpus)
    case = corpus["cases"][0]
    case["paired_case_id"] = "pilot.orientation-summary.zh-tw.v1"
    corpus["case_hashes"][case["case_id"]] = canonical_sha256(case)

    with pytest.raises(BenchmarkContractError, match="bilingual pair"):
        validate_benchmark(corpus, benchmark.catalogs)


def test_canonical_hash_does_not_depend_on_mapping_order() -> None:
    assert canonical_sha256({"a": 1, "b": 2}) == canonical_sha256({"b": 2, "a": 1})
