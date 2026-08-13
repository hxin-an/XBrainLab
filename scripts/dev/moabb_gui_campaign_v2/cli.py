"""Command-line entry for campaign preflight, orchestration, and workers."""

from __future__ import annotations

import argparse
from pathlib import Path

from .contract import (
    JOURNEY_MODES,
    execution_preflight_errors,
    load_campaign_plan,
)
from .driver import missing_product_source_hooks

DEFAULT_PLAN = (
    Path(__file__).resolve().parents[3]
    / "artifacts"
    / "user-journeys"
    / "moabb-gui-campaign-v2.json"
)
REPO_ROOT = Path(__file__).resolve().parents[3]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m scripts.dev.moabb_gui_campaign_v2")
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--plan", type=Path, default=DEFAULT_PLAN)

    run = subparsers.add_parser("run")
    run.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    run.add_argument("--evidence-root", type=Path, required=True)
    run.add_argument("--journey-timeout-seconds", type=int, default=3600)

    worker = subparsers.add_parser("worker")
    worker.add_argument("--plan", type=Path, required=True)
    worker.add_argument("--dataset", required=True)
    worker.add_argument("--mode", choices=JOURNEY_MODES, required=True)
    worker.add_argument("--receipt", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    plan = load_campaign_plan(args.plan)
    if args.command == "preflight":
        errors = execution_preflight_errors(plan)
        errors.extend(
            f"product UI hook is missing: {name}"
            for name in missing_product_source_hooks(REPO_ROOT)
        )
        if errors:
            print("Campaign is not execution-ready:")
            for error in errors:
                print(f"- {error}")
            return 2
        print("Campaign execution preflight passed.")
        return 0
    if args.command == "run":
        from .runner import run_campaign

        run_campaign(
            plan_path=args.plan,
            plan=plan,
            evidence_root=args.evidence_root,
            journey_timeout_seconds=args.journey_timeout_seconds,
        )
        return 0
    from .worker import run_worker

    return run_worker(
        plan=plan,
        dataset=args.dataset,
        mode=args.mode,
        receipt_path=args.receipt,
        plan_path=args.plan,
    )
