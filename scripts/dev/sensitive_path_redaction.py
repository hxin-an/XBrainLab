"""Shared host-path redaction for persisted validation evidence."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

_PATH_SEPARATOR_PATTERN = r"[\\/]+"


def path_aliases(value: str) -> tuple[str, ...]:
    """Return exact POSIX, Windows, and JSON spellings of one path."""
    raw = str(value)
    aliases = {raw, raw.replace("\\", "/"), raw.replace("/", "\\")}
    normalized = raw.replace("\\", "/")
    mounted = re.match(r"^/mnt/([a-zA-Z])/(.*)$", normalized)
    drive_path = re.match(r"^([a-zA-Z]):/(.*)$", normalized)
    if mounted:
        drive = mounted.group(1).upper()
        remainder = mounted.group(2)
        windows_remainder = remainder.replace("/", "\\")
        aliases.add(f"{drive}:/{remainder}")
        aliases.add(f"{drive}:\\{windows_remainder}")
    elif drive_path:
        drive = drive_path.group(1).lower()
        aliases.add(f"/mnt/{drive}/{drive_path.group(2)}")
    aliases.update(json.dumps(alias)[1:-1] for alias in tuple(aliases))
    return tuple(sorted((alias for alias in aliases if alias), key=len, reverse=True))


def redact_sensitive_text(text: str, redactions: Mapping[str, str]) -> str:
    """Redact each configured path across WSL, Windows, UNC, and JSON forms."""
    redacted = text
    for path, marker in _ordered_redactions(redactions):
        for pattern in _path_patterns(path):
            redacted = re.sub(pattern, marker, redacted, flags=re.IGNORECASE)
        for alias in path_aliases(path):
            redacted = re.sub(
                re.escape(alias),
                marker,
                redacted,
                flags=re.IGNORECASE,
            )
    return redacted


def redact_sensitive_value(value: object, redactions: Mapping[str, str]) -> Any:
    """Recursively redact strings in one JSON-compatible report value."""
    if isinstance(value, str):
        return redact_sensitive_text(value, redactions)
    if isinstance(value, list):
        return [redact_sensitive_value(item, redactions) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive_value(item, redactions) for item in value]
    if isinstance(value, dict):
        return {
            redact_sensitive_text(str(key), redactions): redact_sensitive_value(
                item,
                redactions,
            )
            for key, item in value.items()
        }
    return value


def contains_sensitive_path(text: str, redactions: Mapping[str, str]) -> bool:
    """Return whether text contains any configured path spelling."""
    for path, _marker in _ordered_redactions(redactions):
        if any(
            re.search(pattern, text, flags=re.IGNORECASE)
            for pattern in _path_patterns(path)
        ):
            return True
        casefolded = text.casefold()
        if any(alias.casefold() in casefolded for alias in path_aliases(path)):
            return True
    return False


def _ordered_redactions(redactions: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            ((str(path), str(marker)) for path, marker in redactions.items() if path),
            key=lambda item: len(item[0]),
            reverse=True,
        )
    )


def _path_patterns(value: str) -> tuple[str, ...]:
    """Build separator-tolerant patterns, including UNC WSL path tails."""
    normalized = str(value).replace("\\", "/")
    mounted = re.match(r"^/mnt/([a-zA-Z])/(.*)$", normalized)
    drive_path = re.match(r"^([a-zA-Z]):/(.*)$", normalized)
    if mounted:
        drive = mounted.group(1)
        remainder = mounted.group(2)
    elif drive_path:
        drive = drive_path.group(1)
        remainder = drive_path.group(2)
    else:
        return ()
    components = tuple(part for part in remainder.split("/") if part)
    if not components:
        return ()
    escaped_tail = _PATH_SEPARATOR_PATTERN.join(map(re.escape, components))
    return (
        (
            rf"{_PATH_SEPARATOR_PATTERN}mnt{_PATH_SEPARATOR_PATTERN}"
            rf"{re.escape(drive)}{_PATH_SEPARATOR_PATTERN}{escaped_tail}"
        ),
        rf"{re.escape(drive)}:{_PATH_SEPARATOR_PATTERN}{escaped_tail}",
    )


__all__ = [
    "contains_sensitive_path",
    "path_aliases",
    "redact_sensitive_text",
    "redact_sensitive_value",
]
