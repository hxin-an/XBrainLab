"""Confirmation stale-context warning follows authoritative publication truth."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from XBrainLab.backend.training_state_contract import TrainingRunIdentity
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


@pytest.mark.parametrize(
    ("run_id", "status", "reliable", "changed"),
    [
        (1, "running", True, False),
        (2, "running", True, True),
        (1, "stop_requested", True, True),
        (1, "completed", True, True),
        (1, "running", False, True),
    ],
)
def test_stop_confirmation_warning_uses_reviewed_run(run_id, status, reliable, changed):
    request = AgentConfirmationRequest.for_action(
        command_name="stop_training",
        params={},
        action_label="Stop training",
        description="Stop the reviewed run.",
        destructive=False,
        publication_generation=4,
        expected_training_run=TrainingRunIdentity("trainer", 1),
    )
    state = {
        "state_reliable": reliable,
        "training_liveness_reliable": True,
        "training": {
            "is_running": True,
            "terminal_outcome": {
                "state": status,
                "run": {"trainer_id": "trainer", "run_id": run_id},
            },
        },
    }
    publication = SimpleNamespace(
        usable=True, generation=5, state=SimpleNamespace(to_dict=lambda: state)
    )
    assert (
        AgentPresentationService.confirmation_context_changed(request, publication)
        is changed
    )
