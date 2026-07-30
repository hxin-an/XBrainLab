"""Coverage-boost tests for remaining LLM module gaps."""

import json
import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.backend.application.results import ErrorType
from XBrainLab.llm.agent.tool_execution_coordinator import ToolExecutionOutcome
from XBrainLab.llm.agent.turn import (
    AssistantGenerationEvent,
    AssistantGenerationEventPhase,
    AssistantTurnScope,
)
from XBrainLab.llm.tools import application_surface
from XBrainLab.llm.tools.application_surface import (
    ToolAvailability,
    ToolAvailabilityContext,
    ToolCommandResult,
)


def _tool_outcome(message: str, *, ok: bool = True) -> ToolExecutionOutcome:
    return ToolExecutionOutcome(
        ok,
        ToolCommandResult(
            ok=ok,
            tool_name="cmd",
            message=message,
            error_type="none" if ok else "runtime",
        ),
    )


def _command_result(
    *,
    failed: bool = False,
    message: str = "ok",
    diagnostics: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        failed=failed,
        ok=not failed,
        message=message,
        diagnostics=diagnostics or {},
        error_type=ErrorType.RUNTIME if failed else ErrorType.NONE,
        recoverable=True,
    )


def _install_application_surface_contract(
    monkeypatch,
    tool_name: str,
    *,
    result: ToolCommandResult | None = None,
    side_effect: Exception | None = None,
) -> tuple[MagicMock, MagicMock, ToolAvailabilityContext]:
    command_name = application_surface.TOOL_TO_COMMAND[tool_name].value
    context = ToolAvailabilityContext(
        availability=ToolAvailability(
            tool_name=tool_name,
            enabled=True,
            command_name=command_name,
        ),
        state={"canonical_snapshot": True},
        generation=13,
    )
    get_context = MagicMock(return_value=context)
    execute_surface = MagicMock()
    if side_effect is not None:
        execute_surface.side_effect = side_effect
    else:
        execute_surface.return_value = result
    monkeypatch.setattr(application_surface, "get_application_context", get_context)
    monkeypatch.setattr(
        application_surface,
        "execute_application_tool_command",
        execute_surface,
    )
    return get_context, execute_surface, context


# ── retriever.py ────────────────────────────────────────────


