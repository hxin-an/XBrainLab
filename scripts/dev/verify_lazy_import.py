import os
import sys

# Ensure project root is in path
# Ensure project root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.engine import LLMEngine

print("DEBUG: Imported LLMEngine")

if "XBrainLab.llm.core.backends.local" in sys.modules:
    print("FAILURE: LocalBackend was imported eagerly by engine import!")
    sys.exit(1)
else:
    print("SUCCESS: LocalBackend NOT imported by engine import.")

# Check Torch
if "torch" in sys.modules:
    print("WARNING: Torch is loaded. Checking if it came from LocalBackend...")
    # It might be loaded by other things in environment, but ideally should not be.
    # But let's check strict separation.

# Initialize API Engine
conf = LLMConfig(inference_mode="api", api_key="dummy")
try:
    engine = LLMEngine(conf)
    print("DEBUG: Initialized API Engine")
except Exception as e:
    # Might fail if APIBackend tries to validate something, but that's fine for import check
    print(f"DEBUG: Engine init failed logic but import check proceeds: {e}")

if "XBrainLab.llm.core.backends.local" in sys.modules:
    print("FAILURE: LocalBackend was imported after API init!")
    sys.exit(1)
else:
    print("SUCCESS: LocalBackend NOT imported after API init.")

# Initialize Local Engine
print("DEBUG: Initializing Local Engine...")
conf_local = LLMConfig(inference_mode="local")
try:
    engine_local = LLMEngine(conf_local)
    print("DEBUG: Initialized Local Engine")
except Exception:
    pass  # Expected as model not found etc.

if "XBrainLab.llm.core.backends.local" in sys.modules:
    print("SUCCESS: LocalBackend imported when requested.")
else:
    print("FAILURE: LocalBackend NOT imported when requested!")
    sys.exit(1)

sys.exit(0)
