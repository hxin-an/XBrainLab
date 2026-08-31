#!/usr/bin/env python3
"""Fail on new Basedpyright diagnostics without rewriting the debt baseline."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = ROOT / "scripts" / "dev" / "basedpyright_baseline.json"
SCHEMA_VERSION = 1
_VERSION_PATTERN = re.compile(r"\bbasedpyright\s+([0-9]+(?:\.[0-9]+){2})\b")
_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_DEPENDENCY_PROBE_SOURCE = "from PyQt6.QtCore import QObject\nprobe: QObject = 1\n"


class BasedpyrightRegressionError(RuntimeError):
    """Raised when analyzer output or the checked-in baseline is invalid."""


@dataclass(frozen=True, order=True)
class DiagnosticKey:
    """Stable identity for one project diagnostic; message wording is excluded."""

    path: str
    rule: str
    start_line: int
    start_character: int
    end_line: int
    end_character: int

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> DiagnosticKey:
        expected = {
            "path",
            "rule",
            "start_line",
            "start_character",
            "end_line",
            "end_character",
        }
        if set(value) != expected:
            raise BasedpyrightRegressionError(
                "Basedpyright baseline diagnostic fields are invalid."
            )
        try:
            return cls(
                path=str(value["path"]),
                rule=str(value["rule"]),
                start_line=int(value["start_line"]),
                start_character=int(value["start_character"]),
                end_line=int(value["end_line"]),
                end_character=int(value["end_character"]),
            )
        except (TypeError, ValueError) as exc:
            raise BasedpyrightRegressionError(
                "Basedpyright baseline diagnostic values are invalid."
            ) from exc

    def as_mapping(self) -> dict[str, str | int]:
        return {
            "path": self.path,
            "rule": self.rule,
            "start_line": self.start_line,
            "start_character": self.start_character,
            "end_line": self.end_line,
            "end_character": self.end_character,
        }


@dataclass(frozen=True)
class BasedpyrightBaseline:
    source_sha: str
    basedpyright_version: str
    diagnostics: tuple[DiagnosticKey, ...]


def load_baseline(path: Path = BASELINE_PATH) -> BasedpyrightBaseline:
    """Load the immutable checked-in regression baseline."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BasedpyrightRegressionError(
            "Basedpyright regression baseline could not be read."
        ) from exc
    if not isinstance(raw, dict) or set(raw) != {
        "schema_version",
        "source_sha_parts",
        "basedpyright_version",
        "diagnostics",
    }:
        raise BasedpyrightRegressionError("Basedpyright baseline schema is invalid.")
    if raw["schema_version"] != SCHEMA_VERSION:
        raise BasedpyrightRegressionError(
            "Basedpyright baseline schema is unsupported."
        )
    source_sha_parts = raw["source_sha_parts"]
    version = raw["basedpyright_version"]
    diagnostics = raw["diagnostics"]
    if (
        not isinstance(source_sha_parts, list)
        or len(source_sha_parts) != 4
        or not all(
            isinstance(part, str) and re.fullmatch(r"[0-9a-f]{10}", part)
            for part in source_sha_parts
        )
    ):
        raise BasedpyrightRegressionError(
            "Basedpyright baseline source identity is invalid."
        )
    source_sha = "".join(source_sha_parts)
    if _SHA_PATTERN.fullmatch(source_sha) is None:
        raise BasedpyrightRegressionError(
            "Basedpyright baseline source identity is invalid."
        )
    if not isinstance(version, str) or not _VERSION_PATTERN.fullmatch(
        f"basedpyright {version}"
    ):
        raise BasedpyrightRegressionError("Basedpyright baseline version is invalid.")
    if not isinstance(diagnostics, list) or not all(
        isinstance(item, dict) for item in diagnostics
    ):
        raise BasedpyrightRegressionError(
            "Basedpyright baseline diagnostics are invalid."
        )
    keys = tuple(sorted(DiagnosticKey.from_mapping(item) for item in diagnostics))
    return BasedpyrightBaseline(source_sha, version, keys)


def _position(raw: Any, *, label: str) -> tuple[int, int]:
    if not isinstance(raw, dict) or set(raw) != {"line", "character"}:
        raise BasedpyrightRegressionError(
            f"Basedpyright diagnostic {label} position is invalid."
        )
    try:
        return int(raw["line"]), int(raw["character"])
    except (TypeError, ValueError) as exc:
        raise BasedpyrightRegressionError(
            f"Basedpyright diagnostic {label} position is invalid."
        ) from exc


def normalize_diagnostics(
    raw_diagnostics: list[dict[str, Any]],
    *,
    repo_root: Path = ROOT,
) -> tuple[DiagnosticKey, ...]:
    """Normalize analyzer JSON to immutable repo-relative error identities."""
    normalized: list[DiagnosticKey] = []
    resolved_root = repo_root.resolve()
    for raw in raw_diagnostics:
        if raw.get("severity") != "error":
            continue
        path_value = raw.get("file")
        rule = raw.get("rule")
        range_value = raw.get("range")
        if not isinstance(path_value, str) or not isinstance(rule, str):
            raise BasedpyrightRegressionError(
                "Basedpyright diagnostic identity is invalid."
            )
        if not isinstance(range_value, dict) or set(range_value) != {"start", "end"}:
            raise BasedpyrightRegressionError(
                "Basedpyright diagnostic range is invalid."
            )
        try:
            relative = Path(path_value).resolve().relative_to(resolved_root).as_posix()
        except (OSError, ValueError) as exc:
            raise BasedpyrightRegressionError(
                "Basedpyright reported an error outside the repository."
            ) from exc
        start_line, start_character = _position(range_value["start"], label="start")
        end_line, end_character = _position(range_value["end"], label="end")
        normalized.append(
            DiagnosticKey(
                path=relative,
                rule=rule,
                start_line=start_line,
                start_character=start_character,
                end_line=end_line,
                end_character=end_character,
            )
        )
    return tuple(sorted(normalized))


