"""Lazy-loaded runtime for bounded exact-Granite long-session evidence."""

from __future__ import annotations

import hashlib
import os
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMainWindow, QToolButton

from scripts.dev.bounded_qt_shutdown import BoundedQtShutdown
from scripts.dev.capture_chatpanel_local_pipeline_chain_walkthrough import (
    assistant_surface_ready,
    runtime_evidence,
)
from scripts.dev.capture_chatpanel_local_tool_chain_walkthrough import _runtime_summary
from scripts.dev.capture_chatpanel_local_walkthrough import collect_executed_tools
from scripts.dev.capture_human_like_product_walkthrough import capture_widget
from scripts.dev.chatpanel_long_session.evidence import (
    ARTIFACT_MANIFEST,
    ARTIFACT_SCHEMA,
    EXPECTED_PRUNED_ROWS,
    FIRST_PROMPT,
    FOLLOWUP_PROMPT,
    JSON_ARTIFACT,
    MARKDOWN_ARTIFACT,
    MAX_MODEL_GENERATION_REQUESTS,
    MAX_TURN_SECONDS,
    MODEL_GENERATION_TIMEOUT_SECONDS,
    MODEL_MAX_NEW_TOKENS,
    PRUNE_NOTICE,
    REQUIRED_SCREENSHOTS,
    SEED_ROW_COUNT,
    SEED_TURN_COUNT,
    build_seed_archive,
    generation_request_observation,
    publish_evidence_bundle,
    seed_archive_descriptor,
    validate_artifact_directory,
    validate_capture_model_identity,
    validate_capture_source_identity,
    validate_long_session_evidence,
)
from scripts.dev.local_assistant_capture_runtime import (
    collect_capture_source_identity,
    collect_model_identity,
    finalize_strict_capture_evidence,
    isolated_assistant_runtime_config,
)
from XBrainLab.backend.application import ResetSessionCommand, get_application_service
from XBrainLab.backend.controller.chat_controller import (
    ChatMessageRecord,
    ChatMessageRole,
)
from XBrainLab.backend.study import Study
from XBrainLab.llm.agent.turn import AssistantTurnTerminal
from XBrainLab.llm.core.model_catalog import PRIMARY_LOCAL_MODEL_ID
from XBrainLab.ui.chat.message_bubble import MessageBubble
from XBrainLab.ui.components.agent_manager import AgentManager

_POLL_INTERVAL_MS = 100
_SCREENSHOT_FILENAMES = {
    "prune_boundary": "chatpanel-long-session-prune-boundary.png",
    "current_state_followup": "chatpanel-long-session-current-state.png",
}
_HOST_ACTIONS = (
    "restored one deterministic 498-row persisted transcript archive in memory",
    "seeded a lightweight data-loaded precondition without retaining an EEG file",
    "submitted two bounded prompts through the real ChatPanel composer",
    "executed confirmed reset_session externally through ApplicationService.execute",
    "captured the prune boundary and post-reset follow-up from the real ChatPanel",
)
_LIMITATIONS = (
    "The persisted transcript archive and initial data-loaded state were host-seeded.",
    "Only two real user turns were inferred; this is not an endurance test.",
    "This does not evaluate RAG behavior or Windows native interaction.",
    "This is not raw-model accuracy, tool-call scoring, or thesis evidence.",
)
_CLAIM_BOUNDARY = (
    "This is host-assisted exact-Granite long-session product evidence, not "
    "raw-model accuracy, not thesis evidence, and not Windows native acceptance "
    "or long-duration endurance evidence."
)


def _layout_bubble_ids(manager: AgentManager) -> list[str]:
    panel = manager.chat_panel
    if panel is None:
        return []
    message_ids: list[str] = []
    for index in range(panel.chat_layout.count()):
        item = panel.chat_layout.itemAt(index)
        widget = item.widget() if item is not None else None
        if not isinstance(widget, MessageBubble):
            continue
        message_id = widget.property("chatMessageId")
        if not isinstance(message_id, str) or not message_id:
            return []
        message_ids.append(message_id)
    return message_ids


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class _SeededRawState:
    """Minimal host precondition consumed only by ApplicationService read models."""

    def __init__(self, filepath: str) -> None:
        self._filepath = filepath

    def get_filepath(self) -> str:
        return self._filepath

    def get_filename(self) -> str:
        return "host-seeded-session.fif"

    def get_subject_name(self) -> str:
        return "bounded-session"

    def get_session_name(self) -> str:
        return "long-session-gate"

    def get_mne(self) -> object:
        return type("SeededMneShape", (), {"ch_names": ["C3", "C4"]})()

    def get_preprocess_history(self) -> list[str]:
        return []


