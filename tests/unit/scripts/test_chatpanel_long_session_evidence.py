from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image

from scripts.dev.chatpanel_long_session.evidence import (
    ARTIFACT_MANIFEST,
    ARTIFACT_SCHEMA,
    FIRST_PROMPT,
    FOLLOWUP_PROMPT,
    JSON_ARTIFACT,
    MARKDOWN_ARTIFACT,
    REQUIRED_SCREENSHOTS,
    build_seed_archive,
    generation_request_observation,
    publish_evidence_bundle,
    render_markdown,
    seed_archive_descriptor,
    validate_artifact_directory,
    validate_long_session_evidence,
)
from scripts.dev.local_assistant_capture_runtime import (
    collect_screenshot_evidence,
    seal_evidence_identity,
)
from XBrainLab.chat_contract import (
    CHAT_HISTORY_LIVE_WINDOW_ROWS,
    MAX_CHAT_HISTORY_ROWS,
    MIN_CHAT_TURN_HISTORY_ROWS,
)
from XBrainLab.llm.core.model_catalog import (
    PRIMARY_LOCAL_MODEL_ID,
    PRIMARY_LOCAL_MODEL_REVISION,
)


def _transcript_delta(
    *,
    rows_before: int,
    rows_pruned: int,
    prompt: str,
    assistant_text: str,
    turn_index: int,
) -> dict[str, object]:
    message_ids = [f"turn-{turn_index}-user", f"turn-{turn_index}-assistant"]
    return {
        "rows_before": rows_before,
        "rows_pruned": rows_pruned,
        "rows_added": 2,
        "rows_after": rows_before - rows_pruned + 2,
        "bubble_count_before": rows_before,
        "bubble_count_after": rows_before - rows_pruned + 2,
        "bubble_tail_ids": message_ids,
        "new_rows": [
            {
                "message_id": message_ids[0],
                "role": "user",
                "content_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            },
            {
                "message_id": message_ids[1],
                "role": "assistant",
                "content_sha256": hashlib.sha256(
                    assistant_text.encode("utf-8")
                ).hexdigest(),
            },
        ],
    }


def _strict_payload() -> dict[str, Any]:
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
            "dimensions": [620, 760],
        }
        for index, name in enumerate(REQUIRED_SCREENSHOTS, start=1)
    }
    archive = seed_archive_descriptor()
    expected_pruned = (
        MAX_CHAT_HISTORY_ROWS
        - MIN_CHAT_TURN_HISTORY_ROWS
        + 1
        - CHAT_HISTORY_LIVE_WINDOW_ROWS
    )
    first_assistant_text = "Preprocessing makes EEG signals easier to analyze."
    second_assistant_text = "No data is loaded, so import EEG data next."
    generation_requests = [
        {
            "sequence": 1,
            "turn_index": 1,
            "generation_id": 11,
            "latest_user_text": FIRST_PROMPT,
            "workflow_stage": "",
            "backend_generation": None,
            "request_sha256": "1" * 64,
            "request_utf8_bytes": 4096,
            "response_contract": "natural_language",
        },
        {
            "sequence": 2,
            "turn_index": 2,
            "generation_id": 12,
            "latest_user_text": FOLLOWUP_PROMPT,
            "workflow_stage": "No data loaded",
            "backend_generation": 5,
            "request_sha256": "2" * 64,
            "request_utf8_bytes": 4200,
            "response_contract": "structured_action",
        },
        {
            "sequence": 3,
            "turn_index": 2,
            "generation_id": 13,
            "latest_user_text": FOLLOWUP_PROMPT,
            "workflow_stage": "No data loaded",
            "backend_generation": 5,
            "request_sha256": "3" * 64,
            "request_utf8_bytes": 4500,
            "response_contract": "structured_action",
        },
    ]
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
            "generation_policy": {
                "max_new_tokens": 96,
                "timeout_seconds": 60,
                "do_sample": False,
            },
        },
        "source_identity": source_identity,
        "capture_source": {
            "identity_at_start": source_identity["identity_sha256"],
            "identity_at_completion": source_identity["identity_sha256"],
            "stable": True,
        },
        "capture_model_cache": {
            "identity_at_start": model_identity["identity_sha256"],
            "identity_at_completion": model_identity["identity_sha256"],
            "stable": True,
            "access": "read-only-preexisting",
        },
        "hf_offline": {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        },
        "host_assistance": {
            "classification": "host-assisted",
            "used": True,
            "actions": [
                "restored the deterministic persisted transcript archive",
                "seeded a lightweight data-loaded ApplicationService precondition",
                "submitted two bounded prompts through ChatPanel",
                "executed confirmed reset_session through ApplicationService",
            ],
        },
        "screenshots": {name: f"{name}.png" for name in REQUIRED_SCREENSHOTS},
        "screenshot_artifacts": {
            "artifacts": screenshot_records,
            "aggregate_sha256": seal_evidence_identity(
                "screenshots",
                screenshot_records,
            )["identity_sha256"],
        },
        "archive": {
            **archive,
            "restored_row_count": archive["row_count"],
            "retained": False,
        },
        "counts": {
            "seeded_archive_count": 1,
            "seeded_archive_rows": archive["row_count"],
            "seeded_archive_turns": archive["turn_count"],
            "real_user_turns": 2,
            "terminal_turns": 2,
            "model_generation_requests": len(generation_requests),
            "prune_events": 1,
            "pruned_rows": expected_pruned,
            "external_state_changes": 1,
        },
        "prune_events": [
            {
                "turn_index": 1,
                "rows_before": archive["row_count"],
                "rows_pruned": expected_pruned,
                "rows_after_prune": CHAT_HISTORY_LIVE_WINDOW_ROWS,
                "oldest_seed_removed": True,
                "retained_seed_observed": True,
                "notice": (
                    "Older messages were removed from this view to keep the "
                    "conversation responsive."
                ),
            }
        ],
        "turns": [
            {
                "index": 1,
                "prompt": FIRST_PROMPT,
                "elapsed_seconds": 12.0,
                "terminal_outcome": "completed",
                "assistant_text": first_assistant_text,
                "assistant_text_source": "product_runtime",
                "model_request_count": 1,
                "new_tools": [],
                "transcript_delta": _transcript_delta(
                    rows_before=archive["row_count"],
                    rows_pruned=expected_pruned,
                    prompt=FIRST_PROMPT,
                    assistant_text=first_assistant_text,
                    turn_index=1,
                ),
            },
            {
                "index": 2,
                "prompt": FOLLOWUP_PROMPT,
                "elapsed_seconds": 18.0,
                "terminal_outcome": "completed",
                "assistant_text": second_assistant_text,
                "assistant_text_source": "product_runtime",
                "model_request_count": 2,
                "new_tools": [
                    {"name": "query_state", "success": True, "duration_ms": 4.0}
                ],
                "transcript_delta": _transcript_delta(
                    rows_before=CHAT_HISTORY_LIVE_WINDOW_ROWS + 2,
                    rows_pruned=0,
                    prompt=FOLLOWUP_PROMPT,
                    assistant_text=second_assistant_text,
                    turn_index=2,
                ),
            },
        ],
        "generation_requests": generation_requests,
        "external_state_change": {
            "command_spine": "ApplicationService.execute",
            "command": "reset_session",
            "confirmed": True,
            "result_ok": True,
            "before": {
                "pipeline_stage": "data_loaded",
                "generation": 4,
                "revision": 8,
            },
            "after": {
                "pipeline_stage": "empty",
                "generation": 5,
                "revision": 9,
            },
            "assistant_projection_revision": 9,
        },
        "current_state_followup": {
            "prompt": FOLLOWUP_PROMPT,
            "expected_pipeline_stage": "empty",
            "expected_workflow_stage": "No data loaded",
            "observed_workflow_stages": ["No data loaded", "No data loaded"],
            "observed_backend_generations": [5, 5],
            "query_state_success": True,
        },
        "timing": {
            "timeout_seconds": 360,
            "command_elapsed_seconds": 80.0,
            "max_turn_seconds": 150,
            "model_generation_timeout_seconds": 60,
        },
        "outcome": {
            "result": "passed",
            "bounded": True,
            "archive_boundary_observed": True,
            "current_state_used": True,
        },
        "ui_state": {
            "send_button_text": "Send",
            "input_enabled": True,
            "chat_processing": False,
            "controller_processing": False,
            "runtime_turn_in_flight": False,
        },
        "shutdown": {"status": "completed", "detail": ""},
        "limitations": [
            "The persisted transcript archive and initial data-loaded state were host-seeded.",
            "Only two real user turns were inferred; this is not an endurance test.",
            "This does not evaluate RAG behavior or Windows native interaction.",
            "This is not raw-model accuracy, tool-call scoring, or thesis evidence.",
        ],
        "claim_boundary": (
            "This is host-assisted exact-Granite long-session product evidence, "
            "not raw-model accuracy, not thesis evidence, and not Windows native "
            "acceptance or long-duration endurance evidence."
        ),
    }


