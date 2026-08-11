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

_VALUE_DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "role": {
            "type": "string",
            "enum": [
                "stimulus",
                "response",
                "artifact",
                "boundary",
                "system",
                "annotation",
                "unknown",
            ],
            "description": "Scientific event role, independent of class use.",
        },
        "keep_event": {
            "type": "boolean",
            "description": "Whether rows with this raw value remain as events.",
        },
        "use_as_class": {
            "type": "boolean",
            "description": "Whether this kept event is a supervised class target.",
        },
        "class_name": {
            "type": "string",
            "description": "Required non-empty class name when use_as_class is true.",
        },
    },
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
        "target_event_codes": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "EEG event codes selected for event-order label placement. "
                "Labels are assigned in row order across this selected event set."
            ),
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
        "sample_index_base": {
            "type": "string",
            "enum": ["zero_based", "one_based"],
            "description": (
                "Required for sample_index timing: whether the first index in "
                "the selected origin is 0 or 1."
            ),
        },
        "sample_index_origin": {
            "type": "string",
            "enum": ["recording_relative", "absolute"],
            "description": (
                "Required for sample_index timing: recording_relative indexes "
                "start at this Raw segment; absolute indexes use MNE sample "
                "coordinates and therefore include first_samp."
            ),
        },
        "placement_method": {
            "type": "string",
            "enum": ["eeg_event", "time_field", "interval", "event_code"],
            "description": (
                "How label rows are positioned on the EEG timeline for review "
                "and downstream EEG epoch setup."
            ),
        },
        "duration_field": {
            "type": "string",
            "description": (
                "Optional duration or end-time field preserved for EEG epoch setup."
            ),
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
        "target_files": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "EEG file paths/names reviewed against one shared label carrier."
            ),
        },
        "value_decisions": {
            "type": "object",
            "additionalProperties": _VALUE_DECISION_SCHEMA,
            "description": (
                "Per-observed-value event role, retention, and independent "
                "supervised-class decision keyed by raw value."
            ),
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
        "label_sources": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Additional label/event files or folders attached from outside "
                "the selected EEG source."
            ),
        },
        "skip_labels": {
            "type": "boolean",
            "description": (
                "User explicitly chose to continue without attaching external "
                "labels for now."
            ),
        },
        "required_label_carriers": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Saved label/event carriers that must be present or explicitly "
                "remapped before apply."
            ),
        },
        "excluded_label_carriers": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Auto-detected or loaded label/event carriers the user removed "
                "from this import."
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
        "run_event_mappings": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
            "description": (
                "Legacy/embedded-event per-run meanings keyed by EEG file path or "
                "run identifier; external carriers use value_decisions."
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
            "description": (
                "Legacy/embedded-event class map; external carrier classes are "
                "derived only from per-carrier value_decisions."
            ),
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
