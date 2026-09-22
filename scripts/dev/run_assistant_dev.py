"""Compose the approved full DEV initial candidate; no tuning or VALID/TEST."""

from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

# Support the Windows launcher without importing another checkout's scripts.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.dev import run_assistant_pilot as runner
from scripts.dev.run_assistant_baseline import LOCK, digest, write_json

ENTRY_FILE = Path(__file__).resolve()


def select_models(value: str) -> list[str]:
    aliases = list(runner._MODELS) if value == "all" else value.split(",")
    if (
        not aliases
        or len(set(aliases)) != len(aliases)
        or set(aliases) - runner._MODELS.keys()
    ):
        raise ValueError("Use approved model aliases once each, or all")
    return [f"{alias}-rag-on" for alias in runner._MODELS if alias in aliases]


def prepare_output(
    output: Path, bank_path: Path, config_path: Path, manifest: dict
) -> None:
    """Retain the exact inputs before executing any case; never replace a run."""
    output.mkdir(parents=True, exist_ok=False)
    inputs = output / "inputs"
    inputs.mkdir()
    shutil.copyfile(bank_path, inputs / "bank.xlsx")
    shutil.copyfile(config_path, inputs / "config.json")
    if (
        digest(inputs / "bank.xlsx") != manifest["bank_sha256"]
        or runner._json(inputs / "config.json") != manifest["config"]
    ):
        raise ValueError(
            "DEV inputs changed during preparation; preserved partial output"
        )
    write_json(inputs / "selection.json", manifest["selection"])
    write_json(output / "prepared-manifest.json", manifest)


