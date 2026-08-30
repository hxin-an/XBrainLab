"""Training record module for per-epoch statistics, checkpoints, and figures."""

from __future__ import annotations

import os
import time
from contextlib import nullcontext
from copy import deepcopy
from math import isclose, isfinite
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import torch
from matplotlib import pyplot as plt
from matplotlib.figure import Figure

from ...dataset import Dataset
from ...training import TrainingOption
from ...utils import get_random_state, set_random_state
from ...utils.filesystem_identity import (
    ContainedOutputDirectory,
    FilesystemIdentityError,
    StableDirectoryIdentity,
    create_contained_output_directory,
    filesystem_safe_identity,
    retain_directory_identity,
)
from ...utils.logger import logger
from ..option import (
    ClassWeightMode,
    class_map_fingerprint,
    class_weighting_request,
    is_canonical_class_map_fingerprint,
    normalize_class_weight_mode,
    normalize_custom_class_weights,
)
from .artifact_store import (
    TRAINING_RECORD_ARTIFACT_TYPE,
    ArtifactStoreError,
    UnsupportedArtifactError,
    read_json_npz_artifact,
    save_model_state_dict,
    write_json_npz_artifact,
)
from .eval import EvalRecord, calculate_confusion
from .key import RecordKey, TrainRecordKey

if TYPE_CHECKING:
    from ..state_tracker import TrainingStateTracker

TRAIN_RECORD_SCHEMA_VERSION = 2
EVALUATION_SPLITS = ("training", "validation", "test")
_MODEL_IDENTITY_FIELDS = {"model_id", "provider", "source_revision"}
_CLASS_WEIGHTING_FIELDS = {"requested", "resolved"}
_CLASS_WEIGHTING_REQUEST_FIELDS = {
    "mode",
    "custom_class_weights",
    "class_map_fingerprint",
}
_CLASS_WEIGHTING_RESOLUTION_FIELDS = {
    "class_names",
    "class_order",
    "class_counts",
    "weights",
}


def _off_class_weighting() -> dict[str, object]:
    """Return the explicit migration target for historical unweighted records."""
    return {
        "requested": {
            "mode": ClassWeightMode.OFF.value,
            "custom_class_weights": {},
            "class_map_fingerprint": None,
        },
        "resolved": {
            "class_names": [],
            "class_order": [],
            "class_counts": [],
            "weights": [],
        },
    }


def _build_class_weighting_criterion(
    class_weighting: dict[str, object],
) -> torch.nn.CrossEntropyLoss:
    """Build only this record's training criterion from detached resolution."""
    requested = class_weighting["requested"]
    resolved = class_weighting["resolved"]
    if not isinstance(requested, dict) or not isinstance(resolved, dict):
        raise ValueError("Training class-weighting metadata is malformed.")
    if requested.get("mode") == ClassWeightMode.OFF.value:
        return torch.nn.CrossEntropyLoss()
    weights = resolved.get("weights")
    if not isinstance(weights, list):
        raise ValueError("Training class-weighting metadata is malformed.")
    return torch.nn.CrossEntropyLoss(
        weight=torch.tensor(weights, dtype=torch.float32),
    )


def _normalize_v2_class_weighting(value: object) -> dict[str, object]:
    """Validate the complete v2 persistence contract without fallback defaults."""
    if type(value) is not dict or set(value) != _CLASS_WEIGHTING_FIELDS:
        raise ArtifactStoreError("Training class-weighting metadata is malformed.")
    requested = value["requested"]
    resolved = value["resolved"]
    if (
        type(requested) is not dict
        or set(requested) != _CLASS_WEIGHTING_REQUEST_FIELDS
        or type(resolved) is not dict
        or set(resolved) != _CLASS_WEIGHTING_RESOLUTION_FIELDS
    ):
        raise ArtifactStoreError("Training class-weighting metadata is malformed.")
    try:
        mode = normalize_class_weight_mode(requested["mode"])
        raw_custom = requested["custom_class_weights"]
        custom = (
            normalize_custom_class_weights(raw_custom)
            if mode is ClassWeightMode.CUSTOM
            else {}
        )
    except ValueError as exc:
        raise ArtifactStoreError(
            "Training class-weighting metadata is malformed."
        ) from exc
    if (mode is ClassWeightMode.CUSTOM and custom != raw_custom) or (
        mode is not ClassWeightMode.CUSTOM and raw_custom != {}
    ):
        raise ArtifactStoreError("Training class-weighting metadata is malformed.")
    fingerprint = requested["class_map_fingerprint"]
    if fingerprint is not None and not is_canonical_class_map_fingerprint(fingerprint):
        raise ArtifactStoreError("Training class-weighting metadata is malformed.")

    class_names = resolved["class_names"]
    class_order = resolved["class_order"]
    class_counts = resolved["class_counts"]
    weights = resolved["weights"]
    if not all(
        isinstance(items, list)
        for items in (class_names, class_order, class_counts, weights)
    ):
        raise ArtifactStoreError("Training class-weighting metadata is malformed.")
    if not (len(class_names) == len(class_order) == len(class_counts) == len(weights)):
        raise ArtifactStoreError("Training class-weighting metadata is malformed.")
    if any(
        not isinstance(name, str) or not name or name != name.strip()
        for name in class_names
    ) or len(set(class_names)) != len(class_names):
        raise ArtifactStoreError("Training class-weighting metadata is malformed.")
    if (
        any(type(index) is not int for index in class_order)
        or class_order != sorted(class_order)
        or len(set(class_order)) != len(class_order)
        or any(type(count) is not int or count <= 0 for count in class_counts)
        or any(
            isinstance(weight, bool)
            or not isinstance(weight, (int, float))
            or not isfinite(float(weight))
            or float(weight) <= 0
            for weight in weights
        )
    ):
        raise ArtifactStoreError("Training class-weighting metadata is malformed.")
    if class_names:
        if not is_canonical_class_map_fingerprint(fingerprint) or (
            fingerprint
            != class_map_fingerprint(dict(zip(class_order, class_names, strict=True)))
        ):
            raise ArtifactStoreError("Training class-weighting metadata is malformed.")
    elif mode is not ClassWeightMode.OFF or fingerprint is not None:
        raise ArtifactStoreError("Training class-weighting metadata is malformed.")

    normalized_weights = [float(weight) for weight in weights]
    if mode is ClassWeightMode.OFF:
        if any(weight != 1.0 for weight in normalized_weights):
            raise ArtifactStoreError("Training class-weighting metadata is malformed.")
    elif mode is ClassWeightMode.BALANCED:
        total = sum(class_counts)
        expected_weights = [
            total / (len(class_order) * count) for count in class_counts
        ]
        if any(
            not isclose(weight, expected, rel_tol=1e-12, abs_tol=0.0)
            for weight, expected in zip(
                normalized_weights, expected_weights, strict=True
            )
        ):
            raise ArtifactStoreError("Training class-weighting metadata is malformed.")
    elif set(custom) != set(class_names) or any(
        normalized_weight != custom[name]
        for name, normalized_weight in zip(
            class_names,
            normalized_weights,
            strict=True,
        )
    ):
        raise ArtifactStoreError("Training class-weighting metadata is malformed.")

    return {
        "requested": {
            "mode": mode.value,
            "custom_class_weights": custom,
            "class_map_fingerprint": fingerprint,
        },
        "resolved": {
            "class_names": list(class_names),
            "class_order": list(class_order),
            "class_counts": list(class_counts),
            "weights": normalized_weights,
        },
    }


