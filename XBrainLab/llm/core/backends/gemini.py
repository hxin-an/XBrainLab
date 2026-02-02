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
    """Google Gemini API backend using google-genai SDK."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.client: Any = None

    def load(self):
        if not genai:
            raise ImportError(
                "google-genai package is missing. Run `poetry add google-genai`."
            )

        api_key = self.config.gemini_api_key
        if not api_key:
            api_key = os.getenv("GEMINI_API_KEY")  # type: ignore[assignment]

        if not api_key:
            logger.warning("No Gemini API KEY provided.")

        # New SDK Initialization
        self.client = genai.Client(api_key=api_key)
        logger.info(
            f"Initialized GeminiBackend (v2 SDK) with Model: "
            f"{self.config.gemini_model_name}"
        )

    def generate_stream(self, messages: list):
        if not self.client:
            self.load()

        # Convert messages to Gemini SDK format
        history = []
        for msg in messages[:-1]:
            role = "user" if msg["role"] == "user" else "model"
            history.append({"role": role, "parts": [{"text": msg["content"]}]})

        last_user_msg = messages[-1]["content"]

        try:
            # Create a fresh chat session with history
            chat = self.client.chats.create(
                model=self.config.gemini_model_name, history=history
            )

            # Streaming send
            response_stream = chat.send_message_stream(last_user_msg)

            for chunk in response_stream:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error(f"Gemini Error: {e}")
            yield f"[Error: {e}]"
