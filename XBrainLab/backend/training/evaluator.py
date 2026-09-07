"""Model evaluation utilities for testing, metric computation, and saliency analysis."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

import numpy as np
import torch
import torch.utils.data as torch_data
from captum.attr import NoiseTunnel, Saliency
from sklearn.metrics import roc_auc_score

from .record import EvalRecord, RecordKey
from .saliency_artifact_integrity import normalize_saliency_method_parameters


class Evaluator:
    """Helper class for model evaluation, testing, and metric computation."""

    _ALL_SALIENCY_METHODS: ClassVar[tuple[str, ...]] = (
        "Gradient",
        "Gradient * Input",
        "SmoothGrad",
        "SmoothGrad_Squared",
        "VarGrad",
    )
    _NOISE_TUNNEL_METHODS: ClassVar[tuple[str, ...]] = (
        "SmoothGrad",
        "SmoothGrad_Squared",
        "VarGrad",
    )

    @staticmethod
    def _model_device(model: torch.nn.Module) -> Any | None:
        try:
            return next(model.parameters()).device
        except (AttributeError, StopIteration, TypeError):
            return None

    @staticmethod
    def _move_batch_to_model_device(
        model: torch.nn.Module,
        inputs: torch.Tensor,
        labels: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        device = Evaluator._model_device(model)
        if device is None:
            return inputs, labels
        return (
            inputs.to(device, non_blocking=True),
            labels.to(device, non_blocking=True),
        )

    @staticmethod
    def require_finite_tensor(value: torch.Tensor, *, context: str) -> None:
        if not bool(value.isfinite().all().item()):
            raise ValueError(f"{context} contains NaN or infinite values.")

    @staticmethod
    def require_finite_array(value: np.ndarray, *, context: str) -> None:
        if not np.isfinite(value).all():
            raise ValueError(f"{context} contains NaN or infinite values.")

    @staticmethod
    def _noise_tunnel_params(
        saliency_params: dict,
        method: str,
    ) -> dict[str, Any]:
        return normalize_saliency_method_parameters(
            method,
            saliency_params.get(method),
        )

    @staticmethod
    def _noise_seed(model: torch.nn.Module) -> int:
        """Capture the active generator seed before NoiseTunnel attribution."""
        device = Evaluator._model_device(model)
        if getattr(device, "type", None) == "cuda":
            return int(torch.cuda.initial_seed())
        return int(torch.initial_seed())

    @staticmethod
    def _selected_saliency_methods(saliency_params: dict) -> set[str]:
        value = saliency_params.get("_methods")
        if value is None:
            value = saliency_params.get("methods")

        if isinstance(value, str):
            raw_methods = [value]
        elif isinstance(value, (list, tuple, set)):
            raw_methods = list(value)
        else:
            return set(Evaluator._ALL_SALIENCY_METHODS)

        valid_methods = set(Evaluator._ALL_SALIENCY_METHODS)
        selected = {str(method).strip() for method in raw_methods}
        selected &= valid_methods
        return selected or set(Evaluator._ALL_SALIENCY_METHODS)

    @staticmethod
    def _captum_output_to_numpy(value: Any) -> np.ndarray:
        """Return the first tensor attribution as a CPU numpy array."""
        if isinstance(value, tuple):
            value = value[0]
        result = value.detach().cpu().numpy()
        Evaluator.require_finite_array(
            result,
            context="Saliency attribution",
        )
        return result

    @staticmethod
    def compute_auc(y_true, y_pred, multi_class="ovr") -> float | None:
        """Compute AUC score safely, handling tensor conversion and edge cases.

        Args:
            y_true: Ground truth labels as a tensor or numpy array.
            y_pred: Predicted logits or probabilities as a tensor or numpy array.
            multi_class: Multi-class strategy for AUC computation.
                Defaults to ``'ovr'`` (one-vs-rest).

        Returns:
            The computed AUC score, or ``None`` when AUC is undefined.

        """
        if y_true is None or y_pred is None:
            logging.getLogger(__name__).warning("No data to compute AUC")
            return None

        raw_predictions = (
            y_pred.detach().cpu().numpy()
            if isinstance(y_pred, torch.Tensor)
            else np.asarray(y_pred)
        )
        Evaluator.require_finite_array(
            raw_predictions,
            context="AUC prediction array",
        )

        try:
            # Detach and CPU if tensors
            if isinstance(y_true, torch.Tensor):
                y_true = y_true.detach().cpu().numpy()
            y_true = np.asarray(y_true)
            if np.unique(y_true).size < 2:
                logging.getLogger(__name__).warning(
                    "AUC is undefined because the split contains fewer than two classes"
                )
                return None

            # Handle predictions
            if isinstance(y_pred, torch.Tensor):
                probs = (
                    torch.nn.functional.softmax(y_pred, dim=1).detach().cpu().numpy()
                )
            else:
                probs = raw_predictions

            if probs.shape[-1] <= 2:
                # Binary case
                auc = roc_auc_score(y_true, probs[:, 1])
            else:
                # Multi-class
                auc = roc_auc_score(y_true, probs, multi_class=multi_class)

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.warning("Failed to calculate AUC: %s", e)
            return None
        else:
            # roc_auc_score may return nan for undefined cases (e.g. single class)
            if np.isnan(auc):
                return None
            return float(auc)

    @staticmethod
    def evaluate_metrics(
        model: torch.nn.Module,
        data_loader: torch_data.DataLoader,
        criterion: torch.nn.Module,
    ) -> dict[str, float | None]:
        """Compute aggregate metrics for a model and data loader.

        Args:
            model: The PyTorch model to evaluate.
            data_loader: DataLoader providing input-label pairs.
            criterion: Loss function used to compute evaluation loss.

        Returns:
            A dictionary containing accuracy (``RecordKey.ACC``),
            AUC (``RecordKey.AUC``), and loss (``RecordKey.LOSS``).

        """
        model.eval()

        running_loss = 0.0
        total_count = 0
        correct = 0.0
        y_true_parts: list[torch.Tensor] = []
        y_pred_parts: list[torch.Tensor] = []

        with torch.no_grad():
            for inputs, labels in data_loader:
                batch_inputs, batch_labels = Evaluator._move_batch_to_model_device(
                    model,
                    inputs,
                    labels,
                )
                outputs = model(batch_inputs)
                Evaluator.require_finite_tensor(
                    outputs,
                    context="Evaluation model output",
                )
                loss = criterion(outputs, batch_labels)
                Evaluator.require_finite_tensor(
                    loss,
                    context="Evaluation loss",
                )
                batch_count = len(batch_labels)
                running_loss += loss.item() * batch_count

                correct += (outputs.argmax(axis=1) == batch_labels).float().sum().item()
                total_count += batch_count

                y_true_parts.append(batch_labels.detach().cpu())
                y_pred_parts.append(outputs.detach().cpu())

        y_true = torch.cat(y_true_parts) if y_true_parts else None  # pyright: ignore[reportPrivateImportUsage]
        y_pred = torch.cat(y_pred_parts) if y_pred_parts else None  # pyright: ignore[reportPrivateImportUsage]

        if total_count == 0:
            return {RecordKey.ACC: 0, RecordKey.AUC: None, RecordKey.LOSS: 0}

        running_loss /= total_count
        acc = correct / total_count * 100

        # Calculate AUC using shared helper
        auc = Evaluator.compute_auc(y_true, y_pred)

        return {RecordKey.ACC: acc, RecordKey.AUC: auc, RecordKey.LOSS: running_loss}

    @staticmethod
    def evaluate(
        model: torch.nn.Module,
        data_loader: torch_data.DataLoader,
        *,
        evaluation_split: str = "unknown",
    ) -> EvalRecord:
        """Evaluate model outputs without saliency attribution.

        This is the default training-completion path. Saliency maps are
        computed only after the user explicitly configures saliency analysis.
        """
        model.eval()

        output_list = []
        label_list = []

        with torch.no_grad():
            for inputs, labels in data_loader:
                batch_inputs, batch_labels = Evaluator._move_batch_to_model_device(
                    model,
                    inputs,
                    labels,
                )
                outputs = model(batch_inputs)
                Evaluator.require_finite_tensor(
                    outputs,
                    context="Evaluation model output",
                )
                output_list.append(outputs.detach().cpu().numpy())
                label_list.append(batch_labels.detach().cpu().numpy())

        if not output_list or not label_list:
            return EvalRecord(
                np.array([], dtype=int),
                np.empty((0, 0)),
                {},
                {},
                {},
                {},
                {},
                evaluation_split=evaluation_split,
            )

        return EvalRecord(
            np.concatenate(label_list),
            np.concatenate(output_list),
            {},
            {},
            {},
            {},
            {},
            evaluation_split=evaluation_split,
        )

    @staticmethod
    def evaluate_with_saliency(
        model: torch.nn.Module,
        data_loader: torch_data.DataLoader,
        saliency_params: dict,
        *,
        evaluation_split: str = "unknown",
    ) -> EvalRecord:
        """Evaluate model and compute saliency maps using multiple attribution methods.

        Computes Gradient, Gradient*Input, SmoothGrad, SmoothGrad Squared,
        and VarGrad saliency maps for each batch in the data loader.

        Args:
            model: The PyTorch model to evaluate (should be in eval mode).
            data_loader: DataLoader providing input-label pairs.
            saliency_params: Dictionary of parameters for each saliency method,
                keyed by method name (e.g., ``'SmoothGrad'``,
                ``'SmoothGrad_Squared'``, ``'VarGrad'``).

        Returns:
            An :class:`EvalRecord` containing labels, outputs, and per-class
            saliency maps for all attribution methods.

        """
        model.eval()

        selected_methods = Evaluator._selected_saliency_methods(saliency_params)
        compute_gradient = "Gradient" in selected_methods
        compute_gradient_input = "Gradient * Input" in selected_methods
        compute_smoothgrad = "SmoothGrad" in selected_methods
        compute_smoothgrad_sq = "SmoothGrad_Squared" in selected_methods
        compute_vargrad = "VarGrad" in selected_methods
        compute_any_gradient = compute_gradient or compute_gradient_input
        compute_any_noise = any(
            method in selected_methods for method in Evaluator._NOISE_TUNNEL_METHODS
        )
        compute_any_saliency = compute_any_gradient or compute_any_noise
        effective_parameters = {
            method: normalize_saliency_method_parameters(
                method,
                saliency_params.get(method),
            )
            for method in selected_methods
        }
        noise_seed = Evaluator._noise_seed(model) if compute_any_noise else None

        output_list = []
        label_list = []

        gradient_list = []
        gradient_input_list = []
        smoothgrad_list = []
        smoothgrad_sq_list = []
        vargrad_list = []

        noise_tunnel_inst = NoiseTunnel(Saliency(model)) if compute_any_noise else None

        for inputs, labels in data_loader:
            batch_inputs, batch_labels = Evaluator._move_batch_to_model_device(
                model,
                inputs,
                labels,
            )
            with torch.set_grad_enabled(compute_any_gradient):
                if compute_any_gradient:
                    batch_inputs.requires_grad_(True)
                outputs = model(batch_inputs)
                Evaluator.require_finite_tensor(
                    outputs,
                    context="Saliency evaluation model output",
                )
                if compute_any_gradient:
                    # Reuse the logits graph for signed true-label attribution.
                    selected_outputs = outputs.gather(1, batch_labels[:, None]).sum()
                    batch_gradient = Evaluator._captum_output_to_numpy(
                        torch.autograd.grad(selected_outputs, batch_inputs)[0]
                    )

            output_list.append(outputs.detach().cpu().numpy())
            label_list.append(batch_labels.detach().cpu().numpy())

            if compute_any_saliency:
                batch_inputs.requires_grad_(True)
            target_labels = label_list[-1].tolist()

            if compute_any_gradient:
                if compute_gradient:
                    gradient_list.append(batch_gradient)
                if compute_gradient_input:
                    batch_inputs_array = batch_inputs.detach().cpu().numpy()
                    gradient_input_list.append(
                        np.multiply(batch_inputs_array, batch_gradient),
                    )
            if compute_smoothgrad and noise_tunnel_inst is not None:
                smoothgrad_list.append(
                    Evaluator._captum_output_to_numpy(
                        noise_tunnel_inst.attribute(
                            batch_inputs,
                            target=target_labels,
                            nt_type="smoothgrad",
                            abs=False,
                            **Evaluator._noise_tunnel_params(
                                saliency_params,
                                "SmoothGrad",
                            ),
                        )
                    ),
                )
            if compute_smoothgrad_sq and noise_tunnel_inst is not None:
                smoothgrad_sq_list.append(
                    Evaluator._captum_output_to_numpy(
                        noise_tunnel_inst.attribute(
                            batch_inputs,
                            target=target_labels,
                            nt_type="smoothgrad_sq",
                            abs=False,
                            **Evaluator._noise_tunnel_params(
                                saliency_params,
                                "SmoothGrad_Squared",
                            ),
                        )
                    ),
                )
            if compute_vargrad and noise_tunnel_inst is not None:
                vargrad_list.append(
                    Evaluator._captum_output_to_numpy(
                        noise_tunnel_inst.attribute(
                            batch_inputs,
                            target=target_labels,
                            nt_type="vargrad",
                            abs=False,
                            **Evaluator._noise_tunnel_params(
                                saliency_params,
                                "VarGrad",
                            ),
                        )
                    ),
                )

        label_list = np.concatenate(label_list)
        output_list = np.concatenate(output_list)

        gradient_values = np.concatenate(gradient_list) if gradient_list else None
        gradient_input_values = (
            np.concatenate(gradient_input_list) if gradient_input_list else None
        )
        smoothgrad_values = np.concatenate(smoothgrad_list) if smoothgrad_list else None
        smoothgrad_sq_values = (
            np.concatenate(smoothgrad_sq_list) if smoothgrad_sq_list else None
        )
        vargrad_values = np.concatenate(vargrad_list) if vargrad_list else None

        num_classes = output_list.shape[-1]

        # Helper to organize by class
        def _by_class(arr, labels, n_classes):
            if arr is None:
                return {}
            return {i: arr[np.where(labels == i)] for i in range(n_classes)}

        return EvalRecord(
            label_list,
            output_list,
            _by_class(gradient_values, label_list, num_classes),
            _by_class(gradient_input_values, label_list, num_classes),
            _by_class(smoothgrad_values, label_list, num_classes),
            _by_class(smoothgrad_sq_values, label_list, num_classes),
            _by_class(vargrad_values, label_list, num_classes),
            evaluation_split=evaluation_split,
            saliency_method_parameters=effective_parameters,
            saliency_noise_seeds=(
                {
                    method: noise_seed
                    for method in selected_methods
                    if method in Evaluator._NOISE_TUNNEL_METHODS
                    and noise_seed is not None
                }
            ),
        )
