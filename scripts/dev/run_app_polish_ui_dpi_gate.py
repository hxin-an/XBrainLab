#!/usr/bin/env python3
"""Capture the canonical app-polish matrix at Windows 100/125/150% scale."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.dev.app_polish_capture_contract import (
    FILTERING_SURFACES,
    load_app_polish_evidence,
    validate_app_polish_evidence,
)
from scripts.dev.app_polish_capture_contract import (
    MANIFEST_NAME as APP_POLISH_MANIFEST,
)
from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_source_identity,
)

ROOT = Path(__file__).resolve().parents[2]
CAPTURE_SCRIPT = ROOT / "scripts" / "dev" / "capture_ui_polish_surfaces.py"
DEFAULT_OUTPUT_DIR = ROOT / "build" / "dev-artifacts" / "app-polish-dpi"
MANIFEST_NAME = "dpi-gate.json"
SCHEMA_VERSION = 1
ARTIFACT_TYPE = "xbrainlab.app_polish_windows_dpi"
REQUIRED_SCALE_FACTORS = (1.0, 1.25, 1.5)
DPI_APP_POLISH_SURFACES = (
    "model-selection-dialog.png",
    "training-setting-dialog.png",
    "preprocess-rereference-dialog.png",
    *FILTERING_SURFACES,
    "preprocess-epoching-internal-events-dialog.png",
    "preprocess-epoching-bids-interval-duration-dialog.png",
    "data-splitting-dialog.png",
    "data-splitting-dialog-narrow.png",
    "data-splitting-preview-dialog.png",
    "saliency-setting-dialog.png",
    "saliency-setting-single-method.png",
    "saliency-setting-empty-state.png",
    "set-montage-dialog.png",
    "electrode-layout-bids-summary.png",
    "electrode-layout-bids-picker.png",
    "evaluation-controls-panel.png",
    "evaluation-metrics-table.png",
    "training-history-few-rows.png",
    "training-history-many-rows.png",
)
SCALE_TOLERANCE = 0.03


def _scale_label(scale: float) -> str:
    return f"{round(scale * 100):03d}"


def build_dpi_gate_manifest(
    *,
    captures: Sequence[Mapping[str, object]],
    source_identity: Mapping[str, object],
) -> dict[str, object]:
    """Build a bounded aggregate over exact-source per-scale evidence."""
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source_identity": dict(source_identity),
        "required_scale_factors": list(REQUIRED_SCALE_FACTORS),
        "required_surfaces": list(DPI_APP_POLISH_SURFACES),
        "captures": [dict(capture) for capture in captures],
        "claim_boundary": (
            "Automated Windows-runtime Qt scale evidence; not interactive human "
            "Windows DPI or multi-monitor acceptance."
        ),
    }


def validate_dpi_gate_manifest(
    payload: Mapping[str, object],
    *,
    expected_source_digest: str,
) -> tuple[bool, str]:
    """Reject missing scales, non-Windows runs, stale source, or DPR mismatch."""
    if payload.get("schema_version") != SCHEMA_VERSION:
        return False, "Windows DPI schema version is missing or unsupported."
    if payload.get("artifact_type") != ARTIFACT_TYPE:
        return False, "Artifact is not Windows DPI evidence."
    source_identity = payload.get("source_identity")
    if not isinstance(source_identity, Mapping):
        return False, "Windows DPI source identity is missing."
    if source_identity.get("source_digest") != expected_source_digest:
        return False, "Windows DPI evidence is stale for the current source."
    if payload.get("required_scale_factors") != list(REQUIRED_SCALE_FACTORS):
        return False, "Windows DPI required scale inventory is inconsistent."
    if payload.get("required_surfaces") != list(DPI_APP_POLISH_SURFACES):
        return False, "Windows DPI required surface inventory is inconsistent."
    captures = payload.get("captures")
    if not isinstance(captures, list):
        return False, "Windows DPI capture inventory is missing."
    observed_scales: list[float] = []
    for value in captures:
        if not isinstance(value, Mapping):
            return False, "Windows DPI capture entry is invalid."
        try:
            requested = float(value.get("requested_scale_factor", 0.0))
            observed = float(value.get("observed_device_pixel_ratio", 0.0))
        except (TypeError, ValueError):
            return False, "Windows DPI scale observation is invalid."
        observed_scales.append(requested)
        if value.get("platform_system") != "Windows":
            return False, "Windows DPI evidence was not captured on Windows."
        if str(value.get("qt_platform") or "").lower() != "windows":
            return False, "Windows DPI evidence did not use the native Qt platform."
        if value.get("evidence_valid") is not True:
            return (
                False,
                f"Windows DPI app-polish evidence failed at scale {requested:g}.",
            )
        if value.get("selected_surfaces") != list(DPI_APP_POLISH_SURFACES):
            return (
                False,
                f"Windows DPI surface matrix is incomplete at scale {requested:g}.",
            )
        expected_path = f"scale-{_scale_label(requested)}/{APP_POLISH_MANIFEST}"
        if value.get("evidence_path") != expected_path:
            return (
                False,
                f"Windows DPI evidence path is invalid at scale {requested:g}.",
            )
        if abs(observed - requested) > SCALE_TOLERANCE:
            return False, (
                f"Windows DPI observed DPR {observed:g} does not match requested "
                f"scale {requested:g}."
            )
    if observed_scales != list(REQUIRED_SCALE_FACTORS):
        return False, "Windows DPI scale matrix must be exactly 1.0, 1.25, and 1.5."
    boundary = str(payload.get("claim_boundary") or "")
    if "not interactive human Windows DPI" not in boundary:
        return False, "Windows DPI claim boundary is missing."
    return True, "Windows 100/125/150% app-polish evidence is complete."


def _write_manifest(output_dir: Path, payload: Mapping[str, object]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / MANIFEST_NAME
    temporary = output_dir / f".{MANIFEST_NAME}.tmp"
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination


def _capture_scale(
    *,
    scale: float,
    output_dir: Path,
    source_identity: Mapping[str, Any],
    timeout_seconds: float,
) -> dict[str, object]:
    scale_dir = output_dir / f"scale-{_scale_label(scale)}"
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "windows"
    environment["QT_SCALE_FACTOR"] = f"{scale:g}"
    environment["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    environment.pop("QT_AUTO_SCREEN_SCALE_FACTOR", None)
    command = [
        sys.executable,
        str(CAPTURE_SCRIPT),
        "--output-dir",
        str(scale_dir),
    ]
    for filename in DPI_APP_POLISH_SURFACES:
        command.extend(("--only", filename))
    completed = subprocess.run(  # noqa: S603 - fixed repo-owned interpreter/script
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-1200:]
        raise RuntimeError(
            f"App-polish capture failed at {scale:g}x with exit "
            f"{completed.returncode}: {detail}"
        )
    evidence = load_app_polish_evidence(scale_dir)
    valid, reason = validate_app_polish_evidence(
        evidence,
        output_dir=scale_dir,
        refresh_source_identity=False,
        current_source_identity=source_identity,
        require_complete=False,
    )
    environment_record = evidence.get("capture_environment")
    if not isinstance(environment_record, Mapping):
        environment_record = {}
    return {
        "requested_scale_factor": float(
            environment_record.get("requested_scale_factor", 0.0)
        ),
        "observed_device_pixel_ratio": float(
            environment_record.get("observed_device_pixel_ratio", 0.0)
        ),
        "platform_system": str(environment_record.get("platform_system") or ""),
        "qt_platform": str(environment_record.get("qt_platform") or ""),
        "evidence_path": (f"scale-{_scale_label(scale)}/{APP_POLISH_MANIFEST}"),
        "evidence_valid": valid,
        "selected_surfaces": list(DPI_APP_POLISH_SURFACES),
        "validation_reason": reason,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--scale",
        action="append",
        type=float,
        help="Required scale factor; repeat for the complete matrix.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    args = parser.parse_args(argv)
    scales = tuple(args.scale or REQUIRED_SCALE_FACTORS)
    if scales != REQUIRED_SCALE_FACTORS:
        parser.error("--scale must be exactly 1.0, 1.25, 1.5 in that order")
    if platform.system() != "Windows":
        print("Windows DPI evidence must run on Windows.", file=sys.stderr)
        return 2
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / MANIFEST_NAME).unlink(missing_ok=True)
    source_at_start = collect_source_identity(ROOT, refresh=True)
    captures = [
        _capture_scale(
            scale=scale,
            output_dir=output_dir,
            source_identity=source_at_start,
            timeout_seconds=args.timeout_seconds,
        )
        for scale in scales
    ]
    source_at_end = collect_source_identity(ROOT, refresh=True)
    if source_at_start.get("source_digest") != source_at_end.get("source_digest"):
        print("Product source changed during Windows DPI capture.", file=sys.stderr)
        return 3
    payload = build_dpi_gate_manifest(
        captures=captures,
        source_identity=source_at_end,
    )
    _write_manifest(output_dir, payload)
    ok, reason = validate_dpi_gate_manifest(
        payload,
        expected_source_digest=str(source_at_end.get("source_digest") or ""),
    )
    print(reason, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
