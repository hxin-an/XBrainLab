"""Coverage tests for AgentWorker & GenerationThread."""

from __future__ import annotations

from dataclasses import dataclass, replace
from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.llm.agent.runtime_state import (
    AssistantRuntimePhase,
)
from XBrainLab.llm.agent.turn import (
    AssistantGenerationDispatchAcknowledgement,
    AssistantGenerationDispatchPhase,
    AssistantGenerationRequest,
    AssistantGenerationStopAcknowledgement,
    AssistantGenerationStopRequest,
    AssistantResponseContract,
)
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.runtime_selection import (
    AssistantRuntimeLaunchResolver,
    AssistantRuntimeLaunchSpec,
)
from XBrainLab.llm.tools.result_contract import SAFE_UNEXPECTED_FAILURE_MESSAGE


@dataclass(frozen=True)
class _ActivationRequest(AssistantRuntimeLaunchSpec):
    activation_id: int = 0


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


def _launch_spec(
    model_id: str | None = None,
    *,
    ready_model_id: str | None = None,
    ready_message: str = "Local runtime ready.",
) -> AssistantRuntimeLaunchSpec:
    requested_model = model_id or LLMConfig.default_local_model_id()
    ready_model = ready_model_id or requested_model
    config = LLMConfig(model_name=requested_model)
    config.local_backend_ready = lambda candidate=None: (  # type: ignore[method-assign]
        candidate == ready_model
    )
    config.local_backend_status_message = (  # type: ignore[method-assign]
        lambda candidate=None: (
            ready_message
            if candidate == ready_model
            else f"Model cache not found for {candidate}."
        )
    )
    resolution = AssistantRuntimeLaunchResolver().resolve(config)
    assert resolution.launch_spec is not None
    return resolution.launch_spec


def _activation_request(
    model_id: str | None = None,
    *,
    activation_id: int,
) -> _ActivationRequest:
    spec = _launch_spec(model_id)
    return _ActivationRequest(
        backend=spec.backend,
        requested_backend_id=spec.requested_backend_id,
        requested_model_id=spec.requested_model_id,
        model_id=spec.model_id,
        outcome=spec.outcome,
        selection_detail=spec.selection_detail,
        settings=spec.settings,
        activation_id=activation_id,
    )


@pytest.fixture
def worker():
    """Return an AgentWorker with mocked Qt signals.

    Patches ``QObject.__init__`` so the real ``AgentWorker.__init__``
    executes (setting ``engine`` and ``generation_thread``) without
    requiring a running ``QApplication``.
    """
    from PyQt6.QtCore import QObject

    from XBrainLab.llm.agent.worker import AgentWorker

    with patch.object(QObject, "__init__", lambda self: None):
        w = AgentWorker()
    # Signals need explicit mocking because QObject was not fully initialised
    w.error = MagicMock()
    w.generation_finished = MagicMock()
    w.generation_chunk_received = MagicMock()
    w.generation_error = MagicMock()
    w.generation_dispatch_acknowledged = MagicMock()
    w.generation_stop_finished = MagicMock()
    w.log = MagicMock()
    w.runtime_snapshot_changed = MagicMock()
    yield w

    generation_thread = w.generation_thread
    if generation_thread is not None:
        w._release_generation_thread(generation_thread)


class TestAgentWorkerSignalContract:
    def test_exposes_only_correlated_generation_signals(self, worker):
        worker_type = type(worker)

        assert not hasattr(worker_type, "finished")
        assert not hasattr(worker_type, "chunk_received")
        assert hasattr(worker_type, "generation_finished")
        assert hasattr(worker_type, "generation_chunk_received")
        assert hasattr(worker_type, "generation_error")
        assert hasattr(worker_type, "generation_dispatch_acknowledged")


