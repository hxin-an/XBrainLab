import ast
import copy
import inspect
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

import scripts.dev.chatpanel_guided_boundary.driver as guided_boundary_driver
import scripts.dev.chatpanel_guided_boundary.runtime as guided_boundary_runtime
from scripts.dev.capture_chatpanel_local_guided_boundary_walkthrough import main
from scripts.dev.chatpanel_guided_boundary import (
    DEFAULT_MODEL_ID,
    EXPECTED_AUTO_CHAIN,
    GuidedBoundaryEvidenceAssembler,
    GuidedBoundaryPhase,
    GuidedBoundaryState,
    build_guided_prompts,
    capture_and_cancel_workflow_dialog,
    reconcile_closed_event_loop,
)
from scripts.dev.chatpanel_guided_boundary import (
    validate_guided_boundary_payload as _validate_guided_boundary_payload,
)
from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_screenshot_artifacts,
    collect_source_identity,
    validate_source_identity,
)
from scripts.dev.chatpanel_guided_boundary.artifact_runner import (
    publish_guided_boundary_artifact_run,
)
from scripts.dev.chatpanel_guided_boundary.driver import (
    _application_result_succeeded,
    _validate_pre_shutdown_candidate,
)
from scripts.dev.chatpanel_guided_boundary.tool_trace import GuidedToolTraceRecorder
from scripts.dev.chatpanel_guided_boundary.validation import (
    JSON_ARTIFACT,
    MARKDOWN_ARTIFACT,
    canonical_turn_calls,
    validate_auto_chain_boundary,
    validate_guided_boundary_artifact_root,
)
from XBrainLab.llm.agent.ui_handoff import WorkflowUiHandoffRequest
from XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog import (
    DataInterpretationPreviewDialog,
)

_SYNTHETIC_CURRENT_SOURCE_IDENTITY = collect_source_identity()


def test_prepare_capture_config_uses_only_the_isolated_config_dir(
    monkeypatch,
    tmp_path,
) -> None:
    original_dir = tmp_path / "original-config"
    isolated_dir = tmp_path / "isolated-config"
    monkeypatch.setenv(guided_boundary_runtime.CONFIG_DIR_ENV, str(original_dir))

    config = guided_boundary_runtime._prepare_capture_config(
        DEFAULT_MODEL_ID,
        isolated_dir,
    )

    assert config.model_name == DEFAULT_MODEL_ID
    assert os.environ[guided_boundary_runtime.CONFIG_DIR_ENV] == str(isolated_dir)
    assert (isolated_dir / "settings.json").is_file()
    assert not (original_dir / "settings.json").exists()

    guided_boundary_runtime._restore_capture_config_env(str(original_dir))
    assert os.environ[guided_boundary_runtime.CONFIG_DIR_ENV] == str(original_dir)


def validate_guided_boundary_payload(
    payload: dict,
    *,
    require_shutdown: bool = True,
) -> tuple[bool, str]:
    """Avoid repeating one expensive repo digest across mutation-only unit cases."""
    return _validate_guided_boundary_payload(
        payload,
        require_shutdown=require_shutdown,
        refresh_source_identity=False,
        current_source_identity=_SYNTHETIC_CURRENT_SOURCE_IDENTITY,
    )


def _state_payload() -> dict:
    return {
        "pipeline_stage": "interpretation_validated",
        "raw": {"loaded": False, "count": 0},
        "dataset": {"generated": False, "count": 0},
        "interpretation": {
            "has_scan_result": True,
            "has_candidate": True,
            "has_preview": True,
            "has_validation_decision": True,
            "has_applied_interpretation": False,
            "validation_decision": "needs_confirmation",
            "pending_confirmation": True,
            "action_items": [
                {
                    "issue": "Confirm subject metadata for recording.fif.",
                    "severity": "needs_confirmation",
                    "target_step": "Review Metadata",
                },
                {
                    "issue": "Confirm task metadata for recording.fif.",
                    "severity": "needs_confirmation",
                    "target_step": "Review Metadata",
                },
                {
                    "issue": (
                        "Confirm which events are trial anchors, class cues, "
                        "responses, artifacts, or boundaries."
                    ),
                    "severity": "needs_confirmation",
                    "target_step": "Match Labels",
                },
                {
                    "issue": "No external label file or folder is attached.",
                    "severity": "warning",
                    "target_step": "Load Labels",
                },
            ],
        },
    }


def _publication(generation: int) -> dict:
    return {
        "available": True,
        "generation": generation,
        "usable": True,
        "verified": True,
        "stale": False,
        "refresh_error": None,
        "pipeline_stage": "interpretation_validated",
        "state": _state_payload(),
    }


def _run_git(git: str, repo: Path, *args: str) -> None:
    subprocess.run([git, *args], cwd=repo, check=True)  # noqa: S603


