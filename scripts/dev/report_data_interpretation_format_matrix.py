#!/usr/bin/env python3
"""Report Data Interpretation format boundaries from the live command path."""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scipy.io import savemat

from XBrainLab.backend.application.commands import (
    PreviewInterpretationCommand,
    ScanSourceCommand,
    ValidateInterpretationCommand,
)
from XBrainLab.backend.application.service import ApplicationService
from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.logger import logger as xbrainlab_logger

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "artifacts" / "data_interpretation"
ARTIFACT_JSON = "format-capability-matrix.json"
ARTIFACT_MARKDOWN = "format-capability-matrix.md"


@dataclass(frozen=True)
class FixtureFile:
    """A small synthetic file used only for scan/preview capability reporting."""

    relative_path: str
    kind: str = "binary"


@dataclass(frozen=True)
class ExpectedCapability:
    """Expected capability row for one detected file."""

    coverage_label: str
    filename: str
    format_name: str
    role: str
    status: str
    message_contains: str


@dataclass(frozen=True)
class FormatCase:
    """One scan/preview/validate source fixture."""

    case_id: str
    title: str
    source_entry: str
    source_hint: str
    expected_validation: str
    files: tuple[FixtureFile, ...]
    expected_capabilities: tuple[ExpectedCapability, ...]


FORMAT_CASES: tuple[FormatCase, ...] = (
    FormatCase(
        case_id="gdf_with_mat_labels",
        title="GDF recording with external MAT labels",
        source_entry=".",
        source_hint="auto",
        expected_validation="needs_confirmation",
        files=(
            FixtureFile("sub-01_ses-01_task-mi_run-1.gdf"),
            FixtureFile("sub-01_ses-01_task-mi_run-1.mat", "mat_labels"),
        ),
        expected_capabilities=(
            ExpectedCapability(
                "GDF recording",
                "sub-01_ses-01_task-mi_run-1.gdf",
                "GDF",
                "eeg",
                "needs_review",
                "trial anchor",
            ),
            ExpectedCapability(
                "MAT labels",
                "sub-01_ses-01_task-mi_run-1.mat",
                "MAT labels",
                "external_labels",
                "needs_review",
                "variable selection",
            ),
        ),
    ),
    FormatCase(
        case_id="edf_recording",
        title="EDF recording with annotation review boundary",
        source_entry="sub-01_ses-01_task-rest_run-1.edf",
        source_hint="file",
        expected_validation="needs_confirmation",
        files=(FixtureFile("sub-01_ses-01_task-rest_run-1.edf"),),
        expected_capabilities=(
            ExpectedCapability(
                "EDF recording",
                "sub-01_ses-01_task-rest_run-1.edf",
                "EDF",
                "eeg",
                "needs_review",
                "annotations",
            ),
        ),
    ),
    FormatCase(
        case_id="bdf_recording",
        title="BDF recording with annotation review boundary",
        source_entry="sub-01_ses-01_task-rest_run-2.bdf",
        source_hint="file",
        expected_validation="needs_confirmation",
        files=(FixtureFile("sub-01_ses-01_task-rest_run-2.bdf"),),
        expected_capabilities=(
            ExpectedCapability(
                "BDF recording",
                "sub-01_ses-01_task-rest_run-2.bdf",
                "EDF",
                "eeg",
                "needs_review",
                "EDF / BDF",
            ),
        ),
    ),
    FormatCase(
        case_id="eeglab_set",
        title="EEGLAB SET with boundary-marker review",
        source_entry="sub-01_ses-01_task-mi_run-1.set",
        source_hint="file",
        expected_validation="needs_confirmation",
        files=(FixtureFile("sub-01_ses-01_task-mi_run-1.set"),),
        expected_capabilities=(
            ExpectedCapability(
                "EEGLAB SET",
                "sub-01_ses-01_task-mi_run-1.set",
                "EEGLAB",
                "eeg",
                "needs_review",
                "boundary",
            ),
        ),
    ),
    FormatCase(
        case_id="brainvision_recording",
        title="BrainVision header plus marker sidecar",
        source_entry=".",
        source_hint="folder",
        expected_validation="needs_confirmation",
        files=(
            FixtureFile("sub-01_ses-01_task-mi_run-1.vhdr", "brainvision_vhdr"),
            FixtureFile("sub-01_ses-01_task-mi_run-1.vmrk", "brainvision_vmrk"),
            FixtureFile("sub-01_ses-01_task-mi_run-1.eeg"),
        ),
        expected_capabilities=(
            ExpectedCapability(
                "BrainVision VHDR",
                "sub-01_ses-01_task-mi_run-1.vhdr",
                "BrainVision",
                "eeg",
                "needs_review",
                "marker sidecars",
            ),
            ExpectedCapability(
                "BrainVision VMRK",
                "sub-01_ses-01_task-mi_run-1.vmrk",
                "BrainVision markers",
                "sidecar",
                "context",
                "associated .vhdr",
            ),
        ),
    ),
    FormatCase(
        case_id="mne_fif_recording",
        title="MNE FIF recording with complete filename metadata",
        source_entry="sub-01_ses-01_task-rest_run-1_raw.fif",
        source_hint="file",
        expected_validation="safe",
        files=(FixtureFile("sub-01_ses-01_task-rest_run-1_raw.fif"),),
        expected_capabilities=(
            ExpectedCapability(
                "MNE FIF",
                "sub-01_ses-01_task-rest_run-1_raw.fif",
                "MNE FIF",
                "eeg",
                "supported",
                "loaded as an EEG recording",
            ),
        ),
    ),
    FormatCase(
        case_id="bids_events_root",
        title="BIDS-like root with events.tsv",
        source_entry=".",
        source_hint="auto",
        expected_validation="needs_confirmation",
        files=(
            FixtureFile("dataset_description.json", "dataset_description"),
            FixtureFile("sub-01/ses-01/eeg/sub-01_ses-01_task-mi_run-1_raw.fif"),
            FixtureFile(
                "sub-01/ses-01/eeg/sub-01_ses-01_task-mi_run-1_events.tsv",
                "bids_events",
            ),
        ),
        expected_capabilities=(
            ExpectedCapability(
                "BIDS events.tsv",
                "sub-01_ses-01_task-mi_run-1_events.tsv",
                "BIDS events",
                "external_labels",
                "needs_review",
                "onset and duration",
            ),
        ),
    ),
    FormatCase(
        case_id="tabular_and_text_labels",
        title="Generic CSV, TSV, and TXT label carriers",
        source_entry=".",
        source_hint="folder",
        expected_validation="needs_confirmation",
        files=(
            FixtureFile("sub-01_ses-01_task-mi_run-1_raw.fif"),
            FixtureFile("labels.csv", "csv_labels"),
            FixtureFile("labels.tsv", "tsv_labels"),
            FixtureFile("labels.txt", "txt_labels"),
        ),
        expected_capabilities=(
            ExpectedCapability(
                "CSV labels",
                "labels.csv",
                "CSV / TSV labels",
                "external_labels",
                "needs_review",
                "label column",
            ),
            ExpectedCapability(
                "TSV labels",
                "labels.tsv",
                "CSV / TSV labels",
                "external_labels",
                "needs_review",
                "label column",
            ),
            ExpectedCapability(
                "TXT labels",
                "labels.txt",
                "TXT labels",
                "external_labels",
                "needs_review",
                "trial-order",
            ),
        ),
    ),
    FormatCase(
        case_id="xdf_lsl_device_export",
        title="XDF / LSL stream export blocked until stream selection exists",
        source_entry="session01_streams.xdf",
        source_hint="device_export",
        expected_validation="blocked",
        files=(FixtureFile("session01_streams.xdf"),),
        expected_capabilities=(
            ExpectedCapability(
                "XDF / LSL stream export",
                "session01_streams.xdf",
                "XDF / LSL",
                "device_export",
                "blocked",
                "stream selection",
            ),
        ),
    ),
)


