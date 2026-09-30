"""One movable experiment, shared snapshots, explicit stage/round selection.

This adapter seals files and selects invocations. The existing runner alone
owns admission, measurement, journal, cleanup and scoring.
"""

# ruff: noqa: S603 -- fixed interpreter/modules and argv, never shell expansion.

from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.dev import assistant_experiment_package as package_api
from scripts.dev.assistant_experiment_progress import display as display_progress
from scripts.dev.assistant_experiment_shared import (
    check_environment,
    environment_binding,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "xbrainlab.assistant_experiment_tree.v1"
MODULE = "scripts/dev/assistant_experiment_batch.py"


def _physical(root: Path, relative: str) -> Path:
    item = PurePosixPath(relative)
    if (
        not relative
        or item.is_absolute()
        or str(item) != relative
        or any(part in {".", ".."} for part in item.parts)
        or "\\" in relative
        or relative == "."
    ):
        raise ValueError("Experiment paths must be explicit descendants")
    path = root
    for part in item.parts:
        path /= part
        if path.is_symlink():
            raise ValueError(f"Experiment paths must be physical: {path}")
    if not path.resolve().is_relative_to(root):
        raise ValueError("Experiment path escapes its root")
    return path


def _leaves(manifest: dict, scope: str, *, allow_blocked: bool = False) -> list[str]:
    seen: set[str] = set()
    leaves = []

    def visit(key: str) -> None:
        if key not in manifest["scopes"]:
            raise ValueError(f"Unknown experiment scope: {key}")
        if key in seen:
            raise ValueError("Duplicate or cyclic experiment scope")
        seen.add(key)
        value = manifest["scopes"][key]
        if "blocked_reason" in value:
            if not allow_blocked:
                raise ValueError(
                    f"Blocked experiment scope {key}: {value['blocked_reason']}"
                )
        elif "children" in value:
            for child in value["children"]:
                visit(child)
        else:
            leaves.append(key)

    visit(scope)
    return leaves


def select_scopes(manifest: dict, scope: str) -> list[str]:
    """Reject any unready/duplicate selection before launching the first child."""
    return _leaves(manifest, scope)


def _seal_input(output: Path, path: Path) -> str:
    relative = f"snapshot/inputs/{package_api._digest(path)}{path.suffix}"
    destination = output / relative
    if not destination.exists():
        shutil.copyfile(path, destination)
    return relative


def create_experiment(
    output: Path,
    selections: list[dict],
    scopes: dict,
    *,
    coordinator_root: Path = ROOT,
    shared_python: Path,
    references: tuple[Path, ...] | list[Path] = (),
) -> Path:
    """Seal once per source/input; partial failures never publish a valid tree."""
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    coordinator_root = coordinator_root.resolve(strict=True)
    head = package_api._git(coordinator_root, "rev-parse", "HEAD")
    sources = {head: coordinator_root}
    manifest = {
        "schema": SCHEMA,
        "coordinator": head,
        "sources": [],
        "scopes": dict(scopes),
        "references": [],
        "files": {},
    }
    for name in (
        "snapshot/sources",
        "snapshot/inputs",
        "snapshot/environment",
        "stages",
        "results/reference",
        "results/runs",
    ):
        (output / name).mkdir(parents=True, exist_ok=True)
    for selection in selections:
        key = selection["path"]
        directory = _physical(output, key)
        if not re.fullmatch(r"stages/[a-z0-9/-]+", key) or key in manifest["scopes"]:
            raise ValueError("Duplicate or invalid stage selection")
        directory.mkdir(parents=True, exist_ok=True)
        original = Path(selection["config"]).resolve(strict=True)
        config = package_api._json(original)
        package_api.experiment_identity(config)
        _seal_input(output, original)
        for model in config["models"]:
            source = model["source"]
            sources[source["head"]] = (original.parent / source["root"]).resolve(
                strict=True
            )
            source["root"] = os.path.relpath(
                output / "snapshot/sources" / source["head"], directory
            )
            model["model_cache"] = str(
                (original.parent / model["model_cache"]).resolve(strict=True)
            )
        config["embedding_cache"] = str(
            (original.parent / config["embedding_cache"]).resolve(strict=True)
        )
        resources = _seal_input(
            output,
            (original.parent / config["resource_inventory"]).resolve(strict=True),
        )
        config["resource_inventory"] = os.path.relpath(output / resources, directory)
        package_api._write(directory / "config.json", config)
        rows = [
            "# Frozen candidate mapping",
            "",
            "| Model | Candidate | Source |",
            "| --- | --- | --- |",
        ]
        rows.extend(
            f"| {m['alias']} | {m['candidate_index']} | `{m['source']['head']}` |"
            for m in config["models"]
        )
        rows.extend(["", "## Adjustment rationale", "", selection["notes"], ""])
        (directory / "README.md").write_text("\n".join(rows), encoding="utf-8")
        manifest["scopes"][key] = {
            "bank": _seal_input(output, Path(selection["bank"]).resolve(strict=True)),
            "config": f"{key}/config.json",
        }
    for commit, source in sources.items():
        package_api._clean_source(source, commit)
        package_api._snapshot(source, output / "snapshot/sources" / commit, commit)
        for name in ("pyproject.toml", "poetry.lock"):
            shutil.copyfile(
                source / name, output / "snapshot/environment" / f"{commit}-{name}"
            )
    manifest["sources"] = sorted(sources)
    package_api._write(
        output / "snapshot/environment/shared.json", environment_binding(shared_python)
    )
    for scope in manifest["scopes"]:
        if scope != "." and not re.fullmatch(r"stages/[a-z0-9/-]+", scope):
            raise ValueError("Invalid scope path")
        directory = output if scope == "." else _physical(output, scope)
        directory.mkdir(parents=True, exist_ok=True)
        _entry(
            directory / "run.sh",
            os.path.relpath(output, directory),
            head,
            f"--scope {scope}",
        )
    _entry(output / "compare.sh", ".", head, "--compare")
    (output / "README.md").write_text(
        "# Reproducible experiment\n\n"
        "Copy this entire directory to your writable Linux/NAS location.\n"
        "Only fixed Python/model resources remain external; recipient access is required.\n"
        "Do not copy a round alone. Each source commit is stored once.\n\n"
        "- stages/: frozen scopes, per-model config/source and adjustment notes.\n"
        "- snapshot/: independent sources, inputs and environment identities. Do not edit.\n"
        "- results/reference/: unchanged original evidence, compare-only.\n"
        "- results/runs/: a new directory per run; no overwrite.\n"
        "- .runtime/: local caches/logs/temp; no installation or downloads.\n\n"
        "At any scope: ./run.sh --check-environment (no inference), or ./run.sh.\n"
        "At root: ./compare.sh results/reference/<id> results/runs/<id>.\n"
        "Blocked scopes refuse before any inference; selection is explicit, not folder discovery.\n"
        "Check mode checks versions/access, not GPU/model quality; the runner verifies model hashes.\n"
        "Each run has a 18000-second wall guard. Keep the terminal connected or use tmux.\n"
        "Coordinate GPU access; no cross-user reservation service is supplied.\n"
        "Copied references retain historical absolute paths; comparison uses local raw/source.\n"
        "Partial-run resume is not a relocation feature.\n",
        encoding="utf-8",
    )
    for reference in references:
        _copy_reference(output, reference, manifest)
    immutable = [output / "README.md", output / "run.sh", output / "compare.sh"]
    for directory in ("stages", "snapshot/inputs", "snapshot/environment"):
        immutable.extend(p for p in (output / directory).rglob("*") if p.is_file())
    manifest["files"] = {
        p.relative_to(output).as_posix(): package_api._digest(p) for p in immutable
    }
    package_api._write(output / "snapshot/manifest.json", manifest)
    verify_experiment(output)
    return output


def append_round(root: Path, selection: dict, *, coordinator_root: Path = ROOT) -> Path:
    """Append one frozen DEV round without rewriting earlier evidence or inputs.

    New artifacts are prepared and validated privately. Existing entries remain
    byte-identical: they already resolve the runner from the manifest coordinator.
    The atomic manifest replacement is the only publication point. Call this
    deployment operation with no concurrent writers to the experiment tree.
    """
    manifest = verify_experiment(root)
    root = root.resolve(strict=True)
    manifest_path = root / "snapshot/manifest.json"
    original = manifest_path.read_bytes()
    key = selection["path"]
    parent = "stages/dev"
    if (
        not re.fullmatch(r"stages/dev/round-[0-9]{2}", key)
        or key in manifest["scopes"]
        or set(manifest["scopes"].get(parent, {})) != {"children"}
        or _physical(root, key).exists()
    ):
        raise ValueError("Append requires a new round under the existing DEV scope")
    config = package_api._json(Path(selection["config"]))
    if config.get("split") != "DEV":
        raise ValueError("Only a DEV configuration can be appended as a DEV round")
    binding = package_api._json(root / "snapshot/environment/shared.json")
    added: list[Path] = []
    # A sibling keeps moves on the same filesystem; no model/results are copied.
    with tempfile.TemporaryDirectory(
        prefix=".experiment-append-", dir=root.parent
    ) as temporary:
        staged = Path(temporary) / "tree"
        create_experiment(
            staged,
            [selection],
            {".": {"children": [key]}},
            coordinator_root=coordinator_root,
            shared_python=Path(binding["python"]),
        )
        incoming = verify_experiment(staged)
        if package_api._json(staged / "snapshot/environment/shared.json") != binding:
            raise ValueError("Shared environment differs from the frozen identity")
        incoming_files = {
            name: digest
            for name, digest in incoming["files"].items()
            if name.startswith((f"{key}/", "snapshot/inputs/", "snapshot/environment/"))
        }
        moves = [key]
        moves.extend(
            f"snapshot/sources/{head}"
            for head in incoming["sources"]
            if head not in manifest["sources"]
        )
        for name, digest in incoming_files.items():
            if name in manifest["files"]:
                if manifest["files"][name] != digest:
                    raise ValueError(f"Append would change a frozen file: {name}")
            elif not name.startswith(f"{key}/"):
                moves.append(name)
        for name in moves:
            if _physical(root, name).exists():
                raise FileExistsError(f"Append destination already exists: {name}")
        manifest["coordinator"] = incoming["coordinator"]
        manifest["sources"] = sorted(
            set(manifest["sources"]) | set(incoming["sources"])
        )
        manifest["files"].update(incoming_files)
        manifest["scopes"][key] = incoming["scopes"][key]
        manifest["scopes"][parent]["children"].append(key)
        try:
            for name in moves:
                destination = _physical(root, name)
                (staged / name).rename(destination)
                added.append(destination)
            _verify_manifest(root, manifest)
            if manifest_path.read_bytes() != original:
                raise ValueError("Experiment manifest changed during append")  # noqa: TRY301 - rollback owns added artifacts.
            pending = Path(temporary) / "manifest.json"
            package_api._write(pending, manifest)
            os.replace(pending, manifest_path)
        except BaseException:
            # Only newly moved paths belong to this invocation; never old evidence.
            for path in reversed(added):
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            raise
    return root / key


def _copy_reference(output: Path, reference: Path, manifest: dict) -> None:
    source = reference.resolve(strict=True)
    target = output / "results/reference" / source.name
    if target.exists():
        raise ValueError("Duplicate reference run")
    for path in source.rglob("*"):
        if (
            path.is_symlink()
            and path.relative_to(source).as_posix() != "raw/rag/models"
        ):
            raise ValueError(f"Unexpected reference link: {path}")
    shutil.copytree(source, target, symlinks=True)
    hashes = {
        p.relative_to(source).as_posix(): package_api._digest(p)
        for p in source.rglob("*")
        if p.is_file() and not p.is_symlink()
    }
    if any(
        package_api._digest(target / name) != digest for name, digest in hashes.items()
    ):
        raise ValueError("Reference copy differs")
    package_api._write(
        output / "snapshot/inputs" / f"reference-{source.name}.json", hashes
    )
    manifest["references"].append(source.name)


def _entry(path: Path, relative: str, head: str, action: str) -> None:
    path.write_text(
        "#!/bin/sh\nset -eu\n"
        f'EXPERIMENT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/{relative}" && pwd)\n'
        f"exec python{sys.version_info.major}.{sys.version_info.minor} -I -B "
        f'"$EXPERIMENT_ROOT/snapshot/sources/{head}/{MODULE}" '
        f'--experiment "$EXPERIMENT_ROOT" {action} "$@"\n',
        encoding="utf-8",
    )
    path.chmod(0o755)


def verify_experiment(root: Path) -> dict:
    if root.is_symlink():
        raise ValueError("Experiment root must be physical")
    root = root.resolve(strict=True)
    manifest = package_api._json(_physical(root, "snapshot/manifest.json"))
    return _verify_manifest(root, manifest)


def _verify_manifest(root: Path, manifest: dict) -> dict:
    if manifest.get("schema") != SCHEMA or manifest.get(
        "coordinator"
    ) not in manifest.get("sources", []):
        raise ValueError("Invalid experiment snapshot")
    for name, digest in manifest["files"].items():
        if package_api._digest(_physical(root, name)) != digest:
            raise ValueError(f"Frozen experiment file differs: {name}")
    required = {"README.md", "run.sh", "compare.sh", "snapshot/environment/shared.json"}
    for head in manifest["sources"]:
        if not re.fullmatch(r"[a-f0-9]{40}", head):
            raise ValueError("Invalid source identity")
        source = _physical(root, f"snapshot/sources/{head}")
        git = _physical(source, ".git")
        if not git.is_dir() or (git / "objects/info/alternates").exists():
            raise ValueError("Source must be an independent Git checkout")
        package_api._clean_source(source, head)
        for name in ("pyproject.toml", "poetry.lock"):
            relative = f"snapshot/environment/{head}-{name}"
            required.add(relative)
            if manifest["files"].get(relative) != package_api._digest(source / name):
                raise ValueError("Environment specification differs from source")
    if "." not in manifest["scopes"]:
        raise ValueError("Missing whole-experiment scope")
    for key, value in manifest["scopes"].items():
        if key != "." and (
            not re.fullmatch(r"stages/[a-z0-9/-]+", key)
            or not _physical(root, key).is_dir()
        ):
            raise ValueError("Invalid scope path")
        required.add("run.sh" if key == "." else f"{key}/run.sh")
        if set(value) == {"children"}:
            if not isinstance(value["children"], list) or not value["children"]:
                raise ValueError("Scope needs an explicit nonempty selection")
            _leaves(manifest, key, allow_blocked=True)
        elif set(value) == {"blocked_reason"}:
            if (
                not isinstance(value["blocked_reason"], str)
                or not value["blocked_reason"].strip()
            ):
                raise ValueError("Blocked scope needs a reason")
        elif set(value) == {"bank", "config"}:
            required.update(_verify_config(root, manifest, key, value))
        else:
            raise ValueError("Invalid scope configuration")
    if not required <= manifest["files"].keys():
        raise ValueError("Incomplete immutable inventory")
    return manifest


def _verify_config(root: Path, manifest: dict, key: str, value: dict) -> set[str]:
    if value["config"] != f"{key}/config.json" or not value["bank"].startswith(
        "snapshot/inputs/"
    ):
        raise ValueError("Scope inputs must be sealed")
    config = package_api._json(_physical(root, value["config"]))
    package_api.experiment_identity(config)
    base = root / key
    resource = (base / config["resource_inventory"]).resolve(strict=True)
    if not resource.is_relative_to(root / "snapshot/inputs"):
        raise ValueError("Resource inventory must be sealed")
    for model in config["models"]:
        source = model["source"]
        if source["head"] not in manifest["sources"] or source[
            "root"
        ] != os.path.relpath(root / "snapshot/sources" / source["head"], base):
            raise ValueError("Candidate source differs from snapshot")
    if not all(
        Path(p).is_absolute()
        for p in [
            config["embedding_cache"],
            *(m["model_cache"] for m in config["models"]),
        ]
    ):
        raise ValueError("Shared model bindings must be absolute")
    return {
        value["bank"],
        value["config"],
        f"{key}/README.md",
        resource.relative_to(root).as_posix(),
    }


def _identifier() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]


