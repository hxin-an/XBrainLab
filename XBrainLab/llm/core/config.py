"""LLM configuration management.

Defines the ``LLMConfig`` dataclass holding all settings for local,
API, and Gemini inference backends, with JSON persistence support.
"""

import importlib.util
import json
import logging
import os
import warnings
from dataclasses import asdict, dataclass, field
from typing import Any, cast

from dotenv import load_dotenv

from XBrainLab.llm.core.model_catalog import (
    allowed_local_model_ids,
    default_local_model_id,
    fallback_local_model_id,
    local_model_policy_error,
    model_cache_candidates,
)

LEGACY_REMOTE_RUNTIME_ENV = "XBRAINLAB_SHOW_LEGACY_REMOTE_LLM"


def _cuda_available() -> bool:
    """Check CUDA availability cross-platform via PyTorch."""
    try:
        import torch  # conditional import

        return torch.cuda.is_available()
    except ImportError:
        return False


def legacy_remote_runtime_enabled() -> bool:
    """Return whether legacy remote assistant runtime UI should be visible."""
    return os.getenv(LEGACY_REMOTE_RUNTIME_ENV) == "1"


@dataclass
class AssistantRuntimeSelection:
    """Structured runtime-selection truth for the assistant stack.

    ``backend_mode`` drives actual backend loading and generation.
    ``model_id`` identifies the concrete model inside that backend family.
    ``ui_active_mode`` is the user-facing local vs. Gemini mode label that
    settings, menus, and safety checks can present without guessing from
    display strings.
    """

    backend_mode: str
    model_id: str
    ui_active_mode: str


