"""Seal independent experiment inputs/source and delegate to the existing runner.

Editable config is an input to create, never a second runtime authority. Package
verification protects immutable files; execution, admission, journal and cleanup
remain owned by run_assistant_dev and its runner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.dev.assistant_experiment_config import experiment_identity

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "xbrainlab.assistant_experiment_package.v1"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _git(root: Path, *arguments: str) -> str:
    executable = shutil.which("git")
    if executable is None:
        raise FileNotFoundError("Git is required for independent source snapshots")
    return subprocess.check_output(  # noqa: S603 - fixed Git operations, no shell.
        [executable, "-C", str(root), *arguments],
        text=True,
        stderr=subprocess.PIPE,
        timeout=60,
    ).strip()


def _clean_source(root: Path, head: str) -> None:
    if _git(root, "rev-parse", "HEAD") != head:
        raise ValueError(f"Source HEAD differs: {root}")
    if _git(root, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError(f"Source is not clean: {root}")
    for name in ("pyproject.toml", "poetry.lock"):
        if not (root / name).is_file():
            raise ValueError(f"Missing source environment specification: {root / name}")


def _snapshot(source: Path, destination: Path, head: str) -> None:
    destination.mkdir()
    _git(destination, "init", "-q")
    # File transport with depth one creates independent objects, unlike local
    # clone optimizations or a worktree .git link to the editable repository.
    _git(destination, "fetch", "--quiet", "--depth=1", source.as_uri(), head)
    _git(destination, "checkout", "--quiet", "--detach", "FETCH_HEAD")
    _clean_source(destination, head)


def _resource_reference(value: str, original_base: Path, sealed_base: Path) -> str:
    path = Path(value)
    if path.is_absolute():
        return value  # Explicit external binding; never silently relocate it.
    return os.path.relpath((original_base / path).resolve(), sealed_base)


def create_package(
    bank: Path,
    config: Path,
    output: Path,
    *,
    coordinator_root: Path = ROOT,
) -> Path:
    """Create a new sealed package; failures leave no published manifest.

    Source/config edits require another create. Partial output is retained for
    diagnosis, never overwritten or treated as a runnable package.
    """
    bank, config, output = (
        bank.resolve(strict=True),
        config.resolve(strict=True),
        output.absolute(),
    )
    if output.exists():
        raise FileExistsError(output)
    values = _json(config)
    experiment_identity(values)
    resources = (config.parent / values["resource_inventory"]).resolve(strict=True)
    coordinator_root = coordinator_root.resolve(strict=True)
    coordinator = _git(coordinator_root, "rev-parse", "HEAD")
    sources = {coordinator: coordinator_root}
    _clean_source(coordinator_root, coordinator)
    for model in values["models"]:
        source = model["source"]
        root = (config.parent / source["root"]).resolve(strict=True)
        _clean_source(root, source["head"])
        sources[source["head"]] = root
    output.mkdir(parents=True)
    for directory in ("sources", "inputs", "environment"):
        (output / directory).mkdir()
    sealed = json.loads(json.dumps(values))
    for model in sealed["models"]:
        model["source"]["root"] = f"../sources/{model['source']['head']}"
        model["model_cache"] = _resource_reference(
            model["model_cache"], config.parent, output / "inputs"
        )
    sealed["embedding_cache"] = _resource_reference(
        sealed["embedding_cache"], config.parent, output / "inputs"
    )
    sealed["resource_inventory"] = "resources.json"
    specifications = []
    for head, source in sources.items():
        destination = output / "sources" / head
        _snapshot(source, destination, head)
        for name in ("pyproject.toml", "poetry.lock"):
            specification = output / "environment" / f"{head}-{name}"
            shutil.copyfile(destination / name, specification)
            specifications.append(specification)
    shutil.copyfile(bank, output / "inputs/bank.xlsx")
    shutil.copyfile(config, output / "inputs/config-original.json")
    shutil.copyfile(resources, output / "inputs/resources.json")
    _write(output / "inputs/config.json", sealed)
    entry = output / "run.sh"
    entry.write_text(
        "#!/bin/sh\nset -eu\n"
        'PACKAGE_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
        'PYTHON=${XBL_PYTHON:-"$PACKAGE_ROOT/environment/python"}\n'
        # Resolve this binding once, not the venv executable's own symlink to
        # base Python: pyvenv.cfg must be discovered beside venv/bin/python.
        'if [ -z "${XBL_PYTHON:-}" ] && [ -L "$PYTHON" ]; then\n'
        '  PYTHON=$(readlink -- "$PYTHON")\n'
        '  case "$PYTHON" in /*) ;; *) PYTHON="$PACKAGE_ROOT/environment/$PYTHON" ;; esac\n'
        "fi\n"
        'if [ ! -x "$PYTHON" ]; then\n'
        '  echo "Bind environment/python or set XBL_PYTHON to the locked Python executable" >&2\n'
        "  exit 2\n"
        "fi\n"
        f'exec "$PYTHON" "$PACKAGE_ROOT/sources/{coordinator}/scripts/dev/assistant_experiment_package.py" '
        'launch --package "$PACKAGE_ROOT" "$@"\n',
        encoding="utf-8",
    )
    entry.chmod(0o755)
    immutable = [entry, *sorted((output / "inputs").iterdir()), *specifications]
    manifest = {
        "schema": SCHEMA,
        "coordinator": coordinator,
        "sources": sorted(sources),
        "files": {
            path.relative_to(output).as_posix(): _digest(path) for path in immutable
        },
    }
    # The manifest is the completion marker. No state/journal is owned here.
    _write(output / "manifest.json", manifest)
    verify_package(output)
    return output


def verify_package(package: Path) -> dict:
    """Check sealed inputs and independent Git snapshots without model access."""
    package = package.resolve(strict=True)
    manifest = _json(package / "manifest.json")
    if manifest.get("schema") != SCHEMA or manifest.get(
        "coordinator"
    ) not in manifest.get("sources", []):
        raise ValueError("Invalid experiment package manifest")
    for relative, expected in manifest["files"].items():
        path = (package / relative).resolve(strict=True)
        if not path.is_relative_to(package) or _digest(path) != expected:
            raise ValueError(f"Sealed package file differs: {relative}")
    required = {
        "run.sh",
        "inputs/bank.xlsx",
        "inputs/config.json",
        "inputs/config-original.json",
        "inputs/resources.json",
    }
    for head in manifest["sources"]:
        source = (package / "sources" / head).resolve(strict=True)
        if (
            not source.is_relative_to(package / "sources")
            or not (source / ".git").is_dir()
            or (source / ".git").is_symlink()
        ):
            raise ValueError("Package source is not an independent Git checkout")
        if (source / ".git/objects/info/alternates").exists():
            raise ValueError("Package source depends on an external object store")
        _clean_source(source, head)
        for name in ("pyproject.toml", "poetry.lock"):
            relative = f"environment/{head}-{name}"
            required.add(relative)
            if _digest(source / name) != manifest["files"].get(relative):
                raise ValueError(
                    "Package environment specification differs from source"
                )
    if set(manifest["files"]) != required:
        raise ValueError("Package immutable file inventory differs")
    config = _json(package / "inputs/config.json")
    experiment_identity(config)
    if config["resource_inventory"] != "resources.json":
        raise ValueError("Package resource inventory must use its sealed copy")
    for model in config["models"]:
        source = model["source"]
        if (
            source["head"] not in manifest["sources"]
            or source["root"] != f"../sources/{source['head']}"
        ):
            raise ValueError("Candidate source differs from package inventory")
    return manifest


def _retained_run(package: Path, requested: Path) -> Path:
    """Bind a retained run to sealed package inputs, not merely its directory."""
    run = requested if requested.is_absolute() else package / "runs" / requested
    run = run.resolve(strict=True)
    if not run.is_dir() or run.parent != (package / "runs").resolve():
        raise ValueError("Select an existing run belonging to this package")
    for name in ("bank.xlsx", "config.json", "resources.json"):
        retained = run / "inputs" / name
        if not retained.is_file() or _digest(retained) != _digest(
            package / "inputs" / name
        ):
            raise ValueError(f"Retained run inputs differ from sealed package: {name}")
    return run


def launch_package(
    package: Path,
    *,
    resume: Path | None = None,
    report_only: Path | None = None,
    audit: Path | None = None,
    replace_invalid: bool = False,
) -> NoReturn:
    """Delegate one invocation; the runner alone owns locks and run state."""
    if sum(path is not None for path in (resume, report_only, audit)) > 1 or (
        replace_invalid and resume is None
    ):
        raise ValueError("Replacement requires resume; select only one run action")
    package = package.resolve(strict=True)
    manifest = verify_package(package)
    module = "scripts.dev.run_assistant_dev"
    if audit is not None:
        run = _retained_run(package, audit)
        module = "scripts.dev.assistant_experiment_audit"
        arguments = ["--package", str(package), "--run", str(run)]
    elif resume is not None or report_only is not None:
        run = _retained_run(package, resume if resume is not None else report_only)
        arguments = ["resume" if resume is not None else "report", "--output", str(run)]
        if replace_invalid:
            arguments.append("--replace-invalid")
    else:
        identifier = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
        (package / "runs").mkdir(exist_ok=True)
        arguments = [
            "run",
            "--bank",
            str(package / "inputs/bank.xlsx"),
            "--config",
            str(package / "inputs/config.json"),
            "--output",
            str(package / "runs" / identifier),
        ]
    environment = dict(os.environ)
    coordinator = package / "sources" / manifest["coordinator"]
    environment.update(
        PYTHONPATH=str(coordinator), HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1"
    )
    # Replace this adapter instead of becoming another process/lifecycle owner.
    os.chdir(coordinator)
    os.execve(  # noqa: S606 - fixed interpreter/module; runner owns lifecycle.
        sys.executable,
        [sys.executable, "-m", module, *arguments],
        environment,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    create = actions.add_parser(
        "create", help="Seal an editable config into a new package"
    )
    for name in ("bank", "config", "output"):
        create.add_argument(f"--{name}", type=Path, required=True)
    launch = actions.add_parser("launch", help="Internal run.sh adapter")
    launch.add_argument("--package", type=Path, required=True)
    selection = launch.add_mutually_exclusive_group()
    selection.add_argument("--resume", type=Path)
    selection.add_argument("--report-only", type=Path)
    selection.add_argument("--audit", type=Path)
    launch.add_argument("--replace-invalid", action="store_true")
    args = parser.parse_args(argv)
    if args.action == "create":
        print(create_package(args.bank, args.config, args.output))
        return 0
    return launch_package(
        args.package,
        resume=args.resume,
        report_only=args.report_only,
        audit=args.audit,
        replace_invalid=args.replace_invalid,
    )


if __name__ == "__main__":
    raise SystemExit(main())
