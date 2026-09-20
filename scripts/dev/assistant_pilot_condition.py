"""Run one frozen model/RAG condition with a reusable product runtime.

The loaded local model and RAG index are condition-scoped.  EEG workflow state,
Assistant conversation, UI evidence, trace, deadlines, and results remain
case-scoped and must cross an audited reset boundary before the next case.
"""

from __future__ import annotations

# Phase failures are caught once so partial evidence survives a failed condition.
# ruff: noqa: TRY301
import argparse
import json
import os
import threading
import time
from dataclasses import asdict
from functools import partial
from pathlib import Path
from typing import Any

from scripts.dev.assistant_pilot_case import (
    _write,
    audit_initial_input,
    bootstrap_case_checkout,
    force_case_exit,
    poll_case_safely,
    submit_case_input,
    validate_case_request,
    verify_prompt_captures,
)

SCHEMA = "xbrainlab.assistant_pilot_condition.v1"


def _capture_paths(root: Path) -> list[Path]:
    return sorted(
        root.glob("*/*/metadata.json"),
        key=lambda path: (path.parent.parent.name, int(path.parent.name)),
    )


def validate_condition_request(payload: dict) -> None:
    jobs = payload.get("jobs")
    if (
        payload.get("schema") != SCHEMA
        or not isinstance(payload.get("condition"), str)
        or not isinstance(jobs, list)
        or not 1 <= len(jobs) <= 30
        or any(
            not isinstance(job, dict)
            or not isinstance(job.get("id"), str)
            or not job["id"]
            or not isinstance(job.get("payload"), dict)
            for job in jobs
        )
        or len({job["id"] for job in jobs}) != len(jobs)
    ):
        raise ValueError("Invalid Pilot condition request")
    for job in jobs:
        validate_case_request(job["payload"])
    first = jobs[0]["payload"]
    identity = (
        first["model_id"],
        first["model_cache"],
        first["rag_enabled"],
        first.get("rag_cache"),
        first["seed"],
        first["repeat"],
    )
    if any(
        (
            job["payload"]["model_id"],
            job["payload"]["model_cache"],
            job["payload"]["rag_enabled"],
            job["payload"].get("rag_cache"),
            job["payload"]["seed"],
            job["payload"]["repeat"],
        )
        != identity
        for job in jobs[1:]
    ):
        raise ValueError("A condition child cannot mix runtime identities")


