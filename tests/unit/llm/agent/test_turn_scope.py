"""Tests for the non-authoritative single-action scope resolver."""

import pytest

from XBrainLab.llm.agent.turn import AssistantTurnScope
from XBrainLab.llm.agent.turn_scope import (
    AssistantTurnScopeResolution,
    resolve_assistant_turn_scope,
)


@pytest.mark.parametrize(
    "text",
    (
        "Import and preprocess everything for me",
        "continue until training",
        "do not preprocess",
        "what is an epoch?",
        "",
    ),
)
def test_user_text_never_widens_host_autonomy(text: str) -> None:
    resolution = resolve_assistant_turn_scope(text)

    assert resolution.scope is AssistantTurnScope.SINGLE_ACTION
    assert resolution.terminal_command is None
    assert resolution.excluded_commands == ()


def test_resolution_rejects_legacy_guided_scope() -> None:
    with pytest.raises(ValueError, match="single-action"):
        AssistantTurnScopeResolution(AssistantTurnScope.GUIDED_WORKFLOW)
