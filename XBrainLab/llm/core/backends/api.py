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
    """OpenAI-compatible API backend."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.client = None

    def load(self):
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
            f"Initialized APIBackend with URL: {base_url} "
            f"Model: {self.config.api_model_name}"
        )

    def generate_stream(self, messages: list):
        if not self.client:
            self.load()

        try:
            stream = self.client.chat.completions.create(  # type: ignore[attr-defined]
                model=self.config.api_model_name,
                messages=messages,
                stream=True,
                temperature=self.config.temperature,
                top_p=self.config.top_p,
                max_tokens=self.config.max_new_tokens,
            )

            for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except Exception as e:
            logger.error(f"API Generation Error: {e}")
            yield f"[Error: {e}]"
