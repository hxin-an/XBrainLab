"""SCCNet model implementation for EEG-based motor imagery classification."""

import math

import numpy as np
import torch
from torch import nn


class SCCNet(nn.Module):
    """Spatio-spectral feature learning network for EEG classification.

    SCCNet (Spatial Component-wise Convolutional Network) learns spatial
    filters and temporal/spectral features from EEG signals using a
    two-stage convolution architecture followed by squaring nonlinearity,
    average pooling, and log transformation.

    Reference:
        Wei, C.-S., et al. (2019). "Spatial component-wise convolutional
        network (SCCNet) for motor-imagery EEG classification."
        *2019 9th International IEEE/EMBS Conference on Neural Engineering
        (NER)*, pp. 328-331.
        https://ieeexplore.ieee.org/document/8716937

    Attributes:
        tp: Number of time samples.
        ch: Number of EEG channels.
        sf: Sampling frequency in Hz.
        n_class: Number of output classes.
        octsf: One-tenth of the sampling frequency (temporal kernel size).
        conv1: Spatial convolutional layer.
        Bn1: Batch normalization after spatial convolution.
        conv2: Temporal convolutional layer.
        Bn2: Batch normalization after temporal convolution.
        Drop1: Dropout layer.
        AvgPool1: Average pooling layer.
        classifier: Fully connected classification layer.
    """

    def __init__(self, n_classes, channels, samples, sfreq, ns=22):
        """Initializes SCCNet.

        Args:
            n_classes: Number of output classes for classification.
            channels: Number of EEG channels.
            samples: Number of time samples per trial.
            sfreq: Sampling frequency in Hz.
            ns: Number of spatial filters. Defaults to 22.

        Raises:
            ValueError: If the epoch duration (samples) is too short for the
                network architecture.
        """
        super().__init__()  # input:bs, 1, channel, sample

        self.tp = samples
        self.ch = channels
        self.sf = sfreq
        self.n_class = n_classes
        self.octsf = math.floor(self.sf * 0.1)

        # Validate minimum samples requirement
        # SCCNet requires: Conv2 padding + AvgPool(sf/2)
        min_samples = int(self.sf / 2) + 1
        epoch_duration = samples / sfreq
        min_duration = min_samples / sfreq
        if samples < min_samples:
            raise ValueError(
                f"Epoch duration is too short for SCCNet. "
                f"Current: {samples} samples ({epoch_duration:.3f}s at {sfreq}Hz). "
                f"Minimum required: {min_samples} samples ({min_duration:.3f}s). "
                f"Please increase epoch length (tmax-tmin) to at least "
                f"{min_duration:.2f}s or use a lower sampling frequency."
            )

        # (1, n_ch, kernelsize=(n_ch,1))
        self.conv1 = nn.Conv2d(1, ns, (self.ch, 1))
        self.Bn1 = nn.BatchNorm2d(ns)  # (n_ch)
        # kernelsize=(1, floor(sf*0.1)) padding= (0, floor(sf*0.1)/2)
        self.conv2 = nn.Conv2d(
            ns, 20, (1, self.octsf), padding=(0, int(np.ceil((self.octsf - 1) / 2)))
        )
        self.Bn2 = nn.BatchNorm2d(20)

        self.Drop1 = nn.Dropout(0.5)
        # kernelsize=(1, sf/2) revise to 128/2?  stride=(1, floor(sf*0.1))
        self.AvgPool1 = nn.AvgPool2d((1, int(self.sf / 2)), stride=(1, int(self.octsf)))
        # (20* ceiling((timepoint-sf/2)/floor(sf*0.1)), n_class)
        self.classifier = nn.Linear(
            (
                20
                * int(
                    (
                        self.tp
                        + (int(np.ceil((self.octsf - 1) / 2)) * 2 - self.octsf + 1)
                        - int(self.sf / 2)
                    )
                    / int(self.octsf)
                    + 1
                )
            ),
            self.n_class,
            bias=True,
        )

    def forward(self, x):
        """Performs the forward pass of SCCNet.

        Args:
            x: Input EEG tensor of shape ``(batch, channels, samples)`` or
                ``(batch, 1, channels, samples)``.

        Returns:
            Output logits tensor of shape ``(batch, n_classes)``.
        """
        if len(x.shape) != 4:
            x = x.unsqueeze(1)
        sp_x = self.conv1(x)  # (128,22,1,562)
        x = self.Bn1(sp_x)
        tp_x = self.conv2(x)  # (128,20,1,563)

        x = self.Bn2(tp_x)
        x = x**2
        x = self.Drop1(x)
        x = self.AvgPool1(x)  # (128,20,1,42)
        x = torch.log(x)
        x = x.view(
            -1,
            20
            * int(
                (
                    self.tp
                    + (int(np.ceil((self.octsf - 1) / 2)) * 2 - self.octsf + 1)
                    - int(self.sf / 2)
                )
                / int(self.octsf)
                + 1
            ),
        )
        x = self.classifier(x)

        return x
