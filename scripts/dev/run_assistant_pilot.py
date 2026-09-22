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
from pathlib import Path, PurePosixPath
from uuid import uuid4

from scripts.dev import assistant_experiment_config as experiment_config
from scripts.dev.assistant_pilot_bank import (
    DEV_EXPERIMENT,
    build_dev_selection,
    build_pilot_selection,
    load_bank,
)
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
_MODELS = experiment_config.MODELS
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
        batches.setdefault(experiment_config.job_condition_identity(job), []).append(
            job
        )
    return [
        {"condition": batch[0]["condition"], "jobs": batch}
        for batch in batches.values()
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
    if (
        manifest.get("experiment") == DEV_EXPERIMENT
        or experiment_config.is_experiment_protocol(manifest.get("experiment"))
    ) and os.environ.get("QT_QPA_PLATFORM") != DEV_EXPERIMENT["qt_platform"]:
        raise ValueError("DEV Qt platform must match the frozen offscreen identity")
    source = source_identity()
    if (
        source["dirty"]
        or source != manifest["source"]
        or environment_identity() != manifest["environment"]
    ):
        raise ValueError("Pilot requires the exact clean source/environment identity")
    if experiment_config.is_experiment_protocol(manifest.get("experiment")):
        for item in manifest["runtime_config"]["sources"].values():
            _verify_candidate_source(Path(item["root"]), item["head"])


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
        payload = _json(request)
        source_root = payload.get("source_root")
        environment = _child_environment()
        if source_root is not None:
            environment["PYTHONPATH"] = source_root
        process = subprocess.Popen(  # noqa: S603 - fixed child module, shell disabled
            _condition_command(request, destination, cases_root),
            cwd=source_root or ROOT,
            stdout=stdout,
            stderr=stderr,
            env=environment,
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


def valid_measurement(end: dict, result: dict) -> bool:
    """Incorrect answers and valid decision timeouts must never be resubmitted."""
    return (
        result.get("status") == "recorded" and result.get("cleanup_ok") is True
    ) or (end.get("status") == "recorded" and end.get("cleanup_certified") is True)


def _dev_pending_jobs(
    jobs: list[dict], records: list[dict], output: Path, replace_invalid: bool
) -> tuple[list[dict], bool]:
    """Audit prior immutable results before selecting missing/explicit replacement work."""
    ends = {record["id"]: record for record in records if record["event"] == "case_end"}
    pending, invalid_remaining = [], False
    for job in jobs:
        previous = ends.get(job["id"])
        attempt = 1
        replaces = None
        if previous is not None:
            artifact = previous.get("artifact_id", job["id"])
            result_path = output / "cases" / artifact / "result.json"
            if not result_path.is_file() or hashlib.sha256(
                result_path.read_bytes()
            ).hexdigest() != previous.get("result_sha256"):
                raise ValueError("Preserved case evidence changed; replacement refused")
            result = _json(result_path)
            if valid_measurement(previous, result):
                continue
            if previous.get("cleanup_certified") is not True:
                raise ValueError("Unresolved case cleanup; replacement refused")
            if not replace_invalid or previous.get("attempt", 1) >= 2:
                invalid_remaining = True
                continue
            attempt = 2
            replaces = artifact
        artifact = job["id"] if attempt == 1 else f"{job['id']}__attempt-{attempt}"
        if (output / "cases" / artifact).exists():
            raise ValueError("Unresolved case directory; inspect preserved evidence")
        pending.append(
            {
                **job,
                "artifact_id": artifact,
                "attempt": attempt,
                "replaces_artifact_id": replaces,
            }
        )
    return pending, invalid_remaining


def execute(
    manifest: dict,
    bank: dict,
    output: Path,
    *,
    resume: bool = False,
    started_at: float | None = None,
    replace_invalid: bool = False,
) -> int:
    if manifest.get(
        "experiment"
    ) == DEV_EXPERIMENT or experiment_config.is_experiment_protocol(
        manifest.get("experiment")
    ):
        from filelock import FileLock

        lock_path = output.absolute().with_name(f".{output.name}.dev.lock")
        with FileLock(str(lock_path), timeout=0):
            return _execute(
                manifest,
                bank,
                output,
                resume=resume,
                started_at=started_at,
                replace_invalid=replace_invalid,
            )
    return _execute(
        manifest,
        bank,
        output,
        resume=resume,
        started_at=started_at,
        replace_invalid=replace_invalid,
    )


def _execute(
    manifest: dict,
    bank: dict,
    output: Path,
    *,
    resume: bool = False,
    started_at: float | None = None,
    replace_invalid: bool = False,
) -> int:
    started = time.monotonic() if started_at is None else started_at
    configured = experiment_config.is_experiment_protocol(manifest.get("experiment"))
    if configured:
        selection = experiment_config.build_selection(bank, manifest["config"])
        expected_jobs = experiment_config.build_jobs(selection, manifest["config"])
        decisions = {case["case_id"]: case["decision"] for case in bank["cases"]}
        for job in expected_jobs:
            job["source_root"] = manifest["runtime_config"]["sources"][
                job["condition"].removesuffix("-rag-on")
            ]["root"]
            job["decision"] = decisions[job["case_id"]]
        if (
            manifest["experiment"]
            != experiment_config.experiment_identity(manifest["config"])
            or manifest["budget_seconds"] != manifest["config"]["budget_seconds"]
            or manifest["selection"] != selection
            or manifest["jobs"] != expected_jobs
        ):
            raise ValueError(
                "Experiment manifest differs from the derived config identity"
            )
    dev_initial = manifest.get("experiment") == DEV_EXPERIMENT or configured
    runtime_config = manifest.get("runtime_config", manifest["config"])
    budget_seconds = manifest["budget_seconds"] if configured else BUDGET_SECONDS
    if ("experiment" in manifest and not dev_initial) or (
        replace_invalid and (not dev_initial or not resume)
    ):
        raise ValueError("Replacement requires an explicit initial DEV resume")
    if dev_initial and any(
        not CONDITIONS[job["condition"]][1] for job in manifest["jobs"]
    ):
        raise ValueError("Initial DEV only permits RAG on")
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
    pending_jobs, invalid_remaining = (
        _dev_pending_jobs(manifest["jobs"], records, output, replace_invalid)
        if dev_initial
        else (manifest["jobs"], False)
    )
    if dev_initial and not pending_jobs:
        return int(invalid_remaining)
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
    cleanup_certified, outcome = True, int(invalid_remaining)
    minimum_reservation = (
        600 + CHILD_TIMEOUT_SECONDS if dev_initial else CONDITION_TIMEOUT_SECONDS
    )
    try:
        if consumed + time.monotonic() - started + minimum_reservation > budget_seconds:
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
                    embedding_cache=Path(runtime_config["embedding_cache"]),
                    expected_embedding_sha256=manifest["embedding_sha256"],
                )
                _write_new(preparation, storage)
            rag_root = storage["cache_root"]
            journal(
                "rag_storage_prepared", embedding_sha256=storage["embedding_sha256"]
            )
        cases = {
            case["case_id"]: case
            for case in bank["cases"]
            if case["split"]
            == (manifest["experiment"]["stage"] if configured else "DEV")
        }
        batches = condition_batches(pending_jobs)
        for batch in batches:
            condition = batch["condition"]
            condition_key = experiment_config.job_condition_identity(batch["jobs"][0])
            if not dev_initial and condition in starts:
                continue
            if (
                consumed + time.monotonic() - started + minimum_reservation
                > budget_seconds
            ):
                journal("budget_exhausted")
                outcome = 2
                break
            _assert_identity(manifest)
            condition_attempt = 1 + sum(
                record["event"] == "condition_start"
                and record.get("condition_key", record.get("condition", record["id"]))
                == condition_key
                for record in records
                if "id" in record
            )
            condition_artifact = (
                condition_key
                if condition_attempt == 1
                else f"{condition_key}__attempt-{condition_attempt}"
            )
            condition_timeout = (
                min(
                    budget_seconds - consumed - (time.monotonic() - started),
                    600 + len(batch["jobs"]) * CHILD_TIMEOUT_SECONDS,
                )
                if dev_initial
                else CONDITION_TIMEOUT_SECONDS
            )
            model, rag_enabled = CONDITIONS[condition]
            jobs = []
            for job in batch["jobs"]:
                case = cases[job["case_id"]]
                payload = {
                    "case": case,
                    "fixture": bank["fixtures"][case["fixture_id"]],
                    "model_id": model,
                    "model_cache": runtime_config["model_caches"][model],
                    "rag_enabled": rag_enabled,
                    "rag_cache": rag_root if rag_enabled else None,
                    "seed": 0,
                    "repeat": job.get("repeat", 0),
                }
                if dev_initial:
                    payload["experiment"] = dict(manifest["experiment"])
                if configured:
                    payload.update(
                        {
                            key: job[key]
                            for key in ("candidate_index", "split", "source_head")
                        }
                    )
                artifact = job.get("artifact_id", job["id"])
                case_request = output / "cases" / f"{artifact}.request.json"
                if dev_initial and case_request.exists():
                    if _json(case_request) != payload:
                        # Outer handler journals the failure before re-raising.
                        raise ValueError("Preserved unstarted request changed")  # noqa: TRY301
                else:
                    _write_new(case_request, payload)
                jobs.append(
                    {
                        **job,
                        "artifact_id": artifact,
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
                    {"id": item["artifact_id"], "payload": item["payload"]}
                    for item in jobs
                ],
            }
            if dev_initial:
                condition_payload["experiment"] = dict(manifest["experiment"])
                condition_payload["artifact_id"] = condition_artifact
                condition_payload["case_start_budget_seconds"] = condition_timeout - 60
            if configured:
                condition_payload.update(
                    {
                        key: batch["jobs"][0][key]
                        for key in (
                            "candidate_index",
                            "split",
                            "repeat",
                            "source_head",
                            "source_root",
                        )
                    }
                )
            destination = output / "conditions" / condition_artifact
            request = destination.with_suffix(".request.json")
            _write_new(request, condition_payload)
            journal(
                "condition_start",
                id=condition_artifact,
                condition=condition,
                **({"condition_key": condition_key} if configured else {}),
                case_ids=[item["id"] for item in jobs],
                timeout_seconds=condition_timeout,
                request_sha256=hashlib.sha256(request.read_bytes()).hexdigest(),
            )
            cleanup_certified = False
            code, timed_out = _run_condition_child(
                request,
                destination,
                output / "cases",
                condition_timeout,
                on_started=lambda pid, condition_id=condition_artifact: journal(
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
                id=condition_artifact,
                condition=condition,
                **({"condition_key": condition_key} if configured else {}),
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
                if item["artifact_id"] not in completed:
                    continue
                case_result_path = (
                    output / "cases" / item["artifact_id"] / "result.json"
                )
                recorded = completed.get(item["artifact_id"], {})
                case_status = (
                    "recorded"
                    if recorded.get("status") == "recorded"
                    and recorded.get("cleanup_ok") is True
                    and case_result_path.is_file()
                    else "failed"
                )
                attempt_identity = (
                    {
                        key: item[key]
                        for key in ("artifact_id", "attempt", "replaces_artifact_id")
                    }
                    if dev_initial
                    else {}
                )
                journal(
                    "case_start",
                    id=item["id"],
                    timeout_seconds=CHILD_TIMEOUT_SECONDS,
                    request_sha256=item["request_sha256"],
                    **attempt_identity,
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
                    **attempt_identity,
                )
            if status != "recorded":
                outcome = 2 if result.get("stop_reason") == "budget_exhausted" else 1
                break
        if not dev_initial and any(
            record["status"] != "recorded" for record in ends.values()
        ):
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


def _verify_candidate_source(root: Path, head: str) -> None:
    """Check the candidate's own checkout; old d0 cannot run a new protocol."""
    if not root.is_dir():
        raise ValueError("Candidate source directory is missing")

    def git(*arguments):
        return subprocess.check_output(  # noqa: S603 - fixed read-only Git arguments
            [_executable("git"), "-C", str(root), *arguments], text=True, timeout=15
        ).strip()

    if git("rev-parse", "HEAD") != head or git(
        "status", "--porcelain", "--untracked-files=normal"
    ):
        raise ValueError("Candidate requires the exact clean source identity")
    helper = root / "scripts" / "dev" / "assistant_experiment_config.py"
    if not helper.is_file() or experiment_config.PROTOCOL not in helper.read_text(
        encoding="utf-8"
    ):
        raise ValueError("Candidate source does not support the experiment protocol")
    lock = root / "poetry.lock"
    if not lock.is_file() or lock.read_bytes() != (ROOT / "poetry.lock").read_bytes():
        raise ValueError(
            "Candidate dependency lock differs from the coordinator runtime"
        )

    for relative in (
        "scripts/dev/assistant_pilot_models.py",
        "XBrainLab/llm/core/model_catalog.py",
        "XBrainLab/llm/rag/config.py",
        "XBrainLab/llm/rag/data/gold_set.json",
    ):
        candidate = root / relative
        if (
            not candidate.is_file()
            or hashlib.sha256(candidate.read_bytes()).digest()
            != hashlib.sha256((ROOT / relative).read_bytes()).digest()
        ):
            raise ValueError(
                "Candidate pinned model/generation/RAG policy differs: " + relative
            )


def _verify_resource_inventory(path: Path, runtime: dict) -> tuple[dict, str]:
    """Hash every selected pinned snapshot payload before any model child starts."""
    content = path.read_bytes()
    inventory = json.loads(content)
    if (
        not isinstance(inventory, dict)
        or set(inventory) != {"resources"}
        or not isinstance(inventory["resources"], list)
    ):
        raise ValueError("Invalid resource inventory")
    resources = {}
    for resource in inventory["resources"]:
        if (
            not isinstance(resource, dict)
            or set(resource) != {"repo", "revision", "files"}
            or not isinstance(resource["repo"], str)
            or resource["repo"] in resources
        ):
            raise ValueError("Invalid or duplicate resource inventory entry")
        repo = resource["repo"]
        expected = (
            RAGConfig.EMBEDDING_REVISION
            if repo == RAGConfig.EMBEDDING_MODEL
            else research_model_spec(repo).revision
        )
        if resource["revision"] != expected:
            raise ValueError("Pinned resource revision differs")
        resources[repo] = resource
    caches = {
        **runtime["model_caches"],
        RAGConfig.EMBEDDING_MODEL: runtime["embedding_cache"],
    }
    for repo, cache in caches.items():
        resource = resources.get(repo)
        if (
            resource is None
            or not isinstance(resource["files"], dict)
            or not 1 <= len(resource["files"]) <= 4096
        ):
            raise ValueError("Missing pinned resource inventory")
        snapshot = (
            Path(cache)
            / ("models--" + repo.replace("/", "--"))
            / "snapshots"
            / resource["revision"]
        )
        files = resource["files"]
        for name, identity in files.items():
            relative = PurePosixPath(name)
            if (
                not name
                or relative.is_absolute()
                or ".." in relative.parts
                or "\\" in name
                or ":" in name
                or str(relative) != name
                or not isinstance(identity, dict)
                or set(identity) != {"bytes", "sha256"}
                or type(identity["bytes"]) is not int
                or identity["bytes"] < 0
                or not isinstance(identity["sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", identity["sha256"])
            ):
                raise ValueError("Invalid resource file identity")
            target = snapshot / name
            if not target.is_file() or target.stat().st_size != identity["bytes"]:
                raise ValueError("Missing or changed resource payload: " + name)
            with target.open("rb") as stream:
                if (
                    hashlib.file_digest(stream, "sha256").hexdigest()
                    != identity["sha256"]
                ):
                    raise ValueError("Changed resource payload digest: " + name)
        actual = {
            item.relative_to(snapshot).as_posix()
            for item in snapshot.rglob("*")
            if item.is_file()
        }
        if actual != set(files):
            raise ValueError("Pinned resource file inventory differs")
    return inventory, hashlib.sha256(content).hexdigest()


def _prepare_experiment_manifest(
    bank_path: Path, config_path: Path, config: dict, *, config_base: Path | None = None
) -> tuple[dict, dict]:
    experiment = experiment_config.experiment_identity(config)
    if os.environ.get("QT_QPA_PLATFORM") != experiment["qt_platform"]:
        raise ValueError("Experiment Qt platform must be offscreen before preparation")
    base = (
        config_path.resolve().parent if config_base is None else config_base.resolve()
    )

    def resolved(value):
        path = Path(value)
        return (path if path.is_absolute() else base / path).resolve(strict=True)

    runtime = {
        "model_caches": {},
        "sources": {},
        "embedding_cache": str(resolved(config["embedding_cache"])),
        "resource_inventory": str(resolved(config["resource_inventory"])),
    }
    for model in config["models"]:
        root = resolved(model["source"]["root"])
        _verify_candidate_source(root, model["source"]["head"])
        cache = resolved(model["model_cache"])
        if not cache.is_dir():
            raise ValueError("Model cache must be an existing directory")
        runtime["sources"][model["alias"]] = {
            "head": model["source"]["head"],
            "root": str(root),
        }
        runtime["model_caches"][_MODELS[model["alias"]]] = str(cache)
    inventory, inventory_sha256 = _verify_resource_inventory(
        Path(runtime["resource_inventory"]), runtime
    )
    embedding = Path(runtime["embedding_cache"])
    if (
        not RAGConfig.embedding_cache_ready(embedding)
        or not RAGConfig.gold_set_integrity_ok()
    ):
        raise ValueError("Pinned RAG resources are missing or changed")
    embedding_sha256, _ = _identity(embedding)
    bank = load_bank(bank_path)
    selection = experiment_config.build_selection(bank, config)
    cases = {case["case_id"]: case for case in bank["cases"]}
    jobs = experiment_config.build_jobs(selection, config)
    for job in jobs:
        job["source_root"] = runtime["sources"][
            job["condition"].removesuffix("-rag-on")
        ]["root"]
        job["decision"] = cases[job["case_id"]]["decision"]
    models = {
        model: {
            "spec": asdict(research_model_spec(model)),
            "settings": asdict(make_launch_spec(model, cache).settings),
            "template_kwargs": research_template_kwargs(model),
            "configuration_sha256": _model_configuration(model, cache),
        }
        for model, cache in sorted(runtime["model_caches"].items())
    }
    manifest = {
        "schema": SCHEMA,
        "source": source_identity(),
        "environment": environment_identity(),
        "experiment": experiment,
        "bank_sha256": bank["source"]["sha256"],
        "selection": selection,
        "config": config,
        "config_base": str(base),
        "runtime_config": runtime,
        "models": models,
        "jobs": jobs,
        "resource_inventory": inventory,
        "resource_inventory_sha256": inventory_sha256,
        "corpus_sha256": RAGConfig.GOLD_SET_SHA256,
        "embedding_sha256": embedding_sha256,
        "seed": 0,
        "repeat": 0,
        "budget_seconds": config["budget_seconds"],
        "child_timeout_seconds": CHILD_TIMEOUT_SECONDS,
        "condition_timeout_seconds": config["budget_seconds"],
    }
    return json.loads(json.dumps(manifest, allow_nan=False)), bank


def prepare_manifest(
    bank_path: Path,
    selection_path: Path | None,
    config_path: Path,
    conditions: list[str],
    *,
    dev_initial: bool = False,
    config_base: Path | None = None,
) -> tuple[dict, dict]:
    config = _json(config_path)
    if config.get("schema") == experiment_config.CONFIG_SCHEMA:
        if selection_path is not None:
            raise ValueError("Experiment selection must derive from the single config")
        return _prepare_experiment_manifest(
            bank_path, config_path, config, config_base=config_base
        )
    if (
        dev_initial
        and os.environ.get("QT_QPA_PLATFORM") != DEV_EXPERIMENT["qt_platform"]
    ):
        raise ValueError("DEV Qt platform must be offscreen before preparation")
    bank = load_bank(bank_path)
    expected_selection = (
        build_dev_selection(bank) if dev_initial else build_pilot_selection(bank)
    )
    selection = (
        _json(selection_path) if selection_path is not None else expected_selection
    )
    if selection != expected_selection or (selection_path is None and not dev_initial):
        raise ValueError(
            "Selection does not match the approved deterministic DEV selection"
        )
    if dev_initial and any(not CONDITIONS[condition][1] for condition in conditions):
        raise ValueError("Initial DEV only permits RAG on")
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
    if dev_initial:
        manifest["experiment"] = dict(DEV_EXPERIMENT)
        manifest["condition_timeout_seconds"] = BUDGET_SECONDS
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
