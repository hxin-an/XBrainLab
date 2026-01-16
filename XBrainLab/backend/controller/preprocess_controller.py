from XBrainLab.backend import preprocessor as Preprocessor
from XBrainLab.backend.utils.logger import logger
import copy

class PreprocessController:
    """
    Controller for managing preprocessing operations.
    Handles Filtering, Resampling, Re-referencing, Normalization, and Epoching.
    """
    def __init__(self, study):
        self.study = study

    def get_preprocessed_data_list(self):
        """Returns the list of currently preprocessed data objects."""
        return self.study.preprocessed_data_list

    def reset_preprocess(self):
        """Resets all preprocessing to raw state."""
        self.study.reset_preprocess(force_update=True)

    def is_epoched(self):
        """Checks if the data is currently epoched."""
        data_list = self.study.preprocessed_data_list
        if data_list:
            return not data_list[0].is_raw()
        return False

    def has_data(self):
        return bool(self.study.preprocessed_data_list)

    def get_channel_names(self):
        if self.study.preprocessed_data_list:
            return self.study.preprocessed_data_list[0].get_mne().ch_names
        return []

    def get_first_data(self):
        if self.study.preprocessed_data_list:
            return self.study.preprocessed_data_list[0]
        return None

    def _apply_processor(self, processor_class, *args, **kwargs):
        """Helper to apply a processor and update study."""
        data_list = self.study.preprocessed_data_list
        if not data_list:
            raise ValueError("No data to preprocess.")
            
        processor = processor_class(data_list)
        try:
            result = processor.data_preprocess(*args, **kwargs)
            self.study.set_preprocessed_data_list(result)
            return True
        except Exception as e:
            logger.error(f"Preprocessing failed: {e}")
            raise e

    def apply_filter(self, l_freq, h_freq, notch_freqs=None):
        return self._apply_processor(Preprocessor.Filtering, l_freq, h_freq, notch_freqs=notch_freqs)

    def apply_resample(self, sfreq):
        return self._apply_processor(Preprocessor.Resample, sfreq)

    def apply_rereference(self, ref_channels):
        return self._apply_processor(Preprocessor.Rereference, ref_channels=ref_channels)

    def apply_normalization(self, method):
        return self._apply_processor(Preprocessor.Normalize, norm=method)

    def get_unique_events(self):
        """Returns unique events across all files."""
        events = set()
        for data in self.study.preprocessed_data_list:
            try:
                evs, ev_ids = data.get_event_list()
                if ev_ids:
                    events.update(ev_ids.keys())
            except:
                pass
        return sorted(list(events))

    def apply_epoching(self, baseline, selected_events, tmin, tmax):
        result = self._apply_processor(Preprocessor.TimeEpoch, baseline, selected_events, tmin, tmax)
        if result:
            self.study.lock_dataset()
        return result