def run_capture(
    *,
    output_dir: Path,
    cache_dir: Path,
    requested_model_id: str,
    timeout_seconds: int,
) -> int:
    """Capture, seal, publish, then revalidate one bounded product session."""
    command_started = time.monotonic()
    source_at_start = collect_capture_source_identity(refresh=True)
    source_ok, source_reason = validate_capture_source_identity(source_at_start)
    if not source_ok:
        return _publish_preflight_failure(
            output_dir,
            failure_reason=source_reason,
            command_started=command_started,
            timeout_seconds=timeout_seconds,
            source_identity=source_at_start,
        )
    if requested_model_id != PRIMARY_LOCAL_MODEL_ID:
        return _publish_preflight_failure(
            output_dir,
            failure_reason="Only the exact Granite product model is accepted.",
            command_started=command_started,
            timeout_seconds=timeout_seconds,
            source_identity=source_at_start,
        )

    model_at_start = collect_model_identity(
        requested_model_id=requested_model_id,
        loaded_model_id=requested_model_id,
        cache_dir=str(cache_dir),
    )
    model_ok, model_reason = validate_capture_model_identity(model_at_start)
    if not model_ok:
        return _publish_preflight_failure(
            output_dir,
            failure_reason=model_reason,
            command_started=command_started,
            timeout_seconds=timeout_seconds,
            source_identity=source_at_start,
            model_identity=model_at_start,
        )
    if time.monotonic() - command_started >= timeout_seconds:
        return _publish_preflight_failure(
            output_dir,
            failure_reason="Timed out while sealing source and model cache preflight.",
            command_started=command_started,
            timeout_seconds=timeout_seconds,
            source_identity=source_at_start,
            model_identity=model_at_start,
        )

    with isolated_assistant_runtime_config(
        requested_model_id,
        parent_dir=output_dir,
    ) as config:
        config.max_new_tokens = MODEL_MAX_NEW_TOKENS
        config.timeout = MODEL_GENERATION_TIMEOUT_SECONDS
        config.temperature = 0.0
        config.top_p = 1.0
        config.do_sample = False
        if not config.save_to_file():
            return _publish_preflight_failure(
                output_dir,
                failure_reason="Could not persist the bounded isolated runtime config.",
                command_started=command_started,
                timeout_seconds=timeout_seconds,
                source_identity=source_at_start,
                model_identity=model_at_start,
            )
        if Path(config.cache_dir).expanduser().resolve() != cache_dir.resolve():
            return _publish_preflight_failure(
                output_dir,
                failure_reason="Isolated runtime resolved a different model cache.",
                command_started=command_started,
                timeout_seconds=timeout_seconds,
                source_identity=source_at_start,
                model_identity=model_at_start,
            )

        from scripts.dev.inspect_local_assistant_runtime import classify_runtime

        initial_runtime = classify_runtime(config)
        if (
            initial_runtime.get("classification") not in {"gpu-ready", "cpu-fallback"}
            or initial_runtime.get("current_model_id") != requested_model_id
        ):
            return _publish_preflight_failure(
                output_dir,
                failure_reason=str(
                    initial_runtime.get("message")
                    or "Exact Granite runtime is unavailable offline."
                ),
                command_started=command_started,
                timeout_seconds=timeout_seconds,
                source_identity=source_at_start,
                model_identity=model_at_start,
                runtime=_runtime_summary(initial_runtime),
            )

        app = QApplication(sys.argv[:1])
        app.setStyle("Fusion")
        app.setProperty("model_override", requested_model_id)
        payload = run_long_session_walkthrough(
            app,
            output_dir=output_dir,
            initial_runtime=initial_runtime,
            timeout_seconds=timeout_seconds,
            command_started=command_started,
        )
        runtime_snapshot = payload.pop("_runtime_snapshot", None)
        if (
            payload.get("status") == "running"
            and _mapping(payload.get("shutdown")).get("status") == "completed"
        ):
            payload["status"] = "passed"
            outcome = _mapping(payload.get("outcome"))
            outcome["result"] = "passed"
            payload["outcome"] = outcome

        strict_ok, strict_reason = finalize_strict_capture_evidence(
            payload,
            requested_model_id=requested_model_id,
            runtime_snapshot=(
                dict(runtime_snapshot)
                if isinstance(runtime_snapshot, Mapping)
                else None
            ),
            cache_dir=config.cache_dir,
            artifact_root=output_dir,
            source_identity_at_start=source_at_start,
            host_actions=_HOST_ACTIONS,
        )
        completed_model = _mapping(
            _mapping(payload.get("runtime")).get("model_identity")
        )
        payload["capture_model_cache"] = {
            "identity_at_start": model_at_start.get("identity_sha256"),
            "identity_at_completion": completed_model.get("identity_sha256"),
            "stable": bool(
                model_at_start.get("identity_sha256")
                and model_at_start.get("identity_sha256")
                == completed_model.get("identity_sha256")
            ),
            "access": "read-only-preexisting",
        }
        _relativize_screenshots(payload, output_dir=output_dir)
        timing = _mapping(payload.get("timing"))
        timing["command_elapsed_seconds"] = round(
            time.monotonic() - command_started,
            3,
        )
        payload["timing"] = timing
        if payload.get("status") == "passed" and not strict_ok:
            _mark_failed(payload, strict_reason)
        if payload.get("status") == "passed":
            scenario_ok, scenario_reason = validate_long_session_evidence(
                payload,
                artifact_root=output_dir,
            )
            if not scenario_ok:
                _mark_failed(payload, scenario_reason)

    try:
        publish_evidence_bundle(output_dir, payload)
    except (OSError, ValueError) as exc:
        _mark_failed(payload, f"Artifact publication failed closed: {exc}")
        publish_evidence_bundle(output_dir, payload)

    if payload.get("status") == "passed":
        ok, reason = validate_artifact_directory(output_dir)
        if not ok:
            _mark_failed(payload, reason)
            publish_evidence_bundle(output_dir, payload)

    _print_artifact_paths(output_dir, payload)
    return 0 if payload.get("status") == "passed" else 1


