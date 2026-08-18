"""Resolve the single-action transport scope for one user turn."""

from __future__ import annotations

from dataclasses import dataclass

from XBrainLab.backend.application import CommandName

from .turn import AssistantTurnScope


@dataclass(frozen=True, slots=True)
class AssistantTurnScopeResolution:
    """Immutable transport metadata; text never grants workflow autonomy."""

    scope: AssistantTurnScope
    terminal_command: str | None = None
    excluded_commands: tuple[CommandName, ...] = ()

    def __post_init__(self) -> None:
        if self.scope is not AssistantTurnScope.SINGLE_ACTION:
            raise ValueError("Assistant turns must use single-action scope.")
        if self.terminal_command is not None:
            raise ValueError("Single-action turns cannot define a workflow endpoint.")
        if self.excluded_commands:
            raise ValueError("Text-derived command exclusions are not supported.")


_SINGLE = AssistantTurnScopeResolution(AssistantTurnScope.SINGLE_ACTION)


def resolve_assistant_turn_scope(text: str) -> AssistantTurnScopeResolution:
    """Return one fixed scope without classifying or narrowing user text."""
    del text
    return _SINGLE
