"""Training option and configuration classes for model training."""

import hashlib
import json
import math
import os
import secrets
from collections.abc import Callable
from enum import Enum
from typing import Any

import numpy as np
import torch
from torch import nn

from XBrainLab.backend.utils.logger import logger

from .input_contract import (
    TrainingInputContractError,
    normalize_non_negative_finite_float,
    normalize_non_negative_integer,
    normalize_positive_finite_float,
    normalize_positive_integer,
)

MIN_TRAINING_SEED = 0
MAX_TRAINING_SEED = 0xFFFF_FFFF


def _normalize_output_dir(value: Any) -> str:
    """Return one non-empty filesystem path string or reject the value."""
    if isinstance(value, os.PathLike):
        value = os.fspath(value)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Output directory not set")
    return value


class TrainingEvaluation(Enum):
    """Enumeration of model selection strategies for evaluation.

    Attributes:
        VAL_LOSS: Select model with the best (lowest) validation loss.
        VAL_AUC: Select model with the best validation AUC.
        VAL_ACC: Select model with the best validation accuracy.
        LAST_EPOCH: Use the model from the last training epoch.

    """

    VAL_LOSS = "Best validation loss"
    VAL_AUC = "Best validation AUC"
    VAL_ACC = "Best validation performance"
    LAST_EPOCH = "Last Epoch"

    @classmethod
    def _missing_(cls, value):
        """Migrate persisted test-based choices to validation selection."""
        legacy = {
            "Best testing AUC": cls.VAL_AUC,
            "Best testing performance": cls.VAL_ACC,
        }
        migrated = legacy.get(str(value))
        if migrated is not None:
            logger.warning(
                "Migrating persisted test-based model selection %r to %s",
                value,
                migrated.value,
            )
        return migrated


class ClassWeightMode(str, Enum):
    """Requested training-loss weighting policy."""

    OFF = "off"
    BALANCED = "balanced"
    CUSTOM = "custom"


def _normalize_class_map(class_map: object) -> dict[int, str]:
    """Return the reviewed numeric class map in its one canonical form."""
    if not isinstance(class_map, dict) or not class_map:
        raise ValueError("Training class map is invalid")
    normalized: dict[int, str] = {}
    for index, name in class_map.items():
        if type(index) is not int or not isinstance(name, str):
            raise ValueError("Training class map is invalid")
        normalized_name = name.strip()
        if (
            not normalized_name
            or index in normalized
            or normalized_name in normalized.values()
        ):
            raise ValueError("Training class map is invalid")
        normalized[index] = normalized_name
    return dict(sorted(normalized.items()))


def class_map_fingerprint(class_map: dict[int, str]) -> str:
    """Return a stable identity for one reviewed numeric class map."""
    normalized = {
        str(index): name for index, name in _normalize_class_map(class_map).items()
    }
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_canonical_class_map_fingerprint(value: object) -> bool:
    """Return whether one captured map identity is canonical SHA-256 hex."""
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def normalize_class_weight_mode(value: Any) -> ClassWeightMode:
    try:
        if isinstance(value, ClassWeightMode):
            return value
        return ClassWeightMode(str(value))
    except ValueError as exc:
        raise ValueError("Invalid class loss weighting mode") from exc


def normalize_custom_class_weights(value: Any) -> dict[str, float]:
    if not isinstance(value, dict) or not value:
        raise ValueError("Custom class loss weights are required")
    normalized: dict[str, float] = {}
    for name, multiplier in value.items():
        if not isinstance(name, str):
            raise ValueError("Custom class loss weights must use unique class names")
        normalized_name = name.strip()
        if not normalized_name or normalized_name in normalized:
            raise ValueError("Custom class loss weights must use unique class names")
        try:
            parsed = float(multiplier)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                "Custom class loss weights must be positive and finite"
            ) from exc
        if isinstance(multiplier, bool) or not math.isfinite(parsed) or parsed <= 0:
            raise ValueError("Custom class loss weights must be positive and finite")
        normalized[normalized_name] = parsed
    return normalized