def build_format_capability_snapshot() -> dict[str, Any]:
    """Build a matrix from actual ApplicationService scan/preview/validate calls."""
    with (
        _suppress_application_info_logs(),
        tempfile.TemporaryDirectory(prefix="xbrainlab-di-format-") as temp_dir,
    ):
        fixture_root = Path(temp_dir)
        rows: list[dict[str, Any]] = []
        case_summaries: list[dict[str, Any]] = []
        for case in FORMAT_CASES:
            case_dir = fixture_root / case.case_id
            _write_case_fixture(case_dir, case)
            case_result = _run_case(case_dir, case)
            case_summaries.append(case_result["case_summary"])
            rows.extend(case_result["rows"])

    coverage_labels = [str(row["coverage_label"]) for row in rows]
    all_observed = all(bool(row["observed"]) for row in rows)
    all_matched = all(bool(row["matches_expected"]) for row in rows)
    return {
        "generator": "scripts/dev/report_data_interpretation_format_matrix.py",
        "command_path": [
            "ApplicationService.execute(ScanSourceCommand)",
            "ApplicationService.execute(PreviewInterpretationCommand)",
            "ApplicationService.execute(ValidateInterpretationCommand)",
        ],
        "summary": {
            "case_count": len(FORMAT_CASES),
            "row_count": len(rows),
            "coverage_labels": coverage_labels,
            "statuses": sorted({str(row["status"]) for row in rows}),
            "validation_decisions": sorted(
                {str(row["validation_decision"]) for row in rows}
            ),
            "all_expected_capabilities_observed": all_observed,
            "all_expected_capabilities_match": all_matched,
        },
        "cases": case_summaries,
        "rows": rows,
        "claim_boundary": {
            "supports": (
                "Data Interpretation scan, preview, and validation expose "
                "user-facing format capability boundaries for representative "
                "EEG recordings, label carriers, BIDS events, and blocked XDF / "
                "LSL stream exports."
            ),
            "does_not_support": (
                "This matrix does not implement an XDF / LSL stream parser, "
                "raw-event-anchor-specific GDF / MAT alignment, or a full manual "
                "compatibility certification across real public datasets."
            ),
        },
    }


