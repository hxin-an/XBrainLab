"""Evaluation metric enum definitions for model performance assessment."""

from enum import Enum


class Metric(Enum):
    """Enumeration of supported evaluation metrics.

    Attributes:
        ACC: Classification accuracy as a percentage.
        AUC: Area under the Receiver Operating Characteristic curve.
        KAPPA: Cohen's kappa coefficient for inter-rater agreement.

    """

    ACC = "Accuracy (%)"
    AUC = "Area under ROC-curve"
    KAPPA = "kappa value"
