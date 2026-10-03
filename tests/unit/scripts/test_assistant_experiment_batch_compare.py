"""Whole batches compare saved evidence, not inferred or re-scored answers."""

import json

import pytest

from tests.unit.scripts.test_assistant_experiment_compare import fixture, save


def batch(root, entries, *, reference=False):
    save(
        root / "manifest.json",
        {
            "schema": "xbrainlab.assistant_experiment_"
            + ("reference" if reference else "batch")
            + ".v1",
            "runs": entries,
        },
    )
    return root


def entry(run="dev/round-01", **kwargs):
    return {
        "scope": "stages/dev/round-01",
        "run": run,
        "expected_cases": 1,
        "status": "completed",
        "exit_code": 0,
        **kwargs,
    }


def test_batch_comparison_emits_html_and_preserves_evidence(tmp_path):
    from scripts.dev.assistant_experiment_batch_compare import write_batch_comparison

    a, b = tmp_path / "a", tmp_path / "b"
    for root in (a, b):
        fixture(root / "dev/round-01", [[("resample", {"sfreq": 64}, True)]])
        batch(root, [entry()])
    result = write_batch_comparison(a, b, tmp_path / "comparison")
    assert result["planned_union"] == 1
    assert result["summary"]["final"]["correctness"]["both_right"] == 1
    assert result["inputs"]["first_input_equal"]["equal"] == 1
    assert result["classification"] == "same_config_reproduction"
    assert (tmp_path / "comparison/index.html").is_file()
    assert json.loads((tmp_path / "comparison/comparison.json").read_text())[
        "original_evidence_unchanged"
    ]


def test_reference_selects_repaired_candidate_without_double_counting(tmp_path):
    from scripts.dev.assistant_experiment_batch_compare import compare_batches

    old, repaired, new = tmp_path / "old", tmp_path / "repaired", tmp_path / "new"
    fixture(old, [[("resample", {"sfreq": 32}, False)]])
    fixture(repaired, [[("resample", {"sfreq": 64}, True)]])
    fixture(new / "dev/round-01", [[("resample", {"sfreq": 64}, True)]])
    batch(new, [entry()])
    ref = batch(
        tmp_path / "reference",
        [
            {
                "scope": "stages/dev/round-01",
                "expected_cases": 1,
                "selections": [{"run": "repaired", "conditions": ["phi4-rag-on"]}],
            }
        ],
        reference=True,
    )
    descriptor = json.loads((ref / "manifest.json").read_text())
    save(ref / "manifest.json", {**descriptor, "root": ".."})
    result = compare_batches(ref, new)
    assert result["planned_union"] == 1
    assert result["summary"]["final"]["correctness"]["both_right"] == 1


@pytest.mark.parametrize(
    "change", ["missing", "duplicate", "count", "running", "candidate", "tamper"]
)
def test_incomplete_or_misaligned_batch_never_claims_reproduction(tmp_path, change):
    from scripts.dev.assistant_experiment_batch_compare import compare_batches

    a, b = tmp_path / "a", tmp_path / "b"
    for root in (a, b):
        fixture(
            root / "dev/round-01",
            [[("resample", {"sfreq": 64}, True)]],
            candidate=2 if root == b and change == "candidate" else 1,
        )
        entries = [entry()]
        if root == b:
            if change == "missing":
                entries = []
            if change == "duplicate":
                entries *= 2
            if change == "count":
                entries[0]["expected_cases"] = 2
            if change == "running":
                entries[0]["status"] = "running"
            if change == "tamper":
                next(
                    (root / "dev/round-01/raw/cases").glob("*/result.json")
                ).write_text("{}")
        batch(root, entries)
    result = compare_batches(a, b)
    assert result["classification"] == "incompatible_or_unknown"
    assert result["planned_union"] >= 1


def test_output_cannot_overwrite_selected_evidence(tmp_path):
    from scripts.dev.assistant_experiment_batch_compare import write_batch_comparison

    root = tmp_path / "a"
    fixture(root / "dev/round-01", [[("resample", {"sfreq": 64}, True)]])
    batch(root, [entry()])
    with pytest.raises(ValueError, match="outside"):
        write_batch_comparison(root, root, root / "dev/round-01/comparison")


def test_manifest_path_escape_rejected(tmp_path):
    from scripts.dev.assistant_experiment_batch_compare import compare_batches

    a = batch(tmp_path / "a", [entry("../outside")])
    with pytest.raises(ValueError, match="outside"):
        compare_batches(a, a)


def test_runtime_migration_keeps_decision_agreement_but_not_score_equivalence(tmp_path):
    from scripts.dev.assistant_experiment_batch_compare import compare_batches

    a, b = tmp_path / "a", tmp_path / "b"
    for root, head in ((a, "a" * 40), (b, "b" * 40)):
        fixture(root / "dev/round-01", [[("resample", {"sfreq": 64}, True)]], head=head)
        batch(root, [entry()])
    result = compare_batches(a, b)
    assert result["classification"] == "incompatible_or_unknown"
    assert result["summary"]["final"]["correctness"]["unavailable"] == 1
    assert result["summary"]["final"]["tool_parameters_equal"]["rate"] == 1
    assert result["inputs"]["first_input_equal"]["equal"] == 1
    assert (
        result["cases"][0]["correctness_reason"] == "scorer_source_changed_or_unknown"
    )


def test_overlapping_reference_selection_is_unavailable_not_double_agreement(tmp_path):
    from scripts.dev.assistant_experiment_batch_compare import compare_batches

    root = tmp_path / "reference"
    fixture(root / "old", [[("resample", {"sfreq": 64}, True)]])
    batch(
        root,
        [
            {
                "scope": "stages/dev/round-01",
                "expected_cases": 2,
                "selections": [{"run": "old"}, {"run": "old"}],
            }
        ],
        reference=True,
    )
    result = compare_batches(root, root)
    assert result["classification"] == "incompatible_or_unknown"
    assert result["summary"]["final"]["tool_parameters_equal"]["denominator"] == 0
    assert result["cases"][0]["alignment_counts"] == [2, 2]


def test_comparison_cli_supports_batch_and_rejects_mixed_run_scope(tmp_path):
    from scripts.dev.assistant_experiment_compare import main

    root = tmp_path / "a"
    leaf = fixture(root / "dev/round-01", [[("resample", {"sfreq": 64}, True)]])
    batch(root, [entry()])
    assert main([str(root), str(root), "--output", str(tmp_path / "output")]) == 0
    assert (tmp_path / "output/index.html").is_file()
    with pytest.raises(SystemExit):
        main([str(root), str(leaf)])


@pytest.mark.parametrize(
    "field,value",
    [
        ("complete_selected_schedule", False),
        ("partial", True),
        ("session_cleanup_certified", False),
        ("session_cleanup_certified", None),
    ],
)
def test_report_failure_does_not_certify_reproduction_or_erase_raw_agreement(
    tmp_path, field, value
):
    from scripts.dev.assistant_experiment_batch_compare import compare_batches

    root = tmp_path / "a"
    fixture(root / "dev/round-01", [[("resample", {"sfreq": 64}, True)]])
    batch(root, [entry()])
    report_path = root / "dev/round-01/reports/20260929/report.json"
    report = json.loads(report_path.read_text())
    if value is None:
        report.pop(field)
    else:
        report[field] = value
    save(report_path, report)
    actual = compare_batches(root, root)
    assert actual["classification"] == "incompatible_or_unknown"
    assert actual["summary"]["final"]["tool_parameters_equal"]["rate"] == 1
    assert actual["scopes"]["stages/dev/round-01"]["runs"][0]["issues"]
