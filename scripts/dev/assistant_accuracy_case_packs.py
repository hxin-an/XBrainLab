"""Versioned executable corpora kept separate from the frozen Stable-v8 suite."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
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
SCHEMA_VERSION = "xbrainlab.assistant_accuracy_case_packs.v2"

DIRECT_PARAMETER_FIELDS = {
    "apply_bandpass_filter": ("low_freq", "high_freq"),
    "apply_notch_filter": ("freq",),
    "resample_data": ("rate",),
    "set_reference": ("method",),
    "normalize_data": ("method",),
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


@dataclass(frozen=True, slots=True)
class ReceiptExpectation:
    """The only user-proven receipt state permitted after a turn."""

    missing_inputs: tuple[str, ...]
    verified_values: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AccuracyExperimentTurn:
    """One user message and its exact product-boundary expectation."""

    user_input: str
    publication_generation_advanced_before_turn: bool
    expected_boundary: str
    expected_tool: str | None
    expected_parameters: dict[str, Any]
    receipt: ReceiptExpectation | None


@dataclass(frozen=True, slots=True)
class AccuracyExperimentCase:
    """One non-frozen, product-outcome experiment trajectory."""

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
    fields = DIRECT_PARAMETER_FIELDS[tool_name]
    if set(values).difference(fields) or (complete and set(values) != set(fields)):
        raise ValueError(
            f"Accuracy case {case_id} has invalid direct parameter fields."
        )
    for _field, value in values.items():
        if tool_name in {
            "apply_bandpass_filter",
            "apply_notch_filter",
            "resample_data",
        } and (not isinstance(value, (int, float)) or isinstance(value, bool)):
            raise ValueError(f"Accuracy case {case_id} has invalid numeric parameter.")
        if tool_name in {"set_reference", "normalize_data"} and (
            not isinstance(value, str) or not value.strip()
        ):
            raise ValueError(f"Accuracy case {case_id} has invalid method parameter.")


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
    fields = DIRECT_PARAMETER_FIELDS[expected_tool]
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
        or (expected_tool is not None and expected_tool not in DIRECT_PARAMETER_FIELDS)
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
                f"Respond turn {case_id} must have zero execution authority."
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
    path: Path, *, expected_count: int
) -> tuple[AccuracyExperimentCase, ...]:
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
    return _load_cases(DEVELOPMENT_CASES_PATH, expected_count=DEVELOPMENT_CASE_COUNT)


def load_holdout_cases() -> tuple[AccuracyExperimentCase, ...]:
    """Load the separately named holdout corpus for the evidence custodian only."""
    return _load_cases(HOLDOUT_CASES_PATH, expected_count=HOLDOUT_CASE_COUNT)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _category_counts(cases: tuple[AccuracyExperimentCase, ...]) -> dict[str, int]:
    return dict(sorted(Counter(case.category for case in cases).items()))


def corpus_identity() -> dict[str, object]:
    """Return non-secret identities needed to bind experiment reports to these packs."""
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
    }