def _outputs(root: Path, name: str) -> Path:
    directory = _physical(root, f"results/{name}")
    existing = directory
    while not existing.exists():
        existing = existing.parent
    if not existing.is_dir() or not os.access(existing, os.W_OK | os.X_OK):
        raise ValueError(f"Experiment outputs are not writable: {directory}")
    if directory.exists() and (
        not directory.is_dir() or any(p.is_symlink() for p in directory.iterdir())
    ):
        raise ValueError("Experiment outputs must be physical directories")
    return directory


def _invoke(
    argv: list[str], environment: dict, cwd: Path, *, progress_root: Path | None = None
) -> int:
    interrupted, process = 0, None

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
        started = time.monotonic()
        process = subprocess.Popen(argv, env=environment, cwd=cwd)
        if interrupted:
            process.send_signal(interrupted)
        while True:
            if progress_root is not None:
                display_progress(progress_root, time.monotonic() - started)
            try:
                result = process.wait(timeout=5 if progress_root is not None else None)
                break
            except subprocess.TimeoutExpired:
                continue
        if progress_root is not None:
            display_progress(
                progress_root, time.monotonic() - started, exit_code=result
            )
        return (
            128 + interrupted
            if interrupted
            else (128 - result if result < 0 else result)
        )
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def _command(python: Path, module: str, arguments: list[str]) -> list[str]:
    return [
        shutil.which("prlimit"),
        "--core=0",
        shutil.which("timeout"),
        "--signal=TERM",
        "--kill-after=60s",
        "18000",
        str(python),
        "-B",
        "-m",
        module,
        *arguments,
    ]