class TestInitializeAgent:
    def test_noop_if_already_initialized(self, worker):
        worker.engine = MagicMock()
        worker.initialize_agent(_launch_spec())
        worker.log.emit.assert_not_called()

    def test_loads_model(self, worker):
        spec = _launch_spec()
        with patch("XBrainLab.llm.agent.worker.LLMEngine") as MockEng:
            engine = MockEng.return_value
            worker.initialize_agent(spec)
            engine.load_model.assert_called_once()
            assert worker.engine is engine
            snapshots = [
                call.args[0]
                for call in worker.runtime_snapshot_changed.emit.call_args_list
            ]
            assert snapshots[0].phase is AssistantRuntimePhase.LOADING
            assert snapshots[-1].phase is AssistantRuntimePhase.READY
            assert snapshots[-1].initialized is True
            assert snapshots[-1].model_id == spec.model_id

    def test_runtime_snapshot_redacts_model_selection_details(self, worker):
        private_path = "/home/alice/private/models/local"
        private_token = "Authorization: Bearer hf_super_secret"  # noqa: S105
        spec = replace(
            _launch_spec(),
            model_id=private_path,
            requested_model_id=private_path,
            selection_detail=f"Using {private_path}; {private_token}",
        )

        worker._emit_runtime_snapshot(launch_spec=spec)

        snapshot = worker.runtime_snapshot_changed.emit.call_args.args[0]
        public_output = repr(snapshot)
        assert private_path not in public_output
        assert private_token not in public_output
        assert "hf_super_secret" not in public_output
        assert "[REDACTED_PATH]" in public_output
        assert "[REDACTED_SECRET]" in public_output

    def test_initialize_agent_uses_frozen_spec_settings(self, worker):
        spec = _launch_spec()
        with patch("XBrainLab.llm.agent.worker.LLMEngine") as MockEng:
            worker.initialize_agent(spec)

        launch_config = MockEng.call_args.args[0]
        assert launch_config is not spec.settings
        assert launch_config.model_name == spec.model_id
        assert launch_config.temperature == spec.settings.temperature

    def test_untyped_runtime_selection_fails_closed(self, worker):
        with patch("XBrainLab.llm.agent.worker.LLMEngine") as engine:
            worker.initialize_agent("invalid")

        engine.assert_not_called()
        snapshot = worker.runtime_snapshot_changed.emit.call_args.args[0]
        assert snapshot.phase is AssistantRuntimePhase.FAILED
        assert "launch spec" in snapshot.error
        worker.error.emit.assert_called_once()

    def test_initialize_agent_logs_cpu_fallback_note(self, worker):
        spec = _launch_spec(
            ready_message=(
                "Local runtime ready. GPU execution is unavailable in this "
                "environment, so startup will fall back to CPU and disable "
                "4-bit loading."
            )
        )
        with patch("XBrainLab.llm.agent.worker.LLMEngine") as MockEng:
            engine = MockEng.return_value

            worker.initialize_agent(spec)

            assert (
                worker.log.emit.call_args_list[0]
                .args[0]
                .startswith("Local runtime ready. GPU execution is unavailable")
            )
            engine.load_model.assert_called_once()

    def test_initialize_agent_supports_an_explicit_legacy_model(self, worker):
        legacy_model = LLMConfig.fallback_local_model_id()
        spec = _launch_spec(legacy_model)
        with patch("XBrainLab.llm.agent.worker.LLMEngine") as MockEng:
            engine = MockEng.return_value

            worker.initialize_agent(spec)

            assert MockEng.call_args.args[0].model_name == legacy_model
            assert spec.requested_model_id == legacy_model
            assert spec.fallback_used is False
            engine.load_model.assert_called_once()

    def test_error_on_failure(self, worker):
        with patch(
            "XBrainLab.llm.agent.worker.LLMEngine",
            side_effect=RuntimeError("boom"),
        ):
            worker.initialize_agent(_launch_spec())
            worker.error.emit.assert_called_once()

    def test_load_failure_releases_engine_and_retry_can_succeed(self, worker):
        spec = _launch_spec()
        failed_engine = MagicMock()
        failed_engine.load_model.side_effect = RuntimeError("load failed")
        working_engine = MagicMock()
        with (
            patch(
                "XBrainLab.llm.agent.worker.LLMEngine",
                side_effect=[failed_engine, working_engine],
            ),
        ):
            worker.initialize_agent(spec)
            assert worker.engine is None
            failed_engine.close.assert_called_once()

            worker.initialize_agent(spec)

        assert worker.engine is working_engine
        working_engine.load_model.assert_called_once()


