from __future__ import annotations

from pathlib import Path

import tomllib

from scripts.dev.handoff_gate_spec import HANDOFF_GATE_SPECS
from scripts.dev.run_basedpyright_regression import (
    BASELINE_PATH,
    DiagnosticKey,
    compare_diagnostics,
    load_baseline,
    normalize_diagnostics,
)

ROOT = Path(__file__).resolve().parents[3]


def _diagnostic(*, line: int = 4, rule: str = "reportArgumentType") -> dict:
    return {
        "file": str(ROOT / "XBrainLab" / "example.py"),
        "severity": "error",
        "rule": rule,
        "range": {
            "start": {"line": line, "character": 2},
            "end": {"line": line, "character": 8},
        },
        "message": "Environment-specific wording is not part of the identity.",
    }


def test_normalize_diagnostics_uses_repo_relative_stable_identity() -> None:
    diagnostics = normalize_diagnostics([_diagnostic()], repo_root=ROOT)

    assert diagnostics == (
        DiagnosticKey(
            path="XBrainLab/example.py",
            rule="reportArgumentType",
            start_line=4,
            start_character=2,
            end_line=4,
            end_character=8,
        ),
    )


def test_regression_comparison_allows_resolved_debt_but_rejects_new_error() -> None:
    original = DiagnosticKey(
        path="XBrainLab/example.py",
        rule="reportArgumentType",
        start_line=4,
        start_character=2,
        end_line=4,
        end_character=8,
    )
    added = DiagnosticKey(
        path="XBrainLab/new.py",
        rule="reportCallIssue",
        start_line=9,
        start_character=1,
        end_line=9,
        end_character=5,
    )

    assert compare_diagnostics((), (original,)) == ()
    assert compare_diagnostics((original,), (original,)) == ()
    assert compare_diagnostics((original, added), (original,)) == (added,)


def test_checked_in_baseline_and_all_handoff_consumers_are_read_only() -> None:
    baseline = load_baseline(BASELINE_PATH)

    assert baseline.source_sha == (
        "70274bed4c41331965e7d4795d0d16520cb0aada"  # pragma: allowlist secret
    )
    assert baseline.basedpyright_version == "1.39.2"
    assert len(baseline.diagnostics) == 81
    assert HANDOFF_GATE_SPECS["basedpyright"].argv == (
        "poetry",
        "run",
        "--",
        "python",
        "scripts/dev/run_basedpyright_regression.py",
    )
    dashboard_source = (ROOT / "scripts/dev/update_quality_dashboard.py").read_text(
        encoding="utf-8"
    )
    assert "scripts/dev/run_basedpyright_regression.py" in dashboard_source
    assert "--writebaseline" not in dashboard_source


def test_typecheck_excludes_only_reviewed_third_party_model_source() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert config["tool"]["basedpyright"]["exclude"] == [
        "XBrainLab/llm/core/models",
        "XBrainLab/backend/model_base/legacy_braindecode",
    ]