def run_scope(root: Path, scope: str, *, check_environment: bool = False) -> int:
    print(
        "[progress] Checking experiment snapshot and shared environment...", flush=True
    )
    manifest = verify_experiment(root)
    root = root.resolve(strict=True)
    leaves = select_scopes(manifest, scope)
    configs = [
        package_api._json(root / manifest["scopes"][key]["config"]) for key in leaves
    ]
    output = _outputs(root, "runs")
    python, environment = _environment(root, manifest, configs)
    if check_environment:
        print(
            f"Shared environment ready; scope {scope}: {len(leaves)} selection(s). No inference or run started."
        )
        return 0
    output.mkdir(parents=True, exist_ok=True)
    records = [
        {"scope": key, "run": _identifier(), "status": "unattempted"} for key in leaves
    ]
    index = output / f"{_identifier()}-scope.json"
    for record in records:
        value = manifest["scopes"][record["scope"]]
        destination = output / record["run"]
        record["status"] = "running"
        package_api._write(index, {"scope": scope, "runs": records})
        print(f"Run output: {destination}", flush=True)
        try:
            result = _invoke(
                _command(
                    python,
                    "scripts.dev.run_assistant_dev",
                    [
                        "run",
                        "--bank",
                        str(root / value["bank"]),
                        "--config",
                        str(root / value["config"]),
                        "--output",
                        str(destination),
                    ],
                ),
                environment,
                root / "snapshot/sources" / manifest["coordinator"],
                progress_root=destination,
            )
            if result == 0 and not (destination / "prepared-manifest.json").is_file():
                result = 2
            record["status"] = "completed" if result == 0 else f"failed (exit {result})"
        except BaseException:
            record["status"] = "failed (entry interrupted or unavailable)"
            raise
        finally:
            package_api._write(index, {"scope": scope, "runs": records})
        if result:
            return result
    return 0