class TestGenerateFromMessages:
    def test_initializes_if_needed(self, worker):
        spec = _launch_spec()
        worker._runtime_launch_spec = spec
        worker.initialize_agent = MagicMock()
        worker.generate_from_messages(_request())
        worker.initialize_agent.assert_called_once_with(spec)

    def test_starts_thread(self, worker):
        engine = MagicMock()
        engine.config = MagicMock()
        engine.config.timeout = 30
        engine.config.inference_mode = "local"
        worker.engine = engine
        fresh = LLMConfig()
        fresh.timeout = 30
        fresh.local_backend_ready = MagicMock(return_value=True)

        with (
            patch("XBrainLab.llm.agent.worker.GenerationThread") as MockGT,
            patch("XBrainLab.llm.agent.worker.QTimer") as MockTimer,
            patch(
                "XBrainLab.llm.agent.worker.LLMConfig.load_from_file",
                return_value=fresh,
            ),
        ):
            gt = MockGT.return_value
            timer = MockTimer.return_value
            request = _request("test")
            worker.generate_from_messages(request)
            gt.start.assert_called_once()
            MockGT.assert_called_once_with(engine, request)
            timer.start.assert_called_once_with(30000)
            assert [
                call.args[0]
                for call in worker.generation_dispatch_acknowledged.emit.call_args_list
            ] == [
                AssistantGenerationDispatchAcknowledgement(
                    generation_id=request.generation_id,
                    phase=AssistantGenerationDispatchPhase.ACCEPTED,
                ),
                AssistantGenerationDispatchAcknowledgement(
                    generation_id=request.generation_id,
                    phase=AssistantGenerationDispatchPhase.STARTED,
                ),
            ]

    def test_request_normalization_failure_is_correlated_and_releases_ids(
        self,
        worker,
    ):
        engine = MagicMock()
        engine.config = MagicMock(timeout=30, inference_mode="local")
        worker.engine = engine
        request = _request("normalization fault", generation_id=24)

        with patch.object(
            AssistantGenerationRequest,
            "to_model_messages",
            side_effect=RuntimeError("fault injection: normalization failed"),
        ):
            worker.generate_from_messages(request)

        worker.generation_dispatch_acknowledged.emit.assert_called_once_with(
            AssistantGenerationDispatchAcknowledgement(
                generation_id=24,
                phase=AssistantGenerationDispatchPhase.ACCEPTED,
            )
        )
        worker.generation_error.emit.assert_called_once()
        generation_id, message = worker.generation_error.emit.call_args.args
        assert generation_id == 24
        assert message == SAFE_UNEXPECTED_FAILURE_MESSAGE
        assert "normalization failed" not in message
        assert worker._active_generation_id is None
        assert worker._generation_thread_id is None
        assert worker.generation_thread is None

    def test_thread_construction_failure_is_correlated_and_releases_ids(
        self,
        worker,
    ):
        engine = MagicMock()
        engine.config = MagicMock(timeout=30, inference_mode="local")
        worker.engine = engine
        request = _request("setup fault", generation_id=25)

        with (
            patch(
                "XBrainLab.llm.agent.worker.GenerationThread",
                side_effect=RuntimeError("fault injection: thread setup failed"),
            ),
            patch(
                "XBrainLab.llm.agent.worker.LLMConfig.load_from_file",
                return_value=None,
            ),
        ):
            worker.generate_from_messages(request)

        worker.generation_dispatch_acknowledged.emit.assert_called_once_with(
            AssistantGenerationDispatchAcknowledgement(
                generation_id=25,
                phase=AssistantGenerationDispatchPhase.ACCEPTED,
            )
        )
        worker.generation_error.emit.assert_called_once()
        generation_id, message = worker.generation_error.emit.call_args.args
        assert generation_id == 25
        assert message == SAFE_UNEXPECTED_FAILURE_MESSAGE
        assert "thread setup failed" not in message
        assert worker._active_generation_id is None
        assert worker._generation_thread_id is None
        assert worker.generation_thread is None

    def test_thread_start_failure_is_correlated_and_releases_ids(
        self,
        worker,
    ):
        engine = MagicMock()
        engine.config = MagicMock(timeout=30, inference_mode="local")
        worker.engine = engine
        request = _request("start fault", generation_id=26)

        with (
            patch("XBrainLab.llm.agent.worker.GenerationThread") as thread_class,
            patch("XBrainLab.llm.agent.worker.QTimer"),
            patch(
                "XBrainLab.llm.agent.worker.LLMConfig.load_from_file",
                return_value=None,
            ),
        ):
            thread_class.return_value.start.side_effect = RuntimeError(
                "fault injection: thread start failed"
            )
            worker.generate_from_messages(request)

        worker.generation_dispatch_acknowledged.emit.assert_called_once_with(
            AssistantGenerationDispatchAcknowledgement(
                generation_id=26,
                phase=AssistantGenerationDispatchPhase.ACCEPTED,
            )
        )
        worker.generation_error.emit.assert_called_once()
        generation_id, message = worker.generation_error.emit.call_args.args
        assert generation_id == 26
        assert message == SAFE_UNEXPECTED_FAILURE_MESSAGE
        assert "thread start failed" not in message
        assert worker._active_generation_id is None
        assert worker._generation_thread_id is None
        assert worker.generation_thread is None

    def test_correlated_request_id_is_forwarded_by_worker_signals(self, worker):
        engine = MagicMock()
        engine.config = MagicMock(timeout=30, inference_mode="local")
        worker.engine = engine
        fresh = LLMConfig()
        fresh.timeout = 30
        fresh.local_backend_ready = MagicMock(return_value=True)
        request = _request("correlated", generation_id=23)

        with (
            patch("XBrainLab.llm.agent.worker.GenerationThread") as thread_class,
            patch("XBrainLab.llm.agent.worker.QTimer"),
            patch(
                "XBrainLab.llm.agent.worker.LLMConfig.load_from_file",
                return_value=fresh,
            ),
        ):
            generation_thread = thread_class.return_value
            worker.generate_from_messages(request)
            chunk_callback = generation_thread.chunk_received.connect.call_args.args[0]
            finished_callback = (
                generation_thread.finished_generation.connect.call_args.args[0]
            )

            chunk_callback("result")
            finished_callback()

        worker.generation_chunk_received.emit.assert_called_once_with(23, "result")
        worker.generation_finished.emit.assert_called_once_with(23, [])

    def test_rejects_untyped_generation_payload(self, worker):
        worker.engine = MagicMock()

        worker.generate_from_messages([{"role": "user", "content": "test"}])

        worker.error.emit.assert_called_once_with(
            "Assistant generation requires a typed request."
        )
        worker.generation_finished.emit.assert_not_called()
        worker.generation_chunk_received.emit.assert_not_called()
        worker.generation_error.emit.assert_not_called()

    def test_rejects_request_without_positive_correlation_id(self, worker):
        worker.engine = MagicMock()
        request = AssistantGenerationRequest.from_messages(
            [{"role": "user", "content": "test"}],
            response_contract=AssistantResponseContract.STRUCTURED_ACTION,
        )

        worker.generate_from_messages(request)

        worker.error.emit.assert_called_once_with(
            "Assistant generation requires a positive correlation ID."
        )
        worker.generation_finished.emit.assert_not_called()
        worker.generation_chunk_received.emit.assert_not_called()
        worker.generation_error.emit.assert_not_called()

    def test_does_not_overlap_generation_that_is_still_stopping(self, worker):
        cfg = LLMConfig()
        cfg.inference_mode = "local"
        cfg.active_mode = "local"
        cfg.model_name = LLMConfig.default_local_model_id()
        cfg.timeout = 30
        engine = MagicMock()
        engine.config = cfg
        worker.engine = engine
        running_thread = MagicMock()
        running_thread.isRunning.return_value = True
        worker.generation_thread = running_thread

        with (
            patch("XBrainLab.llm.agent.worker.GenerationThread") as thread_class,
            patch(
                "XBrainLab.llm.agent.worker.LLMConfig.load_from_file",
                return_value=cfg,
            ) as load_config,
        ):
            worker.generate_from_messages(_request("retry", generation_id=29))

        thread_class.assert_not_called()
        load_config.assert_not_called()
        engine.switch_backend.assert_not_called()
        assert worker.generation_thread is running_thread
        worker.error.emit.assert_not_called()
        worker.generation_error.emit.assert_called_once()
        generation_id, message = worker.generation_error.emit.call_args.args
        assert generation_id == 29
        assert "still stopping" in message.lower()
        worker.generation_finished.emit.assert_not_called()

    def test_syncs_generation_settings_without_runtime_switch(self, worker):
        active_model = "microsoft/Phi-4-mini-instruct"
        engine = MagicMock()
        engine.config = MagicMock()
        engine.config.inference_mode = "local"
        engine.config.active_mode = "local"
        engine.config.model_name = active_model
        engine.config.timeout = 60
        worker.engine = engine

        fresh = LLMConfig()
        fresh.inference_mode = "gemini"
        fresh.active_mode = "gemini"
        fresh.model_name = LLMConfig.fallback_local_model_id()
        fresh.temperature = 1.25

        with (
            patch("XBrainLab.llm.agent.worker.GenerationThread"),
            patch("XBrainLab.llm.agent.worker.QTimer"),
            patch(
                "XBrainLab.llm.agent.worker.LLMConfig.load_from_file",
                return_value=fresh,
            ),
        ):
            worker.generate_from_messages(_request("test"))
            engine.switch_backend.assert_not_called()
            assert engine.config.model_name == active_model
            assert engine.config.inference_mode == "local"
            assert engine.config.temperature == 1.25

    def test_model_id_change_in_settings_does_not_reload_backend(self, worker):
        active_model = "microsoft/Phi-4-mini-instruct"
        engine = MagicMock()
        engine.config = MagicMock()
        engine.config.inference_mode = "local"
        engine.config.active_mode = "local"
        engine.config.model_name = active_model
        engine.config.timeout = 60
        stale_backend = object()
        engine.active_backend = stale_backend
        worker.engine = engine

        fresh = LLMConfig()
        fresh.inference_mode = "local"
        fresh.active_mode = "local"
        fresh.model_name = "microsoft/Phi-3.5-mini-instruct"
        fresh.timeout = 60
        fresh.local_backend_ready = MagicMock(return_value=True)

        with (
            patch("XBrainLab.llm.agent.worker.GenerationThread"),
            patch("XBrainLab.llm.agent.worker.QTimer"),
            patch(
                "XBrainLab.llm.agent.worker.LLMConfig.load_from_file",
                return_value=fresh,
            ),
        ):
            worker.generate_from_messages(_request("test"))

        engine.switch_backend.assert_not_called()
        assert engine.config.model_name == active_model
        assert engine.active_backend is stale_backend

    def test_backend_fields_in_settings_do_not_change_active_selection(
        self,
        worker,
    ):
        active_model = "microsoft/Phi-4-mini-instruct"
        engine = MagicMock()
        engine.config = MagicMock()
        engine.config.inference_mode = "local"
        engine.config.active_mode = "local"
        engine.config.model_name = active_model
        engine.config.timeout = 60
        stale_backend = object()
        engine.active_backend = stale_backend
        worker.engine = engine

        fresh = LLMConfig()
        fresh.inference_mode = "gemini"
        fresh.active_mode = "gemini"
        fresh.model_name = "microsoft/Phi-3.5-mini-instruct"
        fresh.timeout = 60
        with (
            patch("XBrainLab.llm.agent.worker.GenerationThread"),
            patch("XBrainLab.llm.agent.worker.QTimer"),
            patch(
                "XBrainLab.llm.agent.worker.LLMConfig.load_from_file",
                return_value=fresh,
            ),
        ):
            worker.generate_from_messages(_request("test"))

        engine.switch_backend.assert_not_called()
        assert engine.config.inference_mode == "local"
        assert engine.config.active_mode == "local"
        assert engine.config.model_name == active_model
        assert engine.active_backend is stale_backend

    def test_fails_closed_when_generation_settings_reload_fails(self, worker):
        engine = MagicMock()
        engine.config = MagicMock()
        engine.config.inference_mode = "local"
        engine.config.active_mode = "local"
        engine.config.timeout = 60
        worker.engine = engine

        with (
            patch("XBrainLab.llm.agent.worker.GenerationThread") as MockGT,
            patch("XBrainLab.llm.agent.worker.QTimer"),
            patch(
                "XBrainLab.llm.agent.worker.LLMConfig.load_from_file",
                side_effect=RuntimeError("boom"),
            ),
        ):
            worker.generate_from_messages(_request("test", generation_id=31))

        assert worker.engine.config is engine.config
        worker.error.emit.assert_not_called()
        worker.generation_error.emit.assert_called_once_with(
            31,
            SAFE_UNEXPECTED_FAILURE_MESSAGE,
        )
        worker.generation_finished.emit.assert_not_called()
        MockGT.assert_not_called()


