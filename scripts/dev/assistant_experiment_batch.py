"""Run an explicit frozen tree of experiment packages, with a new result index.

This adapter selects scope only. Leaf entries retain environment, wall limits,
admission, journal and scoring ownership; blocked stages are never skipped.
"""

# ruff: noqa: S603 -- verified frozen entry, no shell expansion.

from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.dev import assistant_experiment_package as package_api

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "xbrainlab.assistant_experiment_batch.v1"
LEAF_SCHEMA = "xbrainlab.assistant_experiment_package.v4"
MODULE = "scripts/dev/assistant_experiment_batch.py"


def _physical(root: Path, relative: str) -> Path:
    item = PurePosixPath(relative)
    if (
        not relative
        or item.is_absolute()
        or str(item) != relative
        or any(part in {".", ".."} for part in item.parts)
        or "\\" in relative
    ):
        raise ValueError("Batch paths must be explicit descendants")
    path = root
    for part in item.parts:
        path /= part
        if path.is_symlink():
            raise ValueError(f"Batch paths must be physical: {path}")
    if not path.resolve().is_relative_to(root):
        raise ValueError("Batch path escapes its root")
    return path


def _selection(
    batch: Path, manifest: dict, seen: set[Path], blocked: list[str]
) -> list[Path]:
    if manifest.get("schema") != SCHEMA or not isinstance(
        manifest.get("children"), list
    ):
        raise ValueError("Invalid batch manifest")
    reason = manifest.get("blocked_reason")
    if reason is not None:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("A blocked batch needs an explicit reason")
        blocked.append(f"{batch}: {reason}")
    elif not manifest["children"]:
        raise ValueError("Empty batch has no runnable scope")
    leaves = []
    for child in manifest["children"]:
        root = _physical(batch, child["path"])
        if root in seen:
            raise ValueError("Duplicate recursive batch selection")
        seen.add(root)
        name = child["manifest"]
        if name not in {"batch.json", "manifest.json"}:
            raise ValueError("Invalid child manifest name")
        identity = _physical(root, name)
        if package_api._digest(identity) != child["sha256"]:
            raise ValueError(f"Frozen child manifest differs: {root}")
        if name == "batch.json":
            leaves.extend(_verify(root, seen, blocked))
        else:
            _physical(root, "run.sh")
            package_api.verify_package(root)
            leaves.append(root)
    return leaves


def _verify(batch: Path, seen: set[Path], blocked: list[str]) -> list[Path]:
    manifest = package_api._json(_physical(batch, "batch.json"))
    head = manifest.get("coordinator", "")
    if not isinstance(head, str) or not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ValueError("Batch needs an exact coordinator source")
    source = _physical(batch, "batch-source")
    git = _physical(source, ".git")
    if not git.is_dir() or (git / "objects/info/alternates").exists():
        raise ValueError("Batch source must be an independent Git checkout")
    package_api._clean_source(source, head)
    for name, expected in manifest.get("files", {}).items():
        if name not in {"run.sh", f"batch-source/{MODULE}"}:
            raise ValueError("Invalid batch immutable file inventory")
        if package_api._digest(_physical(batch, name)) != expected:
            raise ValueError(f"Frozen batch file differs: {name}")
    if set(manifest.get("files", {})) != {"run.sh", f"batch-source/{MODULE}"}:
        raise ValueError("Incomplete batch immutable file inventory")
    return _selection(batch, manifest, seen, blocked)


def verify_batch(batch: Path) -> list[Path]:
    """Verify every frozen child before returning the ordered ready leaf scope."""
    if batch.is_symlink():
        raise ValueError("Batch root must be physical")
    batch = batch.resolve(strict=True)
    blocked: list[str] = []
    leaves = _verify(batch, {batch}, blocked)
    if blocked:
        raise ValueError("Blocked experiment scope: " + "; ".join(blocked))
    return leaves


