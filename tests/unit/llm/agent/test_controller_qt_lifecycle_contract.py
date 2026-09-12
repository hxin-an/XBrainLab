"""Source and native lifecycle guards for the controller integration suite."""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path
from threading import Event
from time import monotonic
from typing import Any, cast

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QObject, Qt, pyqtSignal, pyqtSlot

CONTROLLER_SOURCE = Path(__file__).parents[4] / "XBrainLab/llm/agent/controller.py"
WORKER_SOURCE = Path(__file__).parents[4] / "XBrainLab/llm/agent/worker.py"
CONTROLLER_INTEGRATION_TEST = Path(__file__).with_name("test_controller_integration.py")


class _WorkerThreadBlocker(QObject):
    block_requested = pyqtSignal()

    def __init__(self, entered: Event, release: Event) -> None:
        super().__init__()
        self._entered = entered
        self._release = release
        self.block_requested.connect(self._block)

    @pyqtSlot()
    def _block(self) -> None:
        self._entered.set()
        self._release.wait(timeout=2)


class _DeferredRagLifecycle:
    """External RAG seam that leaves completion timing under the test's control."""

    retriever = object()

    def __init__(self, close_outcomes: list[bool | BaseException]) -> None:
        self._close_outcomes = close_outcomes
        self.close_calls = 0
        self.cancelled_turn_ids: list[int] = []
        self._callbacks: list[
            tuple[int, str, Callable[[int, str, str, str], None]]
        ] = []

    @property
    def pending_result_count(self) -> int:
        return len(self._callbacks)

    def retrieve(
        self,
        turn_id: int,
        query: str,
        callback: Callable[[int, str, str, str], None],
        *,
        allowed_tool_names: frozenset[str] | None = None,
    ) -> bool:
        del allowed_tool_names
        self._callbacks.append((turn_id, query, callback))
        return True

    def cancel_retrieval(self, turn_id: int) -> bool:
        self.cancelled_turn_ids.append(turn_id)
        return True

    def close(self) -> bool:
        self.close_calls += 1
        outcome = self._close_outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def deliver_latest_result(self) -> None:
        turn_id, query, callback = self._callbacks[-1]
        callback(turn_id, query, "late context", "")

    def permit_final_cleanup(self) -> None:
        self._close_outcomes[:] = [True]


def _controller_integration_tree() -> ast.Module:
    return ast.parse(CONTROLLER_INTEGRATION_TEST.read_text(encoding="utf-8"))


def test_controller_integration_does_not_replace_the_qobject_worker() -> None:
    """Keep integration coverage on the real QObject/QThread ownership path."""
    tree = _controller_integration_tree()
    patched_targets = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "patch"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }

    assert "XBrainLab.llm.agent.controller.AgentWorker" not in patched_targets


def test_controller_integration_fixture_owns_exception_safe_shutdown() -> None:
    """Keep native thread cleanup in fixture teardown, even after a failed assertion."""
    tree = _controller_integration_tree()
    fixture = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "controller"
    )
    yield_node = next(node for node in ast.walk(fixture) if isinstance(node, ast.Yield))
    teardown_close_calls = [
        node
        for node in ast.walk(fixture)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "close"
        and node.lineno > yield_node.lineno
    ]

    assert teardown_close_calls


def test_assistant_shutdown_source_forbids_nested_loops_and_blocking_waits() -> None:
    """Only an immediate native-completion probe may supplement Qt terminals."""
    forbidden: list[tuple[str, int]] = []

    for source in (CONTROLLER_SOURCE, WORKER_SOURCE):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "QEventLoop":
                forbidden.append((f"{source.name}:QEventLoop", node.lineno))
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "wait"
                and not (
                    len(node.args) == 1
                    and isinstance(node.args[0], ast.Constant)
                    and type(node.args[0].value) is int
                    and node.args[0].value == 0
                    and not node.keywords
                )
            ):
                forbidden.append((f"{source.name}:wait", node.lineno))

    assert forbidden == []


