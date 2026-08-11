"""Authoritative-current-state contracts for assistant setting cards."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

from XBrainLab.backend.application.state import TrainingStateSnapshot
from XBrainLab.llm.agent.confirmation import AgentConfirmationRequest
from XBrainLab.ui.components.agent_manager import AgentManager


class _ManagerProbe:
    _display_ui_value = staticmethod(AgentManager._display_ui_value)

    def __init__(self, publication: object) -> None:
        self.application_service = SimpleNamespace(
            get_view_publication=MagicMock(return_value=publication)
        )


def _request() -> AgentConfirmationRequest:
    return AgentConfirmationRequest.for_action(
        command_name="configure_training",
        params={
            "model_name": "Deep4Net",
            "epoch": 5,
            "batch_size": 16,
            "learning_rate": 0.0005,
            "repeat": 1,
            "device": "cpu",
            "optimizer": "adam",
            "evaluation_option": "last_epoch",
            "save_checkpoints_every": 0,
        },
        action_label="Apply training settings",
        description="Use the reviewed training configuration.",
        destructive=False,
        publication_generation=4,
    )


def _publication(*, reliable: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        usable=True,
        generation=4,
        state=SimpleNamespace(
            state_reliable=reliable,
            training=TrainingStateSnapshot(
                has_model=True,
                model_name="EEGNet",
                has_training_option=True,
                training_option={
                    "epoch": 1,
                    "batch_size": 4,
                    "learning_rate": 0.001,
                    "repeat": 1,
                    "device": "cpu",
                    "optimizer": "Adam",
                    "evaluation_option": "Last Epoch",
                    "checkpoint_epoch": 0,
                },
            ),
        ),
    )


def test_complete_current_values_require_every_proposed_setting() -> None:
    probe = cast(AgentManager, _ManagerProbe(_publication()))

    values, changed = AgentManager._confirmation_current_values(probe, _request())

    assert values == {
        "Model name": "EEGNet",
        "Epoch": "1",
        "Batch size": "4",
        "Learning rate": "0.001",
        "Repeat": "1",
        "Device": "cpu",
        "Optimizer": "adam",
        "Evaluation option": "last_epoch",
        "Save checkpoints every": "0",
    }
    assert changed is False


def test_partial_or_unreliable_current_values_are_explicitly_unverified() -> None:
    partial = _publication()
    partial.state.training.training_option.pop("learning_rate")

    partial_values, partial_changed = AgentManager._confirmation_current_values(
        cast(AgentManager, _ManagerProbe(partial)),
        _request(),
    )
    unreliable_values, unreliable_changed = AgentManager._confirmation_current_values(
        cast(AgentManager, _ManagerProbe(_publication(reliable=False))),
        _request(),
    )

    assert partial_values is None
    assert partial_changed is False
    assert unreliable_values is None
    assert unreliable_changed is False