def _valid_payload(tmp_path: Path) -> dict:
    source = Path("/tmp/guided boundary source.fif").resolve()
    (first_prompt,) = build_guided_prompts(source)
    screenshots = {
        "ready": str(tmp_path / "ready.png"),
        "auto_chain_complete": str(tmp_path / "auto-chain.png"),
        "workflow_dialog_open": str(tmp_path / "workflow-dialog.png"),
        "post_cancel": str(tmp_path / "post-cancel.png"),
        "failure": "",
    }
    for index, path in enumerate(screenshots.values()):
        if path:
            Image.new("RGBA", (12 + index, 8), (20 * index, 40, 80, 255)).save(path)
    first_calls = canonical_turn_calls(str(source), turn="first")
    assert first_calls[0]["parameters"] == {
        "source_path": str(source),
        "source_hint": "file",
    }
    observations = [
        {
            "command_name": command,
            "success": True,
            "publication": _publication(generation),
        }
        for command, generation in zip(EXPECTED_AUTO_CHAIN, (2, 3, 4), strict=True)
    ]
    boundary_state = _state_payload()
    request = {
        "kind": "decision_required",
        "command": "apply_interpretation",
        "request_id": "handoff-4",
        "decision_fields": ["metadata_review", "label_matching"],
        "suggested_values": [],
    }
    action_summary = (
        "Import review needs your input:\n"
        "- Confirm subject metadata for recording.fif.\n"
        "- Confirm task metadata for recording.fif.\n"
        "- Confirm which events are trial anchors, class cues, responses, "
        "artifacts, or boundaries.\n"
        "Use the open Import EEG Data window to review these choices."
    )
    return {
        "schema_version": 5,
        "walkthrough": "adaptive_workflow_ui_handoff_boundary",
        "status": "passed",
        "failure_reason": "",
        "source_path": str(source),
        "model_id": DEFAULT_MODEL_ID,
        "prompts": [first_prompt],
        "expected_auto_chain": list(EXPECTED_AUTO_CHAIN),
        "claim_boundary": (
            "Offscreen evidence is not human Windows desktop acceptance."
        ),
        "capture_source": {
            "source_digest_at_start": _SYNTHETIC_CURRENT_SOURCE_IDENTITY[
                "source_digest"
            ],
            "source_digest_at_completion": _SYNTHETIC_CURRENT_SOURCE_IDENTITY[
                "source_digest"
            ],
            "stable": True,
        },
        "source_identity": copy.deepcopy(_SYNTHETIC_CURRENT_SOURCE_IDENTITY),
        "runtime": {
            "classification": "gpu-ready",
            "requested_model_id": DEFAULT_MODEL_ID,
            "loaded_model_id": DEFAULT_MODEL_ID,
            "phase": "ready",
            "initialized": True,
            "selection_outcome": "exact",
            "fallback_used": False,
        },
        "hf_offline": {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        },
        "scope_resolution": {
            "source": "request_text",
            "scope": "guided_workflow",
            "policy_mode": "multi",
            "terminal_command": None,
            "legacy_selector_present": False,
        },
        "screenshots": screenshots,
        "screenshot_artifacts": collect_screenshot_artifacts(screenshots),
        "initial_publication": _publication(1),
        "command_observations": observations,
        "first_turn": {
            "prompt": first_prompt,
            "new_tools": [
                {"name": command, "success": True} for command in EXPECTED_AUTO_CHAIN
            ],
            "tool_proposals": first_calls[:1],
            "tool_attempts": [
                {
                    "raw": call if index == 0 else None,
                    "canonical": call,
                    "normalized": call if index == 0 else None,
                    "actual": {
                        "kind": ("model_execution" if index == 0 else "host_execution"),
                        **call,
                    },
                }
                for index, call in enumerate(first_calls)
            ],
            "metrics": {
                "completed_turn_count": 1,
                "llm_calls": 1,
                "tool_executions": [
                    {"name": command, "success": True}
                    for command in EXPECTED_AUTO_CHAIN
                ],
            },
            "assistant_text": "The recording is ready for your decision.",
            "assistant_messages": [action_summary],
        },
        "boundary": {
            "publication": _publication(4),
            "state": boundary_state,
            "apply_capability": {
                "enabled": True,
                "requires_confirmation": True,
                "confirmation_required": True,
                "can_auto_execute": False,
            },
            "assistant_waiting_surface": {
                "turn_phase": "waiting",
                "header_status": "Local · Waiting",
                "send_button_text": "Waiting",
                "send_button_enabled": False,
                "input_enabled": False,
                "cancelability_text": ("Continue in the open Import EEG Data window."),
            },
        },
        "workflow_handoff": {
            "observed": True,
            "observed_while_dialog_visible": True,
            "request": request,
            "controller_pending_request": request,
            "host_active_request": request,
        },
        "wizard": {
            "dialog_opened": True,
            "dialog_visible": True,
            "dialog_class": (
                "XBrainLab.ui.dialogs.dataset.data_interpretation_preview_dialog."
                "DataInterpretationPreviewDialog"
            ),
            "object_name": "DataImportWizardDialog",
            "dialog_title": "Import EEG Data",
            "request_id": "handoff-4",
            "decision_fields": ["metadata_review", "label_matching"],
            "step_titles": [
                "Choose EEG Data",
                "Load Labels",
                "Review Metadata",
                "Match Labels",
                "Review and Import",
            ],
            "current_step_index": 2,
            "current_step_title": "Review Metadata",
            "cancel_button_text": "Cancel",
            "cancel_clicked": True,
            "cancel_signal_observed": True,
            "visible_after_cancel_click": False,
            "screenshot": screenshots["workflow_dialog_open"],
        },
        "post_cancel": {
            "publication": _publication(4),
            "state": boundary_state,
            "pending_workflow_handoff": False,
            "workflow_dialog_visible": False,
            "apply_completion_observed": False,
            "executed_tools": [
                {"name": command, "success": True} for command in EXPECTED_AUTO_CHAIN
            ],
        },
        "visible_messages": [
            {"sender": "user", "text": first_prompt},
            {
                "sender": "assistant",
                "text": action_summary,
            },
            {
                "sender": "assistant",
                "text": "Data interpretation review was cancelled.",
            },
        ],
        "executed_tools": [
            {"name": command, "success": True} for command in EXPECTED_AUTO_CHAIN
        ],
        "workflow_handoff_requests": [request],
        "confirmation_requests": [],
        "interaction_events": [
            {
                "request_id": "handoff-4",
                "command_name": "apply_interpretation",
                "status": "cancelled",
            }
        ],
        "application_results": [
            {"command_name": command, "status": "ok"} for command in EXPECTED_AUTO_CHAIN
        ],
        "turn_terminals": [{"turn_id": 1, "outcome": "completed"}],
        "runtime_snapshot": {"phase": "ready", "initialized": True},
        "transcript_clean": True,
        "ui_state": {
            "send_button_text": "Send",
            "send_button_enabled": False,
            "input_enabled": True,
            "input_text": "",
            "chat_processing": False,
            "controller_processing": False,
            "runtime_turn_in_flight": False,
        },
        "shutdown": {"status": "completed", "detail": ""},
        "phase_history": [
            "created",
            "starting",
            "waiting_for_ready",
            "resolving_turn_scope",
            "running_auto_chain",
            "waiting_at_boundary",
            "workflow_handoff_open",
            "waiting_after_cancel",
            "finalizing",
            "shutting_down",
            "completed",
        ],
        "elapsed_seconds": 12.3,
    }


