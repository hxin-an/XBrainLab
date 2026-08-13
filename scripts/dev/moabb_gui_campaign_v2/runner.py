"""Serial fresh-process orchestration for the MOABB GUI campaign."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.dev.moabb_dataset_materializer import exact_environment_identity

from .contract import (
    DATASET_MATRIX,
    JOURNEY_MODES,
    REQUIRED_STAGES,
    campaign_plan_sha256,
    execution_preflight_errors,
    validate_campaign_receipts,
)
from .driver import missing_product_source_hooks
from .visual_review import (
    VISUAL_REVIEW_FILENAME,
    build_pending_visual_review_template,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class JourneyCommand:
    """One cold or replay process with its unique receipt destination."""

    dataset: str
    mode: str
    argv: tuple[str, ...]
    receipt_path: Path


@dataclass(frozen=True)
class JourneyProcessOutcome:
    """Exact child-session termination evidence for one GUI journey."""

    returncode: int
    timed_out: bool = False
    terminated_process_group: bool = False
    killed_process_group: bool = False
    pid: int = 0
    duration_seconds: float = 0.0
    # ``returncode`` is the runner outcome.  Preserve the worker's own exit
    # separately so a zero-exit leader cannot hide an orphaned descendant.
    leader_returncode: int | None = None
    residual_descendant_count: int = 0
    residual_process_group_status: str = "clean"


@dataclass(frozen=True)
class _ProcessSnapshot:
    """Linux process identity fields that make a PGID safe to address."""

    pid: int
    process_group: int
    session: int
    start_ticks: int
    state: str


@dataclass(frozen=True)
class _OwnedProcessGroup:
    """The exact session created by ``start_new_session=True``."""

    leader_pid: int
    process_group: int
    session: int
    leader_start_ticks: int


def build_journey_commands(
    *,
    plan_path: Path,
    plan: dict[str, Any],
    evidence_root: Path,
) -> list[JourneyCommand]:
    """Build the exact serial 15 x 2 process inventory in manifest order."""
    known = {
        str(row["moabb_class"])
        for row in plan.get("datasets", [])
        if isinstance(row, dict) and row.get("moabb_class")
    }
    if known != set(DATASET_MATRIX):
        raise ValueError("Campaign plan does not contain the fixed dataset inventory.")
    commands: list[JourneyCommand] = []
    for dataset in DATASET_MATRIX:
        for mode in JOURNEY_MODES:
            receipt_path = evidence_root / dataset / mode / "journey-receipt.json"
            argv = (
                "prlimit",
                "--core=0",
                "--",
                sys.executable,
                "-m",
                "scripts.dev.moabb_gui_campaign_v2",
                "worker",
                "--plan",
                str(plan_path.resolve()),
                "--dataset",
                dataset,
                "--mode",
                mode,
                "--receipt",
                str(receipt_path.resolve()),
            )
            commands.append(
                JourneyCommand(
                    dataset=dataset,
                    mode=mode,
                    argv=argv,
                    receipt_path=receipt_path,
                )
            )
    return commands


def run_campaign(
    *,
    plan_path: Path,
    plan: dict[str, Any],
    evidence_root: Path,
    journey_timeout_seconds: int,
) -> list[dict[str, Any]]:
    """Run every GUI journey serially and fail at the first non-green receipt."""
    evidence_root = _validated_fresh_evidence_root(
        evidence_root,
        protected_paths=_plan_protected_paths(plan),
    )
    environment = exact_environment_identity()
    preflight_errors = execution_preflight_errors(plan, environment=environment)
    preflight_errors.extend(
        f"product UI hook is missing: {name}"
        for name in missing_product_source_hooks(REPO_ROOT)
    )
    if preflight_errors:
        raise ValueError(
            "Campaign execution preflight failed:\n- " + "\n- ".join(preflight_errors)
        )
    receipts: list[dict[str, Any]] = []
    child_environment = _campaign_child_environment(evidence_root)
    for command in build_journey_commands(
        plan_path=plan_path,
        plan=plan,
        evidence_root=evidence_root,
    ):
        command.receipt_path.parent.mkdir(parents=True, exist_ok=True)
        _quarantine_stale_receipt(command.receipt_path)
        stdout_path = command.receipt_path.with_name("journey-stdout.log")
        stderr_path = command.receipt_path.with_name("journey-stderr.log")
        outcome = _run_owned_process(
            command.argv,
            timeout_seconds=journey_timeout_seconds,
            cwd=REPO_ROOT,
            env=child_environment,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )
        process_receipt_path = _write_process_receipt(
            command,
            outcome,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            environment=child_environment,
        )
        if outcome.returncode != 0 or outcome.timed_out:
            _write_process_failure(command, outcome)
            raise RuntimeError(
                f"{command.dataset}/{command.mode} "
                + (
                    "timed out and its owned process group was stopped."
                    if outcome.timed_out
                    else (
                        "left owned residual descendants after its leader exited."
                        if outcome.residual_descendant_count
                        else f"exited with {outcome.returncode}."
                    )
                )
            )
        if not command.receipt_path.is_file():
            raise RuntimeError(f"{command.dataset}/{command.mode} produced no receipt.")
        payload = json.loads(command.receipt_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"{command.dataset}/{command.mode} receipt is not an object."
            )
        payload = _seal_journey_receipt(
            command,
            outcome,
            payload,
            process_receipt_path=process_receipt_path,
        )
        receipts.append(payload)
    final_environment = exact_environment_identity()
    final_preflight_errors = execution_preflight_errors(
        plan,
        environment=final_environment,
    )
    if final_preflight_errors:
        raise RuntimeError(
            "Post-campaign source/data/environment integrity failed:\n- "
            + "\n- ".join(final_preflight_errors)
        )
    errors = validate_campaign_receipts(
        plan,
        receipts,
        artifact_root=evidence_root,
        expected_plan_sha256=campaign_plan_sha256(plan_path),
    )
    if errors:
        raise RuntimeError(
            "Campaign receipt denominator failed:\n- " + "\n- ".join(errors)
        )
    _write_ready_checklists(
        plan_path=plan_path,
        plan=plan,
        receipts=receipts,
        evidence_root=evidence_root,
    )
    return receipts


def _run_owned_process(
    argv: tuple[str, ...],
    *,
    timeout_seconds: float,
    termination_timeout_seconds: float = 5.0,
    residual_grace_period_seconds: float = 1.0,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
) -> JourneyProcessOutcome:
    """Run one fresh process session and reap only that owned process group."""
    started = time.monotonic()
    stdout_handle = stdout_path.open("wb") if stdout_path is not None else None
    stderr_handle = stderr_path.open("wb") if stderr_path is not None else None
    try:
        process = subprocess.Popen(  # noqa: S603
            argv,
            start_new_session=True,
            cwd=cwd,
            env=env,
            stdout=stdout_handle,
            stderr=stderr_handle,
        )
        owned_group = _capture_owned_process_group(process)
        try:
            leader_returncode = process.wait(timeout=timeout_seconds)
            (
                residual_count,
                residual_status,
                terminated,
                killed,
            ) = _verify_and_reap_residual_owned_process_group(
                owned_group,
                grace_period_seconds=residual_grace_period_seconds,
                termination_timeout_seconds=termination_timeout_seconds,
            )
            return JourneyProcessOutcome(
                # Preserve a real worker failure.  A zero-exit leader that
                # left any owned descendant is separately failed by the
                # runner, even if that descendant is subsequently reaped.
                returncode=(
                    leader_returncode
                    if leader_returncode != 0
                    else (0 if residual_count == 0 else -1)
                ),
                leader_returncode=leader_returncode,
                residual_descendant_count=residual_count,
                residual_process_group_status=residual_status,
                terminated_process_group=terminated,
                killed_process_group=killed,
                pid=process.pid,
                duration_seconds=time.monotonic() - started,
            )
        except subprocess.TimeoutExpired:
            (
                residual_count,
                residual_status,
                terminated,
                killed,
            ) = _terminate_and_reap_owned_process_group(
                owned_group,
                termination_timeout_seconds=termination_timeout_seconds,
            )
            try:
                leader_returncode = process.wait(
                    timeout=termination_timeout_seconds,
                )
            except subprocess.TimeoutExpired:
                # The group scan already found no live group member, so this
                # is a process-table inconsistency.  Do not report a clean
                # stop when the leader itself cannot be reaped.
                leader_returncode = process.poll()
                residual_status = f"{residual_status}_leader_unreaped"
            return JourneyProcessOutcome(
                returncode=(leader_returncode if leader_returncode is not None else -1),
                timed_out=True,
                terminated_process_group=terminated,
                killed_process_group=killed,
                pid=process.pid,
                duration_seconds=time.monotonic() - started,
                leader_returncode=leader_returncode,
                residual_descendant_count=residual_count,
                residual_process_group_status=residual_status,
            )
        except BaseException:
            _terminate_and_reap_owned_process_group(
                owned_group,
                termination_timeout_seconds=termination_timeout_seconds,
            )
            raise
    finally:
        if stdout_handle is not None:
            stdout_handle.close()
        if stderr_handle is not None:
            stderr_handle.close()


def _capture_owned_process_group(process: subprocess.Popen[Any]) -> _OwnedProcessGroup:
    """Capture an unambiguous session identity before the leader can exit.

    A numeric PGID alone is unsafe: after a group has disappeared the kernel
    may eventually reuse it.  The session/PGID pair and the original leader's
    `/proc` start tick establish that this runner created the group.  If that
    identity cannot be captured, campaign execution fails closed rather than
    risking a signal to an unrelated process.
    """
    if os.name != "posix":
        raise RuntimeError("campaign process-group ownership requires POSIX")
    snapshot = _process_snapshot(process.pid)
    if snapshot is None:
        raise RuntimeError(
            "journey leader exited before its owned session identity was captured"
        )
    if (
        snapshot.process_group != process.pid
        or snapshot.session != process.pid
        or snapshot.start_ticks <= 0
    ):
        raise RuntimeError("journey process did not retain its owned session identity")
    return _OwnedProcessGroup(
        leader_pid=process.pid,
        process_group=snapshot.process_group,
        session=snapshot.session,
        leader_start_ticks=snapshot.start_ticks,
    )


def _process_snapshot(pid: int) -> _ProcessSnapshot | None:
    """Read stable POSIX ownership fields from Linux procfs, if still alive."""
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    # ``comm`` can contain spaces and closing parentheses, so split only at
    # the final delimiter before the fixed stat fields.
    delimiter = raw.rfind(") ")
    if delimiter < 0:
        return None
    fields = raw[delimiter + 2 :].split()
    # state (3), pgrp (5), session (6), starttime (22)
    if len(fields) <= 19:
        return None
    try:
        return _ProcessSnapshot(
            pid=pid,
            state=fields[0],
            process_group=int(fields[2]),
            session=int(fields[3]),
            start_ticks=int(fields[19]),
        )
    except ValueError:
        return None


def _live_owned_process_group_members(
    owned_group: _OwnedProcessGroup,
) -> list[_ProcessSnapshot]:
    """Return live members of exactly the session and PGID this runner made."""
    try:
        proc_entries = list(Path("/proc").iterdir())
    except OSError as exc:
        raise RuntimeError("cannot verify owned journey process group") from exc
    members: list[_ProcessSnapshot] = []
    for entry in proc_entries:
        try:
            pid = int(entry.name)
        except ValueError:
            continue
        snapshot = _process_snapshot(pid)
        if snapshot is None or snapshot.state in {"Z", "X"}:
            continue
        if (
            snapshot.process_group == owned_group.process_group
            and snapshot.session == owned_group.session
        ):
            if (
                snapshot.pid == owned_group.leader_pid
                and snapshot.start_ticks != owned_group.leader_start_ticks
            ):
                raise RuntimeError(
                    "owned journey leader PID identity was reused before cleanup"
                )
            members.append(snapshot)
    return members


def _signal_owned_process_group(
    owned_group: _OwnedProcessGroup,
    signal_number: signal.Signals,
) -> bool:
    """Signal only revalidated members of the captured session/group.

    ``killpg`` accepts only a numeric PGID.  If every verified member exits in
    the gap between a scan and that syscall, Linux may reuse the number for an
    unrelated group.  Signalling each member after a second start-tick / SID /
    PGID check is fail-closed against that reuse, while repeated membership
    scans catch descendants forked during the cleanup window.
    """
    members = _live_owned_process_group_members(owned_group)
    if not members:
        return False
    signalled = False
    for member in members:
        current = _process_snapshot(member.pid)
        if current is None or current.state in {"Z", "X"}:
            continue
        if (
            current.start_ticks != member.start_ticks
            or current.process_group != owned_group.process_group
            or current.session != owned_group.session
        ):
            raise RuntimeError(
                "owned journey process member identity changed before stop"
            )
        try:
            os.kill(member.pid, signal_number)
        except ProcessLookupError:
            continue
        signalled = True
    return signalled


def _residual_descendant_count(
    members: list[_ProcessSnapshot],
    *,
    leader_pid: int,
) -> int:
    """Count post-leader descendants without inflating timeout evidence."""
    return sum(member.pid != leader_pid for member in members)


def _wait_for_owned_process_group_empty(
    owned_group: _OwnedProcessGroup,
    *,
    timeout_seconds: float,
) -> bool:
    """Boundedly verify that no live member remains in the exact owned group."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _live_owned_process_group_members(owned_group):
            return True
        time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
    return not _live_owned_process_group_members(owned_group)


