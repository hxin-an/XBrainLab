"""Command-line interface for the Agent tool-call showcase."""

from __future__ import annotations

import argparse
import contextlib
import fnmatch
import io
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from XBrainLab.backend.utils.public_diagnostics import public_diagnostic_text

from .cases import SHOWCASE_CASES, ShowcaseCase, filter_cases
from .report import render_stdout, sanitize_payload, write_reports
from .runner import (
    DIAGNOSTIC_DISCLAIMER,
    SCHEMA_VERSION,
    ShowcaseContractError,
    ShowcaseRunner,
    current_source_commit,
    current_source_fingerprint,
    finalize_showcase_payload,
    resumable_passed_cases,
)
from .selector import DeterministicSelector, GraniteSelector

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = ROOT / "build" / "dev-artifacts" / "agent-toolcall-showcase"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a fast product showcase of XBrainLab Agent tool-call handling. "
            "This is not a thesis benchmark."
        )
    )
    parser.add_argument(
        "--list-cases",
        action="store_true",
        help="List matching built-in cases without initializing the application.",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        metavar="PATTERN",
        help="Select case ids/titles/tags by substring or glob; repeatable.",
    )
    parser.add_argument(
        "--area",
        action="append",
        default=[],
        metavar="PATTERN",
        help="Select case areas by substring or glob; repeatable.",
    )
    parser.add_argument(
        "--filter",
        action="append",
        default=[],
        metavar="PATTERN",
        help="Compatibility alias for --case.",
    )
    parser.add_argument(
        "--resume",
        type=Path,
        help="Reuse passing terminal cases from a prior showcase JSON report.",
    )
    parser.add_argument(
        "--real-granite",
        action="store_true",
        help="Use the exact offline product Granite model for proposal selection.",
    )
    parser.add_argument(
        "--details",
        "--verbose",
        action="store_true",
        help="Print complete per-case details (automatic for one selected case).",
    )
    parser.add_argument(
        "--model-cache-dir",
        type=Path,
        help="Explicit existing model cache for --real-granite; never downloaded.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        help="Machine-readable output path (default: build/.../latest.json).",
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        help="Readable output path (default: build/.../latest.md).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cases = _selected_cases(
        case_patterns=[*args.case, *args.filter],
        area_patterns=args.area,
    )
    if args.list_cases:
        _print_case_list(cases)
        return 0 if cases else 2
    if not cases:
        print("No showcase cases matched. Use --list-cases to inspect the catalog.")
        return 2

    output_dir = DEFAULT_OUTPUT_DIR
    json_path = (args.json_out or output_dir / "latest.json").resolve()
    markdown_path = (args.markdown_out or output_dir / "latest.md").resolve()
    retained: dict[str, dict[str, Any]] = {}
    resumed_from: str | None = None

    try:
        with _quiet_runtime_output():
            selector = (
                GraniteSelector(model_cache_dir=args.model_cache_dir)
                if args.real_granite
                else DeterministicSelector()
            )
    except Exception as exc:
        payload = _runtime_initialization_failure(
            cases,
            error=public_diagnostic_text(str(exc)),
        )
        sanitized, _markdown = write_reports(
            payload,
            json_path=json_path,
            markdown_path=markdown_path,
        )
        print(
            render_stdout(
                sanitized,
                include_details=args.details or len(cases) == 1,
            ),
            end="",
        )
        _print_report_paths(json_path, markdown_path)
        return 1

    if args.resume is not None:
        try:
            resume_path = args.resume.resolve()
            prior = json.loads(resume_path.read_text(encoding="utf-8"))
            retained = resumable_passed_cases(
                _require_resume_object(prior),
                expected_cases=cases,
                expected_source_commit=current_source_commit(),
                expected_source_fingerprint=current_source_fingerprint(),
                expected_selector=selector.metadata(),
            )
            resumed_from = str(resume_path)
        except (OSError, json.JSONDecodeError, ShowcaseContractError) as exc:
            selector.close()
            print(f"Resume failed: {public_diagnostic_text(str(exc))}")
            return 2

    try:
        with _quiet_runtime_output():
            runner = ShowcaseRunner(output_dir=output_dir, selector=selector)
            payload = runner.run(
                cases,
                resumed_from=resumed_from,
                retained_cases=retained,
            )
        payload = finalize_showcase_payload(payload, cases)
        sanitized, _markdown = write_reports(
            payload,
            json_path=json_path,
            markdown_path=markdown_path,
        )
    except Exception as exc:
        selector.close()
        print(f"Showcase failed closed: {public_diagnostic_text(str(exc))}")
        return 1

    print(
        render_stdout(
            sanitized,
            include_details=args.details or len(cases) == 1,
        ),
        end="",
    )
    _print_report_paths(json_path, markdown_path)
    summary = sanitized.get("summary")
    return 0 if isinstance(summary, dict) and summary.get("status") == "passed" else 1


