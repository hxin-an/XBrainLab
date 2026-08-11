"""CLI for source-bound MOABB Qt evidence capture."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from scripts.dev.moabb_user_journeys.registry import (
    DEFAULT_REGISTRY_PATH,
    REPO_ROOT,
    load_registry,
)
from scripts.dev.moabb_user_journeys.storage import (
    default_plan_path,
    load_validated_plan,
    validate_plan_cache,
)

from .contract import MANIFEST_NAME, require_build_output_path

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.dev.moabb_ui_evidence",
        description=(
            "Capture exact-source MOABB journeys through real Qt and "
            "ApplicationService state."
        ),
    )
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--profile", choices=("smoke", "showcase"), default="smoke")
    parser.add_argument(
        "--mode",
        choices=("complete", "import-review"),
        default="complete",
        help="Import-only mode remains unverified for site publication.",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--confirm-resource-plan", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not RUN_ID_PATTERN.fullmatch(args.run_id):
        raise ValueError(
            "run-id must contain only letters, numbers, dot, dash, underscore"
        )
    registry_path = args.registry.resolve()
    registry = load_registry(registry_path)
    plan_path = (args.plan or default_plan_path(registry)).resolve()
    plan = load_validated_plan(
        plan_path,
        registry=registry,
        registry_path=registry_path,
    )

    # This is the exact-source fail-closed boundary. Qt is not imported until
    # every declared source file has passed size and checksum verification.
    cache = validate_plan_cache(plan)
    default_output = (
        REPO_ROOT
        / registry["resource_policy"]["evidence_root"]
        / "qt-captures"
        / args.run_id
    )
    output_dir = require_build_output_path(args.output_dir or default_output)
    if output_dir.exists():
        if not args.force:
            raise FileExistsError(
                f"Capture output already exists; choose a new run-id: {output_dir}"
            )
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    _configure_qt_environment()
    from PyQt6.QtCore import QThreadPool
    from PyQt6.QtWidgets import QApplication

    from XBrainLab.ui.qt_runtime import (
        configure_qt_platform_for_runtime,
        drain_qt_runtime_after_event_loop,
    )

    configure_qt_platform_for_runtime()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    from .capture import capture_all_datasets

    payload = capture_all_datasets(
        app=app,
        registry=registry,
        registry_path=registry_path,
        plan=plan,
        cache=cache,
        output_dir=output_dir,
        run_id=args.run_id,
        profile=args.profile,
        mode=args.mode,
        confirm_resource_plan=args.confirm_resource_plan,
    )
    thread_pool = QThreadPool.globalInstance()
    if thread_pool is not None:
        thread_pool.waitForDone(30_000)
    drain_qt_runtime_after_event_loop(app)
    summary: dict[str, Any] = {
        "manifest": str(output_dir / MANIFEST_NAME),
        "status": payload["status"],
        "site_qualification": payload["site_qualification"],
        "datasets": [item["dataset_id"] for item in payload["datasets"]],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if payload["status"] != "failed" else 1


def _configure_qt_environment() -> None:
    if os.environ.get("QT_QPA_PLATFORM", "").strip():
        return
    if (
        not os.environ.get("DISPLAY", "").strip()
        and not os.environ.get("WAYLAND_DISPLAY", "").strip()
    ):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"


if __name__ == "__main__":
    raise SystemExit(main())
