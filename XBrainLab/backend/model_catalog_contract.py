"""Lightweight stable identifiers for the supported EEG model catalog."""

from __future__ import annotations

BRAINDECODE_MODEL_IDS = (
    "braindecode.eegnet",
    "braindecode.shallowfbcspnet",
    "braindecode.deep4net",
    "braindecode.eegconformer",
    "braindecode.atcnet",
    "braindecode.eeginceptionerp",
    "braindecode.sccnet",
    "braindecode.eegnex",
    "braindecode.eegitnet",
    "braindecode.ctnet",
)

LEGACY_XBRAINLAB_MODEL_NAMES = ("EEGNet", "ShallowConvNet", "SCCNet")
TRAINING_MODEL_NAMES = (*BRAINDECODE_MODEL_IDS, *LEGACY_XBRAINLAB_MODEL_NAMES)
DEFAULT_MODEL_ID = "braindecode.eegnet"
