"""Tests for LocalBackend (HuggingFace Transformers local inference)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from XBrainLab.llm.core.config import LLMConfig


def _make_config(**overrides):
    defaults = {
        "model_name": "test-model",
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
        mock_model_cls = MagicMock(return_value=mock_tokenizer)
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
