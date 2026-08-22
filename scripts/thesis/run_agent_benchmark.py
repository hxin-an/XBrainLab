#!/usr/bin/env python3
"""Validate XBrainLab Agent Benchmark v1 or score one normalized trace."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from XBrainLab.experiments.agent_benchmark import BenchmarkHarness, load_benchmark

DEFAULT_ROOT = ROOT / "benchmarks" / "xbrainlab_agent" / "v1"


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if type(value) is not dict:
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--trace", type=Path, help="Normalized trace to score")
    parser.add_argument("--output", type=Path, help="Create-only verdict artifact path")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    benchmark = load_benchmark(args.benchmark_root)
    summary: dict[str, Any] = {
        "benchmark_id": benchmark.corpus["benchmark_id"],
        "case_count": len(benchmark.cases),
        "family_count": len({case["semantic_family_id"] for case in benchmark.cases}),
        "valid": True,
    }
    if args.trace is not None:
        harness = BenchmarkHarness(benchmark)
        trace = _object(args.trace)
        verdict = harness.score(trace)
        summary["verdict"] = verdict
        if args.output is not None:
            harness.write_verdict(trace, args.output)
        if not verdict["episode"]["passed"]:
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
            return 1
    elif args.output is not None:
        raise ValueError("--output requires --trace")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