def _migrate_v1_class_weighting() -> dict[str, object]:
    """Migrate pre-class-weighting v1 records explicitly to Off.

    The real migration target is a training record created before this feature
    existed.  Removing v1 support needs a separate public artifact-support
    decision; a missing field in v2 is never a migration signal.
    """
    return _off_class_weighting()


def _normalize_model_identity(value: object) -> dict[str, str] | None:
    if value is None:
        return None
    if type(value) is not dict or set(value) != _MODEL_IDENTITY_FIELDS:
        raise ArtifactStoreError("Training model identity is malformed.")
    normalized: dict[str, str] = {}
    for field in sorted(_MODEL_IDENTITY_FIELDS):
        item = value[field]
        if not isinstance(item, str) or not item.strip():
            raise ArtifactStoreError("Training model identity is malformed.")
        normalized[field] = item.strip()
    return normalized


def _validate_loaded_model_identity(
    loaded: dict[str, str] | None,
    current: dict[str, str] | None,
) -> None:
    if current is not None and loaded is None:
        raise UnsupportedArtifactError(
            "Training artifact has no model provider identity. Start a new training "
            "run instead of assigning it to the configured model."
        )
    if loaded is not None and current is not None and loaded != current:
        raise UnsupportedArtifactError(
            "Training artifact model identity does not match the configured model. "
            "Start a new training run."
        )


def _prepare_figure(
    fig: Figure | None,
    figsize: tuple,
    dpi: int,
) -> tuple[Figure, bool]:
    """Return a cleared figure and whether this call created it."""
    if fig is None:
        fig = cast(Figure, plt.figure(figsize=figsize, dpi=dpi))
        return fig, True
    fig.clf()
    return fig, False


def _numeric_series(values: list[float | None]) -> np.ndarray:
    """Convert optional metrics to a plottable series with explicit gaps."""
    return np.asarray(
        [np.nan if value is None else float(value) for value in values],
        dtype=float,
    )


def _serialize_history(
    history: dict[str, list[float | None]],
    *,
    prefix: str,
    arrays: dict[str, object],
) -> list[dict[str, str]]:
    serialized: list[dict[str, str]] = []
    for index, (metric, series) in enumerate(history.items()):
        if not isinstance(metric, str):
            raise ArtifactStoreError(f"{prefix} metric names must be strings.")
        values = np.empty(len(series), dtype=np.float64)
        present = np.zeros(len(series), dtype=np.bool_)
        for value_index, value in enumerate(series):
            if value is None:
                values[value_index] = 0.0
                continue
            try:
                values[value_index] = float(value)
            except (TypeError, ValueError) as exc:
                raise ArtifactStoreError(
                    f"{prefix}.{metric}[{value_index}] must be numeric or null."
                ) from exc
            present[value_index] = True
        values_name = f"{prefix}.{index}.values"
        present_name = f"{prefix}.{index}.present"
        arrays[values_name] = values
        arrays[present_name] = present
        serialized.append(
            {
                "metric": metric,
                "values_array": values_name,
                "present_array": present_name,
            }
        )
    return serialized


