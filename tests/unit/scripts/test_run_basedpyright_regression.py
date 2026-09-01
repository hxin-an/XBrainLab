from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

from scripts.dev.handoff_gate_spec import HANDOFF_GATE_SPECS
from scripts.dev.run_basedpyright_regression import (
    BASELINE_PATH,
    BasedpyrightBaseline,
    BasedpyrightRegressionError,
    DiagnosticKey,
    _evaluate,
    _run_analyzer,
    _run_command,
    compare_diagnostics,
    load_baseline,
    normalize_diagnostics,
    validate_dependency_probe,
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
        "dace4e7324eea80d296ebcabd67b8d6fb8c40935"  # pragma: allowlist secret
    )
    assert baseline.basedpyright_version == "1.39.2"
    assert baseline.diagnostics == ()
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


def test_dependency_probe_rejects_analyzer_that_erases_pinned_types() -> None:
    with pytest.raises(
        BasedpyrightRegressionError,
        match="did not resolve the pinned PyQt6 types",
    ):
        validate_dependency_probe(
            {
                "generalDiagnostics": [],
                "summary": {"filesAnalyzed": 1, "errorCount": 0},
            },
            probe_path=Path("/tmp/xbrainlab-basedpyright-probe.py"),
        )


def test_dependency_probe_accepts_the_expected_pyqt_sentinel_error() -> None:
    probe_path = Path("/tmp/xbrainlab-basedpyright-probe.py")

    validate_dependency_probe(
        {
            "generalDiagnostics": [
                {
                    "file": str(probe_path),
                    "severity": "error",
                    "rule": "reportAssignmentType",
                    "range": {
                        "start": {"line": 1, "character": 17},
                        "end": {"line": 1, "character": 18},
                    },
                }
            ]
        },
        probe_path=probe_path,
    )


def test_gate_runs_sentinel_before_accepting_a_project_result(monkeypatch) -> None:
    baseline = BasedpyrightBaseline(
        source_sha="dace4e7324eea80d296ebcabd67b8d6fb8c40935",  # pragma: allowlist secret
        basedpyright_version="1.39.2",
        diagnostics=(),
    )
    monkeypatch.setattr(
        "scripts.dev.run_basedpyright_regression.load_baseline", lambda: baseline
    )
    monkeypatch.setattr(
        "scripts.dev.run_basedpyright_regression.shutil.which", lambda _: "basedpyright"
    )
    monkeypatch.setattr(
        "scripts.dev.run_basedpyright_regression._resolve_version", lambda _: "1.39.2"
    )
    monkeypatch.setattr(
        "scripts.dev.run_basedpyright_regression._run_analyzer",
        lambda _: pytest.fail(
            "The project result must not be accepted before the probe."
        ),
    )

    def fail_probe(_: str) -> None:
        raise BasedpyrightRegressionError(
            "Basedpyright did not resolve the pinned PyQt6 types."
        )

    monkeypatch.setattr(
        "scripts.dev.run_basedpyright_regression._run_dependency_probe", fail_probe
    )

    with pytest.raises(BasedpyrightRegressionError, match="pinned PyQt6 types"):
        _evaluate()


def test_analyzer_is_bound_to_the_gate_python_interpreter(monkeypatch) -> None:
    recorded_argv: list[str] = []

    class Completed:
        returncode = 0
        stdout = '{"generalDiagnostics": [], "summary": {"filesAnalyzed": 1}}'
        stderr = ""

    def capture(argv: list[str]) -> Completed:
        recorded_argv.extend(argv)
        return Completed()

    monkeypatch.setattr("scripts.dev.run_basedpyright_regression._run_command", capture)

    _run_analyzer("basedpyright")

    assert recorded_argv == [
        "basedpyright",
        "--pythonpath",
        sys.executable,
        "--outputjson",
    ]


def test_analyzer_output_is_decoded_as_utf8_on_windows_locales(monkeypatch) -> None:
    recorded: dict[str, object] = {}

    def capture(argv, **kwargs):
        recorded.update(kwargs)
        return type(
            "Completed",
            (),
            {"args": argv, "returncode": 0, "stdout": "{}", "stderr": ""},
        )()

    monkeypatch.setattr("subprocess.run", capture)

    _run_command(["basedpyright", "--version"])

    assert recorded["encoding"] == "utf-8"