def test_guided_prompts_are_natural_and_exact(tmp_path):
    source = (tmp_path / "recording.fif").resolve()

    prompts = build_guided_prompts(source)

    assert prompts == (
        (
            f"Use the EEG recording at {source} to prepare the data for analysis. "
            "Continue until a decision is needed."
        ),
    )
    assert not any(tool in " ".join(prompts) for tool in EXPECTED_AUTO_CHAIN)
    assert "apply_interpretation" not in " ".join(prompts)


def test_guided_phase_rejects_skipping_the_workflow_handoff_boundary():
    state = GuidedBoundaryState(
        source_path="/tmp/recording.fif",
        model_id=DEFAULT_MODEL_ID,
        prompts=("first",),
        started_at=1.0,
    )
    state.advance(GuidedBoundaryPhase.STARTING)

    with pytest.raises(RuntimeError, match="Invalid guided walkthrough phase"):
        state.advance(GuidedBoundaryPhase.WORKFLOW_HANDOFF_OPEN)


def test_event_loop_reconciliation_requires_both_shutdown_owners_closed():
    state = GuidedBoundaryState(
        source_path="/tmp/recording.fif",
        model_id=DEFAULT_MODEL_ID,
        prompts=("first",),
        started_at=1.0,
    )
    for phase in (
        GuidedBoundaryPhase.STARTING,
        GuidedBoundaryPhase.WAITING_FOR_READY,
        GuidedBoundaryPhase.RESOLVING_TURN_SCOPE,
        GuidedBoundaryPhase.RUNNING_AUTO_CHAIN,
        GuidedBoundaryPhase.WAITING_AT_BOUNDARY,
        GuidedBoundaryPhase.WORKFLOW_HANDOFF_OPEN,
        GuidedBoundaryPhase.WAITING_AFTER_CANCEL,
        GuidedBoundaryPhase.FINALIZING,
        GuidedBoundaryPhase.SHUTTING_DOWN,
    ):
        state.advance(phase)
    state.shutdown = {"status": "closing", "detail": ""}

    assert (
        reconcile_closed_event_loop(
            state,
            window_visible=False,
            lifecycle_state="cleanup_pending",
        )
        is False
    )
    assert state.phase is GuidedBoundaryPhase.SHUTTING_DOWN
    assert (
        reconcile_closed_event_loop(
            state,
            window_visible=False,
            lifecycle_state="closed",
        )
        is True
    )
    assert state.phase is GuidedBoundaryPhase.COMPLETED
    assert state.shutdown["status"] == "completed"


def test_validator_accepts_exact_guided_boundary_contract(tmp_path):
    ok, reason = validate_guided_boundary_payload(_valid_payload(tmp_path))

    assert ok is True
    assert reason == ""


def test_validator_rejects_working_copy_at_decision_boundary(tmp_path) -> None:
    payload = _valid_payload(tmp_path)
    waiting = payload["boundary"]["assistant_waiting_surface"]
    waiting["header_status"] = "Local · Working"
    waiting["send_button_text"] = "Working"

    ok, reason = validate_guided_boundary_payload(payload)

    assert ok is False
    assert "presented as active assistant work" in reason


def _publish_valid_current(tmp_path: Path) -> tuple[Path, dict]:
    current_root = tmp_path / "chatpanel-guided-boundary"
    staging = tmp_path / ".chatpanel-guided-boundary-staging-valid"
    staging.mkdir()
    payload = _valid_payload(staging)
    destination, published = publish_guided_boundary_artifact_run(
        staging_dir=staging,
        current_root=current_root,
        payload=payload,
        frozen_source_identity=_SYNTHETIC_CURRENT_SOURCE_IDENTITY,
        run_id="run-valid",
        json_name=JSON_ARTIFACT,
        markdown_name=MARKDOWN_ARTIFACT,
    )
    return destination, published


def test_schema_4_runner_publishes_one_canonical_current_root(tmp_path) -> None:
    current_root, published = _publish_valid_current(tmp_path)

    assert current_root == tmp_path / "chatpanel-guided-boundary"
    assert (current_root / JSON_ARTIFACT).is_file()
    assert (current_root / MARKDOWN_ARTIFACT).is_file()
    stored = json.loads((current_root / JSON_ARTIFACT).read_text(encoding="utf-8"))
    assert stored["schema_version"] == 5
    assert stored["generated_at_utc"]
    assert stored["source_identity"] == _SYNTHETIC_CURRENT_SOURCE_IDENTITY
    for key in (
        "ready",
        "auto_chain_complete",
        "workflow_dialog_open",
        "post_cancel",
    ):
        assert Path(stored["screenshots"][key]).parent == current_root
        assert stored["screenshot_artifacts"][key]["sha256"]
        assert published["screenshots"][key] == stored["screenshots"][key]

    ok, reason = validate_guided_boundary_artifact_root(
        current_root,
        canonical_root=current_root,
        refresh_source_identity=False,
        current_source_identity=_SYNTHETIC_CURRENT_SOURCE_IDENTITY,
    )

    assert ok is True, reason


