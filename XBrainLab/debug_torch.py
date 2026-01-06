import sys
import torch
print(f"sys.path: {sys.path}")
print(f"torch file: {torch.__file__}")
print(f"torch path: {torch.__path__}")

try:
    import torch.jit
    print("torch.jit imported successfully")
except ImportError as e:
    print(f"Failed to import torch.jit: {e}")

try:
    from torchinfo import summary
    print("torchinfo.summary imported successfully")
except ImportError as e:
    print(f"Failed to import torchinfo.summary: {e}")
