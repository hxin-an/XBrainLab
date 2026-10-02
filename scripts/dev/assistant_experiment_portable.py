"""Offline, same-host experiment distribution; execution stays in the runner.

Build from an already verified environment/cache. Bootstrap needs only system
Python and Git, never credentials, network access, or the producer's home.
"""

# Fixed subprocess arguments, no shell; cache metadata is validated before use.
# ruff: noqa: S603

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import venv
from pathlib import Path, PurePosixPath

SCHEMA = "xbrainlab.assistant_portable_environment.v1"
INSTRUCTIONS = """# Portable experiment bundle (same workstation 137)

Copy this entire distribution into your own writable NAS directory. Log in to
workstation 137, ensure the GPU is available/reserved, then run:

    ./run.sh --check-environment   # offline setup only; no inference
    ./run.sh                       # executes the sealed experiment schedule
    ./compare.sh /path/run-a /path/run-b

Do not start the research schedule until its scope/budget has been approved.
The GPU lock is per user, not a cross-user reservation system. Coordinate GPU
access with other workstation users; no job scheduler is installed by this pack.

System Python and Git are prerequisites on the same Linux host. Exact Python,
platform and installed package versions are recorded in environment/portable.json.
Models/embedding and offline wheels are included; network access, credentials,
the producer's Python environment and their home directory are not required.
The first launch creates a private .runtime/env-* from pinned wheel hashes.
Later launches reuse it and reject changed package versions. A different copied
path/user gets its own new environment, never reuses the producer's venv.
There is no fallback download, model substitution or automatic package upgrade.

sources/, inputs/, models/, environment/, manifest.json and the entry scripts
are immutable experiment inputs. Treat this as trusted executable code, not as
a safe sandbox for arbitrary bundles. Verify the supplied manifest/source identity.
config-original.json is provenance only; the sealed config uses package-relative
resource paths. Reconfiguration requires a new package, not editing this one.
Model file hashes are verified by the existing runner before inference starts.

Outputs use runs/<new-id>/, comparisons/<new-id>/ and .runtime/ only. Each launch
gets a new run unless --resume RUN_ID is explicitly requested. Comparisons are
read-only for their inputs; explicit --output must be under this pack's comparisons/.
Resume requires the original execution paths/environment, not a relocated old run.
Do not modify historical manifests to make an old run resumable after moving it.

Prefer distributing the clean bundle before first use: .runtime/ and runs/ from
an already used copy are unnecessary for a new experiment and may contain private
diagnostics. They are not automatically deleted. Incomplete installation is kept
for diagnosis; use a fresh distribution copy rather than silently repairing it.
Environment checking alone does not validate CUDA/model inference or prove exact
output reproduction. This pack does not support arbitrary hosts/OS/GPU platforms.

Distribute only to recipients authorized for the included model licenses and
research data; this tool does not grant model access or redistribution rights.
"""


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _write(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise ValueError("Invalid installed distribution name/version")
    return re.sub(r"[-_.]+", "-", value).lower()


def installed_versions() -> dict[str, str]:
    result = {}
    for distribution in importlib.metadata.distributions():
        if distribution.read_text("direct_url.json") is not None:
            raise ValueError(
                "Portable environment cannot contain editable/direct URL installs"
            )
        name, version = _name(distribution.metadata["Name"]), distribution.version
        if name in result or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.!+_-]*", version):
            raise ValueError("Duplicate or invalid installed distribution")
        result[name] = version
    return result


def _platform() -> dict:
    return {
        "python": list(sys.version_info[:3]),
        "implementation": platform.python_implementation(),
        "system": platform.system(),
        "machine": platform.machine(),
        "libc": list(platform.libc_ver()),
    }


def _relative(value: str) -> Path:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in value
        or ":" in value
        or str(path) != value
    ):
        raise ValueError("Invalid portable resource path")
    return Path(value)


