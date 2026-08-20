"""CI ownership contract for the human-like product walkthrough artifact."""

from pathlib import Path

import yaml

from scripts.dev.handoff_gate_spec import HANDOFF_GATE_SPECS

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
RETIRED_PYTEST_WRAPPER = (
    ROOT / "tests" / "integration" / "ui" / "test_product_walkthrough_artifact.py"
)


def test_human_like_walkthrough_has_one_parallel_ci_owner() -> None:
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    job = jobs["human-like-product"]

    assert job["needs"] == "changes"
    assert job["if"] == "needs.changes.outputs.product == 'true'"
    assert job["timeout-minutes"] == 15
    assert "scripts/dev/capture_human_like_product_walkthrough.py" in str(job)
    assert "build/dev-artifacts/human-like-product" in str(job)
    assert RETIRED_PYTEST_WRAPPER.exists() is False


def test_local_handoff_keeps_the_canonical_walkthrough_artifact_gate() -> None:
    gate = HANDOFF_GATE_SPECS["human-like-product"]

    assert "scripts/dev/capture_human_like_product_walkthrough.py" in gate.argv
    assert gate.required_artifact_paths == ("ui/human-like-product",)