def _environment(root: Path, manifest: dict, configs: list[dict]) -> tuple[Path, dict]:
    python, environment = check_environment(
        root, package_api._json(root / "snapshot/environment/shared.json"), configs
    )
    environment["PYTHONPATH"] = str(root / "snapshot/sources" / manifest["coordinator"])
    return python, environment


def compare_experiment(root: Path, first: Path, second: Path) -> int:
    manifest = verify_experiment(root)
    root = root.resolve(strict=True)
    python, environment = _environment(root, manifest, [])
    output = _outputs(root, "comparisons")
    output.mkdir(parents=True, exist_ok=True)
    for requested in (first, second):
        run = requested.resolve(strict=True)
        if run.parent == root / "results/reference":
            inventory = package_api._json(
                _physical(root, f"snapshot/inputs/reference-{run.name}.json")
            )
            for name, digest in inventory.items():
                if package_api._digest(_physical(run, name)) != digest:
                    raise ValueError(f"Reference evidence differs: {run.name}/{name}")
    return _invoke(
        _command(
            python,
            "scripts.dev.assistant_experiment_compare",
            [
                str(first.resolve(strict=True)),
                str(second.resolve(strict=True)),
                "--output",
                str(output / _identifier()),
            ],
        ),
        environment,
        root / "snapshot/sources" / manifest["coordinator"],
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--scope")
    action.add_argument("--compare", nargs=2, type=Path)
    parser.add_argument("--check-environment", action="store_true")
    args = parser.parse_args(argv)
    if args.compare and args.check_environment:
        parser.error("Check mode is only for run scopes")
    try:
        if args.compare:
            return compare_experiment(args.experiment, *args.compare)
        return run_scope(
            args.experiment, args.scope, check_environment=args.check_environment
        )
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ) as error:
        print(f"Experiment refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