def validate_custom_class_weight_names(
    custom_class_weights: object,
    class_map: dict[int, str],
) -> dict[str, float]:
    """Normalize Custom multipliers and require the exact reviewed name set."""
    normalized = normalize_custom_class_weights(custom_class_weights)
    class_names = set(_normalize_class_map(class_map).values())
    if set(normalized) != class_names:
        raise ValueError(
            "Custom class loss weights do not match the reviewed class map."
        )
    return normalized


def resolve_class_weighting(
    *,
    mode: ClassWeightMode | str,
    custom_class_weights: dict[str, float] | None,
    class_map_fingerprint_value: str | None,
    class_map: dict[int, str],
    labels: object,
    train_mask: object,
) -> dict[str, object]:
    """Resolve one fold-local criterion policy before training mutates state.

    The same pure policy serves Start admission and plan construction so a
    reviewed class-map change or zero-count class cannot be admitted on one path
    and fail later on another.  Only ``train_mask`` labels contribute to counts.
    """
    normalized_mode = normalize_class_weight_mode(mode)
    normalized_map = _normalize_class_map(class_map)
    actual_fingerprint = class_map_fingerprint(normalized_map)
    if normalized_mode is not ClassWeightMode.OFF and (
        not is_canonical_class_map_fingerprint(class_map_fingerprint_value)
        or class_map_fingerprint_value != actual_fingerprint
    ):
        raise ValueError(
            "Reviewed class mapping changed. Reopen Training Settings before training."
        )

    label_values = np.asarray(labels)
    mask_values = np.asarray(train_mask, dtype=bool)
    if (
        label_values.ndim != 1
        or mask_values.ndim != 1
        or label_values.shape[0] != mask_values.shape[0]
    ):
        raise ValueError("Training split labels are invalid")
    train_labels = label_values[mask_values]
    class_order = list(normalized_map)
    class_names = [normalized_map[index] for index in class_order]
    counts = [int(np.sum(train_labels == index)) for index in class_order]
    missing_names = [
        name for name, count in zip(class_names, counts, strict=True) if count == 0
    ]
    if missing_names:
        raise ValueError(
            "Training split is missing class(es): " + ", ".join(missing_names) + "."
        )

    if normalized_mode is ClassWeightMode.BALANCED:
        total = int(train_labels.shape[0])
        class_count = len(class_order)
        weights = [total / (class_count * count) for count in counts]
    elif normalized_mode is ClassWeightMode.CUSTOM:
        requested = validate_custom_class_weight_names(
            custom_class_weights,
            normalized_map,
        )
        weights = [requested[name] for name in class_names]
    else:
        weights = [1.0] * len(class_order)

    return {
        "class_names": class_names,
        "class_order": class_order,
        "class_counts": counts,
        "weights": weights,
    }


def class_weighting_request(
    option: object,
    *,
    class_map: dict[int, str] | None = None,
) -> dict[str, object]:
    """Detach the complete requested policy persisted with a training run."""
    mode = normalize_class_weight_mode(getattr(option, "class_weight_mode", "off"))
    custom = (
        normalize_custom_class_weights(getattr(option, "custom_class_weights", None))
        if mode is ClassWeightMode.CUSTOM
        else {}
    )
    fingerprint = (
        class_map_fingerprint(class_map)
        if class_map is not None
        else getattr(option, "class_map_fingerprint", None)
    )
    if mode is not ClassWeightMode.OFF and not is_canonical_class_map_fingerprint(
        fingerprint
    ):
        raise ValueError("Training class map identity is required")
    return {
        "mode": mode.value,
        "custom_class_weights": custom,
        "class_map_fingerprint": fingerprint
        if is_canonical_class_map_fingerprint(fingerprint)
        else None,
    }


