"""HuggingFace Transformers local inference backend.

Implements the ``BaseBackend`` interface for on-device inference using
HuggingFace ``transformers`` with optional 4-bit quantization.
"""

import gc
import logging
from threading import Thread
from typing import Any, TypedDict, cast

from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.model_catalog import local_model_policy_error, local_model_spec

from .base import BaseBackend

logger = logging.getLogger("XBrainLab.LLM.Local")


class LocalBackend(BaseBackend):
    """HuggingFace Transformers backend for local inference.

    Loads a causal language model with optional 4-bit quantization and
    streams generated text using ``TextIteratorStreamer``.

    Attributes:
        config: The ``LLMConfig`` instance with model name and generation
            parameters.
        model: The loaded ``AutoModelForCausalLM`` instance (``None``
            until ``load`` is called).
        tokenizer: The loaded ``AutoTokenizer`` instance.
        is_loaded: Whether the model has been successfully loaded.

    """

    def __init__(self, config: LLMConfig):
        """Initializes the LocalBackend.

        Args:
            config: LLM configuration containing model name, device,
                quantization, and generation settings.

        """
        self.config = config
        self.model: Any = None
        self.tokenizer: Any = None
        self.is_loaded = False

    def _normalize_runtime_device(self, torch_module) -> None:
        """Fallback from unusable CUDA setups to CPU before model load."""
        device = str(getattr(self.config, "device", "cpu"))
        if not device.startswith("cuda"):
            return

        reason = None
        if not torch_module.cuda.is_available():
            reason = "CUDA is not available"
        else:
            try:
                probe = torch_module.zeros(1, device=device)
                del probe
            except Exception as exc:  # pragma: no cover - hardware/runtime specific
                reason = str(exc)
            else:
                return

        logger.warning(
            "Configured local LLM device %s is not usable; falling back to CPU: %s",
            device,
            reason,
        )
        self.config.device = "cpu"
        if getattr(self.config, "load_in_4bit", False):
            logger.warning(
                "Disabling 4-bit loading because local LLM is falling back to CPU.",
            )
            self.config.load_in_4bit = False

    def _patch_remote_code_compat(self) -> None:
        """Patch narrow Transformers compatibility gaps in trusted model code.

        Phi-4-mini's remote modeling file imports ``LossKwargs`` from
        ``transformers.utils``. Some supported Transformers builds no longer
        export that TypedDict there. It is only used for runtime annotations, so
        providing the missing TypedDict avoids a startup failure without
        changing generation behavior.
        """
        if "Phi-" not in str(self.config.model_name):
            return

        try:
            import transformers.utils as transformers_utils
        except ModuleNotFoundError:
            return

        if not hasattr(transformers_utils, "LossKwargs"):

            class LossKwargs(TypedDict, total=False):
                labels: Any

            cast(Any, transformers_utils).LossKwargs = LossKwargs

        try:
            from transformers.cache_utils import DynamicCache
        except ModuleNotFoundError:
            return

        if not hasattr(DynamicCache, "seen_tokens"):
            DynamicCache.seen_tokens = property(  # type: ignore[attr-defined]
                lambda cache: cache.get_seq_length()
            )
        if not hasattr(DynamicCache, "get_max_length"):
            DynamicCache.get_max_length = lambda cache: None  # type: ignore[attr-defined]
        if not hasattr(DynamicCache, "get_usable_length"):

            def get_usable_length(  # type: ignore[no-untyped-def]
                cache,
                new_seq_length,
                layer_idx=0,
            ):
                previous_seq_length = cache.get_seq_length(layer_idx)
                max_length = cache.get_max_length()
                if (
                    max_length is not None
                    and previous_seq_length + new_seq_length > max_length
                ):
                    return max_length - new_seq_length
                return previous_seq_length

            DynamicCache.get_usable_length = get_usable_length  # type: ignore[attr-defined]

    def load(self):
        """Downloads (if necessary) and loads the model and tokenizer.

        Uses 4-bit quantization when ``config.load_in_4bit`` is enabled,
        otherwise falls back to float16 on CUDA or full precision on CPU.

        Raises:
            Exception: If model loading fails for any reason.

        """
        if self.is_loaded:
            return

        policy_error = local_model_policy_error(self.config.model_name)
        if policy_error is not None:
            raise RuntimeError(policy_error)

        import torch
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
        )

        self._normalize_runtime_device(torch)

        logger.info(
            "Loading local model: %s on %s",
            self.config.model_name,
            self.config.device,
        )
        try:
            self._patch_remote_code_compat()
            spec = local_model_spec(self.config.model_name)
            trust_remote_code = bool(
                getattr(
                    self.config,
                    "trust_remote_code",
                    spec.trust_remote_code if spec else False,
                )
            )
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.config.model_name,
                cache_dir=self.config.cache_dir,
                trust_remote_code=trust_remote_code,
            )

            # Load model with optional quantization
            model_kwargs = {
                "cache_dir": self.config.cache_dir,
                "trust_remote_code": trust_remote_code,
            }
            if spec and spec.attn_implementation:
                model_kwargs["attn_implementation"] = spec.attn_implementation

            if self.config.load_in_4bit:
                model_kwargs["device_map"] = "auto"
                model_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                )
            elif self.config.device == "cuda":
                model_kwargs["dtype"] = cast(Any, torch).float16

            self.model = AutoModelForCausalLM.from_pretrained(
                self.config.model_name,
                **model_kwargs,
            )
            if (
                not self.config.load_in_4bit
                and str(self.config.device).startswith("cuda")
                and hasattr(self.model, "to")
            ):
                self.model = self.model.to(self.config.device)

            self.is_loaded = True
            logger.info("Model loaded successfully.")

        except Exception as e:
            logger.error("Failed to load model: %s", e)
            raise

    def unload(self) -> None:
        """Release loaded model resources and clear CUDA cache when available."""
        self.model = None
        self.tokenizer = None
        self.is_loaded = False
        gc.collect()

        try:
            import torch
        except ModuleNotFoundError:
            return

        cuda = getattr(torch, "cuda", None)
        if cuda is None:
            return
        try:
            if cuda.is_available():
                cuda.empty_cache()
        except Exception:  # pragma: no cover - defensive cleanup path
            logger.debug("CUDA cache cleanup failed during local model unload.")

    def _process_messages_for_template(self, messages: list) -> list:
        """Processes messages for models with strict chat template rules.

        Handles two common issues:

        1. **No system role support** — merges system messages into the
           first user message.
        2. **Strict user/assistant alternation** — merges consecutive
           same-role messages.

        Args:
            messages: List of message dicts with ``role`` and ``content``.

        Returns:
            A new message list with system content merged and strict
            alternation enforced.

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
                    0,
                    {"role": "user", "content": f"[Instructions]\n{system_content}"},
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
        """Streams generated text from the local model.

        Applies the tokenizer's chat template, spawns a generation
        thread, and yields text chunks via ``TextIteratorStreamer``.

        Args:
            messages: List of message dicts with ``role`` and ``content``.

        Yields:
            Text chunks produced by the model.

        Raises:
            RuntimeError: If the model or tokenizer is not loaded.

        """
        if not self.is_loaded:
            self.load()
        if self.tokenizer is None or self.model is None:
            raise RuntimeError("Model/Tokenizer not loaded")

        from transformers import TextIteratorStreamer

        # Handle models that don't support system role (e.g., Gemma)
        processed_messages = self._process_messages_for_template(messages)

        # Apply chat template
        prompt = self.tokenizer.apply_chat_template(
            processed_messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        if self.model is None:
            raise RuntimeError("Model did not load correctly")
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)

        streamer = TextIteratorStreamer(
            self.tokenizer,
            skip_prompt=True,
            skip_special_tokens=True,
        )

        generation_kwargs = dict(
            inputs,
            streamer=streamer,
            max_new_tokens=self.config.max_new_tokens,
            do_sample=self.config.do_sample,
        )
        if self.config.do_sample:
            generation_kwargs["temperature"] = self.config.temperature
            generation_kwargs["top_p"] = self.config.top_p

        errors: list[BaseException] = []

        def _generate() -> None:
            try:
                self.model.generate(**generation_kwargs)
            except BaseException as exc:  # pragma: no cover - exercised by runtime
                logger.error("Local generation failed: %s", exc, exc_info=True)
                errors.append(exc)
                if hasattr(streamer, "end"):
                    streamer.end()

        thread = Thread(target=_generate)
        thread.start()

        yield from streamer
        thread.join(timeout=0)
        if errors:
            raise RuntimeError(f"Local generation failed: {errors[0]}")
