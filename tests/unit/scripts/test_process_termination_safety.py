"""Source guard for repository-owned process termination commands."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_ROOTS = (ROOT / "scripts",)
SCRIPT_SUFFIXES = {".py", ".ps1", ".sh"}
OWNED_RUNNER_PATHS = (
    ROOT / "scripts" / "dev" / "handoff_evidence_recorder.py",
    ROOT / "scripts" / "dev" / "run_tests.py",
    ROOT / "scripts" / "dev" / "update_quality_dashboard.py",
    ROOT / "scripts" / "dev" / "run_startup_smoke.py",
)

_BROAD_TERMINATION_PATTERNS = {
    "WSL-wide shutdown": re.compile(r"\bwsl(?:\.exe)?\s+--shutdown\b", re.IGNORECASE),
    "system shutdown": re.compile(
        r"(?<![\w.])shutdown(?:\.exe)?\s+(?:-h|-P|now|/s)\b",
        re.IGNORECASE,
    ),
    "killall": re.compile(r"\bkillall\b", re.IGNORECASE),
    "broad pkill": re.compile(r"\bpkill\b", re.IGNORECASE),
    "image-wide taskkill": re.compile(r"\btaskkill\b[^\r\n]*\s/IM\b", re.IGNORECASE),
    "name-wide Stop-Process": re.compile(
        r"\bStop-Process\b[^\r\n]*\s-Name\b",
        re.IGNORECASE,
    ),
    "enumerated Windows process cleanup": re.compile(
        r"Get-CimInstance\s+Win32_Process[\s\S]{0,1200}?Stop-Process",
        re.IGNORECASE,
    ),
}


def _executable_scripts() -> list[Path]:
    return sorted(
        path
        for root in SCRIPT_ROOTS
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in SCRIPT_SUFFIXES
    )


def test_repository_scripts_never_use_broad_process_termination() -> None:
    """Development gates may stop only the exact process they started."""
    violations: list[str] = []
    for path in _executable_scripts():
        source = path.read_text(encoding="utf-8")
        for label, pattern in _BROAD_TERMINATION_PATTERNS.items():
            if pattern.search(source):
                violations.append(f"{path.relative_to(ROOT)}: {label}")

    assert violations == []


def test_validation_runners_use_the_shared_owned_spawn_boundary() -> None:
    for path in OWNED_RUNNER_PATHS:
        source = path.read_text(encoding="utf-8")
        assert "spawn_owned_process(" in source, path.relative_to(ROOT)
        assert "subprocess.Popen(" not in source, path.relative_to(ROOT)