class TestCancelGeneration:
    def test_stale_stop_request_does_not_touch_active_generation(self, worker):
        worker._active_generation_id = 42
        worker.generation_thread = MagicMock()
        worker._cleanup_generation_thread = MagicMock()

        worker.cancel_generation(AssistantGenerationStopRequest(generation_id=41))

        worker._cleanup_generation_thread.assert_not_called()
        worker.generation_stop_finished.emit.assert_called_once_with(
            AssistantGenerationStopAcknowledgement(
                generation_id=41,
                stopped=False,
            )
        )
        assert worker._active_generation_id == 42

    def test_stop_request_fails_closed_when_thread_ownership_is_unknown(
        self,
        worker,
    ):
        worker._active_generation_id = None
        worker._generation_thread_id = None
        worker.generation_thread = MagicMock()
        worker._cleanup_generation_thread = MagicMock()

        worker.cancel_generation(AssistantGenerationStopRequest(generation_id=41))

        worker._cleanup_generation_thread.assert_not_called()
        worker.generation_stop_finished.emit.assert_called_once_with(
            AssistantGenerationStopAcknowledgement(
                generation_id=41,
                stopped=False,
            )
        )


class TestOnTimeout:
    def test_emits_correlated_error_only_after_generation_thread_exits(self, worker):
        gt = MagicMock()
        gt.isRunning.return_value = True
        worker.generation_thread = gt
        worker._active_generation_id = 41
        worker._is_timed_out = False

        worker._on_timeout()

        assert worker._is_timed_out
        worker.error.emit.assert_not_called()
        worker.generation_error.emit.assert_not_called()
        worker.generation_finished.emit.assert_not_called()

        worker._release_generation_thread(gt)

        worker.error.emit.assert_not_called()
        worker.generation_error.emit.assert_called_once_with(
            41,
            "Error: Generation timed out (Local LLM is too slow).",
        )
        worker.generation_finished.emit.assert_not_called()

    def test_already_stopped_noop(self, worker):
        gt = MagicMock()
        gt.isRunning.return_value = False
        worker.generation_thread = gt
        worker._is_timed_out = False
        worker._on_timeout()
        assert not worker._is_timed_out


