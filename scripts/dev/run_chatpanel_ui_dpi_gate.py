#!/usr/bin/env python3
"""Run the ChatPanel visual gate in isolated Qt scale-factor subprocesses."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.dev.app_polish_capture_contract import (
    build_source_bound_capture_session,
    validate_source_bound_capture_session,
    validate_source_bound_screenshot,
)
from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_source_identity,
    inspect_screenshot_artifact,
    validate_source_identity,
)

ROOT = Path(__file__).resolve().parents[2]
CAPTURE_SCRIPT = ROOT / "scripts/dev/capture_chatpanel_ui_ux_walkthrough.py"
GENERATOR = "scripts/dev/run_chatpanel_ui_dpi_gate.py"
MANIFEST_NAME = "dpi-gate.json"
REQUIRED_QT_SCALE_FACTORS = (1.0, 1.25, 1.5)
FULL_WINDOW_DOCK_SCREENSHOTS = (
    "first-paint-320-real-dock.png",
    "main-window-dock-420-action-visible.png",
)
NARROW_CROP_SCREENSHOTS = (
    "responsive-320-idle.png",
    "narrow-message-content-boundaries.png",
    "narrow-setting-change-confirmation-max-content.png",
)
DPI_CONTENT_SCREENSHOTS = (
    "dpi-320-message-error-confirmation.png",
    "dpi-420-message-error-confirmation.png",
    "dpi-760-message-error-confirmation.png",
)
DPI_CONTENT_WIDTHS = (320, 420, 760)
SELECTED_SCREENSHOTS = (
    *FULL_WINDOW_DOCK_SCREENSHOTS,
    *NARROW_CROP_SCREENSHOTS,
    *DPI_CONTENT_SCREENSHOTS,
)
CLAIMS = (
    "The configured Linux Qt subprocess observed each required 100/125/150 percent scale.",
    "Each scale includes full-window Assistant dock context, narrow ChatPanel evidence, "
    "and real widget captures containing messages, an error, and a confirmation card.",
)
LIMITATIONS = (
    "Linux Qt offscreen evidence does not replace Windows native DPI or multi-monitor acceptance.",
    "This gate does not establish compositor, remote-desktop, or long-session behavior.",
)
CLAIM_BOUNDARY = " ".join(LIMITATIONS)


DEFAULT_OUTPUT_DIR = ROOT / "build" / "dev-artifacts" / "chatpanel-dpi"


def _scale_label(scale: float) -> str:
    return f"{round(scale * 100):03d}"


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> Sequence[object]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return ()


def _positive_dimensions(value: object) -> bool:
    return bool(
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(item, int) and item > 0 for item in value)
    )


def _physical_dimension(logical_size: int, device_pixel_ratio: float) -> int:
    return max(int(logical_size * device_pixel_ratio + 0.5), 1)


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _surface_record(payload: Mapping[str, Any], filename: str) -> Mapping[str, Any]:
    if filename == "first-paint-320-real-dock.png":
        first_paint = _mapping(payload.get("first_paint_320_contract"))
        record = _mapping(first_paint.get("real_dock"))
        return record if record.get("file") == filename else {}
    for value in _sequence(payload.get("screens")):
        record = _mapping(value)
        if record.get("file") == filename:
            return record
    return {}


def _surface_evidence(
    payload: Mapping[str, Any],
    filenames: Sequence[str],
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for filename in filenames:
        record = _surface_record(payload, filename)
        evidence.append(
            {
                "source_file": filename,
                "record_name": str(record.get("name") or record.get("surface") or ""),
                "logical_size": list(record.get("logical_size") or []),
                "pixel_size": list(record.get("pixel_size") or []),
                "capture_method": record.get("capture_method"),
                "capture_device_pixel_ratio": record.get("capture_device_pixel_ratio"),
                "image_sha256": record.get("image_sha256"),
                "message_kinds": list(record.get("message_kinds") or []),
                "visible_messages": list(record.get("visible_messages") or []),
                "confirmation": dict(_mapping(record.get("confirmation"))),
                "render_content": dict(_mapping(record.get("render_content"))),
            }
        )
    return evidence


def _validate_full_window_record(filename: str, record: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    if not record:
        return [f"full-window dock evidence is missing: {filename}"]
    if not _positive_dimensions(record.get("pixel_size")):
        failures.append(f"full-window dock pixel size is missing: {filename}")
    if filename == "first-paint-320-real-dock.png":
        if (
            record.get("surface") != "real_dock"
            or record.get("real_main_window") is not True
            or record.get("real_qdockwidget") is not True
            or record.get("dock_visible") is not True
            or record.get("dock_floating") is not False
            or record.get("passed") is not True
        ):
            failures.append(f"full-window first-paint contract failed: {filename}")
        return failures

    checks = _mapping(record.get("checks"))
    required_checks = (
        "real_main_window_visible",
        "real_qdockwidget_visible",
        "dock_is_not_floating",
        "render_content_ready",
    )
    if not _positive_dimensions(record.get("logical_size")):
        failures.append(f"full-window dock logical size is missing: {filename}")
    if any(checks.get(name) is not True for name in required_checks):
        failures.append(f"full-window dock contract failed: {filename}")
    if list(record.get("failures") or []):
        failures.append(f"full-window dock record has failures: {filename}")
    return failures


def _validate_narrow_record(filename: str, record: Mapping[str, Any]) -> list[str]:
    if not record:
        return [f"narrow crop evidence is missing: {filename}"]
    failures: list[str] = []
    logical_size = record.get("logical_size")
    valid_narrow_viewport = bool(
        _positive_dimensions(logical_size)
        and isinstance(logical_size, list)
        and logical_size[0] == 320
    )
    if not valid_narrow_viewport:
        failures.append(f"narrow crop logical viewport is invalid: {filename}")
    if not _positive_dimensions(record.get("pixel_size")):
        failures.append(f"narrow crop pixel size is missing: {filename}")
    if list(record.get("failures") or []):
        failures.append(f"narrow crop record has failures: {filename}")
    return failures


def _validate_dpi_content_record(
    *,
    filename: str,
    width: int,
    record: Mapping[str, Any],
    observed_dpr: float,
) -> list[str]:
    if not record:
        return [f"{width}px DPI content evidence is missing: {filename}"]
    failures: list[str] = []
    logical_size = record.get("logical_size")
    if (
        not _positive_dimensions(logical_size)
        or not isinstance(logical_size, list)
        or logical_size[0] != width
    ):
        failures.append(f"{filename}: logical width is not {width}px")
        return failures
    expected_pixel_size = [
        _physical_dimension(int(value), observed_dpr) for value in logical_size
    ]
    if list(record.get("pixel_size") or []) != expected_pixel_size:
        failures.append(
            f"{filename}: physical capture size does not reflect observed DPR"
        )
    try:
        capture_dpr = float(record.get("capture_device_pixel_ratio", 0.0))
    except (TypeError, ValueError):
        capture_dpr = 0.0
    if abs(capture_dpr - observed_dpr) > 0.02:
        failures.append(f"{filename}: capture DPR does not match observed Qt DPR")
    if record.get("capture_method") != "widget_grab":
        failures.append(f"{filename}: capture did not use widget.grab()")
    if not _is_sha256(record.get("image_sha256")):
        failures.append(f"{filename}: image fingerprint is missing or invalid")

    kinds = {str(kind) for kind in _sequence(record.get("message_kinds"))}
    if "user" not in kinds:
        failures.append(f"{width}px DPI evidence has no user message content")
    if not kinds.intersection({"attention", "error"}):
        failures.append(f"{width}px DPI evidence has no warning/error message")
    visible_messages = _sequence(record.get("visible_messages"))
    if len(visible_messages) < 2 or any(
        not _mapping(message).get("text") for message in visible_messages
    ):
        failures.append(f"{width}px DPI evidence message content is incomplete")
    confirmation = _mapping(record.get("confirmation"))
    if (
        confirmation.get("visible") is not True
        or not str(confirmation.get("title") or "").strip()
        or not str(confirmation.get("values") or "").strip()
    ):
        failures.append(f"{width}px DPI evidence confirmation card is missing")
    regions = _mapping(_mapping(record.get("render_content")).get("regions"))
    expected_regions = {
        "message_content",
        "warning_or_error",
        "confirmation_card",
    }
    if set(regions) != expected_regions or any(
        _mapping(region).get("passed") is not True for region in regions.values()
    ):
        failures.append(
            f"{width}px DPI evidence required content regions were not painted"
        )
    return failures


def validate_scale_payload(
    payload: Mapping[str, Any],
    *,
    expected_scale: float,
) -> list[str]:
    """Validate one independently created Qt scale-factor capture."""
    failures: list[str] = []
    if payload.get("status") != "passed":
        failures.append("focused ChatPanel capture failed")
    try:
        configured = float(payload.get("configured_qt_scale_factor", 0.0))
    except (TypeError, ValueError):
        configured = 0.0
    if abs(configured - expected_scale) > 0.01:
        failures.append(f"configured QT scale factor does not match {expected_scale:g}")
    try:
        observed = float(payload.get("observed_screen_device_pixel_ratio", 0.0))
    except (TypeError, ValueError):
        observed = 0.0
    if abs(observed - expected_scale) > 0.02:
        failures.append(
            f"observed Qt device pixel ratio does not match {expected_scale:g}"
        )
    capture_source = _mapping(payload.get("capture_source"))
    if capture_source.get("stable") is not True:
        failures.append("capture source changed during the DPI subprocess")
    if not payload.get("source_fingerprint"):
        failures.append("capture source fingerprint is missing")
    for filename in FULL_WINDOW_DOCK_SCREENSHOTS:
        failures.extend(
            _validate_full_window_record(filename, _surface_record(payload, filename))
        )
    for filename in NARROW_CROP_SCREENSHOTS:
        failures.extend(
            _validate_narrow_record(filename, _surface_record(payload, filename))
        )
    for width, filename in zip(
        DPI_CONTENT_WIDTHS,
        DPI_CONTENT_SCREENSHOTS,
        strict=True,
    ):
        failures.extend(
            _validate_dpi_content_record(
                filename=filename,
                width=width,
                record=_surface_record(payload, filename),
                observed_dpr=observed,
            )
        )
    return failures


def validate_cross_scale_records(
    records: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Reject content captures whose PNG identity is unchanged across DPRs."""
    failures: list[str] = []
    for filename in DPI_CONTENT_SCREENSHOTS:
        fingerprints: list[str] = []
        for record in records:
            content = _sequence(record.get("dpi_content"))
            screen = next(
                (
                    _mapping(item)
                    for item in content
                    if _mapping(item).get("source_file") == filename
                    or _mapping(item).get("file") == filename
                ),
                {},
            )
            if _is_sha256(screen.get("image_sha256")):
                fingerprints.append(str(screen["image_sha256"]))
        if len(fingerprints) != len(records):
            failures.append(
                f"{filename}: cross-scale fingerprint evidence is incomplete"
            )
        elif len(set(fingerprints)) != len(fingerprints):
            failures.append(
                f"{filename}: PNG fingerprint did not change across observed DPR values"
            )
    return failures