class PilotConditionSession:
    """Own one normal product host and its pinned model for several fresh cases."""

    def __init__(self, payload: dict, root: Path, first_output: Path):
        self.closed = False
        self.manager = self.runtime = self.window = self.driver = None
        self.service = None
        validate_case_request(payload)
        self.root = root.absolute()
        self.prompt_root = self.root / "prompts"
        for name, suffix in (
            ("XBRAINLAB_CONFIG_DIR", "config"),
            ("XBRAINLAB_LOG_DIR", "logs"),
            ("XBRAINLAB_CACHE_DIR", "cache"),
            ("XBRAINLAB_DATA_DIR", "data"),
            ("XBRAINLAB_ASSISTANT_PROMPT_CAPTURE_DIR", "prompts"),
        ):
            os.environ[name] = str(self.root / suffix)
        os.environ.update(
            HF_HUB_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
            HF_HUB_DISABLE_TELEMETRY="1",
        )
        os.environ["XBRAINLAB_RAG_CACHE_DIR"] = (
            payload["rag_cache"]
            if payload["rag_enabled"]
            else str(self.root / "unused-rag")
        )
        bootstrap_case_checkout()

        from PyQt6.QtWidgets import QApplication

        from scripts.dev.assistant_pilot_models import (
            build_frozen_config,
            build_research_worker,
            make_launch_spec,
        )
        from scripts.dev.assistant_pilot_ui import PilotUiDriver
        from XBrainLab.backend.application import get_application_service
        from XBrainLab.backend.study import Study
        from XBrainLab.llm.agent.controller import LLMController
        from XBrainLab.llm.core.generation import GenerationProfile
        from XBrainLab.ui.components.agent_manager import AgentManager
        from XBrainLab.ui.components.assistant_runtime_lifecycle import (
            AssistantRuntimeLifecycle,
        )
        from XBrainLab.ui.main_window import MainWindow

        self.identity = {
            key: payload.get(key)
            for key in (
                "model_id",
                "model_cache",
                "rag_enabled",
                "rag_cache",
                "seed",
                "repeat",
            )
        }
        self.app = QApplication.instance() or QApplication([])
        self.app.setQuitOnLastWindowClosed(False)
        self.study = Study()
        self.service = get_application_service(self.study)
        self.case_index = 0
        self.launch = make_launch_spec(payload["model_id"], payload["model_cache"])
        first_output.mkdir()

        def factory(host, actual_study, *, application_service):
            def controller_factory(actual):
                controller = LLMController(
                    actual,
                    rag_enabled=payload["rag_enabled"],
                    worker_factory=partial(build_research_worker, self.launch),
                )
                self.driver.attach(controller)
                return controller

            self.runtime = AssistantRuntimeLifecycle(
                actual_study,
                controller_factory=controller_factory,
                config_loader=partial(build_frozen_config, self.launch),
                parent=host,
            )
            self.manager = AgentManager(
                host,
                actual_study,
                application_service=application_service,
                runtime_lifecycle=self.runtime,
            )
            self.driver = PilotUiDriver(
                host,
                self.manager,
                first_output / "ui",
                allow_confirmation=True,
            )
            return self.manager

        self.window = MainWindow(self.study, agent_manager_factory=factory)
        self.window.resize(1280, 800)
        self.window.show()
        self.window.init_agent()
        self.manager.chat_dock.show()
        began = time.perf_counter()
        if not self.runtime.start(launch_spec=self.launch):
            raise RuntimeError("Explicit research launch rejected")
        self.wait_until(
            lambda: self.runtime.accepts_commands
            or self.runtime.current.phase.value == "failed",
            180,
        )
        if not self.runtime.accepts_commands:
            raise RuntimeError("Pinned model runtime failed to become ready")
        model_load_seconds = time.perf_counter() - began
        warm: dict[str, str] = {}

        def warmup():
            try:
                warm["output"] = "".join(
                    self.manager.agent_controller.worker.engine.generate_stream(
                        [
                            {
                                "role": "user",
                                "content": "Reply with the single word READY.",
                            }
                        ],
                        profile=GenerationProfile.STRUCTURED_DECISION,
                    )
                )
            except Exception as exc:  # pragma: no cover - real backend evidence
                warm["error"] = str(exc)

        thread = threading.Thread(target=warmup, daemon=True)
        began = time.perf_counter()
        thread.start()
        self.wait_until(lambda: not thread.is_alive(), 120)
        warm["seconds"] = time.perf_counter() - began
        if warm.get("error") or not warm.get("output", "").strip():
            raise RuntimeError("Warm-up failed")
        if len(_capture_paths(self.prompt_root)) != 1:
            raise RuntimeError("Condition warm-up capture is not isolated")

        rag_warmup = None
        if payload["rag_enabled"]:
            rag_result: dict[str, Any] = {}

            def rag_ready(_turn, _query, features, error):
                rag_result.update(features=features, error=error)

            began = time.perf_counter()
            lifecycle = self.manager.agent_controller._rag_lifecycle
            if not lifecycle.retrieve(0, "Open preprocessing.", rag_ready):
                raise RuntimeError("RAG initialization probe was not accepted")
            self.wait_until(lambda: bool(rag_result), 150)
            rag_warmup = {**rag_result, "seconds": time.perf_counter() - began}
            if rag_result["error"]:
                raise RuntimeError("RAG on unavailable")
        self.condition_evidence = {
            "model_load_seconds": model_load_seconds,
            "warmup": warm,
            "rag_warmup": rag_warmup,
            "runtime": asdict(self.runtime.current),
        }

    def wait_until(self, predicate, seconds: float) -> None:
        deadline = time.perf_counter() + seconds
        while not predicate():
            if time.perf_counter() >= deadline:
                raise TimeoutError("Bounded condition phase deadline exceeded")
            self.app.processEvents()
            time.sleep(0.005)
        self.app.processEvents()

    def _assert_identity(self, payload: dict) -> None:
        validate_case_request(payload)
        actual = {
            key: payload.get(key)
            for key in (
                "model_id",
                "model_cache",
                "rag_enabled",
                "rag_cache",
                "seed",
                "repeat",
            )
        }
        if actual != self.identity:
            raise ValueError("Case runtime identity differs from its condition")

    def _boundary_clean(self) -> bool:
        from scripts.dev.capture_chatpanel_local_walkthrough import (
            collect_visible_messages,
        )
        from XBrainLab.backend.application.owned_work import OwnedWorkKind

        controller = self.manager.agent_controller
        pending = controller.pending_interactions
        state = self.service.get_state()
        return bool(
            self.runtime.accepts_commands
            and not self.runtime.turn_in_flight
            and not controller.is_processing
            and controller.history == []
            and pending.confirmation is None
            and pending.workflow_handoff is None
            and pending.tool_input is None
            and pending.active_tool_input is None
            and collect_visible_messages(self.manager.chat_panel) == []
            and all(
                self.service.get_active_owned_operation(kind) is None
                for kind in (OwnedWorkKind.TRAINING, OwnedWorkKind.SALIENCY)
            )
            and not state.raw.loaded
            and not state.epoch.available
            and not state.dataset.available
            and not state.training.is_running
        )

    def _begin_case(self, payload: dict, output: Path) -> dict:
        from PyQt6.QtWidgets import QApplication

        from XBrainLab.backend.application import ResetSessionCommand
        from XBrainLab.llm.agent.response_presentation import (
            AssistantPanelNavigationRequest,
            AssistantPanelTarget,
        )

        self._assert_identity(payload)
        if self.case_index:
            output.mkdir()
            reset = self.service.execute(ResetSessionCommand(confirmed=True))
            if not reset.ok:
                raise RuntimeError("Product session reset was rejected")
            self.manager.start_new_conversation()
            self.manager.handle_panel_navigation(
                AssistantPanelNavigationRequest(AssistantPanelTarget.DATASET)
            )
            self.wait_until(self._boundary_clean, 20)
            modal = QApplication.activeModalWidget()
            if modal is not None:
                raise RuntimeError("An active modal crossed the case boundary")
            self.driver.begin_case(output / "ui")
        elif not output.is_dir():
            raise RuntimeError("First case output was not reserved by the condition")
        if not self._boundary_clean():
            raise RuntimeError("Condition did not reach a clean case boundary")
        return {
            "runtime_reused": self.case_index > 0,
            "model_id": self.runtime.current.model_id,
            "pipeline_stage": self.service.get_state().pipeline_stage,
            "conversation_messages": len(self.manager.agent_controller.history),
            "visible_messages": 0,
            "active_owned_operations": 0,
            "pending_interactions": 0,
        }

    def run_case(self, payload: dict, output: Path) -> dict[str, Any]:
        from PyQt6.QtCore import QTimer

        from scripts.dev.assistant_pilot_fixture import prepare_fixture
        from scripts.dev.assistant_pilot_observation import PilotCaseTrace
        from scripts.dev.assistant_pilot_outcome import (
            score_product_outcome,
            ui_measurement_issues,
        )
        from scripts.dev.assistant_pilot_runtime_evidence import (
            collect_runtime_evidence,
            decision_boundary_ns,
        )
        from scripts.dev.assistant_pilot_scoring import score_case_decisions
        from scripts.dev.capture_chatpanel_local_walkthrough import (
            collect_visible_messages,
        )
        from XBrainLab.backend.application.owned_work import OwnedWorkKind

        case = payload["case"]
        result: dict[str, Any] = {
            "schema": "xbrainlab.assistant_pilot_case.v1",
            "case_id": case["case_id"],
            "model_id": payload["model_id"],
            "rag_enabled": payload["rag_enabled"],
            "status": "running",
            "phase": "boundary",
            "issues": [],
            "decision_timed_out": False,
            "jobs": {},
            "case": case,
            "condition_evidence": self.condition_evidence,
        }
        started = time.perf_counter()
        path = output / "result.json"
        trace = None
        watchdog = threading.Timer(
            420,
            lambda: force_case_exit(self.manager, result, path),
        )
        watchdog.start()
        try:
            result["case_boundary"] = self._begin_case(payload, output)
            capture_start = len(_capture_paths(self.prompt_root))
            before = time.perf_counter()
            fixture = prepare_fixture(
                self.study,
                payload["fixture"],
                output / "fixture",
                **(
                    {"running_training_epochs": 10000}
                    if case["expected_workflow_stage"] == "training"
                    else {}
                ),
            )
            result.update(
                fixture=fixture,
                fixture_seconds=time.perf_counter() - before,
                model_load_seconds=(
                    self.condition_evidence["model_load_seconds"]
                    if self.case_index == 0
                    else 0.0
                ),
                runtime_reused=self.case_index > 0,
                runtime=asdict(self.runtime.current),
                phase="decision",
            )
            state = self.service.get_state()
            if state.pipeline_stage != fixture["stage"]:
                raise RuntimeError("Fixture stage drift before submission")
            result["before_state"] = state.to_dict()
            trace = PilotCaseTrace(case["case_id"])
            trace.attach(self.manager.agent_controller, self.runtime)
            panel = self.manager.chat_panel
            before_decision, before_decision_ns = submit_case_input(
                panel, case["input"], self.wait_until
            )
            _write(path, result)
            decision_done_at = None
            turn_done = False
            deadline = before_decision + 120
            operation_deadline = None
            evidence = {"waiting": False}

            def tick():
                nonlocal decision_done_at, turn_done, operation_deadline, evidence
                snapshot = trace.snapshot()
                events = snapshot["events"]
                observed_boundary = decision_boundary_ns(snapshot)
                if observed_boundary is not None:
                    decision_done_at = (
                        before_decision + (observed_boundary - before_decision_ns) / 1e9
                    )
                evidence = collect_runtime_evidence(
                    self.service, snapshot, fixture, self.window
                )
                if any(event["kind"] == "turn_terminal" for event in events):
                    turn_done = True
                now = time.perf_counter()
                if (
                    decision_done_at is None
                    and now >= deadline
                    and not result["decision_timed_out"]
                ):
                    result["decision_timed_out"] = True
                    self.runtime.stop_generation()
                    operation_deadline = now + 10
                if decision_done_at is not None and operation_deadline is None:
                    operation_deadline = now + 60
                if operation_deadline is not None and now >= operation_deadline:
                    if (
                        not turn_done
                        or evidence["waiting"]
                        or self.driver.snapshot()["pending_count"]
                    ):
                        result["issues"].append("product_or_cancel_deadline")
                        turn_done = True
                if fixture["stage"] == "training":
                    initial = self.service.get_owned_operation(
                        fixture["jobs"]["training"]["operation_id"]
                    )
                    if (turn_done or now >= deadline) and not initial.phase.terminal:
                        if not result.get("fixture_cancel_requested"):
                            result["fixture_cancel_requested"] = {
                                "operation_id": initial.operation_id,
                                "elapsed_seconds": now - before_decision,
                                "accepted": self.service.cancel_owned_operation(
                                    initial.operation_id
                                ),
                            }
                    if initial.phase.value == "completed" and decision_done_at is None:
                        result["issues"].append("running_fixture_drift")
                        self.runtime.stop_generation()
                        turn_done = True

            poll = QTimer()
            poll.setInterval(20)

            def safe_tick():
                nonlocal turn_done
                if not poll_case_safely(
                    tick,
                    result,
                    stop_poll=poll.stop,
                    stop_generation=self.runtime.stop_generation,
                ):
                    turn_done = True

            poll.timeout.connect(safe_tick)
            poll.start()
            try:
                self.wait_until(
                    lambda: turn_done
                    and (
                        result["issues"]
                        or (
                            not evidence["waiting"]
                            and self.driver.snapshot()["pending_count"] == 0
                        )
                    ),
                    195,
                )
            finally:
                poll.stop()
            self.app.processEvents()
            result["decision_seconds"] = (
                decision_done_at or time.perf_counter()
            ) - before_decision
            result["case_turn_seconds"] = time.perf_counter() - before_decision
            result["case_operation_seconds"] = max(
                0.0, result["case_turn_seconds"] - result["decision_seconds"]
            )
            result["trace"] = trace.snapshot()
            result["ui"] = self.driver.snapshot()
            result["runtime_evidence"] = collect_runtime_evidence(
                self.service, result["trace"], fixture, self.window
            )
            result["jobs"] = result["runtime_evidence"]["jobs"]
            result["issues"].extend(result["runtime_evidence"]["issues"])
            result["issues"].extend(ui_measurement_issues(result["ui"]))
            result["after_state"] = self.service.get_state().to_dict()
            result["visible_messages"] = [
                asdict(item) for item in collect_visible_messages(panel)
            ]
            result["capture_audit"] = verify_prompt_captures(
                self.prompt_root,
                result["trace"]["generations"],
                warmup_count=0,
                start_index=capture_start,
            )
            result["scores"] = score_case_decisions(
                case,
                result["trace"],
                decision_timed_out=result["decision_timed_out"],
            )
            result["input_audit"] = audit_initial_input(
                case,
                payload["fixture"],
                result["trace"],
                decision_timed_out=result["decision_timed_out"],
            )
            result["issues"].extend(result["input_audit"]["issues"])
            result["issues"].extend(result["capture_audit"]["issues"])
            result["issues"].extend(result["scores"]["measurement_issues"])
            result["product_outcome"] = score_product_outcome(case, result)
            result["issues"].extend(result["product_outcome"]["issues"])
            result["issues"] = list(dict.fromkeys(result["issues"]))
            result["status"] = "measurement_failed" if result["issues"] else "recorded"
        except Exception as exc:
            result.update(
                status="measurement_failed",
                error_type=type(exc).__name__,
                detail=str(exc),
            )
        finally:
            if trace is not None:
                result.setdefault("trace", trace.snapshot())
                trace.detach()
            result.setdefault("ui", self.driver.snapshot())
            cleanup_started = time.perf_counter()
            self.service.cancel_all_owned_operations()
            try:
                self.wait_until(
                    lambda: all(
                        self.service.get_active_owned_operation(kind) is None
                        for kind in (OwnedWorkKind.TRAINING, OwnedWorkKind.SALIENCY)
                    )
                    and not self.runtime.turn_in_flight
                    and not self.manager.agent_controller.is_processing
                    and self.driver.snapshot()["pending_count"] == 0,
                    15,
                )
                result["cleanup_ok"] = True
            except Exception as exc:
                result.update(
                    cleanup_ok=False,
                    status="measurement_failed",
                    cleanup_error=str(exc),
                )
            watchdog.cancel()
            result["cleanup_seconds"] = time.perf_counter() - cleanup_started
            result["total_seconds"] = time.perf_counter() - started
            result["phase"] = "finished"
            _write(path, result)
            self.case_index += 1
        return result

    def close(self) -> bool:
        if getattr(self, "closed", False):
            return True
        self.closed = True
        from XBrainLab.backend.application.owned_work import OwnedWorkKind

        clean = True
        try:
            service = getattr(self, "service", None)
            if service is not None:
                service.cancel_all_owned_operations()
                self.wait_until(
                    lambda: all(
                        service.get_active_owned_operation(kind) is None
                        for kind in (OwnedWorkKind.TRAINING, OwnedWorkKind.SALIENCY)
                    ),
                    10,
                )
            if self.driver is not None:
                self.driver.close()
            if self.manager is not None:
                self.wait_until(self.manager.close, 20)
            if self.window is not None:
                self.window.close()
                self.wait_until(lambda: not self.window.isVisible(), 15)
            if service is not None:
                service.close()
        except Exception:
            clean = False
        return clean


