import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

print("Importing Agent...")
try:
    from remote.core.agent import Agent
    print("Agent imported successfully.")
    agent = Agent(use_rag=False, use_voting=False)
    print("Agent initialized successfully.")
except Exception as e:
    print(f"Error: {e}")
