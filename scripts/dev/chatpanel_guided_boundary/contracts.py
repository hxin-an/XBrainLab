"""Injected runtime hooks for the Guided Workflow walkthrough driver."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GuidedBoundaryHooks:
    """Expensive UI/runtime operations kept outside deterministic state logic."""

    capture: Callable[[Any, Path], int]
    handle_setup_dialog: Callable[[Any], dict[str, Any] | None]
    assistant_surface_ready: Callable[[Any], tuple[bool, str]]
    collect_visible_messages: Callable[[Any], list[Any]]
    collect_executed_tools: Callable[[Any], list[dict[str, Any]]]
    collect_model_proposals: Callable[[list[dict[str, Any]], str], list[dict[str, Any]]]
    attach_tool_trace: Callable[[Any], None]
    detach_tool_trace: Callable[[], None]
    collect_tool_attempt_traces: Callable[[], list[dict[str, Any]]]
    publication_evidence: Callable[[Any], dict[str, Any]]
    runtime_evidence: Callable[[Mapping[str, object], Any], dict[str, object]]
    structured_value: Callable[[Any], Any]
    turn_metrics_evidence: Callable[[Any, int], dict[str, Any]]
    has_raw_debug_text: Callable[[list[str]], bool]
    has_runtime_error_text: Callable[[list[str]], bool]
    schedule: Callable[[int, Callable[[], None]], None]
    now: Callable[[], float]
