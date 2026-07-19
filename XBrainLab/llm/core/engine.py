"""Local-only LLM engine facade.

Provides the product assistant interface for loading and generating text with
the local HuggingFace backend. Legacy remote backend requests are migrated to
local and never instantiate remote clients.
"""

import contextlib
import logging
from typing import Any

from XBrainLab.llm.tools.result_contract import (
    redact_public_text,
    safe_unexpected_failure,
)

from .config import LLMConfig
from .generation import GenerationProfile, resolve_generation_options

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

    @staticmethod
    def _unload_backend(backend: Any) -> bool:
        """Return whether a backend released its generation-owned resources."""
        unload = getattr(backend, "unload", None)
        if not callable(unload):
            return True
        return unload() is not False

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
                "Ignoring legacy remote backend request %s; using local runtime.",
                redact_public_text(requested_mode),
            )
        logger.info("Switching backend to: %s", mode)

        stale_backend: Any | None = None
        stale_model_id = ""

        # 1. Check Cache and Validity (compare snapshots, not shared refs)
        if mode in self.backends:
            cached_id = self._backend_model_ids.get(mode, "")
            current_id = self._get_current_model_id(mode)
            is_stale = cached_id != current_id

            if is_stale:
                logger.info(
                    "Stale %s model (%s != %s). Reloading.",
                    mode,
                    redact_public_text(cached_id),
                    redact_public_text(current_id),
                )
            else:
                self.active_backend = self.backends[mode]
                logger.info("Switched to cached backend: %s", mode)
                return
            # Remove stale backend
            stale_backend = self.backends[mode]
            stale_model_id = cached_id
            if not self._unload_backend(stale_backend):
                raise RuntimeError(
                    "Cannot switch local models while generation is still running."
                )
            del self.backends[mode]
            self._backend_model_ids.pop(mode, None)
            if self.active_backend is stale_backend:
                self.active_backend = None

        # 2. Create if missing
        new_backend: Any = None

        from .backends.local import LocalBackend

        new_backend = LocalBackend(self.config)
        try:
            new_backend.load()
        except Exception as load_error:
            if callable(getattr(new_backend, "unload", None)):
                with contextlib.suppress(Exception):
                    self._unload_backend(new_backend)
            if stale_backend is not None and stale_model_id:
                try:
                    self.config.apply_runtime_selection(
                        "local",
                        model_id=stale_model_id,
                        ui_active_mode="local",
                    )
                    stale_backend.load()
                except Exception as rollback_error:
                    safe_unexpected_failure(
                        logger,
                        rollback_error,
                        boundary="llm_engine",
                        operation="restore_previous_model",
                    )
                    raise RuntimeError(
                        "Local model switch failed and the previous model could "
                        "not be restored.",
                    ) from load_error
                self.backends[mode] = stale_backend
                self._backend_model_ids[mode] = stale_model_id
                self.active_backend = stale_backend
            raise

        self.backends[mode] = new_backend
        self._backend_model_ids[mode] = self._get_current_model_id(mode)
        self.active_backend = new_backend
        logger.info("Created and switched to backend: %s", mode)

    def close(self) -> bool:
        """Unload cached backends, retaining any generation-owned backend."""
        retained_backends: dict[str, Any] = {}
        retained_model_ids: dict[str, str] = {}
        for mode, backend in list(self.backends.items()):
            try:
                unloaded = self._unload_backend(backend)
            except Exception as exc:
                safe_unexpected_failure(
                    logger,
                    exc,
                    boundary="llm_engine",
                    operation=f"unload_{mode}_backend",
                )
                unloaded = False
            if not unloaded:
                retained_backends[mode] = backend
                if mode in self._backend_model_ids:
                    retained_model_ids[mode] = self._backend_model_ids[mode]

        self.backends = retained_backends
        self._backend_model_ids = retained_model_ids
        if not any(
            self.active_backend is backend for backend in retained_backends.values()
        ):
            self.active_backend = None
        return not retained_backends

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
        """Cancel generation on the active backend when it supports it."""
        backend = self.active_backend
        cancel = getattr(backend, "cancel_generation", None)
        if not callable(cancel):
            return True
        return bool(cancel(wait_timeout=wait_timeout))