def parse_device_name(use_cpu: bool, gpu_idx: int | None) -> str:
    """Return a human-readable device description string.

    Args:
        use_cpu: Whether to use CPU.
        gpu_idx: GPU device index, or ``None`` if CPU is used.

    Returns:
        A string describing the device (e.g., ``'cpu'`` or
        ``'0 - NVIDIA GeForce RTX 3090'``).

    Raises:
        ValueError: If neither CPU nor a valid GPU index is specified.

    """
    if use_cpu:
        return "cpu"
    if gpu_idx is not None:
        return f"{gpu_idx} - {torch.cuda.get_device_name(gpu_idx)}"
    raise ValueError("Device not set")


def is_cuda_device_usable(gpu_idx: int | None) -> tuple[bool, str | None]:
    """Check whether a requested CUDA device can actually execute work.

    Args:
        gpu_idx: Zero-based CUDA device index.

    Returns:
        A tuple of ``(usable, reason)`` where ``reason`` is populated when
        the device cannot be used safely.

    """
    if gpu_idx is None:
        return False, "CUDA device index not set"
    if not torch.cuda.is_available():
        return False, "CUDA is not available"

    device_count = torch.cuda.device_count()
    if gpu_idx < 0 or gpu_idx >= device_count:
        return False, f"CUDA device index {gpu_idx} is out of range"

    try:
        probe = torch.zeros(1, device=f"cuda:{gpu_idx}")  # pyright: ignore[reportPrivateImportUsage]
        del probe
    except Exception as exc:  # pragma: no cover - hardware/runtime specific
        return False, str(exc)

    return True, None


def parse_optim_name(optim: type, optim_params: dict) -> str:
    """Return a formatted optimizer description string.

    Args:
        optim: Optimizer class (e.g., :class:`torch.optim.Adam`).
        optim_params: Dictionary of optimizer parameters.

    Returns:
        A string formatted as ``'OptimizerName (param1=val1, ...)'``.

    """
    option_list = [f"{i}={optim_params[i]}" for i in optim_params if optim_params[i]]
    options = ", ".join(option_list)
    return f"{optim.__name__} ({options})"