def test_real_controller_close_completes_from_worker_and_thread_signals(qtbot) -> None:
    """The first close returns immediately; Qt terminals complete ownership."""
    from XBrainLab.backend.study import Study
    from XBrainLab.llm.agent.controller import LLMController

    class _Retriever:
        def __init__(self) -> None:
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

    class _RagLifecycle:
        def __init__(self) -> None:
            self.close_calls = 0
            self.retriever = _Retriever()

        def close(self) -> bool:
            self.close_calls += 1
            return True

    rag_lifecycle = _RagLifecycle()
    controller = LLMController(Study(), rag_lifecycle=rag_lifecycle)  # type: ignore[arg-type]
    worker = controller.worker
    thread = controller.worker_thread
    terminals: list[tuple[bool, str]] = []
    controller.shutdown_finished.connect(
        lambda ok, message: terminals.append((ok, message))
    )

    started = monotonic()
    assert controller.close() is False
    assert monotonic() - started < 0.1

    qtbot.waitUntil(lambda: bool(terminals), timeout=2_000)
    qtbot.waitUntil(
        lambda: sip.isdeleted(thread) or not thread.isRunning(),
        timeout=2_000,
    )
    assert terminals == [(True, "")]
    assert controller.worker is None
    assert controller.close() is True
    assert rag_lifecycle.close_calls == 1
    assert rag_lifecycle.retriever.close_calls == 0
    if worker is not None:
        qtbot.waitUntil(lambda: sip.isdeleted(worker), timeout=2_000)


@pytest.mark.parametrize(
    "first_close_outcome",
    [False, RuntimeError("injected RAG close failure")],
    ids=["reports-pending", "contains-exception"],
)
def test_real_qt_close_retries_failed_rag_cleanup(
    qtbot,
    first_close_outcome: bool | BaseException,
) -> None:
    """RAG failure stays retryable while real QObject/QThread cleanup completes."""
    from XBrainLab.backend.study import Study
    from XBrainLab.llm.agent.controller import LLMController
    from XBrainLab.llm.agent.rag_process_lifecycle import ProcessRAGRetrieverLifecycle
    from XBrainLab.llm.agent.worker import AgentWorker

    rag_lifecycle = _DeferredRagLifecycle([first_close_outcome, True])
    controller = LLMController(
        Study(),
        rag_lifecycle=cast(ProcessRAGRetrieverLifecycle, rag_lifecycle),
    )
    worker = controller.worker
    thread = controller.worker_thread
    terminals: list[tuple[bool, str]] = []
    controller.shutdown_finished.connect(
        lambda ok, message: terminals.append((bool(ok), str(message or "")))
    )

    try:
        assert isinstance(worker, AgentWorker)
        assert worker.thread() is thread
        assert thread.isRunning()
        assert controller.close() is False
        qtbot.waitUntil(lambda: bool(terminals), timeout=2_000)

        assert terminals == [
            (
                False,
                "Assistant retrieval cleanup did not finish; cleanup is still pending.",
            )
        ]
        assert controller.worker is None
        assert controller.close() is True
        assert terminals[-1] == (True, "")
        assert rag_lifecycle.close_calls == 2
    finally:
        rag_lifecycle.permit_final_cleanup()
        if not controller.close():
            qtbot.waitUntil(lambda: controller.worker is None, timeout=2_000)
            assert controller.close() is True

    qtbot.waitUntil(
        lambda: sip.isdeleted(thread) or not thread.isRunning(),
        timeout=2_000,
    )


