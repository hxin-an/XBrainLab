"""Fail-closed loading and validation for benchmark source contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0.0"
PARTITIONS = {
    "model_selection",
    "architecture_development",
    "architecture_validation",
    "sealed_human_test",
}
SCOPES = {"common_episode", "xbrainlab_full"}
STRATA = {
    "acquisition_orientation",
    "direct_preprocessing",
    "pipeline_configuration",
    "execution_result_navigation",
    "clarification_refusal_recovery",
}
LANGUAGES = {"en", "zh-TW"}
_ROOT_KEYS = {
    "schema_version",
    "benchmark_id",
    "description",
    "required_dimensions",
    "case_hashes",
    "cases",
}
_CASE_KEYS = {
    "schema_version",
    "case_id",
    "semantic_family_id",
    "partition",
    "scope",
    "stratum",
    "language",
    "paired_case_id",
    "provenance",
    "dimensions",
    "initial_state",
    "user_turns",
    "budget",
    "oracle",
    "mappings",
}
_ORACLE_KEYS = {
    "rubric_id",
    "milestones",
    "terminal_predicates",
    "minefields",
    "required_communication",
}
_PREDICATE_KEYS = {"predicate_id", "arguments", "parameter_contract_id"}
_MILESTONE_KEYS = _PREDICATE_KEYS | {
    "milestone_id",
    "required",
    "prerequisites",
}
_MINEFIELD_KEYS = _PREDICATE_KEYS | {"minefield_id", "critical"}


class BenchmarkContractError(ValueError):
    """A benchmark source cannot be interpreted without guessing."""


@dataclass(frozen=True)
class BenchmarkCorpus:
    """Validated benchmark inputs detached from the filesystem."""

    root: Path
    corpus: dict[str, Any]
    catalogs: dict[str, Any]
    split_manifest: dict[str, Any]

    @property
    def cases(self) -> tuple[dict[str, Any], ...]:
        return tuple(self.corpus["cases"])


def canonical_sha256(value: Any) -> str:
    """Hash one JSON value using a stable UTF-8 representation."""
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkContractError(f"Cannot load {path}: {exc}") from exc
    if type(value) is not dict:
        raise BenchmarkContractError(f"{path} must contain a JSON object")
    return value


def load_benchmark(root: Path | str) -> BenchmarkCorpus:
    """Load and validate the versioned corpus, catalogs, schemas, and split."""
    benchmark_root = Path(root)
    schemas = sorted((benchmark_root / "schemas").glob("*.schema.json"))
    expected = {
        "case.schema.json",
        "corpus.schema.json",
        "run.schema.json",
        "trace.schema.json",
        "verdict.schema.json",
    }
    if {path.name for path in schemas} != expected:
        raise BenchmarkContractError("Exactly five v1 schema documents are required")
    for schema_path in schemas:
        schema = _load_object(schema_path)
        if (
            schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema"
            or schema.get("additionalProperties") is not False
        ):
            raise BenchmarkContractError(f"Schema is not strict: {schema_path}")
    corpus = _load_object(benchmark_root / "corpus.json")
    catalogs = _load_object(benchmark_root / "catalogs.json")
    manifest = _load_object(benchmark_root / "split_manifest.json")
    validate_benchmark(corpus, catalogs, manifest)
    return BenchmarkCorpus(benchmark_root, corpus, catalogs, manifest)


def _require_keys(value: dict[str, Any], allowed: set[str], context: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise BenchmarkContractError(f"Unknown {context} fields: {sorted(unknown)}")


def _required_string(value: dict[str, Any], name: str) -> str:
    candidate = value.get(name)
    if not isinstance(candidate, str) or not candidate:
        raise BenchmarkContractError(f"{name} must be a non-empty string")
    return candidate


def _catalog_ids(catalogs: dict[str, Any], name: str) -> set[str]:
    values = catalogs.get(name)
    if not isinstance(values, list) or not all(
        isinstance(item, str) for item in values
    ):
        raise BenchmarkContractError(f"Catalog {name} must be a string list")
    return set(values)


def validate_benchmark(
    corpus: dict[str, Any],
    catalogs: dict[str, Any],
    split_manifest: dict[str, Any] | None = None,
) -> None:
    """Validate integrity, family locking, catalogs, bilingual pairs, and coverage."""
    _require_keys(corpus, _ROOT_KEYS, "corpus")
    if corpus.get("schema_version") != SCHEMA_VERSION:
        raise BenchmarkContractError("Unsupported corpus schema_version")
    cases = corpus.get("cases")
    hashes = corpus.get("case_hashes")
    if not isinstance(cases, list) or not cases or not isinstance(hashes, dict):
        raise BenchmarkContractError("Corpus cases and case_hashes are required")

    predicates = _catalog_ids(catalogs, "predicate_ids")
    rubrics = _catalog_ids(catalogs, "rubric_ids")
    parameter_contracts = _catalog_ids(catalogs, "parameter_contract_ids")
    dimensions = _catalog_ids(catalogs, "dimension_ids")
    family_contracts: dict[str, tuple[str, str, str]] = {}
    family_languages: dict[str, set[str]] = {}
    family_case_ids: dict[str, set[str]] = {}
    cases_by_id: dict[str, dict[str, Any]] = {}
    case_ids: set[str] = set()
    covered_strata: set[str] = set()
    covered_dimensions: set[str] = set()

    for case in cases:
        if type(case) is not dict:
            raise BenchmarkContractError("Every case must be an object")
        _require_keys(case, _CASE_KEYS, "case")
        case_id = _required_string(case, "case_id")
        family_id = _required_string(case, "semantic_family_id")
        partition = _required_string(case, "partition")
        scope = _required_string(case, "scope")
        stratum = _required_string(case, "stratum")
        language = _required_string(case, "language")
        if case_id in case_ids:
            raise BenchmarkContractError(f"Duplicate case_id: {case_id}")
        case_ids.add(case_id)
        cases_by_id[case_id] = case
        if partition not in PARTITIONS or scope not in SCOPES or stratum not in STRATA:
            raise BenchmarkContractError(
                f"Invalid partition/scope/stratum in {case_id}"
            )
        if language not in LANGUAGES:
            raise BenchmarkContractError(f"Invalid language in {case_id}")
        contract = (partition, scope, stratum)
        if family_id in family_contracts and family_contracts[family_id] != contract:
            raise BenchmarkContractError(
                f"family {family_id} crosses partition/scope/stratum"
            )
        family_contracts[family_id] = contract
        family_languages.setdefault(family_id, set()).add(language)
        family_case_ids.setdefault(family_id, set()).add(case_id)
        covered_strata.add(stratum)
        case_dimensions = case.get("dimensions")
        if (
            not isinstance(case_dimensions, list)
            or not set(case_dimensions) <= dimensions
        ):
            raise BenchmarkContractError(f"Unknown dimension_id in {case_id}")
        covered_dimensions.update(case_dimensions)
        oracle = case.get("oracle")
        if type(oracle) is not dict:
            raise BenchmarkContractError(f"Missing oracle in {case_id}")
        _require_keys(oracle, _ORACLE_KEYS, "oracle")
        if oracle.get("rubric_id") not in rubrics:
            raise BenchmarkContractError(f"Unknown rubric_id in {case_id}")
        predicate_groups = (
            ("milestone", oracle.get("milestones", []), _MILESTONE_KEYS),
            (
                "terminal predicate",
                oracle.get("terminal_predicates", []),
                _PREDICATE_KEYS,
            ),
            ("minefield", oracle.get("minefields", []), _MINEFIELD_KEYS),
        )
        for label, group, allowed_keys in predicate_groups:
            if not isinstance(group, list):
                raise BenchmarkContractError(
                    f"Oracle predicate group invalid in {case_id}"
                )
            for predicate in group:
                if type(predicate) is not dict:
                    raise BenchmarkContractError(f"Invalid {label} in {case_id}")
                _require_keys(predicate, allowed_keys, f"{label} predicate")
                if predicate.get("predicate_id") not in predicates:
                    raise BenchmarkContractError(f"Unknown predicate_id in {case_id}")
                parameter_contract_id = predicate.get("parameter_contract_id")
                if (
                    parameter_contract_id is not None
                    and parameter_contract_id not in parameter_contracts
                ):
                    raise BenchmarkContractError(
                        f"Unknown parameter_contract_id in {case_id}"
                    )
        actual_hash = canonical_sha256(case)
        if hashes.get(case_id) != actual_hash:
            raise BenchmarkContractError(f"Case hash mismatch: {case_id}")

    if set(family_contracts) != set(family_languages):
        raise BenchmarkContractError("Family inventory is inconsistent")
    for family_id, languages in family_languages.items():
        if languages != LANGUAGES:
            raise BenchmarkContractError(f"Family {family_id} lacks a bilingual pair")
        if len(family_case_ids[family_id]) != len(LANGUAGES):
            raise BenchmarkContractError(
                f"Family {family_id} must have exactly one case per language"
            )
    for case_id, case in cases_by_id.items():
        paired_case_id = _required_string(case, "paired_case_id")
        paired = cases_by_id.get(paired_case_id)
        if (
            paired is None
            or paired.get("paired_case_id") != case_id
            or paired.get("semantic_family_id") != case.get("semantic_family_id")
            or paired.get("language") == case.get("language")
        ):
            raise BenchmarkContractError(f"Invalid bilingual pair for {case_id}")
    if covered_strata != STRATA:
        raise BenchmarkContractError("Corpus does not cover all macro strata")
    required = set(corpus.get("required_dimensions", []))
    if not required <= dimensions or not required <= covered_dimensions:
        raise BenchmarkContractError("Corpus required dimension coverage is incomplete")
    if set(hashes) != case_ids:
        raise BenchmarkContractError("case_hashes inventory does not match case IDs")
    if split_manifest is not None:
        _validate_split_manifest(split_manifest, family_contracts)


def _validate_split_manifest(
    manifest: dict[str, Any], family_contracts: dict[str, tuple[str, str, str]]
) -> None:
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise BenchmarkContractError("Unsupported split manifest schema_version")
    assignments = manifest.get("family_partitions")
    if not isinstance(assignments, dict) or set(assignments) != set(family_contracts):
        raise BenchmarkContractError("Split manifest family inventory mismatch")
    for family_id, contract in family_contracts.items():
        if assignments.get(family_id) != contract[0]:
            raise BenchmarkContractError(
                f"Split manifest mismatch for family {family_id}"
            )
