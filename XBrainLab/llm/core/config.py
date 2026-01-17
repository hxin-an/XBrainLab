import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class LLMConfig:
    """Configuration for the LLM Engine."""

    model_name: str = "Qwen/Qwen2.5-7B-Instruct"
    # Powerful model for instruction following
    device: str = "cuda" if os.path.exists("/dev/nvidia0") else "cpu"
    max_new_tokens: int = 512
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
    api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    base_url: str = field(
        default_factory=lambda: os.getenv(
            "OPENAI_BASE_URL", "https://api.openai.com/v1"
        )
    )
    api_model_name: str = "gpt-4o"  # or 'deepseek-chat', etc.

    # Gemini Configuration
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_model_name: str = "gemini-2.0-flash"
