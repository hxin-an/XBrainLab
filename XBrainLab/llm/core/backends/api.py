"""OpenAI-compatible API backend.

Implements the ``BaseBackend`` interface for remote inference via any
OpenAI-compatible chat completions API.
"""

import logging
import os
from typing import Any

from XBrainLab.llm.core.config import LLMConfig

from .base import BaseBackend

try:
    from openai import OpenAI
except ImportError:
    OpenAI: Any = None  # type: ignore[no-redef]

logger = logging.getLogger("XBrainLab.LLM.API")


class APIBackend(BaseBackend):
    """OpenAI-compatible API backend.

    Connects to any OpenAI-compatible endpoint using the ``openai``
    Python package and streams chat completion responses.

    Attributes:
        config: The ``LLMConfig`` instance providing API credentials and
            model settings.
        client: The ``OpenAI`` client instance (``None`` until ``load``
            is called).

    """

    def __init__(self, config: LLMConfig):
        """Initializes the APIBackend.

        Args:
            config: LLM configuration containing API key, base URL,
                and model name.

        """
        self.config = config
        self.client = None

    def load(self):
        """Initializes the OpenAI client.

        Reads API key from config or falls back to the
        ``OPENAI_API_KEY`` environment variable.

        Raises:
            ImportError: If the ``openai`` package is not installed.

        """
        if OpenAI is None:
            raise ImportError("OpenAI package is missing. Run `poetry add openai`.")

        api_key = self.config.api_key
        base_url = self.config.base_url

        # Validation
        if not api_key:
            # Fallback
            api_key = os.getenv("OPENAI_API_KEY")  # type: ignore[assignment]

        if not api_key:
            logger.warning("No API KEY provided for APIBackend. Inference may fail.")

        self.client = OpenAI(api_key=api_key, base_url=base_url)  # type: ignore[assignment]
        logger.info(
            "Initialized APIBackend with URL: %s Model: %s",
            base_url,
            self.config.api_model_name,
        )

    def generate_stream(self, messages: list):
        """Streams chat completion responses from the API.

        Automatically calls ``load`` if the client has not been
        initialized.

        Args:
            messages: List of message dicts with ``role`` and ``content``.

        Yields:
            Text chunks from the streaming API response.

        """
        if not self.client:
            self.load()

        stream = self.client.chat.completions.create(  # type: ignore[attr-defined]
            model=self.config.api_model_name,
            messages=messages,
            stream=True,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            max_tokens=self.config.max_new_tokens,
        )

        for chunk in stream:
            if not chunk.choices:
                continue
            content = chunk.choices[0].delta.content
            if content:
                yield content