class TestRetrieverEdgeCases:
    """Cover initialization errors, close, BM25 build, hybrid path."""

    def test_initialize_already_init(self):
        """Cover the is_initialized early return."""
        from XBrainLab.llm.rag.retriever import RAGRetriever

        r = RAGRetriever()
        r.is_initialized = True
        r.initialize()  # should return immediately

    def test_collection_exists_no_client(self):
        """L127: returns False when client is None."""
        from XBrainLab.llm.rag.retriever import RAGRetriever

        r = RAGRetriever()
        r.client = None
        assert r._collection_exists() is False

    def test_collection_exists_exception(self):
        """L131-133: returns False on exception."""
        from XBrainLab.llm.rag.retriever import RAGRetriever

        r = RAGRetriever()
        r.client = MagicMock()
        r.client.get_collections.side_effect = Exception("fail")
        assert r._collection_exists() is False

    def test_auto_init_gold_set_missing(self):
        """L149-150: early return when gold set missing."""
        from XBrainLab.llm.rag.retriever import RAGRetriever

        r = RAGRetriever()
        r.client = MagicMock()
        r.embeddings = MagicMock()
        with patch("pathlib.Path.exists", return_value=False):
            r._auto_initialize()

    def test_build_bm25_gold_set_missing(self):
        """L183-184: BM25 build bail when gold set missing."""
        from XBrainLab.llm.rag.retriever import RAGRetriever

        r = RAGRetriever()
        with patch("pathlib.Path.exists", return_value=False):
            r._build_bm25_index()
        assert r.bm25_index is None

    def test_build_bm25_success(self):
        """L191-192: BM25 index built successfully."""
        from XBrainLab.llm.rag.retriever import RAGRetriever

        r = RAGRetriever()

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("XBrainLab.llm.rag.retriever.BM25Index") as mock_bm25_index,
        ):
            idx = MagicMock()
            idx.doc_count = 2
            mock_bm25_index.return_value = idx
            r._build_bm25_index()

        idx.build_from_json.assert_called_once()
        gold_set_path = idx.build_from_json.call_args.args[0]
        assert gold_set_path.name == "gold_set.json"
        assert gold_set_path.parent.name == "data"
        assert r.bm25_index is idx

    def test_close_with_client(self):
        """L197: close() closes client."""
        from XBrainLab.llm.rag.retriever import RAGRetriever

        r = RAGRetriever()
        client = MagicMock()
        r.client = client
        r.close()
        client.close.assert_called_once()
        assert r.client is None

    def test_hybrid_retrieval_exception(self):
        """L301-303: exception in hybrid search returns empty string."""
        from XBrainLab.llm.rag.retriever import RAGRetriever

        r = RAGRetriever()
        r.is_initialized = True
        r.client = MagicMock()
        r.embeddings = MagicMock()
        r.embeddings.embed_query.side_effect = Exception("fail")
        r.bm25_index = MagicMock()
        result = r.get_similar_examples("test")
        assert result == ""

    def test_hybrid_bm25_merge(self):
        """L264-276: BM25 results merged into candidates."""
        from XBrainLab.llm.rag.retriever import RAGRetriever

        r = RAGRetriever()
        r.is_initialized = True
        r.embeddings = MagicMock()
        strict_metadata = {
            "tool_calls": [
                {
                    "tool_name": "scan_source",
                    "parameters": {
                        "source_path": "/tmp/example.fif",
                        "label_sources": [],
                    },
                }
            ]
        }

        # Mock qdrant client query_points
        mock_point = MagicMock()
        mock_point.id = "1"
        mock_point.score = 0.9
        mock_point.payload = {
            "page_content": "hello world",
            "metadata": strict_metadata,
        }
        mock_result = MagicMock()
        mock_result.points = [mock_point]
        r.client = MagicMock()
        r.client.query_points.return_value = mock_result

        # Set up BM25
        bm25 = MagicMock()
        bm25.query.return_value = [(5.0, "1", "hello world", strict_metadata)]
        r.bm25_index = bm25

        r.embeddings.embed_query.return_value = [0.1, 0.2, 0.3]

        result = r.get_similar_examples("test")
        assert isinstance(result, str)
        assert "Example" in result


# ── downloader.py DownloadWorker.run() ──────────────────────


class TestDownloadWorkerRun:
    """Cover L107-144: DownloadWorker.run() main loop."""

    @staticmethod
    def _process_context(process, result_queue):
        context = MagicMock()
        context.Process.return_value = process
        context.Queue.return_value = result_queue
        return patch(
            "XBrainLab.llm.core.downloader.multiprocessing.get_context",
            return_value=context,
        )

    def test_cancelled_during_run(self):
        """A cancelled worker reaps its child before reporting terminal failure."""
        from XBrainLab.llm.core.downloader import DownloadWorker

        w = DownloadWorker("test/repo", "/tmp")
        failed = MagicMock()
        w.download_failed.connect(failed)
        w._is_cancelled = True

        mock_proc = MagicMock()
        mock_proc.is_alive.side_effect = [True, False]
        mock_q = MagicMock()
        with self._process_context(mock_proc, mock_q):
            w.run()

        failed.assert_called_once_with("Cancelled by user")
        mock_proc.terminate.assert_called_once()
        mock_proc.join.assert_called()
        assert w._process is None
        assert w._queue is None

    def test_process_dies_unexpectedly(self):
        """L131-140: process not alive + no success in queue."""
        from XBrainLab.llm.core.downloader import DownloadWorker

        w = DownloadWorker("test/repo", "/tmp")
        failed = MagicMock()
        w.download_failed.connect(failed)

        mock_proc = MagicMock()
        mock_proc.is_alive.return_value = False
        mock_proc.exitcode = 1

        import queue as stdlib_queue

        mock_q = MagicMock()
        mock_q.get_nowait.side_effect = stdlib_queue.Empty

        with self._process_context(mock_proc, mock_q):
            w.run()
        failed.assert_called()

    def test_check_queue_success(self):
        """L143-144: successful download detected from queue."""
        from XBrainLab.llm.core.downloader import DownloadWorker

        w = DownloadWorker("test/repo", "/tmp")
        finished = MagicMock()
        w.download_finished.connect(finished)

        mock_proc = MagicMock()
        # Monitor sees the child, then cleanup verifies it before and after join.
        mock_proc.is_alive.side_effect = [True, False, False]

        import queue as stdlib_queue

        mock_q = MagicMock()
        items = [("finished", "/model")]

        def side_effect():
            if items:
                return items.pop(0)
            raise stdlib_queue.Empty

        mock_q.get_nowait.side_effect = side_effect

        with self._process_context(mock_proc, mock_q):
            w.run()
        finished.assert_called_once_with("/model")