class TestOnGenerationFinished:
    def test_normal(self, worker):
        worker._is_timed_out = False
        worker._active_generation_id = 51
        worker.timeout_timer = MagicMock()
        worker._on_generation_finished(51)
        worker.timeout_timer.stop.assert_called_once_with()
        worker.generation_finished.emit.assert_called_once_with(51, [])
        worker.generation_error.emit.assert_not_called()
        assert worker._active_generation_id is None

    def test_ignored_after_timeout(self, worker):
        worker._is_timed_out = True
        worker._active_generation_id = 52
        worker._on_generation_finished(52)
        worker.generation_finished.emit.assert_not_called()

    def test_ignores_stale_generation_id(self, worker):
        worker._active_generation_id = 53

        worker._on_generation_finished(54)

        worker.generation_finished.emit.assert_not_called()
        assert worker._active_generation_id == 53


class TestOnGenerationError:
    def test_normal(self, worker):
        worker._is_timed_out = False
        worker._active_generation_id = 61
        worker.timeout_timer = MagicMock()
        worker._on_generation_error(61, "oops")
        worker.timeout_timer.stop.assert_called_once_with()
        worker.generation_error.emit.assert_called_once_with(61, "oops")
        worker.error.emit.assert_not_called()
        assert worker._active_generation_id is None

    def test_ignored_after_timeout(self, worker):
        worker._is_timed_out = True
        worker._active_generation_id = 62
        worker._on_generation_error(62, "oops")
        worker.generation_error.emit.assert_not_called()
        worker.error.emit.assert_not_called()

    def test_ignores_stale_generation_id(self, worker):
        worker._active_generation_id = 63

        worker._on_generation_error(64, "oops")

        worker.generation_error.emit.assert_not_called()
        worker.error.emit.assert_not_called()
        assert worker._active_generation_id == 63


