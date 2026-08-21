"""Reviewed neural-network primitives used by legacy model families."""

from .activation import LogActivation, SafeLog, Square
from .attention import (
    CAT,
    CBAM,
    ECA,
    FCA,
    GCT,
    SRM,
    CATLite,
    CrissCrossTransformerEncoderLayer,
    EncNet,
    GatherExcite,
    GSoP,
    MultiHeadAttention,
    SqueezeAndExcitation,
)
from .blocks import FeedForwardBlock, InceptionBlock, PatchTokenizer
from .convolution import (
    AvgPool2dWithConv,
    CausalConv1d,
    CombinedConv,
    Conv1dWithConstraint,
    Conv2dWithConstraint,
    DepthwiseConv2d,
)
from .filter import FilterBankLayer
from .layers import Chomp1d, DropPath, Ensure4d, SqueezeFinalOutput
from .linear import LinearWithConstraint, MaxNormLinear
from .parametrization import MaxNormParametrize
from .stats import (
    LogPowerLayer,
    LogVarLayer,
    MaxLayer,
    MeanLayer,
    StatLayer,
    StdLayer,
    VarLayer,
)
from .wrapper import Expression

__all__ = [
    "CAT",
    "CBAM",
    "ECA",
    "FCA",
    "GCT",
    "SRM",
    "AvgPool2dWithConv",
    "CATLite",
    "CausalConv1d",
    "Chomp1d",
    "CombinedConv",
    "Conv1dWithConstraint",
    "Conv2dWithConstraint",
    "CrissCrossTransformerEncoderLayer",
    "DepthwiseConv2d",
    "DropPath",
    "EncNet",
    "Ensure4d",
    "Expression",
    "FeedForwardBlock",
    "FilterBankLayer",
    "GSoP",
    "GatherExcite",
    "InceptionBlock",
    "LinearWithConstraint",
    "LogActivation",
    "LogPowerLayer",
    "LogVarLayer",
    "MaxLayer",
    "MaxNormLinear",
    "MaxNormParametrize",
    "MeanLayer",
    "MultiHeadAttention",
    "PatchTokenizer",
    "SafeLog",
    "Square",
    "SqueezeAndExcitation",
    "SqueezeFinalOutput",
    "StatLayer",
    "StdLayer",
    "VarLayer",
]
