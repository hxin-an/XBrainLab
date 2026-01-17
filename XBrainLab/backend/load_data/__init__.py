from enum import Enum

from . import (
    raw_data_loader,  # noqa: F401 (Import for side effects: registering loaders)
)
from .data_loader import RawDataLoader
from .event_loader import EventLoader
from .raw import Raw


class DataType(Enum):
    RAW = "raw"
    EPOCH = "epochs"


__all__ = ["DataType", "EventLoader", "Raw", "RawDataLoader"]
