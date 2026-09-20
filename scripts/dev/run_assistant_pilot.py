"""Sequential, frozen DEV Pilot parent; never retries a started measurement.

Use --list or --prepare before committing the complete research implementation.
Only --run executes cases, each in its own ordinary-product child process.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from uuid import uuid4

from scripts.dev.assistant_pilot_bank import build_pilot_selection, load_bank
from scripts.dev.assistant_pilot_models import (
    make_launch_spec,
    research_model_spec,
    research_template_kwargs,
)
from scripts.dev.assistant_pilot_rag import (
    _identity,
    prepare_rag_cache,
    verify_rag_cache,
)
from XBrainLab.llm.rag.config import RAGConfig

_WINDOWS_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
SCHEMA = "xbrainlab.assistant_pilot_run.v2"
ROOT = Path(__file__).resolve().parents[2]
BUDGET_SECONDS = 14_400
CHILD_TIMEOUT_SECONDS = 450
CONDITION_TIMEOUT_SECONDS = 1_800
_MODELS = {
    "granite4": "ibm-granite/granite-4.0-micro",
    "granite33": "ibm-granite/granite-3.3-2b-instruct",
    "phi4": "microsoft/Phi-4-mini-instruct",
    "llama32": "meta-llama/Llama-3.2-3B-Instruct",
    "gemma3": "google/gemma-3-4b-it",
}
CONDITIONS = {
    f"{alias}-rag-{label}": (model, enabled)
    for alias, model in _MODELS.items()
    for label, enabled in (("on", True), ("off", False))
}


def select_conditions(value: str) -> list[str]:
    requested = list(CONDITIONS) if value == "all" else value.split(",")
    if (
        not requested
        or len(set(requested)) != len(requested)
        or set(requested) - CONDITIONS.keys()
    ):
        raise ValueError("Unknown or duplicate Pilot condition")
    return [condition for condition in CONDITIONS if condition in requested]


def build_jobs(selection: dict, conditions: list[str]) -> list[dict]:
    return [
        {
            "id": f"{condition}__{case}",
            "condition": condition,
            "case_id": case,
            "phase": phase,
        }
        for phase, key in ((1, "phase_one_case_ids"), (2, "phase_two_case_ids"))
        for condition in conditions
        for case in selection[key]
    ]


def condition_batches(jobs: list[dict]) -> list[dict]:
    """Group the frozen matrix by runtime condition, preserving case order."""
    batches: dict[str, list[dict]] = {}
    for job in jobs:
        batches.setdefault(job["condition"], []).append(job)
    return [
        {"condition": condition, "jobs": batch} for condition, batch in batches.items()
    ]


def _git(*args: str) -> str:
    return subprocess.check_output(  # noqa: S603 - fixed internal read-only Git arguments
        [_executable("git"), *_git_location(), *args], text=True, timeout=15
    ).strip()


def _git_location() -> list[str]:
    """Read this checkout's exact WSL gitdir from Windows, without rewriting it."""
    gitfile = ROOT / ".git"
    if os.name == "nt" and gitfile.is_file():
        match = re.fullmatch(
            r"gitdir: /mnt/([a-zA-Z])/(.+)", gitfile.read_text(encoding="utf-8").strip()
        )
        if match:
            drive, relative = match.groups()
            gitdir = Path(f"{drive.upper()}:/{relative}").resolve(strict=True)
            if not gitdir.is_dir():
                raise ValueError("The checkout gitdir is not a directory")
            return [f"--git-dir={gitdir}", f"--work-tree={ROOT}"]
    return ["-C", str(ROOT)]


