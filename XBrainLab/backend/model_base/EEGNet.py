import math

import torch
from torch import nn


class EEGNet(nn.Module):
    """Implementation of EEGNet
    https://iopscience.iop.org/article/10.1088/1741-2552/aace8c/meta

    Parameters:
        n_classes: Number of classes.
        channels: Number of channels.
        samples: Number of samples.
        sfreq: Sampling frequency.
        F1: Number of temporal filters.
        F2: Number of pointwise filters.
        D: Number of spatial filters within each temporal filter.
    """
    def __init__(
        self,
        n_classes: int,
        channels: int,
        samples: int,
        sfreq: float,
        F1: int = 8,
        F2: int = 16,
        D: int = 2
    ):
        super().__init__()

        self.tp = samples
        self.ch = channels
        self.sf = sfreq
        self.n_class = n_classes
        self.half_sf = math.floor(self.sf/2)

        # Validate minimum samples requirement
        # EEGNet requires: Conv1(kernel=sf/2) -> AvgPool(4) -> Conv3(kernel=sf/16) -> AvgPool(8)
        # Approximate minimum: sf/2 + 4 + (sf/16)*4 + 32
        min_samples = self.half_sf + 4 + math.floor(self.half_sf/4)*4 + 32
        epoch_duration = samples / sfreq
        min_duration = min_samples / sfreq
        if samples < min_samples:
            raise ValueError(
                f"Epoch duration is too short for EEGNet. "
                f"Current: {samples} samples ({epoch_duration:.3f}s at {sfreq}Hz). "
                f"Minimum required: {min_samples} samples ({min_duration:.3f}s). "
                f"Please increase epoch length (tmax-tmin) to at least {min_duration:.2f}s or use a lower sampling frequency."
            )

        self.F1=F1
        self.F2=F2
        self.D=D

        self.conv1 = nn.Sequential(
        #temporal kernel size(1, floor(sf*0.5)) means 500ms EEG at sf/2
        #padding=(0, floor(sf*0.5)/2) maintain raw data shape
            nn.Conv2d(
                1, self.F1, (1, self.half_sf), padding='valid', bias=False
            ), #62,32
            nn.BatchNorm2d(self.F1)
        )

        self.conv2 = nn.Sequential(
            # spatial kernel size (n_ch, 1)
            nn.Conv2d(
                self.F1, self.D*self.F1, (self.ch, 1), groups=self.F1, bias=False
            ),
            nn.BatchNorm2d(self.D*self.F1),
            nn.ELU(),
            nn.AvgPool2d((1, 4)), #reduce the sf to sf/4
            # 0.25 in cross-subject classification beacuse the training size are larger
            nn.Dropout(0.5)
        )

        self.conv3 = nn.Sequential(
        # kernel size=(1, floor((sf/4))*0.5) means 500ms EEG at sf/4 Hz
            nn.Conv2d(
                self.D*self.F1,
                self.D*self.F1,
                (1, math.floor(self.half_sf/4)),
                padding='valid',
                groups=self.D*self.F1, bias=False
            ),
            nn.Conv2d(self.D*self.F1, self.F2, (1, 1), bias=False),
            nn.BatchNorm2d(self.F2),
            nn.ELU(),
            nn.AvgPool2d((1, 8)), #dim reduction
            nn.Dropout(0.5)
        )

        ## (floor((sf/4))/2 * timepoint//32, n_class)
        # self.classifier = nn.Linear(
        #     self.F2* math.ceil(self.tp//32), self.n_class, bias=True
        # )
        fc_inSize = self._get_size(self.ch, self.tp)[1]
        self.classifier = nn.Linear(fc_inSize, self.n_class, bias=True)

    def forward(self, x):
        if len(x.shape) != 4:
            x = x.unsqueeze(1)
        x = self.conv1(x)
        x = self.conv2(x)
        x = self.conv3(x)
        #(-1, sf/8* timepoint//32)
        x = x.view(x.size()[0], -1)
        #x = x.view(-1, self.F2* (self.tp//32))
        x = self.classifier(x)
        return x

    def _get_size(self, ch, tsamp):
        data = torch.ones((2, 1, ch, tsamp))
        x = self.conv1(data)
        x = self.conv2(x)
        x = self.conv3(x)
        x = x.view(x.size()[0], -1)
        return x.size()
