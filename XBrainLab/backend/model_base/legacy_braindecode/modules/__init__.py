"""Reviewed neural-network primitives for the baseline legacy family."""

from .activation import LogActivation, SafeLog, Square
from .blocks import InceptionBlock
from .convolution import (
    AvgPool2dWithConv,
    CausalConv1d,
    CombinedConv,
    Conv2dWithConstraint,
    DepthwiseConv2d,
)
from .filter import FilterBankLayer
from .layers import Chomp1d, Ensure4d, SqueezeFinalOutput
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
    "AvgPool2dWithConv",
    "CausalConv1d",
    "Chomp1d",
    "CombinedConv",
    "Conv2dWithConstraint",
    "DepthwiseConv2d",
    "Ensure4d",
    "Expression",
    "FilterBankLayer",
    "InceptionBlock",
    "LinearWithConstraint",
    "LogActivation",
    "LogPowerLayer",
    "LogVarLayer",
    "MaxLayer",
    "MaxNormLinear",
    "MaxNormParametrize",
    "MeanLayer",
    "SafeLog",
    "Square",
    "SqueezeFinalOutput",
    "StatLayer",
    "StdLayer",
    "VarLayer",
]
