from __future__ import annotations

import torch
from mne.filter import _check_coefficients, create_filter
from mne.utils import warn
from torch import Tensor, from_numpy, nn
from torchaudio.functional import fftconvolve, filtfilt, lfilter


class FilterBankLayer(nn.Module):
    """Apply multiple band-pass filters to generate multiview signal representation.

    This layer constructs a bank of signals filtered in specific bands for each channel.
    It uses MNE's `create_filter` function to create the band-specific filters and
    applies them to multi-channel time-series data. Each filter in the bank
    corresponds to a specific frequency band and is applied to all channels of
    the input data. The filtering is performed using FFT-based convolution via
    ``torchaudio.functional`` if the method is FIR, and ``torchaudio.functional``
    if the method is IIR.

    The default configuration creates 9 non-overlapping frequency bands with a
    4 Hz bandwidth, spanning from 4 Hz to 40 Hz (i.e., 4-8 Hz, 8-12 Hz, ...,
    36-40 Hz). This setup is based on the reference: *FBCNet: A Multi-view
    Convolutional Neural Network for Brain-Computer Interface*.

    Parameters
    ----------
    n_chans : int
        Number of channels in the input signal.
    sfreq : int
        Sampling frequency of the input signal in Hz.
    band_filters : Optional[list[tuple[float, float]]] or int, default=None
        List of frequency bands as (low_freq, high_freq) tuples. Each tuple defines
        the frequency range for one filter in the bank. If not provided, defaults
        to 9 non-overlapping bands with 4 Hz bandwidths spanning from 4 to 40 Hz.
    method : str, default='fir'
        ``'fir'`` will use FIR filtering, ``'iir'`` will use IIR filtering.
        For more details, please check the `MNE Preprocessing Tutorial <https://mne.tools/stable/auto_tutorials/preprocessing/25_background_filtering.html>`_.
    filter_length : str | int
        Length of the FIR filter to use (if applicable):

        * **'auto' (default)**: The filter length is chosen based
          on the size of the transition regions (6.6 times the reciprocal
          of the shortest transition band for fir_window='hamming'
          and fir_design="firwin2", and half that for "firwin").
        * **str**: A human-readable time in
          units of "s" or "ms" (e.g., "10s" or "5500ms") will be
          converted to that number of samples if ``phase="zero"``, or
          the shortest power-of-two length at least that duration for
          ``phase="zero-double"``.
        * **int**: Specified length in samples. For fir_design="firwin",
          this should not be used.
    l_trans_bandwidth : Union[str, float, int], default='auto'
        Width of the transition band at the low cut-off frequency in Hz
        (high pass or cutoff 1 in bandpass). Can be "auto"
        (default) to use a multiple of ``l_freq``::

            min(max(l_freq * 0.25, 2), l_freq)

        Only used for ``method='fir'``.
    h_trans_bandwidth : Union[str, float, int], default='auto'
        Width of the transition band at the high cut-off frequency in Hz
        (low pass or cutoff 2 in bandpass). Can be "auto"
        (default in 0.14) to use a multiple of ``h_freq``::

            min(max(h_freq * 0.25, 2.), info['sfreq'] / 2. - h_freq)

        Only used for ``method='fir'``.
    phase : str, default='zero'
        Phase of the filter.
        When ``method='fir'``, symmetric linear-phase FIR filters are constructed
        with the following behaviors when ``method="fir"``:

        ``"zero"`` (default)
            The delay of this filter is compensated for, making it non-causal.
        ``"minimum"``
            A minimum-phase filter will be constructed by decomposing the
            zero-phase filter
            into a minimum-phase and all-pass systems, and then retaining only the
            minimum-phase system (of the same length as the original zero-phase filter)
            via :func:`scipy.signal.minimum_phase`.
        ``"zero-double"``
            *This is a legacy option for compatibility with MNE <= 0.13.*
            The filter is applied twice, once forward, and once backward
            (also making it non-causal).
        ``"forward"`` or ``"causal"``
            The symmetric FIR coefficients are applied once in the forward
            (causal) direction using :func:`~scipy.signal.lfilter` semantics.
        ``"minimum-half"``
            *This is a legacy option for compatibility with MNE <= 1.6.*
            A minimum-phase filter will be reconstructed from the zero-phase filter with
            half the length of the original filter.

        When ``method='iir'``, ``phase='zero'`` (default) or equivalently
        ``'zero-double'`` constructs and applies IIR filter twice, once forward,
        and once backward (making it non-causal) using
        :func:`~scipy.signal.filtfilt`; ``phase='forward'`` or ``'causal'`` will
        apply the filter once in the forward (causal) direction using
        :func:`~scipy.signal.lfilter`.

           The behavior for ``phase="minimum"`` was fixed to use a filter of
           the requested length and improved suppression.
    iir_params : Optional[dict], default=None
        Dictionary of parameters to use for IIR filtering.
        If ``iir_params=None`` and ``method="iir"``, 4th order Butterworth will be used.
        For more information, see :func:`mne.filter.construct_iir_filter`.
    fir_window : str, default='hamming'
        The window to use in FIR design, can be "hamming" (default),
        "hann" (default in 0.13), or "blackman".
    fir_design : str, default='firwin'
        Can be "firwin" (default) to use :func:`scipy.signal.firwin`,
        or "firwin2" to use :func:`scipy.signal.firwin2`. "firwin" uses
        a time-domain design technique that generally gives improved
        attenuation using fewer samples than "firwin2".
    verbose: bool | str | int | None, default=True
        Control verbosity of the logging output. If ``None``, use the default
        verbosity level. See the func:`mne.verbose` for details.
        Should only be passed as a keyword argument.

    Examples
    --------
    >>> import torch
    >>> from braindecode.modules import FilterBankLayer
    >>> module = FilterBankLayer(
    ...     n_chans=2,
    ...     sfreq=128,
    ...     band_filters=[(4.0, 8.0), (8.0, 12.0)],
    ...     method="fir",
    ...     verbose=False,
    ... )
    >>> inputs = torch.randn(2, 2, 256)
    >>> outputs = module(inputs)
    >>> outputs.shape
    torch.Size([2, 2, 2, 256])
    """

    def __init__(
        self,
        n_chans: int,
        sfreq: float,
        band_filters: list[tuple[float, float]] | int | None = None,
        method: str = "fir",
        filter_length: str | float | int = "auto",
        l_trans_bandwidth: str | float | int = "auto",
        h_trans_bandwidth: str | float | int = "auto",
        phase: str = "zero",
        iir_params: dict | None = None,
        fir_window: str = "hamming",
        fir_design: str = "firwin",
        verbose: bool = True,
    ):
        super().__init__()

        # The first step here is to check the band_filters
        # We accept as None values.
        if band_filters is None:
            """
            the filter bank is constructed using 9 filters with non-overlapping
            frequency bands, each of 4Hz bandwidth, spanning from 4 to 40 Hz
            (4-8, 8-12, …, 36-40 Hz)

            Based on the reference: FBCNet: A Multi-view Convolutional Neural
            Network for Brain-Computer Interface
            """
            band_filters = [(low, low + 4) for low in range(4, 36 + 1, 4)]
        # We accept as int.
        if isinstance(band_filters, int):
            warn(
                "Creating the filter banks equally divided in the "
                "interval 4Hz to 40Hz with almost equal bandwidths. "
                "If you want a specific interval, "
                "please specify 'band_filters' as a list of tuples.",
                UserWarning,
            )
            start = 4.0
            end = 40.0

            total_band_width = end - start  # 4 Hz to 40 Hz

            band_width_calculated = total_band_width / band_filters
            band_filters = [
                (
                    float(start + i * band_width_calculated),
                    float(start + (i + 1) * band_width_calculated),
                )
                for i in range(band_filters)
            ]

        if not isinstance(band_filters, list):
            raise ValueError(
                "`band_filters` should be a list of tuples if you want to "
                "use them this way."
            )
        elif any(len(bands) != 2 for bands in band_filters):
            raise ValueError("The band_filters items should be splitable in 2 values.")

        self.band_filters = band_filters
        self.n_bands = len(band_filters)
        self.phase = phase
        self.method = method
        self.n_chans = n_chans

        self.method_iir = self.method == "iir"
        self.forward_filter = phase in ("forward", "causal")

        # Prepare ParameterLists
        self.fir_list = nn.ParameterList()
        self.fir_a_list = nn.ParameterList()
        self.b_list = nn.ParameterList()
        self.a_list = nn.ParameterList()

        if self.method_iir:
            if iir_params is None:
                iir_params = {"output": "ba"}
            elif iir_params.get("output") == "sos":
                warn(
                    "It is not possible to use second-order section filtering "
                    "with Torch. Changing to filter ba",
                    UserWarning,
                )
                iir_params["output"] = "ba"

        filter_phase = phase
        if phase == "causal" and self.method_iir:
            filter_phase = "forward"
        elif phase in ("forward", "causal") and not self.method_iir:
            # MNE designs symmetric FIR coefficients with phase="zero"; the
            # one-pass causal application is handled in forward().
            filter_phase = "zero"

        for l_freq, h_freq in band_filters:
            filt = create_filter(
                data=None,
                sfreq=sfreq,
                l_freq=float(l_freq),
                h_freq=float(h_freq),
                filter_length=filter_length,
                l_trans_bandwidth=l_trans_bandwidth,
                h_trans_bandwidth=h_trans_bandwidth,
                method=self.method,
                iir_params=iir_params,
                phase=filter_phase,
                fir_window=fir_window,
                fir_design=fir_design,
                verbose=verbose,
            )
            if not self.method_iir:
                # FIR filter
                filt = from_numpy(filt).float()
                self.fir_list.append(nn.Parameter(filt, requires_grad=False))
                fir_a = torch.nn.functional.pad(
                    torch.ones(1, dtype=filt.dtype), (0, filt.shape[0] - 1)
                )
                self.fir_a_list.append(nn.Parameter(fir_a, requires_grad=False))
            else:
                a_coeffs = filt["a"]
                b_coeffs = filt["b"]

                _check_coefficients((b_coeffs, a_coeffs))

                b = torch.tensor(b_coeffs, dtype=torch.float64)
                a = torch.tensor(a_coeffs, dtype=torch.float64)

                self.b_list.append(nn.Parameter(b, requires_grad=False))
                self.a_list.append(nn.Parameter(a, requires_grad=False))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Apply the filter bank to the input signal.

        Parameters
        ----------
        x : torch.Tensor
            Input tensor of shape (batch_size, n_chans, time_points).

        Returns
        -------
        torch.Tensor
            Filtered output tensor of shape
            (batch_size, n_bands, n_chans, filtered_time_points).
        """
        outs = []
        if self.method_iir:
            for b, a in zip(self.b_list, self.a_list, strict=True):
                # Pass numerator and denominator directly
                outs.append(
                    self._apply_iir(
                        x=x,
                        b_coeffs=b,
                        a_coeffs=a,
                        forward_filter=self.forward_filter,
                    )
                )
        else:
            for fir, fir_a in zip(self.fir_list, self.fir_a_list, strict=True):
                # Pass FIR filter directly
                outs.append(
                    self._apply_fir(
                        x=x,
                        filt=fir,
                        a_coeffs=fir_a,
                        n_chans=self.n_chans,
                        forward_filter=self.forward_filter,
                    )
                )

        return torch.cat(outs, dim=1)

    @staticmethod
    def _apply_fir(
        x,
        filt: Tensor,
        a_coeffs: Tensor,
        n_chans: int,
        forward_filter: bool = False,
    ) -> Tensor:
        """
        Apply an FIR filter to the input tensor.

        Parameters
        ----------
        x : Tensor
            Input tensor of shape (batch_size, n_chans, n_times).
        filter : dict
            Dictionary containing IIR filter coefficients.
            - "b": Tensor of numerator coefficients.
        a_coeffs: Tensor
            FIR denominator coefficients for one-pass filtering.
        n_chans: int
            Number of channels
        forward_filter : bool
            If True, apply the FIR coefficients once in the forward direction.

        Returns
        -------
        Tensor
            Filtered tensor of shape (batch_size, 1, n_chans, n_times).
        """
        if forward_filter:
            orig_dtype = x.dtype
            b_coeffs = filt.double().to(x.device)
            filtered = lfilter(
                x.double(),
                a_coeffs=a_coeffs.double().to(x.device),
                b_coeffs=b_coeffs,
                clamp=False,
            )
            return filtered.to(orig_dtype).unsqueeze(1)

        # Expand filter coefficients to match the number of channels
        # Original 'b' shape: (filter_length,)
        # After unsqueeze and repeat: (n_chans, filter_length)
        # After final unsqueeze: (1, n_chans, filter_length)
        filt_expanded = filt.to(x.device).unsqueeze(0).repeat(n_chans, 1).unsqueeze(0)

        # Perform FFT-based convolution
        # Input x shape: (batch_size, n_chans, n_times)
        # filt_expanded shape: (1, n_chans, filter_length)
        # After convolution: (batch_size, n_chans, n_times)

        filtered = fftconvolve(
            x, filt_expanded, mode="same"
        )  # Shape: (batch_size, nchans, time_points)

        # Add a new dimension for the band
        # Shape after unsqueeze: (batch_size, 1, n_chans, n_times)
        filtered = filtered.unsqueeze(1)
        # returning the filtered
        return filtered

    @staticmethod
    def _apply_iir(
        x: Tensor, b_coeffs: Tensor, a_coeffs: Tensor, forward_filter: bool = False
    ) -> Tensor:
        """
        Apply an IIR filter to the input tensor.

        Parameters
        ----------
        x : Tensor
            Input tensor of shape (batch_size, n_chans, n_times).
        filter : dict
            Dictionary containing IIR filter coefficients

            - "b": Tensor of numerator coefficients.
            - "a": Tensor of denominator coefficients.
        forward_filter : bool
            If True, apply the filter once in the forward direction.

        Returns
        -------
        Tensor
            Filtered tensor of shape (batch_size, 1, n_chans, n_times).
        """
        # Run the recursion in float64 and cast back: IIR band-passes with poles
        # near the unit circle (e.g. cheby2 banks used by FBMSNet/FBCNet) diverge
        # to NaN in float32. The coefficient buffers are already float64.
        orig_dtype = x.dtype
        filter_fn = lfilter if forward_filter else filtfilt
        filtered = filter_fn(
            x.double(),
            a_coeffs=a_coeffs.double().to(x.device),
            b_coeffs=b_coeffs.double().to(x.device),
            clamp=False,
        )
        # Rearrange dimensions to (batch_size, 1, n_chans, n_times)
        return filtered.to(orig_dtype).unsqueeze(1)
