"""Training plan management, including data loading, training loops, and evaluation."""

from __future__ import annotations

import datetime
import os
import threading
from collections.abc import Callable, Sequence
from contextlib import nullcontext
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING
from uuid import uuid4

import numpy as np
import torch
import torch.utils.data as torch_data

from XBrainLab.backend.utils.cuda_errors import (
    is_cuda_oom_error,
    release_cuda_cache,
)
from XBrainLab.backend.utils.logger import logger

# ... (Previous imports remain, but remove captum/sklearn if unused locally)
# Actually, maintain clean imports:
from ..dataset import Dataset
from ..exceptions import StaleSaliencyUpdateError
from ..utils import set_seed, validate_type
from .evaluator import Evaluator
from .model_holder import ModelHolder
from .option import TrainingEvaluation, TrainingOption
from .record import EvalRecord, RecordKey, TrainRecord, TrainRecordKey
from .saliency_provenance import (
    SaliencyContextError,
    SaliencyProducerIdentity,
    fingerprint_saliency_epoch_data,
    fingerprint_saliency_model_state,
    fingerprint_saliency_split_mask,
)

TrainingMetricValue = float | str | None

if TYPE_CHECKING:
    from .state_tracker import TrainingStateTracker


@dataclass(frozen=True, slots=True)
class SaliencyUpdatePlan:
    """Stable record selection captured before expensive saliency computation."""

    holder: TrainingPlanHolder
    saliency_params: dict
    tracker_generation: int | None
    records: tuple[tuple[TrainRecord, EvalRecord], ...]


@dataclass(frozen=True, slots=True)
class PreparedSaliencyUpdate:
    """Fully computed saliency state that is ready for atomic publication."""

    plan: SaliencyUpdatePlan
    eval_records: tuple[tuple[TrainRecord, EvalRecord, EvalRecord], ...]

    @property
    def holder(self) -> TrainingPlanHolder:
        """Return the holder captured by the immutable computation plan."""
        return self.plan.holder

    @property
    def saliency_params(self) -> dict:
        """Return the parameters captured by the immutable computation plan."""
        return self.plan.saliency_params

    @property
    def tracker_generation(self) -> int | None:
        """Return the stable generation captured before computation."""
        return self.plan.tracker_generation


def _raise_if_prepared_saliency_records_stale(
    updates: list[PreparedSaliencyUpdate],
) -> None:
    """Verify every record captured by each plan still has the same identity."""
    for update in updates:
        holder_records = update.holder.train_record_list
        if any(
            not any(record is candidate for candidate in holder_records)
            or record.eval_record is not previous_eval_record
            for record, previous_eval_record in update.plan.records
        ):
            raise StaleSaliencyUpdateError


def publish_prepared_saliency_updates(
    updates: list[PreparedSaliencyUpdate],
    *,
    manager_params: dict | None = None,
    publish_manager_params: Callable[[dict], None] | None = None,
) -> None:
    """Publish prepared holder and manager state in one tracked mutation."""
    manager_params_copy = dict(manager_params or {})
    if not updates:
        if publish_manager_params is not None:
            publish_manager_params(manager_params_copy)
        return

    tracker = updates[0].holder._state_tracker
    if any(update.holder._state_tracker is not tracker for update in updates[1:]):
        raise RuntimeError("Saliency updates do not share one state tracker")

    holder_params = [dict(update.saliency_params) for update in updates]
    _raise_if_prepared_saliency_records_stale(updates)

    if tracker is not None:
        token = tracker.token()
        if not token.stable or any(
            update.tracker_generation != token.generation for update in updates
        ):
            raise StaleSaliencyUpdateError
        mutation = tracker.mutation_if_current(token.generation)
    else:
        mutation = updates[0].holder._state_mutation()

    with mutation as current:
        if current is False:
            raise StaleSaliencyUpdateError
        _raise_if_prepared_saliency_records_stale(updates)
        if publish_manager_params is not None:
            publish_manager_params(manager_params_copy)
        for update, params in zip(updates, holder_params, strict=True):
            update.holder.saliency_params = params
            for record, _previous_eval_record, eval_record in update.eval_records:
                record._replace_primary_evaluation_record(eval_record)


