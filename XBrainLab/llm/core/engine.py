"""Local-only LLM engine facade.

Provides the product assistant interface for loading and generating text with
the local HuggingFace backend. Legacy remote backend requests are migrated to
local and never instantiate remote clients.
"""

import logging
from typing import Any

from .config import LLMConfig

logger = logging.getLogger("XBrainLab.LLM")


class LLMEngine:
    """Core engine for handling LLM loading and inference.

    Acts as a facade over ``LocalBackend``, lazily instantiating and caching
    it as needed. Stale backends are automatically replaced when the configured
    local model changes.

    Attributes:
        config: The active ``LLMConfig`` instance.
        backends: Cache mapping mode names to instantiated backend objects.
        active_backend: The currently selected backend (or ``None``).

    """

    def __init__(self, config: LLMConfig | None = None):
        """Initializes the LLMEngine.

        Args:
            config: Optional ``LLMConfig`` instance.  If ``None``, a
                default configuration is created.

        """
        self.config = config or LLMConfig()
        self.backends: dict[str, Any] = {}  # Cache for backends
        self._backend_model_ids: dict[str, str] = {}  # snapshot at cache time
        self.active_backend: Any | None = None

        logger.info(
            "Initializing local-only LLMEngine with requested mode: %s",
            self.config.inference_mode,
        )

    def load_model(self):
        """Load the product local model."""
        self.switch_backend(self.config.runtime_backend_mode_key())

    def _get_current_model_id(self, mode: str) -> str:
        """Return the model identifier for the given backend mode."""
        _ = mode
        return self.config.model_name

    def switch_backend(self, mode: str):
        """Switches the active backend, creating it if necessary.

        If a cached backend exists for the requested mode but its model
        configuration is stale, the backend is recreated.

        Args:
            mode: Requested backend mode. Any legacy remote value is migrated
                to ``'local'`` before backend creation.

        """
        requested_mode = str(mode or "local")
        mode = LLMConfig.normalize_backend_mode(requested_mode)
        if requested_mode.strip().lower() != "local":
            logger.warning(
                "Ignoring legacy remote backend request %r; using local runtime.",
                requested_mode,
            )
        logger.info("Switching backend to: %s", mode)

        # 1. Check Cache and Validity (compare snapshots, not shared refs)
        if mode in self.backends:
            cached_id = self._backend_model_ids.get(mode, "")
            current_id = self._get_current_model_id(mode)
            is_stale = cached_id != current_id

            if is_stale:
                logger.info(
                    "Stale %s model (%s != %s). Reloading.",
                    mode,
                    cached_id,
                    current_id,
                )
            else:
                self.active_backend = self.backends[mode]
                logger.info("Switched to cached backend: %s", mode)
                return
            # Remove stale backend
            del self.backends[mode]

        # 2. Create if missing
        new_backend: Any = None

        from .backends.local import LocalBackend

        new_backend = LocalBackend(self.config)
        new_backend.load()

        self.backends[mode] = new_backend
        self._backend_model_ids[mode] = self._get_current_model_id(mode)
        self.active_backend = new_backend
        logger.info("Created and switched to backend: %s", mode)

    def generate_stream(self, messages: list):
        """Generates a response in a streaming fashion.

        Args:
            messages: List of message dicts with ``role`` and ``content``
                keys.

        Yields:
            Text chunks from the active backend.

        Raises:
            RuntimeError: If no active backend is loaded.

        """
        if not self.active_backend:
            raise RuntimeError("No active backend loaded")
        yield from self.active_backend.generate_stream(messages)
