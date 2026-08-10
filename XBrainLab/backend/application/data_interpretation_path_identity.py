"""Path identity resolution shared by Data Interpretation review boundaries."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Literal

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


@dataclass(frozen=True, slots=True)
class CanonicalPathIdentityScope:
    """Canonical values retained only for one verified admission scope."""

    values_by_lexical_path: dict[str, str]

    @classmethod
    def from_admitted_paths(
        cls,
        paths: Iterable[Any],
    ) -> CanonicalPathIdentityScope:
        """Retain paths already canonicalized by discovery or admission."""
        values: dict[str, str] = {}
        for value in paths:
            text = str(value).strip()
            if not text:
                continue
            canonical = os.path.normpath(
                os.path.abspath(os.path.expanduser(text)),
            )
            values[_lexical_path_identity(canonical)] = canonical
        return cls(values_by_lexical_path=values)

    def contains(self, value: Any) -> bool:
        return _lexical_path_identity(value) in self.values_by_lexical_path

    def value(self, value: Any) -> str:
        lexical = _lexical_path_identity(value)
        return self.values_by_lexical_path.get(lexical) or resolved_path_value(value)

    def identity(self, value: Any) -> str:
        return os.path.normcase(self.value(value))


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


def _lexical_path_identity(value: Any) -> str:
    return os.path.normcase(
        os.path.normpath(
            os.path.abspath(os.path.expanduser(str(value))),
        )
    )


def resolved_path_value(value: Any) -> str:
    """Resolve a native path while retaining its spelling for product state."""
    return str(Path(str(value)).expanduser().resolve(strict=False))


def resolved_path_identity(value: Any) -> str:
    """Return a native filesystem comparison key for a resolved path value."""
    return os.path.normcase(resolved_path_value(value))


def deduplicate_resolved_paths(values: Iterable[Any]) -> list[str]:
    """Deduplicate native paths by identity while preserving the first spelling."""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        path = resolved_path_value(value)
        identity = resolved_path_identity(path)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(path)
    return result


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
