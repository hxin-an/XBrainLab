"""Data loading package for importing raw EEG data, events, and labels."""

from enum import Enum

from . import (
    raw_data_loader,  # noqa: F401 (Import for side effects: registering loaders)
)
from .data_loader import RawDataLoader
from .event_loader import EventLoader
from .raw import Raw


class DataType(Enum):
    """Enumeration of supported data types.

    Attributes:
        RAW: Unsegmented continuous raw data.
        EPOCH: Segmented epoch data.
    """

    RAW = "raw"
    EPOCH = "epochs"


__all__ = ["DataType", "EventLoader", "Raw", "RawDataLoader"]
