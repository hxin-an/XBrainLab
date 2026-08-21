"""Reviewed legacy model families from Braindecode 1.6.1."""

from .attn_sleep import AttnSleep
from .contrawr import ContraWR
from .deep4 import Deep4Net
from .deepsleepnet import DeepSleepNet
from .eeginception_erp import EEGInceptionERP
from .eeginception_mi import EEGInceptionMI
from .eegitnet import EEGITNet
from .eegnet import EEGNet
from .eegnex import EEGNeX
from .eegsimpleconv import EEGSimpleConv
from .eegtcnet import EEGTCNet
from .fbcnet import FBCNet
from .fblightconvnet import FBLightConvNet
from .fbmsnet import FBMSNet
from .ifnet import IFNet
from .sccnet import SCCNet
from .shallow_fbcsp import ShallowFBCSPNet
from .sinc_shallow import SincShallowNet
from .sleep_stager_blanco_2020 import SleepStagerBlanco2020
from .sleep_stager_chambon_2018 import SleepStagerChambon2018
from .sparcnet import SPARCNet
from .sstdpn import SSTDPN
from .syncnet import SyncNet
from .tcn import BDTCN
from .tidnet import TIDNet
from .tsinception import TSception
from .usleep import USleep

__all__ = [
    "BDTCN",
    "SSTDPN",
    "AttnSleep",
    "ContraWR",
    "Deep4Net",
    "DeepSleepNet",
    "EEGITNet",
    "EEGInceptionERP",
    "EEGInceptionMI",
    "EEGNeX",
    "EEGNet",
    "EEGSimpleConv",
    "EEGTCNet",
    "FBCNet",
    "FBLightConvNet",
    "FBMSNet",
    "IFNet",
    "SCCNet",
    "SPARCNet",
    "ShallowFBCSPNet",
    "SincShallowNet",
    "SleepStagerBlanco2020",
    "SleepStagerChambon2018",
    "SyncNet",
    "TIDNet",
    "TSception",
    "USleep",
]