def test_current_validator_rejects_legacy_current_run_directory(tmp_path) -> None:
    legacy = tmp_path / "current-run-8"
    legacy.mkdir()

    ok, reason = validate_guided_boundary_artifact_root(
        legacy,
        canonical_root=legacy,
        refresh_source_identity=False,
        current_source_identity=_SYNTHETIC_CURRENT_SOURCE_IDENTITY,
    )

    assert ok is False
    assert "current-run-*" in reason


def test_failed_guided_run_does_not_replace_canonical_current(tmp_path) -> None:
    current_root, _published = _publish_valid_current(tmp_path)
    current_json = (current_root / JSON_ARTIFACT).read_bytes()
    staging = tmp_path / ".chatpanel-guided-boundary-staging-failed"
    staging.mkdir()
    failed = _valid_payload(staging)
    failed["status"] = "failed"
    failed["failure_reason"] = "expected failure"

    destination, _payload = publish_guided_boundary_artifact_run(
        staging_dir=staging,
        current_root=current_root,
        payload=failed,
        frozen_source_identity=_SYNTHETIC_CURRENT_SOURCE_IDENTITY,
        run_id="run-failed",
        json_name=JSON_ARTIFACT,
        markdown_name=MARKDOWN_ARTIFACT,
    )

    assert destination == current_root / "runs" / "run-failed"
    assert (destination / JSON_ARTIFACT).is_file()
    assert (current_root / JSON_ARTIFACT).read_bytes() == current_json


def test_unfrozen_passed_run_cannot_replace_canonical_current(tmp_path) -> None:
    current_root, _published = _publish_valid_current(tmp_path)
    current_json = (current_root / JSON_ARTIFACT).read_bytes()
    staging = tmp_path / ".chatpanel-guided-boundary-staging-unfrozen"
    staging.mkdir()
    unfrozen = _valid_payload(staging)
    unfrozen.pop("capture_source")

    destination, payload = publish_guided_boundary_artifact_run(
        staging_dir=staging,
        current_root=current_root,
        payload=unfrozen,
        frozen_source_identity=_SYNTHETIC_CURRENT_SOURCE_IDENTITY,
        run_id="run-unfrozen",
        json_name=JSON_ARTIFACT,
        markdown_name=MARKDOWN_ARTIFACT,
    )

    assert destination == current_root / "runs" / "run-unfrozen"
    assert payload["status"] == "failed"
    assert "not frozen" in payload["failure_reason"]
    assert (current_root / JSON_ARTIFACT).read_bytes() == current_json


def test_cli_freezes_source_only_after_isolated_config_env_restore(
    monkeypatch,
    tmp_path,
) -> None:
    events: list[str] = []
    source_reads = 0

    class Config:
        pass

    def freeze(*_args, **_kwargs):
        nonlocal source_reads
        source_reads += 1
        events.append("source-at-start" if source_reads == 1 else "freeze-source")
        return copy.deepcopy(_SYNTHETIC_CURRENT_SOURCE_IDENTITY)

    def publish(**kwargs):
        events.append("publish-current-contract")
        assert kwargs["frozen_source_identity"] == _SYNTHETIC_CURRENT_SOURCE_IDENTITY
        destination = Path(kwargs["current_root"]) / "runs" / kwargs["run_id"]
        return destination, dict(kwargs["payload"])

    monkeypatch.setattr(
        guided_boundary_runtime, "_enforce_offline_runtime", lambda: None
    )
    monkeypatch.setattr(
        guided_boundary_runtime,
        "_prepare_capture_config",
        lambda _model, _config_dir: (events.append("isolated-config") or Config()),
    )
    monkeypatch.setattr(
        guided_boundary_runtime,
        "_restore_capture_config_env",
        lambda _previous: events.append("restore-config-env"),
    )
    monkeypatch.setattr(
        guided_boundary_runtime,
        "classify_runtime",
        lambda _config: {
            "classification": "model-missing",
            "message": "not installed",
        },
    )
    monkeypatch.setattr(
        guided_boundary_runtime,
        "_runtime_summary",
        lambda value: dict(value),
    )
    monkeypatch.setattr(guided_boundary_runtime, "collect_source_identity", freeze)
    monkeypatch.setattr(
        guided_boundary_runtime,
        "publish_guided_boundary_artifact_run",
        publish,
    )

    result = guided_boundary_runtime.cli_main(
        ["--output-dir", str(tmp_path / "chatpanel-guided-boundary")]
    )

    assert result == 2
    assert events.index("source-at-start") < events.index("isolated-config")
    assert events.index("restore-config-env") < events.index("freeze-source")
    assert events.index("freeze-source") < events.index("publish-current-contract")


