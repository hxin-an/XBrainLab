
import mne

from XBrainLab.backend.exceptions import FileCorruptedError
from XBrainLab.backend.load_data import DataType, Raw
from XBrainLab.backend.load_data.factory import RawDataLoaderFactory
from XBrainLab.backend.utils.logger import logger


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
            filepath, uint16_codec='latin1', preload=False
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
            raise FileCorruptedError(filepath, f"Failed to load as Epochs: {e}")
    except Exception as e:
        logger.warning(f"Failed to load as Raw: {e}")
        # Try Epochs if Raw failed due to other reasons (e.g. ValueError)
        try:
            selected_data = mne.io.read_epochs_eeglab(
                filepath, uint16_codec='latin1'
            )
            data_type = DataType.EPOCH.value
        except Exception:
             raise FileCorruptedError(filepath, f"Failed to load as Raw or Epochs: {e}")

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
        selected_data = mne.io.read_raw_gdf(filepath, preload=False)

        if selected_data:
            # Wrap in XBrainLab Raw object
            raw_wrapper = Raw(filepath, selected_data)
            return raw_wrapper

    except Exception as e:
        logger.error(f"Failed to load GDF file {filepath}: {e}", exc_info=True)
        raise FileCorruptedError(filepath, str(e))

    return None

def load_fif_file(filepath):
    """
    Load .fif file (MNE-Python native) and return a XBrainLab Raw object.
    """
    try:
        selected_data = mne.io.read_raw_fif(filepath, preload=False)
        if selected_data:
            return Raw(filepath, selected_data)
    except Exception as e:
        logger.error(f"Failed to load FIF file {filepath}: {e}", exc_info=True)
        raise FileCorruptedError(filepath, str(e))
    return None

def load_edf_file(filepath):
    """
    Load .edf file (European Data Format) and return a XBrainLab Raw object.
    """
    try:
        selected_data = mne.io.read_raw_edf(filepath, preload=False)
        if selected_data:
            return Raw(filepath, selected_data)
    except Exception as e:
        logger.error(f"Failed to load EDF file {filepath}: {e}", exc_info=True)
        raise FileCorruptedError(filepath, str(e))
    return None

def load_bdf_file(filepath):
    """
    Load .bdf file (BioSemi) and return a XBrainLab Raw object.
    """
    try:
        selected_data = mne.io.read_raw_bdf(filepath, preload=False)
        if selected_data:
            return Raw(filepath, selected_data)
    except Exception as e:
        logger.error(f"Failed to load BDF file {filepath}: {e}", exc_info=True)
        raise FileCorruptedError(filepath, str(e))
    return None

def load_cnt_file(filepath):
    """
    Load .cnt file (Neuroscan) and return a XBrainLab Raw object.
    """
    try:
        selected_data = mne.io.read_raw_cnt(filepath, preload=False)
        if selected_data:
            return Raw(filepath, selected_data)
    except Exception as e:
        logger.error(f"Failed to load CNT file {filepath}: {e}", exc_info=True)
        raise FileCorruptedError(filepath, str(e))
    return None

def load_brainvision_file(filepath):
    """
    Load .vhdr file (BrainVision) and return a XBrainLab Raw object.
    """
    try:
        selected_data = mne.io.read_raw_brainvision(filepath, preload=False)
        if selected_data:
            return Raw(filepath, selected_data)
    except Exception as e:
        logger.error(f"Failed to load BrainVision file {filepath}: {e}", exc_info=True)
        raise FileCorruptedError(filepath, str(e))
    return None

# Register loaders
RawDataLoaderFactory.register_loader('.set', load_set_file)
RawDataLoaderFactory.register_loader('.gdf', load_gdf_file)
RawDataLoaderFactory.register_loader('.fif', load_fif_file)
RawDataLoaderFactory.register_loader('.edf', load_edf_file)
RawDataLoaderFactory.register_loader('.bdf', load_bdf_file)
RawDataLoaderFactory.register_loader('.cnt', load_cnt_file)
RawDataLoaderFactory.register_loader('.vhdr', load_brainvision_file)

def load_raw_data(filepath: str) -> Raw:
    """
    Load raw data from file using the factory.
    """
    return RawDataLoaderFactory.load(filepath)
