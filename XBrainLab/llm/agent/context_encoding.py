"""Bounded encoding for model-visible data that must not become policy."""

from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from XBrainLab.llm.tools.result_contract import redact_public_text

UNTRUSTED_CONTEXT_SCHEMA = "xbrainlab.untrusted_context.v1"
UNTRUSTED_CONTEXT_TRUST = "untrusted"
MAX_UNTRUSTED_CONTEXT_CHARS = 8_192
MAX_UNTRUSTED_CONTEXT_ITEMS = 8
MAX_UNTRUSTED_STRING_CHARS = 1_024

_MAX_COLLECTION_ITEMS = 24
_MAX_MAPPING_ITEMS = 32
_MAX_NESTING_DEPTH = 6
_SOURCE_LABEL_CHARS = 64
_TRUNCATION_MARKER = "...[truncated]"
_REDACTED_ROLE_MARKER = "[REDACTED_ROLE_MARKER]"
_REDACTED_PATH_MARKER = "[REDACTED_PATH]"
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|authorization|password|"
    r"private[_-]?key|secret|token)"
)
_ROLE_DELIMITER_PATTERN = re.compile(
    r"""(?ix)
    (?:
        <\|[^<>\r\n]{1,64}\|>
        |
        </?\s*(?:system|assistant|user|tool)(?:\s[^>]*)?>
        |
        <<\s*/?\s*SYS\s*>>
        |
        \[\s*/?\s*(?:INST|SYSTEM|ASSISTANT|USER|TOOL)\s*\]
        |
        ["']?role["']?\s*(?::|=)\s*["']?
        (?:system|assistant|user|tool)["']?
        |
        (?<![\w])(?:SYSTEM|ASSISTANT|USER|TOOL)\s*:
    )
    """
)
_PRIVATE_PATH_PATTERNS = (
    re.compile(
        r"""(?P<quote>["'`])"""
        r"""(?:[A-Za-z]:[\\/]|\\\\|//|/|\$HOME[\\/]|%USERPROFILE%[\\/])"""
        r"""[^"'`\r\n]*"""
        r"""(?P=quote)""",
        re.IGNORECASE,
    ),
    re.compile(r"(?i)(?<![\w])file://(?:localhost)?/[^\s,;)\]}]+"),
    re.compile(r"(?i)(?:\$HOME|%USERPROFILE%)[\\/][^\s,;:)\]}]+"),
    re.compile(r"(?<![\w:])(?:\\\\|//)[^\\/\s,;]+[\\/][^\s,;)\]}]+"),
    re.compile(r"(?<![\w])(?:[A-Za-z]:[\\/])[^\s,;)\]}]+"),
    re.compile(r"(?<![\w:/])/(?!/)[^\s,;:)\]}]+"),
)


@dataclass(frozen=True, slots=True)
class UntrustedContextSource:
    """Non-authoritative provenance attached to one context item."""

    kind: str
    id: str | None = None
    category: str | None = None

    def to_payload(self) -> dict[str, str]:
        """Return a bounded source label without accepting control syntax."""
        payload = {
            "kind": sanitize_untrusted_text(
                self.kind,
                max_chars=_SOURCE_LABEL_CHARS,
            )
            or "unknown",
        }
        if self.id is not None:
            payload["id"] = (
                sanitize_untrusted_text(
                    self.id,
                    max_chars=_SOURCE_LABEL_CHARS,
                )
                or "unknown"
            )
        if self.category is not None:
            payload["category"] = (
                sanitize_untrusted_text(
                    self.category,
                    max_chars=_SOURCE_LABEL_CHARS,
                )
                or "uncategorized"
            )
        return payload


@dataclass(frozen=True, slots=True)
class UntrustedContextItem:
    """Typed data and provenance for one model-visible context record."""

    item_type: str
    source: UntrustedContextSource
    data: Any