def test_cli_source_drift_cannot_publish_canonical_current(
    monkeypatch, tmp_path
) -> None:
    identities = [
        copy.deepcopy(_SYNTHETIC_CURRENT_SOURCE_IDENTITY),
        {
            **copy.deepcopy(_SYNTHETIC_CURRENT_SOURCE_IDENTITY),
            "source_digest": "f" * 64,
        },
    ]
    published: dict[str, object] = {}

    class Config:
        pass

    def publish(**kwargs):
        payload = dict(kwargs["payload"])
        published.update(payload)
        assert payload["status"] == "failed"
        destination = Path(kwargs["current_root"]) / "runs" / kwargs["run_id"]
        return destination, payload

    monkeypatch.setattr(
        guided_boundary_runtime, "_enforce_offline_runtime", lambda: None
    )
    monkeypatch.setattr(
        guided_boundary_runtime,
        "_prepare_capture_config",
        lambda _model, _config_dir: Config(),
    )
    monkeypatch.setattr(
        guided_boundary_runtime,
        "_restore_capture_config_env",
        lambda _previous: None,
    )
    monkeypatch.setattr(
        guided_boundary_runtime,
        "classify_runtime",
        lambda _config: {
            "classification": "model-missing",
            "message": "not installed",
        },
    )
    monkeypatch.setattr(
        guided_boundary_runtime,
        "_runtime_summary",
        lambda value: dict(value),
    )
    monkeypatch.setattr(
        guided_boundary_runtime,
        "collect_source_identity",
        lambda *_args, **_kwargs: identities.pop(0),
    )
    monkeypatch.setattr(
        guided_boundary_runtime,
        "publish_guided_boundary_artifact_run",
        publish,
    )

    result = guided_boundary_runtime.cli_main(
        ["--output-dir", str(tmp_path / "chatpanel-guided-boundary")]
    )

    assert result == 1
    assert published["capture_source"] == {
        "source_digest_at_start": _SYNTHETIC_CURRENT_SOURCE_IDENTITY["source_digest"],
        "source_digest_at_completion": "f" * 64,
        "stable": False,
    }
    assert "discard this run" in str(published["failure_reason"])


def test_live_boundary_validation_does_not_require_terminal_turn_metrics(tmp_path):
    payload = _valid_payload(tmp_path)
    payload["first_turn"]["metrics"] = {
        "completed_turn_count": 0,
        "llm_calls": 0,
        "tool_executions": [],
    }

    ok, reason = validate_auto_chain_boundary(
        source_path=payload["source_path"],
        initial_publication=payload["initial_publication"],
        command_observations=payload["command_observations"],
        first_turn=payload["first_turn"],
        boundary=payload["boundary"],
        require_completed_turn=False,
    )

    assert ok is True
    assert reason == ""


def test_validator_rejects_screenshot_paths_that_do_not_exist(tmp_path):
    payload = _valid_payload(tmp_path)
    payload["screenshots"]["ready"] = str(tmp_path / "missing.png")

    ok, reason = validate_guided_boundary_payload(payload)

    assert ok is False
    assert "screenshot" in reason.lower()


def test_validator_rejects_tampered_screenshot_hash(tmp_path):
    payload = _valid_payload(tmp_path)
    payload["screenshot_artifacts"]["ready"]["sha256"] = "0" * 64

    ok, reason = validate_guided_boundary_payload(payload)

    assert ok is False
    assert "hash" in reason.lower()


def test_validator_rejects_semantically_duplicated_screenshots(tmp_path):
    payload = _valid_payload(tmp_path)
    payload["screenshots"]["post_cancel"] = payload["screenshots"]["ready"]
    payload["screenshot_artifacts"]["post_cancel"] = copy.deepcopy(
        payload["screenshot_artifacts"]["ready"]
    )

    ok, reason = validate_guided_boundary_payload(payload)

    assert ok is False
    assert "duplicated" in reason.lower()


def test_validator_rejects_unreadable_workflow_dialog_screenshot(tmp_path):
    payload = _valid_payload(tmp_path)
    wizard_path = Path(payload["screenshots"]["workflow_dialog_open"])
    wizard_path.write_text("not an image", encoding="utf-8")

    ok, reason = validate_guided_boundary_payload(payload)

    assert ok is False
    assert "screenshot" in reason.lower()


def test_validator_recomputes_visible_transcript_leakage(tmp_path):
    payload = _valid_payload(tmp_path)
    payload["transcript_clean"] = True
    payload["visible_messages"].append(
        {
            "sender": "assistant",
            "text": '{"tool_name":"apply_interpretation","parameters":{}}',
        }
    )

    ok, reason = validate_guided_boundary_payload(payload)

    assert ok is False
    assert "transcript" in reason.lower()


def test_validator_requires_empty_idle_composer_with_disabled_send(tmp_path):
    payload = _valid_payload(tmp_path)
    payload["ui_state"]["send_button_enabled"] = True

    ok, reason = validate_guided_boundary_payload(payload)

    assert ok is False
    assert "idle" in reason.lower()


def test_validator_rejects_noncanonical_proposal_parameters(tmp_path):
    payload = _valid_payload(tmp_path)
    payload["first_turn"]["tool_proposals"][0]["parameters"] = {
        "source_path": "/tmp/a-different-recording.fif"
    }

    ok, reason = validate_guided_boundary_payload(payload)

    assert ok is False
    assert "canonical" in reason.lower()


def test_validator_rejects_normalized_and_actual_parameter_drift(tmp_path):
    payload = _valid_payload(tmp_path)
    payload["first_turn"]["tool_attempts"][0]["actual"]["parameters"] = {
        "source_path": "/tmp/wrong.fif"
    }

    ok, reason = validate_guided_boundary_payload(payload)

    assert ok is False
    assert "actual" in reason.lower()


def test_validator_rejects_host_continuation_marked_as_model_execution(tmp_path):
    payload = _valid_payload(tmp_path)
    payload["first_turn"]["tool_attempts"][1]["actual"]["kind"] = "model_execution"

    ok, reason = validate_guided_boundary_payload(payload)

    assert ok is False
    assert "execution owner" in reason.lower()


