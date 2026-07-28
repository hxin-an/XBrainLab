import argparse
import ast
import inspect
import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QDialog, QMessageBox, QPushButton

from scripts.dev.capture_chatpanel_local_pipeline_chain_walkthrough import (
    EXPECTED_TOOLS,
    SettingsFileSnapshot,
    _failed_payload,
    _structured_value,
    approve_product_dialog,
    assistant_surface_ready,
    build_prompts,
    collect_model_proposals,
    publication_evidence,
    render_markdown,
    run_pipeline_chain,
    runtime_evidence,
    validate_pipeline_payload,
)
from scripts.dev.chatpanel_pipeline_chain import (
    PipelineChainDriver,
    PipelineEvidenceAssembler,
    PipelinePhase,
    PipelineShutdownCoordinator,
    PipelineWalkthroughState,
)
from XBrainLab.llm.agent.intent import infer_user_intent
from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
    AssistantRuntimeSnapshot,
)
from XBrainLab.llm.core.runtime_selection import AssistantRuntimeSelectionOutcome


class _FirstRunDialog(QDialog):
    """Typed test double matching the product first-run dialog surface."""

    def __init__(self) -> None:
        super().__init__()
        self.enable_btn = QPushButton("Enable", self)
        self.use_cache_btn = QPushButton("Use existing cache", self)


def _turn_evidence() -> list[dict]:
    return [
        {
            "index": index,
            "expected_tool": tool_name,
            "new_tools": [{"name": tool_name, "success": True}],
            "tool_proposals": [{"tool_name": tool_name, "parameters": {}}],
            "publication_before": {
                "available": True,
                "generation": index,
                "pipeline_stage": "empty" if index == 1 else "in_progress",
            },
            "publication_after": {
                "available": True,
                "generation": index + 1,
                "pipeline_stage": "dataset" if index == 7 else "in_progress",
            },
            "publication_generation_delta": 1,
            "metrics": {
                "completed_turn_count": 1,
                "llm_calls": 1,
                "tool_executions": [{"name": tool_name, "success": True}],
            },
            "confirmation_requests": [],
            "interaction_events": [],
            "workflow_handoffs": [],
            "application_results": [{"command_name": tool_name, "status": "succeeded"}],
            "turn_terminals": [{"outcome": "completed"}],
            "screenshot": f"turn-{index}.png",
        }
        for index, tool_name in enumerate(EXPECTED_TOOLS, start=1)
    ]


def _model_generation_evidence() -> dict[str, list]:
    return {
        "model_generations": [f"generation-{index}" for index in range(1, 8)],
        "model_generation_request_ids": list(range(1, 8)),
    }


def test_validate_pipeline_payload_requires_tool_sequence_and_final_state():
    ok, reason = validate_pipeline_payload(
        {
            **_model_generation_evidence(),
            "expected_tools": EXPECTED_TOOLS,
            "executed_tools": [
                {"name": name, "success": True} for name in EXPECTED_TOOLS
            ],
            "confirmation_dialogs": [{"title": "Confirm Action"}],
            "turns": _turn_evidence(),
            "final_state": {
                "raw": {"loaded": True},
                "interpretation": {"has_applied_interpretation": True},
                "epoch": {"available": True},
                "dataset": {"available": True},
            },
        },
    )

    assert ok is True
    assert reason == ""


def test_validate_pipeline_payload_rejects_missing_dataset():
    ok, reason = validate_pipeline_payload(
        {
            **_model_generation_evidence(),
            "expected_tools": EXPECTED_TOOLS,
            "executed_tools": [
                {"name": name, "success": True} for name in EXPECTED_TOOLS
            ],
            "confirmation_dialogs": [{"title": "Confirm Action"}],
            "turns": _turn_evidence(),
            "final_state": {
                "raw": {"loaded": True},
                "interpretation": {"has_applied_interpretation": True},
                "epoch": {"available": True},
                "dataset": {"available": False},
            },
        },
    )

    assert ok is False
    assert "dataset" in reason


