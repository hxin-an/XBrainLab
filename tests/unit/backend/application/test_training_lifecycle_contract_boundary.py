"""Architecture guard for the neutral training lifecycle event contract."""

from pathlib import Path

from XBrainLab.backend.training_state_contract import (
    TrainingLifecycleEvent,
    TrainingOutcomeState,
    TrainingStateToken,
    TrainingTerminalOutcome,
)

ROOT = Path(__file__).resolve().parents[4]
APPLICATION_FILES = (
    "service.py",
    "application_publication_lifecycle.py",
    "training_publication_lifecycle.py",
    "post_training_saliency.py",
)


def test_training_lifecycle_event_is_owned_by_the_neutral_backend_contract() -> None:
    event = TrainingLifecycleEvent(
        token=TrainingStateToken(generation=1, stable=True),
        outcome=TrainingTerminalOutcome(state=TrainingOutcomeState.COMPLETED),
    )

    assert event.token.generation == 1
    for filename in APPLICATION_FILES:
        source = (ROOT / "XBrainLab" / "backend" / "application" / filename).read_text(
            encoding="utf-8"
        )
        assert "backend.controller.training_controller" not in source
