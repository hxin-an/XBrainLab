import sys
import torch

print(f"DEBUG: sys.path: {sys.path}")
print(f"DEBUG: torch file: {torch.__file__}")
print(f"DEBUG: torch path: {torch.__path__}")

try:
    import torch.jit
    print("DEBUG: torch.jit imported successfully")
except ImportError as e:
    print(f"DEBUG: Failed to import torch.jit: {e}")
    raise

def test_torch_jit_import():
    assert torch.jit is not None
