from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_ci_routes_ui_changes_to_default_and_windows_dpi_gates():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "ui_visual: ${{ steps.scope.outputs.ui_visual }}" in workflow
    assert "ui_visual=true" in workflow
    assert "UI Default Visual Regression" in workflow
    assert "scripts/dev/capture_ui_baseline.py" in workflow
    assert "UI Windows DPI Regression" in workflow
    assert "scripts/dev/run_app_polish_ui_dpi_gate.py" in workflow
    for factor in ("1.0", "1.25", "1.5"):
        assert factor in workflow
