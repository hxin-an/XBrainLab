"""Fail-closed reliability checks for typed and serialized application state."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from XBrainLab.backend.application.state import ApplicationStateSnapshot

_SERIALIZED_STATE_REQUIRED_KEYS = frozenset(
    {
        "pipeline_stage",
        "raw",
        "preprocessed",
        "epoch",
        "dataset",
        "training",
        "evaluation",
        "visualization",
        "interpretation",
        "active_dataset",
        "active_training",
        "state_reliable",
        "training_liveness_reliable",
        "read_errors",
    }
)


def typed_application_state_reliable(state: Any) -> bool:
    """Accept only a complete typed snapshot without read failures."""
    return (
        isinstance(state, ApplicationStateSnapshot)
        and state.state_reliable is True
        and isinstance(state.read_errors, list)
        and not state.read_errors
    )


def serialized_application_state_reliable(state: Any) -> bool:
    """Accept only the complete serialized form of a reliable snapshot."""
    if not isinstance(state, Mapping):
        return False
    if not _SERIALIZED_STATE_REQUIRED_KEYS.issubset(state):
        return False
    read_errors = state.get("read_errors")
    return (
        state.get("state_reliable") is True
        and isinstance(read_errors, list)
        and not read_errors
    )


__all__ = [
    "serialized_application_state_reliable",
    "typed_application_state_reliable",
]
