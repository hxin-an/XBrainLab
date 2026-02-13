import logging
from typing import Any

from .config import LLMConfig

logger = logging.getLogger("XBrainLab.LLM")


class LLMEngine:
    """
    Core engine for handling LLM loading and inference.
    Acts as a Facade to LocalBackend or APIBackend.
    """

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()
        self.backends: dict[str, Any] = {}  # Cache for backends
        self.active_backend: Any | None = None

        logger.info(
            f"Initializing LLMEngine with default mode: {self.config.inference_mode}"
        )

    def load_model(self):
        """Loads the model (or client) for the underlying backend."""
        self.switch_backend(self.config.inference_mode)

    def switch_backend(self, mode: str):
        """Switch active backend, creating it if necessary."""
        logger.info(f"Switching backend to: {mode}")

        # 1. Check Cache and Validity
        if mode in self.backends:
            backend = self.backends[mode]

            # Check for Stale Model (Is the loaded model same as requested?)
            is_stale = False
            if mode == "local":
                # LocalBackend has .config.model_name.
                # We compare it with the *current* self.config.model_name
                if backend.config.model_name != self.config.model_name:
                    logger.info(
                        f"Stale local model ({backend.config.model_name} != "
                        f"{self.config.model_name}). Reloading."
                    )
                    is_stale = True

            elif (
                mode == "gemini"
                and backend.config.gemini_model_name != self.config.gemini_model_name
            ):
                logger.info("Stale Gemini model detected. Reloading.")
                is_stale = True

            if not is_stale:
                self.active_backend = backend
                logger.info(f"Switched to cached backend: {mode}")
                return
            else:
                # Remove stale backend
                del self.backends[mode]

        # 2. Create if missing
        new_backend: Any = None

        if mode == "api":
            from .backends.api import APIBackend

            new_backend = APIBackend(self.config)
        elif mode == "gemini":
            from .backends.gemini import GeminiBackend

            new_backend = GeminiBackend(self.config)
        else:
            # Default to local
            from .backends.local import LocalBackend

            new_backend = LocalBackend(self.config)
            # Local needs explicit load (others might be lazy or fast)
            new_backend.load()

        self.backends[mode] = new_backend
        self.active_backend = new_backend
        logger.info(f"Created and switched to backend: {mode}")

    def generate_stream(self, messages: list):
        """Generates response in a streaming fashion."""
        if not self.active_backend:
            raise RuntimeError("No active backend loaded")
        yield from self.active_backend.generate_stream(messages)