def _terminate_and_reap_owned_process_group(
    owned_group: _OwnedProcessGroup,
    *,
    termination_timeout_seconds: float,
) -> tuple[int, str, bool, bool]:
    """TERM, scan, then KILL the captured group even after leader exit.

    This intentionally never uses ``Popen.poll`` as a completion criterion:
    after the timeout signal, the leader may exit while an inherited child
    survives.  Only the captured SID/PGID membership scan can prove cleanup.
    """
    if termination_timeout_seconds <= 0:
        raise ValueError("process-group termination timeout is invalid")
    initial_members = _live_owned_process_group_members(owned_group)
    residual_count = _residual_descendant_count(
        initial_members,
        leader_pid=owned_group.leader_pid,
    )
    if not initial_members:
        return residual_count, "timeout_group_already_exited", False, False

    terminated = _signal_owned_process_group(owned_group, signal.SIGTERM)
    if _wait_for_owned_process_group_empty(
        owned_group,
        timeout_seconds=termination_timeout_seconds,
    ):
        return (
            residual_count,
            "timeout_residuals_reaped" if residual_count else "timeout_group_reaped",
            terminated,
            False,
        )

    killed = _signal_owned_process_group(owned_group, signal.SIGKILL)
    if _wait_for_owned_process_group_empty(
        owned_group,
        timeout_seconds=termination_timeout_seconds,
    ):
        return (
            residual_count,
            "timeout_residuals_reaped" if residual_count else "timeout_group_reaped",
            terminated,
            killed,
        )
    return residual_count, "timeout_residuals_survived", terminated, killed


