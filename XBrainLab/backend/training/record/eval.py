"""Evaluation record module for storing and exporting model evaluation results."""

import os

import numpy as np
import torch
from sklearn.metrics import precision_recall_fscore_support, roc_auc_score

from XBrainLab.backend.utils.logger import logger


def calculate_confusion(output: np.ndarray, label: np.ndarray) -> np.ndarray:
    """Calculate the confusion matrix from model outputs and ground truth labels.

    Args:
        output: Model output array of shape ``(n, num_classes)``.
        label: Ground truth label array of shape ``(n,)``.

    Returns:
        A confusion matrix of shape ``(num_classes, num_classes)`` where
        entry ``[i][j]`` is the count of samples with true label ``i``
        predicted as label ``j``.

    """
    class_num = output.shape[1] if output.ndim > 1 else len(np.unique(label))
    confusion = np.zeros((class_num, class_num), dtype=np.uint32)
    output = output.argmax(axis=1)
    for ground_truth in range(class_num):
        for predict in range(class_num):
            confusion[ground_truth][predict] = (
                output[label == ground_truth] == predict
            ).sum()
    return confusion


class EvalRecord:
    """Record class for storing and exporting model evaluation results.

    Stores ground truth labels, model outputs, and saliency maps from
    multiple attribution methods, organized by class index.

    Attributes:
        label: Ground truth label array of shape ``(n,)``.
        output: Model output array of shape ``(n, num_classes)``.
        gradient: Dictionary mapping class indices to gradient arrays.
        gradient_input: Dictionary mapping class indices to gradient*input arrays.
        smoothgrad: Dictionary mapping class indices to SmoothGrad arrays.
        smoothgrad_sq: Dictionary mapping class indices to SmoothGrad² arrays.
        vargrad: Dictionary mapping class indices to VarGrad arrays.

    """

    def __init__(
        self,
        label: np.ndarray,
        output: np.ndarray,
        gradient: dict,
        gradient_input: dict,
        smoothgrad: dict,
        smoothgrad_sq: dict,
        vargrad: dict,
    ) -> None:
        """Initialize the evaluation record.

        Args:
            label: Ground truth label array of shape ``(n,)``.
            output: Model output array of shape ``(n, num_classes)``.
            gradient: Per-class gradient saliency maps.
            gradient_input: Per-class gradient*input saliency maps.
            smoothgrad: Per-class SmoothGrad saliency maps.
            smoothgrad_sq: Per-class SmoothGrad² saliency maps.
            vargrad: Per-class VarGrad saliency maps.

        """
        self.label = label
        self.output = output
        self.gradient = gradient
        self.gradient_input = gradient_input
        self.smoothgrad = smoothgrad
        self.smoothgrad_sq = smoothgrad_sq
        self.vargrad = vargrad

    def export(self, target_path: str) -> None:
        """Export the evaluation record as a torch file.

        Args:
            target_path: Directory path where the ``'eval'`` file will be saved.

        """
        record = {
            "label": self.label,
            "output": self.output,
            "gradient": self.gradient,
            "gradient_input": self.gradient_input,
            "smoothgrad": self.smoothgrad,
            "smoothgrad_sq": self.smoothgrad_sq,
            "vargrad": self.vargrad,
        }
        torch.save(record, os.path.join(target_path, "eval"))

    @classmethod
    def load(cls, target_path: str) -> "EvalRecord | None":
        """Load an evaluation record from a torch file.

        Args:
            target_path: Directory path containing the ``'eval'`` file.

        Returns:
            An :class:`EvalRecord` instance, or ``None`` if the file does not
            exist or cannot be loaded.

        """
        path = os.path.join(target_path, "eval")
        if not os.path.exists(path):
            return None

        try:
            data = torch.load(path, weights_only=False)
            return cls(
                label=data["label"],
                output=data["output"],
                gradient=data.get("gradient", {}),
                gradient_input=data.get("gradient_input", {}),
                smoothgrad=data.get("smoothgrad", {}),
                smoothgrad_sq=data.get("smoothgrad_sq", {}),
                vargrad=data.get("vargrad", {}),
            )
        except Exception as e:
            logger.error("Failed to load EvalRecord: %s", e, exc_info=True)
            return None

    def export_csv(self, target_path: str) -> None:
        """Export evaluation results as a CSV file.

        The CSV contains model outputs, ground truth labels, and predicted labels.

        Args:
            target_path: Full file path for the CSV output.

        """
        data = np.c_[self.output, self.label, self.output.argmax(axis=1)]
        index_header_str = ",".join([str(i) for i in range(self.output.shape[1])])
        header = f"{index_header_str},ground_truth,predict"
        np.savetxt(
            target_path,
            data,
            delimiter=",",
            newline="\n",
            header=header,
            comments="",
        )

    def export_saliency(self, method: str, target_path: str | None = None) -> dict:
        """Return (and optionally save) a specific saliency map.

        Args:
            method: Saliency method name. One of ``'Gradient'``,
                ``'Gradient * Input'``, ``'SmoothGrad'``,
                ``'SmoothGrad_Squared'``, or ``'VarGrad'``.
            target_path: Optional file path. If provided, the saliency
                data is also saved via ``torch.save``.

        Returns:
            The saliency dictionary for the requested method.

        """
        if method == "Gradient":
            saliency = self.gradient
        elif method == "Gradient * Input":
            saliency = self.gradient_input
        elif method == "SmoothGrad":
            saliency = self.smoothgrad
        elif method == "SmoothGrad_Squared":
            saliency = self.smoothgrad_sq
        elif method == "VarGrad":
            saliency = self.vargrad
        else:
            raise ValueError(f"Unknown saliency method: {method}")
        if target_path:
            torch.save(saliency, target_path)
        return saliency

    def get_acc(self) -> float:
        """Compute the classification accuracy.

        Returns:
            Accuracy as a float between 0 and 1.

        """
        if len(self.label) == 0:
            return 0.0
        return sum(self.output.argmax(axis=1) == self.label) / len(self.label)

    def get_auc(self) -> float:
        """Compute the AUC (Area Under the ROC Curve) score.

        Handles both binary and multi-class scenarios using one-vs-rest.

        Returns:
            AUC score as a float.

        """
        if len(self.label) == 0 or len(self.output) == 0:
            return 0.0
        if (
            torch.nn.functional.softmax(torch.Tensor(self.output), dim=1)
            .numpy()
            .shape[-1]
            <= 2
        ):
            return roc_auc_score(
                self.label,
                torch.nn.functional.softmax(torch.Tensor(self.output), dim=1).numpy()[
                    :,
                    -1,
                ],
            )
        return roc_auc_score(
            self.label,
            torch.nn.functional.softmax(torch.Tensor(self.output), dim=1).numpy(),
            multi_class="ovr",
        )

    def get_kappa(self) -> float:
        """Compute Cohen's Kappa coefficient.

        Returns:
            The Kappa statistic as a float.

        """
        confusion = calculate_confusion(self.output, self.label)
        class_num = len(confusion)
        p0 = np.diagonal(confusion).sum() / confusion.sum()
        pe = sum(
            [confusion[:, i].sum() * confusion[i].sum() for i in range(class_num)],
        ) / (confusion.sum() * confusion.sum())
        if pe >= 1.0:
            return 0.0
        return (p0 - pe) / (1 - pe)

    def get_per_class_metrics(self) -> dict:
        """Get per-class precision, recall, f1-score, and support.

        Returns:
            Dictionary where keys are class indices and values are dicts containing:
            'precision', 'recall', 'f1-score', 'support'

        """
        y_true = self.label
        y_pred = self.output.argmax(axis=1)
        class_num = self.output.shape[1]
        labels = np.arange(class_num)

        precision, recall, f1, support = precision_recall_fscore_support(
            y_true,
            y_pred,
            labels=labels,
            zero_division=0,
        )

        metrics: dict[int | str, dict[str, float | int]] = {}
        for i in labels:
            metrics[int(i)] = {
                "precision": precision[i],
                "recall": recall[i],
                "f1-score": f1[i],
                "support": int(support[i]),
            }

        # Calculate macro average
        metrics["macro_avg"] = {
            "precision": np.mean(precision),
            "recall": np.mean(recall),
            "f1-score": np.mean(f1),
            "support": int(np.sum(support)),
        }

        return metrics

    def get_gradient(self, label_index: int) -> np.ndarray:
        """Return gradient saliency maps for the specified class.

        Args:
            label_index: Class index to retrieve saliency maps for.

        Returns:
            Numpy array of gradient saliency maps for the given class.

        """
        return self.gradient[label_index]

    def get_gradient_input(self, label_index: int) -> np.ndarray:
        """Return gradient*input saliency maps for the specified class.

        Args:
            label_index: Class index to retrieve saliency maps for.

        Returns:
            Numpy array of gradient*input saliency maps for the given class.

        """
        return self.gradient_input[label_index]

    def get_smoothgrad(self, label_index: int) -> np.ndarray:
        """Return SmoothGrad saliency maps for the specified class.

        Args:
            label_index: Class index to retrieve saliency maps for.

        Returns:
            Numpy array of SmoothGrad saliency maps for the given class.

        """
        return self.smoothgrad[label_index]

    def get_smoothgrad_sq(self, label_index: int) -> np.ndarray:
        """Return SmoothGrad² saliency maps for the specified class.

        Args:
            label_index: Class index to retrieve saliency maps for.

        Returns:
            Numpy array of SmoothGrad² saliency maps for the given class.

        """
        return self.smoothgrad_sq[label_index]

    def get_vargrad(self, label_index: int) -> np.ndarray:
        """Return VarGrad saliency maps for the specified class.

        Args:
            label_index: Class index to retrieve saliency maps for.

        Returns:
            Numpy array of VarGrad saliency maps for the given class.

        """
        return self.vargrad[label_index]
