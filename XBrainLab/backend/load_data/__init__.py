from enum import Enum

from .data_loader import RawDataLoader
from .event_loader import EventLoader
from .raw import Raw


class DataType(Enum):
    RAW = 'raw'
    EPOCH = 'epochs'

__all__ = [
    'Raw',
    'RawDataLoader',
    'EventLoader',
    'DataType'
]
