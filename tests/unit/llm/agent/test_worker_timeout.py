"""Tests for AgentWorker timeout mechanism."""

from threading import Event, Lock
from typing import Any, cast
from unittest.mock import MagicMock, patch

from PyQt6.QtCore import QObject, pyqtSignal

from XBrainLab.llm.agent.controller import LLMController
from XBrainLab.llm.agent.response_presentation import AssistantResponsePresentation
from XBrainLab.llm.agent.turn import (
    AssistantGenerationEvent,
    AssistantGenerationEventPhase,
    AssistantGenerationRequest,
    AssistantGenerationStopRequest,
    AssistantResponseContract,
)
from XBrainLab.llm.agent.worker import ACTIVE_GENERATION_THREADS, AgentWorker
from XBrainLab.llm.core.config import LLMConfig


def _request(
    text: str = "hi",
    *,
    generation_id: int = 1,
) -> AssistantGenerationRequest:
    request = AssistantGenerationRequest.from_messages(
        [{"role": "user", "content": text}],
        response_contract=AssistantResponseContract.STRUCTURED_ACTION,
    )
    return request.correlated(generation_id)


class TestAgentWorkerTimeout:
    """Test suite for Agent timeout protection."""

    def test_timeout_timer_created_on_generation(self):
        """Verify timeout timer is created during generation."""
        worker = AgentWorker()
        config = LLMConfig()
        config.timeout = 30
        worker.engine = MagicMock()
        worker.engine.config = config

        # Mock GenerationThread to prevent actual execution
        # Keep config reload on the same explicit runtime contract.
        with (
            patch("XBrainLab.llm.agent.worker.GenerationThread") as MockThread,
            patch(
                "XBrainLab.llm.agent.worker.LLMConfig.load_from_file", return_value=None
            ),
        ):
            mock_thread = MockThread.return_value
            mock_thread.start = MagicMock()

            worker.generate_from_messages(_request())

            # Verify timer was created and configured
            assert worker.timeout_timer is not None, "Timeout timer should be created"
            # Note: isActive() returns False in test env without QEventLoop
            # We verify configuration instead
            assert worker.timeout_timer.interval() == 30000, (
                f"Expected 30s, got {worker.timeout_timer.interval()}ms"
            )
            generation_thread = worker.generation_thread
            assert generation_thread is not None
            worker._release_generation_thread(generation_thread)
            assert generation_thread not in ACTIVE_GENERATION_THREADS

    def test_timeout_response_waits_for_generation_thread_exit(self):
        """Keep timeout completion pending until native generation exits."""
        worker = AgentWorker()
        worker.engine = MagicMock()

        # Setup mock signals
        worker.error = MagicMock()
        worker.generation_finished = MagicMock()
        worker.generation_error = MagicMock()

        # Setup mock thread
        mock_thread = MagicMock()
        mock_thread.isRunning.return_value = True
        worker.generation_thread = mock_thread
        worker._active_generation_id = 101
        worker._is_timed_out = False

        # Trigger timeout
        worker._on_timeout()

        # Verify flag set
        assert worker._is_timed_out, "Timeout flag should be set"

        worker.error.emit.assert_not_called()
        worker.generation_error.emit.assert_not_called()
        worker.generation_finished.emit.assert_not_called()
        assert worker.generation_thread is mock_thread

        worker._release_generation_thread(mock_thread)

        worker.error.emit.assert_not_called()
        worker.generation_error.emit.assert_called_once_with(
            101,
            "Error: Generation timed out (Local LLM is too slow).",
        )
        worker.generation_finished.emit.assert_not_called()

        worker._release_generation_thread(mock_thread)
        worker.generation_error.emit.assert_called_once()

    def test_normal_completion_stops_timer(self):
        """Verify normal completion stops the timeout timer."""
        worker = AgentWorker()
        worker.engine = MagicMock()

        # Setup mocks
        worker.generation_finished = MagicMock()
        worker.generation_error = MagicMock()
        worker.timeout_timer = MagicMock()
        worker._is_timed_out = False
        worker._active_generation_id = 102

        worker._on_generation_finished(102)

        # Verify timer stopped
        worker.timeout_timer.stop.assert_called_once()
        worker.generation_finished.emit.assert_called_once_with(102, [])
        worker.generation_error.emit.assert_not_called()

    def test_timeout_retry_never_overlaps_live_generation(self, qtbot):
        started = Event()
        release = Event()

        class BlockingEngine:
            def __init__(self) -> None:
                self.config = LLMConfig()
                self.config.timeout = 60
                self.calls = 0
                self.active = 0
                self.max_active = 0
                self.lock = Lock()

            def generate_stream(self, _messages, *, profile):
                del profile
                with self.lock:
                    self.calls += 1
                    self.active += 1
                    self.max_active = max(self.max_active, self.active)
                started.set()
                release.wait(timeout=2)
                try:
                    yield "done"
                finally:
                    with self.lock:
                        self.active -= 1

            def cancel_generation(self, *, wait_timeout: float) -> bool:
                del wait_timeout
                return release.is_set()

        worker = AgentWorker()
        engine = BlockingEngine()
        worker.engine = cast(Any, engine)
        lifecycle_errors: list[str] = []
        generation_errors: list[tuple[int, str]] = []
        worker.error.connect(lifecycle_errors.append)
        worker.generation_error.connect(
            lambda generation_id, message: generation_errors.append(
                (generation_id, message)
            )
        )
        with patch(
            "XBrainLab.llm.agent.worker.LLMConfig.load_from_file",
            return_value=engine.config,
        ):
            worker.generate_from_messages(_request("run", generation_id=201))
            qtbot.waitUntil(started.is_set, timeout=1000)
            active_thread = worker.generation_thread

            worker._on_timeout()
            worker.generate_from_messages(_request("run", generation_id=202))

            assert worker.generation_thread is active_thread
            assert engine.calls == 1
            assert engine.max_active == 1
            assert lifecycle_errors == []
            assert any(
                generation_id == 202 and "still stopping" in message.lower()
                for generation_id, message in generation_errors
            )
            release.set()
            qtbot.waitUntil(lambda: worker.generation_thread is None, timeout=2000)
            assert any(
                generation_id == 201 and "timed out" in message.lower()
                for generation_id, message in generation_errors
            )

            worker.generate_from_messages(_request("run", generation_id=203))
            qtbot.waitUntil(lambda: engine.calls == 2, timeout=1000)
            qtbot.waitUntil(lambda: worker.generation_thread is None, timeout=2000)
            assert engine.max_active == 1

        if worker.timeout_timer is not None:
            worker.timeout_timer.stop()

    def test_cancel_ack_reaches_controller_only_after_thread_exit(self, qtbot):
        started = Event()
        release = Event()

        class BlockingEngine:
            def __init__(self) -> None:
                self.config = LLMConfig()
                self.config.timeout = 60

            def generate_stream(self, _messages, *, profile):
                del profile
                started.set()
                release.wait(timeout=2)
                yield "done"

            def cancel_generation(self, *, wait_timeout: float) -> bool:
                del wait_timeout
                return release.is_set()

        class CancellationController(QObject):
            status_update = pyqtSignal(str)
            processing_finished = pyqtSignal()
            turn_finished = pyqtSignal(object)
            response_presentation_ready = pyqtSignal(object)
            activity_changed = pyqtSignal(object)
            generation_event = pyqtSignal(object)
            _on_generation_stop_finished = LLMController._on_generation_stop_finished
            _complete_cancelled_turn = LLMController._complete_cancelled_turn
            _publish_response = LLMController._publish_response
            _publish_activity = LLMController._publish_activity
            _emit_processing_finished = LLMController._emit_processing_finished
            _active_turn_correlation = LLMController._active_turn_correlation
            _require_active_turn_correlation = (
                LLMController._require_active_turn_correlation
            )

            def __init__(self) -> None:
                super().__init__()
                self._turn_cancelled = True
                self.is_processing = True
                self._active_host_turn_id = 77
                self._active_host_turn_generation = 3
                self._active_generation_id = 1
                self._stopping_generation_id = 1
                self._cancellation_response_sent = False
                self._visible_response_sent = False
                self.history: list[dict[str, str]] = []

            def _append_history(self, role: str, content: str) -> None:
                self.history.append({"role": role, "content": content})

        worker = AgentWorker()
        engine = BlockingEngine()
        worker.engine = cast(Any, engine)
        controller = CancellationController()
        statuses: list[str] = []
        completions: list[bool] = []
        presentations: list[AssistantResponsePresentation] = []
        generation_events: list[AssistantGenerationEvent] = []
        controller.status_update.connect(statuses.append)
        controller.processing_finished.connect(lambda: completions.append(True))
        controller.response_presentation_ready.connect(presentations.append)
        controller.generation_event.connect(generation_events.append)
        worker.generation_stop_finished.connect(
            controller._on_generation_stop_finished,
        )
        with (
            patch(
                "XBrainLab.llm.agent.worker.LLMConfig.load_from_file",
                return_value=engine.config,
            ),
            patch(
                "XBrainLab.llm.agent.worker.GENERATION_THREAD_SHUTDOWN_WAIT_MS",
                20,
            ),
        ):
            worker.generate_from_messages(_request("run"))
            qtbot.waitUntil(started.is_set, timeout=1000)

            worker.cancel_generation(AssistantGenerationStopRequest(generation_id=1))

            assert controller.is_processing is True
            assert statuses[-1] == "Stopping..."
            assert completions == []
            release.set()
            qtbot.waitUntil(lambda: not controller.is_processing, timeout=2000)

        assert statuses[-1] == "Stopped"
        assert completions == [True]
        assert len(presentations) == 1
        assert presentations[0].text == (
            "Request cancelled. You can revise it or ask something else."
        )
        assert generation_events == [
            AssistantGenerationEvent(
                generation_id=1,
                phase=AssistantGenerationEventPhase.CANCELLED,
            )
        ]

    def test_stop_ack_reports_backend_generation_still_running(self):
        worker = AgentWorker()
        worker.engine = MagicMock()
        worker.engine.cancel_generation.return_value = False
        generation_thread = MagicMock()
        generation_thread.isRunning.return_value = True
        generation_thread.wait.return_value = True
        worker.generation_thread = generation_thread
        worker._active_generation_id = 301
        worker._generation_thread_id = 301
        acknowledgements: list[Any] = []
        worker.generation_stop_finished.connect(acknowledgements.append)

        worker.cancel_generation(
            AssistantGenerationStopRequest(generation_id=301),
        )

        assert len(acknowledgements) == 1
        acknowledgement = acknowledgements[0]
        assert acknowledgement.generation_id == 301
        assert acknowledgement.stopped is False
