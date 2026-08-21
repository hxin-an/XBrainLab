"""Static Braindecode 1.6.1 model metadata used by the product catalog.

This module deliberately contains no Braindecode imports.  Listing models must
remain cheap and must not execute the upstream ``braindecode.models`` barrel.
The order and constructor requirements mirror Braindecode 1.6.1's
``models_mandatory_parameters`` contract.
"""

from __future__ import annotations

from dataclasses import dataclass

BRAINCDECODE_SOURCE_REVISION = "braindecode==1.6.1"


@dataclass(frozen=True, slots=True)
class BraindecodeCatalogEntry:
    """One pinned upstream architecture and its product-facing metadata."""

    class_name: str
    module_name: str
    required_inputs: tuple[str, ...]
    family: str
    task: str
    license_id: str
    unavailable_reason: str = ""
    legacy_copy_allowed: bool = False
    legacy_unavailable_reason: str = (
        "Local recovery source is unavailable until per-file provenance is verified."
    )

    @property
    def model_id(self) -> str:
        return f"braindecode.{self.class_name.casefold()}"

    @property
    def available(self) -> bool:
        return not self.unavailable_reason


_RESTRICTED_MODELS = {
    "BrainModule",
    "EEGMiner",
    "EMG2QwertyNet",
    "MetaNeuromotorHand",
}
_NON_CLASSIFICATION_TASKS = {
    "InterpolatedSignalJEPA": "representation",
    "SignalJEPA": "representation",
    "EMG2QwertyNet": "sequence",
    "MetaNeuromotorHand": "sequence",
}
_MIT_MODELS = {"CTNet", "IFNet", "MEDFormer", "TCFormer"}
_APACHE_MODELS = {"LUNA", "MVPFormer"}

_SLEEP_MODELS = {
    "AttnSleep",
    "DeepSleepNet",
    "SleepStagerBlanco2020",
    "SleepStagerChambon2018",
    "USleep",
}
_FILTER_BANK_MODELS = {
    "EEGMiner",
    "FBCNet",
    "FBLightConvNet",
    "FBMSNet",
    "IFNet",
}
_FOUNDATION_MODELS = {
    "BENDR",
    "BIOT",
    "CBraMod",
    "CodeBrain",
    "EEGDINO",
    "EEGPT",
    "InterpolatedBENDR",
    "InterpolatedBIOT",
    "InterpolatedEEGPT",
    "InterpolatedLaBraM",
    "InterpolatedSignalJEPA",
    "Labram",
    "REVE",
    "SignalJEPA",
    "SignalJEPA_Contextual",
    "SignalJEPA_PostLocal",
    "SignalJEPA_PreLocal",
}
_ATTENTION_MODELS = {
    "ATCNet",
    "AttentionBaseNet",
    "CTNet",
    "EEGConformer",
    "MEDFormer",
    "MSVTNet",
    "MVPFormer",
    "PBT",
    "STEEGFormer",
    "TCFormer",
}
_GRAPH_MODELS = {"DGCNN", "EEGSym"}


def _family(class_name: str) -> str:
    if class_name in _SLEEP_MODELS:
        return "Sleep"
    if class_name in _FILTER_BANK_MODELS:
        return "Filter bank"
    if class_name in _FOUNDATION_MODELS:
        return "Foundation"
    if class_name in _ATTENTION_MODELS:
        return "Attention"
    if class_name in _GRAPH_MODELS:
        return "Graph"
    return "Convolutional"


def _task(class_name: str) -> str:
    return _NON_CLASSIFICATION_TASKS.get(class_name, "classification")


def _license(class_name: str) -> str:
    if class_name in _RESTRICTED_MODELS:
        return "CC-BY-NC-4.0"
    if class_name in _MIT_MODELS:
        return "MIT"
    if class_name in _APACHE_MODELS:
        return "Apache-2.0"
    return "UNVERIFIED"


def _unavailable_reason(class_name: str) -> str:
    if class_name in _RESTRICTED_MODELS:
        return (
            "Unavailable because this model's license is not approved for product use."
        )
    if class_name in _NON_CLASSIFICATION_TASKS:
        return (
            "Unavailable because the current training workflow supports "
            "classification outputs only."
        )
    return ""


def _entry(
    class_name: str,
    module_name: str,
    required_inputs: tuple[str, ...],
) -> BraindecodeCatalogEntry:
    return BraindecodeCatalogEntry(
        class_name=class_name,
        module_name=module_name,
        required_inputs=required_inputs,
        family=_family(class_name),
        task=_task(class_name),
        license_id=_license(class_name),
        unavailable_reason=_unavailable_reason(class_name),
    )


