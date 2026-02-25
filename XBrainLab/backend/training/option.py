"""Training option and configuration classes for model training."""

from enum import Enum

import torch
from torch import nn


class TrainingEvaluation(Enum):
    """Enumeration of model selection strategies for evaluation.

    Attributes:
        VAL_LOSS: Select model with the best (lowest) validation loss.
        TEST_AUC: Select model with the best testing AUC.
        TEST_ACC: Select model with the best testing accuracy.
        LAST_EPOCH: Use the model from the last training epoch.
    """

    VAL_LOSS = "Best validation loss"
    TEST_AUC = "Best testing AUC"
    TEST_ACC = "Best testing performance"
    LAST_EPOCH = "Last Epoch"


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
        self.criterion = nn.CrossEntropyLoss()
        self.optimizer_name = "adam"  # Default
        self.validate()

    def validate(self) -> None:
        """Validate training options

        Raises:
            ValueError: If any option is invalid or not set
        """
        reason = None
        if self.output_dir is None:
            reason = "Output directory not set"
        if self.optim is None or self.optim_params is None:
            reason = "Optimizer not set"
        if self.use_cpu is None:
            reason = "Device not set"
        if not self.use_cpu and self.gpu_idx is None:
            reason = "Device not set"
        if self.evaluation_option is None:
            reason = "Evaluation option not set"

        def check_num(i):
            """Return True if i is not a number"""
            try:
                float(i)
            except Exception:
                return True
            else:
                return False

        if self.gpu_idx is not None and check_num(self.gpu_idx):
            reason = "Invalid gpu_idx"
        if check_num(self.epoch):
            reason = "Invalid epoch"
        if check_num(self.bs):
            reason = "Invalid batch size"
        if check_num(self.lr):
            reason = "Invalid learning rate"
        if check_num(self.checkpoint_epoch):
            reason = "Invalid checkpoint epoch"
        if check_num(self.repeat_num) or int(self.repeat_num) <= 0:
            reason = "Invalid repeat number"

        if reason:
            raise ValueError(reason)

        self.epoch = int(self.epoch)
        self.bs = int(self.bs)
        self.lr = float(self.lr)
        self.checkpoint_epoch = int(self.checkpoint_epoch)
        self.repeat_num = int(self.repeat_num)
        if self.gpu_idx is not None:
            self.gpu_idx = int(self.gpu_idx)

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
        """Validate test-only options

        Raises:
            ValueError: If any option is invalid or not set
        """
        reason = None
        if self.output_dir is None:
            reason = "Output directory not set"
        if self.use_cpu is None:
            reason = "Device not set"
        if not self.use_cpu and self.gpu_idx is None:
            reason = "Device not set"

        def check_num(i):
            """Return True if i is not a number"""
            try:
                float(i)
            except Exception:
                return True
            else:
                return False

        if self.gpu_idx is not None and check_num(self.gpu_idx):
            reason = "Invalid gpu_idx"
        if check_num(self.bs):
            reason = "Invalid batch size"

        if reason:
            raise ValueError(reason)

        self.epoch = int(self.epoch)
        self.bs = int(self.bs)
        self.repeat_num = int(self.repeat_num)
        if self.gpu_idx is not None:
            self.gpu_idx = int(self.gpu_idx)

    def get_optim(self, model):
        """Return ``None`` since test-only mode does not use an optimizer.

        Args:
            model: Unused. Present for interface compatibility.

        Returns:
            ``None``.
        """
        return None

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