# ── controller.py remaining lines ───────────────────────────


def _make_ctrl() -> Any:
    from PyQt6.QtCore import QObject

    from XBrainLab.llm.agent.assembler import PromptToolPublication
    from XBrainLab.llm.agent.controller import LLMController
    from XBrainLab.llm.agent.strict_envelope_recovery import (
        StrictEnvelopeRecoveryPolicy,
    )
    from XBrainLab.llm.agent.tool_attempt_coordinator import ToolAttemptCoordinator
    from XBrainLab.llm.agent.tool_execution_coordinator import (
        ToolExecutionCoordinator,
    )
    from XBrainLab.llm.tools.application_surface import READ_ONLY_TOOLS, TOOL_TO_COMMAND

    ctrl = LLMController.__new__(LLMController)
    QObject.__init__(ctrl)
    conv = MagicMock()
    conv.messages = []
    ctrl._conversation = conv
    ctrl.metrics = MagicMock()
    ctrl.metrics.current_turn = MagicMock()
    ctrl.status_update = MagicMock()
    ctrl.processing_finished = MagicMock()
    ctrl.turn_finished = MagicMock()
    ctrl._active_host_turn_id = 1
    ctrl._active_host_turn_generation = 1
    ctrl.sig_generate = MagicMock()
    ctrl.assembler = MagicMock()
    ctrl.generation_event = MagicMock()
    ctrl.response_presentation_ready = MagicMock()
    ctrl.panel_navigation_requested = MagicMock()
    ctrl.error_occurred = MagicMock()
    ctrl.current_response = ""
    ctrl._generation_id = 0
    ctrl._active_generation_id = None
    ctrl._retry_count = 0
    ctrl._strict_envelope_recovery_policy = StrictEnvelopeRecoveryPolicy(
        max_recovery_attempts=3,
    )
    ctrl.is_processing = True
    ctrl._tool_failure_count = 0
    ctrl._max_tool_failures = 3
    ctrl._successful_tool_count = 0
    ctrl._tool_execution_count = 0
    ctrl._max_tool_executions = 5
    ctrl._turn_cancelled = False
    ctrl._active_turn_scope = AssistantTurnScope.SINGLE_ACTION
    from XBrainLab.llm.agent.pending_interaction import PendingInteractionCoordinator

    ctrl._pending_interactions = PendingInteractionCoordinator()
    ctrl._loop_break_count = 0
    ctrl._max_loop_breaks = 2
    ctrl._active_tool_publication = PromptToolPublication(
        tool_names=frozenset(set(TOOL_TO_COMMAND) | set(READ_ONLY_TOOLS))
    )
    ctrl.registry = MagicMock()
    ctrl.study = MagicMock()
    ctrl.verifier = MagicMock()
    ctrl._rag_lifecycle = MagicMock()
    ctrl._rag_lifecycle.retriever = MagicMock()
    context_source = MagicMock()
    context_source.get_context.side_effect = lambda tool_name: (
        ToolAvailabilityContext(
            availability=ToolAvailability(tool_name=tool_name, enabled=True),
            state={"pipeline_stage": "empty"},
            generation=1,
        )
    )
    ctrl._tool_attempt_coordinator = ToolAttemptCoordinator(
        registry=ctrl.registry,
        verifier=ctrl.verifier,
        context_source=context_source,
    )
    ctrl._tool_execution_coordinator = ToolExecutionCoordinator(
        ctrl,
        block_policy=ctrl._tool_attempt_coordinator,
    )
    return ctrl


