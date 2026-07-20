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

ROOT = Path(__file__).resolve().parents[2]
CAPTURE_SCRIPT = ROOT / "scripts/dev/capture_chatpanel_ui_ux_walkthrough.py"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts/ui/chatpanel-dpi-current"
REQUIRED_QT_SCALE_FACTORS = (1.0, 1.25, 1.5)
SELECTED_SCREENSHOTS = (
    "first-paint-320-real-dock.png",
    "responsive-320-idle.png",
    "narrow-setting-change-confirmation-max-content.png",
)
CLAIM_BOUNDARY = (
    "This gate runs Linux Qt offscreen subprocesses with explicit QT_SCALE_FACTOR "
    "values. It validates device-pixel-ratio observation, layout, text-fit, and "
    "interaction contracts at those configured scales. It does not replace Windows "
    "native DPI, multi-monitor, compositor, or human click-through acceptance."
)


def _scale_label(scale: float) -> str:
    return f"{round(scale * 100):03d}"


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
    capture_source = payload.get("capture_source")
    if (
        not isinstance(capture_source, Mapping)
        or capture_source.get("stable") is not True
    ):
        failures.append("capture source changed during the DPI subprocess")
    if not payload.get("source_fingerprint"):
        failures.append("capture source fingerprint is missing")
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


def run_dpi_gate(
    output_dir: Path,
    *,
    scales: Sequence[float] = REQUIRED_QT_SCALE_FACTORS,
) -> dict[str, Any]:
    """Run and retain compact evidence for every required Qt scale."""
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(
        prefix=".chatpanel-dpi-",
        dir=output_dir.parent,
    ) as temporary_root:
        root = Path(temporary_root)
        for scale in scales:
            scale_dir = root / f"scale-{_scale_label(scale)}"
            completed, payload = _run_scale_capture(
                scale=scale,
                output_dir=scale_dir,
            )
            failures = validate_scale_payload(payload, expected_scale=scale)
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
                shutil.copy2(source, output_dir / destination_name)
                retained.append(destination_name)
            records.append(
                {
                    "scale": scale,
                    "status": "passed" if not failures else "failed",
                    "failures": failures,
                    "configured_qt_scale_factor": payload.get(
                        "configured_qt_scale_factor"
                    ),
                    "observed_screen_device_pixel_ratio": payload.get(
                        "observed_screen_device_pixel_ratio"
                    ),
                    "source_fingerprint": payload.get("source_fingerprint", ""),
                    "selected_screenshots": retained,
                    "subprocess_returncode": completed.returncode,
                }
            )

    failures = [
        f"scale {record['scale']:g}: {failure}"
        for record in records
        for failure in record["failures"]
    ]
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "passed" if not failures else "failed",
        "required_scales": list(scales),
        "claim_boundary": CLAIM_BOUNDARY,
        "records": records,
        "failures": failures,
        "replay_command": (
            "poetry run python scripts/dev/run_chatpanel_ui_dpi_gate.py"
        ),
    }
    (output_dir / "dpi-gate.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "README.md").write_text(
        _render_readme(payload),
        encoding="utf-8",
    )
    return payload


def _render_readme(payload: Mapping[str, Any]) -> str:
    lines = [
        "# ChatPanel Qt Scale Gate",
        "",
        f"- status: `{payload['status']}`",
        f"- replay: `{payload['replay_command']}`",
        "",
        "| QT scale | Observed DPR | Status | Screenshots |",
        "| ---: | ---: | --- | --- |",
    ]
    for record in payload["records"]:
        screenshots = ", ".join(f"`{name}`" for name in record["selected_screenshots"])
        lines.append(
            f"| {record['scale']:g} | "
            f"{record['observed_screen_device_pixel_ratio']} | "
            f"{record['status']} | {screenshots} |"
        )
    lines.extend(["", "## Claim Boundary", "", str(payload["claim_boundary"]), ""])
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
