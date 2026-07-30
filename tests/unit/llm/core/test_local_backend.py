"""Tests for LocalBackend (HuggingFace Transformers local inference)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from threading import Event, Thread
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.generation import ResolvedGenerationOptions

CONFIGURED_TEST_OPTIONS = ResolvedGenerationOptions(
    max_new_tokens=128,
    do_sample=True,
    temperature=0.7,
    top_p=0.9,
)
GRANITE_MODEL_ID = "ibm-granite/granite-3.3-2b-instruct"
GRANITE_MODEL_REVISION = (
    "707f574c62054322f6b5b04b6d075f0a8f05e0f0"  # pragma: allowlist secret
)
PRIMARY_MODEL_REVISION = GRANITE_MODEL_REVISION


class _EmptyStreamer:
    def __iter__(self) -> Iterator[str]:
        return iter(())

    def end(self) -> None:
        return None


def _configure_blocking_generation(
    backend: Any,
) -> tuple[
    MagicMock,
    Event,
    Event,
    list[Thread],
    Callable[..., Thread],
    MagicMock,
]:
    tokenizer = MagicMock()
    tokenizer.apply_chat_template.return_value = "prompt text"
    tokenizer.return_value = MagicMock(to=MagicMock(return_value={}))

    release = Event()
    started = Event()
    model = MagicMock()
    model.device = "cpu"

    def block_generation(**_kwargs: Any) -> None:
        started.set()
        release.wait(timeout=3)

    model.generate.side_effect = block_generation
    backend.is_loaded = True
    backend.tokenizer = tokenizer
    backend.model = model

    threads: list[Thread] = []

    def thread_factory(*args: Any, **kwargs: Any) -> Thread:
        thread = Thread(*args, **kwargs)
        threads.append(thread)
        return thread

    transformers = MagicMock()
    transformers.TextIteratorStreamer.side_effect = lambda *_args, **_kwargs: (
        _EmptyStreamer()
    )
    return model, release, started, threads, thread_factory, transformers


def _make_config(**overrides):
    defaults = {
        "model_name": GRANITE_MODEL_ID,
        "device": "cpu",
        "load_in_4bit": False,
        "cache_dir": "/tmp/cache",
        "max_new_tokens": 128,
        "temperature": 0.7,
        "top_p": 0.9,
        "do_sample": True,
    }
    defaults.update(overrides)
    cfg = MagicMock(spec=LLMConfig)
    for k, v in defaults.items():
        setattr(cfg, k, v)
    return cfg


class TestLocalBackendInit:
    def test_init_defaults(self):
        from XBrainLab.llm.core.backends.local import LocalBackend

        cfg = _make_config()
        backend = LocalBackend(cfg)
        assert backend.config is cfg
        assert backend.model is None
        assert backend.tokenizer is None
        assert backend.is_loaded is False


class TestGenerationOwnedEngineLifecycle:
    def test_engine_retains_backend_when_generation_blocks_unload(self):
        from XBrainLab.llm.core.engine import LLMEngine

        config = LLMConfig(inference_mode="local")
        engine = LLMEngine(config)
        backend = MagicMock()
        backend.unload.return_value = False
        engine.backends["local"] = backend
        engine._backend_model_ids["local"] = "old-model"
        engine.active_backend = backend
        config.model_name = "new-model"

        with pytest.raises(RuntimeError, match="generation is still running"):
            engine.switch_backend("local")

        assert engine.backends == {"local": backend}
        assert engine.active_backend is backend
        assert engine._backend_model_ids == {"local": "old-model"}
        assert engine.close() is False
        assert engine.backends == {"local": backend}
        assert engine.active_backend is backend


class TestGenerationProfiles:
    @pytest.mark.parametrize(
        ("options", "expected_sampling"),
        [
            (
                ResolvedGenerationOptions(
                    max_new_tokens=128,
                    do_sample=True,
                    temperature=0.7,
                    top_p=0.9,
                ),
                True,
            ),
            (ResolvedGenerationOptions(max_new_tokens=128, do_sample=False), False),
        ],
    )
    def test_profile_controls_sampling_without_mutating_saved_config(
        self,
        options,
        expected_sampling,
    ):
        from XBrainLab.llm.core.backends.local import LocalBackend

        config = _make_config(do_sample=True)
        backend = LocalBackend(config)
        backend.is_loaded = True
        tokenizer = MagicMock()
        tokenizer.apply_chat_template.return_value = "prompt text"
        tokenizer.return_value = MagicMock(to=MagicMock(return_value={}))
        model = MagicMock()
        model.device = "cpu"
        backend.tokenizer = tokenizer
        backend.model = model
        streamer = MagicMock()
        streamer.__iter__ = MagicMock(return_value=iter([]))

        class ImmediateThread:
            def __init__(self, target, **_kwargs):
                self._target = target

            def start(self):
                self._target()

            def join(self, timeout=0):
                return None

            def is_alive(self):
                return False

        with (
            patch.dict(
                "sys.modules",
                {
                    "transformers": MagicMock(
                        TextIteratorStreamer=MagicMock(return_value=streamer)
                    ),
                },
            ),
            patch(
                "XBrainLab.llm.core.backends.local.Thread",
                ImmediateThread,
            ),
        ):
            list(
                backend.generate_stream(
                    [{"role": "user", "content": "hi"}],
                    options=options,
                )
            )

        generation_kwargs = model.generate.call_args.kwargs
        assert generation_kwargs["do_sample"] is expected_sampling
        assert config.do_sample is True
        if expected_sampling:
            assert generation_kwargs["temperature"] == 0.7
            assert generation_kwargs["top_p"] == 0.9
        else:
            assert "temperature" not in generation_kwargs
            assert "top_p" not in generation_kwargs

    def test_tokenizer_input_is_bounded_by_the_catalog_runtime_context(self):
        from XBrainLab.llm.core.backends.local import LocalBackend

        config = _make_config(model_name=GRANITE_MODEL_ID)
        backend = LocalBackend(config)
        backend.is_loaded = True
        tokenizer = MagicMock()
        tokenizer.apply_chat_template.return_value = "prompt text"
        tokenizer.return_value = MagicMock(to=MagicMock(return_value={}))
        model = MagicMock()
        model.device = "cpu"
        backend.tokenizer = tokenizer
        backend.model = model
        streamer = MagicMock()
        streamer.__iter__ = MagicMock(return_value=iter([]))

        class ImmediateThread:
            def __init__(self, target, **_kwargs):
                self._target = target

            def start(self):
                self._target()

            def join(self, timeout=0):
                return None

            def is_alive(self):
                return False

        with (
            patch.dict(
                "sys.modules",
                {
                    "transformers": MagicMock(
                        TextIteratorStreamer=MagicMock(return_value=streamer)
                    ),
                },
            ),
            patch("XBrainLab.llm.core.backends.local.Thread", ImmediateThread),
        ):
            list(
                backend.generate_stream(
                    [{"role": "user", "content": "hi"}],
                    options=CONFIGURED_TEST_OPTIONS,
                )
            )

        tokenizer.assert_called_once_with(
            "prompt text",
            return_tensors="pt",
            truncation=True,
            max_length=8_192 - CONFIGURED_TEST_OPTIONS.max_new_tokens,
        )
        assert tokenizer.truncation_side == "left"


class TestLocalBackendLoad:
    def test_load_already_loaded(self):
        from XBrainLab.llm.core.backends.local import LocalBackend

        cfg = _make_config()
        backend = LocalBackend(cfg)
        backend.is_loaded = True
        # Should return immediately without importing anything
        backend.load()
        assert backend.is_loaded is True

    @patch("XBrainLab.llm.core.backends.local.torch", create=True)
    def test_load_cpu(self, mock_torch):
        from XBrainLab.llm.core.backends.local import LocalBackend

        cfg = _make_config(device="cpu", load_in_4bit=False)
        backend = LocalBackend(cfg)

        mock_tokenizer = MagicMock()
        mock_model = MagicMock()
        mock_tokenizer_cls = MagicMock(
            from_pretrained=MagicMock(return_value=mock_tokenizer)
        )
        mock_model_cls = MagicMock(from_pretrained=MagicMock(return_value=mock_model))

        with patch.dict(
            "sys.modules",
            {
                "torch": mock_torch,
                "transformers": MagicMock(
                    AutoTokenizer=mock_tokenizer_cls,
                    AutoModelForCausalLM=mock_model_cls,
                ),
            },
        ):
            backend.load()

        assert backend.is_loaded is True
        assert backend.tokenizer is not None
        assert backend.model is not None
        tokenizer_kwargs = mock_tokenizer_cls.from_pretrained.call_args.kwargs
        model_kwargs = mock_model_cls.from_pretrained.call_args.kwargs
        assert tokenizer_kwargs["local_files_only"] is True
        assert model_kwargs["local_files_only"] is True
        assert tokenizer_kwargs["revision"] == PRIMARY_MODEL_REVISION
        assert model_kwargs["revision"] == PRIMARY_MODEL_REVISION

    @patch("XBrainLab.llm.core.backends.local.torch", create=True)
    def test_load_4bit(self, mock_torch):
        from XBrainLab.llm.core.backends.local import LocalBackend

        cfg = _make_config(device="cuda", load_in_4bit=True)
        backend = LocalBackend(cfg)

        mock_tokenizer = MagicMock()
        mock_model = MagicMock()
        mock_quantization_config = object()
        mock_bnb_config = MagicMock(return_value=mock_quantization_config)

        with patch.dict(
            "sys.modules",
            {
                "torch": mock_torch,
                "transformers": MagicMock(
                    BitsAndBytesConfig=mock_bnb_config,
                    AutoTokenizer=MagicMock(
                        from_pretrained=MagicMock(return_value=mock_tokenizer)
                    ),
                    AutoModelForCausalLM=MagicMock(
                        from_pretrained=MagicMock(return_value=mock_model)
                    ),
                ),
            },
        ):
            backend.load()

        assert backend.is_loaded is True
        mock_bnb_config.assert_called_once_with(load_in_4bit=True)

    @patch("XBrainLab.llm.core.backends.local.torch", create=True)
    def test_granite_cuda_index_uses_catalog_bfloat16_and_forbids_remote_code(
        self,
        mock_torch,
    ):
        from XBrainLab.llm.core.backends.local import LocalBackend

        cfg = _make_config(
            model_name=GRANITE_MODEL_ID,
            device="cuda:0",
            trust_remote_code=True,
        )
        backend = LocalBackend(cfg)
        mock_tokenizer_cls = MagicMock(
            from_pretrained=MagicMock(return_value=MagicMock())
        )
        mock_model = MagicMock()
        mock_model_cls = MagicMock(from_pretrained=MagicMock(return_value=mock_model))

        with patch.dict(
            "sys.modules",
            {
                "torch": mock_torch,
                "transformers": MagicMock(
                    BitsAndBytesConfig=MagicMock(),
                    AutoTokenizer=mock_tokenizer_cls,
                    AutoModelForCausalLM=mock_model_cls,
                ),
            },
        ):
            backend.load()

        tokenizer_kwargs = mock_tokenizer_cls.from_pretrained.call_args.kwargs
        model_kwargs = mock_model_cls.from_pretrained.call_args.kwargs
        assert tokenizer_kwargs["revision"] == GRANITE_MODEL_REVISION
        assert tokenizer_kwargs["trust_remote_code"] is False
        assert model_kwargs["trust_remote_code"] is False
        assert model_kwargs["dtype"] is mock_torch.bfloat16
        mock_model.to.assert_called_once_with("cuda:0")

    @patch("XBrainLab.llm.core.backends.local.torch", create=True)
    def test_load_failure(self, mock_torch):
        from XBrainLab.llm.core.backends.local import LocalBackend

        cfg = _make_config()
        backend = LocalBackend(cfg)

        with (
            patch.dict(
                "sys.modules",
                {
                    "torch": mock_torch,
                    "transformers": MagicMock(
                        AutoTokenizer=MagicMock(
                            from_pretrained=MagicMock(
                                side_effect=OSError("download failed")
                            )
                        ),
                        AutoModelForCausalLM=MagicMock(),
                    ),
                },
            ),
            pytest.raises(OSError, match="download failed"),
        ):
            backend.load()

        assert backend.is_loaded is False

    @patch("XBrainLab.llm.core.backends.local.torch", create=True)
    def test_load_falls_back_to_cpu_when_cuda_probe_fails(self, mock_torch):
        from XBrainLab.llm.core.backends.local import LocalBackend

        cfg = _make_config(device="cuda", load_in_4bit=True)
        backend = LocalBackend(cfg)

        mock_torch.cuda.is_available.return_value = True
        mock_torch.zeros.side_effect = RuntimeError("no kernel image")

        mock_tokenizer = MagicMock()
        mock_model_loader = MagicMock(return_value=MagicMock())

        with patch.dict(
            "sys.modules",
            {
                "torch": mock_torch,
                "transformers": MagicMock(
                    BitsAndBytesConfig=MagicMock(),
                    AutoTokenizer=MagicMock(
                        from_pretrained=MagicMock(return_value=mock_tokenizer)
                    ),
                    AutoModelForCausalLM=MagicMock(from_pretrained=mock_model_loader),
                ),
            },
        ):
            backend.load()

        assert cfg.device == "cpu"
        assert cfg.load_in_4bit is False
        call_kwargs = mock_model_loader.call_args.kwargs
        assert "device_map" not in call_kwargs
        assert "quantization_config" not in call_kwargs

    def test_product_backend_has_no_remote_code_compatibility_hook(self):
        from XBrainLab.llm.core.backends.local import LocalBackend

        assert not hasattr(LocalBackend, "_patch_remote_code_compat")

    def test_unload_releases_model_and_cuda_cache(self):
        from XBrainLab.llm.core.backends.local import LocalBackend

        cfg = _make_config(device="cuda")
        backend = LocalBackend(cfg)
        backend.model = MagicMock()
        backend.tokenizer = MagicMock()
        backend.is_loaded = True

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True

        with patch.dict("sys.modules", {"torch": mock_torch}):
            backend.unload()

        assert backend.model is None
        assert backend.tokenizer is None
        assert backend.is_loaded is False
        mock_torch.cuda.empty_cache.assert_called_once()


class TestProcessMessages:
    def _get_backend(self):
        from XBrainLab.llm.core.backends.local import LocalBackend

        return LocalBackend(_make_config())

    def test_empty_messages(self):
        backend = self._get_backend()
        assert backend._process_messages_for_template([]) == []

    def test_no_system_message(self):
        backend = self._get_backend()
        msgs = [{"role": "user", "content": "hello"}]
        result = backend._process_messages_for_template(msgs)
        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_granite_preserves_native_system_role(self):
        from XBrainLab.llm.core.backends.local import LocalBackend

        backend = LocalBackend(_make_config(model_name=GRANITE_MODEL_ID))
        messages = [
            {"role": "system", "content": "Use the strict action envelope."},
            {"role": "user", "content": "Continue until a decision is needed."},
        ]

        result = backend._process_messages_for_template(messages)

        assert result == messages

    def test_granite_preserves_system_only_message(self):
        backend = self._get_backend()
        msgs = [{"role": "system", "content": "instructions"}]
        result = backend._process_messages_for_template(msgs)
        assert result == msgs

    def test_consecutive_same_role_merged(self):
        backend = self._get_backend()
        msgs = [
            {"role": "user", "content": "a"},
            {"role": "user", "content": "b"},
            {"role": "assistant", "content": "c"},
        ]
        result = backend._process_messages_for_template(msgs)
        assert len(result) == 2
        assert "a" in result[0]["content"]
        assert "b" in result[0]["content"]

    def test_alternating_roles_not_merged(self):
        backend = self._get_backend()
        msgs = [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"},
        ]
        result = backend._process_messages_for_template(msgs)
        assert len(result) == 3


class TestGenerateStream:
    def test_generate_stream_not_loaded(self):
        from XBrainLab.llm.core.backends.local import LocalBackend

        cfg = _make_config()
        backend = LocalBackend(cfg)
        backend.is_loaded = True
        backend.tokenizer = None
        backend.model = None

        with pytest.raises(RuntimeError, match="not loaded"):
            list(
                backend.generate_stream(
                    [{"role": "user", "content": "hi"}],
                    options=CONFIGURED_TEST_OPTIONS,
                )
            )

    def test_generate_stream_calls_load(self):
        """generate_stream calls load() if not loaded."""
        from XBrainLab.llm.core.backends.local import LocalBackend

        cfg = _make_config()
        backend = LocalBackend(cfg)

        with (
            patch.object(backend, "load", side_effect=RuntimeError("skip")),
            pytest.raises(RuntimeError, match="skip"),
        ):
            list(
                backend.generate_stream(
                    [{"role": "user", "content": "hi"}],
                    options=CONFIGURED_TEST_OPTIONS,
                )
            )

    def test_generate_stream_success(self):
        from XBrainLab.llm.core.backends.local import LocalBackend

        cfg = _make_config()
        backend = LocalBackend(cfg)
        backend.is_loaded = True

        mock_tokenizer = MagicMock()
        mock_tokenizer.apply_chat_template.return_value = "prompt text"
        mock_tokenizer.return_value = MagicMock(to=MagicMock(return_value={}))

        mock_model = MagicMock()
        mock_model.device = "cpu"

        backend.tokenizer = mock_tokenizer
        backend.model = mock_model

        mock_streamer = MagicMock()
        mock_streamer.__iter__ = MagicMock(return_value=iter(["Hello", " world"]))

        with (
            patch.dict(
                "sys.modules",
                {
                    "transformers": MagicMock(
                        TextIteratorStreamer=MagicMock(return_value=mock_streamer)
                    ),
                },
            ),
            patch(
                "XBrainLab.llm.core.backends.local.Thread",
            ) as mock_thread_cls,
        ):
            result = list(
                backend.generate_stream(
                    [{"role": "user", "content": "hi"}],
                    options=CONFIGURED_TEST_OPTIONS,
                )
            )
            mock_thread_cls.return_value.start.assert_called_once()
            assert result == ["Hello", " world"]

    def test_generate_stream_surfaces_generation_thread_error(self):
        from XBrainLab.llm.core.backends.local import LocalBackend

        cfg = _make_config()
        backend = LocalBackend(cfg)
        backend.is_loaded = True

        mock_tokenizer = MagicMock()
        mock_tokenizer.apply_chat_template.return_value = "prompt text"
        mock_tokenizer.return_value = MagicMock(to=MagicMock(return_value={}))

        mock_model = MagicMock()
        mock_model.device = "cpu"
        mock_model.generate.side_effect = RuntimeError("boom")

        backend.tokenizer = mock_tokenizer
        backend.model = mock_model

        mock_streamer = MagicMock()
        mock_streamer.__iter__ = MagicMock(return_value=iter([]))

        class ImmediateThread:
            def __init__(self, target, **_kwargs):
                self.target = target

            def start(self):
                self.target()

            def join(self, timeout=0):
                return None

            def is_alive(self):
                return False

        with (
            patch.dict(
                "sys.modules",
                {
                    "transformers": MagicMock(
                        TextIteratorStreamer=MagicMock(return_value=mock_streamer)
                    ),
                },
            ),
            patch(
                "XBrainLab.llm.core.backends.local.Thread",
                ImmediateThread,
            ),
            pytest.raises(RuntimeError, match="Local generation failed: boom"),
        ):
            list(
                backend.generate_stream(
                    [{"role": "user", "content": "hi"}],
                    options=CONFIGURED_TEST_OPTIONS,
                )
            )

        mock_streamer.end.assert_called_once()

    def test_cancel_generation_waits_for_model_thread_exit(self):
        from XBrainLab.llm.core.backends.local import LocalBackend

        backend = LocalBackend(_make_config())
        (
            _model,
            release,
            started,
            threads,
            thread_factory,
            transformers,
        ) = _configure_blocking_generation(backend)
        outer_thread = Thread(
            target=lambda: list(
                backend.generate_stream(
                    [{"role": "user", "content": "first"}],
                    options=CONFIGURED_TEST_OPTIONS,
                )
            )
        )

        try:
            with (
                patch.dict("sys.modules", {"transformers": transformers}),
                patch(
                    "XBrainLab.llm.core.backends.local.Thread",
                    side_effect=thread_factory,
                ),
            ):
                outer_thread.start()
                assert started.wait(timeout=1)

                assert backend.cancel_generation(wait_timeout=0.01) is False
                release.set()
                outer_thread.join(timeout=1)
                assert backend.cancel_generation(wait_timeout=0.01) is True
        finally:
            release.set()
            outer_thread.join(timeout=1)
            for thread in threads:
                thread.join(timeout=1)
        assert outer_thread.is_alive() is False

    def test_rejects_next_generation_while_model_thread_outlives_streamer(self):
        from XBrainLab.llm.core.backends.local import LocalBackend

        backend = LocalBackend(_make_config())
        (
            model,
            release,
            started,
            threads,
            thread_factory,
            transformers,
        ) = _configure_blocking_generation(backend)
        outer_errors: list[BaseException] = []

        def consume_first_generation() -> None:
            try:
                list(
                    backend.generate_stream(
                        [{"role": "user", "content": "first"}],
                        options=CONFIGURED_TEST_OPTIONS,
                    )
                )
            except BaseException as error:
                outer_errors.append(error)

        outer_thread = Thread(target=consume_first_generation)

        try:
            with (
                patch.dict("sys.modules", {"transformers": transformers}),
                patch(
                    "XBrainLab.llm.core.backends.local.Thread",
                    side_effect=thread_factory,
                ),
            ):
                outer_thread.start()
                assert started.wait(timeout=1)

                with pytest.raises(RuntimeError, match=r"generation.*still running"):
                    list(
                        backend.generate_stream(
                            [{"role": "user", "content": "second"}],
                            options=CONFIGURED_TEST_OPTIONS,
                        )
                    )

            assert model.generate.call_count == 1
        finally:
            release.set()
            outer_thread.join(timeout=1)
            for thread in threads:
                thread.join(timeout=1)
        assert outer_thread.is_alive() is False
        assert outer_errors == []

    def test_unload_preserves_resources_while_model_thread_is_alive(self):
        from XBrainLab.llm.core.backends.local import LocalBackend

        backend = LocalBackend(_make_config())
        (
            _model,
            release,
            started,
            threads,
            thread_factory,
            transformers,
        ) = _configure_blocking_generation(backend)
        loaded_model = backend.model
        loaded_tokenizer = backend.tokenizer
        outer_errors: list[BaseException] = []

        def consume_first_generation() -> None:
            try:
                list(
                    backend.generate_stream(
                        [{"role": "user", "content": "first"}],
                        options=CONFIGURED_TEST_OPTIONS,
                    )
                )
            except BaseException as error:
                outer_errors.append(error)

        outer_thread = Thread(target=consume_first_generation)

        try:
            with (
                patch.dict("sys.modules", {"transformers": transformers}),
                patch(
                    "XBrainLab.llm.core.backends.local.Thread",
                    side_effect=thread_factory,
                ),
            ):
                outer_thread.start()
                assert started.wait(timeout=1)

                assert backend.unload() is False

            assert backend.model is loaded_model
            assert backend.tokenizer is loaded_tokenizer
            assert backend.is_loaded is True
        finally:
            release.set()
            outer_thread.join(timeout=1)
            for thread in threads:
                thread.join(timeout=1)
        assert outer_thread.is_alive() is False
        assert outer_errors == []
