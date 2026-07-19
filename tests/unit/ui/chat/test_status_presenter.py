"""Pure product-language tests for assistant workflow status."""

from XBrainLab.ui.chat.status_presenter import (
    assistant_footer_hint,
    build_assistant_empty_state,
)


def test_results_stage_uses_result_specific_empty_state() -> None:
    presentation = build_assistant_empty_state(
        "Results available",
        ["Review results"],
    )

    assert presentation.title == "Explore your results"
    assert presentation.stage_sentence == "Current workflow stage: Results available."
    assert presentation.next_text == "Review results"
    assert presentation.footer_text == "Results available"


def test_blocked_state_uses_one_reason_in_empty_state_and_footer() -> None:
    presentation = build_assistant_empty_state(
        "Dataset ready",
        [],
        "Choose a model before training.",
    )

    assert presentation.next_text == "Choose a model before training."
    assert presentation.footer_text == "Dataset ready · Action required"


def test_no_data_footer_does_not_duplicate_panel_action() -> None:
    assert assistant_footer_hint("No data loaded", ["Scan data source"]) == (
        "No EEG data open"
    )
