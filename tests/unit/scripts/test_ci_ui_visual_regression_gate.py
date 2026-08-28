from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_ci_routes_ui_changes_to_default_and_windows_dpi_gates():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "ui_visual: ${{ steps.scope.outputs.ui_visual }}" in workflow
    assert "python scripts/dev/ci_change_scope.py" in workflow
    assert "UI Default Visual Regression" in workflow
    assert "scripts/dev/capture_ui_baseline.py" in workflow
    assert "UI Windows DPI Regression" in workflow
    assert "scripts/dev/run_app_polish_ui_dpi_gate.py" in workflow
    for factor in ("1.0", "1.25", "1.5"):
        assert factor in workflow


def test_ci_routes_agent_guidance_to_a_focused_contract_job() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    jobs = yaml.safe_load(workflow)["jobs"]

    assert "agent_guidance: ${{ steps.scope.outputs.agent_guidance }}" in workflow
    assert "python scripts/dev/ci_change_scope.py" in workflow
    assert jobs["agent-guidance"]["needs"] == "changes"
    assert jobs["agent-guidance"]["if"] == (
        "needs.changes.outputs.agent_guidance == 'true'"
    )
    guidance_job = str(jobs["agent-guidance"])
    assert "tests/unit/test_agent_guidance_contract.py" not in guidance_job
    assert "tests/unit/scripts/test_audit_agent_guidance.py" in guidance_job
    assert "--confcutdir=tests/unit/scripts" in guidance_job
    assert jobs["docs-only"]["if"] == (
        "needs.changes.outputs.product != 'true' && "
        "needs.changes.outputs.agent_guidance != 'true'"
    )
    for job_name in ("lint", "linux-shard", "platform-test", "public-dataset-gate"):
        assert jobs[job_name]["if"] == "needs.changes.outputs.product == 'true'"
