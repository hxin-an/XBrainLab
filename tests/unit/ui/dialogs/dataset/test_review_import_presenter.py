import pytest

from XBrainLab.ui.dialogs.dataset.review_import_presenter import (
    SubmissionFacts,
    SubmissionProjection,
    eeg_data_summary,
    internal_label_placement_summary,
    label_source_summary,
    metadata_summary,
    project_submission,
    recipe_note,
)


def _submission_facts(
    *,
    decision: str = "safe",
    resource_blocked: bool = False,
    has_unresolved_required_decisions: bool = False,
    has_remap_options: bool = False,
    has_complete_remap_choices: bool = False,
    event_values_ready_for_recheck: bool = False,
) -> SubmissionFacts:
    return SubmissionFacts(
        decision=decision,
        resource_blocked=resource_blocked,
        has_unresolved_required_decisions=has_unresolved_required_decisions,
        has_remap_options=has_remap_options,
        has_complete_remap_choices=has_complete_remap_choices,
        event_values_ready_for_recheck=event_values_ready_for_recheck,
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
    assert (
        recipe_note(
            decision="needs_confirmation",
            source_mode="label_files",
            has_internal_choices=False,
            active_carrier_count=1,
            needs_label_conversion=True,
        )
        == "Label file needs conversion before supervised training."
    )
