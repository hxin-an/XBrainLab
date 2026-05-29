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


class Evaluator:
    """Helper class for model evaluation, testing, and metric computation."""

    _DEFAULT_NOISE_TUNNEL_PARAMS: ClassVar[dict[str, Any]] = {
        "nt_samples": 5,
        "nt_samples_batch_size": None,
        "stdevs": 1.0,
    }

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
    def _noise_tunnel_params(
        saliency_params: dict,
        method: str,
    ) -> dict[str, Any]:
        params = dict(Evaluator._DEFAULT_NOISE_TUNNEL_PARAMS)
        value = saliency_params.get(method)
        if isinstance(value, dict):
            params.update(value)
        return params

    @staticmethod
    def compute_auc(y_true, y_pred, multi_class="ovr") -> float:
        """Compute AUC score safely, handling tensor conversion and edge cases.

        Args:
            y_true: Ground truth labels as a tensor or numpy array.
            y_pred: Predicted logits or probabilities as a tensor or numpy array.
            multi_class: Multi-class strategy for AUC computation.
                Defaults to ``'ovr'`` (one-vs-rest).

        Returns:
            The computed AUC score, or ``0.0`` if computation fails.

        """
        try:
            if y_true is None or y_pred is None:
                logging.getLogger(__name__).warning("No data to compute AUC")
                return 0.0

            # Detach and CPU if tensors
            if isinstance(y_true, torch.Tensor):
                y_true = y_true.detach().cpu().numpy()

            # Handle predictions
            if isinstance(y_pred, torch.Tensor):
                if multi_class == "ovr":
                    probs = (
                        torch.nn.functional.softmax(y_pred, dim=1)
                        .detach()
                        .cpu()
                        .numpy()
                    )
                else:
                    # For simple binary or other cases logic might differ,
                    # but preserving original logic structure:
                    # Actually original logical branch was:
                    # if tensor: apply softmax (assuming logits)
                    # else: assume probs
                    # But wait, original code checked 'ovr' inside?
                    # No, it checked 'ovr' inside the if tensor block?
                    # Let's verify original logic.
                    # Assuming y_pred IS logits if tensor.
                    probs = (
                        torch.nn.functional.softmax(y_pred, dim=1)
                        .detach()
                        .cpu()
                        .numpy()
                    )
            else:
                probs = y_pred

            if probs.shape[-1] <= 2:
                # Binary case
                auc = roc_auc_score(y_true, probs[:, 1])
            else:
                # Multi-class
                auc = roc_auc_score(y_true, probs, multi_class=multi_class)

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.warning("Failed to calculate AUC: %s", e)
            return 0.0
        else:
            # roc_auc_score may return nan for undefined cases (e.g. single class)
            if np.isnan(auc):
                return 0.0
            return auc

    @staticmethod
    def test_model(
        model: torch.nn.Module,
        data_loader: torch_data.DataLoader,
        criterion: torch.nn.Module,
    ) -> dict[str, float]:
        """Test a model on the given data loader and compute metrics.

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
                loss = criterion(outputs, batch_labels)
                running_loss += loss.item()

                correct += (outputs.argmax(axis=1) == batch_labels).float().sum().item()
                total_count += len(batch_labels)

                y_true_parts.append(batch_labels.detach().cpu())
                y_pred_parts.append(outputs.detach().cpu())

        y_true = torch.cat(y_true_parts) if y_true_parts else None
        y_pred = torch.cat(y_pred_parts) if y_pred_parts else None

        if total_count == 0:
            return {RecordKey.ACC: 0, RecordKey.AUC: 0, RecordKey.LOSS: 0}

        running_loss /= len(data_loader)
        acc = correct / total_count * 100

        # Calculate AUC using shared helper
        auc = Evaluator.compute_auc(y_true, y_pred)

        return {RecordKey.ACC: acc, RecordKey.AUC: auc, RecordKey.LOSS: running_loss}

    @staticmethod
    def evaluate(
        model: torch.nn.Module,
        data_loader: torch_data.DataLoader,
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
            )

        return EvalRecord(
            np.concatenate(label_list),
            np.concatenate(output_list),
            {},
            {},
            {},
            {},
            {},
        )

    @staticmethod
    def evaluate_with_saliency(
        model: torch.nn.Module,
        data_loader: torch_data.DataLoader,
        saliency_params: dict,
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

        output_list = []
        label_list = []

        gradient_list = []
        gradient_input_list = []
        smoothgrad_list = []
        smoothgrad_sq_list = []
        vargrad_list = []

        saliency_inst = Saliency(model)
        noise_tunnel_inst = NoiseTunnel(saliency_inst)

        for inputs, labels in data_loader:
            batch_inputs, batch_labels = Evaluator._move_batch_to_model_device(
                model,
                inputs,
                labels,
            )
            outputs = model(batch_inputs)

            output_list.append(outputs.detach().cpu().numpy())
            label_list.append(batch_labels.detach().cpu().numpy())

            batch_inputs.requires_grad_(True)
            target_labels = label_list[-1].tolist()
            batch_gradient = (
                saliency_inst.attribute(
                    batch_inputs,
                    target=target_labels,
                    abs=False,
                )
                .detach()
                .cpu()
                .numpy()
            )

            gradient_list.append(batch_gradient)
            gradient_input_list.append(
                np.multiply(batch_inputs.detach().cpu().numpy(), batch_gradient),
            )
            smoothgrad_list.append(
                noise_tunnel_inst.attribute(
                    batch_inputs,
                    target=target_labels,
                    nt_type="smoothgrad",
                    **Evaluator._noise_tunnel_params(saliency_params, "SmoothGrad"),
                )
                .detach()
                .cpu()
                .numpy(),
            )
            smoothgrad_sq_list.append(
                noise_tunnel_inst.attribute(
                    batch_inputs,
                    target=target_labels,
                    nt_type="smoothgrad_sq",
                    **Evaluator._noise_tunnel_params(
                        saliency_params,
                        "SmoothGrad_Squared",
                    ),
                )
                .detach()
                .cpu()
                .numpy(),
            )
            vargrad_list.append(
                noise_tunnel_inst.attribute(
                    batch_inputs,
                    target=target_labels,
                    nt_type="vargrad",
                    **Evaluator._noise_tunnel_params(saliency_params, "VarGrad"),
                )
                .detach()
                .cpu()
                .numpy(),
            )

        label_list = np.concatenate(label_list)
        output_list = np.concatenate(output_list)

        gradient_list = np.concatenate(gradient_list)
        gradient_input_list = np.concatenate(gradient_input_list)
        smoothgrad_list = np.concatenate(smoothgrad_list)
        smoothgrad_sq_list = np.concatenate(smoothgrad_sq_list)
        vargrad_list = np.concatenate(vargrad_list)

        num_classes = output_list.shape[-1]

        # Helper to organize by class
        def _by_class(arr, labels, n_classes):
            return {i: arr[np.where(labels == i)] for i in range(n_classes)}

        return EvalRecord(
            label_list,
            output_list,
            _by_class(gradient_list, label_list, num_classes),
            _by_class(gradient_input_list, label_list, num_classes),
            _by_class(smoothgrad_list, label_list, num_classes),
            _by_class(smoothgrad_sq_list, label_list, num_classes),
            _by_class(vargrad_list, label_list, num_classes),
        )
