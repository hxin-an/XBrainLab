"""Windows B0 entry. Run this FILE, not -m: frozen modules load after bootstrap.

This only composes the archived runner and renderer; it never scores, retries,
downloads models, installs packages, or changes the frozen product checkout.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

SOURCE = "926d90ea80b0fa66322238d7914fde07cde26af3"  # pragma: allowlist secret
MANIFEST_SHA = (  # Public archive checksum, not a credential.
    "63c62e517656e2ec4c947460fa441f06455a0ad8faa5394a2bd4c2e0152dbded"  # pragma: allowlist secret
)
ARCHIVE = "E:/XBrainLabData/evidence/assistant-b0-formal-20260921-926d90ea"
CHECKOUT = "D:/XBrainLabCache/b0-926d90ea"
LOCK = Path("D:/XBrainLabCache/assistant-b0.lock")
ENTRY_FILE = Path(__file__).resolve()
INPUT_FILES = (
    "reviewed-non-test-bank.xlsx",
    "pilot-selection-runtime.json",
    "pilot-config.json",
)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def verify_archive(archive: Path) -> dict:
    manifest = archive / "manifest.sha256"
    if digest(manifest) != MANIFEST_SHA:
        raise ValueError(
            "Frozen archive manifest differs; original archive is never repaired here"
        )
    hashes = dict(
        line.split("  ", 1)[::-1] for line in manifest.read_text().splitlines()
    )
    required = [
        "source/identity.json",
        "resources/resource-manifest.json",
        "results/raw/manifest.json",
        *("experiment/" + name for name in INPUT_FILES),
    ]
    for name in required:
        if digest(archive / name) != hashes[name]:
            raise ValueError("Frozen archive input differs: " + name)
    return {
        "hashes": hashes,
        "manifest": read_json(archive / "results/raw/manifest.json"),
        "resources": read_json(archive / "resources/resource-manifest.json"),
    }


def git(*args: str) -> str:
    executable = shutil.which("git")
    if executable is None:
        raise ValueError("Git is required to restore/check the frozen source")
    result = subprocess.run(  # noqa: S603 - fixed Git operations, argv without shell
        [executable, *map(str, args)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    return result.stdout.strip()


def ensure_checkout(bundle: Path, checkout: Path, expected_hash: str) -> None:
    if not checkout.exists():
        if digest(bundle) != expected_hash:
            raise ValueError("Frozen source bundle hash differs")
        checkout.parent.mkdir(parents=True, exist_ok=True)
        print(
            "Restoring the frozen source once (no environment/model copy)...",
            flush=True,
        )
        git(
            "clone",
            "--config",
            "core.autocrlf=false",
            "--no-checkout",
            str(bundle),
            str(checkout),
        )
        git("-C", str(checkout), "checkout", "--detach", SOURCE)
    if git("-C", str(checkout), "rev-parse", "HEAD") != SOURCE:
        raise ValueError(
            "Source cache is not frozen B0; it will not be reset or overwritten"
        )
    if git("-C", str(checkout), "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Source cache must be clean; user changes are preserved")
    # The frozen tree includes tracked defaults; the clean check also covers them.
    # Never copy the main worktree's user-owned settings into this cache.


def validate_layout(
    archive: Path, checkout: Path, output: Path, *, windows: bool
) -> None:
    paths = [path.resolve() for path in (archive, checkout, output)]
    for index, left in enumerate(paths):
        for right in paths[index + 1 :]:
            if left.is_relative_to(right) or right.is_relative_to(left):
                raise ValueError("Archive, source and output paths must not overlap")
    if windows and (len(str(paths[1])) > 60 or len(str(paths[2])) > 60):
        raise ValueError(
            "Use short Windows source/output roots (at most 60 characters)"
        )


def verify_environment(actual: dict, frozen: dict) -> None:
    for name in ("python", "machine", "gpus", "packages"):
        if actual.get(name) != frozen.get(name):
            raise ValueError(
                "B0 environment differs in "
                + name
                + "; no automatic installation or fallback"
            )


def verify_run_identity(manifest: dict, frozen: dict, conditions: dict) -> None:
    for field in (
        "schema",
        "source",
        "bank_sha256",
        "selection",
        "config",
        "corpus_sha256",
        "seed",
        "repeat",
        "budget_seconds",
        "child_timeout_seconds",
        "condition_timeout_seconds",
    ):
        if manifest[field] != frozen[field]:
            raise ValueError("Frozen configuration mismatch: " + field)
    if not manifest["models"] or not manifest["jobs"]:
        raise ValueError("Empty baseline selection")
    for name, spec in manifest["models"].items():
        if spec != frozen["models"].get(name):
            raise ValueError("Frozen model configuration mismatch: " + name)
    selected = {job["condition"] for job in manifest["jobs"]}
    if selected - conditions.keys() or manifest["jobs"] != [
        job for job in frozen["jobs"] if job["condition"] in selected
    ]:
        raise ValueError("Baseline requires complete canonical condition schedules")
    if set(manifest["models"]) != {conditions[name][0] for name in selected}:
        raise ValueError("Baseline model membership differs from selected conditions")
    embedding = (
        frozen["embedding_sha256"]
        if any(conditions[name][1] for name in selected)
        else None
    )
    if manifest["embedding_sha256"] != embedding:
        raise ValueError("Frozen embedding configuration mismatch")


def load_frozen(checkout: Path):
    if any(
        name in {"scripts", "XBrainLab"} or name.startswith(("scripts.", "XBrainLab."))
        for name in sys.modules
    ):
        raise ValueError(
            "Product/scripts already imported; launch this entry as a file in a fresh process"
        )
    checkout = checkout.resolve()
    sys.path[:] = [
        path
        for path in sys.path
        if Path(path or ".").resolve() != ENTRY_FILE.parent
        and not (Path(path or ".") / "XBrainLab" / "__init__.py").is_file()
    ]
    sys.path.insert(0, str(checkout))
    os.chdir(checkout)
    os.environ.update(
        QT_QPA_PLATFORM="offscreen",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        PYTHONPATH=str(checkout),
    )
    owner = importlib.import_module("scripts.dev.active_checkout")
    owner.assert_active_checkout_import(checkout)
    runner = importlib.import_module("scripts.dev.run_assistant_pilot")
    reporter = importlib.import_module("scripts.dev.assistant_pilot_report")
    owner.assert_active_checkout_import(checkout)
    return runner, reporter


def verify_resources(resources: dict, manifest: dict) -> dict:
    inventories = [resources["models"][name]["snapshot"] for name in manifest["models"]]
    if manifest.get("embedding_sha256"):
        inventories.append(resources["embedding"])
    total = 0
    for inventory in inventories:
        location = inventory["root"]
        if os.name == "nt":
            location = re.sub(
                r"^/mnt/([a-z])/", lambda m: m[1].upper() + ":/", location
            )
        root = Path(location)
        # Hugging Face snapshots legitimately link to their sibling blobs store.
        boundary = root.parent.parent if root.parent.name == "snapshots" else root
        print("Checking pinned resource contents: " + str(root), flush=True)
        for item in inventory["files"]:
            path = (root / item["path"]).resolve(strict=True)
            if (
                not path.is_relative_to(boundary.resolve())
                or path.stat().st_size != item["bytes"]
                or digest(path) != item["sha256"]
            ):
                raise ValueError("Pinned resource content differs: " + item["path"])
            total += 1
    return {"files_content_hashed": total, "stat_cache_used": False}


def prepare_output(archive: Path, output: Path, *, resume: bool) -> None:
    if resume:
        if not output.is_dir():
            raise ValueError("Resume requires the original output directory")
        for name in INPUT_FILES:
            if digest(output / "inputs" / name) != digest(
                archive / "experiment" / name
            ):
                raise ValueError("Retained input differs; cannot resume")
    else:
        output.mkdir(parents=True, exist_ok=False)
        (output / "inputs").mkdir()
        for name in INPUT_FILES:
            shutil.copyfile(archive / "experiment" / name, output / "inputs" / name)


def run_attempt(
    runner,
    reporter,
    manifest: dict,
    bank: dict,
    output: Path,
    *,
    resume: bool,
    report_only: bool = False,
    metadata: dict | None = None,
) -> int:
    attempt = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-") + uuid4().hex[:8]
    for name in ("launches", "reports"):
        (output / name).mkdir(exist_ok=True)
    report_path = output / "reports" / attempt
    info = {
        "entry_sha256": digest(ENTRY_FILE),
        "source": SOURCE,
        "resume": resume,
        "report_only": report_only,
        **(metadata or {}),
    }
    write_json(output / "launches" / (attempt + "-start.json"), info)
    shutil.copyfile(ENTRY_FILE, output / "launches" / (attempt + "-entry.py"))
    error, report, code = None, None, 0
    try:
        if not report_only:
            code = runner.execute(manifest, bank, output / "raw", resume=resume)
    except KeyboardInterrupt:
        code, error = (
            130,
            "Interrupted; existing runner owns child cleanup. Never resend an unresolved operation.",
        )
    except Exception as exc:
        code, error = 1, str(exc)[:2000]
    runner_code = None if report_only else code
    if (output / "raw" / "manifest.json").is_file():
        try:
            report = reporter.write_report(output / "raw", report_path)
            audit = read_json(report_path / "presentation-audit.json")
            if (
                not report["complete_selected_schedule"]
                or not audit["complete"]
                or audit["issues"]
            ):
                code = code or 1
        except Exception as exc:
            code, error = (
                code or 1,
                "Report failed; raw evidence retained: " + str(exc)[:2000],
            )
    else:
        code = code or 1
    info.update(
        runner_exit_code=runner_code,
        exit_code=code,
        error=error,
        report=str(report_path.relative_to(output)) if report else None,
    )
    write_json(output / "launches" / (attempt + "-end.json"), info)
    link = report_path.relative_to(output).as_posix() + "/index.html"
    status = (
        "Selected schedule complete"
        if code == 0
        else "Incomplete / failed attempt (exit " + str(code) + ")"
    )
    notice = "DEV Pilot only. Decision scores are not complete task success. No Validation/Test or model ranking."
    text = f"# B0 results\n\n{status}\n\n{notice}\n\nSource: `{SOURCE}`\n\n"
    if report:
        text += f"[Latest report]({link})\n\n"
    text += "inputs/: fixed non-Test inputs; raw/: original measurements; reports/: immutable report attempts; launches/: entry identity and failures.\n\n"
    if error:
        text += error + "\n"
    # Only these two explicitly derived navigation files are refreshed on resume.
    (output / "README.md").write_text(text, encoding="utf-8")
    page = f'<!doctype html><meta charset="utf-8"><title>B0 results</title><h1>{html.escape(status)}</h1><p>{notice}</p>'
    if report:
        page += f'<p><a href="{link}">Open latest report</a></p>'
    page += (
        '<p><a href="README.md">Results layout</a></p><pre>'
        + html.escape(error or "")
        + "</pre>"
    )
    (output / "index.html").write_text(page, encoding="utf-8")
    print(status + ": " + str(output / "index.html"), flush=True)
    return code


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--list", action="store_true")
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--report-only", action="store_true")
    parser.add_argument("--conditions", default="all")
    parser.add_argument("--archive", type=Path, default=Path(ARCHIVE))
    parser.add_argument("--checkout", type=Path, default=Path(CHECKOUT))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if os.name != "nt":
        parser.error("This measured B0 entry supports Windows Python only")
    if (args.resume or args.report_only) and args.output is None:
        parser.error("--resume/--report-only requires the original --output")
    archive, checkout = args.archive.resolve(), args.checkout.resolve()
    output = args.output or Path("D:/XBrainLabRuns") / (
        "b0-" + datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid4().hex[:6]
    )
    output = output.resolve()
    validate_layout(archive, checkout, output, windows=True)
    if output.exists() and not (
        args.resume or args.report_only or args.check or args.list
    ):
        raise FileExistsError(
            "Output already exists; use a new path or explicit --resume"
        )
    # Reuse the installed filelock, not a second process/lifecycle controller.
    from filelock import FileLock

    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(LOCK), timeout=0):
        frozen = verify_archive(archive)
        ensure_checkout(
            archive / "source/xbrainlab-b0.bundle",
            checkout,
            frozen["hashes"]["source/xbrainlab-b0.bundle"],
        )
        runner, reporter = load_frozen(checkout)
        if args.list:
            print(json.dumps(runner.CONDITIONS, indent=2))
            return 0
        if args.report_only:
            prepare_output(archive, output, resume=True)
            retained = read_json(output / "raw" / "manifest.json")
            verify_run_identity(retained, frozen["manifest"], runner.CONDITIONS)
            verify_environment(
                retained["environment"], frozen["manifest"]["environment"]
            )
            return run_attempt(
                runner, reporter, {}, {}, output, resume=False, report_only=True
            )
        print("Checking frozen inputs, environment and resources...", flush=True)
        paths = [archive / "experiment" / name for name in INPUT_FILES]
        manifest, bank = runner.prepare_manifest(
            *paths, runner.select_conditions(args.conditions)
        )
        verify_environment(manifest["environment"], frozen["manifest"]["environment"])
        verify_run_identity(manifest, frozen["manifest"], runner.CONDITIONS)
        resources = verify_resources(frozen["resources"], manifest)
        if args.check:
            print(
                f"B0 ready: {len(manifest['jobs'])} selected cases; no model inference started."
            )
            return 0
        prepare_output(archive, output, resume=args.resume)
        return run_attempt(
            runner,
            reporter,
            manifest,
            bank,
            output,
            resume=args.resume,
            metadata={
                "archive": str(archive),
                "archive_manifest_sha256": MANIFEST_SHA,
                "resources": resources,
                "conditions": args.conditions,
                "python": sys.executable,
            },
        )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print("B0 entry stopped: " + str(exc), file=sys.stderr)
        raise SystemExit(1) from None
