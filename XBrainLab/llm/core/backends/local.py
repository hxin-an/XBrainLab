"""HuggingFace Transformers local inference backend.

Implements the ``BaseBackend`` interface for on-device inference using
HuggingFace ``transformers`` with optional 4-bit quantization.
"""

import gc
import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any, cast
from uuid import uuid4

from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.application.resource_guard import (
    check_model_load_resource_preflight,
    enforce_model_load_resource_preflight,
    is_cuda_oom_error,
    release_cuda_cache,
)
from XBrainLab.chat_contract import (
    LOCAL_MODEL_INPUT_TOO_LONG_MESSAGE,
    MODEL_UNTRUSTED_CONTEXT_BOUNDARY_MESSAGE,
)
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.generation import ResolvedGenerationOptions
from XBrainLab.llm.core.model_catalog import (
    BYTES_PER_GB,
    local_model_policy_error,
    local_model_spec,
)

from .base import BaseBackend

logger = logging.getLogger("XBrainLab.LLM.Local")

_PROMPT_CAPTURE_DIRECTORY_ENV = "XBRAINLAB_ASSISTANT_PROMPT_CAPTURE_DIR"


@dataclass(slots=True)
class _GenerationLease:
    """Own one model generation until its native generation thread exits."""

    cancel_event: Event
    model: Any
    tokenizer: Any
    streamer: Any = None
    thread: Thread | None = None


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
        self._generation_lock = Lock()
        self._active_generation: _GenerationLease | None = None
        self._unloading = False
        self._prompt_capture_session_id = uuid4().hex
        self._prompt_capture_sequence = 0

    @staticmethod
    def _write_capture_file(path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")

    def _start_prompt_capture(
        self,
        prompt: str,
        options: ResolvedGenerationOptions,
        model_id: str,
        revision: str,
    ) -> dict[str, Any] | None:
        """Persist prepared exact input only when a developer opts in by env."""
        configured = os.environ.get(_PROMPT_CAPTURE_DIRECTORY_ENV, "").strip()
        if not configured:
            return None
        self._prompt_capture_sequence += 1
        root = Path(configured).expanduser()
        if not root.is_absolute():
            logger.warning("Assistant prompt capture needs an absolute directory.")
            return None
        try:
            root.mkdir(parents=True, exist_ok=True)
            root = root.resolve(strict=True)
            directory = (
                root
                / self._prompt_capture_session_id
                / str(self._prompt_capture_sequence)
            )
            directory.mkdir(parents=True, exist_ok=False)
            directory.chmod(0o700)
            prompt_bytes = prompt.encode("utf-8")
            metadata = {
                "model": {"id": model_id, "revision": revision},
                "options": asdict(options),
                "session_id": self._prompt_capture_session_id,
                "sequence": self._prompt_capture_sequence,
                "prompt_bytes": len(prompt_bytes),
                "prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
                "raw_output_bytes": 0,
                "raw_output_sha256": hashlib.sha256(b"").hexdigest(),
                "status": "prepared",
            }
            self._write_capture_file(directory / "prompt.txt", prompt)
            self._write_capture_file(directory / "raw-output.txt", "")
            self._write_capture_file(
                directory / "metadata.json",
                json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2)
                + "\n",
            )
        except Exception:
            logger.warning(
                "Assistant prompt capture preparation failed; inference continues."
            )
            return None
        else:
            return {"directory": directory, "metadata": metadata}

    def _finish_prompt_capture(
        self,
        capture: dict[str, Any] | None,
        raw_output: str,
        status: str,
    ) -> None:
        if capture is None:
            return
        try:
            metadata = dict(capture["metadata"])
            raw_bytes = raw_output.encode("utf-8")
            metadata.update(
                raw_output_bytes=len(raw_bytes),
                raw_output_sha256=hashlib.sha256(raw_bytes).hexdigest(),
                status=status,
            )
            directory = capture["directory"]
            self._write_capture_file(directory / "raw-output.txt", raw_output)
            self._write_capture_file(
                directory / "metadata.json",
                json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2)
                + "\n",
            )
        except Exception:
            logger.warning(
                "Assistant prompt capture finalization failed; inference continues."
            )

    def _normalize_runtime_device(self, torch_module) -> None:
        """Fail visibly if the pre-resolved CUDA device became unavailable."""
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

        raise PreconditionError(
            (
                "The selected GPU became unavailable before the local model could "
                "load. Retry the assistant or choose a CPU-compatible setup in "
                "Assistant Settings."
            ),
            diagnostics={
                "code": "local_runtime_cuda_became_unavailable",
                "operation": "local_model_load",
                "requested_device": device,
                "reason": str(reason or "unknown"),
                "retryable": True,
            },
        )

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
        spec = local_model_spec(self.config.model_name)
        if spec is None:
            raise RuntimeError(
                "Configured local model has no runtime specification: "
                f"{self.config.model_name}."
            )

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
        resource_preflight = check_model_load_resource_preflight(
            required_memory_bytes=int(spec.estimated_vram_gb * BYTES_PER_GB),
            device=str(self.config.device),
        )
        enforce_model_load_resource_preflight(resource_preflight)
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.config.model_name,
                cache_dir=self.config.cache_dir,
                revision=spec.revision,
                trust_remote_code=False,
                local_files_only=True,
            )

            # Load model with optional quantization
            model_kwargs = {
                "cache_dir": self.config.cache_dir,
                "revision": spec.revision,
                "trust_remote_code": False,
                "local_files_only": True,
            }
            if spec.attn_implementation:
                model_kwargs["attn_implementation"] = spec.attn_implementation

            if self.config.load_in_4bit:
                model_kwargs["device_map"] = "auto"
                model_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                )
            elif str(self.config.device).startswith("cuda"):
                model_kwargs["dtype"] = getattr(
                    cast(Any, torch),
                    spec.preferred_cuda_dtype,
                )

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
            if is_cuda_oom_error(e):
                self._release_materialized_resources()
                raise PreconditionError(
                    (
                        "Local model loading ran out of GPU memory. Partial model "
                        "resources and the CUDA cache were released. Close other "
                        "GPU applications and retry."
                    ),
                    diagnostics={
                        "code": "local_model_load_cuda_oom",
                        "operation": "local_model_load",
                        "resource": "cuda_memory",
                        "retryable": True,
                        "runtime_state": "unloaded",
                    },
                ) from e
            logger.error("Failed to load model: %s", e)
            raise

    def _release_materialized_resources(self) -> None:
        """Release only references and cache owned by this backend."""
        with self._generation_lock:
            self.model = None
            self.tokenizer = None
            self.is_loaded = False
        gc.collect()
        try:
            release_cuda_cache()
        except Exception:  # pragma: no cover - defensive cleanup path
            logger.debug("CUDA cache cleanup failed during local model release.")

    def unload(self) -> bool:
        """Release model resources only after active generation has stopped."""
        with self._generation_lock:
            if self._unloading:
                return False
            self._unloading = True

        try:
            if not self.cancel_generation():
                logger.warning(
                    "Local model unload deferred because generation is still running."
                )
                return False

            with self._generation_lock:
                if self._active_generation is not None:
                    return False
            self._release_materialized_resources()
            return True
        finally:
            with self._generation_lock:
                self._unloading = False

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

        spec = local_model_spec(self.config.model_name)
        preserves_system_role = bool(spec and spec.supports_system_role)

        # Step 1: Preserve native system-role support where the pinned model
        # declares it; legacy strict templates receive the compatibility merge.
        system_content = None
        filtered = []
        for msg in messages:
            if msg.get("role") == "system" and not preserves_system_role:
                system_content = msg.get("content", "")
            else:
                filtered.append(dict(msg))

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
                if (
                    preserves_system_role
                    and msg.get("role") == "user"
                    and self._is_untrusted_context_message(result[-1])
                ):
                    result.append(
                        {
                            "role": "assistant",
                            "content": MODEL_UNTRUSTED_CONTEXT_BOUNDARY_MESSAGE,
                        }
                    )
                    result.append(msg)
                    continue
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

    @staticmethod
    def _is_untrusted_context_message(message: dict[str, Any]) -> bool:
        content = message.get("content")
        if type(content) is not str or len(content.encode("utf-8")) > 8_192:
            return False
        try:
            payload = json.loads(content)
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
        return bool(
            type(payload) is dict
            and payload.get("schema") == "xbrainlab.untrusted_context.v1"
            and payload.get("trust") == "untrusted"
            and type(payload.get("items")) is list
        )

    @staticmethod
    def _required_policy_and_request_messages(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Keep only host policy and the exact latest user request."""
        required_messages = [
            dict(message) for message in messages if message.get("role") == "system"
        ]
        latest_user_message = next(
            (
                dict(message)
                for message in reversed(messages)
                if message.get("role") == "user"
            ),
            None,
        )
        if latest_user_message is not None:
            required_messages.append(latest_user_message)
        return required_messages

    @staticmethod
    def _render_chat_template_with_token_count(
        tokenizer: Any,
        messages: list[dict[str, Any]],
    ) -> tuple[str, int]:
        """Render and count one exact chat template without truncation."""
        token_ids = tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
        )
        token_count = len(token_ids)
        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        if type(prompt) is not str:
            raise RuntimeError("Local tokenizer did not render a text chat template.")
        return prompt, token_count

    def _fit_prompt_to_runtime_context(
        self,
        tokenizer: Any,
        messages: list[dict[str, Any]],
        *,
        max_input_tokens: int,
    ) -> str:
        """Drop optional context or reject before token-level truncation."""
        processed_messages = self._process_messages_for_template(messages)
        prompt, token_count = self._render_chat_template_with_token_count(
            tokenizer,
            processed_messages,
        )
        if token_count <= max_input_tokens:
            return prompt

        required_messages = self._required_policy_and_request_messages(messages)
        processed_required_messages = self._process_messages_for_template(
            required_messages
        )
        required_prompt, required_token_count = (
            self._render_chat_template_with_token_count(
                tokenizer,
                processed_required_messages,
            )
        )
        if required_token_count > max_input_tokens:
            raise RuntimeError(LOCAL_MODEL_INPUT_TOO_LONG_MESSAGE)
        return required_prompt

    def _acquire_generation_lease(self) -> _GenerationLease:
        """Reserve the loaded model for exactly one generation."""
        with self._generation_lock:
            if self._unloading:
                raise RuntimeError("Local model unload is in progress.")
            if self._active_generation is not None:
                raise RuntimeError("A local generation is still running.")
            if not self.is_loaded or self.tokenizer is None or self.model is None:
                raise RuntimeError("Model/Tokenizer not loaded")
            lease = _GenerationLease(
                cancel_event=Event(),
                model=self.model,
                tokenizer=self.tokenizer,
            )
            self._active_generation = lease
            return lease

    def _release_generation_lease(self, lease: _GenerationLease) -> None:
        """Release only the exact generation lease owned by the caller."""
        with self._generation_lock:
            if self._active_generation is lease:
                self._active_generation = None

    def generate_stream(
        self,
        messages: list,
        *,
        options: ResolvedGenerationOptions,
    ):
        """Streams generated text from the local model.

        Applies the tokenizer's chat template, spawns a generation
        thread, and yields text chunks via ``TextIteratorStreamer``.

        Args:
            messages: List of message dicts with ``role`` and ``content``.
            options: Fully resolved decoding options from ``LLMEngine``.

        Yields:
            Text chunks produced by the model.

        Raises:
            RuntimeError: If the model or tokenizer is not loaded.

        """
        if type(options) is not ResolvedGenerationOptions:
            raise TypeError("options must be ResolvedGenerationOptions")
        ResolvedGenerationOptions.validate(options)
        if not self.is_loaded:
            self.load()
        lease = self._acquire_generation_lease()
        thread_started = False
        capture: dict[str, Any] | None = None
        raw_chunks: list[str] = []
        terminal_status = "failed"
        try:
            import transformers

            text_iterator_streamer_cls = transformers.TextIteratorStreamer

            spec = local_model_spec(self.config.model_name)
            if spec is None:
                raise RuntimeError(
                    "Configured local model has no runtime specification: "
                    f"{self.config.model_name}."
                )
            max_input_tokens = spec.runtime_context_tokens - options.max_new_tokens
            if max_input_tokens <= 0:
                raise RuntimeError(
                    "Generation output budget exceeds the local model runtime "
                    "context limit."
                )
            prompt = self._fit_prompt_to_runtime_context(
                lease.tokenizer,
                messages,
                max_input_tokens=max_input_tokens,
            )
            capture = self._start_prompt_capture(
                prompt, options, spec.repo_id, spec.revision
            )
            inputs = lease.tokenizer(
                prompt,
                return_tensors="pt",
                add_special_tokens=False,
            ).to(lease.model.device)

            streamer = text_iterator_streamer_cls(
                lease.tokenizer,
                skip_prompt=True,
                skip_special_tokens=True,
            )
            with self._generation_lock:
                if self._active_generation is not lease:
                    raise RuntimeError("Local generation lease was lost.")
                lease.streamer = streamer

            generation_kwargs = dict(
                inputs,
                streamer=streamer,
                max_new_tokens=options.max_new_tokens,
                do_sample=options.do_sample,
            )
            if options.do_sample:
                generation_kwargs["temperature"] = options.temperature
                generation_kwargs["top_p"] = options.top_p
            stopping_criteria = self._build_stopping_criteria(
                transformers,
                lease.cancel_event,
            )
            if stopping_criteria is not None:
                generation_kwargs["stopping_criteria"] = stopping_criteria

            errors: list[BaseException] = []

            def _generate() -> None:
                try:
                    lease.model.generate(**generation_kwargs)
                except BaseException as exc:  # pragma: no cover - runtime path
                    logger.error("Local generation failed: %s", exc, exc_info=True)
                    errors.append(exc)
                    if hasattr(streamer, "end"):
                        streamer.end()
                finally:
                    self._release_generation_lease(lease)

            thread = Thread(target=_generate, daemon=True)
            with self._generation_lock:
                if self._active_generation is not lease:
                    raise RuntimeError("Local generation lease was lost.")
                if lease.cancel_event.is_set():
                    terminal_status = "cancelled"
                    return
                lease.thread = thread
            thread.start()
            thread_started = True
            terminal_status = "completed"
            try:
                try:
                    for chunk in streamer:
                        if lease.cancel_event.is_set():
                            terminal_status = "cancelled"
                            break
                        text_chunk = str(chunk)
                        raw_chunks.append(text_chunk)
                        yield text_chunk
                finally:
                    thread.join()
                if lease.cancel_event.is_set():
                    terminal_status = "cancelled"
                if errors and not lease.cancel_event.is_set():
                    terminal_status = "failed"
                    error_message = f"Local generation failed: {errors[0]}"
                    raise RuntimeError(error_message)  # noqa: TRY301
            except GeneratorExit:
                terminal_status = "cancelled"
                raise
            except BaseException:
                terminal_status = "failed"
                raise
        finally:
            self._finish_prompt_capture(capture, "".join(raw_chunks), terminal_status)
            if not thread_started:
                self._release_generation_lease(lease)

    def _build_stopping_criteria(
        self,
        transformers_module: Any,
        cancel_event: Event,
    ) -> Any | None:
        """Return a HuggingFace stopping criterion tied to backend cancellation."""
        stopping_base = getattr(transformers_module, "StoppingCriteria", None)
        stopping_list = getattr(transformers_module, "StoppingCriteriaList", None)
        if not isinstance(stopping_base, type) or stopping_list is None:
            return None

        def _cancel_requested(_self, input_ids, scores, **kwargs):
            _ = input_ids, scores, kwargs
            return cancel_event.is_set()

        cancel_stopping_criteria = type(
            "_CancelStoppingCriteria",
            (stopping_base,),
            {"__call__": _cancel_requested},
        )
        return stopping_list([cancel_stopping_criteria()])

    def cancel_generation(self, wait_timeout: float = 0.25) -> bool:
        """Request cancellation without releasing a live generation lease."""
        with self._generation_lock:
            lease = self._active_generation
            if lease is None:
                return True
            lease.cancel_event.set()
            streamer = lease.streamer
            thread = lease.thread

        if hasattr(streamer, "end"):
            try:
                streamer.end()
            except Exception:
                logger.debug("Failed to end local generation streamer", exc_info=True)

        if thread is None:
            return False
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(0.0, float(wait_timeout)))
        return not thread.is_alive()