def sanitize_untrusted_text(value: object, *, max_chars: int) -> str:
    """Redact paths, neutralize role syntax, remove controls, and bound text."""
    text = str(value)
    for pattern in _PRIVATE_PATH_PATTERNS:
        text = pattern.sub(_REDACTED_PATH_MARKER, text)
    text = redact_public_text(text)
    text = "".join(
        " " if unicodedata.category(character).startswith("C") else character
        for character in text
    )
    text = _ROLE_DELIMITER_PATTERN.sub(_REDACTED_ROLE_MARKER, text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    if max_chars <= len(_TRUNCATION_MARKER):
        return _TRUNCATION_MARKER[:max_chars]
    prefix_chars = max_chars - len(_TRUNCATION_MARKER)
    return text[:prefix_chars].rstrip() + _TRUNCATION_MARKER


def encode_untrusted_context(
    items: Sequence[UntrustedContextItem],
    *,
    max_chars: int = MAX_UNTRUSTED_CONTEXT_CHARS,
    max_items: int = MAX_UNTRUSTED_CONTEXT_ITEMS,
    max_string_chars: int = MAX_UNTRUSTED_STRING_CHARS,
) -> str:
    """Encode context as valid JSON while enforcing item and total bounds."""
    bounded_max_chars = max(int(max_chars), 256)
    bounded_max_items = max(int(max_items), 0)
    bounded_string_chars = max(int(max_string_chars), len(_TRUNCATION_MARKER))
    selected = list(items[:bounded_max_items])
    was_truncated = len(items) > bounded_max_items
    encoded_items: list[dict[str, Any]] = []

    for item in selected:
        fitted: dict[str, Any] | None = None
        item_truncated = False
        string_limit = bounded_string_chars
        while string_limit >= len(_TRUNCATION_MARKER):
            candidate, candidate_truncated = _item_payload(
                item,
                max_string_chars=string_limit,
            )
            envelope = _envelope_payload(
                encoded_items=[*encoded_items, candidate],
                max_chars=bounded_max_chars,
                max_items=bounded_max_items,
                max_string_chars=bounded_string_chars,
                truncated=(
                    was_truncated
                    or item_truncated
                    or candidate_truncated
                    or string_limit < bounded_string_chars
                ),
            )
            if len(_json_dumps(envelope)) <= bounded_max_chars:
                fitted = candidate
                item_truncated = (
                    item_truncated
                    or candidate_truncated
                    or string_limit < bounded_string_chars
                )
                break
            next_limit = string_limit // 2
            if next_limit == string_limit:
                break
            string_limit = next_limit

        if fitted is None:
            was_truncated = True
            continue
        encoded_items.append(fitted)
        was_truncated = was_truncated or item_truncated

    envelope = _envelope_payload(
        encoded_items=encoded_items,
        max_chars=bounded_max_chars,
        max_items=bounded_max_items,
        max_string_chars=bounded_string_chars,
        truncated=was_truncated,
    )
    encoded = _json_dumps(envelope)
    if len(encoded) <= bounded_max_chars:
        return encoded

    minimal = _envelope_payload(
        encoded_items=[],
        max_chars=bounded_max_chars,
        max_items=bounded_max_items,
        max_string_chars=bounded_string_chars,
        truncated=True,
    )
    return _json_dumps(minimal)


def decode_untrusted_context(value: str) -> tuple[UntrustedContextItem, ...] | None:
    """Decode only the typed internal envelope used by the RAG boundary."""
    if not isinstance(value, str) or len(value) > MAX_UNTRUSTED_CONTEXT_CHARS:
        return None
    try:
        payload = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != UNTRUSTED_CONTEXT_SCHEMA
        or payload.get("trust") != UNTRUSTED_CONTEXT_TRUST
        or not isinstance(payload.get("items"), list)
    ):
        return None

    decoded: list[UntrustedContextItem] = []
    for raw_item in payload["items"][:MAX_UNTRUSTED_CONTEXT_ITEMS]:
        if not isinstance(raw_item, dict):
            continue
        item_type = raw_item.get("type")
        source = raw_item.get("source")
        if (
            not isinstance(item_type, str)
            or not isinstance(source, dict)
            or not isinstance(source.get("kind"), str)
            or "data" not in raw_item
        ):
            continue
        decoded.append(
            UntrustedContextItem(
                item_type=item_type,
                source=UntrustedContextSource(
                    kind=source["kind"],
                    id=source.get("id") if isinstance(source.get("id"), str) else None,
                    category=(
                        source.get("category")
                        if isinstance(source.get("category"), str)
                        else None
                    ),
                ),
                data=raw_item["data"],
            )
        )
    return tuple(decoded)


