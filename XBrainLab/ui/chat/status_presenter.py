"""Pure product-language presentation for assistant workflow status."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssistantEmptyStatePresentation:
    """User-facing copy for one assistant workflow stage."""

    title: str
    intro: str
    stage_sentence: str
    next_text: str
    footer_text: str


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
        "Ask me to explain metrics, compare runs, or open a visualization.",
    ),
    "Workflow status unavailable": (
        "Workflow status unavailable",
        "Try the status check again before asking the assistant to change data.",
    ),
}


def build_assistant_empty_state(
    stage: str,
    display_commands: list[str] | None,
    blocked_reason: str | None = None,
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
    )


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
