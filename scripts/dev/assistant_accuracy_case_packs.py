"""Machine-loadable boundary-oracle corpora separate from frozen Stable-v8."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEVELOPMENT_CASES_PATH = (
    ROOT / "scripts" / "dev" / "assistant_accuracy_development_cases.json"
)
HOLDOUT_CASES_PATH = ROOT / "scripts" / "dev" / "assistant_accuracy_holdout_cases.json"
DEVELOPMENT_CASE_COUNT = 48
HOLDOUT_CASE_COUNT = 32
SCHEMA_VERSION = "xbrainlab.assistant_accuracy_case_packs.v4"

# Deliberately update these only alongside an approved corpus-baseline decision.
# They are not recomputed-and-written by a runner, so wording or expectation drift
# fails closed in development before it can change a finalist comparison.
PINNED_DEVELOPMENT_CASES_SHA256 = "13b5a4434781d7be89f6e5618395232e854376ac1020500b55d228cabb46be94"  # pragma: allowlist secret
PINNED_HOLDOUT_CASES_SHA256 = "4919e5db805e34851ec32eeea199915a453316d0d68ca46b214d7dda1f0eca55"  # pragma: allowlist secret
FROZEN_V8_BASELINE_SOURCE_SHA = (
    "f9b8595f2a0644d1caa57ed3f4aa3530825644a7"  # pragma: allowlist secret
)
FROZEN_V8_CASE_PATHS = {
    "positive": ROOT / "XBrainLab" / "llm" / "rag" / "data" / "gold_set.json",
    "challenge": ROOT / "scripts" / "dev" / "stable_assistant_challenge_cases.json",
    "precision": ROOT
    / "scripts"
    / "dev"
    / "stable_assistant_no_action_precision_cases.json",
    "clarification": ROOT
    / "scripts"
    / "dev"
    / "stable_assistant_clarification_cases.json",
}
PINNED_FROZEN_V8_CASES_SHA256 = {
    "positive": "a4311b63165c2f4fb1c68d88c1ed8c81ecb9ae3beb1760bf1c2e52cda57f31bc",  # pragma: allowlist secret
    "challenge": "df300230c11b0ca014b1320e20ec80f2529766d2cbb2d50cd38adbe78ba2405b",  # pragma: allowlist secret
    "precision": "1b9d03bf0eb6802313f69cff955dab8bc39058fccb58667a2903fbab8a3e16f6",  # pragma: allowlist secret
    "clarification": "de3bb8e1f41cd820ead690a1f9767ab7d47cf0142568c5dda8f25405a5a97087",  # pragma: allowlist secret
}

# This is intentionally a frozen experiment snapshot, not product runtime policy.
# Update it only through the approved L0 corpus-baseline decision. Full-product CI
# asserts exact registry and ToolSchemaValidator parity without making the static
# corpus loader import the product package or its heavy dependencies.
PINNED_DIRECT_PARAMETER_TOOLS = frozenset(
    {
        "apply_bandpass_filter",
        "apply_notch_filter",
        "resample_data",
        "set_reference",
        "normalize_data",
    }
)
PINNED_DIRECT_PARAMETER_SCHEMAS: dict[str, dict[str, Any]] = {
    "apply_bandpass_filter": {
        "type": "object",
        "properties": {
            "low_freq": {"type": "number"},
            "high_freq": {"type": "number"},
        },
        "required": ["low_freq", "high_freq"],
    },
    "apply_notch_filter": {
        "type": "object",
        "properties": {"freq": {"type": "number"}},
        "required": ["freq"],
    },
    "resample_data": {
        "type": "object",
        "properties": {"rate": {"type": "integer"}},
        "required": ["rate"],
    },
    "set_reference": {
        "type": "object",
        "properties": {"method": {"type": "string"}},
        "required": ["method"],
    },
    "normalize_data": {
        "type": "object",
        "properties": {
            "method": {"type": "string", "enum": ["z-score", "min-max"]},
        },
        "required": ["method"],
    },
}

_CATEGORIES = frozenset(
    {
        "ambiguous",
        "cancellation",
        "different_tool",
        "format_recovery",
        "general",
        "generic_action_selection",
        "missing_parameter",
        "multi_action",
        "negated",
        "out_of_stage",
        "partial_accumulation",
        "stale_generation",
        "unrelated",
    }
)
_BOUNDARIES = frozenset({"respond", "typed_receipt", "verified_execute"})
_WORKFLOW_STAGES = frozenset(
    {
        "empty",
        "data_loaded",
        "preprocessed",
        "epoch_ready",
        "dataset_ready",
        "training",
        "trained",
    }
)


def pinned_direct_parameter_schemas() -> dict[str, dict[str, Any]]:
    """Return a defensive copy of the frozen experiment schema snapshot.

    The snapshot only keeps the non-frozen corpus machine-loadable. It does
    not decide current product admission or runtime parameter policy.
    """
    return deepcopy(PINNED_DIRECT_PARAMETER_SCHEMAS)


def _required_direct_fields(tool_name: str) -> tuple[str, ...]:
    schema = PINNED_DIRECT_PARAMETER_SCHEMAS[tool_name]
    required = schema.get("required")
    if not isinstance(required, list) or not all(
        isinstance(field, str) for field in required
    ):
        raise RuntimeError(f"Direct tool {tool_name} lacks a valid required schema.")
    return tuple(required)


@dataclass(frozen=True, slots=True)
class ReceiptExpectation:
    """Static oracle expectation for a pending receipt after a turn."""

    missing_inputs: tuple[str, ...]
    verified_values: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AccuracyExperimentTurn:
    """One user message and its static composed-boundary expectation."""

    user_input: str
    publication_generation_advanced_before_turn: bool
    expected_boundary: str
    expected_tool: str | None
    expected_parameters: dict[str, Any]
    receipt: ReceiptExpectation | None


@dataclass(frozen=True, slots=True)
class AccuracyExperimentCase:
    """One non-frozen trajectory oracle, not an observed product outcome."""

    case_id: str
    category: str
    language: str
    workflow_stage: str
    turns: tuple[AccuracyExperimentTurn, ...]

    @property
    def normalized_turns(self) -> tuple[str, ...]:
        return tuple(
            " ".join(turn.user_input.casefold().split()) for turn in self.turns
        )


def _validate_direct_parameter_values(
    tool_name: str,
    values: dict[str, Any],
    *,
    complete: bool,
    case_id: str,
) -> None:
    """Validate only the bounded semantics represented by the pinned snapshot."""
    schema = PINNED_DIRECT_PARAMETER_SCHEMAS[tool_name]
    properties = schema["properties"]
    if complete:
        missing = [field for field in schema["required"] if field not in values]
        if missing:
            raise ValueError(
                f"Accuracy case {case_id} violates pinned experiment schema: "
                f"missing required parameter(s): {', '.join(missing)}"
            )
    unknown = sorted(set(values).difference(properties))
    if unknown:
        raise ValueError(
            f"Accuracy case {case_id} violates pinned experiment schema: "
            f"unknown parameter(s): {', '.join(unknown)}"
        )
    for name, value in values.items():
        property_schema = properties[name]
        enum_values = property_schema.get("enum")
        if isinstance(enum_values, list) and not _json_enum_matches(value, enum_values):
            raise ValueError(
                f"Accuracy case {case_id} violates pinned experiment schema: "
                f"{name} must be one of {enum_values}"
            )
        expected_type = property_schema.get("type")
        if isinstance(expected_type, str) and not _json_type_matches(
            value, expected_type
        ):
            raise ValueError(
                f"Accuracy case {case_id} violates pinned experiment schema: "
                f"{name} must be {expected_type}"
            )


def _json_type_matches(value: Any, expected_type: str) -> bool:
    """Match the JSON primitive semantics used by the pinned direct schemas."""
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return False


def _json_enum_matches(value: Any, enum_values: list[Any]) -> bool:
    """Preserve the product validator's case-insensitive string enum behavior."""
    if value in enum_values:
        return True
    if isinstance(value, str):
        lowered = value.lower()
        return any(
            isinstance(item, str) and item.lower() == lowered for item in enum_values
        )
    return False