def _deserialize_history(
    payload: object,
    *,
    prefix: str,
    arrays: dict[str, np.ndarray],
    consumed_arrays: set[str],
) -> dict[str, list[float | None]]:
    if not isinstance(payload, list):
        raise ArtifactStoreError(f"{prefix} history index is malformed.")
    history: dict[str, list[float | None]] = {}
    for entry in payload:
        if type(entry) is not dict or set(entry) != {
            "metric",
            "values_array",
            "present_array",
        }:
            raise ArtifactStoreError(f"{prefix} history index is malformed.")
        metric = entry["metric"]
        values_name = entry["values_array"]
        present_name = entry["present_array"]
        if (
            not isinstance(metric, str)
            or metric in history
            or not isinstance(values_name, str)
            or not isinstance(present_name, str)
            or values_name not in arrays
            or present_name not in arrays
            or values_name in consumed_arrays
            or present_name in consumed_arrays
        ):
            raise ArtifactStoreError(f"{prefix} history index is malformed.")
        values = arrays[values_name]
        present = arrays[present_name]
        if (
            values.ndim != 1
            or present.ndim != 1
            or values.shape != present.shape
            or present.dtype != np.bool_
        ):
            raise ArtifactStoreError(f"{prefix}.{metric} arrays are malformed.")
        history[metric] = [
            float(value) if is_present else None
            for value, is_present in zip(values, present, strict=True)
        ]
        consumed_arrays.update({values_name, present_name})
    return history


def _decode_training_artifact(
    data: dict[str, object],
    arrays: dict[str, np.ndarray],
    *,
    best_record_keys: set[str],
) -> tuple[
    dict[str, list[float | None]],
    dict[str, list[float | None]],
    dict[str, list[float | None]],
    dict[str, Any],
    int,
    int,
    dict[str, str] | None,
    dict[str, object],
]:
    record_schema_version = data.get("record_schema_version")
    if type(record_schema_version) is not int or record_schema_version not in {
        1,
        TRAIN_RECORD_SCHEMA_VERSION,
    }:
        raise UnsupportedArtifactError(
            "Unsupported training record schema version "
            f"{record_schema_version!r}. Start a new training run; unsafe "
            "migration is not supported."
        )
    consumed_arrays: set[str] = set()
    train = _deserialize_history(
        data.get("train"),
        prefix="train",
        arrays=arrays,
        consumed_arrays=consumed_arrays,
    )
    val = _deserialize_history(
        data.get("val"),
        prefix="val",
        arrays=arrays,
        consumed_arrays=consumed_arrays,
    )
    test = _deserialize_history(
        data.get("test"),
        prefix="test",
        arrays=arrays,
        consumed_arrays=consumed_arrays,
    )
    if consumed_arrays != set(arrays):
        raise ArtifactStoreError(
            "Training record contains unreferenced numeric arrays."
        )
    if set(train) != set(TrainRecordKey()):
        raise ArtifactStoreError("Training record metric coverage is incomplete.")
    if set(val) != set(RecordKey()) or set(test) != set(RecordKey()):
        raise ArtifactStoreError("Validation record metric coverage is incomplete.")
    loaded_best = data.get("best_record")
    if type(loaded_best) is not dict or set(loaded_best) != best_record_keys:
        raise ArtifactStoreError("Training best-record metadata is malformed.")
    seed = data.get("seed")
    epoch = data.get("epoch")
    if (
        isinstance(seed, bool)
        or not isinstance(seed, int)
        or isinstance(epoch, bool)
        or not isinstance(epoch, int)
        or epoch < 0
        or epoch != len(train[RecordKey.LOSS])
    ):
        raise ArtifactStoreError("Training record scalar metadata is malformed.")
    normalized_best: dict[str, Any] = {}
    for key, loaded_value in loaded_best.items():
        normalized_value = (
            None
            if (
                not key.endswith("_epoch")
                and isinstance(loaded_value, (int, float))
                and loaded_value in {-1, torch.inf}
            )
            else loaded_value
        )
        normalized_best[key] = normalized_value
    try:
        model_identity = _normalize_model_identity(data.get("model_identity"))
    except ArtifactStoreError as exc:
        raise UnsupportedArtifactError(
            "Training artifact model identity is malformed. Start a new training run."
        ) from exc
    if record_schema_version == 1:
        if "class_weighting" in data:
            raise UnsupportedArtifactError(
                "v1 training artifact contains class-weighting metadata; "
                "unsafe schema downgrade is not supported."
            )
        class_weighting = _migrate_v1_class_weighting()
    else:
        class_weighting = _normalize_v2_class_weighting(data.get("class_weighting"))
    return (
        train,
        val,
        test,
        normalized_best,
        seed,
        epoch,
        model_identity,
        class_weighting,
    )


