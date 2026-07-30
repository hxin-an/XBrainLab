"""Pure product-language presentation for assistant workflow status."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssistantPromptSuggestion:
    """One stage-aware prompt offered without starting a turn automatically."""

    title: str
    subtitle: str
    prompt: str
    required_command: str | None = None


@dataclass(frozen=True)
class AssistantEmptyStatePresentation:
    """User-facing copy for one assistant workflow stage."""

    title: str
    intro: str
    stage_sentence: str
    next_text: str
    footer_text: str
    suggestions: tuple[AssistantPromptSuggestion, ...]


_EMPTY_STATE_COPY: dict[str, tuple[str, str]] = {
    "No data loaded": (
        "Start with your EEG data",
        "Ask me to find EEG files, explain supported formats, or begin an import.",
    ),
    "Ready for preprocessing": (
        "Prepare your EEG data",
        "Ask what preprocessing is appropriate or what must be reviewed first.",
    ),
    "Ready for epoching": (
        "Define the analysis windows",
        "Ask me to explain event anchors or prepare the epoch settings.",
    ),
    "Ready to build dataset": (
        "Build the training dataset",
        "Ask me to review the epoch data or prepare the dataset split.",
    ),
    "Dataset ready": (
        "Set up training",
        "Ask me to choose the next training setup step or explain what is missing.",
    ),
    "Ready to train": (
        "Ready to train",
        "Ask me to review the settings or start the confirmed training run.",
    ),
    "Training running": (
        "Training is running",
        "Ask for progress or stop the current training run.",
    ),
    "Results available": (
        "Explore your results",
        "Ask me to explain metrics, review available analyses, or recommend "
        "what to inspect next.",
    ),
    "Workflow status unavailable": (
        "Workflow status unavailable",
        "Try the status check again before asking the assistant to change data.",
    ),
}

_GENERIC_SUGGESTIONS = (
    AssistantPromptSuggestion(
        "Check workflow status",
        "See what is ready and what needs attention.",
        "Check the current workflow status",
    ),
    AssistantPromptSuggestion(
        "Explain current settings",
        "Review the settings used by the current workflow.",
        "Explain the current settings",
    ),
    AssistantPromptSuggestion(
        "Suggest the next step",
        "Get one recommendation based on the current state.",
        "Suggest the next step",
    ),
)

_STAGE_SUGGESTIONS: dict[str, tuple[AssistantPromptSuggestion, ...]] = {
    "No data loaded": (
        AssistantPromptSuggestion(
            "Import EEG data",
            "Prepare a request to start the guided import flow.",
            "Help me import EEG data",
            required_command="scan_source",
        ),
        AssistantPromptSuggestion(
            "Check supported formats",
            "See which EEG and label formats can be reviewed.",
            "Explain which EEG data formats XBrainLab supports",
        ),
        AssistantPromptSuggestion(
            "Explain the import workflow",
            "Understand data, metadata, labels, and review.",
            "Explain the EEG data import workflow",
        ),
    ),
    "Ready for preprocessing": (
        AssistantPromptSuggestion(
            "Review preprocessing",
            "Check what the loaded signal may need.",
            "Explain the preprocessing options for the loaded EEG data",
        ),
        AssistantPromptSuggestion(
            "Explain current data",
            "Summarize channels, sampling, and available events.",
            "Explain the currently loaded EEG data",
        ),
        AssistantPromptSuggestion(
            "Suggest the next step",
            "Get one recommendation from the current state.",
            "Explain how to choose the next preprocessing step",
        ),
    ),
    "Ready for epoching": (
        AssistantPromptSuggestion(
            "Explain epoch anchors",
            "Review which events can define analysis windows.",
            "Explain the available epoch anchors",
        ),
        AssistantPromptSuggestion(
            "Review epoch settings",
            "Check the current window and baseline choices.",
            "Explain the current epoch settings",
        ),
        AssistantPromptSuggestion(
            "Open epoch setup",
            "Continue in the existing Time Epoching dialog.",
            "Help me configure epoching",
            required_command="create_epoch",
        ),
    ),
    "Ready to build dataset": (
        AssistantPromptSuggestion(
            "Review epoch data",
            "Check the available epochs before creating a split.",
            "Explain whether the current epochs are ready for dataset creation",
        ),
        AssistantPromptSuggestion(
            "Explain data splitting",
            "Understand training, validation, and testing choices.",
            "Explain the available data splitting options",
        ),
        AssistantPromptSuggestion(
            "Prepare dataset setup",
            "Get one recommendation for the next dataset step.",
            "Explain how to prepare the next dataset setup",
        ),
    ),
    "Dataset ready": (
        AssistantPromptSuggestion(
            "Review training readiness",
            "Check split, model, and training requirements.",
            "Explain whether the current dataset meets training requirements",
        ),
        AssistantPromptSuggestion(
            "Explain the data split",
            "Understand how training, validation, and test data are separated.",
            "Explain the current data split",
        ),
        AssistantPromptSuggestion(
            "Review training settings",
            "Inspect the current model and run configuration.",
            "Explain the current training configuration",
        ),
    ),
    "Ready to train": (
        AssistantPromptSuggestion(
            "Review training settings",
            "Check the model, batch size, and run configuration.",
            "Explain the current training configuration",
        ),
        AssistantPromptSuggestion(
            "Check resource safety",
            "Review the current RAM and VRAM estimate.",
            "Explain the current training resource estimate",
        ),
        AssistantPromptSuggestion(
            "Start a training run",
            "Review the final confirmation before training starts.",
            "Start training with the current reviewed settings",
            required_command="train",
        ),
    ),
    "Training running": (
        AssistantPromptSuggestion(
            "Check training progress",
            "Summarize the current run without changing it.",
            "Explain the current training progress",
        ),
        AssistantPromptSuggestion(
            "Explain live metrics",
            "Understand the latest loss and accuracy values.",
            "Explain the current training metrics",
        ),
        AssistantPromptSuggestion(
            "Stop training",
            "Review the impact before stopping the run.",
            "Stop the current training run",
            required_command="stop_training",
        ),
    ),
    "Results available": (
        AssistantPromptSuggestion(
            "Explain these results",
            "Summarize the current evaluation metrics.",
            "Explain the current evaluation results",
        ),
        AssistantPromptSuggestion(
            "Review available analyses",
            "Check which result views are ready for the current run.",
            "Explain which analyses are available for the current results",
        ),
        AssistantPromptSuggestion(
            "Suggest the next analysis",
            "Get one recommendation grounded in the current results.",
            "Explain how to choose the next analysis for the current results",
        ),
    ),
}


def build_assistant_empty_state(
    stage: str,
    display_commands: list[str] | None,
    blocked_reason: str | None = None,
    *,
    available_command_names: list[str] | tuple[str, ...] | None = None,
) -> AssistantEmptyStatePresentation:
    """Build one consistent empty-state and footer presentation."""
    title, intro = _EMPTY_STATE_COPY.get(
        stage,
        (
            "Continue your EEG workflow",
            "Ask what is ready, what is blocked, or where to continue.",
        ),
    )
    stage_sentence = (
        "No EEG files are open yet."
        if stage == "No data loaded"
        else f"Current workflow stage: {stage}."
    )
    if display_commands:
        next_text = " · ".join(display_commands[:3])
    elif blocked_reason:
        next_text = blocked_reason
    elif stage == "No data loaded":
        next_text = "Scan a data source to begin"
    else:
        next_text = "Ask what is ready"

    return AssistantEmptyStatePresentation(
        title=title,
        intro=intro,
        stage_sentence=stage_sentence,
        next_text=next_text,
        footer_text=assistant_footer_hint(stage, display_commands, blocked_reason),
        suggestions=_available_suggestions(stage, available_command_names),
    )


def _available_suggestions(
    stage: str,
    available_command_names: list[str] | tuple[str, ...] | None,
) -> tuple[AssistantPromptSuggestion, ...]:
    """Keep executable prompts aligned with backend-published capabilities."""
    suggestions = _STAGE_SUGGESTIONS.get(stage, _GENERIC_SUGGESTIONS)
    if available_command_names is None:
        return suggestions

    available = {
        str(command_name).strip().lower()
        for command_name in available_command_names
        if str(command_name).strip()
    }
    selected = [
        suggestion
        for suggestion in suggestions
        if suggestion.required_command is None
        or suggestion.required_command in available
    ]
    known_prompts = {suggestion.prompt for suggestion in selected}
    for suggestion in _GENERIC_SUGGESTIONS:
        if len(selected) >= 3:
            break
        if suggestion.prompt not in known_prompts:
            selected.append(suggestion)
            known_prompts.add(suggestion.prompt)
    return tuple(selected[:3])


def assistant_footer_hint(
    stage: str,
    display_commands: list[str] | None,
    blocked_reason: str | None = None,
) -> str:
    """Return a stage-only status-bar hint without duplicating panel actions."""
    if blocked_reason:
        return f"{stage} · Action required"
    if stage == "No data loaded":
        return "No EEG data open"
    return stage