def _parse_receipt(
    value: object,
    *,
    case_id: str,
    expected_tool: str,
    expected_parameters: dict[str, Any],
) -> ReceiptExpectation:
    if not isinstance(value, dict) or set(value) != {
        "missing_inputs",
        "verified_values",
    }:
        raise ValueError(f"Accuracy case {case_id} has invalid receipt schema.")
    missing = value["missing_inputs"]
    verified = value["verified_values"]
    fields = _required_direct_fields(expected_tool)
    if (
        not isinstance(missing, list)
        or not missing
        or len(set(missing)) != len(missing)
        or any(not isinstance(field, str) or field not in fields for field in missing)
        or not isinstance(verified, dict)
        or set(verified).difference(fields)
        or set(missing).intersection(verified)
        or set(missing).union(verified) != set(fields)
        or expected_parameters != verified
    ):
        raise ValueError(f"Accuracy case {case_id} has invalid receipt evidence.")
    _validate_direct_parameter_values(
        expected_tool,
        verified,
        complete=False,
        case_id=case_id,
    )
    return ReceiptExpectation(tuple(missing), dict(verified))


def _parse_turn(row: object, *, case_id: str, category: str) -> AccuracyExperimentTurn:
    required = {
        "user_input",
        "publication_generation_advanced_before_turn",
        "expected_boundary",
        "expected_tool",
        "expected_parameters",
        "receipt",
    }
    if not isinstance(row, dict) or set(row) != required:
        raise ValueError(f"Accuracy case {case_id} has invalid turn schema.")
    user_input = row["user_input"]
    advanced = row["publication_generation_advanced_before_turn"]
    boundary = row["expected_boundary"]
    expected_tool = row["expected_tool"]
    expected_parameters = row["expected_parameters"]
    receipt_value = row["receipt"]
    if (
        not isinstance(user_input, str)
        or not user_input.strip()
        or not isinstance(advanced, bool)
        or boundary not in _BOUNDARIES
        or not isinstance(expected_parameters, dict)
        or (
            expected_tool is not None
            and expected_tool not in PINNED_DIRECT_PARAMETER_TOOLS
        )
        or (advanced and category != "stale_generation")
    ):
        raise ValueError(f"Accuracy case {case_id} has invalid turn values.")
    if boundary == "respond":
        if (
            expected_tool is not None
            or expected_parameters
            or receipt_value is not None
        ):
            raise ValueError(
                f"Respond turn {case_id} must encode a no-action expectation."
            )
        return AccuracyExperimentTurn(
            user_input.strip(), advanced, boundary, None, {}, None
        )
    if not isinstance(expected_tool, str):
        raise ValueError(f"Action turn {case_id} must name one direct tool.")
    if boundary == "typed_receipt":
        receipt = _parse_receipt(
            receipt_value,
            case_id=case_id,
            expected_tool=expected_tool,
            expected_parameters=expected_parameters,
        )
        return AccuracyExperimentTurn(
            user_input.strip(),
            advanced,
            boundary,
            expected_tool,
            dict(expected_parameters),
            receipt,
        )
    if advanced or receipt_value is not None:
        raise ValueError(
            f"Execute turn {case_id} must be a fresh complete direct action."
        )
    _validate_direct_parameter_values(
        expected_tool,
        expected_parameters,
        complete=True,
        case_id=case_id,
    )
    return AccuracyExperimentTurn(
        user_input.strip(),
        advanced,
        boundary,
        expected_tool,
        dict(expected_parameters),
        None,
    )


