"""Local-only LLM configuration management.

Defines the ``LLMConfig`` dataclass used by the product assistant runtime.
Legacy remote selections from old settings are accepted only as migration
input and are normalized back to the local runtime.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import tempfile
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, cast

from XBrainLab.llm.core.config_paths import (
    legacy_repo_settings_path,
    user_settings_path,
)
from XBrainLab.llm.core.model_catalog import (
    allowed_local_model_ids,
    default_local_model_id,
    fallback_local_model_id,
    local_model_policy_error,
    model_cache_candidates,
    model_cache_complete,
)
from XBrainLab.platform_paths import user_model_cache_dir


def _cuda_available() -> bool:
    """Check CUDA availability cross-platform via PyTorch."""
    try:
        import torch  # conditional import

        return torch.cuda.is_available()
    except ImportError:
        return False


@dataclass
class AssistantRuntimeSelection:
    """Structured runtime-selection truth for the assistant stack.

    ``backend_mode`` drives actual backend loading and generation.
    ``model_id`` identifies the concrete model inside that backend family.
    ``ui_active_mode`` remains as a compatibility field for UI callers; in
    the product runtime it is always ``local``.
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
        inference_mode: Active backend mode. Product runtime normalizes every
            value to ``'local'``.
        active_mode: User-facing UI mode. Product runtime normalizes every
            value to ``'local'``.
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
    cache_dir: str = field(default_factory=lambda: str(user_model_cache_dir()))

    # Runtime selection. Legacy values from env/settings are migrated by
    # ``__post_init__`` and ``load_from_file``.
    inference_mode: str = field(
        default_factory=lambda: os.getenv("INFERENCE_MODE", "local"),
    )
    active_mode: str = "local"

    local_model_enabled: bool = True  # Whether local model features are enabled
    local_runtime_notice_acknowledged: bool = False

    def __post_init__(self) -> None:
        """Migrate any remote runtime request to the local product runtime."""
        self._force_local_runtime_selection()

    def _force_local_runtime_selection(self) -> None:
        """Normalize execution/UI modes to the only product runtime."""
        self.inference_mode = "local"
        self.active_mode = "local"
        for legacy_attr in (
            "api_key",
            "base_url",
            "api_model_name",
            "gemini_api_key",
            "gemini_model_name",
            "gemini_enabled",
        ):
            if hasattr(self, legacy_attr):
                delattr(self, legacy_attr)

    @staticmethod
    def normalize_backend_mode(mode: str | None, fallback: str = "local") -> str:
        """Normalize backend identifiers to the local-only product runtime."""
        _ = mode, fallback
        return "local"

    @staticmethod
    def normalize_ui_mode(mode: str | None, fallback: str = "local") -> str:
        """Normalize UI mode labels to the local-only product runtime."""
        _ = mode, fallback
        return "local"

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
        _ = mode
        return str(getattr(config, "model_name", ""))

    def assistant_runtime_selection(self) -> AssistantRuntimeSelection:
        """Return the normalized runtime-selection truth for the assistant."""
        return self.assistant_runtime_selection_from(self)

    @classmethod
    def assistant_runtime_selection_from(
        cls,
        config: Any,
    ) -> AssistantRuntimeSelection:
        """Return normalized runtime truth for any config-like object."""
        _ = (
            getattr(config, "inference_mode", None),
            getattr(
                config,
                "active_mode",
                None,
            ),
        )
        backend_mode = "local"
        ui_active_mode = "local"
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
        _ = backend_mode, ui_active_mode
        resolved_backend = "local"

        if model_id:
            policy_error = local_model_policy_error(model_id)
            if policy_error is not None:
                raise ValueError(policy_error)
            self.model_name = model_id

        self.inference_mode = resolved_backend
        self.active_mode = "local"
        return self.assistant_runtime_selection()

    def to_dict(self):
        """Converts the configuration to a plain dictionary.

        Returns:
            A dict representation of all configuration fields.

        """
        data = asdict(self)
        return data

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

    def has_local_model_cache(self, model_name: str | None = None) -> bool:
        """Return ``True`` only for a complete startup-usable model cache."""
        repo_id = model_name or self.model_name
        return model_cache_complete(self.cache_dir, repo_id)

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

    def configured_model_unavailable_message(self) -> str | None:
        """Return migration guidance for an unsupported persisted model.

        Loading settings is intentionally read-only. Callers may present this
        message and let the user explicitly save the exact product model.
        """
        return local_model_policy_error(self.model_name)

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
        """Return the OS per-user path for mutable assistant settings."""
        return str(user_settings_path())

    @staticmethod
    def _legacy_settings_path() -> str:
        """Return the old repo path used only for one-time migration."""
        return str(legacy_repo_settings_path())

    def save_to_file(self, filepath: str | None = None) -> bool:
        """Saves non-sensitive configuration to a JSON file.

        Persists the local model, enabled flag, the active mode, and
        generation parameters (temperature, top_p, max_new_tokens).
        Legacy remote settings are intentionally not persisted.

        Args:
            filepath: Path to the output JSON file.  Defaults to
                the current OS user's XBrainLab config directory.

        Returns:
            ``True`` when the settings were persisted, otherwise ``False``.

        """
        if filepath is None:
            filepath = self._default_settings_path()
        target_path = Path(filepath)
        data = {
            "local": {
                "model_name": self.model_name,
                "enabled": self.local_model_enabled,
                "runtime_notice_acknowledged": (self.local_runtime_notice_acknowledged),
            },
            "active_mode": "local",
            "inference_mode": "local",
            "generation": {
                "temperature": self.temperature,
                "top_p": self.top_p,
                "max_new_tokens": self.max_new_tokens,
            },
        }
        temporary_path: Path | None = None
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=target_path.parent,
                prefix=f".{target_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                json.dump(data, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, target_path)
        except Exception as e:
            logging.getLogger(__name__).error("Error saving settings: %s", e)
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    logging.getLogger(__name__).warning(
                        "Could not remove incomplete settings file %s",
                        temporary_path,
                    )
            return False
        return True

    @classmethod
    def _load_existing_file(cls, filepath: Path) -> LLMConfig | None:
        """Parse one existing settings file without applying path fallback."""
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)

            config = cls()
            if "local" in data:
                config.model_name = data["local"].get("model_name", config.model_name)
                config.local_model_enabled = data["local"].get("enabled", True)
                config.local_runtime_notice_acknowledged = data["local"].get(
                    "runtime_notice_acknowledged",
                    False,
                )
            # Old settings may contain remote active/inference modes. They are
            # accepted as migration input and immediately normalized to local.
            config.active_mode = data.get("active_mode", "local")
            config.inference_mode = data.get("inference_mode", config.active_mode)
            config._force_local_runtime_selection()

            if "generation" in data:
                gen = data["generation"]
                config.temperature = float(gen.get("temperature", config.temperature))
                config.top_p = float(gen.get("top_p", config.top_p))
                config.max_new_tokens = int(
                    gen.get("max_new_tokens", config.max_new_tokens)
                )
        except Exception as e:
            logging.getLogger(__name__).error(
                "Error loading settings from %s: %s",
                filepath,
                e,
            )
            return None

        return config

    @classmethod
    def load_from_file(cls, filepath: str | None = None) -> LLMConfig | None:
        """Loads configuration from a JSON file.

        Creates a new ``LLMConfig`` instance populated with values from the
        file and normalizes legacy remote-runtime fields to the local runtime.

        Args:
            filepath: Path to the JSON settings file.  Defaults to
                the current OS user's XBrainLab config directory. Explicit
                paths never participate in legacy migration.

        Returns:
            A loaded or first-run default ``LLMConfig``. Returns ``None`` for
            an explicitly selected missing file or any selected file that
            cannot be parsed.

        """
        using_default_path = filepath is None
        target_path = Path(filepath or cls._default_settings_path())
        if target_path.exists():
            return cls._load_existing_file(target_path)

        if not using_default_path:
            return None

        legacy_path = Path(cls._legacy_settings_path())
        if legacy_path != target_path and legacy_path.is_file():
            migrated_config = cls._load_existing_file(legacy_path)
            if migrated_config is not None:
                if migrated_config.save_to_file(str(target_path)):
                    logging.getLogger(__name__).info(
                        "Migrated local LLM settings from %s to %s",
                        legacy_path,
                        target_path,
                    )
                    return migrated_config

                logging.getLogger(__name__).error(
                    "Legacy local LLM settings were readable but could not be "
                    "persisted to %s; legacy values will not be used",
                    target_path,
                )
                return cls()

            logging.getLogger(__name__).warning(
                "Legacy local LLM settings at %s were invalid; creating per-user "
                "defaults instead",
                legacy_path,
            )

        default_config = cls()
        if default_config.save_to_file(str(target_path)):
            logging.getLogger(__name__).info(
                "Created default local LLM settings at %s",
                target_path,
            )
        else:
            logging.getLogger(__name__).warning(
                "Default local LLM settings could not be persisted to %s; using "
                "in-memory defaults for this session",
                target_path,
            )
        return default_config
