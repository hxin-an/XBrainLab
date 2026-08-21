"""Reviewed baseline model family from Braindecode 1.6.1."""

from .deep4 import Deep4Net
from .eeginception_erp import EEGInceptionERP
from .eegnet import EEGNet
from .eegnex import EEGNeX
from .sccnet import SCCNet
from .shallow_fbcsp import ShallowFBCSPNet

__all__ = [
    "Deep4Net",
    "EEGInceptionERP",
    "EEGNeX",
    "EEGNet",
    "SCCNet",
    "ShallowFBCSPNet",
]
