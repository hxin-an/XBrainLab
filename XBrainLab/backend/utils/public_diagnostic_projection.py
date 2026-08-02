"""Fail-closed structured projection for public diagnostic values."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from itertools import islice
from typing import Any, cast

from XBrainLab.backend.utils import public_diagnostics as text_rules


@dataclass
class _ProjectionContext:
    """Global work budget shared by one structured diagnostic projection."""

    remaining_nodes: int = text_rules.PUBLIC_DIAGNOSTIC_MAX_TOTAL_NODES
    remaining_bytes: int = text_rules.PUBLIC_DIAGNOSTIC_MAX_OUTPUT_BYTES
    active_container_ids: set[int] = field(default_factory=set)
    seen_container_ids: set[int] = field(default_factory=set)
    exhausted: bool = False

    def reserve_node(self) -> bool:
        if self.remaining_nodes <= 0 or self.remaining_bytes <= 0:
            self.exhausted = True
            return False
        self.remaining_nodes -= 1
        return True

    def bounded_text(self, value: str) -> str:
        if self.remaining_bytes <= 0:
            self.exhausted = True
            return text_rules.PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER
        bounded = text_rules._truncate_text_to_bytes(value, self.remaining_bytes)
        used = len(bounded.encode("utf-8", errors="replace"))
        self.remaining_bytes = max(0, self.remaining_bytes - used)
        if bounded != value:
            self.exhausted = True
        return bounded

    def bounded_primitive(self, value: None | bool | int | float) -> Any:
        limit = min(self.remaining_bytes, text_rules._MAX_SAFE_PRIMITIVE_TEXT_BYTES)
        rendered = text_rules._safe_primitive_text(value, max_bytes=limit)
        if rendered is None:
            self.exhausted = True
            return self.bounded_text(text_rules.PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER)
        self.remaining_bytes -= len(rendered.encode("utf-8"))
        return value


def project_public_diagnostic_value(
    value: Any,
    *,
    field_name: str | None,
    disclosure: text_rules.DiagnosticDisclosure,
) -> Any:
    """Project exact safe values and enforce the serialized JSON byte cap."""
    projected = _project_value(
        value,
        field_name=field_name,
        disclosure=disclosure,
        depth=0,
        context=_ProjectionContext(),
    )
    return _fit_serialized_output(projected)


def _project_value(
    value: Any,
    *,
    field_name: str | None,
    disclosure: text_rules.DiagnosticDisclosure,
    depth: int,
    context: _ProjectionContext,
) -> Any:
    if not context.reserve_node():
        return text_rules.PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER
    normalized_field_name = (
        text_rules._normalized_field_name(field_name)
        if field_name is not None
        else None
    )
    sensitivity = (
        text_rules._diagnostic_field_sensitivity(normalized_field_name)
        if normalized_field_name is not None
        else text_rules._DiagnosticFieldSensitivity.PUBLIC
    )
    if sensitivity is text_rules._DiagnosticFieldSensitivity.SECRET:
        return context.bounded_text(text_rules.REDACTED_SECRET_MARKER)
    if (
        disclosure is text_rules.DiagnosticDisclosure.PUBLIC
        and normalized_field_name is not None
        and sensitivity is text_rules._DiagnosticFieldSensitivity.IDENTITY
    ):
        return _identity_value_reference(
            value,
            preserve_mapping_keys=bool(
                text_rules._IDENTITY_BY_CONTAINER_PATTERN.search(normalized_field_name)
            ),
            depth=depth,
            context=context,
            reserve_node=False,
        )
    if text_rules._has_exact_type(value, text_rules._SAFE_PATH_TYPES):
        return context.bounded_text(
            text_rules._path_reference(
                text_rules._pathlike_text(value),
                disclosure=disclosure,
                force=True,
            )
        )
    if type(value) is str:
        if sensitivity is text_rules._DiagnosticFieldSensitivity.PATH:
            return context.bounded_text(
                text_rules._path_reference(
                    value,
                    disclosure=disclosure,
                    force=True,
                )
            )
        return context.bounded_text(
            text_rules.public_diagnostic_text(value, disclosure=disclosure)
        )
    if text_rules._has_exact_type(value, text_rules._SAFE_CONTAINER_TYPES):
        return _project_container(
            value,
            field_name=field_name,
            disclosure=disclosure,
            depth=depth,
            context=context,
        )
    if value is None or text_rules._has_exact_type(
        value,
        text_rules._SAFE_PRIMITIVE_TYPES,
    ):
        return context.bounded_primitive(value)
    return context.bounded_text(text_rules.PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER)


def _project_container(
    value: dict[Any, Any] | list[Any] | tuple[Any, ...] | set[Any],
    *,
    field_name: str | None,
    disclosure: text_rules.DiagnosticDisclosure,
    depth: int,
    context: _ProjectionContext,
) -> Any:
    if depth >= text_rules.PUBLIC_DIAGNOSTIC_MAX_CONTAINER_DEPTH:
        return context.bounded_text(text_rules.PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER)
    container_id = id(value)
    if container_id in context.active_container_ids:
        return context.bounded_text(text_rules.PUBLIC_DIAGNOSTIC_CYCLE_MARKER)
    if container_id in context.seen_container_ids:
        return context.bounded_text(text_rules.PUBLIC_DIAGNOSTIC_SHARED_MARKER)
    context.seen_container_ids.add(container_id)
    context.active_container_ids.add(container_id)
    try:
        if type(value) is dict:
            return _project_mapping(
                value,
                disclosure=disclosure,
                depth=depth,
                context=context,
            )
        sequence = cast(list[Any] | tuple[Any, ...] | set[Any], value)
        return _project_sequence(
            sequence,
            field_name=field_name,
            disclosure=disclosure,
            depth=depth,
            context=context,
        )
    finally:
        context.active_container_ids.remove(container_id)


def _project_mapping(
    value: dict[Any, Any],
    *,
    disclosure: text_rules.DiagnosticDisclosure,
    depth: int,
    context: _ProjectionContext,
) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    truncated = False
    for index, (key, item) in enumerate(
        islice(
            dict.items(value),
            text_rules.PUBLIC_DIAGNOSTIC_MAX_CONTAINER_ITEMS + 1,
        )
    ):
        if (
            index >= text_rules.PUBLIC_DIAGNOSTIC_MAX_CONTAINER_ITEMS
            or context.exhausted
        ):
            truncated = True
            break
        if not context.reserve_node():
            truncated = True
            break
        public_key = context.bounded_text(
            _public_mapping_key(key, disclosure=disclosure)
        )
        if context.exhausted:
            projected[text_rules.PUBLIC_DIAGNOSTIC_TRUNCATED_ITEMS_KEY] = 1
            return projected
        projected[public_key] = _project_value(
            item,
            field_name=public_key,
            disclosure=disclosure,
            depth=depth + 1,
            context=context,
        )
        if context.exhausted:
            truncated = True
            break
    omitted = (
        0
        if context.exhausted
        else _bounded_omitted_count(
            value,
            len(projected),
            truncated=truncated,
        )
    )
    if omitted > 0:
        projected[text_rules.PUBLIC_DIAGNOSTIC_TRUNCATED_ITEMS_KEY] = omitted
    return projected


def _project_sequence(
    value: list[Any] | tuple[Any, ...] | set[Any],
    *,
    field_name: str | None,
    disclosure: text_rules.DiagnosticDisclosure,
    depth: int,
    context: _ProjectionContext,
) -> list[Any]:
    projected: list[Any] = []
    truncated = False
    for index, item in enumerate(
        islice(value, text_rules.PUBLIC_DIAGNOSTIC_MAX_CONTAINER_ITEMS + 1)
    ):
        if (
            index >= text_rules.PUBLIC_DIAGNOSTIC_MAX_CONTAINER_ITEMS
            or context.exhausted
        ):
            truncated = True
            break
        projected.append(
            _project_value(
                item,
                field_name=field_name,
                disclosure=disclosure,
                depth=depth + 1,
                context=context,
            )
        )
        if context.exhausted:
            truncated = True
            break
    omitted = (
        0
        if context.exhausted
        else _bounded_omitted_count(
            value,
            len(projected),
            truncated=truncated,
        )
    )
    if omitted > 0:
        projected.append(f"{text_rules.PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER}:{omitted}")
    return projected


def _bounded_omitted_count(
    value: object,
    projected_count: int,
    *,
    truncated: bool,
) -> int:
    if text_rules._has_exact_type(value, text_rules._SAFE_CONTAINER_TYPES):
        return max(0, len(value) - projected_count)  # type: ignore[arg-type]
    return 1 if truncated else 0


def _identity_value_reference(
    value: Any,
    *,
    preserve_mapping_keys: bool = False,
    depth: int = 0,
    context: _ProjectionContext,
    reserve_node: bool = True,
) -> Any:
    if reserve_node and not context.reserve_node():
        return text_rules.PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER
    if value is None or type(value) is bool:
        return value
    if type(value) is str:
        if (
            not value.strip()
            or text_rules._is_non_identity_assignment(value)
            or text_rules._is_subject_reference(value)
        ):
            return context.bounded_text(value)
        reference = text_rules._private_reference(value, namespace="subject")
        return context.bounded_text(f"[SUBJECT_REF:{reference}]")
    if text_rules._has_exact_type(value, text_rules._SAFE_CONTAINER_TYPES):
        return _project_identity_container(
            value,
            preserve_mapping_keys=preserve_mapping_keys,
            depth=depth,
            context=context,
        )
    if type(value) is int or type(value) is float:
        reference = text_rules._private_reference(value, namespace="subject")
        return context.bounded_text(f"[SUBJECT_REF:{reference}]")
    return context.bounded_text(text_rules.PUBLIC_DIAGNOSTIC_UNSUPPORTED_MARKER)


def _project_identity_container(
    value: dict[Any, Any] | list[Any] | tuple[Any, ...] | set[Any],
    *,
    preserve_mapping_keys: bool,
    depth: int,
    context: _ProjectionContext,
) -> Any:
    if depth >= text_rules.PUBLIC_DIAGNOSTIC_MAX_CONTAINER_DEPTH:
        return context.bounded_text(text_rules.PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER)
    container_id = id(value)
    if container_id in context.active_container_ids:
        return context.bounded_text(text_rules.PUBLIC_DIAGNOSTIC_CYCLE_MARKER)
    if container_id in context.seen_container_ids:
        return context.bounded_text(text_rules.PUBLIC_DIAGNOSTIC_SHARED_MARKER)
    context.seen_container_ids.add(container_id)
    context.active_container_ids.add(container_id)
    try:
        if type(value) is dict:
            return _project_identity_mapping(
                value,
                preserve_mapping_keys=preserve_mapping_keys,
                depth=depth,
                context=context,
            )
        sequence = cast(list[Any] | tuple[Any, ...] | set[Any], value)
        return _project_identity_sequence(
            sequence,
            preserve_mapping_keys=preserve_mapping_keys,
            depth=depth,
            context=context,
        )
    finally:
        context.active_container_ids.remove(container_id)


def _project_identity_mapping(
    value: dict[Any, Any],
    *,
    preserve_mapping_keys: bool,
    depth: int,
    context: _ProjectionContext,
) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    truncated = False
    for index, (key, item) in enumerate(
        islice(
            dict.items(value),
            text_rules.PUBLIC_DIAGNOSTIC_MAX_CONTAINER_ITEMS + 1,
        )
    ):
        if (
            index >= text_rules.PUBLIC_DIAGNOSTIC_MAX_CONTAINER_ITEMS
            or context.exhausted
        ):
            truncated = True
            break
        if not context.reserve_node():
            truncated = True
            break
        key_text = context.bounded_text(_public_mapping_key(key))
        if context.exhausted:
            truncated = True
            break
        if _is_identity_value_key(key) or _is_identity_field_key(key):
            projected[key_text] = _identity_value_reference(
                item,
                depth=depth + 1,
                context=context,
            )
        elif _is_identity_metadata_key(key):
            projected[key_text] = _project_value(
                item,
                field_name=key_text,
                disclosure=text_rules.DiagnosticDisclosure.PUBLIC,
                depth=depth + 1,
                context=context,
            )
        elif preserve_mapping_keys:
            projected[key_text] = _identity_value_reference(
                item,
                preserve_mapping_keys=True,
                depth=depth + 1,
                context=context,
            )
        else:
            projected[context.bounded_text(_identity_mapping_key_reference(key))] = (
                _identity_value_reference(
                    item,
                    depth=depth + 1,
                    context=context,
                )
            )
        if context.exhausted:
            truncated = True
            break
    omitted = (
        0
        if context.exhausted
        else _bounded_omitted_count(
            value,
            len(projected),
            truncated=truncated,
        )
    )
    if omitted > 0:
        projected[text_rules.PUBLIC_DIAGNOSTIC_TRUNCATED_ITEMS_KEY] = omitted
    return projected


def _project_identity_sequence(
    value: list[Any] | tuple[Any, ...] | set[Any],
    *,
    preserve_mapping_keys: bool,
    depth: int,
    context: _ProjectionContext,
) -> list[Any]:
    projected: list[Any] = []
    truncated = False
    for index, item in enumerate(
        islice(value, text_rules.PUBLIC_DIAGNOSTIC_MAX_CONTAINER_ITEMS + 1)
    ):
        if (
            index >= text_rules.PUBLIC_DIAGNOSTIC_MAX_CONTAINER_ITEMS
            or context.exhausted
        ):
            truncated = True
            break
        projected.append(
            _identity_value_reference(
                item,
                preserve_mapping_keys=preserve_mapping_keys,
                depth=depth + 1,
                context=context,
            )
        )
        if context.exhausted:
            truncated = True
            break
    omitted = (
        0
        if context.exhausted
        else _bounded_omitted_count(
            value,
            len(projected),
            truncated=truncated,
        )
    )
    if omitted > 0:
        projected.append(f"{text_rules.PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER}:{omitted}")
    return projected


def _is_identity_field_key(value: object) -> bool:
    return (
        text_rules._diagnostic_field_sensitivity(value)
        is text_rules._DiagnosticFieldSensitivity.IDENTITY
    )


def _is_identity_value_key(value: object) -> bool:
    return bool(
        text_rules._IDENTITY_VALUE_KEY_PATTERN.fullmatch(
            text_rules._normalized_field_name(value)
        )
    )


def _is_identity_metadata_key(value: object) -> bool:
    return (
        text_rules._normalized_field_name(value).casefold()
        in text_rules._IDENTITY_METADATA_KEYS
    )


def _identity_mapping_key_reference(value: object) -> str:
    reference = text_rules._private_reference(value, namespace="subject")
    return f"[SUBJECT_REF:{reference}]"


def _public_mapping_key(
    value: object,
    *,
    disclosure: text_rules.DiagnosticDisclosure = (
        text_rules.DiagnosticDisclosure.PUBLIC
    ),
) -> str:
    text = text_rules._normalized_field_name(value)
    if (
        text_rules._diagnostic_field_sensitivity(text)
        is not text_rules._DiagnosticFieldSensitivity.PUBLIC
    ):
        return text_rules._remove_control_characters(
            text,
            layout=text_rules.DiagnosticTextLayout.SINGLE_LINE,
        )
    return text_rules.public_diagnostic_text(text, disclosure=disclosure)


def _fit_serialized_output(value: Any) -> Any:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(serialized) <= text_rules.PUBLIC_DIAGNOSTIC_MAX_OUTPUT_BYTES:
        return value
    if type(value) is dict:
        return {text_rules.PUBLIC_DIAGNOSTIC_TRUNCATED_ITEMS_KEY: 1}
    if type(value) is list:
        return [text_rules.PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER]
    return text_rules.PUBLIC_DIAGNOSTIC_TRUNCATED_MARKER