class TrainRecord:
    """Class for recording statistics during training

    Attributes:
        repeat: int
            Index of the repeat
        dataset: :class:`XBrainLab.backend.dataset.Dataset`
            Dataset used for training
        model: :class:`torch.nn.Module`
            Model used for training
        option: :class:`XBrainLab.backend.training.TrainingOption`
            Training option
        seed: int
            Random seed
        optim: :class:`torch.optim.Optimizer`
            Optimizer used for training
        criterion: :class:`torch.nn.Module`
            Criterion used for training
        eval_record: :class:`EvalRecord` | None
            Evaluation record, set after training is finished
        best_val_loss_model: :class:`torch.nn.Module` | None
            Model with best validation loss, set during training
        best_val_accuracy_model: :class:`torch.nn.Module` | None
            Model with best validation accuracy, set during training
        best_val_auc_model: :class:`torch.nn.Module` | None
            Model with best validation auc, set during training
        train: dict
            Stores the statistics of each epoch, including loss, accuracy, auc,
            time used and learning rate
        val: dict
            Stores the statistics of each epoch, including loss, auc and accuracy
        best_record: dict
            Stores validation metrics used for checkpoint selection and their epochs.
        epoch: int
            Current epoch
        target_path: str
            Path to save the record
        random_state: tuple
            Random state for reproducibility

    """

    def __init__(
        self,
        repeat: int,
        dataset: Dataset,
        model: torch.nn.Module,
        option: TrainingOption,
        seed: int,
        plan_id: str | None = None,
        model_identity: dict[str, str] | None = None,
        class_weighting_resolution: dict[str, object] | None = None,
        class_weighting_requested: dict[str, object] | None = None,
    ):
        """Initialize a training record.

        Sets up the model, optimizer, criterion, record dictionaries, and
        a new exclusive output directory. Existing runs are never resumed
        implicitly.

        Args:
            repeat: Zero-based index of the training repetition.
            dataset: The dataset used for training.
            model: The PyTorch model to train.
            option: Training configuration options.
            seed: Random seed for reproducibility.
            plan_id: Optional unique identifier (timestamp) for the training plan,
                used to construct the output path.

        """
        self.repeat = repeat
        self.dataset = dataset
        self.option = option
        self.seed = seed
        self.plan_id = plan_id
        self.model_identity = _normalize_model_identity(model_identity)
        self.model = model
        self.optim = self.option.get_optim(model)
        requested = class_weighting_requested or class_weighting_request(self.option)
        resolved = class_weighting_resolution or _off_class_weighting()["resolved"]
        self._set_class_weighting(
            {
                "requested": requested,
                "resolved": resolved,
            }
        )
        self._state_tracker: TrainingStateTracker | None = None
        self.eval_record: EvalRecord | None = None
        self.evaluation_records: dict[str, EvalRecord] = {}
        for key in RecordKey():
            setattr(self, "best_val_" + key + "_model", None)
        self.train: dict[str, list[float | None]] = {i: [] for i in TrainRecordKey()}
        self.val: dict[str, list[float | None]] = {i: [] for i in RecordKey()}
        # Private compatibility data used only to render records from older releases.
        self._legacy_test_history: dict[str, list[float | None]] = {
            i: [] for i in RecordKey()
        }
        self.best_record: dict[str, Any] = {}
        for key in RecordKey():
            self.best_record[f"best_val_{key}"] = None
            self.best_record[f"best_val_{key}_epoch"] = None

        self.epoch = 0
        self.target_path: str | None = None
        self._artifact_io_path: str | None = None
        self._output_directory: ContainedOutputDirectory | None = None
        self.init_dir()
        self.random_state = get_random_state()
        self.start_timestamp: float | None = None
        self.end_timestamp: float | None = None

    def bind_state_tracker(self, tracker: TrainingStateTracker) -> None:
        """Bind record mutations to the owning trainer's state token."""
        self._state_tracker = tracker

    def _state_mutation(self):
        """Return the shared mutation context when attached to a trainer."""
        tracker = self._state_tracker
        return tracker.mutation() if tracker is not None else nullcontext()

    def _set_class_weighting(self, class_weighting: dict[str, object]) -> None:
        """Replace record-local weighting evidence and its matching criterion."""
        requested = class_weighting.get("requested")
        resolved = class_weighting.get("resolved")
        if not isinstance(requested, dict) or not isinstance(resolved, dict):
            raise ValueError("Training class-weighting metadata is malformed.")
        self.class_weighting = {
            "requested": deepcopy(requested),
            "resolved": deepcopy(resolved),
        }
        self.class_weighting_resolution = self.class_weighting["resolved"]
        self.criterion = _build_class_weighting_criterion(self.class_weighting)

    def init_dir(self) -> None:
        """Initialize the output directory for saving checkpoints and records.

        Creates the directory tree:
        ``output_dir / dataset_filesystem_identity / model_planid / repeat``.
        """
        display_name = self.dataset.get_name()
        record_name = filesystem_safe_identity(
            display_name,
            field="dataset display metadata",
        )
        repeat_name = self.get_name()

        model_name = self.model.__class__.__name__
        unique_id = f"{model_name}_{self.plan_id}" if self.plan_id else model_name

        output_directory = create_contained_output_directory(
            self.option.get_output_dir(),
            record_name,
            unique_id,
            repeat_name,
            exclusive=True,
            legacy_components=(display_name,),
        )
        previous_directory = self._output_directory
        self._output_directory = output_directory
        self.target_path = str(output_directory.path)
        self._artifact_io_path = str(output_directory.io_path)
        if previous_directory is not None:
            previous_directory.close()

    def resume(self) -> None:
        """Restore global RNG state for a holder-approved local transition.

        ``TrainingPlanHolder`` permits this only for an untouched repeat, which
        it immediately reseeds, or completed in-memory training entering
        evaluation. DataLoader generator state is excluded, so partial stochastic
        training cannot resume reproducibly through this method.
        """
        with self._state_mutation():
            set_random_state(self.random_state)
            if self.start_timestamp is None:
                self.start_timestamp = time.time()
            self.end_timestamp = None

    def _retain_artifact_identity(
        self,
        target_path: str,
    ) -> StableDirectoryIdentity:
        """Bind one persistence operation to the admitted output directory."""
        output_directory = self._output_directory
        if output_directory is not None:
            return output_directory.retain_identity()
        return retain_directory_identity(target_path)

    def pause(self) -> None:
        """Capture process-local global RNG state and an end timestamp.

        This is not a resumable checkpoint because DataLoader generator state is
        not captured.
        """
        with self._state_mutation():
            self.random_state = get_random_state()
            self.end_timestamp = time.time()

    def get_name(self) -> str:
        """Return the display name of this record.

        Returns:
            A string formatted as ``'Repeat-{index}'``.

        """
        return f"Repeat-{self.repeat}"

    def get_epoch(self) -> int:
        """Return the current epoch number.

        Returns:
            The number of epochs completed so far.

        """
        return self.epoch

    def get_training_model(self, device: str) -> torch.nn.Module:
        """Return the model moved to the specified device for training.

        Args:
            device: PyTorch device string (e.g., ``'cpu'`` or ``'cuda:0'``).

        Returns:
            The model on the target device.

        """
        self.model = self.model.to(device)
        self.criterion = self.criterion.to(device)
        return self.model

    def is_finished(self) -> bool:
        """Check whether training and evaluation are both complete.

        Returns:
            ``True`` if the current epoch meets or exceeds the target and
            an evaluation record exists.

        """
        return self.get_epoch() >= self.option.epoch and self.eval_record is not None

    def append_record(self, val: Any, arr: list) -> None:
        """Internal function for appending a value to a statistic array

        Fill the array with None if the data is not available before the current epoch

        Args:
            val: Value to be appended
            arr: Array to be appended

        """
        with self._state_mutation():
            self._append_record(val, arr)

    def _append_record(self, val: Any, arr: list) -> None:
        """Append one value while the caller owns the mutation interval."""
        while len(arr) < self.epoch:
            arr.append(None)
        if len(arr) > self.epoch:
            arr[self.epoch] = val
        elif len(arr) == self.epoch:
            arr.append(val)

    def _update_validation_metrics(
        self,
        test_result: dict[str, float | None],
    ) -> None:
        """Append validation metrics and update validation checkpoint tracking.

        For each metric key in ``test_result``, appends the value to the
        corresponding record list and updates the best model state dict if
        the new value surpasses the previous best.

        Args:
            test_result: Dictionary mapping :class:`RecordKey` values to
                metric values for the current epoch.

        """
        for key, value in test_result.items():
            self._append_record(value, self.val[key])
            if value is None:
                continue
            best_key = f"best_val_{key}"
            previous = self.best_record[best_key]
            if "loss" in key:
                should_update = previous is None or value <= previous
            else:
                should_update = previous is None or value >= previous
            if should_update:
                self.best_record[best_key] = value
                self.best_record[f"{best_key}_epoch"] = self.get_epoch()
                setattr(
                    self,
                    f"best_val_{key}_model",
                    {k: v.cpu().clone() for k, v in self.model.state_dict().items()},
                )

    def update_validation(self, result: dict[str, float | None]) -> None:
        """Append validation statistics and update the best validation model.

        Args:
            result: Dictionary of validation metrics for the current epoch.

        """
        with self._state_mutation():
            self._update_validation_metrics(result)

    def update_train(self, test_result: dict[str, float | None]) -> None:
        """Append training statistics for the current epoch.

        Args:
            test_result: Dictionary of training metrics (loss, accuracy, AUC).

        """
        with self._state_mutation():
            for key, value in test_result.items():
                self._append_record(value, self.train[key])

    def update_statistic(self, statistic: dict[str, float]) -> None:
        """Append extra statistics (e.g., learning rate) for the current epoch.

        Args:
            statistic: Dictionary of statistic values to record.

        """
        with self._state_mutation():
            for key, value in statistic.items():
                self._append_record(value, self.train[key])

    def step(self) -> None:
        """Advance the epoch counter by one."""
        with self._state_mutation():
            self.epoch += 1

    def set_eval_record(self, eval_record: EvalRecord) -> None:
        """Set the evaluation record after training completes.

        Args:
            eval_record: The :class:`EvalRecord` containing final evaluation results.

        """
        with self._state_mutation():
            self._replace_primary_evaluation_record(eval_record)

    def _replace_primary_evaluation_record(self, eval_record: EvalRecord) -> None:
        """Replace the compatibility record and its matching split entry."""
        self.eval_record = eval_record
        evaluation_records = self._evaluation_record_store()
        split = (
            str(getattr(eval_record, "evaluation_split", None) or "unknown")
            .strip()
            .casefold()
        )
        if split in EVALUATION_SPLITS:
            evaluation_records[split] = eval_record

    def _replace_saliency_evaluation_record(self, eval_record: EvalRecord) -> None:
        """Store saliency on its source split without changing primary metrics."""
        split = (
            str(getattr(eval_record, "evaluation_split", None) or "unknown")
            .strip()
            .casefold()
        )
        if split not in EVALUATION_SPLITS:
            self._replace_primary_evaluation_record(eval_record)
            return
        evaluation_records = self._evaluation_record_store()
        primary_split = (
            str(getattr(self.eval_record, "evaluation_split", None) or "unknown")
            .strip()
            .casefold()
        )
        evaluation_records[split] = eval_record
        if primary_split == split:
            self.eval_record = eval_record

    def _evaluation_record_store(self) -> dict[str, EvalRecord]:
        """Return the split record store, initializing legacy instances lazily."""
        evaluation_records = getattr(self, "evaluation_records", None)
        if not isinstance(evaluation_records, dict):
            evaluation_records = {}
            self.evaluation_records = evaluation_records
        return evaluation_records

    def set_evaluation_records(
        self,
        records: dict[str, EvalRecord],
        *,
        primary_split: str,
    ) -> None:
        """Publish split-specific predictions and the primary held-out record."""
        normalized_primary = str(primary_split).strip().casefold()
        normalized = {
            str(split).strip().casefold(): record
            for split, record in records.items()
            if record is not None
        }
        if normalized_primary not in normalized:
            raise ValueError("Primary evaluation split is missing")
        if any(split not in EVALUATION_SPLITS for split in normalized):
            raise ValueError("Unsupported evaluation split")
        with self._state_mutation():
            self.evaluation_records = normalized
            self.eval_record = normalized[normalized_primary]

    def export_checkpoint(self) -> None:
        """Save the current training state, best models, and evaluation record to disk.

        Exports the model state dict, record statistics, best model state dicts,
        and the evaluation record (if available) to :attr:`target_path`.
        """
        epoch = len(self.train[RecordKey.LOSS])

        target_path = self._artifact_io_path
        if not target_path:
            return
        with self._retain_artifact_identity(target_path) as identity:
            if self.eval_record:
                self.eval_record.export(
                    target_path,
                    directory_identity=identity,
                )
            for split, eval_record in self.evaluation_records.items():
                if eval_record is self.eval_record:
                    continue
                eval_record.export(
                    target_path,
                    artifact_basename=f"eval-{split}",
                    directory_identity=identity,
                )

            for key in RecordKey():
                full_key = f"best_val_{key}_model"
                model = getattr(self, full_key)
                if model:
                    save_model_state_dict(
                        model,
                        os.path.join(target_path, full_key),
                        directory_identity=identity,
                    )

            fname = f"Epoch-{epoch}-model"
            save_model_state_dict(
                self.model.state_dict(),
                os.path.join(target_path, fname),
                directory_identity=identity,
            )
            arrays: dict[str, object] = {}
            payload = {
                "record_schema_version": TRAIN_RECORD_SCHEMA_VERSION,
                "epoch": epoch,
                "train": _serialize_history(
                    self.train,
                    prefix="train",
                    arrays=arrays,
                ),
                "val": _serialize_history(
                    self.val,
                    prefix="val",
                    arrays=arrays,
                ),
                "test": _serialize_history(
                    self._legacy_test_history,
                    prefix="test",
                    arrays=arrays,
                ),
                "best_record": self.best_record,
                "seed": self.seed,
                "class_weighting": deepcopy(self.class_weighting),
            }
            if self.model_identity is not None:
                payload["model_identity"] = dict(self.model_identity)
            write_json_npz_artifact(
                os.path.join(target_path, "record"),
                artifact_type=TRAINING_RECORD_ARTIFACT_TYPE,
                payload=payload,
                arrays=arrays,
                arrays_filename="record.npz",
                directory_identity=identity,
            )

    def load(self) -> None:
        """Load a previously saved training record from disk.

        Restores training statistics, best records, seed, and evaluation record
        only from the already-bound secure artifact directory. Model, optimizer,
        global RNG, and DataLoader generator continuation state are not persisted
        together, so a partial record cannot resume stochastic training.
        """
        with self._state_mutation():
            target_path = self._artifact_io_path
            if not target_path:
                return
            try:
                identity = self._retain_artifact_identity(target_path)
            except FileNotFoundError:
                return
            with identity:
                record_path = os.path.join(target_path, "record")
                if os.path.exists(record_path):
                    try:
                        data, arrays = read_json_npz_artifact(
                            record_path,
                            expected_artifact_type=TRAINING_RECORD_ARTIFACT_TYPE,
                            directory_identity=identity,
                        )
                        (
                            train,
                            val,
                            test,
                            loaded_best,
                            seed,
                            epoch,
                            loaded_model_identity,
                            class_weighting,
                        ) = _decode_training_artifact(
                            data,
                            arrays,
                            best_record_keys=set(self.best_record),
                        )
                        _validate_loaded_model_identity(
                            loaded_model_identity,
                            self.model_identity,
                        )
                        self.best_record.update(loaded_best)
                        self.train = train
                        self.val = val
                        self._legacy_test_history = test
                        self.seed = seed
                        self.epoch = epoch
                        if loaded_model_identity is not None:
                            self.model_identity = loaded_model_identity
                        self._set_class_weighting(class_weighting)
                    except (FilesystemIdentityError, UnsupportedArtifactError):
                        raise
                    except Exception as e:
                        logger.error(
                            "Failed to load TrainRecord stats: %s",
                            e,
                            exc_info=True,
                        )

                self.eval_record = EvalRecord.load(
                    target_path,
                    directory_identity=identity,
                )
                self.evaluation_records = {}
                if self.eval_record is not None:
                    split = (
                        str(self.eval_record.evaluation_split or "unknown")
                        .strip()
                        .casefold()
                    )
                    if split in EVALUATION_SPLITS:
                        self.evaluation_records[split] = self.eval_record
                for split in EVALUATION_SPLITS:
                    loaded = EvalRecord.load(
                        target_path,
                        artifact_basename=f"eval-{split}",
                        directory_identity=identity,
                    )
                    if loaded is not None:
                        self.evaluation_records[split] = loaded

    def get_model_output(self) -> str:
        """Return a formatted string summary of the training history.

        Returns:
            A multi-line string containing epoch count, best performance
            metrics, and last-epoch statistics.

        """
        lines = []
        lines.append(f"=== Training Summary for {self.get_name()} ===")
        lines.append(f"Total Training Epochs: {self.epoch}")

        # Best Performance
        lines.append("\n[Best Performance]")
        for key, val in self.best_record.items():
            if "epoch" in key:
                continue
            epoch_key = key + "_epoch"
            epoch_val = self.best_record.get(epoch_key, "-")
            formatted = "N/A" if val is None else f"{val:.4f}"
            lines.append(f"  {key}: {formatted} (Training epoch {epoch_val or '-'})")

        # Last training-epoch statistics
        lines.append("\n[Last Training Epoch Statistics]")
        if self.epoch > 0:
            idx = -1

            def get_val(d, k):
                return d[k][idx] if len(d[k]) > 0 else "N/A"

            def fmt(val, p=4):
                if isinstance(val, (int, float)):
                    return f"{val:.{p}f}"
                return str(val)

            lines.append(f"  Train Loss: {fmt(get_val(self.train, RecordKey.LOSS))}")
            lines.append(f"  Train Acc:  {fmt(get_val(self.train, RecordKey.ACC), 2)}%")
            lines.append(f"  Val Loss:   {fmt(get_val(self.val, RecordKey.LOSS))}")
            lines.append(f"  Val Acc:    {fmt(get_val(self.val, RecordKey.ACC), 2)}%")
        else:
            lines.append("  No training data available.")

        return "\n".join(lines)

    # figure
    def get_loss_figure(
        self,
        fig: Figure | None = None,
        figsize: tuple = (6.4, 4.8),
        dpi: int = 100,
    ) -> Figure | None:
        """Generate a line chart of training, validation, and test loss over epochs.

        Args:
            fig: Existing figure to plot on. If ``None``, a new figure is created.
            figsize: Width and height of the figure in inches.
            dpi: Dots per inch for the figure.

        Returns:
            The matplotlib :class:`~matplotlib.figure.Figure`, or ``None``
            if no loss data is available.

        """
        figure, created_figure = _prepare_figure(fig, figsize, dpi)

        training_loss_list = self.train[RecordKey.LOSS]
        val_loss_list = self.val[RecordKey.LOSS]
        test_loss_list = self._legacy_test_history[RecordKey.LOSS]
        if (
            len(training_loss_list) == 0
            and len(val_loss_list) == 0
            and len(test_loss_list) == 0
        ):
            if created_figure:
                plt.close(figure)
            return None

        ax = figure.add_subplot(111)
        if len(training_loss_list) > 0:
            ax.plot(_numeric_series(training_loss_list), "g", label="Training loss")
        if len(val_loss_list) > 0:
            ax.plot(_numeric_series(val_loss_list), "b", label="validation loss")
        if len(test_loss_list) > 0:
            ax.plot(_numeric_series(test_loss_list), "r", label="testing loss")
        ax.set_title("Training loss")
        ax.set_xlabel("Training epochs")
        ax.set_ylabel("Loss")
        _ = ax.legend(loc="center left")

        return figure

    def get_acc_figure(
        self,
        fig: Figure | None = None,
        figsize: tuple = (6.4, 4.8),
        dpi: int = 100,
    ) -> Figure | None:
        """Generate a line chart of training, validation, and test accuracy over epochs.

        Args:
            fig: Existing figure to plot on. If ``None``, a new figure is created.
            figsize: Width and height of the figure in inches.
            dpi: Dots per inch for the figure.

        Returns:
            The matplotlib :class:`~matplotlib.figure.Figure`, or ``None``
            if no accuracy data is available.

        """
        figure, created_figure = _prepare_figure(fig, figsize, dpi)

        training_acc_list = self.train[RecordKey.ACC]
        val_acc_list = self.val[RecordKey.ACC]
        test_acc_list = self._legacy_test_history[RecordKey.ACC]
        if (
            len(training_acc_list) == 0
            and len(val_acc_list) == 0
            and len(test_acc_list) == 0
        ):
            if created_figure:
                plt.close(figure)
            return None

        ax = figure.add_subplot(111)
        if len(training_acc_list) > 0:
            ax.plot(_numeric_series(training_acc_list), "g", label="Training accuracy")
        if len(val_acc_list) > 0:
            ax.plot(_numeric_series(val_acc_list), "b", label="validation accuracy")
        if len(test_acc_list) > 0:
            ax.plot(_numeric_series(test_acc_list), "r", label="testing accuracy")
        ax.set_title("Training Accuracy")
        ax.set_xlabel("Training epochs")
        ax.set_ylabel("Accuracy (%)")
        _ = ax.legend(loc="upper left")

        return figure

    def get_auc_figure(
        self,
        fig: Figure | None = None,
        figsize: tuple = (6.4, 4.8),
        dpi: int = 100,
    ) -> Figure | None:
        """Generate a line chart of training, validation, and test AUC over epochs.

        Args:
            fig: Existing figure to plot on. If ``None``, a new figure is created.
            figsize: Width and height of the figure in inches.
            dpi: Dots per inch for the figure.

        Returns:
            The matplotlib :class:`~matplotlib.figure.Figure`, or ``None``
            if no AUC data is available.

        """
        figure, created_figure = _prepare_figure(fig, figsize, dpi)

        training_auc_list = self.train[RecordKey.AUC]
        val_auc_list = self.val[RecordKey.AUC]
        test_auc_list = self._legacy_test_history[RecordKey.AUC]
        if (
            len(training_auc_list) == 0
            and len(val_auc_list) == 0
            and len(test_auc_list) == 0
        ):
            if created_figure:
                plt.close(figure)
            return None

        ax = figure.add_subplot(111)
        if len(training_auc_list) > 0:
            ax.plot(_numeric_series(training_auc_list), "g", label="Training AUC")
        if len(val_auc_list) > 0:
            ax.plot(_numeric_series(val_auc_list), "b", label="validation AUC")
        if len(test_auc_list) > 0:
            ax.plot(_numeric_series(test_auc_list), "r", label="testing AUC")
        ax.set_title("Training AUC")
        ax.set_xlabel("Training epochs")
        ax.set_ylabel("AUC")
        _ = ax.legend(loc="upper left")

        return figure

    def get_lr_figure(
        self,
        fig: Figure | None = None,
        figsize: tuple = (6.4, 4.8),
        dpi: int = 100,
    ) -> Figure | None:
        """Generate a line chart of learning rate over epochs.

        Args:
            fig: Existing figure to plot on. If ``None``, a new figure is created.
            figsize: Width and height of the figure in inches.
            dpi: Dots per inch for the figure.

        Returns:
            The matplotlib :class:`~matplotlib.figure.Figure`, or ``None``
            if no learning rate data is available.

        """
        figure, created_figure = _prepare_figure(fig, figsize, dpi)

        lr_list = self.train[TrainRecordKey.LR]
        if len(lr_list) == 0:
            if created_figure:
                plt.close(figure)
            return None

        ax = figure.add_subplot(111)
        ax.plot(_numeric_series(lr_list), "g")
        ax.set_title("Learning Rate")
        ax.set_xlabel("Training epochs")
        ax.set_ylabel("lr")
        return figure

    def get_confusion_figure(
        self,
        fig: Figure | None = None,
        figsize: tuple = (6.4, 4.8),
        dpi: int = 100,
        show_percentage: bool = False,
    ) -> Figure | None:
        """Generate a confusion matrix heatmap from the evaluation record.

        Args:
            fig: Existing figure to plot on. If ``None``, a new figure is created.
            figsize: Width and height of the figure in inches.
            dpi: Dots per inch for the figure.
            show_percentage: If ``True``, show row-normalized percentages
                instead of raw counts.

        Returns:
            The matplotlib :class:`~matplotlib.figure.Figure`, or ``None``
            if no evaluation record is available.

        """
        figure, created_figure = _prepare_figure(fig, figsize, dpi)
        if not self.eval_record:
            if created_figure:
                plt.close(figure)
            return None
        output = self.eval_record.output
        label = self.eval_record.label
        confusion = calculate_confusion(output, label)
        class_num = confusion.shape[0]

        if show_percentage:
            # Normalize by row (Ground Truth)
            row_sums = confusion.sum(axis=1, keepdims=True)
            row_sums[row_sums == 0] = 1  # Avoid division by zero
            plot_data = confusion / row_sums
        else:
            plot_data = confusion

        ax = figure.add_subplot(111)
        ax.set_title("Confusion matrix", color="#cccccc", pad=20)

        # Improved Labels
        ax.set_xlabel("Predicted Label", labelpad=10, color="#cccccc")
        ax.set_ylabel("True Label", labelpad=10, color="#cccccc")

        res = ax.imshow(plot_data, cmap="magma", interpolation="nearest")

        # Threshold for text color
        threshold = (plot_data.max() + plot_data.min()) / 2

        for x in range(class_num):
            for y in range(class_num):
                val = plot_data[x][y]
                annot_color = "k" if val > threshold else "w"

                text = f"{val:.1%}" if show_percentage else str(int(val))

                ax.annotate(
                    text,
                    xy=(y, x),
                    horizontalalignment="center",
                    verticalalignment="center",
                    color=annot_color,
                )

        # Colorbar
        cbar = figure.colorbar(res)
        cbar.ax.yaxis.set_tick_params(color="#cccccc")
        plt.setp(cbar.ax.get_yticklabels(), color="#cccccc")

        # Ticks
        labels = [self.dataset.get_epoch_data().label_map[i] for i in range(class_num)]
        ax.set_xticks(range(class_num), labels, rotation=0, ha="center")
        ax.set_yticks(range(class_num), labels, va="center")

        # Styling
        ax.tick_params(axis="x", colors="#cccccc")
        ax.tick_params(axis="y", colors="#cccccc")
        for spine in ax.spines.values():
            spine.set_edgecolor("#444444")

        # Ensure tight layout handles labels correctly
        figure.tight_layout()

        return figure

    # get evaluate
    def get_acc(self) -> float | None:
        """Return the evaluation accuracy, or ``None`` if not yet evaluated.

        Returns:
            Accuracy as a float, or ``None``.

        """
        if not self.eval_record:
            return None
        return self.eval_record.get_acc()

    def get_auc(self) -> float | None:
        """Return the evaluation AUC, or ``None`` if not yet evaluated.

        Returns:
            AUC score as a float, or ``None``.

        """
        if not self.eval_record:
            return None
        return self.eval_record.get_auc()

    def get_kappa(self) -> float | None:
        """Return the evaluation Cohen's Kappa, or ``None`` if not yet evaluated.

        Returns:
            Kappa coefficient as a float, or ``None``.

        """
        if not self.eval_record:
            return None
        return self.eval_record.get_kappa()

    def get_eval_record(self) -> EvalRecord | None:
        """Return the evaluation record, or ``None`` if training is not complete.

        Returns:
            The :class:`EvalRecord` instance, or ``None``.

        """
        return self.eval_record

    def get_saliency_eval_record(self) -> EvalRecord | None:
        """Return the split record containing saliency without changing metrics."""
        evaluation_records = self._evaluation_record_store()
        candidates = [
            self.eval_record,
            evaluation_records.get("test"),
            evaluation_records.get("validation"),
            evaluation_records.get("training"),
        ]
        seen: set[int] = set()
        for candidate in candidates:
            if candidate is None or id(candidate) in seen:
                continue
            seen.add(id(candidate))
            if any(
                bool(getattr(candidate, attribute, None))
                for attribute in (
                    "gradient",
                    "gradient_input",
                    "smoothgrad",
                    "smoothgrad_sq",
                    "vargrad",
                )
            ):
                return candidate
        return self.eval_record
