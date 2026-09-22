"""One fresh Windows ChatPanel case using the real product owners.

This subprocess receives a DEV case only. Oracle fields stay in result/scorer
code; only case input and the actual application publication reach the Assistant.
"""

from __future__ import annotations

# Phase failures are deliberately caught once to preserve partial artifacts.
# ruff: noqa: TRY301
import argparse
import hashlib
import json
import os
import re
import threading
import time
from contextlib import suppress
from pathlib import Path
from typing import Any


def validate_case_request(payload: dict) -> None:
    from scripts.dev.assistant_experiment_config import is_experiment_protocol
    from scripts.dev.assistant_pilot_bank import DEV_EXPERIMENT
    from scripts.dev.assistant_pilot_models import research_model_spec

    case, fixture = payload.get("case", {}), payload.get("fixture", {})
    experiment = payload.get("experiment")
    current = is_experiment_protocol(experiment)
    split = experiment["stage"] if current else "DEV"
    if experiment is not None and not current and experiment != DEV_EXPERIMENT:
        raise ValueError("Invalid frozen experiment policy")
    if current and (
        payload.get("split") != split
        or type(payload.get("candidate_index")) is not int
        or not 1 <= payload["candidate_index"] <= 5
        or not isinstance(payload.get("source_head"), str)
        or not re.fullmatch(r"[0-9a-f]{40}", payload["source_head"])
        or payload.get("rag_enabled") is not True
    ):
        raise ValueError("Invalid frozen experiment candidate identity")
    if (
        case.get("split") != split
        or not str(case.get("case_id", "")).startswith(split + "-")
        or not isinstance(case.get("input"), str)
        or not case["input"].strip()
        or len(case["input"]) > 8192
        or case.get("fixture_id") != fixture.get("metadata", {}).get("fixture_id")
        or case.get("expected_workflow_stage")
        != fixture.get("conditions", {}).get("stage")
        or type(payload.get("rag_enabled")) is not bool
        or type(payload.get("seed")) is not int
        or payload["seed"] != 0
        or type(payload.get("repeat")) is not int
        or payload["repeat"] not in (experiment["repeats"] if current else [0])
    ):
        raise ValueError("Invalid or unapproved Pilot case/condition")
    research_model_spec(payload.get("model_id", ""))


def experiment_result_identity(payload: dict) -> dict:
    """Copy already-admitted frozen identity into new results; legacy bytes stay distinct."""
    from scripts.dev.assistant_experiment_config import is_experiment_protocol

    if not is_experiment_protocol(payload.get("experiment")):
        return {}
    return {
        key: payload[key]
        for key in (
            "experiment",
            "candidate_index",
            "split",
            "repeat",
            "seed",
            "source_head",
        )
    }


def verify_prompt_captures(
    root: Path,
    generations: list[dict],
    *,
    warmup_count: int,
    start_index: int = 0,
) -> dict:
    """Bind actual final rendered prompts/raw outputs to ordered observations."""
    issues, captures = [], []
    all_paths = sorted(
        root.glob("*/*/metadata.json"),
        key=lambda p: (p.parent.parent.name, int(p.parent.name)),
    )
    if type(start_index) is not int or start_index < 0 or start_index > len(all_paths):
        raise ValueError("Invalid prompt capture boundary")
    paths = all_paths[start_index:]
    if len(paths) != len(generations) + warmup_count:
        issues.append("capture_count_mismatch")
    for index, path in enumerate(paths):
        metadata = json.loads(path.read_text(encoding="utf-8"))
        prompt = (path.parent / "prompt.txt").read_bytes()
        raw = (path.parent / "raw-output.txt").read_bytes()
        if (
            hashlib.sha256(prompt).hexdigest() != metadata["prompt_sha256"]
            or hashlib.sha256(raw).hexdigest() != metadata["raw_output_sha256"]
            or metadata["status"] not in {"completed", "cancelled", "failed"}
        ):
            issues.append("capture_integrity")
        capture = {"path": str(path.parent), "metadata": metadata}
        if index >= warmup_count:
            ordinal = index - warmup_count
            if ordinal < len(generations):
                generation = generations[ordinal]
                observed, captured = generation["raw_response"], raw.decode("utf-8")
                cancelled_prefix = (
                    generation.get("terminal") == "cancelled"
                    and metadata["status"] == "cancelled"
                    and captured.startswith(observed)
                )
                if captured != observed and not cancelled_prefix:
                    issues.append("capture_response_mismatch")
                capture["observed_raw_chars"] = len(observed)
                capture["unobserved_tail_chars"] = (
                    len(captured) - len(observed)
                    if captured == observed or cancelled_prefix
                    else None
                )
        captures.append(capture)
    return {"issues": issues, "captures": captures}


