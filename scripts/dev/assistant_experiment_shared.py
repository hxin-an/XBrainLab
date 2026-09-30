"""Bind shared read-only resources; all execution state stays in the copied package."""

# ruff: noqa: S603 -- fixed interpreter and frozen adapter argv, no shell.

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.dev.assistant_experiment_portable import (
    _platform,
    installed_versions,
    runtime_environment,
)

SCHEMA = "xbrainlab.assistant_shared_environment.v1"
INSTRUCTIONS = """# Frozen experiment with shared read-only resources

Copy this package into your own writable directory on the same Linux workstation/NAS.
Python and models remain shared, version-pinned, readable/executable resources.
They are not included in this copy and must not be removed or upgraded in place.
No credentials or producer's private runtime files are needed.

    ./run.sh --check-environment   # checks only; no inference or new run
    ./run.sh                       # full frozen scope, new runs/<id>/ each time
    ./compare.sh /path/run-a /path/run-b

Each model's candidate index and source commit are in inputs/config.json;
complete sources, scorer, inputs and environment specifications are sealed here.
Do not modify them or substitute the current main branch. Select a new package
for a changed configuration. Historical results retain their original identity.
Check mode checks environment versions/resource access, not CUDA or model quality;
the runner checks full model hashes before inference.

Only .runtime/, runs/ and comparisons/ in your copy are writable outputs. Cache,
logs and temporary files do not go to the shared environment/model locations.
Environment variables are set automatically and conflicting Python overrides removed.
There is no installation, download, silent fallback or new environment creation.
System Python/Git/prlimit/timeout and an accessible fixed shared Python are required.
The leaf command retains a 18000-second wall guard and disables core dumps.
Coordinate GPU access: the existing GPU lock is per user, not a reservation service.
Keep the terminal connected or use your own tmux session. An interrupted run is not
a complete measurement; moving partial runs does not make them resumable.

Scope/budget approval is still required before inference. Check mode does not grant it.
Sharing code/data/models requires appropriate recipient access and license rights.
This entry does not chmod user directories or promise arbitrary-machine portability.
"""


def _probe(python: Path, environment: dict[str, str]) -> dict:
    result = subprocess.check_output(
        [str(python), "-I", "-B", str(Path(__file__).resolve()), "--describe"],
        env=environment,
        text=True,
        timeout=60,
    )
    return json.loads(result)


def environment_binding(python: Path) -> dict:
    # Do not resolve bin/python to the base executable: pyvenv.cfg selects the venv.
    python = python.absolute()
    if not python.is_file() or not os.access(python, os.X_OK):
        raise ValueError("Shared Python is not accessible/executable")
    environment = dict(os.environ)
    for name in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
        environment.pop(name, None)
    return {
        "schema": SCHEMA,
        "python": str(python),
        "identity": _probe(python, environment),
    }


def prepare_binding(package: Path, python: Path, *, notes: str = "") -> Path:
    value = environment_binding(python)
    path = package / "environment/shared.json"
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    config = json.loads((package / "inputs/config.json").read_text())
    rows = [
        f"\n## Frozen {config['split']} candidate mapping\n",
        "| Model | Candidate | Source commit |",
        "| --- | --- | --- |",
        *[
            f"| {model['alias']} | {model['candidate_index']} | `{model['source']['head']}` |"
            for model in config["models"]
        ],
        "\n## Adjustment rationale and affected models\n",
        notes.strip()
        or "No adjustment notes supplied; config/source define execution.",
    ]
    (package / "README.md").write_text(
        INSTRUCTIONS + "\n".join(rows) + "\n", encoding="utf-8"
    )
    return path


def check_environment(
    package: Path, value: dict, configs: list[dict]
) -> tuple[Path, dict]:
    """Validate fixed shared resources; writable state is confined to this copy."""
    if value.get("schema") != SCHEMA:
        raise ValueError("Invalid shared environment binding")
    python = Path(value["python"])
    if (
        not python.is_absolute()
        or not python.is_file()
        or not os.access(python, os.X_OK)
    ):
        raise ValueError("Shared Python environment is missing or not executable")
    environment = runtime_environment(package)
    if _probe(python, environment) != value["identity"]:
        raise ValueError("Shared environment differs from the frozen identity")
    for root in {
        root
        for config in configs
        for root in [
            config["embedding_cache"],
            *(m["model_cache"] for m in config["models"]),
        ]
    }:
        if not Path(root).is_dir() or not os.access(root, os.R_OK | os.X_OK):
            raise ValueError(f"Shared resource directory is not readable: {root}")
    limiter = shutil.which("prlimit")
    if limiter is None or shutil.which("timeout") is None:
        raise ValueError("prlimit and timeout are required for bounded execution")
    return python, environment


def bootstrap(package: Path, entry: str, arguments: list[str]) -> int:
    from scripts.dev.assistant_experiment_package import verify_package

    package = package.resolve(strict=True)
    manifest = verify_package(package)
    if entry not in {"launch", "compare"}:
        raise ValueError("Invalid shared environment entry")
    python, environment = check_environment(
        package,
        json.loads((package / "environment/shared.json").read_text()),
        [json.loads((package / "inputs/config.json").read_text())],
    )
    if entry == "launch" and arguments == ["--check-environment"]:
        print(
            f"Shared environment ready: {python}\nNo inference or experiment run was started."
        )
        return 0
    script = (
        package
        / "sources"
        / manifest["coordinator"]
        / "scripts/dev/assistant_experiment_package.py"
    )
    os.execve(  # noqa: S606 -- replace adapter with bounded, frozen runner; no shell.
        shutil.which("prlimit"),
        [
            shutil.which("prlimit"),
            "--core=0",
            "timeout",
            "--signal=TERM",
            "--kill-after=60s",
            "18000",
            str(python),
            "-I",
            "-B",
            str(script),
            entry,
            "--package",
            str(package),
            *arguments,
        ],
        environment,
    )


def main() -> int:
    if sys.argv[1:] == ["--describe"]:
        print(json.dumps({"platform": _platform(), "packages": installed_versions()}))
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--entry", choices=("launch", "compare"), required=True)
    args, forwarded = parser.parse_known_args()
    return bootstrap(args.package, args.entry, forwarded)


if __name__ == "__main__":
    raise SystemExit(main())
