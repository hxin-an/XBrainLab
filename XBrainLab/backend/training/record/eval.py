import os

import numpy as np
import torch
from sklearn.metrics import precision_recall_fscore_support, roc_auc_score


def calculate_confusion(output: np.ndarray, label: np.ndarray) -> np.ndarray:
    """Calculate confusion matrix.

    Args:
        output: Output of model.
        label: Ground truth label.
    """
    class_num = len(np.unique(label))
    confusion = np.zeros((class_num, class_num), dtype=np.uint32)
    output = output.argmax(axis=1)
    for ground_truth in range(class_num):
        for predict in range(class_num):
            confusion[ground_truth][predict] = (
                output[label == ground_truth] == predict
            ).sum()
    return confusion


class EvalRecord:
    """Class for recording evaluation result.

    Attributes:
        label: :class:`numpy.ndarray` of shape (n,).
            Ground truth label.
        output: :class:`numpy.ndarray` of shape (n, classNum).
            Output of model.
        gradient: dict of :class:`numpy.ndarray` of shape (n, classNum, ...) with
                  class index as key.
            Gradient of model by class index.
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
        self.label = label
        self.output = output
        self.gradient = gradient
        self.gradient_input = gradient_input
        self.smoothgrad = smoothgrad
        self.smoothgrad_sq = smoothgrad_sq
        self.vargrad = vargrad

    def export(self, target_path: str) -> None:
        """Export evaluation result as torch file.

        Args:
            target_path: Path to save evaluation result.
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
        """Load evaluation result from torch file.

        Args:
            target_path: Path to load evaluation result.
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
            print(f"Failed to load EvalRecord: {e}")
            return None

    def export_csv(self, target_path: str) -> None:
        """Export evaluation result as csv file.

        Args:
            target_path: Path to save evaluation result.
        """
        data = np.c_[self.output, self.label, self.output.argmax(axis=1)]
        index_header_str = ",".join([str(i) for i in range(self.output.shape[1])])
        header = f"{index_header_str},ground_truth,predict"
        np.savetxt(
            target_path, data, delimiter=",", newline="\n", header=header, comments=""
        )

    def export_saliency(self, method: str, target_path: str) -> None:
        """Export saliency map as torch file.
        Args:
            method: saliency type to be exported.
            target_path: Path to save saliency map.
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
        torch.save(saliency, target_path)

    def get_acc(self) -> float:
        """Get accuracy of the model."""
        return sum(self.output.argmax(axis=1) == self.label) / len(self.label)

    def get_auc(self) -> float:
        """Get auc of the model."""
        if (
            torch.nn.functional.softmax(torch.Tensor(self.output), dim=1)
            .numpy()
            .shape[-1]
            <= 2
        ):
            return roc_auc_score(
                self.label,
                torch.nn.functional.softmax(torch.Tensor(self.output), dim=1).numpy()[
                    :, -1
                ],
            )
        else:
            return roc_auc_score(
                self.label,
                torch.nn.functional.softmax(torch.Tensor(self.output), dim=1).numpy(),
                multi_class="ovr",
            )

    def get_kappa(self) -> float:
        """Get kappa of the model."""
        confusion = calculate_confusion(self.output, self.label)
        class_num = len(confusion)
        p0 = np.diagonal(confusion).sum() / confusion.sum()
        pe = sum(
            [confusion[:, i].sum() * confusion[i].sum() for i in range(class_num)]
        ) / (confusion.sum() * confusion.sum())
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
            y_true, y_pred, labels=labels, zero_division=0
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
        """Return gradient of model by class index."""
        return self.gradient[label_index]

    def get_gradient_input(self, label_index: int) -> np.ndarray:
        """Return gradient times input of model by class index."""
        return self.gradient_input[label_index]

    def get_smoothgrad(self, label_index: int) -> np.ndarray:
        """Return smoothgrad of model by class index."""
        return self.smoothgrad[label_index]

    def get_smoothgrad_sq(self, label_index: int) -> np.ndarray:
        """Return smoothgrad squared of model by class index."""
        return self.smoothgrad_sq[label_index]

    def get_vargrad(self, label_index: int) -> np.ndarray:
        """Return vargrad of model by class index."""
        return self.vargrad[label_index]
