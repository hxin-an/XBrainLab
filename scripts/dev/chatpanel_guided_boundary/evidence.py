"""Stable JSON and Markdown evidence for the adaptive-workflow walkthrough."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_screenshot_artifacts,
    collect_source_identity,
)
from scripts.dev.chatpanel_guided_boundary.state import GuidedBoundaryState
from scripts.dev.chatpanel_guided_boundary.validation import EXPECTED_AUTO_CHAIN

SCHEMA_VERSION = 5
WALKTHROUGH_NAME = "adaptive_workflow_ui_handoff_boundary"
CLAIM_BOUNDARY = (
    "This is deterministic offscreen/local-runtime product evidence. Offscreen "
    "evidence is not human Windows desktop acceptance."
)


@dataclass(frozen=True)
class GuidedBoundaryEvidenceAssembler:
    """Serialize one runtime-owned walkthrough state without inventing evidence."""

    state: GuidedBoundaryState
    initial_runtime: Mapping[str, object]
    runtime_evidence: Callable[[Mapping[str, object], Any], dict[str, object]]
    structured_value: Callable[[Any], Any]

    def build(self) -> dict[str, Any]:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "walkthrough": WALKTHROUGH_NAME,
            "status": self.state.status,
            "failure_reason": self.state.failure_reason,
            "exception": self.state.exception,
            "source_path": self.state.source_path,
            "model_id": self.state.model_id,
            "prompts": list(self.state.prompts),
            "expected_auto_chain": list(EXPECTED_AUTO_CHAIN),
            "claim_boundary": CLAIM_BOUNDARY,
            "source_identity": collect_source_identity(),
            "runtime": self.runtime_evidence(
                self.initial_runtime,
                self.state.runtime_snapshot,
            ),
            "hf_offline": {
                "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE"),
                "TRANSFORMERS_OFFLINE": os.environ.get("TRANSFORMERS_OFFLINE"),
            },
            "scope_resolution": self.state.scope_resolution,
            "screenshots": self.state.screenshots,
            "screenshot_artifacts": collect_screenshot_artifacts(
                self.state.screenshots
            ),
            "initial_publication": self.state.initial_publication,
            "command_observations": self.state.command_observations,
            "first_turn": self.state.first_turn,
            "boundary": self.state.boundary,
            "workflow_handoff": self.state.workflow_handoff,
            "wizard": self.state.wizard,
            "post_cancel": self.state.post_cancel,
            "visible_messages": self.state.visible_messages,
            "executed_tools": self.state.executed_tools,
            "setup_dialogs": self.state.setup_dialogs,
            "workflow_handoff_requests": self.state.workflow_handoff_requests,
            "confirmation_requests": self.state.confirmation_requests,
            "interaction_events": self.state.interaction_events,
            "application_results": self.state.application_results,
            "turn_terminals": self.state.turn_terminals,
            "runtime_snapshot": self.state.runtime_snapshot,
            "ui_state": self.state.ui_state,
            "transcript_clean": self.state.transcript_clean,
            "shutdown": self.state.shutdown,
            "phase_history": self.state.phase_history,
            "elapsed_seconds": self.state.elapsed_seconds,
        }
        serialized = self.structured_value(payload)
        if not isinstance(serialized, dict):
            raise TypeError(
                "Guided boundary evidence serializer must return a mapping."
            )
        return serialized


def render_guided_boundary_markdown(payload: Mapping[str, Any]) -> str:
    """Render a compact human-readable summary from the stable JSON contract."""
    runtime = _mapping(payload.get("runtime"))
    screenshots = _mapping(payload.get("screenshots"))
    scope = _mapping(payload.get("scope_resolution"))
    boundary = _mapping(payload.get("boundary"))
    boundary_publication = _mapping(boundary.get("publication"))
    handoff = _mapping(payload.get("workflow_handoff"))
    handoff_request = _mapping(handoff.get("request"))
    wizard = _mapping(payload.get("wizard"))
    post_cancel = _mapping(payload.get("post_cancel"))
    post_publication = _mapping(post_cancel.get("publication"))
    source_identity = _mapping(payload.get("source_identity"))
    screenshot_artifacts = _mapping(payload.get("screenshot_artifacts"))
    lines = [
        "# ChatPanel Local Adaptive Workflow Boundary Walkthrough",
        "",
        f"- status: `{payload.get('status', 'unknown')}`",
        f"- generated at (UTC): `{payload.get('generated_at_utc', '')}`",
        f"- failure reason: {payload.get('failure_reason') or 'none'}",
        f"- source path: `{payload.get('source_path', '')}`",
        f"- source commit: `{source_identity.get('commit_sha', 'unavailable')}`",
        f"- source digest: `{source_identity.get('source_digest', 'unavailable')}`",
        f"- dirty source: `{source_identity.get('dirty', False)}`",
        f"- requested model: `{runtime.get('requested_model_id', '')}`",
        f"- loaded model: `{runtime.get('loaded_model_id', '')}`",
        f"- runtime classification: `{runtime.get('classification', 'unknown')}`",
        f"- runtime phase: `{runtime.get('phase', 'unknown')}`",
        f"- fallback used: `{runtime.get('fallback_used', False)}`",
        f"- turn scope source: `{scope.get('source', '')}`",
        f"- resolved turn scope: `{scope.get('scope', '')}`",
        f"- terminal command: `{scope.get('terminal_command')}`",
        f"- legacy mode selector present: "
        f"`{scope.get('legacy_selector_present', True)}`",
        f"- expected auto-chain: `{', '.join(payload.get('expected_auto_chain', []))}`",
        f"- boundary generation: `{boundary_publication.get('generation')}`",
        f"- workflow handoff request: `{handoff_request.get('request_id', '')}`",
        f"- workflow decision fields: "
        f"`{', '.join(handoff_request.get('decision_fields', []))}`",
        f"- wizard target step: `{wizard.get('current_step_title', '')}`",
        f"- post-cancel generation: `{post_publication.get('generation')}`",
        f"- shutdown: `{_mapping(payload.get('shutdown')).get('status', 'unknown')}`",
        f"- elapsed seconds: `{payload.get('elapsed_seconds', 0.0)}`",
        "",
        "## Screenshots",
        "",
    ]
    for name in (
        "ready",
        "auto_chain_complete",
        "workflow_dialog_open",
        "post_cancel",
        "failure",
    ):
        artifact = _mapping(screenshot_artifacts.get(name))
        dimensions = artifact.get("dimensions") or []
        size_text = (
            f"{dimensions[0]}x{dimensions[1]}"
            if isinstance(dimensions, list) and len(dimensions) == 2
            else "unavailable"
        )
        lines.append(
            f"- {name.replace('_', ' ')}: `{screenshots.get(name, '')}` "
            f"(`{size_text}`, sha256 `{artifact.get('sha256', '')}`)"
        )
    lines.extend(
        [
            "",
            "## Command Publications",
            "",
        ]
    )
    for item in payload.get("command_observations", []):
        observation = _mapping(item)
        publication = _mapping(observation.get("publication"))
        lines.append(
            f"- `{observation.get('command_name', '')}`: "
            f"generation `{publication.get('generation')}`, "
            f"usable `{publication.get('usable', False)}`"
        )
    lines.extend(
        [
            "",
            "## Workflow UI Handoff Boundary",
            "",
            f"- typed handoff observed: `{handoff.get('observed', False)}`",
            f"- dialog opened: `{wizard.get('dialog_opened', False)}`",
            f"- dialog class: `{wizard.get('dialog_class', '')}`",
            f"- dialog title: `{wizard.get('dialog_title', '')}`",
            f"- target step: `{wizard.get('current_step_title', '')}`",
            f"- cancel clicked: `{wizard.get('cancel_clicked', False)}`",
            f"- state unchanged: `{post_cancel.get('state') == boundary.get('state')}`",
            f"- apply completion observed: "
            f"`{post_cancel.get('apply_completion_observed', False)}`",
            "",
            "## Claim Boundary",
            "",
            str(payload.get("claim_boundary") or CLAIM_BOUNDARY),
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def write_guided_boundary_artifacts(
    output_dir: Any,
    payload: Mapping[str, Any],
    *,
    json_name: str,
    markdown_name: str,
) -> None:
    """Write stable machine-readable and human-readable evidence files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / json_name).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / markdown_name).write_text(
        render_guided_boundary_markdown(payload),
        encoding="utf-8",
    )


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
