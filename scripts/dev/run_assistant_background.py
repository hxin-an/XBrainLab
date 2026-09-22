"""Detach one approved experiment and attempt one exact-session Codex continuation.

WSL/POSIX supervisor only. The experiment runner owns its timeout and cleanup.
Arm explicitly; a matching completed turn and no later active turn are also
required. CLI resume requires an available writer (an unloaded session); turn
completion does not release a still-open interactive conversation's writer.
Keep that existing conversation active and use bounded process waits instead.
Rollout lifecycle is an observed format, not a locking API; even an unloaded
session can acquire another writer between the final check and resume.
Crashes, changed pins, ambiguous lifecycle and failed wakes require manual review.
"""

# Phase errors are retained once in status.json for manual recovery.
# ruff: noqa: TRY301, TRY300

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

_MAX_LINE = 16 * 1024**2


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _new_json(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


def _status(state: Path, status: str, **values) -> None:
    temporary = state / "status.json.tmp"
    temporary.write_text(
        json.dumps(
            {"status": status, "pid": os.getpid(), "time": time.time(), **values}
        ),
        encoding="utf-8",
    )
    temporary.replace(state / "status.json")


def _source(cwd: Path) -> str:
    dirty = subprocess.check_output(  # noqa: S603 - fixed read-only source check
        ["git", "-C", str(cwd), "status", "--porcelain"],  # noqa: S607 - repository's Git on PATH
        text=True,
        timeout=15,
    )
    if dirty:
        raise ValueError("Source worktree is not clean")
    return subprocess.check_output(  # noqa: S603 - fixed git read-only invocation
        ["git", "-C", str(cwd), "rev-parse", "HEAD"],  # noqa: S607 - repository's Git on PATH
        text=True,
        timeout=15,
    ).strip()


def _check_pins(config: dict) -> None:
    if _source(Path(config["cwd"])) != config["source_sha"]:
        raise ValueError("Source commit changed")
    if _digest(Path(config["manifest"])) != config["manifest_sha256"]:
        raise ValueError("Prepared manifest changed")


def prepare(config: dict) -> dict:
    """Validate explicit trusted inputs without starting any process or wake."""
    if os.name != "posix":
        raise ValueError("Launch the supervisor in WSL/POSIX")
    value = dict(config)
    for key in ("cwd", "manifest", "rollout", "codex", "prompt_file"):
        value[key] = str(Path(value[key]).resolve(strict=True))
    for key in ("session_id", "turn_id"):
        if str(uuid.UUID(value[key])) != value[key]:
            raise ValueError("Exact canonical session and turn UUIDs required")
    if not re.fullmatch(r"[a-f0-9]{40}", value["source_sha"]):
        raise ValueError("Exact source SHA required")
    command = value["command"]
    if (
        not isinstance(command, list)
        or not command
        or not all(
            isinstance(item, str) and item and "\0" not in item for item in command
        )
        or not Path(command[0]).is_absolute()
        or not Path(command[0]).is_file()
    ):
        raise ValueError(
            "Experiment requires explicit executable argv, never shell text"
        )
    if type(value["turn_offset"]) is not int or value["turn_offset"] < 0:
        raise ValueError("Exact task_started byte offset required")
    for key, default, maximum in (
        ("release_timeout_seconds", 43200, 43200),
        ("wake_timeout_seconds", 3600, 3600),
        ("poll_seconds", 2, 10),
    ):
        number = value.setdefault(key, default)
        if type(number) not in (int, float) or not 0 < number <= maximum:
            raise ValueError("Invalid bounded timing: " + key)
    path = Path(value["rollout"])
    identity = path.stat()
    with path.open("rb") as stream:
        header = json.loads(stream.readline(_MAX_LINE))
        if (
            header.get("type") != "session_meta"
            or header.get("payload", {}).get("id") != value["session_id"]
        ):
            raise ValueError("Rollout session identity mismatch")
        stream.seek(value["turn_offset"])
        event = json.loads(stream.readline(_MAX_LINE))
        if (
            event.get("type") != "event_msg"
            or event.get("payload", {}).get("type") != "task_started"
            or event["payload"].get("turn_id") != value["turn_id"]
        ):
            raise ValueError("Captured task_started offset/turn mismatch")
    value["rollout_identity"] = [identity.st_dev, identity.st_ino]
    manifest = json.loads(Path(value["manifest"]).read_text(encoding="utf-8"))
    if manifest.get("source", {}).get("head") != value["source_sha"]:
        raise ValueError("Prepared manifest source mismatch")
    value["manifest_sha256"] = _digest(Path(value["manifest"]))
    value["wake_prompt"] = Path(value.pop("prompt_file")).read_text(encoding="utf-8")
    if not 1 <= len(value["wake_prompt"]) <= 16384:
        raise ValueError("Wake prompt must be nonempty and bounded")
    _check_pins(value)
    return value


def scan_lifecycle(config: dict, cursor: dict) -> None:
    """Read only lifecycle envelopes after the exact saved task_started offset."""
    path = Path(config["rollout"])
    with path.open("rb") as stream:
        stat = os.fstat(stream.fileno())
        if [stat.st_dev, stat.st_ino] != config[
            "rollout_identity"
        ] or stat.st_size < cursor["offset"]:
            raise ValueError("Rollout rotated or truncated")
        stream.seek(cursor["offset"])
        cursor["incomplete"] = False
        while True:
            line = stream.readline(_MAX_LINE + 1)
            if len(line) > _MAX_LINE:
                raise ValueError("Rollout record exceeds bounded reader")
            if not line or not line.endswith(b"\n"):
                cursor["incomplete"] = bool(line)
                return
            envelope = json.loads(line)
            cursor["offset"] = stream.tell()
            if envelope.get("type") != "event_msg":
                continue
            payload = envelope.get("payload", {})
            kind = payload.get("type")
            if kind not in {"task_started", "task_complete", "turn_aborted"}:
                if isinstance(kind, str) and kind.startswith(("task_", "turn_")):
                    raise ValueError("Unknown lifecycle event")
                continue
            turn = payload.get("turn_id")
            if not isinstance(turn, str) or not turn:
                raise ValueError("Lifecycle turn identity missing")
            if kind == "task_started":
                if cursor["active"] is not None:
                    raise ValueError("Overlapping lifecycle turns")
                cursor["active"] = turn
            elif turn != cursor["active"]:
                raise ValueError("Uncorrelated lifecycle completion")
            else:
                cursor["active"] = None
                if turn == config["turn_id"]:
                    if kind == "turn_aborted":
                        raise ValueError(
                            "Captured turn aborted; continuation requires manual review"
                        )
                    cursor["released"] = True


def arm(state: Path) -> None:
    """Approve the frozen handoff; this never bypasses the turn-release gate."""
    _new_json(state / "armed.json", {"config_sha256": _digest(state / "config.json")})


def launch(config: dict, state: Path) -> subprocess.Popen:
    """Detach a fresh supervisor; never resume an uncertain previous worker."""
    frozen = prepare(config)
    state = state.absolute()
    state.mkdir()
    _new_json(state / "config.json", frozen)
    digest = _digest(state / "config.json")
    manifest = Path(frozen["manifest"])
    _new_json(
        manifest.with_name(manifest.name + ".background-claim.json"),
        {"state": str(state), "config_sha256": digest},
    )
    with (state / "supervisor.log").open("xb") as log:
        process = subprocess.Popen(  # noqa: S603 - own fixed module, shell disabled
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker",
                str(state),
                "--config-sha256",
                digest,
            ],
            cwd=frozen["cwd"],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    return process


def worker(state: Path, expected_digest: str | None = None) -> int:
    """Execute once; failures leave durable evidence, never automatic retries."""
    try:
        _new_json(state / "worker-started.json", {"pid": os.getpid()})
    except FileExistsError:
        return 1
    details = {}
    try:
        digest = _digest(state / "config.json")
        if digest != expected_digest:
            raise ValueError("Frozen supervisor configuration changed")
        config = json.loads((state / "config.json").read_text(encoding="utf-8"))
        prompt = (
            config["wake_prompt"]
            + "\n\nBackground handoff evidence: "
            + json.dumps(
                {
                    "status": str(state / "status.json"),
                    "experiment_log": str(state / "experiment.log"),
                    "manifest": config["manifest"],
                    "manifest_sha256": config["manifest_sha256"],
                    "source_sha": config["source_sha"],
                }
            )
            + "\nVerify these read-only first. Continue only the already approved DEV initial baseline; no new candidate, VALID or TEST."
        )
        command = [
            config["codex"],
            "--cd",
            config["cwd"],
            "exec",
            "resume",
            config["session_id"],
            prompt,
            "--json",
            "-o",
            str(state / "continuation.md"),
        ]
        _new_json(
            state / "manual-recovery.json",
            {
                "cwd": config["cwd"],
                "argv": command,
                "instruction": (
                    "Inspect status, experiment logs and wake intent first. CLI resume "
                    "requires an available writer (an unloaded session); a completed "
                    "turn does not release an open conversation's writer. For an open "
                    "session, continue in the existing conversation using bounded "
                    "process waits. Never retry automatically or bypass writer locks."
                ),
            },
        )
        _check_pins(config)
        _status(state, "experiment_running")
        try:
            with (state / "experiment.log").open("xb") as log:
                result = subprocess.run(  # noqa: S603 - frozen explicit argv, runner owns deadline
                    config["command"],
                    cwd=config["cwd"],
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
            details["experiment_returncode"] = result.returncode
        except OSError as exc:
            details.update(experiment_returncode=None, experiment_error=str(exc))
        _status(state, "waiting_for_release", **details)
        cursor = {"offset": config["turn_offset"], "active": None, "released": False}
        deadline = time.monotonic() + config["release_timeout_seconds"]
        while time.monotonic() < deadline:
            scan_lifecycle(config, cursor)
            armed = state / "armed.json"
            if (
                armed.exists()
                and cursor["released"]
                and cursor["active"] is None
                and not cursor["incomplete"]
            ):
                if json.loads(armed.read_text())["config_sha256"] != digest:
                    raise ValueError("Arm marker does not match frozen configuration")
                _check_pins(config)
                if _digest(state / "config.json") != digest:
                    raise ValueError("Frozen supervisor configuration changed")
                scan_lifecycle(config, cursor)
                if cursor["active"] is None and not cursor["incomplete"]:
                    break
            time.sleep(config["poll_seconds"])
        else:
            raise ValueError("Turn release/arming deadline reached")
        _new_json(
            state / "wake-intent.json",
            {
                "session_id": config["session_id"],
                "cwd": config["cwd"],
                "config_sha256": digest,
                **details,
            },
        )
        _status(state, "wake_started", **details)
        with (
            (state / "wake.jsonl").open("xb") as output,
            (state / "wake.stderr.log").open("xb") as errors,
        ):
            result = subprocess.run(  # noqa: S603 - exact saved session, no permission overrides
                command,
                cwd=config["cwd"],
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=errors,
                timeout=config["wake_timeout_seconds"],
                check=False,
            )
        details["wake_returncode"] = result.returncode
        wake_status = "wake_completed" if result.returncode == 0 else "wake_failed"
        if result.returncode != 0:
            # Classify the observed CLI refusal, not the session's current lock state.
            # Raw stderr stays on disk; status never embeds arbitrary process output.
            with (state / "wake.stderr.log").open("rb") as errors:
                diagnostic = errors.read(64 * 1024).decode("utf-8", errors="replace")
            if (
                f"thread {config['session_id']} already has an active writer"
                in diagnostic
            ):
                wake_status = "wake_refused_active_writer"
                details["instruction"] = (
                    "Continue in the existing conversation using bounded process "
                    "waits and inspect the saved experiment results. Do not retry "
                    "CLI resume or bypass the writer lock."
                )
        _status(
            state,
            wake_status,
            **details,
        )
        return 0 if result.returncode == 0 else 1
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        _status(state, "manual_recovery", error=str(exc), **details)
        return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--launch", type=Path, help="Reviewed JSON configuration file")
    modes.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    modes.add_argument("--arm", type=Path)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--config-sha256", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.arm:
        arm(args.arm)
        return 0
    if args.worker:
        return worker(args.worker, args.config_sha256)
    if args.state is None:
        parser.error("--launch requires a new --state directory")
    process = launch(json.loads(args.launch.read_text(encoding="utf-8")), args.state)
    print(
        json.dumps(
            {
                "pid": process.pid,
                "state": str(args.state.absolute()),
                "next": "Arm explicitly; matching turn must complete before one wake.",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
