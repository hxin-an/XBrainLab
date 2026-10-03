"""Pure, complete-TEST paired family bootstrap; never runs or rescales a model."""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from scripts.dev.assistant_experiment_config import TEST_ABLATIONS

_FAMILIES = {"Action": 36, "Clarification": 12, "No-call": 18}
_REPEATS = (0, 1, 2)
_DRAWS = 10_000
_SEED = 0


def paired_family_analysis(
    rows: list[dict], *, repeats: tuple[int, ...] = _REPEATS
) -> dict:
    """Estimate three-category macro accuracy and paired Full-minus-off intervals.

    Each family is one cluster: its two variants, declared repeats and four
    conditions travel together. Resampling is with replacement within each
    decision category. Repeats are not treated as independent new questions.
    The caller owns source/scorer/capture validation; this function additionally
    rejects incomplete, unverified or inconsistent scored TEST matrices.
    """
    if (
        type(repeats) is not tuple
        or any(type(repeat) is not int for repeat in repeats)
        or repeats not in ((0,), _REPEATS)
    ):
        raise ValueError("Unsupported declared TEST repeat policy")
    expected_count = 132 * len(TEST_ABLATIONS) * len(repeats)
    if not isinstance(rows, list) or len(rows) != expected_count:
        raise ValueError("TEST statistics require the complete declared matrix")
    matrix, case_identity, family_category = {}, {}, {}
    family_cases = defaultdict(set)
    for row in rows:
        if not isinstance(row, dict) or (
            row.get("split") != "TEST"
            or row.get("evidence_status") != "verified"
            or row.get("case_recorded") is not True
            or row.get("decision_valid") is not True
            or type(row.get("final")) is not bool
        ):
            raise ValueError("TEST statistics require verified recorded decisions")
        case, family, decision, repeat, ablation = (
            row.get(key)
            for key in ("case_id", "family_id", "decision", "repeat", "ablation")
        )
        if (
            any(
                not isinstance(value, str) or not value.strip()
                for value in (case, family)
            )
            or not isinstance(decision, str)
            or decision not in _FAMILIES
            or type(repeat) is not int
            or repeat not in repeats
            or not isinstance(ablation, str)
            or ablation not in TEST_ABLATIONS
        ):
            raise ValueError("Invalid TEST case/family/category/repeat/ablation")
        identity = (family, decision)
        if case_identity.setdefault(case, identity) != identity:
            raise ValueError("Conflicting case family or decision category")
        if family_category.setdefault(family, decision) != decision:
            raise ValueError("Conflicting categories within a TEST family")
        key = (case, repeat, ablation)
        if key in matrix:
            raise ValueError("Duplicate TEST case/repeat/ablation")
        matrix[key] = row["final"]
        family_cases[family].add(case)
    if len(case_identity) != 132 or any(
        len(cases) != 2 for cases in family_cases.values()
    ):
        raise ValueError("TEST requires 132 cases in two-variant families")
    grouped = {
        decision: sorted(
            family
            for family, category in family_category.items()
            if category == decision
        )
        for decision in _FAMILIES
    }
    if any(len(grouped[decision]) != count for decision, count in _FAMILIES.items()):
        raise ValueError("TEST requires 36/12/18 families by decision category")
    expected = {
        (case, repeat, ablation)
        for case in case_identity
        for repeat in repeats
        for ablation in TEST_ABLATIONS
    }
    if matrix.keys() != expected:
        raise ValueError("Missing TEST case/repeat/ablation measurements")

    rng = np.random.default_rng(_SEED)
    macro = np.zeros(len(TEST_ABLATIONS))
    bootstrap = np.zeros((_DRAWS, len(TEST_ABLATIONS)))
    category_scores = {}
    for decision, families in grouped.items():
        # N families x four conditions; keep every declared repeat in its cluster.
        values = np.array(
            [
                [
                    np.mean(
                        [
                            matrix[(case, repeat, ablation)]
                            for case in sorted(family_cases[family])
                            for repeat in repeats
                        ]
                    )
                    for ablation in TEST_ABLATIONS
                ]
                for family in families
            ]
        )
        category_scores[decision] = values.mean(axis=0)
        macro += category_scores[decision] / len(_FAMILIES)
        indices = rng.integers(0, len(families), size=(_DRAWS, len(families)))
        bootstrap += values[indices].mean(axis=1) / len(_FAMILIES)

    def interval(estimate, samples):
        return {
            "estimate": float(estimate),
            "ci95": np.quantile(samples, [0.025, 0.975], method="linear").tolist(),
        }

    return {
        "schema": "xbrainlab.assistant_test_paired_family_analysis.v1",
        "method": {
            "name": "stratified-paired-family-percentile-bootstrap",
            "draws": _DRAWS,
            "seed": _SEED,
            "rng": type(rng.bit_generator).__name__,
            "quantile_method": "linear",
            "confidence_level": 0.95,
            "paired_unit": "family including all variants, repeats and conditions",
        },
        "population": {
            "cases": 132,
            "families_by_category": dict(_FAMILIES),
            "variants_per_family": 2,
            "repeats": list(repeats),
            "measurements": len(rows),
        },
        "conditions": {
            ablation: {
                **interval(macro[index], bootstrap[:, index]),
                "category_accuracy": {
                    decision: float(scores[index])
                    for decision, scores in category_scores.items()
                },
            }
            for index, ablation in enumerate(TEST_ABLATIONS)
        },
        "full_minus_ablation": {
            ablation: interval(
                macro[0] - macro[index], bootstrap[:, 0] - bootstrap[:, index]
            )
            for index, ablation in enumerate(TEST_ABLATIONS)
            if ablation != "full"
        },
        "always_respond_reference": {
            "macro": 2 / 3,
            "category_accuracy": {"Action": 0.0, "Clarification": 1.0, "No-call": 1.0},
        },
        "limitations": [
            "Intervals are conditional on the bank's task coverage and family sampling assumptions, not all real users.",
            "Three repeats measure execution variability on the same questions, not three independent banks."
            if repeats == _REPEATS
            else "Single repeat: intervals reflect family sampling, not repeated-execution variability.",
            "Intervals are pointwise, not simultaneous multiple-comparison significance claims; no p-values are computed.",
        ],
    }
