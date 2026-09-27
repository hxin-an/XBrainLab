"""Confirmation stale-context warning follows authoritative publication truth."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from XBrainLab.llm.agent.confirmation import AgentConfirmationRequest
from XBrainLab.ui.components.agent_presentation_service import AgentPresentationService


@pytest.mark.parametrize(
    ("request_generation", "generation", "usable", "reliable", "changed"),
    [
        (4, 4, True, True, False),
        (4, 5, True, True, True),
        (4, 5, False, True, False),
        (4, 5, True, False, False),
        (None, 5, True, True, False),
    ],
)
def test_confirmation_context_warning_uses_reliable_publication_generation(
    request_generation, generation, usable, reliable, changed
) -> None:
    request = AgentConfirmationRequest.for_action(
        command_name="start_training",
        params={},
        action_label="Start training",
        description="Run the reviewed training configuration.",
        destructive=False,
        publication_generation=request_generation,
    )
    publication = SimpleNamespace(
        usable=usable,
        generation=generation,
        state=SimpleNamespace(state_reliable=reliable),
    )

    actual_changed = AgentPresentationService.confirmation_context_changed(
        request, publication
    )

    assert actual_changed is changed