def test_validate_pipeline_payload_requires_per_turn_state_change_evidence():
    turns = _turn_evidence()
    turns[3].pop("publication_after")

    ok, reason = validate_pipeline_payload(
        {
            **_model_generation_evidence(),
            "expected_tools": EXPECTED_TOOLS,
            "executed_tools": [
                {"name": name, "success": True} for name in EXPECTED_TOOLS
            ],
            "confirmation_dialogs": [{"title": "Confirm action"}],
            "turns": turns,
            "final_state": {
                "raw": {"loaded": True},
                "interpretation": {"has_applied_interpretation": True},
                "epoch": {"available": True},
                "dataset": {"available": True},
            },
        }
    )

    assert ok is False
    assert "publication evidence" in reason


def test_validate_pipeline_payload_requires_typed_terminal_evidence():
    turns = _turn_evidence()
    turns[2]["turn_terminals"] = []

    ok, reason = validate_pipeline_payload(
        {
            **_model_generation_evidence(),
            "expected_tools": EXPECTED_TOOLS,
            "executed_tools": [
                {"name": name, "success": True} for name in EXPECTED_TOOLS
            ],
            "confirmation_dialogs": [{"title": "Confirm action"}],
            "turns": turns,
            "final_state": {
                "raw": {"loaded": True},
                "interpretation": {"has_applied_interpretation": True},
                "epoch": {"available": True},
                "dataset": {"available": True},
            },
        }
    )

    assert ok is False
    assert "typed terminal evidence" in reason


def test_validate_pipeline_payload_rejects_uncorrelated_model_output():
    payload = {
        **_model_generation_evidence(),
        "expected_tools": EXPECTED_TOOLS,
        "executed_tools": [{"name": name, "success": True} for name in EXPECTED_TOOLS],
        "confirmation_dialogs": [{"title": "Confirm action"}],
        "turns": _turn_evidence(),
        "final_state": {
            "raw": {"loaded": True},
            "interpretation": {"has_applied_interpretation": True},
            "epoch": {"available": True},
            "dataset": {"available": True},
        },
    }
    payload["model_generation_request_ids"][-1] = 2

    ok, reason = validate_pipeline_payload(payload)

    assert ok is False
    assert "request-ID correlation" in reason


def test_pipeline_prompts_map_to_the_exact_workflow_intents():
    prompts = build_prompts(Path("/tmp/source.fif"))

    assert [infer_user_intent(prompt) for prompt in prompts] == [
        "scan_source",
        "preview_interpretation",
        "validate_interpretation",
        "apply_interpretation",
        "preprocess",
        "create_epoch",
        "generate_dataset",
    ]
    assert "validated" not in prompts[3].casefold()
    assert not any(tool_name in " ".join(prompts) for tool_name in EXPECTED_TOOLS)


def test_contract_prompts_remain_available_for_explicit_tool_probes():
    prompts = build_prompts(Path("/tmp/source.fif"), style="contract")

    assert [infer_user_intent(prompt) for prompt in prompts] == [
        "scan_source",
        "preview_interpretation",
        "validate_interpretation",
        "apply_interpretation",
        "preprocess",
        "create_epoch",
        "generate_dataset",
    ]
    assert EXPECTED_TOOLS[0] in prompts[0]