def _copy_verified(source: Path, target: Path, identity: dict) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    digest, size = hashlib.sha256(), 0
    with source.open("rb") as incoming, target.open("xb") as outgoing:
        for chunk in iter(lambda: incoming.read(8 * 1024 * 1024), b""):
            size += len(chunk)
            if size > identity["bytes"]:
                raise ValueError("Resource grew during portable copy")
            outgoing.write(chunk)
            digest.update(chunk)
    if size != identity["bytes"] or digest.hexdigest() != identity["sha256"]:
        raise ValueError("Portable resource differs from frozen inventory")


def _copy_models(package: Path, config: dict, base: Path) -> None:
    from scripts.dev.assistant_experiment_config import MODELS

    inventory = json.loads((base / config["resource_inventory"]).read_text())
    entries = inventory["resources"]
    indexed = {entry["repo"]: entry for entry in entries}
    if len(indexed) != len(entries):
        raise ValueError("Duplicate portable model resource")
    embeddings = set(indexed) - set(MODELS.values())
    if len(embeddings) != 1:
        raise ValueError("Exactly one embedding inventory is required")
    caches = {MODELS[item["alias"]]: item["model_cache"] for item in config["models"]}
    caches[embeddings.pop()] = config["embedding_cache"]
    for repo, cache in caches.items():
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or repo not in indexed:
            raise ValueError("Invalid or missing portable model repository")
        entry = indexed[repo]
        if not re.fullmatch(r"[0-9a-f]{40}", entry["revision"]):
            raise ValueError("Portable model needs an exact revision")
        root = (base / cache).resolve(strict=True)
        relative = (
            Path("models--" + repo.replace("/", "--")) / "snapshots" / entry["revision"]
        )
        files = entry["files"]
        if not isinstance(files, dict) or not 1 <= len(files) <= 4096:
            raise ValueError("Invalid portable model file inventory")
        print(f"Copying pinned resource: {repo}", flush=True)
        for name, identity in files.items():
            item = _relative(name)
            source = (root / relative / item).resolve(strict=True)
            if not source.is_relative_to(root) or not source.is_file():
                raise ValueError("Model resource escapes its original cache")
            if (
                set(identity) != {"bytes", "sha256"}
                or type(identity["bytes"]) is not int
                or identity["bytes"] < 0
                or not re.fullmatch(r"[0-9a-f]{64}", identity["sha256"])
            ):
                raise ValueError("Invalid portable model file identity")
            _copy_verified(source, package / "models" / relative / item, identity)


def prepare_assets(
    package: Path, config: dict, config_base: Path, wheel_cache: Path
) -> Path:
    """Copy only inventoried model files and exact installed-version wheels."""
    from pip._vendor.packaging.tags import sys_tags
    from pip._vendor.packaging.utils import parse_wheel_filename

    if sys.platform != "linux":
        raise ValueError("Portable bundles currently target same-host Linux only")
    versions, tags = installed_versions(), set(sys_tags())
    if "pip" not in versions:
        raise ValueError("Include the exact installed pip wheel for offline bootstrap")
    selected = {}
    for path in sorted(wheel_cache.resolve(strict=True).rglob("*.whl")):
        name, version, _, compatible = parse_wheel_filename(path.name)
        if name in versions and str(version) == versions[name] and tags & compatible:
            if name in selected and _digest(path) != _digest(selected[name]):
                raise ValueError("Ambiguous wheels for installed distribution: " + name)
            selected[name] = path
    if set(selected) != set(versions):
        raise ValueError(
            "Missing exact offline wheels: "
            + ", ".join(sorted(set(versions) - set(selected)))
        )
    wheels = package / "environment/wheels"
    wheels.mkdir()
    records, requirements = {}, []
    for name, source in sorted(selected.items()):
        target = wheels / source.name
        shutil.copyfile(source, target)
        identity = {"sha256": _digest(target), "bytes": target.stat().st_size}
        records[source.name] = {**identity, "name": name, "version": versions[name]}
        requirements.append(
            f"{name}=={versions[name]} --hash=sha256:{identity['sha256']}"
        )
    (package / "environment/requirements.txt").write_text(
        "\n".join(requirements) + "\n"
    )
    _copy_models(package, config, config_base)
    metadata = package / "environment/portable.json"
    _write(metadata, {"schema": SCHEMA, "platform": _platform(), "wheels": records})
    (package / "README.md").write_text(INSTRUCTIONS, encoding="utf-8")
    return metadata