def _verify_and_reap_residual_owned_process_group(
    owned_group: _OwnedProcessGroup,
    *,
    grace_period_seconds: float,
    termination_timeout_seconds: float,
) -> tuple[int, str, bool, bool]:
    """Boundedly drain descendants after every completed leader outcome.

    The initial count is retained even when children exit during the grace
    window: their existence means the MainWindow journey was not clean at its
    process boundary, regardless of whether the leader itself succeeded.
    """
    if grace_period_seconds < 0 or termination_timeout_seconds <= 0:
        raise ValueError("process-group grace and termination timeouts are invalid")
    initial_members = _live_owned_process_group_members(owned_group)
    initial_count = len(initial_members)
    if initial_count == 0:
        return 0, "clean", False, False
    grace_deadline = time.monotonic() + grace_period_seconds
    while time.monotonic() < grace_deadline:
        if not _live_owned_process_group_members(owned_group):
            return initial_count, "residuals_exited_during_grace", False, False
        time.sleep(min(0.05, max(0.0, grace_deadline - time.monotonic())))
    if not _live_owned_process_group_members(owned_group):
        return initial_count, "residuals_exited_during_grace", False, False

    terminated = _signal_owned_process_group(owned_group, signal.SIGTERM)
    termination_deadline = time.monotonic() + termination_timeout_seconds
    while time.monotonic() < termination_deadline:
        if not _live_owned_process_group_members(owned_group):
            return initial_count, "residuals_reaped", terminated, False
        time.sleep(min(0.05, max(0.0, termination_deadline - time.monotonic())))

    killed = _signal_owned_process_group(owned_group, signal.SIGKILL)
    kill_deadline = time.monotonic() + termination_timeout_seconds
    while time.monotonic() < kill_deadline:
        if not _live_owned_process_group_members(owned_group):
            return initial_count, "residuals_reaped", terminated, killed
        time.sleep(min(0.05, max(0.0, kill_deadline - time.monotonic())))
    return initial_count, "residuals_survived", terminated, killed


