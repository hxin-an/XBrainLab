import os
import sys
import traceback

# Add project root to path
sys.path.append(os.getcwd())

from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine


def main():
    print("=== XBrainLab Gemini API Verification ===")

    # 1. Ask for credentials
    # 1. Check for credentials
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        api_key = input("Enter Google Gemini API Key: ").strip()

    if not api_key:
        print("Error: No API Key provided.")
        return
    else:
        print(f"Using API Key: {api_key[:4]}...{api_key[-4:]}")

    model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash")
    # Optional prompt override could go here but let's keep it simple for auto-run

    # 2. Setup Config
    config = LLMConfig()
    config.inference_mode = "gemini"
    config.gemini_api_key = api_key
    config.gemini_model_name = model_name

    # 3. Initialize Engine
    print(f"\nInitializing Engine in Gemini mode (Target: {model_name})...")
    try:
        engine = LLMEngine(config)
        engine.load_model()  # This initializes GenAI client
        print("Engine Initialized Successfully.")
    except Exception as e:
        print(f"Initialization Failed: {e}")

        traceback.print_exc()
        return

    # 4. Run Inference
    print("\nSending test message ('Hello, can you explain EEG?')...")
    messages = [{"role": "user", "content": "Hello, can you explain EEG briefly?"}]

    print("\nResponse:")
    print("-" * 20)
    try:
        for chunk in engine.generate_stream(messages):
            print(chunk, end="", flush=True)
        print("\n" + "-" * 20)
        print("\nSuccess! Gemini Client is working.")

    except Exception as e:
        print(f"\nGeneration Failed: {e}")

        traceback.print_exc()


if __name__ == "__main__":
    main()
