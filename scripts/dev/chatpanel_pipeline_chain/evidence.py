"""Stable turn and terminal evidence assembly for the pipeline walkthrough."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.dev.chatpanel_pipeline_chain.contracts import PipelineDriverHooks
from scripts.dev.chatpanel_pipeline_chain.state import (
    PipelineTurnContext,
    PipelineWalkthroughState,
)
from XBrainLab.llm.agent.runtime_state import AssistantRuntimeSnapshot


@dataclass(frozen=True)
class CompletedTurnEvidence:
    """One completed turn plus values needed for deterministic validation."""

    payload: dict[str, Any]
    new_tools: list[dict[str, Any]]
    proposals: list[dict[str, Any]]
    expected_tool: str


@dataclass(frozen=True)
class PipelineTurnEvidenceBuilder:
    """Build one turn's evidence without deciding workflow progression."""

    state: PipelineWalkthroughState
    service: Any
    hooks: PipelineDriverHooks

    def build(
        self,
        *,
        index: int,
        prompt: str,
        context: PipelineTurnContext,
        assistant_text: str,
        controller: Any,
        screenshot_path: Path,
    ) -> CompletedTurnEvidence:
        executed_tools = self.hooks.collect_executed_tools(controller.metrics)
        new_tools = executed_tools[context.before_tools :]
        expected_tool = self.state.expected_tools[index]
        after_publication = self.hooks.publication_evidence(self.service)
        proposals = self.hooks.collect_model_proposals(controller.history, prompt)
        payload = {
            "index": index + 1,
            "prompt": prompt,
            "expected_tool": expected_tool,
            "assistant_text": assistant_text,
            "new_tools": [dict(tool) for tool in new_tools],
            "tool_proposals": proposals,
            "publication_before": context.publication_before,
            "publication_after": after_publication,
            "publication_generation_delta": generation_delta(
                context.publication_before,
                after_publication,
            ),
            "metrics": self.hooks.turn_metrics_evidence(
                controller.metrics,
                context.before_metric_turns,
            ),
            "confirmation_requests": self.state.event_slice(
                "confirmation_requests", context.event_counts
            ),
            "interaction_events": self.state.event_slice(
                "interaction_events", context.event_counts
            ),
            "workflow_handoffs": self.state.event_slice(
                "workflow_handoffs", context.event_counts
            ),
            "application_results": self.state.event_slice(
                "application_results", context.event_counts
            ),
            "turn_terminals": self.state.event_slice(
                "turn_terminals", context.event_counts
            ),
            "elapsed_seconds": round(
                self.hooks.now() - context.started_at,
                3,
            ),
            "screenshot": str(screenshot_path),
        }
        return CompletedTurnEvidence(
            payload=payload,
            new_tools=new_tools,
            proposals=proposals,
            expected_tool=expected_tool,
        )


@dataclass(frozen=True)
class PipelineEvidenceAssembler:
    """Build the stable JSON artifact contract from typed run state."""

    state: PipelineWalkthroughState
    prompts: list[str]
    initial_runtime: Mapping[str, object]
    runtime_evidence: Callable[
        [Mapping[str, object], AssistantRuntimeSnapshot | Mapping[str, object] | None],
        dict[str, object],
    ]
    structured_value: Callable[[Any], Any]

    def build(self) -> dict[str, Any]:
        payload = {
            "status": self.state.status,
            "failure_reason": self.state.failure_reason,
            "exception": self.state.exception,
            "source_path": self.state.source_path,
            "prompt_style": self.state.prompt_style,
            "prompts": self.prompts,
            "expected_tools": self.state.expected_tools,
            "runtime": self.runtime_evidence(
                self.initial_runtime,
                self.state.runtime_snapshot,
            ),
            "hf_offline": {
                "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE"),
                "TRANSFORMERS_OFFLINE": os.environ.get("TRANSFORMERS_OFFLINE"),
            },
            "screenshots": {
                "ready": self.state.ready_screenshot,
                "terminal": self.state.terminal_screenshot,
                "failure": self.state.failure_screenshot,
            },
            "turns": self.state.turns,
            "model_generations": self.state.model_generations,
            "model_generation_request_ids": self.state.model_generation_request_ids,
            "visible_messages": self.state.visible_messages,
            "executed_tools": self.state.executed_tools,
            "setup_dialogs": self.state.setup_dialogs,
            "confirmation_dialogs": self.state.confirmation_dialogs,
            "confirmation_requests": self.state.confirmation_requests,
            "interaction_events": self.state.interaction_events,
            "workflow_handoffs": self.state.workflow_handoffs,
            "application_results": self.state.application_results,
            "turn_terminals": self.state.turn_terminals,
            "controller_history": self.state.controller_history,
            "final_state": self.state.final_state,
            "final_publication": self.state.final_publication,
            "runtime_snapshot": self.state.runtime_snapshot,
            "ui_state": {
                "send_button_text": self.state.send_button_text,
                "send_button_enabled": self.state.send_button_enabled,
                "input_enabled": self.state.input_enabled,
                "chat_processing": self.state.chat_processing,
                "controller_processing": self.state.controller_processing,
            },
            "shutdown": self.state.shutdown,
            "elapsed_seconds": self.state.elapsed_seconds,
        }
        serialized = self.structured_value(payload)
        if not isinstance(serialized, dict):
            raise TypeError("Pipeline evidence serializer must return a mapping.")
        return serialized


def generation_delta(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> int | None:
    before_generation = before.get("generation")
    after_generation = after.get("generation")
    if isinstance(before_generation, bool) or isinstance(after_generation, bool):
        return None
    if not isinstance(before_generation, int) or not isinstance(after_generation, int):
        return None
    return after_generation - before_generation