def test_approve_product_dialog_handles_real_first_run_shape(qtbot):
    dialog = _FirstRunDialog()
    qtbot.addWidget(dialog)
    dialog.setWindowTitle("Local Assistant Runtime")
    dialog.enable_btn.clicked.connect(dialog.accept)
    dialog.use_cache_btn.setEnabled(False)

    event = approve_product_dialog(dialog)

    assert event == {
        "kind": "first_run",
        "title": "Local Assistant Runtime",
        "action": "Enable",
        "approved": True,
    }
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_approve_product_dialog_uses_custom_accept_role_case_insensitively(qtbot):
    dialog = QMessageBox()
    qtbot.addWidget(dialog)
    dialog.setWindowTitle("Confirm action")
    dialog.setText("Apply interpretation")
    approve = dialog.addButton(
        "Apply interpretation", QMessageBox.ButtonRole.AcceptRole
    )
    assert approve is not None
    dialog.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    clicked: list[bool] = []
    approve.clicked.connect(lambda: clicked.append(True))

    event = approve_product_dialog(dialog)

    assert event is not None
    assert event["kind"] == "confirmation"
    assert event["title"] == "Confirm action"
    assert event["action"] == "Apply interpretation"
    assert event["approved"] is True
    assert clicked == [True]


def test_assistant_surface_ready_requires_runtime_and_composer_truth():
    panel = SimpleNamespace(
        send_btn=SimpleNamespace(isEnabled=lambda: False, text=lambda: "Send"),
        input_field=SimpleNamespace(isEnabled=lambda: True),
    )
    manager = SimpleNamespace(
        assistant_runtime=SimpleNamespace(
            accepts_commands=True,
            current=AssistantRuntimeSnapshot(
                phase=AssistantRuntimePhase.READY,
                initialized=True,
                backend_mode="local",
                model_id="microsoft/Phi-3.5-mini-instruct",
            ),
        ),
        chat_panel=panel,
        chat_dock=SimpleNamespace(isVisible=lambda: True),
        chat_controller=SimpleNamespace(is_processing=False),
        agent_controller=SimpleNamespace(is_processing=False),
    )

    ready, reason = assistant_surface_ready(manager)
    manager.assistant_runtime.accepts_commands = False
    not_ready, not_ready_reason = assistant_surface_ready(manager)

    assert (ready, reason) == (True, "ready")
    assert not_ready is False
    assert "runtime" in not_ready_reason


def test_collect_model_proposals_preserves_full_canonical_parameters():
    prompt = "Scan the source."
    history = [
        {"role": "user", "content": "Earlier request"},
        {"role": "user", "content": prompt},
        {
            "role": "assistant",
            "content": (
                '{"tool_name":"scan_source","parameters":'
                '{"source_path":"/tmp/source.fif","label_sources":[]}}'
            ),
        },
        {"role": "user", "content": "Tool Output: done"},
    ]

    assert collect_model_proposals(history, prompt) == [
        {
            "tool_name": "scan_source",
            "parameters": {
                "source_path": "/tmp/source.fif",
                "label_sources": [],
            },
        }
    ]


def test_collect_model_proposals_rejects_legacy_wrapped_envelopes():
    prompt = "Scan the source."
    history = [
        {"role": "user", "content": prompt},
        {
            "role": "assistant",
            "content": (
                '{"tool_call":{"tool_name":"scan_source","parameters":'
                '{"source_path":"/tmp/source.fif","label_sources":[]}}}'
            ),
        },
    ]

    assert collect_model_proposals(history, prompt) == []


def test_publication_evidence_keeps_generation_and_serialized_state():
    publication = SimpleNamespace(
        generation=7,
        usable=True,
        verified=True,
        stale=False,
        refresh_error=None,
        state=SimpleNamespace(
            pipeline_stage="epoch_ready",
            to_dict=lambda: {
                "pipeline_stage": "epoch_ready",
                "epoch": {"available": True},
            },
        ),
    )

    evidence = publication_evidence(
        SimpleNamespace(get_view_publication=lambda: publication)
    )

    assert evidence["generation"] == 7
    assert evidence["pipeline_stage"] == "epoch_ready"
    assert evidence["state"]["epoch"]["available"] is True


