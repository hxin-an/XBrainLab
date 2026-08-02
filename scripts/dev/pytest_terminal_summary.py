"""Parse real pytest terminal-summary lines for strict evidence gates."""

from __future__ import annotations

import re

PYTEST_OUTCOME_KEYS = (
    "passed",
    "failed",
    "errors",
    "skipped",
    "xfailed",
    "xpassed",
    "deselected",
)

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_COUNT_AND_LABEL = (
    r"\d+\s+(?:passed|failed|errors?|skipped|xfailed|xpassed|deselected|warnings?)"
)
_TERMINAL_SUMMARY = re.compile(
    rf"^\s*(?:=+\s*)?"
    rf"(?P<body>{_COUNT_AND_LABEL}(?:,\s*{_COUNT_AND_LABEL})*)"
    rf"\s+in\s+\d+(?:\.\d+)?s"
    rf"(?:\s+\([^\r\n)]*\))?\s*(?:=+)?\s*$",
    re.IGNORECASE,
)
_OUTCOME = re.compile(
    r"(?P<count>\d+)\s+"
    r"(?P<label>passed|failed|skipped|xfailed|xpassed|deselected|errors?)\b",
    re.IGNORECASE,
)


def terminal_summary_lines(output: str) -> tuple[str, ...]:
    """Return only complete pytest terminal summaries, including shard summaries."""
    summaries: list[str] = []
    for raw_line in output.splitlines():
        line = _ANSI_ESCAPE.sub("", raw_line).strip()
        if line and _TERMINAL_SUMMARY.fullmatch(line):
            summaries.append(line)
    return tuple(summaries)


def parse_terminal_outcomes(output: str) -> dict[str, int]:
    """Aggregate outcomes only from complete terminal-summary lines."""
    outcomes: dict[str, int] = dict.fromkeys(PYTEST_OUTCOME_KEYS, 0)
    for line in terminal_summary_lines(output):
        for match in _OUTCOME.finditer(line):
            label = match.group("label").casefold()
            if label == "error":
                label = "errors"
            outcomes[label] = max(outcomes[label], int(match.group("count")))
    return outcomes


def last_terminal_summary(output: str) -> str | None:
    """Return the last complete pytest summary, or ``None`` when absent."""
    summaries = terminal_summary_lines(output)
    return summaries[-1] if summaries else None