@dataclass
class LLMConfig:
    """Configuration for the LLM engine.

    Attributes:
        model_name: HuggingFace model identifier for local inference.
        device: Compute device (``'cuda'`` or ``'cpu'``).
        max_new_tokens: Maximum number of tokens to generate.
        timeout: Generation timeout in seconds.
        temperature: Sampling temperature.
        top_p: Nucleus sampling probability.
        do_sample: Whether to use sampling (vs. greedy decoding).
        load_in_4bit: Enable 4-bit quantization for local models.
        cache_dir: Directory for caching downloaded model files.
        inference_mode: Active backend mode (``'local'``, ``'api'``, or
            ``'gemini'``).
        api_key: OpenAI-compatible API key (loaded from environment).
        base_url: Base URL for the OpenAI-compatible API.
        api_model_name: Model name for the API backend.
        gemini_api_key: Google Gemini API key (loaded from environment).
        gemini_model_name: Model name for the Gemini backend.
        gemini_enabled: Whether the Gemini backend is enabled and verified.
        active_mode: Currently active UI mode (``'local'`` or ``'gemini'``).
        local_model_enabled: Whether local model features are enabled.

    """

    model_name: str = field(default_factory=default_local_model_id)
    # Powerful model for instruction following
    device: str = field(default_factory=lambda: "cuda" if _cuda_available() else "cpu")
    max_new_tokens: int = 512
    timeout: int = 60  # Default timeout in seconds for generation
    temperature: float = 0.7
    top_p: float = 0.9
    do_sample: bool = True
    load_in_4bit: bool = False

    # Paths
    # Store models inside the project directory: XBrainLab/llm/models
    cache_dir: str = field(
        default_factory=lambda: os.path.join(os.path.dirname(__file__), "models"),
    )

    # API Configuration
    inference_mode: str = field(
        default_factory=lambda: os.getenv("INFERENCE_MODE", "local"),
    )  # 'local', 'api', or 'gemini'
    api_key: str = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", ""),
        repr=False,
    )
    base_url: str = field(
        default_factory=lambda: os.getenv(
            "OPENAI_BASE_URL",
            "https://api.openai.com/v1",
        ),
    )
    api_model_name: str = "gpt-4o"  # or 'deepseek-chat', etc.

    # Gemini Configuration
    gemini_api_key: str = field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY", ""),
        repr=False,
    )
    gemini_model_name: str = "gemini-2.0-flash"
    gemini_enabled: bool = False

    # Active Mode
    active_mode: str = "local"  # 'local' or 'gemini'
    local_model_enabled: bool = True  # Whether local model features are enabled
    local_runtime_notice_acknowledged: bool = False

    @staticmethod
    def normalize_backend_mode(mode: str | None, fallback: str = "local") -> str:
        """Normalize runtime backend identifiers and tolerate legacy labels."""
        normalized = str(mode or "").strip().lower()
        if normalized in {"local", "api", "gemini"}:
            return normalized
        if "gemini" in normalized:
            return "gemini"
        if "local" in normalized:
            return "local"
        return fallback

    @staticmethod
    def normalize_ui_mode(mode: str | None, fallback: str = "local") -> str:
        """Normalize local-vs-Gemini UI mode labels."""
        normalized = str(mode or "").strip().lower()
        if "gemini" in normalized:
            return "gemini"
        if "local" in normalized:
            return "local"
        return fallback

    def ui_active_mode_key(self) -> str:
        """Return the normalized user-facing local/Gemini mode."""
        return self.normalize_ui_mode(self.active_mode)

    def runtime_backend_mode_key(self) -> str:
        """Return the normalized backend mode that should drive execution."""
        return self.normalize_backend_mode(
            self.inference_mode,
            fallback=self.ui_active_mode_key(),
        )

    def runtime_backend_model_id(self, mode: str | None = None) -> str:
        """Return the model identifier for the requested backend mode."""
        return self.runtime_backend_model_id_from(self, mode)

    @classmethod
    def runtime_backend_model_id_from(
        cls,
        config: Any,
        mode: str | None = None,
    ) -> str:
        """Return the model identifier for any config-like object."""
        resolved_mode = cls.normalize_backend_mode(
            mode,
            fallback=cls.normalize_backend_mode(
                getattr(config, "inference_mode", None),
                fallback=cls.normalize_ui_mode(getattr(config, "active_mode", None)),
            ),
        )
        if resolved_mode == "local":
            return str(getattr(config, "model_name", ""))
        if resolved_mode == "api":
            return str(getattr(config, "api_model_name", ""))
        if resolved_mode == "gemini":
            return str(getattr(config, "gemini_model_name", ""))
        return ""

    def assistant_runtime_selection(self) -> AssistantRuntimeSelection:
        """Return the normalized runtime-selection truth for the assistant."""
        return self.assistant_runtime_selection_from(self)

    @classmethod
    def assistant_runtime_selection_from(
        cls,
        config: Any,
    ) -> AssistantRuntimeSelection:
        """Return normalized runtime truth for any config-like object."""
        ui_active_mode = cls.normalize_ui_mode(getattr(config, "active_mode", None))
        backend_mode = cls.normalize_backend_mode(
            getattr(config, "inference_mode", None),
            fallback=ui_active_mode,
        )
        ui_active_mode = (
            backend_mode if backend_mode in {"local", "gemini"} else ui_active_mode
        )
        return AssistantRuntimeSelection(
            backend_mode=backend_mode,
            model_id=cls.runtime_backend_model_id_from(config, backend_mode),
            ui_active_mode=ui_active_mode,
        )

    def apply_runtime_selection(
        self,
        backend_mode: str,
        *,
        model_id: str | None = None,
        ui_active_mode: str | None = None,
    ) -> AssistantRuntimeSelection:
        """Persist a normalized backend/model/UI selection into this config."""
        previous_selection = self.assistant_runtime_selection()
        resolved_backend = self.normalize_backend_mode(
            backend_mode,
            fallback=previous_selection.backend_mode,
        )

        if model_id:
            if resolved_backend == "local":
                self.model_name = model_id
            elif resolved_backend == "api":
                self.api_model_name = model_id
            elif resolved_backend == "gemini":
                self.gemini_model_name = model_id

        self.inference_mode = resolved_backend

        resolved_ui_mode = (
            self.normalize_ui_mode(
                ui_active_mode,
                fallback=previous_selection.ui_active_mode,
            )
            if ui_active_mode is not None
            else (
                resolved_backend
                if resolved_backend in {"local", "gemini"}
                else previous_selection.ui_active_mode
            )
        )
        self.active_mode = resolved_ui_mode
        return self.assistant_runtime_selection()

    def to_dict(self):
        """Converts the configuration to a plain dictionary.

        Returns:
            A dict representation of all configuration fields.

        """
        return asdict(self)

    def missing_local_runtime_packages(self) -> list[str]:
        """Return optional local-backend packages missing in this environment.

        The local backend always needs ``transformers``. The default product
        path uses small BF16 models under the download limit; 4-bit loading is
        optional and requires ``accelerate`` plus ``bitsandbytes``.
        """
        required = ["transformers"]
        if self.load_in_4bit:
            required.extend(["accelerate", "bitsandbytes"])

        return [
            package for package in required if importlib.util.find_spec(package) is None
        ]

    def _local_cache_candidates(self, model_name: str | None = None) -> list[str]:
        """Return candidate cache paths for a local Hugging Face model."""
        repo_id = model_name or self.model_name
        return model_cache_candidates(self.cache_dir, repo_id)

    def local_cache_candidates(self, model_name: str | None = None) -> list[str]:
        """Return the supported cache layouts for a local Hugging Face model."""
        return list(self._local_cache_candidates(model_name))

    @staticmethod
    def _dir_entries(path: str) -> list[str]:
        """Return directory entries, or an empty list when unavailable."""
        if not os.path.exists(path):
            return []

        try:
            return os.listdir(path)
        except OSError:
            return []

    @classmethod
    def _cache_layout_complete(cls, path: str) -> bool:
        """Return ``True`` when a cache path looks usable for local startup."""
        entries = set(cls._dir_entries(path))
        if not entries:
            return False

        has_config = {"config.json", "tokenizer_config.json"}.issubset(entries)
        has_weights = "model.safetensors.index.json" in entries or any(
            name.endswith((".safetensors", ".bin")) for name in entries
        )
        if has_config and has_weights:
            return True

        snapshots_dir = os.path.join(path, "snapshots")
        for snapshot_name in cls._dir_entries(snapshots_dir):
            snapshot_path = os.path.join(snapshots_dir, snapshot_name)
            snapshot_entries = set(cls._dir_entries(snapshot_path))
            if not snapshot_entries:
                continue

            has_snapshot_config = {"config.json", "tokenizer_config.json"}.issubset(
                snapshot_entries
            )
            has_snapshot_weights = (
                "model.safetensors.index.json" in snapshot_entries
                or any(
                    name.endswith((".safetensors", ".bin")) for name in snapshot_entries
                )
            )
            if has_snapshot_config and has_snapshot_weights:
                return True

        return False

    def has_local_model_cache(self, model_name: str | None = None) -> bool:
        """Return ``True`` when the local model cache looks complete enough."""
        return any(
            self._cache_layout_complete(path)
            for path in self._local_cache_candidates(model_name)
        )

    def local_backend_cpu_fallback_reason(self) -> str | None:
        """Return a reason when local startup must fall back from CUDA to CPU."""
        device = str(getattr(self, "device", "cpu"))
        if not device.startswith("cuda"):
            return None

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                import torch  # conditional import
        except ImportError:
            return None

        torch_module = cast(Any, torch)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if not torch_module.cuda.is_available():
                return "CUDA is not available"

            try:
                probe = torch_module.zeros(1, device=device)
                del probe
            except Exception as exc:  # pragma: no cover - hardware/runtime specific
                return str(exc)

        return None

    def local_backend_ready(self, model_name: str | None = None) -> bool:
        """Return ``True`` when the configured local backend can start."""
        if local_model_policy_error(model_name or self.model_name):
            return False
        return (
            not self.missing_local_runtime_packages()
        ) and self.has_local_model_cache(model_name)

    def local_backend_status_message(self, model_name: str | None = None) -> str:
        """Describe local-backend readiness in user-facing terms."""
        repo_id = model_name or self.model_name
        policy_error = local_model_policy_error(repo_id)
        if policy_error is not None:
            return f"Local runtime unavailable. {policy_error}"

        missing = self.missing_local_runtime_packages()
        if not missing:
            if self.has_local_model_cache(repo_id):
                fallback_reason = self.local_backend_cpu_fallback_reason()
                if fallback_reason is None:
                    return "Local runtime ready."

                suffix = " and disable 4-bit loading" if self.load_in_4bit else ""
                return (
                    "Local runtime ready. GPU execution is unavailable in this "
                    f"environment, so startup will fall back to CPU{suffix}."
                )

            return (
                "Local runtime unavailable. Model cache not found for "
                f"{repo_id}. Install the model in Settings to enable local startup."
            )

        packages = ", ".join(missing)
        return (
            "Local runtime unavailable. Missing optional packages: "
            f"{packages}. Install the Poetry llm group to enable local startup."
        )

    def available_local_model_id(
        self,
        preferred_model: str | None = None,
    ) -> tuple[str | None, str]:
        """Return the first ready local model and a user-facing status message.

        The current model is tried first, then the product primary and fallback
        models. This gives the desktop assistant a deterministic fallback path
        while still enforcing the non-Chinese model catalog and cache limits.
        """
        preferred = (preferred_model or self.model_name or "").strip()
        candidates: list[str] = []
        for model_id in (
            preferred,
            self.default_local_model_id(),
            self.fallback_local_model_id(),
        ):
            if model_id and model_id not in candidates:
                candidates.append(model_id)

        first_failure = ""
        for model_id in candidates:
            if self.local_backend_ready(model_id):
                if model_id == preferred:
                    return model_id, self.local_backend_status_message(model_id)

                if preferred:
                    preferred_message = (
                        first_failure or self.local_backend_status_message(preferred)
                    )
                else:
                    preferred_message = "No preferred local model is configured."
                return (
                    model_id,
                    f"{preferred_message} Falling back to supported local model "
                    f"{model_id}.",
                )

            if not first_failure:
                first_failure = self.local_backend_status_message(model_id)

        return None, first_failure or "No supported local model is ready."

    @staticmethod
    def allowed_local_model_ids() -> list[str]:
        """Return supported local model IDs for product UI surfaces."""
        return allowed_local_model_ids()

    @staticmethod
    def default_local_model_id() -> str:
        """Return the primary supported local model ID."""
        return default_local_model_id()

    @staticmethod
    def fallback_local_model_id() -> str:
        """Return the fallback supported local model ID."""
        return fallback_local_model_id()

    @staticmethod
    def _default_settings_path() -> str:
        """Return the default path for settings.json relative to the project root."""
        # Import here to avoid circular dependency at module level
        try:
            from XBrainLab.config import AppConfig

            return str(AppConfig.BASE_DIR / "settings.json")
        except ImportError:
            return "settings.json"

    def save_to_file(self, filepath: str | None = None):
        """Saves non-sensitive configuration to a JSON file.

        Persists model names, enabled flags, the active mode, and
        generation parameters (temperature, top_p, max_new_tokens).
        API keys are intentionally excluded for security.

        Args:
            filepath: Path to the output JSON file.  Defaults to
                ``settings.json`` in the project root.

        """
        if filepath is None:
            filepath = self._default_settings_path()
        data = {
            "local": {
                "model_name": self.model_name,
                "enabled": self.local_model_enabled,
                "runtime_notice_acknowledged": (self.local_runtime_notice_acknowledged),
            },
            "gemini": {
                "model_name": self.gemini_model_name,
                "enabled": self.gemini_enabled,
            },
            "active_mode": self.active_mode,
            "inference_mode": self.inference_mode,
            "generation": {
                "temperature": self.temperature,
                "top_p": self.top_p,
                "max_new_tokens": self.max_new_tokens,
            },
        }
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logging.getLogger(__name__).error("Error saving settings: %s", e)

    @classmethod
    def load_from_file(cls, filepath: str | None = None):
        """Loads configuration from a JSON file.

        Creates a new ``LLMConfig`` instance populated with values from
        the file.  API keys are always loaded from environment variables
        for security.

        Args:
            filepath: Path to the JSON settings file.  Defaults to
                ``settings.json`` in the project root.

        Returns:
            A new ``LLMConfig`` instance, or ``None`` if the file does
            not exist or cannot be parsed.

        """
        if filepath is None:
            filepath = cls._default_settings_path()
        if not os.path.exists(filepath):
            return None

        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)

            # Load .env BEFORE creating config so field defaults
            # (api_key, base_url, gemini_api_key, inference_mode)
            # can read environment variables correctly.
            load_dotenv()

            config = cls()
            if "local" in data:
                config.model_name = data["local"].get("model_name", config.model_name)
                config.local_model_enabled = data["local"].get("enabled", True)
                config.local_runtime_notice_acknowledged = data["local"].get(
                    "runtime_notice_acknowledged",
                    False,
                )
            if "gemini" in data:
                config.gemini_model_name = data["gemini"].get(
                    "model_name",
                    config.gemini_model_name,
                )
                config.gemini_enabled = data["gemini"].get(
                    "enabled",
                    data["gemini"].get("verified", False),
                )

            config.active_mode = data.get("active_mode", "local")
            config.inference_mode = data.get(
                "inference_mode",
                config.active_mode,
            )

            # Restore generation parameters
            if "generation" in data:
                gen = data["generation"]
                config.temperature = float(gen.get("temperature", config.temperature))
                config.top_p = float(gen.get("top_p", config.top_p))
                config.max_new_tokens = int(
                    gen.get("max_new_tokens", config.max_new_tokens)
                )

        except Exception as e:
            logging.getLogger(__name__).error("Error loading settings: %s", e)
            return None

        return config