def test_runtime_evidence_reports_requested_and_loaded_model_truth():
    runtime = {
        "classification": "gpu-ready",
        "model_id": "microsoft/Phi-4-mini-instruct",
        "cache_usage": "8 GB",
    }
    snapshot = AssistantRuntimeSnapshot(
        phase=AssistantRuntimePhase.READY,
        initialized=True,
        backend_mode="local",
        requested_model_id="microsoft/Phi-4-mini-instruct",
        model_id="microsoft/Phi-3.5-mini-instruct",
        selection_outcome=AssistantRuntimeSelectionOutcome.FALLBACK,
        selection_detail="Fallback selected.",
    )

    evidence = runtime_evidence(runtime, snapshot)

    assert evidence["requested_model_id"] == "microsoft/Phi-4-mini-instruct"
    assert evidence["loaded_model_id"] == "microsoft/Phi-3.5-mini-instruct"
    assert evidence["model_id"] == "microsoft/Phi-3.5-mini-instruct"
    assert evidence["fallback_used"] is True


def test_structured_value_serializes_string_enums_before_plain_strings():
    assert _structured_value(AssistantRuntimePhase.READY) == "ready"
    assert _structured_value(AssistantRuntimeSelectionOutcome.EXACT) == "exact"


def test_settings_file_snapshot_restores_existing_and_missing_files(tmp_path):
    existing = tmp_path / "settings.json"
    existing.write_text('{"before": true}\n', encoding="utf-8")
    existing_snapshot = SettingsFileSnapshot.capture(existing)
    existing.write_text('{"after": true}\n', encoding="utf-8")

    existing_snapshot.restore()

    assert existing.read_text(encoding="utf-8") == '{"before": true}\n'

    missing = tmp_path / "missing.json"
    missing_snapshot = SettingsFileSnapshot.capture(missing)
    missing.write_text("temporary", encoding="utf-8")

    missing_snapshot.restore()

    assert not missing.exists()


def test_failed_payload_is_terminal_and_markdown_safe():
    payload = _failed_payload(
        argparse.Namespace(model="microsoft/Phi-3.5-mini-instruct"),
        {
            "classification": "gpu-ready",
            "model_id": "microsoft/Phi-3.5-mini-instruct",
            "cache_usage": "8 GB",
        },
        Path("/tmp/source.fif"),
        "startup failed",
        exception="traceback",
    )

    markdown = render_markdown(payload)

    assert payload["status"] == "failed"
    assert payload["failure_reason"] == "startup failed"
    assert payload["runtime"]["requested_model_id"] == (
        "microsoft/Phi-3.5-mini-instruct"
    )
    assert payload["shutdown"]["status"] == "not_started"
    assert "startup failed" in markdown


def test_render_markdown_records_confirmation_and_dataset_state():
    markdown = render_markdown(
        {
            "status": "passed",
            "failure_reason": "",
            "source_path": "/tmp/source.fif",
            "runtime": {
                "classification": "gpu-ready",
                "model_id": "microsoft/Phi-4-mini-instruct",
                "requested_model_id": "microsoft/Phi-4-mini-instruct",
                "loaded_model_id": "microsoft/Phi-4-mini-instruct",
                "phase": "ready",
                "cache_usage": "15.34 GB",
            },
            "hf_offline": {
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
            },
            "screenshots": {"ready": "ready.png"},
            "terminal_screenshot": "terminal.png",
            "expected_tools": EXPECTED_TOOLS,
            "confirmation_dialogs": [{"title": "Confirm Action"}],
            "elapsed_seconds": 42.0,
            "turns": [
                {
                    "index": 1,
                    "prompt": "Scan.",
                    "expected_tool": "scan_source",
                    "assistant_text": "Scanned source.",
                    "new_tools": [{"name": "scan_source"}],
                    "tool_proposals": [
                        {
                            "tool_name": "scan_source",
                            "parameters": {"source_path": "/tmp/source.fif"},
                        }
                    ],
                    "publication_before": {"generation": 1, "pipeline_stage": "empty"},
                    "publication_after": {
                        "generation": 2,
                        "pipeline_stage": "interpretation",
                    },
                    "metrics": {
                        "llm_calls": 1,
                        "tool_executions": [{"name": "scan_source"}],
                    },
                    "screenshot": "turn-1.png",
                },
            ],
            "executed_tools": [
                {"name": "scan_source", "success": True, "duration_ms": 1.0},
            ],
            "final_state": {
                "interpretation": {
                    "has_applied_interpretation": True,
                    "validation_decision": "needs_confirmation",
                },
                "epoch": {"available": True, "epoch_count": 3},
                "dataset": {"available": True, "count": 1},
            },
            "ui_state": {
                "send_button_text": "Send",
                "send_button_enabled": True,
                "input_enabled": True,
                "chat_processing": False,
                "controller_processing": False,
            },
        },
    )

    assert "# ChatPanel Local Pipeline-Chain Walkthrough" in markdown
    assert "confirmation dialogs observed: `1`" in markdown
    assert "dataset available: `True`" in markdown
    assert "requested model: `microsoft/Phi-4-mini-instruct`" in markdown
    assert "loaded model: `microsoft/Phi-4-mini-instruct`" in markdown
    assert "publication: `1 -> 2`" in markdown