def audit_initial_input(
    case: dict, fixture: dict, trace: dict, *, decision_timed_out: bool = False
) -> dict:
    """Audit observed input provenance, not the semantic correctness of a question.

    RAG examples and action schemas contain parameter names/values by design;
    neither is an authoritative value supplied by this case's user or state.
    Semantic absence from reviewed English input remains a human-review claim.
    """
    issues, contexts = [], []
    generations = trace.get("generations", [])
    if not generations:
        submitted = [
            event.get("payload", {}).get("text")
            for event in trace.get("events", [])
            if event.get("kind") == "submission"
        ]
        if (
            decision_timed_out
            and submitted == [case["input"]]
            and trace.get("turn_terminal", {}).get("outcome") == "cancelled"
        ):
            return {
                "issues": [],
                "sent_to_model": False,
                "user_input_sha256": hashlib.sha256(case["input"].encode()).hexdigest(),
            }
        return {"issues": ["initial_input_not_observed"]}
    messages = [dict(message) for message in generations[0]["request"]["messages"]]
    requests = []
    for message in messages:
        role, content = message.get("role"), message.get("content")
        if role == "system":
            continue
        if role != "user":
            issues.append("initial_conversation_not_fresh")
            continue
        try:
            value = json.loads(content)
        except (ValueError, TypeError):
            value = None
        if (
            isinstance(value, dict)
            and value.get("schema") == "xbrainlab.untrusted_context.v1"
        ):
            if value.get("trust") != "untrusted":
                issues.append("context_trust_mismatch")
            contexts.extend(value.get("items", []))
        else:
            requests.append(content)
    if requests != [case["input"]]:
        issues.append("initial_user_input_mismatch")

    def has_value(value, key):
        if isinstance(value, dict):
            return (key in value and value[key] is not None) or any(
                has_value(item, key) for item in value.values()
            )
        return isinstance(value, list) and any(has_value(item, key) for item in value)

    state_cards = [
        item.get("data", {}) for item in contexts if item.get("type") == "state_card"
    ]
    missing = fixture.get("conditions", {}).get("missing_authoritative_values", [])
    for field in missing:
        if has_value(state_cards, field):
            issues.append("missing_value_present_in_state:" + field)
    return {
        "issues": list(dict.fromkeys(issues)),
        "user_input_sha256": hashlib.sha256(case["input"].encode()).hexdigest(),
        "state_card_count": len(state_cards),
        "untrusted_rag_example_count": sum(
            item.get("type") == "rag_example" for item in contexts
        ),
        "missing_authoritative_values": missing,
        "human_review_required_for_input_semantics": bool(missing),
    }