class TestReinitializeAgent:
    def test_model_selection_recovers_an_uninitialized_runtime(self, worker):
        model_id = LLMConfig.fallback_local_model_id()
        spec = _launch_spec(model_id)
        worker.engine = None
        worker.initialize_agent = MagicMock()

        with patch.object(LLMConfig, "save_to_file") as save_config:
            worker.reinitialize_agent(spec)

        save_config.assert_called_once_with()
        worker.initialize_agent.assert_called_once_with(spec)

    def test_model_switch_is_rejected_while_generation_is_running(self, worker):
        engine = MagicMock()
        engine.config = LLMConfig()
        worker.engine = engine
        running_thread = MagicMock()
        running_thread.isRunning.return_value = True
        worker.generation_thread = running_thread

        request = _activation_request(
            LLMConfig.fallback_local_model_id(),
            activation_id=31,
        )
        worker.reinitialize_agent(request)

        engine.switch_backend.assert_not_called()
        running_thread.requestInterruption.assert_not_called()
        worker.error.emit.assert_called_once()
        assert "generation" in worker.error.emit.call_args.args[0].lower()
        snapshot = worker.runtime_snapshot_changed.emit.call_args.args[0]
        assert snapshot.phase is AssistantRuntimePhase.FAILED
        assert snapshot.activation_id == 31
        assert "generation" in snapshot.error.lower()

    def test_successful_switch_publishes_terminal_for_same_activation(self, worker):
        initial_spec = _launch_spec(LLMConfig.default_local_model_id())
        request = _activation_request(
            LLMConfig.fallback_local_model_id(),
            activation_id=32,
        )
        engine = MagicMock()
        engine.config = initial_spec.build_config()
        engine.active_backend = object()
        worker.engine = engine
        worker._runtime_launch_spec = initial_spec

        with patch.object(LLMConfig, "save_to_file"):
            worker.reinitialize_agent(request)

        snapshots = [
            call.args[0] for call in worker.runtime_snapshot_changed.emit.call_args_list
        ]
        assert [snapshot.phase for snapshot in snapshots] == [
            AssistantRuntimePhase.LOADING,
            AssistantRuntimePhase.READY,
        ]
        assert {snapshot.activation_id for snapshot in snapshots} == {32}

    def test_failed_switch_publishes_terminal_for_same_activation(self, worker):
        initial_spec = _launch_spec(LLMConfig.default_local_model_id())
        request = _activation_request(
            LLMConfig.fallback_local_model_id(),
            activation_id=33,
        )
        engine = MagicMock()
        engine.config = initial_spec.build_config()
        engine.active_backend = object()
        engine.switch_backend.side_effect = RuntimeError("model load failed")
        worker.engine = engine
        worker._runtime_launch_spec = initial_spec

        worker.reinitialize_agent(request)

        terminal = worker.runtime_snapshot_changed.emit.call_args.args[0]
        assert terminal.phase is AssistantRuntimePhase.FAILED
        assert terminal.activation_id == 33
        assert terminal.error == SAFE_UNEXPECTED_FAILURE_MESSAGE
        assert "model load failed" not in terminal.error

    def test_double_switch_failure_marks_runtime_uninitialized(self, worker):
        from XBrainLab.llm.core.engine import LLMEngine

        config = LLMConfig()
        old_model_id = config.model_name
        old_spec = _launch_spec(old_model_id)
        target_spec = _launch_spec(LLMConfig.fallback_local_model_id())
        engine = LLMEngine(config)
        old_backend = MagicMock()
        old_backend.config = config
        old_backend.load.side_effect = RuntimeError("rollback load failed")
        engine.backends["local"] = old_backend
        engine._backend_model_ids["local"] = old_model_id
        engine.active_backend = old_backend
        worker.engine = engine
        worker._runtime_launch_spec = old_spec
        replacement = MagicMock()
        replacement.load.side_effect = RuntimeError("replacement load failed")

        with patch(
            "XBrainLab.llm.core.backends.local.LocalBackend",
            return_value=replacement,
        ):
            worker.reinitialize_agent(target_spec)

        assert worker.engine is None
        snapshot = worker.runtime_snapshot_changed.emit.call_args.args[0]
        assert snapshot.phase is AssistantRuntimePhase.FAILED
        assert snapshot.initialized is False
        assert snapshot.model_id == target_spec.model_id
        assert snapshot.error == SAFE_UNEXPECTED_FAILURE_MESSAGE
        assert "previous model" not in snapshot.error
        worker.error.emit.assert_called_once()

    def test_legacy_remote_mode_is_rejected(self, worker):
        engine = MagicMock()
        engine.config = LLMConfig()
        engine.config.active_mode = "local"
        worker.engine = engine
        with patch.object(engine.config, "save_to_file") as mock_save:
            worker.reinitialize_agent("Gemini")
        engine.switch_backend.assert_not_called()
        mock_save.assert_not_called()
        worker.error.emit.assert_called_once()
        assert engine.config.active_mode == "local"
        assert engine.config.inference_mode == "local"

    def test_untyped_local_alias_is_rejected(self, worker):
        engine = MagicMock()
        engine.config = LLMConfig()
        engine.config.active_mode = "gemini"
        worker.engine = engine
        with patch.object(engine.config, "save_to_file") as mock_save:
            worker.reinitialize_agent("Local")
        engine.switch_backend.assert_not_called()
        mock_save.assert_not_called()
        worker.error.emit.assert_called_once()
        assert engine.config.active_mode == "gemini"
        assert engine.config.inference_mode == "local"

    def test_unknown_non_catalog_model_is_rejected(self, worker):
        engine = MagicMock()
        engine.config = LLMConfig()
        worker.engine = engine
        with patch.object(engine.config, "save_to_file") as mock_save:
            worker.reinitialize_agent("gpt-4o")
        engine.switch_backend.assert_not_called()
        mock_save.assert_not_called()
        worker.error.emit.assert_called_once()
        assert engine.config.active_mode == "local"
        assert engine.config.inference_mode == "local"

    def test_uninitialized_runtime_rejects_non_catalog_model(self, worker):
        worker.engine = None
        worker.reinitialize_agent("Gemini")
        worker.error.emit.assert_called_once()
        assert "launch spec" in worker.error.emit.call_args.args[0]

    def test_error_emits_signal(self, worker):
        engine = MagicMock()
        old_spec = _launch_spec()
        engine.config = old_spec.build_config()
        engine.switch_backend.side_effect = RuntimeError("fail")
        worker.engine = engine
        worker._runtime_launch_spec = old_spec
        worker.reinitialize_agent(_launch_spec(LLMConfig.fallback_local_model_id()))
        worker.error.emit.assert_called_once()
        assert engine.config.model_name == old_spec.model_id
