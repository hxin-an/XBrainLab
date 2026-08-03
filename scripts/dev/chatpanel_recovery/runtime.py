"""Real exact-Granite ChatPanel recovery and cancellation walkthrough."""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
import time
from argparse import Namespace
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from PIL import Image
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QDockWidget

from scripts.dev.bounded_qt_shutdown import BoundedQtShutdown
from scripts.dev.capture_chatpanel_local_pipeline_chain_walkthrough import (
    assistant_surface_ready,
    collect_model_proposals,
    runtime_evidence,
)
from scripts.dev.capture_chatpanel_local_tool_chain_walkthrough import (
    _clear_saved_main_window_geometry,
    _runtime_summary,
    _set_baseline_window_geometry,
)
from scripts.dev.capture_chatpanel_local_walkthrough import collect_executed_tools
from scripts.dev.capture_human_like_product_walkthrough import capture_widget
from scripts.dev.chatpanel_recovery.evidence import (
    ARTIFACT_SCHEMA,
    BLOCKED_PROMPT,
    CANCELLATION_PROMPT,
    JSON_ARTIFACT,
    MARKDOWN_ARTIFACT,
    PRIOR_EVIDENCE_AUDIT,
    REQUIRED_SCREENSHOTS,
    relativize_screenshot_paths,
    validate_recovery_evidence,
    write_artifacts,
)
from scripts.dev.chatpanel_training_fixture import write_training_ready_raw_fif
from scripts.dev.inspect_local_assistant_runtime import classify_runtime
from scripts.dev.local_assistant_capture_runtime import (
    collect_capture_source_identity,
    finalize_strict_capture_evidence,
    isolated_assistant_runtime_config,
)
from XBrainLab.backend.application import (
    ApplyInterpretationCommand,
    ConfigureTrainingCommand,
    CreateEpochCommand,
    GenerateDatasetCommand,
    PreprocessCommand,
    PreprocessOperation,
    PreviewInterpretationCommand,
    ScanSourceCommand,
    TrainCommand,
    ValidateInterpretationCommand,
    get_application_service,
)
from XBrainLab.backend.controller.chat_controller import (
    ChatMessageRecord,
    ChatMessageRole,
)
from XBrainLab.llm.agent.turn import (
    AssistantGenerationEvent,
    AssistantGenerationEventPhase,
    AssistantTurnTerminal,
)
from XBrainLab.llm.core.model_catalog import PRIMARY_LOCAL_MODEL_ID
from XBrainLab.platform_paths import MODEL_CACHE_DIR_ENV

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = ROOT / "build" / "dev-artifacts" / "chatpanel-local-recovery"
DEFAULT_TIMEOUT_SECONDS = 600
_POLL_INTERVAL_MS = 100

_SCREENSHOT_FILENAMES = {
    "ready": "chatpanel-recovery-ready.png",
    "blocked_retry": "chatpanel-recovery-blocked-retry.png",
    "recovery_complete": "chatpanel-recovery-complete.png",
    "cancel_in_flight": "chatpanel-recovery-cancel-in-flight.png",
    "cancel_stopping": "chatpanel-recovery-cancel-stopping.png",
    "cancelled_terminal": "chatpanel-recovery-cancelled-terminal.png",
}
_ACTION_CREATE_FIXTURE = (
    "created one deterministic synthetic FIF fixture in D-drive capture scratch "
    "and retained only its digest"
)
_ACTION_PREPARE_PRECONDITION = (
    "prepared a dataset-ready and training-configured precondition through eight "
    "real ApplicationService.execute commands"
)
_ACTION_OPEN_ASSISTANT = (
    "opened and floated the real Assistant dock at capture width so Retry was visible"
)
_ACTION_SUBMIT_BLOCKED = (
    "submitted the bounded evaluation request through the ChatPanel composer"
)
_ACTION_SUBMIT_TRAINING = (
    "submitted one real interactive TrainCommand after the visible evaluation block "
    "and waited for its terminal publication"
)
_ACTION_CLICK_RETRY = "clicked the visible Retry last request control without changing the original prompt"
_ACTION_SUBMIT_CANCELLATION = (
    "submitted one informational request and waited for exact-model generation "
    "dispatch to start"
)
_ACTION_CLICK_STOP = (
    "clicked the visible Stop control while the turn was explicitly cancellable"
)
_CLAIM_BOUNDARY = (
    "This is host-assisted exact-Granite product recovery evidence, not raw-model "
    "accuracy, tool-call scoring, thesis evidence, long-session Granite evidence, "
    "or Windows native acceptance. Offscreen cancellation does not prove recovery "
    "from an uninterruptible CUDA or native-process hang."
)


