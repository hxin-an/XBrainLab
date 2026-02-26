"""Training record module for per-epoch statistics, checkpoints, and figures."""

from __future__ import annotations

import os
import time
from typing import Any

import torch
from matplotlib import pyplot as plt
from matplotlib.figure import Figure

from XBrainLab.backend.utils.logger import logger

from ...dataset import Dataset
from ...training import TrainingOption
from ...utils import get_random_state, set_random_state
from .eval import EvalRecord, calculate_confusion
from .key import RecordKey, TrainRecordKey


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
        best_test_accuracy_model: :class:`torch.nn.Module` | None
            Model with best test accuracy, set during training
        best_test_auc_model: :class:`torch.nn.Module` | None
            Model with best test auc, set during training
        train: dict
            Stores the statistics of each epoch, including loss, accuracy, auc,
            time used and learning rate
        val: dict
            Stores the statistics of each epoch, including loss, auc and accuracy
        test: dict
            Stores the statistics of each epoch, including loss, auc and accuracy
        best_record: dict
            Stores the statistics of the best model, including best validation loss,
            best validation auc, best validation accuracy, best test auc,
            best test accuracy, and their corresponding epoch
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
    ):
        """Initialize a training record.

        Sets up the model, optimizer, criterion, record dictionaries, and
        output directory. Loads any existing data from disk if available.

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
        self.model = model
        self.optim = self.option.get_optim(model)
        self.criterion = self.option.criterion
        self.eval_record: EvalRecord | None = None
        for key in RecordKey():
            setattr(self, "best_val_" + key + "_model", None)
            setattr(self, "best_test_" + key + "_model", None)
        self.train: dict[str, list[float]] = {i: [] for i in TrainRecordKey()}
        self.val: dict[str, list[float]] = {i: [] for i in RecordKey()}
        self.test: dict[str, list[float]] = {i: [] for i in RecordKey()}
        self.best_record: dict[str, Any] = {}
        for record_type in ["val", "test"]:
            for key in RecordKey():
                self.best_record[f"best_{record_type}_{key}"] = -1
                self.best_record[f"best_{record_type}_{key}_epoch"] = None
            self.best_record[f"best_{record_type}_" + RecordKey.LOSS] = torch.inf

        self.epoch = 0
        self.target_path: str | None = None
        self.init_dir()
        self.random_state = get_random_state()
        self.start_timestamp: float | None = None
        self.end_timestamp: float | None = None

        # Load existing data if available
        self.load()

    def init_dir(self) -> None:
        """Initialize the output directory for saving checkpoints and records.

        Creates the directory tree:
        ``output_dir / dataset_name / model_planid / repeat``.
        """
        record_name = self.dataset.get_name()
        repeat_name = self.get_name()

        # Construct unique path: output / dataset / model_timestamp / repeat
        model_name = self.model.__class__.__name__
        unique_id = f"{model_name}_{self.plan_id}" if self.plan_id else model_name

        target_path = os.path.join(
            self.option.get_output_dir(),
            record_name,
            unique_id,
            repeat_name,
        )

        # Do NOT backup automatically. Just ensure it exists.
        os.makedirs(target_path, exist_ok=True)
        self.target_path = target_path

    def resume(self) -> None:
        """Resume training by restoring the saved random state.

        Also sets the start timestamp if this is the first resume.
        """
        set_random_state(self.random_state)
        if self.start_timestamp is None:
            self.start_timestamp = time.time()

    def pause(self) -> None:
        """Pause training by saving the current random state and timestamp."""
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
        return self.model.to(device)

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
        while len(arr) < self.epoch:
            arr.append(None)
        if len(arr) > self.epoch:
            arr[self.epoch] = val
        elif len(arr) == self.epoch:
            arr.append(val)

    def update(self, update_type: str, test_result: dict[str, float]) -> None:
        """Append metrics for the current epoch and update best-model tracking.

        For each metric key in ``test_result``, appends the value to the
        corresponding record list and updates the best model state dict if
        the new value surpasses the previous best.

        Args:
            update_type: Record type to update (``'val'`` or ``'test'``).
            test_result: Dictionary mapping :class:`RecordKey` values to
                metric values for the current epoch.

        """
        for key, value in test_result.items():
            self.append_record(value, getattr(self, update_type)[key])
            should_update = False
            if "loss" in key:
                if value <= self.best_record["best_" + update_type + "_" + key]:
                    should_update = True
            elif value >= self.best_record["best_" + update_type + "_" + key]:
                should_update = True
            if should_update:
                self.best_record["best_" + update_type + "_" + key] = value
                self.best_record["best_" + update_type + "_" + key + "_epoch"] = (
                    self.get_epoch()
                )
                setattr(
                    self,
                    "best_" + update_type + "_" + key + "_model",
                    {k: v.cpu().clone() for k, v in self.model.state_dict().items()},
                )

    def update_eval(self, test_result: dict[str, float]) -> None:
        """Append validation statistics and update the best validation model.

        Args:
            test_result: Dictionary of validation metrics for the current epoch.

        """
        self.update("val", test_result)

    def update_test(self, test_result: dict[str, float]) -> None:
        """Append test statistics and update the best test model.

        Args:
            test_result: Dictionary of test metrics for the current epoch.

        """
        self.update("test", test_result)

    def update_train(self, test_result: dict[str, float]) -> None:
        """Append training statistics for the current epoch.

        Args:
            test_result: Dictionary of training metrics (loss, accuracy, AUC).

        """
        for key, value in test_result.items():
            self.append_record(value, self.train[key])

    def update_statistic(self, statistic: dict[str, float]) -> None:
        """Append extra statistics (e.g., learning rate) for the current epoch.

        Args:
            statistic: Dictionary of statistic values to record.

        """
        for key, value in statistic.items():
            self.append_record(value, self.train[key])

    def step(self) -> None:
        """Advance the epoch counter by one."""
        self.epoch += 1

    def set_eval_record(self, eval_record: EvalRecord) -> None:
        """Set the evaluation record after training completes.

        Args:
            eval_record: The :class:`EvalRecord` containing final evaluation results.

        """
        self.eval_record = eval_record

    def export_checkpoint(self) -> None:
        """Save the current training state, best models, and evaluation record to disk.

        Exports the model state dict, record statistics, best model state dicts,
        and the evaluation record (if available) to :attr:`target_path`.
        """
        epoch = len(self.train[RecordKey.LOSS])

        if not self.target_path:
            return

        if self.eval_record:
            self.eval_record.export(self.target_path)

        for best_type in ["val", "test"]:
            for key in RecordKey():
                full_key = "best_" + best_type + "_" + key + "_model"
                model = getattr(self, full_key)
                if model:
                    torch.save(model, os.path.join(self.target_path, full_key))

        if not self.target_path:
            return
        fname = f"Epoch-{epoch}-model"
        torch.save(self.model.state_dict(), os.path.join(self.target_path, fname))
        record = {
            "train": self.train,
            "val": self.val,
            "test": self.test,
            "best_record": self.best_record,
            "seed": self.seed,
        }
        torch.save(record, os.path.join(self.target_path, "record"))

    def load(self) -> None:
        """Load a previously saved training record from disk.

        Restores training statistics, best records, seed, and evaluation record
        from :attr:`target_path` if files exist.
        """
        if not self.target_path or not os.path.exists(self.target_path):
            return

        # Load record dict
        record_path = os.path.join(self.target_path, "record")
        if os.path.exists(record_path):
            try:
                # SECURITY: weights_only=False required because record
                # contains non-tensor objects (dicts, lists).  Only load
                # files from trusted sources.
                data = torch.load(record_path, weights_only=False)
                self.train = data["train"]
                self.val = data["val"]
                self.test = data["test"]
                self.best_record = data["best_record"]
                self.seed = data["seed"]
                # Restore epoch from train loss length
                self.epoch = len(self.train[RecordKey.LOSS])
            except Exception as e:
                logger.error("Failed to load TrainRecord stats: %s", e, exc_info=True)

        # Load EvalRecord
        self.eval_record = EvalRecord.load(self.target_path)

    def get_model_output(self) -> str:
        """Return a formatted string summary of the training history.

        Returns:
            A multi-line string containing epoch count, best performance
            metrics, and last-epoch statistics.

        """
        lines = []
        lines.append(f"=== Training Summary for {self.get_name()} ===")
        lines.append(f"Total Epochs: {self.epoch}")

        # Best Performance
        lines.append("\n[Best Performance]")
        for key, val in self.best_record.items():
            if "epoch" in key:
                continue
            epoch_key = key + "_epoch"
            epoch_val = self.best_record.get(epoch_key, "-")
            lines.append(f"  {key}: {val:.4f} (Epoch {epoch_val})")

        # Last Epoch Stats
        lines.append("\n[Last Epoch Statistics]")
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
        if fig is None:
            fig = plt.figure(figsize=figsize, dpi=dpi)
        plt.clf()

        training_loss_list = self.train[RecordKey.LOSS]
        val_loss_list = self.val[RecordKey.LOSS]
        test_loss_list = self.test[RecordKey.LOSS]
        if (
            len(training_loss_list) == 0
            and len(val_loss_list) == 0
            and len(test_loss_list) == 0
        ):
            return None

        if len(training_loss_list) > 0:
            plt.plot(training_loss_list, "g", label="Training loss")
        if len(val_loss_list) > 0:
            plt.plot(val_loss_list, "b", label="validation loss")
        if len(test_loss_list) > 0:
            plt.plot(test_loss_list, "r", label="testing loss")
        plt.title("Training loss")
        plt.xlabel("Epochs")
        plt.ylabel("Loss")
        _ = plt.legend(loc="center left")

        return fig

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
        if fig is None:
            fig = plt.figure(figsize=figsize, dpi=dpi)
        plt.clf()

        training_acc_list = self.train[RecordKey.ACC]
        val_acc_list = self.val[RecordKey.ACC]
        test_acc_list = self.test[RecordKey.ACC]
        if (
            len(training_acc_list) == 0
            and len(val_acc_list) == 0
            and len(test_acc_list) == 0
        ):
            return None

        if len(training_acc_list) > 0:
            plt.plot(training_acc_list, "g", label="Training accuracy")
        if len(val_acc_list) > 0:
            plt.plot(val_acc_list, "b", label="validation accuracy")
        if len(test_acc_list) > 0:
            plt.plot(test_acc_list, "r", label="testing accuracy")
        plt.title("Training Accuracy")
        plt.xlabel("Epochs")
        plt.ylabel("Accuracy (%)")
        _ = plt.legend(loc="upper left")

        return fig

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
        if fig is None:
            fig = plt.figure(figsize=figsize, dpi=dpi)
        plt.clf()

        training_auc_list = self.train[RecordKey.AUC]
        val_auc_list = self.val[RecordKey.AUC]
        test_auc_list = self.test[RecordKey.AUC]
        if (
            len(training_auc_list) == 0
            and len(val_auc_list) == 0
            and len(test_auc_list) == 0
        ):
            return None

        if len(training_auc_list) > 0:
            plt.plot(training_auc_list, "g", label="Training AUC")
        if len(val_auc_list) > 0:
            plt.plot(val_auc_list, "b", label="validation AUC")
        if len(test_auc_list) > 0:
            plt.plot(test_auc_list, "r", label="testing AUC")
        plt.title("Training AUC")
        plt.xlabel("Epochs")
        plt.ylabel("AUC")
        _ = plt.legend(loc="upper left")

        return fig

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
        if fig is None:
            fig = plt.figure(figsize=figsize, dpi=dpi)
        plt.clf()

        lr_list = self.train[TrainRecordKey.LR]
        if len(lr_list) == 0:
            return None

        plt.plot(lr_list, "g")
        plt.title("Learning Rate")
        plt.xlabel("Epochs")
        plt.ylabel("lr")
        return fig

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
        if fig is None:
            fig = plt.figure(figsize=figsize, dpi=dpi)
        plt.clf()
        if not self.eval_record:
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

        ax = fig.add_subplot(111)
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
        cbar = fig.colorbar(res)
        cbar.ax.yaxis.set_tick_params(color="#cccccc")
        plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color="#cccccc")

        # Ticks
        labels = [self.dataset.get_epoch_data().label_map[i] for i in range(class_num)]
        plt.xticks(
            range(class_num),
            labels,
            rotation=0,
            ha="center",
        )  # Horizontal labels
        plt.yticks(range(class_num), labels, va="center")  # Vertically centered

        # Styling
        ax.tick_params(axis="x", colors="#cccccc")
        ax.tick_params(axis="y", colors="#cccccc")
        for spine in ax.spines.values():
            spine.set_edgecolor("#444444")

        # Ensure tight layout handles labels correctly
        fig.tight_layout()

        return fig

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