def validate_layout(package: Path) -> dict:
    metadata = json.loads((package / "environment/portable.json").read_text())
    if (
        set(metadata) != {"schema", "platform", "wheels"}
        or metadata["schema"] != SCHEMA
    ):
        raise ValueError("Invalid portable environment manifest")
    wheels = metadata["wheels"]
    if not isinstance(wheels, dict) or not 1 <= len(wheels) <= 1024:
        raise ValueError("Invalid portable wheel inventory")
    actual = set()
    for name, record in wheels.items():
        if _relative(name).name != name or not name.endswith(".whl"):
            raise ValueError("Invalid portable wheel filename")
        if set(record) != {"name", "version", "bytes", "sha256"}:
            raise ValueError("Invalid portable wheel identity")
        actual.add(name)
    if actual != {path.name for path in (package / "environment/wheels").iterdir()}:
        raise ValueError("Portable wheel inventory differs")
    for directory in ("models", "environment/wheels"):
        root = package / directory
        if not root.is_dir() or root.is_symlink():
            raise ValueError("Portable assets must be physical package directories")
        for path in root.rglob("*"):
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                raise ValueError(
                    "Portable assets cannot link outside the copied package"
                )
    return metadata


def _runtime_directory(package: Path) -> Path:
    runtime = package / ".runtime"
    if runtime.is_symlink():
        raise ValueError("Portable runtime must not be a symlink")
    runtime.mkdir(mode=0o700, exist_ok=True)
    if runtime.stat().st_uid != os.getuid():
        raise ValueError("Portable runtime must belong to the executing user")
    return runtime


def _environment(
    package: Path, metadata: dict, runtime: Path, environment: dict
) -> Path:
    """Install once per copied path/user, with an exclusive bounded bootstrap lock."""
    import fcntl

    identity = {
        "root": str(package),
        "uid": os.getuid(),
        "manifest": _digest(package / "environment/portable.json"),
    }
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    target, receipt = runtime / f"env-{key}", runtime / f"installed-{key}.json"
    lock = runtime / "bootstrap.lock"
    if lock.is_symlink() or target.is_symlink() or receipt.is_symlink():
        raise ValueError("Portable environment paths must not be symlinks")
    with lock.open("a") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError(
                "Another process is preparing this copied environment"
            ) from error
        python = target / "bin/python"
        if receipt.exists():
            if json.loads(receipt.read_text()) != identity or not python.is_file():
                raise ValueError("Installed portable environment identity differs")
            _verify_installed(python, metadata, environment)
            return python
        if target.exists():
            raise ValueError(
                f"Incomplete environment retained at {target}; use a fresh distribution copy"
            )
        for name, record in metadata["wheels"].items():
            path = package / "environment/wheels" / name
            if (
                path.stat().st_size != record["bytes"]
                or _digest(path) != record["sha256"]
            ):
                raise ValueError("Offline wheel checksum differs: " + name)
        pip_wheels = [
            name
            for name, record in metadata["wheels"].items()
            if record["name"] == "pip"
        ]
        if len(pip_wheels) != 1:
            raise ValueError("Exactly one pinned pip wheel is required")
        print(
            "Building private environment from bundled offline wheels (first launch only).",
            flush=True,
        )
        venv.EnvBuilder(with_pip=False).create(target)
        # Ubuntu's system Python need not provide ensurepip. Use our pinned pip
        # wheel directly, isolated from user-site and network package indexes.
        command = [
            str(python),
            "-I",
            "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); from pip._internal.cli.main import main; sys.exit(main(sys.argv[2:]))",
            str(package / "environment/wheels" / pip_wheels[0]),
        ]
        subprocess.run(
            [
                *command,
                "--isolated",
                "--disable-pip-version-check",
                "--no-cache-dir",
                "install",
                "--no-index",
                "--no-deps",
                "--only-binary=:all:",
                "--require-hashes",
                "--find-links",
                str(package / "environment/wheels"),
                "-r",
                str(package / "environment/requirements.txt"),
            ],
            check=True,
            timeout=1800,
            env=environment,
        )
        subprocess.run(
            [str(python), "-I", "-m", "pip", "--isolated", "check"],
            check=True,
            timeout=60,
            env=environment,
        )
        _verify_installed(python, metadata, environment)
        _write(receipt, identity)
        return python