def test_walkthrough_state_enforces_pipeline_phase_order():
    state = PipelineWalkthroughState(
        source_path="/tmp/source.fif",
        prompt_style="natural",
        expected_tools=list(EXPECTED_TOOLS),
        started_at=10.0,
    )

    state.advance(PipelinePhase.STARTING)
    state.advance(PipelinePhase.WAITING_FOR_READY)
    state.advance(PipelinePhase.RUNNING_TURNS)
    state.advance(PipelinePhase.FINALIZING)
    state.advance(PipelinePhase.SHUTTING_DOWN)
    state.advance(PipelinePhase.COMPLETED)

    assert state.phase_history == [
        PipelinePhase.CREATED,
        PipelinePhase.STARTING,
        PipelinePhase.WAITING_FOR_READY,
        PipelinePhase.RUNNING_TURNS,
        PipelinePhase.FINALIZING,
        PipelinePhase.SHUTTING_DOWN,
        PipelinePhase.COMPLETED,
    ]
    with pytest.raises(RuntimeError, match="Invalid walkthrough phase transition"):
        state.advance(PipelinePhase.RUNNING_TURNS)


def test_walkthrough_state_keeps_each_streamed_model_generation_separate():
    state = PipelineWalkthroughState(
        source_path="/tmp/source.fif",
        prompt_style="natural",
        expected_tools=list(EXPECTED_TOOLS),
        started_at=10.0,
    )

    assert state.begin_model_generation(41) is True
    assert state.append_model_chunk(40, "stale response") is False
    assert state.append_model_chunk(41, '{"tool_name":') is True
    assert state.append_model_chunk(41, '"scan_source","parameters":{}}') is True
    assert state.begin_model_generation(42) is True
    assert state.append_model_chunk(41, "late response") is False
    assert state.append_model_chunk(42, "corrected response") is True
    assert state.end_model_generation(42) is True
    assert state.append_model_chunk(42, "after finish") is False

    assert state.model_generations == [
        '{"tool_name":"scan_source","parameters":{}}',
        "corrected response",
    ]
    assert state.model_generation_request_ids == [41, 42]
    assert state.active_model_request_id is None


def test_pipeline_driver_uses_only_controller_generation_event_stream() -> None:
    source = inspect.getsource(PipelineChainDriver._connect_controller_observers)

    assert "generation_event.connect" in source
    assert ".worker" not in source
    assert "_active_generation_id" not in source


def test_run_pipeline_chain_remains_a_thin_composition_root():
    source = inspect.getsource(run_pipeline_chain)
    function = ast.parse(source).body[0]

    assert isinstance(function, ast.FunctionDef)
    assert len(source.splitlines()) < 80
    assert not [
        node
        for node in ast.walk(function)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node is not function
    ]


