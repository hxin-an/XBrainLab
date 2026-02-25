"""Raw data loader implementations for various EEG file formats.

Registers loader functions with :class:`RawDataLoaderFactory` for supported
formats including EEGLAB (.set), BIOSIG (.gdf), MNE (.fif), EDF (.edf),
BioSemi (.bdf), Neuroscan (.cnt), and BrainVision (.vhdr).
"""

import mne

from XBrainLab.backend.exceptions import FileCorruptedError
from XBrainLab.backend.load_data.factory import RawDataLoaderFactory
from XBrainLab.backend.utils.logger import logger

from .raw import Raw


def load_set_file(filepath):
    """Load an EEGLAB ``.set`` file and return a Raw wrapper.

    Attempts to load as continuous raw data first, falling back to epochs
    if the raw loader fails.

    Args:
        filepath: Path to the ``.set`` file.

    Returns:
        Raw object wrapping the loaded data, or None on failure.

    Raises:
        FileCorruptedError: If the file cannot be loaded as raw or epochs.
    """
    selected_data = None

    # Try loading as Raw first (default assumption for now)
    try:
        selected_data = mne.io.read_raw_eeglab(
            filepath, uint16_codec="latin1", preload=False
        )
    except TypeError:
        # Fallback to Epochs
        try:
            selected_data = mne.io.read_epochs_eeglab(filepath, uint16_codec="latin1")
        except Exception as e:
            logger.warning("Failed to load as Epochs: %s", e)
            raise FileCorruptedError(filepath, f"Failed to load as Epochs: {e}") from e
    except Exception as e:
        logger.warning("Failed to load as Raw: %s", e)
        # Try Epochs if Raw failed due to other reasons (e.g. ValueError)
        try:
            selected_data = mne.io.read_epochs_eeglab(filepath, uint16_codec="latin1")
        except Exception:
            raise FileCorruptedError(
                filepath, f"Failed to load as Raw or Epochs: {e}"
            ) from e

    if selected_data:
        # Wrap in XBrainLab Raw object
        raw_wrapper = Raw(filepath, selected_data)
        return raw_wrapper

    return None


def load_gdf_file(filepath):
    """Load a BIOSIG ``.gdf`` file and return a Raw wrapper.

    Args:
        filepath: Path to the ``.gdf`` file.

    Returns:
        Raw object wrapping the loaded data, or None on failure.

    Raises:
        FileCorruptedError: If loading fails.
    """
    try:
        # GDF is typically loaded as Raw
        selected_data = mne.io.read_raw_gdf(filepath, preload=False)

        if selected_data:
            # Wrap in XBrainLab Raw object
            raw_wrapper = Raw(filepath, selected_data)
            return raw_wrapper

    except Exception as e:
        logger.error("Failed to load GDF file %s: %s", filepath, e, exc_info=True)
        raise FileCorruptedError(filepath, str(e)) from e

    return None


def load_fif_file(filepath):
    """Load an MNE-Python native ``.fif`` file and return a Raw wrapper.

    Args:
        filepath: Path to the ``.fif`` file.

    Returns:
        Raw object wrapping the loaded data, or None on failure.

    Raises:
        FileCorruptedError: If loading fails.
    """
    try:
        selected_data = mne.io.read_raw_fif(filepath, preload=False)
        if selected_data:
            return Raw(filepath, selected_data)
    except Exception as e:
        logger.error("Failed to load FIF file %s: %s", filepath, e, exc_info=True)
        raise FileCorruptedError(filepath, str(e)) from e
    return None


def load_edf_file(filepath):
    """Load a European Data Format ``.edf`` file and return a Raw wrapper.

    Args:
        filepath: Path to the ``.edf`` file.

    Returns:
        Raw object wrapping the loaded data, or None on failure.

    Raises:
        FileCorruptedError: If loading fails.
    """
    try:
        selected_data = mne.io.read_raw_edf(filepath, preload=False)
        if selected_data:
            return Raw(filepath, selected_data)
    except Exception as e:
        logger.error("Failed to load EDF file %s: %s", filepath, e, exc_info=True)
        raise FileCorruptedError(filepath, str(e)) from e
    return None


def load_bdf_file(filepath):
    """Load a BioSemi ``.bdf`` file and return a Raw wrapper.

    Args:
        filepath: Path to the ``.bdf`` file.

    Returns:
        Raw object wrapping the loaded data, or None on failure.

    Raises:
        FileCorruptedError: If loading fails.
    """
    try:
        selected_data = mne.io.read_raw_bdf(filepath, preload=False)
        if selected_data:
            return Raw(filepath, selected_data)
    except Exception as e:
        logger.error("Failed to load BDF file %s: %s", filepath, e, exc_info=True)
        raise FileCorruptedError(filepath, str(e)) from e
    return None


def load_cnt_file(filepath):
    """Load a Neuroscan ``.cnt`` file and return a Raw wrapper.

    Args:
        filepath: Path to the ``.cnt`` file.

    Returns:
        Raw object wrapping the loaded data, or None on failure.

    Raises:
        FileCorruptedError: If loading fails.
    """
    try:
        selected_data = mne.io.read_raw_cnt(filepath, preload=False)
        if selected_data:
            return Raw(filepath, selected_data)
    except Exception as e:
        logger.error("Failed to load CNT file %s: %s", filepath, e, exc_info=True)
        raise FileCorruptedError(filepath, str(e)) from e
    return None


def load_brainvision_file(filepath):
    """Load a BrainVision ``.vhdr`` file and return a Raw wrapper.

    Args:
        filepath: Path to the ``.vhdr`` file.

    Returns:
        Raw object wrapping the loaded data, or None on failure.

    Raises:
        FileCorruptedError: If loading fails.
    """
    try:
        selected_data = mne.io.read_raw_brainvision(filepath, preload=False)
        if selected_data:
            return Raw(filepath, selected_data)
    except Exception as e:
        logger.error(
            "Failed to load BrainVision file %s: %s", filepath, e, exc_info=True
        )
        raise FileCorruptedError(filepath, str(e)) from e
    return None


# Register loaders
RawDataLoaderFactory.register_loader(".set", load_set_file)
RawDataLoaderFactory.register_loader(".gdf", load_gdf_file)
RawDataLoaderFactory.register_loader(".fif", load_fif_file)
RawDataLoaderFactory.register_loader(".edf", load_edf_file)
RawDataLoaderFactory.register_loader(".bdf", load_bdf_file)
RawDataLoaderFactory.register_loader(".cnt", load_cnt_file)
RawDataLoaderFactory.register_loader(".vhdr", load_brainvision_file)


def load_raw_data(filepath: str) -> Raw:
    """Load raw EEG data from file using the registered factory.

    Args:
        filepath: Path to the data file.

    Returns:
        Raw wrapper containing the loaded data.

    Raises:
        ValueError: If loading returns None.
        UnsupportedFormatError: If the file format is not registered.
        FileCorruptedError: If the file is corrupted or unreadable.
    """
    raw = RawDataLoaderFactory.load(filepath)
    if raw is None:
        raise ValueError(f"Failed to load raw data from {filepath}")
    return raw
