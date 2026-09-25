"""Local-only LLM engine facade.

Owns one local HuggingFace backend for loading and generating text. Product
model changes replace the surrounding runtime process, not an in-engine cache.
"""

import logging
from collections.abc import Callable
from typing import Any

from XBrainLab.llm.tools.result_contract import safe_unexpected_failure

from .config import LLMConfig
from .generation import GenerationProfile, resolve_generation_options

logger = logging.getLogger("XBrainLab.LLM")


class LLMEngine:
    """Core engine for handling LLM loading and inference.

    Lazily creates one ``LocalBackend``. Physical ownership survives failed
    cleanup independently of readiness to generate.

    Attributes:
        config: The active ``LLMConfig`` instance.
        active_backend: The ready backend, or ``None`` before load/after close.

    """

    def __init__(
        self,
        config: LLMConfig | None = None,
        *,
        backend_factory: Callable[[LLMConfig], Any] | None = None,
    ):
        """Initializes the LLMEngine.

        Args:
            config: Optional ``LLMConfig`` instance.  If ``None``, a
                default configuration is created.

        """
        self.config = config or LLMConfig()
        self._backend_factory = backend_factory
        self._backend: Any | None = None
        self.active_backend: Any | None = None

        logger.info(
            "Initializing local-only LLMEngine with requested mode: %s",
            self.config.inference_mode,
        )

    def load_model(self):
        """Load once; an incompletely released backend must be closed first."""
        if self.active_backend is not None:
            return
        if self._backend is not None:
            raise RuntimeError(
                "Local backend cleanup is incomplete; retry close first."
            )

        from .backends.local import LocalBackend

        backend = (self._backend_factory or LocalBackend)(self.config)
        self._backend = backend
        try:
            backend.load()
        except Exception:
            self.close()
            raise
        self.active_backend = backend
        logger.info("Local backend loaded.")

    def close(self) -> bool:
        """Retire readiness, retaining the exact backend until unload succeeds."""
        self.active_backend = None
        backend = self._backend
        if backend is None:
            return True
        try:
            if backend.unload() is False:
                return False
        except Exception as exc:
            safe_unexpected_failure(
                logger,
                exc,
                boundary="llm_engine",
                operation="unload_local_backend",
            )
            return False
        self._backend = None
        return True

    def generate_stream(
        self,
        messages: list,
        *,
        profile: GenerationProfile,
    ):
        """Generates a response in a streaming fashion.

        Args:
            messages: List of message dicts with ``role`` and ``content``
                keys.
            profile: Decoding behavior selected by the response contract.

        Yields:
            Text chunks from the active backend.

        Raises:
            RuntimeError: If no active backend is loaded.

        """
        if not self.active_backend:
            raise RuntimeError("No active backend loaded")
        options = resolve_generation_options(
            profile=profile,
            max_new_tokens=self.config.max_new_tokens,
            do_sample=self.config.do_sample,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
        )
        yield from self.active_backend.generate_stream(messages, options=options)

    def cancel_generation(self, wait_timeout: float = 0.25) -> bool:
        """Cancel generation even when failed cleanup has retired readiness."""
        backend = self._backend
        if backend is None:
            return True
        return bool(backend.cancel_generation(wait_timeout=wait_timeout))
