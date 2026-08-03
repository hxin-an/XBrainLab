"""Pure evidence contract for the bounded exact-Granite long-session gate."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, TypeGuard, cast

from scripts.dev.local_assistant_capture_runtime import (
    seal_evidence_identity,
    validate_strict_capture_evidence,
)
from XBrainLab.chat_contract import (
    CHAT_HISTORY_LIVE_WINDOW_ROWS,
    CHAT_HISTORY_SCHEMA_VERSION,
    MAX_CHAT_HISTORY_ROWS,
    MAX_CHAT_MODEL_REQUEST_UTF8_BYTES,
    MIN_CHAT_TURN_HISTORY_ROWS,
)
from XBrainLab.llm.core.model_catalog import (
    PRIMARY_LOCAL_MODEL_ID,
    PRIMARY_LOCAL_MODEL_REVISION,
)

ARTIFACT_SCHEMA = "xbrainlab.chatpanel-exact-granite-long-session.v1"
ARTIFACT_MANIFEST_SCHEMA = "xbrainlab.evidence-artifact-manifest.v1"
JSON_ARTIFACT = "chatpanel-exact-granite-long-session.json"
MARKDOWN_ARTIFACT = "chatpanel-exact-granite-long-session.md"
ARTIFACT_MANIFEST = "artifact-manifest.json"

FIRST_PROMPT = (
    "In one short sentence, explain why EEG preprocessing is useful. "
    "Do not run an XBrainLab action."
)
FOLLOWUP_PROMPT = (
    "Check what is ready in the current XBrainLab workflow. Use the state "
    "query tool if needed, then answer in one short sentence."
)
PRUNE_NOTICE = (
    "Older messages were removed from this view to keep the conversation responsive."
)
REQUIRED_SCREENSHOTS = ("prune_boundary", "current_state_followup")

SEED_ROW_COUNT = MAX_CHAT_HISTORY_ROWS - MIN_CHAT_TURN_HISTORY_ROWS + 1
SEED_TURN_COUNT = SEED_ROW_COUNT // 2
EXPECTED_PRUNED_ROWS = SEED_ROW_COUNT - CHAT_HISTORY_LIVE_WINDOW_ROWS
REAL_USER_TURN_COUNT = 2
MAX_MODEL_GENERATION_REQUESTS = 5
MAX_TURN_SECONDS = 150
MODEL_GENERATION_TIMEOUT_SECONDS = 60
MODEL_MAX_NEW_TOKENS = 96

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40,64}$")
_UNTRUSTED_SCHEMA = "xbrainlab.untrusted_context.v1"
_CLAIM_PHRASES = (
    "host-assisted",
    "not raw-model accuracy",
    "not thesis evidence",
    "not windows",
)


def build_seed_archive() -> list[dict[str, object]]:
    """Build the smallest deterministic persisted transcript that forces a prune."""
    rows: list[dict[str, object]] = []
    for row_index in range(SEED_ROW_COUNT):
        turn_index = row_index // 2
        is_user = row_index % 2 == 0
        role = "user" if is_user else "assistant"
        content = (
            f"Archived checkpoint {turn_index}: obsolete workflow prose from the "
            "host-seeded transcript. Current ApplicationService state is authoritative."
        )
        rows.append(
            {
                "schema_version": CHAT_HISTORY_SCHEMA_VERSION,
                "role": role,
                "content": content,
                "presentation_kind": role,
                "message_id": f"long-session-seed-{row_index:04d}",
                "presentation_id": "",
                "actions": [],
                "action_state": "none",
            }
        )
    return rows


def seed_archive_descriptor() -> dict[str, object]:
    """Return a path-free identity for the deterministic in-memory archive."""
    archive = build_seed_archive()
    return {
        "kind": "host-seeded-persisted-chat-history",
        "schema_version": CHAT_HISTORY_SCHEMA_VERSION,
        "archive_count": 1,
        "row_count": len(archive),
        "turn_count": len(archive) // 2,
        "sha256": _canonical_sha256(archive),
    }


def generation_request_observation(
    request: object,
    *,
    sequence: int,
    turn_index: int,
    backend_generation: int | None,
) -> dict[str, object]:
    """Project one real worker request into bounded, path-free evidence."""
    to_model_messages = getattr(request, "to_model_messages", None)
    if not callable(to_model_messages):
        raise ValueError("Generation request does not expose model messages.")
    raw_messages = to_model_messages()
    if not isinstance(raw_messages, Sequence) or isinstance(raw_messages, str | bytes):
        raise ValueError("Generation request messages are not a sequence.")
    messages = [dict(item) for item in raw_messages if isinstance(item, Mapping)]
    if len(messages) != len(raw_messages):
        raise ValueError("Generation request contains an unstructured message.")

    latest_user_text = _latest_user_text(messages)
    workflow_stage = _workflow_stage(messages)
    response_contract = getattr(request, "response_contract", None)
    response_contract_value = str(
        getattr(response_contract, "value", response_contract) or ""
    )
    if not latest_user_text:
        raise ValueError("Generation request omitted the latest user turn.")
    if response_contract_value == "structured_action" and not workflow_stage:
        raise ValueError("Generation request omitted workflow publication context.")
    if workflow_stage:
        observed_backend_generation: int | None = _positive_int(
            backend_generation,
            "backend_generation",
        )
    elif backend_generation is None:
        observed_backend_generation = None
    else:
        raise ValueError(
            "Generation request reported a backend generation without workflow "
            "publication context."
        )

    encoded = json.dumps(
        messages,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    response_contract = getattr(request, "response_contract", None)
    return {
        "sequence": _positive_int(sequence, "sequence"),
        "turn_index": _positive_int(turn_index, "turn_index"),
        "generation_id": _positive_int(
            getattr(request, "generation_id", 0),
            "generation_id",
        ),
        "latest_user_text": latest_user_text,
        "workflow_stage": workflow_stage,
        "backend_generation": observed_backend_generation,
        "request_sha256": hashlib.sha256(encoded).hexdigest(),
        "request_utf8_bytes": len(encoded),
        "response_contract": response_contract_value,
    }


def application_command_result_observation(
    result: object,
    *,
    sequence: int,
    turn_index: int,
) -> dict[str, object]:
    """Project one authoritative read-only result into path-free evidence."""
    tool_name = getattr(result, "tool_name", None)
    command_name = getattr(result, "command_name", None)
    message = getattr(result, "message", None)
    diagnostics = _mapping(getattr(result, "diagnostics", None))
    state = _mapping(getattr(result, "state", None))
    ok = getattr(result, "ok", None)
    if type(ok) is not bool:
        raise ValueError("Application command result omitted its success state.")
    if not isinstance(tool_name, str) or not tool_name:
        raise ValueError("Application command result omitted its tool name.")
    if not isinstance(command_name, str) or not command_name:
        raise ValueError("Application command result omitted its command name.")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("Application command result omitted its visible message.")
    pipeline_stage = state.get("pipeline_stage")
    if not isinstance(pipeline_stage, str) or not pipeline_stage:
        raise ValueError("Application command result omitted its pipeline stage.")

    return {
        "sequence": _positive_int(sequence, "sequence"),
        "turn_index": _positive_int(turn_index, "turn_index"),
        "tool_name": tool_name,
        "command_name": command_name,
        "ok": ok,
        "publication_generation": _positive_int(
            diagnostics.get("publication_generation"),
            "publication_generation",
        ),
        "publication_revision": _positive_int(
            diagnostics.get("publication_revision"),
            "publication_revision",
        ),
        "pipeline_stage": pipeline_stage,
        "message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
    }


def validate_capture_source_identity(
    source: Mapping[str, object],
) -> tuple[bool, str]:
    """Reject a dirty or incomplete source before model startup."""
    if not _sealed_identity_matches("source", source):
        return False, "Capture source identity is unsealed or inconsistent."
    if source.get("dirty") is not False:
        return False, "Exact Granite capture requires a clean source checkout."
    if (
        not _GIT_SHA.fullmatch(str(source.get("commit_sha") or ""))
        or not _GIT_SHA.fullmatch(str(source.get("head_tree_sha") or ""))
        or not _SHA256.fullmatch(str(source.get("dirty_fingerprint") or ""))
        or not _SHA256.fullmatch(str(source.get("source_content_sha256") or ""))
    ):
        return False, "Capture source identity is incomplete."
    return True, ""


def validate_capture_model_identity(
    model: Mapping[str, object],
) -> tuple[bool, str]:
    """Reject any cache that is not the complete pinned Granite snapshot."""
    if not _sealed_identity_matches("model", model):
        return False, "Model cache identity is unsealed or inconsistent."
    if (
        model.get("requested_model_id") != PRIMARY_LOCAL_MODEL_ID
        or model.get("loaded_model_id") != PRIMARY_LOCAL_MODEL_ID
        or model.get("loaded_revision") != PRIMARY_LOCAL_MODEL_REVISION
        or model.get("cache_complete") is not True
        or model.get("loader_policy") != "pinned-local-files-only"
        or not _SHA256.fullmatch(str(model.get("snapshot_manifest_sha256") or ""))
        or not _is_positive_int(model.get("snapshot_file_count"))
        or not _is_positive_int(model.get("snapshot_total_bytes"))
    ):
        return False, "Model cache is not the complete pinned exact Granite snapshot."
    return True, ""


def validate_long_session_evidence(
    payload: Mapping[str, object],
    *,
    strict: bool = True,
    artifact_root: Path | None = None,
    current_source_identity: Mapping[str, object] | None = None,
    current_model_identity: Mapping[str, object] | None = None,
) -> tuple[bool, str]:
    """Fail closed unless every bounded long-session observation is present."""
    if payload.get("schema") != ARTIFACT_SCHEMA:
        return False, "Long-session evidence schema is missing or unsupported."
    if strict and payload.get("status") != "passed":
        return False, "Only a passed long-session capture is strict evidence."

    runtime = _mapping(payload.get("runtime"))
    if (
        runtime.get("requested_model_id") != PRIMARY_LOCAL_MODEL_ID
        or runtime.get("loaded_model_id") != PRIMARY_LOCAL_MODEL_ID
    ):
        return False, "Requested and loaded models must be exact Granite."

    ok, reason = _validate_archive(_mapping(payload.get("archive")))
    if not ok:
        return False, reason
    counts = _mapping(payload.get("counts"))
    ok, reason = _validate_counts(counts)
    if not ok:
        return False, reason
    ok, reason = _validate_prune_events(payload.get("prune_events"))
    if not ok:
        return False, reason
    ok, reason = _validate_external_state_change(
        _mapping(payload.get("external_state_change"))
    )
    if not ok:
        return False, reason
    ok, reason = _validate_generation_requests(payload.get("generation_requests"))
    if not ok:
        return False, reason
    ok, reason = _validate_turns(payload.get("turns"))
    if not ok:
        return False, reason
    ok, reason = _validate_application_command_results(
        payload.get("application_command_results"),
        external_change=_mapping(payload.get("external_state_change")),
        turns=payload.get("turns"),
    )
    if not ok:
        return False, reason
    ok, reason = _validate_cross_counts(
        counts,
        generation_requests=payload.get("generation_requests"),
        application_command_results=payload.get("application_command_results"),
        turns=payload.get("turns"),
    )
    if not ok:
        return False, reason
    ok, reason = _validate_current_state_followup(
        _mapping(payload.get("current_state_followup")),
        application_command_results=payload.get("application_command_results"),
        external_change=_mapping(payload.get("external_state_change")),
        turns=payload.get("turns"),
    )
    if not ok:
        return False, reason
    ok, reason = _validate_ui_state(_mapping(payload.get("ui_state")))
    if not ok:
        return False, reason
    ok, reason = _validate_timing(_mapping(payload.get("timing")))
    if not ok:
        return False, reason

    cache_capture = _mapping(payload.get("capture_model_cache"))
    model_identity = _mapping(runtime.get("model_identity"))
    model_digest = str(model_identity.get("identity_sha256") or "")
    if (
        cache_capture.get("stable") is not True
        or cache_capture.get("access") != "read-only-preexisting"
        or cache_capture.get("identity_at_start") != model_digest
        or cache_capture.get("identity_at_completion") != model_digest
    ):
        return False, "Model cache identity changed during capture."

    assistance = _mapping(payload.get("host_assistance"))
    actions = assistance.get("actions")
    if (
        assistance.get("classification") != "host-assisted"
        or assistance.get("used") is not True
        or not isinstance(actions, list)
        or len(actions) < 4
    ):
        return False, "Host assistance was not recorded completely."

    screenshots = _mapping(payload.get("screenshots"))
    if any(not screenshots.get(name) for name in REQUIRED_SCREENSHOTS):
        return False, "Required long-session screenshots are missing."

    outcome = _mapping(payload.get("outcome"))
    if (
        outcome.get("result") != "passed"
        or outcome.get("bounded") is not True
        or outcome.get("archive_boundary_observed") is not True
        or outcome.get("current_state_used") is not True
    ):
        return False, "Long-session outcome observations are incomplete."

    limitations = payload.get("limitations")
    if not isinstance(limitations, list) or len(limitations) < 4:
        return False, "Long-session evidence limitations are incomplete."
    claim_boundary = str(payload.get("claim_boundary") or "").lower()
    if any(phrase not in claim_boundary for phrase in _CLAIM_PHRASES):
        return False, "Claim boundary omits host assistance or excluded claims."

    if strict:
        return validate_strict_capture_evidence(
            payload,
            current_source_identity=current_source_identity,
            current_model_identity=current_model_identity,
            artifact_root=artifact_root,
        )
    return True, ""


def render_markdown(payload: Mapping[str, object]) -> str:
    """Render a concise review surface for the machine-validated evidence."""
    runtime = _mapping(payload.get("runtime"))
    model = _mapping(runtime.get("model_identity"))
    source = _mapping(payload.get("source_identity"))
    archive = _mapping(payload.get("archive"))
    counts = _mapping(payload.get("counts"))
    timing = _mapping(payload.get("timing"))
    state_change = _mapping(payload.get("external_state_change"))
    before = _mapping(state_change.get("before"))
    after = _mapping(state_change.get("after"))
    screenshots = _mapping(payload.get("screenshot_artifacts"))

    lines = [
        "# ChatPanel Exact Granite Long-Session Evidence",
        "",
        f"- status: `{payload.get('status', '')}`",
        f"- failure reason: {payload.get('failure_reason') or 'none'}",
        f"- requested model: `{runtime.get('requested_model_id', '')}`",
        f"- loaded model: `{runtime.get('loaded_model_id', '')}`",
        f"- loaded revision: `{model.get('loaded_revision', '')}`",
        f"- model cache snapshot: `{model.get('snapshot_manifest_sha256', '')}`",
        f"- source commit: `{source.get('commit_sha', '')}`",
        f"- source identity: `{source.get('identity_sha256', '')}`",
        f"- screenshot aggregate: `{screenshots.get('aggregate_sha256', '')}`",
        "",
        "## Bounded Session",
        "",
        f"- seeded archive SHA-256: `{archive.get('sha256', '')}`",
        f"- seeded archive rows: `{counts.get('seeded_archive_rows', 0)}`",
        f"- seeded archive turns: `{counts.get('seeded_archive_turns', 0)}`",
        f"- real user turns: `{counts.get('real_user_turns', 0)}`",
        f"- model generation requests: `{counts.get('model_generation_requests', 0)}`",
        f"- application command results: `{counts.get('application_command_results', 0)}`",
        f"- prune events: `{counts.get('prune_events', 0)}`",
        f"- pruned rows: `{counts.get('pruned_rows', 0)}`",
        f"- external state changes: `{counts.get('external_state_changes', 0)}`",
        "",
        "## Current-State Observation",
        "",
        f"- command spine: `{state_change.get('command_spine', '')}`",
        f"- command: `{state_change.get('command', '')}`",
        f"- stage before: `{before.get('pipeline_stage', '')}`",
        f"- stage after: `{after.get('pipeline_stage', '')}`",
        f"- follow-up: {FOLLOWUP_PROMPT}",
        "",
        "## Timing",
        "",
        f"- timeout seconds: `{timing.get('timeout_seconds', 0)}`",
        f"- command elapsed seconds: `{timing.get('command_elapsed_seconds', 0)}`",
        f"- per-turn limit seconds: `{timing.get('max_turn_seconds', 0)}`",
        f"- model generation timeout seconds: `{timing.get('model_generation_timeout_seconds', 0)}`",
        "",
        "## Host Assistance",
        "",
    ]
    assistance = _mapping(payload.get("host_assistance"))
    for action in _list(assistance.get("actions")):
        lines.append(f"- {action}")
    lines.extend(["", "## Limitations", ""])
    for limitation in _list(payload.get("limitations")):
        lines.append(f"- {limitation}")
    lines.extend(
        [
            "",
            "## Claim Boundary",
            "",
            str(payload.get("claim_boundary") or ""),
            "",
            f"Artifact hashes are recorded in `{ARTIFACT_MANIFEST}`.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def publish_evidence_bundle(output_dir: Path, payload: Mapping[str, object]) -> None:
    """Publish evidence plus a hash manifest under the caller's output root."""
    root = output_dir.expanduser().resolve(strict=True)
    if payload.get("status") == "passed":
        ok, reason = validate_long_session_evidence(payload, artifact_root=root)
        if not ok:
            raise ValueError(f"Refusing to publish invalid strict evidence: {reason}")

    json_path = root / JSON_ARTIFACT
    markdown_path = root / MARKDOWN_ARTIFACT
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")

    relative_paths = [JSON_ARTIFACT, MARKDOWN_ARTIFACT]
    screenshot_evidence = _mapping(payload.get("screenshot_artifacts"))
    for raw_record in _mapping(screenshot_evidence.get("artifacts")).values():
        relative_path = str(_mapping(raw_record).get("relative_path") or "")
        if relative_path:
            relative_paths.append(relative_path)
    artifact_records = _artifact_records(root, relative_paths)
    manifest = {
        "schema": ARTIFACT_MANIFEST_SCHEMA,
        "evidence_schema": payload.get("schema"),
        "artifacts": artifact_records,
        "aggregate_sha256": _canonical_sha256(artifact_records),
    }
    (root / ARTIFACT_MANIFEST).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    ok, reason = _validate_artifact_manifest(root, payload)
    if not ok:
        raise ValueError(f"Published artifact bundle is invalid: {reason}")


