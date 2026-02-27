"""Single-epoch training orchestrator.

Encapsulates the sequence *batch-loop → metrics → record update →
validation → test → checkpoint* so that
:class:`~XBrainLab.backend.training.training_plan.TrainingPlanHolder`
can delegate to a focused, unit-testable component.
"""

from __future__ import annotations

import threading
import time

import torch
import torch.utils.data as torch_data

from .evaluator import Evaluator
from .record import RecordKey, TrainRecordKey
from .record.train import TrainRecord


class EpochRunner:
    """Runs a single training epoch end-to-end.

    Isolates:
    1. Batch loop (forward + backward)
    2. Metric computation (AUC)
    3. Record update (loss / acc / auc / lr / time)
    4. Validation & test evaluation
    5. Checkpoint export

    Args:
        interrupt: A :class:`threading.Event` checked between batches.
        checkpoint_epoch: Export a checkpoint every *N* epochs
            (``0`` / ``None`` to disable).
    """

    def __init__(
        self,
        interrupt: threading.Event,
        checkpoint_epoch: int | None = None,
    ) -> None:
        self._interrupt = interrupt
        self._checkpoint_epoch = checkpoint_epoch or 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        model: torch.nn.Module,
        train_loader: torch_data.DataLoader,
        val_loader: torch_data.DataLoader | None,
        test_loader: torch_data.DataLoader | None,
        optimizer: torch.optim.Optimizer,
        criterion: torch.nn.Module,
        train_record: TrainRecord,
    ) -> None:
        """Execute one full epoch: train → metrics → eval → checkpoint.

        Args:
            model: The model to train (will be put into ``.train()`` mode).
            train_loader: Training data loader.
            val_loader: Optional validation data loader.
            test_loader: Optional test data loader.
            optimizer: Optimizer for back-propagation.
            criterion: Loss function.
            train_record: Record for storing epoch statistics.
        """
        start_time = time.time()
        model.train()

        # 1. Batch loop
        running_loss, correct, total_count, y_true, y_pred = self._train_batches(
            model,
            train_loader,
            optimizer,
            criterion,
        )
        if self._interrupt.is_set():
            return

        if total_count == 0:
            return

        # 2. Metrics
        train_auc = Evaluator.compute_auc(y_true, y_pred)
        running_loss /= len(train_loader)
        train_acc = correct / total_count * 100

        # 3. Record update
        self._update_records(
            train_record,
            running_loss,
            train_acc,
            train_auc,
            optimizer.param_groups[0]["lr"],
            time.time() - start_time,
        )

        # 4. Validation & test
        if val_loader:
            result = Evaluator.test_model(model, val_loader, criterion)
            train_record.update_eval(result)

        if test_loader:
            result = Evaluator.test_model(model, test_loader, criterion)
            train_record.update_test(result)

        train_record.step()

        # 5. Checkpoint
        if (
            self._checkpoint_epoch
            and train_record.get_epoch() % self._checkpoint_epoch == 0
        ):
            train_record.export_checkpoint()

        # Free VRAM to prevent linear growth
        torch.cuda.empty_cache()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _train_batches(
        self,
        model: torch.nn.Module,
        train_loader: torch_data.DataLoader,
        optimizer: torch.optim.Optimizer,
        criterion: torch.nn.Module,
    ) -> tuple[float, float, int, torch.Tensor | None, torch.Tensor | None]:
        """Run the forward/backward pass over every batch in the loader."""
        running_loss = 0.0
        correct = 0.0
        total_count = 0
        y_true_parts: list[torch.Tensor] = []
        y_pred_parts: list[torch.Tensor] = []

        for inputs, labels in train_loader:
            if self._interrupt.is_set():
                break
            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

            correct += (outputs.argmax(axis=1) == labels).float().sum().item()
            y_true_parts.append(labels.detach().cpu())
            y_pred_parts.append(outputs.detach().cpu())
            total_count += len(labels)
            running_loss += loss.item()

        y_true = torch.cat(y_true_parts) if y_true_parts else None
        y_pred = torch.cat(y_pred_parts) if y_pred_parts else None
        return running_loss, correct, total_count, y_true, y_pred

    @staticmethod
    def _update_records(
        train_record: TrainRecord,
        loss: float,
        acc: float,
        auc: float,
        lr: float,
        duration: float,
    ) -> None:
        """Push epoch metrics into the training record."""
        train_record.update_train(
            {
                RecordKey.LOSS: loss,
                RecordKey.ACC: acc,
                RecordKey.AUC: auc,
            },
        )
        train_record.update_statistic(
            {
                TrainRecordKey.LR: lr,
                TrainRecordKey.TIME: duration,
            },
        )
