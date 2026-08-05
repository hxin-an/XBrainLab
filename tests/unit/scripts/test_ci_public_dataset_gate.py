from __future__ import annotations

import re
from pathlib import Path

from scripts.dev.handoff_gate_spec import HANDOFF_GATE_SPECS

ROOT = Path(__file__).resolve().parents[3]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_has_required_public_dataset_gate() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert re.search(r"poetry run\s+(?!--)", workflow) is None
    assert "public-dataset-gate:" in workflow
    assert "scripts/dev/fetch_public_eeg_fixtures.py --profile required-ci" in workflow
    assert (
        "scripts/dev/fetch_public_eeg_fixtures.py --profile required-ci --verify-only"
        in workflow
    )
    assert "scripts/dev/report_dataset_validation_matrix.py --strict" in workflow
    assert (
        "scripts/dev/report_data_interpretation_format_matrix.py --strict" in workflow
    )
    assert (
        "tests/integration/io/test_public_bids_fixture.py::"
        "test_public_mne_bids_import_apply_recipe_and_epoch" in workflow
    )
    assert (
        "tests/integration/io/test_public_bids_fixture.py::"
        "test_openneuro_p300_trial_type_excludes_missing_rows_and_imports"
        not in workflow
    )
    assert "Run public BIDS visible UI wizard format matrix" in workflow
    assert (
        "QT_QPA_PLATFORM=offscreen poetry run -- python -m "
        "scripts.dev.run_required_pytest_gate --result-json "
        "test-results/public-bids-visible-ui.json -- --capture=sys "
        "tests/integration/ui/test_data_import_wizard_format_matrix.py -q" in workflow
    )
    assert (
        "tests/integration/pipeline/test_public_cross_source_training_smoke.py"
        in workflow
    )
    assert workflow.count("scripts.dev.run_required_pytest_gate") == 2
    assert "test-results/required-public-io.json" in workflow
    contract = HANDOFF_GATE_SPECS["required-public-io"].pytest_attestation_contract()
    assert contract is not None
    for node in (item for item in contract[1] if item.startswith("tests/")):
        assert node in workflow
    assert "scripts/dev/run_public_cross_source_training_smoke.py" in workflow
    assert "--format json --strict" in workflow
    assert "data-interpretation-format-matrix.json" in workflow


def test_ci_public_fixture_cache_is_bounded_and_invalidated_by_manifest() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "path: tests/fixtures/data/public" in workflow
    assert "hashFiles('scripts/dev/fetch_public_eeg_fixtures.py')" in workflow
    assert ".github/workflows/ci.yml|pyproject.toml" in workflow


def test_ci_exposes_one_stable_fail_closed_merge_gate() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "fetch-depth: 0" not in workflow
    assert "fetch-depth: 2" in workflow
    assert "merge-gate:" in workflow
    assert "name: CI Merge Gate" in workflow
    assert "needs: [changes, docs-only, lint, test, public-dataset-gate]" in workflow
    assert "CHANGE_SCOPE_RESULT: ${{ needs.changes.result }}" in workflow
    assert "PRODUCT_CHANGED: ${{ needs.changes.outputs.product }}" in workflow
    assert '[[ "$LINT_RESULT" == "success" ]] || exit 1' in workflow
    assert '[[ "$TEST_RESULT" == "success" ]] || exit 1' in workflow
    assert '[[ "$PUBLIC_DATASET_RESULT" == "success" ]] || exit 1' in workflow
    assert '[[ "$DOCS_ONLY_RESULT" == "success" ]] || exit 1' in workflow