def run_long_session_walkthrough(
    app: QApplication,
    *,
    output_dir: Path,
    initial_runtime: Mapping[str, object],
    timeout_seconds: int,
    command_started: float,
) -> dict[str, Any]:
    """Run two real turns around one host-seeded prune and external state reset."""
    driver = _LongSessionDriver(
        app=app,
        output_dir=output_dir,
        initial_runtime=initial_runtime,
        timeout_seconds=timeout_seconds,
        command_started=command_started,
    )
    QTimer.singleShot(0, driver.start)
    QTimer.singleShot(timeout_seconds * 1000, driver.timeout)
    app.exec()
    driver.shutdown.reconcile_after_event_loop()
    return driver.payload()


class _LongSessionDriver:
    """Own one bounded real ChatPanel session and its observations."""

    def __init__(
        self,
        *,
        app: QApplication,
        output_dir: Path,
        initial_runtime: Mapping[str, object],
        timeout_seconds: int,
        command_started: float,
    ) -> None:
        self.app = app
        self.output_dir = output_dir
        self.initial_runtime = dict(initial_runtime)
        self.timeout_seconds = timeout_seconds
        self.command_started = command_started
        self.study = Study()
        seeded_path = output_dir / ".host-seeded-session.fif"
        self.study.loaded_data_list = [cast(Any, _SeededRawState(str(seeded_path)))]
        self.service = get_application_service(self.study)
        self.window = QMainWindow()
        self.window.setWindowTitle("XBrainLab Assistant Long-Session Evidence")
        self.window.resize(760, 800)
        self.window.ai_btn = QToolButton(self.window)  # type: ignore[attr-defined]
        self.window.ai_btn.setCheckable(True)  # type: ignore[attr-defined]
        self.manager = AgentManager(
            self.window,
            self.study,
            application_service=self.service,
        )
        self.manager.init_ui()
        archive = build_seed_archive()
        restored = self.manager.chat_controller.restore_history(archive)
        archive_evidence = {
            **seed_archive_descriptor(),
            "restored_row_count": restored,
            "retained": False,
        }
        self.terminals: list[dict[str, object]] = []
        self.generation_requests: list[dict[str, object]] = []
        self.turns: list[dict[str, object]] = []
        self._active_turn_index = 0
        self._turn_started = 0.0
        self._turn_baseline: dict[str, Any] = {}
        self._generation_signal_connected = False
        self._finishing = False
        self._state: dict[str, Any] = {
            "schema": ARTIFACT_SCHEMA,
            "status": "running",
            "failure_reason": "",
            "runtime": {
                **_runtime_summary(self.initial_runtime),
                "generation_policy": {
                    "max_new_tokens": MODEL_MAX_NEW_TOKENS,
                    "timeout_seconds": MODEL_GENERATION_TIMEOUT_SECONDS,
                    "do_sample": False,
                },
            },
            "hf_offline": {
                "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE", ""),
                "TRANSFORMERS_OFFLINE": os.environ.get(
                    "TRANSFORMERS_OFFLINE",
                    "",
                ),
            },
            "host_assistance": {
                "classification": "host-assisted",
                "used": True,
                "actions": list(_HOST_ACTIONS),
            },
            "screenshots": dict.fromkeys(REQUIRED_SCREENSHOTS, ""),
            "archive": archive_evidence,
            "counts": {},
            "prune_events": [],
            "turns": self.turns,
            "generation_requests": self.generation_requests,
            "external_state_change": {},
            "current_state_followup": {},
            "timing": {
                "timeout_seconds": timeout_seconds,
                "command_elapsed_seconds": 0.001,
                "max_turn_seconds": MAX_TURN_SECONDS,
                "model_generation_timeout_seconds": (MODEL_GENERATION_TIMEOUT_SECONDS),
            },
            "outcome": {
                "result": "pending",
                "bounded": True,
                "archive_boundary_observed": False,
                "current_state_used": False,
            },
            "ui_state": {},
            "shutdown": {"status": "pending", "detail": ""},
            "limitations": list(_LIMITATIONS),
            "claim_boundary": _CLAIM_BOUNDARY,
            "_runtime_snapshot": {},
        }
        self.shutdown = BoundedQtShutdown(
            app=self.app,
            window=self.window,
            manager_provider=lambda: self.manager,
            state=self._state,
            schedule=QTimer.singleShot,
            now=time.monotonic,
        )

    def payload(self) -> dict[str, Any]:
        return self._state

    def start(self) -> None:
        if self._expired("starting the assistant"):
            return
        if self._state["archive"]["restored_row_count"] != SEED_ROW_COUNT:
            self.fail("Host-seeded persisted archive did not restore atomically.")
            return
        publication = self._publication_observation()
        if publication.get("pipeline_stage") != "data_loaded":
            self.fail("Host-seeded precondition did not publish data_loaded state.")
            return
        self.window.show()
        if self.manager.chat_dock is None:
            self.fail("ChatPanel dock was not initialized.")
            return
        self.manager.chat_dock.show()
        self.manager.start_system()
        self.manager.assistant_runtime.turn_finished.connect(self._record_terminal)
        QTimer.singleShot(_POLL_INTERVAL_MS, self._wait_for_ready)

    def timeout(self) -> None:
        if not self._finishing:
            self.fail(f"Timed out after {self.timeout_seconds}s during capture.")

    def _wait_for_ready(self) -> None:
        if self._expired("waiting for exact Granite readiness"):
            return
        ready, _reason = assistant_surface_ready(self.manager)
        if not ready:
            QTimer.singleShot(_POLL_INTERVAL_MS, self._wait_for_ready)
            return
        snapshot = self.manager.assistant_runtime.current
        snapshot_payload = snapshot.to_dict()
        if (
            snapshot_payload.get("model_id") != PRIMARY_LOCAL_MODEL_ID
            or snapshot_payload.get("phase") != "ready"
            or snapshot_payload.get("initialized") is not True
            or snapshot_payload.get("selection_outcome") == "fallback"
        ):
            self.fail(
                "Assistant did not activate the exact non-fallback Granite model."
            )
            return
        controller = self.manager.agent_controller
        if controller is None:
            self.fail("Assistant controller is unavailable after runtime startup.")
            return
        if not self._generation_signal_connected:
            controller.sig_generate.connect(self._record_generation_request)
            self._generation_signal_connected = True
        expected_revision = self._publication_observation().get("revision")
        if self._projection_revision() != expected_revision:
            QTimer.singleShot(_POLL_INTERVAL_MS, self._wait_for_ready)
            return
        self._send_turn(1, FIRST_PROMPT)

    def _send_turn(self, turn_index: int, prompt: str) -> None:
        if self._expired(f"starting real turn {turn_index}"):
            return
        panel = self.manager.chat_panel
        controller = self.manager.agent_controller
        if panel is None or controller is None:
            self.fail(f"ChatPanel disappeared before real turn {turn_index}.")
            return
        tools = collect_executed_tools(controller.metrics)
        history_records = self.manager.chat_controller.get_typed_history()
        history_ids = [record.message_id for record in history_records]
        bubble_ids = _layout_bubble_ids(self.manager)
        if bubble_ids != history_ids[: len(bubble_ids)]:
            self.fail(
                f"ChatPanel transcript prefix diverged before real turn {turn_index}."
            )
            return
        self._active_turn_index = turn_index
        self._turn_started = time.monotonic()
        self._turn_baseline = {
            "terminal_count": len(self.terminals),
            "generation_request_count": len(self.generation_requests),
            "tool_count": len(tools),
            "history_rows": len(self.manager.chat_controller.get_typed_history()),
            "pruned_rows": self.manager.chat_controller.pruned_row_count,
            "history_ids": history_ids,
            "bubble_ids": bubble_ids,
        }
        panel.input_field.setText(prompt)
        panel.send_btn.click()
        if turn_index == 1 and not self._observe_prune_boundary():
            return
        QTimer.singleShot(_POLL_INTERVAL_MS, self._wait_for_turn_terminal)

    def _observe_prune_boundary(self) -> bool:
        controller = self.manager.chat_controller
        panel = self.manager.chat_panel
        if panel is None:
            self.fail("ChatPanel disappeared at the prune boundary.")
            return False
        pruned = controller.pruned_row_count - self._turn_baseline["pruned_rows"]
        records = controller.get_typed_history()
        ids = {record.message_id for record in records}
        event = {
            "turn_index": 1,
            "rows_before": self._turn_baseline["history_rows"],
            "rows_pruned": pruned,
            "rows_after_prune": self._turn_baseline["history_rows"] - pruned,
            "oldest_seed_removed": "long-session-seed-0000" not in ids,
            "retained_seed_observed": (
                f"long-session-seed-{EXPECTED_PRUNED_ROWS:04d}" in ids
            ),
            "notice": panel.notice_label.text(),
        }
        self._state["prune_events"] = [event]
        if (
            event["rows_before"] != SEED_ROW_COUNT
            or pruned != EXPECTED_PRUNED_ROWS
            or event["rows_after_prune"] != SEED_ROW_COUNT - EXPECTED_PRUNED_ROWS
            or event["notice"] != PRUNE_NOTICE
        ):
            self.fail(
                "Real ChatPanel admission did not cross the expected prune boundary."
            )
            return False
        self._state["outcome"]["archive_boundary_observed"] = True
        return self._capture("prune_boundary")

    def _wait_for_turn_terminal(self) -> None:
        if self._expired(f"waiting for real turn {self._active_turn_index}"):
            return
        if time.monotonic() - self._turn_started > MAX_TURN_SECONDS:
            self.fail(
                f"Real turn {self._active_turn_index} exceeded {MAX_TURN_SECONDS}s."
            )
            return
        if not self._turn_is_terminal():
            QTimer.singleShot(_POLL_INTERVAL_MS, self._wait_for_turn_terminal)
            return
        self._complete_turn()

    def _complete_turn(self) -> None:
        controller = self.manager.agent_controller
        if controller is None:
            self.fail("Assistant controller disappeared before turn completion.")
            return
        latest = self._latest_assistant_record()
        tools = collect_executed_tools(controller.metrics)
        new_tools = [dict(item) for item in tools[self._turn_baseline["tool_count"] :]]
        model_request_count = (
            len(self.generation_requests)
            - self._turn_baseline["generation_request_count"]
        )
        terminal = self.terminals[-1]
        prompt = FIRST_PROMPT if self._active_turn_index == 1 else FOLLOWUP_PROMPT
        transcript_delta = self._transcript_delta(prompt)
        if transcript_delta is None:
            return
        turn = {
            "index": self._active_turn_index,
            "prompt": prompt,
            "elapsed_seconds": round(time.monotonic() - self._turn_started, 3),
            "terminal_outcome": terminal.get("outcome"),
            "assistant_text": latest.content if latest is not None else "",
            "assistant_text_source": "product_runtime",
            "model_request_count": model_request_count,
            "new_tools": new_tools,
            "transcript_delta": transcript_delta,
        }
        self.turns.append(turn)
        if terminal.get("outcome") != "completed" or not turn["assistant_text"]:
            self.fail(f"Real turn {self._active_turn_index} did not complete visibly.")
            return
        if not 1 <= model_request_count <= MAX_MODEL_GENERATION_REQUESTS:
            self.fail(
                f"Real turn {self._active_turn_index} model calls were unbounded."
            )
            return

        if self._active_turn_index == 1:
            if new_tools:
                self.fail("Explanatory prune-boundary turn executed a workflow tool.")
                return
            self._execute_external_state_change()
            return

        query_tools = [item for item in new_tools if item.get("name") == "query_state"]
        if len(query_tools) != 1 or query_tools[0].get("success") is not True:
            self.fail("Post-reset follow-up did not execute query_state exactly once.")
            return
        if not self._capture("current_state_followup"):
            return
        self._finalize_observations()
        self.finish()

    def _transcript_delta(self, prompt: str) -> dict[str, object] | None:
        records = self.manager.chat_controller.get_typed_history()
        current_ids = [record.message_id for record in records]
        before_ids = self._turn_baseline.get("history_ids")
        before_bubbles = self._turn_baseline.get("bubble_ids")
        if not isinstance(before_ids, list) or not isinstance(before_bubbles, list):
            self.fail("Real turn transcript baseline is missing.")
            return None
        rows_pruned = self.manager.chat_controller.pruned_row_count - int(
            self._turn_baseline.get("pruned_rows", 0)
        )
        if rows_pruned < 0 or rows_pruned > len(before_ids):
            self.fail("Real turn transcript prune delta is invalid.")
            return None
        retained_ids = before_ids[rows_pruned:]
        if current_ids[: len(retained_ids)] != retained_ids:
            self.fail("Real turn transcript lost or reordered retained rows.")
            return None
        new_records = records[len(retained_ids) :]
        if (
            len(new_records) != 2
            or [record.role for record in new_records]
            != [ChatMessageRole.USER, ChatMessageRole.ASSISTANT]
            or new_records[0].content != prompt
            or not new_records[1].content.strip()
        ):
            self.fail("Real turn did not add exactly one user and one assistant row.")
            return None
        new_ids = [record.message_id for record in new_records]
        bubble_ids = _layout_bubble_ids(self.manager)
        if bubble_ids != current_ids or bubble_ids[-2:] != new_ids:
            self.fail(
                "Real turn ChatPanel bubble delta does not match transcript rows."
            )
            return None
        return {
            "rows_before": len(before_ids),
            "rows_pruned": rows_pruned,
            "rows_added": len(new_records),
            "rows_after": len(records),
            "bubble_count_before": len(before_bubbles),
            "bubble_count_after": len(bubble_ids),
            "bubble_tail_ids": new_ids,
            "new_rows": [
                {
                    "message_id": record.message_id,
                    "role": record.role.value,
                    "content_sha256": _text_sha256(record.content),
                }
                for record in new_records
            ],
        }

    def _execute_external_state_change(self) -> None:
        before = self._publication_observation()
        result = self.service.execute(ResetSessionCommand(confirmed=True))
        after = self._publication_observation()
        self._state["external_state_change"] = {
            "command_spine": "ApplicationService.execute",
            "command": "reset_session",
            "confirmed": True,
            "result_ok": result.ok,
            "before": before,
            "after": after,
            "assistant_projection_revision": 0,
        }
        if (
            not result.ok
            or before.get("pipeline_stage") != "data_loaded"
            or after.get("pipeline_stage") != "empty"
            or not _publication_value_increased(
                before.get("generation"),
                after.get("generation"),
            )
            or not _publication_value_increased(
                before.get("revision"),
                after.get("revision"),
            )
        ):
            self.fail(
                "External reset_session did not advance ApplicationService state."
            )
            return
        QTimer.singleShot(_POLL_INTERVAL_MS, self._wait_for_external_publication)

    def _wait_for_external_publication(self) -> None:
        if self._expired("waiting for external ApplicationService publication"):
            return
        change = self._state["external_state_change"]
        expected_revision = int(change["after"]["revision"])
        projection_revision = self._projection_revision()
        change["assistant_projection_revision"] = projection_revision
        if projection_revision != expected_revision:
            QTimer.singleShot(_POLL_INTERVAL_MS, self._wait_for_external_publication)
            return
        self._send_turn(2, FOLLOWUP_PROMPT)

    def _record_generation_request(self, request: object) -> None:
        if self._finishing:
            return
        try:
            controller = self.manager.agent_controller
            publication = getattr(
                getattr(controller, "assembler", None),
                "latest_tool_publication",
                None,
            )
            backend_generation = int(getattr(publication, "backend_generation", 0) or 0)
            observation = generation_request_observation(
                request,
                sequence=len(self.generation_requests) + 1,
                turn_index=self._active_turn_index,
                backend_generation=backend_generation,
            )
        except (TypeError, ValueError) as exc:
            self.fail(f"Could not observe current model request: {exc}")
            return
        self.generation_requests.append(observation)
        if len(self.generation_requests) > MAX_MODEL_GENERATION_REQUESTS:
            self.fail("Model generation request count exceeded the bounded limit.")

    def _record_terminal(self, payload: object) -> None:
        if not isinstance(payload, AssistantTurnTerminal):
            return
        self.terminals.append(
            {
                "correlation": {
                    "generation": payload.generation,
                    "turn_id": payload.turn_id,
                },
                "outcome": payload.outcome,
            }
        )

    def _turn_is_terminal(self) -> bool:
        controller = self.manager.agent_controller
        lifecycle = self.manager.assistant_runtime
        transcript_ids = [
            record.message_id
            for record in self.manager.chat_controller.get_typed_history()
        ]
        return bool(
            len(self.terminals) > self._turn_baseline.get("terminal_count", 0)
            and not self.manager.chat_controller.is_processing
            and not bool(controller and controller.is_processing)
            and not lifecycle.turn_in_flight
            and _layout_bubble_ids(self.manager) == transcript_ids
        )

    def _latest_assistant_record(self) -> ChatMessageRecord | None:
        return next(
            (
                record
                for record in reversed(self.manager.chat_controller.get_typed_history())
                if record.role is ChatMessageRole.ASSISTANT
            ),
            None,
        )

    def _publication_observation(self) -> dict[str, object]:
        publication = self.service.get_view_publication()
        return {
            "pipeline_stage": publication.state.pipeline_stage,
            "generation": int(publication.generation),
            "revision": int(publication.revision),
        }

    def _projection_revision(self) -> int:
        projection = self.manager.assistant_status_projection
        return int(getattr(projection, "publication_revision", 0) or 0)

    def _capture(self, name: str) -> bool:
        dock = self.manager.chat_dock
        if dock is None:
            self.fail(f"ChatPanel dock is unavailable for {name} capture.")
            return False
        path = self.output_dir / _SCREENSHOT_FILENAMES[name]
        try:
            capture_widget(dock, path)
        except (OSError, RuntimeError) as exc:
            self.fail(f"Could not capture {name}: {exc}")
            return False
        self._state["screenshots"][name] = str(path)
        return True

    def _finalize_observations(self) -> None:
        followup_requests = [
            item for item in self.generation_requests if item.get("turn_index") == 2
        ]
        raw_new_tools = self.turns[-1].get("new_tools")
        new_tools = raw_new_tools if isinstance(raw_new_tools, list) else []
        query_tools = [
            item
            for item in new_tools
            if isinstance(item, Mapping)
            and item.get("name") == "query_state"
            and item.get("success") is True
        ]
        self._state["current_state_followup"] = {
            "prompt": FOLLOWUP_PROMPT,
            "expected_pipeline_stage": "empty",
            "expected_workflow_stage": "No data loaded",
            "observed_workflow_stages": [
                item.get("workflow_stage") for item in followup_requests
            ],
            "observed_backend_generations": [
                item.get("backend_generation") for item in followup_requests
            ],
            "query_state_success": len(query_tools) == 1,
        }
        self._state["counts"] = {
            "seeded_archive_count": 1,
            "seeded_archive_rows": SEED_ROW_COUNT,
            "seeded_archive_turns": SEED_TURN_COUNT,
            "real_user_turns": len(self.turns),
            "terminal_turns": len(self.terminals),
            "model_generation_requests": len(self.generation_requests),
            "prune_events": len(self._state["prune_events"]),
            "pruned_rows": self.manager.chat_controller.pruned_row_count,
            "external_state_changes": 1,
        }
        self._state["outcome"]["current_state_used"] = bool(
            followup_requests
            and query_tools
            and all(
                item.get("workflow_stage") == "No data loaded"
                for item in followup_requests
            )
        )

    def finish(self) -> None:
        if self._finishing:
            return
        self._finishing = True
        snapshot = self.manager.assistant_runtime.current.to_dict()
        self._state["_runtime_snapshot"] = snapshot
        self._state["runtime"] = {
            **runtime_evidence(self._state["runtime"], snapshot),
            "generation_policy": self._state["runtime"]["generation_policy"],
        }
        panel = self.manager.chat_panel
        controller = self.manager.agent_controller
        self._state["ui_state"] = {
            "send_button_text": panel.send_btn.text() if panel is not None else "",
            "input_enabled": bool(panel and panel.input_field.isEnabled()),
            "chat_processing": self.manager.chat_controller.is_processing,
            "controller_processing": bool(controller and controller.is_processing),
            "runtime_turn_in_flight": self.manager.assistant_runtime.turn_in_flight,
        }
        self.manager.close()
        self.shutdown.start()

    def fail(self, reason: str) -> None:
        if self._finishing:
            return
        _mark_failed(self._state, reason)
        self.finish()

    def _expired(self, operation: str) -> bool:
        if time.monotonic() - self.command_started <= self.timeout_seconds:
            return False
        self.fail(f"Timed out after {self.timeout_seconds}s while {operation}.")
        return True