class TestControllerResponseComplete:
    """Cover generation completion paths."""

    def test_tool_calls_path(self):
        """Parsed tool calls trigger _process_tool_calls."""
        ctrl = _make_ctrl()
        ctrl.current_response = (
            '{"tool_name":"load_data","parameters":{"paths":["/a"]}}'
        )
        ctrl._active_generation_id = 61
        with patch.object(ctrl, "_process_tool_calls") as mock_ptc:
            ctrl._on_generation_finished(61, [])
        mock_ptc.assert_called_once_with(
            [("load_data", {"paths": ["/a"]})],
            ctrl.current_response,
        )
        assert ctrl._retry_count == 0
        ctrl.generation_event.emit.assert_called_once_with(
            AssistantGenerationEvent(
                generation_id=61,
                phase=AssistantGenerationEventPhase.FINISHED,
            )
        )

    def test_plain_text_path(self):
        """No tool calls publish one typed response and finalize."""
        from XBrainLab.llm.agent.turn import AssistantResponseContract

        ctrl = _make_ctrl()
        ctrl.current_response = "Hello world"
        ctrl._active_response_contract = AssistantResponseContract.NATURAL_LANGUAGE
        ctrl._active_generation_id = 62
        ctrl._on_generation_finished(62, [])
        presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
        assert presentation.text == "Hello world"
        assert ctrl.is_processing is False

    def test_max_retries_json(self):
        """Max retries consumes malformed output and closes the turn safely."""
        from XBrainLab.llm.agent.parser import CommandParser

        ctrl = _make_ctrl()
        ctrl._retry_count = 3
        response = '{"broken'
        result = ctrl._handle_tool_envelope_failure(
            response,
            CommandParser.parse_product(response),
        )
        assert result is True
        ctrl.response_presentation_ready.emit.assert_called_once()
        ctrl.processing_finished.emit.assert_called_once()
        assert ctrl.is_processing is False

    def test_on_generation_error(self):
        """A correlated generation failure emits a typed terminal event."""
        ctrl = _make_ctrl()
        ctrl._active_generation_id = 63

        ctrl._on_generation_error(63, "Something failed")

        ctrl.generation_event.emit.assert_called_once_with(
            AssistantGenerationEvent(
                generation_id=63,
                phase=AssistantGenerationEventPhase.ERROR,
                text="Something failed",
            )
        )
        ctrl.error_occurred.emit.assert_called_with("Something failed")
        presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
        assert "could not complete the request" in presentation.text
        ctrl.status_update.emit.assert_called_with("Error")
        assert ctrl.is_processing is False
        ctrl.processing_finished.emit.assert_called()

    def test_on_runtime_error_without_active_generation(self):
        """An uncorrelated runtime failure stays on the runtime error path."""
        ctrl = _make_ctrl()
        ctrl._active_generation_id = None

        ctrl._on_runtime_error("Runtime failed")

        ctrl.generation_event.emit.assert_not_called()
        ctrl.error_occurred.emit.assert_called_once_with("Runtime failed")
        presentation = ctrl.response_presentation_ready.emit.call_args.args[0]
        assert "could not complete the request" in presentation.text
        assert ctrl.is_processing is False


# ── worker.py remaining lines ───────────────────────────────