def test_validator_rejects_model_payload_on_host_continuation(tmp_path):
    payload = _valid_payload(tmp_path)
    preview_call = payload["first_turn"]["tool_attempts"][1]["canonical"]
    payload["first_turn"]["tool_attempts"][1]["raw"] = preview_call
    payload["first_turn"]["tool_attempts"][1]["normalized"] = preview_call

    ok, reason = validate_guided_boundary_payload(payload)

    assert ok is False
    assert "host continuation" in reason.lower()


@pytest.mark.parametrize(
    "mutate",
    (
        lambda attempt: attempt["actual"].pop("parameters"),
        lambda attempt: attempt["actual"].__setitem__("parameters", "not-an-object"),
        lambda attempt: attempt["canonical"].pop("parameters"),
        lambda attempt: attempt.pop("raw"),
        lambda attempt: attempt.pop("normalized"),
    ),
)
def test_validator_rejects_malformed_host_execution_evidence(mutate, tmp_path):
    payload = _valid_payload(tmp_path)
    mutate(payload["first_turn"]["tool_attempts"][1])

    ok, reason = validate_guided_boundary_payload(payload)

    assert ok is False
    assert "host" in reason.lower() or "canonical" in reason.lower()


@pytest.mark.parametrize(
    "parameters",
    [{"confirmed": True}, {"candidate_id": "model-invented-candidate"}],
)
def test_validator_rejects_any_post_validation_apply_proposal(parameters, tmp_path):
    payload = _valid_payload(tmp_path)
    payload["first_turn"]["tool_proposals"].append(
        {"tool_name": "apply_interpretation", "parameters": parameters}
    )

    ok, reason = validate_guided_boundary_payload(payload)

    assert ok is False
    assert "auto-chain" in reason.lower() or "proposal" in reason.lower()


def test_validator_rejects_legacy_continue_prompt_and_generic_confirmation(tmp_path):
    payload = _valid_payload(tmp_path)
    payload["prompts"].append("Continue with the reviewed recording.")
    payload["confirmation"] = {
        "dialog_title": "Confirm action",
        "command_name": "apply_interpretation",
    }

    ok, reason = validate_guided_boundary_payload(payload)

    assert ok is False
    assert "prompt" in reason.lower() or "confirmation" in reason.lower()


def test_validator_requires_concrete_action_item_summary_in_transcript(tmp_path):
    payload = _valid_payload(tmp_path)
    payload["visible_messages"][1]["text"] = (
        "Review and confirm the data interpretation before applying it."
    )

    ok, reason = validate_guided_boundary_payload(payload)

    assert ok is False
    assert "action-item summary" in reason.lower()


def test_validator_requires_exact_typed_workflow_handoff_fields(tmp_path):
    payload = _valid_payload(tmp_path)
    payload["workflow_handoff"]["request"]["decision_fields"] = ["metadata_review"]

    ok, reason = validate_guided_boundary_payload(payload)

    assert ok is False
    assert "decision fields" in reason.lower()


def test_validator_requires_real_wizard_at_exact_target_step(tmp_path):
    payload = _valid_payload(tmp_path)
    payload["wizard"]["current_step_title"] = "Review and Import"
    payload["wizard"]["current_step_index"] = 4

    ok, reason = validate_guided_boundary_payload(payload)

    assert ok is False
    assert "target step" in reason.lower()


def test_validator_rejects_evidence_without_source_identity(tmp_path):
    payload = _valid_payload(tmp_path)
    payload.pop("source_identity", None)

    ok, reason = validate_guided_boundary_payload(payload)

    assert ok is False
    assert "source identity" in reason.lower()


def test_production_validator_refreshes_current_source_identity_by_default():
    signature = inspect.signature(_validate_guided_boundary_payload)

    assert signature.parameters["refresh_source_identity"].default is True
    assert signature.parameters["current_source_identity"].default is None


def test_production_validator_rejects_test_identity_with_refresh_enabled(tmp_path):
    payload = _valid_payload(tmp_path)

    ok, reason = _validate_guided_boundary_payload(
        payload,
        current_source_identity=payload["source_identity"],
    )

    assert ok is False
    assert "test source identity override" in reason.lower()


def test_production_validator_requires_identity_when_refresh_is_disabled(tmp_path):
    payload = _valid_payload(tmp_path)

    ok, reason = _validate_guided_boundary_payload(
        payload,
        refresh_source_identity=False,
    )

    assert ok is False
    assert "explicit current identity" in reason.lower()


