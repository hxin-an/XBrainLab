import logging
from threading import Thread
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from XBrainLab.llm.core.config import LLMConfig

from .base import BaseBackend

logger = logging.getLogger("XBrainLab.LLM.Local")


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

        import torch  # noqa: PLC0415
        from transformers import (  # noqa: PLC0415
            AutoModelForCausalLM,
            AutoTokenizer,
        )

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

        from transformers import TextIteratorStreamer  # noqa: PLC0415

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
