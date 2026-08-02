"""Pure product-language tests for assistant workflow status."""

from XBrainLab.llm.agent.intent import command_for_intent, infer_user_intent
from XBrainLab.ui.chat.status_presenter import (
    _STAGE_SUGGESTIONS,
    AssistantPromptSuggestion,
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


def test_no_data_stage_offers_three_contextual_prompts() -> None:
    presentation = build_assistant_empty_state(
        "No data loaded",
        ["Scan data source"],
        available_command_names=["scan_source"],
    )

    assert presentation.title == "Start with your EEG data"
    assert len(presentation.suggestions) == 3
    assert all(
        isinstance(suggestion, AssistantPromptSuggestion)
        for suggestion in presentation.suggestions
    )
    assert [suggestion.title for suggestion in presentation.suggestions] == [
        "Import EEG data",
        "Check supported formats",
        "Explain the import workflow",
    ]
    assert presentation.suggestions[0].prompt == "Help me import EEG data"
    assert all(
        "guided" not in f"{suggestion.title} {suggestion.subtitle}".lower()
        for suggestion in presentation.suggestions
    )


def test_no_data_stage_does_not_offer_import_when_backend_disables_scan() -> None:
    presentation = build_assistant_empty_state(
        "No data loaded",
        [],
        available_command_names=[],
    )

    assert "Import EEG data" not in {
        suggestion.title for suggestion in presentation.suggestions
    }
    assert len(presentation.suggestions) == 3


def test_ready_to_train_only_offers_start_when_backend_enables_train() -> None:
    blocked = build_assistant_empty_state(
        "Ready to train",
        [],
        available_command_names=[],
    )
    enabled = build_assistant_empty_state(
        "Ready to train",
        ["Start training"],
        available_command_names=["train"],
    )

    assert "Start a training run" not in {
        suggestion.title for suggestion in blocked.suggestions
    }
    assert "Start a training run" in {
        suggestion.title for suggestion in enabled.suggestions
    }


def test_stage_suggestions_never_hide_mutating_intent_behind_review_copy() -> None:
    for suggestions in _STAGE_SUGGESTIONS.values():
        for suggestion in suggestions:
            intent = infer_user_intent(suggestion.prompt)
            command = command_for_intent(intent)
            if command is None:
                continue
            assert suggestion.required_command == command.value, (
                suggestion.title,
                suggestion.prompt,
                intent,
            )


def test_results_stage_prompts_focus_on_results_not_training_setup() -> None:
    presentation = build_assistant_empty_state(
        "Results available",
        ["Evaluate", "Visualize"],
    )

    assert [suggestion.title for suggestion in presentation.suggestions] == [
        "Explain these results",
        "Review available analyses",
        "Suggest the next analysis",
    ]
    assert all(
        "training configuration" not in suggestion.prompt.lower()
        for suggestion in presentation.suggestions
    )
