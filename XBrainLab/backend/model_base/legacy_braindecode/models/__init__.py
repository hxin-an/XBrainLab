"""Reviewed legacy model families from Braindecode 1.6.1."""

from .atcnet import ATCNet
from .attentionbasenet import AttentionBaseNet
from .attn_sleep import AttnSleep
from .bendr import BENDR, InterpolatedBENDR
from .biot import BIOT, InterpolatedBIOT
from .cbramod import CBraMod
from .codebrain import CodeBrain
from .contrawr import ContraWR
from .ctnet import CTNet
from .deep4 import Deep4Net
from .deepsleepnet import DeepSleepNet
from .dgcnn import DGCNN
from .eegconformer import EEGConformer
from .eegdino import EEGDINO
from .eeginception_erp import EEGInceptionERP
from .eeginception_mi import EEGInceptionMI
from .eegitnet import EEGITNet
from .eegnet import EEGNet
from .eegnex import EEGNeX
from .eegpt import EEGPT, InterpolatedEEGPT
from .eegsimpleconv import EEGSimpleConv
from .eegsym import EEGSym
from .eegtcnet import EEGTCNet
from .fbcnet import FBCNet
from .fblightconvnet import FBLightConvNet
from .fbmsnet import FBMSNet
from .ifnet import IFNet
from .labram import InterpolatedLaBraM, Labram
from .medformer import MEDFormer
from .msvtnet import MSVTNet
from .mvpformer import MVPFormer
from .patchedtransformer import PBT
from .sccnet import SCCNet
from .shallow_fbcsp import ShallowFBCSPNet
from .sinc_shallow import SincShallowNet
from .sleep_stager_blanco_2020 import SleepStagerBlanco2020
from .sleep_stager_chambon_2018 import SleepStagerChambon2018
from .sparcnet import SPARCNet
from .sstdpn import SSTDPN
from .steegformer import STEEGFormer
from .syncnet import SyncNet
from .tcformer import TCFormer
from .tcn import BDTCN
from .tidnet import TIDNet
from .tsinception import TSception
from .usleep import USleep

__all__ = [
    "BDTCN",
    "BENDR",
    "BIOT",
    "DGCNN",
    "EEGDINO",
    "EEGPT",
    "PBT",
    "SSTDPN",
    "ATCNet",
    "AttentionBaseNet",
    "AttnSleep",
    "CBraMod",
    "CTNet",
    "CodeBrain",
    "ContraWR",
    "Deep4Net",
    "DeepSleepNet",
    "EEGConformer",
    "EEGITNet",
    "EEGInceptionERP",
    "EEGInceptionMI",
    "EEGNeX",
    "EEGNet",
    "EEGSimpleConv",
    "EEGSym",
    "EEGTCNet",
    "FBCNet",
    "FBLightConvNet",
    "FBMSNet",
    "IFNet",
    "InterpolatedBENDR",
    "InterpolatedBIOT",
    "InterpolatedEEGPT",
    "InterpolatedLaBraM",
    "Labram",
    "MEDFormer",
    "MSVTNet",
    "MVPFormer",
    "SCCNet",
    "SPARCNet",
    "STEEGFormer",
    "ShallowFBCSPNet",
    "SincShallowNet",
    "SleepStagerBlanco2020",
    "SleepStagerChambon2018",
    "SyncNet",
    "TCFormer",
    "TIDNet",
    "TSception",
    "USleep",
]