class SharedMemoryDataset(torch_data.Dataset):
    """A PyTorch Dataset that references shared numpy arrays to save RAM/VRAM.

    Data is transferred to the target device only when accessed via
    ``__getitem__``, avoiding upfront copies of the full dataset.

    Attributes:
        data: Full data array shared across all splits.
        labels: Full label array shared across all splits.
        indices: Array of indices into ``data`` and ``labels`` for this split.
        device: Preferred training device string. Samples stay on CPU here;
            full batches are moved by the trainer to avoid many tiny GPU copies.

    """

    def __init__(
        self,
        data: np.ndarray,
        labels: np.ndarray,
        indices: np.ndarray,
        device: str,
    ):
        """Initialize the shared memory dataset.

        Args:
            data: Full data array of shape ``(N, ...)``, shared across splits.
            labels: Full label array of shape ``(N,)``.
            indices: Integer array of sample indices for this split.
            device: Target PyTorch device string.

        """
        self.data = data
        self.labels = labels
        self.indices = indices
        self.device = device

    def __len__(self):
        """Return the number of samples in this split.

        Returns:
            The number of indices in this dataset split.

        """
        return len(self.indices)

    def __getitem__(self, idx):
        """Retrieve a single sample and transfer it to the target device.

        Args:
            idx: Index into :attr:`indices`.

        Returns:
            A tuple of ``(input_tensor, label_tensor)`` on the target device.

        """
        real_idx = self.indices[idx]
        x = torch.from_numpy(self.data[real_idx]).float()
        y = torch.tensor(self.labels[real_idx]).long()
        return x, y


def to_holder(
    data: np.ndarray,
    labels: np.ndarray,
    indices: np.ndarray,
    dev: str,
    bs: int,
    shuffle: bool = False,
) -> torch_data.DataLoader | None:
    """Convert data arrays into a PyTorch DataLoader using shared memory.

    Args:
        data: Full data array of shape ``(N, ...)``.
        labels: Full label array of shape ``(N,)``.
        indices: Integer array of sample indices for this split.
        dev: Target PyTorch device string.
        bs: Batch size.
        shuffle: Whether to shuffle the data. Defaults to ``False``.

    Returns:
        A :class:`torch.utils.data.DataLoader` wrapping a
        :class:`SharedMemoryDataset`, or ``None`` if ``indices`` is empty.

    """
    if len(indices) == 0:
        return None

    # Use SharedMemoryDataset to avoid copying numpy arrays (saves RAM)
    # and to load to GPU on-the-fly (saves VRAM).
    dataset = SharedMemoryDataset(data, labels, indices, dev)

    dataloader = torch_data.DataLoader(
        dataset,
        batch_size=bs,
        shuffle=shuffle,
        pin_memory=dev.startswith("cuda"),
    )
    return dataloader


def _read_model_args_for_identity(epoch_data: object) -> dict:
    """Return one isolated model input contract for artifact provenance."""
    getter = getattr(epoch_data, "get_model_args", None)
    value = getter() if callable(getter) else None
    if not isinstance(value, dict):
        raise SaliencyContextError(
            "EEG model input contract is unavailable for saliency provenance."
        )
    return dict(value)


class Status(Enum):
    """Enumeration of training plan execution states.

    Attributes:
        DONE: Training has completed.
        PENDING: Training has not started yet.
        INIT: Initializing a specific training repeat.
        EVAL: Evaluating a specific training repeat.
        TRAIN: Training a specific repeat.

    """

    DONE = "Finished"
    PENDING = "Pending"
    INIT = "Initializing {}"
    EVAL = "Evaluating {}"
    TRAIN = "Training {}"
    CANCELLED = "Cancelled"


class FinalEvaluationUnavailableError(RuntimeError):
    """Raised when final metrics cannot be produced without substitution."""


