import mne
from XBrainLab.load_data import Raw, DataType
from XBrainLab.utils.logger import logger

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
