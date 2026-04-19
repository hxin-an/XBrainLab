"""Raw data loader implementations for various EEG file formats.

Registers loader functions with :class:`RawDataLoaderFactory` for supported
formats including EEGLAB (.set), BIOSIG (.gdf), MNE (.fif), EDF (.edf),
BioSemi (.bdf), Neuroscan (.cnt), and BrainVision (.vhdr).
"""

import re
import warnings

import mne

from XBrainLab.backend.exceptions import FileCorruptedError
from XBrainLab.backend.load_data.factory import RawDataLoaderFactory
from XBrainLab.backend.utils.logger import logger

from .raw import Raw

_DUPLICATE_GDF_CHANNEL_WARNING = "Channel names are not unique"
_RUNNING_NUMBER_SUFFIX = re.compile(r"^(?P<base>.+)-(?P<index>\d+)$")


def _reemit_captured_warnings(caught_warnings):
    """Re-emit warnings captured around a loader call.

    This lets the loader inspect runtime warnings for richer repo-specific
    diagnostics without suppressing the original MNE warning surface.
    """

    for caught_warning in caught_warnings:
        warnings.warn_explicit(
            message=caught_warning.message,
            category=caught_warning.category,
            filename=caught_warning.filename,
            lineno=caught_warning.lineno,
        )


def _get_running_number_bases(channel_names):
    """Return bases that look auto-renamed via ``name-0``, ``name-1`` patterns."""

    suffixes_by_base = {}
    for channel_name in channel_names:
        match = _RUNNING_NUMBER_SUFFIX.match(channel_name)
        if not match:
            continue
        suffixes_by_base.setdefault(match.group("base"), set()).add(
            int(match.group("index")),
        )

    return sorted(
        base
        for base, suffixes in suffixes_by_base.items()
        if len(suffixes) >= 2 and min(suffixes) == 0
    )


def _get_generated_channel_names(channel_names, generated_bases):
    """Return generated channel names derived from auto-renamed duplicate bases."""

    if not generated_bases:
        return []

    generated_base_set = set(generated_bases)
    generated_names = []
    for channel_name in channel_names:
        match = _RUNNING_NUMBER_SUFFIX.match(channel_name)
        if match and match.group("base") in generated_base_set:
            generated_names.append(channel_name)
    return generated_names


def _build_gdf_channel_name_detail(filepath, selected_data, caught_warnings):
    """Return repo-specific context when MNE auto-renames duplicate GDF channels."""

    if not any(
        _DUPLICATE_GDF_CHANNEL_WARNING in str(caught_warning.message)
        for caught_warning in caught_warnings
    ):
        return None

    channel_names = selected_data.info.get("ch_names", [])
    generated_bases = _get_running_number_bases(channel_names)
    generated_channels = _get_generated_channel_names(channel_names, generated_bases)
    if generated_bases:
        message = (
            f"GDF import for {filepath} relied on MNE auto-renaming duplicate "
            f"channel names for base names {generated_bases}; channel-sensitive "
            "workflows may be unreliable until names are normalized or handled "
            "explicitly."
        )
    else:
        message = (
            f"GDF import for {filepath} relied on MNE auto-renaming duplicate "
            "channel names; channel-sensitive workflows may be unreliable until "
            "names are normalized or handled explicitly."
        )

    return {
        "kind": "gdf_duplicate_channel_names",
        "filepath": filepath,
        "generated_bases": generated_bases,
        "generated_channels": generated_channels,
        "message": message,
    }


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
            filepath,
            uint16_codec="latin1",
            preload=False,
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
                filepath,
                f"Failed to load as Raw or Epochs: {e}",
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
        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            selected_data = mne.io.read_raw_gdf(filepath, preload=False)

        _reemit_captured_warnings(caught_warnings)
        channel_name_detail = _build_gdf_channel_name_detail(
            filepath,
            selected_data,
            caught_warnings,
        )
        if channel_name_detail:
            logger.warning("%s", channel_name_detail["message"])

        if selected_data:
            # Wrap in XBrainLab Raw object
            raw_wrapper = Raw(filepath, selected_data)
            if channel_name_detail:
                raw_wrapper.add_runtime_signal(channel_name_detail["message"])
                raw_wrapper.set_runtime_detail(
                    "gdf_duplicate_channel_names",
                    channel_name_detail,
                )
            return raw_wrapper

    except Exception as e:
        logger.error("Failed to load GDF file %s: %s", filepath, e, exc_info=True)
        raise FileCorruptedError(filepath, str(e)) from e

    return None


def load_fif_file(filepath):
    """Load an MNE-Python native ``.fif`` file and return a Raw wrapper.

    Attempts to load as continuous raw data first, falling back to epochs
    if the raw loader fails.

    Args:
        filepath: Path to the ``.fif`` file.

    Returns:
        Raw object wrapping the loaded data, or None on failure.

    Raises:
        FileCorruptedError: If loading fails as both raw and epochs.

    """
    selected_data = None

    try:
        selected_data = mne.io.read_raw_fif(filepath, preload=False)
    except TypeError:
        try:
            selected_data = mne.read_epochs(filepath, preload=False)
        except Exception as e:
            logger.warning("Failed to load FIF as Epochs: %s", e)
            raise FileCorruptedError(
                filepath,
                f"Failed to load FIF as Epochs: {e}",
            ) from e
    except Exception as e:
        logger.warning("Failed to load FIF as Raw: %s", e)
        try:
            selected_data = mne.read_epochs(filepath, preload=False)
        except Exception:
            logger.error("Failed to load FIF file %s: %s", filepath, e, exc_info=True)
            raise FileCorruptedError(
                filepath,
                f"Failed to load FIF as Raw or Epochs: {e}",
            ) from e

    if selected_data:
        return Raw(filepath, selected_data)
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
            "Failed to load BrainVision file %s: %s",
            filepath,
            e,
            exc_info=True,
        )
        raise FileCorruptedError(filepath, str(e)) from e
    return None


# Register loaders
RawDataLoaderFactory.register_loader(".set", load_set_file)
RawDataLoaderFactory.register_loader(".gdf", load_gdf_file)
RawDataLoaderFactory.register_loader(".fif", load_fif_file)
RawDataLoaderFactory.register_loader(".fif.gz", load_fif_file)
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