def _validate_trajectory(case: AccuracyExperimentCase) -> None:
    boundaries = tuple(turn.expected_boundary for turn in case.turns)
    if case.category in {
        "ambiguous",
        "general",
        "multi_action",
        "negated",
        "out_of_stage",
    } and boundaries != ("respond",):
        raise ValueError(f"No-action case {case.case_id} must never gain authority.")
    if case.category == "missing_parameter":
        if (
            boundaries != ("typed_receipt", "verified_execute")
            or case.turns[0].expected_tool != case.turns[-1].expected_tool
        ):
            raise ValueError(
                f"Missing-parameter case {case.case_id} lacks same-tool recovery."
            )
    if case.category == "generic_action_selection":
        if (
            boundaries != ("respond", "typed_receipt", "verified_execute")
            or case.turns[1].expected_tool != case.turns[2].expected_tool
        ):
            raise ValueError(
                f"Generic selection case {case.case_id} has invalid admission order."
            )
    if case.category == "partial_accumulation":
        if boundaries != ("typed_receipt", "typed_receipt", "verified_execute"):
            raise ValueError(f"Partial case {case.case_id} lacks receipt accumulation.")
        first, second, final = case.turns[0], case.turns[1], case.turns[-1]
        if (
            first.expected_tool != second.expected_tool
            or second.expected_tool != final.expected_tool
            or not first.receipt
            or not second.receipt
            or not set(first.expected_parameters).issubset(second.expected_parameters)
            or not set(second.expected_parameters).issubset(final.expected_parameters)
        ):
            raise ValueError(
                f"Partial case {case.case_id} has invalid receipt accumulation."
            )
    if case.category == "format_recovery" and boundaries != ("verified_execute",):
        raise ValueError(
            f"Format case {case.case_id} must specify one complete action."
        )
    if case.category in {"cancellation", "unrelated"} and boundaries != (
        "typed_receipt",
        "respond",
    ):
        raise ValueError(f"Cancellation case {case.case_id} has invalid receipt clear.")
    if case.category == "different_tool":
        if boundaries != ("typed_receipt", "respond", "verified_execute"):
            raise ValueError(
                f"Different-tool case {case.case_id} executes stale authority."
            )
    if case.category == "stale_generation":
        advanced = [
            turn
            for turn in case.turns
            if turn.publication_generation_advanced_before_turn
        ]
        if (
            boundaries != ("typed_receipt", "respond")
            or len(advanced) != 1
            or advanced[0].expected_boundary != "respond"
        ):
            raise ValueError(f"Stale case {case.case_id} must clear before execution.")
    elif any(turn.publication_generation_advanced_before_turn for turn in case.turns):
        raise ValueError(
            f"Only stale cases may advance publication generation: {case.case_id}"
        )


