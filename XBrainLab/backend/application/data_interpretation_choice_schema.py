"""Shared JSON schema for Data Interpretation preview choices."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def data_interpretation_choices_schema() -> dict[str, Any]:
    """Return the shared schema for ``PreviewInterpretationCommand.choices``."""
    return deepcopy(_CHOICES_SCHEMA)


_STRING_MAP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": {"type": "string"},
}

_LABEL_CARRIER_CHOICE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "label_field": {
            "type": "string",
            "description": "Column, variable, or label sequence used as class labels.",
        },
        "anchor": {
            "type": "string",
            "description": "Column, variable, or event anchor used for timing.",
        },
        "time_model": {
            "type": "string",
            "enum": [
                "seconds",
                "sample_index",
                "relative_time",
                "trial_order",
                "lsl_time",
                "unknown",
            ],
            "description": "How carrier timing should be interpreted.",
        },
        "granularity": {
            "type": "string",
            "enum": ["trial", "event", "recording", "stream", "unknown"],
            "description": "Whether labels describe trials, events, or a recording.",
        },
        "role": {
            "type": "string",
            "description": (
                "User-facing role for the carrier, such as class cue labels."
            ),
        },
        "target_file": {
            "type": "string",
            "description": "EEG file path/name this carrier should align with.",
        },
    },
}

_METADATA_OVERRIDE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "subject": {"type": "string"},
        "session": {"type": "string"},
        "task": {"type": "string"},
        "run": {"type": "string"},
    },
}

_CHOICES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "recipe_id": {
            "type": "string",
            "description": "Saved recipe identifier carried through recipe reload.",
        },
        "selected_eeg_files": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Selected EEG files from the latest scan result.",
        },
        "required_label_carriers": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Saved label/event carriers that must be present or explicitly "
                "remapped before apply."
            ),
        },
        "eeg_file_remap": {
            **_STRING_MAP_SCHEMA,
            "description": (
                "Map saved EEG file path/name from a recipe to the current "
                "replacement EEG file path/name before re-previewing."
            ),
            "examples": [
                {"/recipe/old_raw.fif": "/data/current_raw.fif"},
            ],
        },
        "label_carrier_remap": {
            **_STRING_MAP_SCHEMA,
            "description": (
                "Map saved label/event carrier path/name from a recipe to the "
                "current replacement carrier before re-previewing."
            ),
            "examples": [
                {"/recipe/events.tsv": "/data/events.tsv"},
            ],
        },
        "label_carrier_choices": {
            "type": "object",
            "additionalProperties": _LABEL_CARRIER_CHOICE_SCHEMA,
            "description": (
                "Per-carrier label field, anchor, time model, granularity, role, "
                "and target-file choices keyed by carrier path or file name."
            ),
        },
        "event_roles": {
            **_STRING_MAP_SCHEMA,
            "description": "Map event field names to user-confirmed roles.",
        },
        "metadata_overrides": {
            "type": "object",
            "additionalProperties": _METADATA_OVERRIDE_SCHEMA,
            "description": (
                "Per-EEG-file metadata overrides keyed by file path or file name."
            ),
        },
        "label_carrier": {
            "type": "string",
            "enum": [
                "embedded_events",
                "external_file",
                "bids_events",
                "edf_annotations",
                "xdf_stream",
                "none",
                "unknown",
            ],
            "description": "Where labels/events come from for this import.",
        },
        "event_role": {
            "type": "string",
            "enum": ["stimulus", "response", "trial", "annotation", "unknown"],
            "description": "Role assigned to event markers.",
        },
        "class_map": {
            **_STRING_MAP_SCHEMA,
            "description": "Map raw event or label values to class names.",
        },
        "anchor": {
            "type": "string",
            "enum": ["sample", "timestamp", "onset_seconds", "lsl_time", "unknown"],
            "description": "Time anchor for labels/events.",
        },
        "subject": {
            "type": "string",
            "description": "Subject metadata override.",
        },
        "session": {
            "type": "string",
            "description": "Session metadata override.",
        },
        "task": {
            "type": "string",
            "description": "Task metadata override.",
        },
        "run": {
            "type": "string",
            "description": "Run metadata override.",
        },
    },
    "description": (
        "Optional user-confirmed choices for Data Interpretation preview. "
        "Recipe reload remaps belong here, not in legacy load/attach tools."
    ),
}