def _publish_preflight_failure(
    output_dir: Path,
    *,
    failure_reason: str,
    command_started: float,
    timeout_seconds: int,
    source_identity: Mapping[str, object] | None = None,
    model_identity: Mapping[str, object] | None = None,
    runtime: Mapping[str, object] | None = None,
) -> int:
    runtime_payload = dict(runtime or {})
    if model_identity:
        runtime_payload.update(
            {
                "requested_model_id": PRIMARY_LOCAL_MODEL_ID,
                "loaded_model_id": "",
                "model_identity": dict(model_identity),
            }
        )
    payload: dict[str, Any] = {
        "schema": ARTIFACT_SCHEMA,
        "status": "failed",
        "failure_reason": failure_reason,
        "runtime": runtime_payload,
        "source_identity": dict(source_identity or {}),
        "hf_offline": {
            "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE", ""),
            "TRANSFORMERS_OFFLINE": os.environ.get(
                "TRANSFORMERS_OFFLINE",
                "",
            ),
        },
        "host_assistance": {
            "classification": "host-assisted",
            "used": True,
            "actions": ["ran strict source and model-cache preflight"],
        },
        "screenshots": {},
        "archive": {},
        "counts": {},
        "prune_events": [],
        "turns": [],
        "generation_requests": [],
        "external_state_change": {},
        "current_state_followup": {},
        "timing": {
            "timeout_seconds": timeout_seconds,
            "command_elapsed_seconds": round(time.monotonic() - command_started, 3),
            "max_turn_seconds": MAX_TURN_SECONDS,
            "model_generation_timeout_seconds": MODEL_GENERATION_TIMEOUT_SECONDS,
        },
        "outcome": {
            "result": "failed",
            "bounded": True,
            "archive_boundary_observed": False,
            "current_state_used": False,
        },
        "shutdown": {"status": "not_started", "detail": ""},
        "limitations": list(_LIMITATIONS),
        "claim_boundary": _CLAIM_BOUNDARY,
    }
    publish_evidence_bundle(output_dir, payload)
    _print_artifact_paths(output_dir, payload)
    return 2


