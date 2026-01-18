import os
import sys

from dotenv import load_dotenv

sys.path.append(os.getcwd())
from google import genai

load_dotenv()


def list_models():
    api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    print("--- Listing Gemini Models ---")
    try:
        for model in client.models.list():
            if model.name and "gemini" in model.name:
                print(f"{model.name}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    list_models()
