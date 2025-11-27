from .base import DataType
from .cnt import LoadCnt
from .edf import LoadEdf
from .mat import LoadMat
from .np import LoadNp
from .set import LoadSet
from .auto_cnt import AutoCnt
from .auto_edf import AutoEdf
from .auto_mat import AutoMat
from .auto_np import AutoNp
from .auto_set import AutoSet

IMPORT_TYPE_MODULE_LIST = [LoadSet, LoadMat, LoadEdf, LoadCnt, LoadNp]

__all__ = [
    'DataType', 'IMPORT_TYPE_MODULE_LIST',
    'LoadSet', 'LoadMat', 'LoadEdf', 'LoadCnt', 'LoadNp',
    'AutoSet', 'AutoMat', 'AutoEdf', 'AutoCnt', 'AutoNp'
]