class TrainingPlanHolder:
    """class for storing training plan

    Contains repetition of training plan,
        each training plan is a :class:`TrainRecord` object

    Attributes:
        model_holder: :class:`ModelHolder` object
            Model holder
        dataset: :class:`Dataset` object
            Dataset for the training plan
        option: :class:`TrainingOption` object
            Training option
        train_record_list: List[:class:`TrainRecord`]
            List of training record generated by the training plan,
                used for storing training result
        interrupt: bool
            Whether the training is interrupted
        error: str | None
            Error message
        status: str
            Training status

    """

    def __init__(
        self,
        model_holder: ModelHolder,
        dataset: Dataset,
        option: TrainingOption,
        saliency_params: dict | None,
    ):
        """Initialize the training plan holder.

        Creates :class:`TrainRecord` instances for each repetition, each with
        a fresh model and random seed.

        Args:
            model_holder: Holder containing the model class and parameters.
            dataset: Dataset providing training, validation, and test splits.
            option: Training configuration options.
            saliency_params: Parameters for saliency computation methods.
                If ``None`` or empty, training performs metric evaluation only.

        Raises:
            ValueError: If the dataset, option, or model holder is invalid,
                or if model creation fails due to incompatible parameters.

        """
        self.model_holder = model_holder
        self.dataset = dataset
        self.option = option

        self.saliency_params: dict = dict(saliency_params or {})

        self.check_data()

        # Human-readable time plus random identity prevents concurrent collisions.
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self.plan_id = f"{timestamp}-{uuid4().hex[:12]}"

        self.train_record_list = []
        self._state_tracker: TrainingStateTracker | None = None
        self._interrupt = threading.Event()
        self.error: str | None = None
        self.status = Status.PENDING.value
        for i in range(self.option.repeat_num):
            seed = set_seed(seed=None)
            try:
                model = self.model_holder.get_model(
                    self.dataset.get_epoch_data().get_model_args(),
                )
            except (RuntimeError, ValueError) as e:
                # Catch both RuntimeError (from PyTorch) and ValueError (from our
                # validation)
                if "Output size is too small" in str(
                    e,
                ) or "Epoch duration is too short" in str(e):
                    model_name = self.model_holder.target_model.__name__
                    raise ValueError(
                        f"Failed to create model '{model_name}': {e!s}",
                    ) from e
                raise
            self.train_record_list.append(
                TrainRecord(
                    repeat=i,
                    dataset=self.dataset,
                    model=model,
                    option=self.option,
                    seed=seed,
                    plan_id=self.plan_id,
                ),
            )
        self._validate_loaded_saliency_artifacts()

    def _validate_loaded_saliency_artifacts(self) -> None:
        """Fail closed when a persisted record belongs to another producer."""
        epoch_data = self.dataset.get_epoch_data()
        for record in self.train_record_list:
            eval_record = record.eval_record
            if eval_record is None or not eval_record.has_saliency_data():
                continue
            try:
                producer_identity = self.build_saliency_producer_identity(
                    record,
                    evaluation_split=eval_record.evaluation_split,
                )
                eval_record.validate_saliency_context(
                    epoch_data,
                    producer_identity=producer_identity,
                )
            except SaliencyContextError as exc:
                eval_record.mark_saliency_context_incompatible(str(exc))

    def bind_state_tracker(self, tracker: TrainingStateTracker) -> None:
        """Bind this holder and all records to one trainer mutation token."""
        self._state_tracker = tracker
        for record in self.train_record_list:
            record.bind_state_tracker(tracker)

    def _state_mutation(self):
        """Return the shared mutation context when attached to a trainer."""
        tracker = getattr(self, "_state_tracker", None)
        return tracker.mutation() if tracker is not None else nullcontext()

    def check_data(self) -> None:
        """Validate that the training plan has valid dataset, option, and model.

        Raises:
            ValueError: If any required component is ``None`` or invalid.
            TypeError: If components are not of the expected types.

        """
        if self.dataset is None:
            raise ValueError("dataset cannot be None")
        if not self.dataset.get_epoch_data():
            raise ValueError("No valid training setting is generated")
        if not self.option:
            raise ValueError("No valid training setting is generated")
        if not self.model_holder:
            raise ValueError("No valid model is selected")

        validate_type(self.model_holder, ModelHolder, "model_holder")
        validate_type(self.dataset, Dataset, "dataset")
        validate_type(self.option, TrainingOption, "option")
        self.option.validate()

    # interact
    def train(self) -> None:
        """Execute the full training process for all repetitions.

        Iterates through each :class:`TrainRecord` and trains it. On completion,
        updates the status to ``DONE`` or ``PENDING``. On exception, stores the
        error message.
        """
        try:
            for i in range(self.option.repeat_num):
                with self._state_mutation():
                    self.status = Status.INIT.value.format(
                        self.train_record_list[i].get_name(),
                    )
                train_record = self.train_record_list[i]
                train_record.resume()
                self.train_one_repeat(train_record)
                train_record.pause()
            with self._state_mutation():
                if self.is_finished():
                    self.status = Status.DONE.value
                else:
                    self.status = Status.PENDING.value
        except Exception as e:
            logger.error("Training plan execution failed: %s", e, exc_info=True)
            with self._state_mutation():
                if is_cuda_oom_error(e):
                    self.error = (
                        "CUDA out of memory during training. The current "
                        "configuration is too large for the available GPU memory. "
                        "Try reducing batch size, input length, or model size."
                    )
                    self.status = "Failed: CUDA out of memory"
                else:
                    self.error = str(e)
                    self.status = Status.PENDING.value
        finally:
            # Ensure GPU models are moved back to CPU to prevent VRAM leaks
            for tr in self.train_record_list:
                self._safe_move_to_cpu(tr)
            release_cuda_cache(torch)

    @classmethod
    def _safe_move_to_cpu(cls, train_record):
        """Move archived model and optimizer state to CPU without losing history."""
        try:
            train_record.model.cpu()
            optimizer = getattr(train_record, "optim", None)
            if optimizer is not None:
                for state in optimizer.state.values():
                    for key, value in tuple(state.items()):
                        state[key] = cls._move_optimizer_value(value, "cpu")
        except Exception:
            logger.debug("Failed to move training resources to CPU", exc_info=True)

    @classmethod
    def _move_optimizer_value(cls, value, device: str):
        """Recursively move tensor-bearing optimizer state to one device."""
        if torch.is_tensor(value):
            return value.detach().to(device)
        if isinstance(value, dict):
            return {
                key: cls._move_optimizer_value(item, device)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [cls._move_optimizer_value(item, device) for item in value]
        if isinstance(value, tuple):
            return tuple(cls._move_optimizer_value(item, device) for item in value)
        return value

    @staticmethod
    def _restore_optimizer_state_for_model(
        optimizer: torch.optim.Optimizer,
    ) -> None:
        """Cast archived optimizer state back to its current model parameters."""
        if optimizer.state:
            optimizer.load_state_dict(optimizer.state_dict())

    def get_loader(
        self,
    ) -> tuple[
        torch_data.DataLoader | None,
        torch_data.DataLoader | None,
        torch_data.DataLoader | None,
    ]:
        """Create data loaders for training, validation, and testing splits.

        Returns:
            A tuple of ``(train_loader, val_loader, test_loader)``. Any loader
            may be ``None`` if the corresponding split has no samples.

        """
        bs = self.option.bs
        dev = self.option.get_device()

        # Access full data once (Reference)
        full_data = self.dataset.get_epoch_data().get_data()
        full_labels = self.dataset.get_epoch_data().get_label_list()

        # Get indices from masks
        train_idx = np.where(self.dataset.train_mask)[0]
        val_idx = np.where(self.dataset.val_mask)[0]
        test_idx = np.where(self.dataset.test_mask)[0]

        train_holder: torch_data.DataLoader | None = to_holder(
            full_data,
            full_labels,
            train_idx,
            dev,
            bs,
            True,
        )
        val_holder: torch_data.DataLoader | None = to_holder(
            full_data,
            full_labels,
            val_idx,
            dev,
            bs,
        )
        test_holder: torch_data.DataLoader | None = to_holder(
            full_data,
            full_labels,
            test_idx,
            dev,
            bs,
        )
        return train_holder, val_holder, test_holder

    def get_eval_pair(
        self,
        train_record: TrainRecord,
        val_loader: torch_data.DataLoader | None,
        test_loader: torch_data.DataLoader | None,
    ) -> tuple[torch.nn.Module, torch_data.DataLoader]:
        """Select the best model and data loader for final evaluation.

        The model selection depends on the configured
        :attr:`option.evaluation_option` strategy.

        Args:
            train_record: The training record containing best model state dicts.
            val_loader: Validation data loader, or ``None``.
            test_loader: Test data loader, or ``None``.

        Returns:
            A tuple of ``(model, data_loader)`` for held-out evaluation.

        Raises:
            FinalEvaluationUnavailableError: If the selected checkpoint or a
                validation/test loader is unavailable.
            NotImplementedError: If the evaluation option is not recognized.

        """
        target_loader = test_loader if test_loader is not None else val_loader

        state = self._selected_evaluation_state(train_record)
        if state is None:
            raise FinalEvaluationUnavailableError(
                "Final evaluation unavailable: the selected validation "
                "checkpoint was not produced."
            )
        if target_loader is None:
            raise FinalEvaluationUnavailableError(
                "Final evaluation unavailable: no validation or test split "
                "is configured."
            )

        # Only create the model on GPU once we know we have a valid state_dict
        target_model = self.model_holder.get_model(
            self.dataset.get_epoch_data().get_model_args(),
        ).to(self.option.get_device())
        target_model.load_state_dict(state)
        target_model = target_model.eval()
        return target_model, target_loader

    def _selected_evaluation_state(self, train_record: TrainRecord) -> dict | None:
        """Return the configured model state without substituting another epoch."""
        if self.option.evaluation_option == TrainingEvaluation.VAL_LOSS:
            state = getattr(train_record, f"best_val_{RecordKey.LOSS}_model")
        elif self.option.evaluation_option == TrainingEvaluation.VAL_ACC:
            state = getattr(train_record, f"best_val_{RecordKey.ACC}_model")
        elif self.option.evaluation_option == TrainingEvaluation.VAL_AUC:
            state = getattr(train_record, f"best_val_{RecordKey.AUC}_model")
        elif self.option.evaluation_option == TrainingEvaluation.LAST_EPOCH:
            state = train_record.model.state_dict()
        else:
            raise NotImplementedError

        return state

    def train_one_repeat(self, train_record: TrainRecord) -> None:
        """Train one repetition of the training plan

        Args:
            train_record: Training record for storing training result

        """
        if train_record.is_finished():
            return
        # init
        model = train_record.get_training_model(device=self.option.get_device())
        train_loader, val_loader, test_loader = self.get_loader()
        if self.option.epoch > 0 and not train_loader:
            raise ValueError("No Training Data")
        optimizer = train_record.optim
        if optimizer is None:
            raise RuntimeError("Training optimizer is unavailable")
        self._restore_optimizer_state_for_model(optimizer)
        criterion = train_record.criterion
        with self._state_mutation():
            self.status = Status.TRAIN.value.format(train_record.get_name())
        # train one epoch
        while train_record.epoch < self.option.epoch:
            if self._interrupt.is_set():
                break
            if train_loader is None:
                raise ValueError("train_loader cannot be None during training loop")
            self.train_one_epoch(
                model,
                train_loader,
                val_loader,
                optimizer,
                criterion,
                train_record,
            )

        if train_record.epoch == self.option.epoch:
            with self._state_mutation():
                self.status = Status.EVAL.value.format(train_record.get_name())
            try:
                target, target_loader = self.get_eval_pair(
                    train_record,
                    val_loader,
                    test_loader,
                )
            except FinalEvaluationUnavailableError:
                train_record.export_checkpoint()
                raise

            evaluation_split = self._evaluation_split_name(
                target_loader,
                train_loader=train_loader,
                val_loader=val_loader,
                test_loader=test_loader,
            )
            if evaluation_split not in {"test", "validation"}:
                train_record.export_checkpoint()
                raise FinalEvaluationUnavailableError(
                    "Final evaluation unavailable: the evaluation loader is not "
                    "a validation or test split."
                )
            evaluation_records = {}
            for split, loader in (
                ("training", train_loader),
                ("validation", val_loader),
                ("test", test_loader),
            ):
                if loader is None or len(loader) == 0:
                    continue
                evaluation_records[split] = Evaluator.evaluate(
                    target,
                    loader,
                    evaluation_split=split,
                )
            train_record.set_evaluation_records(
                evaluation_records,
                primary_split=evaluation_split,
            )

        train_record.export_checkpoint()

    def train_one_epoch(
        self,
        model: torch.nn.Module,
        train_loader: torch_data.DataLoader,
        val_loader: torch_data.DataLoader | None,
        optimizer: torch.optim.Optimizer,
        criterion: torch.nn.Module,
        train_record: TrainRecord,
    ) -> None:
        """Train one epoch of the training plan.

        Delegates to :class:`~.epoch_runner.EpochRunner` which
        encapsulates the batch-loop → metrics → eval → checkpoint
        sequence.

        Args:
            model (torch.nn.Module): The model to train.
            train_loader (torch_data.DataLoader): Data loader for training set.
            val_loader (torch_data.DataLoader | None): Data loader for validation set.
            optimizer (torch.optim.Optimizer): Optimizer for backpropagation.
            criterion (torch.nn.Module): Loss function.
            train_record (TrainRecord): Record to store training statistics.

        """
        from .epoch_runner import EpochRunner

        runner = EpochRunner(
            interrupt=self._interrupt,
            checkpoint_epoch=self.option.checkpoint_epoch,
        )
        runner.run(
            model,
            train_loader,
            val_loader,
            optimizer,
            criterion,
            train_record,
        )

    @property
    def interrupt(self) -> bool:
        """Whether an interrupt has been requested (thread-safe)."""
        return self._interrupt.is_set()

    def set_interrupt(self) -> None:
        """Set the interrupt flag to stop training after the current batch."""
        with self._state_mutation():
            self._interrupt.set()

    def clear_interrupt(self) -> None:
        """Clear the interrupt flag and reset the error status."""
        with self._state_mutation():
            self.error = None
            self._interrupt.clear()

    def mark_cancelled(self) -> None:
        """Record terminal cancellation without making the holder retryable."""
        with self._state_mutation():
            self.status = Status.CANCELLED.value

    # getter
    def get_name(self) -> str:
        """Return the name of the training plan (derived from the dataset).

        Returns:
            The dataset name string.

        """
        return self.dataset.get_name()

    def get_dataset(self) -> Dataset:
        """Return the dataset associated with this training plan.

        Returns:
            The :class:`Dataset` instance.

        """
        return self.dataset

    def get_plans(self) -> list[TrainRecord]:
        """Return all training records (one per repetition).

        Returns:
            List of :class:`TrainRecord` instances.

        """
        return self.train_record_list

    def get_saliency_params(self) -> dict:
        """Return the saliency computation parameters.

        Returns:
            Dictionary of saliency method parameters.

        """
        return self.saliency_params

    @staticmethod
    def _qualified_type_name(value: object) -> str:
        target = value if isinstance(value, type) else value.__class__
        return f"{target.__module__}.{target.__qualname__}"

    def build_saliency_producer_identity(
        self,
        train_record: TrainRecord,
        *,
        evaluation_split: str,
    ) -> SaliencyProducerIdentity:
        """Build exact-content provenance for one dataset split, run, and model."""
        if not any(train_record is item for item in self.train_record_list):
            raise ValueError("Training record belongs to another training plan")
        epoch_data = self.dataset.get_epoch_data()
        option = self.option
        optimizer = option.optim
        evaluation_option = option.evaluation_option
        pretrained_path = self.model_holder.pretrained_weight_path

        dataset_component = {
            "dataset_type": self._qualified_type_name(self.dataset),
            "epoch_data_fingerprint": fingerprint_saliency_epoch_data(epoch_data),
        }
        split_component = {
            "evaluation_split": str(evaluation_split or "unknown"),
            "train_mask": fingerprint_saliency_split_mask(self.dataset.train_mask),
            "validation_mask": fingerprint_saliency_split_mask(self.dataset.val_mask),
            "test_mask": fingerprint_saliency_split_mask(self.dataset.test_mask),
        }
        run_component = {
            "plan_id": str(train_record.plan_id or self.plan_id),
            "repeat": int(train_record.repeat),
            "seed": int(train_record.seed),
            "evaluation_split": str(evaluation_split or "unknown"),
            "training_option": {
                "epochs": int(option.epoch),
                "batch_size": int(option.bs),
                "learning_rate": float(option.lr),
                "checkpoint_epoch": int(option.checkpoint_epoch),
                "optimizer": (
                    self._qualified_type_name(optimizer)
                    if optimizer is not None
                    else None
                ),
                "optimizer_params": dict(option.optim_params or {}),
                "evaluation_option": (
                    f"{evaluation_option.__class__.__module__}."
                    f"{evaluation_option.__class__.__qualname__}."
                    f"{evaluation_option.name}"
                ),
            },
        }
        model_component = {
            "model_type": self._qualified_type_name(self.model_holder.target_model),
            "model_params": self.model_holder.model_params_map,
            "input_contract": _read_model_args_for_identity(epoch_data),
            "selected_state_fingerprint": fingerprint_saliency_model_state(
                self._selected_evaluation_state(train_record)
            ),
            "pretrained_weight_path": (
                os.path.normcase(os.path.normpath(os.fspath(pretrained_path)))
                if pretrained_path
                else None
            ),
        }
        return SaliencyProducerIdentity.from_components(
            dataset=dataset_component,
            split=split_component,
            run=run_component,
            model=model_component,
        )

    # setter
    def set_saliency_params(self, saliency_params: dict | None) -> None:
        """Set new saliency parameters and re-evaluate all finished repeats.

        Args:
            saliency_params: New dictionary of saliency method parameters. Empty
                values keep finished records on metric-only evaluation.

        """
        prepared_update = self.prepare_saliency_update(saliency_params)
        publish_prepared_saliency_updates([prepared_update])

    def prepare_saliency_update_plan(
        self,
        saliency_params: dict | None,
        *,
        records: Sequence[TrainRecord] | None = None,
    ) -> SaliencyUpdatePlan:
        """Capture an immutable selection without doing expensive model work."""
        prepared_params = dict(saliency_params or {})
        tracker = self._state_tracker
        tracker_generation: int | None = None
        if tracker is not None:
            token = tracker.token()
            if not token.stable:
                raise StaleSaliencyUpdateError
            tracker_generation = token.generation

        selected_records = (
            tuple(records)
            if records is not None
            else tuple(
                record for record in self.train_record_list if record.is_finished()
            )
        )
        if any(
            not any(record is candidate for candidate in self.train_record_list)
            or not record.is_finished()
            or record.eval_record is None
            for record in selected_records
        ):
            raise StaleSaliencyUpdateError
        return SaliencyUpdatePlan(
            holder=self,
            saliency_params=prepared_params,
            tracker_generation=tracker_generation,
            records=tuple(
                (record, record.eval_record)
                for record in selected_records
                if record.eval_record is not None
            ),
        )

    def compute_saliency_update(
        self,
        plan: SaliencyUpdatePlan,
        *,
        should_cancel: Callable[[], bool] | None = None,
    ) -> PreparedSaliencyUpdate:
        """Compute replacement records without mutating shared training state."""
        if plan.holder is not self:
            raise ValueError("Saliency update plan belongs to another holder")
        self._raise_if_saliency_plan_stale(plan, should_cancel=should_cancel)
        if not plan.records:
            return PreparedSaliencyUpdate(plan=plan, eval_records=())

        train_loader, val_loader, test_loader = self.get_loader()
        prepared_eval_records: list[tuple[TrainRecord, EvalRecord, EvalRecord]] = []
        for train_record, previous_eval_record in plan.records:
            self._raise_if_saliency_plan_stale(plan, should_cancel=should_cancel)
            target, target_loader = self.get_eval_pair(
                train_record,
                val_loader,
                test_loader,
            )
            try:
                # Target selection may call backend code that observes mutable
                # training records. Revalidate the captured identity before
                # interpreting or using the returned target.
                self._raise_if_saliency_plan_stale(
                    plan,
                    should_cancel=should_cancel,
                )
                evaluation_split = self._evaluation_split_name(
                    target_loader,
                    train_loader=train_loader,
                    val_loader=val_loader,
                    test_loader=test_loader,
                )
                if evaluation_split not in {"test", "validation"}:
                    raise FinalEvaluationUnavailableError(
                        "Evaluation recomputation unavailable: the evaluation "
                        "loader is not a validation or test split."
                    )
                self._raise_if_saliency_plan_stale(
                    plan,
                    should_cancel=should_cancel,
                )
                if plan.saliency_params:
                    producer_identity = self.build_saliency_producer_identity(
                        train_record,
                        evaluation_split=evaluation_split,
                    )
                    eval_record = Evaluator.evaluate_with_saliency(
                        target,
                        target_loader,
                        plan.saliency_params,
                        evaluation_split=evaluation_split,
                    )
                    self._raise_if_saliency_plan_stale(
                        plan,
                        should_cancel=should_cancel,
                    )
                    current_producer_identity = self.build_saliency_producer_identity(
                        train_record,
                        evaluation_split=evaluation_split,
                    )
                    if current_producer_identity != producer_identity:
                        raise StaleSaliencyUpdateError
                    eval_record.bind_saliency_context(
                        self.dataset.get_epoch_data(),
                        producer_identity=producer_identity,
                    )
                else:
                    eval_record = Evaluator.evaluate(
                        target,
                        target_loader,
                        evaluation_split=evaluation_split,
                    )
                self._raise_if_saliency_plan_stale(
                    plan,
                    should_cancel=should_cancel,
                )
                prepared_eval_records.append(
                    (train_record, previous_eval_record, eval_record)
                )
            finally:
                self._release_evaluation_model(target, train_record)
        self._raise_if_saliency_plan_stale(plan, should_cancel=should_cancel)
        return PreparedSaliencyUpdate(
            plan=plan,
            eval_records=tuple(prepared_eval_records),
        )

    def prepare_saliency_update(
        self,
        saliency_params: dict | None,
        *,
        records: Sequence[TrainRecord] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> PreparedSaliencyUpdate:
        """Compute replacement evaluation records without mutating shared state."""
        plan = self.prepare_saliency_update_plan(
            saliency_params,
            records=records,
        )
        return self.compute_saliency_update(plan, should_cancel=should_cancel)

    def _raise_if_saliency_plan_stale(
        self,
        plan: SaliencyUpdatePlan,
        *,
        should_cancel: Callable[[], bool] | None,
    ) -> None:
        """Reject computed results once their captured training state is obsolete."""
        if should_cancel is not None and should_cancel():
            raise StaleSaliencyUpdateError

        tracker = self._state_tracker
        if tracker is not None:
            token = tracker.token()
            if not token.stable or plan.tracker_generation != token.generation:
                raise StaleSaliencyUpdateError

        holder_records = self.train_record_list
        if any(
            not any(record is candidate for candidate in holder_records)
            or record.eval_record is not previous_eval_record
            for record, previous_eval_record in plan.records
        ):
            raise StaleSaliencyUpdateError

    @staticmethod
    def _release_evaluation_model(target, train_record: TrainRecord) -> None:
        """Return temporary evaluation models to CPU after saliency computation."""
        if target is None or target is getattr(train_record, "model", None):
            return
        move_to_cpu = getattr(target, "cpu", None)
        if callable(move_to_cpu):
            try:
                move_to_cpu()
            except RuntimeError:
                logger.debug("Failed to move saliency model to CPU", exc_info=True)

    @staticmethod
    def _evaluation_split_name(
        target_loader: torch_data.DataLoader | None,
        *,
        train_loader: torch_data.DataLoader | None,
        val_loader: torch_data.DataLoader | None,
        test_loader: torch_data.DataLoader | None,
    ) -> str:
        if target_loader is test_loader and test_loader is not None:
            return "test"
        if target_loader is val_loader and val_loader is not None:
            return "validation"
        if target_loader is train_loader and train_loader is not None:
            return "training"
        return "unknown"

    # status
    def get_training_status(self) -> str:
        """Return the current training status or error message.

        Returns:
            The error message if an error occurred, otherwise the status string.

        """
        if self.error:
            return self.error
        return self.status

    def get_training_repeat(self) -> int:
        """Return the index of the current (or next unfinished) training repetition.

        Returns:
            Zero-based index of the current training repetition.

        """
        for i in range(self.option.repeat_num):
            if not self.train_record_list[i].is_finished():
                return i
        return max(self.option.repeat_num - 1, 0)

    def get_training_epoch(self) -> int:
        """Return the current epoch of the active training repetition.

        Returns:
            The epoch count for the current repetition.

        """
        return self.train_record_list[self.get_training_repeat()].get_epoch()

    def get_training_evaluation(
        self,
    ) -> tuple[
        TrainingMetricValue,
        TrainingMetricValue,
        TrainingMetricValue,
        TrainingMetricValue,
        TrainingMetricValue,
        TrainingMetricValue,
        TrainingMetricValue,
    ]:
        """Return current evaluation metrics for the active training repetition.

        Returns:
            A tuple of ``(lr, train_loss, train_acc, train_auc, val_loss,
            val_acc, val_auc)``. Empty histories default to ``'-'``; a stored
            unavailable metric remains ``None``.

        """
        record = self.train_record_list[self.get_training_repeat()]

        lr: TrainingMetricValue = "-"
        train_loss: TrainingMetricValue = "-"
        train_acc: TrainingMetricValue = "-"
        train_auc: TrainingMetricValue = "-"
        val_loss: TrainingMetricValue = "-"
        val_acc: TrainingMetricValue = "-"
        val_auc: TrainingMetricValue = "-"
        if len(record.train[TrainRecordKey.LR]) > 0:
            lr = record.train[TrainRecordKey.LR][-1]
        if len(record.train[TrainRecordKey.LOSS]) > 0:
            train_loss = record.train[TrainRecordKey.LOSS][-1]
        if len(record.train[TrainRecordKey.AUC]) > 0:
            train_auc = record.train[TrainRecordKey.AUC][-1]
        if len(record.train[TrainRecordKey.ACC]) > 0:
            train_acc = record.train[TrainRecordKey.ACC][-1]
        if len(record.val[RecordKey.LOSS]) > 0:
            val_loss = record.val[RecordKey.LOSS][-1]
        if len(record.val[RecordKey.ACC]) > 0:
            val_acc = record.val[RecordKey.ACC][-1]
        if len(record.val[RecordKey.AUC]) > 0:
            val_auc = record.val[RecordKey.AUC][-1]
        return lr, train_loss, train_acc, train_auc, val_loss, val_acc, val_auc

    def is_finished(self) -> bool:
        """Check whether all training repetitions have completed.

        Returns:
            ``True`` if the last repetition's training record is finished.

        """
        return self.train_record_list[-1].is_finished()

    def get_epoch_progress_text(self) -> str:
        """Return a progress string showing completed vs. total epochs.

        Returns:
            A string formatted as ``'completed / total'``.

        """
        total = 0
        for train_record in self.train_record_list:
            total += train_record.get_epoch()
        return f"{total} / {self.option.epoch * self.option.repeat_num}"

    def get_best_performance(self) -> float:
        """Return the best accuracy achieved during training.

        Uses validation accuracy when available, then the final evaluation or
        training accuracy. Test-set metrics never select a checkpoint.

        Returns:
            The best accuracy value as a float.

        """
        record = self.train_record_list[self.get_training_repeat()]
        # Check validation accuracy first
        best_val_acc = record.best_record.get(f"best_val_{RecordKey.ACC}", -1)
        if best_val_acc is not None:
            return best_val_acc
        if record.eval_record is not None:
            final_accuracy = record.eval_record.get_acc()
            if final_accuracy is not None:
                return final_accuracy * 100
        if len(record.val[RecordKey.ACC]) > 0:
            latest_validation = record.val[RecordKey.ACC][-1]
            if latest_validation is not None:
                return latest_validation
        if len(record.train[RecordKey.ACC]) > 0:
            latest_training = record.train[RecordKey.ACC][-1]
            if latest_training is not None:
                return latest_training
        return 0.0
