"""Typed callback contract between the product script and walkthrough driver."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from PyQt6.QtWidgets import QWidget

from XBrainLab.llm.agent.runtime_state import AssistantRuntimeSnapshot

EventBucket = Literal[
    "confirmation_requests",
    "interaction_events",
    "workflow_handoffs",
    "application_results",
    "turn_terminals",
]


@dataclass(frozen=True)
class PipelineDriverHooks:
    """Injected product observations used by the harness driver."""

    capture_window: Callable[[Any, Path], int]
    approve_product_dialog: Callable[[QWidget], dict[str, Any] | None]
    assistant_surface_ready: Callable[[Any], tuple[bool, str]]
    collect_visible_messages: Callable[[Any], list[Any]]
    collect_executed_tools: Callable[[Any], list[dict[str, Any]]]
    collect_model_proposals: Callable[[list[dict[str, Any]], str], list[dict[str, Any]]]
    publication_evidence: Callable[[Any], dict[str, Any]]
    runtime_evidence: Callable[
        [Mapping[str, object], AssistantRuntimeSnapshot | Mapping[str, object] | None],
        dict[str, object],
    ]
    structured_value: Callable[[Any], Any]
    turn_metrics_evidence: Callable[[Any, int], dict[str, Any]]
    has_raw_debug_text: Callable[[list[str]], bool]
    has_runtime_error_text: Callable[[list[str]], bool]
    turn_has_expected_tool: Callable[[list[dict[str, Any]], str], bool]
    validate_payload: Callable[[dict[str, Any]], tuple[bool, str]]
    schedule: Callable[[int, Callable[[], None]], None]
    now: Callable[[], float]
