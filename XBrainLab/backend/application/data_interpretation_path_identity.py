"""Path identity resolution shared by Data Interpretation review boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Literal

PathMatchStatus = Literal["exact", "unique_basename", "missing", "ambiguous"]


@dataclass(frozen=True)
class ScanPathMatch:
    """Describe how one saved or selected path maps into the current scan."""

    requested: str
    status: PathMatchStatus
    resolved: str = ""
    candidates: tuple[str, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.status in {"exact", "unique_basename"}


def path_basename(value: str) -> str:
    """Return a basename for native or Windows recipe paths."""
    text = str(value).strip()
    if not text:
        return ""
    windows_path = PureWindowsPath(text)
    if windows_path.drive or "\\" in text:
        return windows_path.name or text
    return Path(text).name or text


def normalized_path_identity(value: str) -> str:
    """Return a stable lexical identity without requiring the path to exist."""
    text = str(value).strip()
    if not text:
        return ""
    windows_path = PureWindowsPath(text)
    if windows_path.drive or "\\" in text:
        return windows_path.as_posix().casefold()
    return Path(text).expanduser().as_posix()


def resolve_scan_path(requested: str, scanned: list[str]) -> ScanPathMatch:
    """Resolve exact identity first and basename only when it is unique."""
    requested_text = str(requested).strip()
    current = list(
        dict.fromkeys(str(item).strip() for item in scanned if str(item).strip())
    )
    requested_identity = normalized_path_identity(requested_text)
    exact = [
        item for item in current if normalized_path_identity(item) == requested_identity
    ]
    if len(exact) == 1:
        return ScanPathMatch(
            requested=requested_text,
            status="exact",
            resolved=exact[0],
            candidates=(exact[0],),
        )
    if len(exact) > 1:
        return ScanPathMatch(
            requested=requested_text,
            status="ambiguous",
            candidates=tuple(exact),
        )

    requested_name = path_basename(requested_text).casefold()
    basename_matches = [
        item for item in current if path_basename(item).casefold() == requested_name
    ]
    if len(basename_matches) == 1:
        return ScanPathMatch(
            requested=requested_text,
            status="unique_basename",
            resolved=basename_matches[0],
            candidates=(basename_matches[0],),
        )
    if len(basename_matches) > 1:
        return ScanPathMatch(
            requested=requested_text,
            status="ambiguous",
            candidates=tuple(basename_matches),
        )
    return ScanPathMatch(requested=requested_text, status="missing")


def unresolved_scan_path_descriptions(
    required: list[str],
    scanned: list[str],
) -> list[str]:
    """Return actionable full-identity descriptions for unresolved paths."""
    issues: list[str] = []
    for required_path in required:
        match = resolve_scan_path(required_path, scanned)
        if match.accepted:
            continue
        if match.status == "ambiguous":
            description = (
                f"{match.requested} (ambiguous; matches: "
                + ", ".join(match.candidates)
                + ")"
            )
        else:
            description = f"{match.requested} (not found)"
        if description not in issues:
            issues.append(description)
    return issues
