#!/usr/bin/env python3
"""Run mandatory product tests without allowing skipped coverage to pass."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.dev.pytest_completion_attestation import (
    REQUIRED_PYTEST_RUNNER_ID,
    build_attestation,
    write_attestation,
)


class RequiredPytestGate:
    """Collect pytest outcomes that invalidate a mandatory product gate."""

    def __init__(self) -> None:
        self.skipped: list[str] = []
        self.platform_skipped: list[str] = []
        self.xfailed: list[str] = []
        self.xpassed: list[str] = []
        self.deselected: list[str] = []
        self.selected_count = 0
        self._outcomes: dict[str, str] = {}

    @property
    def clean(self) -> bool:
        return self.complete and not any(
            (self.skipped, self.xfailed, self.xpassed, self.deselected)
        )

    @property
    def complete(self) -> bool:
        """Return whether every selected case produced one terminal outcome."""
        return self.selected_count == len(self._outcomes)

    def pytest_runtest_logreport(self, report: object) -> None:
        """Record one terminal skip/xfail/xpass without changing pytest internals."""
        when = getattr(report, "when", "")
        if when not in {"setup", "call"}:
            return
        nodeid = str(getattr(report, "nodeid", "") or "<unknown test>")
        was_xfail = bool(getattr(report, "wasxfail", None))
        outcome: str | None = None
        if bool(getattr(report, "failed", False)):
            outcome = "failed" if when == "call" else "errors"
        if bool(getattr(report, "skipped", False)):
            keywords = getattr(report, "keywords", {}) or {}
            target = (
                self.xfailed
                if was_xfail
                else self.platform_skipped
                if "platform_contract" in keywords
                else self.skipped
            )
            if nodeid not in target:
                target.append(nodeid)
            outcome = "xfailed" if was_xfail else "skipped"
        elif bool(getattr(report, "passed", False)) and was_xfail:
            if nodeid not in self.xpassed:
                self.xpassed.append(nodeid)
            outcome = "xpassed"
        elif bool(getattr(report, "passed", False)) and when == "call":
            outcome = "passed"
        if outcome is not None:
            self._record_outcome(nodeid, outcome)

    def pytest_deselected(self, items: Sequence[object]) -> None:
        """Record collected mandatory cases excluded by selection rules."""
        for item in items:
            nodeid = str(getattr(item, "nodeid", "") or "<unknown test>")
            if nodeid not in self.deselected:
                self.deselected.append(nodeid)

    def pytest_collection_finish(self, session: object) -> None:
        """Capture the number of selected tests after deselection."""
        self.selected_count = len(getattr(session, "items", ()))

    def _record_outcome(self, nodeid: str, outcome: str) -> None:
        priority = {
            "passed": 1,
            "skipped": 2,
            "xfailed": 3,
            "xpassed": 4,
            "failed": 5,
            "errors": 6,
        }
        previous = self._outcomes.get(nodeid)
        if previous is None or priority[outcome] >= priority[previous]:
            self._outcomes[nodeid] = outcome

    def counts(self) -> dict[str, int]:
        """Return mutually exclusive terminal outcomes for attestation."""
        counts = {
            "collected": self.selected_count + len(self.deselected),
            "executed": len(self._outcomes),
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "xfailed": 0,
            "xpassed": 0,
            "deselected": len(self.deselected),
        }
        for outcome in self._outcomes.values():
            counts[outcome] += 1
        return counts

    def failure_summary(self) -> str:
        groups = (
            ("skipped", self.skipped),
            ("xfailed", self.xfailed),
            ("xpassed", self.xpassed),
            ("deselected", self.deselected),
        )
        lines = ["Mandatory pytest gate did not execute every required case:"]
        missing_outcomes = max(self.selected_count - len(self._outcomes), 0)
        if missing_outcomes:
            lines.append(f"- missing terminal outcomes: {missing_outcomes}")
        for label, nodeids in groups:
            if not nodeids:
                continue
            lines.append(f"- {label}: {len(nodeids)}")
            lines.extend(f"  - {nodeid}" for nodeid in nodeids)
        return "\n".join(lines)


def _parse_args(argv: Sequence[str]) -> tuple[Path | None, list[str]]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-json", type=Path)
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    parsed = parser.parse_args(list(argv))
    result_path = parsed.result_json
    if result_path is None:
        environment_path = os.environ.get("XBL_PYTEST_RESULT_JSON", "").strip()
        result_path = Path(environment_path) if environment_path else None
    pytest_args = list(parsed.pytest_args)
    if pytest_args[:1] == ["--"]:
        pytest_args = pytest_args[1:]
    return result_path, pytest_args


def main(argv: Sequence[str] | None = None) -> int:
    """Run pytest and fail when any mandatory case was not executed normally."""
    result_path, args = _parse_args(sys.argv[1:] if argv is None else argv)
    if result_path is None:
        print(
            "A --result-json path is required for completion evidence.", file=sys.stderr
        )
        return 2
    if not args:
        print("Pass pytest arguments after --.", file=sys.stderr)
        return 2
    logical_args = tuple(args)
    result_path.unlink(missing_ok=True)
    observer = RequiredPytestGate()
    outer_argv = sys.argv
    sys.argv = [outer_argv[0], *logical_args]
    try:
        exit_code = int(pytest.main(list(logical_args), plugins=[observer]))
    finally:
        sys.argv = outer_argv
    final_exit_code = exit_code
    if exit_code == 0 and not observer.clean:
        print(observer.failure_summary(), file=sys.stderr)
        final_exit_code = 1
    write_attestation(
        result_path,
        build_attestation(
            runner=REQUIRED_PYTEST_RUNNER_ID,
            command_args=logical_args,
            exit_code=final_exit_code,
            counts=observer.counts(),
        ),
    )
    return final_exit_code


if __name__ == "__main__":
    raise SystemExit(main())
