#!/usr/bin/env python3
"""Capture Windows launcher walkthrough evidence from WSL.

The script validates the desktop command bootstrap and PowerShell launcher path
without claiming a human click-through. It exercises Windows cmd.exe,
PowerShell, wsl.exe, launcher live logging, and a bounded run.py startup smoke.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "launcher"
DESKTOP_CMD = r"C:\Users\Administrator\Desktop\XBrainLab.cmd"
POWERSHELL_LAUNCHER = (
    r"D:\workspace_v2\projects\lab\XBrainLab\scripts\launchers"
    r"\xbrainlab_wsl_launcher.ps1"
)
ACTIVE_WSL_REPO = "/mnt/d/workspace_v2/projects/lab/XBrainLab"
JSON_ARTIFACT = "windows-launcher-walkthrough.json"
MD_ARTIFACT = "windows-launcher-walkthrough.md"


@dataclass(frozen=True)
class CommandCapture:
    """Captured result from one launcher command."""

    name: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "command": self.command,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for launcher walkthrough artifacts.",
    )
    parser.add_argument(
        "--startup-timeout",
        type=int,
        default=120,
        help="Outer timeout for the PowerShell startup smoke command.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = capture_walkthrough(args.startup_timeout)
    write_artifacts(output_dir, payload)
    print(f"Wrote {output_dir / JSON_ARTIFACT}")
    print(f"Wrote {output_dir / MD_ARTIFACT}")
    return 0 if payload["status"] == "passed" else 1


def capture_walkthrough(startup_timeout: int) -> dict[str, Any]:
    """Run launcher smoke commands and return a structured artifact payload."""
    desktop = run_command(
        "desktop_cmd_smoke",
        [
            "cmd.exe",
            "/c",
            f"set XBRAINLAB_LAUNCHER_SMOKE=1&& {DESKTOP_CMD}",
        ],
        timeout=45,
    )
    wsl = run_command(
        "powershell_wsl_smoke",
        powershell_command("wsl"),
        timeout=60,
    )
    startup = run_command(
        "powershell_startup_smoke",
        powershell_command("startup"),
        timeout=startup_timeout,
    )

    checks = {
        "desktop_points_to_active_repo": ACTIVE_WSL_REPO in desktop.stdout,
        "desktop_smoke_skipped_wsl": "WSL launch skipped" in desktop.stdout,
        "wsl_stdout_mirrored": "WSL_launcher_smoke_stdout" in wsl.stdout,
        "wsl_stderr_mirrored": "WSL_launcher_smoke_stderr" in wsl.stdout,
        "startup_saw_main_window": "MainWindow initialized" in startup.stdout,
        "startup_bounded": "GUI kept running until timeout" in startup.stdout,
    }
    log_paths = {
        "wsl": windows_log_path_to_wsl(extract_log_path(wsl.stdout)),
        "startup": windows_log_path_to_wsl(extract_log_path(startup.stdout)),
    }
    checks["wsl_log_exists"] = bool(
        log_paths["wsl"] and Path(log_paths["wsl"]).exists()
    )
    checks["startup_log_exists"] = bool(
        log_paths["startup"] and Path(log_paths["startup"]).exists()
    )

    command_payloads = [desktop.to_payload(), wsl.to_payload(), startup.to_payload()]
    command_returncodes_ok = all(item["returncode"] == 0 for item in command_payloads)
    status = "passed" if command_returncodes_ok and all(checks.values()) else "failed"
    return {
        "status": status,
        "claim_boundary": (
            "Automated Windows launcher command walkthrough; not a human desktop "
            "click-through or packaging release approval."
        ),
        "desktop_cmd": DESKTOP_CMD,
        "powershell_launcher": POWERSHELL_LAUNCHER,
        "active_wsl_repo": ACTIVE_WSL_REPO,
        "checks": checks,
        "log_paths": log_paths,
        "commands": command_payloads,
    }


def powershell_command(smoke_mode: str) -> list[str]:
    """Return a PowerShell command that runs the launcher in smoke mode."""
    command = f"$env:XBRAINLAB_LAUNCHER_SMOKE='{smoke_mode}'; & '{POWERSHELL_LAUNCHER}'"
    return [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        command,
    ]


def run_command(name: str, command: list[str], timeout: int) -> CommandCapture:
    """Run a command and capture decoded output."""
    completed = subprocess.run(  # noqa: S603 - launcher commands are fixed constants.
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return CommandCapture(
        name=name,
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def extract_log_path(output: str) -> str:
    """Extract the Windows launcher log path from PowerShell output."""
    match = re.search(r"Log:\s*(C:\\[^\r\n]+launcher-\d+-\d+\.log)", output)
    return match.group(1) if match else ""


def windows_log_path_to_wsl(path: str) -> str:
    """Convert a C:\\... launcher log path to /mnt/c/... for WSL reads."""
    if not path:
        return ""
    normalized = path.replace("\\", "/")
    if len(normalized) >= 2 and normalized[1] == ":":
        drive = normalized[0].lower()
        return f"/mnt/{drive}{normalized[2:]}"
    return normalized


def render_markdown(payload: dict[str, Any]) -> str:
    """Render a compact human-readable launcher evidence summary."""
    lines = [
        "# Windows Launcher Walkthrough",
        "",
        f"- status: `{payload['status']}`",
        f"- claim boundary: {payload['claim_boundary']}",
        f"- desktop command: `{payload['desktop_cmd']}`",
        f"- PowerShell launcher: `{payload['powershell_launcher']}`",
        f"- active WSL repo: `{payload['active_wsl_repo']}`",
        "",
        "## Checks",
        "",
    ]
    for name, passed in payload["checks"].items():
        lines.append(f"- `{name}`: `{passed}`")
    lines.extend(["", "## Logs", ""])
    for name, path in payload["log_paths"].items():
        lines.append(f"- `{name}`: `{path or 'not found'}`")
    lines.extend(["", "## Command Summary", ""])
    for command in payload["commands"]:
        stdout = str(command.get("stdout", ""))
        markers = [
            marker
            for marker in (
                "WSL launch skipped",
                "WSL_launcher_smoke_stdout",
                "WSL_launcher_smoke_stderr",
                "MainWindow initialized",
                "GUI kept running until timeout",
            )
            if marker in stdout
        ]
        lines.append(
            f"- `{command['name']}`: return `{command['returncode']}`, "
            f"markers `{', '.join(markers) or 'none'}`"
        )
    return "\n".join(lines).rstrip() + "\n"


def write_artifacts(output_dir: Path, payload: dict[str, Any]) -> None:
    """Write JSON and Markdown walkthrough artifacts."""
    (output_dir / JSON_ARTIFACT).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / MD_ARTIFACT).write_text(
        render_markdown(payload),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