BRAINCDECODE_CATALOG_ENTRIES = (
    _entry("ATCNet", "braindecode.models.atcnet", ("n_chans", "n_outputs", "n_times")),
    _entry("BDTCN", "braindecode.models.tcn", ("n_chans", "n_outputs")),
    _entry("Deep4Net", "braindecode.models.deep4", ("n_chans", "n_outputs", "n_times")),
    _entry(
        "DeepSleepNet",
        "braindecode.models.deepsleepnet",
        ("n_chans", "n_outputs", "n_times"),
    ),
    _entry(
        "EEGConformer",
        "braindecode.models.eegconformer",
        ("n_chans", "n_outputs", "n_times"),
    ),
    _entry(
        "EEGInceptionERP",
        "braindecode.models.eeginception_erp",
        ("n_chans", "n_outputs", "n_times", "sfreq"),
    ),
    _entry(
        "EEGInceptionMI",
        "braindecode.models.eeginception_mi",
        ("n_chans", "n_outputs", "n_times", "sfreq"),
    ),
    _entry(
        "EEGITNet", "braindecode.models.eegitnet", ("n_chans", "n_outputs", "n_times")
    ),
    _entry("EEGNet", "braindecode.models.eegnet", ("n_chans", "n_outputs", "n_times")),
    _entry(
        "EEGPT",
        "braindecode.models.eegpt",
        ("n_chans", "n_outputs", "n_times", "chs_info"),
    ),
    _entry(
        "InterpolatedEEGPT",
        "braindecode.models.eegpt",
        ("chs_info", "n_outputs", "n_times"),
    ),
    _entry(
        "ShallowFBCSPNet",
        "braindecode.models.shallow_fbcsp",
        ("n_chans", "n_outputs", "n_times"),
    ),
    _entry(
        "SleepStagerBlanco2020",
        "braindecode.models.sleep_stager_blanco_2020",
        ("n_chans", "n_outputs", "n_times"),
    ),
    _entry(
        "SleepStagerChambon2018",
        "braindecode.models.sleep_stager_chambon_2018",
        ("n_chans", "n_outputs", "n_times", "sfreq"),
    ),
    _entry(
        "AttnSleep", "braindecode.models.attn_sleep", ("n_outputs", "n_times", "sfreq")
    ),
    _entry("TIDNet", "braindecode.models.tidnet", ("n_chans", "n_outputs", "n_times")),
    _entry(
        "USleep",
        "braindecode.models.usleep",
        ("n_chans", "n_outputs", "n_times", "sfreq"),
    ),
    _entry(
        "BIOT", "braindecode.models.biot", ("n_chans", "n_outputs", "sfreq", "n_times")
    ),
    _entry(
        "InterpolatedBIOT",
        "braindecode.models.biot",
        ("chs_info", "n_outputs", "sfreq", "n_times"),
    ),
    _entry(
        "AttentionBaseNet",
        "braindecode.models.attentionbasenet",
        ("n_chans", "n_outputs", "n_times"),
    ),
    _entry("Labram", "braindecode.models.labram", ("chs_info", "n_outputs", "n_times")),
    _entry(
        "InterpolatedLaBraM",
        "braindecode.models.labram",
        ("chs_info", "n_outputs", "n_times"),
    ),
    _entry(
        "EEGSimpleConv",
        "braindecode.models.eegsimpleconv",
        ("n_chans", "n_outputs", "sfreq"),
    ),
    _entry(
        "SPARCNet", "braindecode.models.sparcnet", ("n_chans", "n_outputs", "n_times")
    ),
    _entry(
        "ContraWR",
        "braindecode.models.contrawr",
        ("n_chans", "n_outputs", "sfreq", "n_times"),
    ),
    _entry("EEGNeX", "braindecode.models.eegnex", ("n_chans", "n_outputs", "n_times")),
    _entry(
        "EEGSym",
        "braindecode.models.eegsym",
        ("chs_info", "n_chans", "n_outputs", "n_times", "sfreq"),
    ),
    _entry(
        "TSception",
        "braindecode.models.tsinception",
        ("n_chans", "n_outputs", "n_times", "sfreq"),
    ),
    _entry(
        "EEGTCNet", "braindecode.models.eegtcnet", ("n_chans", "n_outputs", "n_times")
    ),
    _entry(
        "SyncNet", "braindecode.models.syncnet", ("n_chans", "n_outputs", "n_times")
    ),
    _entry(
        "MSVTNet", "braindecode.models.msvtnet", ("n_chans", "n_outputs", "n_times")
    ),
    _entry(
        "EEGMiner",
        "braindecode.models.eegminer",
        ("n_chans", "n_outputs", "n_times", "sfreq"),
    ),
    _entry("CTNet", "braindecode.models.ctnet", ("n_chans", "n_outputs", "n_times")),
    _entry(
        "TCFormer", "braindecode.models.tcformer", ("n_chans", "n_outputs", "n_times")
    ),
    _entry(
        "SincShallowNet",
        "braindecode.models.sinc_shallow",
        ("n_chans", "n_outputs", "n_times", "sfreq"),
    ),
    _entry(
        "SCCNet",
        "braindecode.models.sccnet",
        ("n_chans", "n_outputs", "n_times", "sfreq"),
    ),
    _entry("SignalJEPA", "braindecode.models.signal_jepa", ("chs_info",)),
    _entry("InterpolatedSignalJEPA", "braindecode.models.signal_jepa", ("chs_info",)),
    _entry(
        "SignalJEPA_Contextual",
        "braindecode.models.signal_jepa",
        ("chs_info", "n_times", "n_outputs"),
    ),
    _entry(
        "SignalJEPA_PostLocal",
        "braindecode.models.signal_jepa",
        ("n_chans", "n_times", "n_outputs"),
    ),
    _entry(
        "SignalJEPA_PreLocal",
        "braindecode.models.signal_jepa",
        ("n_chans", "n_times", "n_outputs"),
    ),
    _entry(
        "FBCNet",
        "braindecode.models.fbcnet",
        ("n_chans", "n_outputs", "n_times", "sfreq"),
    ),
    _entry(
        "FBMSNet",
        "braindecode.models.fbmsnet",
        ("n_chans", "n_outputs", "n_times", "sfreq"),
    ),
    _entry(
        "MetaNeuromotorHand",
        "braindecode.models.meta_neuromotor",
        ("n_chans", "n_outputs", "n_times", "sfreq"),
    ),
    _entry(
        "EMG2QwertyNet",
        "braindecode.models.emg2qwerty",
        ("n_chans", "n_outputs", "n_times", "sfreq"),
    ),
    _entry(
        "FBLightConvNet",
        "braindecode.models.fblightconvnet",
        ("n_chans", "n_outputs", "n_times", "sfreq"),
    ),
    _entry(
        "IFNet",
        "braindecode.models.ifnet",
        ("n_chans", "n_outputs", "n_times", "sfreq"),
    ),
    _entry(
        "PBT",
        "braindecode.models.patchedtransformer",
        ("n_chans", "n_outputs", "n_times"),
    ),
    _entry(
        "SSTDPN",
        "braindecode.models.sstdpn",
        ("n_chans", "n_outputs", "n_times", "sfreq"),
    ),
    _entry(
        "BrainModule",
        "braindecode.models.brainmodule",
        ("n_chans", "n_outputs", "n_times", "sfreq"),
    ),
    _entry("BENDR", "braindecode.models.bendr", ("n_chans", "n_outputs", "n_times")),
    _entry(
        "InterpolatedBENDR",
        "braindecode.models.bendr",
        ("chs_info", "n_outputs", "n_times"),
    ),
    _entry("LUNA", "braindecode.models.luna", ("n_chans", "n_times", "n_outputs")),
    _entry(
        "MEDFormer", "braindecode.models.medformer", ("n_chans", "n_outputs", "n_times")
    ),
    _entry(
        "STEEGFormer",
        "braindecode.models.steegformer",
        ("n_chans", "n_outputs", "n_times"),
    ),
    _entry(
        "MVPFormer",
        "braindecode.models.mvpformer",
        ("n_chans", "n_outputs", "n_times", "sfreq"),
    ),
    _entry(
        "REVE",
        "braindecode.models.reve",
        ("n_times", "n_outputs", "n_chans", "chs_info"),
    ),
    _entry("CBraMod", "braindecode.models.cbramod", ("n_outputs",)),
    _entry(
        "CodeBrain", "braindecode.models.codebrain", ("n_chans", "n_outputs", "n_times")
    ),
    _entry(
        "DGCNN",
        "braindecode.models.dgcnn",
        ("n_chans", "n_outputs", "n_times", "chs_info"),
    ),
    _entry(
        "EEGDINO", "braindecode.models.eegdino", ("n_chans", "n_outputs", "n_times")
    ),
)