def test_shutdown_coordinator_owns_failure_snapshot_and_cleanup(tmp_path):
    scheduled: list[tuple[int, Callable[[], None]]] = []
    clock = iter((20.0, 20.5, 20.75))
    state = PipelineWalkthroughState(
        source_path="/tmp/source.fif",
        prompt_style="natural",
        expected_tools=list(EXPECTED_TOOLS),
        started_at=10.0,
    )
    state.advance(PipelinePhase.STARTING)
    state.advance(PipelinePhase.WAITING_FOR_READY)
    state.advance(PipelinePhase.RUNNING_TURNS)
    window = SimpleNamespace(
        visible=True,
        close_calls=0,
    )
    window.close = lambda: (
        setattr(window, "close_calls", window.close_calls + 1),
        setattr(window, "visible", False),
    )
    window.isVisible = lambda: window.visible
    app = SimpleNamespace(quit_calls=0)
    app.quit = lambda: setattr(app, "quit_calls", app.quit_calls + 1)
    service = SimpleNamespace(
        get_state=lambda: SimpleNamespace(to_dict=lambda: {"pipeline_stage": "raw"})
    )

    def capture_window(_window, path):
        path.write_bytes(b"png")
        return 0

    coordinator = PipelineShutdownCoordinator(
        app=app,
        window=window,
        service=service,
        output_dir=tmp_path,
        state=state,
        manager_provider=lambda: None,
        capture_window=capture_window,
        collect_visible_messages=lambda _panel: [],
        collect_executed_tools=lambda _metrics: [],
        publication_evidence=lambda _service: {"generation": 1},
        structured_value=_structured_value,
        validate_payload=lambda _payload: (True, ""),
        schedule=lambda delay, callback: scheduled.append((delay, callback)),
        now=lambda: next(clock),
    )

    coordinator.fail("turn failed")

    assert state.status == "failed"
    assert state.failure_reason == "turn failed"
    assert state.final_state == {"pipeline_stage": "raw"}
    assert state.shutdown == {"status": "closing", "detail": ""}
    assert state.phase is PipelinePhase.SHUTTING_DOWN
    assert window.close_calls == 1
    assert len(scheduled) == 1

    scheduled.pop()[1]()

    assert state.shutdown == {"status": "completed", "detail": ""}
    assert state.phase is PipelinePhase.COMPLETED
    assert app.quit_calls == 1


def test_evidence_assembler_serializes_nested_runtime_enums():
    state = PipelineWalkthroughState(
        source_path="/tmp/source.fif",
        prompt_style="contract",
        expected_tools=list(EXPECTED_TOOLS),
        started_at=10.0,
    )
    state.runtime_snapshot = {"phase": "ready", "initialized": True}
    state.controller_history = [
        {"phase": AssistantRuntimePhase.READY},
        {"outcome": AssistantRuntimeSelectionOutcome.EXACT},
    ]
    payload = PipelineEvidenceAssembler(
        state=state,
        prompts=["Scan."],
        initial_runtime={"classification": "gpu-ready"},
        runtime_evidence=runtime_evidence,
        structured_value=_structured_value,
    ).build()

    assert set(payload) == {
        "status",
        "failure_reason",
        "exception",
        "source_path",
        "prompt_style",
        "prompts",
        "expected_tools",
        "runtime",
        "hf_offline",
        "screenshots",
        "turns",
        "model_generations",
        "model_generation_request_ids",
        "visible_messages",
        "executed_tools",
        "setup_dialogs",
        "confirmation_dialogs",
        "confirmation_requests",
        "interaction_events",
        "workflow_handoffs",
        "application_results",
        "turn_terminals",
        "controller_history",
        "final_state",
        "final_publication",
        "runtime_snapshot",
        "ui_state",
        "shutdown",
        "elapsed_seconds",
    }
    assert payload["controller_history"] == [
        {"phase": "ready"},
        {"outcome": "exact"},
    ]
    assert json.loads(json.dumps(payload))["prompt_style"] == "contract"