class TrainingOption:
    """Utility class for storing training options

    Attributes:
        output_dir: Output directory
        optim: Optimizer class of type :class:`torch.optim.Optimizer`
        optim_params: Optimizer parameters
        use_cpu: Whether to use CPU
        gpu_idx: GPU index
        epoch: Number of epochs
        bs: Batch size
        lr: Learning rate
        checkpoint_epoch: Checkpoint epoch
        evaluation_option: Model selection option
        repeat_num: Number of repeats
        seed: Unsigned 32-bit base seed. A base is generated once when omitted;
            repeat ``i`` uses ``seed + i``.
        criterion: Loss function

    """

    def __init__(
        self,
        output_dir: str,
        optim: type | None,
        optim_params: dict | None,
        use_cpu: bool,
        gpu_idx: int | None,
        epoch: int,
        bs: int,
        lr: float,
        checkpoint_epoch: int,
        evaluation_option: TrainingEvaluation,
        repeat_num: int,
        seed: int | None = None,
        class_weight_mode: ClassWeightMode | str = ClassWeightMode.OFF,
        custom_class_weights: dict[str, float] | None = None,
        class_map_fingerprint_value: str | None = None,
        early_stopping_enabled: bool = False,
        early_stopping_patience: int = 3,
        early_stopping_min_delta: float = 0.0,
    ):
        """Initialize training options and validate them.

        Args:
            output_dir: Directory path for saving training outputs.
            optim: Optimizer class (subclass of :class:`torch.optim.Optimizer`),
                or ``None``.
            optim_params: Dictionary of optimizer-specific parameters, or ``None``.
            use_cpu: Whether to train on CPU.
            gpu_idx: GPU device index, or ``None`` if using CPU.
            epoch: Total number of training epochs.
            bs: Batch size.
            lr: Learning rate.
            checkpoint_epoch: Save checkpoint every N epochs.
            evaluation_option: Model selection strategy.
            repeat_num: Number of training repetitions.
            seed: Optional reproducibility base seed in ``0..2^32-1``. When
                omitted, one base is generated during validation. Each repeat
                derives ``seed + repeat_index`` without wraparound.

        Raises:
            ValueError: If any option is invalid or not set.

        """
        self.output_dir = output_dir
        self.optim: type | None = optim
        self.optim_params: dict | None = optim_params
        self.use_cpu = use_cpu
        self.gpu_idx = gpu_idx
        self.epoch = epoch
        self.bs = bs
        self.lr = lr
        self.checkpoint_epoch = checkpoint_epoch
        self.evaluation_option = evaluation_option
        self.repeat_num = repeat_num
        self.seed = seed
        self.class_weight_mode = class_weight_mode
        self.custom_class_weights = custom_class_weights
        self.class_map_fingerprint = class_map_fingerprint_value
        self.early_stopping_enabled = early_stopping_enabled
        self.early_stopping_patience = early_stopping_patience
        self.early_stopping_min_delta = early_stopping_min_delta
        self.criterion = nn.CrossEntropyLoss()
        self.optimizer_name = "adam"  # Default
        self.validate()
        self._normalize_runtime_device()

    def _normalize_runtime_device(self) -> None:
        """Fallback to CPU when a requested CUDA device is unusable."""
        if self.use_cpu:
            return

        usable, reason = is_cuda_device_usable(self.gpu_idx)
        if usable:
            return

        logger.warning(
            "Requested CUDA device %s is not usable; falling back to CPU: %s",
            self.gpu_idx,
            reason,
        )
        self.use_cpu = True
        self.gpu_idx = None

    def validate(self) -> None:
        """Validate training options.

        Raises:
            ValueError: If any option is invalid or not set.  When
                multiple problems exist, all are reported in a single
                semicolon-separated message.

        """
        errors: list[str] = []
        normalized_output_dir: str | None = None
        try:
            normalized_output_dir = _normalize_output_dir(self.output_dir)
        except ValueError:
            errors.append("Output directory not set")
        if (
            not isinstance(self.optim, type)
            or not issubclass(self.optim, torch.optim.Optimizer)
            or not isinstance(self.optim_params, dict)
        ):
            errors.append("Optimizer not set")
        if not isinstance(self.use_cpu, bool):
            errors.append("Device not set")
        if not self.use_cpu and self.gpu_idx is None:
            errors.append("Device not set")
        if not isinstance(self.evaluation_option, TrainingEvaluation):
            errors.append("Evaluation option not set")
        if not isinstance(self.early_stopping_enabled, bool):
            errors.append("Invalid early stopping setting")
        if self.early_stopping_enabled and (
            self.evaluation_option is TrainingEvaluation.LAST_EPOCH
        ):
            errors.append("Early stopping requires a validation evaluation option")
        try:
            mode = normalize_class_weight_mode(self.class_weight_mode)
            custom = (
                normalize_custom_class_weights(self.custom_class_weights)
                if mode is ClassWeightMode.CUSTOM
                else {}
            )
            if mode is not ClassWeightMode.OFF and (
                not is_canonical_class_map_fingerprint(self.class_map_fingerprint)
            ):
                errors.append("Training class map identity is required")
        except ValueError as exc:
            errors.append(str(exc))
            mode = ClassWeightMode.OFF
            custom = {}

        normalized: dict[str, int | float] = {}

        def normalize_value(
            key: str,
            message: str,
            normalizer: Callable[[str, Any], int | float],
            value: Any,
        ) -> None:
            try:
                normalized[key] = normalizer(key, value)
            except TrainingInputContractError:
                errors.append(message)

        if self.gpu_idx is not None:
            normalize_value(
                "gpu_idx",
                "Invalid gpu_idx",
                normalize_non_negative_integer,
                self.gpu_idx,
            )
        normalize_value(
            "epoch",
            "Invalid epoch (must be a positive integer)",
            normalize_positive_integer,
            self.epoch,
        )
        normalize_value(
            "bs",
            "Invalid batch size (must be a positive integer)",
            normalize_positive_integer,
            self.bs,
        )
        normalize_value(
            "lr",
            "Invalid learning rate (must be positive)",
            normalize_positive_finite_float,
            self.lr,
        )
        normalize_value(
            "checkpoint_epoch",
            "Invalid checkpoint epoch",
            normalize_non_negative_integer,
            self.checkpoint_epoch,
        )
        normalize_value(
            "repeat_num",
            "Invalid repeat number",
            normalize_positive_integer,
            self.repeat_num,
        )
        normalize_value(
            "early_stopping_patience",
            "Invalid early stopping patience",
            normalize_positive_integer,
            self.early_stopping_patience,
        )
        normalize_value(
            "early_stopping_min_delta",
            "Invalid early stopping minimum improvement",
            normalize_non_negative_finite_float,
            self.early_stopping_min_delta,
        )

        normalized_seed: int | None = None
        try:
            normalized_seed = self._normalize_seed(
                self.seed,
                repeat_num=(
                    int(normalized["repeat_num"])
                    if "repeat_num" in normalized
                    else None
                ),
            )
        except ValueError as exc:
            errors.append(str(exc))

        if errors:
            raise ValueError("; ".join(errors))

        if normalized_output_dir is None:
            raise ValueError("output_dir must be a non-empty path.")
        self.output_dir = normalized_output_dir
        self.epoch = int(normalized["epoch"])
        self.bs = int(normalized["bs"])
        self.lr = float(normalized["lr"])
        self.checkpoint_epoch = int(normalized["checkpoint_epoch"])
        self.repeat_num = int(normalized["repeat_num"])
        self.early_stopping_patience = int(normalized["early_stopping_patience"])
        self.early_stopping_min_delta = float(normalized["early_stopping_min_delta"])
        self.seed = normalized_seed
        self.class_weight_mode = mode
        self.custom_class_weights = custom
        if self.gpu_idx is not None:
            self.gpu_idx = int(normalized["gpu_idx"])

    @staticmethod
    def _normalize_seed(value: Any, *, repeat_num: int | None) -> int:
        if repeat_num is not None and repeat_num > MAX_TRAINING_SEED + 1:
            raise ValueError(
                "Invalid seed (base seed + repeat count - 1 must not exceed 4294967295)"
            )
        if value is None:
            repeat_count = repeat_num if repeat_num is not None else 1
            max_base_seed = MAX_TRAINING_SEED - (repeat_count - 1)
            return secrets.randbelow(max_base_seed + 1)
        if (
            type(value) is not int
            or not MIN_TRAINING_SEED <= value <= MAX_TRAINING_SEED
        ):
            raise ValueError(
                "Invalid seed (must be an integer between 0 and 4294967295)"
            )
        if repeat_num is not None and value > MAX_TRAINING_SEED - (repeat_num - 1):
            raise ValueError(
                "Invalid seed (base seed + repeat count - 1 must not exceed 4294967295)"
            )
        return value

    def get_seed_for_repeat(self, repeat_index: int) -> int:
        """Return the configured ``base_seed + repeat_index``."""
        if (
            type(repeat_index) is not int
            or repeat_index < 0
            or repeat_index >= self.repeat_num
        ):
            raise IndexError("repeat_index is outside the configured repeat range")
        if type(self.seed) is not int:
            raise RuntimeError("Training base seed is unavailable")
        return self.seed + repeat_index

    def get_configured_repeat_seeds(self) -> list[int]:
        """Return every effective seed derived from the configured base."""
        if type(self.seed) is not int:
            raise RuntimeError("Training base seed is unavailable")
        return [self.seed + repeat_index for repeat_index in range(self.repeat_num)]

    def get_optim(self, model: torch.nn.Module) -> torch.optim.Optimizer:
        """Create and return an optimizer instance for the given model.

        Args:
            model: The PyTorch model whose parameters will be optimized.

        Returns:
            An instantiated optimizer bound to the model's parameters.

        Raises:
            ValueError: If the optimizer or its parameters are not set.

        """
        if self.optim is None or self.optim_params is None:
            raise ValueError("Optimizer not set")
        return self.optim(params=model.parameters(), lr=self.lr, **self.optim_params)

    def get_optimizer_name_repr(self) -> str:
        """Return the optimizer class name as a string.

        Returns:
            The optimizer class name, or ``'None'`` if not set.

        """
        if self.optim is None:
            return "None"
        return self.optim.__name__

    def get_optim_name(self) -> str:
        """Alias for :meth:`get_optimizer_name_repr` for backward compatibility.

        Returns:
            The optimizer class name string.

        """
        return self.get_optimizer_name_repr()

    def get_optim_desc_str(self) -> str:
        """Return a formatted optimizer description string.

        Returns:
            A string formatted as ``'OptimizerName (param=value, ...)'``,
            or ``'None'`` if the optimizer is not set.

        """
        if self.optim is None or self.optim_params is None:
            return "None"
        return parse_optim_name(self.optim, self.optim_params)

    def get_optimizer_repr(self) -> str:
        """Return a formatted optimizer description string.

        Returns:
            A string formatted as ``'OptimizerName (param=value, ...)'``,
            or ``'None'`` if the optimizer is not set.

        """
        if self.optim is None or self.optim_params is None:
            return "None"
        return parse_optim_name(self.optim, self.optim_params)

    def get_device_name(self) -> str:
        """Return a human-readable device description string.

        Returns:
            A string describing the device (e.g., ``'cpu'`` or
            ``'0 - NVIDIA GeForce RTX 3090'``).

        """
        return parse_device_name(self.use_cpu, self.gpu_idx)

    def get_device(self) -> str:
        """Return the PyTorch device string (e.g., ``'cpu'`` or ``'cuda:0'``).

        Returns:
            The device identifier string used by PyTorch.

        """
        if self.use_cpu:
            return "cpu"
        return f"cuda:{self.gpu_idx}"

    def get_evaluation_option_repr(self) -> str:
        """Return a string representation of the model selection option.

        Returns:
            A string in the format ``'ClassName.MEMBER_NAME'``.

        """
        module_name = self.evaluation_option.__class__.__name__
        class_name = self.evaluation_option.name
        return f"{module_name}.{class_name}"

    def get_output_dir(self) -> str:
        """Return the output directory path.

        Returns:
            The path to the training output directory.

        """
        return self.output_dir