def test_real_qt_shutdown_fences_late_rag_stop_and_new_typed_turn(qtbot) -> None:
    """Shutdown cancels one deferred RAG turn before any later delivery can run."""
    from tests.qt_lifecycle import close_controller_and_wait
    from XBrainLab.backend.study import Study
    from XBrainLab.llm.agent.controller import LLMController
    from XBrainLab.llm.agent.rag_process_lifecycle import ProcessRAGRetrieverLifecycle
    from XBrainLab.llm.agent.turn import (
        AssistantToolInputReceipt,
        AssistantTurnCorrelation,
        AssistantTurnDeliveryPhase,
        AssistantTurnRequest,
        AssistantTurnTerminal,
    )
    from XBrainLab.llm.agent.worker import AgentWorker

    rag_lifecycle = _DeferredRagLifecycle([True])
    controller = LLMController(
        Study(),
        rag_lifecycle=cast(ProcessRAGRetrieverLifecycle, rag_lifecycle),
    )
    worker = controller.worker
    thread = controller.worker_thread
    shutdown_terminals: list[tuple[bool, str]] = []
    turn_terminals: list[AssistantTurnTerminal] = []
    generation_requests: list[object] = []
    controller.shutdown_finished.connect(
        lambda ok, message: shutdown_terminals.append((bool(ok), str(message or "")))
    )
    controller.turn_finished.connect(turn_terminals.append)
    controller.sig_generate.connect(generation_requests.append)

    try:
        assert isinstance(worker, AgentWorker)
        assert worker.thread() is thread
        accepted = controller.handle_user_turn(
            AssistantTurnRequest(
                correlation=AssistantTurnCorrelation(generation=1, turn_id=1),
                text="Explain alpha rhythms.",
            )
        )
        assert accepted.phase is AssistantTurnDeliveryPhase.ACCEPTED
        assert rag_lifecycle.pending_result_count == 1
        controller.pending_interactions.begin_tool_input(
            AssistantToolInputReceipt(
                command_name="apply_bandpass_filter",
                original_user_text="Apply a filter.",
                question="Which cutoff should I use?",
                publication_generation=0,
                missing_inputs=("low_cutoff",),
            )
        )

        assert controller.close() is False
        rejected = controller.handle_user_turn(
            AssistantTurnRequest(
                correlation=AssistantTurnCorrelation(generation=2, turn_id=2),
                text="This command must be rejected during cleanup.",
            )
        )
        assert rejected.phase is AssistantTurnDeliveryPhase.REJECTED
        assert rejected.message == "Assistant controller is closing."

        rag_lifecycle.deliver_latest_result()
        controller.stop_generation()
        qtbot.waitUntil(lambda: bool(shutdown_terminals), timeout=2_000)

        assert shutdown_terminals == [(True, "")]
        assert rag_lifecycle.cancelled_turn_ids == [1]
        assert generation_requests == []
        assert controller.pending_interactions.tool_input is None
        assert controller.pending_interactions.active_tool_input is None
        assert [terminal.outcome for terminal in turn_terminals] == [
            "shutdown_cancelled",
            "rejected_closing",
        ]
    finally:
        rag_lifecycle.permit_final_cleanup()
        close_controller_and_wait(controller, qtbot)

    assert worker is not None
    qtbot.waitUntil(lambda: sip.isdeleted(worker), timeout=2_000)
    qtbot.waitUntil(
        lambda: sip.isdeleted(thread) or not thread.isRunning(),
        timeout=2_000,
    )


def test_real_qt_shutdown_supersedes_a_pending_worker_stop_ack(qtbot) -> None:
    """A real worker's delayed cancellation acknowledgement cannot reopen shutdown."""
    from tests.qt_lifecycle import close_controller_and_wait
    from XBrainLab.backend.study import Study
    from XBrainLab.llm.agent.controller import LLMController
    from XBrainLab.llm.agent.rag_process_lifecycle import ProcessRAGRetrieverLifecycle
    from XBrainLab.llm.agent.turn import (
        AssistantGenerationStopAcknowledgement,
        AssistantTurnCorrelation,
        AssistantTurnDeliveryPhase,
        AssistantTurnRequest,
        AssistantTurnTerminal,
    )
    from XBrainLab.llm.agent.worker import AgentWorker

    rag_lifecycle = _DeferredRagLifecycle([True])
    controller = LLMController(
        Study(),
        rag_lifecycle=cast(ProcessRAGRetrieverLifecycle, rag_lifecycle),
    )
    worker = controller.worker
    thread = controller.worker_thread
    pending_stop_acks: list[AssistantGenerationStopAcknowledgement] = []
    terminals: list[AssistantTurnTerminal] = []
    ack_capture_connected = False
    controller_stop_slot_disconnected = False
    controller.turn_finished.connect(terminals.append)

    try:
        assert isinstance(worker, AgentWorker)
        assert worker.thread() is thread
        controller._sig_dispatch_generation.disconnect()
        accepted = controller.handle_user_turn(
            AssistantTurnRequest(
                correlation=AssistantTurnCorrelation(generation=1, turn_id=1),
                text="Explain alpha rhythms.",
            )
        )
        assert accepted.phase is AssistantTurnDeliveryPhase.ACCEPTED
        rag_lifecycle.deliver_latest_result()
        generation_id = controller._turn_orchestrator.active_generation_id
        assert generation_id is not None

        worker.generation_stop_finished.disconnect(
            controller._on_generation_stop_finished
        )
        controller_stop_slot_disconnected = True
        worker.generation_stop_finished.connect(pending_stop_acks.append)
        ack_capture_connected = True
        controller.stop_generation()
        qtbot.waitUntil(lambda: bool(pending_stop_acks), timeout=2_000)
        assert controller.is_processing is True
        assert pending_stop_acks == [
            AssistantGenerationStopAcknowledgement(
                generation_id=generation_id,
                stopped=True,
            )
        ]

        assert controller.close() is False
        controller._on_generation_stop_finished(pending_stop_acks[0])
        assert [terminal.outcome for terminal in terminals] == ["shutdown_cancelled"]
        assert controller.is_processing is False
    finally:
        if ack_capture_connected:
            worker.generation_stop_finished.disconnect(pending_stop_acks.append)
        if controller_stop_slot_disconnected:
            worker.generation_stop_finished.connect(
                controller._on_generation_stop_finished
            )
        rag_lifecycle.permit_final_cleanup()
        close_controller_and_wait(controller, qtbot)

    qtbot.waitUntil(lambda: sip.isdeleted(worker), timeout=2_000)
    qtbot.waitUntil(
        lambda: sip.isdeleted(thread) or not thread.isRunning(),
        timeout=2_000,
    )


