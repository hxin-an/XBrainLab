"""Structured completion evidence for source-controlled pytest runners."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2
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
    outcomes: Mapping[str, str],
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
        "outcomes": dict(
            sorted((str(key), str(value)) for key, value in outcomes.items())
        ),
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
    outcomes = raw.get("outcomes")
    if not isinstance(outcomes, dict) or any(
        not isinstance(nodeid, str) or not nodeid or outcome not in OUTCOME_NAMES
        for nodeid, outcome in outcomes.items()
    ):
        return None, "Pytest completion attestation outcomes are malformed."
    outcome_counts = dict.fromkeys(OUTCOME_NAMES, 0)
    for outcome in outcomes.values():
        outcome_counts[outcome] += 1
    if any(outcome_counts[name] != counts[name] for name in OUTCOME_NAMES):
        return None, "Pytest completion attestation outcomes do not match counts."
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


def aggregate_outcomes(attestations: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Merge disjoint shard outcomes and reject duplicate execution evidence."""
    merged: dict[str, str] = {}
    for attestation in attestations:
        outcomes = attestation.get("outcomes", {})
        if not isinstance(outcomes, Mapping):
            continue
        for nodeid, outcome in outcomes.items():
            key = str(nodeid)
            if key in merged:
                raise ValueError(f"Duplicate pytest outcome for {key!r}.")
            merged[key] = str(outcome)
    return dict(sorted(merged.items()))


def required_outcome_failure(
    attestation: Mapping[str, Any],
    selectors: Sequence[str],
) -> str | None:
    """Return why required file/node selectors lack passing terminal evidence."""
    outcomes = attestation.get("outcomes", {})
    if not isinstance(outcomes, Mapping):
        return "Pytest completion attestation outcomes are malformed."
    for selector in selectors:
        matches = {
            str(nodeid): str(outcome)
            for nodeid, outcome in outcomes.items()
            if str(nodeid) == selector or str(nodeid).startswith(f"{selector}::")
        }
        if not matches:
            return f"Required pytest selector {selector!r} has no terminal evidence."
        nonpassing = sorted(
            nodeid for nodeid, outcome in matches.items() if outcome != "passed"
        )
        if nonpassing:
            return f"Required pytest selector {selector!r} did not pass: " + ", ".join(
                nonpassing
            )
    return None
