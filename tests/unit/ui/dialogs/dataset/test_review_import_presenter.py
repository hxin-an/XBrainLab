import pytest

from XBrainLab.backend.application.data_interpretation_review import ValidationDecision
from XBrainLab.ui.dialogs.dataset.review_import_presenter import (
    SubmissionFacts,
    SubmissionProjection,
    adapt_serialized_validation_decision,
    eeg_data_summary,
    internal_label_placement_summary,
    label_source_summary,
    metadata_summary,
    project_submission,
    recipe_note,
)
from XBrainLab.ui.dialogs.dataset.review_presenter import (
    is_optional_metadata_review_row,
    metadata_required_fields_complete,
    primary_action_item_rows,
)


def _submission_facts(
    *,
    decision: str = "safe",
    action_items: list[dict[str, str]] | None = None,
    include_action_items: bool = True,
    resource_blocked: bool = False,
    has_unresolved_required_decisions: bool = False,
    has_remap_options: bool = False,
    has_complete_remap_choices: bool = False,
    event_values_ready_for_recheck: bool = False,
    interpretation_choices_ready_for_recheck: bool = False,
) -> SubmissionFacts:
    if action_items is None:
        action_items = {
            "safe": [],
            "needs_confirmation": [
                {
                    "target_step": "Match Labels",
                    "issue": "Confirm label placement.",
                    "impact": "Labels may align with the wrong EEG events.",
                    "next_action": "Review the label placement.",
                    "severity": "needs_confirmation",
                }
            ],
            "blocked": [
                {
                    "target_step": "Match Labels",
                    "issue": "Label placement is unresolved.",
                    "impact": "The import cannot be applied.",
                    "next_action": "Resolve the label placement.",
                    "severity": "blocked",
                }
            ],
        }.get(decision, [])
    payload: dict[str, object] = {"decision": decision}
    if include_action_items:
        payload["action_items"] = action_items
    return SubmissionFacts(
        validation=adapt_serialized_validation_decision(payload),
        resource_blocked=resource_blocked,
        has_unresolved_required_decisions=has_unresolved_required_decisions,
        has_remap_options=has_remap_options,
        has_complete_remap_choices=has_complete_remap_choices,
        event_values_ready_for_recheck=event_values_ready_for_recheck,
        interpretation_choices_ready_for_recheck=(
            interpretation_choices_ready_for_recheck
        ),
    )


def test_typed_validation_decision_projects_authoritative_action_targets():
    decision = ValidationDecision(
        candidate_id="candidate-1",
        decision="needs_confirmation",
        action_items=[
            {
                "target_step": "Review Metadata",
                "issue": "Confirm subject metadata.",
                "impact": "The recording may be grouped under the wrong subject.",
                "next_action": "Review the subject value.",
                "severity": "needs_confirmation",
            }
        ],
    )

    contract = adapt_serialized_validation_decision(decision.to_dict())

    assert contract.is_valid is True
    assert contract.decision == "needs_confirmation"
    assert contract.contract_errors == ()
    assert contract.action_items[0].issue == "Confirm subject metadata."
    assert contract.action_targets == frozenset({"Review Metadata"})
    assert contract.blocking_action_targets == frozenset()


@pytest.mark.parametrize("decision", ["needs_confirmation", "blocked"])
def test_actionable_decision_without_typed_action_items_fails_closed(decision: str):
    facts = _submission_facts(
        decision=decision,
        include_action_items=False,
        interpretation_choices_ready_for_recheck=True,
    )

    assert facts.validation.is_valid is False
    assert facts.validation.contract_errors
    assert project_submission(facts) == SubmissionProjection(
        can_submit_for_backend_review=False,
        confirmed_on_accept=False,
        recheck_kind=None,
    )