def write_artifacts(
    snapshot: dict[str, Any],
    output_dir: Path = ARTIFACT_DIR,
) -> tuple[Path, Path]:
    """Write JSON and Markdown artifacts for the current matrix."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / ARTIFACT_JSON
    markdown_path = output_dir / ARTIFACT_MARKDOWN
    json_path.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(snapshot) + "\n", encoding="utf-8")
    return json_path, markdown_path


def render_markdown(snapshot: dict[str, Any]) -> str:
    """Render the format matrix in Markdown."""
    lines = [
        "# Data Interpretation Format Capability Matrix",
        "",
        "Generated from the live ApplicationService command path:",
        "",
        "- `ScanSourceCommand`",
        "- `PreviewInterpretationCommand`",
        "- `ValidateInterpretationCommand`",
        "",
        "| Coverage | Source fixture | Detected format | Role | Status | Validation | Boundary |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in snapshot["rows"]:
        lines.append(
            "| {coverage_label} | {source_fixture} | {format} | {role} | "
            "{status} | {validation_decision} | {message} |".format(
                coverage_label=_escape_markdown(row["coverage_label"]),
                source_fixture=_escape_markdown(row["source_fixture"]),
                format=_escape_markdown(row["format"]),
                role=_escape_markdown(row["role"]),
                status=_escape_markdown(row["status"]),
                validation_decision=_escape_markdown(row["validation_decision"]),
                message=_escape_markdown(row["message"]),
            )
        )

    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Cases: `{snapshot['summary']['case_count']}`",
            f"- Matrix rows: `{snapshot['summary']['row_count']}`",
            "- Statuses: "
            + ", ".join(f"`{item}`" for item in snapshot["summary"]["statuses"]),
            "- Validation decisions: "
            + ", ".join(
                f"`{item}`" for item in snapshot["summary"]["validation_decisions"]
            ),
            "- All expected capabilities observed: "
            f"`{snapshot['summary']['all_expected_capabilities_observed']}`",
            "- All expected capabilities match: "
            f"`{snapshot['summary']['all_expected_capabilities_match']}`",
            "",
            "## Claim Boundary",
            "",
            f"- Supports: {snapshot['claim_boundary']['supports']}",
            f"- Does not support: {snapshot['claim_boundary']['does_not_support']}",
        ]
    )
    return "\n".join(lines)


def _run_case(case_dir: Path, case: FormatCase) -> dict[str, Any]:
    source_path = case_dir / case.source_entry
    service = ApplicationService(Study())

    scan = service.execute(
        ScanSourceCommand(
            source_path=str(source_path),
            source_hint=case.source_hint,
        )
    )
    preview = service.execute(PreviewInterpretationCommand())
    validation = service.execute(ValidateInterpretationCommand())

    scan_result = scan.diagnostics["scan_result"]
    preview_payload = preview.diagnostics["preview"]
    validation_payload = validation.diagnostics["validation_decision"]
    capabilities = {
        str(item.get("name")): item
        for item in scan_result.get("format_capabilities", [])
    }

    rows = [
        _row_for_expected_capability(
            case=case,
            expected=expected,
            actual=capabilities.get(expected.filename),
            preview_payload=preview_payload,
            validation_payload=validation_payload,
        )
        for expected in case.expected_capabilities
    ]
    return {
        "case_summary": {
            "case_id": case.case_id,
            "title": case.title,
            "source_hint": case.source_hint,
            "source_entry": case.source_entry,
            "source_files": [item.relative_path for item in case.files],
            "source_kind": scan_result["source_kind"],
            "eeg_files": _names(scan_result.get("eeg_files", [])),
            "label_carriers": _names(scan_result.get("label_carriers", [])),
            "warning_count": len(scan_result.get("warnings", [])),
            "blocked_reasons": list(scan_result.get("blocked_reasons", [])),
            "preview_summary": preview_payload["summary"],
            "validation_decision": validation_payload["decision"],
        },
        "rows": rows,
    }


def _row_for_expected_capability(
    *,
    case: FormatCase,
    expected: ExpectedCapability,
    actual: dict[str, Any] | None,
    preview_payload: dict[str, Any],
    validation_payload: dict[str, Any],
) -> dict[str, Any]:
    observed = actual is not None
    actual = actual or {}
    message = str(actual.get("message", ""))
    matches_expected = (
        observed
        and actual.get("format") == expected.format_name
        and actual.get("role") == expected.role
        and actual.get("status") == expected.status
        and expected.message_contains in message
        and validation_payload.get("decision") == case.expected_validation
    )
    return {
        "case_id": case.case_id,
        "coverage_label": expected.coverage_label,
        "source_fixture": expected.filename,
        "source_hint": case.source_hint,
        "source_kind_validation": case.expected_validation,
        "format": str(actual.get("format", "")),
        "role": str(actual.get("role", "")),
        "status": str(actual.get("status", "")),
        "message": message,
        "validation_decision": str(validation_payload.get("decision", "")),
        "required_confirmations": list(
            validation_payload.get("required_confirmations", [])
        ),
        "blocked_reasons": list(validation_payload.get("blocked_reasons", [])),
        "preview_summary": str(preview_payload.get("summary", "")),
        "preview_blocked_reasons": list(preview_payload.get("blocked_reasons", [])),
        "preview_confirmation_items": list(
            preview_payload.get("confirmation_items", [])
        ),
        "observed": observed,
        "matches_expected": matches_expected,
    }


def _write_case_fixture(case_dir: Path, case: FormatCase) -> None:
    for fixture in case.files:
        path = case_dir / fixture.relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_fixture_file(path, fixture.kind)


def _write_fixture_file(path: Path, kind: str) -> None:
    if kind == "dataset_description":
        path.write_text(
            json.dumps(
                {
                    "Name": "XBrainLab format capability fixture",
                    "BIDSVersion": "1.9.0",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    elif kind == "mat_labels":
        savemat(
            str(path),
            {
                "classlabel": [[1, 2, 1, 2]],
                "cue_onset": [[0, 250, 500, 750]],
            },
        )
    elif kind == "bids_events":
        path.write_text(
            "onset\tduration\ttrial_type\n0.0\t1.0\tleft\n2.0\t1.0\tright\n",
            encoding="utf-8",
        )
    elif kind == "csv_labels":
        path.write_text("sample,label\n0,left\n250,right\n", encoding="utf-8")
    elif kind == "tsv_labels":
        path.write_text("trial\tclass\n1,left\n2,right\n", encoding="utf-8")
    elif kind == "txt_labels":
        path.write_text("left\nright\n", encoding="utf-8")
    elif kind == "brainvision_vhdr":
        path.write_text(
            "Brain Vision Data Exchange Header File Version 1.0\n"
            "[Common Infos]\n"
            "DataFile=sub-01_ses-01_task-mi_run-1.eeg\n"
            "MarkerFile=sub-01_ses-01_task-mi_run-1.vmrk\n",
            encoding="utf-8",
        )
    elif kind == "brainvision_vmrk":
        path.write_text(
            "Brain Vision Data Exchange Marker File, Version 1.0\n"
            "[Marker Infos]\n"
            "Mk1=Stimulus,S  1,1,1,0\n",
            encoding="utf-8",
        )
    else:
        path.write_bytes(b"scan-only placeholder\n")


def _names(paths: Any) -> list[str]:
    return [Path(str(item)).name for item in paths or []]


def _escape_markdown(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


@contextlib.contextmanager
def _suppress_application_info_logs():
    """Keep report stdout machine-readable while ApplicationService is constructed."""
    logger_level = xbrainlab_logger.level
    handler_levels = [handler.level for handler in xbrainlab_logger.handlers]
    xbrainlab_logger.setLevel(logging.WARNING)
    for handler in xbrainlab_logger.handlers:
        handler.setLevel(logging.WARNING)
    try:
        yield
    finally:
        xbrainlab_logger.setLevel(logger_level)
        for handler, level in zip(
            xbrainlab_logger.handlers,
            handler_levels,
            strict=False,
        ):
            handler.setLevel(level)


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Output format",
    )
    parser.add_argument(
        "--write-artifacts",
        action="store_true",
        help="Write the JSON and Markdown matrix artifacts.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ARTIFACT_DIR,
        help="Artifact output directory when --write-artifacts is set.",
    )
    args = parser.parse_args()

    snapshot = build_format_capability_snapshot()
    if args.write_artifacts:
        json_path, markdown_path = write_artifacts(snapshot, args.output_dir)
        print(f"Wrote {json_path}")
        print(f"Wrote {markdown_path}")
        return 0
    if args.format == "json":
        print(json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print(render_markdown(snapshot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
