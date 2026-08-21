# ruff: noqa: N812, RUF046
# Authors: Robin Schirrmeister <robintibor@gmail.com>
#          Bruno Aristimunha <b.aristimunha@gmail.com>
#
# License: BSD (3-clause)

from __future__ import annotations

import math

import numpy as np
import torch
import torch.nn.functional as F


def square(x):
    return x * x


def safe_log(x, eps: float = 1e-6) -> torch.Tensor:
    """Prevents :math:`log(0)` by using :math:`log(max(x, eps))`."""
    return torch.log(torch.clamp(x, min=eps))


def drop_path(
    x,
    drop_prob: float | None = 0.0,
    training: bool = False,
    scale_by_keep: bool = True,
):
    """Drop paths (Stochastic Depth) per sample.

    Notes: This implementation is taken from timm library.

    All credit goes to Ross Wightman.

    Parameters
    ----------
    x : torch.Tensor
        input tensor
    drop_prob : float, optional
        survival rate (i.e. probability of being kept), by default 0.0
    training : bool, optional
        whether the model is in training mode, by default False
    scale_by_keep : bool, optional
        whether to scale output by (1/keep_prob) during training, by default True

    Returns
    -------
    torch.Tensor
        output tensor

    Notes from Ross Wightman:
    (when applied in main path of residual blocks)
    This is the same as the DropConnect impl I created for EfficientNet,
    etc. networks, however,
    the original name is misleading as 'Drop Connect' is a different form
    of dropout in a separate paper...
    See discussion : https://github.com/tensorflow/tpu/issues/494#issuecomment-532968956
    ... I've opted for changing the layer and argument names to 'drop path'
    rather than mix DropConnect as a layer name and use
    'survival rate' as the argument.
    """
    if drop_prob is None or drop_prob == 0.0 or not training:
        return x
    keep_prob = 1 - drop_prob
    shape = (x.shape[0],) + (1,) * (
        x.ndim - 1
    )  # work with diff dim tensors, not just 2D ConvNets
    random_tensor = x.new_empty(shape).bernoulli_(keep_prob)
    if keep_prob > 0.0 and scale_by_keep:
        random_tensor.div_(keep_prob)
    return x * random_tensor


def _get_gaussian_kernel1d(kernel_size: int, sigma: float) -> torch.Tensor:
    """
    Generates a 1-dimensional Gaussian kernel based on the specified kernel.

    size and standard deviation (sigma).
    This kernel is useful for Gaussian smoothing or filtering operations in
    image processing. The function calculates a range limit to ensure the kernel
    effectively covers the Gaussian distribution. It generates a tensor of
    specified size and type, filled with values distributed according to a
    Gaussian curve, normalized using a softmax function
    to ensure all weights sum to 1.

    Parameters
    ----------
    kernel_size : int
    sigma : float

    Returns
    -------
    kernel1d : torch.Tensor

    Notes
    -----
    Code copied and modified from TorchVision:
    https://github.com/pytorch/vision/blob/main/torchvision/transforms/_functional_tensor.py#L725-L732
    All rights reserved.

    LICENSE in https://github.com/pytorch/vision/blob/main/LICENSE
    """
    ksize_half = (kernel_size - 1) * 0.5
    x = torch.linspace(-ksize_half, ksize_half, steps=kernel_size)
    pdf = torch.exp(-0.5 * (x / sigma).pow(2))
    kernel1d = pdf / pdf.sum()
    return kernel1d


def daubechies_filters(n_vanishing: int) -> torch.Tensor:
    r"""Daubechies ``db<n_vanishing>`` wavelet decomposition filters.

    Computes the orthogonal decomposition (analysis) low-pass and high-pass
    filters by spectral factorisation of the Daubechies half-band (Bezout)
    polynomial, so no external wavelet library (PyWavelets, ptwt) is required.
    For ``n_vanishing=4`` the result equals ``pywt.Wavelet("db4").dec_lo`` /
    ``.dec_hi`` to machine precision (bit-identical once cast to ``float32``).

    Parameters
    ----------
    n_vanishing : int
        Number of vanishing moments (the ``N`` in ``dbN``). The filters have
        ``2 * n_vanishing`` taps.

    Returns
    -------
    torch.Tensor
        Shape ``(2, 2 * n_vanishing)`` whose rows are the low-pass and high-pass
        decomposition filters ``[dec_lo, dec_hi]``.

    Notes
    -----
    Half-band polynomial :math:`P(y) = \sum_{k=0}^{N-1} \binom{N-1+k}{k} y^k`
    with :math:`y = (1 - \cos\omega)/2`. Its roots are mapped to the
    minimum-phase (:math:`|z| < 1`) roots of :math:`z^2 - 2(1-2y)z + 1`; the
    analysis low-pass is :math:`H(z) = (1+z)^N` times that spectral factor
    (normalised so it sums to :math:`\sqrt 2`), and the high-pass is the
    quadrature mirror :math:`g_k = (-1)^{k+1} h_{L-1-k}`.
    """
    n = n_vanishing
    poly = np.array([math.comb(n - 1 + k, k) for k in range(n)], dtype=float)
    z_inside = []
    for y in np.roots(poly[::-1]):
        b = -2.0 * (1.0 - 2.0 * y)
        disc = np.sqrt(b * b - 4.0 + 0j)
        r1, r2 = (-b + disc) / 2.0, (-b - disc) / 2.0
        z_inside.append(r1 if abs(r1) < 1.0 else r2)
    low = np.poly([-1.0] * n + z_inside).real
    low *= math.sqrt(2.0) / low.sum()
    dec_lo = low[::-1]  # pywt stores the time-reversed decomposition low-pass
    length = len(dec_lo)
    dec_hi = np.array(
        [(-1.0) ** (k + 1) * dec_lo[length - 1 - k] for k in range(length)]
    )
    return torch.tensor(np.stack([dec_lo, dec_hi]), dtype=torch.float32)