def run_condition(payload: dict, cases_root: Path, output: Path) -> dict:
    validate_condition_request(payload)
    output = output.absolute()
    cases_root = cases_root.absolute()
    output.mkdir()
    jobs = payload["jobs"]
    session = None
    results = []
    condition_started = time.perf_counter()
    summary = {
        "schema": SCHEMA,
        "condition": payload["condition"],
        "status": "running",
        "case_ids": [job["id"] for job in jobs],
        "results": results,
    }
    path = output / "result.json"
    _write(path, summary)
    try:
        first_output = cases_root / jobs[0]["id"]
        session = PilotConditionSession.__new__(PilotConditionSession)
        session.__init__(jobs[0]["payload"], output, first_output)
        summary["condition_evidence"] = session.condition_evidence
        for job in jobs:
            destination = cases_root / job["id"]
            if job is not jobs[0] and destination.exists():
                raise FileExistsError("Condition case output already exists")
            result = session.run_case(job["payload"], destination)
            results.append(
                {
                    "id": job["id"],
                    "case_id": result["case_id"],
                    "status": result["status"],
                    "cleanup_ok": result.get("cleanup_ok") is True,
                }
            )
            _write(path, summary)
            if result["status"] != "recorded" or result.get("cleanup_ok") is not True:
                break
        summary["status"] = (
            "recorded"
            if len(results) == len(jobs)
            and all(
                item["status"] == "recorded" and item["cleanup_ok"] for item in results
            )
            else "measurement_failed"
        )
    except Exception as exc:
        summary.update(
            status="measurement_failed",
            error_type=type(exc).__name__,
            detail=str(exc),
        )
    finally:
        summary["cleanup_ok"] = bool(session is not None and session.close())
        if not summary["cleanup_ok"]:
            summary["status"] = "measurement_failed"
        summary["total_seconds"] = time.perf_counter() - condition_started
        _write(path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--cases-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not all(
        path.is_absolute() for path in (args.request, args.cases_root, args.output)
    ):
        parser.error("Research request/output paths must be absolute")
    payload = json.loads(args.request.read_text(encoding="utf-8"))
    result = run_condition(payload, args.cases_root, args.output)
    print(
        json.dumps({"condition": result["condition"], "status": result["status"]}),
        flush=True,
    )
    return 0 if result["status"] == "recorded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
