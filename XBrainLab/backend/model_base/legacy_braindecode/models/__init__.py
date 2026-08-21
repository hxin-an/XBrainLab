"""Reviewed legacy model families from Braindecode 1.6.1."""

from .attn_sleep import AttnSleep
from .deep4 import Deep4Net
from .deepsleepnet import DeepSleepNet
from .eeginception_erp import EEGInceptionERP
from .eegnet import EEGNet
from .eegnex import EEGNeX
from .sccnet import SCCNet
from .shallow_fbcsp import ShallowFBCSPNet
from .sleep_stager_blanco_2020 import SleepStagerBlanco2020
from .sleep_stager_chambon_2018 import SleepStagerChambon2018
from .tcn import BDTCN
from .tidnet import TIDNet
from .usleep import USleep

__all__ = [
    "BDTCN",
    "AttnSleep",
    "Deep4Net",
    "DeepSleepNet",
    "EEGInceptionERP",
    "EEGNeX",
    "EEGNet",
    "SCCNet",
    "ShallowFBCSPNet",
    "SleepStagerBlanco2020",
    "SleepStagerChambon2018",
    "TIDNet",
    "USleep",
]
