from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_has_required_public_dataset_gate() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

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
    assert "tests/integration/io/test_public_bids_fixture.py" in workflow
    assert "Run public BIDS visible UI wizard format matrix" in workflow
    assert (
        "QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys "
        "tests/integration/ui/test_data_import_wizard_format_matrix.py -q" in workflow
    )
    assert (
        "tests/integration/pipeline/test_public_cross_source_training_smoke.py"
        in workflow
    )
    assert "scripts/dev/run_public_cross_source_training_smoke.py" in workflow
    assert "--format json --strict" in workflow
    assert "data-interpretation-format-matrix.json" in workflow


def test_ci_public_fixture_cache_is_bounded_and_invalidated_by_manifest() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "path: tests/fixtures/data/public" in workflow
    assert "hashFiles('scripts/dev/fetch_public_eeg_fixtures.py')" in workflow
    assert ".github/workflows/ci.yml|pyproject.toml" in workflow
