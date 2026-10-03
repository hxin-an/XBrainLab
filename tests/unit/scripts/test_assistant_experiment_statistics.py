"""Synthetic complete TEST matrices protect paired family-level analysis."""

from copy import deepcopy

import numpy as np
import pytest

from scripts.dev.assistant_experiment_config import TEST_ABLATIONS
from scripts.dev.assistant_experiment_statistics import paired_family_analysis


def _rows(outcome=None):
    if outcome is None:
        outcome = lambda _decision, family, variant, repeat, _ablation: bool(  # noqa: E731
            (family + variant + repeat) % 2
        )
    return [
        {
            "split": "TEST",
            "case_id": f"TEST-{kind}-{family:02}-V{variant}",
            "family_id": f"TEST-{kind}-{family:02}",
            "decision": decision,
            "repeat": repeat,
            "ablation": ablation,
            "final": outcome(decision, family, variant, repeat, ablation),
            "first": False,
            "evidence_status": "verified",
            "case_recorded": True,
            "decision_valid": True,
        }
        for kind, decision, count in (
            ("A", "Action", 36),
            ("C", "Clarification", 12),
            ("N", "No-call", 18),
        )
        for family in range(count)
        for variant in range(2)
        for repeat in range(3)
        for ablation in TEST_ABLATIONS
    ]


def test_identical_conditions_have_exact_zero_paired_interval_with_varying_families():
    rows = _rows(lambda _d, family, _v, _r, _a: family % 2 == 0)
    original = deepcopy(rows)
    result = paired_family_analysis(rows)
    assert rows == original
    assert result["method"]["draws"] == 10_000
    assert result["method"]["seed"] == 0
    assert result["population"]["cases"] == 132
    assert result["population"]["families_by_category"] == {
        "Action": 36,
        "Clarification": 12,
        "No-call": 18,
    }
    for condition in result["conditions"].values():
        assert condition["estimate"] == 0.5
        assert condition["ci95"][0] < 0.5 < condition["ci95"][1]
    for difference in result["full_minus_ablation"].values():
        assert difference["estimate"] == 0.0
        assert difference["ci95"] == [0.0, 0.0]
    assert result["always_respond_reference"]["macro"] == 2 / 3


def test_macro_weights_categories_not_the_larger_action_population():
    result = paired_family_analysis(
        _rows(
            lambda decision, _f, _v, _r, ablation: decision == "Action"
            or ablation == "full"
        )
    )
    assert result["conditions"]["full"]["estimate"] == 1.0
    assert result["conditions"]["rag-off"]["estimate"] == pytest.approx(1 / 3)
    for difference in result["full_minus_ablation"].values():
        assert difference["estimate"] == pytest.approx(2 / 3)
        assert difference["ci95"] == pytest.approx([2 / 3, 2 / 3])


def test_all_variants_repeats_and_conditions_share_the_family_draw():
    # Each family has six measurements, with a category-specific off score;
    # reconstruct the frozen draws to catch case-level or unpaired resampling.
    rows = _rows(
        lambda _d, family, variant, repeat, ablation: (
            family % 3 == 0 or (ablation == "full" and variant == 0 and repeat == 0)
        )
    )
    result = paired_family_analysis(rows)
    rng = np.random.default_rng(0)
    full, off = np.zeros(10_000), np.zeros(10_000)
    for count in (36, 12, 18):
        group = np.array([float(family % 3 == 0) for family in range(count)])
        sample = rng.integers(0, count, size=(10_000, count))
        off += group[sample].mean(axis=1) / 3
        full += np.where(group == 1, 1, 1 / 6)[sample].mean(axis=1) / 3
    assert result["conditions"]["full"]["estimate"] == pytest.approx(4 / 9)
    assert result["conditions"]["rag-off"]["estimate"] == pytest.approx(1 / 3)
    assert result["full_minus_ablation"]["rag-off"]["ci95"] == pytest.approx(
        np.quantile(full - off, [0.025, 0.975], method="linear").tolist()
    )
    assert paired_family_analysis(list(reversed(rows))) == result


@pytest.mark.parametrize(
    "fault", ["missing", "extra", "duplicate", "missing_repeat", "missing_factor"]
)
def test_rejects_incomplete_or_nonunique_matrix(fault):
    rows = _rows()
    if fault == "missing":
        rows.pop()
    elif fault == "extra":
        rows.append(dict(rows[0], case_id="TEST-extra"))
    elif fault == "duplicate":
        rows[-1] = rows[0].copy()
    elif fault == "missing_repeat":
        rows = [row for row in rows if row["repeat"] != 2]
    else:
        rows = [row for row in rows if row["ablation"] != "retry-off"]
    with pytest.raises(ValueError):
        paired_family_analysis(rows)


@pytest.mark.parametrize(
    "field,value",
    [
        ("split", "VALID"),
        ("repeat", True),
        ("repeat", 3),
        ("ablation", "unknown"),
        ("final", None),
        ("final", 1),
        ("evidence_status", "missing"),
        ("case_recorded", False),
        ("decision_valid", False),
        ("family_id", ""),
        ("case_id", ""),
        ("family_id", "TEST-new-family"),
        ("decision", "Clarification"),
    ],
)
def test_rejects_invalid_evidence_or_conflicting_case_identity(field, value):
    rows = _rows()
    rows[0][field] = value
    with pytest.raises(ValueError):
        paired_family_analysis(rows)


def test_rejects_family_members_with_different_categories():
    rows = _rows()
    for row in rows:
        if row["case_id"] == "TEST-A-00-V1":
            row["decision"] = "No-call"
    with pytest.raises(ValueError, match="family"):
        paired_family_analysis(rows)


def test_rejects_wrong_family_size_even_with_complete_case_matrix():
    rows = _rows()
    for row in rows:
        if row["case_id"] == "TEST-A-00-V1":
            row["family_id"] = "TEST-A-01"
    with pytest.raises(ValueError, match="famil"):
        paired_family_analysis(rows)


def test_single_repeat_requires_explicit_policy_and_preserves_paired_family_draws():
    rows = _rows(lambda _d, family, _v, _r, _a: family % 2 == 0)
    single = [row for row in rows if row["repeat"] == 0]
    with pytest.raises(ValueError):
        paired_family_analysis(single)
    result = paired_family_analysis(single, repeats=(0,))
    assert result["population"]["measurements"] == 528
    assert result["population"]["repeats"] == [0]
    assert result["conditions"] == paired_family_analysis(rows)["conditions"]
    assert (
        result["full_minus_ablation"]
        == paired_family_analysis(rows)["full_minus_ablation"]
    )
    assert any("Single repeat" in item for item in result["limitations"])
    with pytest.raises(ValueError):
        paired_family_analysis(single[:-1], repeats=(0,))
    with pytest.raises(ValueError):
        paired_family_analysis(rows, repeats=(0,))


@pytest.mark.parametrize("repeats", [(), (1,), (0, 1), (False,), (0, 0), (0, 1, 2, 3)])
def test_bootstrap_rejects_unsupported_repeat_policy(repeats):
    with pytest.raises(ValueError):
        paired_family_analysis(_rows(), repeats=repeats)