class TestWorkerEdgeCases:
    """Cover remaining worker.py gaps."""

    def test_generation_thread_interruption(self):
        """L49-50: interruption check in GenerationThread.run()."""
        from XBrainLab.llm.agent.turn import (
            AssistantGenerationRequest,
            AssistantResponseContract,
        )
        from XBrainLab.llm.agent.worker import GenerationThread

        engine = MagicMock()
        request = AssistantGenerationRequest.from_messages(
            [{"role": "user", "content": "hi"}],
            response_contract=AssistantResponseContract.STRUCTURED_ACTION,
        ).correlated(71)
        t = GenerationThread(engine, request)
        chunk_received = MagicMock()
        finished_generation = MagicMock()
        error_occurred = MagicMock()
        t.chunk_received.connect(chunk_received)
        t.finished_generation.connect(finished_generation)
        t.error_occurred.connect(error_occurred)

        # Simulate interruption on first isInterruptionRequested check
        with patch.object(t, "isInterruptionRequested", return_value=True):
            engine.generate_stream.return_value = iter(["chunk1"])
            t.run()
        chunk_received.assert_not_called()
        finished_generation.assert_called_once()
        error_occurred.assert_not_called()

    def test_cleanup_already_disconnected(self):
        """L129-130: cleanup when signal already disconnected."""
        from XBrainLab.llm.agent.worker import AgentWorker

        w = AgentWorker()
        w.engine = MagicMock()
        w.generation_thread = MagicMock()
        w.generation_thread.chunk_received = MagicMock()
        w.generation_thread.finished_generation = MagicMock()
        w.generation_thread.error_occurred = MagicMock()
        # Disconnect raises TypeError → should be caught
        w.generation_thread.chunk_received.disconnect.side_effect = TypeError
        w.generation_thread.finished_generation.disconnect.side_effect = TypeError
        w.generation_thread.error_occurred.disconnect.side_effect = TypeError
        w.generation_thread.isRunning.return_value = False
        w._cleanup_generation_thread()

    def test_timeout_disconnect_fail(self):
        """A timeout remains pending even when callbacks were disconnected."""
        from XBrainLab.llm.agent.worker import AgentWorker

        w = AgentWorker()
        w.engine = MagicMock()
        thread = MagicMock()
        thread.chunk_received = MagicMock()
        thread.finished_generation = MagicMock()
        thread.error_occurred = MagicMock()
        thread.chunk_received.disconnect.side_effect = RuntimeError
        thread.finished_generation.disconnect.side_effect = RuntimeError
        thread.error_occurred.disconnect.side_effect = RuntimeError
        thread.isRunning.return_value = True
        w.generation_thread = thread
        w._active_generation_id = 72
        lifecycle_errors = []
        generation_errors = []
        w.error.connect(lifecycle_errors.append)
        w.generation_error.connect(
            lambda generation_id, message: generation_errors.append(
                (generation_id, message)
            )
        )

        w._on_timeout()

        assert lifecycle_errors == []
        assert generation_errors == []
        assert w.generation_thread is thread
        w._release_generation_thread(thread)
        assert lifecycle_errors == []
        assert generation_errors == [
            (72, "Error: Generation timed out (Local LLM is too slow).")
        ]


# ── config.py ───────────────────────────────────────────────


class TestLLMConfig:
    """Cover config.py gaps."""

    def test_cuda_available_returns_false_on_import_error(self):
        """_cuda_available returns False when PyTorch cannot be imported."""
        from XBrainLab.llm.core import config as config_module

        with patch("builtins.__import__", side_effect=ImportError("torch missing")):
            assert config_module._cuda_available() is False

    def test_save_to_file_default_path(self, tmp_path):
        """L129: save_to_file uses default path."""
        from XBrainLab.llm.core.config import LLMConfig

        cfg = LLMConfig()
        target = tmp_path / "settings.json"
        with patch.object(
            cfg,
            "_default_settings_path",
            return_value=str(target),
        ):
            saved = cfg.save_to_file()

        assert saved is True
        payload = json.loads(target.read_text(encoding="utf-8"))
        assert payload["local"]["model_name"] == cfg.model_name
        assert payload["inference_mode"] == "local"

    def test_save_to_file_exception(self, tmp_path, caplog):
        """L149-150: save failure logged."""
        from XBrainLab.llm.core.config import LLMConfig

        cfg = LLMConfig()
        target = tmp_path / "settings.json"
        original = b'{"local":{"model_name":"known-good"}}\n'
        target.write_bytes(original)
        with (
            patch(
                "XBrainLab.llm.core.config.json.dump", side_effect=OSError("disk full")
            ),
            caplog.at_level(logging.ERROR, logger="XBrainLab.llm.core.config"),
        ):
            saved = cfg.save_to_file(str(target))

        assert saved is False
        assert target.read_bytes() == original
        assert list(tmp_path.glob(".settings.json.*.tmp")) == []
        assert "Error saving settings" in caplog.text


