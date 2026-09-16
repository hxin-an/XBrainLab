"""Run the fixed representative import catalog, without acquiring datasets."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import types
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if __package__ in {None, ""}:
    sys.path.insert(0, str(REPO_ROOT))
    # Editable installs may add another checkout to PEP 420 namespace paths.
    # Bind only previously unloaded script namespaces; never mask loaded code.
    for name in ("scripts", "scripts.dev"):
        if name not in sys.modules:
            package = types.ModuleType(name)
            package.__path__ = [str(REPO_ROOT.joinpath(*name.split(".")))]
            sys.modules[name] = package

from scripts.dev.active_checkout import assert_active_checkout_import
from scripts.dev.moabb_user_journeys.import_catalog import (
    CATALOG_PATH,
    file_sha256,
    load_catalog,
    require_no_regressions,
    resolve_case_manifest,
    resolve_data_path,
)
from scripts.dev.moabb_user_journeys.storage import utc_now, write_json_atomic
from scripts.dev.owned_process_group import spawn_owned_process


def require_same_identity(previous: dict, current: dict) -> None:
    if previous != current:
        raise ValueError("Campaign identity changed; use a new output directory")


def completion_status(rows: list[dict], results: dict[str, dict]) -> str:
    required = [row["id"] for row in rows if row["status"] == "required"]
    return (
        "passed"
        if required
        and all(results.get(key, {}).get("status") == "passed" for key in required)
        else "failed"
    )


def _identity(catalog_path: Path) -> dict[str, Any]:
    def git(*args):
        return subprocess.check_output(["git", "-C", str(REPO_ROOT), *args], timeout=30)  # noqa: S603,S607 - fixed Git inspection arguments.

    # Compare against the accepted main catalog, not a candidate-controlled list
    # of exemptions. Missing Git/ref is an error; only a genuinely absent catalog
    # on main permits the first-catalog bootstrap protected by validate_catalog.
    accepted_sha = git("rev-parse", "--verify", "origin/main^{commit}").decode().strip()
    catalog_name = "scripts/dev/moabb_user_journeys/data/moabb-import-catalog-v1.json"
    accepted_catalog_sha = None
    if git("ls-tree", "--name-only", accepted_sha, "--", catalog_name).strip():
        accepted = git("show", f"{accepted_sha}:{catalog_name}")
        require_no_regressions(json.loads(accepted), load_catalog(catalog_path))
        accepted_catalog_sha = hashlib.sha256(accepted).hexdigest()
    else:
        load_catalog(catalog_path)

    paths = set(git("ls-files", "-z").decode().split("\0"))
    paths.update(
        git(
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
            "XBrainLab",
            "scripts",
            "tests",
        )
        .decode()
        .split("\0")
    )
    digest = hashlib.sha256()
    for name in sorted(paths - {"", "settings.json"}):
        path = REPO_ROOT / name
        digest.update(name.encode())
        digest.update((file_sha256(path) if path.is_file() else "missing").encode())
    packages = sorted(
        (dist.metadata["Name"], dist.version)
        for dist in importlib.metadata.distributions()
        if dist.metadata["Name"]
    )
    return {
        "source": {
            "git_sha": git("rev-parse", "HEAD").decode().strip(),
            "files_sha256": digest.hexdigest(),
        },
        "environment": {
            "python": sys.version,
            "executable": str(Path(sys.executable).resolve()),
            "platform": platform.platform(),
            "packages": packages,
        },
        "catalog": file_sha256(catalog_path),
        "accepted_baseline": {
            "git_sha": accepted_sha,
            "catalog_sha256": accepted_catalog_sha,
        },
    }


def _verify_inputs(case: dict, root: Path) -> None:
    if not case.get("input_files"):
        raise ValueError("Missing bound inputs")
    for item in case["input_files"]:
        if file_sha256(resolve_data_path(root, item["path"])) != item["sha256"]:
            raise ValueError("Case input identity changed")


def _verify_previous(previous: dict, case_id: str) -> None:
    receipt = Path(previous["receipt"])
    if file_sha256(receipt) != previous["receipt_sha256"]:
        raise ValueError("Previous result identity changed")
    result = json.loads(receipt.read_text(encoding="utf-8"))
    if result.get("status") != "passed" or result.get("case_id") != case_id:
        raise ValueError("Previous result does not prove this case")
    recipe = result["recipe"]
    if file_sha256(Path(recipe["path"])) != recipe["sha256"]:
        raise ValueError("Previous recipe identity changed")


def _run_one(row: dict, args: argparse.Namespace, previous: dict | None) -> dict:
    case_id = row["id"]
    stage = "admission"
    attempt = int((previous or {}).get("attempt", 0))
    receipt = None
    try:
        case = resolve_case_manifest(row, args.data_root)
        if previous and previous.get("status") == "passed":
            _verify_inputs(case, args.data_root)
            _verify_previous(previous, case_id)
            return previous
        case_attempts = args.output / "attempts" / case_id
        existing_attempts = (
            [
                int(path.name)
                for path in case_attempts.iterdir()
                if path.name.isdecimal()
            ]
            if case_attempts.exists()
            else []
        )
        attempt = 1 + max([int((previous or {}).get("attempt", 0)), *existing_attempts])
        attempt_root = case_attempts / str(attempt)
        attempt_root.mkdir(parents=True, exist_ok=False)
        receipt = attempt_root / "result.json"
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--catalog",
            str(args.catalog),
            "--data-root",
            str(args.data_root),
            "--output",
            str(attempt_root),
            "--case",
            case_id,
        ]
        stage = "process"
        with (attempt_root / "process.log").open("w", encoding="utf-8") as log:
            process, owner = spawn_owned_process(
                command,
                cwd=REPO_ROOT,
                env={
                    **os.environ,
                    "PYTHONUTF8": "1",
                    "MNE_DONTWRITE_HOME": "true",
                    "QT_QPA_PLATFORM": "offscreen",
                },
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                code = process.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                code = "timeout"
            finally:
                owner.close()
                process.wait(timeout=15)
        result = (
            json.loads(receipt.read_text(encoding="utf-8"))
            if receipt.exists()
            else {
                "case_id": case_id,
                "status": "failed",
                "failure": {"stage": "process", "returncode": code},
            }
        )
        if code != 0 or not receipt.exists():
            result["status"] = "failed"
            result["process_returncode"] = code
            write_json_atomic(receipt, result)
        return {
            "status": result["status"],
            "attempt": attempt,
            "receipt": str(receipt),
            "receipt_sha256": file_sha256(receipt),
            "failure": result.get("failure"),
        }
    except Exception as exc:
        result = {
            "status": "failed",
            "attempt": attempt,
            "failure": {"stage": stage, "message": str(exc)},
        }
        # A cleanup/readback exception is not an admission failure. Preserve the
        # child's receipt and process.log even when it cannot count as a pass.
        if receipt is not None and receipt.is_file():
            result.update(receipt=str(receipt), receipt_sha256=file_sha256(receipt))
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    parser.add_argument(
        "--data-root",
        type=Path,
        help="Defaults to the existing XBRAINLAB_DATA_DIR storage layout.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, choices=range(1, 5), default=1)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--case", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    assert_active_checkout_import(REPO_ROOT)
    from scripts.dev.native_process_safety import disable_core_dumps
    from XBrainLab.platform_paths import dataset_storage_layout

    safety = disable_core_dumps()
    if safety.core_dump_limit_supported and not safety.core_dumps_disabled:
        raise RuntimeError("Import conformance requires disabled native core dumps")
    args.data_root = (args.data_root or dataset_storage_layout().data_root).resolve()
    args.output = args.output.resolve()
    args.catalog = args.catalog.resolve()
    catalog = load_catalog(args.catalog)
    if args.case:
        from scripts.dev.moabb_user_journeys.import_conformance import run_import_case

        row = next(row for row in catalog["entries"] if row["id"] == args.case)
        case = resolve_case_manifest(row, args.data_root)
        result = run_import_case(case, args.data_root, args.output)
        write_json_atomic(args.output / "result.json", result)
        return 0 if result["status"] == "passed" else 1
    identity = _identity(args.catalog)
    # JSON-normalize tuples before comparing persisted identities on resume.
    identity = json.loads(json.dumps(identity))
    manifest_path = args.output / "summary.json"
    if args.resume:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        require_same_identity(manifest["identity"], identity)
    else:
        args.output.mkdir(parents=True, exist_ok=False)
        manifest = {
            "identity": identity,
            "started_at": utc_now(),
            "results": {},
            "dispositions": [
                {"id": r["id"], "status": r["status"]} for r in catalog["entries"]
            ],
        }
    manifest["status"] = "running"
    write_json_atomic(manifest_path, manifest)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        work = {
            pool.submit(_run_one, row, args, manifest["results"].get(row["id"])): row[
                "id"
            ]
            for row in catalog["entries"]
            if row["status"] == "required"
        }
        for future in as_completed(work):
            case_id = work[future]
            result = future.result()
            # Keep every failed attempt, including admission failures, after retries.
            old = manifest["results"].get(case_id)
            if old and old != result:
                manifest.setdefault("prior_results", {}).setdefault(case_id, []).append(
                    old
                )
            manifest["results"][case_id] = result
            write_json_atomic(manifest_path, manifest)
            print(json.dumps({"id": case_id, **result}), flush=True)
    final_identity = json.loads(json.dumps(_identity(args.catalog)))
    manifest["status"] = completion_status(catalog["entries"], manifest["results"])
    if final_identity != identity:
        manifest["status"] = "failed"
        manifest["failure"] = "Source, environment or catalog changed during execution"
    manifest["completed_at"] = utc_now()
    write_json_atomic(manifest_path, manifest)
    return 0 if manifest["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
