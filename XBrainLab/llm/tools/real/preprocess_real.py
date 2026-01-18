from typing import Any

from XBrainLab.backend.preprocessor.channel_selection import ChannelSelection

# Need backend classes
from XBrainLab.backend.preprocessor.filtering import Filtering
from XBrainLab.backend.preprocessor.normalize import Normalize
from XBrainLab.backend.preprocessor.rereference import Rereference
from XBrainLab.backend.preprocessor.resample import Resample

# SetMontage might be specialized
# Epoching
from XBrainLab.backend.preprocessor.time_epoch import TimeEpoch
from XBrainLab.backend.utils.mne_helper import get_montage_positions

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
        rereference: str | None = None,
        resample_rate: int | None = None,
        normalize_method: str = "z-score",
        **kwargs,
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

        except Exception as e:
            return f"Preprocessing failed: {e!s}"

        return "Standard preprocessing applied successfully."


class RealBandPassFilterTool(BaseBandPassFilterTool):
    def execute(
        self,
        study: Any,
        low_freq: float | None = None,
        high_freq: float | None = None,
        **kwargs,
    ) -> str:
        if low_freq is None or high_freq is None:
            return "Error: low_freq and high_freq are required."
        study.preprocess(Filtering, l_freq=low_freq, h_freq=high_freq)
        return f"Applied Bandpass Filter ({low_freq}-{high_freq} Hz)"


class RealNotchFilterTool(BaseNotchFilterTool):
    def execute(self, study: Any, freq: float | None = None, **kwargs) -> str:
        if freq is None:
            return "Error: freq is required."
        # Notch filter uses Filtering class but requires l_freq/h_freq not to crash
        study.preprocess(Filtering, notch_freqs=freq, l_freq=None, h_freq=None)
        return f"Applied Notch Filter ({freq} Hz)"


class RealResampleTool(BaseResampleTool):
    def execute(self, study: Any, rate: int | None = None, **kwargs) -> str:
        if rate is None:
            return "Error: rate is required."
        study.preprocess(Resample, sfreq=rate)
        return f"Resampled data to {rate} Hz"


class RealNormalizeTool(BaseNormalizeTool):
    def execute(self, study: Any, method: str | None = None, **kwargs) -> str:
        if method is None:
            return "Error: method is required."
        study.preprocess(Normalize, norm=method)
        return f"Normalized data using {method}"


class RealRereferenceTool(BaseRereferenceTool):
    def execute(self, study: Any, method: str | None = None, **kwargs) -> str:
        if method is None:
            return "Error: method is required."
        # Backend expects 'ref_channels'
        # 'CAR', 'average' -> 'average'
        ref = "average" if method.lower() in ["car", "average"] else [method]

        study.preprocess(Rereference, ref_channels=ref)
        return f"Applied reference: {method}"


class RealChannelSelectionTool(BaseChannelSelectionTool):
    def execute(self, study: Any, channels: list[str] | None = None, **kwargs) -> str:
        if channels is None:
            return "Error: channels list is required."
        study.preprocess(ChannelSelection, selected_channels=channels)
        return f"Selected {len(channels)} channels."


class RealSetMontageTool(BaseSetMontageTool):
    def execute(self, study: Any, montage_name: str | None = None, **kwargs) -> str:
        if montage_name is None:
            return "Error: montage_name is required."
        # Backend requires epoch data for set_channels currently
        if not study.epoch_data:
            return "Error: Epoch data must be generated before setting montage."

        try:
            # Get Standard Positions
            # {'ch_pos': {name: array, ...}}
            loaded_positions = get_montage_positions(montage_name)
            if not loaded_positions:
                return f"Error: Failed to load montage '{montage_name}'"

            ch_pos_dict = loaded_positions["ch_pos"]

            # Map Dataset Channels to Positions
            # Currently loaded/selected channels
            current_chs = study.epoch_data.get_mne().info["ch_names"]

            mapped_chs = []
            mapped_positions = []

            # Simple Case Insensitive / Clean Match Logic
            montage_lookup = {k.lower(): k for k in ch_pos_dict}

            for ch in current_chs:
                # heuristic breakdown
                clean_ch = (
                    ch.lower()
                    .replace("eeg", "")
                    .replace("ref", "")
                    .replace("-", "")
                    .strip()
                )

                real_name = None
                if ch.lower() in montage_lookup:
                    real_name = montage_lookup[ch.lower()]
                elif clean_ch in montage_lookup:
                    real_name = montage_lookup[clean_ch]

                if real_name:
                    mapped_chs.append(ch)
                    # Convert array to tuple if needed, backend expects tuple (x,y,z)?
                    # study.set_channels doc says "List of channel positions.
                    # Should be tuple of (x, y, z)."
                    # mne returns arrays.
                    mapped_positions.append(tuple(ch_pos_dict[real_name]))

            if not mapped_chs:
                # If automated matching completely fails, request user intervention
                return f"Request: Verify Montage '{montage_name}'"

            # Check for partial match (optional, but good for robustness)
            if len(mapped_chs) < len(current_chs):
                # Partial match detected. Per "Human-in-the-loop" requirement, request
                # user verification.
                return (
                    f"Request: Verify Montage '{montage_name}' "
                    f"(Only {len(mapped_chs)}/{len(current_chs)} channels matched)"
                )

            study.set_channels(mapped_chs, mapped_positions)
            return f"Set Montage '{montage_name}' (Matched {len(mapped_chs)} channels)"

        except Exception as e:
            return f"SetMontage failed: {e!s}"


class RealEpochDataTool(BaseEpochDataTool):
    def execute(
        self,
        study: Any,
        t_min: float = -0.1,
        t_max: float = 1.0,
        event_id: Any = None,
        baseline: list[float] | None = None,
        **kwargs,
    ) -> str:
        try:
            # Check arguments mapping to TimeEpoch constructor
            # Backend TimeEpoch._data_preprocess signature:
            # (self, preprocessed_data: Raw, baseline: list, selected_event_names: list,
            #  tmin: float, tmax: float)

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
            # Note: arguments must match _data_preprocess signature exactly
            # if passed via **kargs
            study.preprocess(
                TimeEpoch,
                tmin=t_min,
                tmax=t_max,
                selected_event_names=selected_names,
                baseline=list(baseline) if baseline else None,
            )
        except Exception as e:
            return f"Epoching failed: {e!s}"

        return f"Data epoched: [{t_min}, {t_max}]s. Events: {selected_names}"