# ── engine.py ───────────────────────────────────────────────


class TestLLMEngine:
    """Cover engine.py gaps."""

    def test_get_current_model_id_legacy_request_uses_local_model(self):
        """Legacy remote model ID lookup returns the local product model."""
        from XBrainLab.llm.core.engine import LLMEngine

        e = LLMEngine.__new__(LLMEngine)
        e.config = MagicMock()
        e.config.model_name = "microsoft/Phi-4-mini-instruct"
        e.backends = {}
        result = e._get_current_model_id("gemini")
        assert result == "microsoft/Phi-4-mini-instruct"

    def test_stale_backend_reloads(self):
        """L83, L94: stale backend deleted and reloaded."""
        from XBrainLab.llm.core.engine import LLMEngine

        e = LLMEngine.__new__(LLMEngine)
        e.config = MagicMock()
        e.config.inference_mode = "local"
        e.config.model_name = "microsoft/Phi-3.5-mini-instruct"
        mock_backend = MagicMock()
        e.backends = {"local": mock_backend}
        e._backend_model_ids = {"local": "microsoft/Phi-4-mini-instruct"}
        e.active_backend = mock_backend

        new_backend = MagicMock()
        with patch("XBrainLab.llm.core.backends.local.LocalBackend") as mock_local:
            mock_local.return_value = new_backend
            e.switch_backend("local")
        assert e.active_backend is new_backend
        assert e.backends["local"] is new_backend
        assert e._backend_model_ids["local"] == "microsoft/Phi-3.5-mini-instruct"

    def test_generate_stream_no_backend(self):
        """L135: raise RuntimeError if no backend."""
        from XBrainLab.llm.core.engine import LLMEngine
        from XBrainLab.llm.core.generation import GenerationProfile

        e = LLMEngine.__new__(LLMEngine)
        e.config = MagicMock()
        e.config.inference_mode = "local"
        e.config.local_model_path = ""
        e.backends = {}
        e.active_backend = None

        with pytest.raises(RuntimeError, match="No active backend"):
            list(
                e.generate_stream(
                    [],
                    profile=GenerationProfile.INFORMATIONAL_TEXT,
                )
            )


# ── backends: local.py only ─────────────────────────────────


class TestRemovedRemoteBackends:
    """Guard remote backend modules stay out of product code."""

    def test_remote_backend_modules_are_absent(self):
        import importlib.util

        assert importlib.util.find_spec("XBrainLab.llm.core.backends.api") is None
        assert importlib.util.find_spec("XBrainLab.llm.core.backends.gemini") is None


