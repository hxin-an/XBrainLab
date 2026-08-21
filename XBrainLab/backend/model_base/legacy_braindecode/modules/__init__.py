"""Reviewed neural-network primitives for the baseline legacy family."""

from .activation import LogActivation, SafeLog, Square
from .blocks import InceptionBlock
from .convolution import (
    AvgPool2dWithConv,
    CombinedConv,
    Conv2dWithConstraint,
    DepthwiseConv2d,
)
from .layers import Ensure4d, SqueezeFinalOutput
from .linear import LinearWithConstraint
from .wrapper import Expression

__all__ = [
    "AvgPool2dWithConv",
    "CombinedConv",
    "Conv2dWithConstraint",
    "DepthwiseConv2d",
    "Ensure4d",
    "Expression",
    "InceptionBlock",
    "LinearWithConstraint",
    "LogActivation",
    "SafeLog",
    "Square",
    "SqueezeFinalOutput",
]
