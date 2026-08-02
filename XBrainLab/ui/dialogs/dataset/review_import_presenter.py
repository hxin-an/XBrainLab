"""Pure presenter helpers for the Data Import review/import step."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SubmissionRecheckKind = Literal["remap", "event_values"]


@dataclass(frozen=True, slots=True)
class SubmissionFacts:
    """Current UI facts that affect whether a review may be submitted."""

    decision: str
    resource_blocked: bool
    has_unresolved_required_decisions: bool
    has_remap_options: bool
    has_complete_remap_choices: bool
    event_values_ready_for_recheck: bool


@dataclass(frozen=True, slots=True)
class SubmissionProjection:
    """Submission state consumed by every review/import UI surface."""

    can_submit_for_backend_review: bool
    confirmed_on_accept: bool
    recheck_kind: SubmissionRecheckKind | None


def project_submission(facts: SubmissionFacts) -> SubmissionProjection:
    """Project UI facts without claiming authority over backend apply."""
    recheck_kind: SubmissionRecheckKind | None = None
    if not facts.resource_blocked:
        if (
            facts.decision == "blocked"
            and facts.has_remap_options
            and facts.has_complete_remap_choices
        ):
            recheck_kind = "remap"
        elif (
            facts.decision == "blocked"
            and facts.event_values_ready_for_recheck
            and not facts.has_unresolved_required_decisions
        ):
            recheck_kind = "event_values"

    can_submit = bool(
        not facts.resource_blocked
        and (
            (
                facts.decision in {"safe", "needs_confirmation"}
                and not facts.has_unresolved_required_decisions
            )
            or recheck_kind is not None
        )
    )
    return SubmissionProjection(
        can_submit_for_backend_review=can_submit,
        confirmed_on_accept=can_submit,
        recheck_kind=recheck_kind,
    )


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
        return "EEG event choices saved; confirm training classes"
    return "No usable labels selected yet"


def recipe_note() -> str:
    """Describe the optional load-only recipe saved after a successful import."""
    return "Save the current data import and label mapping settings for reuse."
