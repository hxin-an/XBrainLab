#!/usr/bin/env python3
"""Capture a true local-model ChatPanel import-to-dataset tool chain."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget

from scripts.dev.capture_chatpanel_local_tool_chain_walkthrough import (
    _capture_current_window,
    _clear_saved_main_window_geometry,
    _force_offline_hf_runtime,
    _load_capture_config,
    _runtime_summary,
    _set_baseline_window_geometry,
    tool_chain_status,
    write_synthetic_raw_fif,
)
from scripts.dev.capture_chatpanel_local_walkthrough import (
    collect_executed_tools,
    collect_visible_messages,
    has_raw_debug_text,
)
from scripts.dev.capture_chatpanel_local_workflow_walkthrough import (
    _has_runtime_error_text,
)
from scripts.dev.chatpanel_pipeline_chain import (
    PipelineChainDriver,
    PipelineDriverHooks,
    PipelineWalkthroughState,
    generation_delta,
)
from scripts.dev.inspect_local_assistant_runtime import classify_runtime
from XBrainLab.config import AppConfig
from XBrainLab.llm.agent.parser import CommandParser, ToolEnvelopeStatus
from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
    AssistantRuntimeSnapshot,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "build" / "dev-artifacts" / "chatpanel-local-pipeline-chain"
READY_SCREENSHOT = "chatpanel-pipeline-chain-ready.png"
TERMINAL_SCREENSHOT = "chatpanel-pipeline-chain-terminal.png"
FAILURE_SCREENSHOT = "chatpanel-pipeline-chain-failure.png"
JSON_ARTIFACT = "chatpanel-local-pipeline-chain-walkthrough.json"
MD_ARTIFACT = "chatpanel-local-pipeline-chain-walkthrough.md"
POLL_INTERVAL_MS = 250
SHUTDOWN_GRACE_SECONDS = 20.0
EXPECTED_TOOLS = [
    "scan_source",
    "preview_interpretation",
    "validate_interpretation",
    "apply_interpretation",
    "apply_standard_preprocess",
    "epoch_data",
    "generate_dataset",
]


@dataclass(frozen=True)
class SettingsFileSnapshot:
    """Exact on-disk settings state restored after a walkthrough process."""

    path: Path
    content: bytes | None
    mode: int | None

    @classmethod
    def capture(cls, path: Path) -> SettingsFileSnapshot:
        target = Path(path)
        if not target.exists():
            return cls(path=target, content=None, mode=None)
        return cls(
            path=target,
            content=target.read_bytes(),
            mode=target.stat().st_mode,
        )

    def restore(self) -> None:
        if self.content is None:
            self.path.unlink(missing_ok=True)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(self.content)
        if self.mode is not None:
            self.path.chmod(self.mode)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for screenshots and transcript artifacts.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=760,
        help="Maximum time for the full pipeline-chain walkthrough.",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Optional approved local model id to prefer for this process.",
    )
    parser.add_argument(
        "--prompt-style",
        choices=("natural", "contract"),
        default="natural",
        help="Use product-language prompts or explicit contract probes.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    settings_path = Path(AppConfig.BASE_DIR) / "settings.json"
    settings_snapshot = SettingsFileSnapshot.capture(settings_path)
    runtime_summary: dict[str, object] = {
        "classification": "unknown",
        "model_id": args.model,
        "cache_usage": "unknown",
    }
    source_path: Path | None = None
    return_code = 1
    try:
        _force_offline_hf_runtime()
        config = _load_capture_config(args.model)
        # The UI first-run dialog reads the persisted config. Persist a transient
        # model override through the real config API, then restore exact bytes.
        if args.model:
            config.save_to_file(str(settings_path))
        runtime = classify_runtime(config)
        runtime_summary = _runtime_summary(runtime)
        if runtime["classification"] not in {"gpu-ready", "cpu-fallback"}:
            payload = _blocked_payload(args, runtime)
            return_code = 2
        else:
            source_path = write_synthetic_raw_fif()
            app = QApplication(sys.argv)
            app.setStyle("Fusion")
            if args.model:
                app.setProperty("model_override", args.model)
            payload = run_pipeline_chain(
                app,
                output_dir,
                source_path,
                args.timeout_seconds,
                initial_runtime=runtime_summary,
                prompt_style=args.prompt_style,
            )
            return_code = 0 if payload["status"] == "passed" else 1
    except Exception as exc:
        payload = _failed_payload(
            args,
            runtime_summary,
            source_path,
            f"Walkthrough harness failed: {exc}",
            exception=traceback.format_exc(),
        )
        return_code = 1
    finally:
        settings_snapshot.restore()

    _write_artifacts(output_dir, payload)
    print(f"Wrote {output_dir / JSON_ARTIFACT}")
    print(f"Wrote {output_dir / MD_ARTIFACT}")
    return return_code


def build_prompts(source_path: Path, *, style: str = "natural") -> list[str]:
    """Return product-language or explicit contract prompts for the chain."""
    if style == "natural":
        return [
            (
                f"Find the EEG recording at {source_path} and prepare it for "
                "review. Tell me briefly what you found."
            ),
            (
                "Show me how XBrainLab understands the selected recording "
                "before it is imported."
            ),
            "Check whether the current interpretation is ready to apply.",
            "Import the reviewed recording now.",
            (
                "Prepare the recording with a 4 to 40 Hz filter and z-score "
                "normalization."
            ),
            ("Create epochs for the left and right events from 0.0 to 0.25 seconds."),
            "Build an individual training dataset with a trial-based split.",
        ]
    if style != "contract":
        raise ValueError(f"Unsupported prompt style: {style}")
    return [
        (
            "Scan the source with scan_source exactly once, using source_path "
            f"{source_path}. Reply with one short result sentence."
        ),
        (
            "Preview the latest Data Interpretation candidate. Reply with one "
            "short result sentence."
        ),
        (
            "Validate the latest Data Interpretation candidate. Reply with one "
            "short result sentence and stop."
        ),
        (
            "Apply the current Data Interpretation candidate now with "
            "apply_interpretation exactly once. Approve the product confirmation "
            "when it appears. Reply with one short result sentence."
        ),
        (
            "Apply standard preprocessing. Use apply_standard_preprocess with "
            "l_freq 4, h_freq 40, and normalize_method z-score. Reply with one "
            "short result sentence."
        ),
        (
            "Create epochs for events left and right from 0.0 to 0.25 seconds. Reply with "
            "one short result sentence."
        ),
        (
            "Generate an individual training dataset using a trial split. Reply "
            "with one short result sentence and stop before training."
        ),
    ]


def approve_product_dialog(widget: QWidget) -> dict[str, Any] | None:
    """Approve only the two real product dialogs used by this walkthrough."""
    title = " ".join(widget.windowTitle().split())
    normalized_title = title.casefold()
    if isinstance(widget, QMessageBox) and normalized_title in {
        "confirm action",
        "confirm destructive action",
    }:
        approve_button = next(
            (
                button
                for button in widget.buttons()
                if widget.buttonRole(button) is QMessageBox.ButtonRole.AcceptRole
                and button.isEnabled()
            ),
            None,
        )
        event = {
            "kind": "confirmation",
            "title": title,
            "text": widget.text(),
            "informative_text": widget.informativeText(),
            "detailed_text": widget.detailedText(),
            "action": approve_button.text() if approve_button is not None else "",
            "approved": approve_button is not None,
        }
        if approve_button is not None:
            approve_button.click()
        return event

    if isinstance(widget, QDialog) and normalized_title == "local assistant runtime":
        candidates = (
            getattr(widget, "use_cache_btn", None),
            getattr(widget, "enable_btn", None),
        )
        button = next(
            (
                candidate
                for candidate in candidates
                if candidate is not None
                and callable(getattr(candidate, "isEnabled", None))
                and candidate.isEnabled()
            ),
            None,
        )
        event = {
            "kind": "first_run",
            "title": title,
            "action": button.text() if button is not None else "",
            "approved": button is not None,
        }
        if button is not None:
            button.click()
        return event
    return None


def assistant_surface_ready(manager: Any) -> tuple[bool, str]:
    """Return readiness only when runtime ownership and composer agree."""
    panel = getattr(manager, "chat_panel", None)
    dock = getattr(manager, "chat_dock", None)
    if panel is None or dock is None or not dock.isVisible():
        return False, "assistant dock is not visible"

    lifecycle = getattr(manager, "assistant_runtime", None)
    snapshot = getattr(lifecycle, "current", None)
    if lifecycle is None or snapshot is None:
        return False, "assistant runtime is unavailable"
    if (
        getattr(snapshot, "phase", None) is not AssistantRuntimePhase.READY
        or not bool(getattr(snapshot, "initialized", False))
        or not bool(getattr(lifecycle, "accepts_commands", False))
    ):
        phase = getattr(getattr(snapshot, "phase", None), "value", "unknown")
        return False, f"assistant runtime is {phase}"

    controller = getattr(manager, "agent_controller", None)
    if controller is None:
        return False, "assistant controller is unavailable"
    if bool(getattr(controller, "is_processing", False)) or bool(
        getattr(getattr(manager, "chat_controller", None), "is_processing", False)
    ):
        return False, "assistant turn is still processing"
    if bool(getattr(lifecycle, "turn_in_flight", False)):
        return False, "assistant turn has not reached a terminal state"
    if not panel.input_field.isEnabled():
        return False, "assistant composer is disabled"
    if panel.send_btn.text() != "Send":
        return False, "assistant send action is not ready"
    return True, "ready"


def collect_model_proposals(
    history: list[dict[str, Any]],
    prompt: str,
) -> list[dict[str, Any]]:
    """Collect complete model-proposed params after the exact user prompt."""
    prompt_index = -1
    for index, message in enumerate(history):
        if message.get("role") == "user" and message.get("content") == prompt:
            prompt_index = index
    if prompt_index < 0:
        return []

    proposals: list[dict[str, Any]] = []
    for message in history[prompt_index + 1 :]:
        if message.get("role") != "assistant":
            continue
        content = str(message.get("content") or "")
        envelope = CommandParser.parse_product(content)
        if envelope.status is not ToolEnvelopeStatus.VALID:
            continue
        for tool_name, parameters in envelope.commands:
            proposals.append(
                {
                    "tool_name": tool_name,
                    "parameters": _structured_value(parameters),
                }
            )
    return proposals


def publication_evidence(service: Any) -> dict[str, Any]:
    """Capture one atomic backend publication without mutating workflow state."""
    try:
        publication = service.get_view_publication()
        state_payload = _structured_value(publication.state.to_dict())
        return {
            "available": True,
            "generation": int(publication.generation),
            "usable": bool(publication.usable),
            "verified": bool(publication.verified),
            "stale": bool(publication.stale),
            "refresh_error": publication.refresh_error,
            "pipeline_stage": str(
                state_payload.get("pipeline_stage")
                if isinstance(state_payload, dict)
                else getattr(publication.state, "pipeline_stage", "")
            ),
            "state": state_payload,
        }
    except Exception as exc:
        return {
            "available": False,
            "generation": None,
            "usable": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def runtime_evidence(
    initial_runtime: Mapping[str, object],
    snapshot: AssistantRuntimeSnapshot | Mapping[str, object] | None,
) -> dict[str, object]:
    """Merge preflight information with authoritative loaded-runtime truth."""
    initial = dict(initial_runtime)
    if isinstance(snapshot, AssistantRuntimeSnapshot):
        current = snapshot.to_dict()
    elif isinstance(snapshot, Mapping):
        current = dict(snapshot)
    else:
        current = {}

    requested = str(current.get("requested_model_id") or initial.get("model_id") or "")
    phase = str(current.get("phase") or "unknown")
    loaded = str(current.get("model_id") or "") if phase == "ready" else ""
    outcome = str(current.get("selection_outcome") or "")
    initial.update(
        {
            "requested_model_id": requested,
            "loaded_model_id": loaded,
            "model_id": loaded or str(initial.get("model_id") or ""),
            "phase": phase,
            "initialized": bool(current.get("initialized", False)),
            "selection_outcome": outcome,
            "selection_detail": str(current.get("selection_detail") or ""),
            "fallback_used": outcome == "fallback",
        }
    )
    return initial


def _structured_value(value: Any) -> Any:
    """Convert typed runtime evidence into JSON-safe values."""
    if isinstance(value, Enum):
        return _structured_value(value.value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return _structured_value(asdict(value))
    to_payload = getattr(value, "to_payload", None)
    if callable(to_payload):
        return _structured_value(to_payload())
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _structured_value(to_dict())
    if isinstance(value, Mapping):
        return {str(key): _structured_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_structured_value(item) for item in value]
    return repr(value)


def _turn_metrics_evidence(metrics: Any, before_count: int) -> dict[str, Any]:
    completed = list(getattr(metrics, "_completed_turns", []) or [])[before_count:]
    turns = []
    for turn in completed:
        executions = [
            {
                "name": str(getattr(item, "name", "")),
                "success": bool(getattr(item, "success", False)),
                "duration_ms": round(float(getattr(item, "duration_ms", 0.0)), 3),
                "error": getattr(item, "error", None),
            }
            for item in (getattr(turn, "tool_executions", []) or [])
        ]
        turns.append(
            {
                "turn_id": str(getattr(turn, "turn_id", "")),
                "conversation_id": str(getattr(turn, "conversation_id", "")),
                "duration_ms": round(float(getattr(turn, "duration_ms", 0.0)), 3),
                "llm_calls": int(getattr(turn, "llm_calls", 0)),
                "input_chars": int(getattr(turn, "input_chars", 0)),
                "output_chars": int(getattr(turn, "output_chars", 0)),
                "tool_executions": executions,
            }
        )
    return {
        "completed_turn_count": len(turns),
        "turn_ids": [turn["turn_id"] for turn in turns],
        "duration_ms": round(sum(turn["duration_ms"] for turn in turns), 3),
        "llm_calls": sum(turn["llm_calls"] for turn in turns),
        "input_chars": sum(turn["input_chars"] for turn in turns),
        "output_chars": sum(turn["output_chars"] for turn in turns),
        "tool_executions": [
            execution for turn in turns for execution in turn["tool_executions"]
        ],
        "turns": turns,
    }


def run_pipeline_chain(
    app: QApplication,
    output_dir: Path,
    source_path: Path,
    timeout_seconds: int,
    *,
    initial_runtime: Mapping[str, object],
    prompt_style: str = "natural",
) -> dict[str, Any]:
    """Run import -> apply -> preprocess -> epoch -> dataset through ChatPanel."""
    from XBrainLab.backend.application import get_application_service
    from XBrainLab.backend.study import Study
    from XBrainLab.ui.main_window import MainWindow

    prompts = build_prompts(source_path, style=prompt_style)
    _clear_saved_main_window_geometry()
    study = Study()
    service = get_application_service(study)
    window = MainWindow(study)
    _set_baseline_window_geometry(window)
    window.show()

    state = PipelineWalkthroughState(
        source_path=str(source_path),
        prompt_style=prompt_style,
        expected_tools=list(EXPECTED_TOOLS),
        started_at=time.monotonic(),
    )
    hooks = PipelineDriverHooks(
        capture_window=_capture_current_window,
        approve_product_dialog=approve_product_dialog,
        assistant_surface_ready=assistant_surface_ready,
        collect_visible_messages=collect_visible_messages,
        collect_executed_tools=collect_executed_tools,
        collect_model_proposals=collect_model_proposals,
        publication_evidence=publication_evidence,
        runtime_evidence=runtime_evidence,
        structured_value=_structured_value,
        turn_metrics_evidence=_turn_metrics_evidence,
        has_raw_debug_text=has_raw_debug_text,
        has_runtime_error_text=_has_runtime_error_text,
        turn_has_expected_tool=_turn_has_expected_tool,
        validate_payload=validate_pipeline_payload,
        schedule=lambda delay, callback: QTimer.singleShot(delay, callback),
        now=time.monotonic,
    )
    return PipelineChainDriver(
        app=app,
        window=window,
        service=service,
        output_dir=output_dir,
        prompts=prompts,
        timeout_seconds=timeout_seconds,
        state=state,
        hooks=hooks,
        poll_interval_ms=POLL_INTERVAL_MS,
        shutdown_grace_seconds=SHUTDOWN_GRACE_SECONDS,
        ready_screenshot_name=READY_SCREENSHOT,
        terminal_screenshot_name=TERMINAL_SCREENSHOT,
        failure_screenshot_name=FAILURE_SCREENSHOT,
    ).run(initial_runtime)


def validate_pipeline_payload(state: dict[str, Any]) -> tuple[bool, str]:
    """Validate the tool sequence and final backend state."""
    ok, reason = tool_chain_status(state["executed_tools"], state["expected_tools"])
    if not ok:
        return False, reason
    expected_tools = list(state.get("expected_tools") or [])
    turns = list(state.get("turns") or [])
    if len(turns) != len(expected_tools):
        return (
            False,
            f"Expected {len(expected_tools)} evidenced turns, observed {len(turns)}.",
        )
    for index, (turn, expected_tool) in enumerate(
        zip(turns, expected_tools, strict=True),
        start=1,
    ):
        if turn.get("expected_tool") != expected_tool:
            return False, f"Turn {index} expected-tool evidence is inconsistent."
        proposals = turn.get("tool_proposals")
        if not isinstance(proposals, list) or not any(
            proposal.get("tool_name") == expected_tool
            and isinstance(proposal.get("parameters"), dict)
            for proposal in proposals
            if isinstance(proposal, dict)
        ):
            return False, f"Turn {index} lacks full proposal parameters."

        before = turn.get("publication_before")
        after = turn.get("publication_after")
        if not isinstance(before, dict) or not isinstance(after, dict):
            return False, f"Turn {index} lacks complete publication evidence."
        if not before.get("available") or not after.get("available"):
            return False, f"Turn {index} publication evidence is unavailable."
        delta = generation_delta(before, after)
        if delta is None or delta <= 0:
            return False, f"Turn {index} did not publish a new state generation."
        if turn.get("publication_generation_delta") != delta:
            return False, f"Turn {index} publication generation delta is inconsistent."

        metrics = turn.get("metrics")
        if not isinstance(metrics, dict):
            return False, f"Turn {index} lacks tool metrics evidence."
        metric_tools = metrics.get("tool_executions")
        if (
            int(metrics.get("completed_turn_count") or 0) < 1
            or int(metrics.get("llm_calls") or 0) < 1
            or not isinstance(metric_tools, list)
            or not any(
                item.get("name") == expected_tool and bool(item.get("success"))
                for item in metric_tools
                if isinstance(item, dict)
            )
        ):
            return False, f"Turn {index} lacks successful tool metrics evidence."

        typed_event_keys = (
            "confirmation_requests",
            "interaction_events",
            "workflow_handoffs",
            "application_results",
            "turn_terminals",
        )
        if any(not isinstance(turn.get(key), list) for key in typed_event_keys):
            return False, f"Turn {index} lacks typed handoff evidence fields."
        if not turn["application_results"]:
            return False, f"Turn {index} lacks typed application result evidence."
        if not turn["turn_terminals"]:
            return False, f"Turn {index} lacks typed terminal evidence."
        if not str(turn.get("screenshot") or ""):
            return False, f"Turn {index} lacks a screenshot artifact."

    model_generations = state.get("model_generations")
    request_ids = state.get("model_generation_request_ids")
    if (
        not isinstance(model_generations, list)
        or not isinstance(request_ids, list)
        or len(model_generations) != len(request_ids)
        or len(model_generations) < len(turns)
        or any(not isinstance(text, str) or not text for text in model_generations)
        or any(
            type(request_id) is not int or request_id <= 0 for request_id in request_ids
        )
        or request_ids != sorted(set(request_ids))
    ):
        return False, "Model generation evidence lacks active request-ID correlation."

    final_state = state.get("final_state") or {}
    raw = _section(final_state, "raw")
    epoch = _section(final_state, "epoch")
    dataset = _section(final_state, "dataset")
    interpretation = _section(final_state, "interpretation")
    if not raw.get("loaded"):
        return False, "Final state did not load interpreted raw data."
    if not interpretation.get("has_applied_interpretation"):
        return False, "Final state does not have an applied interpretation."
    if not epoch.get("available"):
        return False, "Final state does not have epoch data."
    if not dataset.get("available"):
        return False, "Final state does not have a generated dataset."
    if not state.get("confirmation_dialogs"):
        return False, "Apply confirmation dialog was not observed."
    return True, ""


def render_markdown(payload: dict[str, Any]) -> str:
    """Render a compact import-to-dataset walkthrough summary."""
    runtime = payload.get("runtime") or {}
    offline = payload.get("hf_offline") or {}
    screenshots = payload.get("screenshots") or {}
    terminal_screenshot = str(
        screenshots.get("terminal") or payload.get("terminal_screenshot") or ""
    )
    failure_screenshot = str(screenshots.get("failure") or "")
    lines = [
        "# ChatPanel Local Pipeline-Chain Walkthrough",
        "",
        f"- status: `{payload.get('status', 'unknown')}`",
        f"- failure reason: {payload.get('failure_reason') or 'none'}",
        f"- source path: `{payload.get('source_path', '')}`",
        f"- runtime classification: `{runtime.get('classification', 'unknown')}`",
        f"- requested model: `{runtime.get('requested_model_id', '')}`",
        f"- loaded model: `{runtime.get('loaded_model_id', '')}`",
        f"- runtime phase: `{runtime.get('phase', 'unknown')}`",
        f"- model selection: `{runtime.get('selection_outcome', '')}`",
        f"- cache usage: `{runtime.get('cache_usage', 'unknown')}`",
        f"- HF offline: `{offline.get('HF_HUB_OFFLINE')}`",
        f"- Transformers offline: `{offline.get('TRANSFORMERS_OFFLINE')}`",
        f"- ready screenshot: `{screenshots.get('ready', '')}`",
        f"- terminal screenshot: `{terminal_screenshot}`",
        f"- failure screenshot: `{failure_screenshot}`",
        f"- expected tools: `{', '.join(payload.get('expected_tools', []))}`",
        f"- confirmation dialogs observed: `{len(payload.get('confirmation_dialogs', []))}`",
        f"- elapsed seconds: `{payload.get('elapsed_seconds', 0.0)}`",
        "",
        "## Turns",
        "",
    ]
    for turn in payload.get("turns", []):
        tool_names = ", ".join(
            str(tool.get("name", "")) for tool in turn.get("new_tools", [])
        )
        before = turn.get("publication_before") or {}
        after = turn.get("publication_after") or {}
        proposals = json.dumps(
            turn.get("tool_proposals", []),
            ensure_ascii=False,
            sort_keys=True,
        )
        metrics = turn.get("metrics") or {}
        lines.extend(
            [
                f"### Turn {turn['index']}",
                "",
                f"- prompt: {turn['prompt']}",
                f"- expected tool: `{turn['expected_tool']}`",
                f"- assistant: {turn['assistant_text']}",
                f"- new tools: `{tool_names}`",
                f"- publication: `{before.get('generation')} -> {after.get('generation')}`",
                f"- pipeline stage: `{before.get('pipeline_stage', '')} -> "
                f"{after.get('pipeline_stage', '')}`",
                f"- model proposals: `{proposals}`",
                f"- LLM calls: `{metrics.get('llm_calls', 0)}`",
                f"- tool metric count: `{len(metrics.get('tool_executions', []))}`",
                f"- application results: `{len(turn.get('application_results', []))}`",
                f"- turn terminals: `{len(turn.get('turn_terminals', []))}`",
                f"- screenshot: `{turn['screenshot']}`",
                "",
            ],
        )
    lines.extend(["## Executed Tools", ""])
    tools = payload.get("executed_tools", [])
    if tools:
        for tool in tools:
            status = "ok" if tool.get("success") else "failed"
            lines.append(
                f"- `{tool.get('name', '')}`: `{status}` "
                f"({tool.get('duration_ms', 0)} ms)"
            )
    else:
        lines.append("- none")

    final_state = payload.get("final_state") or {}
    final_publication = payload.get("final_publication") or {}
    interpretation = _section(final_state, "interpretation")
    epoch = _section(final_state, "epoch")
    dataset = _section(final_state, "dataset")
    lines.extend(
        [
            "",
            "## Final State",
            "",
            f"- publication generation: `{final_publication.get('generation')}`",
            f"- pipeline stage: `{final_publication.get('pipeline_stage', '')}`",
            f"- applied interpretation: `{interpretation.get('has_applied_interpretation')}`",
            f"- validation decision: `{interpretation.get('validation_decision')}`",
            f"- epoch available: `{epoch.get('available')}`",
            f"- epoch count: `{epoch.get('epoch_count')}`",
            f"- dataset available: `{dataset.get('available')}`",
            f"- dataset count: `{dataset.get('count')}`",
        ],
    )

    ui = payload.get("ui_state") or {}
    lines.extend(
        [
            "",
            "## UI State",
            "",
            f"- send button: `{ui.get('send_button_text', '')}`",
            f"- send button enabled: `{ui.get('send_button_enabled', False)}`",
            f"- input enabled: `{ui.get('input_enabled', False)}`",
            f"- chat processing: `{ui.get('chat_processing', False)}`",
            f"- controller processing: `{ui.get('controller_processing', False)}`",
            "",
            "## Shutdown",
            "",
            f"- status: `{(payload.get('shutdown') or {}).get('status', 'unknown')}`",
            f"- detail: {(payload.get('shutdown') or {}).get('detail') or 'none'}",
        ],
    )
    return "\n".join(lines).rstrip() + "\n"


def _turn_has_expected_tool(
    tools: list[dict[str, Any]],
    expected_tool: str,
) -> bool:
    return any(
        str(tool.get("name") or "") == expected_tool and bool(tool.get("success"))
        for tool in tools
    )


def _section(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _blocked_payload(
    args: argparse.Namespace,
    runtime: dict[str, object],
) -> dict[str, Any]:
    runtime_summary = _runtime_summary(runtime)
    if args.model:
        runtime_summary["model_id"] = args.model
    payload = _terminal_payload(
        status="blocked",
        failure_reason=str(runtime.get("message") or "Local runtime not ready."),
        runtime_summary=runtime_summary,
        source_path=None,
    )
    payload["runtime"]["requested_model_id"] = args.model or str(
        payload["runtime"].get("requested_model_id") or ""
    )
    return payload


def _failed_payload(
    args: argparse.Namespace,
    runtime_summary: Mapping[str, object],
    source_path: Path | None,
    failure_reason: str,
    *,
    exception: str = "",
) -> dict[str, Any]:
    """Build a renderable terminal artifact for pre-event-loop failures."""
    summary = dict(runtime_summary)
    if args.model:
        summary["model_id"] = args.model
    payload = _terminal_payload(
        status="failed",
        failure_reason=failure_reason,
        runtime_summary=summary,
        source_path=source_path,
    )
    payload["exception"] = exception
    payload["runtime"]["requested_model_id"] = args.model or str(
        payload["runtime"].get("requested_model_id") or ""
    )
    return payload


def _terminal_payload(
    *,
    status: str,
    failure_reason: str,
    runtime_summary: Mapping[str, object],
    source_path: Path | None,
) -> dict[str, Any]:
    """Return one stable artifact schema for blocked and startup-failed runs."""
    prompts = build_prompts(source_path) if source_path is not None else []
    return {
        "status": status,
        "failure_reason": failure_reason,
        "exception": "",
        "source_path": str(source_path) if source_path is not None else "",
        "prompts": prompts,
        "expected_tools": list(EXPECTED_TOOLS),
        "runtime": runtime_evidence(runtime_summary, None),
        "hf_offline": {
            "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE"),
            "TRANSFORMERS_OFFLINE": os.environ.get("TRANSFORMERS_OFFLINE"),
        },
        "screenshots": {"ready": "", "terminal": "", "failure": ""},
        "turns": [],
        "visible_messages": [],
        "executed_tools": [],
        "setup_dialogs": [],
        "confirmation_dialogs": [],
        "confirmation_requests": [],
        "interaction_events": [],
        "workflow_handoffs": [],
        "application_results": [],
        "turn_terminals": [],
        "controller_history": [],
        "final_state": {},
        "final_publication": {},
        "runtime_snapshot": {},
        "ui_state": {
            "send_button_text": "",
            "send_button_enabled": False,
            "input_enabled": False,
            "chat_processing": False,
            "controller_processing": False,
        },
        "shutdown": {"status": "not_started", "detail": ""},
        "elapsed_seconds": 0.0,
    }


def _write_artifacts(output_dir: Path, payload: dict[str, Any]) -> None:
    (output_dir / JSON_ARTIFACT).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / MD_ARTIFACT).write_text(
        render_markdown(payload),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
