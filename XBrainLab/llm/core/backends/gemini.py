"""Google Gemini API backend.

Implements the ``BaseBackend`` interface using the ``google-genai`` SDK
for streaming chat generation via Google's Gemini models.
"""

import logging
import os
from typing import Any

from XBrainLab.llm.core.config import LLMConfig

from .base import BaseBackend

try:
    from google import genai
except ImportError:
    genai: Any = None  # type: ignore[no-redef]

logger = logging.getLogger("XBrainLab.LLM.Gemini")


class GeminiBackend(BaseBackend):
    """Google Gemini API backend using the ``google-genai`` SDK.

    Attributes:
        config: The ``LLMConfig`` instance providing Gemini API key and
            model settings.
        client: The ``genai.Client`` instance (``None`` until ``load``
            is called).

    """

    def __init__(self, config: LLMConfig):
        """Initializes the GeminiBackend.

        Args:
            config: LLM configuration containing Gemini API key and
                model name.

        """
        self.config = config
        self.client: Any = None

    def load(self):
        """Initializes the Gemini client.

        Reads the API key from config or falls back to the
        ``GEMINI_API_KEY`` environment variable.

        Raises:
            ImportError: If the ``google-genai`` package is not installed.

        """
        if not genai:
            raise ImportError(
                "google-genai package is missing. Run `poetry add google-genai`.",
            )

        api_key = self.config.gemini_api_key
        if not api_key:
            api_key = os.getenv("GEMINI_API_KEY")  # type: ignore[assignment]

        if not api_key:
            logger.warning("No Gemini API KEY provided.")

        # New SDK Initialization
        self.client = genai.Client(api_key=api_key)
        logger.info(
            "Initialized GeminiBackend (v2 SDK) with Model: %s",
            self.config.gemini_model_name,
        )

    def generate_stream(self, messages: list):
        """Streams chat responses from the Gemini API.

        Converts the standard message list into Gemini SDK format,
        creates a chat session with history, and streams the response.

        Args:
            messages: List of message dicts with ``role`` and ``content``.

        Yields:
            Text chunks from the streaming Gemini response.

        """
        if not self.client:
            self.load()

        # Find the last user message (may not always be messages[-1])
        last_user_msg = ""
        remaining_history_end = len(messages)
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]["role"] == "user":
                last_user_msg = messages[i]["content"]
                remaining_history_end = i
                break

        # Convert messages to Gemini SDK format
        # Extract system messages and merge into system_instruction
        system_parts = []
        history = []
        for msg in messages[:remaining_history_end]:
            if msg["role"] == "system":
                system_parts.append(msg["content"])
            else:
                role = "user" if msg["role"] == "user" else "model"
                history.append({"role": role, "parts": [{"text": msg["content"]}]})

        # Build config with system instruction if present
        chat_kwargs = {
            "model": str(self.config.gemini_model_name),
            "history": history,
        }
        if system_parts:
            chat_kwargs["config"] = {"system_instruction": "\n".join(system_parts)}  # type: ignore[assignment]

        # Create a fresh chat session with history
        chat = self.client.chats.create(**chat_kwargs)

        # Guard against empty user messages
        if not last_user_msg:
            yield "I need a question to respond to."
            return

        # Streaming send
        response_stream = chat.send_message_stream(last_user_msg)

        for chunk in response_stream:
            if chunk.text:
                yield chunk.text