def create_batch(
    output: Path,
    children: list[Path],
    *,
    coordinator_root: Path = ROOT,
    blocked_reason: str | None = None,
) -> Path:
    """Seal exact existing descendants; no discovery, copying or stage unlock."""
    if output.is_symlink():
        raise ValueError("Batch root must be physical")
    output = output.resolve()
    for name in ("batch.json", "manifest.json", "run.sh", "batch-source"):
        if (output / name).exists() or (output / name).is_symlink():
            raise FileExistsError(output / name)
    entries = []
    for child in children:
        relative = child.absolute().relative_to(output).as_posix()
        root = _physical(output, relative)
        names = [
            name for name in ("batch.json", "manifest.json") if (root / name).exists()
        ]
        if len(names) != 1:
            raise ValueError(f"Child needs exactly one sealed manifest: {root}")
        entries.append(
            {
                "path": relative,
                "manifest": names[0],
                "sha256": package_api._digest(_physical(root, names[0])),
            }
        )
    manifest = {"schema": SCHEMA, "children": entries, "blocked_reason": blocked_reason}
    _selection(output, manifest, {output}, [])  # Blocked descendants can be sealed.
    coordinator_root = coordinator_root.resolve(strict=True)
    head = package_api._git(coordinator_root, "rev-parse", "HEAD")
    package_api._clean_source(coordinator_root, head)
    output.mkdir(parents=True, exist_ok=True)
    package_api._snapshot(coordinator_root, output / "batch-source", head)
    entry = output / "run.sh"
    entry.write_text(
        "#!/bin/sh\nset -eu\n"
        'BATCH_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
        f"exec python{sys.version_info.major}.{sys.version_info.minor} -I -B "
        f'"$BATCH_ROOT/batch-source/{MODULE}" --batch "$BATCH_ROOT" "$@"\n',
        encoding="utf-8",
    )
    entry.chmod(0o755)
    manifest.update(
        coordinator=head,
        files={
            name: package_api._digest(output / name)
            for name in ("run.sh", f"batch-source/{MODULE}")
        },
    )
    package_api._write(output / "batch.json", manifest)
    _verify(output, {output}, [])
    return output


def _invoke(leaf: Path, *, check: bool = False) -> int:
    # Keep the terminal's process group. The leaf's timeout guard owns the
    # native process lifetime; signals directed only here reach that exact PID.
    interrupted = 0
    process = None

    def forward(number, _frame):
        nonlocal interrupted
        interrupted = number
        if process is not None and process.poll() is None:
            process.send_signal(number)

    previous = {
        number: signal.signal(number, forward)
        for number in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        process = subprocess.Popen(
            [str(leaf / "run.sh"), *(["--check-environment"] if check else [])]
        )
        if interrupted:
            process.send_signal(interrupted)
        result = process.wait()
        return (
            128 + interrupted
            if interrupted
            else (128 - result if result < 0 else result)
        )
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def _runs(leaf: Path) -> set[Path]:
    root = package_api._portable_output_root(leaf, "runs")
    if not os.access(root if root.exists() else leaf, os.W_OK | os.X_OK):
        raise ValueError(f"Run outputs are not writable: {root}")
    if not root.exists():
        return set()
    if any(path.is_symlink() for path in root.iterdir()):
        raise ValueError("Run outputs must be physical directories")
    return {path for path in root.iterdir() if path.is_dir()}


def _index(path: Path, batch: Path, records: list[dict]) -> None:
    lines = [
        "# Experiment batch results",
        "",
        "Explicit frozen scope; each invocation retains new outputs.",
        "",
    ]
    for record in records:
        relative = record["leaf"].relative_to(batch).as_posix()
        lines.append(f"- `{relative}`: {record['status']}")
        for run in record["runs"]:
            lines.append(f"  - `{run.relative_to(batch).as_posix()}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_batch(batch: Path, *, check_environment: bool = False) -> int:
    leaves = verify_batch(batch)
    batch = batch.resolve(strict=True)
    for leaf in leaves:
        if package_api._json(leaf / "manifest.json")["schema"] != LEAF_SCHEMA:
            raise ValueError("Batch execution requires v4 shared-resource leaf entries")
        _runs(leaf)
    # All environment checks happen before the first inference launch.
    for leaf in leaves:
        result = _invoke(leaf, check=True)
        if result:
            return result
    if check_environment:
        return 0
    output = package_api._portable_output_root(batch, "batches")
    output.mkdir(exist_ok=True)
    identifier = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
    destination = output / identifier
    destination.mkdir()
    index = destination / "index.md"
    records = [{"leaf": leaf, "status": "unattempted", "runs": []} for leaf in leaves]
    _index(index, batch, records)
    print(f"Batch result index: {index}", flush=True)
    for record in records:
        leaf = record["leaf"]
        before = _runs(leaf)
        record["status"] = "running"
        _index(index, batch, records)
        try:
            result = _invoke(leaf)
            record["runs"] = sorted(_runs(leaf) - before)
            if not result and len(record["runs"]) != 1:
                result = 2
            record["status"] = "completed" if result == 0 else f"failed (exit {result})"
            if len(record["runs"]) > 1:
                record["status"] += "; ambiguous new outputs, attribution unknown"
        except BaseException:
            record["status"] = "failed (entry interrupted or unavailable)"
            raise
        finally:
            _index(index, batch, records)
        if result:
            return result
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument(
        "--check-environment",
        action="store_true",
        help="Check all selected environments; no inference or batch result index",
    )
    args = parser.parse_args(argv)
    try:
        return run_batch(args.batch, check_environment=args.check_environment)
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ) as error:
        print(f"Batch refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
