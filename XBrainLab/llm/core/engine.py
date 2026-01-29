import logging
import os
from abc import ABC, abstractmethod
from threading import Thread
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer

try:
    from openai import OpenAI
except ImportError:
    OpenAI: Any = None  # type: ignore[no-redef]

try:
    from google import genai
except ImportError:
    genai: Any = None  # type: ignore[no-redef]

from .config import LLMConfig

logger = logging.getLogger("XBrainLab.LLM")


class BaseBackend(ABC):
    """Abstract base class for LLM backends."""

    @abstractmethod
    def load(self):
        """Initializes the backend resources."""

    @abstractmethod
    def generate_stream(self, messages: list):
        """Yields text chunks from the LLM."""


class LocalBackend(BaseBackend):
    """HuggingFace Transformers backend for local inference."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.model: Any = None
        self.tokenizer: Any = None
        self.is_loaded = False

    def load(self):
        if self.is_loaded:
            return

        logger.info(
            f"Loading local model: {self.config.model_name} on {self.config.device}"
        )
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.config.model_name, cache_dir=self.config.cache_dir
            )

            # Load model with optional quantization
            model_kwargs = {
                "device_map": self.config.device,
                "cache_dir": self.config.cache_dir,
                "trust_remote_code": True,
            }

            if self.config.load_in_4bit:
                # Requires bitsandbytes
                model_kwargs["load_in_4bit"] = True
            elif self.config.device == "cuda":
                model_kwargs["torch_dtype"] = torch.float16

            self.model = AutoModelForCausalLM.from_pretrained(
                self.config.model_name, **model_kwargs
            )

            self.is_loaded = True
            logger.info("Model loaded successfully.")

        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise e

    def _process_messages_for_template(self, messages: list) -> list:
        """Process messages for models with strict chat template requirements.

        Handles two issues for models like Gemma:
        1. No 'system' role support - merges into first user message
        2. Strict user/assistant alternation - merges consecutive same-role messages
        """
        if not messages:
            return messages

        # Step 1: Extract and remove system messages
        system_content = None
        filtered = []
        for msg in messages:
            if msg.get("role") == "system":
                system_content = msg.get("content", "")
            else:
                filtered.append(msg)

        # Step 2: Merge system into first user message
        if system_content:
            merged_system = False
            for i, msg in enumerate(filtered):
                if msg.get("role") == "user":
                    filtered[i] = {
                        "role": "user",
                        "content": (
                            f"[Instructions]\n{system_content}\n\n"
                            f"[Query]\n{msg.get('content', '')}"
                        ),
                    }
                    merged_system = True
                    break
            if not merged_system:
                filtered.insert(
                    0, {"role": "user", "content": f"[Instructions]\n{system_content}"}
                )

        # Step 3: Ensure strict user/assistant alternation
        # Merge consecutive messages with the same role
        if not filtered:
            return filtered

        result = [filtered[0]]
        for msg in filtered[1:]:
            if msg.get("role") == result[-1].get("role"):
                # Same role - merge content
                result[-1] = {
                    "role": msg.get("role"),
                    "content": (
                        f"{result[-1].get('content', '')}\n\n{msg.get('content', '')}"
                    ),
                }
            else:
                result.append(msg)

        return result

    def generate_stream(self, messages: list):
        if not self.is_loaded:
            self.load()
        if self.tokenizer is None or self.model is None:
            raise RuntimeError("Model/Tokenizer not loaded")

        # Handle models that don't support system role (e.g., Gemma)
        processed_messages = self._process_messages_for_template(messages)

        # Apply chat template
        prompt = self.tokenizer.apply_chat_template(
            processed_messages, tokenize=False, add_generation_prompt=True
        )

        if self.model is None:
            raise RuntimeError("Model did not load correctly")
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)

        streamer = TextIteratorStreamer(
            self.tokenizer, skip_prompt=True, skip_special_tokens=True
        )

        generation_kwargs = dict(
            inputs,
            streamer=streamer,
            max_new_tokens=self.config.max_new_tokens,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            do_sample=self.config.do_sample,
        )

        thread = Thread(target=self.model.generate, kwargs=generation_kwargs)
        thread.start()

        yield from streamer


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

        # Convert messages to Gemini SDK format if needed, OR relies on SDK's
        # auto-handling
        # The new SDK 'chats.create' creates a session.
        # We need to construct history from previous messages.

        history = []
        # messages format: [{'role': 'user', 'content': '...'}, ...]
        # google-genai format: usually similar or relies on 'parts'

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


class LLMEngine:
    """
    Core engine for handling LLM loading and inference.
    Acts as a Facade to LocalBackend or APIBackend.
    """

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()

        logger.info(f"Initializing LLMEngine in mode: {self.config.inference_mode}")

        if self.config.inference_mode == "api":
            self.backend = APIBackend(self.config)
        elif self.config.inference_mode == "gemini":
            self.backend = GeminiBackend(self.config)  # type: ignore[assignment]
        else:
            # Default to local
            self.backend = LocalBackend(self.config)  # type: ignore[assignment]

    def load_model(self):
        """Loads the model (or client) for the underlying backend."""
        self.backend.load()

    def generate_stream(self, messages: list):
        """Generates response in a streaming fashion."""
        yield from self.backend.generate_stream(messages)