def test_seed_archive_is_deterministic_valid_shape_at_smallest_prune_boundary() -> None:
    first = build_seed_archive()
    second = build_seed_archive()
    descriptor = seed_archive_descriptor()
    row_count = descriptor["row_count"]
    turn_count = descriptor["turn_count"]

    assert first == second
    assert row_count == (MAX_CHAT_HISTORY_ROWS - MIN_CHAT_TURN_HISTORY_ROWS + 1)
    assert isinstance(row_count, int)
    assert isinstance(turn_count, int)
    assert turn_count * 2 == row_count
    assert descriptor["sha256"] == seed_archive_descriptor()["sha256"]
    assert [row["role"] for row in first[:4]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert len({row["message_id"] for row in first}) == len(first)


class _Request:
    generation_id = 17
    response_contract = type("Contract", (), {"value": "structured_action"})()

    def to_model_messages(self) -> list[dict[str, str]]:
        context = json.dumps(
            {
                "schema": "xbrainlab.untrusted_context.v1",
                "trust": "untrusted",
                "items": [
                    {
                        "type": "workflow_decision",
                        "source": {"kind": "application_service_publication"},
                        "data": {"workflow_stage": "No data loaded"},
                    }
                ],
            }
        )
        return [
            {"role": "system", "content": "bounded system prompt"},
            {"role": "user", "content": context},
            {"role": "user", "content": FOLLOWUP_PROMPT},
        ]


def test_generation_observation_hashes_request_and_extracts_current_publication() -> (
    None
):
    observation = generation_request_observation(
        _Request(),
        sequence=2,
        turn_index=2,
        backend_generation=5,
    )

    assert observation["latest_user_text"] == FOLLOWUP_PROMPT
    assert observation["workflow_stage"] == "No data loaded"
    assert observation["backend_generation"] == 5
    request_sha256 = observation["request_sha256"]
    request_utf8_bytes = observation["request_utf8_bytes"]
    assert isinstance(request_sha256, str)
    assert isinstance(request_utf8_bytes, int)
    assert len(request_sha256) == 64
    assert request_utf8_bytes > 0


def test_generation_observation_fails_closed_without_workflow_context() -> None:
    request = _Request()
    request.to_model_messages = lambda: [  # type: ignore[method-assign]
        {"role": "user", "content": FOLLOWUP_PROMPT}
    ]

    try:
        generation_request_observation(
            request,
            sequence=1,
            turn_index=2,
            backend_generation=5,
        )
    except ValueError as exc:
        assert "workflow publication" in str(exc).lower()
    else:  # pragma: no cover - assertion branch
        raise AssertionError("Missing workflow context must fail closed.")


def test_generation_observation_accepts_bounded_natural_language_turn_without_state() -> (
    None
):
    request = _Request()
    request.response_contract = type(  # type: ignore[assignment]
        "Contract",
        (),
        {"value": "natural_language"},
    )()
    request.to_model_messages = lambda: [  # type: ignore[method-assign]
        {"role": "system", "content": "bounded informational policy"},
        {"role": "user", "content": FIRST_PROMPT},
    ]

    observation = generation_request_observation(
        request,
        sequence=1,
        turn_index=1,
        backend_generation=None,
    )

    assert observation["latest_user_text"] == FIRST_PROMPT
    assert observation["workflow_stage"] == ""
    assert observation["backend_generation"] is None
    assert observation["response_contract"] == "natural_language"


def test_strict_validator_accepts_complete_bounded_long_session() -> None:
    ok, reason = validate_long_session_evidence(_strict_payload())

    assert ok is True
    assert reason == ""


def test_strict_validator_requires_per_turn_transcript_and_bubble_parity() -> None:
    missing = _strict_payload()
    missing["turns"][0].pop("transcript_delta")

    ok, reason = validate_long_session_evidence(missing)

    assert ok is False
    assert "transcript" in reason.lower()

    wrong_bubble_tail = _strict_payload()
    wrong_bubble_tail["turns"][1]["transcript_delta"]["bubble_tail_ids"].reverse()
    ok, reason = validate_long_session_evidence(wrong_bubble_tail)
    assert ok is False
    assert "bubble" in reason.lower()


def test_strict_validator_rejects_wrong_model_and_dirty_source() -> None:
    wrong_model = _strict_payload()
    wrong_model["runtime"]["loaded_model_id"] = "microsoft/Phi-4-mini-instruct"
    ok, reason = validate_long_session_evidence(wrong_model)
    assert ok is False
    assert "exact granite" in reason.lower()

    dirty = _strict_payload()
    dirty_source = seal_evidence_identity(
        "source",
        {**dirty["source_identity"], "dirty": True},
    )
    dirty["source_identity"] = dirty_source
    dirty["capture_source"] = {
        "identity_at_start": dirty_source["identity_sha256"],
        "identity_at_completion": dirty_source["identity_sha256"],
        "stable": True,
    }
    ok, reason = validate_long_session_evidence(dirty)
    assert ok is False
    assert "clean source" in reason.lower()


def test_strict_validator_rejects_source_or_cache_drift() -> None:
    source_drift = _strict_payload()
    source_drift["capture_source"]["stable"] = False
    ok, reason = validate_long_session_evidence(source_drift)
    assert ok is False
    assert "source identity changed" in reason.lower()

    cache_drift = _strict_payload()
    cache_drift["capture_model_cache"]["identity_at_completion"] = "f" * 64
    cache_drift["capture_model_cache"]["stable"] = False
    ok, reason = validate_long_session_evidence(cache_drift)
    assert ok is False
    assert "model cache" in reason.lower()


def test_strict_validator_requires_real_prune_and_host_archive_identity() -> None:
    payload = _strict_payload()
    payload["prune_events"] = []
    payload["counts"]["prune_events"] = 0

    ok, reason = validate_long_session_evidence(payload)

    assert ok is False
    assert "prune" in reason.lower()

    payload = _strict_payload()
    payload["archive"]["sha256"] = "0" * 64
    ok, reason = validate_long_session_evidence(payload)
    assert ok is False
    assert "archive identity" in reason.lower()


def test_strict_validator_requires_post_change_model_observation_and_state_tool() -> (
    None
):
    payload = _strict_payload()
    payload["generation_requests"] = payload["generation_requests"][:1]

    ok, reason = validate_long_session_evidence(payload)

    assert ok is False
    assert "follow-up" in reason.lower()

    payload = _strict_payload()
    payload["turns"][1]["new_tools"] = []
    payload["current_state_followup"]["query_state_success"] = False
    ok, reason = validate_long_session_evidence(payload)
    assert ok is False
    assert "query_state" in reason.lower()


def test_strict_validator_rejects_cross_count_or_missing_idle_ui_observation() -> None:
    payload = _strict_payload()
    payload["counts"]["model_generation_requests"] = 2

    ok, reason = validate_long_session_evidence(payload)

    assert ok is False
    assert "request counts" in reason.lower()

    payload = _strict_payload()
    payload["ui_state"] = {}
    ok, reason = validate_long_session_evidence(payload)
    assert ok is False
    assert "ui state" in reason.lower()


def test_strict_validator_rejects_timeout_and_missing_claim_boundary() -> None:
    payload = _strict_payload()
    payload["timing"]["command_elapsed_seconds"] = 361.0

    ok, reason = validate_long_session_evidence(payload)

    assert ok is False
    assert "timeout" in reason.lower()

    payload = _strict_payload()
    payload["claim_boundary"] = "Host-assisted walkthrough."
    ok, reason = validate_long_session_evidence(payload)
    assert ok is False
    assert "claim boundary" in reason.lower()


def test_artifact_manifest_hashes_every_published_file_and_detects_mutation(
    tmp_path: Path,
) -> None:
    payload = _strict_payload()
    screenshot_paths: dict[str, Path] = {}
    for index, name in enumerate(REQUIRED_SCREENSHOTS, start=1):
        path = tmp_path / f"{name}.png"
        Image.new("RGB", (32, 24), color=(index * 30, 40, 90)).save(path)
        screenshot_paths[name] = path
    payload["screenshot_artifacts"] = collect_screenshot_evidence(
        screenshot_paths,
        artifact_root=tmp_path,
    )

    publish_evidence_bundle(tmp_path, payload)

    ok, reason = validate_artifact_directory(tmp_path)
    assert ok is True
    assert reason == ""
    manifest = json.loads((tmp_path / ARTIFACT_MANIFEST).read_text(encoding="utf-8"))
    assert set(manifest["artifacts"]) == {
        JSON_ARTIFACT,
        MARKDOWN_ARTIFACT,
        *(f"{name}.png" for name in REQUIRED_SCREENSHOTS),
    }
    assert all(len(record["sha256"]) == 64 for record in manifest["artifacts"].values())

    (tmp_path / MARKDOWN_ARTIFACT).write_text("mutated\n", encoding="utf-8")
    ok, reason = validate_artifact_directory(tmp_path)
    assert ok is False
    assert "mutated" in reason.lower()


def test_markdown_exposes_counts_identity_timing_and_limitations() -> None:
    markdown = render_markdown(_strict_payload())

    assert "# ChatPanel Exact Granite Long-Session Evidence" in markdown
    assert PRIMARY_LOCAL_MODEL_ID in markdown
    assert PRIMARY_LOCAL_MODEL_REVISION in markdown
    assert "seeded archive turns: `249`" in markdown
    assert "prune events: `1`" in markdown
    assert "external state changes: `1`" in markdown
    assert "command elapsed seconds: `80.0`" in markdown
    assert "not raw-model accuracy" in markdown