class TestLocalBackendExtra:
    """Cover local.py remaining gaps."""

    def test_quantization_kwarg(self):
        """L88: load_in_4bit set when quantization enabled."""
        from XBrainLab.llm.core.backends.local import LocalBackend
        from XBrainLab.llm.core.config import LLMConfig

        b = LocalBackend.__new__(LocalBackend)
        b.config = MagicMock()
        b.config.model_name = LLMConfig.default_local_model_id()
        b.config.cache_dir = "/tmp/models"
        b.config.load_in_4bit = True
        b.config.device = "cuda"
        b.config.max_new_tokens = 128
        b.config.temperature = 0.7
        b.config.top_p = 0.9
        b.config.do_sample = True
        b.model = None
        b.tokenizer = None
        b.is_loaded = False

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.zeros.return_value = MagicMock()
        mock_bnb_config = MagicMock(return_value=object())
        mock_mdl = MagicMock(from_pretrained=MagicMock(return_value=MagicMock()))

        with (
            patch.dict(
                "sys.modules",
                {
                    "torch": mock_torch,
                    "transformers": MagicMock(
                        BitsAndBytesConfig=mock_bnb_config,
                        AutoTokenizer=MagicMock(
                            from_pretrained=MagicMock(return_value=MagicMock())
                        ),
                        AutoModelForCausalLM=mock_mdl,
                    ),
                },
            ),
            patch(
                "XBrainLab.backend.application.resource_guard."
                "ResourceChecker.get_gpu_vram_status",
                return_value={
                    "gpu_name": "Test GPU",
                    "available_bytes": 20_000_000_000,
                    "total_bytes": 24_000_000_000,
                    "used_bytes": 4_000_000_000,
                    "allocated_bytes": 0,
                    "reserved_bytes": 0,
                    "gpu_index": 0,
                    "device_count": 1,
                    "reason": None,
                    "query_error_type": None,
                },
            ),
        ):
            b.load()
        mock_bnb_config.assert_called_once_with(load_in_4bit=True)
        assert "quantization_config" in mock_mdl.from_pretrained.call_args.kwargs

    def test_generate_stream_no_model(self):
        """L206: raises RuntimeError when model not loaded."""
        from XBrainLab.llm.core.backends.local import LocalBackend
        from XBrainLab.llm.core.generation import ResolvedGenerationOptions

        b = LocalBackend.__new__(LocalBackend)
        b.model = None
        b.tokenizer = None
        b.is_loaded = False
        b.load = MagicMock(side_effect=RuntimeError("model not loaded"))
        with pytest.raises(RuntimeError, match="not loaded"):
            list(
                b.generate_stream(
                    [{"role": "user", "content": "hi"}],
                    options=ResolvedGenerationOptions(
                        max_new_tokens=128,
                        do_sample=False,
                    ),
                )
            )
        b.load.assert_called_once()


# ── indexer.py remaining ────────────────────────────────────


class TestRAGIndexerEdgeCases:
    """Cover indexer.py remaining gaps."""

    def test_index_data_empty_docs(self):
        """L121-122: no documents warning."""
        from XBrainLab.llm.rag.indexer import RAGIndexer

        with patch("XBrainLab.llm.rag.indexer.HuggingFaceEmbeddings"):
            idx: Any = RAGIndexer.__new__(RAGIndexer)
            idx.client = MagicMock()
            idx.embeddings = MagicMock()
            idx._own_client = False
            idx.index_data([])  # should warn and return


# ── mock preprocess tools error paths ───────────────────────


class TestMockPreprocessErrors:
    """Verify missing preprocessing arguments use typed input failures."""

    @pytest.mark.parametrize(
        "cls_name,params,message",
        [
            ("MockBandPassFilterTool", {}, "Error: frequencies are required"),
            ("MockNotchFilterTool", {}, "Error: frequency is required"),
            ("MockResampleTool", {}, "Error: rate is required"),
            ("MockNormalizeTool", {}, "Error: method is required"),
            ("MockRereferenceTool", {}, "Error: method is required"),
            ("MockChannelSelectionTool", {}, "Error: channels list is required"),
            ("MockSetMontageTool", {}, "Error: montage_name is required"),
        ],
    )
    def test_missing_required_params(self, cls_name, params, message):
        import XBrainLab.llm.tools.mock.preprocess_mock as mod
        from XBrainLab.llm.tools.mock.state import MockWorkflowState
        from XBrainLab.llm.tools.result_contract import ToolResult

        cls = getattr(mod, cls_name)
        tool = cls(MockWorkflowState(data_loaded=True))
        result = tool.execute(MagicMock(), **params)
        assert isinstance(result, ToolResult)
        assert result.ok is False
        assert result.message == message
        assert result.payload is None
        assert result.error_type == "input"
        assert result.recoverable is True


