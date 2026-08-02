"""Pure payload helpers shared by Data Interpretation UI workflows."""

from __future__ import annotations

from typing import Any


def diagnostic_payload(result: Any, key: str) -> dict[str, Any]:
    """Return one detached dictionary from command diagnostics."""
    diagnostics = getattr(result, "diagnostics", {})
    value = diagnostics.get(key, {}) if isinstance(diagnostics, dict) else {}
    return dict(value) if isinstance(value, dict) else {}


def optional_payload_id(payload: dict[str, Any], key: str) -> str | None:
    """Normalize an optional command identity field."""
    value = payload.get(key)
    return str(value) if value else None


def decision_reason(decision: dict[str, Any]) -> str:
    """Build the user-facing reason for a blocked interpretation decision."""
    reasons = decision.get("blocked_reasons") or decision.get("reasons") or []
    if reasons:
        return "\n".join(str(reason) for reason in reasons)
    return "This data interpretation cannot be applied."


def merge_interpretation_choices(
    base: dict[str, Any],
    updates: dict[str, Any],
) -> dict[str, Any]:
    """Replace mutually exclusive label choices while merging metadata edits."""
    merged = dict(base)
    label_choice_keys = (
        "skip_labels",
        "label_carrier",
        "class_map",
        "event_roles",
        "excluded_label_carriers",
        "label_carrier_choices",
        "label_carrier_remap",
    )
    if not any(key in updates for key in label_choice_keys):
        for key, value in updates.items():
            if key == "metadata_overrides" and isinstance(value, dict):
                previous = merged.get(key)
                merged[key] = {
                    **(previous if isinstance(previous, dict) else {}),
                    **value,
                }
            else:
                merged[key] = value
        return merged

    for key in label_choice_keys:
        merged.pop(key, None)

    skip_labels = bool(updates.get("skip_labels"))
    label_carrier = str(updates.get("label_carrier") or "").strip()
    if skip_labels or label_carrier == "embedded_events":
        for key in (
            "required_label_carriers",
            "label_carrier_choices",
            "label_carrier_remap",
            "excluded_label_carriers",
        ):
            merged.pop(key, None)
    if skip_labels or label_carrier != "embedded_events":
        for key in (
            "internal_event_selection",
            "run_event_mappings",
            "class_map",
            "event_roles",
        ):
            merged.pop(key, None)

    for key, value in updates.items():
        if key == "metadata_overrides" and isinstance(value, dict):
            previous = merged.get(key)
            merged[key] = {
                **(previous if isinstance(previous, dict) else {}),
                **value,
            }
        else:
            merged[key] = value
    return merged
