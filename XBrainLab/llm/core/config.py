import json
import os
from dataclasses import asdict, dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class LLMConfig:
    """Configuration for the LLM Engine."""

    model_name: str = "Qwen/Qwen2.5-7B-Instruct"
    # Powerful model for instruction following
    device: str = "cuda" if os.path.exists("/dev/nvidia0") else "cpu"
    max_new_tokens: int = 512
    timeout: int = 60  # Default timeout in seconds for generation
    temperature: float = 0.7
    top_p: float = 0.9
    do_sample: bool = True
    load_in_4bit: bool = True  # Enable 4-bit quantization for 7B models to save VRAM

    # Paths
    # Store models inside the project directory: XBrainLab/llm/models
    cache_dir: str = field(
        default_factory=lambda: os.path.join(os.path.dirname(__file__), "models")
    )

    # API Configuration
    inference_mode: str = field(
        default_factory=lambda: os.getenv("INFERENCE_MODE", "local")
    )  # 'local', 'api', or 'gemini'
    api_key: str = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", ""), repr=False
    )
    base_url: str = field(
        default_factory=lambda: os.getenv(
            "OPENAI_BASE_URL", "https://api.openai.com/v1"
        )
    )
    api_model_name: str = "gpt-4o"  # or 'deepseek-chat', etc.

    # Gemini Configuration
    gemini_api_key: str = field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY", ""), repr=False
    )
    gemini_model_name: str = "gemini-2.0-flash"
    gemini_verified: bool = False

    # Active Mode
    active_mode: str = "local"  # 'local' or 'gemini'
    local_model_enabled: bool = True  # Whether local model features are enabled

    def to_dict(self):
        return asdict(self)

    def save_to_file(self, filepath: str = "settings.json"):
        """Save non-sensitive config to JSON file."""
        data = {
            "local": {
                "model_name": self.model_name,
                "enabled": self.local_model_enabled,
            },
            "gemini": {
                "model_name": self.gemini_model_name,
                "verified": self.gemini_verified,
            },
            "active_mode": self.active_mode,
        }
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving settings: {e}")

    @classmethod
    def load_from_file(cls, filepath: str = "settings.json"):
        """Load config from JSON file, returning a new instance or None."""
        if not os.path.exists(filepath):
            return None

        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)

            config = cls()
            if "local" in data:
                config.model_name = data["local"].get("model_name", config.model_name)
                config.local_model_enabled = data["local"].get("enabled", True)
            if "gemini" in data:
                config.gemini_model_name = data["gemini"].get(
                    "model_name", config.gemini_model_name
                )
                config.gemini_verified = data["gemini"].get("verified", False)

            config.active_mode = data.get("active_mode", "local")

            # Load API key from env still (security)
            load_dotenv()
            config.gemini_api_key = os.getenv("GEMINI_API_KEY", "")

        except Exception as e:
            print(f"Error loading settings: {e}")
            return None

        return config