def _write_process_failure(
    command: JourneyCommand,
    outcome: JourneyProcessOutcome,
) -> None:
    """Persist non-green lifecycle evidence beside, never as, a green receipt."""
    path = command.receipt_path.with_name("journey-failure.json")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")
    payload = {
        "schema_version": "1.0.0",
        "status": "failed",
        "dataset": command.dataset,
        "journey_mode": command.mode,
        "returncode": outcome.returncode,
        "leader_returncode": outcome.leader_returncode,
        "timed_out": outcome.timed_out,
        "terminated_owned_process_group": outcome.terminated_process_group,
        "killed_owned_process_group": outcome.killed_process_group,
        "pid": outcome.pid,
        "duration_seconds": outcome.duration_seconds,
        "residual_descendant_count": outcome.residual_descendant_count,
        "residual_process_group_status": outcome.residual_process_group_status,
    }
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _validated_fresh_evidence_root(
    path: Path,
    *,
    protected_paths: list[Path] | None = None,
) -> Path:
    if not path.is_absolute():
        raise ValueError("Campaign evidence root must be an absolute /mnt/d path.")
    resolved = path.resolve()
    if resolved != Path("/mnt/d") and not str(resolved).startswith("/mnt/d/"):
        raise ValueError("Campaign evidence root must be stored on /mnt/d.")
    for protected in protected_paths or []:
        protected_resolved = protected.resolve()
        if resolved == protected_resolved or (
            resolved.is_relative_to(protected_resolved)
            or protected_resolved.is_relative_to(resolved)
        ):
            raise ValueError(
                "Campaign evidence root must not overlap frozen dataset paths."
            )
    if resolved.exists() and any(resolved.iterdir()):
        raise ValueError("Campaign evidence root must be fresh and empty.")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _plan_protected_paths(plan: dict[str, Any]) -> list[Path]:
    protected: list[Path] = []
    for row in plan.get("datasets", []):
        if not isinstance(row, dict):
            continue
        bids = row.get("bids")
        if not isinstance(bids, dict):
            continue
        for field in ("conversion_parent", "root"):
            value = str(bids.get(field) or "").strip()
            if value:
                protected.append(Path(value))
        manifest = str(bids.get("checksum_manifest") or "").strip()
        if manifest:
            protected.append(Path(manifest).parent)
    return protected


