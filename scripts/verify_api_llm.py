import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine


def main():
    print("=== XBrainLab API Verification ===")

    # 1. Ask for credentials
    api_key = input("Enter OpenAI API Key (or press Enter if set in env): ").strip()
    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY") or ""

    if not api_key:
        print("Error: No API Key provided.")
        return

    base_url = input("Enter Base URL (default: https://api.openai.com/v1): ").strip()
    if not base_url:
        base_url = "https://api.openai.com/v1"

    model_name = input("Enter Model Name (default: gpt-4o): ").strip()
    if not model_name:
        model_name = "gpt-4o"

    # 2. Setup Config
    config = LLMConfig()
    config.inference_mode = "api"
    config.api_key = api_key
    config.base_url = base_url
    config.api_model_name = model_name

    # 3. Initialize Engine
    print(f"\nInitializing Engine in API mode (Target: {model_name})...")
    try:
        engine = LLMEngine(config)
        engine.load_model()
        print("Engine Initialized Successfully.")
    except Exception as e:
        print(f"Initialization Failed: {e}")
        return

    # 4. Run Inference
    print("\nSending test message ('Hello, are you working?')...")
    messages = [{"role": "user", "content": "Hello, are you working?"}]

    print("\nResponse:")
    print("-" * 20)
    try:
        for chunk in engine.generate_stream(messages):
            print(chunk, end="", flush=True)
        print("\n" + "-" * 20)
        print("\nSuccess! API Client is working.")

    except Exception as e:
        print(f"\nGeneration Failed: {e}")


if __name__ == "__main__":
    main()
