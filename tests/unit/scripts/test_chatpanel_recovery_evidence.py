from __future__ import annotations

import copy

from scripts.dev.chatpanel_recovery.evidence import (
    ARTIFACT_SCHEMA,
    BLOCKED_PROMPT,
    CANCELLATION_PROMPT,
    EXPECTED_PRECONDITION_COMMANDS,
    EXPECTED_RECOVERY_COMMANDS,
    PRIOR_EVIDENCE_AUDIT,
    render_markdown,
    validate_recovery_evidence,
)
from scripts.dev.chatpanel_recovery.runtime import finalize_walkthrough_after_shutdown
from scripts.dev.local_assistant_capture_runtime import seal_evidence_identity
from XBrainLab.llm.core.model_catalog import (
    PRIMARY_LOCAL_MODEL_ID,
    PRIMARY_LOCAL_MODEL_REVISION,
)
from XBrainLab.product_language import ASSISTANT_CANCELLED_MESSAGE


def _strict_payload() -> dict[str, object]:
    source_identity = seal_evidence_identity(
        "source",
        {
            "branch": "stabilize/product-quality-closure",
            "commit_sha": "a" * 40,
            "head_tree_sha": "b" * 40,
            "dirty": False,
            "dirty_fingerprint": "c" * 64,
            "source_content_sha256": "d" * 64,
        },
    )
    model_identity = seal_evidence_identity(
        "model",
        {
            "requested_model_id": PRIMARY_LOCAL_MODEL_ID,
            "loaded_model_id": PRIMARY_LOCAL_MODEL_ID,
            "loaded_revision": PRIMARY_LOCAL_MODEL_REVISION,
            "snapshot_manifest_sha256": "e" * 64,
            "snapshot_file_count": 13,
            "snapshot_total_bytes": 5_071_897_172,
            "cache_complete": True,
            "loader_policy": "pinned-local-files-only",
        },
    )
    screenshot_records = {
        name: {
            "relative_path": f"{name}.png",
            "sha256": f"{index:x}" * 64,
            "byte_size": 1000 + index,
            "dimensions": [796, 796],
        }
        for index, name in enumerate(
            (
                "ready",
                "blocked_retry",
                "recovery_complete",
                "cancel_in_flight",
                "cancel_stopping",
                "cancelled_terminal",
            ),
            start=1,
        )
    }
    return {
        "schema": ARTIFACT_SCHEMA,
        "status": "passed",
        "failure_reason": "",
        "runtime": {
            "classification": "gpu-ready",
            "phase": "ready",
            "initialized": True,
            "requested_model_id": PRIMARY_LOCAL_MODEL_ID,
            "loaded_model_id": PRIMARY_LOCAL_MODEL_ID,
            "model_identity": model_identity,
        },
        "source_identity": source_identity,
        "capture_source": {
            "identity_at_start": source_identity["identity_sha256"],
            "identity_at_completion": source_identity["identity_sha256"],
            "stable": True,
        },
        "host_assistance": {
            "classification": "host-assisted",
            "used": True,
            "actions": [
                "submitted the blocked prompt through ChatPanel",
                "prepared dataset-ready state through ApplicationService",
                "clicked the visible Retry last request control",
                "submitted and stopped one informational ChatPanel turn",
            ],
        },
        "screenshot_artifacts": {
            "artifacts": screenshot_records,
            "aggregate_sha256": seal_evidence_identity(
                "screenshots",
                screenshot_records,
            )["identity_sha256"],
        },
        "hf_offline": {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        },
        "screenshots": {name: f"{name}.png" for name in screenshot_records},
        "prior_evidence_audit": copy.deepcopy(PRIOR_EVIDENCE_AUDIT),
        "scenario": {
            "precondition": {
                "command_spine": "ApplicationService.execute",
                "commands": [
                    {"command": command, "ok": True}
                    for command in EXPECTED_PRECONDITION_COMMANDS
                ],
                "dataset_available": True,
                "training_configured": True,
                "fixture": {
                    "kind": "synthetic_fif",
                    "display_name": "recovery_raw.fif",
                    "sha256": "f" * 64,
                    "retained": False,
                },
            },
            "blocked": {
                "prompt": BLOCKED_PROMPT,
                "presentation_kind": "attention",
                "assistant_text": (
                    "Review results is not available yet: Create a training plan "
                    "before evaluating results."
                ),
                "new_tools": [],
                "terminal_outcome": "completed",
                "retry_control": {
                    "visible": True,
                    "enabled": True,
                    "accessible_name": "Retry last request",
                },
            },
            "host_recovery": {
                "command_spine": "ApplicationService.execute",
                "commands": [
                    {"command": command, "ok": True}
                    for command in EXPECTED_RECOVERY_COMMANDS
                ],
                "training_finished": True,
                "evaluation_available": True,
                "terminal_outcome": "completed",
                "post_training_saliency_phase": "succeeded",
                "publication_generation": 12,
                "publication_revision": 15,
                "assistant_projection_revision": 15,
                "publication_stable_samples": 3,
                "output_retained": False,
            },
            "retry": {
                "prompt": BLOCKED_PROMPT,
                "same_prompt": True,
                "invoked_via": "Retry last request",
                "presentation_kind": "assistant",
                "assistant_text": "Evaluation summary ready.",
                "model_proposals": [{"tool_name": "evaluate", "parameters": {}}],
                "model_calls": 1,
                "new_tools": [
                    {
                        "name": "evaluate",
                        "success": True,
                        "duration_ms": 20.0,
                    }
                ],
                "terminal_outcome": "completed",
            },
            "cancellation": {
                "prompt": CANCELLATION_PROMPT,
                "in_flight": {
                    "observed": True,
                    "send_button_text": "Stop",
                    "cancelability": "cancellable",
                    "primary_status": "Working on your request",
                    "generation_dispatch_phase": "started",
                    "model_calls": 1,
                    "application_command_in_flight": False,
                    "correlation": {"generation": 1, "turn_id": 3},
                },
                "stop_clicked": True,
                "stopping_observed": True,
                "assistant_text": ASSISTANT_CANCELLED_MESSAGE,
                "presentation_kind": "cancelled",
                "terminal_outcome": "cancelled",
                "new_tools": [],
            },
        },
        "ui_state": {
            "send_button_text": "Send",
            "input_enabled": True,
            "chat_processing": False,
            "controller_processing": False,
            "runtime_turn_in_flight": False,
        },
        "shutdown": {"status": "completed", "detail": ""},
        "claim_boundary": (
            "Host-assisted exact-Granite recovery evidence, not raw-model accuracy, "
            "thesis scoring, or Windows acceptance."
        ),
        "elapsed_seconds": 80.0,
    }