def test_dirty_source_digest_changes_when_content_changes_with_same_status(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git = shutil.which("git")
    assert git is not None
    _run_git(git, repo, "init", "-q")
    _run_git(git, repo, "config", "user.email", "test@example.com")
    _run_git(git, repo, "config", "user.name", "Test")
    source = repo / "module.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    _run_git(git, repo, "add", "module.py")
    _run_git(git, repo, "commit", "-qm", "initial")

    source.write_text("VALUE = 2\n", encoding="utf-8")
    first = collect_source_identity(repo, refresh=True)
    source.write_text("VALUE = 3\n", encoding="utf-8")
    second = collect_source_identity(repo, refresh=True)

    assert first["dirty"] is True
    assert second["dirty"] is True
    assert first["commit_sha"] == second["commit_sha"]
    assert first["head_tree_sha"] == second["head_tree_sha"]
    assert first["dirty_digest"] != second["dirty_digest"]
    assert first["source_digest"] != second["source_digest"]


def test_source_content_digest_survives_committing_identical_worktree_content(
    tmp_path,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    git = shutil.which("git")
    assert git is not None
    _run_git(git, repo, "init", "-q")
    _run_git(git, repo, "config", "user.email", "test@example.com")
    _run_git(git, repo, "config", "user.name", "Test")
    source = repo / "module.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    _run_git(git, repo, "add", "module.py")
    _run_git(git, repo, "commit", "-qm", "initial")

    source.write_text("VALUE = 2\n", encoding="utf-8")
    before_commit = collect_source_identity(repo, refresh=True)
    _run_git(git, repo, "add", "module.py")
    _run_git(git, repo, "commit", "-qm", "source update")
    after_commit = collect_source_identity(repo, refresh=True)

    assert before_commit["commit_sha"] != after_commit["commit_sha"]
    assert before_commit["dirty"] is True
    assert after_commit["dirty"] is False
    assert (
        before_commit["source_content_digest"] == after_commit["source_content_digest"]
    )
    assert validate_source_identity(
        before_commit,
        expected_repo_root=repo,
        refresh=False,
        current_identity=after_commit,
        artifact_name="Test artifact",
    ) == (True, "")


def test_source_content_digest_excludes_generated_artifacts_and_local_settings(
    tmp_path,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    git = shutil.which("git")
    assert git is not None
    _run_git(git, repo, "init", "-q")
    _run_git(git, repo, "config", "user.email", "test@example.com")
    _run_git(git, repo, "config", "user.name", "Test")
    (repo / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "settings.json").write_text('{"local": true}\n', encoding="utf-8")
    artifacts = repo / "artifacts"
    artifacts.mkdir()
    (artifacts / "evidence.json").write_text('{"run": 1}\n', encoding="utf-8")
    _run_git(git, repo, "add", ".")
    _run_git(git, repo, "commit", "-qm", "initial")

    first = collect_source_identity(repo, refresh=True)
    (repo / "settings.json").write_text('{"local": false}\n', encoding="utf-8")
    (artifacts / "evidence.json").write_text('{"run": 2}\n', encoding="utf-8")
    second = collect_source_identity(repo, refresh=True)

    assert first["source_content_digest"] == second["source_content_digest"]
    assert first["dirty_digest"] == second["dirty_digest"]


def test_tool_trace_recorder_observes_normalized_and_actual_parameters():
    class Controller:
        def _select_tool_proposal(self, _command_result):
            return "scan_source", {"source_path": "/tmp/recording.fif"}

        def _execute_tool_no_loop(self, command_name, parameters, *, context=None):
            return command_name, parameters, context

        def _request_tool_confirmation(self, decision, context=None):
            return decision, context

    controller = Controller()
    recorder = GuidedToolTraceRecorder(copy.deepcopy)
    recorder.attach(controller)

    selected = controller._select_tool_proposal(object())
    result = controller._execute_tool_no_loop(*selected, context="current")

    assert result == (
        "scan_source",
        {"source_path": "/tmp/recording.fif"},
        "current",
    )
    assert recorder.snapshot() == [
        {
            "normalized": {
                "tool_name": "scan_source",
                "parameters": {"source_path": "/tmp/recording.fif"},
            },
            "actual": {
                "kind": "model_execution",
                "tool_name": "scan_source",
                "parameters": {"source_path": "/tmp/recording.fif"},
            },
        }
    ]


def test_tool_trace_recorder_marks_unproposed_execution_as_host_owned():
    class Controller:
        def _select_tool_proposal(self, _command_result):
            return None

        def _execute_tool_no_loop(self, command_name, parameters, *, context=None):
            return command_name, parameters, context

    controller = Controller()
    recorder = GuidedToolTraceRecorder(copy.deepcopy)
    recorder.attach(controller)

    result = controller._execute_tool_no_loop(
        "preview_interpretation",
        {},
        context="current",
    )

    assert result == ("preview_interpretation", {}, "current")
    assert recorder.snapshot() == [
        {
            "normalized": None,
            "actual": {
                "kind": "host_execution",
                "tool_name": "preview_interpretation",
                "parameters": {},
            },
        }
    ]


@pytest.mark.parametrize(
    ("structured", "expected"),
    [
        ({"command_name": "scan_source", "ok": True}, True),
        ({"command_name": "scan_source", "ok": False}, False),
    ],
)
def test_application_result_success_uses_current_ok_contract(structured, expected):
    assert _application_result_succeeded(object(), structured) is expected


def test_pre_shutdown_candidate_validation_does_not_require_status_first(
    tmp_path,
    monkeypatch,
) -> None:
    payload = _valid_payload(tmp_path)
    payload["status"] = "running"
    payload["failure_reason"] = ""
    payload["phase_history"] = payload["phase_history"][:8]
    monkeypatch.setattr(
        guided_boundary_driver,
        "validate_guided_boundary_payload",
        validate_guided_boundary_payload,
    )

    ok, reason = _validate_pre_shutdown_candidate(payload)

    assert ok is True
    assert reason == ""


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: payload["first_turn"]["metrics"].__setitem__(
                "llm_calls", 4
            ),
            "format recovery",
        ),
        (
            lambda payload: payload["command_observations"][1][
                "publication"
            ].__setitem__("generation", 2),
            "strictly increase",
        ),
        (
            lambda payload: payload["boundary"]["publication"].__setitem__(
                "stale", True
            ),
            "usable",
        ),
        (
            lambda payload: payload["executed_tools"].append(
                {"name": "apply_interpretation", "success": True}
            ),
            "exactly",
        ),
        (
            lambda payload: payload["first_turn"]["new_tools"].append(
                {"name": "list_files", "success": False}
            ),
            "exactly",
        ),
        (
            lambda payload: payload["post_cancel"].__setitem__(
                "state", {**_state_payload(), "raw": {"loaded": True, "count": 1}}
            ),
            "unchanged",
        ),
        (
            lambda payload: payload["phase_history"].remove("workflow_handoff_open"),
            "phase",
        ),
        (
            lambda payload: payload.__setitem__("workflow_handoff", {}),
            "handoff",
        ),
        (
            lambda payload: payload.__setitem__("wizard", {}),
            "dialog",
        ),
        (
            lambda payload: payload["runtime"].pop("fallback_used"),
            "fallback",
        ),
        (
            lambda payload: payload.__setitem__("transcript_clean", False),
            "transcript",
        ),
        (
            lambda payload: payload.__setitem__("expected_auto_chain", ["scan_source"]),
            "chain contract",
        ),
        (
            lambda payload: payload.__setitem__("claim_boundary", ""),
            "claim boundary",
        ),
    ],
)
def test_validator_fails_closed_on_recovery_stale_extra_or_mutated_state(
    mutate,
    message,
    tmp_path,
):
    payload = _valid_payload(tmp_path)
    mutate(payload)

    ok, reason = validate_guided_boundary_payload(payload)

    assert ok is False
    assert message in reason


