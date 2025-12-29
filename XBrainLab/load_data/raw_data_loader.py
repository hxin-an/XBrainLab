import mne
import os
from XBrainLab.load_data import Raw, DataType
from XBrainLab.utils.logger import logger

def load_set_file(filepath):
    """
    Load .set file (EEGLAB) and return a XBrainLab Raw object.
    Mimics logic from XBrainLab.ui.load_data.set.LoadSet._load
    """
    data_type = None
    selected_data = None
    
    # Try loading as Raw first (default assumption for now)
    try:
        selected_data = mne.io.read_raw_eeglab(
            filepath, uint16_codec='latin1', preload=True
        )
        data_type = DataType.RAW.value
    except TypeError:
        # Fallback to Epochs
        try:
            selected_data = mne.io.read_epochs_eeglab(
                filepath, uint16_codec='latin1'
            )
            data_type = DataType.EPOCH.value
        except Exception as e:
            logger.warning(f"Failed to load as Epochs: {e}")
            return None
    except Exception as e:
        logger.warning(f"Failed to load as Raw: {e}")
        # Try Epochs if Raw failed due to other reasons (e.g. ValueError)
        try:
            selected_data = mne.io.read_epochs_eeglab(
                filepath, uint16_codec='latin1'
            )
            data_type = DataType.EPOCH.value
        except Exception:
            return None

    if selected_data:
        # Wrap in XBrainLab Raw object
        raw_wrapper = Raw(filepath, selected_data)
        return raw_wrapper
    
    return None

def load_gdf_file(filepath):
    """
    Load .gdf file (BIOSIG) and return a XBrainLab Raw object.
    """
    try:
        # GDF is typically loaded as Raw
        selected_data = mne.io.read_raw_gdf(filepath, preload=True)
        
        if selected_data:
            # Wrap in XBrainLab Raw object
            raw_wrapper = Raw(filepath, selected_data)
            return raw_wrapper
            
    except Exception as e:
        logger.error(f"Failed to load GDF file {filepath}: {e}", exc_info=True)
        return None
    
    return None