def test_needs_confirmation_decision_with_blocked_action_fails_closed():
    contract = adapt_serialized_validation_decision(
        {
            "decision": "needs_confirmation",
            "action_items": [
                {
                    "target_step": "Load Labels",
                    "issue": "Label source is missing.",
                    "impact": "The import cannot be applied.",
                    "next_action": "Load labels.",
                    "severity": "blocked",
                },
                {
                    "target_step": "Match Labels",
                    "issue": "Confirm label placement.",
                    "impact": "The placement needs review.",
                    "next_action": "Review label placement.",
                    "severity": "needs_confirmation",
                },
            ],
        }
    )

    assert contract.is_valid is False
    assert "needs_confirmation decision contains a blocked action item" in (
        contract.contract_errors
    )


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        (
            _submission_facts(),
            SubmissionProjection(
                can_submit_for_backend_review=True,
                confirmed_on_accept=True,
                recheck_kind=None,
            ),
        ),
        (
            _submission_facts(has_unresolved_required_decisions=True),
            SubmissionProjection(
                can_submit_for_backend_review=False,
                confirmed_on_accept=False,
                recheck_kind=None,
            ),
        ),
        (
            _submission_facts(
                decision="blocked",
                has_unresolved_required_decisions=True,
                has_remap_options=True,
                has_complete_remap_choices=True,
            ),
            SubmissionProjection(
                can_submit_for_backend_review=True,
                confirmed_on_accept=True,
                recheck_kind="remap",
            ),
        ),
        (
            _submission_facts(
                decision="blocked",
                has_remap_options=True,
                has_complete_remap_choices=False,
            ),
            SubmissionProjection(
                can_submit_for_backend_review=False,
                confirmed_on_accept=False,
                recheck_kind=None,
            ),
        ),
        (
            _submission_facts(
                decision="blocked",
                event_values_ready_for_recheck=True,
            ),
            SubmissionProjection(
                can_submit_for_backend_review=True,
                confirmed_on_accept=True,
                recheck_kind="event_values",
            ),
        ),
        (
            _submission_facts(
                decision="blocked",
                event_values_ready_for_recheck=True,
                has_unresolved_required_decisions=True,
            ),
            SubmissionProjection(
                can_submit_for_backend_review=False,
                confirmed_on_accept=False,
                recheck_kind=None,
            ),
        ),
        (
            _submission_facts(
                decision="blocked",
                interpretation_choices_ready_for_recheck=True,
            ),
            SubmissionProjection(
                can_submit_for_backend_review=True,
                confirmed_on_accept=True,
                recheck_kind="interpretation_choices",
            ),
        ),
    ],
)
def test_project_submission_owns_submission_and_confirmation_truth(
    facts: SubmissionFacts,
    expected: SubmissionProjection,
):
    assert project_submission(facts) == expected


@pytest.mark.parametrize(
    "facts",
    [
        _submission_facts(resource_blocked=True),
        _submission_facts(
            decision="blocked",
            resource_blocked=True,
            has_remap_options=True,
            has_complete_remap_choices=True,
        ),
        _submission_facts(
            decision="blocked",
            resource_blocked=True,
            event_values_ready_for_recheck=True,
        ),
    ],
)
def test_project_submission_never_submits_a_resource_blocker(
    facts: SubmissionFacts,
):
    assert project_submission(facts) == SubmissionProjection(
        can_submit_for_backend_review=False,
        confirmed_on_accept=False,
        recheck_kind=None,
    )


def test_eeg_data_summary_keeps_scope_and_preview_separate():
    assert (
        eeg_data_summary(
            selected_names=["A01T.gdf", "A02T.gdf"],
            file_count=2,
            preview_text="A01T.gdf, A02T.gdf",
        )
        == "2 EEG files · A01T.gdf, A02T.gdf"
    )


def test_metadata_summary_hides_optional_session_run_noise():
    assert (
        metadata_summary(
            row_count=3,
            complete_count=3,
            missing_fields=set(),
            is_bids_source=True,
            fallback_summary="3/3 rows reviewed",
        )
        == "BIDS entities reviewed · 3 files"
    )


def test_review_metadata_requires_subject_but_not_task_session_or_run():
    assert metadata_required_fields_complete(
        row_count=2,
        missing_fields={"task": 2, "session": 2, "run": 2},
    )
    assert not metadata_required_fields_complete(
        row_count=2,
        missing_fields={"subject": 1, "task": 2},
    )
    assert is_optional_metadata_review_row(
        (
            "Review Metadata",
            "Task metadata is missing",
            "Optional task metadata is unavailable.",
            "Review metadata if needed.",
        )
    )


def test_primary_review_rows_exclude_nonblocking_limited_items():
    rows = primary_action_item_rows(
        [
            {"severity": "limited", "issue": "Labels skipped for now."},
            {"severity": "blocked", "issue": "Label alignment is unresolved."},
        ]
    )

    assert [row[1] for row in rows] == ["Label alignment is unresolved."]
    assert (
        metadata_summary(
            row_count=0,
            complete_count=0,
            missing_fields={"subject"},
            is_bids_source=False,
            fallback_summary="unused",
        )
        == "No metadata rows detected."
    )


def test_label_source_summary_distinguishes_internal_and_loaded_sources():
    assert (
        label_source_summary(
            source_mode="internal_events",
            internal_candidate_count=4,
            active_carrier_count=0,
            has_bids_events=False,
            has_extra_sources=False,
        )
        == "Labels inside EEG files · 4 events"
    )
    assert (
        label_source_summary(
            source_mode="label_files",
            internal_candidate_count=0,
            active_carrier_count=2,
            has_bids_events=False,
            has_extra_sources=True,
        )
        == "Loaded label files · 2 files · includes added label source"
    )


def test_internal_label_placement_summary_and_recipe_note():
    assert (
        internal_label_placement_summary(selected_class_count=4, event_role_count=0)
        == "4 EEG events selected as class labels"
    )
    assert recipe_note() == (
        "Save the current data import and label mapping settings for reuse."
    )
