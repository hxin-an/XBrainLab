from typing import Any, List

from XBrainLab.backend.preprocessor.channel_selection import ChannelSelection

# Need backend classes
from XBrainLab.backend.preprocessor.filtering import Filtering
from XBrainLab.backend.preprocessor.normalize import Normalize
from XBrainLab.backend.preprocessor.rereference import Rereference
from XBrainLab.backend.preprocessor.resample import Resample

# SetMontage might be specialized
# Epoching
from XBrainLab.backend.preprocessor.time_epoch import TimeEpoch

from ..definitions.preprocess_def import (
    BaseBandPassFilterTool,
    BaseChannelSelectionTool,
    BaseEpochDataTool,
    BaseNormalizeTool,
    BaseNotchFilterTool,
    BaseRereferenceTool,
    BaseResampleTool,
    BaseSetMontageTool,
    BaseStandardPreprocessTool,
)


class RealStandardPreprocessTool(BaseStandardPreprocessTool):
    def execute(
        self,
        study: Any,
        l_freq: float = 4,
        h_freq: float = 40,
        notch_freq: float = 50,
        rereference: str = None,
        resample_rate: int = None,
        normalize_method: str = "z-score",
    ) -> str:
        # Apply strict sequence
        try:
            # 1. Bandpass
            study.preprocess(Filtering, l_freq=l_freq, h_freq=h_freq)

            # 2. Notch
            if notch_freq:
                study.preprocess(Filtering, notch_freqs=notch_freq)

            # 3. Resample
            if resample_rate:
                study.preprocess(Resample, rate=resample_rate)

            # 4. Rereference
            if rereference:
                study.preprocess(Rereference, method=rereference)

            # 5. Normalize
            if normalize_method:
                study.preprocess(Normalize, method=normalize_method)

            return "Standard preprocessing applied successfully."
        except Exception as e:
            return f"Preprocessing failed: {e!s}"


class RealBandPassFilterTool(BaseBandPassFilterTool):
    def execute(self, study: Any, low_freq: float, high_freq: float) -> str:
        study.preprocess(Filtering, l_freq=low_freq, h_freq=high_freq)
        return f"Applied Bandpass Filter ({low_freq}-{high_freq} Hz)"


class RealNotchFilterTool(BaseNotchFilterTool):
    def execute(self, study: Any, freq: float) -> str:
        study.preprocess(Filtering, notch_freqs=freq)
        return f"Applied Notch Filter ({freq} Hz)"


class RealResampleTool(BaseResampleTool):
    def execute(self, study: Any, rate: int) -> str:
        study.preprocess(Resample, rate=rate)
        return f"Resampled data to {rate} Hz"


class RealNormalizeTool(BaseNormalizeTool):
    def execute(self, study: Any, method: str) -> str:
        study.preprocess(Normalize, method=method)
        return f"Normalized data using {method}"


class RealRereferenceTool(BaseRereferenceTool):
    def execute(self, study: Any, method: str) -> str:
        study.preprocess(Rereference, method=method)
        return f"Applied reference: {method}"


class RealChannelSelectionTool(BaseChannelSelectionTool):
    def execute(self, study: Any, channels: List[str]) -> str:
        study.preprocess(ChannelSelection, channels=channels)
        return f"Selected {len(channels)} channels."


class RealSetMontageTool(BaseSetMontageTool):
    def execute(self, study: Any, montage_name: str) -> str:
        # Assuming MNE set_montage logic is embedded in ChannelSelection or separate utility?
        # Backend check: study.set_channels usage?
        # Actually set_channels takes (chs, positions).
        # We need a way to Convert 'standard_1020' to positions.
        # study.epoch_data.set_montage(montage_name)?

        # If epoch_data exists
        if study.epoch_data:
            # MNE wrapped objects usually have .set_montage method on Raw/Epochs
            # But study wrapper access?
            # Let's assume user calls this AFTER epoching? Or BEFORE?
            # Usually standard montage is applied to Raw.
            pass

        return "SetMontage not fully implemented in Study API yet (requires MNE integration)."


class RealEpochDataTool(BaseEpochDataTool):
    def execute(
        self,
        study: Any,
        t_min: float = -0.1,
        t_max: float = 1.0,
        event_id: Any = None,
        baseline: List[float] = None,
    ) -> str:
        try:
            # Check arguments mapping to TimeEpoch constructor
            # Backend TimeEpoch._data_preprocess signature:
            # (self, preprocessed_data: Raw, baseline: list, selected_event_names: list, tmin: float, tmax: float)

            # 1. Handle "all events" if event_id is None
            # We need to manually inspect the data to find all available events
            # because TimeEpoch requires an explicit list.
            selected_names = []
            if event_id:
                if isinstance(event_id, list):
                    selected_names = [str(e) for e in event_id]
                else:
                    selected_names = [str(event_id)]
            else:
                # Collect all event names from all loaded data
                all_names = set()
                if study.preprocessed_data_list:
                    for d in study.preprocessed_data_list:
                        _, raw_ids = d.get_event_list()
                        if raw_ids:
                            all_names.update(raw_ids.keys())
                selected_names = list(all_names)
                if not selected_names:
                    return "Error: No events found in data to epoch on."

            # 2. Call Preprocess
            # Note: arguments must match _data_preprocess signature exactly if passed via **kargs
            study.preprocess(
                TimeEpoch,
                tmin=t_min,
                tmax=t_max,
                selected_event_names=selected_names,
                baseline=list(baseline) if baseline else None,
            )
            return f"Data epoched: [{t_min}, {t_max}]s. Events: {selected_names}"
        except Exception as e:
            return f"Epoching failed: {e!s}"