def _campaign_child_environment(evidence_root: Path) -> dict[str, str]:
    runtime_root = evidence_root / "runtime"
    paths = {
        "MNE_DATA": runtime_root / "mne-data",
        "MPLCONFIGDIR": runtime_root / "matplotlib",
        "XDG_CACHE_HOME": runtime_root / "xdg-cache",
        "XDG_CONFIG_HOME": runtime_root / "xdg-config",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment.update({key: str(value) for key, value in paths.items()})
    environment["MNE_DONTWRITE_HOME"] = "true"
    environment["PYTHONUNBUFFERED"] = "1"
    return environment


def _quarantine_stale_receipt(path: Path) -> None:
    if not path.exists():
        return
    quarantine = path.with_name(f"{path.stem}.stale-{time.monotonic_ns()}{path.suffix}")
    path.replace(quarantine)


def _write_process_receipt(
    command: JourneyCommand,
    outcome: JourneyProcessOutcome,
    *,
    stdout_path: Path,
    stderr_path: Path,
    environment: dict[str, str],
) -> Path:
    selected_environment = {
        key: environment.get(key, "")
        for key in (
            "MNE_DATA",
            "MNE_DONTWRITE_HOME",
            "MPLCONFIGDIR",
            "XDG_CACHE_HOME",
            "XDG_CONFIG_HOME",
            "QT_QPA_PLATFORM",
        )
    }
    payload = {
        "schema_version": "1.0.0",
        "dataset": command.dataset,
        "journey_mode": command.mode,
        "argv": list(command.argv),
        "cwd": str(REPO_ROOT),
        "environment": selected_environment,
        "environment_sha256": hashlib.sha256(
            json.dumps(
                selected_environment,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        "pid": outcome.pid,
        "returncode": outcome.returncode,
        "leader_returncode": outcome.leader_returncode,
        "duration_seconds": outcome.duration_seconds,
        "timed_out": outcome.timed_out,
        "terminated_owned_process_group": outcome.terminated_process_group,
        "killed_owned_process_group": outcome.killed_process_group,
        "residual_descendant_count": outcome.residual_descendant_count,
        "residual_process_group_status": outcome.residual_process_group_status,
        "stdout": str(stdout_path.resolve()),
        "stderr": str(stderr_path.resolve()),
    }
    path = command.receipt_path.with_name("journey-process.json")
    _atomic_write_json(path, payload)
    return path.resolve()


def _seal_journey_receipt(
    command: JourneyCommand,
    outcome: JourneyProcessOutcome,
    payload: dict[str, Any],
    *,
    process_receipt_path: Path,
) -> dict[str, Any]:
    """Replace provisional child claims with independently observed outcome."""
    process = payload.get("process")
    if not isinstance(process, dict):
        raise RuntimeError("journey receipt lacks provisional process identity")
    if process.get("pid") != outcome.pid:
        raise RuntimeError("journey receipt PID does not match its owned child")
    if (
        payload.get("dataset") != command.dataset
        or payload.get("journey_mode") != command.mode
    ):
        raise RuntimeError("journey receipt identity does not match its command")
    if outcome.returncode != 0 or outcome.timed_out:
        raise RuntimeError("cannot seal a non-successful journey process")
    if (
        outcome.residual_descendant_count != 0
        or outcome.residual_process_group_status != "clean"
    ):
        raise RuntimeError("cannot seal a journey with residual process descendants")
    process_receipt_digest = hashlib.sha256(
        process_receipt_path.read_bytes()
    ).hexdigest()
    sealed = dict(payload)
    sealed["process"] = {
        "fresh_process": True,
        "pid": outcome.pid,
        "exit_code": outcome.returncode,
        "runner_verified": True,
        "timed_out": False,
        "duration_seconds": outcome.duration_seconds,
        "residual_descendant_count": outcome.residual_descendant_count,
        "residual_process_group_status": outcome.residual_process_group_status,
        "process_receipt": str(process_receipt_path),
        "process_receipt_sha256": process_receipt_digest,
    }
    _atomic_write_json(command.receipt_path, sealed)
    return sealed


def _write_ready_checklists(
    *,
    plan_path: Path,
    plan: dict[str, Any],
    receipts: list[dict[str, Any]],
    evidence_root: Path,
) -> None:
    rows: list[dict[str, Any]] = []
    for planned in plan["datasets"]:
        dataset = str(planned["moabb_class"])
        dataset_receipts = [row for row in receipts if row["dataset"] == dataset]
        if [row["journey_mode"] for row in dataset_receipts] != list(JOURNEY_MODES):
            raise RuntimeError("Ready checklist denominator is incomplete.")
        elapsed_by_stage = {
            stage: [
                float(item["elapsed_seconds"])
                for receipt in dataset_receipts
                for item in receipt["stages"]
                if item["stage"] == stage
            ]
            for stage in REQUIRED_STAGES
        }
        rows.append(
            {
                "dataset": dataset,
                "bids_root": planned["bids"]["root"],
                "subjects": planned["subjects"],
                "dataset_checksum_sha256": planned["bids"]["dataset_revision_sha256"],
                "ui_options": {
                    row["journey_mode"]: row["ui_options"] for row in dataset_receipts
                },
                "event_class_summary": dataset_receipts[0]["event_class_summary"],
                "stage_elapsed_seconds": {
                    stage: {"minimum": min(values), "maximum": max(values)}
                    for stage, values in elapsed_by_stage.items()
                },
                "artifacts": {
                    row["journey_mode"]: row["artifacts"] for row in dataset_receipts
                },
                "journey_receipts": {
                    mode: str(
                        (
                            evidence_root / dataset / mode / "journey-receipt.json"
                        ).resolve()
                    )
                    for mode in JOURNEY_MODES
                },
            }
        )
    source = receipts[0]["source_identity"]
    payload = {
        "schema_version": "1.0.0",
        "status": "pending_visual_review",
        "dataset_count": len(rows),
        "source_identity": source,
        "datasets": rows,
    }
    _atomic_write_json(evidence_root / "manual-test-checklist.json", payload)
    visual_review = build_pending_visual_review_template(
        plan_path=plan_path,
        receipts=receipts,
        evidence_root=evidence_root,
    )
    _atomic_write_json(evidence_root / VISUAL_REVIEW_FILENAME, visual_review)
    markdown = [
        "# MOABB 15-dataset manual test checklist",
        "",
        f"Exact commit: `{source['application_commit']}`",
        f"Poetry lock: `{source['poetry_lock_sha256']}`",
        f"CUDA/GPU: `{source['cuda']}` / `{source['gpu']}`",
        "",
        "Campaign receipts are complete, but delivery remains blocked until an "
        "independent reviewer completes `visual-review-attestation.json`. The "
        "review must cover every bound screenshot and every required visual "
        "dimension; the campaign runner cannot complete this attestation.",
        "",
    ]
    for row in rows:
        markdown.extend(
            [
                f"## {row['dataset']}",
                "",
                f"- BIDS: `{row['bids_root']}`",
                f"- Subjects: `{row['subjects']}`",
                f"- Checksum: `{row['dataset_checksum_sha256']}`",
                "- Cold + replay receipts: green",
                "- Event/class oracle: `"
                + json.dumps(
                    row["event_class_summary"],
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "`",
                "- Cold UI options: `"
                + json.dumps(
                    row["ui_options"]["cold"],
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "`",
                "- Replay UI options: `"
                + json.dumps(
                    row["ui_options"]["replay"],
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "`",
                "- Stage duration ranges: `"
                + json.dumps(
                    row["stage_elapsed_seconds"],
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "`",
                f"- Cold receipt: `{row['journey_receipts']['cold']}`",
                f"- Replay receipt: `{row['journey_receipts']['replay']}`",
                "- Visible artifacts: `"
                + json.dumps(
                    row["artifacts"],
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "`",
                "",
            ]
        )
    _atomic_write_text(evidence_root / "manual-test-checklist.md", "\n".join(markdown))


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _atomic_write_text(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
