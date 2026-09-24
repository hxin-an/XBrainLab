"""Passive, bounded evidence for one real Assistant turn; never an executor.

Timestamps measure observer receipt on one monotonic clock, not GPU kernel time.
No case oracle is accepted. UI readiness and asynchronous product completion
require separate real observations; neither is inferred from a turn terminal.
"""

from __future__ import annotations

import json
from contextlib import suppress
from dataclasses import fields, is_dataclass
from enum import Enum
from functools import partial
from threading import RLock
from time import perf_counter_ns
from typing import Any

from PyQt6.QtCore import Qt, pyqtBoundSignal

from XBrainLab.llm.agent.turn import AssistantGenerationRequest
from XBrainLab.llm.core.generation import GenerationProfile


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return _plain(value.value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        payload = {
            field.name: _plain(getattr(value, field.name)) for field in fields(value)
        }
        if isinstance(value, AssistantGenerationRequest):
            if value.generation_profile is not GenerationProfile.STRUCTURED_DECISION:
                raise ValueError("Unsupported Assistant generation evidence profile")
            # Preserve the persisted research contract, not a product request field.
            payload["response_contract"] = "structured_action"
        return payload
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    raise TypeError("Unsupported evidence payload; do not stringify live objects")


class PilotCaseTrace:
    """Record existing events for one case without owning product state."""

    def __init__(
        self,
        case_id: str,
        *,
        clock=perf_counter_ns,
        max_events: int = 20_000,
        max_bytes: int = 16 * 1024 * 1024,
    ):
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("A case identity is required")
        if max_events < 1 or max_bytes < 1:
            raise ValueError("Trace limits must be positive")
        self.case_id = case_id
        self._clock, self._origin = clock, clock()
        self._max_events, self._max_bytes = max_events, max_bytes
        self._bytes = 0
        self._events: list[dict] = []
        self._issues: list[str] = []
        self._connections: list[tuple[Any, Any]] = []
        self._correlation: dict | None = None
        self._lock = RLock()
        self._accepting = False

    def _issue(self, reason: str) -> None:
        if reason not in self._issues and len(self._issues) < 32:
            self._issues.append(reason)

    def attach(self, controller, runtime) -> None:
        """Attach before ChatPanel submission; use a fresh trace per case."""
        if self._connections or self._events:
            raise ValueError("Trace already used")
        self._accepting = True
        channels = (
            (runtime.dispatcher, "input_requested", "submission"),
            (runtime.dispatcher, "turn_delivery_acknowledged", "delivery"),
            (runtime.dispatcher, "confirmation_requested", "confirmation_submitted"),
            (
                runtime.dispatcher,
                "workflow_ui_handoff_resolved_requested",
                "ui_resolution",
            ),
            (controller, "sig_generate", "generation_request"),
            (controller, "generation_event", "generation_event"),
            (controller, "decision_observed", "host_decision"),
            (controller, "application_command_started", "command_started"),
            (controller, "application_command_completed", "command_result"),
            (controller, "confirmation_requested", "confirmation_requested"),
            (controller, "workflow_ui_handoff_requested", "ui_requested"),
            (controller, "panel_navigation_requested", "navigation_requested"),
            (controller, "interaction_resolved", "interaction_resolved"),
            (controller, "activity_changed", "activity"),
            (controller, "response_presentation_ready", "presentation"),
            (controller, "turn_finished", "controller_terminal"),
            (runtime, "turn_finished", "turn_terminal"),
        )
        try:
            for owner, name, kind in channels:
                signal = getattr(owner, name)
                callback = partial(self._observe, kind)
                if isinstance(signal, pyqtBoundSignal):
                    signal.connect(callback, Qt.ConnectionType.DirectConnection)
                else:
                    signal.connect(callback)
                self._connections.append((signal, callback))
        except Exception:
            self.detach()
            raise

    def detach(self) -> None:
        """Disconnect only this collector's callbacks; preserve captured evidence."""
        with self._lock:
            self._accepting = False
        for signal, callback in self._connections:
            # QObject may already have been destroyed by normal close.
            with suppress(TypeError, RuntimeError):
                signal.disconnect(callback)
        self._connections.clear()

    def _observe(self, kind: str, payload: Any = None) -> None:
        # A bad observer must not alter Qt delivery or execution semantics.
        with self._lock:
            if not self._accepting:
                return
            if len(self._events) >= self._max_events or self._bytes >= self._max_bytes:
                self._issue("trace_limit_exceeded")
                return
            try:
                encoded = json.dumps(
                    _plain(payload), allow_nan=False, ensure_ascii=False
                )
                size = len(encoded.encode("utf-8"))
                value = json.loads(encoded)
                elapsed = self._clock() - self._origin
            except Exception:
                self._issue("unserializable_event")
                return
            if self._bytes + size > self._max_bytes:
                self._issue("trace_limit_exceeded")
                return
            if kind != "command_started" and not isinstance(value, dict):
                self._issue("invalid_event_shape")
                return
            if kind in {"generation_request", "generation_event"}:
                identity = value.get("generation_id")
                if type(identity) is not int or identity <= 0:
                    self._issue("invalid_generation_identity")
                    return
                if kind == "generation_event" and (
                    value.get("phase")
                    not in {"started", "chunk", "finished", "error", "cancelled"}
                    or not isinstance(value.get("text"), str)
                ):
                    self._issue("invalid_generation_event")
                    return
            correlation = value.get("correlation") if isinstance(value, dict) else None
            if (
                isinstance(value, dict)
                and value.get("turn_id") is not None
                and value.get("generation") is not None
            ):
                correlation = {
                    "turn_id": value["turn_id"],
                    "generation": value["generation"],
                }
            if kind == "submission":
                if self._correlation is not None:
                    self._issue("multiple_submissions")
                    return
                if not isinstance(correlation, dict):
                    self._issue("missing_submission_correlation")
                    return
                self._correlation = correlation
            if (
                correlation is not None
                and self._correlation is not None
                and correlation != self._correlation
            ):
                self._issue("foreign_correlation")
                return
            if elapsed < 0 or (
                self._events and elapsed < self._events[-1]["elapsed_ns"]
            ):
                self._issue("nonmonotonic_clock")
            self._bytes += size
            self._events.append(
                {
                    "sequence": len(self._events) + 1,
                    "elapsed_ns": elapsed,
                    "kind": kind,
                    "payload": value,
                    "observed_turn": self._correlation,
                }
            )

    def snapshot(self) -> dict:
        """Return detached evidence and completeness diagnostics, never a score."""
        with self._lock:
            events = json.loads(json.dumps(self._events))
            issues = list(self._issues)
            correlation = (
                dict(self._correlation) if self._correlation is not None else None
            )
        generations: dict[int, dict] = {}
        terminal = None
        for event in events:
            kind, payload = event["kind"], event["payload"]
            explicit_correlation = (
                payload.get("correlation") if isinstance(payload, dict) else None
            )
            if explicit_correlation is not None and explicit_correlation != correlation:
                issues.append("foreign_correlation")
            if kind == "host_decision" and payload.get("enabled") is True:
                if (
                    payload.get("kind") == "rag_request"
                    and payload.get("accepted") is False
                ):
                    issues.append("rag_retrieval_unavailable")
                if payload.get("kind") == "rag" and payload.get("error"):
                    issues.append("rag_retrieval_error")
            if kind == "turn_terminal":
                if terminal is not None:
                    issues.append("duplicate_turn_terminal")
                terminal = payload
            if kind not in {"generation_request", "generation_event"}:
                continue
            generation_id = payload["generation_id"]
            item = generations.setdefault(
                generation_id,
                {
                    "generation_id": generation_id,
                    "request": None,
                    "raw_response": "",
                    "terminal": None,
                    "started": False,
                },
            )
            if kind == "generation_request":
                if item["request"] is not None:
                    issues.append(f"duplicate_generation_request:{generation_id}")
                item["request"] = payload
            elif payload["phase"] == "chunk":
                if item["terminal"] is not None:
                    issues.append(f"chunk_after_terminal:{generation_id}")
                item["raw_response"] += payload["text"]
            elif payload["phase"] == "started":
                item["started"] = True
            else:
                if item["terminal"] is not None:
                    issues.append(f"duplicate_generation_terminal:{generation_id}")
                item["terminal"] = payload["phase"]
        if not any(event["kind"] == "submission" for event in events):
            issues.append("missing_submission")
        if terminal is None:
            issues.append("missing_turn_terminal")
        if not generations:
            issues.append("missing_generation")
        for generation_id, item in generations.items():
            for field in ("request", "terminal"):
                if item[field] is None:
                    issues.append(f"missing_generation_{field}:{generation_id}")
            if not item["started"] and item["terminal"] not in {"error", "cancelled"}:
                issues.append(f"missing_generation_start:{generation_id}")
        return {
            "case_id": self.case_id,
            "origin_monotonic_ns": self._origin,
            "timestamp_basis": "observer_receipt_monotonic_ns",
            "events": events,
            "generations": list(generations.values()),
            "turn_terminal": terminal,
            "measurement_issues": list(dict.fromkeys(issues)),
            "ui_readiness": "not_observed",
        }
