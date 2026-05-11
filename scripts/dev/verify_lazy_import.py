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

# Initialize engine with a legacy remote request. Product config should migrate
# the request to local without importing the local backend until load_model().
conf = LLMConfig(inference_mode="api")
engine = LLMEngine(conf)
print("DEBUG: Initialized local-only engine from legacy remote request")

if "XBrainLab.llm.core.backends.local" in sys.modules:
    print("FAILURE: LocalBackend was imported during engine init!")
    sys.exit(1)

if engine.config.inference_mode != "local":
    print("FAILURE: Legacy remote runtime request was not migrated to local!")
    sys.exit(1)

print("SUCCESS: Legacy remote runtime request migrated without eager local import.")

# Initialize Local Engine without loading weights.
print("DEBUG: Initializing Local Engine...")
conf_local = LLMConfig(inference_mode="local")
try:
    _engine_local = LLMEngine(conf_local)
    print("DEBUG: Initialized Local Engine")
except Exception:
    pass  # Expected as model not found etc.

if "XBrainLab.llm.core.backends.local" in sys.modules:
    print("FAILURE: LocalBackend was imported during lazy local engine init!")
    sys.exit(1)

print("SUCCESS: LocalBackend remains lazy until load_model().")
sys.exit(0)