def validate_artifact_directory(
    output_dir: Path,
    *,
    current_source_identity: Mapping[str, object] | None = None,
    current_model_identity: Mapping[str, object] | None = None,
) -> tuple[bool, str]:
    """Revalidate strict semantics and every published artifact byte."""
    try:
        root = output_dir.expanduser().resolve(strict=True)
        payload = json.loads((root / JSON_ARTIFACT).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"Evidence artifact is missing or invalid: {exc}"
    if not isinstance(payload, Mapping):
        return False, "Evidence artifact root is not an object."
    ok, reason = validate_long_session_evidence(
        payload,
        artifact_root=root,
        current_source_identity=current_source_identity,
        current_model_identity=current_model_identity,
    )
    if not ok:
        return False, reason
    return _validate_artifact_manifest(root, payload)


def _validate_archive(archive: Mapping[str, object]) -> tuple[bool, str]:
    expected = seed_archive_descriptor()
    if any(archive.get(key) != value for key, value in expected.items()):
        return False, "Host-seeded transcript archive identity is invalid."
    if (
        archive.get("restored_row_count") != expected["row_count"]
        or archive.get("retained") is not False
    ):
        return False, "Persisted transcript archive was not restored exactly in memory."
    return True, ""


def _validate_counts(counts: Mapping[str, object]) -> tuple[bool, str]:
    expected = {
        "seeded_archive_count": 1,
        "seeded_archive_rows": SEED_ROW_COUNT,
        "seeded_archive_turns": SEED_TURN_COUNT,
        "real_user_turns": REAL_USER_TURN_COUNT,
        "terminal_turns": REAL_USER_TURN_COUNT,
        "prune_events": 1,
        "pruned_rows": EXPECTED_PRUNED_ROWS,
        "external_state_changes": 1,
    }
    if any(counts.get(key) != value for key, value in expected.items()):
        return False, "Turn, prune, archive, or state-change counts are inconsistent."
    if counts.get("application_command_results") != 1:
        return False, "Application command result count is missing or inconsistent."
    model_requests = counts.get("model_generation_requests")
    if not _is_int_between(model_requests, 1, MAX_MODEL_GENERATION_REQUESTS):
        return False, "Model generation request count is missing or unbounded."
    return True, ""


def _validate_prune_events(value: object) -> tuple[bool, str]:
    events = _list(value)
    if len(events) != 1:
        return False, "Exactly one real transcript prune event is required."
    event = _mapping(events[0])
    if (
        event.get("turn_index") != 1
        or event.get("rows_before") != SEED_ROW_COUNT
        or event.get("rows_pruned") != EXPECTED_PRUNED_ROWS
        or event.get("rows_after_prune") != CHAT_HISTORY_LIVE_WINDOW_ROWS
        or event.get("oldest_seed_removed") is not True
        or event.get("retained_seed_observed") is not True
        or event.get("notice") != PRUNE_NOTICE
    ):
        return (
            False,
            "Observed transcript prune boundary is incomplete or inconsistent.",
        )
    return True, ""


def _validate_external_state_change(change: Mapping[str, object]) -> tuple[bool, str]:
    before = _mapping(change.get("before"))
    after = _mapping(change.get("after"))
    if (
        change.get("command_spine") != "ApplicationService.execute"
        or change.get("command") != "reset_session"
        or change.get("confirmed") is not True
        or change.get("result_ok") is not True
        or before.get("pipeline_stage") != "data_loaded"
        or after.get("pipeline_stage") != "empty"
    ):
        return False, "External ApplicationService state change was not observed."
    if (
        not _increased(before.get("generation"), after.get("generation"))
        or not _increased(before.get("revision"), after.get("revision"))
        or change.get("assistant_projection_revision") != after.get("revision")
    ):
        return False, "External state publication did not advance and reach ChatPanel."
    return True, ""


def _validate_generation_requests(
    value: object,
) -> tuple[bool, str]:
    requests = [_mapping(item) for item in _list(value)]
    if not _is_int_between(len(requests), 1, MAX_MODEL_GENERATION_REQUESTS):
        return (
            False,
            "Real model generation observations are missing or unbounded.",
        )
    if [item.get("sequence") for item in requests] != list(range(1, len(requests) + 1)):
        return False, "Model generation request sequence is not contiguous."
    for request in requests:
        if (
            request.get("turn_index") != 1
            or not _is_positive_int(request.get("generation_id"))
            or not _SHA256.fullmatch(str(request.get("request_sha256") or ""))
            or not _is_int_between(
                request.get("request_utf8_bytes"),
                1,
                MAX_CHAT_MODEL_REQUEST_UTF8_BYTES,
            )
            or request.get("response_contract")
            not in {"natural_language", "structured_action"}
        ):
            return False, "A model generation request observation is invalid."

    if any(
        item.get("latest_user_text") != FIRST_PROMPT
        or item.get("workflow_stage") != ""
        or item.get("backend_generation") is not None
        or item.get("response_contract") != "natural_language"
        for item in requests
    ):
        return False, "First informational turn exposed workflow-only context."
    return True, ""


def _validate_turns(value: object) -> tuple[bool, str]:
    turns = [_mapping(item) for item in _list(value)]
    if len(turns) != REAL_USER_TURN_COUNT:
        return False, "Exactly two real ChatPanel turns are required."
    expected_prompts = (FIRST_PROMPT, FOLLOWUP_PROMPT)
    for index, (turn, prompt) in enumerate(
        zip(turns, expected_prompts, strict=True),
        start=1,
    ):
        if (
            turn.get("index") != index
            or turn.get("prompt") != prompt
            or turn.get("terminal_outcome") != "completed"
            or turn.get("assistant_text_source") != "product_runtime"
            or not str(turn.get("assistant_text") or "").strip()
            or not _is_number_between(
                turn.get("elapsed_seconds"),
                0.0,
                float(MAX_TURN_SECONDS),
                exclusive_minimum=True,
            )
        ):
            return False, f"Real ChatPanel turn {index} is incomplete or unbounded."
        model_request_count = turn.get("model_request_count")
        if index == 1 and not _is_int_between(
            model_request_count,
            1,
            MAX_MODEL_GENERATION_REQUESTS,
        ):
            return False, "The explanatory turn did not use bounded model generation."
        if index == 2 and model_request_count != 0:
            return (
                False,
                "The read-only state query unexpectedly used model generation.",
            )
        ok, reason = _validate_turn_transcript_delta(
            turn,
            prompt=prompt,
            expected_rows_pruned=EXPECTED_PRUNED_ROWS if index == 1 else 0,
        )
        if not ok:
            return False, f"Real ChatPanel turn {index}: {reason}"
    if _list(turns[0].get("new_tools")):
        return False, "The explanatory first turn unexpectedly executed a tool."
    query_tools = [
        _mapping(item)
        for item in _list(turns[1].get("new_tools"))
        if _mapping(item).get("name") == "query_state"
    ]
    if len(query_tools) != 1 or query_tools[0].get("success") is not True:
        return False, "Follow-up did not execute query_state successfully exactly once."
    if any(
        _mapping(item).get("success") is True
        and _mapping(item).get("name") != "query_state"
        for item in _list(turns[1].get("new_tools"))
    ):
        return False, "Follow-up executed an unrelated workflow tool."
    return True, ""


def _validate_application_command_results(
    value: object,
    *,
    external_change: Mapping[str, object],
    turns: object,
) -> tuple[bool, str]:
    results = [_mapping(item) for item in _list(value)]
    if len(results) != 1:
        return False, "Exactly one post-change application command result is required."
    result = results[0]
    after = _mapping(external_change.get("after"))
    turn_records = [_mapping(item) for item in _list(turns)]
    assistant_text = (
        str(turn_records[1].get("assistant_text") or "")
        if len(turn_records) == REAL_USER_TURN_COUNT
        else ""
    )
    if (
        result.get("sequence") != 1
        or result.get("turn_index") != 2
        or result.get("tool_name") != "query_state"
        or result.get("command_name") != "query_state"
        or result.get("ok") is not True
        or result.get("publication_generation") != after.get("generation")
        or result.get("publication_revision") != after.get("revision")
        or result.get("pipeline_stage") != after.get("pipeline_stage")
        or result.get("message_sha256")
        != hashlib.sha256(assistant_text.encode("utf-8")).hexdigest()
    ):
        return False, "Post-change query_state command result is inconsistent."
    return True, ""


def _validate_turn_transcript_delta(
    turn: Mapping[str, object],
    *,
    prompt: str,
    expected_rows_pruned: int,
) -> tuple[bool, str]:
    delta = _mapping(turn.get("transcript_delta"))
    rows_before = delta.get("rows_before")
    rows_pruned = delta.get("rows_pruned")
    rows_added = delta.get("rows_added")
    rows_after = delta.get("rows_after")
    bubble_count_before = delta.get("bubble_count_before")
    bubble_count_after = delta.get("bubble_count_after")
    rows_before_value = cast(int, rows_before) if _is_positive_int(rows_before) else 0
    if (
        rows_before_value == 0
        or rows_pruned != expected_rows_pruned
        or rows_added != 2
        or rows_after != rows_before_value - expected_rows_pruned + 2
        or not _is_int_between(bubble_count_before, 0, rows_before_value)
        or bubble_count_after != rows_after
    ):
        return False, "transcript row and bubble delta parity is missing."

    new_rows = [_mapping(item) for item in _list(delta.get("new_rows"))]
    if len(new_rows) != 2 or [row.get("role") for row in new_rows] != [
        "user",
        "assistant",
    ]:
        return False, "transcript did not add one user and one assistant row."
    message_ids = [str(row.get("message_id") or "") for row in new_rows]
    if any(not message_id for message_id in message_ids) or len(set(message_ids)) != 2:
        return False, "transcript delta message identities are missing or duplicated."
    assistant_text = str(turn.get("assistant_text") or "")
    expected_hashes = [
        hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        hashlib.sha256(assistant_text.encode("utf-8")).hexdigest(),
    ]
    if [row.get("content_sha256") for row in new_rows] != expected_hashes:
        return False, "transcript row contents do not match the observed turn."
    if _list(delta.get("bubble_tail_ids")) != message_ids:
        return False, "ChatPanel bubble tail does not match the new transcript rows."
    return True, ""


def _validate_cross_counts(
    counts: Mapping[str, object],
    *,
    generation_requests: object,
    application_command_results: object,
    turns: object,
) -> tuple[bool, str]:
    requests = _list(generation_requests)
    command_results = _list(application_command_results)
    turn_records = [_mapping(item) for item in _list(turns)]
    observed_turn_requests = sum(
        int(turn.get("model_request_count") or 0) for turn in turn_records
    )
    if counts.get("model_generation_requests") != len(
        requests
    ) or observed_turn_requests != len(requests):
        return False, "Turn and model generation request counts are inconsistent."
    if counts.get("application_command_results") != len(command_results):
        return False, "Application command result counts are inconsistent."
    return True, ""


def _validate_ui_state(ui_state: Mapping[str, object]) -> tuple[bool, str]:
    if (
        not str(ui_state.get("send_button_text") or "").strip()
        or ui_state.get("input_enabled") is not True
        or ui_state.get("chat_processing") is not False
        or ui_state.get("controller_processing") is not False
        or ui_state.get("runtime_turn_in_flight") is not False
    ):
        return False, "Final ChatPanel UI state is missing or not idle."
    return True, ""


def _validate_current_state_followup(
    followup: Mapping[str, object],
    *,
    application_command_results: object,
    external_change: Mapping[str, object],
    turns: object,
) -> tuple[bool, str]:
    results = [
        _mapping(item)
        for item in _list(application_command_results)
        if _mapping(item).get("turn_index") == 2
    ]
    after = _mapping(external_change.get("after"))
    turn_records = [_mapping(item) for item in _list(turns)]
    assistant_text = (
        str(turn_records[1].get("assistant_text") or "")
        if len(turn_records) == REAL_USER_TURN_COUNT
        else ""
    )
    result = results[0] if len(results) == 1 else {}
    if (
        followup.get("prompt") != FOLLOWUP_PROMPT
        or followup.get("expected_pipeline_stage") != "empty"
        or followup.get("expected_workflow_stage") != "No data loaded"
        or followup.get("admission_path") != "deterministic_read_only"
        or followup.get("model_generation_bypassed") is not True
        or followup.get("observed_pipeline_stage") != result.get("pipeline_stage")
        or followup.get("observed_pipeline_stage") != after.get("pipeline_stage")
        or followup.get("observed_publication_generation")
        != result.get("publication_generation")
        or followup.get("observed_publication_revision")
        != result.get("publication_revision")
        or followup.get("assistant_text") != assistant_text
        or followup.get("query_state_success") is not True
    ):
        return (
            False,
            "Current-state follow-up observations are missing or inconsistent.",
        )
    return True, ""


def _validate_timing(timing: Mapping[str, object]) -> tuple[bool, str]:
    timeout_seconds = timing.get("timeout_seconds")
    elapsed_seconds = timing.get("command_elapsed_seconds")
    if not _is_int_between(timeout_seconds, 1, 600):
        return False, "Capture timeout is missing or unbounded."
    if not _is_number_between(
        elapsed_seconds,
        0.0,
        float(timeout_seconds),
        exclusive_minimum=True,
    ):
        return False, "Capture exceeded its timeout budget."
    if (
        timing.get("max_turn_seconds") != MAX_TURN_SECONDS
        or timing.get("model_generation_timeout_seconds")
        != MODEL_GENERATION_TIMEOUT_SECONDS
    ):
        return False, "Per-turn or model timing policy is inconsistent."
    return True, ""


def _artifact_records(
    root: Path,
    relative_paths: Sequence[str],
) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    for raw_relative in sorted(set(relative_paths)):
        relative = Path(raw_relative)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Artifact path is not contained by the output directory.")
        resolved = (root / relative).resolve(strict=True)
        resolved.relative_to(root)
        file_stat = resolved.lstat()
        if not stat.S_ISREG(file_stat.st_mode):
            raise ValueError(f"Artifact is not a regular file: {raw_relative}")
        content = resolved.read_bytes()
        completed_stat = resolved.stat()
        if completed_stat.st_size != file_stat.st_size:
            raise OSError(f"Artifact changed while hashing: {raw_relative}")
        records[relative.as_posix()] = {
            "sha256": hashlib.sha256(content).hexdigest(),
            "byte_size": len(content),
        }
    return records


def _validate_artifact_manifest(
    root: Path,
    payload: Mapping[str, object],
) -> tuple[bool, str]:
    try:
        manifest = json.loads((root / ARTIFACT_MANIFEST).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"Artifact hash manifest is missing or invalid: {exc}"
    if not isinstance(manifest, Mapping):
        return False, "Artifact hash manifest root is not an object."
    if manifest.get("schema") != ARTIFACT_MANIFEST_SCHEMA or manifest.get(
        "evidence_schema"
    ) != payload.get("schema"):
        return False, "Artifact hash manifest schema is inconsistent."
    raw_artifacts = manifest.get("artifacts")
    if not isinstance(raw_artifacts, Mapping) or not raw_artifacts:
        return False, "Artifact hash manifest contains no artifacts."
    expected_paths = [JSON_ARTIFACT, MARKDOWN_ARTIFACT]
    screenshot_evidence = _mapping(payload.get("screenshot_artifacts"))
    for raw_record in _mapping(screenshot_evidence.get("artifacts")).values():
        relative_path = str(_mapping(raw_record).get("relative_path") or "")
        if relative_path:
            expected_paths.append(relative_path)
    if set(raw_artifacts) != set(expected_paths):
        return False, "Artifact hash manifest file set is inconsistent."
    try:
        current = _artifact_records(root, expected_paths)
    except (OSError, ValueError) as exc:
        return False, f"Published artifact is missing or unsafe: {exc}"
    if current != dict(raw_artifacts):
        return False, "A published artifact was mutated after capture."
    if manifest.get("aggregate_sha256") != _canonical_sha256(current):
        return False, "Artifact aggregate hash is inconsistent."
    return True, ""


def _latest_user_text(messages: Sequence[Mapping[str, object]]) -> str:
    for message in reversed(messages):
        content = message.get("content")
        if message.get("role") != "user" or not isinstance(content, str):
            continue
        if _untrusted_payload(content) is None:
            return content
    return ""


def _workflow_stage(messages: Sequence[Mapping[str, object]]) -> str:
    for message in messages:
        content = message.get("content")
        if not isinstance(content, str):
            continue
        payload = _untrusted_payload(content)
        if payload is None:
            continue
        for raw_item in _list(payload.get("items")):
            item = _mapping(raw_item)
            source = _mapping(item.get("source"))
            data = _mapping(item.get("data"))
            stage = data.get("workflow_stage")
            if (
                item.get("type") == "workflow_decision"
                and source.get("kind") == "application_service_publication"
                and isinstance(stage, str)
                and stage
            ):
                return stage
    return ""


def _untrusted_payload(content: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None
    if (
        not isinstance(payload, Mapping)
        or payload.get("schema") != _UNTRUSTED_SCHEMA
        or payload.get("trust") != "untrusted"
    ):
        return None
    return dict(payload)


def _sealed_identity_matches(kind: str, value: Mapping[str, object]) -> bool:
    digest = str(value.get("identity_sha256") or "")
    return bool(
        _SHA256.fullmatch(digest)
        and seal_evidence_identity(kind, value).get("identity_sha256") == digest
    )


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _positive_int(value: object, name: str) -> int:
    if not _is_positive_int(value):
        raise ValueError(f"{name} must be a positive integer.")
    return value


def _is_positive_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_int_between(
    value: object,
    minimum: int,
    maximum: int,
) -> TypeGuard[int]:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and minimum <= value <= maximum
    )


def _is_number_between(
    value: object,
    minimum: float,
    maximum: float,
    *,
    exclusive_minimum: bool = False,
) -> bool:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    numeric = float(value)
    lower_ok = numeric > minimum if exclusive_minimum else numeric >= minimum
    return lower_ok and numeric <= maximum


def _increased(before: object, after: object) -> bool:
    if not _is_positive_int(before) or not _is_positive_int(after):
        return False
    return after > before
