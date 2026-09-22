"""Offline replay of a sealed run using each candidate's own scoring code.

This composes existing scorers and evidence readers, not a second scoring policy.
It never loads a model, retries a response or changes saved scores. Consistency
with the frozen scorer does not establish that the human oracle is correct.
"""

# Fixed read-only Git and this module's worker; no shell execution. Replay
# failures are retained as evidence instead of escaping the aggregation loop.
# ruff: noqa: S603, S607, TRY301

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def evidence_digest(run: Path) -> dict:
    """Fingerprint evidence, excluding external cache links and new audit output."""
    files = {}
    for name in ("raw", "inputs", "reports", "launches"):
        for base, directories, names in os.walk(run / name, followlinks=False):
            for child in directories[:] + names:
                path = Path(base) / child
                relative = path.relative_to(run).as_posix()
                if path.is_symlink() or path.is_junction():
                    files[relative] = {"link": os.readlink(path)}
                    if child in directories:
                        directories.remove(child)
                elif path.is_file():
                    files[relative] = _digest(path)
    for name in ("prepared-manifest.json", "index.html", "README.md"):
        path = run / name
        if path.is_file():
            files[name] = _digest(path)
    return {
        "entries": len(files),
        "sha256": hashlib.sha256(
            json.dumps(files, sort_keys=True).encode()
        ).hexdigest(),
    }


def replay_rows(rows, read_detail, scorer, input_audit, experiment: dict) -> dict:
    """Replay existing functions; keep evidence failures distinct from wrong answers."""
    issues = []
    for row in rows:
        problems = []
        try:
            detail = read_detail(row)
            problems.extend(detail["issues"])
            request, result = detail["request"], detail["result"]
            if not request or not result:
                problems.append("missing_request_or_result")
            else:
                arguments = {"decision_timed_out": result["decision_timed_out"]}
                if "max_format_recovery_attempts" in experiment:
                    arguments["max_format_recovery_attempts"] = experiment[
                        "max_format_recovery_attempts"
                    ]
                replay = scorer(request["case"], result["trace"], **arguments)
                if replay != result["scores"]:
                    problems.append("score_replay_mismatch")
                replay_input = input_audit(
                    request["case"],
                    request["fixture"],
                    result["trace"],
                    decision_timed_out=result["decision_timed_out"],
                )
                if replay_input != result["input_audit"]:
                    problems.append("input_audit_replay_mismatch")
        except (ValueError, KeyError, TypeError, OSError) as error:
            problems.append("evidence_replay_failed:" + str(error)[:500])
        if problems:
            issues.append({"id": row["id"], "issues": problems})
    return {"checked": len(rows), "issues": issues}


def _worker(source: Path) -> dict:
    # The executable script belongs to the coordinator, but every research
    # import below belongs to the selected frozen candidate, including parser.
    sys.path.insert(0, str(source))
    payload = json.load(sys.stdin)
    head = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        text=True,
        timeout=15,
    ).strip()
    if head != payload["source_head"]:
        raise ValueError("Replay candidate source differs")
    from scripts.dev.assistant_pilot_case import bootstrap_case_checkout

    bootstrap_case_checkout()
    from scripts.dev import assistant_pilot_scoring as scoring
    from scripts.dev.active_checkout import assert_active_checkout_import
    from scripts.dev.assistant_pilot_case import audit_initial_input
    from scripts.dev.assistant_pilot_presentation import _details
    from scripts.dev.run_assistant_pilot import environment_identity

    assert_active_checkout_import(source)
    result = replay_rows(
        payload["rows"],
        lambda row: _details(Path(payload["raw"]), row, require_generation=True),
        scoring.score_case_decisions,
        audit_initial_input,
        payload["experiment"],
    )
    return {
        **result,
        "source_head": head,
        "scorer_sha256": _digest(Path(scoring.__file__)),
        "environment": environment_identity(),
    }


def audit_package(
    package: Path, requested_run: Path, output: Path | None = None
) -> dict:
    from scripts.dev.assistant_experiment_package import _retained_run, verify_package
    from scripts.dev.assistant_pilot_report import build_report
    from scripts.dev.run_assistant_dev import verify_retained_inputs

    package = package.resolve(strict=True)
    package_manifest = verify_package(package)
    run = _retained_run(package, requested_run)
    if output is None:
        identifier = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-") + uuid4().hex[:8]
        output = run / "audits" / (identifier + ".json")
    if output.exists():
        raise FileExistsError(output)
    if output.resolve().is_relative_to(run) and output.parent != run / "audits":
        raise ValueError("Audit output must not be inside original evidence")
    before = evidence_digest(run)
    retained = json.loads((run / "raw/manifest.json").read_text(encoding="utf-8"))
    verify_retained_inputs(run, retained)
    if retained["config"] != json.loads(
        (package / "inputs/config.json").read_text(encoding="utf-8")
    ) or retained["bank_sha256"] != _digest(package / "inputs/bank.xlsx"):
        raise ValueError("Run inputs differ from the sealed experiment package")
    results, issues = [], []
    report = build_report(run / "raw")
    if not report["complete_selected_schedule"]:
        issues.append("selected_schedule_or_cleanup_incomplete")
    for head in sorted({row["source_head"] for row in report["cases"]}):
        if head not in package_manifest["sources"]:
            raise ValueError("Run candidate is absent from the sealed package")
        source = package / "sources" / head
        payload = {
            "source_head": head,
            "raw": str(run / "raw"),
            "rows": [row for row in report["cases"] if row["source_head"] == head],
            "experiment": report["experiment"],
        }
        environment = dict(
            os.environ,
            PYTHONPATH=str(source),
            HF_HUB_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
            QT_QPA_PLATFORM="offscreen",
            PYTHONDONTWRITEBYTECODE="1",
        )
        try:
            process = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--worker-source",
                    str(source),
                ],
                cwd=source,
                env=environment,
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                check=True,
                timeout=300,
            )
            result = json.loads(process.stdout)
            if result["source_head"] != head or result["checked"] != len(
                payload["rows"]
            ):
                raise ValueError("Replay worker identity or denominator differs")
            results.append(result)
            issues.extend(result["issues"])
        except (subprocess.SubprocessError, ValueError, KeyError) as error:
            issues.append(
                {
                    "source_head": head,
                    "error": str(error)[:1000],
                    "stderr": str(getattr(error, "stderr", ""))[-2000:],
                }
            )
    if evidence_digest(run) != before:
        issues.append("original_evidence_changed")
    verify_package(package)
    result = {
        "schema": "xbrainlab.assistant_experiment_audit.v1",
        "passed": not issues,
        "run": str(run),
        "selected_cases": len(report["cases"]),
        "issues": issues,
        "coordinator": package_manifest["coordinator"],
        "audit_script_sha256": _digest(Path(__file__)),
        "original_evidence": before,
        "candidate_replays": results,
        "scope": "Frozen scorer, input and capture replay only; no inference, score changes or human oracle certification.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({"passed": result["passed"], "output": str(output)}), flush=True)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--run", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker-source", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker_source:
        print(json.dumps(_worker(args.worker_source.resolve(strict=True))))
        return 0
    if args.package is None or args.run is None:
        parser.error("--package and --run are required")
    return 0 if audit_package(args.package, args.run, args.output)["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