# ── real training tools error/success ───────────────────────


class TestRealTrainingTools:
    """Cover training_real.py remaining lines."""

    def test_set_model_success(self, monkeypatch):
        from XBrainLab.llm.tools.real.training_real import RealSetModelTool

        surface_result = ToolCommandResult(
            ok=True,
            tool_name="set_model",
            command_name="configure_training",
            message="Model successfully set to EEGNet.",
            error_type="none",
            recoverable=True,
            diagnostics={"model_name": "EEGNet"},
        )
        get_context, execute_surface, context = _install_application_surface_contract(
            monkeypatch,
            "set_model",
            result=surface_result,
        )
        study = object()

        result = RealSetModelTool().execute(study, model_name="EEGNet")

        assert result.ok is True
        assert result.message == "Model successfully set to EEGNet."
        assert result.payload is None
        assert result.error_type == "none"
        assert result.recoverable is True
        assert result.command_name == "configure_training"
        assert result.diagnostics == {"model_name": "EEGNet"}
        get_context.assert_called_once_with(study, "set_model")
        execute_surface.assert_called_once_with(
            study,
            "set_model",
            {"model_name": "EEGNet"},
            availability=context.availability,
            state=context.state,
        )

    def test_configure_training_exception(self, monkeypatch):
        from XBrainLab.llm.tools.real.training_real import RealConfigureTrainingTool

        error = RuntimeError("bad config")
        get_context, execute_surface, context = _install_application_surface_contract(
            monkeypatch,
            "configure_training",
            side_effect=error,
        )
        study = object()

        result = RealConfigureTrainingTool().execute(
            study,
            epoch=10,
            batch_size=32,
            learning_rate=0.001,
        )

        expected_params = {
            "model_name": None,
            "epoch": 10,
            "batch_size": 32,
            "learning_rate": 0.001,
            "repeat": 1,
            "device": "cpu",
            "optimizer": "adam",
            "evaluation_option": "last_epoch",
            "save_checkpoints_every": 0,
        }
        assert result.ok is False
        assert result.message == (
            "The assistant tool could not complete the action. "
            "Refresh application state before retrying."
        )
        assert result.payload is None
        assert result.error_type == "runtime"
        assert result.recoverable is False
        assert result.command_name == "configure_training"
        assert result.error_code == "unexpected_tool_failure"
        assert result.recovery_action == "refresh_application_state"
        assert result.state is None
        assert result.capability is None
        assert result.changed_state["state_unknown"] is True
        assert result.diagnostics["incident_id"]
        get_context.assert_called_once_with(
            study,
            "configure_training",
        )
        execute_surface.assert_called_once_with(
            study,
            "configure_training",
            expected_params,
            availability=context.availability,
            state=context.state,
        )

    def test_start_training_exception(self, monkeypatch):
        from XBrainLab.llm.tools.real.training_real import RealStartTrainingTool

        error = RuntimeError("GPU OOM")
        get_context, execute_surface, context = _install_application_surface_contract(
            monkeypatch,
            "start_training",
            side_effect=error,
        )
        study = object()

        result = RealStartTrainingTool().execute(study)

        expected_params = {
            "append": True,
            "interactive": True,
            "confirmed": False,
            "resource_preflight_confirmed": False,
            "resource_preflight_token": None,
        }
        assert result.ok is False
        assert result.message == (
            "The assistant tool could not complete the action. "
            "Refresh application state before retrying."
        )
        assert result.payload is None
        assert result.error_type == "runtime"
        assert result.recoverable is False
        assert result.command_name == "train"
        assert result.error_code == "unexpected_tool_failure"
        assert result.recovery_action == "refresh_application_state"
        assert result.state is None
        assert result.capability is None
        assert result.changed_state["state_unknown"] is True
        assert result.diagnostics["incident_id"]
        get_context.assert_called_once_with(study, "start_training")
        execute_surface.assert_called_once_with(
            study,
            "start_training",
            expected_params,
            availability=context.availability,
            state=context.state,
        )