def test_controller_terminal_waits_for_native_cleanup_after_finished(qtbot) -> None:
    """A finished signal must not release ownership before deferred deletion."""
    from XBrainLab.backend.study import Study
    from XBrainLab.llm.agent.controller import LLMController

    controller = LLMController(Study())
    worker = controller.worker
    thread = controller.worker_thread
    entered = Event()
    release = Event()
    blocker = _WorkerThreadBlocker(entered, release)
    thread.finished.connect(blocker._block, Qt.ConnectionType.DirectConnection)
    terminals: list[tuple[bool, str]] = []
    controller.shutdown_finished.connect(
        lambda ok, message: terminals.append((ok, message))
    )

    try:
        assert controller.close() is False
        qtbot.waitUntil(entered.is_set, timeout=1_000)
        qtbot.wait(25)
        assert not release.is_set()
        assert terminals == []
        assert controller.shutdown_in_progress
        assert controller.worker is worker
        assert controller.close() is False
    finally:
        release.set()
        assert thread.wait(2_000)
        qtbot.waitUntil(lambda: terminals == [(True, "")], timeout=2_000)

    assert controller.worker is None
    assert worker is not None and sip.isdeleted(worker)
    assert controller.close() is True


def test_shutdown_timeout_stays_pending_until_the_native_thread_exits(
    qtbot,
    monkeypatch,
) -> None:
    """Timeout reports pending cleanup and only succeeds after native exit."""
    from XBrainLab.backend.study import Study
    from XBrainLab.llm.agent import controller as controller_module

    monkeypatch.setattr(controller_module, "WORKER_SHUTDOWN_TIMEOUT_MS", 25)
    controller = controller_module.LLMController(Study())
    worker = controller.worker
    assert worker is not None
    thread = controller.worker_thread
    entered = Event()
    release = Event()
    blocker = _WorkerThreadBlocker(entered, release)
    blocker.moveToThread(thread)
    thread.finished.connect(blocker.deleteLater)
    blocker.block_requested.emit()
    assert entered.wait(timeout=1)

    terminals: list[tuple[bool, str]] = []
    late_statuses: list[str] = []
    late_runtime_snapshots: list[Any] = []
    controller.shutdown_finished.connect(
        lambda ok, message: terminals.append((ok, message))
    )
    controller.status_update.connect(late_statuses.append)
    controller.runtime_state_changed.connect(late_runtime_snapshots.append)

    try:
        assert controller.close() is False
        qtbot.waitUntil(lambda: bool(terminals), timeout=2_000)

        assert terminals[0][0] is False
        assert "still pending" in terminals[0][1]
        assert controller.worker is worker
        assert controller.close() is False
        assert thread.isRunning() is True

        worker.log.emit("late worker status")
        worker.runtime_snapshot_changed.emit(controller.runtime_snapshot())
        qtbot.wait(25)

        assert late_statuses == []
        assert late_runtime_snapshots == []
        assert terminals == [terminals[0]]
    finally:
        release.set()
        qtbot.waitUntil(
            lambda: sip.isdeleted(thread) or not thread.isRunning(),
            timeout=2_000,
        )

    qtbot.waitUntil(lambda: len(terminals) == 2, timeout=2_000)
    assert terminals[1] == (True, "")
    assert controller.worker is None
    assert controller.close() is True


