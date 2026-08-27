"""Versioned experiment corpora kept separate from the frozen Stable-v8 suite."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEVELOPMENT_CASES_PATH = (
    ROOT / "scripts" / "dev" / "assistant_accuracy_development_cases.json"
)
HOLDOUT_CASES_PATH = ROOT / "scripts" / "dev" / "assistant_accuracy_holdout_cases.json"
DEVELOPMENT_CASE_COUNT = 48
HOLDOUT_CASE_COUNT = 32
SCHEMA_VERSION = "xbrainlab.assistant_accuracy_case_packs.v1"

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
    }
)
_DISPOSITIONS = frozenset({"respond", "direct_action", "receipt_then_action"})
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
class AccuracyExperimentCase:
    """One non-frozen, product-outcome experiment trajectory."""

    case_id: str
    category: str
    language: str
    workflow_stage: str
    turns: tuple[str, ...]
    expected_disposition: str

    @property
    def normalized_turns(self) -> tuple[str, ...]:
        return tuple(" ".join(turn.casefold().split()) for turn in self.turns)


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
    required = {
        "id",
        "category",
        "language",
        "workflow_stage",
        "turns",
        "expected_disposition",
    }
    for row in payload:
        if not isinstance(row, dict) or set(row) != required:
            raise ValueError("Each accuracy experiment case must use the exact schema.")
        case_id = row["id"]
        category = row["category"]
        language = row["language"]
        workflow_stage = row["workflow_stage"]
        turns = row["turns"]
        disposition = row["expected_disposition"]
        if not isinstance(case_id, str) or not case_id or case_id in seen_ids:
            raise ValueError(f"Invalid or duplicate accuracy case id: {case_id!r}")
        if category not in _CATEGORIES or language not in {"en", "zh"}:
            raise ValueError(f"Accuracy case {case_id} has invalid taxonomy.")
        if workflow_stage not in _WORKFLOW_STAGES:
            raise ValueError(f"Accuracy case {case_id} has invalid workflow stage.")
        if (
            not isinstance(turns, list)
            or not turns
            or any(not isinstance(turn, str) or not turn.strip() for turn in turns)
            or disposition not in _DISPOSITIONS
        ):
            raise ValueError(f"Accuracy case {case_id} has invalid trajectory data.")
        case = AccuracyExperimentCase(
            case_id=case_id,
            category=category,
            language=language,
            workflow_stage=workflow_stage,
            turns=tuple(turn.strip() for turn in turns),
            expected_disposition=disposition,
        )
        if case.normalized_turns in seen_turns:
            raise ValueError(f"Duplicate accuracy trajectory: {case_id!r}")
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