def _load_cases(
    path: Path,
    *,
    expected_count: int,
    expected_digest: str | None = None,
) -> tuple[AccuracyExperimentCase, ...]:
    if expected_digest is not None and _digest(path) != expected_digest:
        raise ValueError(
            f"Accuracy experiment corpus digest drifted for {path.name}; "
            "update the pinned identity only through the approved baseline decision."
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not load accuracy experiment cases: {exc}") from exc
    if not isinstance(payload, list) or len(payload) != expected_count:
        raise ValueError(
            f"Accuracy experiment pack must contain exactly {expected_count} cases."
        )

    cases: list[AccuracyExperimentCase] = []
    seen_ids: set[str] = set()
    seen_turns: set[tuple[str, ...]] = set()
    required = {"id", "category", "language", "workflow_stage", "turns"}
    for row in payload:
        if not isinstance(row, dict) or set(row) != required:
            raise ValueError("Each accuracy experiment case must use the exact schema.")
        case_id = row["id"]
        category = row["category"]
        language = row["language"]
        workflow_stage = row["workflow_stage"]
        turns_value = row["turns"]
        if (
            not isinstance(case_id, str)
            or not case_id
            or case_id in seen_ids
            or category not in _CATEGORIES
            or language not in {"en", "zh"}
            or workflow_stage not in _WORKFLOW_STAGES
            or not isinstance(turns_value, list)
            or not turns_value
        ):
            raise ValueError(f"Accuracy case {case_id!r} has invalid taxonomy.")
        case = AccuracyExperimentCase(
            case_id=case_id,
            category=category,
            language=language,
            workflow_stage=workflow_stage,
            turns=tuple(
                _parse_turn(turn, case_id=case_id, category=category)
                for turn in turns_value
            ),
        )
        if case.normalized_turns in seen_turns:
            raise ValueError(f"Duplicate accuracy trajectory: {case_id!r}")
        _validate_trajectory(case)
        seen_ids.add(case_id)
        seen_turns.add(case.normalized_turns)
        cases.append(case)
    return tuple(cases)


def load_development_cases() -> tuple[AccuracyExperimentCase, ...]:
    """Load the visible pre-registered development corpus."""
    return _load_cases(
        DEVELOPMENT_CASES_PATH,
        expected_count=DEVELOPMENT_CASE_COUNT,
        expected_digest=PINNED_DEVELOPMENT_CASES_SHA256,
    )


def load_holdout_cases() -> tuple[AccuracyExperimentCase, ...]:
    """Load the process-blinded, finalist-only tracked holdout corpus."""
    return _load_cases(
        HOLDOUT_CASES_PATH,
        expected_count=HOLDOUT_CASE_COUNT,
        expected_digest=PINNED_HOLDOUT_CASES_SHA256,
    )


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _category_counts(cases: tuple[AccuracyExperimentCase, ...]) -> dict[str, int]:
    return dict(sorted(Counter(case.category for case in cases).items()))


def frozen_v8_identity() -> dict[str, object]:
    """Verify the historical frozen corpus rather than silently accepting drift.

    ``source_sha`` identifies the historical preflight source from which the
    frozen corpus claim derives. It is provenance metadata, not the current
    branch identity and not a claim that this module has run that evaluation.
    """
    digests = {name: _digest(path) for name, path in FROZEN_V8_CASE_PATHS.items()}
    if digests != PINNED_FROZEN_V8_CASES_SHA256:
        raise ValueError(
            "Frozen Stable-v8 corpus digest drifted; update the pinned identity "
            "only through an approved frozen-baseline decision."
        )
    return {
        "source_sha": FROZEN_V8_BASELINE_SOURCE_SHA,
        "case_sha256": dict(digests),
    }


def corpus_identity() -> dict[str, object]:
    """Return static oracle identity; this does not score or execute a trajectory."""
    development = load_development_cases()
    holdout = load_holdout_cases()
    if {case.normalized_turns for case in development}.intersection(
        case.normalized_turns for case in holdout
    ):
        raise ValueError("Development and holdout corpora must not share trajectories.")
    return {
        "schema_version": SCHEMA_VERSION,
        "development_case_count": len(development),
        "holdout_case_count": len(holdout),
        "development_cases_sha256": _digest(DEVELOPMENT_CASES_PATH),
        "holdout_cases_sha256": _digest(HOLDOUT_CASES_PATH),
        "development_category_counts": _category_counts(development),
        "holdout_category_counts": _category_counts(holdout),
        "frozen_v8": frozen_v8_identity(),
    }
