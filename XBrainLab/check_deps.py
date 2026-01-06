import sys
try:
    import mne
    print("mne imported successfully")
except ImportError:
    print("mne not found")

try:
    import captum
    print("captum imported successfully")
except ImportError:
    print("captum not found")

try:
    import torch
    print("torch imported successfully")
except ImportError:
    print("torch not found")
