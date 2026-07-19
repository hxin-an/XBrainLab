"""Typed public outcomes for asynchronous workflow-panel navigation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PanelPreparationFailure:
    """Terminal failure for one requested lazy-panel preparation."""

    panel_index: int
    panel_name: str
    message: str
