# License: BSD-3-Clause
"""Baseline convolution primitives adapted from Braindecode 1.6.1."""

import numpy as np
import torch
from torch import nn
from torch.nn import functional
from torch.nn.utils.parametrize import register_parametrization

from ..util import np_to_th
from .parametrization import MaxNormParametrize


class AvgPool2dWithConv(nn.Module):
    """Compute average pooling as a grouped convolution with dilation."""

    def __init__(self, kernel_size, stride, dilation=1, padding=0):
        super().__init__()
        self.kernel_size = kernel_size
        self.stride = stride
        self.dilation = dilation
        self.padding = padding
        self._pool_weights = None

    def forward(self, x):
        in_channels = x.size()[1]
        weight_shape = (
            in_channels,
            1,
            self.kernel_size[0],
            self.kernel_size[1],
        )
        if self._pool_weights is None or (
            tuple(self._pool_weights.size()) != tuple(weight_shape)
            or self._pool_weights.is_cuda != x.is_cuda
            or self._pool_weights.data.type() != x.data.type()
        ):
            n_pool = np.prod(self.kernel_size)
            weights = np_to_th(np.ones(weight_shape, dtype=np.float32) / float(n_pool))
            weights = weights.type_as(x)
            if x.is_cuda:
                weights = weights.cuda()
            self._pool_weights = weights

        return functional.conv2d(
            x,
            self._pool_weights,
            bias=None,
            stride=self.stride,
            dilation=self.dilation,
            padding=self.padding,
            groups=in_channels,
        )


class Conv2dWithConstraint(nn.Conv2d):
    """Two-dimensional convolution with max-norm parametrization."""

    def __init__(self, *args, max_norm=1, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_norm = max_norm
        nn.init.xavier_uniform_(self.weight, gain=1)
        register_parametrization(self, "weight", MaxNormParametrize(self.max_norm))


class CombinedConv(nn.Module):
    """Merge temporal and spatial convolution weights at forward time."""

    def __init__(
        self,
        in_chans,
        n_filters_time=40,
        n_filters_spat=40,
        filter_time_length=25,
        bias_time=True,
        bias_spat=True,
    ):
        super().__init__()
        self.bias_time = bias_time
        self.bias_spat = bias_spat
        self.conv_time = nn.Conv2d(
            1, n_filters_time, (filter_time_length, 1), bias=bias_time, stride=1
        )
        self.conv_spat = nn.Conv2d(
            n_filters_time,
            n_filters_spat,
            (1, in_chans),
            bias=bias_spat,
            stride=1,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        combined_weight = (
            (self.conv_time.weight * self.conv_spat.weight.permute(1, 0, 2, 3))
            .sum(0)
            .unsqueeze(1)
        )

        calculated_bias: torch.Tensor | None = None
        if self.bias_time:
            time_bias = self.conv_time.bias
            if time_bias is None:
                raise RuntimeError("conv_time.bias is None despite bias_time=True")
            calculated_bias = (
                self.conv_spat.weight.squeeze()
                .sum(-1)
                .mm(time_bias.unsqueeze(-1))
                .squeeze()
            )
        if self.bias_spat:
            spatial_bias = self.conv_spat.bias
            if spatial_bias is None:
                raise RuntimeError("conv_spat.bias is None despite bias_spat=True")
            calculated_bias = (
                spatial_bias
                if calculated_bias is None
                else calculated_bias + spatial_bias
            )

        return functional.conv2d(
            x,
            weight=combined_weight,
            bias=calculated_bias,
            stride=(1, 1),
        )


class CausalConv1d(nn.Conv1d):
    """One-dimensional convolution padded and cropped to preserve causality."""

    def __init__(
        self,
        in_channels,
        out_channels,
        kernel_size,
        dilation=1,
        **kwargs,
    ):
        if "padding" in kwargs:
            raise ValueError(
                "The padding parameter is controlled internally by "
                f"{type(self).__name__}."
            )
        super().__init__(
            in_channels=in_channels,
            out_channels=out_channels,
            kernel_size=kernel_size,
            dilation=dilation,
            padding=(kernel_size - 1) * dilation,
            **kwargs,
        )

    def forward(self, inputs):
        output = functional.conv1d(
            inputs,
            self.weight,
            self.bias,
            stride=self.stride,
            padding=self.padding,
            dilation=self.dilation,
            groups=self.groups,
        )
        return output[..., : -self.padding[0]]


class DepthwiseConv2d(nn.Conv2d):
    """Depthwise convolution with an explicit channel multiplier."""

    def __init__(
        self,
        in_channels,
        depth_multiplier=2,
        kernel_size=3,
        stride=1,
        padding=0,
        dilation=1,
        bias=True,
        padding_mode="zeros",
    ):
        super().__init__(
            in_channels=in_channels,
            out_channels=in_channels * depth_multiplier,
            kernel_size=kernel_size,
            stride=stride,
            padding=padding,
            dilation=dilation,
            groups=in_channels,
            bias=bias,
            padding_mode=padding_mode,
        )