def _capture_command(output_dir: Path) -> list[str]:
    prlimit = shutil.which("prlimit")
    if not prlimit:
        raise RuntimeError("prlimit is required for the native Qt DPI gate.")
    return [
        prlimit,
        "--core=0",
        "--",
        sys.executable,
        str(CAPTURE_SCRIPT),
        "--output-dir",
        str(output_dir),
    ]


def _run_scale_capture(
    *,
    scale: float,
    output_dir: Path,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_SCALE_FACTOR"] = f"{scale:g}"
    completed = subprocess.run(  # noqa: S603 - fixed local interpreter/script
        _capture_command(output_dir),
        cwd=ROOT,
        env=env,
        capture_output=True,
        check=False,
        text=True,
        timeout=180,
    )
    payload_path = output_dir / "walkthrough.json"
    payload = (
        json.loads(payload_path.read_text(encoding="utf-8"))
        if payload_path.is_file()
        else {}
    )
    return completed, payload


def _screenshot_manifest(output_dir: Path, filenames: Sequence[str]) -> dict[str, Any]:
    manifest: dict[str, Any] = {}
    for filename in filenames:
        metadata = inspect_screenshot_artifact(output_dir / filename)
        metadata["path"] = filename
        manifest[filename] = metadata
    return manifest


def run_dpi_gate(
    output_dir: Path,
    *,
    scales: Sequence[float] = REQUIRED_QT_SCALE_FACTORS,
) -> dict[str, Any]:
    """Run all required scales and atomically publish one source-bound manifest."""
    output_dir = output_dir.expanduser().resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    capture_started_at = datetime.now(UTC)
    source_identity_at_start = collect_source_identity(ROOT, refresh=True)
    records: list[dict[str, Any]] = []
    retained_filenames: list[str] = []
    selected_scales = tuple(float(scale) for scale in scales)
    with tempfile.TemporaryDirectory(
        prefix=f".{output_dir.name}-capture-",
        dir=output_dir.parent,
    ) as temporary_root:
        root = Path(temporary_root)
        publication_dir = root / "publication"
        publication_dir.mkdir()
        for scale in selected_scales:
            scale_dir = root / f"scale-{_scale_label(scale)}"
            completed, capture_payload = _run_scale_capture(
                scale=scale,
                output_dir=scale_dir,
            )
            failures = validate_scale_payload(capture_payload, expected_scale=scale)
            if completed.returncode != 0:
                failures.append(
                    f"capture subprocess exited with {completed.returncode}"
                )
            retained: list[str] = []
            for filename in SELECTED_SCREENSHOTS:
                source = scale_dir / filename
                destination_name = f"scale-{_scale_label(scale)}-{filename}"
                if not source.is_file():
                    failures.append(f"missing selected screenshot: {filename}")
                    continue
                shutil.copy2(source, publication_dir / destination_name)
                retained.append(destination_name)
                retained_filenames.append(destination_name)
            records.append(
                {
                    "scale": scale,
                    "status": "passed" if not failures else "failed",
                    "failures": failures,
                    "configured_qt_scale_factor": capture_payload.get(
                        "configured_qt_scale_factor"
                    ),
                    "observed_screen_device_pixel_ratio": capture_payload.get(
                        "observed_screen_device_pixel_ratio"
                    ),
                    "source_fingerprint": capture_payload.get("source_fingerprint", ""),
                    "full_window_dock": _surface_evidence(
                        capture_payload, FULL_WINDOW_DOCK_SCREENSHOTS
                    ),
                    "narrow_crops": _surface_evidence(
                        capture_payload, NARROW_CROP_SCREENSHOTS
                    ),
                    "dpi_content": _surface_evidence(
                        capture_payload, DPI_CONTENT_SCREENSHOTS
                    ),
                    "selected_screenshots": retained,
                    "subprocess_returncode": completed.returncode,
                }
            )

        failures = [
            f"scale {record['scale']:g}: {failure}"
            for record in records
            for failure in record["failures"]
        ]
        failures.extend(
            f"cross-scale: {failure}"
            for failure in validate_cross_scale_records(records)
        )
        if selected_scales != REQUIRED_QT_SCALE_FACTORS:
            failures.append(
                "required DPI scales must be exactly 100, 125, and 150 percent"
            )
        source_identity_at_completion = collect_source_identity(ROOT, refresh=True)
        completed_at = datetime.now(UTC)
        payload: dict[str, Any] = {
            "schema_version": 2,
            "artifact_type": "xbrainlab.chatpanel_dpi_gate",
            "generator": GENERATOR,
            "generated_at_utc": completed_at.isoformat(),
            "status": "passed" if not failures else "failed",
            "source_identity": source_identity_at_completion,
            "capture_session": build_source_bound_capture_session(
                source_identity=source_identity_at_completion,
                source_identity_at_start=source_identity_at_start,
                capture_started_at=capture_started_at,
                completed_at=completed_at,
            ),
            "capture_environment": {
                "platform": sys.platform,
                "qt_platform": "offscreen",
                "required_scales": list(REQUIRED_QT_SCALE_FACTORS),
                "selected_scales": list(selected_scales),
                "scale_variable": "QT_SCALE_FACTOR",
                "full_window_dock_surfaces": list(FULL_WINDOW_DOCK_SCREENSHOTS),
                "narrow_crop_surfaces": list(NARROW_CROP_SCREENSHOTS),
                "dpi_content_surfaces": list(DPI_CONTENT_SCREENSHOTS),
            },
            "capture_scope": {
                "complete": selected_scales == REQUIRED_QT_SCALE_FACTORS,
                "required_scales": list(REQUIRED_QT_SCALE_FACTORS),
                "selected_scales": list(selected_scales),
            },
            "claims": list(CLAIMS),
            "limitations": list(LIMITATIONS),
            "claim_boundary": CLAIM_BOUNDARY,
            "records": records,
            "screenshots": _screenshot_manifest(publication_dir, retained_filenames),
            "failures": failures,
            "replay_command": (
                "poetry run -- python scripts/dev/run_chatpanel_ui_dpi_gate.py"
            ),
        }
        manifest_ok, manifest_reason = validate_dpi_manifest(
            payload,
            output_dir=publication_dir,
        )
        if not manifest_ok and manifest_reason not in payload["failures"]:
            payload["status"] = "failed"
            payload["failures"].append(manifest_reason)
        (publication_dir / MANIFEST_NAME).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (publication_dir / "README.md").write_text(
            _render_readme(payload),
            encoding="utf-8",
        )
        _replace_artifact_directory(publication_dir, output_dir)
    return payload


def validate_dpi_manifest(
    payload: Mapping[str, Any],
    *,
    output_dir: Path,
    refresh_source_identity: bool = True,
    current_source_identity: Mapping[str, Any] | None = None,
) -> tuple[bool, str]:
    """Reject incomplete, stale, or tampered DPI evidence."""
    if payload.get("schema_version") != 2 or payload.get("generator") != GENERATOR:
        return False, "DPI manifest generator/schema binding is missing."
    source_ok, source_reason = validate_source_identity(
        payload.get("source_identity"),
        expected_repo_root=ROOT,
        refresh=refresh_source_identity,
        current_identity=current_source_identity,
        artifact_name="ChatPanel DPI gate",
    )
    if not source_ok:
        return source_ok, source_reason
    session_ok, session_reason = validate_source_bound_capture_session(
        payload.get("capture_session"),
        generated_at=payload.get("generated_at_utc"),
        source_identity=payload.get("source_identity"),
        artifact_name="ChatPanel DPI gate",
    )
    if not session_ok:
        return session_ok, session_reason

    environment = _mapping(payload.get("capture_environment"))
    scope = _mapping(payload.get("capture_scope"))
    if (
        environment.get("qt_platform") != "offscreen"
        or environment.get("required_scales") != list(REQUIRED_QT_SCALE_FACTORS)
        or environment.get("full_window_dock_surfaces")
        != list(FULL_WINDOW_DOCK_SCREENSHOTS)
        or environment.get("narrow_crop_surfaces") != list(NARROW_CROP_SCREENSHOTS)
        or environment.get("dpi_content_surfaces") != list(DPI_CONTENT_SCREENSHOTS)
        or scope.get("complete") is not True
        or scope.get("selected_scales") != list(REQUIRED_QT_SCALE_FACTORS)
    ):
        return False, "DPI environment, scale, or viewport contract is incomplete."
    if payload.get("claims") != list(CLAIMS):
        return False, "DPI claims are missing or unsupported."
    if payload.get("limitations") != list(LIMITATIONS):
        return False, "DPI limitations are missing or unsupported."

    records = list(_sequence(payload.get("records")))
    if [record.get("scale") for record in map(_mapping, records)] != list(
        REQUIRED_QT_SCALE_FACTORS
    ):
        return False, "DPI scale records are incomplete or out of order."
    for record_value in records:
        record = _mapping(record_value)
        if (
            record.get("status") != "passed"
            or len(list(_sequence(record.get("full_window_dock"))))
            != len(FULL_WINDOW_DOCK_SCREENSHOTS)
            or len(list(_sequence(record.get("narrow_crops"))))
            != len(NARROW_CROP_SCREENSHOTS)
            or len(list(_sequence(record.get("dpi_content"))))
            != len(DPI_CONTENT_SCREENSHOTS)
        ):
            return False, "DPI scale evidence roles are incomplete."

    expected_filenames = {
        f"scale-{_scale_label(scale)}-{filename}"
        for scale in REQUIRED_QT_SCALE_FACTORS
        for filename in SELECTED_SCREENSHOTS
    }
    screenshots = _mapping(payload.get("screenshots"))
    if set(screenshots) != expected_filenames:
        return False, "DPI screenshot manifest is incomplete."
    root = output_dir.expanduser().resolve()
    for filename in sorted(expected_filenames):
        ok, reason = validate_source_bound_screenshot(
            root,
            filename,
            screenshots.get(filename),
            artifact_name="ChatPanel DPI gate",
        )
        if not ok:
            return ok, reason
    return True, ""


def _replace_artifact_directory(publication_dir: Path, output_dir: Path) -> None:
    backup = output_dir.parent / f".{output_dir.name}-backup"
    if backup.exists():
        shutil.rmtree(backup)
    if output_dir.exists():
        output_dir.replace(backup)
    try:
        publication_dir.replace(output_dir)
    except Exception:
        if backup.exists() and not output_dir.exists():
            backup.replace(output_dir)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def _render_readme(payload: Mapping[str, Any]) -> str:
    lines = [
        "# ChatPanel Qt Scale Gate",
        "",
        f"- status: `{payload['status']}`",
        f"- generator: `{payload['generator']}`",
        f"- replay: `{payload['replay_command']}`",
        "",
        "| QT scale | Observed DPR | Status | Full window | Narrow | Content |",
        "| ---: | ---: | --- | ---: | ---: | ---: |",
    ]
    for value in _sequence(payload.get("records")):
        record = _mapping(value)
        lines.append(
            f"| {record['scale']:g} | "
            f"{record['observed_screen_device_pixel_ratio']} | "
            f"{record['status']} | {len(record['full_window_dock'])} | "
            f"{len(record['narrow_crops'])} | {len(record['dpi_content'])} |"
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in payload.get("limitations", []))
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for compact DPI evidence.",
    )
    args = parser.parse_args()
    payload = run_dpi_gate(args.output_dir)
    print(f"ChatPanel Qt scale gate: {payload['status']}")
    for failure in payload["failures"]:
        print(f"- {failure}", file=sys.stderr)
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
