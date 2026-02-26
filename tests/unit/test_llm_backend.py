"""Coverage tests for remaining LLM and backend modules with high miss counts."""

from __future__ import annotations

from unittest.mock import MagicMock

# ============ Local Backend ============


class TestLocalBackend:
    def test_creates(self):
        from XBrainLab.llm.core.backends.local import LocalBackend

        config = MagicMock()
        config.model_name = "test-model"
        config.device = "cpu"
        config.cache_dir = "/tmp"
        config.load_in_4bit = False
        backend = LocalBackend(config)
        assert backend is not None
        assert backend.is_loaded is False

    def test_process_messages_empty(self):
        from XBrainLab.llm.core.backends.local import LocalBackend

        config = MagicMock()
        backend = LocalBackend(config)
        result = backend._process_messages_for_template([])
        assert result == []

    def test_process_messages_with_system(self):
        from XBrainLab.llm.core.backends.local import LocalBackend

        config = MagicMock()
        backend = LocalBackend(config)
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
        ]
        result = backend._process_messages_for_template(messages)
        assert len(result) >= 1


# ============ Downloader ============


class TestDownloader:
    def test_model_downloader_creates(self):
        from XBrainLab.llm.core.downloader import ModelDownloader

        dm = ModelDownloader()
        assert dm is not None

    def test_download_worker_creates(self):
        from XBrainLab.llm.core.downloader import DownloadWorker

        worker = DownloadWorker(repo_id="test/model", cache_dir="/tmp")
        assert worker is not None


# ============ RAG Retriever ============


class TestRetriever:
    def test_creates(self):
        from XBrainLab.llm.rag.retriever import RAGRetriever

        r = RAGRetriever()
        assert r is not None


# ============ Gemini Backend ============


class TestGeminiBackend:
    def test_creates(self):
        from XBrainLab.llm.core.backends.gemini import GeminiBackend

        config = MagicMock()
        config.api_key = "fake-key"  # pragma: allowlist secret
        backend = GeminiBackend(config)
        assert backend is not None


# ============ LLM Engine ============


class TestLLMEngine:
    def test_creates_no_config(self):
        from XBrainLab.llm.core.engine import LLMEngine

        e = LLMEngine()
        assert e is not None

    def test_creates_with_config(self):
        from XBrainLab.llm.core.engine import LLMEngine

        config = MagicMock()
        e = LLMEngine(config)
        assert e is not None


# ============ Agent Parser ============


class TestCommandParser:
    def test_parse_empty(self):
        from XBrainLab.llm.agent.parser import CommandParser

        result = CommandParser.parse("")
        assert result is None

    def test_parse_json_command(self):
        from XBrainLab.llm.agent.parser import CommandParser

        text = '{"tool_name": "load_data", "parameters": {"path": "test.fif"}}'
        result = CommandParser.parse(text)
        assert result is not None
        assert len(result) == 1
        assert result[0][0] == "load_data"

    def test_parse_plain_text(self):
        from XBrainLab.llm.agent.parser import CommandParser

        result = CommandParser.parse("Just a regular response with no actions")
        assert result is None