def _relativize_screenshots(payload: dict[str, Any], *, output_dir: Path) -> None:
    root = output_dir.resolve()
    relative: dict[str, str] = {}
    for name, raw_path in _mapping(payload.get("screenshots")).items():
        try:
            relative[str(name)] = (
                Path(str(raw_path)).resolve(strict=True).relative_to(root).as_posix()
            )
        except (OSError, ValueError):
            relative[str(name)] = ""
    payload["screenshots"] = relative


def _mark_failed(payload: dict[str, Any], reason: str) -> None:
    payload["status"] = "failed"
    payload["failure_reason"] = str(reason or "Strict evidence validation failed.")
    outcome = _mapping(payload.get("outcome"))
    outcome["result"] = "failed"
    payload["outcome"] = outcome


def _print_artifact_paths(output_dir: Path, payload: Mapping[str, object]) -> None:
    print(f"status={payload.get('status')}")
    print(f"evidence_json={output_dir / JSON_ARTIFACT}")
    print(f"evidence_markdown={output_dir / MARKDOWN_ARTIFACT}")
    print(f"artifact_manifest={output_dir / ARTIFACT_MANIFEST}")


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _publication_value_increased(before: object, after: object) -> bool:
    return (
        isinstance(before, int)
        and not isinstance(before, bool)
        and isinstance(after, int)
        and not isinstance(after, bool)
        and after > before
    )