def test_real_qobject_worker_shutdown_waits_only_for_finished_signal(
    qtbot,
    monkeypatch,
) -> None:
    """A live native generation makes shutdown pending without blocking its owner."""
    from XBrainLab.llm.agent.turn import (
        AssistantGenerationRequest,
        AssistantResponseContract,
    )
    from XBrainLab.llm.agent.worker import AgentWorker
    from XBrainLab.llm.core.config import LLMConfig

    started = Event()
    release = Event()

    class _BlockingEngine:
        def __init__(self) -> None:
            self.config = LLMConfig()
            self.config.timeout = 60
            self.close_calls = 0

        def generate_stream(self, _messages, *, profile):
            del profile
            started.set()
            release.wait(timeout=2)
            yield "done"

        def cancel_generation(self, *, wait_timeout: float) -> bool:
            del wait_timeout
            return False

        def close(self) -> None:
            self.close_calls += 1

    engine = _BlockingEngine()
    worker = AgentWorker()
    worker.engine = engine  # type: ignore[assignment]
    terminals: list[bool] = []
    worker.shutdown_finished.connect(terminals.append)
    request = AssistantGenerationRequest.from_messages(
        [{"role": "user", "content": "run"}],
        response_contract=AssistantResponseContract.STRUCTURED_ACTION,
    ).correlated(1)
    monkeypatch.setattr(LLMConfig, "load_from_file", lambda: None)

    try:
        worker.generate_from_messages(request)
        qtbot.waitUntil(started.is_set, timeout=1_000)
        generation_thread = worker.generation_thread
        assert generation_thread is not None

        before = monotonic()
        assert worker.shutdown(wait_ms=1_500) is False
        elapsed = monotonic() - before

        assert elapsed < 0.1
        assert terminals == [False]
        assert generation_thread.isRunning() is True
        assert engine.close_calls == 0

        release.set()
        qtbot.waitUntil(lambda: worker.generation_thread is None, timeout=2_000)
        assert worker.shutdown() is True
        assert terminals == [False, True]
        assert engine.close_calls == 1
    finally:
        release.set()
        generation_thread = worker.generation_thread
        if generation_thread is not None:
            qtbot.waitUntil(
                lambda: sip.isdeleted(generation_thread)
                or not generation_thread.isRunning(),
                timeout=2_000,
            )
        if worker.timeout_timer is not None:
            worker.timeout_timer.stop()


def test_controller_timeout_does_not_finalize_with_live_generation(
    qtbot,
    monkeypatch,
) -> None:
    """A timeout stays pending until the worker's generation thread is terminal."""
    from XBrainLab.backend.study import Study
    from XBrainLab.llm.agent import controller as controller_module
    from XBrainLab.llm.agent.turn import (
        AssistantGenerationRequest,
        AssistantResponseContract,
    )
    from XBrainLab.llm.core.config import LLMConfig

    started = Event()
    release = Event()

    class _BlockingEngine:
        def __init__(self) -> None:
            self.config = LLMConfig()
            self.config.timeout = 60
            self.close_calls = 0

        def generate_stream(self, _messages, *, profile):
            del profile
            started.set()
            release.wait(timeout=3)
            yield "done"

        def cancel_generation(self, *, wait_timeout: float) -> bool:
            del wait_timeout
            return False

        def close(self) -> None:
            self.close_calls += 1

    monkeypatch.setattr(controller_module, "WORKER_SHUTDOWN_TIMEOUT_MS", 25)
    monkeypatch.setattr(
        controller_module,
        "WORKER_SHUTDOWN_RETRY_INTERVAL_MS",
        10,
    )
    monkeypatch.setattr(LLMConfig, "load_from_file", lambda: None)
    controller = controller_module.LLMController(Study())
    worker = controller.worker
    assert worker is not None
    worker_thread = controller.worker_thread
    engine = _BlockingEngine()
    worker.engine = engine  # type: ignore[assignment]
    terminals: list[tuple[bool, str]] = []
    controller.shutdown_finished.connect(
        lambda ok, message: terminals.append((ok, message))
    )
    request = AssistantGenerationRequest.from_messages(
        [{"role": "user", "content": "run"}],
        response_contract=AssistantResponseContract.STRUCTURED_ACTION,
    ).correlated(1)

    try:
        controller._sig_dispatch_generation.emit(request)
        qtbot.waitUntil(started.is_set, timeout=1_000)
        generation_thread = worker.generation_thread
        assert generation_thread is not None

        assert controller.close() is False
        qtbot.waitUntil(lambda: any(not ok for ok, _ in terminals), timeout=2_000)
        qtbot.wait(100)

        assert not any(ok for ok, _ in terminals)
        assert controller.worker is worker
        assert worker_thread.isRunning() is True
        assert generation_thread.isRunning() is True
        assert engine.close_calls == 0
    finally:
        release.set()

    qtbot.waitUntil(lambda: any(ok for ok, _ in terminals), timeout=2_000)
    qtbot.waitUntil(
        lambda: sip.isdeleted(worker_thread) or not worker_thread.isRunning(),
        timeout=2_000,
    )
    assert terminals[-1] == (True, "")
    assert controller.worker is None
    assert engine.close_calls == 1
