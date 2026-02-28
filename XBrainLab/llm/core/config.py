"""LLM configuration management.

Defines the ``LLMConfig`` dataclass holding all settings for local,
API, and Gemini inference backends, with JSON persistence support.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field

from dotenv import load_dotenv


def _cuda_available() -> bool:
    """Check CUDA availability cross-platform via PyTorch."""
    try:
        import torch  # conditional import

        return torch.cuda.is_available()
    except ImportError:
        return False


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

    model_name: str = "Qwen/Qwen2.5-7B-Instruct"
    # Powerful model for instruction following
    device: str = field(default_factory=lambda: "cuda" if _cuda_available() else "cpu")
    max_new_tokens: int = 512
    timeout: int = 60  # Default timeout in seconds for generation
    temperature: float = 0.7
    top_p: float = 0.9
    do_sample: bool = True
    load_in_4bit: bool = True  # Enable 4-bit quantization for 7B models to save VRAM

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

    def to_dict(self):
        """Converts the configuration to a plain dictionary.

        Returns:
            A dict representation of all configuration fields.

        """
        return asdict(self)

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
            },
            "gemini": {
                "model_name": self.gemini_model_name,
                "enabled": self.gemini_enabled,
            },
            "active_mode": self.active_mode,
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
            # Sync inference_mode with active_mode from saved settings
            config.inference_mode = config.active_mode

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
