"""Structured completion evidence for source-controlled pytest runners."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
REQUIRED_PYTEST_RUNNER_ID = "xbrainlab.required-pytest-gate"
SHARDED_PYTEST_RUNNER_ID = "xbrainlab.sharded-test-runner"
OUTCOME_NAMES = (
    "passed",
    "failed",
    "errors",
    "skipped",
    "xfailed",
    "xpassed",
    "deselected",
)
COUNT_NAMES = ("collected", "executed", *OUTCOME_NAMES)


def build_attestation(
    *,
    runner: str,
    command_args: Sequence[str],
    exit_code: int,
    counts: Mapping[str, int],
) -> dict[str, Any]:
    """Build one normalized completed-run payload."""
    normalized_counts = {name: int(counts.get(name, 0)) for name in COUNT_NAMES}
    return {
        "schema_version": SCHEMA_VERSION,
        "runner": runner,
        "completed": True,
        "exit_code": int(exit_code),
        "command_args": [str(part) for part in command_args],
        "counts": normalized_counts,
    }


def write_attestation(path: Path, payload: Mapping[str, Any]) -> None:
    """Atomically publish evidence only after the runner has completed."""
    target = path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(dict(payload), indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)


def validate_attestation(
    path: Path,
    *,
    expected_runner: str,
    expected_args: Sequence[str],
    expected_exit_code: int,
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate a completion artifact against the exact invoking runner."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "Pytest completion attestation was not produced."
    except (OSError, json.JSONDecodeError):
        return None, "Pytest completion attestation is unreadable."
    if not isinstance(raw, dict):
        return None, "Pytest completion attestation is malformed."
    if raw.get("schema_version") != SCHEMA_VERSION:
        return None, "Pytest completion attestation schema is unsupported."
    if raw.get("runner") != expected_runner:
        return None, "Pytest completion attestation runner does not match."
    if raw.get("completed") is not True:
        return None, "Pytest runner did not attest normal completion."
    if raw.get("exit_code") != expected_exit_code:
        return None, "Pytest completion attestation exit code does not match."
    if raw.get("command_args") != [str(part) for part in expected_args]:
        return None, "Pytest completion attestation arguments do not match."
    counts = raw.get("counts")
    if not isinstance(counts, dict) or set(counts) != set(COUNT_NAMES):
        return None, "Pytest completion attestation counts are malformed."
    if any(
        isinstance(counts[name], bool)
        or not isinstance(counts[name], int)
        or counts[name] < 0
        for name in COUNT_NAMES
    ):
        return None, "Pytest completion attestation counts are invalid."
    terminal_total = sum(int(counts[name]) for name in OUTCOME_NAMES[:-1])
    if terminal_total != counts["executed"]:
        return None, "Pytest completion attestation executed count is inconsistent."
    if counts["collected"] != counts["executed"] + counts["deselected"]:
        return None, "Pytest completion attestation collected count is inconsistent."
    return raw, None


def aggregate_counts(attestations: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Sum independently attested shard outcomes."""
    totals: dict[str, int] = {}
    for name in COUNT_NAMES:
        totals[name] = 0
    for attestation in attestations:
        counts = attestation.get("counts", {})
        if not isinstance(counts, Mapping):
            continue
        for name in COUNT_NAMES:
            value = counts.get(name, 0)
            if isinstance(value, int) and not isinstance(value, bool):
                totals[name] += value
    return totals
