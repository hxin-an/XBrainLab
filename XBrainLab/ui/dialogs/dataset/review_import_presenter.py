"""Pure presenter helpers for the Data Import review/import step."""

from __future__ import annotations


def eeg_data_summary(
    *,
    selected_names: list[str],
    file_count: int,
    preview_text: str,
) -> str:
    """Return a compact EEG scope summary."""
    count = file_count or len(selected_names)
    file_word = "file" if count == 1 else "files"
    summary = f"{count} EEG {file_word}"
    return f"{summary} · {preview_text}" if preview_text else summary


def metadata_summary(
    *,
    row_count: int,
    complete_count: int,
    missing_fields: set[str],
    is_bids_source: bool,
    fallback_summary: str,
) -> str:
    """Return the metadata review summary shown before import."""
    if row_count <= 0:
        return "No metadata rows detected."
    if is_bids_source and not missing_fields:
        file_word = "file" if row_count == 1 else "files"
        return f"BIDS entities reviewed · {row_count} {file_word}"
    _ = complete_count
    return fallback_summary


def label_source_summary(
    *,
    source_mode: str,
    internal_candidate_count: int,
    active_carrier_count: int,
    has_bids_events: bool,
    has_extra_sources: bool,
) -> str:
    """Return the label source summary shown before import."""
    if source_mode == "internal_events":
        if internal_candidate_count:
            event_word = "event" if internal_candidate_count == 1 else "events"
            return f"Labels inside EEG files · {internal_candidate_count} {event_word}"
        return "Labels inside EEG files · no class labels selected"
    if active_carrier_count <= 0:
        return "No loaded label files"
    label_word = "file" if active_carrier_count == 1 else "files"
    if has_bids_events:
        return f"BIDS events.tsv · {active_carrier_count} {label_word}"
    source_note = "includes added label source" if has_extra_sources else "loaded"
    return f"Loaded label files · {active_carrier_count} {label_word} · {source_note}"


def internal_label_placement_summary(
    *,
    selected_class_count: int,
    event_role_count: int,
) -> str:
    """Return placement text for labels stored inside EEG files."""
    if selected_class_count:
        event_word = "event" if selected_class_count == 1 else "events"
        return f"{selected_class_count} EEG {event_word} selected as class labels"
    if event_role_count:
        return "Event roles saved; confirm class labels before training"
    return "No usable labels selected yet"


def recipe_note(
    *,
    decision: str,
    source_mode: str,
    has_internal_choices: bool,
    active_carrier_count: int,
    needs_label_conversion: bool,
) -> str:
    """Return the short recipe note for the final import step."""
    if decision == "blocked":
        return "Resolve blocking items before import."
    if source_mode == "internal_events":
        return (
            "Internal label choices saved. Epoch setup comes later."
            if has_internal_choices
            else "No training labels selected."
        )
    if active_carrier_count <= 0:
        return "No training labels selected."
    if needs_label_conversion:
        return "Label file needs conversion before supervised training."
    return "Label matching saved. Epoch setup comes later."
