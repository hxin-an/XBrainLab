"""ShallowConvNet model implementation for EEG decoding."""

import math

import torch
from torch import nn


class ShallowConvNet(nn.Module):
    """Shallow convolutional neural network for EEG decoding.

    ShallowConvNet is inspired by the filter bank common spatial pattern
    (FBCSP) algorithm. It uses a temporal convolution followed by a spatial
    convolution, then applies squaring nonlinearity, average pooling, and
    log transformation to extract band-power features for classification.

    Reference:
        Schirrmeister, R. T., et al. (2017). "Deep learning with convolutional
        neural networks for EEG decoding and visualization."
        *Human Brain Mapping*, 38(11), 5391-5420.
        https://onlinelibrary.wiley.com/doi/full/10.1002/hbm.23730

    Attributes:
        temporal_filter: Number of temporal convolution filters.
        spatial_filter: Number of spatial convolution filters.
        kernel: Temporal convolution kernel size (ceil of 0.1 * sfreq).
        conv1: Temporal convolutional layer.
        conv2: Spatial convolutional layer.
        Bn1: Batch normalization layer.
        AvgPool1: Average pooling layer.
        Drop1: Dropout layer.
        classifier: Fully connected classification layer.

    """

    def __init__(
        self,
        n_classes,
        channels,
        samples,
        sfreq,
        pool_len=75,
        pool_stride=15,
    ):
        """Initializes ShallowConvNet.

        Args:
            n_classes: Number of output classes for classification.
            channels: Number of EEG channels.
            samples: Number of time samples per trial.
            sfreq: Sampling frequency in Hz.
            pool_len: Average pooling kernel length. Defaults to 75.
            pool_stride: Average pooling stride. Defaults to 15.

        Raises:
            ValueError: If the epoch duration (samples) is too short for the
                network architecture.

        """
        super().__init__()
        self.temporal_filter = 40
        self.spatial_filter = 40
        self.kernel = math.ceil(sfreq * 0.1)

        # Validate minimum samples requirement
        # ShallowConvNet requires: Conv1(kernel=0.1*sf) + AvgPool(pool_len)
        min_samples = self.kernel + pool_len
        epoch_duration = samples / sfreq
        min_duration = min_samples / sfreq
        if samples < min_samples:
            raise ValueError(
                f"Epoch duration is too short for ShallowConvNet. "
                f"Current: {samples} samples ({epoch_duration:.3f}s at {sfreq}Hz). "
                f"Minimum required: {min_samples} samples ({min_duration:.3f}s). "
                f"Please increase epoch length (tmax-tmin) to at least "
                f"{min_duration:.2f}s or use a lower sampling frequency.",
            )
        self.conv1 = nn.Conv2d(1, self.temporal_filter, (1, self.kernel), bias=False)
        self.conv2 = nn.Conv2d(
            self.temporal_filter,
            self.spatial_filter,
            (channels, 1),
            bias=False,
        )
        self.Bn1 = nn.BatchNorm2d(self.spatial_filter)
        # self.SquareLayer = square_layer()
        self.AvgPool1 = nn.AvgPool2d((1, pool_len), stride=(1, pool_stride))
        # self.LogLayer = Log_layer()
        self.Drop1 = nn.Dropout(0.5)
        fc_in_size = self._get_size(channels, samples)[1]
        self.classifier = nn.Linear(fc_in_size, n_classes, bias=True)
        # self.softmax = nn.Softmax()

    def forward(self, x):
        """Performs the forward pass of ShallowConvNet.

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
        x = self.Bn1(x)
        x = x**2
        x = self.AvgPool1(x)
        x = torch.log(torch.clamp(x, min=1e-7))
        x = self.Drop1(x)
        x = x.view(x.size()[0], -1)
        x = self.classifier(x)

        # x = self.softmax(x)
        return x

    def _get_size(self, ch, tsamp):
        """Computes the flattened feature size after convolutional layers.

        Args:
            ch: Number of EEG channels.
            tsamp: Number of time samples.

        Returns:
            Tensor size after flattening, as a ``torch.Size`` object.

        """
        data = torch.ones((1, 1, ch, tsamp))
        x = self.conv1(data)
        x = self.conv2(x)
        x = self.AvgPool1(x)
        x = x.view(x.size()[0], -1)
        return x.size()