def parse_args(argv: Sequence[str] | None = None) -> Namespace:
    """Parse the bounded exact-model walkthrough command line."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for recovery screenshots and evidence.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=_positive_int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Maximum total walkthrough time.",
    )
    parser.add_argument(
        "--model",
        choices=(PRIMARY_LOCAL_MODEL_ID,),
        default=PRIMARY_LOCAL_MODEL_ID,
        help="Exact supported product model; no fallback model is accepted.",
    )
    parser.add_argument(
        "--cache-dir",
        default="",
        help="Optional local model cache boundary for this process only.",
    )
    return parser.parse_args(argv)


def cli_main(argv: Sequence[str] | None = None) -> int:
    """Run one strict offline recovery capture and write its evidence."""
    args = parse_args(argv)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    _enforce_offline_runtime()
    if args.cache_dir:
        os.environ[MODEL_CACHE_DIR_ENV] = str(
            Path(args.cache_dir).expanduser().resolve()
        )

    source_identity_at_start = collect_capture_source_identity(refresh=True)
    payload: dict[str, Any]
    with tempfile.TemporaryDirectory(prefix=".runtime-", dir=output_dir) as scratch:
        scratch_dir = Path(scratch)
        fixture_path = write_training_ready_raw_fif(scratch_dir / "recovery_raw.fif")
        fixture_identity = {
            "kind": "synthetic_fif",
            "display_name": fixture_path.name,
            "sha256": _sha256_file(fixture_path),
            "retained": False,
        }
        with isolated_assistant_runtime_config(
            args.model,
            parent_dir=output_dir,
        ) as config:
            initial_runtime = classify_runtime(config)
            if initial_runtime.get("classification") not in {
                "gpu-ready",
                "cpu-fallback",
            }:
                payload = _preflight_failure_payload(
                    initial_runtime,
                    source_identity_at_start=source_identity_at_start,
                    failure_reason=str(
                        initial_runtime.get("message")
                        or "Exact Granite runtime is unavailable."
                    ),
                )
                write_artifacts(output_dir, payload)
                _print_artifact_paths(output_dir, payload)
                return 2

            app = QApplication(sys.argv[:1])
            app.setStyle("Fusion")
            app.setProperty("model_override", args.model)
            payload = run_recovery_walkthrough(
                app,
                output_dir=output_dir,
                fixture_path=fixture_path,
                fixture_identity=fixture_identity,
                initial_runtime=initial_runtime,
                timeout_seconds=args.timeout_seconds,
            )
            runtime_snapshot = payload.pop("_runtime_snapshot", None)
            strict_ok, strict_reason = finalize_strict_capture_evidence(
                payload,
                requested_model_id=args.model,
                runtime_snapshot=(
                    dict(runtime_snapshot)
                    if isinstance(runtime_snapshot, Mapping)
                    else None
                ),
                cache_dir=config.cache_dir,
                artifact_root=output_dir,
                source_identity_at_start=source_identity_at_start,
                host_actions=_recorded_host_actions(payload),
            )
            relativize_screenshot_paths(payload, artifact_root=output_dir)
            if payload.get("status") == "passed" and not strict_ok:
                payload["status"] = "failed"
                payload["failure_reason"] = strict_reason
            if payload.get("status") == "passed":
                scenario_ok, scenario_reason = validate_recovery_evidence(
                    payload,
                    artifact_root=output_dir,
                )
                if not scenario_ok:
                    payload["status"] = "failed"
                    payload["failure_reason"] = scenario_reason

    write_artifacts(output_dir, payload)
    _print_artifact_paths(output_dir, payload)
    return 0 if payload.get("status") == "passed" else 1


def run_recovery_walkthrough(
    app: QApplication,
    *,
    output_dir: Path,
    fixture_path: Path,
    fixture_identity: Mapping[str, object],
    initial_runtime: Mapping[str, object],
    timeout_seconds: int,
) -> dict[str, Any]:
    """Exercise blocked -> Retry recovery -> in-flight Stop through real UI."""
    driver = _RecoveryWalkthroughDriver(
        app=app,
        output_dir=output_dir,
        fixture_path=fixture_path,
        fixture_identity=fixture_identity,
        initial_runtime=initial_runtime,
        timeout_seconds=timeout_seconds,
    )
    QTimer.singleShot(1000, driver.open_assistant)
    app.exec()
    driver.shutdown.reconcile_after_event_loop()
    payload = driver.payload()
    finalize_walkthrough_after_shutdown(payload)
    return payload


def finalize_walkthrough_after_shutdown(payload: dict[str, Any]) -> None:
    """Set the terminal result only after bounded Qt shutdown is observable."""
    if payload.get("status") != "running":
        return
    ok, reason = validate_recovery_evidence(payload, strict=False)
    payload["status"] = "passed" if ok else "failed"
    payload["failure_reason"] = "" if ok else reason


def _recorded_host_actions(payload: Mapping[str, object]) -> list[str]:
    assistance = payload.get("host_assistance")
    if not isinstance(assistance, Mapping):
        return []
    actions = assistance.get("actions")
    if not isinstance(actions, list):
        return []
    return [action for action in actions if isinstance(action, str) and action]


class _RecoveryWalkthroughDriver:
    """Own one bounded real-product recovery capture state machine."""

    def __init__(
        self,
        *,
        app: QApplication,
        output_dir: Path,
        fixture_path: Path,
        fixture_identity: Mapping[str, object],
        initial_runtime: Mapping[str, object],
        timeout_seconds: int,
    ) -> None:
        from XBrainLab.backend.study import Study
        from XBrainLab.ui.main_window import MainWindow

        _clear_saved_main_window_geometry()
        self.app = app
        self.output_dir = output_dir
        self.fixture_path = fixture_path
        self.fixture_identity = dict(fixture_identity)
        self.initial_runtime = dict(initial_runtime)
        self.timeout_seconds = timeout_seconds
        self.started_at = time.monotonic()
        self.study = Study()
        self.training_output_dir = self.fixture_path.parent / "training-output"
        self.precondition = prepare_precondition_state(
            self.study,
            self.fixture_path,
            training_output_dir=self.training_output_dir,
            fixture_identity=self.fixture_identity,
        )
        self.window = MainWindow(self.study)
        _set_baseline_window_geometry(self.window)
        self.window.show()
        self.terminals: list[dict[str, object]] = []
        self.generation_events: list[AssistantGenerationEvent] = []
        self._terminal_signal_connected = False
        self._generation_signal_connected = False
        self._terminal_started = False
        self._turn_baseline: dict[str, int] = {}
        self._last_recovery_publication: tuple[int, int, str] | None = None
        self._recovery_publication_stable_samples = 0
        self._state: dict[str, Any] = {
            "schema": ARTIFACT_SCHEMA,
            "status": "running",
            "failure_reason": "",
            "runtime": _runtime_summary(self.initial_runtime),
            "hf_offline": {
                "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE"),
                "TRANSFORMERS_OFFLINE": os.environ.get("TRANSFORMERS_OFFLINE"),
            },
            "prior_evidence_audit": [dict(item) for item in PRIOR_EVIDENCE_AUDIT],
            "screenshots": dict.fromkeys(REQUIRED_SCREENSHOTS, ""),
            "scenario": {
                "precondition": self.precondition,
                "blocked": {},
                "host_recovery": {},
                "retry": {},
                "cancellation": {},
            },
            "host_assistance": {
                "classification": "host-assisted",
                "used": True,
                "actions": [
                    _ACTION_CREATE_FIXTURE,
                    _ACTION_PREPARE_PRECONDITION,
                ],
            },
            "turn_terminals": self.terminals,
            "ui_state": {},
            "shutdown": {"status": "pending", "detail": ""},
            "claim_boundary": _CLAIM_BOUNDARY,
            "elapsed_seconds": 0.0,
            "_runtime_snapshot": {},
        }
        self.shutdown = BoundedQtShutdown(
            app=self.app,
            window=self.window,
            manager_provider=lambda: self.window.agent_manager,
            state=self._state,
            schedule=QTimer.singleShot,
            now=time.monotonic,
        )

    def payload(self) -> dict[str, Any]:
        return self._state

    def open_assistant(self) -> None:
        if self._expired("opening Assistant"):
            return
        ok, reason = _validate_partial(self._state, section="precondition")
        if not ok:
            self.fail(reason)
            return
        self.window.ai_btn.click()
        QTimer.singleShot(250, self._wait_for_ready)

    def _wait_for_ready(self) -> None:
        if self._terminal_started:
            return
        if self._expired("waiting for exact Granite readiness"):
            return
        manager = self.window.agent_manager
        if manager is None:
            self.fail("Assistant manager was not initialized.")
            return
        ready, _reason = assistant_surface_ready(manager)
        if not ready:
            QTimer.singleShot(250, self._wait_for_ready)
            return
        snapshot = getattr(manager.assistant_runtime, "current", None)
        snapshot_payload = (
            snapshot.to_dict()
            if snapshot is not None and hasattr(snapshot, "to_dict")
            else {}
        )
        if (
            snapshot_payload.get("model_id") != PRIMARY_LOCAL_MODEL_ID
            or snapshot_payload.get("phase") != "ready"
            or snapshot_payload.get("initialized") is not True
            or snapshot_payload.get("selection_outcome") == "fallback"
        ):
            self.fail(
                "Assistant activated without exact non-fallback Granite identity."
            )
            return
        if not self._terminal_signal_connected:
            manager.assistant_runtime.turn_finished.connect(self._record_terminal)
            self._terminal_signal_connected = True
        controller = manager.agent_controller
        if controller is None:
            self.fail("Assistant controller was not initialized.")
            return
        if not self._generation_signal_connected:
            controller.generation_event.connect(self._record_generation_event)
            self._generation_signal_connected = True
        manager.float_action.trigger()
        QTimer.singleShot(250, self._size_and_capture_ready)

    def _size_and_capture_ready(self) -> None:
        manager = self.window.agent_manager
        dock = manager.chat_dock if manager is not None else None
        if manager is None or dock is None or not dock.isFloating():
            self.fail("Assistant dock did not enter the observable floating state.")
            return
        dock.setMinimumSize(560, 700)
        dock.resize(620, 760)
        dock.move(0, 0)
        dock.show()
        self._record_host_action(_ACTION_OPEN_ASSISTANT)
        title_bar = dock.titleBarWidget()
        if title_bar is not None:
            title_bar.resize(dock.width(), title_bar.height())
        self.app.processEvents()
        if not self._capture("ready"):
            return
        self._send_blocked_turn()

    def _send_blocked_turn(self) -> None:
        manager = self.window.agent_manager
        panel = manager.chat_panel if manager is not None else None
        if panel is None:
            self.fail("ChatPanel disappeared before the blocked turn.")
            return
        self._turn_baseline = self._collect_turn_baseline()
        panel.input_field.setText(BLOCKED_PROMPT)
        panel.send_btn.click()
        self._record_host_action(_ACTION_SUBMIT_BLOCKED)
        QTimer.singleShot(_POLL_INTERVAL_MS, self._wait_for_blocked_turn)

    def _wait_for_blocked_turn(self) -> None:
        if self._terminal_started:
            return
        if self._expired("waiting for the blocked visualization turn"):
            return
        if not self._turn_reached_terminal():
            QTimer.singleShot(_POLL_INTERVAL_MS, self._wait_for_blocked_turn)
            return
        manager = self.window.agent_manager
        panel = manager.chat_panel if manager is not None else None
        if manager is None or panel is None:
            self.fail("ChatPanel disappeared after the blocked turn.")
            return
        record = self._latest_assistant_record()
        retry = manager.retry_title_btn
        blocked = {
            "prompt": BLOCKED_PROMPT,
            "presentation_kind": _presentation_kind(record),
            "assistant_text": record.content if record is not None else "",
            "new_tools": self._new_tools(),
            "terminal_outcome": self.terminals[-1]["outcome"],
            "retry_control": {
                "visible": retry.isVisible(),
                "enabled": retry.isEnabled(),
                "accessible_name": retry.accessibleName(),
            },
        }
        self._scenario()["blocked"] = blocked
        ok, reason = _validate_partial(self._state, section="blocked")
        if not ok:
            self.fail(reason)
            return
        if not self._capture("blocked_retry"):
            return
        QTimer.singleShot(100, self._prepare_recovery_state)

    def _prepare_recovery_state(self) -> None:
        try:
            recovery = prepare_recovery_state(
                self.study,
            )
        except Exception as exc:
            self.fail(f"ApplicationService recovery raised {type(exc).__name__}: {exc}")
            return
        self._record_host_action(_ACTION_SUBMIT_TRAINING)
        self._scenario()["host_recovery"] = recovery
        if any(not bool(item.get("ok")) for item in recovery.get("commands", [])):
            self.fail("ApplicationService did not admit the training recovery.")
            return
        QTimer.singleShot(250, self._wait_for_training_recovery)

    def _wait_for_training_recovery(self) -> None:
        if self._terminal_started:
            return
        if self._expired("waiting for terminal training recovery"):
            return
        service = get_application_service(self.study)
        state = service.get_state().to_dict()
        training = state.get("training") if isinstance(state, dict) else None
        evaluation = state.get("evaluation") if isinstance(state, dict) else None
        visualization = state.get("visualization") if isinstance(state, dict) else None
        terminal = (
            training.get("terminal_outcome") if isinstance(training, dict) else None
        )
        terminal_state = (
            str(terminal.get("state") or "") if isinstance(terminal, dict) else ""
        )
        saliency = (
            visualization.get("post_training_saliency")
            if isinstance(visualization, dict)
            else None
        )
        saliency_phase = (
            str(saliency.get("phase") or "") if isinstance(saliency, dict) else ""
        )
        publication = service.get_view_publication()
        publication_generation = int(publication.generation)
        publication_revision = int(publication.revision)
        manager = self.window.agent_manager
        projection = (
            manager.assistant_status_projection if manager is not None else None
        )
        projection_revision = int(getattr(projection, "publication_revision", 0) or 0)
        publication_identity = (
            publication_generation,
            publication_revision,
            saliency_phase,
        )
        if publication_identity == self._last_recovery_publication:
            self._recovery_publication_stable_samples += 1
        else:
            self._last_recovery_publication = publication_identity
            self._recovery_publication_stable_samples = 1
        finished = bool(
            isinstance(training, dict)
            and not training.get("is_running")
            and int(training.get("finished_run_count") or 0) >= 1
        )
        evaluation_available = bool(
            isinstance(evaluation, dict)
            and evaluation.get("available")
            and evaluation.get("metrics_available")
        )
        recovery = self._scenario()["host_recovery"]
        recovery.update(
            {
                "training_finished": finished,
                "evaluation_available": evaluation_available,
                "terminal_outcome": terminal_state,
                "post_training_saliency_phase": saliency_phase,
                "publication_generation": publication_generation,
                "publication_revision": publication_revision,
                "assistant_projection_revision": projection_revision,
                "publication_stable_samples": (
                    self._recovery_publication_stable_samples
                ),
            }
        )
        observations = recovery.setdefault("publication_observations", [])
        if isinstance(observations, list):
            observations.append(
                {
                    "generation": publication_generation,
                    "revision": publication_revision,
                    "assistant_projection_revision": projection_revision,
                    "saliency_phase": saliency_phase,
                }
            )
            del observations[:-24]
        saliency_terminal = saliency_phase in {"succeeded", "failed", "cancelled"}
        publication_quiescent = bool(
            self._recovery_publication_stable_samples >= 3
            and projection_revision == publication_revision
        )
        if (
            finished
            and evaluation_available
            and terminal_state == "completed"
            and saliency_terminal
            and publication_quiescent
        ):
            QTimer.singleShot(500, self._start_retry)
            return
        if terminal_state in {"cancelled", "failed"}:
            self.fail(f"Training recovery reached terminal {terminal_state} state.")
            return
        QTimer.singleShot(250, self._wait_for_training_recovery)

    def _start_retry(self) -> None:
        manager = self.window.agent_manager
        if manager is None:
            self.fail("Assistant manager disappeared before Retry.")
            return
        retry = manager.retry_title_btn
        if not retry.isVisible() or not retry.isEnabled():
            self.fail("Visible Retry control was unavailable after host recovery.")
            return
        self._turn_baseline = self._collect_turn_baseline()
        retry.click()
        self._record_host_action(_ACTION_CLICK_RETRY)
        QTimer.singleShot(_POLL_INTERVAL_MS, self._wait_for_retry)

    def _wait_for_retry(self) -> None:
        if self._terminal_started:
            return
        if self._expired("waiting for Retry recovery"):
            return
        if not self._turn_reached_terminal():
            QTimer.singleShot(_POLL_INTERVAL_MS, self._wait_for_retry)
            return
        manager = self.window.agent_manager
        controller = manager.agent_controller if manager is not None else None
        if manager is None or controller is None:
            self.fail("Assistant controller disappeared during Retry recovery.")
            return
        record = self._latest_assistant_record()
        proposals = collect_model_proposals(controller.history, BLOCKED_PROMPT)
        retry = {
            "prompt": BLOCKED_PROMPT,
            "same_prompt": self._latest_user_text() == BLOCKED_PROMPT,
            "invoked_via": "Retry last request",
            "presentation_kind": _presentation_kind(record),
            "assistant_text": record.content if record is not None else "",
            "assistant_text_source": "product_runtime",
            "model_proposals": proposals,
            "model_calls": self._new_model_calls(),
            "new_tools": self._new_tools(),
            "terminal_outcome": self.terminals[-1]["outcome"],
        }
        self._scenario()["retry"] = retry
        ok, reason = _validate_partial(self._state, section="retry")
        if not ok:
            self.fail(reason)
            return
        if not self._capture("recovery_complete"):
            return
        QTimer.singleShot(200, self._send_cancellation_turn)

    def _send_cancellation_turn(self) -> None:
        manager = self.window.agent_manager
        panel = manager.chat_panel if manager is not None else None
        if panel is None:
            self.fail("ChatPanel disappeared before the cancellation turn.")
            return
        self._turn_baseline = self._collect_turn_baseline()
        panel.input_field.setText(CANCELLATION_PROMPT)
        panel.send_btn.click()
        self._record_host_action(_ACTION_SUBMIT_CANCELLATION)
        QTimer.singleShot(25, self._wait_for_cancellable_turn)

    def _wait_for_cancellable_turn(self) -> None:
        if self._terminal_started:
            return
        if self._expired("waiting for a cancellable exact-model turn"):
            return
        if len(self.terminals) > self._turn_baseline.get("terminal_count", 0):
            self.fail(
                "Informational turn completed before started cancellable evidence "
                "could be captured."
            )
            return
        manager = self.window.agent_manager
        panel = manager.chat_panel if manager is not None else None
        controller = manager.agent_controller if manager is not None else None
        if manager is None or panel is None or controller is None:
            self.fail("Assistant disappeared during the cancellation turn.")
            return
        presentation = getattr(panel, "_turn_presentation", None)
        cancelability = getattr(
            getattr(presentation, "cancelability", None), "value", ""
        )
        started_event = self._started_generation_event_after(self._turn_baseline)
        dispatch_phase = started_event.phase.value if started_event is not None else ""
        current_turn = getattr(controller.metrics, "current_turn", None)
        model_calls = int(getattr(current_turn, "llm_calls", 0) or 0)
        if not (
            panel.send_btn.text() == "Stop"
            and cancelability == "cancellable"
            and dispatch_phase == "started"
            and model_calls >= 1
            and bool(getattr(controller, "is_processing", False))
        ):
            QTimer.singleShot(25, self._wait_for_cancellable_turn)
            return
        lease = getattr(getattr(manager, "_assistant_turn_state", None), "lease", None)
        correlation = {
            "generation": int(getattr(lease, "generation", 0) or 0),
            "turn_id": int(getattr(lease, "turn_id", 0) or 0),
        }
        cancellation = {
            "prompt": CANCELLATION_PROMPT,
            "in_flight": {
                "observed": True,
                "send_button_text": panel.send_btn.text(),
                "cancelability": cancelability,
                "primary_status": str(
                    getattr(presentation, "primary_status", "") or ""
                ),
                "generation_dispatch_phase": dispatch_phase,
                "model_calls": model_calls,
                "application_command_in_flight": bool(
                    getattr(manager, "_application_command_in_flight", False)
                ),
                "correlation": correlation,
            },
            "stop_clicked": False,
            "stopping_observed": False,
            "assistant_text": "",
            "presentation_kind": "",
            "terminal_outcome": "",
            "new_tools": [],
        }
        self._scenario()["cancellation"] = cancellation
        if not self._capture("cancel_in_flight", transient=True):
            return
        if not (
            bool(getattr(controller, "is_processing", False))
            and panel.send_btn.text() == "Stop"
        ):
            self.fail("Exact-model turn ended during cancellable-state capture.")
            return
        panel.send_btn.click()
        cancellation["stop_clicked"] = True
        self._record_host_action(_ACTION_CLICK_STOP)
        stopping = getattr(panel, "_turn_presentation", None)
        stopping_cancelability = getattr(
            getattr(stopping, "cancelability", None),
            "value",
            "",
        )
        cancellation["stopping_observed"] = bool(
            panel.send_btn.text() == "Stopping" and stopping_cancelability == "stopping"
        )
        if not cancellation["stopping_observed"]:
            self.fail("Visible Stop did not transition to the typed Stopping state.")
            return
        if not self._capture("cancel_stopping", transient=True):
            return
        QTimer.singleShot(25, self._wait_for_cancelled_terminal)

    def _wait_for_cancelled_terminal(self) -> None:
        if self._terminal_started:
            return
        if self._expired("waiting for the cancelled terminal"):
            return
        if not self._turn_reached_terminal():
            QTimer.singleShot(25, self._wait_for_cancelled_terminal)
            return
        record = self._latest_assistant_record()
        cancellation = self._scenario()["cancellation"]
        cancellation.update(
            {
                "assistant_text": record.content if record is not None else "",
                "presentation_kind": _presentation_kind(record),
                "terminal_outcome": self.terminals[-1]["outcome"],
                "new_tools": self._new_tools(),
            }
        )
        ok, reason = _validate_partial(self._state, section="cancellation")
        if not ok:
            self.fail(reason)
            return
        if not self._capture("cancelled_terminal"):
            return
        self.finish()

    def finish(self) -> None:
        if self._terminal_started:
            return
        self._terminal_started = True
        self._state["elapsed_seconds"] = round(
            time.monotonic() - self.started_at,
            3,
        )
        manager = self.window.agent_manager
        panel = manager.chat_panel if manager is not None else None
        controller = manager.agent_controller if manager is not None else None
        lifecycle = getattr(manager, "assistant_runtime", None)
        snapshot = getattr(lifecycle, "current", None)
        snapshot_payload = (
            snapshot.to_dict()
            if snapshot is not None and hasattr(snapshot, "to_dict")
            else {}
        )
        self._state["_runtime_snapshot"] = snapshot_payload
        self._state["runtime"] = runtime_evidence(
            self._state["runtime"],
            snapshot_payload,
        )
        self._state["ui_state"] = {
            "send_button_text": panel.send_btn.text() if panel is not None else "",
            "input_enabled": bool(panel and panel.input_field.isEnabled()),
            "chat_processing": bool(
                manager is not None and manager.chat_controller.is_processing
            ),
            "controller_processing": bool(
                controller is not None and getattr(controller, "is_processing", False)
            ),
            "runtime_turn_in_flight": bool(
                lifecycle is not None and getattr(lifecycle, "turn_in_flight", False)
            ),
        }
        self.shutdown.start()

    def fail(self, reason: str) -> None:
        if self._terminal_started:
            return
        self._state["status"] = "failed"
        self._state["failure_reason"] = str(reason)
        self.finish()

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

    def _record_generation_event(self, payload: object) -> None:
        if isinstance(payload, AssistantGenerationEvent):
            self.generation_events.append(payload)

    def _started_generation_event_after(
        self,
        baseline: Mapping[str, int],
    ) -> AssistantGenerationEvent | None:
        start = baseline.get("generation_event_count", 0)
        return next(
            (
                event
                for event in self.generation_events[start:]
                if event.phase is AssistantGenerationEventPhase.STARTED
            ),
            None,
        )

    def _collect_turn_baseline(self) -> dict[str, int]:
        manager = self.window.agent_manager
        controller = manager.agent_controller if manager is not None else None
        records = (
            manager.chat_controller.get_typed_history() if manager is not None else ()
        )
        tools = (
            collect_executed_tools(controller.metrics) if controller is not None else []
        )
        completed = list(
            getattr(getattr(controller, "metrics", None), "_completed_turns", []) or []
        )
        return {
            "message_count": len(records),
            "tool_count": len(tools),
            "terminal_count": len(self.terminals),
            "completed_turn_count": len(completed),
            "generation_event_count": len(self.generation_events),
        }

    def _turn_reached_terminal(self) -> bool:
        manager = self.window.agent_manager
        controller = manager.agent_controller if manager is not None else None
        lifecycle = getattr(manager, "assistant_runtime", None)
        return bool(
            len(self.terminals) > self._turn_baseline.get("terminal_count", 0)
            and manager is not None
            and not manager.chat_controller.is_processing
            and not bool(controller and getattr(controller, "is_processing", False))
            and not bool(lifecycle and getattr(lifecycle, "turn_in_flight", False))
        )

    def _latest_assistant_record(self) -> ChatMessageRecord | None:
        manager = self.window.agent_manager
        records = (
            manager.chat_controller.get_typed_history() if manager is not None else ()
        )
        start = self._turn_baseline.get("message_count", 0)
        return next(
            (
                record
                for record in reversed(records[start:])
                if record.role is ChatMessageRole.ASSISTANT
            ),
            None,
        )

    def _latest_user_text(self) -> str:
        manager = self.window.agent_manager
        records = (
            manager.chat_controller.get_typed_history() if manager is not None else ()
        )
        return next(
            (
                record.content
                for record in reversed(records)
                if record.role is ChatMessageRole.USER
            ),
            "",
        )

    def _new_tools(self) -> list[dict[str, Any]]:
        manager = self.window.agent_manager
        controller = manager.agent_controller if manager is not None else None
        tools = (
            collect_executed_tools(controller.metrics) if controller is not None else []
        )
        return [
            dict(tool) for tool in tools[self._turn_baseline.get("tool_count", 0) :]
        ]

    def _new_model_calls(self) -> int:
        manager = self.window.agent_manager
        controller = manager.agent_controller if manager is not None else None
        completed = list(
            getattr(getattr(controller, "metrics", None), "_completed_turns", []) or []
        )
        start = self._turn_baseline.get("completed_turn_count", 0)
        return sum(
            int(getattr(turn, "llm_calls", 0) or 0) for turn in completed[start:]
        )

    def _scenario(self) -> dict[str, Any]:
        return self._state["scenario"]

    def _record_host_action(self, action: str) -> None:
        assistance = self._state["host_assistance"]
        actions = assistance["actions"]
        if action not in actions:
            actions.append(action)

    def _capture(self, name: str, *, transient: bool = False) -> bool:
        manager = self.window.agent_manager
        dock = manager.chat_dock if manager is not None else None
        if not isinstance(dock, QDockWidget):
            self.fail(f"Assistant dock is unavailable for {name} capture.")
            return False
        path = self.output_dir / _SCREENSHOT_FILENAMES[name]
        try:
            if transient:
                _capture_transient_widget(dock, path)
            else:
                capture_widget(dock, path)
        except (OSError, RuntimeError) as exc:
            self.fail(f"Could not capture {name}: {exc}")
            return False
        self._state["screenshots"][name] = str(path)
        return True

    def _expired(self, operation: str) -> bool:
        if time.monotonic() - self.started_at <= self.timeout_seconds:
            return False
        self.fail(f"Timed out after {self.timeout_seconds}s while {operation}.")
        return True


def prepare_precondition_state(
    study: Any,
    fixture_path: Path,
    *,
    training_output_dir: Path,
    fixture_identity: Mapping[str, object],
) -> dict[str, Any]:
    """Build the known training-configured state before the visible block."""
    service = get_application_service(study)
    commands = (
        ScanSourceCommand(source_path=str(fixture_path)),
        PreviewInterpretationCommand(),
        ValidateInterpretationCommand(),
        ApplyInterpretationCommand(confirmed=True),
        PreprocessCommand(
            operation=PreprocessOperation.STANDARD,
            low_freq=4.0,
            high_freq=40.0,
            method="z-score",
        ),
        CreateEpochCommand(t_min=0.0, t_max=1.5, event_ids=["left", "right"]),
        GenerateDatasetCommand(
            test_ratio=0.25,
            val_ratio=0.25,
            split_strategy="trial",
            training_mode="individual",
        ),
        ConfigureTrainingCommand(
            model_name="EEGNet",
            epoch=1,
            batch_size=2,
            learning_rate=0.001,
            device="cpu",
            save_checkpoints_every=0,
            output_dir=str(training_output_dir),
            evaluation_option="Last Epoch",
        ),
    )
    results: list[dict[str, object]] = []
    for command in commands:
        result = service.execute(command)
        results.append(
            {
                "command": command.name.value,
                "ok": result.ok,
                "error_type": result.error_type.value if result.failed else None,
            }
        )
        if result.failed:
            break
    state = service.get_state().to_dict()
    dataset = state.get("dataset") if isinstance(state, dict) else None
    training = state.get("training") if isinstance(state, dict) else None
    return {
        "command_spine": "ApplicationService.execute",
        "commands": results,
        "dataset_available": bool(
            isinstance(dataset, dict) and dataset.get("available")
        ),
        "training_configured": bool(
            isinstance(training, dict)
            and training.get("has_model")
            and training.get("has_training_option")
            and not training.get("has_trainer")
        ),
        "fixture": dict(fixture_identity),
    }


def prepare_recovery_state(study: Any) -> dict[str, Any]:
    """Start real training after the visible evaluate precondition block."""
    service = get_application_service(study)
    command = TrainCommand(confirmed=True, interactive=True)
    result = service.execute(command)
    return {
        "command_spine": "ApplicationService.execute",
        "commands": [
            {
                "command": command.name.value,
                "ok": result.ok,
                "error_type": result.error_type.value if result.failed else None,
            }
        ],
        "training_finished": False,
        "evaluation_available": False,
        "terminal_outcome": "",
        "post_training_saliency_phase": "",
        "publication_generation": 0,
        "publication_revision": 0,
        "assistant_projection_revision": 0,
        "publication_stable_samples": 0,
        "publication_observations": [],
        "output_retained": False,
    }


def _validate_partial(
    payload: Mapping[str, object],
    *,
    section: str,
) -> tuple[bool, str]:
    """Validate completed scenario prefixes without weakening final validation."""
    from scripts.dev.chatpanel_recovery import evidence

    raw_scenario = payload.get("scenario")
    if not isinstance(raw_scenario, Mapping):
        return False, "Recovery scenario is missing."
    scenario = dict(raw_scenario)
    raw_section = scenario.get(section)
    if not isinstance(raw_section, Mapping):
        return False, f"Recovery scenario section is missing: {section}."
    section_payload = dict(raw_section)
    if section == "precondition":
        return evidence._validate_precondition(section_payload)
    if section == "blocked":
        return evidence._validate_blocked(section_payload)
    if section == "retry":
        return evidence._validate_retry(section_payload)
    if section == "cancellation":
        return evidence._validate_cancellation(section_payload)
    return False, f"Unknown recovery validation section: {section}."


def _capture_transient_widget(widget: QDockWidget, path: Path) -> None:
    """Capture one already-rendered transient state without a settling delay."""
    path.parent.mkdir(parents=True, exist_ok=True)
    widget.repaint()
    pixmap = widget.grab()
    if pixmap.isNull() or not pixmap.save(str(path), "PNG"):
        raise RuntimeError(f"Transient screenshot could not be saved: {path.name}.")
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        colors = image.convert("L").getcolors(maxcolors=256)
    if colors is not None and len(colors) <= 1:
        raise RuntimeError(f"Transient screenshot is blank: {path.name}.")


def _presentation_kind(record: ChatMessageRecord | None) -> str:
    return record.presentation_kind.value if record is not None else ""


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return value


def _enforce_offline_runtime() -> None:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _preflight_failure_payload(
    runtime: Mapping[str, object],
    *,
    source_identity_at_start: Mapping[str, object],
    failure_reason: str,
) -> dict[str, Any]:
    return {
        "schema": ARTIFACT_SCHEMA,
        "status": "blocked",
        "failure_reason": failure_reason,
        "runtime": _runtime_summary(dict(runtime)),
        "source_identity": dict(source_identity_at_start),
        "hf_offline": {
            "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE"),
            "TRANSFORMERS_OFFLINE": os.environ.get("TRANSFORMERS_OFFLINE"),
        },
        "prior_evidence_audit": [dict(item) for item in PRIOR_EVIDENCE_AUDIT],
        "screenshots": dict.fromkeys(REQUIRED_SCREENSHOTS, ""),
        "scenario": {},
        "host_assistance": {
            "classification": "host-assisted",
            "used": True,
            "actions": ["checked the exact offline runtime before opening the UI"],
        },
        "ui_state": {},
        "shutdown": {"status": "not_started", "detail": ""},
        "claim_boundary": _CLAIM_BOUNDARY,
        "elapsed_seconds": 0.0,
    }


def _print_artifact_paths(output_dir: Path, payload: Mapping[str, object]) -> None:
    print(f"status={payload.get('status')}")
    print(f"evidence_json={output_dir / JSON_ARTIFACT}")
    print(f"evidence_markdown={output_dir / MARKDOWN_ARTIFACT}")
