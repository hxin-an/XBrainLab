"""Command-line orchestration for resource-bounded MOABB user journeys."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from .evidence import build_manifest, validate_evidence_manifest
from .product import review_dataset, run_dataset_journey
from .registry import (
    DEFAULT_REGISTRY_PATH,
    REPO_ROOT,
    load_registry,
    materialize_dataset,
    select_datasets,
)
from .storage import (
    build_plan,
    default_plan_path,
    fetch_plan,
    load_validated_plan,
    utc_now,
    validate_plan_cache,
    write_json_atomic,
)

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.dev.moabb_user_journeys",
        description="Plan, fetch, validate, and resume MOABB-backed product journeys.",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY_PATH,
        help="Tracked registry path.",
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    plan = subparsers.add_parser("plan", help="Write a no-download resource plan.")
    _add_dataset_selection(plan)
    plan.add_argument("--output", type=Path)

    fetch = subparsers.add_parser(
        "fetch", help="Fetch the exact validated plan serially."
    )
    _add_dataset_selection(fetch)
    fetch.add_argument("--plan", type=Path)
    fetch.add_argument("--force", action="store_true")
    fetch.add_argument("--output", type=Path)

    validate = subparsers.add_parser(
        "validate", help="Verify cache integrity and optionally review product import."
    )
    _add_dataset_selection(validate)
    validate.add_argument("--plan", type=Path)
    validate.add_argument("--files-only", action="store_true")
    validate.add_argument("--confirm-resource-plan", action="store_true")
    validate.add_argument("--output", type=Path)

    run = subparsers.add_parser(
        "run-resume", help="Replay incomplete datasets through ApplicationService."
    )
    _add_dataset_selection(run)
    run.add_argument("--plan", type=Path)
    run.add_argument("--run-id", required=True)
    run.add_argument("--profile", choices=("smoke", "showcase"), default="smoke")
    run.add_argument("--confirm-resource-plan", action="store_true")
    run.add_argument("--force", action="store_true")
    run.add_argument("--fail-fast", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    registry_path = args.registry.resolve()
    registry = load_registry(registry_path)
    if args.action == "plan":
        return _plan(args, registry, registry_path)
    if args.action == "fetch":
        return _fetch(args, registry, registry_path)
    if args.action == "validate":
        return _validate(args, registry, registry_path)
    if args.action == "run-resume":
        return _run_resume(args, registry, registry_path)
    raise AssertionError(f"Unhandled action: {args.action}")


def _add_dataset_selection(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--dataset",
        action="append",
        dest="dataset_ids",
        help="Registry dataset id; repeat to select multiple. Defaults to all.",
    )


def _plan(
    args: argparse.Namespace,
    registry: dict[str, Any],
    registry_path: Path,
) -> int:
    payload = build_plan(
        registry,
        dataset_ids=args.dataset_ids,
        registry_path=registry_path,
    )
    output = (args.output or default_plan_path(registry)).resolve()
    write_json_atomic(output, payload)
    _print_summary(
        {
            "action": "plan",
            "path": str(output),
            "plan_id": payload["plan_id"],
            "datasets": payload["dataset_ids"],
            "expected_download_bytes": payload["expected_download_bytes"],
            "max_download_bytes": payload["max_download_bytes"],
            "serial_downloads": payload["serial_downloads"],
        }
    )
    return 0


def _fetch(
    args: argparse.Namespace,
    registry: dict[str, Any],
    registry_path: Path,
) -> int:
    plan = _load_plan(args, registry, registry_path)
    receipt = fetch_plan(plan, force=args.force)
    output = (args.output or _evidence_root(registry) / "fetch-receipt.json").resolve()
    write_json_atomic(output, receipt)
    _print_summary(
        {
            "action": "fetch",
            "path": str(output),
            "plan_id": plan["plan_id"],
            "file_count": len(receipt["files"]),
            "bytes": receipt["downloaded_or_reused_bytes"],
        }
    )
    return 0


def _validate(
    args: argparse.Namespace,
    registry: dict[str, Any],
    registry_path: Path,
) -> int:
    plan = _load_plan(args, registry, registry_path)
    cache = validate_plan_cache(plan)
    reviews: list[dict[str, Any]] = []
    if not args.files_only:
        data_root = Path(plan["data_root"])
        reviews = [
            review_dataset(
                materialize_dataset(dataset, data_root=data_root),
                confirm_resource_plan=args.confirm_resource_plan,
            )
            for dataset in select_datasets(registry, args.dataset_ids)
        ]
    payload = {
        **cache,
        "product_review": reviews,
        "status": (
            "failed" if any(review["failures"] for review in reviews) else "validated"
        ),
    }
    output = (
        args.output or _evidence_root(registry) / "validation-receipt.json"
    ).resolve()
    write_json_atomic(output, payload)
    _print_summary(
        {
            "action": "validate",
            "path": str(output),
            "status": payload["status"],
            "file_count": len(cache["files"]),
            "product_reviews": len(reviews),
        }
    )
    return 1 if payload["status"] == "failed" else 0


def _run_resume(
    args: argparse.Namespace,
    registry: dict[str, Any],
    registry_path: Path,
) -> int:
    _validate_run_id(args.run_id)
    plan = _load_plan(args, registry, registry_path)
    cache = validate_plan_cache(plan)
    run_root = (_evidence_root(registry) / "runs" / args.run_id).resolve()
    manifest_path = run_root / "evidence-manifest.json"
    existing = _read_existing_manifest(manifest_path)
    manifest = build_manifest(
        run_id=args.run_id,
        registry=registry,
        plan=plan,
        command=[
            sys.executable,
            "-m",
            "scripts.dev.moabb_user_journeys",
            *sys.argv[1:],
        ],
        execution_profile=args.profile,
    )
    selected = select_datasets(registry, args.dataset_ids)
    existing_by_id = {
        item["dataset"]["id"]: item
        for item in (existing or {}).get("datasets", [])
        if isinstance(item, dict) and isinstance(item.get("dataset"), dict)
    }
    source_by_dataset = _source_artifacts_by_dataset(plan, cache)
    data_root = Path(plan["data_root"])
    for dataset in selected:
        dataset_id = dataset["id"]
        prior = existing_by_id.get(dataset_id)
        if not args.force and _can_reuse(prior, existing, plan, args.profile):
            manifest["datasets"].append(prior)
            continue
        checkpoint = _read_json(run_root / dataset_id / "checkpoint.json") or {}
        evidence = run_dataset_journey(
            materialize_dataset(dataset, data_root=data_root),
            run_root=run_root,
            source_artifacts=source_by_dataset.get(dataset_id, []),
            execution_profile=args.profile,
            confirm_resource_plan=args.confirm_resource_plan,
            attempt=int(checkpoint.get("attempt", 0)) + 1,
            previous_failure=checkpoint.get("failure"),
        )
        manifest["datasets"].append(evidence)
        _finish_manifest(manifest, args.profile)
        validate_evidence_manifest(manifest)
        write_json_atomic(manifest_path, manifest)
        if evidence["failures"] and args.fail_fast:
            break

    _finish_manifest(manifest, args.profile)
    validate_evidence_manifest(manifest)
    write_json_atomic(manifest_path, manifest)
    _print_summary(
        {
            "action": "run-resume",
            "path": str(manifest_path),
            "status": manifest["status"],
            "quality_evidence_status": manifest["quality_evidence_status"],
            "profile": args.profile,
            "datasets_completed": sum(
                not item["failures"] for item in manifest["datasets"]
            ),
            "datasets_selected": len(selected),
        }
    )
    return 1 if manifest["status"] != "completed" else 0


def _load_plan(
    args: argparse.Namespace,
    registry: dict[str, Any],
    registry_path: Path,
) -> dict[str, Any]:
    path = (args.plan or default_plan_path(registry)).resolve()
    return load_validated_plan(
        path,
        registry=registry,
        registry_path=registry_path,
        dataset_ids=args.dataset_ids,
    )


def _evidence_root(registry: dict[str, Any]) -> Path:
    return REPO_ROOT / registry["resource_policy"]["evidence_root"]


def _source_artifacts_by_dataset(
    plan: dict[str, Any], cache: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    dataset_by_path = {
        str(Path(item["cache_path"]).resolve()): item["dataset_id"]
        for item in plan["files"]
    }
    grouped: dict[str, list[dict[str, Any]]] = {}
    for artifact in cache["files"]:
        dataset_id = dataset_by_path[artifact["path"]]
        grouped.setdefault(dataset_id, []).append(artifact)
    return grouped


def _finish_manifest(manifest: dict[str, Any], profile: str) -> None:
    failures = [
        failure for dataset in manifest["datasets"] for failure in dataset["failures"]
    ]
    manifest["failures"] = failures
    if failures:
        manifest["status"] = (
            "failed"
            if manifest["datasets"]
            and all(dataset["failures"] for dataset in manifest["datasets"])
            else "partial"
        )
    else:
        manifest["status"] = "completed"
    if profile == "smoke":
        manifest["quality_evidence_status"] = "pending"
    elif failures:
        manifest["quality_evidence_status"] = "failed"
    elif manifest["datasets"] and all(
        item["quality_evidence_status"] == "complete" for item in manifest["datasets"]
    ):
        manifest["quality_evidence_status"] = "complete"
    else:
        manifest["quality_evidence_status"] = "pending"
    if profile == "showcase" and manifest["quality_evidence_status"] != "complete":
        manifest["status"] = "partial" if manifest["datasets"] else "planned"
    manifest["completed_at"] = utc_now()


def _can_reuse(
    prior: dict[str, Any] | None,
    existing: dict[str, Any] | None,
    plan: dict[str, Any],
    profile: str,
) -> bool:
    if prior is None or prior.get("failures"):
        return False
    runner = (existing or {}).get("runner", {})
    return (
        runner.get("registry_sha256") == plan["registry_sha256"]
        and runner.get("execution_profile") == profile
    )


def _read_existing_manifest(path: Path) -> dict[str, Any] | None:
    payload = _read_json(path)
    if payload is not None:
        validate_evidence_manifest(payload)
    return payload


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def _validate_run_id(run_id: str) -> None:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(
            "run-id must start with an alphanumeric character and contain only "
            "letters, digits, dot, underscore, or hyphen"
        )


def _print_summary(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))
