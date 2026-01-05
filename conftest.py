import sys
from unittest.mock import MagicMock

# Mock mne to avoid import errors globally
if "mne" not in sys.modules:
    mne = MagicMock()
    sys.modules["mne"] = mne
    sys.modules["mne.preprocessing"] = MagicMock()
    sys.modules["mne.io"] = MagicMock()
    sys.modules["mne.decoding"] = MagicMock()
    sys.modules["mne.time_frequency"] = MagicMock()

if "captum" not in sys.modules:
    captum = MagicMock()
    sys.modules["captum"] = captum
    sys.modules["captum.attr"] = MagicMock()

if "torch" not in sys.modules:
    sys.modules["torch"] = MagicMock()
    sys.modules["torch.nn"] = MagicMock()
    sys.modules["torch.optim"] = MagicMock()
    sys.modules["torch.utils"] = MagicMock()
    sys.modules["torch.utils.data"] = MagicMock()