def _item_payload(
    item: UntrustedContextItem,
    *,
    max_string_chars: int,
) -> tuple[dict[str, Any], bool]:
    safe_data, truncated = _sanitize_value(
        item.data,
        max_string_chars=max_string_chars,
        depth=0,
    )
    item_type = sanitize_untrusted_text(
        item.item_type,
        max_chars=_SOURCE_LABEL_CHARS,
    )
    return (
        {
            "type": item_type or "context_data",
            "source": item.source.to_payload(),
            "data": safe_data,
        },
        truncated,
    )


def _sanitize_value(
    value: Any,
    *,
    max_string_chars: int,
    depth: int,
    field_name: str | None = None,
) -> tuple[Any, bool]:
    if depth > _MAX_NESTING_DEPTH:
        return _TRUNCATION_MARKER, True
    if field_name and _SENSITIVE_KEY_PATTERN.fullmatch(field_name):
        return "[REDACTED_SECRET]", False
    if value is None or type(value) in {bool, int}:
        return value, False
    if type(value) is float:
        return (value, False) if math.isfinite(value) else ("[non-finite]", False)
    if isinstance(value, str):
        safe = sanitize_untrusted_text(value, max_chars=max_string_chars)
        return safe, safe.endswith(_TRUNCATION_MARKER)
    if isinstance(value, os.PathLike):
        return _REDACTED_PATH_MARKER, False
    if isinstance(value, Enum):
        return _sanitize_value(
            value.value,
            max_string_chars=max_string_chars,
            depth=depth,
            field_name=field_name,
        )
    if isinstance(value, Mapping):
        items = list(value.items())
        truncated = len(items) > _MAX_MAPPING_ITEMS
        safe_mapping: dict[str, Any] = {}
        for raw_key, raw_item in items[:_MAX_MAPPING_ITEMS]:
            key = sanitize_untrusted_text(raw_key, max_chars=_SOURCE_LABEL_CHARS)
            if not key:
                key = "field"
            safe_item, item_truncated = _sanitize_value(
                raw_item,
                max_string_chars=max_string_chars,
                depth=depth + 1,
                field_name=key,
            )
            safe_mapping[key] = safe_item
            truncated = truncated or item_truncated
        return safe_mapping, truncated
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        items = list(value)
        truncated = len(items) > _MAX_COLLECTION_ITEMS
        safe_items: list[Any] = []
        for item in items[:_MAX_COLLECTION_ITEMS]:
            safe_item, item_truncated = _sanitize_value(
                item,
                max_string_chars=max_string_chars,
                depth=depth + 1,
            )
            safe_items.append(safe_item)
            truncated = truncated or item_truncated
        return safe_items, truncated
    if isinstance(value, (set, frozenset)):
        return _sanitize_value(
            sorted(value, key=str),
            max_string_chars=max_string_chars,
            depth=depth + 1,
        )
    safe = sanitize_untrusted_text(value, max_chars=max_string_chars)
    return safe, safe.endswith(_TRUNCATION_MARKER)


def _envelope_payload(
    *,
    encoded_items: list[dict[str, Any]],
    max_chars: int,
    max_items: int,
    max_string_chars: int,
    truncated: bool,
) -> dict[str, Any]:
    return {
        "schema": UNTRUSTED_CONTEXT_SCHEMA,
        "trust": UNTRUSTED_CONTEXT_TRUST,
        "bounds": {
            "max_chars": max_chars,
            "max_items": max_items,
            "max_string_chars": max_string_chars,
        },
        "items": encoded_items,
        "truncated": truncated,
    }


def _json_dumps(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
