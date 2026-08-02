"""Bounded encoding for model-visible data that must not become policy."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import islice
from typing import Any

from XBrainLab.backend.utils.public_diagnostics import (
    REDACTED_PATH_MARKER,
    REDACTED_SECRET_MARKER,
    public_diagnostic_value,
)
from XBrainLab.llm.tools.result_contract import redact_public_text

UNTRUSTED_CONTEXT_SCHEMA = "xbrainlab.untrusted_context.v1"
UNTRUSTED_CONTEXT_TRUST = "untrusted"
MAX_UNTRUSTED_CONTEXT_BYTES = 8_192
# Compatibility name for existing bounded-context callers. The value is now
# interpreted as serialized UTF-8 bytes, not Python characters.
MAX_UNTRUSTED_CONTEXT_CHARS = MAX_UNTRUSTED_CONTEXT_BYTES
MIN_UNTRUSTED_CONTEXT_BYTES = 256
MAX_UNTRUSTED_CONTEXT_ITEMS = 8
MAX_UNTRUSTED_STRING_CHARS = 1_024

_MAX_COLLECTION_ITEMS = 24
_MAX_MAPPING_ITEMS = 32
_MAX_NESTING_DEPTH = 6
_MAX_PROJECTION_NODES = 128
_SOURCE_LABEL_CHARS = 64
_TRUNCATION_MARKER = "...[truncated]"
_REDACTED_ROLE_MARKER = "[REDACTED_ROLE_MARKER]"
_REDACTED_PATH_MARKER = "[REDACTED_PATH]"
_UNSUPPORTED_VALUE_MARKER = "[UNSUPPORTED_VALUE]"
_REPEATED_REFERENCE_MARKER = "[REPEATED_REFERENCE]"
_PROJECTION_BUDGET_MARKER = "[PROJECTION_BUDGET_EXCEEDED]"
_SUBJECT_REFERENCE_PREFIX = "[SUBJECT_REF:"
_STRUCTURED_FIELD_PROBE = "xbrainlab-structured-field-probe"
_HOST_AUTHORITATIVE_SOURCE_MARKERS = (
    "applicationservice",
    "authoritative",
    "capabilitypolicy",
    "conversationhistory",
    "hostpolicy",
    "latestrequest",
    "officialsource",
    "systempolicy",
    "toolresult",
    "trustedsource",
    "userrequest",
)
_HOST_AUTHORITATIVE_ITEM_TYPES = frozenset(
    {
        "applicationstate",
        "capabilityblockers",
        "capabilitystatus",
        "conversationhistory",
        "toolpublication",
        "toolrecovery",
        "workflowdecision",
    }
)
_EXTERNAL_CONTEXT_TYPE_PREFIX = "external_context:"
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
_PROTECTED_ROLE_VALUES = frozenset({"system", "assistant", "user", "tool"})
_SPACED_SLASH_SEPARATOR_PATTERN = re.compile(r"(?<=\s)/(?=\s)")
_PROSE_ARROW_BOUNDARY_PATTERN = re.compile(r"->(?=[ \t])")
_SLASH_SEPARATOR_PLACEHOLDER = "XBrainLabUntrustedSlashSeparator"
_ARROW_BOUNDARY_PLACEHOLDER = "XBrainLabUntrustedArrowBoundary"


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


@dataclass(slots=True)
class _ProjectionBudget:
    remaining_nodes: int
    seen_containers: set[int]
    truncated: bool = False

    def consume_node(self) -> bool:
        if self.remaining_nodes <= 0:
            self.truncated = True
            return False
        self.remaining_nodes -= 1
        return True

    def enter_container(self, value: object) -> bool:
        identity = id(value)
        if identity in self.seen_containers:
            self.truncated = True
            return False
        self.seen_containers.add(identity)
        return True


def sanitize_untrusted_text(
    value: object,
    *,
    max_chars: int,
    max_utf8_bytes: int | None = None,
) -> str:
    """Redact paths, neutralize role syntax, remove controls, and bound text."""
    bounded_max_chars = _exact_int(max_chars, name="max_chars", minimum=0)
    bounded_max_bytes = (
        None
        if max_utf8_bytes is None
        else _exact_int(
            max_utf8_bytes,
            name="max_utf8_bytes",
            minimum=0,
        )
    )
    if type(value) is not str:
        marker = _bounded_marker(
            _UNSUPPORTED_VALUE_MARKER,
            max_chars=bounded_max_chars,
        )
        if bounded_max_bytes is not None:
            marker, _truncated = _truncate_utf8(
                marker,
                max_bytes=bounded_max_bytes,
            )
        return marker
    text = _redact_public_text_preserving_context_separators(value)
    text = "".join(
        " " if unicodedata.category(character).startswith("C") else character
        for character in text
    )
    text = _ROLE_DELIMITER_PATTERN.sub(_REDACTED_ROLE_MARKER, text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > bounded_max_chars:
        if bounded_max_chars <= len(_TRUNCATION_MARKER):
            text = _TRUNCATION_MARKER[:bounded_max_chars]
        else:
            prefix_chars = bounded_max_chars - len(_TRUNCATION_MARKER)
            text = text[:prefix_chars].rstrip() + _TRUNCATION_MARKER
    if bounded_max_bytes is not None:
        text, _truncated = _truncate_utf8(
            text,
            max_bytes=bounded_max_bytes,
        )
    return text


def _exact_int(value: object, *, name: str, minimum: int) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an exact integer.")
    if value < minimum:
        raise ValueError(f"{name} is too small; minimum is {minimum}.")
    return value


def _bounded_marker(marker: str, *, max_chars: int) -> str:
    return marker[: max(max_chars, 0)]


def _redact_public_text_preserving_context_separators(text: str) -> str:
    """Protect non-path separators while delegating path policy centrally."""
    has_spaced_slash = _SPACED_SLASH_SEPARATOR_PATTERN.search(text) is not None
    has_prose_arrow = _PROSE_ARROW_BOUNDARY_PATTERN.search(text) is not None
    if not has_spaced_slash and not has_prose_arrow:
        return redact_public_text(text)

    slash_placeholder = _SLASH_SEPARATOR_PLACEHOLDER
    while slash_placeholder in text:
        slash_placeholder += "_"
    protected = _SPACED_SLASH_SEPARATOR_PATTERN.sub(slash_placeholder, text)

    arrow_placeholder = _ARROW_BOUNDARY_PLACEHOLDER
    while arrow_placeholder in protected:
        arrow_placeholder += "_"
    arrow_marker = f";{arrow_placeholder};"
    protected = _PROSE_ARROW_BOUNDARY_PATTERN.sub(arrow_marker, protected)

    redacted = redact_public_text(protected)
    return redacted.replace(arrow_marker, "->").replace(slash_placeholder, "/")


def encode_untrusted_context(
    items: Sequence[UntrustedContextItem],
    *,
    max_chars: int = MAX_UNTRUSTED_CONTEXT_CHARS,
    max_items: int = MAX_UNTRUSTED_CONTEXT_ITEMS,
    max_string_chars: int = MAX_UNTRUSTED_STRING_CHARS,
) -> str:
    """Encode context as valid JSON under one fail-closed projection budget."""
    if type(items) not in {list, tuple}:
        raise TypeError("Untrusted context items must be an exact list or tuple.")
    requested_max_bytes = _exact_int(
        max_chars,
        name="max_chars",
        minimum=MIN_UNTRUSTED_CONTEXT_BYTES,
    )
    requested_max_items = _exact_int(
        max_items,
        name="max_items",
        minimum=0,
    )
    requested_string_chars = _exact_int(
        max_string_chars,
        name="max_string_chars",
        minimum=len(_TRUNCATION_MARKER),
    )
    bounded_max_bytes = min(requested_max_bytes, MAX_UNTRUSTED_CONTEXT_BYTES)
    bounded_max_items = min(requested_max_items, MAX_UNTRUSTED_CONTEXT_ITEMS)
    bounded_string_chars = min(
        requested_string_chars,
        MAX_UNTRUSTED_STRING_CHARS,
    )
    selected = items[:bounded_max_items]
    was_truncated = len(items) > bounded_max_items
    encoded_items: list[dict[str, Any]] = []
    projection_budget = _ProjectionBudget(
        remaining_nodes=_MAX_PROJECTION_NODES,
        seen_containers=set(),
    )

    for item in selected:
        if type(item) is not UntrustedContextItem:
            raise TypeError(
                "Each untrusted context entry must be an exact UntrustedContextItem."
            )
        if type(item.source) is not UntrustedContextSource:
            raise TypeError(
                "Each untrusted context source must be an exact UntrustedContextSource."
            )
        candidate, item_truncated = _item_payload(
            item,
            max_string_chars=bounded_string_chars,
            projection_budget=projection_budget,
        )
        fitted, fit_truncated = _fit_projected_item(
            candidate,
            encoded_items=encoded_items,
            max_utf8_bytes=bounded_max_bytes,
            max_items=bounded_max_items,
            max_string_chars=bounded_string_chars,
            truncated=was_truncated or item_truncated or projection_budget.truncated,
        )
        if fitted is None:
            was_truncated = True
            continue
        encoded_items.append(fitted)
        was_truncated = (
            was_truncated
            or item_truncated
            or fit_truncated
            or projection_budget.truncated
        )

    envelope = _envelope_payload(
        encoded_items=encoded_items,
        max_utf8_bytes=bounded_max_bytes,
        max_items=bounded_max_items,
        max_string_chars=bounded_string_chars,
        truncated=was_truncated or projection_budget.truncated,
    )
    encoded = _json_dumps(envelope)
    if _utf8_size(encoded) <= bounded_max_bytes:
        return encoded

    minimal = _envelope_payload(
        encoded_items=[],
        max_utf8_bytes=bounded_max_bytes,
        max_items=bounded_max_items,
        max_string_chars=bounded_string_chars,
        truncated=True,
    )
    encoded_minimal = _json_dumps(minimal)
    if _utf8_size(encoded_minimal) > bounded_max_bytes:
        raise ValueError("UTF-8 byte cap is too small for the context envelope.")
    return encoded_minimal


def decode_untrusted_context(value: str) -> tuple[UntrustedContextItem, ...] | None:
    """Decode only the typed internal envelope used by the RAG boundary."""
    if type(value) is not str or _utf8_size(value) > MAX_UNTRUSTED_CONTEXT_BYTES:
        return None
    try:
        payload = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if (
        type(payload) is not dict
        or payload.get("schema") != UNTRUSTED_CONTEXT_SCHEMA
        or payload.get("trust") != UNTRUSTED_CONTEXT_TRUST
        or type(payload.get("items")) is not list
    ):
        return None

    decoded: list[UntrustedContextItem] = []
    for raw_item in payload["items"][:MAX_UNTRUSTED_CONTEXT_ITEMS]:
        if type(raw_item) is not dict:
            continue
        item_type = raw_item.get("type")
        source = raw_item.get("source")
        if (
            type(item_type) is not str
            or type(source) is not dict
            or type(source.get("kind")) is not str
            or "data" not in raw_item
        ):
            continue
        decoded.append(
            UntrustedContextItem(
                item_type=_decoded_untrusted_item_type(item_type),
                source=_decoded_untrusted_source(source),
                data=raw_item["data"],
            )
        )
    return tuple(decoded)


def _item_payload(
    item: UntrustedContextItem,
    *,
    max_string_chars: int,
    projection_budget: _ProjectionBudget,
) -> tuple[dict[str, Any], bool]:
    safe_data, truncated = _sanitize_value(
        item.data,
        max_string_chars=max_string_chars,
        depth=0,
        projection_budget=projection_budget,
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
    projection_budget: _ProjectionBudget,
    field_name: str | None = None,
) -> tuple[Any, bool]:
    if not projection_budget.consume_node():
        return _PROJECTION_BUDGET_MARKER, True
    if depth > _MAX_NESTING_DEPTH:
        return _TRUNCATION_MARKER, True
    if _is_protected_role_assignment(field_name, value):
        return _REDACTED_ROLE_MARKER, False
    if field_name is not None:
        handled, projected = _shared_sensitive_field_projection(field_name, value)
        if handled:
            if type(projected) is str:
                safe = sanitize_untrusted_text(
                    projected,
                    max_chars=max_string_chars,
                )
                return safe, safe.endswith(_TRUNCATION_MARKER)
            return projected, False
    if value is None or type(value) in {bool, int}:
        return value, False
    if type(value) is float:
        return (value, False) if math.isfinite(value) else ("[non-finite]", False)
    if type(value) is str:
        safe = sanitize_untrusted_text(value, max_chars=max_string_chars)
        return safe, safe.endswith(_TRUNCATION_MARKER)
    if type(value) is dict:
        if not projection_budget.enter_container(value):
            return _REPEATED_REFERENCE_MARKER, True
        item_limit = min(_MAX_MAPPING_ITEMS, projection_budget.remaining_nodes)
        truncated = len(value) > item_limit
        safe_mapping: dict[str, Any] = {}
        for raw_key, raw_item in islice(dict.items(value), item_limit):
            if projection_budget.remaining_nodes <= 0:
                safe_mapping["projection_truncated"] = _PROJECTION_BUDGET_MARKER
                projection_budget.truncated = True
                truncated = True
                break
            key = sanitize_untrusted_text(raw_key, max_chars=_SOURCE_LABEL_CHARS)
            if not key:
                key = "field"
            safe_item, item_truncated = _sanitize_value(
                raw_item,
                max_string_chars=max_string_chars,
                depth=depth + 1,
                projection_budget=projection_budget,
                field_name=key,
            )
            safe_mapping[key] = safe_item
            truncated = truncated or item_truncated
        return safe_mapping, truncated
    if type(value) in {list, tuple}:
        if not projection_budget.enter_container(value):
            return _REPEATED_REFERENCE_MARKER, True
        item_limit = min(_MAX_COLLECTION_ITEMS, projection_budget.remaining_nodes)
        truncated = len(value) > item_limit
        safe_items: list[Any] = []
        for item in islice(value, item_limit):
            if projection_budget.remaining_nodes <= 0:
                safe_items.append(_PROJECTION_BUDGET_MARKER)
                projection_budget.truncated = True
                truncated = True
                break
            safe_item, item_truncated = _sanitize_value(
                item,
                max_string_chars=max_string_chars,
                depth=depth + 1,
                projection_budget=projection_budget,
            )
            safe_items.append(safe_item)
            truncated = truncated or item_truncated
        return safe_items, truncated
    if type(value) in {set, frozenset}:
        if not projection_budget.enter_container(value):
            return _REPEATED_REFERENCE_MARKER, True
        item_limit = min(_MAX_COLLECTION_ITEMS, projection_budget.remaining_nodes)
        if len(value) > item_limit:
            projection_budget.truncated = True
            return [_TRUNCATION_MARKER], True
        safe_set_items: list[Any] = []
        truncated = False
        raw_set_items = list(islice(value, item_limit))
        for item in raw_set_items:
            if projection_budget.remaining_nodes <= 0:
                safe_set_items.append(_PROJECTION_BUDGET_MARKER)
                projection_budget.truncated = True
                truncated = True
                break
            safe_item, item_truncated = _sanitize_value(
                item,
                max_string_chars=max_string_chars,
                depth=depth + 1,
                projection_budget=projection_budget,
            )
            safe_set_items.append(safe_item)
            truncated = truncated or item_truncated
        safe_set_items.sort(key=_json_dumps)
        return safe_set_items, truncated
    return _UNSUPPORTED_VALUE_MARKER, False


def _is_protected_role_assignment(
    field_name: str | None,
    value: Any,
) -> bool:
    if field_name is None or _normalized_key(field_name) != "role":
        return False
    return bool(
        type(value) is str and value.strip().casefold() in _PROTECTED_ROLE_VALUES
    )


def _normalized_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _shared_sensitive_field_projection(
    field_name: str,
    value: Any,
) -> tuple[bool, Any]:
    """Use the shared exact-type policy to classify structured private fields."""
    probe = public_diagnostic_value(
        _STRUCTURED_FIELD_PROBE,
        field_name=field_name,
    )
    if probe == REDACTED_SECRET_MARKER:
        return True, REDACTED_SECRET_MARKER
    if probe == REDACTED_PATH_MARKER:
        if value is None or type(value) in {bool, int, float, str}:
            projected = public_diagnostic_value(value, field_name=field_name)
            return True, projected
        return True, _UNSUPPORTED_VALUE_MARKER
    if type(probe) is str and probe.startswith(_SUBJECT_REFERENCE_PREFIX):
        if value is None or type(value) in {bool, int, float, str}:
            projected = public_diagnostic_value(value, field_name=field_name)
            return True, projected
        return True, _UNSUPPORTED_VALUE_MARKER
    return False, None


def _decoded_untrusted_source(source: dict[str, Any]) -> UntrustedContextSource:
    """Downgrade serialized claims to host-owned or authoritative provenance."""
    kind = source["kind"]
    normalized_kind = _normalized_key(kind)
    host_authority_claim = normalized_kind.startswith(
        ("authoritative", "host", "official", "policy", "system", "trusted")
    ) or any(marker in normalized_kind for marker in _HOST_AUTHORITATIVE_SOURCE_MARKERS)
    if host_authority_claim:
        return UntrustedContextSource(kind="untrusted_context")
    return UntrustedContextSource(
        kind=kind,
        id=source.get("id") if type(source.get("id")) is str else None,
        category=(
            source.get("category") if type(source.get("category")) is str else None
        ),
    )


def _decoded_untrusted_item_type(item_type: str) -> str:
    """Namespace external labels that could impersonate host-owned context."""
    safe_item_type = (
        sanitize_untrusted_text(
            item_type,
            max_chars=_SOURCE_LABEL_CHARS,
        )
        or "context_data"
    )
    if _normalized_key(safe_item_type) not in _HOST_AUTHORITATIVE_ITEM_TYPES:
        return safe_item_type
    suffix_max_chars = _SOURCE_LABEL_CHARS - len(_EXTERNAL_CONTEXT_TYPE_PREFIX)
    safe_suffix = sanitize_untrusted_text(
        safe_item_type,
        max_chars=suffix_max_chars,
    )
    return f"{_EXTERNAL_CONTEXT_TYPE_PREFIX}{safe_suffix}"


def _envelope_payload(
    *,
    encoded_items: list[dict[str, Any]],
    max_utf8_bytes: int,
    max_items: int,
    max_string_chars: int,
    truncated: bool,
) -> dict[str, Any]:
    return {
        "schema": UNTRUSTED_CONTEXT_SCHEMA,
        "trust": UNTRUSTED_CONTEXT_TRUST,
        "bounds": {
            "max_chars": max_utf8_bytes,
            "max_utf8_bytes": max_utf8_bytes,
            "max_items": max_items,
            "max_string_chars": max_string_chars,
        },
        "items": encoded_items,
        "truncated": truncated,
    }


def _fit_projected_item(
    candidate: dict[str, Any],
    *,
    encoded_items: list[dict[str, Any]],
    max_utf8_bytes: int,
    max_items: int,
    max_string_chars: int,
    truncated: bool,
) -> tuple[dict[str, Any] | None, bool]:
    envelope = _envelope_payload(
        encoded_items=[*encoded_items, candidate],
        max_utf8_bytes=max_utf8_bytes,
        max_items=max_items,
        max_string_chars=max_string_chars,
        truncated=truncated,
    )
    if _utf8_size(_json_dumps(envelope)) <= max_utf8_bytes:
        return candidate, False

    best: dict[str, Any] | None = None
    low = 0
    high = max_utf8_bytes
    while low <= high:
        leaf_bytes = (low + high) // 2
        clipped_data, _clipped = _clip_projected_strings(
            candidate["data"],
            max_utf8_bytes=leaf_bytes,
        )
        clipped_candidate = {
            "type": candidate["type"],
            "source": candidate["source"],
            "data": clipped_data,
        }
        clipped_envelope = _envelope_payload(
            encoded_items=[*encoded_items, clipped_candidate],
            max_utf8_bytes=max_utf8_bytes,
            max_items=max_items,
            max_string_chars=max_string_chars,
            truncated=True,
        )
        if _utf8_size(_json_dumps(clipped_envelope)) <= max_utf8_bytes:
            best = clipped_candidate
            low = leaf_bytes + 1
        else:
            high = leaf_bytes - 1
    return best, best is not None


def _clip_projected_strings(
    value: Any,
    *,
    max_utf8_bytes: int,
) -> tuple[Any, bool]:
    if type(value) is str:
        return _truncate_utf8(value, max_bytes=max_utf8_bytes)
    if type(value) is dict:
        clipped: dict[str, Any] = {}
        was_clipped = False
        for key, item in value.items():
            clipped_item, item_clipped = _clip_projected_strings(
                item,
                max_utf8_bytes=max_utf8_bytes,
            )
            clipped[key] = clipped_item
            was_clipped = was_clipped or item_clipped
        return clipped, was_clipped
    if type(value) is list:
        clipped_items: list[Any] = []
        was_clipped = False
        for item in value:
            clipped_item, item_clipped = _clip_projected_strings(
                item,
                max_utf8_bytes=max_utf8_bytes,
            )
            clipped_items.append(clipped_item)
            was_clipped = was_clipped or item_clipped
        return clipped_items, was_clipped
    return value, False


def _truncate_utf8(value: str, *, max_bytes: int) -> tuple[str, bool]:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value, False
    marker_bytes = _TRUNCATION_MARKER.encode("utf-8")
    if max_bytes <= len(marker_bytes):
        return marker_bytes[:max_bytes].decode("utf-8", errors="ignore"), True
    prefix_budget = max_bytes - len(marker_bytes)
    prefix = encoded[:prefix_budget].decode("utf-8", errors="ignore").rstrip()
    return prefix + _TRUNCATION_MARKER, True


def _utf8_size(value: str) -> int:
    return len(value.encode("utf-8"))


def _json_dumps(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