def _verify_installed(python: Path, metadata: dict, environment: dict) -> None:
    result = subprocess.check_output(
        [
            str(python),
            "-I",
            "-c",
            "import importlib.metadata as m, json; print(json.dumps([(d.metadata['Name'], d.version) for d in m.distributions()]))",
        ],
        text=True,
        timeout=30,
        env=environment,
    )
    pairs = json.loads(result)
    actual = {_name(name): version for name, version in pairs}
    expected = {
        record["name"]: record["version"] for record in metadata["wheels"].values()
    }
    if len(actual) != len(pairs) or actual != expected:
        raise ValueError(
            "Installed environment differs from the bundled pinned versions"
        )


def runtime_environment(package: Path) -> dict[str, str]:
    """Keep every runtime/cache write in the executing user's physical copy."""
    runtime = _runtime_directory(package)
    cache = runtime / "cache"
    if cache.is_symlink():
        raise ValueError("Portable cache must not be a symlink")
    cache.mkdir(exist_ok=True)
    environment = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "XBL_PYTHON"):
        environment.pop(key, None)
    environment.update(
        PYTHONNOUSERSITE="1",
        PYTHONDONTWRITEBYTECODE="1",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        QT_QPA_PLATFORM="offscreen",
        XDG_CACHE_HOME=str(cache),
        HF_HOME=str(cache / "huggingface"),
        MPLCONFIGDIR=str(cache / "matplotlib"),
        CUDA_CACHE_PATH=str(cache / "cuda"),
        NUMBA_CACHE_DIR=str(cache / "numba"),
        TORCH_HOME=str(cache / "torch"),
        TMPDIR=str(cache / "tmp"),
        PIP_CONFIG_FILE=os.devnull,
    )
    for variable, name in (
        ("XBRAINLAB_CONFIG_DIR", "config"),
        ("XBRAINLAB_LOG_DIR", "logs"),
        ("XBRAINLAB_CACHE_DIR", "app"),
        ("XBRAINLAB_DATA_DIR", "data"),
    ):
        environment[variable] = str(cache / name)
    for name in (
        "huggingface",
        "matplotlib",
        "cuda",
        "numba",
        "torch",
        "tmp",
        "config",
        "logs",
        "app",
        "data",
    ):
        child = cache / name
        if child.is_symlink():
            raise ValueError("Portable cache children must not be symlinks")
        child.mkdir(exist_ok=True)
    # A copied cache may contain nested links from its previous location. Do not
    # let ordinary library writes follow them back into the original user's files.
    for path in cache.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Runtime cache must not contain symlinks: {path}")
    return environment


def bootstrap(package: Path, entry: str, arguments: list[str]) -> int:
    from scripts.dev.assistant_experiment_package import verify_package

    package = package.resolve(strict=True)
    manifest = verify_package(package)
    metadata = validate_layout(package)
    if _platform() != metadata["platform"]:
        raise ValueError(
            "Use the bundle's exact system Python/platform on workstation 137"
        )
    if entry not in {"launch", "compare"}:
        raise ValueError("Unknown portable entry")
    environment = runtime_environment(package)
    runtime = package / ".runtime"
    python = _environment(package, metadata, runtime, environment)
    if entry == "launch" and arguments == ["--check-environment"]:
        print(
            f"Offline environment ready: {python}\nNo inference or experiment run was started."
        )
        return 0
    script = (
        package
        / "sources"
        / manifest["coordinator"]
        / "scripts/dev/assistant_experiment_package.py"
    )
    os.execve(  # noqa: S606 - replace bootstrap with the verified local interpreter.
        str(python),
        [str(python), "-I", str(script), entry, "--package", str(package), *arguments],
        environment,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--entry", choices=("launch", "compare"), required=True)
    args, forwarded = parser.parse_known_args()
    return bootstrap(args.package, args.entry, forwarded)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    raise SystemExit(main())