def _selected_cases(
    *,
    case_patterns: list[str],
    area_patterns: list[str],
) -> list[ShowcaseCase]:
    cases = filter_cases(case_patterns, cases=SHOWCASE_CASES)
    normalized_areas = [
        item.strip().casefold() for item in area_patterns if item.strip()
    ]
    if not normalized_areas:
        return cases
    return [
        case
        for case in cases
        if any(
            pattern in case.area.casefold()
            or fnmatch.fnmatchcase(case.area.casefold(), pattern)
            for pattern in normalized_areas
        )
    ]


def _require_resume_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ShowcaseContractError("Resume artifact root must be an object.")
    return value


def _print_case_list(cases: list[ShowcaseCase]) -> None:
    print(f"{len(cases)} Agent tool-call showcase case(s)")
    print("This catalog is a product diagnostic, not a thesis benchmark.\n")
    for case in cases:
        tags = ", ".join(case.tags)
        print(f"{case.case_id:38} {case.area:28} {case.title} [{tags}]")


def _runtime_initialization_failure(
    cases: list[ShowcaseCase],
    *,
    error: str,
) -> dict[str, Any]:
    case_results = [
        {
            "case_id": case.case_id,
            "case_identity": case.identity(),
            "prompt_identity": case.prompt_identity(),
            "title": case.title,
            "area": case.area,
            "prompt": case.prompt,
            "state_before": {},
            "capabilities": {},
            "exposed_tool_schema_names": [],
            "selection": {
                "owner": "ibm_granite_product_runtime",
                "parse_status": "runtime_unavailable",
            },
            "selected_tool": None,
            "selected_parameters": None,
            "verification": {
                "status": "runtime_unavailable",
                "valid": False,
                "message": error,
            },
            "confirmation": None,
            "handoff": None,
            "command_result": None,
            "changed_state": {},
            "state_after": {},
            "user_visible_presentation": (
                "The exact local Granite runtime is unavailable. No action was run."
            ),
            "terminal": {"kind": "runtime_initialization", "status": "failed"},
            "duration_ms": 0.0,
            "failures": [error],
            "pass": False,
        }
        for case in cases
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "product_showcase_diagnostic",
        "disclaimer": DIAGNOSTIC_DISCLAIMER,
        "run": {
            "status": "failed",
            "mode": "real_granite",
            "started_at": datetime.now(UTC).isoformat(),
            "duration_ms": 0.0,
            "case_count": len(cases),
            "selector": {
                "mode": "real_granite",
                "model_owned": True,
                "initialization_error": error,
            },
        },
        "summary": {
            "status": "failed",
            "total": len(cases),
            "passed": 0,
            "failed": len(cases),
            "missing_terminal_outcomes": 0,
        },
        "generated_data": {
            "written": False,
            "kind": None,
            "path": None,
            "bytes": 0,
            "downloaded": False,
        },
        "limitations": [DIAGNOSTIC_DISCLAIMER],
        "cases": case_results,
    }


def _print_report_paths(json_path: Path, markdown_path: Path) -> None:
    print(f"JSON report: {_display_path(json_path)}")
    print(f"Markdown report: {_display_path(markdown_path)}")


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        sanitized = sanitize_payload(str(path))
        return str(sanitized)


@contextlib.contextmanager
def _quiet_runtime_output():
    """Keep private third-party runtime logs out of the public CLI stream."""
    prior_disable_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            yield
    finally:
        logging.disable(prior_disable_level)