def run_attempt(
    manifest: dict,
    bank: dict,
    output: Path,
    *,
    resume: bool,
    replace_invalid: bool = False,
    report_only: bool = False,
) -> int:
    """Compose the existing runner/report; retain each launch and derived report."""
    from scripts.dev.assistant_pilot_presentation import (
        experiment_conditions,
        experiment_title,
        render_evidence_notice,
        render_overview,
        render_page,
    )
    from scripts.dev.assistant_pilot_report import write_report

    attempt = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-") + uuid4().hex[:8]
    for name in ("launches", "reports"):
        (output / name).mkdir(exist_ok=True)
    report_path = output / "reports" / attempt
    info = {
        "entry_sha256": digest(ENTRY_FILE),
        "source": manifest["source"],
        "resume": resume,
        "replace_invalid": replace_invalid,
        "report_only": report_only,
    }
    write_json(output / "launches" / (attempt + "-start.json"), info)
    code, error, report = 0, None, None
    audit = {}
    try:
        if not report_only:
            code = runner.execute(
                manifest,
                bank,
                output / "raw",
                resume=resume,
                replace_invalid=replace_invalid,
            )
    except KeyboardInterrupt:
        code, error = 130, "Interrupted; unresolved child cleanup blocks resume."
    except Exception as exc:
        code, error = 1, str(exc)[:2000]
    runner_code = None if report_only else code
    if (output / "raw" / "manifest.json").is_file():
        try:
            report = write_report(output / "raw", report_path)
            audit = runner._json(report_path / "presentation-audit.json")
            if (
                not report["complete_selected_schedule"]
                or audit["selected_complete"] is not True
            ):
                code = code or 1
        except Exception as exc:
            code, error = (
                code or 1,
                "Report failed; raw evidence retained: " + str(exc)[:2000],
            )
    else:
        code = code or 1
    link = (
        report_path.relative_to(output).as_posix() + "/index.html" if report else None
    )
    info.update(runner_exit_code=runner_code, exit_code=code, error=error, report=link)
    write_json(output / "launches" / (attempt + "-end.json"), info)
    status = (
        "Selected DEV schedule complete"
        if code == 0
        else f"Incomplete DEV attempt (exit {code})"
    )
    notice = "Initial DEV candidate, RAG on. Full baseline requires all five models / 1,320 valid measurements. No tuning, VALID or TEST."
    title = experiment_title(output, dev=True)
    text = f"# {title}\n\n{status}\n\n{notice}\n\n"
    page = (
        '<header class="hero"><span class="eyebrow">XBrainLab / Experiment report</span>'
        f"<h1>{html.escape(title)}</h1>"
        f'<p class="muted">{html.escape(experiment_conditions(report or {}, dev=True))}</p></header>'
        f'<p class="{"badge" if code == 0 else "notice"}">'
        + (
            "Selected results complete"
            if code == 0
            else "Results incomplete — see technical details"
        )
        + "</p>"
    )
    if link:
        text += f"[{title}]({link})\n\n"
        page += f'<p><a class="button" href="{link}">View {html.escape(output.name.upper())} report &rarr;</a></p>'
    if report:
        page += render_evidence_notice(audit.get("issues", {}))
        page += render_overview(report)
    text += "inputs/: fixed inputs; raw/: original measurements; reports/: immutable reports; launches/: execution status.\n\n"
    text += error or ""
    page += (
        "<details><summary>Technical details</summary>"
        "<p>Inputs and raw measurements are retained unchanged. Reports are versioned; "
        "this page is navigation, not a new measurement.</p>"
        '<nav><a href="README.md">Folder guide</a>'
        '<a href="raw/manifest.json">Frozen manifest</a></nav>'
    )
    if error:
        page += "<pre>" + html.escape(error) + "</pre>"
    page += "</details>"
    # Only derived navigation is refreshed; all evidence and prior reports remain immutable.
    (output / "README.md").write_text(text, encoding="utf-8")
    (output / "index.html").write_text(render_page(title, page), encoding="utf-8")
    print(status + ": " + str(output / "index.html"), flush=True)
    return code


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "resume", "report"))
    parser.add_argument("--models")
    for name in ("bank", "config", "output", "manifest-output", "expected-manifest"):
        parser.add_argument(f"--{name}", type=Path)
    parser.add_argument("--replace-invalid", action="store_true")
    args = parser.parse_args(argv)
    if args.expected_manifest is not None and args.action != "run":
        parser.error("--expected-manifest requires run")
    if args.replace_invalid and args.action != "resume":
        parser.error("--replace-invalid requires resume")
    if args.action == "report":
        if args.output is None:
            parser.error("report requires --output RUN_DIRECTORY")
        manifest = runner._json(args.output / "raw" / "manifest.json")
        if manifest.get("experiment") != runner.DEV_EXPERIMENT:
            raise ValueError("Report entry requires an initial DEV run")
        inputs = args.output / "inputs"
        if (
            runner._json(args.output / "prepared-manifest.json") != manifest
            or digest(inputs / "bank.xlsx") != manifest["bank_sha256"]
            or runner._json(inputs / "config.json") != manifest["config"]
            or runner._json(inputs / "selection.json") != manifest["selection"]
        ):
            raise ValueError(
                "Retained DEV manifest or inputs differ; original run preserved"
            )
        return run_attempt(manifest, {}, args.output, resume=False, report_only=True)
    if args.action == "resume":
        if args.output is None:
            parser.error("resume requires --output RUN_DIRECTORY")
        for name, retained in (("bank", "bank.xlsx"), ("config", "config.json")):
            saved = args.output / "inputs" / retained
            supplied = getattr(args, name)
            if supplied is not None and digest(supplied) != digest(saved):
                raise ValueError("Supplied resume input differs from retained " + name)
            setattr(args, name, saved)
    if (
        args.bank is None
        or args.config is None
        or (args.action != "prepare" and args.output is None)
    ):
        parser.error("--bank, --config and (for run/resume) --output are required")
    from scripts.dev.assistant_pilot_case import bootstrap_case_checkout

    os.environ.update(
        QT_QPA_PLATFORM=runner.DEV_EXPERIMENT["qt_platform"],
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        PYTHONPATH=str(runner.ROOT),
    )
    bootstrap_case_checkout()
    conditions = select_models(args.models or "all")
    if args.action == "resume" and args.models is None:
        retained = runner._json(args.output / "prepared-manifest.json")
        conditions = list(dict.fromkeys(job["condition"] for job in retained["jobs"]))
    manifest, bank = runner.prepare_manifest(
        args.bank, None, args.config, conditions, dev_initial=True
    )
    if (
        args.expected_manifest is not None
        and runner._json(args.expected_manifest) != manifest
    ):
        raise ValueError(
            "Prepared DEV differs from the expected manifest; launch refused"
        )
    if args.action == "prepare":
        if args.manifest_output is not None:
            write_json(args.manifest_output, manifest)
            print(str(args.manifest_output))
        else:
            print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    if os.name != "nt":
        parser.error("DEV model execution requires the existing Windows runtime")
    from filelock import FileLock

    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(LOCK), timeout=0):
        if args.action == "run":
            prepare_output(args.output, args.bank, args.config, manifest)
        elif runner._json(args.output / "prepared-manifest.json") != manifest:
            raise ValueError("Frozen DEV manifest differs; original run preserved")
        return run_attempt(
            manifest,
            bank,
            args.output,
            resume=args.action == "resume",
            replace_invalid=args.replace_invalid,
        )


if __name__ == "__main__":
    raise SystemExit(main())