def test_validate_recovery_evidence_accepts_complete_strict_scenario() -> None:
    ok, reason = validate_recovery_evidence(_strict_payload())

    assert ok is True
    assert reason == ""


def test_validate_recovery_evidence_rejects_dirty_source_as_strict() -> None:
    payload = _strict_payload()
    dirty_source = seal_evidence_identity(
        "source",
        {
            **dict(payload["source_identity"]),
            "dirty": True,
        },
    )
    payload["source_identity"] = dirty_source
    payload["capture_source"] = {
        "identity_at_start": dirty_source["identity_sha256"],
        "identity_at_completion": dirty_source["identity_sha256"],
        "stable": True,
    }

    ok, reason = validate_recovery_evidence(payload)

    assert ok is False
    assert "clean source" in reason.lower()


def test_finalize_walkthrough_status_runs_after_completed_shutdown() -> None:
    payload = _strict_payload()
    payload["status"] = "running"

    finalize_walkthrough_after_shutdown(payload)

    assert payload["status"] == "passed"
    assert payload["failure_reason"] == ""


def test_validate_recovery_evidence_requires_visible_block_and_retry() -> None:
    payload = _strict_payload()
    payload["scenario"]["blocked"]["retry_control"]["visible"] = False  # type: ignore[index]

    ok, reason = validate_recovery_evidence(payload)

    assert ok is False
    assert "retry" in reason.lower()


def test_validate_recovery_evidence_requires_same_prompt_model_owned_recovery() -> None:
    payload = _strict_payload()
    retry = payload["scenario"]["retry"]  # type: ignore[index]
    retry["same_prompt"] = False
    retry["model_proposals"] = []

    ok, reason = validate_recovery_evidence(payload)

    assert ok is False
    assert "same blocked prompt" in reason.lower()


def test_validate_recovery_evidence_rejects_host_named_granite_output() -> None:
    payload = _strict_payload()
    retry = payload["scenario"]["retry"]  # type: ignore[index]
    retry["assistant_text_source"] = "deterministic host Granite output"

    ok, reason = validate_recovery_evidence(payload)

    assert ok is False
    assert "fabricated" in reason.lower()


def test_validate_recovery_evidence_requires_started_cancellable_turn() -> None:
    payload = _strict_payload()
    in_flight = payload["scenario"]["cancellation"]["in_flight"]  # type: ignore[index]
    in_flight["generation_dispatch_phase"] = "accepted"

    ok, reason = validate_recovery_evidence(payload)

    assert ok is False
    assert "started generation" in reason.lower()


def test_validate_recovery_evidence_requires_typed_cancelled_terminal() -> None:
    payload = _strict_payload()
    cancellation = payload["scenario"]["cancellation"]  # type: ignore[index]
    cancellation["terminal_outcome"] = "completed"

    ok, reason = validate_recovery_evidence(payload)

    assert ok is False
    assert "cancelled terminal" in reason.lower()


def test_validate_recovery_evidence_requires_real_applicationservice_commands() -> None:
    payload = _strict_payload()
    recovery = payload["scenario"]["host_recovery"]  # type: ignore[index]
    recovery["commands"] = recovery["commands"][:-1]

    ok, reason = validate_recovery_evidence(payload)

    assert ok is False
    assert "applicationservice" in reason.lower()


def test_validate_recovery_evidence_requires_training_configured_precondition() -> None:
    payload = _strict_payload()
    precondition = payload["scenario"]["precondition"]  # type: ignore[index]
    precondition["training_configured"] = False

    ok, reason = validate_recovery_evidence(payload)

    assert ok is False
    assert "precondition" in reason.lower()


def test_validate_recovery_evidence_requires_terminal_stable_publication() -> None:
    payload = _strict_payload()
    recovery = payload["scenario"]["host_recovery"]  # type: ignore[index]
    recovery["publication_stable_samples"] = 1
    recovery["assistant_projection_revision"] = 14

    ok, reason = validate_recovery_evidence(payload)

    assert ok is False
    assert "quiescent" in reason.lower()


def test_render_markdown_records_identity_observations_and_limits() -> None:
    markdown = render_markdown(_strict_payload())

    assert "# ChatPanel Exact Granite Recovery Walkthrough" in markdown
    assert PRIMARY_LOCAL_MODEL_ID in markdown
    assert PRIMARY_LOCAL_MODEL_REVISION in markdown
    assert "Blocked command and visible Retry" in markdown
    assert "Cancellable in-flight turn" in markdown
    assert "Host Assistance" in markdown
    assert "bounded terminal shutdown" in markdown.lower()
    assert "not raw-model accuracy" in markdown
