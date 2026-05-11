from __future__ import annotations

import json
from pathlib import Path

from scripts.agent.evals.run_tool_call_eval import (
    build_deterministic_eval_gate_preflight,
    main,
    run_eval,
)


def test_run_eval_filters_by_case_id() -> None:
    result = run_eval(repeat_count=1, case_ids=["empty-load-path"])

    assert result["summary"]["total_cases"] == 1
    assert result["repeat_count"] == 1
    assert result["selected_case_ids"] == ["empty-load-path"]
    assert "data_interpretation" in result["selected_case_families"]
    assert result["exploratory"] is True
    assert result["summary"]["failed_cases"] == 0


def test_fast_gate_blocks_full_suite_default(tmp_path: Path) -> None:
    exit_code = main(["--output-dir", str(tmp_path)])

    assert exit_code == 2
    gate_artifact = tmp_path / "deterministic_gate.json"
    assert gate_artifact.exists()
    payload = json.loads(gate_artifact.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["eval_gate"] == "fast"
    assert payload["full_suite"] is True
    assert not (tmp_path / "latest.json").exists()


def test_fast_gate_allows_case_subset(tmp_path: Path) -> None:
    exit_code = main(
        [
            "--output-dir",
            str(tmp_path),
            "--case-id",
            "empty-load-path",
        ],
    )

    assert exit_code == 0
    payload = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert payload["eval_gate"] == "fast"
    assert payload["summary"]["total_cases"] == 1
    assert payload["repeat_count"] == 1
    assert payload["selected_case_ids"] == ["empty-load-path"]


def test_release_gate_allows_full_suite_repeat_two() -> None:
    preflight = build_deterministic_eval_gate_preflight(
        eval_gate="release",
        repeat_count=2,
    )

    assert preflight["ok"] is True
    assert preflight["full_suite"] is True


def test_case_limit_zero_is_rejected() -> None:
    try:
        run_eval(repeat_count=1, case_limit=0)
    except ValueError as exc:
        assert "No eval cases selected" in str(exc)
    else:
        raise AssertionError("Expected empty deterministic eval selection to fail")
