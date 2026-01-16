
import os
from dataclasses import dataclass


@dataclass
class LLMConfig:
    """Configuration for the LLM Engine."""
    model_name: str = "Qwen/Qwen2.5-7B-Instruct"  # Powerful model for instruction following
    device: str = "cuda" if os.path.exists("/dev/nvidia0") else "cpu"
    max_new_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.9
    do_sample: bool = True
    load_in_4bit: bool = True # Enable 4-bit quantization for 7B models to save VRAM

    # Paths
    # Store models inside the project directory: XBrainLab/llm/models
    cache_dir: str = os.path.join(os.path.dirname(__file__), "models")