class TestOnlyOption(TrainingOption):
    """Training option subclass for test-only (inference) scenarios.

    Sets epoch, learning rate, and repeat count to zero/one defaults,
    using ``TrainingEvaluation.LAST_EPOCH`` as the evaluation strategy.

    Attributes:
        output_dir: Output directory.
        use_cpu: Whether to use CPU.
        gpu_idx: GPU device index.
        bs: Batch size.

    """

    __test__ = False  # Not a test case

    def __init__(self, output_dir: str, use_cpu: bool, gpu_idx: int, bs: int):
        """Initialize test-only options.

        Args:
            output_dir: Directory path for saving outputs.
            use_cpu: Whether to use CPU for inference.
            gpu_idx: GPU device index.
            bs: Batch size for inference.

        """
        super().__init__(
            output_dir,
            None,
            None,
            use_cpu,
            gpu_idx,
            0,
            bs,
            0,
            0,
            TrainingEvaluation.LAST_EPOCH,
            1,
        )
        self.validate()

    def validate(self) -> None:
        """Validate test-only options and their fixed runtime semantics.

        Raises:
            ValueError: If any option is invalid or not set

        """
        errors: list[str] = []
        normalized_output_dir: str | None = None
        try:
            normalized_output_dir = _normalize_output_dir(self.output_dir)
        except ValueError:
            errors.append("Output directory not set")
        if not isinstance(self.use_cpu, bool):
            errors.append("Device not set")
        if not self.use_cpu and self.gpu_idx is None:
            errors.append("Device not set")

        normalized_gpu_idx: int | None = None
        if self.gpu_idx is not None:
            try:
                normalized_gpu_idx = normalize_non_negative_integer(
                    "gpu_idx",
                    self.gpu_idx,
                )
            except TrainingInputContractError:
                errors.append("Invalid gpu_idx")
        try:
            normalized_batch_size = normalize_positive_integer("bs", self.bs)
        except TrainingInputContractError:
            normalized_batch_size = 0
            errors.append("Invalid batch size")

        fixed_integer_fields = (
            ("epoch", self.epoch, 0),
            ("checkpoint_epoch", self.checkpoint_epoch, 0),
            ("repeat_num", self.repeat_num, 1),
        )
        normalized_fixed: dict[str, int] = {}
        for field, value, expected in fixed_integer_fields:
            try:
                normalized_value = normalize_non_negative_integer(field, value)
            except TrainingInputContractError:
                errors.append(f"Invalid {field}")
                continue
            if normalized_value != expected:
                errors.append(f"Invalid {field}")
                continue
            normalized_fixed[field] = normalized_value

        try:
            normalized_learning_rate = normalize_non_negative_finite_float(
                "lr",
                self.lr,
            )
        except TrainingInputContractError:
            normalized_learning_rate = 0.0
            errors.append("Invalid lr")
        else:
            if normalized_learning_rate != 0:
                errors.append("Invalid lr")

        if self.optim is not None or self.optim_params is not None:
            errors.append("Optimizer must not be set for test-only mode")
        if self.evaluation_option is not TrainingEvaluation.LAST_EPOCH:
            errors.append("Invalid evaluation option for test-only mode")

        if errors:
            raise ValueError("; ".join(errors))

        if normalized_output_dir is None:
            raise ValueError("output_dir must be a non-empty path.")
        self.output_dir = normalized_output_dir
        self.epoch = normalized_fixed["epoch"]
        self.bs = normalized_batch_size
        self.lr = normalized_learning_rate
        self.checkpoint_epoch = normalized_fixed["checkpoint_epoch"]
        self.repeat_num = normalized_fixed["repeat_num"]
        if self.gpu_idx is not None:
            self.gpu_idx = normalized_gpu_idx

    def get_optim(self, model):
        """Return ``None`` since test-only mode does not use an optimizer.

        Args:
            model: Unused. Present for interface compatibility.

        Returns:
            ``None``.

        """
        return

    def get_optimizer_name_repr(self):
        """Return a placeholder string for the optimizer name.

        Returns:
            The string ``'-'``.

        """
        return "-"

    def get_optim_desc_str(self):
        """Return a placeholder string for the optimizer description.

        Returns:
            The string ``'-'``.

        """
        return "-"

    def get_device_name(self):
        """Return a human-readable device description string.

        Returns:
            A string describing the device.

        """
        return parse_device_name(self.use_cpu, self.gpu_idx)

    def get_device(self):
        """Return the PyTorch device string.

        Returns:
            The device identifier string (e.g., ``'cpu'`` or ``'cuda:0'``).

        """
        if self.use_cpu:
            return "cpu"
        return f"cuda:{self.gpu_idx}"

    def get_evaluation_option_repr(self):
        """Return a string representation of the evaluation option.

        Returns:
            A string in the format ``'ClassName.MEMBER_NAME'``.

        """
        module_name = self.evaluation_option.__class__.__name__
        class_name = self.evaluation_option.name
        return f"{module_name}.{class_name}"

    def get_output_dir(self):
        """Return the output directory path.

        Returns:
            The path to the output directory.

        """
        return self.output_dir