def test_validator_rejects_non_terminal_success_status(tmp_path):
    payload = _valid_payload(tmp_path)
    payload["status"] = "running"

    ok, reason = validate_guided_boundary_payload(payload)

    assert ok is False
    assert "status" in reason


def test_capture_and_cancel_real_data_import_workflow_dialog(qtbot, tmp_path):
    dialog = DataInterpretationPreviewDialog(
        scan_result={"source_path": "/tmp/recording.fif"},
        preview={"summary": "Found one EEG recording."},
        validation_decision={
            "decision": "needs_confirmation",
            "action_items": _state_payload()["interpretation"]["action_items"],
        },
        initial_step="Review Metadata",
    )
    qtbot.addWidget(dialog)
    dialog.show()
    request = WorkflowUiHandoffRequest.for_decision(
        "apply_interpretation",
        decision_fields=("metadata_review", "label_matching"),
        request_id="handoff-real-dialog",
    )
    screenshot = tmp_path / "workflow-dialog.png"

    evidence = capture_and_cancel_workflow_dialog(
        dialog,
        request=request,
        controller_request=request,
        host_request=request,
        screenshot_path=screenshot,
        capture=lambda _widget, path: (
            Image.new("RGB", (40, 30), "black").save(path),
            0,
        )[1],
    )

    assert evidence["dialog_class"].endswith(".DataInterpretationPreviewDialog")
    assert evidence["current_step_title"] == "Review Metadata"
    assert evidence["current_step_index"] == 2
    assert evidence["cancel_signal_observed"] is True
    assert evidence["visible_after_cancel_click"] is False
    assert screenshot.is_file()


def test_workflow_dialog_helper_does_not_cancel_wrong_decision_fields(
    qtbot,
    tmp_path,
):
    dialog = DataInterpretationPreviewDialog(
        scan_result={"source_path": "/tmp/recording.fif"},
        preview={"summary": "Found one EEG recording."},
        validation_decision={"decision": "needs_confirmation"},
        initial_step="Review Metadata",
    )
    qtbot.addWidget(dialog)
    dialog.show()
    request = WorkflowUiHandoffRequest.for_decision(
        "apply_interpretation",
        decision_fields=("metadata_review",),
        request_id="wrong-fields",
    )

    with pytest.raises(RuntimeError, match="decision fields"):
        capture_and_cancel_workflow_dialog(
            dialog,
            request=request,
            controller_request=request,
            host_request=request,
            screenshot_path=tmp_path / "must-not-exist.png",
            capture=lambda _widget, _path: 0,
        )

    assert dialog.isVisible() is True


def test_evidence_assembler_preserves_stable_schema():
    state = GuidedBoundaryState(
        source_path="/tmp/recording.fif",
        model_id=DEFAULT_MODEL_ID,
        prompts=("first",),
        started_at=1.0,
    )
    state.status = "failed"
    state.failure_reason = "expected test failure"

    payload = GuidedBoundaryEvidenceAssembler(
        state=state,
        initial_runtime={"classification": "gpu-ready", "model_id": DEFAULT_MODEL_ID},
        runtime_evidence=lambda initial, _snapshot: dict(initial),
        structured_value=lambda value: value,
    ).build()

    assert payload["schema_version"] == 5
    assert payload["walkthrough"] == "adaptive_workflow_ui_handoff_boundary"
    assert payload["expected_auto_chain"] == list(EXPECTED_AUTO_CHAIN)
    assert set(payload["screenshots"]) == {
        "ready",
        "auto_chain_complete",
        "workflow_dialog_open",
        "post_cancel",
        "failure",
    }
    assert "Windows desktop acceptance" in payload["claim_boundary"]
    assert (
        "Real Granite proposes the first scan_source action"
        in payload["claim_boundary"]
    )
    assert "host-assisted product evidence" in payload["claim_boundary"]
    assert "not raw-model or tool-call accuracy" in payload["claim_boundary"]
    assert payload["source_identity"]["source_digest"]
    assert "screenshot_artifacts" in payload


def test_entrypoint_remains_a_thin_composition_root():
    module = inspect.getmodule(main)
    assert module is not None
    source = inspect.getsource(module)
    tree = ast.parse(source)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]

    assert [node.name for node in functions] == ["main"]
    assert not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
        for node in ast.walk(functions[0])
        if node is not functions[0]
    )
    assert len(functions[0].body) <= 4