def _write(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def bootstrap_case_checkout() -> None:
    """Exclude other editable checkouts in this process, then enforce identity."""
    import sys

    root = Path(__file__).resolve().parents[2]
    sys.path[:] = [
        entry
        for entry in sys.path
        if Path(entry or ".").resolve() == root
        or not (Path(entry or ".") / "XBrainLab" / "__init__.py").is_file()
    ]
    from scripts.dev.active_checkout import assert_active_checkout_import

    assert_active_checkout_import(root)


def force_case_exit(
    manager,
    result: dict,
    path: Path,
    *,
    exit_process=os._exit,
    cleanup_wait: float = 5.0,
) -> None:
    """Bound best-effort cleanup; diagnostics must never defeat the hard exit."""
    processes = []
    owners = []
    try:
        controller = getattr(manager, "agent_controller", None)
        worker = getattr(controller, "worker", None)
        owners = [
            getattr(worker, "engine", None),
            getattr(controller, "_rag_lifecycle", None),
        ]
        processes = [getattr(owner, "_process", None) for owner in owners]
        result.update(
            status="measurement_failed", phase="hard_timeout", cleanup_ok=False
        )
        result.setdefault("issues", []).append("case_hard_timeout")

        def cleanup():
            for owner in owners:
                if owner is None:
                    continue
                with suppress(Exception):
                    owner.close()
            # Missing terminal evidence makes the parent refuse resumption.
            with suppress(Exception):
                _write(path, result)

        cleaner = threading.Thread(target=cleanup, daemon=True)
        cleaner.start()
        cleaner.join(timeout=cleanup_wait)
    finally:
        # These handles came only from this case's owners; never enumerate or
        # kill unrelated processes. A surviving child cannot outlive hard exit.
        for process in processes:
            with suppress(Exception):
                if process is not None and process.is_alive():
                    process.terminate()
                    process.join(timeout=1)
        exit_process(124)


def poll_case_safely(callback, result: dict, *, stop_poll, stop_generation) -> bool:
    """Keep Qt callback failures in case evidence and enter normal cleanup."""
    try:
        callback()
    except Exception as exc:
        if "poll_callback_failed" not in result["issues"]:
            result["issues"].append("poll_callback_failed")
        result["poll_error"] = {
            "error_type": type(exc).__name__,
            "detail": str(exc)[:1000],
        }
        for name, stop in (
            ("stop_poll", stop_poll),
            ("stop_generation", stop_generation),
        ):
            try:
                stop()
            except Exception as stop_error:
                result.setdefault("poll_stop_errors", []).append(
                    {
                        "operation": name,
                        "error_type": type(stop_error).__name__,
                        "detail": str(stop_error)[:1000],
                    }
                )
        return False
    return True


def submit_case_input(panel, text: str, wait_until) -> tuple[float, int]:
    """Fill the real composer before waiting for its input-dependent Send gate."""
    panel.input_field.setPlainText(text)
    wait_until(lambda: panel.send_btn.isEnabled() and panel.input_field.isEnabled(), 15)
    started_ns = time.perf_counter_ns()
    panel.send_btn.click()
    return started_ns / 1e9, started_ns


def record_decision_clock(
    result: dict, start_ns: int, end_ns: int | None, turn_end_ns: int
) -> None:
    """Record the existing observed decision boundary on one monotonic clock.

    An absent boundary remains an explicitly unobserved elapsed interval, never
    a fabricated terminal or a configured timeout. Scoring establishes validity.
    """
    effective_end = turn_end_ns if end_ns is None else end_ns
    if any(
        type(value) is not int for value in (start_ns, effective_end, turn_end_ns)
    ) or not (0 <= start_ns <= effective_end <= turn_end_ns):
        raise ValueError("Invalid decision clock interval")
    result["decision_clock"] = {
        "clock": "perf_counter_ns",
        "start_ns": start_ns,
        "end_ns": effective_end,
        "turn_end_ns": turn_end_ns,
        "terminal_observed": end_ns is not None,
    }
    result["decision_seconds"] = (effective_end - start_ns) / 1e9
    result["case_turn_seconds"] = (turn_end_ns - start_ns) / 1e9
    result["case_operation_seconds"] = (turn_end_ns - effective_end) / 1e9


def run_case(payload: dict, output: Path) -> dict[str, Any]:
    """Run in a dedicated process; never call concurrently in a shared UI process."""
    from scripts.dev.assistant_experiment_config import is_experiment_protocol

    if is_experiment_protocol(payload.get("experiment")):
        raise ValueError("configured experiments require batched condition entry")
    output = output.absolute()
    output.mkdir()  # A previous case/result must never be overwritten.
    for name, suffix in (
        ("XBRAINLAB_CONFIG_DIR", "config"),
        ("XBRAINLAB_LOG_DIR", "logs"),
        ("XBRAINLAB_CACHE_DIR", "cache"),
        ("XBRAINLAB_DATA_DIR", "data"),
        ("XBRAINLAB_ASSISTANT_PROMPT_CAPTURE_DIR", "prompts"),
    ):
        os.environ[name] = str(output / suffix)
    os.environ.update(
        HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1"
    )
    bootstrap_case_checkout()
    if payload.get("rag_enabled"):
        os.environ["XBRAINLAB_RAG_CACHE_DIR"] = payload["rag_cache"]
    else:
        os.environ["XBRAINLAB_RAG_CACHE_DIR"] = str(output / "unused-rag")
    validate_case_request(payload)
    from dataclasses import asdict
    from functools import partial

    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication

    from scripts.dev.assistant_pilot_fixture import prepare_fixture
    from scripts.dev.assistant_pilot_models import (
        build_frozen_config,
        build_research_worker,
        make_launch_spec,
    )
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
    from scripts.dev.assistant_pilot_ui import PilotUiDriver
    from scripts.dev.capture_chatpanel_local_walkthrough import collect_visible_messages
    from XBrainLab.backend.application import get_application_service
    from XBrainLab.backend.application.owned_work import OwnedWorkKind
    from XBrainLab.backend.study import Study
    from XBrainLab.llm.agent.controller import LLMController
    from XBrainLab.llm.core.generation import GenerationProfile
    from XBrainLab.ui.components.agent_manager import AgentManager
    from XBrainLab.ui.components.assistant_runtime_lifecycle import (
        AssistantRuntimeLifecycle,
    )
    from XBrainLab.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    study = Study()
    service = get_application_service(study)
    case = payload["case"]
    result = {
        "schema": "xbrainlab.assistant_pilot_case.v1",
        **experiment_result_identity(payload),
        "case_id": case["case_id"],
        "model_id": payload["model_id"],
        "rag_enabled": payload["rag_enabled"],
        "status": "running",
        "phase": "fixture",
        "issues": [],
        "decision_timed_out": False,
        "jobs": {},
        "case": case,
    }
    started = time.perf_counter()
    path = output / "result.json"
    _write(path, result)
    manager = runtime = window = trace = driver = None

    def hard_stop():
        force_case_exit(manager, result, path)

    watchdog = threading.Timer(420, hard_stop)
    watchdog.start()

    def wait_until(predicate, seconds: float):
        deadline = time.perf_counter() + seconds
        while not predicate():
            if time.perf_counter() >= deadline:
                raise TimeoutError("Bounded case phase deadline exceeded")
            app.processEvents()
            time.sleep(0.005)
        app.processEvents()

    try:
        before = time.perf_counter()
        deferred_training = case["expected_workflow_stage"] == "training"
        fixture = (
            None
            if deferred_training
            else prepare_fixture(study, payload["fixture"], output / "fixture")
        )
        result.update(
            fixture=fixture,
            fixture_seconds=time.perf_counter() - before,
            phase="loading",
        )
        _write(path, result)
        launch = make_launch_spec(payload["model_id"], payload["model_cache"])

        def factory(host, actual_study, *, application_service):
            nonlocal manager, runtime, driver

            def controller_factory(actual):
                controller = LLMController(
                    actual,
                    rag_enabled=payload["rag_enabled"],
                    worker_factory=partial(build_research_worker, launch),
                )
                driver.attach(controller)  # Before host connects modal callbacks.
                return controller

            runtime = AssistantRuntimeLifecycle(
                actual_study,
                controller_factory=controller_factory,
                config_loader=partial(build_frozen_config, launch),
                parent=host,
            )
            manager = AgentManager(
                host,
                actual_study,
                application_service=application_service,
                runtime_lifecycle=runtime,
            )
            driver = PilotUiDriver(
                host, manager, output / "ui", allow_confirmation=True
            )
            return manager

        window = MainWindow(study, agent_manager_factory=factory)
        window.resize(1280, 800)
        window.show()
        window.init_agent()
        manager.chat_dock.show()
        began = time.perf_counter()
        if not runtime.start(launch_spec=launch):
            raise RuntimeError("Explicit research launch rejected")
        wait_until(
            lambda: runtime.accepts_commands or runtime.current.phase.value == "failed",
            180,
        )
        if not runtime.accepts_commands:
            raise RuntimeError("Pinned model runtime failed to become ready")
        result["model_load_seconds"] = time.perf_counter() - began
        result["runtime"] = asdict(runtime.current)
        result["phase"] = "warmup"
        # A single fixed warm-up through the same owned engine; no conversation,
        # fixture, oracle or cases are used, and its capture stays separate.
        warm = {}

        def warmup():
            try:
                warm["output"] = "".join(
                    manager.agent_controller.worker.engine.generate_stream(
                        [
                            {
                                "role": "user",
                                "content": "Reply with the single word READY.",
                            }
                        ],
                        profile=GenerationProfile.STRUCTURED_DECISION,
                    )
                )
            except Exception as exc:
                warm["error"] = str(exc)

        thread = threading.Thread(target=warmup, daemon=True)
        began = time.perf_counter()
        thread.start()
        wait_until(lambda: not thread.is_alive(), 120)
        result["warmup"] = {**warm, "seconds": time.perf_counter() - began}
        if warm.get("error") or not warm.get("output", "").strip():
            raise RuntimeError("Warm-up failed")
        if payload["rag_enabled"]:
            rag_result = {}

            def rag_ready(_turn, _query, features, error):
                rag_result.update(features=features, error=error)

            began = time.perf_counter()
            lifecycle = manager.agent_controller._rag_lifecycle
            if not lifecycle.retrieve(0, "Open preprocessing.", rag_ready):
                raise RuntimeError("RAG initialization probe was not accepted")
            wait_until(lambda: bool(rag_result), 150)
            result["rag_warmup"] = {
                **rag_result,
                "seconds": time.perf_counter() - began,
            }
            if rag_result["error"]:
                raise RuntimeError("RAG on unavailable")
        if deferred_training:
            before = time.perf_counter()
            fixture = prepare_fixture(
                study,
                payload["fixture"],
                output / "fixture",
                running_training_epochs=10000,
            )
            result.update(fixture=fixture, fixture_seconds=time.perf_counter() - before)
        state = service.get_state()
        if state.pipeline_stage != fixture["stage"]:
            raise RuntimeError("Fixture stage drift before submission")
        result["before_state"] = state.to_dict()
        result["phase"] = "decision"
        trace = PilotCaseTrace(case["case_id"])
        trace.attach(manager.agent_controller, runtime)
        panel = manager.chat_panel
        before_decision, before_decision_ns = submit_case_input(
            panel, case["input"], wait_until
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
            evidence = collect_runtime_evidence(service, snapshot, fixture, window)
            if any(e["kind"] == "turn_terminal" for e in events):
                turn_done = True
            now = time.perf_counter()
            if (
                decision_done_at is None
                and now >= deadline
                and not result["decision_timed_out"]
            ):
                result["decision_timed_out"] = True
                runtime.stop_generation()
                operation_deadline = now + 10
            if decision_done_at is not None and operation_deadline is None:
                operation_deadline = now + 60
            if operation_deadline is not None and now >= operation_deadline:
                if (
                    not turn_done
                    or evidence["waiting"]
                    or driver.snapshot()["pending_count"]
                ):
                    result["issues"].append("product_or_cancel_deadline")
                    turn_done = True
            if fixture["stage"] == "training":
                initial = service.get_owned_operation(
                    fixture["jobs"]["training"]["operation_id"]
                )
                if (turn_done or now >= deadline) and not initial.phase.terminal:
                    # Bound fixture CPU work even if the model chose a different
                    # action. This is runner cleanup, never a model stop success.
                    if not result.get("fixture_cancel_requested"):
                        result["fixture_cancel_requested"] = {
                            "operation_id": initial.operation_id,
                            "elapsed_seconds": now - before_decision,
                            "accepted": service.cancel_owned_operation(
                                initial.operation_id
                            ),
                        }
                if initial.phase.value == "completed" and decision_done_at is None:
                    result["issues"].append("running_fixture_drift")
                    runtime.stop_generation()
                    turn_done = True

        poll = QTimer()
        poll.setInterval(20)

        def safe_tick():
            nonlocal turn_done
            if not poll_case_safely(
                tick,
                result,
                stop_poll=poll.stop,
                stop_generation=runtime.stop_generation,
            ):
                turn_done = True

        poll.timeout.connect(safe_tick)
        poll.start()
        try:
            wait_until(
                lambda: turn_done
                and (
                    result["issues"]
                    or (
                        not evidence["waiting"]
                        and driver.snapshot()["pending_count"] == 0
                    )
                ),
                195,
            )
        finally:
            poll.stop()
        app.processEvents()
        result["trace"] = trace.snapshot()
        record_decision_clock(
            result,
            before_decision_ns,
            decision_boundary_ns(result["trace"]),
            time.perf_counter_ns(),
        )
        result["ui"] = driver.snapshot()
        result["runtime_evidence"] = collect_runtime_evidence(
            service, result["trace"], fixture, window
        )
        result["jobs"] = result["runtime_evidence"]["jobs"]
        result["issues"].extend(result["runtime_evidence"]["issues"])
        result["issues"].extend(ui_measurement_issues(result["ui"]))
        result["after_state"] = service.get_state().to_dict()
        result["visible_messages"] = [
            asdict(item) for item in collect_visible_messages(panel)
        ]
        result["capture_audit"] = verify_prompt_captures(
            output / "prompts", result["trace"]["generations"], warmup_count=1
        )
        result["scores"] = score_case_decisions(
            case,
            result["trace"],
            decision_timed_out=result["decision_timed_out"],
            max_format_recovery_attempts=payload.get("experiment", {}).get(
                "max_format_recovery_attempts"
            ),
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
            status="measurement_failed", error_type=type(exc).__name__, detail=str(exc)
        )
    finally:
        if trace is not None:
            result.setdefault("trace", trace.snapshot())
            trace.detach()
        if driver is not None:
            result.setdefault("ui", driver.snapshot())
            driver.close()
        cleanup_started = time.perf_counter()
        # Only this fresh service's owned jobs; no shared Study is accepted.
        service.cancel_all_owned_operations()
        try:
            wait_until(
                lambda: all(
                    service.get_active_owned_operation(kind) is None
                    for kind in (OwnedWorkKind.TRAINING, OwnedWorkKind.SALIENCY)
                ),
                10,
            )
            if manager is not None:
                wait_until(manager.close, 15)
            if window is not None:
                window.close()
                wait_until(lambda: not window.isVisible(), 15)
            service.close()
            result["cleanup_ok"] = True
        except Exception as exc:
            result.update(
                cleanup_ok=False, status="measurement_failed", cleanup_error=str(exc)
            )
        watchdog.cancel()
        result["cleanup_seconds"] = time.perf_counter() - cleanup_started
        result["total_seconds"] = time.perf_counter() - started
        result["phase"] = "finished"
        _write(path, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not args.request.is_absolute() or not args.output.is_absolute():
        parser.error("Research request/output paths must be absolute")
    payload = json.loads(args.request.read_text(encoding="utf-8"))
    result = run_case(payload, args.output)
    print(
        json.dumps({"case_id": result["case_id"], "status": result["status"]}),
        flush=True,
    )
    return 0 if result["status"] == "recorded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
