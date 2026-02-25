"""EEGNet model implementation for EEG-based brain-computer interfaces."""

import math

import torch
from torch import nn


class EEGNet(nn.Module):
    """Compact convolutional neural network for EEG-based BCIs.

    EEGNet is a compact convolutional neural network designed for EEG-based
    brain-computer interfaces. It uses depthwise and separable convolutions
    to learn frequency-specific spatial filters and temporal patterns.

    Reference:
        Lawhern, V. J., et al. (2018). "EEGNet: a compact convolutional neural
        network for EEG-based brain-computer interfaces." *Journal of Neural
        Engineering*, 15(5), 056013.
        https://iopscience.iop.org/article/10.1088/1741-2552/aace8c/meta

    Attributes:
        tp: Number of time samples.
        ch: Number of EEG channels.
        sf: Sampling frequency in Hz.
        n_class: Number of output classes.
        half_sf: Half of the sampling frequency (temporal kernel size).
        F1: Number of temporal filters.
        F2: Number of pointwise filters.
        D: Depth multiplier for depthwise convolutions.
        pool_1: First average pooling kernel size.
        pool_2: Second average pooling kernel size.
        conv1: First convolutional block (temporal filtering).
        conv2: Second convolutional block (depthwise spatial filtering).
        conv3: Third convolutional block (separable pointwise filtering).
        classifier: Fully connected classification layer.

    """

    def __init__(
        self,
        n_classes: int,
        channels: int,
        samples: int,
        sfreq: float,
        f1: int = 8,
        f2: int = 16,
        d: int = 2,
        pool_1: int = 4,
        pool_2: int = 8,
    ):
        """Initializes EEGNet.

        Args:
            n_classes: Number of output classes for classification.
            channels: Number of EEG channels.
            samples: Number of time samples per trial.
            sfreq: Sampling frequency in Hz.
            f1: Number of temporal filters. Defaults to 8.
            f2: Number of pointwise filters. Defaults to 16.
            d: Depth multiplier for depthwise spatial convolutions.
                Defaults to 2.
            pool_1: Kernel size for the first average pooling layer.
                Defaults to 4.
            pool_2: Kernel size for the second average pooling layer.
                Defaults to 8.

        Raises:
            ValueError: If the epoch duration (samples) is too short for the
                network architecture.

        """
        super().__init__()

        self.tp = samples
        self.ch = channels
        self.sf = sfreq
        self.n_class = n_classes
        self.half_sf = math.floor(self.sf / 2)

        # Validate minimum samples requirement
        # EEGNet requires: Conv1(kernel=sf/2) -> AvgPool(4) ->
        # Conv3(kernel=sf/16) -> AvgPool(8)
        # Approximate minimum: sf/2 + 4 + (sf/16)*4 + 32
        min_samples = self.half_sf + 4 + math.floor(self.half_sf / 4) * 4 + 32
        epoch_duration = samples / sfreq
        min_duration = min_samples / sfreq
        if samples < min_samples:
            raise ValueError(
                f"Epoch duration is too short for EEGNet. "
                f"Current: {samples} samples ({epoch_duration:.3f}s at {sfreq}Hz). "
                f"Minimum required: {min_samples} samples ({min_duration:.3f}s). "
                f"Please increase epoch length (tmax-tmin) to at least "
                f"{min_duration:.2f}s or use a lower sampling frequency.",
            )

        self.F1 = f1
        self.F2 = f2
        self.D = d

        self.pool_1 = pool_1
        self.pool_2 = pool_2

        self.conv1 = nn.Sequential(
            # temporal kernel size(1, floor(sf*0.5)) means 500ms EEG at sf/2
            # padding=(0, floor(sf*0.5)/2) maintain raw data shape
            nn.Conv2d(
                1,
                self.F1,
                (1, self.half_sf),
                padding="valid",
                bias=False,
            ),  # 62,32
            nn.BatchNorm2d(self.F1),
        )

        self.conv2 = nn.Sequential(
            # spatial kernel size (n_ch, 1)
            nn.Conv2d(
                self.F1,
                self.D * self.F1,
                (self.ch, 1),
                groups=self.F1,
                bias=False,
            ),
            nn.BatchNorm2d(self.D * self.F1),
            nn.ELU(),
            nn.AvgPool2d((1, self.pool_1)),  # reduce the sf to sf/4
            # 0.25 in cross-subject classification beacuse the training size are larger
            nn.Dropout(0.5),
        )

        self.conv3 = nn.Sequential(
            # kernel size=(1, floor((sf/4))*0.5) means 500ms EEG at sf/4 Hz
            nn.Conv2d(
                self.D * self.F1,
                self.D * self.F1,
                (1, math.floor(self.half_sf / 4)),
                padding="valid",
                groups=self.D * self.F1,
                bias=False,
            ),
            nn.Conv2d(self.D * self.F1, self.F2, (1, 1), bias=False),
            nn.BatchNorm2d(self.F2),
            nn.ELU(),
            nn.AvgPool2d((1, self.pool_2)),  # dim reduction
            nn.Dropout(0.5),
        )

        ## (floor((sf/4))/2 * timepoint//32, n_class)
        # self.classifier = nn.Linear(
        #     self.F2* math.ceil(self.tp//32), self.n_class, bias=True
        # )
        fc_in_size = self._get_size(self.ch, self.tp)[1]
        self.classifier = nn.Linear(fc_in_size, self.n_class, bias=True)

    def forward(self, x):
        """Performs the forward pass of EEGNet.

        Args:
            x: Input EEG tensor of shape ``(batch, channels, samples)`` or
                ``(batch, 1, channels, samples)``.

        Returns:
            Output logits tensor of shape ``(batch, n_classes)``.

        """
        if len(x.shape) != 4:
            x = x.unsqueeze(1)
        x = self.conv1(x)
        x = self.conv2(x)
        x = self.conv3(x)
        # (-1, sf/8* timepoint//32)
        x = x.contiguous().view(x.size()[0], -1)
        # x = x.view(-1, self.F2* (self.tp//32))
        x = self.classifier(x)
        return x

    def _get_size(self, ch, tsamp):
        """Computes the flattened feature size after convolutional layers.

        Args:
            ch: Number of EEG channels.
            tsamp: Number of time samples.

        Returns:
            Tensor size after flattening, as a ``torch.Size`` object.

        """
        data = torch.ones((2, 1, ch, tsamp))
        x = self.conv1(data)
        x = self.conv2(x)
        x = self.conv3(x)
        x = x.view(x.size()[0], -1)
        return x.size()
