"""Source and native lifecycle guards for the controller integration suite."""

from __future__ import annotations

import ast
from pathlib import Path
from threading import Event
from time import monotonic
from typing import Any

from PyQt6 import sip
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

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


def test_assistant_shutdown_source_forbids_nested_loops_and_thread_waits() -> None:
    """Controller and worker teardown must advance from Qt terminal signals."""
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
            ):
                forbidden.append((f"{source.name}:wait", node.lineno))

    assert forbidden == []


def test_real_controller_close_completes_from_worker_and_thread_signals(qtbot) -> None:
    """The first close returns immediately; Qt terminals complete ownership."""
    from XBrainLab.backend.study import Study
    from XBrainLab.llm.agent.controller import LLMController

    class _RagLifecycle:
        retriever = object()

        def __init__(self) -> None:
            self.close_calls = 0

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
    if worker is not None:
        qtbot.waitUntil(lambda: sip.isdeleted(worker), timeout=2_000)


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
