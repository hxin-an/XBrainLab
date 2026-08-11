from __future__ import annotations

import re
from pathlib import Path

from scripts.dev.fetch_public_eeg_fixtures import CI_REQUIRED_MANIFEST_SHA256

ROOT = Path(__file__).resolve().parents[3]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_has_required_public_dataset_gate() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert re.search(r"poetry run\s+(?!--)", workflow) is None
    assert "risk-gates:" in workflow
    assert '--owner "${{ matrix.owner }}"' in workflow
    assert "scripts/dev/run_validation_ci_owner.py run" in workflow
    assert "scripts/dev/fetch_public_eeg_fixtures.py" not in workflow
    assert "scripts/dev/report_dataset_validation_matrix.py" not in workflow
    assert "tests/integration/io/test_public_bids_fixture.py" not in workflow
    assert "scripts.dev.run_required_pytest_gate" not in workflow
    assert "scripts/dev/run_public_cross_source_training_smoke.py" not in workflow


def test_ci_public_fixture_cache_is_bounded_and_invalidated_by_manifest() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "path: tests/fixtures/data/public" in workflow
    assert f"public-eeg-required-ci-{CI_REQUIRED_MANIFEST_SHA256}" in workflow
    assert "hashFiles('scripts/dev/fetch_public_eeg_fixtures.py')" not in workflow
    assert "matrix.owner == 'public-data'" in workflow
    assert "needs.validation_plan.outputs.risk_owners" in workflow