def _executable(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise ValueError(f"Required executable is unavailable: {name}")
    return path


def source_identity() -> dict:
    dirty = set(filter(None, _git("diff", "--name-only", "HEAD", "-z").split("\0")))
    for name in _git("ls-files", "--others", "--exclude-standard", "-z").split("\0"):
        if name and (
            name.split("/")[0] in {"XBrainLab", "scripts", "tests", "docs"}
            or Path(name).suffix in {".py", ".toml", ".lock", ".yaml", ".yml", ".json"}
        ):
            dirty.add(name)
    dirty.discard(
        "settings.json"
    )  # User-owned daily settings are never staged or changed.
    return {"head": _git("rev-parse", "HEAD"), "dirty": sorted(dirty)}


def environment_identity() -> dict:
    versions = sorted(
        {
            (distribution.metadata["Name"], distribution.version)
            for distribution in metadata.distributions()
            if distribution.metadata["Name"]
        }
    )
    try:
        gpu = (
            subprocess.check_output(  # noqa: S603 - fixed read-only hardware query
                [
                    _executable("nvidia-smi"),
                    "--query-gpu=name,uuid,memory.total,driver_version",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                timeout=15,
            )
            .strip()
            .splitlines()
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(
            "Pilot hardware identity requires an available NVIDIA query"
        ) from exc
    return {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": [list(item) for item in versions],
        "gpus": gpu,
    }


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def _write_new(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as target:
        json.dump(
            value, target, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        )
        target.flush()
        os.fsync(target.fileno())


def _append(output: Path, event: dict) -> None:
    with (output / "journal.jsonl").open("a", encoding="utf-8") as target:
        target.write(json.dumps(event, sort_keys=True, allow_nan=False) + "\n")
        target.flush()
        os.fsync(target.fileno())


def read_journal(output: Path) -> list[dict]:
    path = output / "journal.jsonl"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if text and not text.endswith("\n"):
        raise ValueError("Truncated journal; preserve and inspect before resume")
    records = [json.loads(line) for line in text.splitlines()]
    if any(not isinstance(record, dict) or "event" not in record for record in records):
        raise ValueError("Invalid journal")
    return records


def consumed_seconds(records: list[dict]) -> float:
    """Charge observed session time; unfinished children retain conservative reservations."""
    elapsed, pending = {}, {}
    for record in records:
        session = record["session"]
        seconds = record["elapsed_seconds"]
        if (
            not isinstance(seconds, (int, float))
            or not math.isfinite(seconds)
            or seconds < 0
        ):
            raise ValueError("Invalid elapsed time in preserved journal")
        elapsed[session] = max(elapsed.get(session, 0), seconds)
        if record["event"] in {"case_start", "condition_start"}:
            pending[(record["event"], record["id"])] = (
                session,
                seconds
                + record.get(
                    "timeout_seconds",
                    CHILD_TIMEOUT_SECONDS
                    if record["event"] == "case_start"
                    else CONDITION_TIMEOUT_SECONDS,
                ),
            )
        elif record["event"] in {"case_end", "condition_end"}:
            start = "case_start" if record["event"] == "case_end" else "condition_start"
            pending.pop((start, record["id"]), None)
    for session, reserved in pending.values():
        elapsed[session] = max(elapsed[session], reserved)
    return sum(elapsed.values())


def _assert_identity(manifest: dict) -> None:
    source = source_identity()
    if (
        source["dirty"]
        or source != manifest["source"]
        or environment_identity() != manifest["environment"]
    ):
        raise ValueError("Pilot requires the exact clean source/environment identity")


def _python_executable() -> str:
    # Windows venv python.exe is a redirector: its PID is not the executing Python.
    # The child-only launcher hint preserves pyvenv.cfg resolution for the base exe.
    return sys._base_executable if os.name == "nt" else sys.executable


def _child_environment() -> dict[str, str]:
    environment = dict(os.environ)
    if os.name == "nt":
        environment["__PYVENV_LAUNCHER__"] = sys.executable
    return environment


def _child_creation_flags(platform: str = os.name) -> int:
    """Keep per-case Windows interpreters off the interactive desktop."""
    return _WINDOWS_CREATE_NO_WINDOW if platform == "nt" else 0


def _case_command(request: Path, destination: Path) -> list[str]:
    return [
        _python_executable(),
        "-m",
        "scripts.dev.assistant_pilot_case",
        "--request",
        str(request),
        "--output",
        str(destination),
    ]


def _condition_command(request: Path, destination: Path, cases_root: Path) -> list[str]:
    return [
        _python_executable(),
        "-m",
        "scripts.dev.assistant_pilot_condition",
        "--request",
        str(request),
        "--cases-root",
        str(cases_root),
        "--output",
        str(destination),
    ]


def _run_child(
    request: Path, destination: Path, timeout: float, *, on_started
) -> tuple[int, bool]:
    """Terminate only the process created here; uncertified descendants block resume."""
    with (
        request.with_suffix(".stdout.log").open("xb") as stdout,
        request.with_suffix(".stderr.log").open("xb") as stderr,
    ):
        process = subprocess.Popen(  # noqa: S603 - fixed child module, shell disabled
            _case_command(request, destination),
            cwd=ROOT,
            stdout=stdout,
            stderr=stderr,
            env=_child_environment(),
            creationflags=_child_creation_flags(),
        )
        try:
            on_started(process.pid)
            return process.wait(timeout=max(0.01, timeout - 10)), False
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            return process.returncode, True
        except BaseException:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            raise


def _run_condition_child(
    request: Path,
    destination: Path,
    cases_root: Path,
    timeout: float,
    *,
    on_started,
) -> tuple[int, bool]:
    """Run one model/RAG condition without exposing a Windows console."""
    with (
        request.with_suffix(".stdout.log").open("xb") as stdout,
        request.with_suffix(".stderr.log").open("xb") as stderr,
    ):
        process = subprocess.Popen(  # noqa: S603 - fixed child module, shell disabled
            _condition_command(request, destination, cases_root),
            cwd=ROOT,
            stdout=stdout,
            stderr=stderr,
            env=_child_environment(),
            creationflags=_child_creation_flags(),
        )
        try:
            on_started(process.pid)
            return process.wait(timeout=max(0.01, timeout - 10)), False
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            return process.returncode, True
        except BaseException:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            raise


def execute(
    manifest: dict,
    bank: dict,
    output: Path,
    *,
    resume: bool = False,
    started_at: float | None = None,
) -> int:
    started = time.monotonic() if started_at is None else started_at
    _assert_identity(manifest)
    output = output.absolute()
    if resume:
        if _json(output / "manifest.json") != manifest:
            raise ValueError("Frozen manifest mismatch; existing run preserved")
        records = read_journal(output)
        if records and (
            records[-1]["event"] != "session_end"
            or not records[-1].get("cleanup_certified")
        ):
            raise ValueError(
                "Unresolved session/cleanup; inspect owned processes before resume"
            )
    else:
        output.mkdir()
        _write_new(output / "manifest.json", manifest)
        (output / "cases").mkdir()
        (output / "conditions").mkdir()
        records = []
    starts = {
        record["id"] for record in records if record["event"] == "condition_start"
    }
    ends = {
        record["id"]: record for record in records if record["event"] == "condition_end"
    }
    if starts - ends.keys():
        raise ValueError(
            "Unresolved started conditions must never be resent automatically"
        )
    consumed = consumed_seconds(records)
    session = uuid4().hex

    def journal(event: str, **values):
        _append(
            output,
            {
                "event": event,
                "session": session,
                "elapsed_seconds": time.monotonic() - started,
                "timestamp_utc": datetime.now(UTC).isoformat(),
                **values,
            },
        )

    journal("session_start", prior_charged_seconds=consumed)
    cleanup_certified, outcome = True, 0
    try:
        if (
            consumed + time.monotonic() - started + CONDITION_TIMEOUT_SECONDS
            > BUDGET_SECONDS
        ):
            journal("budget_exhausted")
            return 2
        rag_root = None
        if any(CONDITIONS[job["condition"]][1] for job in manifest["jobs"]):
            preparation = output / "rag-preparation.json"
            if resume:
                storage = _json(preparation)
                verify_rag_cache(storage)
            else:
                storage = prepare_rag_cache(
                    output / "rag",
                    embedding_cache=Path(manifest["config"]["embedding_cache"]),
                    expected_embedding_sha256=manifest["embedding_sha256"],
                )
                _write_new(preparation, storage)
            rag_root = storage["cache_root"]
            journal(
                "rag_storage_prepared", embedding_sha256=storage["embedding_sha256"]
            )
        cases = {
            case["case_id"]: case for case in bank["cases"] if case["split"] == "DEV"
        }
        batches = condition_batches(manifest["jobs"])
        for batch in batches:
            condition = batch["condition"]
            if condition in starts:
                continue
            if (
                consumed + time.monotonic() - started + CONDITION_TIMEOUT_SECONDS
                > BUDGET_SECONDS
            ):
                journal("budget_exhausted")
                outcome = 2
                break
            _assert_identity(manifest)
            model, rag_enabled = CONDITIONS[condition]
            jobs = []
            for job in batch["jobs"]:
                case = cases[job["case_id"]]
                payload = {
                    "case": case,
                    "fixture": bank["fixtures"][case["fixture_id"]],
                    "model_id": model,
                    "model_cache": manifest["config"]["model_caches"][model],
                    "rag_enabled": rag_enabled,
                    "rag_cache": rag_root if rag_enabled else None,
                    "seed": 0,
                    "repeat": 0,
                }
                case_request = output / "cases" / f"{job['id']}.request.json"
                _write_new(case_request, payload)
                jobs.append(
                    {
                        "id": job["id"],
                        "payload": payload,
                        "request_sha256": hashlib.sha256(
                            case_request.read_bytes()
                        ).hexdigest(),
                    }
                )
            condition_payload = {
                "schema": "xbrainlab.assistant_pilot_condition.v1",
                "condition": condition,
                "jobs": [
                    {"id": item["id"], "payload": item["payload"]} for item in jobs
                ],
            }
            destination = output / "conditions" / condition
            request = destination.with_suffix(".request.json")
            _write_new(request, condition_payload)
            journal(
                "condition_start",
                id=condition,
                case_ids=[item["id"] for item in jobs],
                timeout_seconds=CONDITION_TIMEOUT_SECONDS,
                request_sha256=hashlib.sha256(request.read_bytes()).hexdigest(),
            )
            cleanup_certified = False
            code, timed_out = _run_condition_child(
                request,
                destination,
                output / "cases",
                CONDITION_TIMEOUT_SECONDS,
                on_started=lambda pid, condition_id=condition: journal(
                    "child_started", id=condition_id, pid=pid
                ),
            )
            result_path = destination / "result.json"
            result = _json(result_path) if result_path.exists() else {}
            cleanup_certified = result.get("cleanup_ok") is True and not timed_out
            status = (
                "recorded"
                if code == 0
                and result.get("status") == "recorded"
                and len(result.get("results", [])) == len(jobs)
                and cleanup_certified
                else "failed"
            )
            journal(
                "condition_end",
                id=condition,
                status=status,
                returncode=code,
                hard_timeout=timed_out,
                cleanup_certified=cleanup_certified,
                result_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest()
                if result_path.exists()
                else None,
            )
            completed = {item.get("id"): item for item in result.get("results", [])}
            for item in jobs:
                if item["id"] not in completed:
                    continue
                case_result_path = output / "cases" / item["id"] / "result.json"
                recorded = completed.get(item["id"], {})
                case_status = (
                    "recorded"
                    if recorded.get("status") == "recorded"
                    and recorded.get("cleanup_ok") is True
                    and case_result_path.is_file()
                    else "failed"
                )
                journal(
                    "case_start",
                    id=item["id"],
                    timeout_seconds=CHILD_TIMEOUT_SECONDS,
                    request_sha256=item["request_sha256"],
                )
                journal(
                    "case_end",
                    id=item["id"],
                    status=case_status,
                    returncode=0 if case_status == "recorded" else code,
                    hard_timeout=timed_out,
                    cleanup_certified=recorded.get("cleanup_ok") is True,
                    result_sha256=hashlib.sha256(
                        case_result_path.read_bytes()
                    ).hexdigest()
                    if case_result_path.is_file()
                    else None,
                )
            if status != "recorded":
                outcome = 1
                break
        if any(record["status"] != "recorded" for record in ends.values()):
            outcome = outcome or 1
    except BaseException as exc:
        journal("session_error", error_type=type(exc).__name__, detail=str(exc))
        raise
    finally:
        journal("session_end", cleanup_certified=cleanup_certified)
    return outcome


def _model_configuration(model: str, cache: str) -> dict:
    """Fingerprint the pinned tokenizer/template/config, without rereading GB weights."""
    spec = research_model_spec(model)
    snapshot = (
        Path(cache)
        / f"models--{model.replace('/', '--')}"
        / "snapshots"
        / spec.revision
    )
    if (
        not (snapshot / "config.json").is_file()
        or not (snapshot / "tokenizer_config.json").is_file()
    ):
        raise ValueError("Pinned model configuration/tokenizer snapshot is incomplete")
    files = sorted(
        path
        for path in snapshot.iterdir()
        if path.is_file() and path.suffix in {".json", ".jinja", ".model", ".txt"}
    )
    if len(files) > 64 or sum(path.stat().st_size for path in files) > 256 * 1024**2:
        raise ValueError("Unexpectedly large model configuration snapshot")
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}


def prepare_manifest(
    bank_path: Path, selection_path: Path, config_path: Path, conditions: list[str]
) -> tuple[dict, dict]:
    bank = load_bank(bank_path)
    selection = _json(selection_path)
    if selection != build_pilot_selection(bank):
        raise ValueError(
            "Selection does not match the approved deterministic DEV selection"
        )
    config = _json(config_path)
    selected_models = {CONDITIONS[condition][0] for condition in conditions}
    if set(config) - {"model_caches", "embedding_cache"}:
        raise ValueError("Unknown run configuration fields")
    caches = config.get("model_caches", {})
    if (
        not isinstance(caches, dict)
        or selected_models - caches.keys()
        or caches.keys() - set(_MODELS.values())
    ):
        raise ValueError("Explicit approved model cache mapping is required")
    for model in selected_models:
        path = Path(caches[model])
        if not path.is_absolute() or not path.is_dir():
            raise ValueError("Model cache must be an existing absolute directory")
    embedding_sha256 = None
    if any(CONDITIONS[condition][1] for condition in conditions):
        path = Path(config.get("embedding_cache", ""))
        if not path.is_absolute() or not RAGConfig.embedding_cache_ready(path):
            raise ValueError("RAG on requires an existing pinned embedding cache")
        embedding_sha256, _ = _identity(path.resolve(strict=True))
    models = {
        model: {
            "spec": asdict(research_model_spec(model)),
            "settings": asdict(make_launch_spec(model, caches[model]).settings),
            "template_kwargs": research_template_kwargs(model),
            "configuration_sha256": _model_configuration(model, caches[model]),
        }
        for model in sorted(selected_models)
    }
    if not RAGConfig.gold_set_integrity_ok():
        raise ValueError("Bundled retrieval corpus identity changed")
    decisions = {
        case["case_id"]: case["decision"]
        for case in bank["cases"]
        if case["split"] == "DEV"
    }
    # JSON normalization makes in-memory and restored manifests identical.
    manifest = {
        "schema": SCHEMA,
        "source": source_identity(),
        "environment": environment_identity(),
        "bank_sha256": bank["source"]["sha256"],
        "selection": selection,
        "config": config,
        "models": models,
        "jobs": [
            {**job, "decision": decisions[job["case_id"]]}
            for job in build_jobs(selection, conditions)
        ],
        "corpus_sha256": RAGConfig.GOLD_SET_SHA256,
        "embedding_sha256": embedding_sha256,
        "seed": 0,
        "repeat": 0,
        "budget_seconds": BUDGET_SECONDS,
        "child_timeout_seconds": CHILD_TIMEOUT_SECONDS,
        "condition_timeout_seconds": CONDITION_TIMEOUT_SECONDS,
    }
    return json.loads(json.dumps(manifest, allow_nan=False)), bank


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for mode in ("list", "prepare", "run"):
        modes.add_argument(f"--{mode}", action="store_true")
    parser.add_argument("--conditions", default="all")
    for name in ("bank", "selection", "config", "output"):
        parser.add_argument(f"--{name}", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    started = time.monotonic()
    if args.list:
        print(json.dumps(CONDITIONS, indent=2))
        return 0
    if not all((args.bank, args.selection, args.config)) or (
        args.run and args.output is None
    ):
        parser.error(
            "--bank, --selection, --config and (for --run) --output are required"
        )
    if args.resume and not args.run:
        parser.error("--resume requires --run")
    from scripts.dev.assistant_pilot_case import bootstrap_case_checkout

    bootstrap_case_checkout()
    manifest, bank = prepare_manifest(
        args.bank, args.selection, args.config, select_conditions(args.conditions)
    )
    if args.prepare:
        print(json.dumps(manifest, indent=2))
        return 0
    return execute(manifest, bank, args.output, resume=args.resume, started_at=started)


if __name__ == "__main__":
    raise SystemExit(main())
