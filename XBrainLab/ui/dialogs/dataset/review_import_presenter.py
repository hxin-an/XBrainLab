"""Pure presenter helpers for the Data Import review/import step."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

SubmissionRecheckKind = Literal["remap", "event_values", "interpretation_choices"]
ValidationDecisionKind = Literal["safe", "needs_confirmation", "blocked"]
ValidationActionSeverity = Literal[
    "blocked",
    "needs_confirmation",
    "warning",
    "limited",
]
ValidationActionTarget = Literal[
    "Choose EEG Data",
    "Load Labels",
    "Review Metadata",
    "Match Labels",
    "Review and Import",
]

_VALIDATION_DECISIONS = frozenset({"safe", "needs_confirmation", "blocked"})
_ACTION_SEVERITIES = frozenset({"blocked", "needs_confirmation", "warning", "limited"})
_ACTION_TARGETS = frozenset(
    {
        "Choose EEG Data",
        "Load Labels",
        "Review Metadata",
        "Match Labels",
        "Review and Import",
    }
)


@dataclass(frozen=True, slots=True)
class ValidationActionItem:
    """One backend-owned review action rendered by the import UI."""

    target_step: ValidationActionTarget
    issue: str
    impact: str
    next_action: str
    severity: ValidationActionSeverity

    def to_review_row(self) -> tuple[str, str, str, str]:
        return self.target_step, self.issue, self.impact, self.next_action


@dataclass(frozen=True, slots=True)
class ValidationReviewContract:
    """Validated backend decision consumed by the review/import product path."""

    decision: ValidationDecisionKind | None
    action_items: tuple[ValidationActionItem, ...]
    contract_errors: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.contract_errors and self.decision is not None

    @property
    def action_targets(self) -> frozenset[str]:
        return frozenset(item.target_step for item in self.action_items)

    @property
    def blocking_action_targets(self) -> frozenset[str]:
        return frozenset(
            item.target_step for item in self.action_items if item.severity == "blocked"
        )

    @property
    def actionable_items(self) -> tuple[ValidationActionItem, ...]:
        return self.items_with_severity("blocked", "needs_confirmation")

    def requires_action_at(self, target_step: str) -> bool:
        return any(item.target_step == target_step for item in self.actionable_items)

    def items_with_severity(
        self,
        *severities: ValidationActionSeverity,
    ) -> tuple[ValidationActionItem, ...]:
        admitted = frozenset(severities)
        return tuple(item for item in self.action_items if item.severity in admitted)


def adapt_serialized_validation_decision(
    payload: Mapping[str, object],
) -> ValidationReviewContract:
    """Validate the serialized backend ``ValidationDecision`` without fallback."""
    errors: list[str] = []
    raw_decision = payload.get("decision")
    decision_text = str(raw_decision or "").strip().lower()
    decision: ValidationDecisionKind | None = None
    if decision_text in _VALIDATION_DECISIONS:
        decision = cast(ValidationDecisionKind, decision_text)
    else:
        errors.append("validation decision is missing or unsupported")

    action_items: list[ValidationActionItem] = []
    raw_action_items = payload.get("action_items")
    if raw_action_items is None:
        if decision in {"needs_confirmation", "blocked"}:
            errors.append(f"{decision} decision is missing typed action_items")
    elif not isinstance(raw_action_items, list):
        errors.append("validation action_items must be a list")
    else:
        for index, raw_item in enumerate(raw_action_items):
            item = _adapt_validation_action_item(raw_item, index=index, errors=errors)
            if item is not None:
                action_items.append(item)

    if decision == "blocked" and not any(
        item.severity == "blocked" for item in action_items
    ):
        errors.append("blocked decision requires a blocked action item")
    if decision == "needs_confirmation" and not any(
        item.severity == "needs_confirmation" for item in action_items
    ):
        errors.append(
            "needs_confirmation decision requires a needs_confirmation action item"
        )
    if decision == "needs_confirmation" and any(
        item.severity == "blocked" for item in action_items
    ):
        errors.append("needs_confirmation decision contains a blocked action item")
    if decision == "safe" and any(
        item.severity in {"blocked", "needs_confirmation"} for item in action_items
    ):
        errors.append("safe decision contains an actionable blocker")

    return ValidationReviewContract(
        decision=decision,
        action_items=tuple(action_items),
        contract_errors=tuple(dict.fromkeys(errors)),
    )


def _adapt_validation_action_item(
    value: object,
    *,
    index: int,
    errors: list[str],
) -> ValidationActionItem | None:
    if not isinstance(value, Mapping):
        errors.append(f"validation action_items[{index}] must be an object")
        return None

    fields = {
        field: raw.strip() if isinstance(raw, str) else ""
        for field in ("target_step", "issue", "impact", "next_action", "severity")
        if (raw := value.get(field)) is not None
    }
    missing = [
        field
        for field in ("target_step", "issue", "impact", "next_action", "severity")
        if not fields.get(field)
    ]
    if missing:
        errors.append(
            f"validation action_items[{index}] is missing: {', '.join(missing)}"
        )
        return None

    target_step = fields["target_step"]
    severity = fields["severity"].lower()
    if target_step not in _ACTION_TARGETS:
        errors.append(f"validation action_items[{index}] has unsupported target_step")
        return None
    if severity not in _ACTION_SEVERITIES:
        errors.append(f"validation action_items[{index}] has unsupported severity")
        return None
    return ValidationActionItem(
        target_step=cast(ValidationActionTarget, target_step),
        issue=fields["issue"],
        impact=fields["impact"],
        next_action=fields["next_action"],
        severity=cast(ValidationActionSeverity, severity),
    )


@dataclass(frozen=True, slots=True)
class SubmissionFacts:
    """Current UI facts that affect whether a review may be submitted."""

    validation: ValidationReviewContract
    resource_blocked: bool
    has_unresolved_required_decisions: bool
    has_remap_options: bool
    has_complete_remap_choices: bool
    event_values_ready_for_recheck: bool
    interpretation_choices_ready_for_recheck: bool


@dataclass(frozen=True, slots=True)
class SubmissionProjection:
    """Submission state consumed by every review/import UI surface."""

    can_submit_for_backend_review: bool
    confirmed_on_accept: bool
    recheck_kind: SubmissionRecheckKind | None


def project_submission(facts: SubmissionFacts) -> SubmissionProjection:
    """Project UI facts without claiming authority over backend apply."""
    if not facts.validation.is_valid:
        return SubmissionProjection(
            can_submit_for_backend_review=False,
            confirmed_on_accept=False,
            recheck_kind=None,
        )

    decision = facts.validation.decision
    recheck_kind: SubmissionRecheckKind | None = None
    if not facts.resource_blocked:
        if (
            decision == "blocked"
            and facts.has_remap_options
            and facts.has_complete_remap_choices
        ):
            recheck_kind = "remap"
        elif (
            decision == "blocked"
            and facts.event_values_ready_for_recheck
            and not facts.has_unresolved_required_decisions
        ):
            recheck_kind = "event_values"
        elif (
            decision == "blocked"
            and facts.interpretation_choices_ready_for_recheck
            and not facts.has_unresolved_required_decisions
        ):
            recheck_kind = "interpretation_choices"

    can_submit = bool(
        not facts.resource_blocked
        and (
            (
                decision in {"safe", "needs_confirmation"}
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
