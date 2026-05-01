"""Tests for LocalBackend (HuggingFace Transformers local inference)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.llm.core.config import LLMConfig


def _make_config(**overrides):
    defaults = {
        "model_name": "microsoft/Phi-4-mini-instruct",
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

        with patch.dict(
            "sys.modules",
            {
                "torch": mock_torch,
                "transformers": MagicMock(
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
        assert backend.tokenizer is not None
        assert backend.model is not None

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

    def test_phi_remote_code_compat_adds_loss_kwargs(self):
        import transformers.utils as transformers_utils

        from XBrainLab.llm.core.backends.local import LocalBackend

        cfg = _make_config(model_name="microsoft/Phi-4-mini-instruct")
        backend = LocalBackend(cfg)
        previous = getattr(transformers_utils, "LossKwargs", None)
        had_previous = hasattr(transformers_utils, "LossKwargs")

        if had_previous:
            delattr(transformers_utils, "LossKwargs")
        try:
            backend._patch_remote_code_compat()
            assert hasattr(transformers_utils, "LossKwargs")
        finally:
            if had_previous:
                transformers_utils.LossKwargs = previous
            elif hasattr(transformers_utils, "LossKwargs"):
                delattr(transformers_utils, "LossKwargs")

    def test_phi_remote_code_compat_adds_dynamic_cache_seen_tokens(self):
        from transformers.cache_utils import DynamicCache

        from XBrainLab.llm.core.backends.local import LocalBackend

        cfg = _make_config(model_name="microsoft/Phi-3.5-mini-instruct")
        backend = LocalBackend(cfg)
        previous_seen = getattr(DynamicCache, "seen_tokens", None)
        previous_max = getattr(DynamicCache, "get_max_length", None)
        previous_usable = getattr(DynamicCache, "get_usable_length", None)
        had_seen = hasattr(DynamicCache, "seen_tokens")
        had_max = hasattr(DynamicCache, "get_max_length")
        had_usable = hasattr(DynamicCache, "get_usable_length")

        if had_seen:
            delattr(DynamicCache, "seen_tokens")
        if had_max:
            delattr(DynamicCache, "get_max_length")
        if had_usable:
            delattr(DynamicCache, "get_usable_length")
        try:
            backend._patch_remote_code_compat()
            assert hasattr(DynamicCache, "seen_tokens")
            assert hasattr(DynamicCache, "get_max_length")
            assert hasattr(DynamicCache, "get_usable_length")
            assert DynamicCache().seen_tokens == 0
            assert DynamicCache().get_max_length() is None
            assert DynamicCache().get_usable_length(1) == 0
        finally:
            if had_seen:
                DynamicCache.seen_tokens = previous_seen
            elif hasattr(DynamicCache, "seen_tokens"):
                delattr(DynamicCache, "seen_tokens")
            if had_max:
                DynamicCache.get_max_length = previous_max
            elif hasattr(DynamicCache, "get_max_length"):
                delattr(DynamicCache, "get_max_length")
            if had_usable:
                DynamicCache.get_usable_length = previous_usable
            elif hasattr(DynamicCache, "get_usable_length"):
                delattr(DynamicCache, "get_usable_length")


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

    def test_system_merged_into_user(self):
        backend = self._get_backend()
        msgs = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "hello"},
        ]
        result = backend._process_messages_for_template(msgs)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert "You are helpful" in result[0]["content"]
        assert "hello" in result[0]["content"]

    def test_system_only_no_user(self):
        backend = self._get_backend()
        msgs = [{"role": "system", "content": "instructions"}]
        result = backend._process_messages_for_template(msgs)
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert "instructions" in result[0]["content"]

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
            list(backend.generate_stream([{"role": "user", "content": "hi"}]))

    def test_generate_stream_calls_load(self):
        """generate_stream calls load() if not loaded."""
        from XBrainLab.llm.core.backends.local import LocalBackend

        cfg = _make_config()
        backend = LocalBackend(cfg)

        with (
            patch.object(backend, "load", side_effect=RuntimeError("skip")),
            pytest.raises(RuntimeError, match="skip"),
        ):
            list(backend.generate_stream([{"role": "user", "content": "hi"}]))

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
            result = list(backend.generate_stream([{"role": "user", "content": "hi"}]))
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
            def __init__(self, target):
                self.target = target

            def start(self):
                self.target()

            def join(self, timeout=0):
                return None

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
            list(backend.generate_stream([{"role": "user", "content": "hi"}]))

        mock_streamer.end.assert_called_once()
