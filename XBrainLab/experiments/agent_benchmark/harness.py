"""Single research owner for corpus validation, scoring, and immutable writes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import BenchmarkContractError, BenchmarkCorpus, canonical_sha256
from .scoring import score_episode


class BenchmarkHarness:
    """Score frozen inputs and emit create-only, hash-addressed artifacts."""

    def __init__(self, benchmark: BenchmarkCorpus) -> None:
        self._benchmark = benchmark
        self._cases = {case["case_id"]: case for case in benchmark.cases}

    def score(self, trace: dict[str, Any]) -> dict[str, Any]:
        case_id = trace.get("case_id")
        case = self._cases.get(case_id)
        if case is None:
            raise BenchmarkContractError(f"Unknown trace case_id: {case_id}")
        return score_episode(case, trace)

    def write_verdict(self, trace: dict[str, Any], destination: Path) -> Path:
        """Create one verdict; never overwrite an evidence-bearing artifact."""
        verdict = self.score(trace)
        envelope = {
            "verdict": verdict,
            "trace_sha256": canonical_sha256(trace),
            "case_sha256": self._benchmark.corpus["case_hashes"][trace["case_id"]],
        }
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with destination.open("x", encoding="utf-8") as handle:
                json.dump(
                    envelope,
                    handle,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                handle.write("\n")
        except FileExistsError as exc:
            raise BenchmarkContractError(
                f"Artifact already exists: {destination}"
            ) from exc
        return destination