def dwt_max_level(n_times: int, filter_len: int) -> int:
    """Maximum number of discrete wavelet decomposition levels.

    Matches ``pywt.dwt_max_level`` = ``floor(log2(n_times / (filter_len - 1)))``.

    Parameters
    ----------
    n_times : int
        Length of the signal.
    filter_len : int
        Number of wavelet filter taps.

    Returns
    -------
    int
        Maximum decomposition level (``0`` if the signal is shorter than the
        filter).
    """
    if n_times < filter_len:
        return 0
    return max(0, int(math.floor(math.log2(n_times / (filter_len - 1)))))


def wavelet_decomposition(
    x: torch.Tensor, filters: torch.Tensor, n_levels: int | None = None
) -> torch.Tensor:
    r"""Multilevel discrete wavelet decomposition with periodic boundary.

    A cascade of strided convolutions with circular padding, bit-identical to
    ``pywt`` / ``ptwt`` ``wavedec(mode="periodic")``. The approximation and
    detail coefficients of every level are concatenated along the last axis as
    ``[cA_n, cD_n, cD_{n-1}, ..., cD_1]``.

    Parameters
    ----------
    x : torch.Tensor
        Input signal of shape ``(..., n_times)``.
    filters : torch.Tensor
        Decomposition filters of shape ``(2, filter_len)`` =
        ``[low-pass, high-pass]`` (e.g. from :func:`daubechies_filters`).
    n_levels : int, optional
        Number of decomposition levels. Defaults to the maximum
        (:func:`dwt_max_level`).

    Returns
    -------
    torch.Tensor
        Concatenated coefficients of shape ``(..., dwt_len)``.
    """
    filter_len = filters.shape[-1]
    if n_levels is None:
        n_levels = dwt_max_level(x.shape[-1], filter_len)
    leading = x.shape[:-1]
    approx = x.reshape(-1, x.shape[-1])
    # Flip the taps so conv1d (cross-correlation) realises the wavelet convolution.
    weight = filters.flip(-1).unsqueeze(1).to(device=approx.device, dtype=approx.dtype)
    details = []
    for _ in range(n_levels):
        pad = (2 * filter_len - 3) // 2
        padded = F.pad(
            approx.unsqueeze(1), (pad, pad + approx.shape[-1] % 2), mode="circular"
        )
        approx, detail = F.conv1d(padded, weight, stride=2).unbind(dim=1)
        details.append(detail)
    out = torch.cat([approx, *reversed(details)], dim=-1)
    return out.reshape(*leading, -1)


def sinusoidal_positional_encoding(n_positions: int, dim: int) -> torch.Tensor:
    r"""Fixed sine/cosine positional-encoding table of shape ``(n_positions, dim)``.

    The standard encoding of Vaswani et al. (2017): for position :math:`p` and
    channel :math:`i`, :math:`pe[p, 2i] = \sin(p / 10000^{2i/d})` and
    :math:`pe[p, 2i+1] = \cos(p / 10000^{2i/d})`. PyTorch ships no sinusoidal
    encoding (``nn.Embedding`` is a *learned* lookup), so braindecode models that
    need one share this primitive instead of re-deriving it. An odd ``dim`` is
    computed on the next even width and truncated, reproducing the per-model
    wrappers (e.g. :class:`~braindecode.models.medformer` odd-``d_model``).

    Parameters
    ----------
    n_positions : int
        Number of positions (sequence length) to encode.
    dim : int
        Embedding dimension of each position.

    Returns
    -------
    torch.Tensor
        ``(n_positions, dim)`` float table; callers add their own batch axis,
        dropout, or offset.
    """
    dim_even = dim + (dim % 2)
    position = torch.arange(n_positions).unsqueeze(1).float()
    div_term = torch.exp(
        torch.arange(0, dim_even, 2).float() * (-math.log(10000.0) / dim_even)
    )
    pe = torch.zeros(n_positions, dim_even)
    pe[:, 0::2] = torch.sin(position * div_term)
    pe[:, 1::2] = torch.cos(position * div_term)
    # ``.contiguous()`` so an odd-``dim`` truncation owns tight storage -- a
    # non-contiguous view over the padded width breaks safetensors buffer saving.
    return pe[:, :dim].contiguous()
