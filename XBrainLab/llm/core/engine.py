import logging

from .config import LLMConfig

logger = logging.getLogger("XBrainLab.LLM")


class LLMEngine:
    """
    Core engine for handling LLM loading and inference.
    Acts as a Facade to LocalBackend or APIBackend.
    """

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()

        logger.info(f"Initializing LLMEngine in mode: {self.config.inference_mode}")

        if self.config.inference_mode == "api":
            from .backends.api import APIBackend  # noqa: PLC0415

            self.backend = APIBackend(self.config)
        elif self.config.inference_mode == "gemini":
            from .backends.gemini import GeminiBackend  # noqa: PLC0415

            self.backend = GeminiBackend(self.config)  # type: ignore[assignment]
        else:
            # Default to local
            from .backends.local import LocalBackend  # noqa: PLC0415

            self.backend = LocalBackend(self.config)  # type: ignore[assignment]

    def load_model(self):
        """Loads the model (or client) for the underlying backend."""
        self.backend.load()

    def generate_stream(self, messages: list):
        """Generates response in a streaming fashion."""
        yield from self.backend.generate_stream(messages)
