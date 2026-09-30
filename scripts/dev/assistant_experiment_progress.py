"""Read-only terminal presentation of existing experiment evidence.

Counts describe recorded measurements, not correct answers or certified runs.
The runner remains responsible for all lifecycle, cleanup and success decisions.
"""

from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path

from scripts.dev.assistant_experiment_config import job_condition_identity


def describe(root: Path) -> str:
    """Read small condition summaries; never scan model weights or case payloads."""
    try:
        manifest = root / "prepared-manifest.json"
        if not manifest.exists():
            return "Preparing inputs / validating resources"
        jobs = json.loads(manifest.read_text(encoding="utf-8"))["jobs"]
        groups: dict[str, set[str]] = {}
        for job in jobs:
            groups.setdefault(job_condition_identity(job), set()).add(job["id"])
        total = sum(map(len, groups.values()))
        recorded = 0
        current = "Waiting for model"
        all_finished = bool(groups)
        for index, (key, ids) in enumerate(groups.items(), 1):
            path = root / "raw/conditions" / key / "result.json"
            if not path.exists():
                all_finished = False
                continue
            summary = json.loads(path.read_text(encoding="utf-8"))
            valid = {
                item["id"]
                for item in summary["results"]
                if item["status"] == "recorded" and item.get("cleanup_ok") is True
            } & ids
            recorded += len(valid)
            status = summary["status"]
            if status != "recorded":
                all_finished = False
            phase = (
                (
                    "Loading model / first case"
                    if not summary["results"]
                    else "Inference / case execution"
                )
                if status == "running"
                else status
            )
            current = (
                f"Model {index}/{len(groups)} | {key} {len(valid)}/{len(ids)} | {phase}"
            )
        if all_finished:
            current = "Finalizing / report (awaiting runner exit)"
    except (OSError, ValueError, KeyError, TypeError):
        # Files may be between writes; an observer must not stop the experiment.
        return "Progress temporarily unavailable; experiment continues"
    else:
        return f"{recorded}/{total} recorded | {current}"


def display(root: Path, elapsed: float, *, exit_code: int | None = None) -> None:
    minutes, seconds = divmod(int(elapsed), 60)
    ending = "" if exit_code is None else f" | Runner exit {exit_code}"
    # A closed progress stream must not abandon an already running child.
    with suppress(OSError):
        print(
            f"[progress] Elapsed {minutes:02}:{seconds:02} | {describe(root)}{ending}",
            flush=True,
        )
