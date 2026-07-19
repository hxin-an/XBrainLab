"""JSON-safe serialization helpers for application-service contracts."""

from __future__ import annotations

import os
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import PurePath
from typing import Any


def serialize_json_value(value: Any, *, _seen: set[int] | None = None) -> Any:
    """Convert application values to JSON-safe primitives.

    Runtime UI queries may carry object references in memory. External command
    consumers receive an explicit opaque-object descriptor instead of the raw
    Python object when a result is serialized.
    """
    if isinstance(value, Enum):
        return serialize_json_value(value.value, _seen=_seen)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, PurePath):
        return os.fspath(value)

    seen = _seen if _seen is not None else set()
    identity = id(value)
    if identity in seen:
        return {"object_type": type(value).__name__, "repr": "<recursive>"}

    if is_dataclass(value) and not isinstance(value, type):
        seen.add(identity)
        try:
            return {
                item.name: serialize_json_value(getattr(value, item.name), _seen=seen)
                for item in fields(value)
            }
        finally:
            seen.remove(identity)
    if isinstance(value, dict):
        seen.add(identity)
        try:
            return {
                str(key): serialize_json_value(item, _seen=seen)
                for key, item in value.items()
            }
        finally:
            seen.remove(identity)
    if isinstance(value, (list, tuple, set, frozenset)):
        seen.add(identity)
        try:
            return [serialize_json_value(item, _seen=seen) for item in value]
        finally:
            seen.remove(identity)

    module_name = type(value).__module__
    if module_name.startswith("numpy"):
        tolist = getattr(value, "tolist", None)
        if callable(tolist):
            return serialize_json_value(tolist(), _seen=seen)
        item = getattr(value, "item", None)
        if callable(item):
            return serialize_json_value(item(), _seen=seen)

    return {
        "object_type": type(value).__name__,
        "repr": _safe_repr(value),
    }


def split_runtime_fields(
    values: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Separate JSON contract fields from process-local runtime references."""
    diagnostics: dict[str, Any] = {}
    runtime: dict[str, Any] = {}
    for key, value in (values or {}).items():
        if _is_json_contract_value(value):
            diagnostics[str(key)] = serialize_json_value(value)
        else:
            runtime[str(key)] = value
    return diagnostics, runtime


def _is_json_contract_value(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, float, bool, Enum, PurePath)):
        return True
    if isinstance(value, dict):
        return all(
            isinstance(key, (str, int, float, bool)) and _is_json_contract_value(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return all(_is_json_contract_value(item) for item in value)
    module_name = type(value).__module__
    if module_name.startswith("numpy"):
        shape = getattr(value, "shape", None)
        return shape in {None, ()}
    return False


def _safe_repr(value: Any) -> str:
    try:
        return repr(value)
    except Exception:
        return f"<{type(value).__name__}>"