def compare_diagnostics(
    observed: tuple[DiagnosticKey, ...],
    allowed: tuple[DiagnosticKey, ...],
) -> tuple[DiagnosticKey, ...]:
    """Return diagnostics that are new relative to the immutable baseline."""
    return tuple(sorted((Counter(observed) - Counter(allowed)).elements()))


def _run_command(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - resolved executable and fixed arguments.
        argv,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=3600,
    )


def _resolve_version(executable: str) -> str:
    completed = _run_command([executable, "--version"])
    text = f"{completed.stdout}\n{completed.stderr}"
    match = _VERSION_PATTERN.search(text)
    if completed.returncode != 0 or match is None:
        raise BasedpyrightRegressionError(
            "Basedpyright version could not be determined."
        )
    return match.group(1)


def _load_analyzer_payload(
    completed: subprocess.CompletedProcess[str],
) -> dict[str, Any]:
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        detail = completed.stderr.strip() or "no structured output"
        raise BasedpyrightRegressionError(
            f"Basedpyright did not return valid JSON: {detail}"
        ) from exc
    if completed.returncode not in {0, 1} or not isinstance(payload, dict):
        raise BasedpyrightRegressionError(
            f"Basedpyright failed with status {completed.returncode}."
        )
    return payload


def _run_analyzer(executable: str) -> dict[str, Any]:
    return _load_analyzer_payload(
        _run_command([executable, "--pythonpath", sys.executable, "--outputjson"])
    )


def validate_dependency_probe(payload: dict[str, Any], *, probe_path: Path) -> None:
    """Require a diagnostic that only exists when Basedpyright resolves PyQt6 types."""
    diagnostics = payload.get("generalDiagnostics")
    if not isinstance(diagnostics, list) or not all(
        isinstance(item, dict) for item in diagnostics
    ):
        raise BasedpyrightRegressionError("Basedpyright JSON diagnostics are invalid.")
    target = probe_path.resolve()
    for diagnostic in diagnostics:
        if diagnostic.get("severity") != "error":
            continue
        if diagnostic.get("rule") != "reportAssignmentType":
            continue
        path_value = diagnostic.get("file")
        if isinstance(path_value, str) and Path(path_value).resolve() == target:
            return
    raise BasedpyrightRegressionError(
        "Basedpyright did not resolve the pinned PyQt6 types; refusing a false-green "
        "project result."
    )


def _run_dependency_probe(executable: str) -> None:
    """Use the analyzer itself to prove its selected Python exposes pinned GUI types."""
    with tempfile.TemporaryDirectory(prefix="xbrainlab-basedpyright-") as temporary_dir:
        probe_path = Path(temporary_dir) / "dependency_probe.py"
        probe_path.write_text(_DEPENDENCY_PROBE_SOURCE, encoding="utf-8")
        completed = _run_command(
            [
                executable,
                "--pythonpath",
                sys.executable,
                "--outputjson",
                str(probe_path),
            ]
        )
        validate_dependency_probe(
            _load_analyzer_payload(completed), probe_path=probe_path
        )


def _evaluate() -> tuple[dict[str, Any], int]:
    baseline = load_baseline()
    executable = shutil.which("basedpyright")
    if executable is None:
        raise BasedpyrightRegressionError("Basedpyright executable is unavailable.")
    observed_version = _resolve_version(executable)
    if observed_version != baseline.basedpyright_version:
        raise BasedpyrightRegressionError(
            "Basedpyright version does not match the checked-in baseline."
        )
    _run_dependency_probe(executable)
    payload = _run_analyzer(executable)
    raw_diagnostics = payload.get("generalDiagnostics")
    if not isinstance(raw_diagnostics, list) or not all(
        isinstance(item, dict) for item in raw_diagnostics
    ):
        raise BasedpyrightRegressionError("Basedpyright JSON diagnostics are invalid.")
    observed = normalize_diagnostics(raw_diagnostics)
    added = compare_diagnostics(observed, baseline.diagnostics)
    summary = {
        "baseline_source_sha": baseline.source_sha,
        "basedpyright_version": observed_version,
        "baseline_diagnostic_count": len(baseline.diagnostics),
        "observed_diagnostic_count": len(observed),
        "resolved_diagnostic_count": sum(
            (Counter(baseline.diagnostics) - Counter(observed)).values()
        ),
        "new_diagnostics": [item.as_mapping() for item in added],
        "passed": not added,
    }
    return summary, (0 if not added else 1)


def main() -> int:
    try:
        summary, return_code = _evaluate()
    except (BasedpyrightRegressionError, OSError, subprocess.SubprocessError) as exc:
        print(f"Basedpyright regression gate failed: {exc}", file=sys.stderr)
        return 2
    else:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return return_code


if __name__ == "__main__":
    raise SystemExit(main())
