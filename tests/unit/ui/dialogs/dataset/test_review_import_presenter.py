from XBrainLab.ui.dialogs.dataset.review_import_presenter import (
    eeg_data_summary,
    internal_label_placement_summary,
    label_source_summary,
    metadata_summary,
    recipe_note,
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
            is_bids_like=True,
            fallback_summary="3/3 rows reviewed",
        )
        == "BIDS entities reviewed · 3 files"
    )
    assert (
        metadata_summary(
            row_count=0,
            complete_count=0,
            missing_fields={"subject"},
            is_bids_like=False,
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
