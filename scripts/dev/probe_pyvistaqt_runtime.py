#!/usr/bin/env python3
"""Probe whether the current desktop can create an interactive PyVistaQt plotter."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "ui" / "visualization-render"
JSON_ARTIFACT = "pyvistaqt-runtime-probe.json"
MD_ARTIFACT = "pyvistaqt-runtime-probe.md"
SCREENSHOT_NAME = "pyvistaqt-runtime-probe.png"

PROBE_CODE = r"""
from pathlib import Path
from PyQt6.QtWidgets import QApplication
import pyvista as pv
import pyvistaqt
import sys

image_path = Path(sys.argv[1])
app = QApplication([])
plotter = pyvistaqt.QtInteractor()
plotter.add_mesh(pv.Sphere(radius=0.5), color="white")
plotter.show()
for _ in range(20):
    app.processEvents()
try:
    plotter.screenshot(str(image_path))
except Exception as exc:
    print(f"screenshot_error={exc}")
print(f"plotter_created={plotter is not None}")
print(f"image_exists={image_path.exists()}")
plotter.close()
app.quit()
"""


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for runtime probe artifacts.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=60,
        help="Timeout for the child PyVistaQt probe.",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = args.output_dir / SCREENSHOT_NAME
    if screenshot_path.exists():
        screenshot_path.unlink()
    payload = run_probe(screenshot_path, args.timeout_seconds)
    write_artifacts(args.output_dir, payload)
    print(f"Wrote {args.output_dir / JSON_ARTIFACT}")
    print(f"Wrote {args.output_dir / MD_ARTIFACT}")
    return 0


def run_probe(screenshot_path: Path, timeout_seconds: int) -> dict[str, Any]:
    """Run the PyVistaQt probe in a child process and summarize the result."""
    env = dict(os.environ)
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-c", PROBE_CODE, str(screenshot_path)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        env=env,
    )
    return summarize_probe_result(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        image_exists=screenshot_path.exists(),
        timeout_seconds=timeout_seconds,
        environment=_runtime_environment(env),
    )


def summarize_probe_result(
    *,
    returncode: int,
    stdout: str,
    stderr: str,
    image_exists: bool,
    timeout_seconds: int,
    environment: dict[str, str],
) -> dict[str, Any]:
    """Build a stable payload from one child-process probe result."""
    plotter_created = "plotter_created=True" in stdout
    stdout_image_exists = "image_exists=True" in stdout
    bad_window_error = "BadWindow" in stderr
    passed = returncode == 0 and plotter_created and image_exists
    status = "passed" if passed else "blocked"
    return {
        "status": status,
        "claim_boundary": (
            "Interactive PyVistaQt runtime probe only; not a full XBrainLab 3D "
            "saliency render or human desktop click-through."
        ),
        "timeout_seconds": int(timeout_seconds),
        "environment": dict(environment),
        "checks": {
            "returncode_zero": returncode == 0,
            "plotter_created_stdout": plotter_created,
            "stdout_image_exists": stdout_image_exists,
            "screenshot_exists": image_exists,
            "bad_window_error": bad_window_error,
        },
        "returncode": int(returncode),
        "stdout": stdout,
        "stderr": stderr,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    """Render a human-readable runtime probe summary."""
    lines = [
        "# PyVistaQt Runtime Probe",
        "",
        f"- status: `{payload['status']}`",
        f"- claim boundary: {payload['claim_boundary']}",
        f"- timeout seconds: `{payload['timeout_seconds']}`",
        "",
        "## Environment",
        "",
    ]
    for key, value in payload["environment"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Checks", ""])
    for key, value in payload["checks"].items():
        lines.append(f"- `{key}`: `{value}`")
    stderr = str(payload.get("stderr") or "").strip()
    stdout = str(payload.get("stdout") or "").strip()
    lines.extend(
        [
            "",
            "## Output",
            "",
            "### stdout",
            "",
            "```text",
            stdout or "(empty)",
            "```",
            "",
            "### stderr",
            "",
            "```text",
            stderr or "(empty)",
            "```",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def write_artifacts(output_dir: Path, payload: dict[str, Any]) -> None:
    """Write JSON and Markdown artifacts."""
    (output_dir / JSON_ARTIFACT).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / MD_ARTIFACT).write_text(
        render_markdown(payload),
        encoding="utf-8",
    )


def _runtime_environment(env: dict[str, str]) -> dict[str, str]:
    keys = (
        "DISPLAY",
        "WAYLAND_DISPLAY",
        "QT_QPA_PLATFORM",
        "PYVISTA_OFF_SCREEN",
    )
    return {key: env.get(key, "") for key in keys}


if __name__ == "__main__":
    raise SystemExit(main())
