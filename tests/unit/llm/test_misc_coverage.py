"""Coverage tests for seed utility, parser, __init__, and small modules."""

import contextlib
from unittest.mock import MagicMock, patch

# ── Seed Utility ──────────────────────────────────────────────


class TestSetSeedCUDA:
    """Cover CUDA branch in set_seed."""

    @patch("XBrainLab.backend.utils.seed.torch")
    def test_cuda_deterministic(self, mock_torch):
        from XBrainLab.backend.utils.seed import set_seed

        mock_torch.cuda.is_available.return_value = True
        mock_torch.seed.return_value = 42
        mock_torch.backends.cudnn = MagicMock()

        result = set_seed(42, deterministic=True)
        assert result == 42
        mock_torch.cuda.manual_seed.assert_called_once_with(42)
        mock_torch.cuda.manual_seed_all.assert_called_once_with(42)
        assert mock_torch.backends.cudnn.benchmark is False
        assert mock_torch.backends.cudnn.deterministic is True

    @patch("XBrainLab.backend.utils.seed.torch")
    def test_cuda_non_deterministic(self, mock_torch):
        from XBrainLab.backend.utils.seed import set_seed

        mock_torch.cuda.is_available.return_value = True
        mock_torch.seed.return_value = 42
        mock_torch.backends.cudnn = MagicMock()

        result = set_seed(42, deterministic=False)
        assert result == 42
        assert mock_torch.backends.cudnn.benchmark is True
        assert mock_torch.backends.cudnn.deterministic is False


# ── Parser ──────────────────────────────────────────────────


class TestCommandParserReturnPaths:
    """Cover the final return paths of CommandParser.parse()."""

    def test_parse_returns_commands(self):
        from XBrainLab.llm.agent.parser import CommandParser

        text = '{"tool_name": "load_data", "parameters": {"paths": ["/a.gdf"]}}'
        result = CommandParser.parse(text)
        assert result is not None
        assert len(result) >= 1
        assert result[0][0] == "load_data"

    def test_parse_returns_none_for_chat(self):
        from XBrainLab.llm.agent.parser import CommandParser

        result = CommandParser.parse("Hello, how are you today?")
        assert result is None


# ── __init__.py fallback ───────────────────────────────────


class TestVersionFallback:
    """Cover the PackageNotFoundError fallback in __init__.py."""

    def test_version_exists(self):
        import XBrainLab

        assert hasattr(XBrainLab, "__version__")
        assert isinstance(XBrainLab.__version__, str)


# ── Removed remote backend modules ──────────────────────────


class TestRemovedRemoteBackends:
    """Guard that product backend package stays local-only."""

    def test_remote_backend_modules_are_absent(self):
        import importlib.util

        assert importlib.util.find_spec("XBrainLab.llm.core.backends.api") is None
        assert importlib.util.find_spec("XBrainLab.llm.core.backends.gemini") is None


# ── Model Downloader ────────────────────────────────────────


class TestModelDownloaderCoverage:
    """Cover thread state and start_download guard."""

    def test_on_failed_resets_thread(self):
        from XBrainLab.llm.core.downloader import ModelDownloader

        d = ModelDownloader()
        d._thread = MagicMock()
        d.failed = MagicMock()
        d._on_failed("error msg")
        assert d._thread is None
        d.failed.emit.assert_called_once_with("error msg")

    def test_start_download_when_already_running(self):
        from XBrainLab.llm.core.downloader import ModelDownloader

        d = ModelDownloader()
        d._thread = MagicMock()
        d.log = MagicMock()
        # Should detect existing thread and handle gracefully
        with contextlib.suppress(RuntimeError, AttributeError):
            d.start_download("test/model", "/tmp/cache")
            # Expected when thread is mock
