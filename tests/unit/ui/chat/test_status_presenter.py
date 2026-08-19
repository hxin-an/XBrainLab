"""Pure product-language tests for assistant workflow status."""

from XBrainLab.ui.chat.status_presenter import assistant_footer_hint


def test_no_data_footer_does_not_duplicate_panel_action() -> None:
    assert assistant_footer_hint("No data loaded", ["Scan data source"]) == (
        "No EEG data open"
    )


def test_blocked_footer_reports_action_required_without_reason_details() -> None:
    assert (
        assistant_footer_hint(
            "Dataset ready",
            [],
            "Choose a model before training.",
        )
        == "Dataset ready · Action required"
    )


def test_ready_footer_uses_backend_stage() -> None:
    assert assistant_footer_hint("Results available", ["Review results"]) == (
        "Results available"
    )
